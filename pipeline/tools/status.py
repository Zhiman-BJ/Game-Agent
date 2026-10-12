#!/usr/bin/env python3
"""Read-only batch progress, including HTTP-200 Responses stream failures."""
from pathlib import Path
import collections
import datetime
import json

ROOT = Path(__file__).resolve().parents[1]


def read(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return default


def snapshot():
    state = read(ROOT / 'batch_status.json', {})
    tasks = state.get('tasks', {})
    cfg = read(ROOT / 'batch_config.json', {})
    lanes = cfg.get('lanes', [])
    providers = {}
    for provider in cfg.get('providers', {}):
        ids = [lane['task_id'] for lane in lanes if lane['provider'] == provider]
        providers[provider] = {
            'candidates': len(ids),
            'statuses': dict(collections.Counter(tasks.get(tid, {}).get('status', 'QUEUED') for tid in ids)),
            'stages': dict(collections.Counter(tasks[tid].get('stage', 'unknown') for tid in ids if tid in tasks and tasks[tid].get('status') == 'RUNNING')),
        }
    streams = {}
    log = ROOT / 'proxy/requests.jsonl'
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('event') != 'end':
                continue
            counters = streams.setdefault(event['provider'], collections.Counter())
            counters['finished_requests'] += 1
            counters['completed_responses'] += bool(event.get('response_completed'))
            counters['explicit_stream_failures'] += bool(event.get('response_failure_event'))
            counters['transport_errors'] += bool(event.get('error_class'))
            counters['non_200_responses'] += event.get('http_status') != 200
    activity = []
    for lane in lanes:
        tid=lane['task_id'];task=tasks.get(tid,{})
        if task.get('status') in ['QUEUED','ACCEPTED','BLOCKED','INFRA_FAILED']:continue
        run=Path(lane['run_root']);job=ROOT/task.get('job','missing-job')
        files={'native_events':job/'events.jsonl','checkpoint':run/'checkpoint.md',
               'spec':run/'private'/tid/'task_spec.json','author_status':run/'author_status.json'}
        observed={k:datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat()
                  for k,p in files.items() if p.is_file()}
        process=read(job/'process.json',{})
        alive=False
        try:
            stat=Path('/proc')/str(process['pid'])/'stat'
            fields=stat.read_text().rsplit(')',1)[1].split()
            alive=fields[0]!='Z' and fields[19]==str(process['start_ticks'])
        except (KeyError,OSError,IndexError):pass
        activity.append({'task_id':tid,'status':task.get('status'),'provider':lane['provider'],
                         'pid':process.get('pid'),'pid_identity_alive':alive,
                         'last_observed_utc':max(observed.values()) if observed else None,
                         'evidence_mtimes':observed,'note':'No recent file event alone does not prove a hung model or tool.'})
    return {
        'activity':activity,
        'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'target_qualified_tasks': cfg.get('target_qualified_tasks'),
        'accepted': sum(task.get('status') == 'ACCEPTED' for task in tasks.values()),
        'providers': providers,
        'proxy': read(ROOT / 'proxy/status.json', {}),
        'stream_totals': streams,
        'control': read(ROOT / 'control.json', {}),
        'batch_launched': (ROOT / 'launch_receipt.json').exists(),
        'batch_completion_record': (ROOT / 'completion.json').exists(),
    }


if __name__ == '__main__':
    print(json.dumps(snapshot(), ensure_ascii=False, indent=2))
