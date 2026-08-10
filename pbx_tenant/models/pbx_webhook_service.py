# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PbxWebhookService(models.AbstractModel):
    """Processes events POSTed by the pbx_ami_daemon to /pbx/webhook.

    Real-time broadcast on `bus.bus` happens FIRST (never blocked by
    side-effects); partner resolution and voicemail handling are defensive.
    """

    _name = "pbx.webhook.service"
    _description = "PBX Webhook Event Service"

    def handle_event(self, tenant_domain, topic, event):
        tenant = self.env["pbx.tenant"].search(
            [("domain", "=", tenant_domain)], limit=1
        )
        if not tenant:
            _logger.warning("Webhook event for unknown tenant: %s", tenant_domain)
            return

        event_name = event.get("Event", "")
        payload = {"topic": topic, "event": event}

        # 1) Real-time broadcast — must never be blocked
        # Odoo 18 bus: _sendone(channel, notification_type, message)
        self.env["bus.bus"]._sendone(
            f"pbx.{tenant_domain}", "pbx_event", payload
        )
        if event_name == "UserEvent" and event.get("UserEvent") == "ManualRequired":
            self.env["bus.bus"]._sendone(
                f"pbx.{tenant_domain}.reception", "pbx_event", payload
            )

        # 2) Partner resolution (defensive — side-effects from other modules
        #    must not break the event flow)
        caller = event.get("CallerIDNum") or event.get("CallerID1") or ""
        if event_name in ("Newchannel", "Hangup", "VoicemailMessage", "UserEvent") and caller:
            try:
                partner, created = self.env["pbx.partner.resolver"].resolve(
                    caller, event.get("CallerIDName") or caller
                )
                payload["partner"] = {
                    "id": partner.id,
                    "name": partner.display_name if partner else "",
                    "created": created,
                }
                self.env["bus.bus"]._sendone(
                    f"pbx.{tenant_domain}", "pbx_event", payload
                )
            except Exception as e:
                _logger.warning("Partner resolution failed for %s: %s", caller, e)

        # 3) Voicemail → existing inbox handler (defensive)
        if event_name == "VoicemailMessage":
            try:
                self._handle_voicemail(tenant, event)
            except Exception as e:
                _logger.warning("Voicemail handling failed: %s", e)

    def _handle_voicemail(self, tenant, event):
        mailbox = event.get("Mailbox", "")  # ext@domain
        spool_dir = event.get("Dir", "")  # /var/spool/asterisk/voicemail/<domain>/<ext>
        file_path = ""
        if spool_dir:
            file_path = f"{spool_dir.rstrip('/')}/msg0001.wav"
        self.env["pbx.voicemail.service"].handle_voicemail_event(
            {
                "domain": tenant.domain,
                "mailbox": mailbox,
                "callerid_num": event.get("CallerIDNum", ""),
                "callerid_name": event.get("CallerIDName", ""),
                "duration": int(event.get("Duration", 0) or 0),
                "file_path": file_path,
            }
        )
