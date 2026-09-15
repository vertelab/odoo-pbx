# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://vertel.se).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PbxCall(models.Model):
    """Telephone transaction: an inbound or outbound call.

    Logged by pbx_ami_daemon → webhook (or manually during testing). Each call
    is looked up against res.partner (phone/mobile) and if the partner is
    missing it is created.
    """

    _name = "pbx.call"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "PBX Call (phone transaction)"
    _order = "start_date desc, id desc"

    partner_id = fields.Many2one(
        "res.partner", string="Contact", index=True, ondelete="set null"
    )
    user_id = fields.Many2one(
        "res.users", string="User", index=True, ondelete="set null"
    )
    extension_id = fields.Many2one(
        "pbx.extension", string="Extension", ondelete="set null"
    )
    direction = fields.Selection(
        [("incoming", "Incoming"), ("outgoing", "Outgoing")],
        string="Direction",
        required=True,
        default="incoming",
        index=True,
    )
    phone_number = fields.Char(string="Number", index=True)
    callerid_name = fields.Char(string="Caller ID")
    start_date = fields.Datetime(string="Start", index=True)
    stop_date = fields.Datetime(string="Stop")
    duration = fields.Integer(
        string="Duration (s)", compute="_compute_duration", store=True
    )
    pbx_handling = fields.Selection(
        [
            ("ringing", "Ringing"),
            ("answered", "Answered"),
            ("voicemail", "Voicemail"),
            ("queue", "Queue"),
            ("ivr", "IVR"),
            ("missed", "Missed"),
            ("busy", "Busy"),
            ("transferred", "Transferred"),
            ("outgoing", "Outgoing"),
        ],
        string="Handled by PBX",
        help="How the call was handled in the PBX (dialplan/AMI).",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )

    _sql_constraints = []

    def _compute_display_name(self):
        for rec in self:
            who = rec.partner_id.display_name or rec.phone_number or rec.callerid_name or "?"
            rec.display_name = "%s — %s" % (
                "In" if rec.direction == "incoming" else "Ut",
                who,
            )

    @api.depends("start_date", "stop_date")
    def _compute_duration(self):
        for rec in self:
            if rec.start_date and rec.stop_date:
                delta = rec.stop_date - rec.start_date
                rec.duration = max(0, int(delta.total_seconds()))
            else:
                rec.duration = 0

    @api.model
    def _resolve_partner(self, number, name=False, create=True):
        """Find res.partner by phone/mobile — auto-create it if missing."""
        number = (number or "").strip()
        if not number:
            return self.env["res.partner"], False
        partner = self.env["res.partner"].search(
            ["|", ("phone", "=", number), ("mobile", "=", number)],
            limit=1,
        )
        if partner:
            return partner, False
        if not create:
            return self.env["res.partner"], False
        partner = self.env["res.partner"].create(
            {"name": name or number, "phone": number}
        )
        return partner, True

    @api.model
    def log_call(self, values):
        """Create a pbx.call from an event (used by webhook/daemon).

        ``values``: phone_number, callerid_name, direction, start_date,
        stop_date, pbx_handling, user_id, extension_id.
        """
        number = (values or {}).get("phone_number") or ""
        name = (values or {}).get("callerid_name") or ""
        partner, created = self._resolve_partner(number, name)
        if created:
            _logger.info("Created res.partner %s for number %s", partner.id, number)
        call = self.create(
            {
                "partner_id": partner.id or False,
                "phone_number": number,
                "callerid_name": name,
                "direction": values.get("direction", "incoming"),
                "start_date": values.get("start_date") or fields.Datetime.now(),
                "stop_date": values.get("stop_date"),
                "pbx_handling": values.get("pbx_handling"),
                "user_id": values.get("user_id") or False,
                "extension_id": values.get("extension_id") or False,
                "company_id": values.get("company_id")
                or self.env.company.id,
            }
        )
        return call
