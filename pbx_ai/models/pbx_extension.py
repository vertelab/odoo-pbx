# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxExtensionAI(models.Model):
    """AI/recording-arv på pbx.extension — tri-state inspelning/transkribering."""

    _inherit = "pbx.extension"

    recording_mode = fields.Selection(
        [
            ("record", "Spela in"),
            ("transcribe", "Transkribera"),
        ],
        default="",
        string="Inspelning/Transkribering",
        help="'' = ärv global policy/kö, 'record' = tvinga inspelning, "
             "'transcribe' = inspelning + transkribering.",
    )
    # Deprecerad — ersatt av recording_mode (migrering: True → transcribe).
    transcribe_enabled = fields.Boolean(
        string="Transkribera samtal (föråldrad)",
        help="Ersatt av 'Inspelning/Transkribering'. Finns kvar för bakåtkompatibilitet.",
    )

    def _get_recording_mode(self):
        """Upplösning: anknytning → kö → global policy.

        Returns:
            '' / 'record' / 'transcribe'
        """
        self.ensure_one()
        if self.recording_mode:
            return self.recording_mode
        # Ärv från kö om anknytningen är kömedlem
        member = self.env["pbx.queue.member"].search(
            [("extension_id", "=", self.id)], limit=1
        )
        if member and member.queue_id.recording_mode:
            return member.queue_id.recording_mode
        # Fallback: global policy (mode=always → record)
        policy = self.env["pbx.recording.policy"].search(
            [("scope", "=", "company"), ("active", "=", True)],
            limit=1,
        )
        if policy and policy.mode == "always":
            return "record"
        return ""
