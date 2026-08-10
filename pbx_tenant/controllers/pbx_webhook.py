# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PbxWebhook(http.Controller):
    """Receives events from the pbx_ami_daemon.

    Payload (raw JSON body):
        {"tenant": "vertel.se", "topic": "pbx.event.vertel.AMI.Newchannel", "event": {...}}
    Auth: Bearer token (ir.config_parameter `pbx.webhook.token`, or per-tenant
    `pbx.webhook.token.<domain>`).
    """

    @http.route("/pbx/webhook", type="http", auth="none", csrf=False, methods=["POST"])
    def webhook(self, **kwargs):
        try:
            payload = request.get_json_data() or {}
        except Exception:
            payload = {}
        tenant = payload.get("tenant") or payload.get("domain")
        event = payload.get("event")
        topic = payload.get("topic", "")

        if not tenant or not event:
            return request.make_json_response(
                {"status": "error", "error": "missing tenant or event"}
            )

        token = self._token_for(tenant)
        auth = request.httprequest.headers.get("Authorization", "")
        if not token or auth != f"Bearer {token}":
            return request.make_json_response(
                {"status": "error", "error": "unauthorized"}, status=403
            )

        try:
            request.env["pbx.webhook.service"].sudo().handle_event(tenant, topic, event)
        except Exception as e:
            _logger.exception("Webhook handling failed for %s", tenant)
            return request.make_json_response(
                {"status": "error", "error": str(e)}, status=500
            )
        return request.make_json_response({"status": "ok"})

    def _token_for(self, tenant):
        ICP = request.env["ir.config_parameter"].sudo()
        return ICP.get_param(f"pbx.webhook.token.{tenant}", "") or ICP.get_param(
            "pbx.webhook.token", ""
        )
