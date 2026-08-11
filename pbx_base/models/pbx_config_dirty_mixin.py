# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://vertel.se).

from odoo import models


class PbxConfigDirtyMixin(models.AbstractModel):
    """Mark the company's PBX config as dirty when config-affecting records
    change (create/write/unlink), so the Sync icon/menu knows changes are
    pending. Mail/activity writes (chatter) do NOT mark dirty.
    """

    _name = "pbx.config.dirty.mixin"
    _description = "PBX Config Dirty Mixin"

    _PBX_MAIL_KEYS = ("message_", "activity_", "mail_", "website_message")

    def _pbx_get_company(self):
        if "company_id" in self._fields and self.company_id:
            return self.company_id
        if "extension_id" in self._fields and self.extension_id:
            return self.extension_id.company_id
        return self.env.company

    def _pbx_mark_dirty(self):
        for rec in self:
            company = rec._pbx_get_company()
            if company:
                company._pbx_mark_dirty()

    @models.api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._pbx_mark_dirty()
        return recs

    def write(self, vals):
        config_change = any(
            not key.startswith(self._PBX_MAIL_KEYS) for key in vals
        )
        res = super().write(vals)
        if config_change:
            self._pbx_mark_dirty()
        return res

    def unlink(self):
        self._pbx_mark_dirty()
        return super().unlink()
