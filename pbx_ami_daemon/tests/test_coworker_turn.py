# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""pbx-ai-extension-coworker 4.4/4.6 — the turn loop and its transcript.

The dialog is: record (VAD silence) -> STT -> LLM -> TTS -> play -> listen
again. The ARI client is mocked so the loop can be exercised without a
running Asterisk: what matters is which ARI commands are issued and in what
order, and that the caller's utterance reaches the dialog payload.

5.x (streaming via externalMedia) and 7.3/7.4 (a real test call) need the
Asterisk box and stay drift.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pbx_ami_daemon.ari import ARIClient, ARIChannel, CoworkerApp, Receptionist


def _channel(channel_id="chan-1"):
    client = MagicMock(spec=ARIClient)
    client.rest = AsyncMock(return_value={})
    client.get_recording_file = AsyncMock(return_value=b"RIFF....WAVE")
    channel = ARIChannel(client, channel_id)
    channel.answer = AsyncMock()
    channel.play = AsyncMock()
    channel.play_uri = AsyncMock()
    channel.record = AsyncMock()
    channel.hangup = AsyncMock()
    channel.redirect = AsyncMock()
    return channel


class TestTurnLoop(unittest.TestCase):
    """4.4 — record with a silence window, then process the turn."""

    def setUp(self):
        self.client = MagicMock(spec=ARIClient)
        self.client.get_recording_file = AsyncMock(return_value=b"RIFF....WAVE")
        self.app = CoworkerApp(self.client, odoo_url="http://odoo.test")
        self.app.audio.start = AsyncMock()
        self.channel = _channel()

    def test_record_uses_silence_window(self):
        """4.4 — the turn listens until 2 s of silence, max 8 s of speech."""
        self.app.conversations[self.channel.channel_id] = {
            "coworker_id": 1,
            "history": [],
            "turn": 0,
            "ended": False,
            "call_id": 0,
        }
        asyncio.run(self.app._start_record(self.channel))
        args, kwargs = self.channel.record.call_args
        self.assertEqual(kwargs.get("max_silence"), 2)
        self.assertEqual(kwargs.get("max_duration"), 8)

    def test_empty_recording_restarts_listening(self):
        """4.4 — silence must not end the dialog, it re-arms the recorder."""
        state = {"coworker_id": 1, "history": [], "turn": 0, "ended": False,
                 "call_id": 0}
        self.app.conversations[self.channel.channel_id] = state
        self.client.get_recording_file = AsyncMock(return_value=b"")
        asyncio.run(self.app._process_turn(self.channel, state, "rec-1"))
        self.assertGreaterEqual(self.channel.record.call_count, 1)

    def test_turn_payload_carries_call_id_and_utterance(self):
        """4.6 — the dialog payload carries call_id and the caller's line."""
        state = {
            "coworker_id": 7,
            "history": ["user: hej", "assistant: hej, hur kan jag hjälpa?"],
            "turn": 2,
            "ended": False,
            "call_id": 4242,
            "channel_id": self.channel.channel_id,
        }
        captured = {}

        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def json(self):
                return {"status": "ok", "reply": "ok", "tts_audio_base64": ""}

        class FakeSession:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def post(self, url, json=None, headers=None, timeout=None):
                captured["url"] = url
                captured["payload"] = json
                return FakeResponse()

        with patch("aiohttp.ClientSession", FakeSession):
            asyncio.run(self.app._dialog(state))

        payload = captured["payload"]
        self.assertEqual(payload["call_id"], 4242)
        self.assertEqual(payload["coworker_id"], 7)
        self.assertEqual(payload["turn"], "user: hej")
        self.assertEqual(payload["channel_id"], self.channel.channel_id)

    def test_stasis_args_split_coworker_and_call(self):
        """4.6 — (coworker,<id>,<call_id>) is parsed into both."""
        channel = _channel("chan-2")
        with patch.object(self.app, "_start_record", AsyncMock()):
            asyncio.run(
                self.app.on_stasis_start(
                    channel, {"args": ["coworker", "12", "555"]}
                )
            )
        state = self.app.conversations["chan-2"]
        self.assertEqual(state["coworker_id"], 12)
        self.assertEqual(state["call_id"], 555)

    def test_stasis_args_without_call_id(self):
        """4.6 — a two-arg Stasis call leaves call_id at 0, not an error."""
        channel = _channel("chan-3")
        with patch.object(self.app, "_start_record", AsyncMock()):
            asyncio.run(
                self.app.on_stasis_start(channel, {"args": ["coworker", "9"]})
            )
        state = self.app.conversations["chan-3"]
        self.assertEqual(state["coworker_id"], 9)
        self.assertEqual(state["call_id"], 0)


class TestReceptionistTenant(unittest.TestCase):
    """4.6 — the receptionist sends its tenant so Odoo picks the right token."""

    def test_payload_has_tenant(self):
        client = MagicMock(spec=ARIClient)
        app = Receptionist(client, odoo_url="http://odoo.test",
                           tenant="vertel.se")
        app.audio.start = AsyncMock()
        state = {"channel_id": "chan-9", "call_id": 1,
                 "history": ["user: hej"], "turn": 1, "ended": False}
        captured = {}

        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def json(self):
                return {"status": "ok", "reply": "ok", "tts_audio_base64": ""}

        class FakeSession:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def post(self, url, json=None, headers=None, timeout=None):
                captured["payload"] = json
                return FakeResponse()

        with patch("aiohttp.ClientSession", FakeSession):
            asyncio.run(app._dialog(state))

        self.assertEqual(captured["payload"]["tenant"], "vertel.se")
        self.assertEqual(captured["payload"]["call_id"], 1)


if __name__ == "__main__":
    unittest.main()
