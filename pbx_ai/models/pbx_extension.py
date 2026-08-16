# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxExtensionAI(models.Model):
    """AI-arv på pbx.extension — transkribering per anknytning."""

    _inherit = "pbx.extension"

    transcribe_enabled = fields.Boolean(
        string="Transkribera samtal",
        help="Skapa automatiskt ett transcript-dokument för samtal på "
             "denna anknytning (om inspelning finns).",
    )
