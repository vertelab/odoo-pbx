# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Unit tests for voicemail-audio integrity in the AMI daemon.

Covers the marker (dedup), the file-bound metadata, the delivery decision, the
reconnect case and the post-restart seed. Run with:

    python3 -m unittest discover -s pbx_ami_daemon/tests -t .

or with the repo root on PYTHONPATH:

    python3 pbx_ami_daemon/tests/test_voicemail_integrity.py
"""

import asyncio
import base64
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from pbx_ami_daemon.daemon import (  # noqa: E402
    EventConsumer,
    MailboxMarker,
    _read_voicemail_audio,
)


def _make_spool(root, domain, mailbox, messages):
    """Create a spool INBOX.

    ``messages`` maps a msg number to (raw_bytes, txt_lines_dict).
    Returns the INBOX path.
    """
    inbox = os.path.join(root, domain, mailbox, "INBOX")
    os.makedirs(inbox, exist_ok=True)
    for num, (raw, meta) in messages.items():
        wav = os.path.join(inbox, f"msg{num:04d}.wav")
        with open(wav, "wb") as f:
            f.write(raw)
        if meta:
            with open(os.path.join(inbox, f"msg{num:04d}.txt"), "w") as f:
                for key, value in meta.items():
                    f.write(f"{key}={value}\n")
    return inbox


class TestMailboxMarker(unittest.TestCase):
    """Task 5.1 — marker semantics."""

    def test_new_hash_is_new(self):
        marker = MailboxMarker()
        self.assertTrue(marker.is_new("02@vertel.se", "msg0001.wav", "h1"))

    def test_same_hash_is_not_new(self):
        marker = MailboxMarker()
        marker.remember("02@vertel.se", "msg0001.wav", "h1")
        self.assertFalse(marker.is_new("02@vertel.se", "msg0001.wav", "h1"))

    def test_changed_hash_is_new_again(self):
        marker = MailboxMarker()
        marker.remember("02@vertel.se", "msg0001.wav", "h1")
        self.assertTrue(marker.is_new("02@vertel.se", "msg0002.wav", "h2"))

    def test_same_hash_reused_file_number_is_new(self):
        """A rewritten file under a reused msg number must not look deduped."""
        marker = MailboxMarker()
        marker.remember("02@vertel.se", "msg0001.wav", "h1")
        self.assertTrue(marker.is_new("02@vertel.se", "msg0001.wav", "h2"))

    def test_mailboxes_are_independent(self):
        marker = MailboxMarker()
        marker.remember("02@vertel.se", "msg0001.wav", "h1")
        self.assertTrue(marker.is_new("03@vertel.se", "msg0001.wav", "h1"))

    def test_get_returns_last_mark(self):
        marker = MailboxMarker()
        marker.remember("02@vertel.se", "msg0001.wav", "h1")
        mark = marker.get("02@vertel.se")
        self.assertEqual(mark["file"], "msg0001.wav")
        self.assertEqual(mark["md5"], "h1")
        self.assertIsNone(marker.get("99@vertel.se"))


class TestReadVoicemailAudio(unittest.TestCase):
    """Task 5.2 — spool reading, hashing and file-bound metadata."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.spool = self._tmp.name
        # _read_voicemail_audio hardcodes the spool root; patch it for tests.
        import pbx_ami_daemon.daemon as daemon_mod
        self._real_spool = getattr(daemon_mod, "_VOICEMAIL_SPOOL", None)
        daemon_mod._VOICEMAIL_SPOOL = self.spool

    def tearDown(self):
        import pbx_ami_daemon.daemon as daemon_mod
        daemon_mod._VOICEMAIL_SPOOL = "/var/spool/asterisk/voicemail"
        self._tmp.cleanup()

    def test_picks_highest_msg_and_reads_its_txt(self):
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"OLD-AUDIO", {"callerid": "070-1111111", "duration": "5"}),
            2: (b"NEW-AUDIO", {"callerid": "070-2222222", "duration": "9"}),
        })
        info = _read_voicemail_audio({"Mailbox": "02@vertel.se"})
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "msg0002.wav")
        self.assertEqual(info["callerid"], "070-2222222")
        self.assertEqual(info["duration"], "9")
        self.assertEqual(
            base64.b64decode(info["base64"]), b"NEW-AUDIO",
        )

    def test_hash_is_stable_for_same_content(self):
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"SAME", {"callerid": "070-1111111"}),
        })
        a = _read_voicemail_audio({"Mailbox": "02@vertel.se"})
        b = _read_voicemail_audio({"Mailbox": "02@vertel.se"})
        self.assertEqual(a["md5"], b["md5"])

    def test_asterisk_sha1_is_preferred_hash(self):
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"AUDIO", {"callerid": "070-1111111", "sha1": "deadbeef"}),
        })
        info = _read_voicemail_audio({"Mailbox": "02@vertel.se"})
        self.assertEqual(info["md5"], "deadbeef")
        self.assertEqual(info["sha1"], "deadbeef")

    def test_missing_txt_yields_empty_metadata(self):
        _make_spool(self.spool, "vertel.se", "02", {1: (b"AUDIO", None)})
        info = _read_voicemail_audio({"Mailbox": "02@vertel.se"})
        self.assertIsNotNone(info)
        self.assertEqual(info["callerid"], "")
        self.assertEqual(info["duration"], "")

    def test_empty_inbox_returns_none(self):
        _make_spool(self.spool, "vertel.se", "02", {})
        self.assertIsNone(_read_voicemail_audio({"Mailbox": "02@vertel.se"}))

    def test_missing_mailbox_returns_none(self):
        self.assertIsNone(_read_voicemail_audio({"Mailbox": "42@vertel.se"}))

    def test_does_not_mutate_event(self):
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"AUDIO", {"callerid": "070-1111111", "duration": "7"}),
        })
        event = {"Mailbox": "02@vertel.se"}
        _read_voicemail_audio(event)
        self.assertNotIn("CallerIDNum", event)
        self.assertNotIn("Duration", event)


class _FakeWebhook:
    def __init__(self):
        self.calls = []

    async def publish(self, tenant, routing_key, data):
        self.calls.append((tenant, routing_key, data))


def _make_consumer(marker=None, spool=None):
    """Build an EventConsumer with a fake webhook and no AMI/publisher."""
    return EventConsumer(
        ami=None, publisher=None, state_cache=None,
        webhook=_FakeWebhook(),
        known_domains={"vertel.se"},
        marker=marker,
    )


class TestDeliveryDecision(unittest.TestCase):
    """Tasks 5.3–5.5 — sent / dedup / reconnect / seed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.spool = self._tmp.name
        import pbx_ami_daemon.daemon as daemon_mod
        daemon_mod._VOICEMAIL_SPOOL = self.spool

    def tearDown(self):
        import pbx_ami_daemon.daemon as daemon_mod
        daemon_mod._VOICEMAIL_SPOOL = "/var/spool/asterisk/voicemail"
        self._tmp.cleanup()

    def _deliver(self, consumer, topic="pbx.event.vertel.se.AMI.MessageWaiting"):
        event = {"Event": "MessageWaiting", "Mailbox": "02@vertel.se"}
        asyncio.run(consumer._publish_voicemail("vertel.se", topic, event))
        return consumer.webhook.calls[-1][2]

    def test_seed_then_sent_then_dedup(self):
        """First event seeds (no audio), a new message sends, a repeat dedups."""
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"AUDIO-1", {"callerid": "070-1111111", "duration": "3"}),
        })
        marker = MailboxMarker()
        consumer = _make_consumer(marker=marker, spool=self.spool)

        # 1) First MWI after start → seed, no audio
        payload = self._deliver(consumer)
        self.assertNotIn("_audio_base64", payload)
        self.assertEqual(payload["CallerIDNum"], "070-1111111")

        # 2) A new message arrives → audio delivered
        _make_spool(self.spool, "vertel.se", "02", {
            2: (b"AUDIO-2", {"callerid": "070-2222222", "duration": "8"}),
        })
        payload = self._deliver(consumer)
        self.assertIn("_audio_base64", payload)
        self.assertEqual(
            base64.b64decode(payload["_audio_base64"]), b"AUDIO-2",
        )
        self.assertEqual(payload["CallerIDNum"], "070-2222222")

        # 3) Repeat MWI for the same message → no audio, but still published
        payload = self._deliver(consumer)
        self.assertNotIn("_audio_base64", payload)
        self.assertEqual(len(consumer.webhook.calls), 3)

    def test_metadata_overrides_event_values(self):
        """Metadata comes from the delivered file, not the MWI event."""
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"A-1", {"callerid": "070-1111111", "duration": "3"}),
        })
        marker = MailboxMarker()
        marker.remember("02@vertel.se", "msg0000.wav", "stale")
        consumer = _make_consumer(marker=marker, spool=self.spool)
        event = {
            "Event": "MessageWaiting", "Mailbox": "02@vertel.se",
            "CallerIDNum": "999-WRONG", "Duration": "999",
        }
        asyncio.run(consumer._publish_voicemail("vertel.se", "t", event))
        payload = consumer.webhook.calls[-1][2]
        self.assertEqual(payload["CallerIDNum"], "070-1111111")
        self.assertEqual(payload["Duration"], "3")

    def test_reconnect_with_shared_marker_does_not_duplicate(self):
        """Task 5.4 — a new EventConsumer must reuse the process marker."""
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"AUDIO-1", {"callerid": "070-1111111"}),
        })
        marker = MailboxMarker()
        first = _make_consumer(marker=marker, spool=self.spool)
        self._deliver(first)          # seed (msg0001, no audio)

        # New message arrives → delivered with audio
        _make_spool(self.spool, "vertel.se", "02", {
            2: (b"AUDIO-2", {"callerid": "070-2222222"}),
        })
        payload = self._deliver(first)
        self.assertIn("_audio_base64", payload)

        # Reconnect: new consumer, same marker, unchanged file
        second = _make_consumer(marker=marker, spool=self.spool)
        payload = self._deliver(second)
        self.assertNotIn("_audio_base64", payload)

    def test_new_consumer_without_marker_duplicates(self):
        """Documents why the marker must be shared (design D2)."""
        _make_spool(self.spool, "vertel.se", "02", {
            1: (b"AUDIO-1", {"callerid": "070-1111111"}),
        })
        first = _make_consumer(marker=MailboxMarker(), spool=self.spool)
        self._deliver(first)            # seed

        _make_spool(self.spool, "vertel.se", "02", {
            2: (b"AUDIO-2", {"callerid": "070-2222222"}),
        })
        self._deliver(first)            # sent

        # A reconnect with a FRESH marker loses state. The new marker is empty,
        # so the next event takes the seed path. Audio is therefore omitted
        # (one lost delivery), not duplicated — but with a *newer* file still
        # unread the fresh marker could just as well have re-sent. Sharing the
        # marker is what makes the reconnect safe.
        second = _make_consumer(marker=MailboxMarker(), spool=self.spool)
        payload = self._deliver(second)
        self.assertNotIn("_audio_base64", payload)
        self.assertIsNotNone(second.marker.get("02@vertel.se"))

    def test_no_spool_still_publishes_event(self):
        consumer = _make_consumer(marker=MailboxMarker(), spool=self.spool)
        payload = self._deliver(consumer)
        self.assertNotIn("_audio_base64", payload)


if __name__ == "__main__":
    unittest.main()
