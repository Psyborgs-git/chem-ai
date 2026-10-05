#!/usr/bin/env python3
"""Offline validation of the Chemistry Studio SPECIFICATION pack, not the application.

Requires Python 3.10+ and jsonschema >=4.18,<5. No network calls are made.
Usage: python scripts/validate_pack.py [--report planning/pack-validation-report.json]
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    sys.exit('Missing dependency: install the dependencies in requirements-validation.txt in an isolated environment.')

ROOT = Path(__file__).resolve().parent.parent
# This tolerance checks the synthetic fixtures only. It is not a laboratory threshold.
FIXTURE_COMPOSITION_TOLERANCE = Decimal('0.000001')

def read_json(relative: str) -> Any:
    path = (ROOT / relative).resolve()
    if ROOT not in path.parents:
        raise ValueError(f'Path escapes package: {relative}')
    return json.loads(path.read_text(encoding='utf-8'))

def semantic_errors(kind: str, value: dict[str, Any]) -> list[str]:
    """Selected invariants supplement JSON Schema; not a production domain validator."""
    errors: list[str] = []
    if kind == 'FormulationRevision' and value['status'] == 'accepted':
        if value['basis'] != 'mass_fraction_as_supplied':
            errors.append('Accepted fixture needs reviewed optimizer basis')
        fractions = [Decimal(x['fraction']) for x in value['ingredients']]
        declared = Decimal(value['declared_total'])
        if any(x < 0 or x > 1 for x in fractions):
            errors.append('Fraction outside [0,1]')
        if abs(sum(fractions, Decimal(0)) - declared) > FIXTURE_COMPOSITION_TOLERANCE or abs(declared - 1) > FIXTURE_COMPOSITION_TOLERANCE:
            errors.append('Accepted composition total is invalid')
        if not value['process_revision_id'] or value['unknowns']:
            errors.append('Accepted fixture lacks reviewed process or contains unresolved fields')
        line_ids = [x['line_id'] for x in value['ingredients']]
        if len(line_ids) != len(set(line_ids)):
            errors.append('Duplicate line identity')
    if kind == 'SuccessContract' and value['status'] == 'frozen':
        for metric in value['metrics']:
            if not metric['required']:
                continue
            if not metric['method_revision_id'] or not metric['target_values']:
                errors.append(f"Frozen required metric {metric['id']} lacks method/targets")
            if metric['value_kind'] == 'numeric':
                try:
                    targets = [Decimal(x) for x in metric['target_values']]
                    if any(not x.is_finite() for x in targets):
                        errors.append('Non-finite numeric target')
                except InvalidOperation:
                    errors.append('Numeric target is not a decimal')
    if kind == 'ToolResult' and value['execution_status'] != 'succeeded' and value['acceptance'] in ('meets', 'misses'):
        errors.append('Failed run cannot determine target acceptance')
    if kind == 'ExportManifest' and value['state'] in ('approved', 'transferring', 'running', 'completed'):
        required = ['feasibility_report_id', 'provider', 'account', 'region', 'runtime_digest', 'spend_cap', 'approval_id', 'expires_at']
        if value['local_feasibility'] != 'infeasible' or any(value.get(x) is None for x in required):
            errors.append('Approved export lacks local-infeasible finding and/or recipient, budget, approval or expiry')
        if value['approved_payload_sha256'] != value['payload_sha256'] or value['block_reasons']:
            errors.append('Exact payload is not approved or blockers remain')
        if value['alias_map_location'] != 'local_only':
            errors.append('Alias mapping must remain local')
    if kind == 'DatasetSnapshot':
        included = value['record_ids']
        if len(included) != len(set(included)) or len(included) != len(value['record_hashes']):
            errors.append('Record/hash membership is inconsistent')
        excluded = {x['record_id'] for x in value['exclusions']}
        if excluded.intersection(included):
            errors.append('Included and excluded records overlap')
        group_seen: dict[str, str] = {}
        record_seen: dict[str, str] = {}
        for group in value['split_groups']:
            gid, part = group['group_id'], group['partition']
            if gid in group_seen:
                errors.append('Duplicate lineage group, including cross-partition leakage')
            group_seen[gid] = part
            for rid in group['record_ids']:
                if rid not in included:
                    errors.append('Split record is absent from the snapshot')
                if rid in record_seen:
                    errors.append('Record assigned to multiple split groups/partitions')
                record_seen[rid] = part
        if value['status'] in ('frozen', 'approved'):
            if set(record_seen) != set(included) or not value['rights_reviewed'] or not value['approval_id']:
                errors.append('Frozen dataset lacks complete approved partition/rights review')
    return errors

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    fixtures_report: list[dict[str, Any]] = []
    json_paths = sorted(ROOT.rglob('*.json'))
    for path in json_paths:
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            errors.append(f'{path.relative_to(ROOT)}: {exc}')
    schemas = {
        'planning/workplan.json': 'contracts/workplan.schema.json',
        'planning/design-map.json': 'contracts/design-map.schema.json',
        'planning/acceptance-tests.json': 'contracts/acceptance-tests.schema.json',
    }
    for filename in list(schemas.values()) + ['contracts/domain.schema.json']:
        try:
            Draft202012Validator.check_schema(read_json(filename))
        except Exception as exc:
            errors.append(f'Invalid schema {filename}: {exc}')
    for data_path, schema_path in schemas.items():
        validator = Draft202012Validator(read_json(schema_path), format_checker=FormatChecker())
        for issue in validator.iter_errors(read_json(data_path)):
            errors.append(f'{data_path}/{"/".join(map(str, issue.absolute_path))}: {issue.message}')
    work = read_json('planning/workplan.json')
    tests = read_json('planning/acceptance-tests.json')['tests']
    reqs = read_json('planning/requirements.json')['requirements']
    design = read_json('planning/design-map.json')
    sources = read_json('planning/sources.json')['sources']
    unknowns = read_json('planning/unknowns.json')['unknowns']
    integrations = read_json('planning/integrations.json')['integrations']
    collections = {'tickets': work['tickets'], 'tests': tests, 'requirements': reqs, 'phases': work['phases'], 'screens': design['screens'], 'components': design['components'], 'sources': sources, 'unknowns': unknowns, 'integrations': integrations}
    for label, values in collections.items():
        for key, count in Counter(x['id'] for x in values).items():
            if count != 1:
                errors.append(f'Duplicate {label} identifier: {key}')
    ids = {label: {x['id'] for x in values} for label, values in collections.items()}
    tickets = {x['id']: x for x in work['tickets']}
    def references(label: str, values: list[str], target: str) -> None:
        for value in values:
            if value not in ids[target]:
                errors.append(f'{label}: unknown {target} reference {value}')
    for ticket in work['tickets']:
        label = ticket['id']
        references(label, ticket['depends_on'], 'tickets')
        references(label, [ticket['phase']], 'phases')
        references(label, ticket['acceptance_test_ids'], 'tests')
        references(label, ticket['requirement_ids'], 'requirements')
        references(label, ticket['external_blocker_ids'], 'unknowns')
        for test_id in ticket['acceptance_test_ids']:
            matching = [x for x in tests if x['id'] == test_id]
            if matching and matching[0]['ticket_id'] != label:
                errors.append(f'{label}/{test_id}: asymmetric ticket/test relationship')
    memberships = [tid for phase in work['phases'] for tid in phase['ticket_ids']]
    if Counter(memberships) != Counter(ids['tickets']):
        errors.append('Phase membership is not exactly one per ticket')
    for phase in work['phases']:
        for tid in phase['ticket_ids']:
            if tid in tickets and tickets[tid]['phase'] != phase['id']:
                errors.append(f'Phase mismatch {tid}')
    visiting, visited = set(), set()
    def visit(tid: str) -> None:
        if tid in visiting:
            errors.append(f'Dependency cycle at {tid}')
            return
        if tid in visited or tid not in tickets:
            return
        visiting.add(tid)
        for dep in tickets[tid]['depends_on']:
            visit(dep)
        visiting.remove(tid)
        visited.add(tid)
    for tid in tickets:
        visit(tid)
    for test in tests:
        references(test['id'], [test['ticket_id']], 'tickets')
    for req in reqs:
        references(req['id'], req['ticket_ids'], 'tickets')
        references(req['id'], req['acceptance_test_ids'], 'tests')
    for component in design['components']:
        references(component['id'], component['composes'], 'components')
    for screen in design['screens']:
        references(screen['id'], screen['components'], 'components')
        references(screen['id'], screen['ticket_ids'], 'tickets')
        references(screen['id'], screen['acceptance_test_ids'], 'tests')
        references(screen['id'], [screen['phase']], 'phases')
    for integration in integrations:
        references(integration['id'], integration['source_ids'], 'sources')
        references(integration['id'], [integration['phase']], 'phases')
    domain = read_json('contracts/domain.schema.json')
    for case in read_json('fixtures/index.json')['fixtures']:
        validator = Draft202012Validator({'$schema': domain['$schema'], '$defs': domain['$defs'], '$ref': '#/$defs/' + case['definition']}, format_checker=FormatChecker())
        value = read_json(case['path'])
        issues = [e.message for e in validator.iter_errors(value)]
        if not issues:
            issues += semantic_errors(case['definition'], value)
        actual_valid = not issues
        passed = actual_valid == case['expected_valid']
        fixtures_report.append({'path': case['path'], 'expected_valid': case['expected_valid'], 'actual_valid': actual_valid, 'expectation_passed': passed, 'validation_messages': issues})
        if not passed:
            errors.append(f"Fixture expectation mismatch: {case['path']}: {issues}")
    report = {'schema_version': '1.0.0', 'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'Specification consistency only; no application tests, chemistry engines, training jobs or laboratory experiments executed.', 'passed': not errors, 'counts': {k: len(v) for k, v in collections.items()}, 'fixture_cases': len(fixtures_report), 'fixture_expectations_passed': sum(x['expectation_passed'] for x in fixtures_report), 'errors': errors, 'fixtures': fixtures_report}
    if args.report:
        destination = args.report.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for error in errors:
        print('ERROR:', error, file=sys.stderr)
    print(f"Specification validation: {'PASS' if not errors else 'FAIL'}; {len(tickets)} tickets; {len(tests)} acceptance cases; {report['fixture_expectations_passed']}/{len(fixtures_report)} fixture expectations matched.")
    print(report['scope'])
    return 1 if errors else 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f'Cannot validate pack: {exc}', file=sys.stderr)
        raise SystemExit(2)
