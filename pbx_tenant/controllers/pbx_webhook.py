# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PbxWebhook(http.Controller):
    """Receives events from the pbx_ami_daemon.

    Payload: {"tenant": "vertel.se", "topic": "pbx.event.vertel.AMI.Newchannel", "event": {...}}
    Auth: Bearer token (ir.config_parameter `pbx.webhook.token`, or per-tenant
    `pbx.webhook.token.<domain>`).
    """

    @http.route("/pbx/webhook", type="json", auth="none", csrf=False, methods=["POST"])
    def webhook(self, tenant=None, topic=None, event=None, **kwargs):
        if not tenant or not event:
            return {"status": "error", "error": "missing tenant or event"}

        token = self._token_for(tenant)
        auth = request.httprequest.headers.get("Authorization", "")
        if not token or auth != f"Bearer {token}":
            return {"status": "error", "error": "unauthorized"}

        try:
            request.env["pbx.webhook.service"].handle_event(tenant, topic or "", event)
        except Exception as e:
            _logger.exception("Webhook handling failed for %s", tenant)
            return {"status": "error", "error": str(e)}
        return {"status": "ok"}

    def _token_for(self, tenant):
        ICP = request.env["ir.config_parameter"].sudo()
        return ICP.get_param(f"pbx.webhook.token.{tenant}", "") or ICP.get_param(
            "pbx.webhook.token", ""
        )
