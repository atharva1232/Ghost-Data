"""Loopback-only local application with bounded uploads and no runtime dependencies."""

import base64
import binascii
import json
import mimetypes
import os
import re
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .engine import Corpus, TABLES
from .io import InputError, write_json
from .service import evaluate_results, perform_audit, readiness, is_official


MAX_UPLOAD = 24 * 1024 * 1024
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")
ALLOWED_FILES = {"deletion_requests.csv", "expected.csv", *(name + ".csv" for name in TABLES)}


class Store:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.static = Path(__file__).parent / "web"
        self.root = self.project / "artifacts" / "app"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def workspaces(self):
        result = []
        roots = [("demo", "Synthetic demo", self.project / "code" / "examples" / "demo"),
                 ("organizer", "October hackathon requests", self.project / "dataset")]
        for p in sorted((self.root / "uploads").glob("*")):
            if IDENTIFIER.fullmatch(p.name) and (p / "upload.json").exists():
                meta = json.loads((p / "upload.json").read_text(encoding="utf-8"))
                roots.append(("upload:" + p.name, meta["name"], p / "data"))
        for key, label, root in roots:
            if not (root / "deletion_requests.csv").is_file():
                continue
            if is_official(root):
                from .official import rows
                count = len(rows(root / 'deletion_requests.csv'))
            else:
                count = len(Corpus(root).requests)
            result.append({"id": key, "name": label, "demo": (root / "SYNTHETIC_DEMO").is_file(), "requests": count,
                           "readiness": readiness(root), "has_labels": (root / "expected.csv").is_file()})
        return result

    def workspace_path(self, key):
        if key == "demo":
            return self.project / "code" / "examples" / "demo"
        if key == "organizer":
            return self.project / "dataset"
        if isinstance(key, str) and key.startswith("upload:") and IDENTIFIER.fullmatch(key[7:]):
            root = self.root / "uploads" / key[7:]
            if (root / "upload.json").is_file():
                return root / "data"
        raise InputError("Unknown workspace")

    def run_path(self, run_id):
        if not isinstance(run_id, str) or not IDENTIFIER.fullmatch(run_id):
            raise InputError("Invalid audit run ID")
        path = self.root / "runs" / run_id
        if not (path / "run.json").is_file():
            raise InputError("Audit run not found")
        return path

    def list_runs(self):
        rows = []
        for path in (self.root / "runs").glob("*/run.json"):
            if IDENTIFIER.fullmatch(path.parent.name):
                rows.append(json.loads(path.read_text(encoding="utf-8")))
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    def run(self, workspace):
        root = self.workspace_path(workspace)
        run_id = uuid.uuid4().hex
        output = self.root / "runs" / run_id
        data = perform_audit(root, output)
        meta = {"id": run_id, "workspace": workspace, "created_at": datetime.now(timezone.utc).isoformat(),
                "summary": data["summary"]}
        write_json(output / "run.json", meta)
        return {"run": meta, **data}

    def upload(self, payload):
        files = payload.get("files")
        if not isinstance(files, list) or not files or len(files) > 60:
            raise InputError("Choose between 1 and 60 evidence files")
        decoded, names = [], set()
        for file in files:
            if not isinstance(file, dict):
                raise InputError("Malformed upload")
            name = file.get("name", "")
            # Flat CSVs or one explicit media folder; no arbitrary paths.
            is_media = bool(re.fullmatch(r"media/[A-Za-z0-9_ .-]+\.(?:txt|md|png|jpg|jpeg|webp|pdf|mp3|wav|mp4)", name, re.I))
            if name not in ALLOWED_FILES and not is_media:
                raise InputError("Unsupported filename. Use evidence CSV names from the contract, or files under media/.")
            if ".." in name or name in names:
                raise InputError("Duplicate or unsafe upload filename")
            names.add(name)
            try:
                content = base64.b64decode(file.get("content", ""), validate=True)
            except (ValueError, TypeError, binascii.Error) as exc:
                raise InputError("Invalid file encoding") from exc
            decoded.append((name, content))
        if "deletion_requests.csv" not in names:
            raise InputError("Upload must include deletion_requests.csv")
        if sum(len(content) for _, content in decoded) > 16 * 1024 * 1024:
            raise InputError("Decoded evidence exceeds 16 MB")
        key = uuid.uuid4().hex
        root = self.root / "uploads" / key
        for name, content in decoded:
            path = root / "data" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        # Invalid uploads remain quarantined without upload.json; never appear in workspaces.
        Corpus(root / "data")
        label = str(payload.get("name", "Uploaded evidence")).strip()[:80] or "Uploaded evidence"
        synthetic = payload.get("synthetic", False)
        if not isinstance(synthetic, bool):
            raise InputError("synthetic must be a boolean")
        if synthetic:
            (root / "data" / "SYNTHETIC_DEMO").write_text("User-declared synthetic workspace.\n", encoding="utf-8")
        write_json(root / "upload.json", {"name": label, "files": sorted(names), "synthetic": synthetic})
        return {"id": "upload:" + key, "name": label}


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GhostTrace/0.2"

        def log_message(self, fmt, *args):
            # Avoid logging request IDs, user data, or filenames.
            pass

        def send_bytes(self, data, content_type, status=200, filename=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, data, status=200):
            self.send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

        def check_origin(self):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in hosts:
                raise InputError("Invalid local host")
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in hosts}:
                raise InputError("Cross-origin access is not supported")

        def do_GET(self):
            try:
                self.check_origin()
                path = urlsplit(self.path).path
                if path == "/api/workspaces":
                    return self.send_json({"workspaces": store.workspaces(), "ai_available": bool(os.environ.get("OPENAI_API_KEY"))})
                if path == "/api/runs":
                    return self.send_json({"runs": store.list_runs()})
                match = re.fullmatch(r"/api/runs/([a-f0-9]{32})(/download)?", path)
                if match:
                    root = store.run_path(match[1])
                    if match[2]:
                        kind = parse_qs(urlsplit(self.path).query).get("format", ["csv"])[0]
                        names = {"csv": ("audit.csv", "text/csv; charset=utf-8"), 'submission': ('output.csv', 'text/csv; charset=utf-8'),
                                 "json": ("audit.json", "application/json"), "html": ("report.html", "text/html; charset=utf-8")}
                        if kind not in names:
                            raise InputError("Unsupported export format")
                        name, mime = names[kind]
                        return self.send_bytes((root / name).read_bytes(), mime, filename=name)
                    data = json.loads((root / "audit.json").read_text(encoding="utf-8"))
                    data["run"] = json.loads((root / "run.json").read_text(encoding="utf-8"))
                    return self.send_json(data)
                static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg"}
                if path in static:
                    file = store.static / static[path]
                    mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                    return self.send_bytes(file.read_bytes(), mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
                self.send_json({"error": "Not found"}, 404)
            except (InputError, OSError, ValueError) as exc:
                self.send_json({"error": str(exc)}, 400)

        def do_POST(self):
            try:
                self.check_origin()
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise InputError("JSON content type required")
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > MAX_UPLOAD:
                    return self.send_json({"error": "Request body must be between 1 byte and 24 MB"}, 413)
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise InputError("JSON object required")
                path = urlsplit(self.path).path
                if path == "/api/upload":
                    with store.lock:
                        return self.send_json(store.upload(payload), 201)
                if path == "/api/audit":
                    with store.lock:
                        return self.send_json(store.run(payload.get("workspace")))
                if path == "/api/evaluate":
                    root = store.run_path(payload.get("run_id"))
                    metadata = json.loads((root / "run.json").read_text(encoding="utf-8"))
                    data = json.loads((root / "audit.json").read_text(encoding="utf-8"))
                    workspace = store.workspace_path(metadata['workspace'])
                    if is_official(workspace):
                        from main import metrics
                        from .official import OfficialCorpus, rows
                        corpus = OfficialCorpus(workspace, store.root / 'extractions')
                        answers = [corpus.solve(r) for r in rows(workspace / 'sample_deletion_requests.csv')]
                        score = metrics(rows(workspace / 'sample_output.csv'), answers)
                        failures = [{'case_id': r['case_id'], 'expected': r['expected']['deletion_status'], 'predicted': r['predicted']['deletion_status']} for r in score['failures']]
                        result = {'labeled_cases': score['cases'], 'accuracy_including_abstentions': score['status_accuracy'],
                                  'prediction_coverage': 1, 'abstentions': 0, 'false_complete': sum(r['expected']['deletion_status'] != 'COMPLETE' and r['predicted']['deletion_status'] == 'COMPLETE' for r in score['failures']),
                                  'failures': failures, 'confusion_matrix': [], 'demo': False,
                                  'scope': '32 public samples; hidden-case accuracy is unknown',
                                  'step_accuracy': score['step_accuracy'], 'field_accuracy': score['field_accuracy'], 'sequence_accuracy': score['sequence_accuracy']}
                        write_json(root / 'evaluation.json', result)
                        return self.send_json(result)
                    expected = workspace / "expected.csv"
                    if not expected.exists():
                        raise InputError("No reference labels supplied. Upload expected.csv with case_id,status to evaluate.")
                    result = evaluate_results(data["results"], expected)
                    result["demo"] = data["summary"]["demo"]
                    write_json(root / "evaluation.json", result)
                    return self.send_json(result)
                if path == "/api/review":
                    from .ai import review
                    root = store.run_path(payload.get("run_id"))
                    data = json.loads((root / "audit.json").read_text(encoding="utf-8"))
                    case = next((r for r in data["results"] if r["case_id"] == payload.get("case_id")), None)
                    model = payload.get("model", "")
                    if not case or not isinstance(model, str) or not model.strip():
                        raise InputError("Choose a case and enter an explicit model ID")
                    # Advisory review is returned separately; deterministic verdicts stay immutable.
                    return self.send_json(review(case, model.strip()))
                self.send_json({"error": "Not found"}, 404)
            except (InputError, OSError, ValueError, KeyError, TypeError) as exc:
                self.send_json({"error": str(exc)}, 400)

    return Handler


def serve(project=None, port=8765, open_browser=False):
    project = Path(project) if project else Path(__file__).resolve().parents[2]
    store = Store(project)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store))
    server.daemon_threads = True
    server.timeout = 1
    print(f"GhostTrace is running at http://127.0.0.1:{server.server_port}", flush=True)
    print("Press Ctrl+C to stop. Local files stay in artifacts/app.", flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{server.server_port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
