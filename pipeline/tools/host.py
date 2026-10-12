"""Host-owned configuration, process lifecycle and verified package export."""
from pathlib import Path
import datetime, hashlib, json, os, re, signal, subprocess, sys, time, uuid, zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from host_tools.actor_permissions import actor_permission_args

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def identity(pid):
    try:
        proc = Path('/proc') / str(pid)
        stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'start_ticks': stat[19], 'uid': proc.stat().st_uid,
                'argv': (proc / 'cmdline').read_bytes().decode(errors='replace').split('\0')[:-1],
                'state': stat[0]}
    except (OSError,ValueError,IndexError):
        return None


def same_process(record, *, require_argv=True):
    if not isinstance(record,dict) or not record.get('pid'):
        return False
    current = identity(record['pid'])
    fields=['start_ticks','uid']+(['argv'] if require_argv else [])
    return bool(current and current['state'] != 'Z' and
                all(current.get(k) == record.get(k) for k in fields))


def descendant_identities(pid):
    """Walk every thread's children links, then recurse through child processes.

    Linux attaches forked children to the spawning thread's children file, so a
    Tokio worker's helper is absent from task/<process-leader>/children.
    """
    found={}
    frontier=[pid]
    while frontier:
        parent=frontier.pop()
        children=set()
        try:
            child_files = list((Path('/proc')/str(parent)/'task').glob('*/children'))
        except OSError:
            continue
        for path in child_files:
            try:
                children.update(int(child) for child in path.read_text().split())
            except (OSError,ValueError):
                continue
        for number in children:
            if number in found:continue
            record=identity(number)
            if record:
                found[number]=record
                frontier.append(number)
    return found


def terminate(proc):
    if proc.poll() is not None:
        return True
    descendants=descendant_identities(proc.pid)
    def signal_group(signum):
        try:os.killpg(proc.pid,signum)
        except ProcessLookupError:pass
    def signal_child(pid,record,signum):
        if same_process(record,require_argv=False):
            try:os.kill(pid,signum)
            except ProcessLookupError:pass
    try:
        for pid,record in descendants.items():
            signal_child(pid,record,signal.SIGTERM)
        signal_group(signal.SIGTERM)
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            # ESRCH here is a normal exit race, not a cleanup exception.
            signal_group(signal.SIGKILL)
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:pass
    finally:
        for pid,record in descendants.items():
            signal_child(pid,record,signal.SIGKILL)
    # A process in uninterruptible kernel I/O may remain after SIGKILL. Report
    # this explicitly so the caller retains its identity and does not retry it.
    return proc.poll() is not None


def command(cfg, provider, run, job):
    """Pure argv construction; no secrets and no shell interpolation."""
    return [cfg['codex_binary'], 'exec', '--ignore-user-config', '--ignore-rules',
            '--skip-git-repo-check', '--json', '--disable', 'multi_agent',
            *actor_permission_args(cfg['private_root'], cfg.get('godot_slot_dir')), '-C', str(run), '-m', cfg['model'],
            '-c', 'model_reasoning_effort=' + json.dumps(cfg['reasoning_effort']),
            '-c', 'approval_policy="never"', '-c', 'features.multi_agent=false',
            '-c', 'shell_environment_policy.exclude=["*API_KEY*","*SECRET*","*TOKEN*","CODEX_HOME"]',
            '-c', 'model_provider="batch_proxy"',
            '-c', 'model_providers.batch_proxy.name="Host batch proxy"',
            '-c', 'model_providers.batch_proxy.base_url=' + json.dumps(provider['base_url']),
            '-c', 'model_providers.batch_proxy.env_key="CODEX_PROXY_TOKEN"',
            '-c', 'model_providers.batch_proxy.wire_api="responses"',
            '-c', 'model_providers.batch_proxy.request_max_retries=2',
            '-c', 'model_providers.batch_proxy.stream_max_retries=2',
            '-c', 'model_providers.batch_proxy.stream_idle_timeout_ms=600000',
            '-o', str(job / 'last_message.txt'), '-']


def validate_config(cfg):
    assert isinstance(cfg['model'],str) and cfg['model'].strip()
    assert cfg['reasoning_effort'] in ('low','medium','high','xhigh','max','ultra')
    assert 1 <= len(cfg['providers']) <= 3
    ids = [x['task_id'] for x in cfg['lanes']]
    assert len(ids) == len(set(ids)) and len(ids) <= 128
    runs = [str(Path(x['run_root']).resolve()) for x in cfg['lanes']]
    assert len(runs) == len(set(runs))
    for key, p in cfg['providers'].items():
        assert 1 <= p.get('max_concurrency', 64) <= 64
        assert 0 <= p.get('initial_concurrency', 8) <= p.get('max_concurrency', 64)
        assert re.match(r'^http://127\.0\.0\.1:\d+/[A-Za-z0-9_-]+/v1/?$', p['base_url'])
    for lane in cfg['lanes']:
        assert lane['provider'] in cfg['providers']
        assert re.fullmatch(r'[A-Za-z0-9_-]+', lane['task_id'])
        assert Path(lane['run_root']).resolve().is_relative_to(ROOT / 'runs')
        assert Path(lane['context']).resolve().is_file()
    for stage in ['design', 'construction', 'review']:
        assert 1 <= cfg['stage_timeout_seconds'][stage] <= 86400
    assert 0 <= cfg.get('max_transport_retries', 2) <= 2
    for setting in ['max_revision_rounds', 'max_pre_gate_repairs']:
        value = cfg.get(setting, 2)
        assert isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10
    for setting in ['substage_timeout_seconds','max_substage_slices']:
        value=cfg.get(setting,900 if setting=='substage_timeout_seconds' else 4)
        assert isinstance(value,int) and not isinstance(value,bool) and value>0
    for setting in ['native_worker_threads','render_worker_threads']:
        value=cfg.get(setting,2)
        assert isinstance(value,int) and not isinstance(value,bool) and value>=1


def design_handoff(lane, pinned_context=None):
    """Check schema/identity and handoff files, not Construction quality evidence."""
    run,tid=Path(lane['run_root']),lane['task_id']
    errors=[]
    for rel in ['run_context.json','repo_analysis.md','candidate_registry.json',f'private/{tid}/task_spec.json',f'private/{tid}/design_report.md']:
        path=run/rel
        if not path.is_file() or not path.stat().st_size:errors.append('Missing/empty Design handoff: '+rel)
    try:
        context=read(lane['context'])
        spec=read(run/'private'/tid/'task_spec.json')
        required={'schema_version','task_id','spec_revision','design_status','name','source','task_origin',
                  'difficulty_rationale','capabilities','source_evidence','start_state','target_state','edit_scope',
                  'requirements','non_goals','assets','dependencies','runtime','validation_plan','feasibility'}
        missing=required-set(spec)
        if missing:errors.append('Missing spec fields: '+', '.join(sorted(missing)))
        if spec.get('schema_version')!=3 or spec.get('task_id')!=tid or spec.get('design_status')!='DESIGN_READY':errors.append('Design schema/task/status mismatch')
        if not isinstance(spec.get('spec_revision'),int) or spec['spec_revision']<1:errors.append('Invalid spec_revision')
        if Path(context['run_root']).resolve()!=run.resolve() or context['repository_id']!=lane['repository_id']:errors.append('Run context identity mismatch')
        if pinned_context:
            for key in ['source_repo','source_revision','repository_id','project_subdir','godot_binary','godot_version','run_root']:
                if context.get(key)!=pinned_context.get(key):errors.append('Pinned context changed: '+key)
        source=spec.get('source',{})
        if source.get('repository_id')!=context['repository_id']:errors.append('Spec source repository mismatch')
        revision_values=[source[k] for k in ['revision','commit','source_revision','commit_sha','git_commit','git_revision','fixed_commit','pinned_commit','commit_hash'] if source.get(k)]
        # The shared prompt describes source identity without fixing a JSON key
        # for the commit. Accept another scalar key carrying the exact pinned
        # commit; explicit contradictory conventional identity keys still fail.
        if not revision_values and context['source_revision'] in source.values():revision_values=[context['source_revision']]
        if not revision_values or any(value!=context['source_revision'] for value in revision_values):errors.append('Spec source revision missing/mismatched')
        subdir=source.get('project_subdir')
        pinned_subdir=context.get('project_subdir')
        if (subdir is None)!=(pinned_subdir is None):errors.append('Spec source project selection mismatch')
        if subdir is not None:
            selected=Path(subdir)
            if selected.is_absolute() or not (Path(context['source_repo'])/selected).resolve().is_relative_to(Path(context['source_repo']).resolve()):errors.append('Unsafe source project_subdir')
            if pinned_subdir is not None and (Path(context['source_repo'])/selected).resolve()!=(Path(context['source_repo'])/pinned_subdir).resolve():errors.append('Spec source project selection mismatch')
        reqs=spec.get('requirements',[])
        fields={'id','kind','description','source_evidence_ids','acceptance','validation_method','valid_variations','negative_probe'}
        if not isinstance(reqs,list) or not reqs:errors.append('No requirements')
        else:
            ids=[]
            for requirement in reqs:
                if not isinstance(requirement,dict) or not fields<=set(requirement):
                    errors.append('Incomplete requirement schema');continue
                ids.append(requirement['id'])
                if requirement['kind'] not in ['target','preservation']:errors.append('Invalid requirement kind')
            if len(ids)!=len(set(ids)):errors.append('Duplicate requirement IDs')
            if not any(r.get('kind')=='target' for r in reqs if isinstance(r,dict)):errors.append('No target requirement')
        if not isinstance(spec.get('capabilities'),dict):errors.append('capabilities must be an object')
        # JSON parsing the candidate registry catches truncated handoffs while
        # leaving its semantic selection judgment to Design/Review.
        read(run/'candidate_registry.json')
    except (OSError,ValueError,KeyError,TypeError) as error:
        errors.append('Unreadable Design handoff: '+str(error))
    return {'task_id':tid,'status':'READY' if not errors else 'INCOMPLETE','errors':errors}


class HostRuntime:
    def control(self):
        try:
            return read(ROOT / 'control.json', {})
        except (ValueError, OSError):
            # A malformed operator control safely stops new launches.
            return {'pause_new': True, 'control_error': True}


    def run_process(self, argv, cwd, env, stdout, stderr, timeout, stdin=None, record=None):
        if self.cancel.is_set():
            return 130
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin,
                                stdout=stdout, stderr=stderr, start_new_session=True)
        observed_children={}
        try:
            with self.lock:
                self.active_processes[proc.pid] = proc
            ident = identity(proc.pid)
            if ident is None:
                raise RuntimeError('Cannot establish newly started process identity: '+str(proc.pid))
            if record:
                dump(record, {**ident, 'process_group': proc.pid, 'started_utc': now(), 'deadline_seconds': timeout})
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                observed_children.update(descendant_identities(proc.pid))
                if self.cancel.is_set() or self.control().get('cancel_active'):
                    self.cancel.set()
                    return 130
                if time.monotonic() >= deadline:
                    return 124
                time.sleep(0.5)
            return proc.returncode
        finally:
            cleaned=terminate(proc)
            # Background Godot children may create separate sessions and survive
            # an otherwise successful CLI exit. Only kill identities we observed
            # while they belonged to this invocation, never a recycled PID.
            for child,record in observed_children.items():
                if same_process(record,require_argv=False):
                    try:os.kill(child,signal.SIGKILL)
                    except ProcessLookupError:pass
            with self.lock:
                if cleaned:self.active_processes.pop(proc.pid, None)
            if not cleaned:
                raise RuntimeError('Process still alive after bounded SIGTERM/SIGKILL cleanup; automatic lane retry stopped: '+str(proc.pid))


    def actor_environment(self, lane):
        # Deliberately do not copy arbitrary parent environment or upstream credentials.
        env = {k: os.environ[k] for k in ['PATH','HOME','USER','LOGNAME','LANG','LC_ALL','LD_LIBRARY_PATH','PYTHONPATH'] if k in os.environ}
        env.update(GODOT=self.cfg['godot_binary'], GODOT_EXEC_PATH=self.cfg['godot_binary'],
                   LIBGL_ALWAYS_SOFTWARE='1', PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
                   OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   TOKIO_WORKER_THREADS=str(self.cfg.get('native_worker_threads',2)),
                   LP_NUM_THREADS=str(self.cfg.get('render_worker_threads',2)))
        if self.cfg.get('library_path'):
            env['LD_LIBRARY_PATH']=self.cfg['library_path']
        run = Path(lane['run_root'])
        for var, folder in [('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('TMPDIR','tmp')]:
            path = run / '.runtime_home' / folder
            if var == 'TMPDIR':path=path/uuid.uuid4().hex
            path.mkdir(parents=True, exist_ok=True)
            env[var] = str(path)
        p = self.cfg['providers'][lane['provider']]
        token_path = p.get('proxy_token_file')
        env['CODEX_PROXY_TOKEN'] = Path(token_path).read_text().strip() if token_path else 'local-proxy'
        return env


    def next_job(self, tid, stage):
        folder = ROOT / 'jobs' / tid
        folder.mkdir(parents=True, exist_ok=True)
        numbers = [int(p.name.split('-')[-1]) for p in folder.glob(stage + '-*') if p.name.split('-')[-1].isdigit()]
        return folder / f'{stage}-{max(numbers, default=0)+1:03d}'


    def export(self, lane, frozen, replay):
        tid, run=lane['task_id'],Path(lane['run_root'])
        for rel, digest in frozen['files'].items():
            path=(ROOT/rel).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file() or sha(path)!=digest:
                raise RuntimeError('Frozen file changed: '+rel)
        public=run/'tasks'/tid
        expected=frozen['public_export_files']
        assert self.runner.hashes(public)==expected
        folder=ROOT/'solver_packages'
        folder.mkdir(exist_ok=True)
        target=folder/(tid+'.zip')
        temporary=folder/(tid+'.'+uuid.uuid4().hex+'.tmp')
        with zipfile.ZipFile(temporary,'x',zipfile.ZIP_DEFLATED) as archive:
            for rel in sorted(expected):
                path=(public/rel).resolve()
                if not path.is_relative_to(public.resolve()):
                    raise ValueError('Public export path escapes project')
                archive.write(path,arcname=tid+'/'+rel)
        with zipfile.ZipFile(temporary) as archive:
            assert {n[len(tid)+1:]:hashlib.sha256(archive.read(n)).hexdigest() for n in archive.namelist()}==expected
        temporary.replace(target)
        record={'task_id':tid,'repository_id':lane['repository_id'],'provider':lane['provider'],
                'status':'ACCEPTED','difficulty':'uncalibrated','public_zip':str(target.relative_to(ROOT)),
                'public_zip_sha256':sha(target),'public_digest':self.runner.digest(expected),
                'release_manifest':str((run/'private'/tid/'release_manifest.json').relative_to(ROOT)),
                'release_manifest_sha256':sha(run/'private'/tid/'release_manifest.json'),
                'host_replay':replay,'accepted_utc':now()}
        with self.lock:
            entries=[read(p) for p in sorted((ROOT/'accepted').glob('*.json')) if p.stem!=tid]+[record]
            entries.sort(key=lambda item:item['task_id'])
            previous=read(ROOT/'existing_task_registry.json',{'entries':[]})
            inherited=list(previous.get('entries',[]))
            inherited_ids={item['task_id'] for item in inherited}
            new=[]
            for accepted in entries:
                accepted_id=accepted['task_id']
                if accepted_id in inherited_ids:
                    raise ValueError('Accepted task ID duplicates historical registry: '+accepted_id)
                accepted_lane=next(x for x in self.cfg['lanes'] if x['task_id']==accepted_id)
                accepted_run=Path(accepted.get('run_root') or accepted_lane['run_root'])
                spec=read(accepted_run/'private'/accepted_id/'task_spec.json')
                config=read(accepted_run/'tasks'/accepted_id/'task_config.json')
                if accepted.get('acceptance_basis')=='AUTHOR_PRE_REVIEW':
                    evidence=ROOT/accepted['manual_qualification']
                    if sha(evidence)!=accepted['pre_review_sha256']:
                        raise RuntimeError('Retained author acceptance evidence changed: '+accepted_id)
                    new.append({'task_id':accepted_id,'source':accepted['repository_id'],
                                'source_revision':read(accepted_run/'run_context.json')['source_revision'],
                                'goal':spec['name'],'status':'ACCEPTED','difficulty':'uncalibrated',
                                'task_origin':spec['task_origin'],'public_instruction':config['instruction'],
                                'feature_gap':spec['start_state'],'origin_registry_batch':ROOT.name,
                                'manifest':str(evidence),'manifest_sha256':accepted['pre_review_sha256'],
                                'release_revision':0,'acceptance_basis':'AUTHOR_PRE_REVIEW',
                                'independent_review_status':'NOT_RUN','fresh_blind_review':False})
                    continue
                release=read(ROOT/accepted['release_manifest'])
                new.append({'task_id':accepted_id,'source':accepted['repository_id'],
                            'source_revision':read(accepted_run/'run_context.json')['source_revision'],'goal':spec['name'],
                            'status':'ACCEPTED','difficulty':'uncalibrated','task_origin':spec['task_origin'],
                            'origin_registry_batch':ROOT.name,'manifest':str(ROOT/accepted['release_manifest']),
                            'manifest_sha256':accepted['release_manifest_sha256'],
                            'public_instruction':config['instruction'],'feature_gap':spec['start_state'],
                            'release_revision':release['release_revision'],
                            **{key:accepted[key] for key in ['acceptance_basis','review_mode','fresh_blind_review','independent_review_status','artifact_root','run_root','frozen'] if key in accepted}})
            registry_path=ROOT/'existing_task_registry.json'
            dump(ROOT/'next_task_registry.json',{'batch':ROOT.name,
                 'inherited_registry_sha256':sha(registry_path) if registry_path.is_file() else None,
                 'prior_entries':len(inherited),'new_accepted':len(new),
                 'entries':inherited+new})
            dump(ROOT/'accepted'/f'{tid}.json',record)
            dump(ROOT/'solver_packages/index.json',{'batch':ROOT.name,'accepted':len(entries),'tasks':entries})
        return record
