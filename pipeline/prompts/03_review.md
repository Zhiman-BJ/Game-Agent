# Stage 3 — Review and refine the task

Audit one constructed task using the evidence-based checks below. Read the accompanying `README.md` before execution; its shared contracts are required inputs. Use a fresh session; if you built the task in this session, record the limitation and request a fresh review handoff. Builder reports are claims to verify.

## Inputs and outputs

Inputs: `RUN_CONTEXT_PATH`, `TASK_ID`, public task, spec, source/provenance, GT, validator, and Construction evidence. Require READY_FOR_REVIEW for the current versions.

Write private `review_report.md` and `review_report.json`. Record a verdict and evidence for every check below. Only ACCEPTED tasks receive `release_manifest.json`.

## 1. Read as a solver first

Before private tests, GT, or claimed coverage, read the public instruction/start and record:

- Required result, available scaffolding/assets/controls, and retained behavior.
- Necessary node/API/numeric/format constraints, edit freedom, and non-goals.
- Ambiguities and reasonable alternative solutions.

Check the instruction principles: concise, clear, unambiguous, self-contained; sufficient without tests/GT; technical requirements without usage details; no hints, tips, test commands, code examples, or references to tests, transcripts, tutorials, or other tasks. The goal must exercise meaningful game-development work.

## 2. Check source and task fidelity

- [ ] Public requirements agree with the spec and canonical `task_config.json`; coverage refers to its exact wording.
- [ ] Source snapshot, file/asset provenance, and runtime match the current records.
- [ ] Reconstruction preserves the selected upstream behavior with documented deviations; extensions have explicit design and implemented feasibility evidence.
- [ ] The actual start and target satisfy Design's functional-completeness rule: the solver must implement the feature's core mechanisms and necessary integration. An insufficient planned gap returns to Design; a start that supplies work the spec assigns to the solver returns to Construction.
- [ ] Capability labels match actual work. Distinguish multimodal input from required multimodal reasoning; do not impose modality quotas.

## 3. Check every assertion against the instruction

Read all verdict-affecting tests, fixtures, helpers, tolerances, and result parsing. For EVERY assertion, record its check ID/location, R IDs, exact supporting public text/interface, measured property, and possible false acceptance/rejection.

- [ ] Every public requirement is exercised; every scoring assertion follows from a public requirement.
- [ ] Exact strings, padding, delimiters, number formats, comparison boundaries, node paths/types, signals, and property values are specified wherever required by tests.
- [ ] Tests accept reasonable alternative solutions and do not require private reference details.
- [ ] Behavioral checks exercise actual transitions/effects, not only node/method existence or unreachable synthetic state. Check reset, constant-output loopholes, and relevant physics/rendering conditions.
- [ ] Required checks actually run; setup failure, skipped checks, or exceptions cannot produce PASS. The runner loads canonical tests, without GT substitution or duplicate game instances.

Examples of ambiguous and justified checks:

- “Display progress” does not specify zero-padding or an exact delimiter.
- An explicit rectangle-size formula justifies checking that relationship with appropriate numerical tolerance.
- “Connect manager signals” does not specify an undisclosed list of signal names.

Fix omitted wording for existing requirements or loosen an unjustified test restriction. New requirements return to Design; do not copy arbitrary GT internals into the instruction.

## 4. Rerun and challenge

Use clean workspaces and the documented validator, saving commands, runtime, candidate hashes, check results, and logs under separate review evidence.

- [ ] **Start:** import/launch succeeds; validation FAIL reflects the target gap, with preservation intact.
- [ ] **GT:** import, representative gameplay/visual/audio inspection, and all required checks PASS.
- [ ] **Controls:** reproduce builder negatives and valid alternatives. Every target R has an executed, meaningful negative control; verify samples actually violate/satisfy the contract.
- [ ] **New challenge:** add at least one plausible task-specific negative or boundary probe; state its expected outcome before execution.
- [ ] **False rejection:** independently select or inspect and run a meaningful valid variation where implementation freedom exists.
- [ ] **Integrity:** marker-only output, early termination, missing reports, and stale results cannot yield success.
- [ ] **Stability:** repeat clean start/GT checks for `stability_runs`, keeping cases, seeds, and runtime fixed; resolve inconsistencies.
- [ ] **Public export:** run the actual exported files; check dependencies, source paths, symlinks, caches, and private-answer leakage.

Inspect visual/audio evidence when relevant; a headless exit code is insufficient. Finite probes do not prove complete coverage. Unreliably measurable required properties need redesign. An optional solver pilot using only public task files may expose ambiguity; later revisions invalidate pilot evidence for the changed task.

## 5. Refine and decide

- **RETURN_TO_CONSTRUCTION:** sound spec, defective wording/code/tests/packaging/evidence. Give affected R/check IDs, reproduction, expected/actual results, and repair target.
- **RETURN_TO_DESIGN:** goals, acceptance, allowed solutions, selected source/feature, or feasibility must change.
- **BLOCKED:** missing input, environment, or evidence; state what is needed.
- **REJECTED:** trivial/duplicate task or unsuitable objective. Demonstrate duplication through the goal, start-to-target gap, and acceptance requirements.
- **ACCEPTED:** all required checks pass on the final unchanged versions, with no unresolved findings.

Small in-scope review fixes are allowed: log authorship/patches, update coverage and relevant revisions, invalidate old evidence, and rerun full start/GT plus affected controls/export checks. Substantive gameplay/validator rewrites return to Construction for fresh Review; semantic changes return to Design. Recheck corrected instructions before acceptance. Respect the host-recorded outer revision limit as defined in README; internal calibration loops and validator revision numbers do not consume it. Preserve the consumed count across transport recovery. Do not infer missing user authorization from those internal counts, and do not weaken requirements to pass.

## 6. Record and freeze

The JSON report contains `task_id`, `spec_revision`, `validator_revision`, `status`, `review_session`, `gates`, `findings`, `executions`, `changes`, `limitations`, and `next_action`. Findings include severity, affected paths/R/check IDs, evidence, expected/actual behavior, and resolution/routing. Markdown summarizes the same decision.

For ACCEPTED only, generate and verify the README's release manifest after all edits, with versioned hashes and export allowlist. Later task changes require renewed review and a new release revision.

End with status, findings, evidence paths, and next action. Report only observed execution results.

## Scaling release guard
Load the supplied quality-baseline reference. Use a genuinely fresh authoring context and record its identity. First record a solver-only reading of the public package; then inspect private evidence. Independently add a targeted counterexample and a meaningful allowed implementation variant where needed. Check exported bytes, controls, observations and final runner/grader fingerprints. Invoke the mechanical gate before freeze. A passed gate verifies recorded consistency, not semantic completeness: unresolved visible defects, hidden requirements, source leakage or trivial feature gaps still reject the task. Report uncalibrated difficulty explicitly.


## Execution records and isolation
Run concurrent mouse/keyboard/window-focus checks on separate displays, or serialize them on one display. One display per author does not isolate multiple interactive games launched within that author. Preserve initial failures and diagnose interference before assigning a gameplay verdict. Execute repeatable matrices with scripts and save full evidence to files; return concise check summaries, loading detailed logs only when needed. Report instruction-body word count plus all mandatory referenced public text. Condense repeated wording where useful without hiding or removing required behavior or imposing a word-count acceptance quota.
