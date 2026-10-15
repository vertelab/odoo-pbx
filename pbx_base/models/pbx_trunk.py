# Copyright 2026 Vertel Sverige AB
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
        help="Source IP for inbound trunk calls (identify match). Empty = "
             "resolve the trunk host via DNS at config generation time.",
    )
    identify_nets = fields.Text(
        string="Identify Networks",
        help="One IP or CIDR per line for inbound trunk calls (identify match). "
             "Use this when the provider signals from several addresses or a "
             "whole range — e.g. Telavox, which sends inbound INVITEs from "
             "multiple SBCs in 80.83.208.0/22 and 80.83.212.0/24. "
             "Empty = fall back to Identify IP, then DNS on the host. "
             "Lines starting with # are ignored.",
    )
    inbound_destination_id = fields.Reference(
        selection=destination_models,
        string="Inbound Account Destination",
        help="Destination for inbound calls where Telavox/the provider uses "
             "the account name (username) as the called party instead of the DID. "
             "Tom = ingen kontonamns-rutt.",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
