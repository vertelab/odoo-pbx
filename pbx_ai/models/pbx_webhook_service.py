# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PbxWebhookServiceAI(models.AbstractModel):
    """pbx_ai-hook på webhook-tjänsten.

    - Vidarebefordrar pbx.result.* (transcriber-resultat) till pbx.ai.
    - Vid voicemail: skapar systray-aktivitet + publicerar transcribe-jobb
      om brevlådans device har transcribe_voicemail.
    """

    _inherit = "pbx.webhook.service"

    def handle_event(self, tenant_domain, topic, event):
        if topic.startswith("pbx.result."):
            try:
                self.env["pbx.ai"].handle_transcribe_result(tenant_domain, event)
            except Exception as e:
                _logger.warning("Transcribe-resultat misslyckades: %s", e)
            return
        return super().handle_event(tenant_domain, topic, event)

    def _handle_voicemail(self, tenant, event):
        """Voicemail → aktivitet (systray) + opt-in transkribering."""
        super()._handle_voicemail(tenant, event)
        try:
            audio_b64 = event.get("_audio_base64") or ""
            mailbox = event.get("Mailbox", "")  # ext@domain
            ext_number = mailbox.split("@")[0] if "@" in mailbox else mailbox
            call = self._find_voicemail_call(tenant, ext_number)
            if not call:
                return

            pbx_ai = self.env["pbx.ai"]
            # Aktivitet i systray: röstmeddelande att lyssna på
            try:
                pbx_ai._create_voicemail_activity(call)
            except Exception as e:
                _logger.warning("Voicemail-aktivitet misslyckades: %s", e)

            # Opt-in transkribering av röstmeddelandet
            device = pbx_ai._voicemail_device(call)
            if device and device.transcribe_voicemail and audio_b64:
                attachment = self._voicemail_attachment(call, audio_b64)
                if attachment:
                    pbx_ai._publish_transcribe_job(call, attachment)
        except Exception as e:
            _logger.warning("pbx_ai voicemail-hook misslyckades: %s", e)

    def _find_voicemail_call(self, tenant, ext_number):
        """Hitta senaste pbx.call för anknytningen (voicemail-samtal)."""
        try:
            extension = self.env["pbx.extension"].search(
                [("public_number", "=", ext_number)], limit=1
            )
            if not extension:
                return self.env["pbx.call"]
            return self.env["pbx.call"].search(
                [
                    ("extension_id", "=", extension.id),
                    ("pbx_handling", "=", "voicemail"),
                ],
                order="create_date desc, id desc",
                limit=1,
            )
        except Exception:
            return self.env["pbx.call"]

    def _voicemail_attachment(self, call, audio_b64):
        """Spara voicemail-ljudet som ir.attachment på pbx.call."""
        import base64
        try:
            return self.env["ir.attachment"].create(
                {
                    "name": f"Voicemail_{call.phone_number or ''}_{call.id}",
                    "datas": audio_b64,
                    "mimetype": "audio/wav",
                    "res_model": "pbx.call",
                    "res_id": call.id,
                }
            )
        except Exception as e:
            _logger.warning("Voicemail-attachment misslyckades: %s", e)
            return self.env["ir.attachment"]
