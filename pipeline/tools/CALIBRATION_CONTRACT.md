# Early fairness calibration in the continuing author session

This is an ordering checkpoint inside the existing author, not a new agent pipeline. Preserve complete-feature scope, existing valid evidence and all original counterexamples. Never edit original result/behavior files. Existing same-version executions can satisfy this checkpoint; do not rerun them merely to change the date or create a prescribed number of variants.

Before continuing an expensive full matrix, inspect the COMPLETE validator and helpers for six dependency categories: `discovery`, `fixtures`, `input_geometry`, `timing`, `lifecycle`, `aggregation`. For each actual high-risk assumption, state its public basis, allowed implementation variation and code location. Mark irrelevant categories N/A with a reason; not every category needs a new project. A challenge can cover several genuinely related assumptions. First establish why each variant meets or violates the public contract, then interpret its observed result. Reviewers still independently check these semantic claims.

Write `private/TASK/fairness_calibration.json` using this schema:

```json
{
  "schema_version": 1,
  "fingerprints": {"start":"...", "reference":"...", "grader":{}, "runner":"...", "entry":{}, "spec":"..."},
  "reference_run": "private/TASK/evidence/.../result.json",
  "start_baseline_run": "private/TASK/evidence/.../result.json",
  "start_full_run": "private/TASK/evidence/.../result.json",
  "assumption_audit": {
    "discovery": {"applicable":true,"reason":"Actual high-risk selector...","risk_ids":["object_lookup"]},
    "fixtures": {"applicable":false,"reason":"Concrete reason...","risk_ids":[]},
    "input_geometry": {"applicable":false,"reason":"Concrete reason...","risk_ids":[]},
    "timing": {"applicable":false,"reason":"Concrete reason...","risk_ids":[]},
    "lifecycle": {"applicable":false,"reason":"Concrete reason...","risk_ids":[]},
    "aggregation": {"applicable":false,"reason":"Concrete reason...","risk_ids":[]}
  },
  "risks": [{
    "id":"object_lookup",
    "category":"discovery",
    "code_locations":["validators/TASK/test.gd:100"],
    "public_R_ids":["R1"],
    "allowed_variation":"Concrete freedom in the public requirement",
    "legal":{"candidate":"scratch/...","run":"private/TASK/evidence/.../result.json","why_legal":"Actual behavior evidence and why this challenges the identified assumption"},
    "negative":{"candidate":"scratch/...","run":"private/TASK/evidence/.../result.json","why_invalid":"Specific publicly required behavior missing","expected_failed_checks":["actual_check_id"]}
  }],
  "open_blockers": []
}
```

Use `python3 BATCH/tools/fairness_check.py --run-root RUN --task TASK --fingerprint` for exact current bindings. Use the same command without `--fingerprint` to check the record. Baseline/reference/start and controls need complete current runner protocol, distinct real executions where appropriate, matching candidate/grader hashes and no execution errors counted as behavioral evidence. This checks evidence consistency, not universal validator fairness. Visual assumptions require actual applicable image inspection and remain part of final acceptance.

If a new legal implementation fails or a known faulty implementation passes, repair the relevant observer and its related callers, then recalibrate the affected assumptions before running the full matrix. A changed task/spec/grader invalidates this record; metadata-only reports do not. Preserve old evidence. If the matrix is already substantially complete, first map existing current evidence to this audit and run ONLY missing risk probes.

Tasks whose current author gate passed at the frozen migration snapshot may enter independent review without adding a new author form. Their exact bindings are host-recorded in calibration_exemptions.json. Independent review must audit the same assumptions. Any substantive candidate/spec/grader change invalidates this exemption and requires calibration.

After host-confirmed calibration, continue the remaining matrix, actual visual verification, protocol/export checks and the existing final pre-review gate. Do not endlessly invent variants after risks are covered and no new evidence indicates a gap.
