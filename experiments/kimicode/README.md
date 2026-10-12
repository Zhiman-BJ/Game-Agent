# Kimi Code solver experiments

Linux + Bubblewrap are required. The included GameDevBench runtime adapter creates a private solver filesystem, exposes only the task's `start` project and instruction, and routes model requests through a host-owned bridge. References and validators are never mounted. Install Kimi Code in a dedicated environment and provide an absolute executable path. Set `GAMEDEVBENCH_XVFB_ROOT` if Xvfb uses a separate runtime installation.

The external dataset must provide `catalog.json` and `tasks/<id>/start/`,
`tasks/<id>/instruction.md`, and `tasks/<id>/task.json`. Keep its validator
and evaluator files with the dataset so evaluation uses the matching protocol.
No task packages or experiment results are included in this repository.

```bash
export SOLVER_BASE_URL='https://your-provider.example/v1'
read -rs SOLVER_API_KEY; export SOLVER_API_KEY
python experiments/kimicode/run.py \
  --dataset /absolute/path/to/dataset --tasks task_0001 task_0002 \
  --model YOUR_MODEL --family k3 --parallel 2 \
  --godot /absolute/path/to/godot --kimi /absolute/path/to/kimi \
  --output /absolute/path/to/new-experiment
```

For Qwen, select `--family qwen` and the matching model/API endpoint. Each task has one solve attempt. Output includes the initial file hashes, complete wire events, checkpoint, final project, provider records, and event counts. `StepBegin` is the reported step count; tool events are counted separately. Solver completion does not imply feature correctness. Evaluate final workspaces separately with the dataset's `evaluate.py`; provide fresh visual review where required.

Experiment output may contain private prompts and API payloads. Keep it outside the publication repository. Transport retries, later validator repairs and retrospective adjudication must be recorded separately in local research records.
