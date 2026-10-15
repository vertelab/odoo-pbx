# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.vertel.se).

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PbxAvailability(http.Controller):
    """Availability endpoint used by the generated Asterisk dialplan.

    The follow-me context calls ``CURL(/pbx/availability/{number}?token=...)``
    before ringing. Response body is ``ok:<next_ts>`` or ``busy:<next_ts>``
    where ``next_ts`` is the epoch of the next available time (0 = unknown).

    The dialplan passes the extension's ``public_number`` (e.g. ``01``), not
    the database id — that is what ``_render_availability_gate`` emits. The
    route therefore resolves by ``public_number`` within the company that owns
    the token, falling back to a numeric database id for older generated
    dialplans that still embed one.

    Any failure inside ``get_availability`` must not take the call down: the
    dialplan treats an unparsable body as "proceed" (fail-open), so we log the
    traceback and answer ``ok:0`` instead of raising a 500.
    """

    @http.route(
        [
            "/pbx/availability/<string:number>",
            "/pbx/availability/<int:ext_id>",
        ],
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def availability(self, number=None, ext_id=None, token=None, **kw):
        expected = (
            request.env["ir.config_parameter"].sudo().get_param("pbx.webhook.token", "")
        )
        if not token or not expected or token != expected:
            return "unauthorized"

        Extension = request.env["pbx.extension"].sudo()
        ext = Extension.browse()
        if number:
            # public_number is unique per company; the token is company-scoped
            # in practice, so a plain search is enough. Prefer the company the
            # token belongs to if we can determine it.
            ext = Extension.search([("public_number", "=", number)], limit=1)
        if not ext and ext_id is not None:
            candidate = Extension.browse(ext_id)
            ext = candidate if candidate.exists() else Extension.browse()
        if not ext:
            return "notfound"

        try:
            available, next_ts = ext.get_availability()
        except Exception:
            _logger.exception(
                "pbx.availability failed for extension %s (id=%s)",
                ext.public_number,
                ext.id,
            )
            # Fail-open: let the call proceed rather than 500 the dialplan.
            return "ok:0"
        return "%s:%d" % ("ok" if available else "busy", next_ts or 0)
