# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxExtension(models.Model):
    _name = "pbx.extension"
    _inherit = ["pbx.destination.mixin"]
    _description = "PBX Extension (public number)"

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
    skip_if_busy = fields.Boolean(
        default=True,
        help="If any active device is already INUSE, skip ringing entirely "
             "and send the call directly to voicemail.",
    )
    sub_extension_ids = fields.One2many(
        "pbx.sub_extension",
        "extension_id",
        string="Sub-Extensions",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "extension_company_unique",
            "unique(company_id, public_number)",
            "Extension number must be unique within the company!",
        ),
    ]

    def get_dialplan_target(self):
        self.ensure_one()
        domain = self.env["ir.config_parameter"].get_param("pbx.domain", "")
        return ("%s-ext-%s" % (domain, self.public_number), "s", "1")

    def get_internal_number(self):
        self.ensure_one()
        return self.public_number
