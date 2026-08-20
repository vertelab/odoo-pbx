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
        # Asterisk 20.6 sänder MessageWaiting (MWI), INTE VoicemailMessage
        if event_name in ("VoicemailMessage", "MessageWaiting"):
            try:
                self._handle_voicemail(tenant_domain, event)
            except Exception as e:
                _logger.warning("Voicemail handling failed: %s", e)

        # 4) Call history: Cdr-händelser → pbx.call (defensiv)
        if event_name == "Cdr":
            try:
                self._handle_cdr_call(tenant_domain, event)
            except Exception as e:
                _logger.warning("Call logging failed for %s: %s", tenant_domain, e)

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
            company.write(
                {
                    "config_dirty": True,
                    "pbx_config_sync_error": event.get("error") or "Okänt fel",
                }
            )
            _logger.error(
                "Config apply failed for %s v%s: %s",
                tenant_domain, version, event.get("error"),
            )

    def _handle_cdr_call(self, tenant_domain, event):
        """Logga ett samtal i pbx.call från en AMI Cdr-händelse.

        Ett samtal producerar en CDR-post per ben; vi loggar bara den post
        där den INTERNA enhetens egen kanal (PJSIP/u<username>-…) är Channel
        — trunk-/övriga ben hoppas, så varje samtal ger en post.

        Riktning: utgående när Source = anknytningens eget nummer (samtalet
        startade internt), annars inkommande. pbx_handling mappas från
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
        # Source är CDR:ns callerid-nummer — för interna ben kan det vara
        # "01@pbx-test.vertel.se" (eller saniterad variant "01@pbxtestvertelse"
        # om en äldre callerid deployats). Jämför bara prefixet före @/<.
        src_number = re.split(r"[@<]", src)[0].strip()
        if not src_number:
            # Ingen Source (t.ex. Local-kanal utan callerid) — kan inte
            # klassificera riktning pålitligt; hoppa.
            return
        # Utgående: Source = anknytningens eget nummer; annars inkommande
        outgoing = bool(extension) and src_number in (
            extension.public_number or "",
            username,
        )
        number = event.get("Destination" if outgoing else "Source", "") or ""
        number = str(number).strip()
        # Samma normalisering som Source: "02@pbx-test.vertel.se" → "02"
        number = re.split(r"[@<]", number)[0].strip()
        # Hoppa över icke-dialbara nummer (t.ex. 's' från originate till
        # special-exten i operator panel/queue) — inga riktiga samtal
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
                # Daemonen bifogar ljudet (base64) eftersom Odoo ligger på
                # annan maskin än Asterisk-spoolen
                "audio_base64": event.get("_audio_base64") or "",
            }
        )
