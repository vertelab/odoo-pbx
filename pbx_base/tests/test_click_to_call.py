# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestClickToCall(TransactionCase):
    """Click-to-call: första device, nummernormalisering, felhantering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.user = cls.env.ref("base.user_demo")

    def _make_ext(self, user=True, number="9030", **subs):
        sub_cmds = []
        numbers = subs.get("numbers", {})
        for device in subs.get("devices", [("browser", 1, True)]):
            typ, seq, active = device[0], device[1], device[2]
            cmd = {"type": typ, "sequence": seq, "active": active}
            if typ in numbers:
                cmd["number"] = numbers[typ]
            if len(device) > 3 and device[3]:
                cmd["mac_address"] = device[3]
            sub_cmds.append((0, 0, cmd))
        return self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": number,
                "user_id": self.user.id if user else False,
                "sub_extension_ids": sub_cmds,
            }
        )

    def test_normalize_number(self):
        ext = self._make_ext()
        self.assertEqual(ext._normalize_click_number("+46 (70) 123-456"), "+4670123456")
        self.assertEqual(ext._normalize_click_number("0701-23 45 67"), "0701234567")
        self.assertEqual(ext._normalize_click_number("  "), "")

    def test_no_user_raises(self):
        ext = self._make_ext(user=False)
        with self.assertRaises(UserError):
            ext.action_click_to_call("0701234567")

    def test_no_active_device_raises(self):
        # create() auto-skapar en browser-enhet om ingen finns — gör den inaktiv
        ext = self._make_ext(number="9031", devices=[("voicemail", 99, True)])
        ext.sub_extension_ids.write({"active": False})
        with self.assertRaises(UserError):
            ext.action_click_to_call("0701234567")

    def test_first_active_device_used(self):
        """Voicemail räknas inte; första aktiva enhet (sequence) används."""
        ext = self._make_ext(
            number="9032",
            devices=[
                ("voicemail", 99, True),
                ("hardware", 2, True, "00:1B:66:11:22:44"),
                ("browser", 1, True),
            ]
        )
        res = ext.action_click_to_call("0701234567")
        browser = ext.sub_extension_ids.filtered(lambda s: s.type == "browser")
        self.assertEqual(res["device"], browser.number)
        self.assertTrue(res["channel"].startswith("PJSIP/test.se-"))
        self.assertEqual(res["exten"], "0701234567")

    def test_inactive_device_skipped(self):
        ext = self._make_ext(
            number="9033",
            devices=[
                ("browser", 1, False),
                ("mobile", 2, True),
            ],
            numbers={"browser": "90331", "mobile": "90332"}
        )
        res = ext.action_click_to_call("0701234567")
        mobile = ext.sub_extension_ids.filtered(lambda s: s.type == "mobile")
        self.assertEqual(res["device"], mobile.number)
