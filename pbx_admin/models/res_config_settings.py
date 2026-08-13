# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Centrala (MSP) inställningar — läggs på samma settings-sida som
    pbx_base:s Grundinställningar (en enda settings-sida)."""

    _inherit = "res.config.settings"

    server_id = fields.Many2one(
        "pbx.server",
        string="Default Asterisk Server",
        config_parameter="pbx_admin.default_server_id",
    )
    pbx_turn_server = fields.Char(
        string="TURN Server (central)",
        config_parameter="pbx.turn.server",
        help="Coturn-adress för TURN-relay, t.ex. turn.vertel.se:3478. "
        "Deployas till kundminioner via Salt (odoo.conf + pillar).",
    )
    pbx_stun_server = fields.Char(
        string="STUN Server (central)",
        config_parameter="pbx.stun.server",
        help="Coturn-adress för STUN, t.ex. stun.vertel.se:3478. "
        "Deployas till kundminioner via Salt (odoo.conf + pillar).",
    )
    rabbitmq_host = fields.Char(
        string="RabbitMQ Host (central)",
        config_parameter="pbx_admin.rabbitmq_host",
        default="localhost",
    )
    rabbitmq_port = fields.Integer(
        string="RabbitMQ Port (central)",
        config_parameter="pbx_admin.rabbitmq_port",
        default=5672,
    )
    rabbitmq_user = fields.Char(
        string="RabbitMQ User (central)",
        config_parameter="pbx_admin.rabbitmq_user",
        default="pbx",
    )
    rabbitmq_secret = fields.Char(
        string="RabbitMQ Secret (central)",
        config_parameter="pbx_admin.rabbitmq_secret",
        groups="base.group_system",
    )
    billing_api_enabled = fields.Boolean(
        string="Billing API Enabled",
        config_parameter="pbx_admin.billing_api_enabled",
    )
    billing_api_token = fields.Char(
        string="Billing API Token",
        config_parameter="pbx_admin.billing_api_token",
        groups="base.group_system",
    )
    zabbix_url = fields.Char(
        string="Zabbix URL",
        config_parameter="pbx_admin.zabbix_url",
        help="Zabbix-server för övervakning av Asterisk-servern (MSP).",
    )
    zabbix_token = fields.Char(
        string="Zabbix Token",
        config_parameter="pbx_admin.zabbix_token",
        groups="base.group_system",
        help="API-token mot Zabbix för övervakning (MSP).",
    )
