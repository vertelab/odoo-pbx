# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestPbxTimeCondition(TransactionCase):
    """Time condition generation incl. resource.calendar holidays."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = cls.env["pbx.server"].create(
            {"name": "Test", "host": "127.0.0.1", "config_path": "/tmp/pbx-test"}
        )
        cls.tenant = cls.env["pbx.tenant"].create(
            {"name": "Test AB", "domain": "test.se", "server_id": cls.server.id}
        )
        cls.vm_dest = cls.env["pbx.voicemail.destination"].create(
            {
                "tenant_id": cls.tenant.id,
                "extension_id": cls.env["pbx.extension"]
                .create(
                    {
                        "tenant_id": cls.tenant.id,
                        "public_number": "10",
                        "sub_extension_ids": [
                            (0, 0, {"number": "101", "type": "browser"}),
                            (0, 0, {"number": "199", "type": "voicemail"}),
                        ],
                    }
                )
                .id,
            }
        )
        cls.custom_dest = cls.env["pbx.custom.destination"].create(
            {"tenant_id": cls.tenant.id, "name": "Blackhole", "context": "app-blackhole"}
        )

    def test_holidays_render_as_no_match_days(self):
        """holidays_calendar_id leaves render as no-match days."""
        tc = self.env["pbx.time_condition"].create(
            {
                "tenant_id": self.tenant.id,
                "name": "Kontorstid",
                "start_time": 8.0,
                "end_time": 17.0,
                "days_of_week": "mon-fri",
                "destination_match_id": "%s,%d"
                % (self.vm_dest._name, self.vm_dest.id),
                "destination_nomatch_id": "%s,%d"
                % (self.custom_dest._name, self.custom_dest.id),
                "holidays_calendar_id": self.env["resource.calendar"]
                .create(
                    {
                        "name": "Helgdagar",
                        "leave_ids": [
                            (
                                0,
                                0,
                                {
                                    "name": "Nyårsdagen",
                                    "date_from": datetime(2026, 1, 1, 0, 0),
                                    "date_to": datetime(2026, 1, 1, 23, 59),
                                },
                            )
                        ],
                    }
                )
                .id,
            }
        )
        conf = tc._generate_time_conf(tc)
        self.assertIn("GotoIfTime(08:00-17:00,mon-fri,*,*?in-range)", conf)
        self.assertIn("GotoIfTime(00:00-23:59,1,1,2026?no-match)", conf)
        self.assertIn("Goto(test.se-vm-10,s,1)", conf)
        self.assertIn("Goto(app-blackhole,s,1)", conf)

    def test_target_triple(self):
        tc = self.env["pbx.time_condition"].create(
            {
                "tenant_id": self.tenant.id,
                "name": "Office Hours",
                "destination_match_id": "%s,%d"
                % (self.vm_dest._name, self.vm_dest.id),
                "destination_nomatch_id": "%s,%d"
                % (self.custom_dest._name, self.custom_dest.id),
            }
        )
        self.assertEqual(tc.get_dialplan_target(), ("test.se-time-office-hours", "s", "1"))
