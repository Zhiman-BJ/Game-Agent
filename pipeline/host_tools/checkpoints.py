"""Host-owned, fingerprint-bound substage journal. Never confers acceptance."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import uuid

PHASES = {
    'design': ('specification',),
    'construction': ('implementation', 'calibration', 'qualification', 'visual_handoff'),
    'review': ('solver_first', 'challenge', 'qualification_audit', 'decision'),
}
EXCLUDE = {'.godot', '.git', '__pycache__'}
ROUTES = {'RETURN_TO_DESIGN', 'RETURN_TO_CONSTRUCTION', 'BLOCKED', 'REJECTED'}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def safe_file(run, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Expected run-relative artifact: ' + str(relative))
    p = Path(run) / p
    if not p.resolve().is_relative_to(Path(run).resolve()) or not p.is_file():
        raise ValueError('Missing/outside artifact: ' + str(relative))
    return p


def tree(run, relative):
    root = Path(run) / relative
    out = {}
    if root.is_file():
        out[str(relative)] = sha(root)
    elif root.is_dir():
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE)
            for name in sorted(files):
                p = Path(base) / name
                if p.is_symlink():
                    raise ValueError('Symlink in checkpoint inputs: ' + str(p))
                out[str(p.relative_to(run))] = sha(p)
    return out


def fingerprint(run, tid):
    """Complete relevant trees, never a sample; evidence is bound separately."""
    groups = {
        'contract': ['run_context.json', 'candidate_registry.json', 'repo_analysis.md',
                     f'private/{tid}/task_spec.json'],
        'candidate': [f'tasks/{tid}', f'tasks_gt/{tid}', f'private/{tid}/provenance.json'],
        'validator': [f'validators/{tid}', f'private/{tid}/coverage.json'],
    }
    out = {}
    for group, paths in groups.items():
        items = {}
        for path in paths:
            items.update(tree(run, path))
        out[group] = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    return out


class Journal:
    def __init__(self, root, run, tid, stage, generation, runtime_identity):
        self.run, self.tid, self.stage = Path(run), tid, stage
        # Outside actor's writable run_root. Append-only history; current atomically replaced.
        self.folder = Path(root) / 'checkpoints' / tid / stage
        self.path = self.folder / 'current.json'
        self.data = load(self.path, {})
        if self.data.get('generation') != generation or self.data.get('runtime_identity') != runtime_identity:
            self.data = dict(schema_version=2, task_id=tid, stage=stage, generation=generation,
                             runtime_identity=runtime_identity, completed={}, attempts={},
                             review_group=uuid.uuid4().hex, status='PENDING')
            self.save('new_generation')
        self.reconcile()

    def save(self, reason):
        self.data.update(updated_utc=utc(), last_reason=reason)
        history = self.folder / 'history' / (uuid.uuid4().hex + '.json')
        dump(history, self.data)
        dump(self.path, self.data)

    def reconcile(self):
        done = self.data['completed']
        if not done:
            return
        phases = PHASES[self.stage]
        current = fingerprint(self.run, self.tid)
        last = next(done[p] for p in reversed(phases) if p in done)
        old = last['fingerprint']
        cut = None
        if old != current:
            if self.stage != 'construction' or any(old[g] != current[g] for g in ('contract', 'candidate')):
                cut = 0
            else:
                cut = phases.index('calibration')
        for i, phase in enumerate(phases):
            if phase not in done:
                continue
            try:
                valid = all(sha(safe_file(self.run, p)) == h for p, h in done[phase]['evidence'].items())
            except (OSError, ValueError):
                valid = False
            if not valid:
                cut = min(cut, i) if cut is not None else i
        if cut is not None:
            for phase in phases[cut:]:
                done.pop(phase, None)
            # Do not reset spent retry/slice budgets on artifact mutation.
            self.data['status'] = 'INVALIDATED'
            self.save('changed_inputs_or_evidence:' + phases[cut])

    @property
    def phase(self):
        return next((p for p in PHASES[self.stage] if p not in self.data['completed']), None)

    def begin(self, job):
        phase = self.phase
        a = self.data['attempts'].setdefault(phase, {'launches': 0, 'timeouts': 0, 'transport': 0})
        a['launches'] += 1
        self.data.update(status='RUNNING', current_phase=phase, job=str(job),
                         nonce=uuid.uuid4().hex, before=fingerprint(self.run, self.tid))
        self.save('substage_start')
        return self.data['nonce']

    def failure(self, kind):
        a = self.data['attempts'][self.phase]
        if kind == 'TIMEOUT':
            a['timeouts'] += 1
        elif kind == 'TRANSPORT':
            a['transport'] += 1
        self.data['status'] = kind
        self.save(kind.lower())

    def finish(self, receipt, evidence):
        phase = self.phase
        self.data['completed'][phase] = {
            'job': self.data['job'], 'nonce': self.data['nonce'],
            'fingerprint': fingerprint(self.run, self.tid), 'evidence': evidence,
            'summary': receipt['summary'], 'finished_utc': utc(),
        }
        self.data['status'] = 'COMPLETE' if self.phase is None else 'CHECKPOINTED'
        self.save('substage_completed:' + phase)

    def summary(self):
        return {
            'generation': self.data['generation'], 'review_group': self.data['review_group'],
            'substage': self.phase, 'completed': {
                p: {'summary': v['summary'], 'evidence': list(v['evidence'])}
                for p, v in self.data['completed'].items()
            }, 'attempts': self.data['attempts'], 'last_receipt': self.data.get('last_receipt'),
        }


def validate_receipt(journal, path):
    r = load(path)
    if not isinstance(r, dict):
        raise ValueError('Missing substage receipt')
    for key, expected in [('task_id', journal.tid), ('stage', journal.stage),
                          ('phase', journal.phase), ('nonce', journal.data['nonce'])]:
        if r.get(key) != expected:
            raise ValueError('Receipt identity mismatch: ' + key)
    if r.get('status') not in {'COMPLETE', 'CHECKPOINTED'} | ROUTES:
        raise ValueError('Invalid substage status')
    if not isinstance(r.get('summary'), str) or not r['summary'].strip():
        raise ValueError('Missing bounded handoff summary')
    evidence = {}
    for rel in r.get('artifacts', []):
        evidence[rel] = sha(safe_file(journal.run, rel))
    if not evidence:
        raise ValueError('Empty checkpoint evidence')
    if r['status'] == 'CHECKPOINTED' and not r.get('next_action'):
        raise ValueError('Partial checkpoint needs next_action')
    return r, evidence
