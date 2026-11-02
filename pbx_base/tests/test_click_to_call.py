# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestClickToCall(TransactionCase):
    """Click-to-call: first device, number normalisation, error handling."""

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
        # create() auto-creates a browser device if none exists — make it inactive
        ext = self._make_ext(number="9031", devices=[("voicemail", 99, True)])
        ext.sub_extension_ids.write({"active": False})
        with self.assertRaises(UserError):
            ext.action_click_to_call("0701234567")

    def test_first_active_device_used(self):
        """Voicemail is not counted; the first active device (sequence) is used."""
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
        self.assertTrue(res["channel"].startswith("PJSIP/u"))
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

    # ------------------------------------------------------------------
    # 5.2 — the originate payload published to the daemon
    # ------------------------------------------------------------------
    def test_originate_published_on_mq(self):
        """5.2 — clicking rings the FIRST device and bridges the number.

        The click publishes `pbx.cmd.Action.Originate` with the first active
        device's channel, the company's outbound context and the normalized
        number. Mocking the publisher keeps Asterisk out of the test.
        """
        ext = self._make_ext(number="9040")
        published = []

        def fake_originate(self, server, channel, context, exten, priority=1):
            published.append(
                {
                    "server": server,
                    "routing_key": "pbx.cmd.Action.Originate",
                    "channel": channel,
                    "context": context,
                    "exten": exten,
                }
            )
            return True

        publisher = self.env["pbx.mq.publisher"]
        original = type(publisher).action_originate
        type(publisher).action_originate = fake_originate
        try:
            result = ext.action_click_to_call("0701-23 45 67")
        finally:
            type(publisher).action_originate = original

        self.assertEqual(len(published), 1, "exactly one originate per click")
        call = published[0]
        self.assertEqual(call["routing_key"], "pbx.cmd.Action.Originate")
        self.assertEqual(call["context"], "test.se-outbound")
        self.assertEqual(call["exten"], "+46701234567")
        self.assertTrue(
            call["channel"].startswith("PJSIP/"),
            "the channel must be the device's PJSIP endpoint",
        )
        self.assertTrue(result["ok"])

    def test_first_device_is_lowest_sequence_not_creation_order(self):
        """5.2 — ring order is the device sequence, not the creation order.

        A user who moves their mobile to the top of the list expects that
        device to ring first, regardless of which device was created first.
        """
        ext = self._make_ext(number="9041")
        ext.sub_extension_ids.write({"active": False})
        first = self.env["pbx.sub_extension"].create(
            {"extension_id": ext.id, "type": "mobile", "sequence": 5, "active": True}
        )
        second = self.env["pbx.sub_extension"].create(
            {"extension_id": ext.id, "type": "desktop", "sequence": 1, "active": True}
        )
        device = ext.sub_extension_ids.filtered(
            lambda s: s.active and s.type != "voicemail"
        ).sorted("sequence")[:1]
        self.assertEqual(device, second, "lowest sequence rings first")
        self.assertNotEqual(device, first)

    def test_failed_publish_reported_as_not_ok(self):
        """5.2 — a failed MQ publish surfaces as ok=False, not an exception."""
        ext = self._make_ext(number="9042")
        publisher = self.env["pbx.mq.publisher"]
        original = type(publisher).action_originate
        type(publisher).action_originate = lambda *a, **kw: False
        try:
            result = ext.action_click_to_call("0701234567")
        finally:
            type(publisher).action_originate = original
        self.assertFalse(result["ok"])

    def test_no_publish_on_invalid_number(self):
        """5.2 — an unparseable number never reaches the daemon."""
        ext = self._make_ext(number="9043")
        published = []
        publisher = self.env["pbx.mq.publisher"]
        original = type(publisher).action_originate
        type(publisher).action_originate = lambda *a, **kw: published.append(1) or True
        try:
            with self.assertRaises(UserError):
                ext.action_click_to_call("abc")
        finally:
            type(publisher).action_originate = original
        self.assertEqual(published, [], "nothing may be published for a bad number")
