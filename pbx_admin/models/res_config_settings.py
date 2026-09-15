# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Central (MSP) settings — added to the same settings page as
    pbx_base's Basic settings (a single settings page)."""

    _inherit = "res.config.settings"

    server_id = fields.Many2one(
        "pbx.server",
        string="Default Asterisk Server",
        config_parameter="pbx_admin.default_server_id",
    )
    pbx_turn_server = fields.Char(
        string="TURN Server (central)",
        config_parameter="pbx.turn.server",
        help="Coturn address for STUN+TURN, e.g. turn.vertel.se:3478. "
        "Deployed to customer minions via Salt (odoo.conf + pillar).",
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
        help="Zabbix server for monitoring of the Asterisk server (MSP).",
    )
    zabbix_token = fields.Char(
        string="Zabbix Token",
        config_parameter="pbx_admin.zabbix_token",
        groups="base.group_system",
        help="API token for Zabbix monitoring (MSP).",
    )
