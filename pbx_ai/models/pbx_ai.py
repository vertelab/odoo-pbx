# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import logging

from odoo import models

_logger = logging.getLogger(__name__)

TRANSCRIBE_JOB_KEY = "pbx.job.transcribe"


class PbxAI(models.AbstractModel):
    _name = "pbx.ai"
    _inherit = ["pbx.plugin"]
    _description = "PBX AI Bridge — Odoo Mind integration"

    # ── Inspelning redo → publicera transcribe-jobb (lokal transcriber) ──

    def on_recording_ready(self, voip_call, attachment):
        """Called by pbx_recording when a recording is available.

        Bestäm om samtalet ska transkriberas (tri-state recording_mode eller
        voicemail-opt-in) och publicera ett transcribe-jobb till den lokala
        pbx-transcriberen (fors). Resultatet hanteras i
        handle_transcribe_result (via webhook).
        """
        if not self._should_transcribe(voip_call):
            return
        if not self._publish_transcribe_job(voip_call, attachment):
            # Fallback om MQ saknas: transkribera direkt via provider
            self._transcribe_and_document(voip_call, attachment)

    # ── Policy-upplösning ────────────────────────────────────────────

    def _should_transcribe(self, voip_call):
        """Avgör om samtalet ska transkriberas:
        (a) voicemail-samtal med brevlåda som har transcribe_voicemail, eller
        (b) anknytningens upplösta recording_mode == transcribe."""
        if not voip_call:
            return False
        if voip_call.pbx_handling == 'voicemail' or voip_call.type_call == 'voicemail':
            # Voicemail: kräver opt-in per brevlåda (device)
            device = self._voicemail_device(voip_call)
            if device and device.transcribe_voicemail:
                return True
            # Bakåtkompatibilitet: gammalt beteende transkriberade alla
            # voicemail — nu opt-in, men tillåt företags-policy
            policy = self.env["pbx.recording.policy"].search(
                [("scope", "=", "company"), ("active", "=", True)], limit=1
            )
            return bool(policy and policy.mode == "always")
        if voip_call.extension_id:
            mode = voip_call.extension_id._get_recording_mode()
            if mode == "transcribe":
                return True
            if mode == "record" and voip_call.extension_id.transcribe_enabled:
                # Deprecerad kombination: transcribe_enabled tvingar ändå
                return True
        return False

    def _voicemail_device(self, voip_call):
        """Hitta voicemail-enheten (pbx.sub_extension) för samtalet."""
        try:
            if voip_call.extension_id:
                dev = self.env["pbx.sub_extension"].search(
                    [
                        ("extension_id", "=", voip_call.extension_id.id),
                        ("type", "=", "voicemail"),
                    ],
                    limit=1,
                )
                if dev:
                    return dev
            mailbox = getattr(voip_call, "voicemail_box", "") or ""
            if mailbox:
                return self.env["pbx.sub_extension"].search(
                    [
                        ("type", "=", "voicemail"),
                        ("voicemail_box", "=", mailbox),
                    ],
                    limit=1,
                )
        except Exception as e:
            _logger.warning("voicemail device lookup failed: %s", e)
        return self.env["pbx.sub_extension"]

    # ── Publicera transcribe-jobb (lokal pbx-transcriber, fors) ──────

    def _publish_transcribe_job(self, voip_call, attachment):
        """Publicera pbx.job.transcribe med ljudet (base64) via pbx.mq.publisher.

        Returns True om jobbet publicerades, False om MQ saknas (caller
        får då fallbacka till direkt transkribering).
        """
        publisher = self.env.get("pbx.mq.publisher")
        if not publisher:
            return False
        if not attachment or not attachment.datas:
            return False
        payload = {
            "job_id": "pbx-%s-%s" % (voip_call.id or 0, attachment.id or 0),
            "call_id": voip_call.id or 0,
            "tenant": getattr(voip_call, "tenant_domain", "") or "",
            "audio_base64": attachment.datas.decode() if isinstance(
                attachment.datas, bytes) else attachment.datas,
            "language": "sv",
        }
        try:
            publisher.publish(TRANSCRIBE_JOB_KEY, payload)
            _logger.info(
                "Transcribe-jobb publicerat för pbx.call %s (attachment %s)",
                voip_call.id, attachment.id,
            )
            return True
        except Exception as e:
            _logger.warning("MQ publish failed: %s", e)
            return False

    # ── Resultat (pbx.result.transcribe via webhook) ─────────────────

    def handle_transcribe_result(self, tenant_domain, event):
        """Processa pbx.result.transcribe (från pbx-transcriber via daemonen).

        event: {"job_id", "call_id", "tenant", "status", "transcript",
                "model", "language", "duration_seconds", "processing_seconds",
                "error"}
        """
        call_id = int(event.get("call_id") or 0)
        call = self.env["pbx.call"].sudo().browse(call_id) if call_id else \
            self.env["pbx.call"]
        if not call.exists():
            _logger.warning("Transcribe-resultat för okänd pbx.call %s", call_id)
            return

        status = event.get("status", "error")
        if status != "ok" or not event.get("transcript"):
            _logger.error(
                "Transkribering misslyckades för pbx.call %s: %s",
                call_id, event.get("error"),
            )
            # Zabbix-alert via logg (zabbix-aggregate i drift)
            _logger.error("PBX_TRANSCRIBE_ERROR call=%s error=%s",
                          call_id, event.get("error"))
            return

        transcript = event.get("transcript")
        # Dokument (text-bilaga) + stt-metadata
        self._create_transcript_document(call, transcript)
        call.write({
            "stt_model": event.get("model") or "large-v3-turbo",
            "stt_duration_s": event.get("duration_seconds") or 0.0,
            "stt_processing_s": event.get("processing_seconds") or 0.0,
        })

        # LLM-pipeline: memory + entity extraction (token-förbrukning här)
        usage = {}
        if self._has_ai_agent_core():
            usage = self._create_company_memory(call, transcript)
        self._extract_entities(call, transcript)
        if usage:
            self._record_token_usage(call, usage)

    # ── Token-förbrukning ────────────────────────────────────────────

    def _record_token_usage(self, voip_call, usage):
        """Sätt token-fält på pbx.call från LLM-usage.

        usage: dict {"in": int, "out": int} (tokens).
        """
        if not usage:
            return
        tokens_in = int(usage.get("in") or 0)
        tokens_out = int(usage.get("out") or 0)
        price = float(self.env["ir.config_parameter"].sudo().get_param(
            "pbx.ai.token_price", "0.0") or 0.0)
        cost = (tokens_in + tokens_out) * price
        voip_call.write({
            "ai_tokens_in": tokens_in,
            "ai_tokens_out": tokens_out,
            "ai_token_cost": round(cost, 6),
        })

    # ── Befintliga hjälpmetoder (LLM-pipeline) ───────────────────────

    def _has_odoo_ai(self):
        return "odoo.ai" in self.env.registry

    def _has_ai_agent_core(self):
        return "ai.company.memory" in self.env.registry or \
            "ai.coworker" in self.env.registry

    def _create_company_memory(self, voip_call, transcript):
        """Skapa ai.company.memory. Returnerar token-usage om tillgängligt."""
        memory_model = self.env.get("ai.company.memory")
        if not memory_model:
            return {}

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
        # v1: token-usage från LLM rapporteras inte i memory-skapandet —
        # fälten fylls av dialog/pipeline när usage finns tillgängligt.
        return {}

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

    def get_internal_dialplan(self, domain, company):
        """Make AI-anknytningar reachable by their public number (Stasis)."""
        company_id = company.id if isinstance(company, models.Model) else company
        extensions = self.env["pbx.extension"].search(
            [("company_id", "=", company_id)]
        )
        lines = []
        for ext in extensions:
            if not ext._is_ai_extension():
                continue
            coworker = ext._get_ai_coworker()
            if coworker:
                lines.append(
                    "exten => %s,1,Stasis(coworker,%s)"
                    % (ext.public_number, coworker.id)
                )
        return "\n".join(lines)

    def get_operator_panel_widgets(self):
        return [{"name": "ai_transcript", "component": "PbxAiTranscript", "props": {}}]

    # ── Transcript-dokument (pbx-ai-call-assistant) ──────────────────

    def _create_transcript_document(self, voip_call, transcript):
        """Skapa ir.attachment (text) med samtalet som bilaga + koppla till
        pbx.call. Returnerar attachment."""
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

    def _transcribe_and_document(self, voip_call, attachment):
        """FALLBACK (ingen MQ): transkribera direkt via provider och skapa
        dokument + memory. Används när pbx.mq.publisher saknas."""
        if not self._should_transcribe(voip_call):
            return
        try:
            transcript = self.env['odoo.ai'].transcribe_audio(
                attachment.datas, language='sv'
            ) if self._has_odoo_ai() else ''
            if not transcript and self._has_ai_agent_core():
                transcript = self._transcribe_via_provider(attachment)
        except Exception as e:
            _logger.warning('Transcription failed: %s', e)
            return
        if not transcript:
            return
        self._create_transcript_document(voip_call, transcript)
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

    # ── Voicemail-aktivitet (systray) ────────────────────────────────

    def _create_voicemail_activity(self, voip_call, attachment=None):
        """Skapa mail.activity "Röstmeddelande" på pbx.call (systray)."""
        activity_type = self.env.ref(
            "pbx_ai.activity_type_voicemail", raise_if_not_found=False
        )
        if not activity_type:
            activity_type = self.env["mail.activity.type"].search(
                [("name", "=", "Röstmeddelande")], limit=1
            )
        if not activity_type:
            _logger.warning("Aktivitetstyp 'Röstmeddelande' saknas")
            return

        # Mottagare: röstbrevlådans ägare (device → extension → user)
        user = False
        device = self._voicemail_device(voip_call)
        if device and device.extension_id and device.extension_id.user_id:
            user = device.extension_id.user_id
        if not user and voip_call.extension_id and voip_call.extension_id.user_id:
            user = voip_call.extension_id.user_id

        # Undvik dubbletter (en aktivitet per samtal)
        existing = self.env["mail.activity"].search(
            [
                ("res_model", "=", "pbx.call"),
                ("res_id", "=", voip_call.id),
                ("activity_type_id", "=", activity_type.id),
            ],
            limit=1,
        )
        if existing:
            return existing

        summary = "Röstmeddelande att lyssna på"
        if voip_call.phone_number:
            summary += f" från {voip_call.phone_number}"
        return self.env["mail.activity"].create(
            {
                "res_model": "pbx.call",
                "res_id": voip_call.id,
                "activity_type_id": activity_type.id,
                "user_id": user.id if user else self.env.uid,
                "date_deadline": self.env["fields"].Date.today(),
                "summary": summary,
                "note": (
                    "Det finns ett röstmeddelande att lyssna på."
                    + (" Länk: %s" % attachment.name if attachment else "")
                ),
            }
        )

    # ── Receptionist-verktyg (samtals-coworker) ──────────────────────

    def pbx_call_get(self, call_id):
        """Hämta samtalskontext (JSON) för receptionist-dialog."""
        call = self.env["pbx.call"].sudo().browse(int(call_id))
        if not call.exists():
            return {"error": "call not found"}
        return {
            "call_id": call.id,
            "phone_number": call.phone_number,
            "callerid_name": call.callerid_name,
            "direction": call.direction,
            "extension": call.extension_id.public_number if call.extension_id else "",
            "transcript": call.transcript_text or "",
        }

    def pbx_ticket_create(self, call_id, caller_number='', caller_name='',
                          transcript=''):
        """Skapa helpdesk-ticket via pbx_helpdesk (felanmälan)."""
        helpdesk = self.env.get('pbx.helpdesk')
        if not helpdesk:
            return 'pbx_helpdesk ej installerat'
        result = helpdesk.create_ticket_from_call(
            caller_number, caller_name, transcript)
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
        return 'transfer_to_queue:%s:%s' % (queue.extension or '', queue.id)

    def pbx_transfer_extension(self, call_id, extension_id):
        """Vidarekoppla samtal till anknytning."""
        ext = self.env['pbx.extension'].sudo().browse(int(extension_id))
        if not ext.exists():
            return 'Extension %s not found' % extension_id
        return 'transfer_to_extension:%s:%s' % (ext.public_number or '', ext.id)
