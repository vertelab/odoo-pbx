# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import secrets

from odoo import fields, models, api
from odoo.tools import config as odoo_config

_logger = logging.getLogger(__name__)

# Keys that pbx_admin (Salt) can provision via odoo.conf [options].
# When any of them exists in odoo.conf the settings are "managed" (read-only in
# the form) — administration happens centrally on the management system, not per minion.
PBX_ODOO_CONF_KEYS = (
    "pbx_domain",
    "pbx_server_host",
    "pbx_api_key",
    "pbx_odoo_url",
    "pbx_sip_port",
    "pbx_sip_ws_port",
    "pbx_ws_server",
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
        help="True when pbx_admin/Salt has provisioned the settings via "
        "odoo.conf — the fields become read-only because administration is central.",
    )

    @api.depends_context("company")
    def _compute_pbx_config_managed(self):
        managed = any(odoo_config.get(key) for key in PBX_ODOO_CONF_KEYS)
        for rec in self:
            rec.pbx_config_managed = managed

    # ── Basic settings (per company — multicompany) ──
    pbx_domain = fields.Char(
        string="SIP Domain",
        related="company_id.pbx_domain",
        readonly=False,
        help="The company's SIP domain on the Asterisk server (per company).",
    )
    pbx_server_host = fields.Char(
        string="PBX Server",
        related="company_id.pbx_server_host",
        readonly=False,
        help="Asterisk server address (per company).",
    )
    pbx_api_key = fields.Char(
        string="API Key",
        related="company_id.pbx_api_key",
        readonly=False,
        groups="base.group_system",
        help="API key for the Asterisk server / provisioning daemon (per company).",
    )
    pbx_odoo_url = fields.Char(
        string="Odoo URL",
        related="company_id.pbx_odoo_url",
        readonly=False,
        help="The customer's Odoo base URL for availability checks in the generated dialplan.",
    )
    pbx_sip_port = fields.Char(
        string="SIP Port",
        related="company_id.pbx_sip_port",
        readonly=False,
        help="SIP port for devices (per company).",
    )
    pbx_sip_ws_port = fields.Integer(
        string="WebSocket Port",
        related="company_id.pbx_sip_ws_port",
        readonly=False,
        help="Asterisk HTTP/WebSocket port for the Odoo softphone (per company).",
    )
    pbx_external_ip = fields.Char(
        string="External IP (Asterisk)",
        config_parameter="pbx.external.ip",
        readonly=False,
        help="Public IP of the Asterisk box — used as external_media_address "
             "on trunks and external_signaling_address (the transport, salt side). "
             "Empty = no external address is generated.",
    )
    pbx_ws_server = fields.Char(
        string="WebSocket Server (override)",
        related="company_id.pbx_ws_server",
        readonly=False,
        help="Explicit WebSocket URL for the Odoo softphone (per company). "
             "Empty = derive automatically.",
    )
    pbx_turn_enabled = fields.Boolean(
        string="TURN enabled",
        related="company_id.pbx_turn_enabled",
        readonly=False,
        help="TURN for devices behind NAT (coturn serves both STUN+TURN on the same address).",
    )
    pbx_turn_server = fields.Char(
        string="TURN Server",
        config_parameter="pbx.turn.server",
        readonly=False,
        help="Coturn address for STUN+TURN — e.g. turn.vertel.se:3478. "
        "Provisioned by pbx_admin via odoo.conf.",
    )

    # ── RabbitMQ + webhook ──
    # Host and Vhost are derived from the PBX server and the SIP domain
    # respectively (removed from the form — see pbx_mq.publisher._get_config).
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
    pbx_sip_password_length = fields.Integer(
        string="SIP password length",
        config_parameter="pbx.sip_password_length",
        default=10,
        help="Length of generated SIP passwords (extension.password).",
    )

    pbx_webhook_token = fields.Char(
        string="PBX Webhook Token",
        config_parameter="pbx.webhook.token",
        groups="base.group_system",
        readonly=True,
        help="Bearer token that pbx_ami_daemon uses against /pbx/webhook. "
        "Generated automatically if none exists (standalone use), "
        "or provisioned by pbx_admin via odoo.conf.",
    )
    pbx_webhook_url = fields.Char(
        string="PBX Webhook URL",
        compute="_compute_pbx_webhook_url",
        readonly=True,
        help="Full endpoint that pbx_ami_daemon POSTs to "
        "(based on the Odoo URL or web.base.url).",
    )

    @api.depends_context("company")
    def _compute_pbx_webhook_url(self):
        base = (
            self.company_id.pbx_odoo_url
            or self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        )
        for rec in self:
            rec.pbx_webhook_url = "%s/pbx/webhook" % (base or "").rstrip("/")

    # ── Webhook token: auto-generation (standalone) ────────────────
    @api.model
    def _ensure_webhook_token(self):
        """Generate a webhook token if none exists (idempotent).

        Standalone use: the module must work without Salt/pbx_admin.
        Called from get_values so the token is created when the form is opened
        if it is completely missing.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        token = ICP.get_param("pbx.webhook.token", "")
        if not token:
            token = secrets.token_urlsafe(32)
            ICP.set_param("pbx.webhook.token", token)
            _logger.info("PBX webhook token generated (was missing)")
        return token

    def get_values(self):
        res = super().get_values()
        self._ensure_webhook_token()
        res["pbx_webhook_token"] = self.env[
            "ir.config_parameter"
        ].sudo().get_param("pbx.webhook.token", "")
        return res

    def action_generate_webhook_token(self):
        """Generate a new webhook token (button in the settings form)."""
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(
            "pbx.webhook.token", token
        )
        self.pbx_webhook_token = token
        _logger.info("PBX webhook token regenerated (manual)")
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
