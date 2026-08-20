# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxQueueAI(models.Model):
    """AI/recording-arv på pbx.queue — tri-state inspelning/transkribering."""

    _inherit = "pbx.queue"

    recording_mode = fields.Selection(
        [
            ("record", "Spela in"),
            ("transcribe", "Transkribera"),
        ],
        default="",
        string="Inspelning/Transkribering",
        help="'' = ärv global policy, 'record' = tvinga inspelning, "
             "'transcribe' = inspelning + transkribering. Ärvs av "
             "anknytningar i kön om de själva är tomma.",
    )
