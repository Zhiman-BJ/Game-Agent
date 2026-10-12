"""Bounded work orders and mechanical substage checks, separate from frozen gates."""
from pathlib import Path
import json
from host_tools import checkpoints as cp

WORK = {
    'specification': 'Produce the Design handoff only. Demonstrate feasibility and observation contracts; do not implement Construction.',
    'implementation': 'Audit existing reference/start/public instruction and provenance first; repair only missing implementation within the approved specification. Preserve complete existing work. Do not run full qualification matrices or perform independent Review.',
    'calibration': 'Audit/fix the canonical observer against historical findings. Run a small targeted calibration with reference, at least one runnable negative and a substantive legal alternative. Save an executable matrix plan for remaining cases. Do not run the full qualification or visual/export matrix.',
    'qualification': 'Run only missing/current-version qualification cases and controls. Reuse previously completed cases only after exact candidate/grader/runtime fingerprint and result-protocol checks. Finish qualification.json and controls.json; do not redesign the task or repeatedly launch full matrices.',
    'visual_handoff': 'Finish missing visual inspection, receipts, integrity, exact public export and Construction handoff. Reuse verified current qualification evidence. Run the original pre-review gate; do not change the public contract to make tests green.',
    'solver_first': 'Read ONLY public instruction/start. Write a new solver_first.md with ambiguities and legal variations. Do not open private spec, tests, GT or builder findings in this substage. End immediately after saving the public-only record.',
    'challenge': 'First read the public package, then the saved independent solver-first record. Audit prior defects and assertion/public-contract alignment. Independently select/run a new negative and a legal alternative. If a major defect is reproduced, return it now; do not spend time on full stability matrices for known-invalid inputs.',
    'qualification_audit': 'First read the public package. Audit independent challenge evidence and run remaining independent stability, control, visual, integrity and export checks on unchanged inputs. Preserve prior current-version independent evidence; do not repeat completed cases just because this is a fresh execution slice.',
    'decision': 'First read the public package. Assemble the independent review from this review group and its evidence; confirm current fingerprints. Write current-job review_report.json/md and solver_first.md. ACCEPTED still requires the original final gate and host replay. Return any unresolved defect with routing and reproduction, never mark it resolved from a checkpoint alone.',
}


def work_order(journal, receipt, timeout):
    phase = journal.phase
    sample = {
        'task_id': journal.tid, 'stage': journal.stage, 'phase': phase,
        'nonce': journal.data['nonce'], 'status': 'COMPLETE',
        'summary': 'What actually completed; concise evidence-backed handoff',
        'artifacts': ['run-relative/path/to/real/evidence'],
        'next_action': 'First unfinished action if CHECKPOINTED',
    }
    return '\n\n--- Host substage execution contract (authoritative scope for this invocation) ---\n' + (
        f'Execute ONLY {journal.stage}/{phase}. The full stage documents are reference requirements, '
        'not an instruction to finish all stages in this invocation.\n'
        f'{WORK[phase]}\n'
        f'Invocation deadline: {timeout} seconds. Reserve the final 90 seconds for a partial handoff. '
        'After each completed case, persist its actual result path and hashes in your private progress log. '
        'If unfinished, write CHECKPOINTED and exit cleanly. Never claim COMPLETE merely because files exist.\n'
        f'Receipt file: {receipt}\n'
        'Write receipt atomically, using the exact identity below. Valid statuses: COMPLETE, CHECKPOINTED, '
        'RETURN_TO_DESIGN, RETURN_TO_CONSTRUCTION, BLOCKED, REJECTED. Artifacts are run-relative files. '
        'A checkpoint is NOT task acceptance. The host alone owns the substage cursor and validates evidence.\n'
        'Do not edit task_spec.json or narrow public requirements outside Design; return to Design. '
        'Do not change implementation/validator inputs during qualification or Review: return to Construction.\n'
        'Calibration/challenge COMPLETE additionally needs probes: a list of {kind: reference|negative|legal, '
        'result: run-relative/result.json, candidate: run-relative/candidate, expected_failed_checks: [...]}. '
        'List targeted check IDs for negatives; ERROR/TIMEOUT never qualify as a negative.\n'
        'Run repeated matrices using host_tools/resume_matrix.py from the batch root when compatible with '
        'the canonical runner. Its plan retains separate repetitions and interrupted-case evidence. '
        'Do not launch extra model calls.\n'
        + json.dumps(sample, ensure_ascii=False, indent=2)
        + '\nVerified host checkpoint summary:\n'
        + json.dumps(journal.summary(), ensure_ascii=False, indent=2)
    )


def verify_probe(run, tid, probe, gate):
    run = Path(run)
    kind = probe['kind']
    if kind not in {'reference', 'negative', 'legal'}:
        raise ValueError('Invalid probe kind')
    result_path = cp.safe_file(run, probe['result'])
    result = cp.load(result_path)
    behavior_path = result_path.with_name('behavior.json')
    behavior = cp.load(behavior_path)
    manifest_path = run / 'validators' / tid / 'validator_manifest.json'
    manifest = cp.load(manifest_path)
    expected = 'FAIL' if kind == 'negative' else 'PASS'
    errors, nonce = gate.audit_result(result, manifest, 'full', expected, behavior)
    fp = gate.current(run, tid)
    if result.get('grader_files') != fp['grader'] or result.get('runner_sha256') != fp['runner']:
        errors.append('stale grader/runner')
    if not result.get('source_unchanged'):
        errors.append('candidate changed')
    candidate = (run / probe['candidate']).resolve()
    if not candidate.is_relative_to(run.resolve()) or not candidate.is_dir():
        errors.append('candidate missing/outside run')
    elif gate.digest(gate.hashes(candidate)) != result.get('candidate_digest'):
        errors.append('stale candidate')
    if kind == 'reference' and result.get('candidate_digest') != fp['reference']:
        errors.append('reference mismatch')
    if kind == 'negative':
        failed = {x['check_id'] for x in result['checks'] if x['status'] == 'FAIL'}
        intended = set(probe.get('expected_failed_checks', []))
        if not intended or not intended <= set(manifest['checks']) or not intended & failed:
            errors.append('no intended negative check failed')
    if errors:
        raise ValueError('; '.join(errors))
    return {str(p.relative_to(run)): cp.sha(p) for p in (result_path, behavior_path)}


def qualification_evidence(run, tid, gate):
    """Validate matrix before visual step, using the same runner protocol checks."""
    private=run/'private'/tid
    m=cp.load(run/'validators'/tid/'validator_manifest.json')
    fp=gate.current(run,tid)
    spec=cp.load(private/'task_spec.json')
    allids={x['id'] for x in spec['requirements']}
    targets={x['id'] for x in spec['requirements'] if x['kind']=='target'}
    evidence={}
    def result(rel,expected,mode='full',candidate=None):
        p=cp.safe_file(run,rel);r=cp.load(p);b=cp.load(p.with_name('behavior.json'))
        errors,nonce=gate.audit_result(r,m,mode,expected,b)
        if r.get('grader_files')!=fp['grader'] or r.get('runner_sha256')!=fp['runner'] or not r.get('source_unchanged'):
            errors.append('stale grader/runtime or candidate changed')
        if candidate and r.get('candidate_digest')!=candidate:errors.append('candidate fingerprint differs')
        if errors:raise ValueError('; '.join(errors))
        for name in ['result.json','behavior.json','import.log','validation.log']:
            item=p.with_name(name)
            evidence[str(item.relative_to(run))]=cp.sha(item)
        return r,nonce
    q=cp.load(private/'qualification.json')
    allnonces=set()
    for group,kind,expected,mode in [('reference','reference','PASS','full'),('start_baseline','start','PASS','baseline'),('start_full','start','FAIL','full')]:
        paths=q.get(group,[])
        if len(paths)<3 or len(set(paths))!=len(paths):raise ValueError('Need three distinct '+group+' runs')
        for rel in paths:
            r,nonce=result(rel,expected,mode,fp[kind])
            if nonce in allnonces:raise ValueError('Repeated qualification nonce')
            allnonces.add(nonce)
            if group=='start_full' and not any(c['status']=='FAIL' and targets & set(c['R_ids']) for c in r['checks']):
                raise ValueError('No intended target failure')
    covered=set();legal=0
    for c in cp.load(private/'controls.json'):
        if c['kind'] not in ['legal','negative']:raise ValueError('Unknown control kind')
        if c['source_reference_digest']!=fp['reference']:raise ValueError('Stale control reference')
        r,_=result(c['run'],'PASS' if c['kind']=='legal' else 'FAIL',candidate=c['candidate_digest'])
        if c['kind']=='legal':legal+=1
        else:
            failed={x['check_id'] for x in r['checks'] if x['status']=='FAIL'}
            intended=set(c['expected_failed_checks']);declared=set(c['R_ids'])
            if not intended or not intended<=set(m['checks']):raise ValueError('Invalid intended control checks')
            detected={rid for cid in failed & intended for rid in m['checks'][cid]['R_ids']}
            if not declared or not declared<=allids or not declared<=detected:raise ValueError('Control lacks attributed requirement failure')
            covered|=detected
    if not allids<=covered or legal<1:raise ValueError('Missing effective negative/legal controls')
    return evidence


def validate_complete(journal, receipt, evidence, gate):
    """Mechanical milestone validation only; semantic acceptance stays independent."""
    run, tid, phase = journal.run, journal.tid, journal.phase
    private = run / 'private' / tid
    current = cp.fingerprint(run, tid)
    before = journal.data['before']
    if journal.stage != 'design' and current['contract'] != before['contract']:
        raise ValueError('SPEC_CHANGED_OUTSIDE_DESIGN')
    if (journal.stage == 'review' or phase in {'qualification', 'visual_handoff'}) and current != before:
        raise ValueError('INPUT_CHANGED_DURING_EVIDENCE_PHASE')
    required = []
    if phase == 'specification':
        required = ['repo_analysis.md', 'candidate_registry.json', f'private/{tid}/task_spec.json', f'private/{tid}/design_report.md']
    elif phase == 'implementation':
        required = [f'tasks/{tid}/task_config.json', f'private/{tid}/provenance.json']
        if not (run / 'tasks_gt' / tid).is_dir():
            raise ValueError('Missing reference tree')
    elif phase in {'calibration', 'challenge'}:
        probes = receipt.get('probes', [])
        if not {'reference', 'negative', 'legal'} <= {x.get('kind') for x in probes}:
            raise ValueError('Reference/negative/legal calibrated probes required')
        for probe in probes:
            evidence.update(verify_probe(run, tid, probe, gate))
    elif phase in {'qualification', 'qualification_audit'}:
        evidence.update(qualification_evidence(run,tid,gate))
        required.extend([f'private/{tid}/qualification.json',f'private/{tid}/controls.json'])
        if phase=='qualification_audit':
            result=gate.gate(run,tid,False)
            if result['status']!='ACCEPTED':raise ValueError('Independent evidence gate: '+str(result['errors'][:8]))
            visual=cp.load(private/'visual_review.json')
            required.extend([f'private/{tid}/visual_review.json',f'private/{tid}/visual_receipt.json',visual['render_result'],visual['receipt']])
            required.extend(x['path'] for x in visual['images'])
    elif phase == 'visual_handoff':
        result = gate.gate(run, tid, False)
        if result['status'] != 'ACCEPTED':
            raise ValueError('Pre-review gate: ' + '; '.join(result['errors'][:8]))
        required = [f'private/{tid}/construction_report.md']
    elif phase == 'solver_first':
        required = [f'private/{tid}/solver_first.md']
    elif phase == 'decision':
        required = [f'private/{tid}/review_report.json', f'private/{tid}/review_report.md', f'private/{tid}/solver_first.md']
        report = cp.load(private / 'review_report.json')
        if str(journal.data['job']) not in json.dumps(report.get('review_session')):
            raise ValueError('Review report not bound to current job')
        if report.get('status') == 'ACCEPTED':
            result = gate.gate(run, tid)
            if result['status'] != 'ACCEPTED':
                raise ValueError('Final review gate: ' + '; '.join(result['errors'][:8]))
        elif report.get('status') not in cp.ROUTES:
            raise ValueError('Invalid review verdict')
    for relative in required:
        p = cp.safe_file(run, relative)
        if not p.stat().st_size:
            raise ValueError('Empty milestone artifact: ' + relative)
        evidence[relative] = cp.sha(p)
    return evidence
