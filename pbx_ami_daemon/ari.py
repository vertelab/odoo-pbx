# -*- coding: utf-8 -*-
"""
pbx-ari — Asterisk ARI client (Stasis) for pbx_ami_daemon.

Level 2 (smart receptionist): AI coworker for real-time dialog in the call.
Connects to Asterisk ARI (port 8089 websocket + 8088 REST), listens to
Stasis events and performs actions (answer, play, redirect).

Turn-based dialog (v1):
  StasisStart -> answer -> record (silence-detect) -> STT (pbx-transcriber,
  fors) -> LLM (Odoo /pbx/ai/dialog) -> TTS (Odoo, is_asr provider) ->
  play_uri (TTS audio served by the daemon on :8081) -> record again ...
  DTMF # = hang up, DTMF 0 = transfer to a human.

No new GitHub dependency — builds directly on aiohttp (the daemon is
already async).
"""

import base64
import json
import logging
import os
import tempfile
import uuid
from typing import Optional

logger = logging.getLogger("pbx_ari")


class ARIChannel:
    """An active Stasis channel (call)."""

    def __init__(self, client: "ARIClient", channel_id: str, data: dict = None):
        self.client = client
        self.channel_id = channel_id
        self.data = data or {}
        self.script = data.get("dialplan", {}).get("exten", "")
        self.caller = data.get("caller", {}) or {}
        self.caller_num = self.caller.get("number", "")

    async def answer(self):
        return await self.client.rest("POST", f"/channels/{self.channel_id}/answer")

    async def play(self, media: str, lang: str = "en"):
        """Play audio. media: 'sound:name' or a URL to TTS audio."""
        return await self.client.rest(
            "POST",
            f"/channels/{self.channel_id}/play",
            json={"media": [media], "lang": lang},
        )

    async def play_uri(self, url: str):
        """Play an audio URL (e.g. TTS-generated mp3 from Odoo)."""
        return await self.client.rest(
            "POST",
            f"/channels/{self.channel_id}/play",
            json={"media": [url]},
        )

    async def redirect(self, context: str, exten: str, priority: int = 1):
        """Transfer the call (e.g. to a queue/extension)."""
        return await self.client.rest(
            "POST",
            f"/channels/{self.channel_id}/redirect",
            json={"context": context, "exten": exten, "priority": priority},
        )

    async def hangup(self):
        return await self.client.rest(
            "DELETE", f"/channels/{self.channel_id}"
        )

    async def record(self, name: str, format: str = "wav",
                     max_silence: int = 2, max_duration: int = 15):
        """Start recording with silence detection (turn)."""
        return await self.client.rest(
            "POST",
            f"/channels/{self.channel_id}/record",
            json={
                "name": name,
                "format": format,
                "max_silence_seconds": max_silence,
                "max_duration_seconds": max_duration,
                "beep": False,
            },
        )

    async def stop_recording(self, name: str):
        return await self.client.rest("DELETE", f"/recordings/live/{name}")


class ARIClient:
    """ARI client: REST (8088) + WebSocket events (8089)."""

    def __init__(self, base_url: str, ws_url: str, app: str,
                 api_key: str, on_stasis_start=None, on_dtmf=None,
                 on_stasis_end=None, on_recording_finished=None,
                 on_playback_finished=None):
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url
        self.app = app
        self.api_key = api_key
        self.on_stasis_start = on_stasis_start
        self.on_dtmf = on_dtmf
        self.on_stasis_end = on_stasis_end
        self.on_recording_finished = on_recording_finished
        self.on_playback_finished = on_playback_finished
        self.channels: dict[str, ARIChannel] = {}

    async def rest(self, method: str, path: str, json: Optional[dict] = None):
        """Call the ARI REST API."""
        import aiohttp.web  # noqa: F401  (ensures aiohttp is imported)
        import aiohttp
        url = f"{self.base_url}/ari{path}"
        headers = {"Authorization": f"Basic {self._basic_auth()}"}
        async with aiohttp.ClientSession() as session:
            async with session.request(
                    method, url, json=json, headers=headers) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning("ARI %s %s → %s: %s",
                                   method, path, resp.status, body[:200])
                    return None
                if resp.status == 204:
                    return None
                return await resp.json()

    async def get_recording_file(self, name: str) -> bytes:
        """Fetch a recorded file as bytes (wav)."""
        import aiohttp
        url = f"{self.base_url}/ari/recordings/{name}/file"
        headers = {"Authorization": f"Basic {self._basic_auth()}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("Get recording %s → %s", name, resp.status)
                    return b""
                return await resp.read()

    def _basic_auth(self) -> str:
        import base64
        return base64.b64encode(self.api_key.encode()).decode()

    async def run(self):
        """Listen for ARI WebSocket events (Stasis)."""
        import aiohttp
        url = (f"{self.ws_url}/ari/events?api_key={self.api_key}"
               f"&app={self.app}")
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url) as ws:
                logger.info("ARI connected: %s app=%s", url, self.app)
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            await self._handle_event(json.loads(msg.data))
                        except Exception as e:
                            logger.warning("ARI event parse failed: %s", e)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("ARI websocket error: %s", msg.data)
                        break

    async def _handle_event(self, event: dict):
        etype = event.get("type", "")
        channel = event.get("channel") or {}

        if etype == "StasisStart":
            ch = ARIChannel(self, channel.get("id", ""), channel)
            self.channels[ch.channel_id] = ch
            if self.on_stasis_start:
                await self.on_stasis_start(ch, event)
        elif etype == "ChannelDtmfReceived":
            digit = event.get("digit", "")
            if self.on_dtmf:
                await self.on_dtmf(self.channels.get(
                    channel.get("id", "")), digit, event)
        elif etype == "StasisEnd":
            ch = self.channels.pop(channel.get("id", ""), None)
            if ch and self.on_stasis_end:
                await self.on_stasis_end(ch, event)
        elif etype == "RecordingFinished":
            rec_name = (event.get("recording") or {}).get("name", "")
            ch = self.channels.get(channel.get("id", ""))
            if ch and self.on_recording_finished:
                await self.on_recording_finished(ch, rec_name, event)
        elif etype == "PlaybackFinished":
            ch = self.channels.get(channel.get("id", ""))
            if ch and self.on_playback_finished:
                await self.on_playback_finished(ch, event)


# ──────────────────────────────────────────────────────────────────
# Receptionist logic — turn-based dialog (STT -> LLM -> TTS -> playback)
# ──────────────────────────────────────────────────────────────────


class TTSAudioServer:
    """Serves TTS audio over HTTP so ARI can play it via play_uri."""

    def __init__(self, port: int = 8081, ttl: int = 300):
        self.port = port
        self.ttl = ttl
        self._files: dict[str, str] = {}
        self._runner = None

    async def start(self):
        import aiohttp.web
        app = aiohttp.web.Application()
        app.router.add_get("/tts/{name}", self._serve)
        app.router.add_get("/health", self._health)
        self._runner = aiohttp.web.AppRunner(app)
        await self._runner.setup()
        site = aiohttp.web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("TTS server on :%s (play_uri http://localhost:%s/tts/...)",
                    self.port, self.port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def _health(self, request):
        import aiohttp.web
        return aiohttp.web.json_response({"status": "ok", "service": "pbx-tts"})

    def add(self, audio: bytes, suffix: str = ".mp3") -> str:
        """Store audio, return the URI part /tts/<name>."""
        name = f"tts-{uuid.uuid4().hex}{suffix}"
        path = os.path.join(tempfile.gettempdir(), name)
        with open(path, "wb") as f:
            f.write(audio)
        self._files[name] = path
        return f"/tts/{name}"

    async def _serve(self, request):
        import aiohttp.web
        name = request.match_info["name"]
        path = self._files.get(name)
        if not path or not os.path.exists(path):
            return aiohttp.web.Response(status=404, text="not found")
        with open(path, "rb") as f:
            data = f.read()
        ctype = "audio/mpeg" if name.endswith(".mp3") else "audio/wav"
        return aiohttp.web.Response(body=data, content_type=ctype)


class Receptionist:
    """Turn-based dialog: record -> STT -> Odoo LLM -> TTS -> playback.

    The dialog runs in Odoo (ai.coworker) via /pbx/ai/dialog; STT locally on
    pbx-transcriber (fors). TTS audio is served by TTSAudioServer and played
    via ARI play_uri.
    """

    def __init__(self, client: ARIClient, odoo_url: str = "",
                 webhook_token: str = "", coworker_id: int = 0,
                 transcriber_url: str = "http://localhost:8091",
                 tts_port: int = 8081, transfer_context: str = "",
                 transfer_exten: str = ""):
        self.client = client
        self.odoo_url = odoo_url.rstrip("/")
        self.webhook_token = webhook_token
        self.coworker_id = coworker_id
        self.transcriber_url = transcriber_url.rstrip("/")
        self.transfer_context = transfer_context
        self.transfer_exten = transfer_exten
        self.audio = TTSAudioServer(tts_port)
        self.conversations: dict[str, dict] = {}   # channel_id → state
        self.rec_names: dict[str, str] = {}         # recording → channel
        self._tts_urls: dict[str, str] = {}

    async def start_audio_server(self):
        await self.audio.start()

    async def stop_audio_server(self):
        await self.audio.stop()

    # ── Stasis events ──────────────────────────────────────────────

    async def on_stasis_start(self, channel: ARIChannel, event: dict):
        logger.info("StasisStart: %s (%s)", channel.channel_id,
                    channel.caller_num)
        state = {
            "history": [],
            "last_playback": None,
            "turn": 0,
            "ended": False,
        }
        self.conversations[channel.channel_id] = state
        await channel.answer()
        # First turn immediately (greeting via Odoo) — start recording
        await self._start_record(channel)

    async def on_dtmf(self, channel: ARIChannel, digit: str, event: dict):
        logger.info("DTMF %s: %s", channel.channel_id, digit)
        if not channel:
            return
        if digit == "#":
            await self._end_dialog(channel)
        elif digit == "0":
            await self._transfer_human(channel)

    async def on_stasis_end(self, channel: ARIChannel, event: dict):
        self.conversations.pop(channel.channel_id, None)
        logger.info("StasisEnd: %s", channel.channel_id)

    async def on_recording_finished(self, channel: ARIChannel, rec_name: str,
                                    event: dict):
        if not channel:
            return
        state = self.conversations.get(channel.channel_id)
        if not state or state.get("ended"):
            return
        await self._process_turn(channel, state, rec_name)

    async def on_playback_finished(self, channel: ARIChannel, event: dict):
        if not channel:
            return
        state = self.conversations.get(channel.channel_id)
        if not state or state.get("ended"):
            return
        # Reply done — listen for the next turn
        await self._start_record(channel)

    # ── Turn-logik ─────────────────────────────────────────────────

    async def _start_record(self, channel: ARIChannel):
        state = self.conversations.get(channel.channel_id)
        if not state or state.get("ended"):
            return
        state["turn"] += 1
        rec_name = f"pbx-turn-{channel.channel_id}-{state['turn']}"
        self.rec_names[rec_name] = channel.channel_id
        await channel.record(
            rec_name, max_silence=2, max_duration=15)

    async def _process_turn(self, channel: ARIChannel, state: dict,
                            rec_name: str):
        audio = await self.client.get_recording_file(rec_name)
        if not audio:
            logger.warning("Empty recording for %s", rec_name)
            await self._start_record(channel)
            return

        transcript = await self._stt(audio)
        if not transcript or not transcript.strip():
            # No spoken input — ask again
            await self._play_reply(channel, state, "I did not hear that, could you repeat?")
            return

        state["history"].append(f"user: {transcript.strip()}")

        reply = await self._dialog(state)
        await self._play_reply(channel, state, reply)

    async def _stt(self, audio: bytes) -> str:
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.transcriber_url}/transcribe?language=sv",
                        data=audio, headers={"Content-Type": "audio/wav"},
                        timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    data = await resp.json()
                    return data.get("transcript", "")
        except Exception as e:
            logger.error("STT failed: %s", e)
            return ""

    async def _dialog(self, state: dict) -> str:
        import aiohttp
        payload = {
            "tenant": "",
            "channel_id": "",
            "coworker_id": self.coworker_id,
            "history": list(state["history"]),
            "turn": "",
        }
        try:
            headers = {}
            if self.webhook_token:
                headers["Authorization"] = f"Bearer {self.webhook_token}"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.odoo_url}/pbx/ai/dialog",
                        json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    data = await resp.json()
                    if data.get("status") == "ok":
                        state["history"].append(
                            f"assistant: {data.get('reply', '')}")
                        tts_b64 = data.get("tts_audio_base64", "")
                        if tts_b64:
                            audio = base64.b64decode(tts_b64)
                            uri = self.audio.add(audio)
                            self._tts_urls[uri] = True
                        return data.get("reply", "…")
                    return "One moment, I will transfer you."
        except Exception as e:
            logger.error("Odoo dialog failed: %s", e)
            return "One moment, I will transfer you."

    async def _play_reply(self, channel: ARIChannel, state: dict, reply: str):
        # The TTS audio for the latest reply is at /tts/<uri> (set by _dialog).
        uri = next(iter(self._tts_urls.keys()), None)
        if uri:
            await channel.play_uri(f"http://localhost:{self.audio.port}{uri}")
            del self._tts_urls[uri]
        else:
            await channel.play("sound:hello-world")
        # on_playback_finished starts the next turn

    async def _end_dialog(self, channel: ARIChannel):
        state = self.conversations.get(channel.channel_id)
        if state:
            state["ended"] = True
        await channel.play("sound:goodbye")
        await channel.hangup()

    async def _transfer_human(self, channel: ARIChannel):
        state = self.conversations.get(channel.channel_id)
        if state:
            state["ended"] = True
        if self.transfer_context and self.transfer_exten:
            await channel.redirect(self.transfer_context, self.transfer_exten)
        else:
            await channel.play("sound:goodbye")
            await channel.hangup()


# ──────────────────────────────────────────────────────────────────
# CoworkerApp — AI-anknytning (Stasis(coworker,<id>))
#
# Generalized Receptionist: coworker_id comes from the Stasis args per
# call (several AI extensions may have different coworkers). The turn loops
# (record -> STT -> Odoo LLM -> TTS -> playback) + DTMF barge-in is the same
# mechanism. stt_mode=streaming is future work (external media); fallback
# to turn-based when streaming is unavailable.
# ──────────────────────────────────────────────────────────────────


class CoworkerApp:
    """Dialog for an AI extension: StasisStart(coworker,<id>)."""

    def __init__(self, client: ARIClient, odoo_url: str = "",
                 webhook_token: str = "",
                 transcriber_url: str = "http://localhost:8091",
                 tts_port: int = 8081, transfer_context: str = "",
                 transfer_exten: str = ""):
        self.client = client
        self.odoo_url = odoo_url.rstrip("/")
        self.webhook_token = webhook_token
        self.transcriber_url = transcriber_url.rstrip("/")
        self.transfer_context = transfer_context
        self.transfer_exten = transfer_exten
        self.audio = TTSAudioServer(tts_port)
        self.conversations: dict[str, dict] = {}
        self.rec_names: dict[str, str] = {}
        self._tts_urls: dict[str, str] = {}

    async def start_audio_server(self):
        await self.audio.start()

    async def stop_audio_server(self):
        await self.audio.stop()

    # ── Stasis events ──────────────────────────────────────────────

    async def on_stasis_start(self, channel: ARIChannel, event: dict):
        args = event.get("args") or []
        coworker_id = 0
        for arg in args:
            if str(arg).strip().isdigit():
                coworker_id = int(arg)
                break
        logger.info("CoworkerApp StasisStart: %s coworker=%s",
                    channel.channel_id, coworker_id)
        state = {
            "coworker_id": coworker_id,
            "history": [],
            "last_playback": None,
            "turn": 0,
            "ended": False,
        }
        self.conversations[channel.channel_id] = state
        await channel.answer()
        # First turn immediately — start recording (greeting via Odoo)
        await self._start_record(channel)

    async def on_dtmf(self, channel: ARIChannel, digit: str, event: dict):
        logger.info("CoworkerApp DTMF %s: %s", channel.channel_id, digit)
        if not channel:
            return
        if digit == "#":
            await self._end_dialog(channel)
        elif digit == "0":
            await self._transfer_human(channel)

    async def on_stasis_end(self, channel: ARIChannel, event: dict):
        self.conversations.pop(channel.channel_id, None)
        logger.info("CoworkerApp StasisEnd: %s", channel.channel_id)

    async def on_recording_finished(self, channel: ARIChannel, rec_name: str,
                                    event: dict):
        if not channel:
            return
        state = self.conversations.get(channel.channel_id)
        if not state or state.get("ended"):
            return
        await self._process_turn(channel, state, rec_name)

    async def on_playback_finished(self, channel: ARIChannel, event: dict):
        if not channel:
            return
        state = self.conversations.get(channel.channel_id)
        if not state or state.get("ended"):
            return
        # Reply done — listen for the next turn
        await self._start_record(channel)

    # ── Turn-logik ─────────────────────────────────────────────────

    async def _start_record(self, channel: ARIChannel):
        state = self.conversations.get(channel.channel_id)
        if not state or state.get("ended"):
            return
        state["turn"] += 1
        rec_name = f"pbx-cw-{channel.channel_id}-{state['turn']}"
        self.rec_names[rec_name] = channel.channel_id
        await channel.record(
            rec_name, max_silence=2, max_duration=15)

    async def _process_turn(self, channel: ARIChannel, state: dict,
                            rec_name: str):
        audio = await self.client.get_recording_file(rec_name)
        if not audio:
            logger.warning("Empty recording for %s", rec_name)
            await self._start_record(channel)
            return

        transcript = await self._stt(audio)
        if not transcript or not transcript.strip():
            await self._play_reply(
                channel, state, "I did not hear that, could you repeat?")
            return

        state["history"].append(f"user: {transcript.strip()}")

        reply = await self._dialog(state)
        await self._play_reply(channel, state, reply)

    async def _stt(self, audio: bytes) -> str:
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.transcriber_url}/transcribe?language=sv",
                        data=audio, headers={"Content-Type": "audio/wav"},
                        timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    data = await resp.json()
                    return data.get("transcript", "")
        except Exception as e:
            logger.error("STT failed: %s", e)
            return ""

    async def _dialog(self, state: dict) -> str:
        import aiohttp
        payload = {
            "tenant": "",
            "channel_id": "",
            "coworker_id": state.get("coworker_id", 0),
            "history": list(state["history"]),
            "turn": "",
        }
        try:
            headers = {}
            if self.webhook_token:
                headers["Authorization"] = f"Bearer {self.webhook_token}"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.odoo_url}/pbx/ai/dialog",
                        json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    data = await resp.json()
                    if data.get("status") == "ok":
                        state["history"].append(
                            f"assistant: {data.get('reply', '')}")
                        tts_b64 = data.get("tts_audio_base64", "")
                        if tts_b64:
                            audio = base64.b64decode(tts_b64)
                            uri = self.audio.add(audio)
                            self._tts_urls[uri] = True
                        return data.get("reply", "…")
                    return "One moment, I will transfer you."
        except Exception as e:
            logger.error("Odoo dialog failed: %s", e)
            return "One moment, I will transfer you."

    async def _play_reply(self, channel: ARIChannel, state: dict, reply: str):
        uri = next(iter(self._tts_urls.keys()), None)
        if uri:
            await channel.play_uri(f"http://localhost:{self.audio.port}{uri}")
            del self._tts_urls[uri]
        else:
            await channel.play("sound:hello-world")
        # on_playback_finished starts the next turn

    async def _end_dialog(self, channel: ARIChannel):
        state = self.conversations.get(channel.channel_id)
        if state:
            state["ended"] = True
        await channel.play("sound:goodbye")
        await channel.hangup()

    async def _transfer_human(self, channel: ARIChannel):
        state = self.conversations.get(channel.channel_id)
        if state:
            state["ended"] = True
        if self.transfer_context and self.transfer_exten:
            await channel.redirect(self.transfer_context, self.transfer_exten)
        else:
            await channel.play("sound:goodbye")
            await channel.hangup()
