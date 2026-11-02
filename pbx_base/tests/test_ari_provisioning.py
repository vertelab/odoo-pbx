# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""pbx-ari-provisioning 1.1-2.2 — ARI credentials per tenant.

Each tenant (SIP domain) gets its own ARI user so a Stasis application — the
AI receptionist — authenticates per instance instead of with a shared global
credential. The user is emitted into ari.d/<domain>.conf by the config
generator and written by the daemon.

2.3 (curl against the running Asterisk) and 4.1 (a real test call) are
deployment questions; the generated file is asserted here.
"""

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestAriCredentials(TransactionCase):
    """1.1-1.3 — the credential model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.pbx_domain = "test.se"

    def setUp(self):
        super().setUp()
        self.company.write({"pbx_ari_user": False, "pbx_ari_secret": False})

    def test_ensure_creates_user_and_secret(self):
        """1.1 — the user defaults to receptionist-<sanitized domain>."""
        self.company._ensure_pbx_ari()
        self.assertEqual(self.company.pbx_ari_user, "receptionist-test-se")
        self.assertTrue(self.company.pbx_ari_secret)
        self.assertGreaterEqual(len(self.company.pbx_ari_secret), 20)

    def test_ensure_is_idempotent(self):
        """1.1 — a second call must not rotate an existing secret."""
        self.company._ensure_pbx_ari()
        secret = self.company.pbx_ari_secret
        self.company._ensure_pbx_ari()
        self.assertEqual(self.company.pbx_ari_secret, secret)

    def test_sanitize_replaces_dots(self):
        """1.1 — Asterisk section names may not contain dots."""
        self.assertEqual(
            self.env["res.company"]._pbx_sanitize_ari_name("vertel.se"),
            "vertel-se",
        )
        self.assertEqual(
            self.env["res.company"]._pbx_sanitize_ari_name("pbx-test.vertel.se"),
            "pbx-test-vertel-se",
        )

    def test_collision_gets_suffix(self):
        """1.2 — two tenants with the same sanitized name do not collide."""
        other = self.env["res.company"].create(
            {"name": "Other Tenant", "pbx_domain": "test.se"}
        )
        self.company._ensure_pbx_ari()
        other._ensure_pbx_ari()
        self.assertNotEqual(self.company.pbx_ari_user, other.pbx_ari_user)
        self.assertTrue(other.pbx_ari_user.startswith("receptionist-test-se-"))

    def test_rotation_changes_secret_and_flags_dirty(self):
        """1.3 — rotation generates a new secret and marks the config dirty."""
        self.company._ensure_pbx_ari()
        old = self.company.pbx_ari_secret
        self.company.config_dirty = False
        self.company.action_rotate_pbx_ari_secret()
        self.assertNotEqual(self.company.pbx_ari_secret, old)
        self.assertTrue(self.company.config_dirty)

    def test_ari_app_derives_from_user(self):
        """1.1 — the Stasis app name is the ARI user."""
        self.company._ensure_pbx_ari()
        self.assertEqual(self.company.pbx_ari_app, self.company.pbx_ari_user)


@tagged("-post_install", "at_install")
class TestAriGeneration(TransactionCase):
    """2.1-2.2 — ari.d/<domain>.conf generation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.pbx_domain = "test.se"
        cls.generator = cls.env["pbx.config.generator"]

    def setUp(self):
        super().setUp()
        self.company.write({"pbx_ari_user": False, "pbx_ari_secret": False})

    def test_no_credentials_means_no_file(self):
        """2.2 — without credentials the file is not emitted at all.

        Asterisk rejects a section without a password, so an empty file is
        worse than no file.
        """
        self.assertEqual(self.generator.generate_ari("test.se", self.company), "")
        self.assertNotIn("ari.d/test.se.conf", self.generator.generate_all(
            "test.se", self.company
        ))

    def test_generated_file_has_the_ari_section(self):
        """2.1 — the file carries the user, type, read_only and password."""
        self.company._ensure_pbx_ari()
        conf = self.generator.generate_ari("test.se", self.company)
        self.assertIn("[%s]" % self.company.pbx_ari_user, conf)
        self.assertIn("type=user", conf)
        self.assertIn("read_only=no", conf)
        self.assertIn("password=%s" % self.company.pbx_ari_secret, conf)

    def test_file_included_in_generate_all(self):
        """2.2 — generate_all() carries ari.d/<domain>.conf."""
        self.company._ensure_pbx_ari()
        configs = self.generator.generate_all("test.se", self.company)
        self.assertIn("ari.d/test.se.conf", configs)
        self.assertIn(self.company.pbx_ari_user, configs["ari.d/test.se.conf"])

    def test_rotated_secret_reaches_the_file(self):
        """2.2 — after rotation the generated file carries the new secret."""
        self.company._ensure_pbx_ari()
        self.company.action_rotate_pbx_ari_secret()
        conf = self.generator.generate_ari("test.se", self.company)
        self.assertIn(self.company.pbx_ari_secret, conf)
