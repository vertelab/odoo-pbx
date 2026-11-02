# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PbxDeviceTemplate(models.Model):
    """Configurable device templates per device type.

    The template defines which SIP configuration parameters a device has and
    where the value comes from (source). On My Profile the template is
    populated with live data (username, shared password, server, port, STUN …).

    config_template (Json) example:
        {
          "sip_username": {"label": "Username", "source": "device", "field": "username", "order": 1},
          "sip_password": {"label": "Password", "source": "extension", "field": "password", "order": 2},
          "sip_server":   {"label": "SIP Server", "source": "company", "field": "pbx_server_host", "order": 3},
          "sip_port":     {"label": "Port", "source": "company", "field": "pbx_sip_port", "order": 4},
          "sip_domain":   {"label": "Domain", "source": "company", "field": "pbx_domain", "order": 5},
          "turn":         {"label": "TURN", "source": "config", "field": "pbx.turn.server",
                           "only_if": "pbx_turn_enabled", "order": 7},
          "guide":        {"label": "Configuration guide", "source": "static", "value": "…", "order": 99}
        }
    """

    _name = "pbx.device.template"
    _description = "PBX Device Template"
    _order = "device_type, name"
    _inherit = ["pbx.config.dirty.mixin"]

    name = fields.Char(required=True)
    device_type = fields.Selection(
        [
            ("browser", "Odoo VOIP"),
            ("desktop", "Desktop Softphone"),
            ("hardware", "Hardware Phone"),
            ("mobile", "Mobile"),
            ("voicemail", "Voicemail"),
        ],
        required=True,
        string="Device Type",
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company,
        help="Company (empty = global template).",
    )
    active = fields.Boolean(default=True)
    transport = fields.Selection(
        [("wss", "WebSocket Secure"), ("udp", "UDP"), ("tcp", "TCP")],
        string="Transport (default)",
        help="Default SIP transport for devices using this template. The device "
             "may override it.",
    )
    codec_ids = fields.One2many(
        "pbx.codec.line",
        "template_id",
        string="Codecs (default)",
        help="Default codec selection for devices using this template. The order "
             "(sequence) is the codec preference. Left empty → global default.",
    )
    config_template = fields.Json(
        string="Configuration Template",
        help=(
            "Parameterdefinitioner per enhetstyp: "
            '{"nyckel": {"label": …, "source": device|extension|company|config|user|static, '
            '"field"/"value": …, "only_if": …, "order": …}}'
        ),
    )

    # ── Catalog metadata (pbx-device-catalog) ────────────────────────
    # Several templates may exist per device type: different software
    # (sipdroid, Zoiper, Linphone) and hardware (Yealink, Fanvil) present the
    # same SIP credentials with different field names and guides.
    vendor = fields.Char(
        help="Software or hardware vendor, e.g. Zoiper, Yealink.",
    )
    sequence = fields.Integer(
        default=10,
        help="Order in the catalog. Lower comes first.",
    )
    user_selectable = fields.Boolean(
        default=True,
        help="Show this template to end users on My Profile. Uncheck for "
             "internal-only templates that should never be picked by hand.",
    )
    default_for_type = fields.Boolean(
        help="Used when a device has no explicit template and no model match.",
    )
    model_match = fields.Char(
        help="Glob matched against the device model, e.g. 'T46S' or 'T4xS*'. "
             "Lets a hardware phone pick its own template automatically.",
    )

    _sql_constraints = [
        (
            "unique_device_type_name_company",
            "UNIQUE(device_type, name, company_id)",
            "A template with this name already exists for the device type!",
        ),
    ]
