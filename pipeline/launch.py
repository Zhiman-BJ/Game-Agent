#!/usr/bin/env python3
"""Start or resume a prepared batch; this is the only construction entry point."""
from pathlib import Path
import fcntl
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'tools'))
from host import read, validate_config
from scheduler import BatchScheduler

def main():
    cfg = read(ROOT/'batch_config.json')
    validate_config(cfg)
    # Preserve the lock name used by existing work orders.
    with (ROOT/'direct_supervisor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        BatchScheduler(cfg).main()

if __name__ == '__main__':
    main()
