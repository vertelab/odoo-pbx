# -*- coding: utf-8 -*-
"""Tests for pbx_ai (pbx-ai-call-assistant) — transcript documents + tools.

Run with: odoo --test-enable -u pbx_ai (or checkmodule -t).
"""

from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestTranscriptDocument(common.TransactionCase):
    """6.1/6.2: transcript documents are created for voicemail/extension."""

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
        """6.1a: voicemail calls are transcribed."""
        call = self._call(pbx_handling='voicemail')
        pbx_ai = self.env['pbx.ai']
        self.assertTrue(pbx_ai._should_transcribe(call))

    def test_extension_enabled_should_transcribe(self):
        """6.2a: an extension with transcribe_enabled is transcribed."""
        self.extension.write({'transcribe_enabled': True})
        call = self._call(extension_id=self.extension.id)
        pbx_ai = self.env['pbx.ai']
        self.assertTrue(pbx_ai._should_transcribe(call))

    def test_plain_call_not_transcribed(self):
        """6.1b: an ordinary call without voicemail/flag is not transcribed."""
        call = self._call()
        pbx_ai = self.env['pbx.ai']
        self.assertFalse(pbx_ai._should_transcribe(call))

    def test_document_created(self):
        """6.1c: _create_transcript_document creates an ir.attachment + links it."""
        call = self._call(pbx_handling='voicemail')
        pbx_ai = self.env['pbx.ai']
        attach = pbx_ai._create_transcript_document(
            call, 'Hello, I have a problem with the machine')
        self.assertTrue(attach.exists())
        self.assertEqual(call.transcript_attachment_id, attach)
        self.assertIn('problem', call.transcript_text)


@tagged('post_install', '-at_install')
class TestReceptionistTools(common.TransactionCase):
    """6.3/6.4: receptionist coworker + tools."""

    def test_receptionist_coworker_exists(self):
        """6.3: the PBX Receptionist coworker exists with the right tools."""
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
        """6.4: pbx_transfer_queue returns the destination."""
        queue = self.env['pbx.queue'].create({
            'name': 'Test Queue',
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
