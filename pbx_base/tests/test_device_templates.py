# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestDeviceTemplates(TransactionCase):
    """pbx-device-templates: mall → resolverad config per enhet."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.env.company.pbx_server_host = "pbx.example.com"
        cls.env.company.pbx_sip_port = "5061"
        cls.env.company.pbx_stun_enabled = True
        cls.env.company.pbx_stun_server = "stun.example.com"
        cls.user = cls.env.ref("base.user_demo")

    def _make_template(self, device_type="mobile", **overrides):
        base = {
            "name": "Test " + device_type,
            "device_type": device_type,
            "config_template": {
                "sip_username": {"label": "Användarnamn", "source": "device", "field": "username", "order": 1},
                "sip_password": {"label": "Lösenord", "source": "device", "field": "secret", "order": 2},
                "sip_server": {"label": "SIP-server", "source": "company", "field": "pbx_server_host", "order": 3},
                "sip_port": {"label": "Port", "source": "company", "field": "pbx_sip_port", "order": 4},
                "sip_domain": {"label": "Domän", "source": "company", "field": "pbx_domain", "order": 5},
                "stun": {"label": "STUN", "source": "company", "field": "pbx_stun_server",
                         "only_if": "pbx_stun_enabled", "order": 6},
                "guide": {"label": "Guide", "source": "static", "value": "Steg 1", "order": 99},
            },
        }
        base.update(overrides)
        return self.env["pbx.device.template"].create(base)

    def _make_sub(self, device_type="mobile", number="80402"):
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "8040",
                "user_id": self.user.id,
            }
        )
        sub = self.env["pbx.sub_extension"].create(
            {"extension_id": ext.id, "number": number, "type": device_type}
        )
        return sub

    def test_config_populated_from_template(self):
        self._make_template("mobile")
        sub = self._make_sub("mobile")
        cfg = sub.config
        self.assertTrue(cfg, "config ska vara ifylld från mallen")
        self.assertEqual(cfg["sip_username"]["value"], sub.username)
        self.assertEqual(cfg["sip_password"]["value"], sub.secret)
        self.assertEqual(cfg["sip_server"]["value"], "pbx.example.com")
        self.assertEqual(cfg["sip_domain"]["value"], "test.se")
        self.assertEqual(cfg["guide"]["value"], "Steg 1")

    def test_only_if_hides_stun(self):
        self._make_template("mobile")
        self.env.company.pbx_stun_enabled = False
        sub = self._make_sub("mobile")
        self.assertNotIn("stun", sub.config)

    def test_no_template_falls_back(self):
        # ingen mall för voicemail → config False
        sub = self._make_sub("voicemail", number="80499")
        self.assertFalse(sub.config)
        self.assertTrue(sub.config_display)  # fallback till sip_config_display
