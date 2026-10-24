"""Generate independent, explicitly synthetic audit fixtures. No organizer case IDs."""

from pathlib import Path

from ghosttrace.engine import REQUEST_COLUMNS, TABLES
from ghosttrace.io import write_csv


def generate(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "SYNTHETIC_DEMO").write_text("Synthetic fixtures, not organizer evidence.\n", encoding="utf-8")
    requested, observed, audit = "2026-01-01T10:00:00Z", "2026-01-02T10:00:00Z", "2026-01-03T10:00:00Z"
    specs = [("demo_resurrected", "resurrected@example.invalid", "Please delete my account.", "INCOMPLETE"),
             ("demo_clean", "clean@example.invalid", "Please delete my account.", "COMPLETE"),
             ("demo_information", "information@example.invalid", "This is an information request, not a request to erase it.", "NOT_APPLICABLE"),
             ("demo_retention", "retention@example.invalid", "Please erase my account.", "INCOMPLETE"),
             ("demo_restore", "restore@example.invalid", "Please delete my account.", "INCOMPLETE")]
    requests = [{"case_id": case, "email": email, "requested_at": requested, "reported_status": "COMPLETE",
                 "reported_at": observed, "audit_at": audit, "request_text": text} for case, email, text, _ in specs]
    write_csv(root / "deletion_requests.csv", requests, REQUEST_COLUMNS)
    rules = [{"system": "crm", "category": "profile", "action": "DELETE", "allowed_fields": [], "required_retain": "false"},
             {"system": "billing", "category": "invoice", "action": "REDACT", "allowed_fields": ["invoice_id", "amount"], "required_retain": "true"}]
    write_csv(root / "deletion_rules.csv", rules, TABLES["deletion_rules"])
    identifiers, records, processes, coverage = [], [], [], []
    for case, email, _, _ in specs:
        if case == "demo_information":
            continue
        identifiers.append({"subject_id": case, "identifier_type": "email", "identifier_value": email,
                            "verified": "true", "observed_at": requested})
        if case == "demo_resurrected":
            identifiers.append({"subject_id": case, "identifier_type": "email", "identifier_value": "old-address@example.invalid",
                                "verified": "true", "observed_at": requested})
        records.extend([
            {"record_id": f"{case}-profile", "system": "crm", "category": "profile", "subject_id": case,
             "identifiers": {}, "fields": {}, "state": "deleted", "observed_at": observed},
            {"record_id": f"{case}-invoice", "system": "billing", "category": "invoice", "subject_id": case,
             "identifiers": {}, "fields": {"invoice_id": f"{case}-invoice", "amount": 42}, "state": "present", "observed_at": observed}])
        if case == "demo_resurrected":
            records.append({"record_id": f"{case}-profile", "system": "crm", "category": "profile", "subject_id": "",
                            "identifiers": {"email": ["old-address@example.invalid"]}, "fields": {"email": "old-address@example.invalid"},
                            "state": "present", "observed_at": audit})
        if case == "demo_retention":
            records[-1]["fields"]["email"] = email
        if case == "demo_restore":
            records[-1]["state"], records[-1]["fields"] = "deleted", {}
        processes.append({"process_id": f"{case}-sync", "source_system": "billing", "target_system": "crm", "subject_id": case,
                          "active": "true", "can_recreate": "true", "blocked": "false" if case == "demo_resurrected" else "true",
                          "observed_at": observed})
        for rule in rules:
            coverage.append({"case_id": case, "system": rule["system"], "category": rule["category"],
                             "records_complete": "true", "processes_complete": "true", "identities_complete": "true", "observed_at": audit})
    for name, rows in (("identifiers", identifiers), ("records", records), ("processes", processes), ("coverage", coverage)):
        write_csv(root / f"{name}.csv", rows, TABLES[name])
    write_csv(root / "expected.csv", [{"case_id": case, "status": status} for case, _, _, status in specs], ("case_id", "status"))
    return root


if __name__ == "__main__":
    generate(Path(__file__).parent / "examples" / "demo")
    print("Synthetic demo generated in code/examples/demo")
