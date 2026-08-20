# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class VoicemailService(models.AbstractModel):
    _name = "pbx.voicemail.service"
    _description = "Voicemail Service — handles incoming voicemail events"

    def handle_voicemail_event(self, event_data: dict):
        """Process a VoicemailMessage event from RabbitMQ.

        event_data contains:
            - domain: tenant SIP domain
            - mailbox: extension@domain
            - callerid_num: caller number
            - callerid_name: caller name
            - duration: recording duration in seconds
            - file_path: path to .wav file on Asterisk server (samma maskin)
            - audio_base64: inspelningen som base64 (daemonen läser spoolen
              åt Odoo när de ligger på olika maskiner)
        """
        domain = event_data.get("domain", "")
        mailbox = event_data.get("mailbox", "")
        caller_number = event_data.get("callerid_num", "")
        caller_name = event_data.get("callerid_name", "")
        duration = int(event_data.get("duration", 0))
        file_path = event_data.get("file_path", "")
        audio_base64 = event_data.get("audio_base64", "") or ""

        # Find the extension. Instansen administrerar bara sin egen växel
        # (company-scopad via ir.rule) — ingen tenant-post krävs lokalt.
        public_number = mailbox.split("@")[0] if "@" in mailbox else mailbox
        extension = self.env["pbx.extension"].search(
            [("public_number", "=", public_number)],
            limit=1,
        )
        if not extension:
            _logger.warning(
                "Unknown extension %s in tenant %s", public_number, domain
            )
            return

        # Try to match caller to a partner
        partner = self.env["res.partner"].search(
            ["|", ("phone", "=", caller_number), ("mobile", "=", caller_number)],
            limit=1,
        )
        if partner:
            caller_name = partner.display_name

        # Create attachment from audio (base64 från daemonen, eller lokal fil
        # när Odoo och Asterisk delar maskin)
        attachment = None
        if audio_base64:
            try:
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": f"Voicemail_{caller_number}_{fields.Datetime.now()}",
                        "datas": base64.b64encode(base64.b64decode(audio_base64)),
                        "mimetype": "audio/wav",
                        "res_model": "pbx.voicemail.message",
                    }
                )
            except Exception as e:
                _logger.warning("Could not store voicemail audio: %s", e)
        elif file_path:
            try:
                with open(file_path, "rb") as f:
                    audio_data = base64.b64encode(f.read())
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": f"Voicemail_{caller_number}_{fields.Datetime.now()}",
                        "datas": audio_data,
                        "mimetype": "audio/wav",
                        "res_model": "pbx.voicemail.message",
                    }
                )
            except (FileNotFoundError, OSError) as e:
                _logger.warning("Could not read voicemail file %s: %s", file_path, e)

        # Create voip.call record
        call = self.env["voip.call"].sudo().create(
            {
                "phone_number": caller_number,
                "type_call": "incoming",
                "state": "voicemail",
                "end_date": fields.Datetime.now(),
                "partner_id": partner.id if partner else False,
                "user_id": extension.user_id.id or self.env.uid,
            }
        )

        # Create voicemail message
        message = self.env["pbx.voicemail.message"].create(
            {
                "extension_id": extension.id,
                "caller_number": caller_number,
                "caller_name": caller_name,
                "duration": duration,
                "audio_attachment_id": attachment.id if attachment else False,
                "call_id": call.id,
                # sudo()-kontext (webhook) har ingen env.company — ta från
                # anknytningen
                "company_id": extension.company_id.id,
            }
        )

        # Notify user (defensivt — får inte blockera lagringen; notify_info
        # finns inte på res.users i alla Odoo-versioner)
        if extension.user_id:
            try:
                extension.user_id.notify_info(
                    f"New voicemail from {caller_name or caller_number} ({duration}s)"
                )
            except Exception as e:
                _logger.warning("Voicemail notify failed: %s", e)

        # Transcribe if enabled and odoo_ai is available
        voicemail_sub = extension.sub_extension_ids.filtered(
            lambda s: s.type == "voicemail" and s.transcribe_enabled
        )
        if voicemail_sub and attachment and self._has_odoo_ai():
            self._transcribe_async(message, attachment)

        return message

    def _has_odoo_ai(self):
        """Check if odoo_ai module is installed."""
        return "odoo.ai" in self.env.registry

    def _transcribe_async(self, message, attachment):
        """Transcribe voicemail asynchronously using odoo_ai."""
        # This runs in a separate thread/cron to avoid blocking
        self.env.cr.commit()  # Commit the message before async work
        try:
            ai_model = self.env["odoo.ai"]
            transcript = ai_model.transcribe_audio(
                attachment.datas, language="sv"
            )
            if transcript:
                message.sudo().write({"transcript": transcript})
                attachment.sudo().write({"description": transcript})
            _logger.info("Voicemail %d transcribed", message.id)
        except Exception as e:
            _logger.warning("Voicemail transcription failed: %s", e)
