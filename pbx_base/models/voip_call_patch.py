# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class VoipCall(models.Model):
    _inherit = "voip.call"

    tenant_id = fields.Many2one("pbx.tenant", string="Tenant", index=True)
    company_id = fields.Many2one(related="tenant_id.company_id", store=True)

    state = fields.Selection(selection_add=[("voicemail", "Voicemail")])

    def _get_voicemail_state(self):
        return "voicemail"
