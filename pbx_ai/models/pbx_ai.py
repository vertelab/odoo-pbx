# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PbxAI(models.AbstractModel):
    _name = "pbx.ai"
    _inherit = ["pbx.plugin"]
    _description = "PBX AI Bridge — Odoo Mind integration"

    def on_recording_ready(self, voip_call, attachment):
        """Called by pbx_recording when a recording is available.
        Transcribes audio and stores as company memory if odoo_ai is available."""
        if not self._has_odoo_ai():
            return

        try:
            transcript = self.env["odoo.ai"].transcribe_audio(
                attachment.datas, language="sv"
            )
        except Exception as e:
            _logger.warning("Transcription failed: %s", e)
            return

        if not transcript:
            return

        # Store as company memory
        if self._has_ai_agent_core():
            self._create_company_memory(voip_call, transcript)

        # Entity extraction → graph edges (async via cron)
        self._extract_entities(voip_call, transcript)

    def _has_odoo_ai(self):
        return "odoo.ai" in self.env.registry

    def _has_ai_agent_core(self):
        return "ai.agent.core" in self.env.registry or "ai.company.memory" in self.env.registry

    def _create_company_memory(self, voip_call, transcript):
        memory_model = self.env.get("ai.company.memory")
        if not memory_model:
            return

        content = f"""**Phone Call** — {voip_call.create_date.strftime('%Y-%m-%d %H:%M')}
**Direction:** {voip_call.type_call}
**Number:** {voip_call.phone_number}
**Agent:** {voip_call.user_id.name}

**Transcript:**
{transcript}
"""
        memory_model.create({
            "company_id": voip_call.company_id.id,
            "content": content,
            "category": "pbx_call",
            "scope": "internal",
            "importance": "medium",
        })

    def _extract_entities(self, voip_call, transcript):
        """Extract entities from transcript and create graph edges.
        Stored as JSON on voip.call for cron-based AGE sync."""
        if not self._has_odoo_ai():
            return

        try:
            entities = self.env["odoo.ai"].extract_entities(transcript)
        except Exception:
            return

        # Store for later graph sync
        voip_call.sudo().write({"entities": entities})

    def get_config_snippets(self, tenant):
        return {}

    def get_fop2_widgets(self):
        return [{"name": "ai_transcript", "component": "PbxAiTranscript", "props": {}}]
