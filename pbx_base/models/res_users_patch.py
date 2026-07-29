# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    pbx_extension_id = fields.Many2one(
        "pbx.extension",
        string="PBX Extension",
        help="The user's primary PBX extension",
    )
