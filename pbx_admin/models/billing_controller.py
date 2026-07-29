# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class BillingController(http.Controller):
    _name = "pbx.billing.controller"

    def _check_token(self):
        token = request.httprequest.headers.get("Authorization", "").replace(
            "Bearer ", ""
        )
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("pbx_admin.billing_api_token", "")
        )
        if not token or token != expected:
            return False
        return True

    @http.route("/api/v1/billing/tenants", type="http", auth="none", methods=["GET"], csrf=False)
    def billing_tenants(self):
        if not self._check_token():
            return request.make_response(
                json.dumps({"error": "Unauthorized"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        tenants = request.env["pbx.tenant"].sudo().search([])
        result = []
        for tenant in tenants:
            extensions = request.env["pbx.extension"].sudo().search_count(
                [("tenant_id", "=", tenant.id), ("active", "=", True)]
            )
            result.append(
                {
                    "id": tenant.id,
                    "domain": tenant.domain,
                    "plan": tenant.plan,
                    "extensions_count": extensions,
                    "queues_count": 0,  # Filled by pbx_queue plugin
                    "conference_rooms": 0,  # Filled by pbx_conference plugin
                    "recordings_storage_mb": 0.0,  # Filled by pbx_recording plugin
                    "minutes_this_month": 0,
                    "minutes_previous_month": 0,
                    "trunk_channels": 0,
                }
            )

        return request.make_response(
            json.dumps({"tenants": result, "generated_at": fields.Datetime.now()}),
            headers=[("Content-Type", "application/json")],
        )

    @http.route(
        "/api/v1/billing/tenants/<int:tenant_id>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def billing_tenant(self, tenant_id):
        if not self._check_token():
            return request.make_response(
                json.dumps({"error": "Unauthorized"}),
                headers=[("Content-Type", "application/json")],
                status=401,
            )

        tenant = request.env["pbx.tenant"].sudo().browse(tenant_id)
        if not tenant.exists():
            return request.make_response(
                json.dumps({"error": "Not found"}),
                headers=[("Content-Type", "application/json")],
                status=404,
            )

        extensions = request.env["pbx.extension"].sudo().search_count(
            [("tenant_id", "=", tenant.id), ("active", "=", True)]
        )

        return request.make_response(
            json.dumps(
                {
                    "id": tenant.id,
                    "domain": tenant.domain,
                    "plan": tenant.plan,
                    "extensions_count": extensions,
                    "queues_count": 0,
                    "conference_rooms": 0,
                    "recordings_storage_mb": 0.0,
                    "minutes_this_month": 0,
                    "minutes_previous_month": 0,
                    "trunk_channels": 0,
                }
            ),
            headers=[("Content-Type", "application/json")],
        )
