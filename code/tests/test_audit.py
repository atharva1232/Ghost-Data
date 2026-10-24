import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from make_demo import generate
from ghosttrace.engine import Corpus, audit, audit_all, intent
from ghosttrace.io import InputError
from ghosttrace.report import render_report
from ghosttrace.__main__ import main


class AuditTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[2] / "artifacts" / "test-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        assert Path(self.tmp.name).resolve().is_relative_to(temp_root.resolve())
        self.addCleanup(self.tmp.cleanup)
        self.root = generate(Path(self.tmp.name) / "demo")
        self.corpus = Corpus(self.root)

    def request(self, case="demo_clean"):
        return next(r for r in self.corpus.requests if r["case_id"] == case)

    def run_case(self, case="demo_clean"):
        return audit(self.corpus, self.request(case))

    def test_demo_labels_are_separate_from_predictions(self):
        (self.root / "expected.csv").unlink()
        actual = {r["case_id"]: r["status"] for r in audit_all(Corpus(self.root))}
        self.assertEqual(actual, {"demo_clean": "COMPLETE", "demo_information": "NOT_APPLICABLE",
            "demo_resurrected": "INCOMPLETE", "demo_retention": "INCOMPLETE", "demo_restore": "INCOMPLETE"})

    def test_reported_status_cannot_change_verdict(self):
        first = self.run_case()["status"]
        self.request()["reported_status"] = "NOT_STARTED"
        self.assertEqual(first, self.run_case()["status"])

    def test_requests_only_abstain(self):
        self.corpus.tables = {k: [] for k in self.corpus.tables}
        self.assertEqual(self.run_case()["status"], "REVIEW_REQUIRED")

    def test_historical_alias_finds_resurrected_copy(self):
        result = self.run_case("demo_resurrected")
        self.assertTrue(result["findings"])
        self.assertIn("old-address@example.invalid", [r["value"] for r in result["identifiers"]])
        self.assertTrue(result["remediation"][0]["action"].startswith("Block recreation"))

    def test_retention_exposure_is_not_excused(self):
        result = self.run_case("demo_retention")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("email", result["findings"][0]["forbidden_fields"])

    def test_missing_required_record_is_incomplete(self):
        result = self.run_case("demo_restore")
        self.assertEqual(result["findings"][0]["type"], "MISSING_REQUIRED_RETENTION")

    def test_future_deletion_does_not_hide_present_copy(self):
        source = next(r for r in self.corpus.tables["records"] if r["record_id"] == "demo_retention-invoice")
        future = {**source, "state": "deleted", "fields": {}, "observed_at": "2027-01-01T00:00:00Z"}
        self.corpus.tables["records"].append(future)
        self.assertEqual(self.run_case("demo_retention")["status"], "INCOMPLETE")

    def test_stale_coverage_cannot_prove_complete(self):
        for row in self.corpus.tables["coverage"]:
            row["observed_at"] = "2026-01-02T10:00:00Z"
        self.assertEqual(self.run_case()["status"], "REVIEW_REQUIRED")

    def test_unverified_alias_cannot_join_people(self):
        for row in self.corpus.tables["identifiers"]:
            if row["subject_id"] == "demo_clean":
                row["verified"] = False
        self.assertEqual(self.run_case()["status"], "REVIEW_REQUIRED")

    def test_ambiguous_subject_link_abstains(self):
        row = next(r for r in self.corpus.tables["identifiers"] if r["subject_id"] == "demo_clean")
        self.corpus.tables["identifiers"].append({**row, "subject_id": "different-person"})
        self.assertEqual(self.run_case()["status"], "REVIEW_REQUIRED")

    def test_active_global_restore_is_detected(self):
        self.corpus.tables["processes"].append({"process_id": "restore-all", "subject_id": "*", "source_system": "archive",
            "target_system": "crm", "active": True, "can_recreate": True, "blocked": False,
            "observed_at": "2026-01-02T10:00:00Z", "_ref": "processes.csv:999"})
        self.assertEqual(self.run_case()["status"], "INCOMPLETE")

    def test_order_and_unrelated_records_do_not_change_results(self):
        before = self.run_case()
        for table in self.corpus.tables.values():
            table.reverse()
        self.assertEqual(before, self.run_case())

    def test_casefold_email_preserves_other_identifier_types(self):
        self.request()["email"] = self.request()["email"].upper()
        self.assertEqual(self.run_case()["status"], "COMPLETE")

    def test_unknown_policy_blocks_completion(self):
        row = next(r for r in self.corpus.tables["records"] if r["subject_id"] == "demo_clean")
        row["category"] = "unknown"
        self.assertEqual(self.run_case()["status"], "REVIEW_REQUIRED")

    def test_media_is_not_silently_ignored(self):
        (self.root / "media").mkdir()
        (self.root / "media" / "scan.png").write_bytes(b"placeholder")
        self.corpus = Corpus(self.root)
        self.assertEqual(self.run_case()["status"], "REVIEW_REQUIRED")

    def test_malformed_boolean_rejected(self):
        path = self.root / "coverage.csv"
        path.write_text(path.read_text().replace("true", "maybe", 1))
        with self.assertRaises(InputError):
            Corpus(self.root)

    def test_duplicate_request_rejected(self):
        path = self.root / "deletion_requests.csv"
        lines = path.read_text().splitlines()
        path.write_text("\n".join(lines + [lines[1]]))
        with self.assertRaises(InputError):
            Corpus(self.root)

    def test_html_cannot_execute_evidence(self):
        result = self.run_case()
        result["gaps"].append('</script><script>alert("evidence")</script>')
        report = Path(self.tmp.name) / "report.html"
        render_report(report, [result], {"counts": {}, "demo": True})
        self.assertNotIn('</script><script>alert', report.read_text(encoding="utf-8"))
        self.assertIn('\\u003c/script', report.read_text(encoding="utf-8"))

    def test_export_refuses_demo(self):
        path = Path(self.tmp.name) / "audit.json"
        path.write_text(json.dumps({"summary": {"demo": True}, "results": [self.run_case()]}))
        with patch("sys.argv", ["ghosttrace", "export", "--audit", str(path), "--schema", "unused"]):
            self.assertEqual(main(), 2)

    def test_export_refuses_abstention(self):
        path = Path(self.tmp.name) / "audit.json"
        path.write_text(json.dumps({"summary": {}, "results": [{"status": "REVIEW_REQUIRED"}]}))
        with patch("sys.argv", ["ghosttrace", "export", "--audit", str(path), "--schema", "unused"]):
            self.assertEqual(main(), 2)


class IntentTests(unittest.TestCase):
    def test_explicit_non_deletion(self):
        self.assertEqual(intent("I still use it, so please don't delete or change anything."), "NON_DELETION")
        self.assertEqual(intent("Please change my email. I want to continue using the service."), "NON_DELETION")

    def test_ambiguous_mixed_scope_abstains(self):
        self.assertEqual(intent("Please delete my invoices but don't delete my profile."), "UNKNOWN")

    def test_unsupported_language_abstains(self):
        self.assertEqual(intent("Solicito a exclusão permanente da conta."), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
