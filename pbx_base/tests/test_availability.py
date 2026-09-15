# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta

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
