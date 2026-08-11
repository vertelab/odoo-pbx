# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .pbx_destination_mixin import destination_models


class PbxInboundRoute(models.Model):
    _name = "pbx.inbound_route"
    _inherit = ["mail.thread", "mail.activity.mixin", "pbx.config.dirty.mixin"]
    _description = "PBX Inbound Route (DID/CID -> destination)"
    _order = "sequence, id"

    sequence = fields.Integer(default=10, help="Lower sequence is matched first")

    def _compute_display_name(self):
        for rec in self:
            did = rec.did or "*"
            cid = rec.cid or "*"
            dest = rec.destination_id.display_name if rec.destination_id else ""
            rec.display_name = "%s → %s" % (did, dest or "?")
    did = fields.Char(
        string="DID",
        help="Number or Asterisk pattern to match. Empty = any DID",
    )
    cid = fields.Char(
        string="Caller ID",
        help="Caller ID match. Empty = any caller",
    )
    destination_id = fields.Reference(
        selection=destination_models,
        string="Destination",
        required=True,
    )
    description = fields.Char()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "inbound_route_unique",
            "unique(company_id, did, cid)",
            "An inbound route with this DID/CID combination already exists!",
        ),
    ]
