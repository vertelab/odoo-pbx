# Copyright 2026 Vertel Sverige AB
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
        cls.env.company.pbx_turn_enabled = True
        cls.env["ir.config_parameter"].set_param("pbx.turn.server", "turn.example.com")
        cls.user = cls.env.ref("base.user_demo")

    def _make_template(self, device_type="mobile", **overrides):
        base = {
            "name": "Test " + device_type,
            "device_type": device_type,
            "config_template": {
                "sip_username": {"label": "Username", "source": "device", "field": "username", "order": 1},
                "sip_password": {"label": "Password", "source": "extension", "field": "password", "order": 2},
                "sip_server": {"label": "SIP Server", "source": "company", "field": "pbx_server_host", "order": 3},
                "sip_port": {"label": "Port", "source": "company", "field": "pbx_sip_port", "order": 4},
                "sip_domain": {"label": "Domain", "source": "company", "field": "pbx_domain", "order": 5},
                "turn": {"label": "TURN", "source": "config", "field": "pbx.turn.server",
                         "only_if": "pbx_turn_enabled", "order": 6},
                "guide": {"label": "Guide", "source": "static", "value": "Step 1", "order": 99},
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
        self.assertTrue(cfg, "config must be populated from the template")
        self.assertEqual(cfg["sip_username"]["value"], sub.username)
        self.assertEqual(cfg["sip_password"]["value"], sub.extension_id.password)
        self.assertEqual(cfg["sip_server"]["value"], "pbx.example.com")
        self.assertEqual(cfg["sip_domain"]["value"], "test.se")
        self.assertEqual(cfg["guide"]["value"], "Step 1")

    def test_only_if_hides_turn(self):
        self._make_template("mobile")
        self.env.company.pbx_turn_enabled = False
        sub = self._make_sub("mobile")
        self.assertNotIn("turn", sub.config)

    def test_no_template_falls_back(self):
        # no template for voicemail → config False
        sub = self._make_sub("voicemail", number="80499")
        self.assertFalse(sub.config)
        self.assertTrue(sub.config_display)  # fallback to sip_config_display

    # ------------------------------------------------------------------
    # 7.x — password rotation ("Generate new password")
    # ------------------------------------------------------------------
    def test_rotate_password_changes_shared_password(self):
        """7.1 — rotation writes a new shared password and logs it.

        Every device reads `extension.password`, so rotating it is the only
        way to invalidate a leaked credential. The write hook flags the
        config dirty and re-syncs voip_oca.
        """
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9070",
                "user_id": self.user.id,
            }
        )
        before = ext.password
        self.assertTrue(before, "a new extension gets a generated password")

        ext.action_generate_new_password()

        self.assertNotEqual(ext.password, before)
        self.assertTrue(ext.password)
        # The rotation is auditable: a message is posted on the chatter.
        self.assertTrue(
            ext.message_ids.filtered(lambda m: "rotated" in (m.body or "").lower()),
            "rotation must be logged on the extension chatter",
        )

    def test_rotate_password_denied_for_foreign_extension(self):
        """7.5 — a plain user cannot rotate someone else's password."""
        from odoo.exceptions import AccessError

        other = self.env["res.users"].create(
            {
                "name": "Other User",
                "login": "pbx_other_user",
                "email": "other@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9071",
                "user_id": other.id,
            }
        )
        with self.assertRaises(AccessError):
            ext.with_user(self.user).action_generate_new_password()

    def test_rotate_password_allowed_for_own_extension(self):
        """7.1 — the owner may rotate their own extension's password."""
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9072",
                "user_id": self.user.id,
            }
        )
        before = ext.password
        ext.with_user(self.user).action_generate_new_password()
        self.assertNotEqual(ext.password, before)

    def test_rotation_flags_company_config_dirty(self):
        """7.5 — rotation marks the company config dirty so the next publish runs.

        The dirty flag lives on res.company (pbx.config.dirty.mixin), not on
        the extension: the Sync icon reads it to know a publish is pending.
        """
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9073",
                "user_id": self.user.id,
            }
        )
        # Clear the flag the create already set, then rotate.
        self.env.company.config_dirty = False
        ext.action_generate_new_password()
        self.assertTrue(
            self.env.company.config_dirty,
            "a rotated password must trigger a config republish",
        )

    # ------------------------------------------------------------------
    # 8.1 — linking a user grants PBX Operator (self-service access)
    # ------------------------------------------------------------------
    def test_sync_user_link_grants_operator_group(self):
        """8.1 — a user linked to an extension becomes a PBX Operator.

        Self-service needs base.group_user only, but the operator panel and
        the call widgets check group_pbx_operator. Granting it on link means
        a provisioned user does not wait for an administrator.
        """
        operator = self.env.ref("pbx_base.group_pbx_operator")
        user = self.env["res.users"].create(
            {
                "name": "Fresh Operator",
                "login": "pbx_fresh_operator",
                "email": "fresh@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertNotIn(operator, user.groups_id)

        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9074",
                "user_id": user.id,
            }
        )
        ext._sync_user_link()

        self.assertIn(operator, user.groups_id)
        self.assertEqual(user.pbx_extension_id, ext)

    def test_sync_user_link_is_idempotent(self):
        """8.1 — re-syncing does not duplicate the group or raise."""
        operator = self.env.ref("pbx_base.group_pbx_operator")
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9075",
                "user_id": self.user.id,
            }
        )
        ext._sync_user_link()
        ext._sync_user_link()
        self.assertEqual(
            len(self.user.groups_id.filtered(lambda g: g == operator)), 1
        )
