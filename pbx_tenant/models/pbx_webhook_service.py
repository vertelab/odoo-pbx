# Copyright 2026 Vertel Sverige AB
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

    # Asterisk CDR dispositions. The AMI Cdr event sends Disposition as text
    # (ANSWERED / NO ANSWER / BUSY / CONGESTION / FAILED); the CSV backend in
    # DOCUMENTATION mode writes numeric codes. Accept both so the handler is
    # independent of the cdr backend in use.
    _CDR_DISPOSITIONS = {
        "ANSWERED": "answered",
        "NO ANSWER": "missed",
        "BUSY": "busy",
        "CONGESTION": "missed",
        "FAILED": "missed",
        # Numeric (cdr_csv DOCUMENTATION) codes
        "8": "answered",
        "10": "answered",
        "0": "missed",
        "2": "busy",
        "3": "missed",
    }

    def _handle_cdr_call(self, tenant_domain, event):
        """Log a call in pbx.call from an AMI Cdr event.

        One call produces several CDR records (one per leg). We log exactly
        one record per call, from the leg that dialled the INTERNAL device —
        i.e. LastApplication = Dial with DestinationChannel = PJSIP/u<username>-…
        (the extension that answered, or the last one rung if unanswered).

        The internal device sits in different fields depending on direction:

        * Outbound: the extension originated the call, so Channel is
          PJSIP/u011-… and DestinationChannel is the trunk leg. The dialling
          leg is the one with the internal device in Channel.
        * Inbound: the trunk received the call, so Channel is
          PJSIP/<domain>-trunk-<slug>-… and DestinationChannel is
          PJSIP/u011-… for each rung device (ring group / follow-me).

        Looking only at Channel (the previous behaviour) therefore logged
        outbound calls and silently dropped every inbound one — pbx.call had
        no direction=incoming rows at all.

        Direction: outbound when Source is the extension's own number, i.e.
        the call started internally; otherwise inbound. pbx_handling is
        mapped from Disposition.
        """
        channel = event.get("Channel", "") or ""
        dest_channel = event.get("DestinationChannel", "") or ""
        last_app = (event.get("LastApplication", "") or "").strip()
        # The internal device is PJSIP/u<username>-… . Outbound legs carry it
        # in Channel; inbound legs carry it in DestinationChannel. Only the
        # Dial leg represents "this call reached extension X" — the trunk's
        # own leg (Channel = trunk, no internal device) and the Local-channel
        # wrappers are skipped, so one call yields one record.
        internal = re.search(r"PJSIP/(u[0-9]+)-", channel)
        if not internal:
            if last_app != "Dial":
                # Inbound non-dial legs (the trunk leg itself, voicemail
                # fallback, etc.) carry no extension to attribute.
                return
            internal = re.search(r"PJSIP/(u[0-9]+)-", dest_channel)
        if not internal:
            # Trunk↔trunk or Local-only leg with no internal device — no
            # extension to attribute the call to; skip.
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
        disposition = (event.get("Disposition", "") or "").strip().upper()
        handling = self._CDR_DISPOSITIONS.get(disposition, "missed")
        company = self.env["res.company"].search(
            [("pbx_domain", "=", tenant_domain)], limit=1
        )
        # Deduplicate: a ring group / follow-me rings several devices, so one
        # inbound call yields one Dial leg per rung device (each with the
        # internal device in DestinationChannel). Without this every call
        # would be logged once per rung.
        #
        # The call's identity is the trunk leg's channel suffix — every leg of
        # one inbound call shares the same trunk channel (e.g.
        # PJSIP/<domain>-trunk-<slug>-00000036). UniqueID is NOT usable here:
        # each leg has its own, and the cdr_csv backend writes the literal
        # "DOCUMENTATION" in its place.
        cdr_key = ""
        trunk_leg = re.search(
            r"(PJSIP/[A-Za-z0-9.\-]*-trunk-[A-Za-z0-9.\-]*-[0-9a-f]+)",
            "%s %s" % (channel, dest_channel),
        )
        if trunk_leg:
            cdr_key = trunk_leg.group(1)
        if not cdr_key:
            # Outbound (or an internal-only call): the originating channel is
            # unique per call, so it identifies the call on its own.
            cdr_key = channel.strip()
        existing = (
            self.env["pbx.call"].search([("cdr_unique_id", "=", cdr_key)], limit=1)
            if cdr_key
            else self.env["pbx.call"]
        )
        if existing:
            # The call is already logged. Ring-group legs arrive in ring
            # order, so the first one is often an unanswered rung
            # ("missed") while a later leg is the one that was answered.
            # Upgrade the record when this leg carries the better outcome —
            # never log a second row for the same call.
            if handling != "answered" or existing.pbx_handling == "answered":
                return
            existing.write(
                {
                    "pbx_handling": handling,
                    "extension_id": extension.id if extension else False,
                    "user_id": extension.user_id.id if extension else False,
                    "stop_date": event.get("EndTime") or existing.stop_date,
                }
            )
            return
        self.env["pbx.call"].log_call(
            {
                "phone_number": str(number),
                "callerid_name": name,
                "direction": "outgoing" if outgoing else "incoming",
                "start_date": event.get("StartTime") or fields.Datetime.now(),
                "stop_date": event.get("EndTime"),
                "pbx_handling": handling,
                "cdr_unique_id": cdr_key or False,
                "user_id": extension.user_id.id if extension else False,
                "extension_id": extension.id if extension else False,
                "company_id": company.id if company else False,
            }
        )

    def _handle_voicemail(self, tenant, event):
        mailbox = event.get("Mailbox", "")  # ext@domain
        # No path fallback: a hardcoded spool filename (msg0001.wav) would attach
        # an unrelated recording when the event carries no audio. The daemon
        # sends the message's own audio as _audio_base64; without it the message
        # is stored without an attachment.
        self.env["pbx.voicemail.service"].handle_voicemail_event(
            {
                "domain": tenant,
                "mailbox": mailbox,
                "callerid_num": event.get("CallerIDNum", ""),
                "callerid_name": event.get("CallerIDName", ""),
                "duration": int(event.get("Duration", 0) or 0),
                # The daemon attaches the audio (base64) because Odoo runs on
                # a different machine than the Asterisk spool
                "audio_base64": event.get("_audio_base64") or "",
            }
        )
