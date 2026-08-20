# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxSubExtensionAI(models.Model):
    """AI-arv på pbx.sub_extension — voicemail-transkribering per device."""

    _inherit = "pbx.sub_extension"

    transcribe_voicemail = fields.Boolean(
        string="Transkribera röstmeddelanden",
        help="Transkribera röstmeddelanden för denna brevlåda (kräver att "
             "enheten är av typ voicemail). Oberoende av anknytningens "
             "recording_mode.",
    )
