# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
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
        self.assertIn("DEVICE_STATE(PJSIP/u80201)", dialplan)
        self.assertIn("DEVICE_STATE(PJSIP/u80202)", dialplan)
        # per-device timeouts in sequential ring
        self.assertIn("Dial(PJSIP/u80201,15)", dialplan)
        self.assertIn("Dial(PJSIP/u80202,25)", dialplan)
        # voicemail-type är inte en ringenhet
        self.assertNotIn("PJSIP/u80299,", dialplan)

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
        self.assertIn("PJSIP/u80211,15", dialplan)
        self.assertNotIn("PJSIP/u80212", dialplan)

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
        self.assertIn("Dial(PJSIP/u80221&PJSIP/u80222,30)", dialplan)

    # ------------------------------------------------------------------
    # Security (self-service: egen anknytning + egna samtal för alla interna
    # användare — utan att göra dem till PBX Operator)
    # ------------------------------------------------------------------

    def _plain_user(self):
        """En vanlig intern användare UTAN någon PBX-grupp."""
        user = self.env.ref("base.user_demo")
        for gid in (
            "pbx_base.group_pbx_operator",
            "pbx_base.group_pbx_office",
            "pbx_base.group_pbx_admin",
        ):
            group = self.env.ref(gid)
            if user.has_group(gid):
                user.write({"groups_id": [(3, group.id)]})
        return user

    def test_plain_user_own_extension_rule(self):
        """Vanlig användare (utan PBX-grupp) ser endast sin egen anknytning."""
        user = self._plain_user()
        ext_own = self._make_ext(public_number="8023")
        ext_own.user_id = user.id
        ext_other = self._make_ext(public_number="8024")
        ext_other.user_id = self.env.ref("base.user_admin").id
        visible = self.env["pbx.extension"].with_user(user).search([])
        self.assertIn(ext_own, visible)
        self.assertNotIn(ext_other, visible)

    def test_plain_user_can_write_own_extension(self):
        """Vanlig användare kan skriva ring_strategy på sin egen anknytning."""
        user = self._plain_user()
        ext_own = self._make_ext(public_number="8023", ring_strategy="sequential")
        ext_own.user_id = user.id
        ext_own.with_user(user).write({"ring_strategy": "parallel"})
        self.assertEqual(ext_own.ring_strategy, "parallel")

    def test_plain_user_cannot_write_other_extension(self):
        """Vanlig användare kan inte skriva någon annans anknytning."""
        user = self._plain_user()
        ext_other = self._make_ext(public_number="8024")
        ext_other.user_id = self.env.ref("base.user_admin").id
        with self.assertRaises(AccessError):
            ext_other.with_user(user).write({"ring_strategy": "parallel"})

    def test_plain_user_cannot_create_extension(self):
        """Vanlig användare får inte skapa anknytningar."""
        user = self._plain_user()
        with self.assertRaises(AccessError):
            self.env["pbx.extension"].with_user(user).create(
                {"public_number": "8025", "company_id": self.env.company.id}
            )

    def test_plain_user_sees_own_sub_extensions_only(self):
        """Vanlig användare ser bara sina egna enheter (sub_extension)."""
        user = self._plain_user()
        ext_own = self._make_ext(
            public_number="8023", sub_extension_ids=[(0, 0, {"type": "browser"})]
        )
        ext_own.user_id = user.id
        ext_other = self._make_ext(
            public_number="8024", sub_extension_ids=[(0, 0, {"type": "browser"})]
        )
        ext_other.user_id = self.env.ref("base.user_admin").id
        own_sub = ext_own.sub_extension_ids
        other_sub = ext_other.sub_extension_ids
        visible = self.env["pbx.sub_extension"].with_user(user).search([])
        self.assertIn(own_sub, visible)
        self.assertNotIn(other_sub, visible)

    def test_plain_user_own_call_rule(self):
        """Vanlig användare ser bara sina egna samtal (pbx.call)."""
        user = self._plain_user()
        call_own = self.env["pbx.call"].create(
            {"user_id": user.id, "phone_number": "123"}
        )
        call_other = self.env["pbx.call"].create(
            {"user_id": self.env.ref("base.user_admin").id, "phone_number": "456"}
        )
        visible = self.env["pbx.call"].with_user(user).search([])
        self.assertIn(call_own, visible)
        self.assertNotIn(call_other, visible)

    def test_no_auto_assign_operator(self):
        """Koppling till anknytning tilldelar INTE group_pbx_operator."""
        user = self._plain_user()
        ext = self._make_ext(public_number="8023")
        ext.user_id = user.id
        self.assertFalse(user.has_group("pbx_base.group_pbx_operator"))
