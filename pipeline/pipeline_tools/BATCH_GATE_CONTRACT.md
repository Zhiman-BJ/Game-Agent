# 128-task batch qualification contract

This batch copies the existing pipeline and runtime. It preserves task_spec schema 3 and the existing manifest, qualification, controls and review record shapes. `pipeline.py` is unchanged by this gate update. Use this batch's fixed runtime and validator entry; do not rewrite a separate runner per task.

## Actual execution records

`qualification.json` retains the three lists `reference`, `start_baseline`, `start_full`. Each must contain at least three distinct run-relative `result.json` paths from independent executions, with distinct execution nonces. Repeating a path or copying one result to three directories does not satisfy stability. Keep each result's adjacent `behavior.json` and original logs. The batch runner automatically adds `nonce` to `result.json`; older results are compatible when the nonce exists in their adjacent behavior report and recorded validation command.

Reference uses `full/PASS`, start baseline uses `baseline/PASS`, and start full uses `full/FAIL` with an actual target check failing. Every control and the reference rendered run uses `full`. Mode-specific check IDs must match the manifest exactly, with no duplicates and no implicit skipped success. The manifest retains dictionary fields `checks` and `baseline_checks`; baseline check IDs are a subset of full IDs and use the same R mappings. If `required_check_ids` is present it must match `checks`.

The gate checks task/spec/validator/engine identity, candidate/grader/runner fingerprints, import and validation execution records, command mode/nonce, completion, raw behavior versus result check statuses, timeouts/errors and exit codes. Successful import is exit 0; validation is exit 0 for PASS and exit 1 for diagnosed FAIL. Missing execution, timeout, process crash, or malformed/incomplete report cannot count as an effective functional negative.

## Attributed negative coverage

Every public requirement in `task_spec.requirements`, including preserved behavior, needs effective negative coverage. `controls.json` retains its existing format:

- `kind` is `negative` or `legal`.
- A negative lists nonempty `R_ids` and `expected_failed_checks`.
- Coverage is credited only to the intersection of the control's declared R IDs and the manifest R IDs of expected checks that actually fail.
- Every R claimed by a negative must receive that attribution. Do not list an unrelated R merely because another expected check fails.
- More than one R may share a control/check when that failure actually establishes each behavioral defect; independent Review verifies this semantic claim.
- Keep at least one substantive legal control that passes the full validator. The gate counts records; independent Review determines whether the variation is legal and substantive.

No new mandatory control fields are introduced. Additional per-R evidence can be documented in existing coverage and construction/review reports. The contract does not demand one mutated project per requirement when a valid joint control demonstrates multiple violations.

## Review and evidence limits

Unresolved `blocker` and `major` findings reject qualification regardless of letter case or surrounding whitespace; resolved findings accept `resolved` case-insensitively. Existing independent-context, exact-fingerprint and rendered-image/visual-receipt checks remain in force.

These mechanical checks detect malformed, stale, incomplete or misattributed records. They do not prove that an observation tests public behavior, that a mutation isolates the intended defect, that a legal variation is substantive, or that the visual judgment is correct. Those remain independent Review obligations.

## Verification performed

`python3 -m unittest discover -s tests -v` passes 16 synthetic protocol regression tests, including complete and legacy-compatible acceptance and rejection of duplicated evidence, missing preservation controls, unrelated-R credit, uppercase unresolved blockers, skipped/missing checks, wrong modes, wrong revisions, missing stages and contradictory exit codes/nonces. These fixtures patch fingerprint discovery and visual combination so they test host protocol aggregation only; they do not claim Godot gameplay or visual validation.

A read-only pre-review diagnostic on the existing pilot `sc0001` found only the expected newly enforced missing `P1` preserved-behavior negative. No old artifact or record was changed, and no old Godot workload was rerun.
