# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxSubExtensionAI(models.Model):
    """AI inheritance on pbx.sub_extension — voicemail transcription per device."""

    _inherit = "pbx.sub_extension"

    transcribe_voicemail = fields.Boolean(
        string="Transcribe voicemails",
        help="Transcribe voicemails for this mailbox (requires the "
             "device to be of type voicemail). Independent of the extension's "
             "recording_mode.",
    )
