# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from odoo.addons.pbx_base.models.pbx_destination_mixin import destination_models


class PbxTrunk(models.Model):
    _name = "pbx.trunk"
    _inherit = ["mail.thread", "mail.activity.mixin", "pbx.config.dirty.mixin"]
    _description = "PBX SIP Trunk"

    name = fields.Char(required=True, help="e.g. Telia")
    host = fields.Char(required=True)
    port = fields.Integer(default=5060)
    username = fields.Char()
    secret = fields.Char(groups="base.group_system")
    channels = fields.Integer(default=10, help="Max simultaneous channels")
    callerid = fields.Char(string="Outgoing CallerID")
    identify_ip = fields.Char(
        string="Identify IP",
        help="Käll-IP för inkommande trunk-samtal (identify-match). Tom = "
             "resolvera trunkens host via DNS vid config-generering.",
    )
    inbound_destination_id = fields.Reference(
        selection=destination_models,
        string="Inbound Account Destination",
        help="Destination för inkommande samtal där Telavox/providern använder "
             "kontonamnet (username) som uppringd part istället för DID:et. "
             "Tom = ingen kontonamns-rutt.",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
