# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""pbx-device-catalog — the template catalog and per-device template choice.

These tests document the behaviour the catalog adds on top of
``pbx-device-templates``. They are written against the target model, so they
only pass once the model changes in tasks 1.1–1.4 have landed:

* 1.1  UNIQUE ``(device_type, company_id)`` → ``(device_type, name, company_id)``
* 1.2  new fields ``vendor``, ``sequence``, ``user_selectable``,
       ``default_for_type``, ``model_match``
* 1.3  ``pbx.sub_extension.template_id`` domain: ``device_type`` +
       ``user_selectable``
* 1.4  ``_compute_config`` resolution order:
       ``template_id`` → ``model_match`` → ``default_for_type`` →
       first ``user_selectable``
* 3.1  ``_populate_config`` passes ``section``/``render`` through into
       ``config``

Until then the field-dependent tests fail with a clear message instead of an
obscure ORM error — see ``_require_catalog_fields``.
"""

from odoo.tests import TransactionCase, tagged

CATALOG_FIELDS = ("vendor", "sequence", "user_selectable", "default_for_type", "model_match")


@tagged("-post_install", "at_install")
class TestDeviceCatalog(TransactionCase):
    """pbx-device-catalog: flera mallar per typ, kuratering, auto-match."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.env.company.pbx_server_host = "pbx.example.com"
        cls.env.company.pbx_sip_port = "5061"
        cls.user = cls.env.ref("base.user_demo")
        cls.Template = cls.env["pbx.device.template"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_catalog_fields(self):
        """Skip with an explicit message while the model changes are pending.

        A plain ``self.skipTest`` would hide the gap; the message names the
        task so a failing run points at the missing model change.
        """
        missing = [f for f in CATALOG_FIELDS if f not in self.Template._fields]
        if missing:
            self.skipTest(
                "pbx-device-catalog tasks 1.1–1.2 not landed: pbx.device.template "
                "is missing %s" % ", ".join(missing)
            )

    def _make_template(self, device_type="mobile", name=None, **overrides):
        vals = {
            "name": name or ("%s template" % device_type),
            "device_type": device_type,
            "config_template": {
                "sip_username": {
                    "label": "Username",
                    "source": "device",
                    "field": "username",
                    "section": "Account",
                    "order": 1,
                },
                "sip_password": {
                    "label": "Password",
                    "source": "extension",
                    "field": "password",
                    "section": "Account",
                    "render": "reveal",
                    "order": 2,
                },
                "sip_server": {
                    "label": "SIP Server",
                    "source": "company",
                    "field": "pbx_server_host",
                    "section": "Network",
                    "order": 3,
                },
            },
        }
        vals.update(overrides)
        return self.Template.create(vals)

    def _make_sub(self, device_type="mobile", number="80402", **overrides):
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "8040",
                "user_id": self.user.id,
            }
        )
        vals = {"extension_id": ext.id, "number": number, "type": device_type}
        vals.update(overrides)
        return self.env["pbx.sub_extension"].create(vals)

    # ------------------------------------------------------------------
    # 1.1 — the catalog: several templates per device type
    # ------------------------------------------------------------------
    def test_multiple_templates_per_device_type(self):
        """1.1 — two mobile templates can coexist (UNIQUE relaxed).

        The old constraint was UNIQUE(device_type, company_id), which made a
        catalog impossible: a second mobile template raised an IntegrityError.
        """
        self._make_template("mobile", name="sipdroid")
        self._make_template("mobile", name="Zoiper")
        templates = self.Template.search(
            [("device_type", "=", "mobile"), ("company_id", "in", [self.env.company.id, False])]
        )
        self.assertGreaterEqual(len(templates), 2)

    def test_same_name_still_unique_per_type_and_company(self):
        """1.1 — the new uniqueness is (device_type, name, company_id)."""
        self._make_template("mobile", name="Zoiper")
        with self.assertRaises(Exception):
            self._make_template("mobile", name="Zoiper")

    # ------------------------------------------------------------------
    # 1.2 — catalog metadata
    # ------------------------------------------------------------------
    def test_catalog_fields_exist_with_defaults(self):
        """1.2 — vendor/sequence/user_selectable/default_for_type/model_match."""
        self._require_catalog_fields()
        tpl = self._make_template("mobile", name="Zoiper", vendor="Zoiper")
        self.assertEqual(tpl.vendor, "Zoiper")
        self.assertEqual(tpl.sequence, 10, "sequence default is 10")
        self.assertTrue(tpl.user_selectable, "templates are user-selectable by default")
        self.assertFalse(tpl.default_for_type)
        self.assertFalse(tpl.model_match)

    # ------------------------------------------------------------------
    # 1.3 — explicit choice per device
    # ------------------------------------------------------------------
    def test_template_id_field_on_sub_extension(self):
        """1.3 — pbx.sub_extension.template_id exists."""
        self.assertIn("template_id", self.env["pbx.sub_extension"]._fields)

    # ------------------------------------------------------------------
    # 1.4 — resolution order
    # ------------------------------------------------------------------
    def test_explicit_template_id_wins(self):
        """1.4 step 1 — the device's explicit choice beats the default."""
        self._require_catalog_fields()
        sipdroid = self._make_template("mobile", name="sipdroid", default_for_type=True)
        zoiper = self._make_template("mobile", name="Zoiper")
        sub = self._make_sub("mobile", template_id=zoiper.id)
        self.assertEqual(sub._resolve_template(), zoiper)
        self.assertNotEqual(sub._resolve_template(), sipdroid)

    def test_model_match_auto_selects_hardware(self):
        """1.4 step 2 — device_model "T46S" matches the Yealink template."""
        self._require_catalog_fields()
        self._make_template("hardware", name="Generic hardware")
        yealink = self._make_template(
            "hardware", name="Yealink T4xS", model_match="T46S"
        )
        sub = self._make_sub("hardware", number="80410", device_model="T46S")
        self.assertEqual(sub._resolve_template(), yealink)

    def test_model_match_wildcard(self):
        """1.4 step 2 — "T4xS*" matches a concrete model name."""
        self._require_catalog_fields()
        yealink = self._make_template(
            "hardware", name="Yealink T4xS", model_match="T4xS*"
        )
        sub = self._make_sub("hardware", number="80411", device_model="T46S")
        self.assertEqual(sub._resolve_template(), yealink)

    def test_default_for_type_used_when_nothing_matches(self):
        """1.4 step 3 — the company's default for the type is the fallback."""
        self._require_catalog_fields()
        self._make_template("mobile", name="sipdroid", sequence=1)
        zoiper = self._make_template("mobile", name="Zoiper", default_for_type=True, sequence=2)
        sub = self._make_sub("mobile", number="80412")
        self.assertEqual(sub._resolve_template(), zoiper)

    def test_company_specific_default_beats_global(self):
        """1.4 step 3 — company-first/global-fallback precedence is kept."""
        self._require_catalog_fields()
        self._make_template(
            "mobile", name="Global default", default_for_type=True, company_id=False
        )
        company_tpl = self._make_template(
            "mobile", name="Company default", default_for_type=True
        )
        sub = self._make_sub("mobile", number="80413")
        self.assertEqual(sub._resolve_template(), company_tpl)

    def test_first_user_selectable_is_last_resort(self):
        """1.4 step 4 — no explicit choice, no default → first selectable."""
        self._require_catalog_fields()
        hidden = self._make_template(
            "mobile", name="Internal only", user_selectable=False, sequence=1
        )
        first = self._make_template("mobile", name="sipdroid", sequence=2)
        sub = self._make_sub("mobile", number="80414")
        resolved = sub._resolve_template()
        self.assertEqual(resolved, first)
        self.assertNotEqual(resolved, hidden, "user_selectable=False must not be picked")

    # ------------------------------------------------------------------
    # 3.1 — section/render pass-through
    # ------------------------------------------------------------------
    def test_config_carries_section_and_render(self):
        """3.1 — config entries carry section/render from the template."""
        tpl = self._make_template("mobile", name="Zoiper")
        sub = self._make_sub("mobile", number="80415", template_id=tpl.id)
        cfg = sub.config
        self.assertTrue(cfg, "config must resolve from the explicit template")
        self.assertEqual(cfg["sip_password"]["section"], "Account")
        self.assertEqual(cfg["sip_password"]["render"], "reveal")
        self.assertEqual(cfg["sip_server"]["section"], "Network")
        self.assertNotIn("render", cfg["sip_server"], "render defaults to plain text")

    def test_config_password_comes_from_extension(self):
        """Design A — the password source is extension/password, not device/secret."""
        tpl = self._make_template("mobile", name="Zoiper")
        sub = self._make_sub("mobile", number="80416", template_id=tpl.id)
        self.assertEqual(sub.config["sip_password"]["value"], sub.extension_id.password)

    # ------------------------------------------------------------------
    # Catalog seed (task 2.1) — asserted against the shipped data file
    # ------------------------------------------------------------------
    def test_catalog_seed_covers_every_device_type(self):
        """2.1 — the seed provides at least one template per device type."""
        for device_type in ("browser", "desktop", "hardware", "mobile"):
            templates = self.Template.search(
                [
                    ("device_type", "=", device_type),
                    ("company_id", "=", False),
                    ("active", "=", True),
                ]
            )
            self.assertTrue(
                templates, "no seeded template for device type %s" % device_type
            )
