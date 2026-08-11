# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .pbx_destination_mixin import DESTINATION_MODELS


class PbxInboundRoute(models.Model):
    _name = "pbx.inbound_route"
    _description = "PBX Inbound Route (DID/CID -> destination)"
    _order = "sequence, id"

    sequence = fields.Integer(default=10, help="Lower sequence is matched first")
    did = fields.Char(
        string="DID",
        help="Number or Asterisk pattern to match. Empty = any DID",
    )
    cid = fields.Char(
        string="Caller ID",
        help="Caller ID match. Empty = any caller",
    )
    destination_id = fields.Reference(
        selection=DESTINATION_MODELS,
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
