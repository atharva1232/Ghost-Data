import base64
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from make_demo import generate
from ghosttrace.io import InputError
from ghosttrace.server import Store, make_handler
from ghosttrace.service import evaluate_results


class AppTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[2] / "artifacts" / "test-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        assert Path(self.tmp.name).resolve().is_relative_to(temp_root.resolve())
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.demo = generate(self.project / "code" / "examples" / "demo")
        self.store = Store(self.project)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        body = json.dumps(data).encode() if data is not None else None
        connection.request(method, path, body=body, headers=headers or ({"Content-Type": "application/json"} if body else {}))
        response = connection.getresponse()
        content = response.read()
        result = (response.status, content, dict(response.getheaders()))
        connection.close()
        return result

    def upload_payload(self, filename="deletion_requests.csv", content=None):
        return {"name": "Test evidence", "files": [{"name": filename,
            "content": base64.b64encode(content if content is not None else (self.demo / "deletion_requests.csv").read_bytes()).decode()}]}

    def test_static_dashboard_and_assets_are_served(self):
        for path in ("/", "/app.js", "/style.css", "/favicon.svg"):
            status, content, headers = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertGreater(len(content), 10)
            self.assertIn("Content-Security-Policy", headers)

    def test_workspaces_report_available_sources(self):
        status, content, _ = self.request("GET", "/api/workspaces")
        self.assertEqual(status, 200)
        row = json.loads(content)["workspaces"][0]
        self.assertTrue(row["demo"])
        self.assertEqual(len(row["readiness"]), 6)

    def test_audit_can_be_reopened_and_downloaded(self):
        status, content, _ = self.request("POST", "/api/audit", {"workspace": "demo"})
        self.assertEqual(status, 200)
        data = json.loads(content)
        run_id = data["run"]["id"]
        self.assertEqual(data["summary"]["requests"], 5)
        self.assertEqual(data["summary"]["findings"], 3)
        self.assertIn("text", data["results"][0]["request"])
        status, reopened, _ = self.request("GET", "/api/runs/" + run_id)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(reopened)["results"], data["results"])
        for extension in ("csv", "html", "json"):
            status, content, headers = self.request("GET", f"/api/runs/{run_id}/download?format={extension}")
            self.assertEqual(status, 200)
            self.assertIn("attachment", headers["Content-Disposition"])
            self.assertGreater(len(content), 10)

    def test_evaluate_is_separate_and_demo_is_labeled(self):
        run = self.store.run("demo")
        status, content, _ = self.request("POST", "/api/evaluate", {"run_id": run["run"]["id"]})
        result = json.loads(content)
        self.assertEqual(status, 200)
        self.assertTrue(result["demo"])
        self.assertEqual(result["false_complete"], 0)
        self.assertEqual(result["accuracy_including_abstentions"], 1)

    def test_requests_only_upload_abstains_on_deletions(self):
        status, content, _ = self.request("POST", "/api/upload", self.upload_payload())
        self.assertEqual(status, 201)
        workspace = json.loads(content)["id"]
        run = self.store.run(workspace)
        self.assertFalse(run["summary"]["demo"])
        self.assertEqual(run["summary"]["counts"].get("REVIEW_REQUIRED"), 4)
        status, content, _ = self.request("POST", "/api/evaluate", {"run_id": run["run"]["id"]})
        self.assertEqual(status, 400)
        self.assertIn("No reference labels", json.loads(content)["error"])

    def test_upload_cannot_escape_workspace(self):
        for filename in ("../outside.csv", "C:/outside.csv", "media/../../outside.txt"):
            with self.assertRaises(InputError):
                self.store.upload(self.upload_payload(filename))

    def test_invalid_upload_is_not_listed_as_workspace(self):
        status, _, _ = self.request("POST", "/api/upload", self.upload_payload(content=b"bad,headers\n1,2"))
        self.assertEqual(status, 400)
        self.assertEqual(len(self.store.workspaces()), 1)

    def test_duplicate_files_are_rejected(self):
        payload = self.upload_payload()
        payload["files"] *= 2
        with self.assertRaises(InputError):
            self.store.upload(payload)

    def test_uploaded_synthetic_evidence_remains_labeled(self):
        payload = self.upload_payload()
        payload["synthetic"] = True
        workspace = self.store.upload(payload)["id"]
        run = self.store.run(workspace)
        self.assertTrue(run["summary"]["demo"])
        self.assertTrue(next(w for w in self.store.workspaces() if w["id"] == workspace)["demo"])

    def test_non_json_and_cross_origin_requests_are_rejected(self):
        status, _, _ = self.request("POST", "/api/audit", {"workspace": "demo"}, {"Content-Type": "text/plain"})
        self.assertEqual(status, 400)
        status, _, _ = self.request("POST", "/api/audit", {"workspace": "demo"},
                                    {"Content-Type": "application/json", "Origin": "https://other.example"})
        self.assertEqual(status, 400)

    def test_invalid_host_and_arbitrary_file_reads_are_rejected(self):
        status, _, _ = self.request("GET", "/api/workspaces", headers={"Host": "other.example"})
        self.assertEqual(status, 400)
        status, _, _ = self.request("GET", "/../README.md")
        self.assertEqual(status, 404)

    def test_evaluation_labels_cannot_change_prediction(self):
        before = self.store.run("demo")["results"]
        path = self.demo / "expected.csv"
        path.write_text(path.read_text().replace("INCOMPLETE", "COMPLETE"))
        after = self.store.run("demo")["results"]
        self.assertEqual(before, after)

    def test_empty_reference_labels_are_not_scored_as_success(self):
        path = self.project / "empty.csv"
        path.write_text("case_id,status\n")
        with self.assertRaises(InputError):
            evaluate_results([], path)
