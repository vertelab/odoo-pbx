# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxAdminSettings(models.TransientModel):
    _name = "pbx.admin.settings"
    _inherit = "res.config.settings"
    _description = "PBX Admin Settings"

    default_server_id = fields.Many2one(
        "pbx.server",
        string="Default Asterisk Server",
        config_parameter="pbx_admin.default_server_id",
    )
    rabbitmq_host = fields.Char(
        config_parameter="pbx_admin.rabbitmq_host",
        default="localhost",
    )
    rabbitmq_port = fields.Integer(
        config_parameter="pbx_admin.rabbitmq_port",
        default=5672,
    )
    rabbitmq_user = fields.Char(
        config_parameter="pbx_admin.rabbitmq_user",
        default="pbx",
    )
    rabbitmq_secret = fields.Char(
        config_parameter="pbx_admin.rabbitmq_secret",
        groups="base.group_system",
    )
    billing_api_enabled = fields.Boolean(
        config_parameter="pbx_admin.billing_api_enabled",
    )
    billing_api_token = fields.Char(
        config_parameter="pbx_admin.billing_api_token",
        groups="base.group_system",
    )
    zabbix_url = fields.Char(
        config_parameter="pbx_admin.zabbix_url",
    )
    zabbix_token = fields.Char(
        config_parameter="pbx_admin.zabbix_token",
        groups="base.group_system",
    )
