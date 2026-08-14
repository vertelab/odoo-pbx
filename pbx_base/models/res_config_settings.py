# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import secrets

from odoo import fields, models, api
from odoo.tools import config as odoo_config

_logger = logging.getLogger(__name__)

# Nycklar som pbx_admin (Salt) kan provisionera via odoo.conf [options].
# När någon av dem finns i odoo.conf är inställningarna "managed" (read-only i
# formuläret) — admin sker centralt på ledningssystemet, inte per minion.
PBX_ODOO_CONF_KEYS = (
    "pbx_domain",
    "pbx_server_host",
    "pbx_api_key",
    "pbx_odoo_url",
    "pbx_sip_port",
    "pbx_turn_enabled",
    "pbx_turn_server",
    "pbx_mq_host",
    "pbx_mq_port",
    "pbx_mq_user",
    "pbx_mq_password",
    "pbx_mq_vhost",
    "pbx_webhook_token",
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ── Central admin-styrning (odoo.conf) ────────────────────────
    pbx_config_managed = fields.Boolean(
        string="PBX konfigureras centralt",
        compute="_compute_pbx_config_managed",
        help="True när pbx_admin/Salt har provisionerat inställningarna via "
        "odoo.conf — fälten blir read-only eftersom admin sker centralt.",
    )

    @api.depends_context("company")
    def _compute_pbx_config_managed(self):
        managed = any(odoo_config.get(key) for key in PBX_ODOO_CONF_KEYS)
        for rec in self:
            rec.pbx_config_managed = managed

    # ── Grundinställningar (per företag — multicompany) ──
    pbx_domain = fields.Char(
        string="SIP Domain",
        related="company_id.pbx_domain",
        readonly=False,
        help="Företagets SIP-domän på Asterisk-servern (per företag).",
    )
    pbx_server_host = fields.Char(
        string="PBX Server",
        related="company_id.pbx_server_host",
        readonly=False,
        help="Asterisk-serveradress (per företag).",
    )
    pbx_api_key = fields.Char(
        string="API Key",
        related="company_id.pbx_api_key",
        readonly=False,
        groups="base.group_system",
        help="API-nyckel mot Asterisk-servern / provisioning-daemon (per företag).",
    )
    pbx_odoo_url = fields.Char(
        string="Odoo URL",
        related="company_id.pbx_odoo_url",
        readonly=False,
        help="Kundens Odoo-bas-URL för tillgänglighetskontroll i genererad dialplan.",
    )
    pbx_sip_port = fields.Char(
        string="SIP Port",
        related="company_id.pbx_sip_port",
        readonly=False,
        help="SIP-port för enheter (per företag).",
    )
    pbx_turn_enabled = fields.Boolean(
        string="TURN aktiverad",
        related="company_id.pbx_turn_enabled",
        readonly=False,
        help="TURN för enheter bakom NAT (coturn gör både STUN+TURN på samma adress).",
    )
    pbx_turn_server = fields.Char(
        string="TURN Server",
        config_parameter="pbx.turn.server",
        readonly=False,
        help="Coturn-adress för STUN+TURN — t.ex. turn.vertel.se:3478. "
        "Provisioneras av pbx_admin via odoo.conf.",
    )

    # ── RabbitMQ + webhook ──
    # Host och Vhost härleds från PBX-servern respektive SIP-domänen
    # (tas bort ur formuläret — se pbx_mq.publisher._get_config).
    pbx_mq_port = fields.Integer(
        string="RabbitMQ Port",
        config_parameter="pbx.mq.port",
        default=5672,
    )
    pbx_mq_user = fields.Char(
        string="RabbitMQ User",
        config_parameter="pbx.mq.user",
        default="pbx",
    )
    pbx_mq_password = fields.Char(
        string="RabbitMQ Password",
        config_parameter="pbx.mq.password",
    )
    pbx_mq_vhost = fields.Char(
        string="RabbitMQ Vhost",
        config_parameter="pbx.mq.vhost",
        default="pbx",
    )
    pbx_webhook_token = fields.Char(
        string="PBX Webhook Token",
        config_parameter="pbx.webhook.token",
        groups="base.group_system",
        readonly=True,
        help="Bearer-token som pbx_ami_daemon använder mot /pbx/webhook. "
        "Genereras automatiskt om ingen finns (fristående användning), "
        "eller provisioneras av pbx_admin via odoo.conf.",
    )
    pbx_webhook_url = fields.Char(
        string="PBX Webhook URL",
        compute="_compute_pbx_webhook_url",
        readonly=True,
        help="Fullständig endpoint som pbx_ami_daemon POSTar till "
        "(baseras på Odoo-URL eller web.base.url).",
    )

    @api.depends_context("company")
    def _compute_pbx_webhook_url(self):
        base = (
            self.company_id.pbx_odoo_url
            or self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        )
        for rec in self:
            rec.pbx_webhook_url = "%s/pbx/webhook" % (base or "").rstrip("/")

    # ── Webhook-token: auto-generering (fristående) ────────────────
    @api.model
    def _ensure_webhook_token(self):
        """Generera en webhook-token om ingen finns (idempotent).

        Fristående användning: modulen ska fungera utan Salt/pbx_admin.
        Anropas från get_values så att token skapas när formuläret öppnas
        om den saknas helt.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        token = ICP.get_param("pbx.webhook.token", "")
        if not token:
            token = secrets.token_urlsafe(32)
            ICP.set_param("pbx.webhook.token", token)
            _logger.info("PBX webhook-token genererad (saknades)")
        return token

    def get_values(self):
        res = super().get_values()
        self._ensure_webhook_token()
        res["pbx_webhook_token"] = self.env[
            "ir.config_parameter"
        ].sudo().get_param("pbx.webhook.token", "")
        return res

    def action_generate_webhook_token(self):
        """Generera en ny webhook-token (knapp i settings-formuläret)."""
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(
            "pbx.webhook.token", token
        )
        self.pbx_webhook_token = token
        _logger.info("PBX webhook-token genererad på nytt (manuellt)")
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
