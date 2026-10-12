# Host checkpoint protocol

Each long stage is resumable. Before repeating work, inspect the latest host checkpoint under `RUN_ROOT/host_checkpoints/TASK_ID/STAGE.json` and all existing artifacts. Do not discard a completed milestone because a later command timed out.

Use these milestone names and record them in `RUN_ROOT/private/TASK_ID/checkpoints/STAGE.json` after the corresponding evidence is actually written:

- Design: `baseline_and_candidate`, `spec_and_public_instruction`, `handoff`
- Construction: `baseline`, `implementation`, `calibration`, `qualification_matrix`, `visual_and_export`
- Review: `solver_first`, `independent_challenge`, `qualification_audit`, `visual_review`, `report`

The model checkpoint is a progress hint only. The host verifies artifact fingerprints and the mechanical gate; a claimed phase is never acceptance. On continuation, start at the first incomplete milestone, preserve old logs, and run only the affected checks before the required final matrix.

The host may terminate a stage after its bounded timeout. A timeout gets at most one continuation attempt using the checkpoint. A second timeout pauses the task for diagnosis instead of launching another full copy of the stage.
