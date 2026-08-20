# -*- coding: utf-8 -*-
"""
pbx-ari — Asterisk ARI-klient (Stasis) för pbx_ami_daemon.

Nivå 2 (smart receptionist): AI-coworker för realtidsdialog i samtalet.
Ansluter till Asterisk ARI (port 8089 websocket + 8088 REST), lyssnar
på Stasis-händelser och utför åtgärder (answer, play, redirect).

Turn-baserad dialog (v1):
  StasisStart → answer → record (silence-detect) → STT (pbx-transcriber,
  fors) → LLM (Odoo /pbx/ai/dialog) → TTS (Odoo, is_asr-provider) →
  play_uri (TTS-ljud serveras av daemonen på :8081) → record igen …
  DTMF # = avsluta, DTMF 0 = koppla till människa.

Inget nytt GitHub-beroende — bygger direkt på aiohttp (daemonen är
redan async).
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
    """En aktiv Stasis-kanal (samtal)."""

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
        """Spela upp ljud. media: 'sound:name' eller en URL till TTS-ljud."""
        return await self.client.rest(
            "POST",
            f"/channels/{self.channel_id}/play",
            json={"media": [media], "lang": lang},
        )

    async def play_uri(self, url: str):
        """Spela upp en ljud-URL (t.ex. TTS-genererad mp3 från Odoo)."""
        return await self.client.rest(
            "POST",
            f"/channels/{self.channel_id}/play",
            json={"media": [url]},
        )

    async def redirect(self, context: str, exten: str, priority: int = 1):
        """Koppla vidare samtalet (t.ex. till kö/anknytning)."""
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
        """Starta inspelning med tystnads-detektering (turn)."""
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
    """ARI-klient: REST (8088) + WebSocket-händelser (8089)."""

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
        """Anropa ARI REST API."""
        import aiohttp.web  # noqa: F401  (säkerställer att aiohttp är importerat)
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
        """Hämta inspelad fil som bytes (wav)."""
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
        """Lyssna på ARI WebSocket-händelser (Stasis)."""
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
# Receptionist-logik — turn-baserad dialog (STT → LLM → TTS → playback)
# ──────────────────────────────────────────────────────────────────


class TTSAudioServer:
    """Serverar TTS-ljud över HTTP så ARI kan spela via play_uri."""

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

    async def _health(self, request):
        import aiohttp.web
        return aiohttp.web.json_response({"status": "ok", "service": "pbx-tts"})
        self._runner = aiohttp.web.AppRunner(app)
        await self._runner.setup()
        site = aiohttp.web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("TTS-server på :%s (play_uri http://localhost:%s/tts/...)",
                    self.port, self.port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    def add(self, audio: bytes, suffix: str = ".mp3") -> str:
        """Lagra ljud, returnera URI-delen /tts/<name>."""
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
    """Turn-baserad dialog: record → STT → Odoo-LLM → TTS → playback.

    Dialogen körs i Odoo (ai.coworker) via /pbx/ai/dialog; STT lokalt på
    pbx-transcriber (fors). TTS-ljud serveras av TTSAudioServer och spelas
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

    # ── Stasis-händelser ───────────────────────────────────────────

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
        # Första turn direkt (hälsning via Odoo) — starta inspelning
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
        # Svar klart — lyssna på nästa tur
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
            logger.warning("Tom inspelning för %s", rec_name)
            await self._start_record(channel)
            return

        transcript = await self._stt(audio)
        if not transcript or not transcript.strip():
            # Ingen talad input — fråga igen
            await self._play_reply(channel, state, "Jag hörde inte, kan du upprepa?")
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
                    return "Ett ögonblick, jag kopplar dig vidare."
        except Exception as e:
            logger.error("Odoo dialog failed: %s", e)
            return "Ett ögonblick, jag kopplar dig vidare."

    async def _play_reply(self, channel: ARIChannel, state: dict, reply: str):
        # TTS-ljudet för senaste svaret ligger på /tts/<uri> (satt av _dialog).
        uri = next(iter(self._tts_urls.keys()), None)
        if uri:
            await channel.play_uri(f"http://localhost:{self.audio.port}{uri}")
            del self._tts_urls[uri]
        else:
            await channel.play("sound:hello-world")
        # on_playback_finished startar nästa turn

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
