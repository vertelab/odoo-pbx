# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import shlex
import subprocess

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PbxTenantSalt(models.Model):
    """Salt-brygga: deployar växelinformation till kundens Odoo-minion.

    Knappen **Deploy** kör ``salt <minion_id> state.apply odoo.pbx`` med en
    pillar innehållande SIP-domän, serveradress, API-nyckel, RabbitMQ- och
    webhook-konfiguration. Salt-staten (vertelab/salt: odoo/pbx.sls) skriver
    värdena till kund-Odoo:s DB.
    """

    _inherit = "pbx.tenant"

    minion_id = fields.Char(
        string="Salt Minion",
        help="Salt-minion-id för kundens Odoo (t.ex. luke18).",
    )
    deploy_status = fields.Selection(
        [("draft", "Ej deployad"), ("ok", "OK"), ("error", "Fel"), ("dry-run", "Dry-run")],
        string="Deploy-status",
        default="draft",
    )
    last_deploy = fields.Datetime(string="Senaste deploy")
    deploy_log = fields.Text(string="Deploy-logg")

    def deploy_config(self):
        """Deploya växelinformationen till kundminionen via Salt."""
        self.ensure_one()
        if not self.minion_id:
            raise UserError(_("Sätt Salt-minion-id på tenanten först."))
        pillar = self._build_pillar()
        command = self._salt_command(pillar)
        dry_run = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("pbx_saltstack.dry_run", "false")
            .lower()
            in ("1", "true", "yes")
        )
        if dry_run:
            self.deploy_status = "dry-run"
            self.deploy_log = command
            self.last_deploy = fields.Datetime.now()
            return {"status": "dry-run", "command": command}
        try:
            res = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.deploy_status = "ok" if res.returncode == 0 else "error"
            self.deploy_log = (res.stdout or "")[:4000] + "\n" + (res.stderr or "")[:4000]
            self.last_deploy = fields.Datetime.now()
            return {"status": self.deploy_status, "output": self.deploy_log}
        except Exception as e:
            self.deploy_status = "error"
            self.deploy_log = str(e)
            _logger.exception("Salt deploy misslyckades för %s", self.domain)
            return {"status": "error", "error": str(e)}

    def _build_pillar(self):
        """Bygg pillar med växelinformation att deploya till kundminionen."""
        self.ensure_one()
        company = self.company_id
        server = self.server_id
        ICP = self.env["ir.config_parameter"].sudo()
        mq = {
            "host": ICP.get_param("pbx.mq.host", ""),
            "port": ICP.get_param("pbx.mq.port", "5672"),
            "user": ICP.get_param("pbx.mq.user", "pbx"),
            "password": ICP.get_param("pbx.mq.password", ""),
            "vhost": ICP.get_param("pbx.mq.vhost", "pbx"),
        }
        return {
            "pbx": {
                "domain": self.domain,
                "server_host": (server.host if server else "") or company.pbx_server_host or "",
                "api_key": company.pbx_api_key or "",
                "mq": mq,
                "webhook_token": ICP.get_param("pbx.webhook.token", ""),
                "db_name": ICP.get_param("pbx_saltstack.db_name", "odoo"),
            }
        }

    def _salt_command(self, pillar):
        """``salt <minion> state.apply odoo.pbx pillar='{json}'``."""
        salt_bin = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("pbx_saltstack.salt_bin", "salt")
        )
        return "%s '%s' state.apply odoo.pbx pillar='%s'" % (
            salt_bin,
            self.minion_id,
            json.dumps(pillar).replace("'", "'\\''"),
        )
