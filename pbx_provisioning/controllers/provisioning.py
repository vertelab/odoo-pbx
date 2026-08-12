# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import http
from odoo.http import request

from werkzeug.exceptions import NotFound


class PbxProvisioningController(http.Controller):
    """Provisioning-endpoints.

    Alla endpoints är auth='public' (telefoner/appar har ingen Odoo-inloggning)
    och autentiseras av token/MAC själva. Ogiltiga förfrågningar → 404 (ingen
    information om att ett MAC/token finns).
    """

    def _normalize_mac(self, mac):
        return "".join(ch for ch in (mac or "") if ch.isalnum()).lower()

    def _sub_from_mac(self, mac, company):
        return request.env["pbx.sub_extension"].sudo().search(
            [
                ("mac_address", "=", mac),
                ("type", "=", "hardware"),
                ("extension_id.company_id", "=", company.id),
                ("active", "=", True),
            ],
            limit=1,
        )

    @http.route(
        "/pbx/provisioning/<mac>.cfg",
        type="http",
        auth="public",
        csrf=False,
        save_session=False,
    )
    def hardware_config(self, mac, **kw):
        """Yealink AutoP: /pbx/provisioning/<MAC>.cfg

        Auth: HTTP Basic (URL-credentials) med username=<domän> och
        password=<företagets provisioning-token>.
        """
        mac = self._normalize_mac(mac)
        auth = request.httprequest.authorization
        if not mac or not auth or not auth.username or not auth.password:
            raise NotFound()
        company = request.env["res.company"].sudo().search(
            [
                "|",
                ("pbx_domain", "=", auth.username),
                ("name", "=", auth.username),
            ],
            limit=1,
        )
        if not company or not company.pbx_provisioning_token:
            raise NotFound()
        if company.pbx_provisioning_token != auth.password:
            raise NotFound()
        sub = self._sub_from_mac(mac, company)
        if not sub:
            raise NotFound()
        body = sub._get_yealink_config()
        return request.make_response(
            body,
            headers=[("Content-Type", "text/plain; charset=utf-8")],
        )

    @http.route(
        "/pbx/provisioning/softphone/<token>.xml",
        type="http",
        auth="public",
        csrf=False,
        save_session=False,
    )
    def softphone_config(self, token, **kw):
        """Linphone: /pbx/provisioning/softphone/<token>.xml

        Token = per-enhet (128-bit) — både nyckel och auth.
        """
        token = (token or "").strip()
        if not token:
            raise NotFound()
        sub = request.env["pbx.sub_extension"].sudo().search(
            [
                ("provisioning_token", "=", token),
                ("type", "in", ["desktop", "mobile"]),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not sub:
            raise NotFound()
        body = sub._get_linphone_xml()
        return request.make_response(
            body,
            headers=[("Content-Type", "application/xml; charset=utf-8")],
        )
