# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .pbx_destination_mixin import destination_models


class PbxOutboundRoute(models.Model):
    _name = "pbx.outbound_route"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "PBX Outbound Route"
    _order = "sequence, id"

    sequence = fields.Integer(default=10, help="Lower sequence is tried first")
    name = fields.Char(required=True)
    pattern = fields.Char(
        required=True,
        help="Asterisk dial pattern, e.g. _0. (national) or _00. (international)",
    )
    trunk_ids = fields.One2many(
        "pbx.outbound.route.trunk", "route_id", string="Trunks"
    )
    failover_destination_id = fields.Reference(
        selection=destination_models,
        string="Failover Destination",
        help="Where the call goes when every trunk in this route fails",
    )
    time_source = fields.Selection(
        [
            ("none", "No time restriction"),
            ("time_condition", "Time Condition"),
            ("calendar", "Working Hours Calendar"),
        ],
        string="Time Restriction",
        default="none",
    )
    time_condition_id = fields.Many2one(
        "pbx.time_condition",
        string="Time Condition",
        help="Used when time_source = Time Condition",
    )
    calendar_id = fields.Many2one(
        "resource.calendar",
        string="Working Hours",
        help="Used when time_source = Working Hours Calendar. "
             "Attendance lines define working hours, leaves exclude days.",
    )
    strip_digits = fields.Integer(
        default=0, help="Leading digits to strip from the dialed number"
    )
    prepend_digits = fields.Char(
        help="Prefix added before the number sent to the trunk"
    )
    outbound_callerid = fields.Char(string="Outbound CallerID")
    password = fields.Char(string="PIN", groups="base.group_system")
    emergency_route = fields.Boolean(
        help="Highest priority — matches regardless of route ordering"
    )
    trunk_count = fields.Integer(compute="_compute_trunk_count", string="Trunks")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )

    def _compute_trunk_count(self):
        for route in self:
            route.trunk_count = len(route.trunk_ids)


class PbxOutboundRouteTrunk(models.Model):
    _name = "pbx.outbound.route.trunk"
    _description = "Outbound Route Trunk (failover order)"
    _order = "sequence, id"

    route_id = fields.Many2one(
        "pbx.outbound_route", string="Route", required=True, ondelete="cascade"
    )
    trunk_id = fields.Many2one(
        "pbx.trunk", string="Trunk", required=True, ondelete="restrict"
    )
    sequence = fields.Integer(default=10, help="Failover order within the route")
    continue_ = fields.Boolean(
        string="Continue",
        default=True,
        help="Try the next trunk when this one fails (busy/unavailable)",
    )
    company_id = fields.Many2one(related="route_id.company_id", store=True)
