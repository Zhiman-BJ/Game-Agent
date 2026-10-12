# Batch supervision

Prepare a new work directory with `scripts/prepare_batch.py`, complete each
provider's tool/Godot/render and session-resume preflight, then approve those
records with `tools/approve_preflight.py`. Start or resume with one entry point:

```bash
python /absolute/path/to/new-batch/launch.py
```

The scheduler checks prior actor PID identity and refuses to start beside a
matching live actor. A persistent batch lock excludes duplicate schedulers.
Existing work orders retain their frozen code; do not overwrite their tools
with a new template or delete fingerprint records to bypass a mismatch.

## Components

- `scheduler.py`: repository feature claims, sibling admission, provider lane
  limits, pause boundaries and bounded native-session recovery.
- `construction.py`: one continuing author, early calibration, qualification
  matrix, fresh public-first independent review and repairs.
- `replay.py`: canonical reference/full, start/baseline and start/full execution;
  current candidate, grader and runtime evidence binding.
- `host.py`: process identity and cleanup, configuration, source handoff and
  exact-byte frozen export.

The API relay limits actual requests separately from admitted task lanes.
Godot slots apply to engine invocations, not entire validation matrices.
Each task has private Xvfb and XDG paths. Credentials stay with the host-owned
relay; the author receives a local relay token through the harness.

## Pause and resume

Write `control.json` atomically in the work directory:

```json
{
  "pause_new": false,
  "cancel_active": false,
  "providers": {
    "provider_a": {"concurrency": 16}
  }
}
```

`pause_new: true` stops new lanes and the next model invocation in active lanes;
a currently running call may finish. The task's session, counters, checkpoints
and evidence are retained. Clear it and run `launch.py` again to resume.
`cancel_active`, SIGINT or SIGTERM cancel owned process groups and observed
descendants. Cleanup checks process identity; it must not target other users'
processes. A malformed control file pauses admission. Lowering a provider limit
does not interrupt calls that are already running.

Terminal `ACCEPTED`, `BLOCKED` and `INFRA_FAILED` tasks are not automatically
reopened. Diagnose their saved evidence before explicitly scheduling recovery.
An author assertion or exhausted budget never counts as acceptance. Continuation
budgets remain finite; evidence reuse requires matching current fingerprints.
A configured oversized-review recovery archives its original checkpoint and
permits only one fresh independent-review reset.

## Progress and acceptance

`batch_status.json`, `events.jsonl`, `jobs/*/*/job.json` and
`lane_progress/*.json` distinguish invocations, author verification, independent
review, host replay and acceptance. Inspect them with:

```bash
python /absolute/path/to/new-batch/tools/status.py
python /absolute/path/to/new-batch/tools/runtime_health.py
```

Usage comes from completed native turn receipts; missing or interrupted usage
is unknown/partial. Tool-item counts are not complete teacher trajectory step
counts, and no billing cost is inferred.

Acceptance requires independent review, the public-contract gate, canonical
host replay, visual evidence where required, source revision/cleanliness checks,
frozen fingerprints and exact-byte ZIP verification. Only accepted public files
enter `solver_packages/`. Construction acceptance does not establish teacher vs.
student difficulty; that requires the separately retained solver experiments.
