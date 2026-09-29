# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib
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
            - file_path: path to .wav file on the Asterisk server (same machine)
            - audio_base64: the recording as base64 (the daemon reads the spool
              for Odoo when they run on different machines)
        """
        domain = event_data.get("domain", "")
        mailbox = event_data.get("mailbox", "")
        caller_number = event_data.get("callerid_num", "")
        caller_name = event_data.get("callerid_name", "")
        duration = int(event_data.get("duration", 0))
        file_path = event_data.get("file_path", "")
        audio_base64 = event_data.get("audio_base64", "") or ""

        # Find the extension. The instance only manages its own PBX
        # (company-scoped via ir.rule) — no tenant record is needed locally.
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

        # Create attachment from audio (base64 from the daemon). A path-based
        # read is only used when the caller passed a path belonging to the SAME
        # message — never as a substitute for message-specific audio.
        attachment = None
        if audio_base64:
            try:
                decoded = base64.b64decode(audio_base64)
                audio_hash = hashlib.md5(decoded).hexdigest()
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": f"Voicemail_{caller_number}_{fields.Datetime.now()}",
                        "datas": base64.b64encode(decoded),
                        "mimetype": "audio/wav",
                        "res_model": "pbx.voicemail.message",
                    }
                )
                _logger.info(
                    "voicemail stored extension=%s hash=%s attachment_id=%s bytes=%d",
                    public_number, audio_hash, attachment.id, len(decoded),
                )
            except Exception as e:
                _logger.warning("Could not store voicemail audio: %s", e)
        elif file_path:
            try:
                with open(file_path, "rb") as f:
                    raw = f.read()
                audio_hash = hashlib.md5(raw).hexdigest()
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": f"Voicemail_{caller_number}_{fields.Datetime.now()}",
                        "datas": base64.b64encode(raw),
                        "mimetype": "audio/wav",
                        "res_model": "pbx.voicemail.message",
                    }
                )
                _logger.info(
                    "voicemail stored extension=%s hash=%s attachment_id=%s "
                    "bytes=%d source=file",
                    public_number, audio_hash, attachment.id, len(raw),
                )
            except (FileNotFoundError, OSError) as e:
                _logger.warning("Could not read voicemail file %s: %s", file_path, e)
        else:
            # No audio in the event: create the message WITHOUT an attachment.
            # Never fall back to another recording.
            _logger.info(
                "voicemail without audio extension=%s — no attachment created",
                public_number,
            )

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
                # sudo() context (webhook) has no env.company — take it from
                # the extension
                "company_id": extension.company_id.id,
            }
        )
        # Link the attachment to the RECEIVER (attachment on the receiver's partner),
        # not to pbx.voicemail.message — so the recording shows up as an attachment on
        # the person who received the call. audio_attachment_id on the message is kept
        # for the form.
        if attachment:
            receiver = extension.user_id.partner_id or extension.company_id.partner_id
            attachment.write({"res_model": "res.partner", "res_id": receiver.id})

        # Notify user (defensive — must not block the storage; notify_info
        # does not exist on res.users in all Odoo versions)
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
