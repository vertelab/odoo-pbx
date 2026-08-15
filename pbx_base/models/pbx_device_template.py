# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PbxDeviceTemplate(models.Model):
    """Konfigurerbara enhetsmallar per enhetstyp.

    Mallen definierar vilka SIP-konfigurationsparametrar en enhet har och
    var värdet kommer ifrån (source). På Min profil populeras mallen med
    skarpa data (username, delat lösenord, server, port, STUN …).

    config_template (Json) exempel:
        {
          "sip_username": {"label": "Användarnamn", "source": "device", "field": "username", "order": 1},
          "sip_password": {"label": "Lösenord", "source": "extension", "field": "password", "order": 2},
          "sip_server":   {"label": "SIP-server", "source": "company", "field": "pbx_server_host", "order": 3},
          "sip_port":     {"label": "Port", "source": "company", "field": "pbx_sip_port", "order": 4},
          "sip_domain":   {"label": "Domän", "source": "company", "field": "pbx_domain", "order": 5},
          "turn":         {"label": "TURN", "source": "config", "field": "pbx.turn.server",
                           "only_if": "pbx_turn_enabled", "order": 7},
          "guide":        {"label": "Konfigurationsguide", "source": "static", "value": "…", "order": 99}
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
        help="Företag (tom = global mall).",
    )
    active = fields.Boolean(default=True)
    transport = fields.Selection(
        [("wss", "WebSocket Secure"), ("udp", "UDP"), ("tcp", "TCP")],
        string="Transport (default)",
        help="Default SIP-transport för enheter med denna mall. Enheten kan "
             "överskrida.",
    )
    codec_ids = fields.One2many(
        "pbx.codec.line",
        "template_id",
        string="Codecs (default)",
        help="Default codec-selektion för enheter av denna mall. Ordningen "
             "(sequence) är codec-preferensen. Lämnas tom → global default.",
    )
    config_template = fields.Json(
        string="Configuration Template",
        help=(
            "Parameterdefinitioner per enhetstyp: "
            '{"nyckel": {"label": …, "source": device|extension|company|config|user|static, '
            '"field"/"value": …, "only_if": …, "order": …}}'
        ),
    )

    _sql_constraints = [
        (
            "unique_device_type_company",
            "UNIQUE(device_type, company_id)",
            "Endast en mall per enhetstyp och företag!",
        ),
    ]
