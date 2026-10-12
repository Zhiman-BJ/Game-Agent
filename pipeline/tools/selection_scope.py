"""Read-only task admission for an explicitly selected continuation cohort."""
import json
from pathlib import Path

def read_scope(root):
    path=Path(root)/'execution_scope.json'
    if not path.exists():
        raise RuntimeError("Required execution scope is missing; refusing task admission")
    data=json.loads(path.read_text())
    if data.get('schema_version')!=1 or data.get('mode')!='allowlist':
        raise RuntimeError('Invalid execution scope; refusing task admission')
    selected=data.get('selected_task_ids')
    deferred=data.get('deferred_task_ids')
    retained=data.get('retained_accepted_task_ids')
    if not all(isinstance(x,list) and all(isinstance(t,str) for t in x) for x in (selected,deferred,retained)):
        raise RuntimeError('Invalid execution scope lists; refusing task admission')
    if any(len(x)!=len(set(x)) for x in (selected,deferred,retained)) or set(selected)&(set(deferred)|set(retained)) or set(deferred)&set(retained):
        raise RuntimeError('Overlapping execution scope lists; refusing task admission')
    return data

def task_allowed(root,tid):
    scope=read_scope(root)
    return scope is None or tid in scope['selected_task_ids']

def ordered_lanes(root,lanes):
    scope=read_scope(root)
    if scope is None:return lanes
    known={lane['task_id']:lane for lane in lanes}
    classified=set(scope['selected_task_ids']+scope['deferred_task_ids']+scope['retained_accepted_task_ids'])
    if classified!=set(known):
        raise RuntimeError('Execution scope does not partition batch lanes; refusing task admission')
    return [known[tid] for tid in scope['selected_task_ids']]


def task_selection_note(root, tid):
    if not task_allowed(root, tid):
        raise RuntimeError('Task is not in the continuation allowlist: '+tid)
    notes=json.loads((Path(root)/'selection_notes.json').read_text())
    if tid not in notes:
        raise RuntimeError('Missing task-specific continuation guidance: '+tid)
    return '\n本轮候选选择说明（调度优先级不是验收结论；不得重跑无关证据）：'+json.dumps(notes[tid],ensure_ascii=False)
