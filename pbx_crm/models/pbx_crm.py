# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PbxCrm(models.AbstractModel):
    _name = "pbx.crm"
    _inherit = ["pbx.plugin"]
    _description = "PBX CRM Integration"

    def get_fop2_widgets(self):
        return [{"name": "crm_popup", "component": "PbxCrmPopup", "props": {}}]

    def get_notification_handlers(self):
        return {
            "AMI.Newchannel": "_on_incoming_call",
            "AMI.Hangup": "_on_call_ended",
        }

    def _on_incoming_call(self, event_data):
        """Search CRM leads by caller number, return matching records."""
        caller_number = event_data.get("callerid_num", "")
        if not caller_number:
            return

        leads = self.env["crm.lead"].search(
            ["|", ("phone", "=", caller_number), ("mobile", "=", caller_number),
             ("active", "=", True)],
            limit=5,
        )
        partner = self.env["res.partner"].search(
            ["|", ("phone", "=", caller_number), ("mobile", "=", caller_number)],
            limit=1,
        )

        return {
            "caller_number": caller_number,
            "partner": partner.read(["id", "name", "email"]) if partner else None,
            "leads": leads.read(["id", "name", "stage_id", "planned_revenue"]),
            "has_leads": len(leads) > 0,
        }

    def _on_call_ended(self, event_data):
        """Log the call in the lead's chatter."""
        call_id = event_data.get("call_id", 0)
        if not call_id:
            return

        call = self.env["voip.call"].browse(call_id)
        if not call.exists() or not call.partner_id:
            return

        # Find leads for this partner
        leads = self.env["crm.lead"].search(
            [("partner_id", "=", call.partner_id.id), ("active", "=", True)]
        )
        for lead in leads:
            duration = ""
            if hasattr(call, "duration") and call.duration:
                hours = int(call.duration)
                minutes = int((call.duration - hours) * 60)
                duration = f" ({hours}h{minutes:02d}m)"
            lead.message_post(
                body=f"📞 Phone call{duration} — {call.phone_number}"
            )

    def create_lead_from_call(self, caller_number, caller_name=""):
        """Create a new CRM lead from an unknown caller."""
        partner = self.env["res.partner"].search(
            ["|", ("phone", "=", caller_number), ("mobile", "=", caller_number)],
            limit=1,
        )
        if not partner:
            partner = self.env["res.partner"].create({
                "name": caller_name or caller_number,
                "phone": caller_number,
            })

        lead = self.env["crm.lead"].create({
            "name": f"Call from {caller_name or caller_number}",
            "partner_id": partner.id,
            "phone": caller_number,
            "type": "lead",
        })
        return lead.read(["id", "name"])


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pbx_crm_auto_popup = fields.Boolean(
        string="Auto-popup lead on incoming call",
        config_parameter="pbx_crm.auto_popup",
        default=True,
    )
    pbx_crm_auto_create_lead = fields.Boolean(
        string="Auto-create lead for unknown numbers",
        config_parameter="pbx_crm.auto_create_lead",
        default=False,
    )
    pbx_crm_log_calls = fields.Boolean(
        string="Log all calls in CRM",
        config_parameter="pbx_crm.log_calls",
        default=True,
    )
