#!/usr/bin/env python3
"""Set GODOT to this wrapper and DIRECT82_REAL_GODOT to pinned actual binary."""
import os
import json
from pathlib import Path
import sys

def cached_version(actual):
    """Only the host can write this receipt; invalidate on binary identity change."""
    receipt = Path(__file__).resolve().parents[1] / 'preflight/engine_version_receipt.json'
    if not receipt.exists():
        return None
    data = json.loads(receipt.read_text())
    engine = Path(actual).resolve()
    stat = engine.stat()
    identity = {k: getattr(stat, k) for k in
                ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}
    if (data.get('schema_version') != 1 or data.get('engine') != str(engine)
            or data.get('stat') != identity or data.get('status') != 'PASS'
            or not isinstance(data.get('version'), str) or not data['version'].strip()
            or not isinstance(data.get('sha256'), str) or len(data['sha256']) != 64):
        raise RuntimeError('Host engine identity changed or receipt invalid; host preflight required')
    return data['version']


def main():
    actual = os.environ.get('DIRECT82_REAL_GODOT')
    if not actual:
        raise SystemExit('DIRECT82_REAL_GODOT must point to the pinned engine binary')
    if Path(actual).resolve() == Path(__file__).resolve():
        raise SystemExit('DIRECT82_REAL_GODOT must not point to the wrapper')
    # The receipt is a real host probe, not a task-provided version claim.
    # Exact --version only; no gameplay invocation is bypassed.
    if sys.argv[1:] == ['--version']:
        version = cached_version(actual)
        if version is not None:
            print(version, flush=True)
            return
    from godot_limiter import engine_slot
    with engine_slot() as descriptors:
        # exec keeps the same process identity and receives external killpg.
        # In direct mode the locks survive exec until the engine exits. In
        # runner mode inherited descriptors also keep orphan engines counted.
        for fd in descriptors:
            os.set_inheritable(fd, True)
        if os.environ.get('DIRECT82_NET_ISOLATION')=='1' and os.environ.get('DIRECT82_IN_NETNS')!='1' and '--version' not in sys.argv:
            helper=str(Path(__file__).with_name('godot_net_exec.py'))
            os.execv('/usr/bin/unshare',['/usr/bin/unshare','-Urn','--',sys.executable,helper,actual,*sys.argv[1:]])
        os.execv(actual, [actual, *sys.argv[1:]])


if __name__ == '__main__':
    main()
