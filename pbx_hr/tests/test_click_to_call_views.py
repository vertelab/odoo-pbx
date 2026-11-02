# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestHrClickToCallViews(TransactionCase):
    """pbx-click-to-call 4.2 — the ring icon is on the employee phone fields."""

    def test_employee_phone_fields_have_call_widget(self):
        views = self.env["hr.employee"].get_views([(False, "form")])
        arch = views["views"]["form"]["arch"]
        for field in ("work_phone", "mobile_phone"):
            self.assertIn(
                'widget="pbx_call"',
                arch,
                "hr.employee.%s must carry the click-to-call widget" % field,
            )
