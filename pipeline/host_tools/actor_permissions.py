"""Native permission profile shared by real actors and workload preflight."""
import json, os
from pathlib import Path


def actor_permission_args(private_root, godot_slot_dir=None):
    """Replace -s and all sandbox_workspace_write overrides with these args."""
    values = [
        'default_permissions="actor"',
        'permissions.actor.extends=":workspace"',
        'permissions.actor.network.enabled=true',
    ]
    roots = {str(Path(private_root).absolute()), str(Path(private_root).resolve())}
    slots = godot_slot_dir or os.environ.get('DIRECT82_GODOT_SLOT_DIR')
    entries = [json.dumps(':slash_tmp') + '="read"']
    if slots: entries.append(json.dumps(slots) + '="write"')
    entries += [json.dumps(p) + '="deny"' for p in sorted(roots)]
    values.append('permissions.actor.filesystem={' + ','.join(entries) + '}')
    return [part for value in values for part in ['-c', value]]
