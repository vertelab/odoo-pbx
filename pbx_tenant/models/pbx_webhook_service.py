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
        # Instansen administrerar bara sin egen domän (settings) — men vi
        # accepterar webhook-event för den domänen som anropas.
        if not self.env["res.company"].search_count(
            [("pbx_domain", "=", tenant_domain)]
        ):
            _logger.warning("Webhook event for unknown tenant domain: %s", tenant_domain)
            return

        event_name = event.get("Event", "")
        payload = {"topic": topic, "event": event}

        # 0) Config-ack från daemonen (pbx-freepbx-core) — uppdatera
        #    företagets sync-state innan övriga händelser (inget bus-flöde).
        if topic.startswith("pbx.state.Config."):
            try:
                self._handle_config_ack(tenant_domain, event)
            except Exception as e:
                _logger.warning("Config ack handling failed for %s: %s", tenant_domain, e)

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
        #    must not break the event flow). Savepoint: ai_agent_core's
        #    partner-watch may fail on some environments; roll back locally.
        caller = event.get("CallerIDNum") or event.get("CallerID1") or ""
        if event_name in ("Newchannel", "Hangup", "VoicemailMessage", "UserEvent") and caller:
            try:
                with self.env.cr.savepoint():
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
                self._handle_voicemail(tenant_domain, event)
            except Exception as e:
                _logger.warning("Voicemail handling failed: %s", e)

    def _handle_config_ack(self, tenant_domain, event):
        """Uppdatera företagets sync-state från daemonens config-ack.

        Payload (event): {"domain": ..., "version": N, "status":
        "applied"|"skipped"|"error", "error": "..."}.

        - applied/skipped: om versionen är den (eller nyare än den)
          publicerade nollställs config_dirty och applied-version sätts.
        - error: error-text sparas, config_dirty kvarstår.
        """
        company = self.env["res.company"].search(
            [("pbx_domain", "=", tenant_domain)], limit=1
        )
        if not company:
            _logger.warning("Config ack for unknown domain: %s", tenant_domain)
            return
        version = int(event.get("version", 0) or 0)
        status = event.get("status", "")
        published = company.pbx_config_version or 0
        if status in ("applied", "skipped"):
            if version >= published:
                company.write(
                    {
                        "config_dirty": False,
                        "pbx_config_applied_version": version,
                        "pbx_config_sync_error": False,
                    }
                )
                _logger.info(
                    "Config %s v%s confirmed applied for %s",
                    tenant_domain, version, status,
                )
        elif status == "error":
            company.write({"pbx_config_sync_error": event.get("error") or "Okänt fel"})
            _logger.error(
                "Config apply failed for %s v%s: %s",
                tenant_domain, version, event.get("error"),
            )

    def _handle_voicemail(self, tenant, event):
        mailbox = event.get("Mailbox", "")  # ext@domain
        spool_dir = event.get("Dir", "")  # /var/spool/asterisk/voicemail/<domain>/<ext>
        file_path = ""
        if spool_dir:
            file_path = f"{spool_dir.rstrip('/')}/msg0001.wav"
        self.env["pbx.voicemail.service"].handle_voicemail_event(
            {
                "domain": self.env["ir.config_parameter"].get_param("pbx.domain", ""),
                "mailbox": mailbox,
                "callerid_num": event.get("CallerIDNum", ""),
                "callerid_name": event.get("CallerIDName", ""),
                "duration": int(event.get("Duration", 0) or 0),
                "file_path": file_path,
            }
        )
