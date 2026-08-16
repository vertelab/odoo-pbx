# -*- coding: utf-8 -*-
"""
pbx-ari — Asterisk ARI-klient (Stasis) för pbx_ami_daemon.

Nivå 2 (smart receptionist): AI-coworker för realtidsdialog i samtalet.
Ansluter till Asterisk ARI (port 8089 websocket + 8088 REST), lyssnar
på Stasis-händelser och utför åtgärder (answer, play, redirect).

Inget nytt GitHub-beroende — bygger direkt på aiohttp (daemonen är
redan async).
"""

import json
import logging
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

    async def record(self, name: str, format: str = "wav"):
        """Starta inspelning (transkription i efterhand)."""
        return await self.client.rest(
            "POST",
            f"/channels/{self.channel_id}/record",
            json={"name": name, "format": format},
        )


class ARIClient:
    """ARI-klient: REST (8088) + WebSocket-händelser (8089)."""

    def __init__(self, base_url: str, ws_url: str, app: str,
                 api_key: str, on_stasis_start=None, on_dtmf=None,
                 on_stasis_end=None):
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url
        self.app = app
        self.api_key = api_key
        self.on_stasis_start = on_stasis_start
        self.on_dtmf = on_dtmf
        self.on_stasis_end = on_stasis_end
        self.channels: dict[str, ARIChannel] = {}

    async def rest(self, method: str, path: str, json: Optional[dict] = None):
        """Anropa ARI REST API."""
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
                            event = json.loads(msg.data)
                            await self._handle_event(event)
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


# ──────────────────────────────────────────────────────────────────
# Receptionist-logik (kopplar ARI → AI-coworker via Odoo-webhook)
# ──────────────────────────────────────────────────────────────────


class Receptionist:
    """Smart receptionist: STT-chunks → LLM → TTS → playback.

    Dialogen körs i Odoo (ai.coworker "PBX Receptionist") — detta lager
    dirigerar ljudet: inspelning → webhook (STT) → svarstext →
    TTS-URL → ARI-playback → ev. redirect.
    """

    def __init__(self, client: ARIClient, odoo_url: str = "",
                 webhook_token: str = "", coworker_id: int = 0):
        self.client = client
        self.odoo_url = odoo_url.rstrip("/")
        self.webhook_token = webhook_token
        self.coworker_id = coworker_id
        self.conversations: dict[str, list[dict]] = {}

    async def on_stasis_start(self, channel: ARIChannel, event: dict):
        logger.info("StasisStart: %s (%s)", channel.channel_id,
                    channel.caller_num)
        await channel.answer()
        await channel.play("sound:hello-world")
        self.conversations[channel.channel_id] = []

    async def on_dtmf(self, channel: ARIChannel, digit: str, event: dict):
        logger.info("DTMF %s: %s", channel.channel_id, digit)
        if digit == "#":
            await self._end_dialog(channel)
        else:
            await channel.play(f"sound:digits/{digit}")

    async def on_stasis_end(self, channel: ARIChannel, event: dict):
        self.conversations.pop(channel.channel_id, None)
        logger.info("StasisEnd: %s", channel.channel_id)

    async def _end_dialog(self, channel: ARIChannel):
        """Avsluta dialogen — koppla till kö/anknytning enligt konfig."""
        await channel.play("sound:goodbye")
        # Redirect till kö (exempel): kontext + exten sätts av Odoo-konfig
        # await channel.redirect(context="from-internal", exten="6001")
