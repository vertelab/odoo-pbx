# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestFollowMeDeviceControl(TransactionCase):
    """follow-me-device-control: per-device ring timeout, DEVICE_STATE busy
    gate, sequence ordering, active/inactive, auto-numbering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.generator = cls.env["pbx.config.generator"]

    def _make_ext(self, **kw):
        vals = {
            "company_id": self.env.company.id,
            "public_number": kw.pop("public_number", "8020"),
            "ring_strategy": kw.pop("ring_strategy", "sequential"),
            "sub_extension_ids": kw.pop("sub_extension_ids", []),
        }
        vals.update(kw)
        return self.env["pbx.extension"].create(vals)

    # ------------------------------------------------------------------
    # Auto-numbering
    # ------------------------------------------------------------------

    def test_auto_numbering(self):
        ext = self._make_ext(
            sub_extension_ids=[
                (0, 0, {"type": "browser"}),
                (0, 0, {"type": "mobile"}),
            ]
        )
        subs = ext.sub_extension_ids.sorted("number")
        self.assertEqual([s.number for s in subs], ["80201", "80202"])

    def test_auto_numbering_min_free(self):
        ext = self._make_ext(
            sub_extension_ids=[
                (0, 0, {"number": "80201", "type": "browser"}),
                (0, 0, {"type": "mobile"}),
            ]
        )
        # 80201 upptagen → minsta lediga ska bli 80202
        self.assertEqual(ext.sub_extension_ids[1].number, "80202")

    # ------------------------------------------------------------------
    # Dialplan generation (busy gate + per-device timeout)
    # ------------------------------------------------------------------

    def test_busy_gate_and_per_device_timeout(self):
        ext = self._make_ext(
            public_number="8020",
            ring_strategy="sequential",
            sub_extension_ids=[
                (0, 0, {"number": "80201", "type": "browser", "sequence": 1, "ring_timeout": 15}),
                (0, 0, {"number": "80202", "type": "hardware", "sequence": 2, "ring_timeout": 25, "mac_address": "00:1B:66:AA:BB:CC"}),
                (0, 0, {"number": "80299", "type": "voicemail", "sequence": 99}),
            ],
        )
        dialplan = self.generator.generate_extensions("test.se", self.env.company)
        self.assertIn("DEVICE_STATE(PJSIP/test.se-80201)", dialplan)
        self.assertIn("DEVICE_STATE(PJSIP/test.se-80202)", dialplan)
        # per-device timeouts in sequential ring
        self.assertIn("Dial(PJSIP/test.se-80201,15)", dialplan)
        self.assertIn("Dial(PJSIP/test.se-80202,25)", dialplan)
        # voicemail-type är inte en ringenhet
        self.assertNotIn("PJSIP/test.se-80299,", dialplan)

    def test_inactive_device_excluded(self):
        ext = self._make_ext(
            public_number="8021",
            ring_strategy="sequential",
            sub_extension_ids=[
                (0, 0, {"number": "80211", "type": "browser", "sequence": 1, "ring_timeout": 15}),
                (0, 0, {"number": "80212", "type": "browser", "sequence": 2, "ring_timeout": 15, "active": False}),
            ],
        )
        dialplan = self.generator.generate_extensions("test.se", self.env.company)
        self.assertIn("PJSIP/test.se-80211,15", dialplan)
        self.assertNotIn("PJSIP/test.se-80212", dialplan)

    def test_parallel_max_timeout(self):
        ext = self._make_ext(
            public_number="8022",
            ring_strategy="parallel",
            sub_extension_ids=[
                (0, 0, {"number": "80221", "type": "browser", "sequence": 1, "ring_timeout": 10}),
                (0, 0, {"number": "80222", "type": "browser", "sequence": 2, "ring_timeout": 30}),
            ],
        )
        dialplan = self.generator.generate_extensions("test.se", self.env.company)
        # parallel: längsta timeout används
        self.assertIn("Dial(PJSIP/test.se-80221&PJSIP/test.se-80222,30)", dialplan)

    # ------------------------------------------------------------------
    # Security (self-service: egen anknytning)
    # ------------------------------------------------------------------

    def test_operator_own_extension_rule(self):
        """Operatör ser endast sin egen anknytning (record rule)."""
        user = self.env.ref("base.user_demo")
        # koppla demo-användaren till en egen anknytning
        ext_own = self._make_ext(public_number="8023")
        ext_own.user_id = user.id
        ext_other = self._make_ext(public_number="8024")
        ext_other.user_id = self.env.ref("base.user_admin").id
        # ge användaren operator-gruppen (self-service-grund)
        user.write(
            {
                "groups_id": [
                    (4, self.env.ref("pbx_base.group_pbx_operator").id)
                ]
            }
        )
        visible = self.env["pbx.extension"].with_user(user).search([])
        self.assertIn(ext_own, visible)
        self.assertNotIn(ext_other, visible)

    def test_operator_cannot_create_extension(self):
        """Operatör får inte skapa anknytningar (record rule perm_create=False)."""
        user = self.env.ref("base.user_demo")
        user.write(
            {
                "groups_id": [
                    (4, self.env.ref("pbx_base.group_pbx_operator").id)
                ]
            }
        )
        with self.assertRaises(Exception):
            self.env["pbx.extension"].with_user(user).create(
                {"public_number": "8025", "company_id": self.env.company.id}
            )
