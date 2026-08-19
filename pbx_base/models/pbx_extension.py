# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .pbx_sub_extension import _generate_sip_secret

_logger = logging.getLogger(__name__)


class PbxExtension(models.Model):
    _name = "pbx.extension"
    _inherit = ["pbx.destination.mixin", "mail.thread", "mail.activity.mixin", "pbx.config.dirty.mixin"]
    _description = "PBX Extension (public number)"

    public_number = fields.Char(required=True, default=lambda self: self._default_public_number())

    def _default_public_number(self):
        """Förslag: nästa lediga anknytningsnummer (pbx.numbering).

        include_existing=False → bara nästa OANVÄNDA nummer (inte återbruk av
        befintliga fria anknytningar) — annars krockar default med
        unique-public_number vid skapelse.
        """
        try:
            _, number = self.env["pbx.numbering"]._next_free_extension_number(
                self.env.company, include_existing=False
            )
            return number or False
        except Exception:
            return False
    user_id = fields.Many2one("res.users", string="Odoo User")
    password = fields.Char(
        string="SIP Password",
        groups="base.group_user",
        help="Personligt SIP-lösenord som gäller för alla enheter på anknytningen. "
             "Auto-genereras och skrivs in i den genererade pjsip-konfigurationen.",
    )
    callerid_name = fields.Char(
        help="Visas som namn på utgående samtal. Fylls i från användarens namn "
             "när en användare kopplas — kan överskrivas manuellt."
    )

    @api.onchange("user_id")
    def _onchange_user_id(self):
        if self.user_id and not self.callerid_name:
            self.callerid_name = self.user_id.name

    @api.model_create_multi
    def create(self, vals_list):
        """Generera delat SIP-lösenord, skapa implicit Odoo VOIP-enhet, synka
        user-länken (pbx_extension_id) och voip_oca-inställningarna."""
        skip_check = self.env.context.get("pbx_skip_number_check")
        for vals in vals_list:
            vals.setdefault("password", self._generate_sip_password())
            if not skip_check and vals.get("company_id") and vals.get("public_number"):
                company = self.env["res.company"].browse(vals["company_id"])
                self.env["pbx.numbering"]._check_dialable_number(
                    company, vals["public_number"]
                )
        extensions = super().create(vals_list)
        self.env.flush_all()
        batch_has_browser = any(
            cmd[0] == 0 and cmd[2].get("type") == "browser"
            for vals in vals_list
            for cmd in vals.get("sub_extension_ids") or []
        )
        for ext in extensions:
            if not batch_has_browser and not ext.sub_extension_ids.filtered(
                lambda s: s.type == "browser"
            ):
                self.env["pbx.sub_extension"].create(
                    {
                        "extension_id": ext.id,
                        "type": "browser",
                        "label": "Odoo VOIP",
                        "sequence": 1,
                    }
                )
            ext._sync_user_link()
            ext._sync_voip()
        return extensions

    def write(self, vals):
        old_links = {}
        if vals.get("user_id"):
            for ext in self:
                old_links[ext.id] = ext.user_id
        if not self.env.context.get("pbx_skip_number_check") and (
            vals.get("public_number") or vals.get("company_id")
        ):
            for ext in self:
                company = (
                    self.env["res.company"].browse(vals["company_id"])
                    if vals.get("company_id")
                    else ext.company_id
                )
                number = vals.get("public_number", ext.public_number)
                self.env["pbx.numbering"]._check_dialable_number(
                    company, number, exclude=ext
                )
        res = super().write(vals)
        for ext in self:
            if ext.id in old_links:
                old = old_links[ext.id]
                if old and old != ext.user_id and old.pbx_extension_id == ext:
                    old.pbx_extension_id = False
            ext._sync_user_link()
        if vals.get("user_id") or vals.get("password"):
            for ext in self:
                ext._sync_voip()
        return res

    def _generate_sip_password(self):
        """Generera SIP-lösenord med konfigurerad längd (pbx.sip_password_length)."""
        length = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "pbx.sip_password_length", "10"
            )
        )
        return _generate_sip_secret(length)

    def action_generate_new_password(self):
        """Generera nytt delat SIP-lösenord (gäller alla enheter).

        Ägarkoll: egen anknytning (user_id) eller PBX Office/Admin. Dirty-
        flaggning + voip_oca-sync sker automatiskt via write-hook.
        """
        for ext in self:
            if ext.user_id.id != self.env.user.id and not (
                self.env.user.has_group("pbx_base.group_pbx_office")
                or self.env.user.has_group("pbx_base.group_pbx_admin")
                or self.env.user.has_group("base.group_system")
            ):
                raise AccessError(_("Du kan bara rotera lösenordet på din egen anknytning."))
        self.write({"password": self._generate_sip_password()})
        self.message_post(body=_("SIP-lösenord roterat"))
        return True

    def _sync_user_link(self):
        """Säkerställ att user.pbx_extension_id pekar på denna extension.

        Lägger även användaren i group_pbx_operator (självbetjäning: ser sin
        egen anknytning/enheter/samtal) om hen inte redan har office/admin
        (vilka implicerar operator). Office/Admin tilldelas fortfarande
        manuellt — endast grundnivån är automatisk.
        """
        self.ensure_one()
        user = self.user_id
        if not user:
            return
        if user.pbx_extension_id != self:
            user.pbx_extension_id = self.id
        if user.has_group("pbx_base.group_pbx_office") or user.has_group(
            "pbx_base.group_pbx_admin"
        ):
            return
        operator = self.env.ref("pbx_base.group_pbx_operator")
        if not user.has_group("pbx_base.group_pbx_operator"):
            user.write({"groups_id": [(4, operator.id)]})
            _logger.info(
                "Auto-assigned PBX Operator to user %s (extension %s)",
                user.login,
                self.public_number,
            )

    def _sync_voip(self):
        """Synka voip_oca-inställningarna på den kopplade användaren.

        - PBX (voip.pbx) hämtas/skapas från företagets Asterisk-konfig
        - ws_server: explicit `company.pbx_ws_server` vinner; annars härleds
          `{ws|wss}://<host>:<port>/ws` (schema från browser-sub-extensionens
          transport, port från `pbx_sip_ws_port`, default 8089). Skrivs även
          på befintlig voip.pbx (självläkande) så gamla installationer med
          felaktig adress rättas vid nästa synk.
        - Username från den implicita browser-sub-extensionen (Odoo VOIP)
        - Lösenord = personens delade SIP-lösenord (gäller alla enheter)
        """
        self.ensure_one()
        if "voip.pbx" not in self.env or not self.user_id:
            return
        company = self.company_id
        domain = company.pbx_domain or ""
        browser_sub = self.sub_extension_ids.filtered(lambda s: s.type == "browser")[:1]
        pbx = self.env["voip.pbx"].search([("domain", "=", domain)], limit=1)
        if not pbx:
            pbx = self.env["voip.pbx"].create(
                {
                    "name": company.pbx_domain or company.name or "PBX",
                    "domain": domain,
                    "mode": "prod",
                }
            )
        ws_server = self._derive_ws_server(company, browser_sub)
        if pbx.ws_server != ws_server:
            pbx.ws_server = ws_server
        self.user_id.write(
            {
                "voip_pbx_id": pbx.id,
                "voip_username": browser_sub.username if browser_sub else "",
                "voip_password": self.password or "",
            }
        )

    @staticmethod
    def _derive_ws_server(company, browser_sub):
        """Härled WebSocket-URL för Odoo-softphonen (SIP.js).

        Prioritet:
        1. `company.pbx_ws_server` — explicit override (används exakt).
        2. Legacy: `pbx_server_host` som redan innehåller ws:// eller wss://.
        3. Auto: `{ws|wss}://<host>:<port>/ws` — schema från browser-
           sub-extensionens transport, port från pbx_sip_ws_port (default 8089).
        """
        if company.pbx_ws_server:
            return company.pbx_ws_server.strip()
        host = company.pbx_server_host or "localhost"
        if host.startswith(("ws://", "wss://")):
            return host
        scheme = "wss" if browser_sub and browser_sub.transport == "wss" else "ws"
        port = company.pbx_sip_ws_port or 8089
        return "%s://%s:%s/ws" % (scheme, host, port)
    description = fields.Char(
        string="Description",
        help="Visas i Operator Panel-panelen, t.ex. 'Reception', 'Anna – Support'",
    )
    is_receptionist = fields.Boolean(
        string="Receptionist",
        help="Receptionist ser alla anknytningar + allt inkommande + manuell hantering i Operator Panel",
    )
    ring_strategy = fields.Selection(
        [("sequential", "Sequential"), ("parallel", "Parallel")],
        default="sequential",
    )
    respect_schedule = fields.Boolean(
        default=True,
        string="Respektera schema",
        help="Ring bara under personens arbetstid (resource.calendar via HR). "
             "Utanför arbetstid: meddela 'tillbaka {tid}' och gå till röstbrevlåda.",
    )
    respect_calendar = fields.Boolean(
        default=True,
        string="Respektera kalender",
        help="Ring inte när personen är upptagen i kalendern (calendar.event). "
             "Upptagen: meddela 'tillbaka {tid}' och gå till röstbrevlåda.",
    )
    sub_extension_ids = fields.One2many(
        "pbx.sub_extension",
        "extension_id",
        string="Sub-Extensions",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "extension_company_unique",
            "unique(company_id, public_number)",
            "Extension number must be unique within the company!",
        ),
    ]

    def _compute_display_name(self):
        for rec in self:
            user = rec.user_id.name or ""
            base = rec.public_number or rec.callerid_name or ""
            rec.display_name = "%s – %s" % (base, user) if user else base

    def get_dialplan_target(self):
        self.ensure_one()
        domain = self.company_id.pbx_domain or ""
        return ("%s-ext-%s" % (domain, self.public_number), "s", "1")

    def get_internal_number(self):
        self.ensure_one()
        return self.public_number

    def _get_work_calendar(self):
        """The user's working-hours calendar (via hr.employee), or None."""
        user = self.user_id
        if not user:
            return None
        for emp in user.employee_ids:
            if emp.resource_calendar_id:
                return emp.resource_calendar_id
        return None

    def get_availability(self):
        """Return ``(available, next_available_ts)`` for follow-me routing.

        Respects ``respect_schedule`` (resource.calendar via HR) and
        ``respect_calendar`` (calendar.event busy check).
        ``next_available_ts`` = epoch seconds of the next time the person is
        available (0 = unknown). Fail-open: missing calendar / uninstalled
        modules / missing user mean 'available'.
        """
        self.ensure_one()
        import pytz
        from datetime import timedelta

        now = fields.Datetime.now()  # naive UTC

        # 1) Calendar busy check
        if self.respect_calendar and "calendar.event" in self.env:
            partner = self.user_id.partner_id if self.user_id else None
            if partner:
                events = self.env["calendar.event"].search(
                    [
                        ("partner_ids", "in", [partner.id]),
                        ("start", "<=", now),
                        ("stop", ">=", now),
                        ("state", "in", ["open", "done"]),
                    ],
                    limit=1,
                )
                if events:
                    stop = events[0].stop
                    if isinstance(stop, str):
                        stop = fields.Datetime.to_datetime(stop)
                    return False, int(stop.timestamp())

        # 2) Schedule check (resource.calendar via HR)
        if self.respect_schedule:
            cal = self._get_work_calendar()
            if cal:
                tz = pytz.timezone(cal.tz or "UTC")
                local_now = now.replace(tzinfo=pytz.utc).astimezone(tz)
                atts = cal.attendance_ids.filtered(
                    lambda a: a.dayofweek == str(local_now.weekday())
                )
                in_hours = any(
                    att.hour_from <= local_now.hour + local_now.minute / 60.0 <= att.hour_to
                    for att in atts
                )
                if not in_hours:
                    # Next working-hours start (today or upcoming days)
                    for day_offset in range(8):
                        day = local_now + timedelta(days=day_offset)
                        day_atts = cal.attendance_ids.filtered(
                            lambda a: a.dayofweek == str(day.weekday())
                        )
                        for att in day_atts.sorted("hour_from"):
                            h = int(att.hour_from)
                            m = int(round((att.hour_from - h) * 60))
                            start_dt = day.replace(
                                hour=h, minute=m, second=0, microsecond=0
                            )
                            if start_dt > local_now:
                                return False, int(
                                    start_dt.astimezone(pytz.utc).timestamp()
                                )
                    return False, 0
        return True, 0

    def _render_availability_gate(self, odoo_url, webhook_token):
        """Dialplan lines checking availability before follow-me ringing."""
        if not (self.respect_schedule or self.respect_calendar):
            return ""
        if not odoo_url:
            return ""
        return (
            "same => n,Set(OC_AVAIL=${{CURL({url}/pbx/availability/{num}?token={tok})}})\n"
            'same => n,GotoIf($["${{CUT(OC_AVAIL,:,1)}}" = "busy"]?unavailable)\n'
        ).format(url=odoo_url, num=self.public_number, tok=webhook_token)

    # ------------------------------------------------------------------
    # Click-to-call
    # ------------------------------------------------------------------

    @api.model
    def action_click_to_call_current_user(self, number):
        """Click-to-call för inloggad användare (anropas via RPC/route)."""
        ext = self.search([("user_id", "=", self.env.user.id)], limit=1)
        if not ext:
            raise UserError(_("Du har ingen PBX-anknytning kopplad."))
        return ext.action_click_to_call(number)

    def action_click_to_call(self, number):
        """Ring användarens första aktiva enhet och koppla målnumret.

        Publicerar ``pbx.cmd.Action.Originate`` (→ daemonen kör AMI Originate):
        channel = PJSIP/<username> (användarens telefon ringer först),
        exten = <normaliserat nummer>, context = <domain>-outbound.
        """
        self.ensure_one()
        if not self.user_id:
            raise UserError(_("Anknytningen har ingen användare kopplad."))
        device = self.sub_extension_ids.filtered(
            lambda s: s.active and s.type != "voicemail"
        ).sorted("sequence")[:1]
        if not device:
            raise UserError(_("Ingen aktiv enhet finns på anknytningen."))
        number = self._normalize_click_number(number)
        if not number:
            raise UserError(_("Ogiltigt telefonnummer."))
        company = self.company_id
        domain = company.pbx_domain
        if not domain:
            raise UserError(_("Ingen SIP-domän är konfigurerad för företaget."))
        channel = "PJSIP/%s" % device.username
        ok = self.env["pbx.mq.publisher"].action_originate(
            server=company.pbx_server_host or "asterisk",
            channel=channel,
            context="%s-outbound" % domain,
            exten=number,
        )
        return {
            "ok": bool(ok),
            "channel": channel,
            "exten": number,
            "device": device.number,
        }

    @staticmethod
    def _normalize_click_number(number):
        """Normalisera till E.164: '+46 (70) 123-456' / '0701-23 45 67' /
        '46725020525' → '+46725020525'.

        - Ledande '+' → som det är
        - Svensk E.164 utan '+' (46 + minst 9 siffror) → lägg till '+'
        - Svenskt nationellt format (0 + minst 8 siffror) → +46 + resten
        """
        digits = re.sub(r"[\s\(\)\-\.]", "", number or "").strip()
        if not digits:
            return ""
        if digits.startswith("+"):
            return digits
        if digits.startswith("46") and len(digits) >= 11 and digits[1].isdigit():
            return "+" + digits
        if digits.startswith("0") and len(digits) >= 9:
            return "+46" + digits[1:]
        return digits
