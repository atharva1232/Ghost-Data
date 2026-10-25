"""Independent synthetic cases for the official solver, not golden-case shortcuts."""
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from ghosttrace.official import OfficialCorpus, Observation, request_intent, write_output


def corpus(observations):
    result = OfficialCorpus.__new__(OfficialCorpus)
    result.identities = [{'user_id': 'user_90001', 'email': 'demo@example.invalid', 'phone': '+1 202 555 0199', 'email_hash': 'a'*64}]
    result.audit_log = []
    result.activities, result.links, result.scopes, result.manifest = [], [], [], []
    result.rules = {'USER_PROFILE': 'DELETE', 'ACCOUNT_TOMBSTONE': 'REDACT', 'ANALYTICS_PROFILE': 'ANONYMIZE', 'SECURITY_AUDIT_LOG': 'RETAIN'}
    result.observations = observations
    result.by_resource = defaultdict(list)
    for row in observations:
        result.by_resource[(row.system, row.resource)].append(row)
    return result


def observation(system, resource, kind, state, at='2026-08-02T10:00:00Z', available=None, keys=None):
    return Observation(system, resource, kind, state, at, available or at, 'evidence_1', keys or {'user_90001'})


REQUEST = {'case_id': 'custom_a', 'email': 'demo@example.invalid', 'requested_at': '2026-08-01T10:00:00Z',
           'reported_at': '2026-08-02T10:00:00Z', 'audit_at': '2026-08-03T10:00:00Z', 'request_text': 'Please delete my account.'}


class OfficialTests(unittest.TestCase):
    def test_custom_stable_tombstone_is_preserved(self):
        c = corpus([observation('identity_service', 'tombstone_90001', 'ACCOUNT_TOMBSTONE', 'REDACTED')])
        result = c.solve(REQUEST)
        self.assertEqual(result['deletion_status'], 'COMPLETE')
        self.assertEqual([s['operation'] for s in result['steps_json']], ['VERIFY_RECORD_REDACTED'])

    def test_custom_tombstone_pii_is_redacted_not_deleted(self):
        c = corpus([observation('identity_service', 'tombstone_90001', 'ACCOUNT_TOMBSTONE', 'IDENTIFIABLE')])
        result = c.solve(REQUEST)
        self.assertEqual(result['deletion_status'], 'INCOMPLETE')
        self.assertEqual([s['operation'] for s in result['steps_json']], ['REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED'])
        self.assertEqual([s['evidence_id'] for s in result['steps_json']], ['evidence_1', '', ''])

    def test_custom_restore_is_blocked_before_profile_deletion(self):
        c = corpus([observation('account_service', 'account_90001', 'USER_PROFILE', 'PRESENT'),
                    observation('backup_service', 'backup_90001', 'BACKUP_ARCHIVE', 'ACTIVE')])
        result = c.solve(REQUEST)
        operations = [s['operation'] for s in result['steps_json']]
        self.assertLess(operations.index('BLOCK_RESTORE'), operations.index('DELETE_RECORD'))
        self.assertEqual([s['step_no'] for s in result['steps_json']], list(range(1, len(operations)+1)))

    def test_custom_future_cleanup_cannot_hide_present_profile(self):
        c = corpus([observation('account_service', 'account_90001', 'USER_PROFILE', 'PRESENT'),
                    observation('account_service', 'account_90001', 'USER_PROFILE', 'ABSENT', at='2026-08-04T10:00:00Z')])
        self.assertEqual(c.solve(REQUEST)['deletion_status'], 'INCOMPLETE')

    def test_future_capture_cannot_be_cited_for_earlier_audit(self):
        c = corpus([observation('account_service', 'account_90001', 'USER_PROFILE', 'PRESENT'),
                    observation('account_service', 'account_90001', 'USER_PROFILE', 'ABSENT', available='2026-08-04T10:00:00Z')])
        self.assertEqual(c.solve(REQUEST)['deletion_status'], 'INCOMPLETE')

    def test_old_email_is_resolved_through_audit_history(self):
        c = corpus([observation('account_service', 'account_90001', 'USER_PROFILE', 'PRESENT', keys={'old@example.invalid'})])
        c.audit_log = [{'user_id': 'user_90001', 'event_time': '2026-07-20T10:00:00Z', 'field_name': 'email', 'old_value': 'old@example.invalid', 'new_value': 'demo@example.invalid'}]
        self.assertEqual(c.solve(REQUEST)['deletion_status'], 'INCOMPLETE')

    def test_decoy_identity_is_not_joined(self):
        c = corpus([observation('account_service', 'account_90001', 'USER_PROFILE', 'ABSENT'),
                    observation('account_service', 'account_90002', 'USER_PROFILE', 'PRESENT', keys={'unrelated@example.invalid'})])
        self.assertEqual(c.solve(REQUEST)['deletion_status'], 'COMPLETE')
        self.assertNotIn('account_90002', json.dumps(c.solve(REQUEST)))

    def test_non_deletion_requires_empty_steps(self):
        c = corpus([observation('account_service', 'account_90001', 'USER_PROFILE', 'PRESENT')])
        result = c.solve({**REQUEST, 'request_text': 'Please send me my invoices. Do not delete my account.'})
        self.assertEqual(result['deletion_status'], 'NOT_APPLICABLE')
        self.assertEqual(result['steps_json'], [])

    def test_multilingual_authorization(self):
        self.assertTrue(request_intent('Solicito a exclusão permanente da conta.'))
        self.assertTrue(request_intent('Je demande la suppression définitive du compte.'))
        self.assertTrue(request_intent('アカウントの削除を依頼します。'))
        self.assertTrue(request_intent('계정의 영구 삭제를 요청합니다.'))

    def test_sql_boolean_is_interpreted(self):
        from ghosttrace.official import payload_state
        self.assertEqual(payload_state({'enabled': 1}, 'DATA_FLOW'), 'ACTIVE')
        self.assertEqual(payload_state({'restore_allowed': 0}, 'BACKUP_ARCHIVE'), 'BLOCKED')

    def test_log_transport_wrappers_preserve_event_and_trace(self):
        from ghosttrace.official import decode_log
        examples = [
            '2026-08-02T10:00:00Z | INFO | account_service | tr-1 | profile_lookup_completed | resource_id="account_9" rows="0"',
            '2026-08-02T10:00:00Z [INFO] [account_service] [tr-1] profile_lookup_completed: resource_id="account_9" rows="0"',
            '2026-08-02T10:00:00Z <14>1 host account_service tr-1 - - event="profile_lookup_completed" resource_id="account_9" rows="0"',
            '2026-08-02T10:00:00Z requestId=tr-1 function=account_service message=' + json.dumps('event="profile_lookup_completed" resource_id="account_9" rows="0"'),
        ]
        for line in examples:
            with self.subTest(line=line):
                result = decode_log(line)
                self.assertEqual(result['trace_id'], 'tr-1')
                self.assertEqual(result['event'], 'profile_lookup_completed')
                self.assertEqual(result['resource_id'], 'account_9')

    def test_official_output_sorted_and_exact_header(self):
        import io
        stream = io.StringIO()
        with patch('pathlib.Path.open') as opened:
            opened.return_value.__enter__.return_value = stream
            write_output('output.csv', [{'case_id': 'z', 'deletion_status': 'NOT_APPLICABLE', 'steps_json': []},
                                        {'case_id': 'a', 'deletion_status': 'NOT_APPLICABLE', 'steps_json': []}])
        self.assertEqual(stream.getvalue().splitlines(), ['case_id,deletion_status,steps_json', 'a,NOT_APPLICABLE,[]', 'z,NOT_APPLICABLE,[]'])
