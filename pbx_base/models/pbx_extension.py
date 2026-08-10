# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxExtension(models.Model):
    _name = "pbx.extension"
    _description = "PBX Extension (public number)"

    tenant_id = fields.Many2one("pbx.tenant", required=True, ondelete="cascade")
    public_number = fields.Char(required=True)
    user_id = fields.Many2one("res.users", string="Odoo User")
    callerid_name = fields.Char()
    description = fields.Char(
        string="Description",
        help="Visas i FOP2-panelen, t.ex. 'Reception', 'Anna – Support'",
    )
    is_receptionist = fields.Boolean(
        string="Receptionist",
        help="Receptionist ser alla anknytningar + allt inkommande + manuell hantering i FOP2",
    )
    ring_strategy = fields.Selection(
        [("sequential", "Sequential"), ("parallel", "Parallel")],
        default="sequential",
    )
    sub_extension_ids = fields.One2many(
        "pbx.sub_extension",
        "extension_id",
        string="Sub-Extensions",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(related="tenant_id.company_id", store=True)

    _sql_constraints = [
        (
            "extension_tenant_unique",
            "unique(tenant_id, public_number)",
            "Extension number must be unique within a tenant!",
        ),
    ]
