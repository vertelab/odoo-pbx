# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PbxAI(models.AbstractModel):
    _name = "pbx.ai"
    _inherit = ["pbx.plugin"]
    _description = "PBX AI Bridge — Odoo Mind integration"

    def on_recording_ready(self, voip_call, attachment):
        """Called by pbx_recording when a recording is available.
        Transcribes audio → transcript-dokument (text-bilaga) + memory."""
        # Bestäm om samtalet ska transkriberas (voicemail eller
        # transcribe_enabled på anknytningen).
        if not self._should_transcribe(voip_call):
            return
        self._transcribe_and_document(voip_call, attachment)

    def _has_odoo_ai(self):
        return "odoo.ai" in self.env.registry

    def _has_ai_agent_core(self):
        return "ai.company.memory" in self.env.registry or \
            "ai.coworker" in self.env.registry

    def _create_company_memory(self, voip_call, transcript):
        memory_model = self.env.get("ai.company.memory")
        if not memory_model:
            return

        content = f"""**Phone Call** — {voip_call.create_date.strftime('%Y-%m-%d %H:%M')}
**Direction:** {voip_call.type_call}
**Number:** {voip_call.phone_number}
**Agent:** {voip_call.user_id.name}

**Transcript:**
{transcript}
"""
        memory_model.create({
            "company_id": voip_call.company_id.id,
            "content": content,
            "category": "pbx_call",
            "scope": "internal",
            "importance": "medium",
        })

    def _extract_entities(self, voip_call, transcript):
        """Extract entities from transcript and create graph edges.
        Stored as JSON on voip.call for cron-based AGE sync."""
        if not self._has_odoo_ai():
            return

        try:
            entities = self.env["odoo.ai"].extract_entities(transcript)
        except Exception:
            return

        # Store for later graph sync
        voip_call.sudo().write({"entities": entities})

    def get_config_snippets(self, tenant):
        return {}

    def get_operator_panel_widgets(self):
        return [{"name": "ai_transcript", "component": "PbxAiTranscript", "props": {}}]

    # ── Transcript-dokument (pbx-ai-call-assistant) ──────────────────

    def _create_transcript_document(self, voip_call, transcript):
        """Skapa ir.attachment (text) med samtalet som bilaga + koppla till
        pbx.call. Returnerar attachment."""
        import base64
        if not voip_call or not transcript:
            return self.env['ir.attachment']
        content = (
            f"Samtal {voip_call.create_date.strftime('%Y-%m-%d %H:%M')}\n"
            f"Riktning: {voip_call.direction or voip_call.type_call}\n"
            f"Nummer: {voip_call.phone_number or ''}\n"
            f"Anknytning: {voip_call.extension_id.public_number if voip_call.extension_id else ''}\n"
            f"Varaktighet: {voip_call.duration or 0}s\n"
            f"\n--- Transkription ---\n{transcript}\n"
        )
        attach = self.env['ir.attachment'].create({
            'name': f"samtal-{voip_call.id}.txt",
            'mimetype': 'text/plain',
            'datas': base64.b64encode(content.encode('utf-8')),
            'res_model': 'pbx.call',
            'res_id': voip_call.id,
        })
        voip_call.write({
            'transcript_attachment_id': attach.id,
            'transcript_text': transcript,
        })
        return attach

    def _should_transcribe(self, voip_call):
        """Avgör om samtalet ska transkriberas:
        (a) voicemail-samtal, eller (b) anknytning med transcribe_enabled."""
        if not voip_call:
            return False
        if voip_call.pbx_handling == 'voicemail' or voip_call.type_call == 'voicemail':
            return True
        if voip_call.extension_id and voip_call.extension_id.transcribe_enabled:
            return True
        return False

    def _transcribe_and_document(self, voip_call, attachment):
        """Transkribera inspelning → transcript-dokument (text-bilaga)."""
        if not self._should_transcribe(voip_call):
            return
        try:
            transcript = self.env['odoo.ai'].transcribe_audio(
                attachment.datas, language='sv'
            ) if self._has_odoo_ai() else ''
            if not transcript and self._has_ai_agent_core():
                # Fallback: whisper via ai.provider
                transcript = self._transcribe_via_provider(attachment)
        except Exception as e:
            _logger.warning('Transcription failed: %s', e)
            return
        if not transcript:
            return
        # Dokument (text-bilaga)
        self._create_transcript_document(voip_call, transcript)
        # Befintligt beteende: memory + entity-extraction
        if self._has_ai_agent_core():
            self._create_company_memory(voip_call, transcript)
        self._extract_entities(voip_call, transcript)

    def _transcribe_via_provider(self, attachment):
        """Whisper via ai.provider (ai_agent_core)."""
        try:
            import subprocess, tempfile, os
            provider = self.env['ai.provider'].search(
                [('active', '=', True)], limit=1)
            if not provider or not hasattr(provider, '_transcribe_audio'):
                return ''
            with tempfile.NamedTemporaryFile(suffix='.audio', delete=False) as f:
                f.write(attachment.raw)
                tmp = f.name
            try:
                wav = '/tmp/pbx_ai_%s.wav' % attachment.id
                subprocess.run(
                    ['ffmpeg', '-y', '-i', tmp, '-ar', '16000', '-ac', '1',
                     wav], capture_output=True, timeout=300)
                with open(wav, 'rb') as f:
                    return provider._transcribe_audio(f.read()) or ''
            finally:
                for p in (tmp, '/tmp/pbx_ai_%s.wav' % attachment.id):
                    if os.path.exists(p):
                        os.remove(p)
        except Exception as e:
            _logger.warning('transcribe via provider failed: %s', e)
            return ''

    # ── Receptionist-verktyg (samtals-coworker) ──────────────────────

    def pbx_call_get(self, call_id):
        """Hämta samtalskontext (JSON) för receptionist-dialog."""
        import json
        call = self.env['pbx.call'].sudo().browse(int(call_id))
        if not call.exists():
            return json.dumps({'error': 'Call %s not found' % call_id})
        return json.dumps({
            'id': call.id,
            'phone_number': call.phone_number or '',
            'callerid_name': call.callerid_name or '',
            'direction': call.direction or call.type_call or '',
            'duration': call.duration or 0,
            'extension': (call.extension_id.public_number
                          if call.extension_id else ''),
            'transcript': call.transcript_text or '',
        }, ensure_ascii=False, default=str)

    def pbx_ticket_create(self, call_id, caller_number='', caller_name='',
                          transcript=''):
        """Skapa helpdesk-ticket via pbx_helpdesk (felanmälan)."""
        helpdesk = self.env.get('pbx.helpdesk')
        if not helpdesk:
            return 'pbx_helpdesk ej installerat'
        result = helpdesk.create_ticket_from_call(
            caller_number, caller_name, transcript)
        # Tagga samtalet med ärende
        call = self.env['pbx.call'].sudo().browse(int(call_id))
        if call.exists() and result:
            try:
                tid = result[0].get('id') if isinstance(result, list) else None
                if tid:
                    call.write({'helpdesk_ticket_id': tid})
            except Exception:
                pass
        return 'Ticket skapad: %s' % result

    def pbx_lead_create(self, call_id, caller_number='', caller_name=''):
        """Skapa CRM-lead via pbx_crm (intresseanmälan)."""
        crm = self.env.get('pbx.crm')
        if not crm:
            return 'pbx_crm ej installerat'
        result = crm.create_lead_from_call(caller_number, caller_name)
        return 'Lead skapad: %s' % result

    def pbx_transfer_queue(self, call_id, queue_id):
        """Vidarekoppla samtal till kö (pbx.queue)."""
        queue = self.env['pbx.queue'].sudo().browse(int(queue_id))
        if not queue.exists():
            return 'Queue %s not found' % queue_id
        # AMI/ARI Redirect utförs av daemonen (pbx_ami_daemon) via
        # RabbitMQ-kommando — här returnerar vi destinationen.
        return 'transfer_to_queue:%s:%s' % (queue.extension or '', queue.id)

    def pbx_transfer_extension(self, call_id, extension_id):
        """Vidarekoppla samtal till anknytning (pbx.extension)."""
        ext = self.env['pbx.extension'].sudo().browse(int(extension_id))
        if not ext.exists():
            return 'Extension %s not found' % extension_id
        return 'transfer_to_extension:%s:%s' % (ext.public_number or '', ext.id)
