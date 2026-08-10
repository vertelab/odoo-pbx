# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxVoicemailDestination(models.Model):
    _name = "pbx.voicemail.destination"
    _inherit = ["pbx.destination.mixin"]
    _description = "PBX Voicemail Destination"

    tenant_id = fields.Many2one("pbx.tenant", required=True, ondelete="cascade")
    extension_id = fields.Many2one(
        "pbx.extension", string="Extension", required=True, ondelete="cascade"
    )
    name = fields.Char(compute="_compute_name", string="Name")

    def _compute_name(self):
        for rec in self:
            rec.name = "Voicemail %s" % (rec.extension_id.public_number or "")

    def get_dialplan_target(self):
        self.ensure_one()
        domain = self.tenant_id.domain
        return ("%s-vm-%s" % (domain, self.extension_id.public_number), "s", "1")

    def get_internal_number(self):
        return None
