# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    """Tenant as res.partner (the bifrost pattern: res.partner + a boolean).

    A partner with `is_pbx_tenant = True` is a PBX tenant: SIP domain,
    Asterisk server, Salt minion and deploy status. Everything standard partner
    (image, chatter, kanban, archive ribbon) comes for free.
    """

    _inherit = "res.partner"

    is_pbx_tenant = fields.Boolean(
        string="PBX Tenant",
        help="The checkbox that turns the partner into a PBX tenant (shown in PBX → Tenants).",
    )
    domain = fields.Char(
        string="SIP Domain",
        help="The customer's SIP domain on the Asterisk server, e.g. vertel.se. Unique among tenants.",
    )
    server_id = fields.Many2one(
        "pbx.server",
        string="PBX Server",
        help="The Asterisk server where the tenant's PBX runs.",
    )
    minion_id = fields.Many2one(
        "salt.minion",
        string="Salt Minion",
        help="The customer's Salt minion (customer Odoo) that the PBX info is deployed to.",
    )
    deploy_status = fields.Selection(
        [
            ("draft", "Not deployed"),
            ("ok", "OK"),
            ("error", "Error"),
            ("dry-run", "Dry-run"),
        ],
        string="Deploy Status",
        default="draft",
    )
    last_deploy = fields.Datetime(string="Last Deploy")
    deploy_log = fields.Text(string="Deploy Log")

    def init(self):
        """Partial unique index: only tenants with a non-empty domain."""
        super().init()
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS res_partner_pbx_domain_uniq
            ON res_partner (domain)
            WHERE is_pbx_tenant AND domain IS NOT NULL AND domain <> ''
            """
        )

    # ------------------------------------------------------------------
    # Minion sync (deploy of PBX info via Salt)
    # ------------------------------------------------------------------

    def deploy_config(self):
        """Deploy the PBX information to the customer minion via Salt (salt-api).

        Runs ``state.apply odoo.pbx`` with a pillar containing the SIP domain,
        server address, API key, RabbitMQ and webhook configuration.
        """
        self.ensure_one()
        if not self.is_pbx_tenant:
            raise UserError(_("The partner is not a PBX tenant."))
        if not self.minion_id:
            raise UserError(_("Set a Salt minion on the tenant first."))
        pillar = self._build_pillar()
        dry_run = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("pbx_admin.salt_dry_run", "false")
            .lower()
            in ("1", "true", "yes")
        )
        if dry_run:
            self.deploy_status = "dry-run"
            self.deploy_log = "state.apply odoo.pbx pillar=%s" % json.dumps(pillar)
            self.last_deploy = fields.Datetime.now()
            return {"status": "dry-run", "pillar": pillar}
        try:
            result = self.minion_id._call_salt_api(
                "local",
                self.minion_id.name,
                "state.apply",
                "odoo.pbx",
                pillar=pillar,
            )
            self.deploy_status = "ok"
            self.deploy_log = json.dumps(result, default=str)[:4000]
            self.last_deploy = fields.Datetime.now()
            return {"status": "ok", "result": result}
        except Exception as e:
            self.deploy_status = "error"
            self.deploy_log = str(e)[:4000]
            _logger.exception("Salt deploy failed for %s", self.domain)
            return {"status": "error", "error": str(e)}

    def _build_pillar(self):
        """Build the pillar with PBX information to deploy to the customer minion."""
        self.ensure_one()
        server = self.server_id
        ICP = self.env["ir.config_parameter"].sudo()
        company = self.company_id
        api_key = company.pbx_api_key or ""
        # RabbitMQ runs on the PBX server and uses the SIP domain as vhost —
        # host/vhost are derived (unless provisioned centrally in odoo.conf).
        # User = SIP domain, password = API key (one secret per domain,
        # permission scoped to the instance's domain set on the RabbitMQ side).
        mq = {
            "host": ICP.get_param("pbx.mq.host", "")
            or (server.host if server else ""),
            "port": ICP.get_param("pbx.mq.port", "5672"),
            "user": ICP.get_param("pbx.mq.user", "") or (self.domain or "pbx"),
            "password": ICP.get_param("pbx.mq.password", "") or api_key,
            "vhost": ICP.get_param("pbx.mq.vhost", "") or (self.domain or "pbx"),
        }
        return {
            "pbx": {
                "domain": self.domain or "",
                "server_host": (server.host if server else "") or "",
                "api_key": api_key,
                "mq": mq,
                "webhook_token": ICP.get_param("pbx.webhook.token", ""),
                "turn_server": ICP.get_param("pbx.turn.server", ""),
                "db_name": ICP.get_param("pbx_admin.salt_db_name", "odoo"),
            }
        }

    def action_derive_domain_from_website(self):
        """Derive the SIP domain from the partner's website (strip https/www/path).

        Example: https://www.kund.se → kund.se. Just a suggestion — the user
        can adjust it before saving. The SIP domain should be stable and explicit,
        not automatically follow the website on changes.
        """
        self.ensure_one()
        website = (self.website or "").strip().lower()
        if not website:
            raise UserError(_("The partner has no website configured."))
        domain = re.sub(r"^https?://", "", website)
        domain = re.sub(r"^www\.", "", domain)
        domain = domain.split("/")[0].split(":")[0]
        if not domain:
            raise UserError(_("Could not derive a domain from the website."))
        self.domain = domain
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def action_open_partner(self):
        """Open the underlying res.partner record (the full form)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
