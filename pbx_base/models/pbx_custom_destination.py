# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxCustomDestination(models.Model):
    _name = "pbx.custom.destination"
    _inherit = ["pbx.destination.mixin"]
    _description = "PBX Custom Destination (raw dialplan goto-triple)"

    tenant_id = fields.Many2one("pbx.tenant", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    context = fields.Char(
        required=True,
        help="Asterisk dialplan context, e.g. app-blackhole",
    )
    exten = fields.Char(required=True, default="s", help="Extension within the context")
    priority = fields.Char(required=True, default="1", help="Priority within the context")

    def get_dialplan_target(self):
        self.ensure_one()
        return (self.context, self.exten, self.priority)
