# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""AI coworker as a first-class pbx.extension (coworker-as-extension).

The identity chain (D1):
    ai.coworker -> hr.employee (is_ai=True, ai_coworker_id)
               -> res.users (personal_coworker_id)
               -> pbx.extension (user_id)

The number is derived from the person — there is no separate number field
on the coworker.
"""

from odoo import _, api, fields, models


class PbxCoworkerAI(models.Model):
    """AI additions to ai.coworker — PBX extension, STT mode, TTS voice."""

    _inherit = "ai.coworker"

    stt_mode = fields.Selection(
        selection=[
            ("turn", "Turn (record -> local STT)"),
            ("streaming", "Streaming (external media)"),
        ],
        string="STT Mode",
        default="turn",
        help="turn = recording chunks -> local pbx-transcriber (fors); "
             "streaming = ARI externalMedia -> streaming STT backend. "
             "If the streaming capability is missing the system falls back "
             "to turn.",
    )

    tts_voice = fields.Char(
        string="TTS Voice",
        help="Voice for dialog replies (persona). Leave empty for the default voice.",
    )

    tts_lang = fields.Selection(
        selection=[
            ("sv-SE", "Swedish (sv-SE)"),
            ("sv", "Swedish (sv)"),
            ("en-US", "English (en-US)"),
            ("en", "English (en)"),
        ],
        string="TTS Language",
        default="sv-SE",
        help="Language for dialog replies (persona).",
    )

    # ── Identity (D1) ───────────────────────────────────────────────

    def _get_pbx_extension(self):
        """Derive pbx.extension via employee -> user -> pbx.extension.

        Prioritizes the user's personal_coworker_id link (a user who has this
        coworker as a personal assistant), falling back to the employee's
        user.
        """
        self.ensure_one()
        user = self.env["res.users"].search(
            [("personal_coworker_id", "=", self.id)], limit=1)
        if not user and self.employee_id:
            user = self.employee_id.user_id
        return user.pbx_extension_id if user else self.env["pbx.extension"]

    def _get_pbx_extension_number(self):
        ext = self._get_pbx_extension()
        return ext.public_number if ext else False

    def _has_streaming_capability(self):
        """The agent's model has has_streaming -> streaming dialog possible."""
        self.ensure_one()
        agent = self._get_leader_agent()
        if not agent or not agent.model_id:
            return False
        return bool(agent.model_id.has_streaming)

    def _get_leader_agent(self):
        """The leader agent for the coworker (via ai.coworker.agent, role=leader)."""
        self.ensure_one()
        link = self.env["ai.coworker.agent"].search(
            [("coworker_id", "=", self.id), ("role", "=", "leader")],
            limit=1)
        return link.agent_id if link else False

    @api.constrains("employee_id")
    def _check_single_persona_extension(self):
        """One persona per coworker — the extension must point to a user
        with personal_coworker_id == this coworker."""
        for rec in self:
            ext = rec._get_pbx_extension()
            if ext and ext.user_id and ext.user_id.personal_coworker_id != rec:
                raise models.ValidationError(
                    _("Extension %s belongs to a user with a different "
                      "personal AI coworker.") % (ext.public_number or ext.id))
