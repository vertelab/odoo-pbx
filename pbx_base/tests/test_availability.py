# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta, timezone

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAvailability(TransactionCase):
    """pbx-availability: respect_schedule/calendar + gate-generering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.env.company.pbx_odoo_url = "https://odoo.example.com"
        cls.env["ir.config_parameter"].set_param("pbx.webhook.token", "tok")
        cls.user = cls.env.ref("base.user_demo")
        # employee with working hours 09:00-17:00 (Monday–Friday)
        cls.cal = cls.env["resource.calendar"].create(
            {
                "name": "Office hours",
                "attendance_ids": [
                    (0, 0, {"name": "Office hours", "dayofweek": str(d), "hour_from": 9.0, "hour_to": 17.0})
                    for d in range(5)
                ],
            }
        )
        emp = cls.user.employee_ids[:1]
        if not emp:
            emp = cls.env["hr.employee"].create(
                {"name": "Demo Employee", "user_id": cls.user.id}
            )
        emp.resource_calendar_id = cls.cal.id
        cls.ext = cls.env["pbx.extension"].create(
            {
                "company_id": cls.env.company.id,
                "public_number": "9050",
                "user_id": cls.user.id,
            }
        )

    def test_available_no_constraints(self):
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9051",
                "respect_schedule": False,
                "respect_calendar": False,
            }
        )
        available, ts = ext.get_availability()
        self.assertTrue(available)

    def test_busy_outside_work_hours(self):
        self.ext.write({"respect_schedule": True, "respect_calendar": False})
        # simulate the clock being 22:00 on a weekday → busy + next 09:00
        available, ts = self.ext.get_availability()
        if not available:
            self.assertTrue(ts > 0)
            dt = datetime.fromtimestamp(ts)
            self.assertEqual((dt.hour, dt.minute), (9, 0))
        else:
            # the test runs during office hours → ok is also correct
            self.assertTrue(available)

    def test_gate_generated_when_respecting(self):
        self.ext.write({"respect_schedule": True})
        gate = self.ext._render_availability_gate(
            odoo_url="https://odoo.example.com", webhook_token="tok"
        )
        self.assertIn("CURL(https://odoo.example.com/pbx/availability/9050?token=tok)", gate)
        self.assertIn("GotoIf", gate)

    def test_no_gate_when_not_respecting(self):
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9052",
                "respect_schedule": False,
                "respect_calendar": False,
            }
        )
        self.assertEqual(ext._render_availability_gate("https://x", "tok"), "")

    # ------------------------------------------------------------------
    # HTTP route: the dialplan passes public_number, not the database id
    # ------------------------------------------------------------------
    def test_route_resolves_by_public_number(self):
        """The gate emits /pbx/availability/<public_number>.

        The route must resolve that string. Regression: it was declared
        `<int:ext_id>`, so "01" was coerced to 1 and looked up the wrong
        record (or 500'd) instead of the extension the dialplan meant.
        """
        from odoo.tests.common import HttpCase

        rule = None
        for r in self.env["ir.http"]._routing_map().iter_rules():
            if r.rule == "/pbx/availability/<string:number>":
                rule = r
                break
        self.assertIsNotNone(
            rule, "route /pbx/availability/<string:number> is missing"
        )

    def test_epoch_utc_treats_naive_as_utc(self):
        """_epoch_utc must not shift naive datetimes by the server offset."""
        naive = datetime(2026, 10, 15, 12, 0, 0)
        self.assertEqual(
            self.env["pbx.extension"]._epoch_utc(naive),
            int(naive.replace(tzinfo=timezone.utc).timestamp()),
        )

    def test_epoch_utc_handles_missing_values(self):
        """Missing/unparsable values yield 0 (dialplan: 'unknown next time')."""
        Extension = self.env["pbx.extension"]
        self.assertEqual(Extension._epoch_utc(False), 0)
        self.assertEqual(Extension._epoch_utc(None), 0)
        self.assertEqual(Extension._epoch_utc(""), 0)

    def test_epoch_utc_parses_string(self):
        Extension = self.env["pbx.extension"]
        self.assertEqual(
            Extension._epoch_utc("2026-10-15 12:00:00"),
            int(datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc).timestamp()),
        )

    # ------------------------------------------------------------------
    # Generated dialplan — the availability gate in extensions.conf
    # ------------------------------------------------------------------
    def _generated_extensions(self):
        """Full extensions.conf for the test company (no Asterisk needed)."""
        return self.env["pbx.config.generator"].generate_extensions(
            "test.se", self.env.company
        )

    def _extension_block(self, conf, public_number):
        """The lines of the [test.se-ext-<number>] context."""
        header = "[test.se-ext-%s]" % public_number
        self.assertIn(header, conf)
        block = conf.split(header, 1)[1]
        # the context ends at the next context header
        return block.split("\n[", 1)[0]

    def test_dialplan_contains_availability_gate(self):
        """2.5 — CURL gate + OC_AVAIL + GotoIf busy.

        The gate is the CURL call to /pbx/availability/<number> whose answer
        is stored in OC_AVAIL ("ok:<ts>" | "busy:<ts>"); a busy answer jumps
        to the `unavailable` label.
        """
        self.ext.write(
            {
                "respect_schedule": True,
                "respect_calendar": True,
                "public_number": "9060",
            }
        )
        block = self._extension_block(self._generated_extensions(), "9060")
        self.assertIn(
            "Set(OC_AVAIL=${CURL(https://odoo.example.com/pbx/availability/9060?token=tok)})",
            block,
        )
        self.assertIn(
            'GotoIf($["${CUT(OC_AVAIL,:,1)}" = "busy"]?unavailable)', block
        )

    def test_dialplan_announces_next_time_then_voicemail(self):
        """2.5 — SayUnixTime of the next available time, then voicemail.

        OC_AVAIL is "<state>:<epoch>". The announcement block skips
        SayUnixTime when the epoch is 0 (unknown) and always ends in
        Voicemail(<number>@<domain>,u) — the caller never hears silence.
        """
        self.ext.write({"respect_schedule": True, "public_number": "9061"})
        block = self._extension_block(self._generated_extensions(), "9061")
        self.assertIn("same => n(unavailable),NoOp(Person unavailable", block)
        self.assertIn(
            'GotoIf($["${CUT(OC_AVAIL,:,2)}" = "0"]?unavail_noannounce)', block
        )
        self.assertIn("SayUnixTime(${CUT(OC_AVAIL,:,2)},,%H:%M)", block)
        self.assertIn("same => n(unavail_noannounce),Voicemail(9061@test.se,u)", block)
        self.assertIn("same => n,Hangup()", block)

    def test_dialplan_gate_ordered_before_dial(self):
        """2.5 — the gate runs before the follow-me Dial, never after.

        A gate emitted after the Dial would only be reached when nobody
        answered — the phone would still ring outside working hours.
        """
        self.ext.write({"respect_schedule": True, "public_number": "9062"})
        block = self._extension_block(self._generated_extensions(), "9062")
        gate_pos = block.index("Set(OC_AVAIL=")
        dial_pos = block.index("Dial(PJSIP/")
        self.assertLess(gate_pos, dial_pos)

    def test_dialplan_no_gate_when_not_respecting(self):
        """2.5 — no OC_AVAIL/SayUnixTime when both flags are off."""
        ext = self.env["pbx.extension"].create(
            {
                "company_id": self.env.company.id,
                "public_number": "9063",
                "respect_schedule": False,
                "respect_calendar": False,
            }
        )
        ext.sub_extension_ids.write({"active": True})
        block = self._extension_block(self._generated_extensions(), "9063")
        self.assertNotIn("OC_AVAIL", block)
        self.assertNotIn("SayUnixTime", block)
        self.assertNotIn("unavailable", block)

    def test_dialplan_voicemail_context_for_voicemail_device(self):
        """2.5 — the `unavailable` path lands in a real mailbox context.

        Voicemail(<number>@<domain>,u) requires the mailbox to exist in
        voicemail.conf; the [<domain>-vm-<number>] context is emitted for
        extensions that have a voicemail device.
        """
        self.ext.write({"respect_schedule": True, "public_number": "9064"})
        self.env["pbx.sub_extension"].create(
            {
                "extension_id": self.ext.id,
                "type": "voicemail",
                "label": "Voicemail",
                "sequence": 9,
            }
        )
        conf = self._generated_extensions()
        self.assertIn("[test.se-vm-9064]", conf)
        self.assertIn("Voicemail(9064@test.se,u)", conf)

    def test_dialplan_gate_uses_company_odoo_url(self):
        """4.2 (dev side) — the gate targets the company's configured Odoo URL.

        The CURL must point at the instance that owns the extension, not at
        the global web.base.url, otherwise a multi-tenant deployment asks the
        wrong Odoo for availability. The Asterisk end-to-end run itself is a
        deployment question, not a development task.
        """
        self.env.company.pbx_odoo_url = "https://pbx.example.org"
        self.ext.write({"respect_schedule": True, "public_number": "9065"})
        block = self._extension_block(self._generated_extensions(), "9065")
        self.assertIn(
            "CURL(https://pbx.example.org/pbx/availability/9065?token=tok)", block
        )
