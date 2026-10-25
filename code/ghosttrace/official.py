"""Participant-facing corpus investigation and exact competition serialization.

No expected outputs, organizer internals, case IDs, or case-number patterns are
consulted during inference. Business schemas and observable event semantics are
normalized here; policy actions are read from deletion_rules.csv.
"""
import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .io import InputError, timestamp
from .media import extract


COLLECTIONS = {
    'customer_profiles': ('account_service', 'USER_PROFILE'),
    'customer_search_documents': ('search_service', 'SEARCH_INDEX_ENTRY'),
    'customer_analytics_reports': ('analytics_platform', 'ANALYTICS_PROFILE'),
    'connector_configurations': ('integration_service', 'DATA_FLOW'),
    'backup_catalog': ('backup_service', 'BACKUP_ARCHIVE'),
    'customer_export_jobs': ('export_service', 'USER_EXPORT'),
    'support_conversations': ('support_platform', 'SUPPORT_MESSAGE'),
    'ticket_attachments': ('support_platform', 'SUPPORT_ATTACHMENT'),
    'security_audit_events': ('security_service', 'SECURITY_AUDIT_LOG'),
    'retained_order_records': ('finance_service', 'LEGAL_HOLD_RECORD'),
    'deleted_customer_references': ('identity_service', 'ACCOUNT_TOMBSTONE'),
}
PREFIX = {
    'account': ('account_service', 'USER_PROFILE'), 'search': ('search_service', 'SEARCH_INDEX_ENTRY'),
    'analytics': ('analytics_platform', 'ANALYTICS_PROFILE'), 'data_flow': ('integration_service', 'DATA_FLOW'),
    'backup': ('backup_service', 'BACKUP_ARCHIVE'), 'export': ('export_service', 'USER_EXPORT'),
    'support': ('support_platform', 'SUPPORT_MESSAGE'), 'audit_record': ('security_service', 'SECURITY_AUDIT_LOG'),
    'marketing': ('marketing_platform', 'MARKETING_PROFILE'), 'object': ('object_storage', 'SUPPORT_ATTACHMENT'),
    'tombstone': ('identity_service', 'ACCOUNT_TOMBSTONE'), 'cache': ('cache_service', 'CACHE_ENTRY'),
    'email_log': ('notification_service', 'EMAIL_DELIVERY_LOG'), 'legal': ('legal_service', 'LEGAL_HOLD_RECORD'),
}
OPERATIONS = {
    'FINDING': ['REPORT_REMAINING_RECORD', 'REPORT_EXPOSED_PII', 'REPORT_ACTIVE_DATA_FLOW', 'REPORT_RESTORE_RISK'],
    'REMEDIATION': ['DISABLE_DATA_FLOW', 'BLOCK_RESTORE', 'DELETE_RECORD', 'REDACT_RECORD', 'ANONYMIZE_RECORD'],
    'VERIFICATION': ['VERIFY_RECORD_ABSENT', 'VERIFY_RECORD_PRESENT', 'VERIFY_RECORD_REDACTED', 'VERIFY_RECORD_ANONYMIZED', 'VERIFY_DATA_FLOW_DISABLED', 'VERIFY_RESTORE_BLOCKED'],
}
STATES = {'REPORT_REMAINING_RECORD': 'PRESENT', 'REPORT_EXPOSED_PII': 'PRESENT',
    'REPORT_ACTIVE_DATA_FLOW': 'ACTIVE', 'REPORT_RESTORE_RISK': 'ACTIVE',
    'DISABLE_DATA_FLOW': 'DISABLED', 'BLOCK_RESTORE': 'BLOCKED', 'DELETE_RECORD': 'ABSENT',
    'REDACT_RECORD': 'REDACTED', 'ANONYMIZE_RECORD': 'ANONYMIZED', 'VERIFY_RECORD_ABSENT': 'ABSENT',
    'VERIFY_RECORD_PRESENT': 'PRESENT', 'VERIFY_RECORD_REDACTED': 'REDACTED',
    'VERIFY_RECORD_ANONYMIZED': 'ANONYMIZED', 'VERIFY_DATA_FLOW_DISABLED': 'DISABLED', 'VERIFY_RESTORE_BLOCKED': 'BLOCKED'}
DIRECT = {'email', 'phone', 'email_hash', 'full_name', 'name', 'display_name', 'customer_email',
          'owner_email', 'owner_phone', 'requester_name', 'requester_email', 'requester_phone', 'correlation_key'}
STABLE = {'user_id', 'customer_reference', 'subject_reference', 'subject_ref'}
EMAIL = re.compile(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}')
RESOURCE = re.compile(r'\b(?:account|search|analytics|data_flow|backup|export|support|audit_record|marketing|object|tombstone|cache|email_log|legal)_\d+\b', re.I)
KV = re.compile(r'([\w]+)=("(?:[^"\\]|\\.)*"|[^\s]+)')


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def normal(value):
    return unicodedata.normalize('NFKC', str(value)).strip().casefold()


def folded(value):
    return unicodedata.normalize('NFC', ''.join(c for c in unicodedata.normalize('NFKD', normal(value)) if not unicodedata.combining(c)))


def tokens(value):
    text = normal(json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)
    result = set(EMAIL.findall(text)) | set(re.findall(r'\buser_\d+\b|\b[0-9a-f]{64}\b', text))
    return result


def values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield from values(item)
            else:
                yield key, item
    elif isinstance(value, list):
        for item in value:
            yield from values(item)


def is_value(value):
    return value is not None and normal(value) not in ('', 'null', 'none', '[redacted]', 'redacted', 'anonymous', 'anonymized', 'n/a')


def pii(payload, allow_stable=False):
    for key, value in values(payload):
        if not is_value(value):
            continue
        if key in DIRECT or (key in STABLE and not allow_stable):
            return True
        if key in ('message_text', 'message_excerpt', 'body', 'text') and (EMAIL.search(str(value)) or re.search(r'\+\d[\d ()-]{7,}', str(value))):
            return True
    return False


def category(resource):
    return next((pair for prefix, pair in PREFIX.items() if resource.startswith(prefix + '_')), ('', ''))


def request_intent(text):
    """Multilingual explicit authorization, with conservative non-deletion negation."""
    text = folded(text).replace('’', "'")
    negative = [r"not (?:a |asking (?:you )?to )?(?:request (?:to|for) )?(?:delete|erase|deletion|erasure)",
        r"(?:do not|don't|dont|no need to) (?:delete|erase|close|remove)",
        r'leave .{0,80}(?:in place|unchanged|active)', r'(?:keep|continue) using (?:the|this|your) (?:service|account)',
        r'(?:not|without) .{0,20}(?:delet|eras)', r'(?:stop|unsubscribe).{0,50}(?:marketing|promotional|emails)',
        r'(?:copy|export|access).{0,50}(?:information|data).{0,60}(?:still|keep)',
        r'ne .{0,30}(?:supprimez|supprimer).{0,15}pas', r'no .{0,20}(?:eliminen|eliminar|borren)']
    if any(re.search(pattern, text) for pattern in negative):
        return False
    positive = [r'\b(?:delete|deleted|deleting|deletion|erase|erased|erasure)\b',
        r'\bremove (?:that search result|records|the rest|my name)',
        r'(?:profile|account) (?:is|was) gone', r'(?:account|analytics).{0,70}(?:been removed|cannot identify)',
        r'(?:close|closed|remove|removed).{0,45}(?:account|profile|personal)',
        r'(?:account|profile).{0,45}(?:closed|removed)',
        r'\b(?:eliminacion|eliminar|elimine|eliminado|borrar|supprimer|suppression|effacer|exclusao|excluir|apagar|loschen|loschung)\b',
        r'削除|消去|삭제|删除|刪除|حذف|मिटा']
    return any(re.search(pattern, text) for pattern in positive)


def decode_log(line):
    """Normalize business events wrapped by JSON, cloud, pipe, app and syslog transports."""
    def key_values(text):
        return {m[1]: json.loads(m[2]) if m[2].startswith('"') else m[2] for m in KV.finditer(text)}
    data = json.loads(line[line.index('{'):]) if '{' in line else key_values(line)
    if isinstance(data.get('message'), str):
        data.update(key_values(data['message']))
    pipe = line.split('|', 5)
    if len(pipe) == 6:
        data.update(service=pipe[2].strip(), trace_id=pipe[3].strip(), event=pipe[4].strip())
    bracket = re.match(r'^\S+\s+\[\w+\]\s+\[([^]]+)\]\s+\[([^]]+)\]\s+(\w+):', line)
    if bracket:
        data.update(service=bracket[1], trace_id=bracket[2], event=bracket[3])
    syslog = re.match(r'^\S+\s+<\d+>\d\s+\S+\s+(\S+)\s+(\S+)\s+-\s+-', line)
    if syslog:
        data.update(service=syslog[1], trace_id=syslog[2])
    if 'requestId' in data:
        data.setdefault('trace_id', data['requestId'])
        data.setdefault('service', data.get('function', ''))
    return data


@dataclass
class Observation:
    system: str
    resource: str
    category: str
    state: str
    at: str
    available: str
    evidence: str
    keys: set = field(default_factory=set)
    payload: dict = field(default_factory=dict)
    source: str = ''
    rank: int = 2


def payload_state(payload, kind):
    if kind == 'DATA_FLOW':
        return 'ACTIVE' if str(payload.get('enabled', False)).lower() in ('true', '1') else 'DISABLED'
    if kind == 'BACKUP_ARCHIVE':
        return 'ACTIVE' if str(payload.get('restore_allowed', False)).lower() in ('true', '1') else 'BLOCKED'
    if kind == 'ANALYTICS_PROFILE' or kind == 'PRODUCT_TELEMETRY':
        return 'IDENTIFIABLE' if pii(payload) else 'ANONYMIZED'
    if kind in ('SUPPORT_MESSAGE', 'ACCOUNT_TOMBSTONE', 'EMAIL_DELIVERY_LOG'):
        return 'IDENTIFIABLE' if pii(payload, allow_stable=True) else 'REDACTED'
    return 'PRESENT'


class OfficialCorpus:
    def __init__(self, dataset, cache=None):
        self.dataset = Path(dataset).resolve()
        self.cache = Path(cache) if cache else self.dataset.parent / 'artifacts' / 'extractions'
        self.identities = rows(self.dataset / 'user_identities.csv')
        self.audit_log = rows(self.dataset / 'user_audit_log.csv')
        self.activities = rows(self.dataset / 'system_activity.csv')
        self.manifest = rows(self.dataset / 'evidence_files.csv')
        self.rules = {r['data_category']: r['required_action'] for r in rows(self.dataset / 'deletion_rules.csv')}
        self.observations = []
        self.scopes = []
        self.media_facts = []
        self.extractions = []
        self.links = []
        self._load()
        self.by_resource = defaultdict(list)
        for obs in self.observations:
            self.by_resource[(obs.system, obs.resource)].append(obs)

    def add(self, system, resource, kind, state, at, manifest, keys=None, payload=None, source='', rank=2):
        if not system or not resource or not kind or not at:
            return
        state = {'FOUND': 'PRESENT', 'NOT_FOUND': 'ABSENT', 'DELETED': 'ABSENT'}.get(state, state)
        self.observations.append(Observation(system, resource, kind, state, at, manifest['captured_at'],
            manifest['file_id'], tokens(payload or {}) | set(keys or []), payload or {}, source, rank))

    def _load(self):
        for item in self.manifest:
            path = (self.dataset / item['file_path']).resolve()
            if not path.is_relative_to(self.dataset):
                raise InputError('Evidence path escapes dataset')
            suffix = path.suffix.lower()
            if suffix == '.json':
                self._json(json.loads(path.read_text(encoding='utf-8')), item)
            elif suffix == '.sql':
                self._sql(path, item)
            elif suffix == '.log':
                self._logs(path.read_text(encoding='utf-8'), item)
            elif suffix == '.txt':
                self._text(path.read_text(encoding='utf-8'), item)
            elif suffix in ('.pdf', '.png', '.jpg', '.jpeg'):
                extracted = extract(path, self.cache)
                self.extractions.append({'file_id': item['file_id'], 'method': extracted['method'], 'sha256': extracted['sha256'], 'cache_hit': extracted['cache_hit']})
                self.media_facts.append((item, extracted['text']))
            else:
                raise InputError('Unsupported evidence format: ' + suffix)
        for activity in self.activities:
            if activity['event_type'] == 'LINK_RESOURCE_IDENTITY':
                self.links.append(activity)
        self._media()

    def _record(self, record, collection, system, at, item, source=''):
        if 'record_type' in record and ('result' in record or 'state' in record):
            self.add(record.get('system', system), record.get('resource_id'), record['record_type'],
                     record.get('result', record.get('state')), record.get('recorded_at', at), item,
                     tokens(record), record, source)
            return
        resource = record.get('resource_id', '')
        default_system, kind = COLLECTIONS.get(collection, category(resource))
        system = system or default_system
        if 'tombstone' in collection:
            kind = 'ACCOUNT_TOMBSTONE'
        if resource:
            self.add(system, resource, kind, payload_state(record, kind), record.get('observed_at', at), item,
                     payload=record, source=source, rank=3)

    def _json(self, document, item):
        at = document.get('captured_at', document.get('exported_at', item['captured_at']))
        for snapshot in document.get('snapshots', []):
            for record in snapshot.get('records', []):
                self._record(record, snapshot.get('collection', ''), snapshot.get('data_store', ''), snapshot.get('captured_at', at), item)
        for record in document.get('records', []):
            self._record(record, document.get('collection', ''), '', at, item)
        for system, groups in document.get('service_exports', {}).items():
            for group, records in groups.items():
                for record in records:
                    resource = record.get('resource_id', '')
                    _, kind = category(resource)
                    observed = record.get('observed_at', at)
                    state = payload_state(record, kind)
                    if group == 'profile_lookups':
                        state = 'ABSENT' if int(record.get('status_code', 0)) == 404 else 'PRESENT'
                    elif group == 'index_queries':
                        state = 'PRESENT' if int(record.get('hits', {}).get('total', 0)) else 'ABSENT'
                    self.add(system, resource, kind, state, observed, item, payload=record, rank=3)

    def _sql(self, path, item):
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        def authorize(action, p1, p2, db, context):
            if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_PRAGMA and str(p1).lower() not in ('foreign_keys',):
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION and str(p2).lower() in ('load_extension', 'readfile', 'writefile'):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        con.set_authorizer(authorize)
        con.executescript(path.read_text(encoding='utf-8'))
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        scope = {}
        if 'snapshot_scope' in tables:
            scope = {r['origin_system']: r['captured_at'] for r in con.execute('SELECT * FROM snapshot_scope')}
        present = defaultdict(set)
        for table in tables:
            if table == 'snapshot_scope':
                continue
            safe = table.replace('"', '""')
            for row in con.execute(f'SELECT * FROM "{safe}"'):
                record = dict(row)
                if 'record_json' in record:
                    payload = json.loads(record['record_json'])
                    system, collection = record['origin_system'], record['collection_name']
                else:
                    payload = record
                    if table.startswith('customer_profiles'):
                        collection = 'customer_profiles'
                    elif table.startswith('search_documents'):
                        collection = 'customer_search_documents'
                    else:
                        collection = table
                    system = COLLECTIONS.get(collection, category(record.get('resource_id', '')))[0]
                at = record.get('updated_at', scope.get(system, item['captured_at']))
                self._record(payload, collection, system, at, item, table)
                present[system].add(record.get('resource_id', payload.get('resource_id', '')))
        # Only explicit snapshot_scope attests full system coverage for absence.
        for system in present:
            # Complete primary/replica inventories can establish absence only in
            # the subject scope represented by that capture. Dedicated account
            # primary/replica exports describe the full profile inventory.
            related = set().union(*(o.keys for o in self.observations if o.evidence == item['file_id']))
            full_profiles = any(t.startswith('customer_profiles_') for t in tables)
            self.scopes.append((system, scope.get(system, item['captured_at']), item, present[system], related, full_profiles))
        con.close()

    def _logs(self, text, item):
        traces = defaultdict(set)
        for line in text.splitlines():
            at_match = re.match(r'(\d{4}-\d\d-\d\dT[\d:]+Z)', line)
            if not at_match:
                continue
            at = at_match[1]
            try:
                data = decode_log(line)
            except (ValueError, TypeError):
                continue
            trace = data.get('trace_id', '')
            key_values = set()
            for key in ('lookup_key', 'subject_key', 'subject_ref', 'subject_reference', 'match_key', 'scan_key', 'owner_key', 'correlation_key', 'matched_value'):
                if is_value(data.get(key)):
                    key_values.add(normal(data[key]))
            if trace:
                traces[trace].update(key_values)
                key_values |= traces[trace]
            resource = data.get('resource_id', '')
            if not resource:
                continue
            system, kind = category(resource)
            event = data.get('event', '')
            state = None
            if event == 'record_lookup':
                kind = data.get('record_type', kind)
                system = data.get('system', system)
                state = data.get('result')
            elif event in ('profile_lookup_completed',):
                state = 'ABSENT' if str(data.get('rows')) == '0' or str(data.get('http_status')) == '404' else 'PRESENT'
            elif event in ('index_query_completed',):
                state = 'ABSENT' if data.get('result') in ('miss', 'not_found') or str(data.get('total_hits')) == '0' else 'PRESENT'
            elif event in ('message_pii_scan', 'analytics_identity_scan', 'contact_lookup_completed'):
                state = 'IDENTIFIABLE'
                if event == 'contact_lookup_completed':
                    kind, state = 'SECONDARY_IDENTIFIER', 'PRESENT'
            elif event == 'attachment_pii_scan':
                kind, state = 'SUPPORT_ATTACHMENT', 'PRESENT'
            elif event in ('connector_heartbeat', 'connector_config_loaded', 'connector_config_read_completed'):
                state = 'ACTIVE' if str(data.get('enabled')).lower() == 'true' else 'DISABLED'
            elif event in ('restore_candidate_evaluated', 'restore_policy_read_completed'):
                active = str(data.get('restore_allowed', data.get('eligible'))).lower() == 'true' and str(data.get('deletion_block')).lower() != 'true'
                state = 'ACTIVE' if active else 'BLOCKED'
            elif event == 'restore_authorization_completed':
                state = 'BLOCKED' if data.get('decision') == 'deny' else 'ACTIVE'
            elif event.startswith('analytics_profile_read'):
                state = 'ANONYMIZED' if str(data.get('direct_identifiers')) == '0' or not pii(data) else 'IDENTIFIABLE'
            elif event in ('message_read', 'support_ticket_read_completed'):
                state = 'IDENTIFIABLE' if pii(data, allow_stable=True) else 'REDACTED'
            elif event in ('export_download_check_completed', 'export_metadata_read_completed'):
                state = 'PRESENT' if str(data.get('available', 'true')).lower() == 'true' else 'ABSENT'
            elif event in ('audit_record_read_completed', 'audit_record_query_completed'):
                state = 'ABSENT' if str(data.get('rows')) == '0' else 'PRESENT'
            elif event == 'contact_query_completed':
                state = 'IDENTIFIABLE' if str(data.get('rows')) != '0' else 'ABSENT'
            if state:
                self.add(system, resource, kind, state, at, item, key_values, data)

    def _text(self, text, item):
        for line in text.splitlines():
            match = re.search(r'(\d{4}-\d\d-\d\dT[\d:]+Z)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(.*)', line)
            if match:
                at, system, resource, kind, state, identifier = match.groups()
                self.add(system, resource, kind, state, at, item, tokens(identifier))

    def _media(self):
        for item, raw in self.media_facts:
            # OCR normalization is semantic, not keyed to any filename or case.
            text = re.sub(r'\b(account|user|data_flow|backup|search|analytics|support|audit_record|export|marketing|tombstone)\s*_?\s*(\d+)\b', r'\1_\2', raw, flags=re.I)
            keys = tokens(text)
            resources = set(RESOURCE.findall(text))
            for link in self.links:
                alias = re.search(r'\(([^)]+)\)', link['details'])
                if alias and normal(alias[1]) in normal(text) and (not alias[1].startswith('user_') or 'reference registry' in normal(text)):
                    resources.add(link['resource_id'])
                    # Catalog identity links are provenance, not proof of PII state.
            if item['file_path'].lower().endswith('.png'):
                # Treat the main selected business object as evidence. Sidebar
                # links and unrelated rows in the same screen are not ownership.
                screen_kinds = [('customer operations', 'account_'), ('search console', 'search_'),
                    ('integration studio', 'data_flow_'), ('connector', 'data_flow_'),
                    ('product analytics', 'analytics_'), ('event timeline', 'analytics_'),
                    ('customer download center', 'export_'), ('helpdesk', 'support_'),
                    ('conversation', 'support_'), ('vault recovery manager', 'backup_'),
                    ('compliance journal', 'audit_record_'), ('signed events', 'audit_record_'),
                    ('reference registry', 'tombstone_'), ('object storage', 'object_'), ('audience operations', 'marketing_')]
                prefix = next((prefix for phrase, prefix in screen_kinds if phrase in normal(text)), None)
                if prefix:
                    candidates = [r for r in resources if r.startswith(prefix)]
                    if candidates:
                        # Selected details generally repeat the row's resource ID.
                        detail = re.search('(' + RESOURCE.pattern.replace(r'\b', '') + r')\s*\n(?:Owner|Account|event_type)\b', text, re.I)
                        target = detail[1] if detail and detail[1] in candidates else max(sorted(candidates), key=lambda r: text.count(r))
                        resources = {target}
            for resource in sorted(resources):
                system, kind = category(resource)
                if kind == 'SUPPORT_MESSAGE' and ('attachment' in folded(text) or 'correction request' in folded(text)):
                    kind = 'SUPPORT_ATTACHMENT'
                if kind == 'ACCOUNT_TOMBSTONE':
                    state = 'IDENTIFIABLE' if EMAIL.search(text) else 'REDACTED'
                elif kind == 'DATA_FLOW':
                    state = 'DISABLED' if re.search(r'\bdisabled\b', normal(text)) else 'ACTIVE'
                elif kind == 'BACKUP_ARCHIVE':
                    state = 'BLOCKED' if re.search(r'\bblocked\b|restore.{0,20}denied', normal(text)) else 'ACTIVE'
                elif kind in ('ANALYTICS_PROFILE', 'SUPPORT_MESSAGE'):
                    state = 'IDENTIFIABLE' if EMAIL.search(text) or re.search(r'\+\d[\d -]{7,}', text) else 'ANONYMIZED' if kind == 'ANALYTICS_PROFILE' else 'REDACTED'
                else:
                    state = 'PRESENT'
                self.add(system, resource, kind, state, item['captured_at'], item, keys, {'artifact_text': text}, rank=3)

    def identity(self, email, cutoff):
        profiles = defaultdict(set)
        for row in self.identities:
            profiles[row['user_id']].add(normal(row['user_id']))
            for key in ('email', 'phone', 'email_hash'):
                if is_value(row.get(key)):
                    profiles[row['user_id']].add(normal(row[key]))
        for row in self.audit_log:
            if row['event_time'] <= cutoff:
                for key in ('old_value', 'new_value'):
                    if is_value(row.get(key)):
                        profiles[row['user_id']].add(normal(row[key]))
        matched = [(user, ids) for user, ids in profiles.items() if normal(email) in ids]
        if len(matched) != 1:
            raise InputError('Request identity is unresolved or ambiguous: ' + email)
        return matched[0]

    def solve(self, request):
        if not request_intent(request['request_text']):
            return {'case_id': request['case_id'], 'deletion_status': 'NOT_APPLICABLE', 'steps_json': []}
        cutoff = request['audit_at']
        user, identifiers = self.identity(request['email'], cutoff)
        # Attribute workflow targets using contextual time windows and any
        # already grounded resource relationships. Results remain claims; these
        # links never create a state observation.
        direct_resources = {key[1] for key, obs in self.by_resource.items()
                            if any(o.at <= cutoff and o.available <= cutoff and o.keys & identifiers for o in obs)}
        primary_events = [a for a in self.activities if a['source_system'] == 'deletion_worker'
                          and a['event_type'] == 'DELETE_RECORD' and a['target_system'] == 'account_service'
                          and a['event_time'] <= cutoff]
        anchors = [a for a in primary_events if a['resource_id'] in direct_resources]
        if not anchors and not direct_resources:
            near = sorted(primary_events, key=lambda a: abs((timestamp(a['event_time']) - timestamp(request['reported_at'])).total_seconds()))
            if near and abs((timestamp(near[0]['event_time']) - timestamp(request['reported_at'])).total_seconds()) <= 900:
                anchors = near[:1]
        workflow_resources = set()
        for anchor in anchors:
            workflow_resources.add(anchor['resource_id'])
            next_primary = min((timestamp(a['event_time']) for a in primary_events if a['event_time'] > anchor['event_time']), default=timestamp(cutoff))
            for event in self.activities:
                delta = (timestamp(event['event_time']) - timestamp(anchor['event_time'])).total_seconds()
                if (0 <= delta <= 2700 and timestamp(event['event_time']) < next_primary
                        and event['source_system'] in ('deletion_worker', 'privacy_audit', 'privacy_verifier', 'policy_worker')):
                    workflow_resources.add(event['resource_id'])
        if not direct_resources and not workflow_resources:
            policy_events = [a for a in self.activities if a['source_system'] == 'deletion_worker'
                             and a['event_type'] in ('ANONYMIZE_RECORD', 'REDACT_RECORD') and a['event_time'] <= cutoff]
            near = sorted(policy_events, key=lambda a: abs((timestamp(a['event_time']) - timestamp(request['reported_at'])).total_seconds()))
            if near and abs((timestamp(near[0]['event_time']) - timestamp(request['reported_at'])).total_seconds()) <= 900:
                workflow_resources.add(near[0]['resource_id'])
        relevant = {}
        subject_ids = {r['user_id'] for r in self.identities}
        email_ids = {normal(r['email']) for r in self.identities}
        for key, observations in self.by_resource.items():
            available = [o for o in observations if o.at <= cutoff and o.available <= cutoff]
            linked = any(o.keys & identifiers for o in available) or key[1] in workflow_resources
            if linked:
                explicit_subjects = set().union(*(o.keys for o in available)) & subject_ids
                if explicit_subjects and user not in explicit_subjects and not any(o.keys & identifiers for o in available):
                    linked = False
            for link in self.links:
                if link['resource_id'] == key[1] and link['event_time'] <= cutoff and tokens(link['details']) & identifiers:
                    # A catalogue claim cannot override an artifact explicitly
                    # identifying another person.
                    direct_emails = set().union(*(o.keys for o in available)) & email_ids
                    if not direct_emails or direct_emails & identifiers:
                        linked = True
            if not linked:
                continue
            # Historic resource attribution survives irreversible anonymization.
            relevant[key] = available
        for resource in workflow_resources:
            system, kind = category(resource)
            relevant.setdefault((system, resource), [])
        selected = []
        for (system, resource), observations in relevant.items():
            observations = [o for o in observations if o.at >= request['requested_at']]
            for scope_system, at, item, present, related, full_profiles in self.scopes:
                if (scope_system == system and request['requested_at'] <= at <= cutoff and item['captured_at'] <= cutoff and resource not in present
                        and (related & identifiers or full_profiles)):
                    kind = observations[-1].category if observations else category(resource)[1]
                    observations = observations + [Observation(system, resource, kind, 'ABSENT', at, item['captured_at'], item['file_id'], identifiers, source='snapshot_scope', rank=3)]
            if observations:
                latest_at = max(o.at for o in observations)
                current = [o for o in observations if o.at == latest_at]
                # A surviving replica at the same snapshot time defeats primary absence.
                current.sort(key=lambda o: (o.state in ('PRESENT', 'IDENTIFIABLE', 'ACTIVE'), o.rank, -int(o.evidence.split('_')[-1])), reverse=True)
                selected.append(current[0])
        findings, repairs, verification = [], [], []
        for observation in selected:
            action = self.rules.get(observation.category)
            system, resource, state = observation.system, observation.resource, observation.state
            if observation.category == 'DATA_FLOW':
                bad = state == 'ACTIVE'
                find, repair, verify = 'REPORT_ACTIVE_DATA_FLOW', 'DISABLE_DATA_FLOW', 'VERIFY_DATA_FLOW_DISABLED'
            elif observation.category == 'BACKUP_ARCHIVE':
                bad = state == 'ACTIVE'
                find, repair, verify = 'REPORT_RESTORE_RISK', 'BLOCK_RESTORE', 'VERIFY_RESTORE_BLOCKED'
            elif action == 'DELETE':
                bad = state != 'ABSENT'
                find, repair, verify = 'REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT'
            elif action == 'REDACT':
                bad = state not in ('REDACTED', 'ABSENT')
                find, repair, verify = 'REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED'
            elif action == 'ANONYMIZE':
                bad = state not in ('ANONYMIZED', 'ABSENT')
                find, repair, verify = 'REPORT_EXPOSED_PII', 'ANONYMIZE_RECORD', 'VERIFY_RECORD_ANONYMIZED'
            elif action == 'RETAIN':
                bad = False
                find, repair, verify = '', '', 'VERIFY_RECORD_PRESENT'
            else:
                continue
            def step(phase, operation, evidence):
                return {'step_no': 0, 'phase': phase, 'system_id': system, 'resource_id': resource,
                        'operation': operation, 'state': STATES[operation], 'evidence_id': evidence}
            if bad:
                findings.append(step('FINDING', find, observation.evidence))
                repairs.append(step('REMEDIATION', repair, ''))
            verification.append(step('VERIFICATION', verify, observation.evidence))
        incomplete = bool(findings)
        if incomplete:
            for step in verification:
                step['evidence_id'] = ''
        steps = findings + repairs + verification
        phase_order = list(OPERATIONS)
        steps.sort(key=lambda s: (phase_order.index(s['phase']), OPERATIONS[s['phase']].index(s['operation']), s['system_id'], s['resource_id']))
        for number, step in enumerate(steps, 1):
            step['step_no'] = number
        return {'case_id': request['case_id'], 'deletion_status': 'INCOMPLETE' if incomplete else 'COMPLETE', 'steps_json': steps}


def write_output(path, answers):
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['case_id', 'deletion_status', 'steps_json'])
        writer.writeheader()
        for row in sorted(answers, key=lambda r: r['case_id']):
            writer.writerow({**row, 'steps_json': json.dumps(row['steps_json'], ensure_ascii=False, separators=(',', ':'))})
