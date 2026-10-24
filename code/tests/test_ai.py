import io
import json
import os
import unittest
from unittest.mock import patch

from ghosttrace.ai import review
from ghosttrace.io import InputError


class ReviewTests(unittest.TestCase):
    def result(self):
        return {"case_id": "test", "status": "REVIEW_REQUIRED", "request_source": "deletion_requests.csv:2",
                "identifiers": [{"type": "email", "value": "private@example.invalid"}], "timeline": [],
                "findings": [], "proof": [], "remediation": [], "recreation_paths": [], "gaps": ["Missing rules"]}

    def response(self, source):
        content = {"summary": "More evidence needed", "checks": [{"observation": "Request needs policy", "source": source}]}
        return io.BytesIO(json.dumps({"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": json.dumps(content)}]}]}).encode())

    def test_missing_key_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(InputError):
            review(self.result(), "explicit-model")

    def test_review_is_advisory_and_minimizes_payload(self):
        original = self.result()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-local-test-key"}), patch(
                "urllib.request.urlopen", return_value=self.response("deletion_requests.csv:2")) as call:
            result = review(original, "explicit-model")
        self.assertTrue(result["advisory_only"])
        self.assertEqual(original["status"], "REVIEW_REQUIRED")
        payload = json.loads(call.call_args.args[0].data)
        self.assertNotIn("private@example.invalid", payload["input"])
        self.assertFalse(payload["store"])

    def test_hallucinated_reference_is_rejected(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-local-test-key"}), patch(
                "urllib.request.urlopen", return_value=self.response("invented.csv:88")), self.assertRaises(InputError):
            review(self.result(), "explicit-model")

    def test_refusal_does_not_become_success(self):
        refusal = io.BytesIO(json.dumps({"status": "completed", "output": [{"content": [
            {"type": "refusal", "refusal": "Cannot comply"}]}]}).encode())
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-local-test-key"}), patch(
                "urllib.request.urlopen", return_value=refusal), self.assertRaises(InputError):
            review(self.result(), "explicit-model")
