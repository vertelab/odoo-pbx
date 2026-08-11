# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class VoipCall(models.Model):
    _inherit = "voip.call"

    company_id = fields.Many2one("res.company", string="Company", index=True)

    state = fields.Selection(selection_add=[("voicemail", "Voicemail")])

    def _get_voicemail_state(self):
        return "voicemail"
