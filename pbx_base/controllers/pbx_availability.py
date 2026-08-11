# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.vertel.se).

from odoo import http
from odoo.http import request


class PbxAvailability(http.Controller):
    """Availability endpoint used by the generated Asterisk dialplan.

    The follow-me context calls ``CURL(/pbx/availability/{ext}?token=...)``
    before ringing. Response body is ``ok:<next_ts>`` or ``busy:<next_ts>``
    where ``next_ts`` is the epoch of the next available time (0 = unknown).
    """

    @http.route(
        "/pbx/availability/<int:ext_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def availability(self, ext_id, token=None, **kw):
        expected = (
            request.env["ir.config_parameter"].sudo().get_param("pbx.webhook.token", "")
        )
        if not token or not expected or token != expected:
            return "unauthorized"
        ext = request.env["pbx.extension"].sudo().browse(ext_id)
        if not ext.exists():
            return "notfound"
        available, next_ts = ext.get_availability()
        return "%s:%d" % ("ok" if available else "busy", next_ts or 0)
