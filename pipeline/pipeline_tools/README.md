# API / Codex harness integration

The three prompts remain Design → Construction → Review. `pipeline.py render` embeds the exact skill text, relevant references, shared/stage prompts and context snapshots. No paid API call is made by rendering. `run` invokes an explicitly supplied argv; the wrapper receives prompt text on stdin, with optional `{prompt_file}`, `{job_dir}`, `{run_root}` substitutions. Use a new harness conversation per job; do not load builder chat history into Review or solver runs.

```bash
python3 pipeline_tools/pipeline.py render --stage design --context /absolute/run_context.json --skill /absolute/skills/godot-task-construction --output /absolute/jobs/design-001
python3 pipeline_tools/pipeline.py render --stage construction --task sc0001 --context /absolute/run_context.json --skill /absolute/skills/godot-task-construction --output /absolute/jobs/construction-001
python3 pipeline_tools/pipeline.py run --job /absolute/jobs/construction-001 --command-json '["/absolute/your_harness_wrapper", "{prompt_file}"]' --timeout 3600
python3 pipeline_tools/gate.py --run-root /absolute/run --task sc0001 --freeze
```

The harness wrapper is yours: configure the real API, tool protocol, credentials and process isolation there. These commands do not invent Codex CLI flags. A model exit code does not qualify a task. The gate checks schema, exact artifact/grader/runner hashes, three clean start-baseline/start-full/reference runs, targeted runnable negatives, a substantive legal alternative, visual evidence and a fresh independent review. Review is a semantic obligation, not something hash checks can prove.

`qualification.json` lists run-relative result.json paths under keys `reference`, `start_baseline`, `start_full`. `controls.json` records candidate/reference fingerprints, mutation, R IDs, expected failing checks and result path. `visual_review.json` records actual reviewed image hashes and current reference digest. `review_report.json` records fresh context, findings and `gate.current` fingerprints. No missing evidence defaults to success. Any changed input requires a new job or new qualification evidence; existing logs remain immutable.

Run validators with `GODOT=/absolute/Godot` to select the exact pinned binary. Public solver exports contain only tasks/TASK_ID. Do not expose tasks_gt, validators, controls, evidence or source patches to solver jobs. This runner isolates copies and verdict code; the external harness is responsible for OS/network isolation when executing untrusted generated projects.

## Candidate grading and visual completion

The private canonical `validators/TASK_ID/validate.py` is the grading entry. `runtime/runner.py` reports automated behavior only. Full candidate PASS additionally needs a candidate-bound visual receipt covering `visual_checklist.json`, from actual rendered images. The entry returns ERROR/visual_review_required when behavior passes but the receipt is missing; visual judgments cannot override behavior errors. Use `--render` to create evidence, then `--combine-existing --visual-review /path/review.json` to aggregate. A reviewer or separately configured multimodal judge writes the receipt; merely generating image files does not satisfy it. `runtime/grade.py` validates image, candidate, rendered-run and grader/runner fingerprints.
