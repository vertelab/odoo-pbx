# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxQueueAI(models.Model):
    """AI/recording inheritance on pbx.queue — tri-state recording/transcription."""

    _inherit = "pbx.queue"

    recording_mode = fields.Selection(
        [
            ("record", "Record"),
            ("transcribe", "Transcribe"),
        ],
        default="",
        string="Recording/Transcription",
        help="'' = inherit the global policy, 'record' = force recording, "
             "'transcribe' = recording + transcription. Inherited by "
             "extensions in the queue if they are themselves empty.",
    )
