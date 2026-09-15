# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxExtensionAI(models.Model):
    """AI/recording inheritance on pbx.extension — tri-state recording/transcription."""

    _inherit = "pbx.extension"

    recording_mode = fields.Selection(
        [
            ("record", "Record"),
            ("transcribe", "Transcribe"),
        ],
        default="",
        string="Recording/Transcription",
        help="'' = inherit the global policy/queue, 'record' = force recording, "
             "'transcribe' = recording + transcription.",
    )
    # Deprecated — replaced by recording_mode (migration: True → transcribe).
    transcribe_enabled = fields.Boolean(
        string="Transcribe calls (deprecated)",
        help="Replaced by 'Recording/Transcription'. Kept for backwards compatibility.",
    )

    # ── AI extension (coworker-as-extension) ──────────────────────

    follow_me_ai_coworker_id = fields.Many2one(
        "ai.coworker",
        string="Follow-me AI destination",
        help="AI coworker that takes over the call after the devices have been rung "
             "without answer (Stasis(coworker,<id>)).",
    )
    ai_coworker_id = fields.Many2one(
        "ai.coworker",
        string="AI Coworker",
        compute="_compute_ai_coworker_id",
        help="Derived AI coworker via the user's personal_coworker_id "
             "(read-only).",
    )

    def _get_recording_mode(self):
        """Resolution: extension → queue → global policy.

        Returns:
            '' / 'record' / 'transcribe'
        """
        self.ensure_one()
        if self.recording_mode:
            return self.recording_mode
        # Inherit from the queue if the extension is a queue member
        member = self.env["pbx.queue.member"].search(
            [("extension_id", "=", self.id)], limit=1
        )
        if member and member.queue_id.recording_mode:
            return member.queue_id.recording_mode
        # Fallback: global policy (mode=always -> record)
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
        """Return the active AI coworker (personal_coworker_id) or an empty record."""
        self.ensure_one()
        coworker = self.user_id.personal_coworker_id if self.user_id else False
        if coworker and coworker.active:
            return coworker
        return self.env["ai.coworker"]

    def _is_ai_extension(self):
        """True if the extension is an AI extension (active coworker with a leader agent)."""
        self.ensure_one()
        coworker = self._get_ai_coworker()
        if not coworker:
            return False
        return bool(coworker._get_leader_agent())
