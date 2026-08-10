# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

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
