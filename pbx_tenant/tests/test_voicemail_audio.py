# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Voicemail-audio integrity on the Odoo side (pbx-voicemail-audio-integrity).

Task 4.3 — regression guard: each voicemail event must create its OWN
attachment with the audio it carried. Never a singleton, never a reused file.

Run with: checkmodule -t pbx_tenant (or odoo --test-enable -u pbx_tenant).
"""

import base64

from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestVoicemailAudio(common.TransactionCase):
    """Two events with different audio → two distinct attachments."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.extension = cls.env["pbx.extension"].create({
            "company_id": cls.env.company.id,
            "public_number": "7001",
            "callerid_name": "Voicemail-test",
        })

    def _store(self, raw_audio, caller="0701112233"):
        return self.env["pbx.voicemail.service"].handle_voicemail_event({
            "domain": "test.se",
            "mailbox": "7001@test.se",
            "callerid_num": caller,
            "callerid_name": "Test Caller",
            "duration": 5,
            "audio_base64": base64.b64encode(raw_audio).decode(),
        })

    def test_two_voicemails_yield_two_distinct_attachments(self):
        """Task 4.3: distinct audio → distinct attachments + messages."""
        first = self._store(b"FIRST-RECORDING")
        second = self._store(b"SECOND-RECORDING")

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertNotEqual(first.id, second.id)
        self.assertTrue(first.audio_attachment_id)
        self.assertTrue(second.audio_attachment_id)
        self.assertNotEqual(
            first.audio_attachment_id.id, second.audio_attachment_id.id,
        )
        self.assertNotEqual(
            first.audio_attachment_id.datas, second.audio_attachment_id.datas,
        )

    def test_stored_audio_is_the_received_audio(self):
        """The attachment holds the event's own bytes, not another recording."""
        raw = b"UNIQUE-BYTES-12345"
        message = self._store(raw)
        stored = base64.b64decode(message.audio_attachment_id.datas)
        self.assertEqual(stored, raw)

    def test_event_without_audio_creates_no_substitute_attachment(self):
        """No audio in the event → message without attachment (no fallback)."""
        message = self.env["pbx.voicemail.service"].handle_voicemail_event({
            "domain": "test.se",
            "mailbox": "7001@test.se",
            "callerid_num": "0701112233",
            "duration": 3,
            "audio_base64": "",
        })
        self.assertTrue(message)
        self.assertFalse(message.audio_attachment_id)
