# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestPbxCodecs(TransactionCase):
    """pbx-codecs: katalog, selektion, config-generering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.env.company.pbx_server_host = "pbx.example.com"
        cls.generator = cls.env["pbx.config.generator"]

    def _make_ext(self, public_number="80"):
        return self.env["pbx.extension"].create(
            {"public_number": public_number, "company_id": self.env.company.id}
        )

    def _make_sub(self, device_type="mobile", ext=None, **vals):
        ext = ext or self._make_ext()
        return self.env["pbx.sub_extension"].create(
            {
                "extension_id": ext.id,
                "type": device_type,
                "label": "Test",
                **vals,
            }
        )

    def _codec(self, name):
        return self.env["pbx.codec"].search([("name", "=", name)], limit=1)

    def test_seed_catalog(self):
        """Seed: g722/ulaw/alaw/opus aktiva; video inaktiv."""
        for name in ("g722", "ulaw", "alaw", "opus"):
            codec = self._codec(name)
            self.assertTrue(codec, "seed-codec %s saknas" % name)
            self.assertTrue(codec.active)
        self.assertFalse(self.env["pbx.codec"].search(
            [("name", "=", "g729")], limit=1), "g729 ska inte vara i seed")

    def test_default_fallback(self):
        """Enhet utan codec-rader → global default i priority-ordning."""
        sub = self._make_sub()
        pjsip = self.generator.generate_pjsip("test.se", self.env.company.id)
        block = "[%s](test.se-endpoint)" % sub.username
        self.assertIn(block, pjsip)
        # allow-rader i priority-ordning (g722 → ulaw → alaw → opus)
        idx_g722 = pjsip.index("allow = g722")
        idx_opus = pjsip.index("allow = opus")
        self.assertLess(idx_g722, idx_opus)

    def test_device_codec_lines_order(self):
        """Enhetens rader i sequence-ordning → allow i samma ordning."""
        g722 = self._codec("g722")
        ulaw = self._codec("ulaw")
        sub = self._make_sub()
        sub.write(
            {
                "codec_ids": [
                    (0, 0, {"sequence": 20, "codec_id": ulaw.id}),
                    (0, 0, {"sequence": 10, "codec_id": g722.id}),
                ]
            }
        )
        pjsip = self.generator.generate_pjsip("test.se", self.env.company.id)
        block_start = pjsip.index("[%s](test.se-endpoint)" % sub.username)
        block_end = pjsip.index("[test.se-%s-auth]" % sub.number)
        block = pjsip[block_start:block_end]
        self.assertLess(block.index("allow = g722"), block.index("allow = ulaw"))

    def test_browser_always_opus(self):
        """Browser-enhet utan opus i raderna → opus prependas (WebRTC)."""
        alaw = self._codec("alaw")
        sub = self._make_sub(device_type="browser")
        sub.write({"codec_ids": [(0, 0, {"sequence": 10, "codec_id": alaw.id})]})
        pjsip = self.generator.generate_pjsip("test.se", self.env.company.id)
        block_start = pjsip.index("[%s](test.se-endpoint)" % sub.username)
        block_end = pjsip.index("[test.se-%s-auth]" % sub.number)
        block = pjsip[block_start:block_end]
        self.assertLess(block.index("allow = opus"), block.index("allow = alaw"))

    def test_sync_from_available(self):
        """pbx.codecs.available bygger/uppdaterar katalogen."""
        icp = self.env["ir.config_parameter"]
        icp.set_param("pbx.codecs.available", "opus,g722,ulaw")
        self.env["pbx.codec"]._sync_from_available()
        opus = self._codec("opus")
        g722 = self._codec("g722")
        self.assertLess(opus.priority, g722.priority)
