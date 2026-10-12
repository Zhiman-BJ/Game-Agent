"""Per-validation FIFO admission; legacy matrix scopes do not reserve capacity.

The scoring runner is unchanged. Global capacity is owned by one validate() or
one direct engine invocation, never by a caller's whole matrix. Lock descriptors
survive subprocess/namespace boundaries and orphan engines. This is cooperative
resource scheduling, not a hostile-code security boundary.
"""
import contextlib
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path
import random
import time
import uuid

HELD = 'DIRECT82_GODOT_SLOT_HELD'
LANE_HELD = 'DIRECT82_GODOT_LANE_HELD'


def _root():
    root = Path(os.environ.get('DIRECT82_GODOT_SLOT_DIR', '/tmp/direct82_godot_slots')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _try_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _valid(key, root):
    # Descriptor identity works across PID namespaces; PID numbers alone do not.
    try:
        value = json.loads(os.environ[key])
        if value['root'] != str(root):
            return None
        path = root / value['file']
        if path.parent != root or json.loads(path.read_text()) != value:
            return None
        live = os.fstat(value['fd'])
        disk = path.stat()
        if (live.st_dev, live.st_ino) != (disk.st_dev, disk.st_ino):
            return None
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return None


def godot_slot_fds():
    root = _root()
    return tuple(dict.fromkeys(v['fd'] for k in (LANE_HELD, HELD) if (v := _valid(k, root))))


def _inherited(root):
    return bool(_valid(HELD, root))


def _wait(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('Godot capacity queue timeout (no Godot validation was started)')
    time.sleep(.10 + random.random() * .10)


def _deadline():
    timeout = float(os.environ.get('DIRECT82_GODOT_QUEUE_TIMEOUT', '21600'))
    return time.monotonic() + timeout if timeout > 0 else None


def _mark(fd, path, root):
    value = {'root': str(root), 'file': path.name, 'fd': fd,
             'pid': os.getpid(), 'token': uuid.uuid4().hex}
    os.ftruncate(fd, 0)
    os.write(fd, json.dumps(value, sort_keys=True).encode())
    return value


def _restore(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


@contextlib.contextmanager
def _lane_slot():
    """Serialize a single workload on this task/display."""
    root = _root()
    if _valid(LANE_HELD, root):
        yield godot_slot_fds()
        return
    lane = os.environ.get('DIRECT82_GODOT_LANE') or os.environ.get('DISPLAY')
    if not lane:
        yield godot_slot_fds()
        return
    path = root / ('lane-' + hashlib.sha256(lane.encode()).hexdigest()[:24] + '.lock')
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    previous = os.environ.get(LANE_HELD)
    try:
        deadline = _deadline()
        while not _try_lock(fd):
            _wait(deadline)
        os.environ[LANE_HELD] = json.dumps(_mark(fd, path, root), sort_keys=True)
        yield godot_slot_fds()
    finally:
        _restore(LANE_HELD, previous)
        os.close(fd)


@contextlib.contextmanager
def godot_slot():
    """Legacy matrix scope: no reservation. Each validate()/wrapper owns admission.

    Forward an already held workload's descriptors when called inside one;
    callers wrapping entire matrices no longer hold either global or lane locks.
    """
    yield godot_slot_fds()


def _event(root, kind, **fields):
    # Telemetry failure must not alter a validation verdict.
    try:
        fd = os.open(root / 'scheduler_events.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            row = {'event': kind, 'time': time.time(), 'pid': os.getpid(),
                   'lane': os.environ.get('DIRECT82_GODOT_LANE', os.environ.get('DISPLAY')), **fields}
            os.write(fd, (json.dumps(row, sort_keys=True) + '\n').encode())
        finally:
            os.close(fd)
    except OSError:
        pass


@contextlib.contextmanager
def engine_slot():
    """One bounded validation or direct engine call, with FIFO admission."""
    root = _root()
    with _lane_slot():
        if _valid(HELD, root):
            yield godot_slot_fds()
            return
        capacity = int(os.environ.get('DIRECT82_GODOT_SLOTS', '48'))
        if not 1 <= capacity <= 48:
            raise ValueError('Godot capacity must be between 1 and 48')
        deadline = _deadline()
        guard = os.open(root / 'admission.lock', os.O_RDWR | os.O_CREAT, 0o600)
        ticket = None
        ticket_fd = slot_fd = None
        previous = os.environ.get(HELD)
        began = time.monotonic()
        acquired = None
        slot_index = None
        try:
            while not _try_lock(guard):
                _wait(deadline)
            try:
                cfg = root / 'configuration.json'
                if cfg.exists() and json.loads(cfg.read_text()) != {'capacity': capacity}:
                    raise ValueError('Godot slot capacity disagrees with existing pool configuration')
                if not cfg.exists():
                    cfg.write_text(json.dumps({'capacity': capacity}) + '\n')
                sequence_file = root / 'queue_sequence.json'
                sequence = json.loads(sequence_file.read_text())['next'] if sequence_file.exists() else 0
                temporary = root / ('sequence-' + uuid.uuid4().hex + '.tmp')
                temporary.write_text(json.dumps({'next': sequence + 1}))
                temporary.replace(sequence_file)
                ticket = root / ('ticket-%020d-%s.lock' % (sequence, uuid.uuid4().hex))
                ticket_fd = os.open(ticket, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
                fcntl.flock(ticket_fd, fcntl.LOCK_EX)
            finally:
                fcntl.flock(guard, fcntl.LOCK_UN)
            _event(root, 'enqueue', ticket=ticket.name)
            while slot_fd is None:
                while not _try_lock(guard):
                    _wait(deadline)
                try:
                    head = None
                    for queued in sorted(root.glob('ticket-*.lock')):
                        if queued == ticket:
                            head = queued
                            break
                        try:
                            fd = os.open(queued, os.O_RDWR)
                        except FileNotFoundError:
                            continue
                        try:
                            if _try_lock(fd):
                                queued.unlink(missing_ok=True)  # dead waiter; kernel released its lease
                                continue
                            head = queued
                            break
                        finally:
                            os.close(fd)
                    if head == ticket:
                        for index in range(capacity):
                            path = root / ('slot-%03d.lock' % index)
                            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
                            if _try_lock(fd):
                                slot_fd = fd
                                slot_index = index
                                os.environ[HELD] = json.dumps(_mark(fd, path, root), sort_keys=True)
                                ticket.unlink()
                                os.close(ticket_fd)
                                ticket_fd = None
                                acquired = time.monotonic()
                                break
                            os.close(fd)
                finally:
                    fcntl.flock(guard, fcntl.LOCK_UN)
                if slot_fd is None:
                    _wait(deadline)
            _event(root, 'acquire', slot=slot_index, queue_seconds=round(acquired-began, 4))
            yield godot_slot_fds()
        finally:
            _restore(HELD, previous)
            if slot_fd is not None:
                os.close(slot_fd)
                _event(root, 'release', slot=slot_index, held_seconds=round(time.monotonic()-acquired, 4))
            if ticket_fd is not None:
                # Closing before unlinking is harmless: the next waiter can reap it.
                os.close(ticket_fd)
            if ticket is not None:
                ticket.unlink(missing_ok=True)
            os.close(guard)


def limit_godot_validation(function):
    @functools.wraps(function)
    def limited(*args, **kwargs):
        with engine_slot():
            return function(*args, **kwargs)
    return limited
