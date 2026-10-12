# Repo-only Godot task construction：仓库分配 + 三阶段 prompts


| 阶段                       | Prompt                                                     | 核心问题                           | 主要产物                                    |
| ------------------------ | ---------------------------------------------------------- | ------------------------------ | --------------------------------------- |
| 0. Repository allocation | [00_repository_allocation.md](00_repository_allocation.md) | 一次固定仓库并共享可运行入口、功能边界和题目分配       | allocation、repository brief、候选 slot     |
| 1. Design                | [01_design.md](01_design.md)                               | 从这个 repo 中能提出什么有价值、可完成、可验证的任务？ | repo 分析、候选清单、固定版本的任务规格                  |
| 2. Construction          | [02_construction.md](02_construction.md)                   | 如何将规格做成可运行、可测的任务？              | 参考实现、正式 instruction、起始项目、validator、执行证据 |
| 3. Review                | [03_review.md](03_review.md)                               | 任务与 validator 是否正确、公平、可验收？     | 独立复核、返修意见或验收及冻结清单                       |




## 设计依据与边界

A 同时承担了任务理解、构造 reference/start 和编写 validator；B 负责复核及修正。三阶段方案把 A 中依赖教程来确定目标的部分独立为 Design，其余构造工作仍放在 Construction，并强化 B 对需求与测试双向对应、合理替代解、执行证据的要求。**Validator 属于 Construction 的交付物，不需要再拆成第四个串行阶段。**

**Instruction 按 A 的方式在构造 GT 后编写。** Design 负责任务目标、起点/终点和验收要求，Construction 在实际 reference 基础上写正式公开指令，沿用 A 的六条写作原则。当前 Construction 顺序为：确认规格 → GT → instruction → starting point → validator → 验证。此处对齐 instruction 环节，starting point 与 validator 的先后顺序保持本方案现有安排。

只有 repo 时，需要补充的是“为什么选这个目标、起点缺什么、终点满足什么、如何判断完成”的设计决策。代码、文档和实际运行现象是证据；repo 当前行为不自动等于正确需求。默认先做经过运行确认的现有功能重建，也允许明确标注的 repo 内新功能扩展，但扩展必须额外证明可实现性。

保留原文的可运行 start、可通过 reference、自包含 instruction、需求与 validator 对应、证据记录。调整原文的教程依赖、强制 node/inspector 导向、按操作步数划分难度、默认仓库已筛选、每个 repo 强制产出多题等假设。允许代码、场景、交互、资源与游戏系统任务；多样性在整个数据集上控制，不为单个 repo 强凑题型。

对照 A/B 后，已补回具体的任务特征记录及模糊测试示例，并细化重建来源核对、输入资源完整性和模板复用要求。代表性交互对照等执行细化属于我们的适配，不表述为 GBD 原文已有的实验要求。

先用少量任务跑通三阶段，检查返修原因、validator 漏判/误判和任务覆盖，再扩量。

## 调度运行约定

通过 `launch.py` 调度时，同一个作者会话连续完成 Design、Construction 和返修；阶段文档中的停止或移交要求以宿主当前调用范围为准。Review 使用独立上下文，先阅读公开任务。模型、并发和预算以当前工作目录配置为准，不预设批次数量或节点布局。

- 只写分配的 `run_root`；源仓库、宿主代码和其他任务只按授权读取。持续保存 `checkpoint.md`，复用指纹一致的有效证据。
- Godot 调用使用 `$GODOT` 及随批次提供的 runtime；同题串行，引擎执行时取得槽位。排队超时属于基础设施问题，不能作为缺陷被成功检测的证据。保留 DISPLAY、XDG、LD_LIBRARY_PATH 和运行器所需环境；工具 shell 使用 `login:false`。
- 先完成 `tools/CALIBRATION_CONTRACT.md` 要求的公平性校准，再补齐稳定性矩阵。独立复核、宿主重放与冻结导出仍必须完成；作者不能自行给出独立 ACCEPTED。

## 使用方式

每次运行一个阶段时，提供本 README 的共同契约、该阶段 prompt 和明确的输入路径。Design 每次处理一个固定版本的 repo，并选择其中一个工程或插件集成范围；Construction、Review 每次处理一个任务。阶段切换依靠落盘产物，不依赖聊天历史。Review 使用新会话，先从公开任务重建验收标准，再读取私有 reference/tests；可以使用同一模型，但这不构成统计独立性或质量保证。

单 repo 调用示例（工作目录为仓库根目录 `Task_construction/`）：

```text
Read prompts/README.md and follow prompts/01_design.md.
REPO_PATH=/path/to/experiments/gamedevbench-upstream/repos/godotrecipes/2d_grid_movement
RUN_ROOT=/path/to/experiments/runs/godotrecipes__2d_grid_movement/run_001
PROJECT_SUBDIR=.
```

也可以继续传入已有的 `RUN_CONTEXT_PATH`，由其中的 `source_repo`、`run_root`、`project_subdir` 确定范围。Design 将直接输入和可核实的索引事实规范化为 `RUN_ROOT/run_context.json`；后两个阶段使用该文件并提供 `TASK_ID=...`。返修沿用同一任务及来源范围。上述输入行是给 agent 的文本参数；若转成 shell 命令，含空格路径需要引号。示例输出目录尚未创建。

源仓库由当前分配配置提供，以传入的固定版本 checkout 和 repository brief 为准。静态工程索引或 Git 检查不能代替 Godot 运行验证。Design prompt 规定了嵌套工程、多工程、插件仓库、稀疏检出和运行依赖的处理方式。

### 运行上下文

调用者可提供 `run_context.json`，也可先提供单 repo 的直接输入。Design 将解析后的规范副本保存到 `RUN_ROOT/run_context.json`，后续阶段使用该副本。可以补齐可从环境确认的事实；缺失的工程选择、运行环境等必要输入显式记录为未决项，允许先分析，不能编造或标记 ready。以下为完整上下文字段示意，尖括号必须替换，不能作为可执行配置使用：

```json
{
  "run_id": "<unique-run-id>",
  "run_root": "<absolute-authoring-directory>",
  "source_repo": "<absolute-upstream-repo-path>",
  "upstream_root": "<absolute-collection-root-or-null-for-standalone>",
  "repository_id": "<owner/repo-or-verified-source-identity>",
  "project_subdir": "<relative-project-directory-or-null-for-addon>",
  "source_revision": "<immutable-commit-or-snapshot-id>",
  "godot_binary": "<absolute-godot-binary-path>",
  "godot_version": "<verified-exact-version>",
  "runtime_profile": "<OS-renderer-display-physics-profile>",
  "max_tasks": 3,
  "instruction_language": "en",
  "timeouts_seconds": {"import": 120, "smoke": 60, "validation": 120},
  "stability_runs": 3,
  "max_revision_rounds": 2
}
```

- `max_tasks=3` 是未指定时的候选上限，不是配额；可以产出 0 个。
- `source_repo` 始终指 Git checkout 根目录；Godot 项目路径由它与 `project_subdir` 组合得到。插件无项目时 `project_subdir` 使用 JSON `null`，在 spec 中描述宿主方案。`upstream_root` 对独立 repo 可为 JSON `null`。源/输出路径不应嵌套；一个 run 不混合其他 repo 的题目或游戏实现。
- Godot 版本、图形环境及 agent 工具条件需要固定。若要求与 GameDevBench 运行环境兼容，以实际评测 checkout 和 runner 核实的版本为准，记录版本与来源；不为适配而静默迁移上游项目。无法运行的仓库先登记问题。
- 若已有验证过的通用骨架和 runner，可在上下文中提供 `project_template`、`validation_runner` 的路径及版本/摘要。它们应明确游戏/测试入口和运行约定，保持通用骨架；Construction 复用并核实，缺失时记录共享环境准备需求。共享评分入口与工作单工具由同批 pipeline_tools 提供；传入其实际路径和版本，不能只凭文档假定已安装。
- 以上超时是初始默认值；根据任务资源量显式配置。所有 Godot、导入、图形录制和验证调用必须有上限，测试内部不得无限等待。不得通过临时扩大单次预算来隐瞒不稳定性。



## 共同产物契约



### 目录与可见性

```text
RUN_ROOT/
  run_context.json
  repo_analysis.md
  candidate_registry.json
  tasks/TASK_ID/                   # 可向 solver 导出的唯一任务内容
    task_config.json               # 仅 task_id、name、instruction
    project.godot
    ...                           # 必要场景、脚本、资源、许可声明
  tasks_gt/TASK_ID/                # 私有：可运行参考实现
    project.godot
    ...
  validators/TASK_ID/              # 私有：唯一规范 validator 及宿主入口
    validate.py
    validator_manifest.json
    ...                           # GDScript、测试场景、必要测试数据
  private/TASK_ID/
    task_spec.json
    design_report.md
    construction_report.md
    provenance.json
    coverage.json
    evidence/
    review_report.json
    review_report.md
    release_manifest.json          # 仅 ACCEPTED 后生成
```

Design 创建规范运行上下文、repo 分析、候选清单、task_spec 和 design_report，不定稿公开 instruction。Construction 构造 GT 后在 `tasks/TASK_ID/task_config.json` 中编写正式 instruction；其余文件按阶段创建。试验、变异样本和导入缓存放在独立 scratch 工作区，不污染固定的 source/start/reference；用于验收的变异补丁、输入数据及重放命令另存到私有 evidence，保证清理 scratch 后仍能复现。

公开任务导出仅包含 instruction、starting project 和所需资源；GT、validator 和构题记录保持私有。按公开文件清单检查 symlink、备份、缓存及来源文档，避免夹带完整答案或依赖作者本地目录；保留必要运行资源、UID 文件和许可声明。

### `task_spec.json`：Design 的事实来源

至少包含以下字段；所有 ID 在阶段间保持稳定，所有路径相对固定的 source 或 RUN_ROOT，不能依赖临时目录：


| 字段                                                            | 内容                                                                                                                                                                        |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `schema_version`, `task_id`, `spec_revision`, `design_status` | 本版 schema 为 3，spec revision 初始为 1；Design 状态见下文                                                                                                                            |
| `name`                                                        | 任务名称；正式 instruction 由 Construction 写入公开 `task_config.json`，不在 Design spec 中重复维护                                                                                           |
| `source`                                                      | URL/来源、`repository_id`、固定 commit 或文件树摘要、与运行上下文一致的 `project_subdir`、实际引擎版本、复用文件与资源的许可记录                                                                                    |
| `task_origin`, `difficulty_rationale`                         | `verified_reconstruction` 或 `repo_grounded_extension`；难点与估计规模，不用点击数充当难度                                                                                                   |
| `capabilities`                                                | 对象：`primary`、`secondary`（列表）、`godot_operations`（列表）、`multimodal_inputs`（列表：模态、公开路径/观察入口及用途）、`multimodal_reasoning_required`（布尔）、`reasoning_evidence`（需要推断的信息及依据，或无需推断的理由） |
| `source_evidence`                                             | `E1...`：文件/节点/函数定位、观察日志；区分 `observed / documented / inferred / proposed`                                                                                                  |
| `start_state`, `target_state`, `edit_scope`                   | 已有内容、缺失目标、所需改变、必须保持的环境与功能、允许修改的文件/API；不要只给抽象标题                                                                                                                            |
| `requirements`                                                | `R1...`：`id`、`kind`（`target / preservation`）、`description`（作者侧需求描述）、`source_evidence_ids`、`acceptance`、`validation_method`、`valid_variations`、`negative_probe`            |
| `non_goals`, `assets`, `dependencies`                         | 明确边界、公开资源及引用方式、依赖闭包；无外部待下载答案                                                                                                                                              |
| `runtime`, `validation_plan`, `feasibility`                   | 固定环境、测试接入点及生命周期、可观测性/容差/随机种子方案、可实现性证据、风险及未决项                                                                                                                              |


`requirements[*].description` 和 `acceptance` 是 Design 的作者侧规格。Construction 在构造 GT 后将这些要求写成简洁、自包含的 instruction，并在 `coverage.json` 中记录 R ID 与正式公开文字的对应关系；不是逐字复制规格或公开测试过程。进入 Review 前，所有产品要求必须能从该 instruction 及其中明确引用的公开项目接口中推出。可以隐藏具体测试输入与实现，不能隐藏新的需求。精确节点路径、数值、文本格式和实现接口只有在任务确实需要时才能设为硬要求，并在指令中明确；否则测试应接受合理实现差异。

一个任务可以有多个有联系的要求，但必须构成一个可解释的游戏开发目标。`target` 描述需要补足的能力；`preservation` 描述明确列出的回归约束。不要要求未改动的整个上游游戏通过未声明的全面验收。

`capabilities` 用于数据集分析和审查，不增加隐藏评分要求。多模态输入可来自 instruction 附件、公开项目资产或可复现的运行观察，记录实际位置；有输入不等于必须进行多模态推理。Review 核实并在已有报告中记录，不为每道题强制配置多模态目标。

### Construction 的记录

- `provenance.json`：原始文件/资源到 start/reference 的映射、复制与改写原因、源版本、任务相关删除/修改清单、公开文件清单及必要许可信息。
- `coverage.json`：逐条 `R_id → 公开文字 → validator check_id/位置 → reference 证据 → start 预期 → 负例证据`；同时反向列出每个评分 assertion 对应的 R，不能有游离硬性检查。报告机制/超时等检查单列为非产品要求的运行完整性检查。
- `construction_report.md`：引用的 spec revision、状态、关键实现选择、所有实际运行命令及日志路径、未决问题、返修次数。
- `validator_manifest.json`：validator revision、绑定的 spec revision、测试文件清单、运行配置、必需 check IDs、每个 check 的 R IDs、固定随机种子、超时及适用容差。



### Validator 执行接口

本方案规定作者侧统一入口，由 Construction 实现或适配已有 runner；这不是对现有 GameDevBench CLI 的声明。优先复用同一个固定版本的通用运行器，每个任务只增加薄入口和任务 tests，避免让生成模型逐题重写超时、导入、隔离和结果解析代码。复用的运行器及依赖必须记录版本/摘要，纳入可复现清单。

```text
python validators/TASK_ID/validate.py --candidate /absolute/project --output-dir /absolute/fresh-result-dir
```

入口从自身清单读取固定运行配置，在一次性目录复制候选、导入、执行同一份规范 tests，并向独立结果目录写 `result.json`、命令/进程信息及日志。不得修改候选原件，不得使用 candidate 提供的 validator/运行配置，不得加载 reference 来替代实际观测；reference 与 start 都走相同入口。图形任务使用清单中声明的 display/renderer。

`--output-dir` 必须是新建或空目录，拒绝将旧结果当作本次执行结果。候选摘要基于导入前输入文件计算，明确缓存排除规则；测试入口不得复用候选的 `.godot` 缓存。

`result.json` 至少包括 `task_id`、`spec_revision`、`validator_revision`、`candidate_digest`、`status`、`checks`（check_id、R IDs、结果、观测和原因）、`execution`（命令、退出码、超时、Godot 版本、日志）。


| 状态 / 入口退出码    | 含义                                |
| ------------- | --------------------------------- |
| `PASS / 0`    | 必需检查全部执行且通过，报告完整，没有影响验收的候选运行错误    |
| `FAIL / 1`    | 候选违反公开要求，或候选自身不能正确导入/运行；注明具体原因    |
| `ERROR / 2`   | 环境、依赖、validator 或报告完整性失败，无法可靠判断候选 |
| `TIMEOUT / 3` | 导入、运行或测试超时，记录发生阶段；不能作为目标功能负例的证据   |


单项 check 使用 `PASS / FAIL / NOT_RUN`；有必需项未执行不能给整体 PASS。候选问题与环境/validator 问题区分不清时用 ERROR，禁止伪装成预期功能失败。

可以为兼容输出 `VALIDATION_PASSED/VALIDATION_FAILED`，但验收不能只搜索 stdout 中的关键词。宿主应检查完整的报告、执行情况与所有必需 check。测试文件从私有可信位置注入；候选伪造一行 PASS、提前退出或不执行测试均不能通过。这是报告完整性要求，不意味着同进程 GDScript 已构成对恶意候选的安全沙箱。

现有 GameDevBench 的 `tasks/`、`tasks_gt/`、`scripts/test.gd`、`scenes/test.tscn` 可作为兼容导出布局：在私有临时副本中注入 tests，再交给已核实的 runner。兼容导出不能成为第二套手工维护的 validator，也不能把 tests 复制进 solver 的公开任务。需以当前代码验证参数、测试场景路径和文件过滤行为，不能照抄 A/B 中旧 CLI 后宣称已兼容。

### 状态、返修与冻结

```text
Design:       DESIGN_READY | BLOCKED | REJECTED
Construction: READY_FOR_REVIEW | RETURN_TO_DESIGN | BLOCKED | REJECTED
Review:       ACCEPTED | RETURN_TO_CONSTRUCTION | RETURN_TO_DESIGN | BLOCKED | REJECTED
```

- `DESIGN_READY`：规格明确、源版本已确认、起点/终点可行、每项要求有验证计划；正式 instruction 尚待 Construction 编写，也未证明 task/validator 正确。
- `READY_FOR_REVIEW`：构造产物齐全，执行及负例证据满足 Construction 门槛，等待 Review。
- 设计目标、验收要求、允许解空间或任务来源变化：`RETURN_TO_DESIGN`，更新 spec revision。指令漏写/误述已有规格、代码、测试实现或打包修复：`RETURN_TO_CONSTRUCTION`。修改 instruction 后更新 coverage 并重新审查相关证据；不能为迁就现有 reference 私自改需求。冻结后的任何 instruction 修改仍需按下文重新验收和发布版本。
- `BLOCKED` 用于可以补齐的环境/输入/证据缺口；`REJECTED` 用于实际重复的任务、无有效任务目标或无法合理验收等。未决项不能写成通过。
- 每次外层返修记录差异和证据。`max_revision_rounds` 指独立 Review 返回后，允许再次执行 Construction → 独立 Review 的轮次数；首次 Construction → Review 不计作返修。Construction 内部调试/校准、validator revision 编号、供应商流重连和宿主中断恢复分别记录，不计作该外层次数，也不得借恢复调用重置已消耗的外层次数。宿主记录已用/剩余外层次数及各层自己的时限/重试上限，作者与审查者按该账本判断；缺少账本时记录计数不确定，不根据内部测试数自行宣称用户未授权。超过外层上限后保持 BLOCKED/REJECTED 并说明原因，不无休止重写或自动降低门槛。
- `ACCEPTED` 后冻结 spec、公开任务、reference、validator、运行上下文、coverage、provenance 和验收证据。`release_manifest.json` 列出 task ID、递增的 `release_revision`、spec/validator 版本、每个实际文件的 SHA-256、公开导出清单、审查结果和时间。排除可重建缓存及清单自身，且明确排除规则。验收后任何被记录内容变化都会使该冻结失效，必须重审并产生新版本。



## 批量构造约束

采用`../skills/godot-task-construction` 的固定快照。三个阶段保持不变；完整功能质量画像见 skill 的 `references/quality-baseline.md`。工作单工具必须实际嵌入主 skill 及阶段参考并记录内容摘要。`run_context.quality_profile` 指向使用的基线版本，`existing_task_registry` 指向已有合格/候选摘要；它们是宿主扩展字段，不改变 task_spec schema 3。

317 个静态优先源与已有 32 个源组成 349 个候选身份，不等于 349 个已运行项目。以 source_pool/unified_catalog.json 的实际复制和去重状态为准。每仓库最多 3 个实质不同的候选，可以为 0；500 以验收及冻结后的任务计数。本次试产 5 个，不自动启动全部 500 个或模型采样。

公开新增观察接口只允许提供状态/交互契约，不能提供目标算法；私有测试须通过真实输入及场景效果交叉验证。统计 instruction 同时计入其引用的强制公开契约。先完成任务质量，再单独校准教师/学生差距。

工作单和 gate 的实际命令见 ../pipeline_tools/README.md。gate 不接受仅填写 ACCEPTED 的自我声明，也不把 marker、旧输出、缺失检查、执行错误或未完成视觉复核算合格。人工审查属于证据，不能被机械 gate 自动证明其正确性。

## Qualification and evidence contract

Use the fixed runtime and validator entry provided with the working directory. Preserve task_spec schema 3 and the manifest, qualification, controls and review record formats. Do not implement a separate runner per task.

### Actual execution records

`qualification.json` retains the three lists `reference`, `start_baseline`, `start_full`. Each must contain at least three distinct run-relative `result.json` paths from independent executions, with distinct execution nonces. Repeating a path or copying one result to three directories does not satisfy stability. Keep each result's adjacent `behavior.json` and original logs. The batch runner automatically adds `nonce` to `result.json`; older results are compatible when the nonce exists in their adjacent behavior report and recorded validation command.

Reference uses `full/PASS`, start baseline uses `baseline/PASS`, and start full uses `full/FAIL` with an actual target check failing. Every control and the reference rendered run uses `full`. Mode-specific check IDs must match the manifest exactly, with no duplicates and no implicit skipped success. The manifest retains dictionary fields `checks` and `baseline_checks`; baseline check IDs are a subset of full IDs and use the same R mappings. If `required_check_ids` is present it must match `checks`.

The gate checks task/spec/validator/engine identity, candidate/grader/runner fingerprints, import and validation execution records, command mode/nonce, completion, raw behavior versus result check statuses, timeouts/errors and exit codes. Successful import is exit 0; validation is exit 0 for PASS and exit 1 for diagnosed FAIL. Missing execution, timeout, process crash, or malformed/incomplete report cannot count as an effective functional negative.

### Attributed negative coverage

Every public requirement in `task_spec.requirements`, including preserved behavior, needs effective negative coverage. `controls.json` retains its existing format:

- `kind` is `negative` or `legal`.
- A negative lists nonempty `R_ids` and `expected_failed_checks`.
- Coverage is credited only to the intersection of the control's declared R IDs and the manifest R IDs of expected checks that actually fail.
- Every R claimed by a negative must receive that attribution. Do not list an unrelated R merely because another expected check fails.
- More than one R may share a control/check when that failure actually establishes each behavioral defect; independent Review verifies this semantic claim.
- Keep at least one substantive legal control that passes the full validator. The gate counts records; independent Review determines whether the variation is legal and substantive.

No new mandatory control fields are introduced. Additional per-R evidence can be documented in existing coverage and construction/review reports. The contract does not demand one mutated project per requirement when a valid joint control demonstrates multiple violations.

### Review and evidence limits

Unresolved `blocker` and `major` findings reject qualification regardless of letter case or surrounding whitespace; resolved findings accept `resolved` case-insensitively. Existing independent-context, exact-fingerprint and rendered-image/visual-receipt checks remain in force.

These mechanical checks detect malformed, stale, incomplete or misattributed records. They do not prove that an observation tests public behavior, that a mutation isolates the intended defect, that a legal variation is substantive, or that the visual judgment is correct. Those remain independent Review obligations.
