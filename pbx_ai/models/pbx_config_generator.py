# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class PbxConfigGenerator(models.AbstractModel):
    _inherit = "pbx.config.generator"

    def _get_extension_internal_entry(self, ext, domain):
        """AI-anknytning → Stasis(coworker,<id>) i den interna kontexten.

        Vid inaktiv/avsaknad coworker faller vi tillbaka på super()
        (None → normal ring-grupp → voicemail).
        """
        if ext._is_ai_extension():
            coworker = ext._get_ai_coworker()
            if coworker:
                return "exten => %s,1,Stasis(coworker,%s)" % (
                    ext.public_number, coworker.id
                )
        return super()._get_extension_internal_entry(ext, domain)
