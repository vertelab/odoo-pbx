# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    pbx_extension_id = fields.Many2one(
        "pbx.extension",
        string="PBX Extension",
        help="The user's primary PBX extension",
    )

    pbx_call_count = fields.Integer(
        string="Calls", compute="_compute_pbx_call_count"
    )

    def _compute_pbx_call_count(self):
        for rec in self:
            rec.pbx_call_count = self.env["pbx.call"].search_count(
                [("user_id", "=", rec.id)]
            )

    def action_pbx_call_user(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "My Calls",
            "res_model": "pbx.call",
            "view_mode": "list,form",
            "domain": [("user_id", "=", self.id)],
        }
