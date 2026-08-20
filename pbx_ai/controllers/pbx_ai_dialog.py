# -*- coding: utf-8 -*-
# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

RECEPTIONIST_XMLID = "pbx_ai.coworker_pbx_receptionist"


class PbxAIDialog(http.Controller):
    """Dialog-endpoint för samtals-coworker (receptionist + AI-anknytning).

    Daemonen (pbx_ami_daemon) POST:ar varje turn (transkript) hit och får
    tillbaka svars-text + TTS-ljud (base64) som spelas upp via ARI.

    Payload (JSON):
        {
          "tenant": "kund.se",
          "channel_id": "1787241019.1",
          "coworker_id": 0,          # 0 → default receptionist
          "call_id": 0,              # pbx.call id om känd
          "caller_number": "0701234567",
          "history": [               # full dialog (user/assistant)
            "user: Hej!",
            "assistant: Hej, hur kan jag hjälpa?"
          ],
          "turn": "user: min maskin är trasig"
        }

    Response:
        {"reply": "...", "tts_audio_base64": "...", "status": "ok"}
    """

    @http.route("/pbx/ai/dialog", type="json", auth="none", csrf=False, methods=["POST"])
    def dialog(self, **kwargs):
        payload = request.get_json_data() or {}
        tenant = payload.get("tenant", "")
        token = self._token_for(tenant)
        auth = request.httprequest.headers.get("Authorization", "")
        if not token or auth != f"Bearer {token}":
            return {"status": "error", "error": "unauthorized"}

        try:
            coworker = self._resolve_coworker(payload)
            if not coworker:
                return {
                    "status": "ok",
                    "reply": "Tyvärr är ingen AI-medarbetare konfigurerad just nu.",
                    "tts_audio_base64": "",
                }

            conversation = self._build_conversation(payload)
            reply = self._run_coworker(coworker, conversation, payload)
            tts = self._tts_audio(reply, coworker)

            return {
                "status": "ok",
                "reply": reply,
                "tts_audio_base64": base64.b64encode(tts).decode() if tts else "",
            }
        except Exception as e:
            _logger.exception("AI dialog failed for %s", tenant)
            request.env.cr.rollback()
            return {"status": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────

    def _token_for(self, tenant):
        ICP = request.env["ir.config_parameter"].sudo()
        return ICP.get_param(f"pbx.webhook.token.{tenant}") or \
            ICP.get_param("pbx.webhook.token", "")

    def _resolve_coworker(self, payload):
        coworker_id = int(payload.get("coworker_id") or 0)
        if coworker_id:
            cw = request.env["ai.coworker"].sudo().browse(coworker_id)
            if cw.exists():
                return cw
        rec = request.env.ref(RECEPTIONIST_XMLID, raise_if_not_found=False)
        return rec.sudo() if rec else request.env["ai.coworker"]

    def _build_conversation(self, payload):
        """Bygg konversationstext med samtalskontext."""
        lines = []
        caller = payload.get("caller_number", "")
        if caller:
            lines.append(f"Kontext: inkommande samtal från {caller} (PBX).")
        history = payload.get("history") or []
        turn = payload.get("turn", "")
        if history:
            lines.extend(history)
        if turn:
            lines.append(turn)
        if not lines:
            lines.append("user: (tystnad)")
        return "\n".join(lines)

    def _run_coworker(self, coworker, conversation, payload):
        """Kör coworkern. HITL (AgentLoopPaused) → artigt svar."""
        try:
            res = coworker.run(conversation)
            text = getattr(res, "content", None)
            if isinstance(text, str):
                return text.strip()
            if isinstance(text, list):
                parts = [
                    p.get("text", "") for p in text
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return "\n".join(parts).strip() or "…"
            return "…"
        except Exception as e:
            if "AgentLoopPaused" in type(e).__name__:
                return "Ett ögonblick, jag kopplar dig vidare."
            _logger.warning("Coworker run failed: %s", e)
            return "Ett ögonblick, jag kopplar dig vidare."

    def _tts_audio(self, text, coworker):
        """Generera tal via ai.provider (is_asr-modell). Returnerar bytes."""
        if not text or text in ("…",):
            return b""
        try:
            provider = request.env["ai.provider"].sudo().search(
                [("active", "=", True)], limit=1)
            if not provider or not hasattr(provider, "_text_to_speech"):
                return b""
            return provider._text_to_speech(text) or b""
        except Exception as e:
            _logger.warning("TTS failed: %s", e)
            return b""
