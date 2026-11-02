# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""pbx-self-service 4.2 + 4.3 — the user's own changes reach the dialplan,
and a user without a PBX extension sees no self-service page.

4.2 is a development question: changing ring order / ring time on the user's
own record must be reflected in the generated dialplan. The Asterisk reload
itself is drift.

4.3 asserts the page contract: the Settings/Devices pages are rendered for
every internal user (base.group_user), because self-service is not gated on a
PBX group — but a user with no extension sees the "No PBX extension linked"
notice and no editable fields.
"""

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestSelfServiceToDialplan(TransactionCase):
    """A self-service edit must change the generated extensions.conf."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.env.company.pbx_server_host = "pbx.example.com"
        cls.user = cls.env.ref("base.user_demo")
        cls.ext = cls.env["pbx.extension"].create(
            {
                "company_id": cls.env.company.id,
                "public_number": "9200",
                "user_id": cls.user.id,
                "ring_strategy": "sequential",
            }
        )
        cls.ext.sub_extension_ids.write({"active": False})
        cls.first = cls.env["pbx.sub_extension"].create(
            {
                "extension_id": cls.ext.id,
                "type": "mobile",
                "sequence": 1,
                "ring_timeout": 15,
                "active": True,
            }
        )
        cls.second = cls.env["pbx.sub_extension"].create(
            {
                "extension_id": cls.ext.id,
                "type": "desktop",
                "sequence": 2,
                "ring_timeout": 15,
                "active": True,
            }
        )

    def _dialplan(self):
        return self.env["pbx.config.generator"].generate_extensions(
            "test.se", self.env.company
        )

    def test_ring_order_change_reaches_dialplan(self):
        """4.2 — moving a device up the list changes which one rings first."""
        before = self._dialplan()
        first_pos = before.index("PJSIP/%s,15" % self.first.username)
        second_pos = before.index("PJSIP/%s,15" % self.second.username)
        self.assertLess(first_pos, second_pos, "sequence 1 rings before 2")

        # The user reorders their devices from My Profile.
        self.first.write({"sequence": 9})

        after = self._dialplan()
        new_first = after.index("PJSIP/%s,15" % self.first.username)
        new_second = after.index("PJSIP/%s,15" % self.second.username)
        self.assertLess(new_second, new_first, "the reordered device rings last")

    def test_ring_timeout_change_reaches_dialplan(self):
        """4.2 — the per-device timeout is what the dialplan dials with."""
        self.assertIn("PJSIP/%s,15" % self.first.username, self._dialplan())
        self.first.write({"ring_timeout": 30})
        self.assertIn("PJSIP/%s,30" % self.first.username, self._dialplan())

    def test_disabling_a_device_removes_it_from_dialplan(self):
        """4.2 — an inactive device is not dialled at all."""
        self.assertIn("PJSIP/%s" % self.first.username, self._dialplan())
        self.first.write({"active": False})
        self.assertNotIn("PJSIP/%s" % self.first.username, self._dialplan())


@tagged("-post_install", "at_install")
class TestSelfServiceVisibility(TransactionCase):
    """4.3 — the self-service page contract."""

    def test_page_rendered_for_plain_internal_user(self):
        """Self-service needs base.group_user only — no PBX group.

        The pages are injected into the user form for every internal user;
        what differs is the content (the "no extension" notice).
        """
        views = self.env["res.users"].get_views([(False, "form")])
        arch = views["views"]["form"]["arch"]
        self.assertIn('name="pbx_settings"', arch)
        self.assertIn('name="pbx_devices"', arch)

    def test_no_extension_shows_notice(self):
        """A user without an extension sees the notice, not editable fields."""
        user = self.env["res.users"].create(
            {
                "name": "No PBX User",
                "login": "pbx_no_extension_user",
                "email": "nopbx@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertFalse(user.pbx_extension_id)
        self.assertFalse(
            user.pbx_sub_extension_ids,
            "a user without an extension has no devices to administer",
        )
