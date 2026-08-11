# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxVoicemailMessage(models.Model):
    _name = "pbx.voicemail.message"
    _description = "Voicemail Message"
    _order = "create_date desc"

    extension_id = fields.Many2one("pbx.extension", required=True, ondelete="cascade")
    user_id = fields.Many2one(
        "res.users",
        related="extension_id.user_id",
        store=True,
    )
    caller_number = fields.Char()
    caller_name = fields.Char()
    duration = fields.Integer(help="Duration in seconds")
    audio_attachment_id = fields.Many2one("ir.attachment", string="Audio")
    transcript = fields.Text()
    is_read = fields.Boolean(default=False)
    call_id = fields.Many2one("voip.call", string="Related Call")
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )

    def mark_read(self):
        self.is_read = True

    def action_listen(self):
        self.ensure_one()
        if self.audio_attachment_id:
            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content/{self.audio_attachment_id.id}?download=true",
                "target": "self",
            }
