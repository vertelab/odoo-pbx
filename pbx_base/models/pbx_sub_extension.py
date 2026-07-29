# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import secrets
import string

from odoo import fields, models


def _generate_sip_secret(length=16):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PbxSubExtension(models.Model):
    _name = "pbx.sub_extension"
    _description = "PBX Sub Extension (individual device)"

    extension_id = fields.Many2one("pbx.extension", required=True, ondelete="cascade")
    tenant_id = fields.Many2one(related="extension_id.tenant_id", store=True)
    number = fields.Char(required=True)
    label = fields.Char(help="e.g. Odoo, Yealink, Mobile")
    type = fields.Selection(
        [
            ("browser", "Browser (WSS)"),
            ("desktop", "Desktop Softphone"),
            ("hardware", "Hardware Phone"),
            ("mobile", "Mobile"),
            ("voicemail", "Voicemail"),
        ],
        default="browser",
        required=True,
    )
    priority = fields.Integer(default=1, help="Ring priority (1 = first, 99 = last)")
    transport = fields.Selection(
        [("wss", "WebSocket Secure"), ("udp", "UDP"), ("tcp", "TCP")],
        default="wss",
    )
    username = fields.Char(default=lambda self: _generate_sip_secret(8))
    secret = fields.Char(default=lambda self: _generate_sip_secret())
    active = fields.Boolean(default=True)

    # Voicemail fields
    greeting = fields.Many2one("ir.attachment", string="Greeting")
    max_duration = fields.Integer(default=120, help="Max recording duration (seconds)")
    max_messages = fields.Integer(default=100)
    delete_after_days = fields.Integer(default=30)
    transcribe_enabled = fields.Boolean(default=False)

    _sql_constraints = [
        (
            "sub_ext_unique",
            "unique(extension_id, number)",
            "Sub-extension number must be unique per extension!",
        ),
    ]
