# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxCallAI(models.Model):
    """AI-arv på pbx.call — transcript-dokument."""

    _inherit = "pbx.call"

    transcript_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Transcript-dokument",
        help="Text-bilaga med transkriptionen av samtalet.",
    )
    transcript_text = fields.Text(
        string="Transcript",
        help="Transkriptionen av samtalet (för visning).",
    )
