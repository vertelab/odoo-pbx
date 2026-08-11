# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import fields, models, api

_logger = logging.getLogger(__name__)


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
        """Generate and publish this tenant's Asterisk config (via MQ/daemon)."""
        self.ensure_one()
        generator = self.env["pbx.config.generator"]
        generator.write_config(self.domain, self.company_id.id or 1)
        self.config_dirty = False

    def write_config_local(self, configs=None):
        """Write generated config files to local disk (dev fallback)."""
        self.ensure_one()
        generator = self.env["pbx.config.generator"]
        if configs is None:
            configs = generator.generate_all(self.domain, self.company_id.id or 1)

        server = self.server_id
        import os

        tenant_dir = f"{server.config_path}/tenants/{self.domain}"
        os.makedirs(tenant_dir, exist_ok=True)
        for filename, content in configs.items():
            filepath = f"{tenant_dir}/{filename}"
            with open(filepath, "w") as f:
                f.write(content)
            _logger.info("Wrote config: %s for tenant %s", filepath, self.domain)
        return True

    def reload_asterisk(self):
        """Reload Asterisk configuration for this tenant's server via AMI."""
        self.ensure_one()
        server = self.server_id
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((server.host, server.ami_port))
            sock.recv(1024)  # Read banner
            sock.sendall(
                f"Action: Login\r\nUsername: {server.ami_user}\r\nSecret: {server.ami_secret}\r\n\r\n".encode()
            )
            sock.recv(1024)
            sock.sendall(b"Action: Command\r\nCommand: reload\r\n\r\n")
            sock.recv(1024)
            sock.close()
            return True
        except Exception as e:
            _logger.warning("AMI reload failed for %s: %s", server.host, e)
            return False
