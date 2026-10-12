#!/usr/bin/env python3
"""Read-only actor health; never read process environments or provider secrets."""
import collections
import json
import time
from pathlib import Path
import host as s


def snapshot():
    state = s.read(s.ROOT / 'batch_status.json', {})
    current = time.time()
    actors = []
    for tid, task in state.get('tasks', {}).items():
        if task.get('status') != 'RUNNING' or not task.get('job'):
            continue
        job = s.ROOT / task['job']
        record = s.read(job / 'process.json')
        live = bool(record and s.same_process(record))
        processes = s.descendant_identities(record['pid']) if live else {}
        if live:
            processes[record['pid']] = record
        states = collections.Counter()
        threads = 0
        for pid in processes:
            try:
                fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
                states[fields[0]] += 1
                threads += int(fields[17])
            except (OSError, ValueError, IndexError):
                continue
        events = job / 'events.jsonl'
        counts = collections.Counter()
        last_type = None
        if events.exists():
            for line in events.read_text(errors='replace').splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                item = event.get('item', {})
                last_type = item.get('type', event.get('type'))
                if event.get('type') == 'item.completed':
                    counts[item.get('type', 'unknown')] += 1
                    if item.get('type') == 'command_execution' and item.get('exit_code', 0):
                        counts['nonzero_command_exits'] += 1
        actors.append({'task_id': tid, 'provider': task['provider'], 'stage': task['stage'],
                       'job': task['job'], 'live': live, 'process_states': dict(states),
                       'process_count': len(processes), 'threads': threads,
                       'events_age_seconds': round(current-events.stat().st_mtime, 1) if events.exists() else None,
                       'completed_items': dict(counts), 'last_item_type': last_type})
    return {'at': s.now(), 'actors': actors, 'actor_count': len(actors),
            'live_actor_count': sum(x['live'] for x in actors),
            'actor_tree_threads': sum(x['threads'] for x in actors),
            'actor_tree_uninterruptible_processes': sum(x['process_states'].get('D', 0) for x in actors)}


if __name__ == '__main__':
    print(json.dumps(snapshot(), indent=2))
