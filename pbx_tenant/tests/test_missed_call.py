# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""follow-me-device-control 3.4 — a call that went to voicemail because the
user was busy is logged as such, not as an answered call.

The dialplan sends a busy user straight to voicemail (2.1). Asterisk then
reports the CDR disposition, and `pbx.call.pbx_handling` is derived from it.
The mapping is the contract: a BUSY disposition must become `busy`, and a
NO ANSWER / CONGESTION / FAILED must become `missed` — both are "the person
was not reachable", and the operator panel distinguishes them.
"""

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestMissedCallDisposition(TransactionCase):
    """The CDR disposition → pbx_handling mapping."""

    def _handling(self, disposition):
        service = self.env["pbx.webhook.service"]
        return service._CDR_DISPOSITIONS.get(
            (disposition or "").strip().upper(), "missed"
        )

    def test_busy_disposition_maps_to_busy(self):
        """A busy user's call is logged as busy, not as missed."""
        self.assertEqual(self._handling("BUSY"), "busy")
        self.assertEqual(self._handling("2"), "busy")

    def test_no_answer_maps_to_missed(self):
        self.assertEqual(self._handling("NO ANSWER"), "missed")
        self.assertEqual(self._handling("0"), "missed")

    def test_congestion_and_failed_map_to_missed(self):
        """A dead trunk is a missed call, not an answered one."""
        self.assertEqual(self._handling("CONGESTION"), "missed")
        self.assertEqual(self._handling("FAILED"), "missed")
        self.assertEqual(self._handling("3"), "missed")

    def test_answered_maps_to_answered(self):
        self.assertEqual(self._handling("ANSWERED"), "answered")
        self.assertEqual(self._handling("8"), "answered")
        self.assertEqual(self._handling("10"), "answered")

    def test_unknown_disposition_defaults_to_missed(self):
        """An unrecognised disposition must never claim the call was answered."""
        self.assertEqual(self._handling("SOMETHING NEW"), "missed")
        self.assertEqual(self._handling(""), "missed")

    def test_busy_and_missed_are_distinct(self):
        """The operator panel relies on these being different values."""
        self.assertNotEqual(self._handling("BUSY"), self._handling("NO ANSWER"))
