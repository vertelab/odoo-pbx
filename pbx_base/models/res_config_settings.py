# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ── Grundinställningar (read-only tenant info, defined centrally) ──
    pbx_tenant_domain = fields.Char(
        string="SIP Domain",
        readonly=True,
        compute="_compute_pbx_tenant_info",
        help="Tenant's SIP domain, defined by the central management system.",
    )
    pbx_tenant_plan = fields.Selection(
        [("standard", "Standard"), ("premium", "Premium"), ("enterprise", "Enterprise")],
        string="Plan",
        readonly=True,
        compute="_compute_pbx_tenant_info",
    )
    pbx_tenant_max_extensions = fields.Integer(
        string="Max Extensions",
        readonly=True,
        compute="_compute_pbx_tenant_info",
    )
    pbx_server_name = fields.Char(
        string="PBX Server",
        readonly=True,
        compute="_compute_pbx_tenant_info",
    )

    @api.model
    def _get_pbx_tenant(self):
        """The tenant record of the current company (created by provisioning)."""
        return self.env["pbx.tenant"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )

    @api.depends("company_id")
    def _compute_pbx_tenant_info(self):
        for rec in self:
            tenant = rec._get_pbx_tenant()
            rec.pbx_tenant_domain = tenant.domain
            rec.pbx_tenant_plan = tenant.plan
            rec.pbx_tenant_max_extensions = tenant.max_extensions
            rec.pbx_server_name = tenant.server_id.name

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
