# -*- coding: utf-8 -*-
# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""AI-coworker som förstklassig pbx.extension (coworker-as-extension).

Identitetskedjan (D1):
    ai.coworker → hr.employee (is_ai=True, ai_coworker_id)
               → res.users (personal_coworker_id)
               → pbx.extension (user_id)

Numret härleds ur personen — inget separat nummerfält på coworkern.
"""

from odoo import _, api, fields, models


class PbxCoworkerAI(models.Model):
    """AI-arv på ai.coworker — PBX-anknytning, STT-läge, TTS-röst."""

    _inherit = "ai.coworker"

    stt_mode = fields.Selection(
        selection=[
            ("turn", "Turn (record → lokal STT)"),
            ("streaming", "Streaming (external media)"),
        ],
        string="STT Mode",
        default="turn",
        help="turn = inspelningschunks → lokal pbx-transcriber (fors); "
             "streaming = ARI externalMedia → streaming-STT-backend. "
             "Saknas streaming-förmåga faller systemet tillbaka till turn.",
    )

    tts_voice = fields.Char(
        string="TTS Voice",
        help="Röst för dialog-svar (persona). Lämnas tomt för default-röst.",
    )

    tts_lang = fields.Selection(
        selection=[
            ("sv-SE", "Svenska (sv-SE)"),
            ("sv", "Svenska (sv)"),
            ("en-US", "English (en-US)"),
            ("en", "English (en)"),
        ],
        string="TTS Language",
        default="sv-SE",
        help="Språk för dialog-svar (persona).",
    )

    # ── Identitet (D1) ──────────────────────────────────────────────

    def _get_pbx_extension(self):
        """Härled pbx.extension via employee → user → pbx.extension.

        Prioriterar användarens personal_coworker_id-koppling (en användare
        som har denna coworker som personlig assistent), med fallback till
        anställdes user.
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
        """Agentens modell har has_streaming → streaming-dialog möjlig."""
        self.ensure_one()
        agent = self._get_leader_agent()
        if not agent or not agent.model_id:
            return False
        return bool(agent.model_id.has_streaming)

    def _get_leader_agent(self):
        """Leader-agenten för coworkern (via ai.coworker.agent, role=leader)."""
        self.ensure_one()
        link = self.env["ai.coworker.agent"].search(
            [("coworker_id", "=", self.id), ("role", "=", "leader")],
            limit=1)
        return link.agent_id if link else False

    @api.constrains("employee_id")
    def _check_single_persona_extension(self):
        """En persona per coworker — anknytningen ska peka på en användare
        med personal_coworker_id == denna coworker."""
        for rec in self:
            ext = rec._get_pbx_extension()
            if ext and ext.user_id and ext.user_id.personal_coworker_id != rec:
                raise models.ValidationError(
                    _("Anknytningen %s tillhör en användare med en annan "
                      "personlig AI-kollegare.") % (ext.public_number or ext.id))
