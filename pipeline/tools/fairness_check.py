#!/usr/bin/env python3
"""Mechanical audit of early calibration evidence; semantic fairness still needs review."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'pipeline_tools'), str(ROOT/'runtime')]
import gate
from runner import hashes, digest
CATEGORIES = ('discovery', 'fixtures', 'input_geometry', 'timing', 'lifecycle', 'aggregation')
FP_KEYS = ('start', 'reference', 'grader', 'runner', 'entry', 'spec')


def fingerprint(run, tid):
    full = gate.current(Path(run), tid)
    return {key: full[key] for key in FP_KEYS}


def check(run, tid):
    run = Path(run).resolve()
    errors = []
    def require(condition, message):
        if not condition:
            errors.append(message)
    def inside(relative):
        path = (run/relative).resolve()
        if not path.is_relative_to(run):
            raise ValueError('Calibration evidence escapes task directory')
        return path
    try:
        fp = fingerprint(run, tid)
        p = run/'private'/tid/'fairness_calibration.json'
        data = json.loads(p.read_text())
        require(data.get('schema_version') == 1, 'calibration schema_version must be1')
        require(data.get('fingerprints') == fp, 'calibration fingerprints stale')
        require(data.get('open_blockers') == [], 'calibration has unresolved blockers')
        manifest = json.loads((run/'validators'/tid/'validator_manifest.json').read_text())
        spec = json.loads((run/'private'/tid/'task_spec.json').read_text())
        requirement_ids = {x['id'] for x in spec['requirements']}
        candidate_cache = {}
        nonces = {}
        def result(relative, expected, mode='full', candidate=None, fixed_digest=None):
            ep = inside(relative)
            record = json.loads(ep.read_text())
            behavior = json.loads(ep.with_name('behavior.json').read_text())
            issues, nonce = gate.audit_result(record, manifest, mode, expected, behavior)
            errors.extend(relative+': '+issue for issue in issues)
            require(record.get('source_unchanged') is True, relative+': candidate changed')
            require(record.get('runner_sha256') == fp['runner'] and record.get('grader_files') == fp['grader'], relative+': stale grader/runner')
            if candidate is not None:
                cp = inside(candidate)
                if str(cp) not in candidate_cache:
                    candidate_cache[str(cp)] = digest(hashes(cp))
                fixed_digest = candidate_cache[str(cp)]
            require(record.get('candidate_digest') == fixed_digest, relative+': stale candidate')
            require(nonce not in nonces or nonces[nonce] == str(ep), relative+': reused execution nonce')
            nonces[nonce] = str(ep)
            return record
        result(data['reference_run'], 'PASS', fixed_digest=fp['reference'])
        result(data['start_baseline_run'], 'PASS', 'baseline', fixed_digest=fp['start'])
        start = result(data['start_full_run'], 'FAIL', fixed_digest=fp['start'])
        preserved = {x['id'] for x in spec['requirements'] if x['kind'] != 'target'}
        for c in start['checks']:
            if set(c['R_ids']) and set(c['R_ids']) <= preserved:
                require(c['status'] == 'PASS', 'start lost retained behavior: '+c['check_id'])
        risks = data['risks']
        require(isinstance(risks,list) and bool(risks), 'missing risk-specific calibration')
        ids = [x['id'] for x in risks]
        require(len(ids) == len(set(ids)), 'duplicate risk id')
        audit = data['assumption_audit']
        require(set(audit) == set(CATEGORIES), 'assumption audit must address all six categories (N/A allowed with reason)')
        for category in CATEGORIES:
            entry = audit[category]
            require(type(entry['applicable']) is bool and bool(str(entry['reason']).strip()), category+': missing applicability rationale')
            named = set(entry.get('risk_ids',[]))
            require(named <= set(ids), category+': unknown risk IDs')
            if entry['applicable']:
                require(bool(named), category+': no targeted challenge')
            for rid in named:
                require(next(x for x in risks if x['id']==rid)['category']==category, category+': risk category mismatch')
        for risk in risks:
            require(risk['category'] in CATEGORIES, 'unknown risk category')
            require(risk['id'] in audit[risk['category']].get('risk_ids',[]), 'risk omitted from category audit')
            require(bool(risk['public_R_ids']) and set(risk['public_R_ids']) <= requirement_ids, 'risk has no valid public basis')
            require(bool(str(risk['allowed_variation']).strip()), 'missing implementation freedom')
            require(bool(risk['code_locations']), 'missing observer code locations')
            for location in risk['code_locations']:
                require(inside(location.split(':',1)[0]).is_file(), 'missing code location: '+location)
            legal = risk['legal']; negative = risk['negative']
            require(bool(str(legal['why_legal']).strip()) and bool(str(negative['why_invalid']).strip()), 'missing challenge semantics')
            positive = result(legal['run'], 'PASS', candidate=legal['candidate'])
            require(positive['candidate_digest'] != fp['reference'], 'legal challenge duplicates reference bytes')
            bad = result(negative['run'], 'FAIL', candidate=negative['candidate'])
            expected = set(negative['expected_failed_checks'])
            require(bool(expected) and expected <= set(manifest['checks']), 'invalid targeted failed checks')
            failed = {x['check_id'] for x in bad['checks'] if x['status']=='FAIL'}
            require(bool(failed & expected), 'negative did not expose targeted defect: '+risk['id'])
        return {'status':'PASS' if not errors else 'NEEDS_CALIBRATION','errors':errors,'fingerprints':fp,
                'risk_count':len(risks),'semantic_review_required':True,
                'record_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration) as exc:
        return {'status':'NEEDS_CALIBRATION','errors':errors+[str(exc)],'semantic_review_required':True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root',required=True)
    parser.add_argument('--task',required=True)
    parser.add_argument('--fingerprint',action='store_true')
    args = parser.parse_args()
    output = fingerprint(args.run_root,args.task) if args.fingerprint else check(args.run_root,args.task)
    print(json.dumps(output,ensure_ascii=False,indent=2))
    raise SystemExit(0 if args.fingerprint or output['status']=='PASS' else 1)
