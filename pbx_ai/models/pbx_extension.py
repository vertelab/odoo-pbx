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

    # ── AI-anknytning (coworker-as-extension) ──────────────────────

    follow_me_ai_coworker_id = fields.Many2one(
        "ai.coworker",
        string="Follow-me AI-destination",
        help="AI-kollegare som tar över samtalet efter att enheterna ringts "
             "utan svar (Stasis(coworker,<id>)).",
    )
    ai_coworker_id = fields.Many2one(
        "ai.coworker",
        string="AI-kollegare",
        compute="_compute_ai_coworker_id",
        help="Härledd AI-kollegare via användarens personal_coworker_id "
             "(read-only).",
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

    def _compute_ai_coworker_id(self):
        for ext in self:
            ext.ai_coworker_id = ext._get_ai_coworker().id

    def _get_ai_coworker(self):
        """Returnera den aktiva AI-kollegaren (personal_coworker_id) eller tom record."""
        self.ensure_one()
        coworker = self.user_id.personal_coworker_id if self.user_id else False
        if coworker and coworker.active:
            return coworker
        return self.env["ai.coworker"]

    def _is_ai_extension(self):
        """True om anknytningen är en AI-anknytning (aktiv coworker med leader-agent)."""
        self.ensure_one()
        coworker = self._get_ai_coworker()
        if not coworker:
            return False
        return bool(coworker._get_leader_agent())
