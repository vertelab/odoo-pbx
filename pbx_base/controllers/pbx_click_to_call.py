# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PbxClickToCall(http.Controller):
    """Click-to-call: POST /pbx/click_to_call {number} → ring användarens
    första aktiva enhet och koppla målnumret (via MQ → AMI Originate)."""

    @http.route("/pbx/click_to_call", type="json", auth="user", methods=["POST"], csrf=False)
    def click_to_call(self, number, **kwargs):
        try:
            result = request.env["pbx.extension"].action_click_to_call_current_user(number)
            return {"status": "ok", **result}
        except UserError as e:
            return {"status": "error", "error": e.args[0]}
        except Exception as e:
            _logger.exception("Click-to-call failed")
            return {"status": "error", "error": str(e)}
