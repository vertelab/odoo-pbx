# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxCallAI(models.Model):
    """AI additions to pbx.call — attachments, token tracking, STT metadata."""

    _inherit = "pbx.call"

    recording_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Recording",
        help="The audio recording of the call (Garage S3 via ir.attachment).",
    )
    transcript_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Transcript Document",
        help="Text attachment with the transcription of the call.",
    )
    transcript_text = fields.Text(
        string="Transcript",
        help="The transcription of the call (for display).",
    )

    # Token usage from the LLM processing after transcription
    ai_tokens_in = fields.Integer(
        string="AI tokens in",
        help="Tokens sent to the LLM (memory + entity extraction). Local STT "
             "costs no tokens — this is the LLM usage afterwards.",
    )
    ai_tokens_out = fields.Integer(string="AI tokens out")
    ai_token_cost = fields.Float(
        string="AI Cost",
        digits=(16, 6),
        help="Estimated cost (tokens x price per token, "
             "ir.config_parameter pbx.ai.token_price).",
    )

    # STT metadata (local transcription)
    stt_model = fields.Char(string="STT Model")
    stt_duration_s = fields.Float(
        string="STT Audio Length (s)",
        help="The length of the audio in seconds that was transcribed.",
    )
    stt_processing_s = fields.Float(
        string="STT Processing (s)",
        help="Transcription time in seconds (local, no tokens).",
    )
