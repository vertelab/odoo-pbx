# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


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
          "stun":         {"label": "STUN", "source": "company", "field": "pbx_stun_server",
                           "only_if": "pbx_stun_enabled", "order": 6},
          "turn":         {"label": "TURN", "source": "config", "field": "pbx.turn.server",
                           "order": 7},
          "guide":        {"label": "Konfigurationsguide", "source": "static", "value": "…", "order": 99}
        }
    """

    _name = "pbx.device.template"
    _description = "PBX Device Template"
    _order = "device_type, name"

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
        "res.company", default=lambda self: self.env.company, required=True
    )
    active = fields.Boolean(default=True)
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
