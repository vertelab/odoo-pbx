# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # Proxy fields for self-service UI — read/write through to pbx.extension
    pbx_ring_strategy = fields.Selection(
        related="pbx_extension_id.ring_strategy",
        readonly=False,
    )
    pbx_skip_if_busy = fields.Boolean(
        related="pbx_extension_id.skip_if_busy",
        readonly=False,
    )
    pbx_sub_extension_ids = fields.One2many(
        related="pbx_extension_id.sub_extension_ids",
        readonly=False,
    )
