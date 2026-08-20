# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxCallAI(models.Model):
    """AI-arv på pbx.call — attachments, token-spårning, STT-metadata."""

    _inherit = "pbx.call"

    recording_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Inspelning",
        help="Ljudinspelningen av samtalet (Garage S3 via ir.attachment).",
    )
    transcript_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Transcript-dokument",
        help="Text-bilaga med transkriptionen av samtalet.",
    )
    transcript_text = fields.Text(
        string="Transcript",
        help="Transkriptionen av samtalet (för visning).",
    )

    # Token-förbrukning från LLM-bearbetningen efter transkription
    ai_tokens_in = fields.Integer(
        string="AI tokens in",
        help="Tokens till LLM (memory + entity extraction). Lokal STT kostar "
             "inga tokens — detta är LLM-förbrukningen efteråt.",
    )
    ai_tokens_out = fields.Integer(string="AI tokens out")
    ai_token_cost = fields.Float(
        string="AI kostnad",
        digits=(16, 6),
        help="Beräknad kostnad (tokens × pris per token, "
             "ir.config_parameter pbx.ai.token_price).",
    )

    # STT-metadata (lokal transkribering)
    stt_model = fields.Char(string="STT-modell")
    stt_duration_s = fields.Float(
        string="STT ljudlängd (s)",
        help="Ljudets längd i sekunder som transkriberades.",
    )
    stt_processing_s = fields.Float(
        string="STT processering (s)",
        help="Transkriberingstid i sekunder (lokalt, inga tokens).",
    )
