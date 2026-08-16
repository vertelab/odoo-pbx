# -*- coding: utf-8 -*-
"""Tester för pbx_ai (pbx-ai-call-assistant) — transcript-dokument + verktyg.

Körs med: odoo --test-enable -u pbx_ai (eller checkmodule -t).
"""

from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestTranscriptDocument(common.TransactionCase):
    """6.1/6.2: transcript-dokument skapas för voicemail/anknytning."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.extension = cls.env['pbx.extension'].create({
            'public_number': '6001',
            'name': 'Test-ext',
        })

    def _call(self, **kw):
        return self.env['pbx.call'].create(dict({
            'phone_number': '0701112233',
            'direction': 'inbound',
        }, **kw))

    def test_voicemail_should_transcribe(self):
        """6.1a: voicemail-samtal transkriberas."""
        call = self._call(pbx_handling='voicemail')
        pbx_ai = self.env['pbx.ai']
        self.assertTrue(pbx_ai._should_transcribe(call))

    def test_extension_enabled_should_transcribe(self):
        """6.2a: anknytning med transcribe_enabled transkriberas."""
        self.extension.write({'transcribe_enabled': True})
        call = self._call(extension_id=self.extension.id)
        pbx_ai = self.env['pbx.ai']
        self.assertTrue(pbx_ai._should_transcribe(call))

    def test_plain_call_not_transcribed(self):
        """6.1b: vanligt samtal utan voicemail/flagga transkriberas ej."""
        call = self._call()
        pbx_ai = self.env['pbx.ai']
        self.assertFalse(pbx_ai._should_transcribe(call))

    def test_document_created(self):
        """6.1c: _create_transcript_document skapar ir.attachment + kopplar."""
        call = self._call(pbx_handling='voicemail')
        pbx_ai = self.env['pbx.ai']
        attach = pbx_ai._create_transcript_document(
            call, 'Hej, jag har ett problem med maskinen')
        self.assertTrue(attach.exists())
        self.assertEqual(call.transcript_attachment_id, attach)
        self.assertIn('problem', call.transcript_text)


@tagged('post_install', '-at_install')
class TestReceptionistTools(common.TransactionCase):
    """6.3/6.4: receptionist-coworker + verktyg."""

    def test_receptionist_coworker_exists(self):
        """6.3: PBX Receptionist-coworker finns med rätt verktyg."""
        cw = self.env['ai.coworker'].search(
            [('name', '=', 'PBX Receptionist')], limit=1)
        self.assertTrue(cw.exists())
        names = cw.tool_ids.mapped('name')
        self.assertIn('pbx_call_get', names)
        self.assertIn('pbx_ticket_create', names)
        self.assertIn('pbx_lead_create', names)
        self.assertIn('pbx_transfer_queue', names)
        self.assertIn('pbx_transfer_extension', names)

    def test_transfer_queue_returns_destination(self):
        """6.4: pbx_transfer_queue returnerar destination."""
        queue = self.env['pbx.queue'].create({
            'name': 'Test-kö',
            'extension': '7001',
        })
        result = self.env['ai.coworker'].pbx_transfer_queue(1, queue.id)
        self.assertIn('transfer_to_queue', result)

    def test_transfer_extension_returns_destination(self):
        """6.4: pbx_transfer_extension returnerar destination."""
        ext = self.env['pbx.extension'].create({
            'public_number': '6101',
            'name': 'Test-ext-2',
        })
        result = self.env['ai.coworker'].pbx_transfer_extension(1, ext.id)
        self.assertIn('transfer_to_extension', result)
