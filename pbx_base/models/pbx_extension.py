# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PbxExtension(models.Model):
    _name = "pbx.extension"
    _inherit = ["pbx.destination.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "PBX Extension (public number)"

    public_number = fields.Char(required=True)
    user_id = fields.Many2one("res.users", string="Odoo User")
    callerid_name = fields.Char(
        help="Visas som namn på utgående samtal. Fylls i från användarens namn "
             "när en användare kopplas — kan överskrivas manuellt."
    )

    @api.onchange("user_id")
    def _onchange_user_id(self):
        if self.user_id and not self.callerid_name:
            self.callerid_name = self.user_id.name
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

    def _compute_display_name(self):
        for rec in self:
            user = rec.user_id.name or ""
            base = rec.public_number or rec.callerid_name or ""
            rec.display_name = "%s – %s" % (base, user) if user else base

    def get_dialplan_target(self):
        self.ensure_one()
        domain = self.company_id.pbx_domain or ""
        return ("%s-ext-%s" % (domain, self.public_number), "s", "1")

    def get_internal_number(self):
        self.ensure_one()
        return self.public_number
