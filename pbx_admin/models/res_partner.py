# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    """Tenant som res.partner (bifrost-mönstret: res.partner + kryssruta).

    En partner med `is_pbx_tenant = True` är en PBX-tenant: SIP-domän,
    Asterisk-server, Salt-minion och deploy-status. Allt standard-partner
    (bild, chatter, kanban, arkiv-ribbon) kommer gratis.
    """

    _inherit = "res.partner"

    is_pbx_tenant = fields.Boolean(
        string="PBX-tenant",
        help="Kryssrutan som gör partnern till en PBX-tenant (visas i PBX → Tenants).",
    )
    domain = fields.Char(
        string="SIP-domän",
        help="Kundens SIP-domän på Asterisk-servern, t.ex. vertel.se. Unikt bland tenanter.",
    )
    server_id = fields.Many2one(
        "pbx.server",
        string="PBX Server",
        help="Asterisk-servern där tenantens växel körs.",
    )
    minion_id = fields.Many2one(
        "salt.minion",
        string="Salt Minion",
        help="Kundens Salt-minion (kund-Odoo) som växelinfo deployas till.",
    )
    deploy_status = fields.Selection(
        [
            ("draft", "Ej deployad"),
            ("ok", "OK"),
            ("error", "Fel"),
            ("dry-run", "Dry-run"),
        ],
        string="Deploy-status",
        default="draft",
    )
    last_deploy = fields.Datetime(string="Senaste deploy")
    deploy_log = fields.Text(string="Deploy-logg")

    def init(self):
        """Partiellt unikt index: bara tenanter med icke-tom domän."""
        super().init()
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS res_partner_pbx_domain_uniq
            ON res_partner (domain)
            WHERE is_pbx_tenant AND domain IS NOT NULL AND domain <> ''
            """
        )

    # ------------------------------------------------------------------
    # Minion-sync (deploy av växelinfo via Salt)
    # ------------------------------------------------------------------

    def deploy_config(self):
        """Deploya växelinformationen till kundminionen via Salt (salt-api).

        Kör ``state.apply odoo.pbx`` med en pillar innehållande SIP-domän,
        serveradress, API-nyckel, RabbitMQ- och webhook-konfiguration.
        """
        self.ensure_one()
        if not self.is_pbx_tenant:
            raise UserError(_("Partnern är inte en PBX-tenant."))
        if not self.minion_id:
            raise UserError(_("Sätt Salt-minion på tenanten först."))
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
            _logger.exception("Salt deploy misslyckades för %s", self.domain)
            return {"status": "error", "error": str(e)}

    def _build_pillar(self):
        """Bygg pillar med växelinformation att deploya till kundminionen."""
        self.ensure_one()
        server = self.server_id
        ICP = self.env["ir.config_parameter"].sudo()
        mq = {
            "host": ICP.get_param("pbx.mq.host", ""),
            "port": ICP.get_param("pbx.mq.port", "5672"),
            "user": ICP.get_param("pbx.mq.user", "pbx"),
            "password": ICP.get_param("pbx.mq.password", ""),
            "vhost": ICP.get_param("pbx.mq.vhost", "pbx"),
        }
        company = self.company_id
        return {
            "pbx": {
                "domain": self.domain or "",
                "server_host": (server.host if server else "") or "",
                "api_key": company.pbx_api_key or "",
                "mq": mq,
                "webhook_token": ICP.get_param("pbx.webhook.token", ""),
                "db_name": ICP.get_param("pbx_admin.salt_db_name", "odoo"),
            }
        }

    def action_open_partner(self):
        """Öppna den underliggande res.partner-posten (fullständigt formulär)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
