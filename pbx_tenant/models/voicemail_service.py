# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib
import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


class VoicemailService(models.AbstractModel):
    _name = "pbx.voicemail.service"
    _description = "Voicemail Service — handles incoming voicemail events"

    def handle_voicemail_event(self, event_data: dict):
        """Process a VoicemailMessage event from RabbitMQ.

        A voicemail is stored as a single ``pbx.call`` with
        ``pbx_handling = 'voicemail'``. The recording is an ir.attachment on
        that call and the transcript is written to ``transcript_text``.

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

        # The call is created BEFORE the attachment so the attachment can be
        # linked to it (res_model='pbx.call', res_id=call.id).
        # duration is computed from start_date/stop_date on pbx.call — never
        # write it directly, or the compute will be silenced.
        stop = fields.Datetime.now()
        start = stop - timedelta(seconds=max(0, duration))
        call = self.env["pbx.call"].sudo().create(
            {
                "phone_number": caller_number,
                "callerid_name": caller_name,
                "direction": "incoming",
                "pbx_handling": "voicemail",
                "start_date": start,
                "stop_date": stop,
                "partner_id": partner.id if partner else False,
                "user_id": extension.user_id.id or self.env.uid,
                "extension_id": extension.id,
                # sudo() context (webhook) has no env.company — take it from
                # the extension
                "company_id": extension.company_id.id,
                "voicemail_read": False,
            }
        )

        # Store the audio as an attachment ON THE CALL.
        attachment = self._store_audio(call, caller_number, audio_base64, file_path)

        # Transcribe if enabled and odoo_ai is available
        voicemail_sub = extension.sub_extension_ids.filtered(
            lambda s: s.type == "voicemail" and s.transcribe_enabled
        )
        if voicemail_sub and attachment:
            self._trigger_transcription(call, attachment)

        # Notify the mailbox owner via the Odoo bus (the same mechanism the
        # webhook service uses). res.users has no notify_info in Odoo 18 —
        # that came from OCA web_notify. Must not block the storage.
        if extension.user_id:
            try:
                self.env["bus.bus"]._sendone(
                    f"res.partner.{extension.user_id.partner_id.id}",
                    "pbx_event",
                    {
                        "event": {
                            "Event": "VoicemailMessage",
                            "CallerIDNum": caller_number,
                            "CallerIDName": caller_name,
                            "Duration": duration,
                            "CallId": call.id,
                            "Extension": extension.public_number,
                        }
                    },
                )
            except Exception as e:
                _logger.warning("Voicemail notify failed: %s", e)

        return call

    def _store_audio(self, call, caller_number, audio_base64, file_path):
        """Attach the recording to the call. Returns the attachment or False.

        A path-based read is only used when the caller passed a path belonging
        to the SAME message — never as a substitute for message-specific audio.
        """
        raw = None
        source = None
        if audio_base64:
            try:
                raw = base64.b64decode(audio_base64)
                source = "base64"
            except Exception as e:
                _logger.warning("Could not decode voicemail audio: %s", e)
        elif file_path:
            try:
                with open(file_path, "rb") as f:
                    raw = f.read()
                source = "file"
            except (FileNotFoundError, OSError) as e:
                _logger.warning("Could not read voicemail file %s: %s", file_path, e)

        if raw is None:
            # No audio in the event: keep the call WITHOUT an attachment.
            # Never fall back to another recording.
            _logger.info(
                "voicemail without audio call=%s — no attachment created", call.id
            )
            return self.env["ir.attachment"]

        audio_hash = hashlib.md5(raw).hexdigest()
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": f"Voicemail_{caller_number}_{fields.Datetime.now()}.wav",
                "datas": base64.b64encode(raw),
                "mimetype": "audio/wav",
                "res_model": "pbx.call",
                "res_id": call.id,
            }
        )
        call.sudo().write({"recording_attachment_id": attachment.id})
        _logger.info(
            "voicemail stored call=%s hash=%s attachment_id=%s bytes=%d source=%s",
            call.id, audio_hash, attachment.id, len(raw), source,
        )
        return attachment

    def _trigger_transcription(self, call, attachment):
        """Hand the recording to pbx_ai, which decides (tri-state policy /
        voicemail opt-in) and publishes the transcribe job to the local
        transcriber. pbx_tenant does not depend on pbx_ai, so the service is
        looked up defensively.

        Note: pbx.ai is an AbstractModel — env.get() returns an EMPTY
        recordset (bool() is False) even when the model exists, so the
        registry must be checked instead.
        """
        if "pbx.ai" not in self.env.registry:
            _logger.info(
                "voicemail: pbx_ai not installed — transcription skipped call=%s",
                call.id,
            )
            return
        try:
            self.env["pbx.ai"].on_recording_ready(call, attachment)
        except Exception as e:
            _logger.warning("Could not trigger transcription call=%s: %s", call.id, e)
