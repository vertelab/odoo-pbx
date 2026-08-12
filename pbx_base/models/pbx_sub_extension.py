# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
import secrets
import string

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _generate_sip_secret(length=16):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PbxSubExtension(models.Model):
    _name = "pbx.sub_extension"
    _inherit = ["pbx.config.dirty.mixin"]
    _description = "PBX Sub Extension (individual device)"

    extension_id = fields.Many2one("pbx.extension", required=True, ondelete="cascade")
    number = fields.Char(
        string="Nummer",
        readonly=True,
        help="SIP-identitet för enheten (auto-genererat, t.ex. 101 för anknytning 10). "
             "Har ingen koppling till ringordningen — sequence styr i vilken ordning enheterna ringer.",
    )
    label = fields.Char(help="e.g. Odoo, Yealink, Mobile")
    type = fields.Selection(
        [
            ("browser", "Odoo VOIP"),
            ("desktop", "Desktop Softphone"),
            ("hardware", "Hardware Phone"),
            ("mobile", "Mobile"),
            ("voicemail", "Voicemail"),
        ],
        default="browser",
        required=True,
    )
    sequence = fields.Integer(
        default=1,
        string="Sequence",
        help="Ringordning (1 = först). Number har ingen koppling till ringordningen.",
    )
    ring_timeout = fields.Integer(
        default=10,
        help="How long (seconds) to ring this device before giving up. "
             "In sequential mode each device gets its own timeout; "
             "in parallel mode the longest timeout among active devices is used.",
    )
    transport = fields.Selection(
        [("wss", "WebSocket Secure"), ("udp", "UDP"), ("tcp", "TCP")],
        default="wss",
    )
    username = fields.Char(default=lambda self: _generate_sip_secret(8))
    secret = fields.Char(default=lambda self: _generate_sip_secret())
    active = fields.Boolean(
        default=True,
        help="When unchecked, this device is excluded from the generated dialplan.",
    )

    sip_config_display = fields.Char(
        string="SIP-konfiguration",
        compute="_compute_sip_config_display",
        help="Genererade SIP-parametrar för enheten: username, lösenord, server, port, "
             "domän, protokoll och STUN.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generera `number` (SIP-identitet) när den inte anges.

        Konvention: {extension.public_number}{index} → anknytning 10 får enheter
        101, 102, 103…  Minsta lediga nummer väljs så att raderingar/prio-byten
        aldrig orsakar kollisioner eller omnumrering. Nummer som genereras i
        samma batch räknas med (annars kolliderar flera rader på samma nummer).

        För provisioning: `mac_address` normaliseras för hardware-typ och
        `provisioning_token` auto-genereras för desktop/mobile-typ.
        """
        used = {}
        for vals in vals_list:
            if vals.get("type") == "hardware" and vals.get("mac_address"):
                vals["mac_address"] = self._normalize_mac(vals["mac_address"])
            if vals.get("type") in ("desktop", "mobile"):
                vals.setdefault("provisioning_token", secrets.token_hex(16))
            if not vals.get("number") and vals.get("extension_id"):
                ext_id = vals["extension_id"]
                if ext_id not in used:
                    used[ext_id] = set(
                        self.env["pbx.sub_extension"]
                        .search([("extension_id", "=", ext_id)])
                        .mapped("number")
                    )
                number = self._next_free_number(ext_id, used[ext_id])
                used[ext_id].add(number)
                vals["number"] = number
        recs = super().create(vals_list)
        for rec in recs:
            rec._validate_provisioning_fields()
        return recs

    def write(self, vals):
        if vals.get("mac_address"):
            vals["mac_address"] = self._normalize_mac(vals["mac_address"])
        if vals.get("type") in ("desktop", "mobile"):
            # Rotera bara om token saknas (skapa sköter generering).
            for rec in self:
                if not rec.provisioning_token:
                    vals.setdefault("provisioning_token", secrets.token_hex(16))
        res = super().write(vals)
        for rec in self:
            rec._validate_provisioning_fields()
        return res

    def _validate_provisioning_fields(self):
        """Hardware kräver mac_address; övriga typer får inte ha MAC."""
        for rec in self:
            if rec.type == "hardware" and not rec.mac_address:
                raise ValidationError(
                    _("Hårdvaruenhet kräver MAC-adress.")
                )

    @staticmethod
    def _normalize_mac(mac):
        """'00:15:65:A1:B2:C3' / '00-15-65-A1-B2-C3' → '001565a1b2c3'."""
        return re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()

    @api.model
    def _next_free_number(self, extension_id, used=None):
        ext = self.env["pbx.extension"].browse(extension_id)
        prefix = "".join(ch for ch in str(ext.public_number or "") if ch.isdigit())
        if not prefix:
            prefix = "0"
        if used is None:
            used = set(
                self.env["pbx.sub_extension"]
                .search([("extension_id", "=", extension_id)])
                .mapped("number")
            )
        else:
            used = set(used)
        i = 1
        while True:
            candidate = "%s%d" % (prefix, i)
            if candidate not in used:
                return candidate
            i += 1

    @api.depends("username", "secret", "transport", "extension_id.password", "extension_id.company_id")
    def _compute_sip_config_display(self):
        for rec in self:
            company = rec.extension_id.company_id
            server = company.pbx_server_host or "«central inställning saknas»"
            domain = company.pbx_domain or "—"
            port = company.pbx_sip_port or (5061 if rec.transport == "wss" else 5060)
            stun = ""
            if company.pbx_stun_enabled and company.pbx_stun_server:
                stun = " | STUN: %s" % company.pbx_stun_server
            shared = rec.extension_id.password or rec.secret
            rec.sip_config_display = (
                "Användare: %s | Lösenord: %s | Server: %s:%s | Domän: %s | "
                "Protokoll: %s%s" % (rec.username, shared, server, port, domain, rec.transport, stun)
            )

    # Voicemail fields
    greeting = fields.Many2one("ir.attachment", string="Greeting")
    max_duration = fields.Integer(default=120, help="Max recording duration (seconds)")
    max_messages = fields.Integer(default=100)
    delete_after_days = fields.Integer(default=30)
    transcribe_enabled = fields.Boolean(default=False)

    # Provisioning (pbx-provisioning): hardware keyed by MAC, softphones by token
    mac_address = fields.Char(
        string="MAC-adress",
        help="Fysisk enhets MAC — provisioning-nyckel för hårdvarutelefoner. "
             "Normaliseras till gemener utan separatorer (001565a1b2c3).",
    )
    device_model = fields.Char(
        string="Enhetsmodell",
        help="t.ex. T46S — för att välja rätt gemensam provisioning-config.",
    )
    provisioning_token = fields.Char(
        string="Provisioning-token",
        copy=False,
        groups="pbx_base.group_pbx_admin",
        help="Per-enhet token för softphone-provisioning (desktop/mobile). "
             "Auto-genereras; URL:en är /pbx/provisioning/softphone/<token>.xml",
    )

    _sql_constraints = [
        (
            "sub_ext_unique",
            "unique(extension_id, number)",
            "Sub-extension number must be unique per extension!",
        ),
        (
            "sub_ext_mac_unique",
            "unique(mac_address)",
            "MAC-adressen får bara användas av en enhet!",
        ),
        (
            "sub_ext_token_unique",
            "unique(provisioning_token)",
            "Provisioning-token måste vara unik!",
        ),
    ]
