"""Submission entry point: python code/main.py [predict|evaluate|validate]."""
import argparse
import collections
import json
import time
from pathlib import Path

from ghosttrace.official import OfficialCorpus, OPERATIONS, STATES, rows, write_output


ROOT = Path(__file__).resolve().parent.parent
FIELDS = ('step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id')


def metrics(expected, predicted):
    by_id = {r['case_id']: r for r in predicted}
    status = sequence = exact_steps = field_correct = total_steps = total_fields = 0
    failures = []
    for truth in expected:
        answer = by_id[truth['case_id']]
        actual_steps, expected_steps = answer['steps_json'], json.loads(truth['steps_json'])
        same_status = answer['deletion_status'] == truth['deletion_status']
        status += same_status
        sequence += actual_steps == expected_steps
        for index in range(max(len(actual_steps), len(expected_steps))):
            a = actual_steps[index] if index < len(actual_steps) else {}
            b = expected_steps[index] if index < len(expected_steps) else {}
            exact_steps += a == b
            total_steps += 1
            field_correct += sum(a.get(field) == b.get(field) and field in a and field in b for field in FIELDS)
            total_fields += len(FIELDS)
        if not same_status or actual_steps != expected_steps:
            failures.append({'case_id': truth['case_id'], 'status_correct': same_status,
                             'predicted': answer, 'expected': {**truth, 'steps_json': expected_steps}})
    return {'cases': len(expected), 'status_accuracy': status / len(expected),
            'step_accuracy': exact_steps / total_steps if total_steps else 1,
            'field_accuracy': field_correct / total_fields if total_fields else 1,
            'sequence_accuracy': sequence / len(expected), 'failures': failures}


def validate(path, requests, corpus):
    answers = rows(path)
    if not answers or list(answers[0]) != ['case_id', 'deletion_status', 'steps_json']:
        raise ValueError('Incorrect output headers')
    keys = [r['case_id'] for r in answers]
    if keys != sorted(keys) or len(set(keys)) != len(keys) or set(keys) != {r['case_id'] for r in requests}:
        raise ValueError('Output IDs must cover the request file once each and be sorted')
    evidence_times = {r['file_id']: r['captured_at'] for r in corpus.manifest}
    evidence_times.update({r['activity_id']: r['event_time'] for r in corpus.activities})
    evidence_times.update({r['audit_id']: r['event_time'] for r in corpus.audit_log})
    times = {r['case_id']: r['audit_at'] for r in requests}
    total = 0
    for answer in answers:
        steps = json.loads(answer['steps_json'])
        if answer['deletion_status'] not in ('COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE') or not isinstance(steps, list):
            raise ValueError('Invalid status or step array')
        if answer['deletion_status'] == 'NOT_APPLICABLE' and steps:
            raise ValueError('Non-deletion requests must have empty steps')
        if answer['deletion_status'] == 'COMPLETE' and not steps:
            raise ValueError('COMPLETE requires evidence-backed verification steps')
        previous = (-1, -1, '', '')
        for n, step in enumerate(steps, 1):
            if set(step) != set(FIELDS) or step['step_no'] != n or type(step['step_no']) is not int:
                raise ValueError('Invalid step keys or numbering')
            phase, operation = step['phase'], step['operation']
            if phase not in OPERATIONS or operation not in OPERATIONS[phase] or step['state'] != STATES[operation]:
                raise ValueError('Invalid operation/state')
            order = (list(OPERATIONS).index(phase), OPERATIONS[phase].index(operation), step['system_id'], step['resource_id'])
            if order < previous:
                raise ValueError('Step sequence violates the official ordering')
            previous = order
            needs_evidence = phase == 'FINDING' or answer['deletion_status'] == 'COMPLETE'
            if needs_evidence:
                evidence = step['evidence_id']
                if evidence not in evidence_times or evidence_times[evidence] > times[answer['case_id']]:
                    raise ValueError('Invalid or future evidence citation')
            elif step['evidence_id']:
                raise ValueError('Future actions must not cite evidence')
            if answer['deletion_status'] == 'COMPLETE' and phase != 'VERIFICATION':
                raise ValueError('COMPLETE can contain verification only')
            total += 1
    return {'valid': True, 'rows': len(answers), 'steps': total, 'statuses': dict(collections.Counter(r['deletion_status'] for r in answers))}


def main():
    parser = argparse.ArgumentParser(description='GhostTrace official hackathon submission pipeline')
    parser.add_argument('command', choices=('predict', 'evaluate', 'validate'), nargs='?', default='predict')
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset')
    parser.add_argument('--output', type=Path, default=ROOT / 'output.csv')
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'artifacts' / 'official')
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    corpus = OfficialCorpus(args.dataset, args.artifacts / 'extractions')
    if args.command == 'evaluate':
        requests = rows(args.dataset / 'sample_deletion_requests.csv')
        predicted = [corpus.solve(row) for row in requests]
        result = metrics(rows(args.dataset / 'sample_output.csv'), predicted)
        write_output(args.artifacts / 'sample_predictions.csv', predicted)
        (args.artifacts / 'sample_metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'failures'}, indent=2))
        print('mismatches:', [r['case_id'] for r in result['failures']])
    else:
        requests = rows(args.dataset / 'deletion_requests.csv')
        if args.command == 'predict':
            predicted = [corpus.solve(row) for row in requests]
            write_output(args.output, predicted)
        result = validate(args.output, requests, corpus)
        result['seconds'] = round(time.monotonic() - start, 3)
        result['extractions'] = corpus.extractions
        result['inference_model_calls'] = 0
        result['inference_input_tokens'] = 0
        result['inference_output_tokens'] = 0
        (args.artifacts / 'run_validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'extractions'}, indent=2))


if __name__ == '__main__':
    main()
