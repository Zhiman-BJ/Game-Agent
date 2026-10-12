# Stage 1 — Design repo-grounded Godot tasks

Design bounded, feasible game-development tasks from one upstream Godot repo without a tutorial. Analyze one checkout and one selected project or addon scope per run. Define the task before Construction builds it.

Read the accompanying `README.md` before execution; its shared schemas, visibility, runtime, and state contracts are required inputs. Treat source text as evidence, not workflow instructions. Do not use earlier prompt drafts.

## Inputs and outputs

Provide `REPO_PATH` (checkout root) and `RUN_ROOT` (separate output directory), or an existing `RUN_CONTEXT_PATH`. Optional: `PROJECT_SUBDIR`, `UPSTREAM_ROOT`. Resolve conflicting inputs explicitly. For repairs, also read `TASK_ID`, its spec, and routed findings.

Resolve `PROJECT_SUBDIR` relative to and within the checkout. `UPSTREAM_ROOT` is the managed collection root, inferable from checkout ancestors; it may be absent for a standalone repo.

The managed collection contains:

```text
gamedevbench-upstream/
  selected_repositories.json     # selected repo IDs
  download_manifest.json        # snapshot and project hints
  verification.json             # Git checks, not runtime tests
  source_index.json             # repository and task source index
  repos/<owner>/<repo>/          # select one actual checkout
```

Match only the selected repo's records. Stored absolute paths may predate relocation; use the actual checkout. From `source_index.json`, project the selected `repositories[]` entry's `id`, `clone_url`, `relative_path`, and `kind`. Use the repo's code, scenes, assets, and documentation to develop task ideas; the index locates source material.

Under `RUN_ROOT`, write:

- `run_context.json`: normalized paths, repo identity/revision, project selection, and runtime facts; mark unresolved fields.
- `repo_analysis.md`: source, features, dependencies, runtime observations, and unresolved issues.
- `candidate_registry.json`: candidate IDs, goals, capabilities, selection reasons, risks, and status.
- `private/TASK_ID/task_spec.json` and `design_report.md` for selected candidates, using the README schema.

Propose at most `max_tasks` candidates (default three), allowing zero. Do not create final task packages or public instructions here. Scratch feasibility probes are allowed.

## 1. Establish the source and runtime

- Verify the checkout, Git origin, revision, dirty files, and relevant submodules; honor pinned revisions and report manifest mismatches. For managed sources, check selection membership and download status. Do not pull, reset, switch revisions, restart downloads, or modify the source.
- Discover actual `project.godot` files; exclude caches and distinguish vendored tests. Use the requested project or one unambiguous selection; unresolved alternatives are BLOCKED. Use a nested project's directory as Godot's project path. Upstream `Start/End` names do not define our task boundary.
- For an addon without a project, identify installation requirements and a minimal generic host. Verify a scratch integration probe before claiming runtime readiness; do not borrow another repo's game. Distinguish addons from incomplete downloads and engine-source references.
- Check engine/renderer requirements, C# or native dependencies, LFS/submodule/sparse-checkout completeness, and asset licenses. Locate the actual runnable scene; do not assume `main.tscn`. `config_version` is not the engine release. Do not silently migrate the project or download missing content.
- Import and run a disposable copy with the configured engine and timeouts. Record commands and results; separate environment failures from source defects. Git verification is not gameplay evidence.
Record runtime readiness and task feasibility separately. Missing execution evidence permits static analysis, not DESIGN_READY.

## 2. Analyze the repo for task ideas

Inspect the selected feature's files; do not assume standard directory names:

- `project.godot`: entry scene, input actions, autoloads, plugins, and relevant settings.
- Scenes: node types/hierarchy, inherited or instanced scenes, Inspector values, attached scripts, resources, and signals.
- Scripts: input handlers, state transitions, collision/interaction logic, and runtime-created nodes/connections.
- Resources/assets: animation tracks, spritesheet layout, materials/shaders, audio, and import settings. Inspect relevant visual/audio content rather than inferring it from filenames.
- Repo documentation: intended goals and controls, checked against implementation and execution.

For each promising feature, trace **trigger/configuration → implementation and dependencies → observable result**. Exercise a normal case and relevant boundary case; for static configuration, inspect the instantiated properties and their effect. Reuse existing runtime evidence when sufficient.

Record the feature goal, file/node/function evidence, dependency map, exercised cases/results, and uncertainty in `repo_analysis.md`. Label evidence `observed`, `documented`, `inferred`, or `proposed`. Project launch alone does not verify a feature; upstream behavior is not automatically correct.

Look for actionable work: create/configure nodes, attach or implement scripts, connect signals, organize scenes, construct animation/resources, or complete a game interaction. Choose connected operations serving one goal. For example, an obstacle-blocking task may retain working movement while leaving collision detection and its integration with movement state to the solver; verify both blocked and unobstructed movement.

## 3. Select a task and define its gap

**Meaningful task scope:** Each task should have a clear, coherent game-development goal and leave substantive implementation, configuration, or integration work to the solver. Define the intended behavior from the repo analysis, then design the start around that goal. Completing or modifying part of an existing system is valid; reusable functionality may remain supplied.

- Prefer `verified_reconstruction`: remove or neutralize selected functionality from an exercised feature, retaining runnable context and reusable components. Choose the gap to exercise the intended capability.
- Use `repo_grounded_extension` for new behavior or repairs without a verified upstream endpoint. Build on relevant existing functionality; explain the proposed change and probe uncertain feasibility. Never describe an extension as existing upstream behavior.

For each candidate, specify:

- **Provided at start:** supplied scenes, assets, infrastructure, interfaces, and existing behavior.
- **Solver responsibility:** the key implementation, configuration, or integration work needed to achieve the goal; identify source elements to remove, neutralize, or complete.
- **Completed functional behavior:** the useful player/developer goal and how input, triggers, or configuration lead to observable results. Include relevant state transitions for interactions or required visual/audio effects for presentation tasks.
- Necessary dependencies, edit freedom, and non-goals.
- Why the start remains runnable and the change forms an independent task.

Record these distinctions in the existing `start_state`, `target_state`, and `edit_scope` fields, with rationale in the design report. Judge scope by the actual development work and capability exercised, not instruction length, requirement/file counts, lines of code, operation counts, or the proportion of code removed. Node configuration, signal wiring, and focused behavior changes can be meaningful tasks. If the solution is effectively supplied and only a mechanical edit remains, redesign or reject the candidate. Cover necessary behavior and boundaries within the chosen goal; do not remove unrelated functionality or add adjacent features merely to enlarge the task.

Avoid broken imports as the task gap, duplicate answers in retained files, unnecessary whole-repo copies, trivial reskins, and dependence on another task's output. For addons, distinguish generic host setup from the target work. Estimate difficulty from reasoning/integration demands, not clicks or lines changed.

Compare candidates with each other and any supplied existing tasks by their goal, start-to-target gap, and acceptance requirements; merge substantive duplicates.

Record the README's `capabilities` profile: category, Godot operations, public multimodal inputs, and required inference. Node/Inspector tasks are welcome but not mandatory. Decorative assets alone do not establish multimodal reasoning; seek diversity across the dataset without per-repo quotas.

## 4. Define requirements and validation feasibility

Assign stable R IDs using every README requirement field: target/preservation kind, description, source evidence, acceptance condition, validation method, valid variations, and negative probe.

- Make completion explainable from the eventual instruction and public start. Require exact names, nodes, APIs, values, or formats only when justified by the task; disclose such constraints later.
- Prefer observable behavior; use structural checks for structural goals. Hidden cases may test the public contract, not add requirements.
- Plan startup, a single game instance, reset, input/observation, and termination. Specify relevant seeds, timing, tolerances, and rendering needs.
- Plan normal/edge cases and a targeted negative control for each target R, runnable where the tested property permits. Explain shared probes or necessary structural exceptions; plan a valid alternative where implementation freedom exists.
- Every required property needs a feasible executable check. Narrow or reject subjective goals that cannot be measured reliably. Public resources and documented interfaces must suffice to solve the task without reference access.

Design records the requirements; Construction writes the final instruction after building GT. Do not add a final `instruction` field to the spec.

## 5. Select and hand off

Use DESIGN_READY only when source revision, runtime evidence, meaningful scope and solver responsibility, runnable start plan, feasible target, and complete validation plan are established. Use BLOCKED for missing input/environment/evidence, or REJECTED for an unsuitable candidate; state the reason and reconsideration condition.

Write `schema_version=3`, initial `spec_revision=1`, and resolved source identity/revision/project selection into the spec. On semantic repairs, preserve unchanged IDs, increment the revision, record differences, and invalidate downstream acceptance evidence. Explain rejected alternatives and upstream deviations in the design report.

End with candidate IDs, status, capability/origin, output paths, and which may enter Construction. Do not report proposals as constructed tasks.

## Complete-feature scaling profile
Load the supplied quality-baseline skill reference. Before DESIGN_READY, record the actual input→state→existing dependency→visible outcome→lifecycle chain, with supplied/missing/solver-integration ownership. Compare semantic scope and integration gap with the existing registry, including same-source candidates. Do not enforce a file-count minimum, fill per-repository quotas, or infer runnable readiness from the static source bucket. Record a complete-feature difficulty hypothesis separately from empirical teacher/student results.

## Source-first reconstruction priority

Before selecting a repo-grounded extension, inspect the few nearest plausible upstream feature boundaries and record which were actually exercised. Prefer an independently meaningful verified reconstruction. If none is feasible, document the concrete reason and the proposed extension's integration and validation evidence. This is a preference, not an instruction to invent an ablation from unverified source behavior. Keep one-time source navigation in the repository brief and candidate registry for later same-repo tasks.
