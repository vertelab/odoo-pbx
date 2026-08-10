# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PbxPartnerResolver(models.AbstractModel):
    """Resolves a caller number to res.partner — auto-creates if missing.

    Used for incoming calls, manual queues and voicemails.
    """

    _name = "pbx.partner.resolver"
    _description = "PBX Partner Resolution (lookup + auto-create)"

    def resolve(self, number, name=False, create=True):
        """Find res.partner by phone/mobile.

        Returns (partner, created: bool). When `create` is False and no
        match exists, returns (empty recordset, False).
        """
        number = (number or "").strip()
        if not number:
            return self.env["res.partner"], False

        partner = self.env["res.partner"].search(
            ["|", ("phone", "=", number), ("mobile", "=", number)],
            limit=1,
        )
        if partner:
            return partner, False
        if not create:
            return self.env["res.partner"], False

        partner = self.env["res.partner"].create(
            {
                "name": name or number,
                "phone": number,
            }
        )
        _logger.info("Auto-created res.partner %s for caller %s", partner.id, number)
        return partner, True
