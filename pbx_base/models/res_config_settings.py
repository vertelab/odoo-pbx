# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

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
    pbx_stun_enabled = fields.Boolean(
        string="STUN aktiverad",
        related="company_id.pbx_stun_enabled",
        readonly=False,
    )
    pbx_stun_server = fields.Char(
        string="STUN Server",
        related="company_id.pbx_stun_server",
        readonly=False,
        help="t.ex. stun.vertel.se:3478",
    )

    # ── RabbitMQ + webhook ──
    pbx_mq_host = fields.Char(
        string="RabbitMQ Host",
        config_parameter="pbx.mq.host",
        default="localhost",
    )
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
        help="Bearer-token som pbx_ami_daemon använder mot /pbx/webhook",
    )
