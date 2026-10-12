# GameDevBench runner and agent adapters

This directory retains the full benchmark runner and the Kimi Code, Claude Code,
Codex, Gemini CLI, Mini SWE, OpenHands, OpenCode and Muse adapters. The local
provider bridge, confinement and checkpoint adaptations are retained too.
See [NOTICE](NOTICE) and [LICENSE](LICENSE).

From the repository root, install the runner dependencies and inspect its CLI:

```bash
python -m pip install -r requirements-benchmark.txt
PYTHONPATH=third_party/gamedevbench python -m gamedevbench.src.benchmark_runner --help
```

Install the executable or SDK required by your selected agent separately.
Claude Code imports `claude_agent_sdk`; OpenHands imports its SDK and Pydantic.
The optional MCP server imports `mcp` and Pillow. Adapters with unavailable
Python dependencies are omitted from the factory's available-agent list;
retaining an adapter does not install its runtime.

The runner uses the original GameDevBench task layout (`tasks/`, `tasks_gt/`,
`task_config.json`) relative to this directory. It supports task lists,
parallel runs, resume, validation and result aggregation. Strict solver
confinement requires the Linux runtime described in the main README.

Feature task datasets are external to this code-only repository. Use the
[Kimi Code experiment entry](../../experiments/kimicode/README.md) with
`--dataset /absolute/path/to/dataset` and the dataset's `evaluate.py` to evaluate
candidates. The retained runner does not implicitly convert the feature-task
format into the original GBD layout.

The Godot screenshot MCP has an installable `gamedevbench-mcp` command;
see [MCP setup](../../docs/MCP.md). Its diagnostic output is redirected to stderr
so it cannot corrupt the stdio protocol.
