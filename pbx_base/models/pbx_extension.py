# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PbxExtension(models.Model):
    _name = "pbx.extension"
    _inherit = ["pbx.destination.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "PBX Extension (public number)"

    public_number = fields.Char(required=True)
    user_id = fields.Many2one("res.users", string="Odoo User")
    callerid_name = fields.Char(
        help="Visas som namn på utgående samtal. Fylls i från användarens namn "
             "när en användare kopplas — kan överskrivas manuellt."
    )

    @api.onchange("user_id")
    def _onchange_user_id(self):
        if self.user_id and not self.callerid_name:
            self.callerid_name = self.user_id.name
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
    skip_if_busy = fields.Boolean(
        default=True,
        help="If any active device is already INUSE, skip ringing entirely "
             "and send the call directly to voicemail.",
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
