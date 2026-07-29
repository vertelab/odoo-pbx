# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class VoipPbx(models.Model):
    _inherit = "voip.pbx"

    company_id = fields.Many2one("res.company", string="Company")
