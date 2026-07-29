# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PbxHelpdesk(models.AbstractModel):
    _name = "pbx.helpdesk"
    _inherit = ["pbx.plugin"]
    _description = "PBX Helpdesk Integration"

    def get_fop2_widgets(self):
        return [{"name": "helpdesk_popup", "component": "PbxHelpdeskPopup", "props": {}}]

    def get_notification_handlers(self):
        return {
            "AMI.Newchannel": "_on_incoming_call",
            "AMI.QueueEntry": "_on_queue_entry",
        }

    def _on_incoming_call(self, event_data):
        """Search helpdesk tickets by caller number."""
        caller_number = event_data.get("callerid_num", "")
        if not caller_number:
            return

        partner = self.env["res.partner"].search(
            ["|", ("phone", "=", caller_number), ("mobile", "=", caller_number)],
            limit=1,
        )
        tickets = self.env["helpdesk.ticket"].search([])
        if partner:
            tickets = tickets.filtered(lambda t: t.partner_id == partner)
        else:
            return {"caller_number": caller_number, "tickets": []}

        return {
            "caller_number": caller_number,
            "partner": partner.read(["id", "name"]) if partner else None,
            "tickets": tickets.read(["id", "name", "stage_id", "priority"]),
            "has_tickets": len(tickets) > 0,
        }

    def create_ticket_from_call(self, caller_number, caller_name="", transcript=""):
        """Create a helpdesk ticket from a call or voicemail."""
        partner = self.env["res.partner"].search(
            ["|", ("phone", "=", caller_number), ("mobile", "=", caller_number)],
            limit=1,
        )
        if not partner:
            partner = self.env["res.partner"].create({
                "name": caller_name or caller_number,
                "phone": caller_number,
            })

        team = self.env["helpdesk.team"].search([], limit=1)
        description = transcript or f"Phone call from {caller_name or caller_number}"
        ticket = self.env["helpdesk.ticket"].create({
            "name": f"Call from {caller_name or caller_number}",
            "partner_id": partner.id,
            "team_id": team.id if team else False,
            "description": description,
        })
        return ticket.read(["id", "name"])

    def _on_queue_entry(self, event_data):
        """Monitor queue entry for SLA tracking."""
        wait_seconds = int(event_data.get("wait", 0))
        domain = event_data.get("domain", "")
        caller = event_data.get("callerid_num", "")

        sla_warning = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "pbx_helpdesk.sla_warning_seconds", "120"
            )
        )
        sla_breach = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "pbx_helpdesk.sla_breach_seconds", "300"
            )
        )

        if wait_seconds >= sla_breach:
            _logger.warning("SLA BREACH: %s waited %ds in queue %s", caller, wait_seconds, domain)
            # Notify team leader via bus
            self.env["bus.bus"]._sendone(
                "pbx_helpdesk_sla_breach",
                {
                    "type": "sla_breach",
                    "caller": caller,
                    "wait_seconds": wait_seconds,
                    "domain": domain,
                },
            )
        elif wait_seconds >= sla_warning:
            _logger.info("SLA warning: %s waited %ds in queue %s", caller, wait_seconds, domain)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pbx_helpdesk_sla_warning_seconds = fields.Integer(
        string="SLA Warning (seconds)",
        config_parameter="pbx_helpdesk.sla_warning_seconds",
        default=120,
    )
    pbx_helpdesk_sla_breach_seconds = fields.Integer(
        string="SLA Breach (seconds)",
        config_parameter="pbx_helpdesk.sla_breach_seconds",
        default=300,
    )
    pbx_helpdesk_auto_create_ticket = fields.Boolean(
        string="Auto-create ticket for unknown callers",
        config_parameter="pbx_helpdesk.auto_create_ticket",
        default=False,
    )
