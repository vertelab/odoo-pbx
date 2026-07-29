# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, api


class PbxTenant(models.Model):
    _name = "pbx.tenant"
    _description = "PBX Tenant"

    name = fields.Char(required=True)
    domain = fields.Char(required=True, help="SIP domain, e.g. vertel.se")
    server_id = fields.Many2one("pbx.server", string="PBX Server", required=True)
    company_id = fields.Many2one("res.company", string="Company")
    active = fields.Boolean(default=True)
    plan = fields.Selection(
        [("standard", "Standard"), ("premium", "Premium"), ("enterprise", "Enterprise")],
        default="standard",
    )
    max_extensions = fields.Integer(default=50)
    notes = fields.Text()
    config_dirty = fields.Boolean(default=True, help="Config needs regeneration")

    _sql_constraints = [
        ("domain_unique", "unique(domain)", "SIP domain must be unique!"),
    ]

    def generate_config(self):
        """Generate and write Asterisk config for this tenant."""
        self.ensure_one()
        generator = self.env["pbx.config.generator"]
        generator.write_config(self)
        self.config_dirty = False

    def reload_asterisk(self):
        """Reload Asterisk configuration for this tenant's server."""
        self.ensure_one()
        generator = self.env["pbx.config.generator"]
        generator.generate_config()
        return generator.reload_asterisk(self.server_id)
