# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://vertel.se).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    pbx_call_count = fields.Integer(
        string="Calls", compute="_compute_pbx_call_count"
    )

    def _compute_pbx_call_count(self):
        for rec in self:
            rec.pbx_call_count = self.env["pbx.call"].search_count(
                [("partner_id", "=", rec.id)]
            )

    def action_pbx_call_partner(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Calls",
            "res_model": "pbx.call",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
        }
