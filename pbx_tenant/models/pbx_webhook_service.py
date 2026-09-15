# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PbxWebhookService(models.AbstractModel):
    """Processes events POSTed by the pbx_ami_daemon to /pbx/webhook.

    Real-time broadcast on `bus.bus` happens FIRST (never blocked by
    side-effects); partner resolution and voicemail handling are defensive.
    """

    _name = "pbx.webhook.service"
    _description = "PBX Webhook Event Service"

    def handle_event(self, tenant_domain, topic, event):
        # The instance only manages its own domain (settings) — but we
        # accept webhook events for the domain being called.
        if not self.env["res.company"].search_count(
            [("pbx_domain", "=", tenant_domain)]
        ):
            _logger.warning("Webhook event for unknown tenant domain: %s", tenant_domain)
            return

        event_name = event.get("Event", "")
        payload = {"topic": topic, "event": event}

        # 0) Config ack from the daemon (pbx-freepbx-core) — update the
        #    company's sync state before the other events (no bus flow).
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
        if event_name in (
            "Newchannel", "Hangup", "VoicemailMessage", "MessageWaiting",
            "UserEvent",
        ) and caller:
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
        # Asterisk 20.6 sends MessageWaiting (MWI), NOT VoicemailMessage
        if event_name in ("VoicemailMessage", "MessageWaiting"):
            try:
                self._handle_voicemail(tenant_domain, event)
            except Exception as e:
                _logger.warning("Voicemail handling failed: %s", e)

        # 4) Call history: Cdr events → pbx.call (defensive)
        if event_name == "Cdr":
            try:
                self._handle_cdr_call(tenant_domain, event)
            except Exception as e:
                _logger.warning("Call logging failed for %s: %s", tenant_domain, e)

    def _handle_config_ack(self, tenant_domain, event):
        """Update the company's sync state from the daemon's config ack.

        Payload (event): {"domain": ..., "version": N, "status":
        "applied"|"skipped"|"error", "error": "..."}.

        - applied/skipped: if the version is the (or newer than the)
          published one, config_dirty is reset and the applied version is set.
        - error: the error text is saved, config_dirty remains.
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
            company.write(
                {
                    "config_dirty": True,
                    "pbx_config_sync_error": event.get("error") or "Unknown error",
                }
            )
            _logger.error(
                "Config apply failed for %s v%s: %s",
                tenant_domain, version, event.get("error"),
            )

    def _handle_cdr_call(self, tenant_domain, event):
        """Log a call in pbx.call from an AMI Cdr event.

        One call produces one CDR record per leg; we only log the record
        where the INTERNAL device's own channel (PJSIP/u<username>-…) is Channel
        — trunk/other legs are skipped, so each call gives one record.

        Direction: outbound when Source = the extension's own number (the call
        started internally), otherwise inbound. pbx_handling is mapped from
        Disposition (ANSWERED / NO ANSWER / BUSY / …).
        """
        channel = event.get("Channel", "") or ""
        internal = re.search(r"PJSIP/(u[0-9]+)-", channel)
        if not internal:
            return
        username = internal.group(1)
        sub = self.env["pbx.sub_extension"].search(
            [("username", "=", username)], limit=1
        )
        extension = sub.extension_id if sub else False
        src = str(event.get("Source", "") or "")
        # Source is the CDR's callerid number — for internal legs it can be
        # "01@pbx-test.vertel.se" (or the sanitised variant "01@pbxtestvertelse"
        # if an older callerid was deployed). Only compare the prefix before @/<.
        src_number = re.split(r"[@<]", src)[0].strip()
        if not src_number:
            # No Source (e.g. a Local channel without callerid) — cannot
            # classify the direction reliably; skip.
            return
        # Outbound: Source = the extension's own number; otherwise inbound
        outgoing = bool(extension) and src_number in (
            extension.public_number or "",
            username,
        )
        number = event.get("Destination" if outgoing else "Source", "") or ""
        number = str(number).strip()
        # Same normalisation as Source: "02@pbx-test.vertel.se" → "02"
        number = re.split(r"[@<]", number)[0].strip()
        # Skip non-dialable numbers (e.g. 's' from an originate to
        # special extension in the operator panel/queue) — no real calls
        if not re.match(r"^\+?[0-9]+$", number):
            return
        name = event.get("CallerIDName", "") or ""
        disposition = (event.get("Disposition", "") or "").upper()
        handling_map = {
            "ANSWERED": "answered",
            "NO ANSWER": "missed",
            "BUSY": "busy",
            "CONGESTION": "missed",
            "FAILED": "missed",
        }
        handling = handling_map.get(disposition, "missed")
        company = self.env["res.company"].search(
            [("pbx_domain", "=", tenant_domain)], limit=1
        )
        self.env["pbx.call"].log_call(
            {
                "phone_number": str(number),
                "callerid_name": name,
                "direction": "outgoing" if outgoing else "incoming",
                "start_date": event.get("StartTime") or fields.Datetime.now(),
                "stop_date": event.get("EndTime"),
                "pbx_handling": handling,
                "user_id": extension.user_id.id if extension else False,
                "extension_id": extension.id if extension else False,
                "company_id": company.id if company else False,
            }
        )

    def _handle_voicemail(self, tenant, event):
        mailbox = event.get("Mailbox", "")  # ext@domain
        spool_dir = event.get("Dir", "")  # /var/spool/asterisk/voicemail/<domain>/<ext>
        file_path = ""
        if spool_dir:
            file_path = f"{spool_dir.rstrip('/')}/msg0001.wav"
        self.env["pbx.voicemail.service"].handle_voicemail_event(
            {
                "domain": tenant,
                "mailbox": mailbox,
                "callerid_num": event.get("CallerIDNum", ""),
                "callerid_name": event.get("CallerIDName", ""),
                "duration": int(event.get("Duration", 0) or 0),
                "file_path": file_path,
                # The daemon attaches the audio (base64) because Odoo runs on
                # a different machine than the Asterisk spool
                "audio_base64": event.get("_audio_base64") or "",
            }
        )
