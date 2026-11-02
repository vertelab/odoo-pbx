# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""pbx-recording-transcription 7.1-7.3 — the recording/transcription contract.

7.1  tri-state resolution: extension -> queue -> global policy
7.2  the voicemail flag publishes a pbx.job.transcribe job
7.3  a successful result creates the attachment and records stt metadata

7.4 (job -> pbx-transcriber container -> result) needs the fors container and
is a deployment question; the transport is mocked here.
"""

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestRecordingModeResolution(TransactionCase):
    """7.1 — extension beats queue beats global policy."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.user = cls.env.ref("base.user_demo")
        cls.ext = cls.env["pbx.extension"].create(
            {
                "company_id": cls.env.company.id,
                "public_number": "9300",
                "user_id": cls.user.id,
            }
        )

    def test_extension_setting_wins(self):
        self.ext.write({"recording_mode": "transcribe"})
        self.assertEqual(self.ext._get_recording_mode(), "transcribe")

    def test_queue_setting_used_when_extension_empty(self):
        self.ext.write({"recording_mode": False})
        queue = self.env["pbx.queue"].create(
            {"name": "Test Queue", "extension": "7301", "recording_mode": "record"}
        )
        self.env["pbx.queue.member"].create(
            {"queue_id": queue.id, "extension_id": self.ext.id}
        )
        self.assertEqual(self.ext._get_recording_mode(), "record")

    def test_global_policy_fallback(self):
        """No extension or queue setting -> the company policy decides."""
        self.ext.write({"recording_mode": False})
        self.env["pbx.recording.policy"].create(
            {
                "scope": "company",
                "mode": "always",
                "company_id": self.env.company.id,
            }
        )
        self.assertEqual(self.ext._get_recording_mode(), "record")

    def test_no_policy_means_no_recording(self):
        """Without a policy the extension records nothing — tri-state '' ."""
        self.ext.write({"recording_mode": False})
        self.env["pbx.recording.policy"].search(
            [("company_id", "=", self.env.company.id)]
        ).unlink()
        self.assertEqual(self.ext._get_recording_mode(), "")


@tagged("-post_install", "at_install")
class TestTranscribeJobPublish(TransactionCase):
    """7.2 — the voicemail flag publishes a transcribe job with the audio."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.user = cls.env.ref("base.user_demo")
        cls.ext = cls.env["pbx.extension"].create(
            {
                "company_id": cls.env.company.id,
                "public_number": "9310",
                "user_id": cls.user.id,
            }
        )

    def _call(self, **kw):
        return self.env["pbx.call"].create(
            dict(
                {
                    "phone_number": "0701112233",
                    "direction": "inbound",
                    "pbx_handling": "voicemail",
                },
                **kw
            )
        )

    def _attachment(self, data=b"RIFF....WAVEfmt "):
        return self.env["ir.attachment"].create(
            {"name": "voicemail.wav", "datas": data, "mimetype": "audio/wav"}
        )

    def test_voicemail_flag_publishes_job(self):
        """7.2 — a transcribe-flagged mailbox publishes pbx.job.transcribe."""
        call = self._call()
        attachment = self._attachment()
        published = []

        Publisher = type(self.env["pbx.mq.publisher"])
        original = Publisher.publish
        Publisher.publish = lambda self_, key, payload: published.append(
            (key, payload)
        ) or True
        try:
            ok = self.env["pbx.ai"]._publish_transcribe_job(call, attachment)
        finally:
            Publisher.publish = original

        self.assertTrue(ok)
        self.assertEqual(len(published), 1)
        key, payload = published[0]
        self.assertEqual(key, "pbx.job.transcribe")
        self.assertEqual(payload["call_id"], call.id)
        self.assertEqual(payload["tenant"], "test.se")
        self.assertTrue(payload["audio_base64"], "the audio must travel with the job")
        self.assertEqual(payload["language"], "sv")

    def test_no_domain_means_no_job(self):
        """7.2 — without a tenant domain the job is not published."""
        self.env.company.pbx_domain = False
        try:
            ok = self.env["pbx.ai"]._publish_transcribe_job(
                self._call(), self._attachment()
            )
        finally:
            self.env.company.pbx_domain = "test.se"
        self.assertFalse(ok)

    def test_no_audio_means_no_job(self):
        """7.2 — an empty attachment must not publish an empty job."""
        empty = self.env["ir.attachment"].create(
            {"name": "empty.wav", "mimetype": "audio/wav"}
        )
        self.assertFalse(
            self.env["pbx.ai"]._publish_transcribe_job(self._call(), empty)
        )


@tagged("-post_install", "at_install")
class TestTranscribeResult(TransactionCase):
    """7.3 — a successful result creates the document and stt metadata."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"

    def _call(self, **kw):
        return self.env["pbx.call"].create(
            dict(
                {
                    "phone_number": "0701112233",
                    "direction": "inbound",
                    "pbx_handling": "voicemail",
                },
                **kw
            )
        )

    def test_result_creates_attachment_and_stt_fields(self):
        call = self._call()
        self.env["pbx.ai"].handle_transcribe_result(
            "test.se",
            {
                "call_id": call.id,
                "status": "ok",
                "transcript": "Hej, jag behover hjalp med maskinen.",
                "model": "large-v3-turbo",
                "duration_seconds": 12.5,
                "processing_seconds": 3.1,
            },
        )
        self.assertTrue(call.transcript_attachment_id.exists())
        self.assertIn("maskinen", call.transcript_text)
        self.assertEqual(call.stt_model, "large-v3-turbo")
        self.assertAlmostEqual(call.stt_duration_s, 12.5, places=1)
        self.assertAlmostEqual(call.stt_processing_s, 3.1, places=1)

    def test_error_result_creates_nothing(self):
        """7.3 — a failed transcription must not leave a half-written call."""
        call = self._call()
        self.env["pbx.ai"].handle_transcribe_result(
            "test.se",
            {"call_id": call.id, "status": "error", "error": "model crashed"},
        )
        self.assertFalse(call.transcript_attachment_id)
        self.assertFalse(call.transcript_text)

    def test_result_for_unknown_call_is_ignored(self):
        """7.3 — a stale job result must not raise."""
        self.env["pbx.ai"].handle_transcribe_result(
            "test.se",
            {"call_id": 999999, "status": "ok", "transcript": "orphan"},
        )
