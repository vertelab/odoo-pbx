# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestPbxRouting(TransactionCase):
    """Routing layer tests: inbound/outbound generation, trunk endpoints,
    destination mixin, time-based routing with resource.calendar."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.ext10 = cls.env["pbx.extension"].create(
            {
                "company_id": cls.env.company.id,
                "public_number": "8010",
                "callerid_name": "Reception",
                "sub_extension_ids": [
                    (0, 0, {"number": "80101", "type": "browser", "sequence": 1}),
                    (0, 0, {"number": "80199", "type": "voicemail", "sequence": 99}),
                ],
            }
        )
        cls.ext11 = cls.env["pbx.extension"].create(
            {
                "company_id": cls.env.company.id,
                "public_number": "8011",
                "callerid_name": "Anna",
                "sub_extension_ids": [
                    (0, 0, {"number": "80111", "type": "hardware", "sequence": 1, "mac_address": "00:1B:66:DD:EE:FF"}),
                ],
            }
        )
        cls.voicemail_dest = cls.env["pbx.voicemail.destination"].create(
            {"extension_id": cls.ext10.id}
        )
        cls.custom_dest = cls.env["pbx.custom.destination"].create(
            {"name": "Blackhole", "context": "app-blackhole"}
        )
        cls.generator = cls.env["pbx.config.generator"]

    # ------------------------------------------------------------------
    # Destination mixin
    # ------------------------------------------------------------------
    def test_extension_dialplan_target(self):
        self.assertEqual(
            self.ext10.get_dialplan_target(),
            ("test.se-ext-8010", "s", "1"),
        )

    def test_voicemail_destination_target(self):
        self.assertEqual(
            self.voicemail_dest.get_dialplan_target(),
            ("test.se-vm-8010", "s", "1"),
        )

    def test_render_destination(self):
        ref = "%s,%d" % (self.voicemail_dest._name, self.voicemail_dest.id)
        self.assertEqual(
            self.env["pbx.destination.mixin"]._render_destination(ref),
            "Goto(test.se-vm-8010,s,1)",
        )
        self.assertEqual(
            self.env["pbx.destination.mixin"]._render_destination(False),
            "Hangup()",
        )

    # ------------------------------------------------------------------
    # Trunk generation
    # ------------------------------------------------------------------
    def test_trunk_endpoints_generated(self):
        trunk = self.env["pbx.trunk"].create(
            {
                "company_id": self.env.company.id,
                "name": "Telia",
                "host": "sip.telia.se",
                "username": "user1",
                "secret": "secret1",
                "callerid": "08-123456",
            }
        )
        pjsip = self.generator.generate_pjsip("test.se", self.env.company.id)
        self.assertIn("[test.se-trunk-telia]", pjsip)
        self.assertIn("context = test.se-from-trunk", pjsip)
        self.assertIn("contact = sip:sip.telia.se:5060", pjsip)
        self.assertIn("username = user1", pjsip)
        self.assertIn("password = secret1", pjsip)
        # extensions are still generated
        self.assertIn("[u80101]", pjsip)

    # ------------------------------------------------------------------
    # Inbound routes
    # ------------------------------------------------------------------
    def _inbound(self, did="", cid="", sequence=10, destination=None):
        return self.env["pbx.inbound_route"].create(
            {
                "company_id": self.env.company.id,
                "did": did,
                "cid": cid,
                "sequence": sequence,
                "destination_id": destination
                or "%s,%d" % (self.voicemail_dest._name, self.voicemail_dest.id),
            }
        )

    def test_inbound_route_ordering(self):
        self._inbound(did="08-123456", sequence=10)
        self._inbound(sequence=99)  # catch-all
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        self.assertIn("exten => 08-123456,1,NoOp", dialplan)
        self.assertIn("exten => s,1,NoOp(Inbound:", dialplan)
        # specific DID emitted before the catch-all
        self.assertLess(
            dialplan.index("exten => 08-123456,1,"),
            dialplan.index("exten => s,1,NoOp(Inbound:"),
        )
        # DID route renders its destination
        self.assertIn("Goto(test.se-vm-8010,s,1)", dialplan)

    def test_inbound_did_cid(self):
        self._inbound(did="08-123456", cid="070-5551234")
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        self.assertIn("exten => 08-123456/070-5551234,1,NoOp", dialplan)
        self.assertIn("Set(__FROM_DID=08-123456)", dialplan)

    def test_inbound_cid_only(self):
        self._inbound(cid="070-5551234")
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        self.assertIn("exten => _.,1,NoOp", dialplan)
        self.assertIn('GotoIf($["${CALLERID(num)}" = "070-5551234"]?', dialplan)

    def test_inbound_catch_all_fallback(self):
        # no catch-all route -> ss-noservice fallback for unmatched DIDs
        self._inbound(did="08-123456")
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        self.assertIn("exten => _.,1,NoOp(No DID or CID match)", dialplan)
        self.assertIn("Playback(ss-noservice)", dialplan)

    # ------------------------------------------------------------------
    # Outbound routes
    # ------------------------------------------------------------------
    def _trunk(self, name="Telia"):
        return self.env["pbx.trunk"].create(
            {
                "company_id": self.env.company.id,
                "name": name,
                "host": "sip.%s.se" % name.lower(),
            }
        )

    def _outbound(self, trunks, pattern="_0.", sequence=10, failover=None,
                  time_source="none", calendar=None):
        return self.env["pbx.outbound_route"].create(
            {
                "company_id": self.env.company.id,
                "name": "Route %s" % sequence,
                "pattern": pattern,
                "sequence": sequence,
                "time_source": time_source,
                "calendar_id": calendar and calendar.id or False,
                "failover_destination_id": failover or False,
                "trunk_ids": [
                    (0, 0, {"trunk_id": t.id, "sequence": 10 * (i + 1), "continue_": True})
                    for i, t in enumerate(trunks)
                ],
            }
        )

    def test_outbound_failover_chain(self):
        t1 = self._trunk("Telia")
        t2 = self._trunk("Fortnox")
        self._outbound([t1, t2])
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        self.assertIn("[test.se-outbound]", dialplan)
        self.assertIn("Dial(PJSIP/${DIAL_NUMBER}@test.se-trunk-telia,60,tT)", dialplan)
        self.assertIn("Dial(PJSIP/${DIAL_NUMBER}@test.se-trunk-fortnox,60,tT)", dialplan)
        self.assertIn('GotoIf($["${DIALSTATUS}" = "ANSWER"]?', dialplan)
        # internal "0" dialing reaches the outbound context
        self.assertIn("exten => _0.,1,Goto(test.se-outbound,${EXTEN},1)", dialplan)
        self.assertIn("exten => _+.,1,Goto(test.se-outbound,${EXTEN},1)", dialplan)

    def test_outbound_strip_prepend(self):
        trunk = self._trunk()
        route = self.env["pbx.outbound_route"].create(
            {
                "company_id": self.env.company.id,
                "name": "International",
                "pattern": "_00.",
                "sequence": 20,
                "strip_digits": 2,
                "prepend_digits": "+46",
                "trunk_ids": [(0, 0, {"trunk_id": trunk.id})],
            }
        )
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        self.assertIn("Set(DIAL_NUMBER=+46${EXTEN:2})", dialplan)

    def test_outbound_failover_destination(self):
        trunk = self._trunk()
        self._outbound(
            [trunk],
            failover="%s,%d" % (self.voicemail_dest._name, self.voicemail_dest.id),
        )
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        self.assertIn("[test.se-outbound-failover]", dialplan)
        self.assertIn("Goto(test.se-vm-8010,s,1)", dialplan)

    def test_outbound_time_calendar(self):
        """resource.calendar attendance + leave gate the route."""
        trunk = self._trunk()
        cal = self.env["resource.calendar"].create(
            {
                "name": "Kontorstid",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Mon-Fri",
                            "dayofweek": "1",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                            "day_period": "morning",
                        },
                    )
                ],
                "leave_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Juldagen",
                            "date_from": datetime(2026, 12, 25, 0, 0),
                            "date_to": datetime(2026, 12, 25, 23, 59),
                        },
                    )
                ],
            }
        )
        self._outbound([trunk], time_source="calendar", calendar=cal)
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        # attendance gate
        self.assertIn("GotoIfTime(08:00-17:00,tue,*,*?", dialplan)
        # leave day skips the route
        self.assertIn("GotoIfTime(00:00-23:59,25,12,2026?", dialplan)

    # ------------------------------------------------------------------
    # Internal dialing + app contexts
    # ------------------------------------------------------------------
    def test_internal_dialing_and_app_contexts(self):
        dialplan = self.generator.generate_extensions("test.se", self.env.company.id)
        # extension reachable internally -> ring-group app context
        self.assertIn("exten => 8010,1,Goto(test.se-ext-8010,s,1)", dialplan)
        self.assertIn("[test.se-ext-8010]", dialplan)
        self.assertIn("Dial(PJSIP/u80101,10)", dialplan)
        # voicemail app context exists because ext 10 has a voicemail sub
        self.assertIn("[test.se-vm-8010]", dialplan)
        self.assertIn("Voicemail(8010@test.se,u)", dialplan)

    def test_destination_custom(self):
        ref = "%s,%d" % (self.custom_dest._name, self.custom_dest.id)
        self.assertEqual(
            self.env["pbx.destination.mixin"]._render_destination(ref),
            "Goto(app-blackhole,s,1)",
        )

    def test_time_condition_holidays(self):
        """pbx.time_condition tests live in pbx_time_condition/tests/
        (the model is not loaded during pbx_base at_install tests)."""
        self.skipTest("Covered by pbx_time_condition/tests/test_time_condition.py")
