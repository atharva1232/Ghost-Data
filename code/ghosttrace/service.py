"""Shared application operations for local UI and command-line callers."""

import collections
import json
from pathlib import Path

from . import __version__
from .engine import Corpus, TABLES, audit_all
from .io import InputError, manifest, read_csv, unique, write_csv, write_json
from .report import render_report


AUDIT_COLUMNS = ("case_id", "status", "intent", "reported_status", "identifiers", "findings", "recreation_paths", "remediation", "gaps", "proof")
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}


def readiness(root):
    root = Path(root)
    if is_official(root):
        return [{'filename': name, 'available': (root / name).is_file(), 'role': role} for name, role in [
            ('deletion_requests.csv', 'Requests to investigate'), ('user_identities.csv', 'Current identities'),
            ('user_audit_log.csv', 'Historical identifier changes'), ('deletion_rules.csv', 'Official deletion and retention policy'),
            ('system_activity.csv', 'Global operational claims and resource links'), ('evidence_files.csv', 'Local multimodal evidence manifest')]]
    return [{"filename": f"{name}.csv", "available": (root / f"{name}.csv").is_file(),
             "role": role} for name, role in [
        ("deletion_requests", "Requests to investigate"),
        ("identifiers", "Verified current and historical identities"),
        ("deletion_rules", "Treatment and retention policy"),
        ("records", "Observed state of data copies"),
        ("processes", "Sync, import and restore mechanisms"),
        ("coverage", "Evidence search completeness at audit time")]]


def is_official(root):
    return (Path(root) / 'user_identities.csv').is_file() and (Path(root) / 'evidence_files.csv').is_file()


def official_audit(root, output):
    from .official import OfficialCorpus, rows, write_output
    corpus = OfficialCorpus(root, output.parent / 'extractions')
    requests = rows(root / 'deletion_requests.csv')
    answers = [corpus.solve(request) for request in requests]
    results = []
    for request, answer in zip(requests, answers):
        steps = answer['steps_json']
        findings = [s for s in steps if s['phase'] == 'FINDING']
        repairs = [s for s in steps if s['phase'] == 'REMEDIATION']
        checks = [s for s in steps if s['phase'] == 'VERIFICATION']
        resources = {(s['system_id'], s['resource_id']) for s in steps}
        observations = [o for key in resources for o in corpus.by_resource.get(key, []) if request['requested_at'] <= o.at <= request['audit_at'] and o.available <= request['audit_at']]
        result = {'case_id': answer['case_id'], 'status': answer['deletion_status'],
            'intent': 'NON_DELETION' if answer['deletion_status'] == 'NOT_APPLICABLE' else 'DELETION',
            'reported_status': request['reported_status'], 'identifiers': [{'type': 'request_email', 'value': request['email']}],
            'findings': [{'type': s['operation'], 'description': s['operation'].replace('_', ' ').capitalize(),
                         'record_id': s['resource_id'], 'system': s['system_id'], 'source': s['evidence_id']} for s in findings],
            'recreation_paths': [{'process_id': s['resource_id'], 'from': s['system_id'], 'to': 'downstream / restore target', 'source': s['evidence_id']}
                                 for s in findings if s['operation'] in ('REPORT_ACTIVE_DATA_FLOW', 'REPORT_RESTORE_RISK')],
            'retained_records': [s['resource_id'] for s in checks if s['operation'] == 'VERIFY_RECORD_PRESENT'],
            'remediation': [{'step': i, 'action': f"{s['operation']}: {s['system_id']}/{s['resource_id']}", 'source': 'Proposed action'} for i, s in enumerate(repairs, 1)],
            'proof': [{'description': ('Required future check, not yet passed: ' if answer['deletion_status'] == 'INCOMPLETE' else '') + f"{s['operation']}: {s['resource_id']}",
                       'source': s['evidence_id'] or 'Future verification'} for s in checks],
            'gaps': [], 'timeline': [{'at': o.at, 'description': f'{o.system}/{o.resource}: {o.state}', 'source': o.evidence} for o in sorted(observations, key=lambda o: (o.at, o.resource))],
            'request_source': 'deletion_requests.csv', 'request': {'email': request['email'], 'text': request['request_text'], 'requested_at': request['requested_at'], 'audit_at': request['audit_at']},
            'official_steps': steps}
        if result['intent'] == 'DELETION':
            _, identifiers = corpus.identity(request['email'], request['audit_at'])
            result['identifiers'] = [{'type': 'resolved_identifier', 'value': v} for v in sorted(identifiers)]
        results.append(result)
    output.mkdir(parents=True, exist_ok=True)
    write_output(output / 'output.csv', answers)
    summary = {'version': __version__, 'demo': False, 'official': True, 'requests': len(results),
               'counts': dict(collections.Counter(r['status'] for r in results)), 'competition_ready': True,
               'schema_note': 'Official three-column output.csv is available; prediction accuracy is evaluated on public samples only.',
               'ai_reviews': 0, 'inputs': manifest(root), 'readiness': readiness(root),
               'findings': sum(len(r['findings']) for r in results), 'recreation_paths': sum(len(r['recreation_paths']) for r in results)}
    data = {'summary': summary, 'results': results}
    write_json(output / 'audit.json', data)
    write_json(output / 'summary.json', summary)
    write_csv(output / 'audit.csv', results, AUDIT_COLUMNS)
    render_report(output / 'report.html', results, summary)
    return data


def perform_audit(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if root == output or root in output.parents:
        raise InputError("Output directory must be outside the dataset")
    if is_official(root):
        return official_audit(root, output)
    corpus = Corpus(root)
    results = audit_all(corpus)
    for result, request in zip(results, corpus.requests):
        result["request"] = {"email": request["email"], "text": request["request_text"],
                             "requested_at": request["requested_at"], "audit_at": request["audit_at"]}
    summary = {"version": __version__, "demo": (root / "SYNTHETIC_DEMO").is_file(),
               "requests": len(results), "counts": dict(collections.Counter(r["status"] for r in results)),
               "competition_ready": False,
               "schema_note": "Internal schema. The official problem_statement.md and output schema are still needed.",
               "ai_reviews": 0, "inputs": manifest(root), "readiness": readiness(root),
               "findings": sum(len(r["findings"]) for r in results),
               "recreation_paths": sum(len(r["recreation_paths"]) for r in results)}
    data = {"summary": summary, "results": results}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "audit.json", data)
    write_json(output / "summary.json", summary)
    write_csv(output / "audit.csv", results, AUDIT_COLUMNS)
    render_report(output / "report.html", results, summary)
    return data


def evaluate_results(results, expected_path):
    rows = read_csv(expected_path, ("case_id", "status"))
    unique(rows, "case_id")
    if not rows:
        raise InputError("Reference labels are empty")
    if any(r["status"] not in STATUSES for r in rows):
        raise InputError("Reference labels must use COMPLETE, INCOMPLETE, or NOT_APPLICABLE")
    predictions = {r["case_id"]: r["status"] for r in results}
    if len(predictions) != len(results):
        raise InputError("Duplicate predicted request IDs")
    if {r["case_id"] for r in rows} - predictions.keys():
        raise InputError("Some labeled cases have no prediction")
    correct = abstentions = false_complete = 0
    matrix = collections.Counter()
    failures = []
    for row in rows:
        predicted, truth = predictions[row["case_id"]], row["status"]
        correct += predicted == truth
        abstentions += predicted == "REVIEW_REQUIRED"
        false_complete += predicted == "COMPLETE" and truth != "COMPLETE"
        matrix[(truth, predicted)] += 1
        if predicted != truth:
            failures.append({"case_id": row["case_id"], "expected": truth, "predicted": predicted})
    return {"labeled_cases": len(rows), "accuracy_including_abstentions": correct / len(rows),
            "prediction_coverage": (len(rows) - abstentions) / len(rows),
            "abstentions": abstentions, "false_complete": false_complete, "failures": failures,
            "confusion_matrix": [{"expected": a, "predicted": b, "count": n} for (a, b), n in sorted(matrix.items())],
            "note": "Status metrics only. Synthetic demo accuracy does not establish organizer performance."}
