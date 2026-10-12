#!/usr/bin/env python3
"""Run missing matrix cases only; retain failures and verify cached case bytes.

Usage: python3 host_tools/resume_matrix.py --plan RUN/private/.../matrix.json
Plan: {run_root, task_id, manifest, output_root, cases:[{id,candidate,mode,
expected,render,expected_failed_checks}]}. All non-root paths are run-relative.
No model calls. The canonical runtime and qualification gates are unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'pipeline_tools'))
import gate
from host_tools import checkpoints as cp
sys.path.insert(0,str(ROOT/'runtime'))
from godot_limiter import engine_slot, HELD


def bound(run, path):
    path = Path(path)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected run-relative path')
    result = (run / path).resolve()
    if not result.is_relative_to(run):
        raise ValueError('Path outside run_root')
    return result


def identity(run, manifest, case, runner):
    m = cp.load(manifest)
    candidate = bound(run, case['candidate'])
    return {
        'candidate': gate.digest(gate.hashes(candidate)),
        'grader': {manifest.name: cp.sha(manifest), **{
            rel: cp.sha((manifest.parent / rel).resolve()) for rel in m['files'].values()}},
        'runner': cp.sha(runner), 'case': case,
        'runtime_env': {k: os.environ.get(k) for k in ('GODOT','GODOT_EXEC_PATH','LD_LIBRARY_PATH','LP_NUM_THREADS','LIBGL_ALWAYS_SOFTWARE')},
    }


def verify(result_path, manifest, case, fp):
    r = cp.load(result_path)
    b = cp.load(result_path.with_name('behavior.json'))
    issues, _ = gate.audit_result(r, cp.load(manifest), case.get('mode','full'), case['expected'], b)
    if not r.get('source_unchanged') or r['candidate_digest'] != fp['candidate']:
        issues.append('candidate fingerprint differs')
    if r['grader_files'] != fp['grader'] or r['runner_sha256'] != fp['runner']:
        issues.append('grader/runner fingerprint differs')
    if r.get('rendered') != bool(case.get('render',False)):
        issues.append('render mode differs')
    if case['expected']=='FAIL':
        failed = {c['check_id'] for c in r['checks'] if c['status']=='FAIL'}
        if not failed & set(case.get('expected_failed_checks',[])):
            issues.append('no intended negative failure')
    if issues:
        raise ValueError('; '.join(issues))
    files={}
    for p in result_path.parent.iterdir():
        if p.is_file():
            files[p.name]=cp.sha(p)
    return files


class InfrastructureRetry(RuntimeError):
    """A durable, classified pre-execution failure eligible for bounded retry."""


def failure_class(result_path):
    try:
        result = cp.load(result_path, {})
    except (OSError, ValueError):
        return 'UNCLASSIFIED'
    if result.get('source_unchanged') is False:
        return 'INPUT_CHANGED'
    reasons = result.get('reason', [])
    if (result.get('status') == 'ERROR' and result.get('execution') == []
            and result.get('checks') == [] and isinstance(reasons, list) and len(reasons) == 1
            and isinstance(reasons[0], str)
            and '--version' in reasons[0] and 'timed out after' in reasons[0]):
        return 'ENGINE_VERSION_TIMEOUT'
    # Import/script errors, functional failures, execution timeouts, absent
    # results and unknown termination signals are never blindly auto-retried.
    return 'REQUIRES_DIAGNOSIS'


def classify_attempt(run, attempt):
    output = attempt.get('output')
    if not output:
        return 'REQUIRES_DIAGNOSIS'
    return failure_class(bound(run, output) / 'result.json')


def run_plan(plan_path, retry_failed=False, executor=None, runner=None):
    while True:
        try:
            return _run_plan(plan_path, retry_failed, executor, runner)
        except InfrastructureRetry as error:
            # The per-fingerprint journal is the durable retry budget. Reentry
            # verifies and reuses COMPLETE cases, never repeats the whole matrix.
            print('HOST_INFRA_RETRY ' + str(error), flush=True)
            time.sleep(2)


def _run_plan(plan_path, retry_failed=False, executor=None, runner=None):
    plan=cp.load(plan_path)
    run=Path(plan['run_root']).resolve()
    manifest=bound(run,plan['manifest'])
    output=bound(run,plan['output_root'])
    runner=Path(runner or ROOT/'runtime/runner.py')
    cases=plan['cases']; ids=[c['id'] for c in cases]
    if len(set(ids))!=len(ids) or not cases or any(not re.fullmatch(r'[A-Za-z0-9_-]+',x) for x in ids):
        raise ValueError('Unique safe case IDs required; repetitions need distinct IDs')
    if any(c.get('expected') not in ['PASS','FAIL'] for c in cases):
        raise ValueError('Only behavior PASS/FAIL are valid expected outcomes')
    output.mkdir(parents=True,exist_ok=True)
    # Refuse concurrent writers to the same matrix plan.
    import fcntl
    with (output/'matrix.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        journal=cp.load(output/'matrix.json',{'schema_version':1,'cases':{}})
        for case in cases:
            fp=identity(run,manifest,case,runner)
            key=hashlib.sha256(json.dumps(fp,sort_keys=True).encode()).hexdigest()
            versions=journal['cases'].setdefault(case['id'],{})
            record=versions.get(key)
            if record and record['status']=='COMPLETE':
                result_path=bound(run,record['result'])
                try:
                    files=verify(result_path,manifest,case,fp)
                    if files!=record['files']:raise ValueError('cached evidence bytes changed')
                except (OSError,ValueError,KeyError,TypeError):
                    record['status']='INVALIDATED'
                else:
                    print(case['id']+' REUSED',flush=True)
                    continue
            attempts=record.get('attempts',[]) if record else []
            if attempts:
                kinds = [classify_attempt(run, a) for a in attempts]
                auto = (record['status'] == 'FAILED' and kinds[-1] == 'ENGINE_VERSION_TIMEOUT')
                if auto:
                    if len(attempts) >= 3:
                        raise ValueError(case['id'] + ': infrastructure retry budget exhausted; host diagnosis required')
                elif len(attempts) >= 2 or (record['status'] in ['FAILED','INVALIDATED'] and not retry_failed):
                    raise ValueError(case['id']+': prior failure/invalidation requires diagnosis; no automatic rerun')
            if record and record.get('status') == 'QUEUED' and record.get('queue'):
                abandoned = dict(record['queue'], status='QUEUE_INTERRUPTED', finished_utc=cp.utc(),
                                 reason='Prior matrix owner exited before admission; matrix lock reacquired')
                record.setdefault('queue_history', []).append(abandoned)
            dest=output/(case['id']+'_'+uuid.uuid4().hex[:12])
            entry={'status':'QUEUED','output':str(dest.relative_to(run)),'queued_utc':cp.utc()}
            record=versions[key]={'status':'QUEUED','identity':fp,'attempts':attempts,
                                 'queue_history':record.get('queue_history',[]) if record else [],'queue':entry}
            cp.dump(output/'matrix.json',journal)
            queued = time.monotonic()
            executed = None
            def admitted():
                nonlocal executed
                if identity(run, manifest, case, runner) != fp:
                    raise ValueError('inputs changed while waiting for capacity')
                entry.update(status='RUNNING', started_utc=cp.utc(),
                             queue_seconds=round(time.monotonic()-queued,3))
                attempts.append(entry)
                executed = time.monotonic()
                record.update(status='RUNNING')
                record.pop('queue', None)
                cp.dump(output/'matrix.json', journal)
            argv=[sys.executable,str(runner),'--manifest',str(manifest),'--candidate',str(bound(run,case['candidate'])),
                  '--output-dir',str(dest),'--mode',case.get('mode','full')]
            if case.get('render'):argv.append('--render')
            env=dict(os.environ)
            for k,folder in [('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('TMPDIR','tmp')]:
                p=output/(dest.name+'_runtime')/folder;p.mkdir(parents=True,exist_ok=True);env[k]=str(p)
            m=cp.load(manifest);limit=sum(m['timeouts_seconds'].get(k,0) for k in ['import','render_validation' if case.get('render') else 'validation'])+60
            log=output/(dest.name+'.process.log')
            try:
                if executor:
                    admitted()
                    code=executor(argv,env,limit)
                else:
                    # Capacity waiting must precede the case execution timer.
                    # Children inherit the same held slot; no nested reacquire.
                    with engine_slot() as slot_fds:
                        admitted()
                        if os.environ.get(HELD):env[HELD]=os.environ[HELD]
                        with log.open('w') as f:
                            proc=subprocess.Popen(argv,cwd=run,env=env,pass_fds=slot_fds,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
                            try:code=proc.wait(timeout=limit)
                            except BaseException:
                                try:os.killpg(proc.pid,signal.SIGTERM)
                                except ProcessLookupError:pass
                                try:proc.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    try:os.killpg(proc.pid,signal.SIGKILL)
                                    except ProcessLookupError:pass
                                    proc.wait()
                                raise
                if code!=(0 if case['expected']=='PASS' else 1):raise ValueError('unexpected process exit '+str(code))
                if identity(run,manifest,case,runner)!=fp:raise ValueError('inputs changed during case')
                files=verify(dest/'result.json',manifest,case,fp)
                # Distinct repetitions cannot reuse one execution nonce.
                nonce=cp.load(dest/'result.json').get('nonce') or cp.load(dest/'behavior.json')['nonce']
                used={v.get('nonce') for versions in journal['cases'].values() for v in versions.values() if v.get('status')=='COMPLETE'}
                if nonce in used:raise ValueError('duplicate execution nonce')
                record.update(status='COMPLETE',result=str((dest/'result.json').relative_to(run)),files=files,nonce=nonce)
                entry.update(status='COMPLETE',finished_utc=cp.utc(), execution_seconds=round(time.monotonic()-executed,3))
                cp.dump(output/'matrix.json',journal)
                print(case['id']+' '+case['expected'],flush=True)
            except BaseException as error:
                kind = failure_class(dest/'result.json')
                try:
                    if identity(run, manifest, case, runner) != fp:
                        kind = 'INPUT_CHANGED'
                except (OSError, ValueError, KeyError):
                    kind = 'INPUT_CHANGED'
                if entry['status'] == 'QUEUED':
                    # No engine was dispatched: do not spend an execution attempt.
                    entry.update(status='QUEUE_INTERRUPTED', finished_utc=cp.utc(), reason=str(error),
                                 queue_seconds=round(time.monotonic()-queued,3))
                    record['status'] = 'QUEUE_INTERRUPTED'
                    record.setdefault('queue_history', []).append(dict(entry))
                else:
                    entry.update(status='FAILED', finished_utc=cp.utc(), reason=str(error), failure_class=kind,
                                 execution_seconds=round(time.monotonic()-executed,3) if executed is not None else None)
                    record['status']='FAILED'
                cp.dump(output/'matrix.json',journal)
                if kind == 'ENGINE_VERSION_TIMEOUT' and isinstance(error, Exception):
                    count = sum(classify_attempt(run,a)=='ENGINE_VERSION_TIMEOUT' for a in attempts)
                    if count < 3 and len(attempts) < 3:
                        raise InfrastructureRetry(case['id'] + ': ENGINE_VERSION_TIMEOUT; attempt ' + str(count) + '/3') from error
                raise
        return journal


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',required=True)
    p.add_argument('--retry-failed',action='store_true',help='After documented diagnosis only; at most two attempts per unchanged case')
    args=p.parse_args()
    run_plan(args.plan,args.retry_failed)
