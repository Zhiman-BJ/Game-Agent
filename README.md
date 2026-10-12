# Godot Task Forge

从真实 Godot 工程构造完整功能补全任务，提供构题 pipeline、skills、公平性校准、独立复核、并发调度，以及 K3/Qwen + Kimi Code 求解实验工具。

本仓库仅包含构题与实验代码，不包含任务集、游戏工程、素材、参考答案或实验输出。已有任务集通过外部路径接入；API 凭据和运行日志保存在独立工作目录。

## MCP

包括 **Godot 截图 MCP**（`godot-screenshot` 工具）和 **HTTP/stdio 桥接**，提供可安装命令、依赖与配置示例。

```bash
pip install -e '.[mcp,benchmark]'
export GODOT_EXEC_PATH=/absolute/path/to/godot
gamedevbench-mcp
# 或将已有 HTTP MCP 服务接到 stdio 客户端：
game-mcp-bridge --url http://127.0.0.1:6601/mcp
```

以上服务通过 MCP 客户端调用，直接启动会等待协议输入。详见 [MCP 安装与使用](docs/MCP.md)。Kimi Code 实验入口仍沿用原设置，未启用 MCP；发布 MCP 代码不代表改变已有实验配置。

## 构造流程

```text
固定仓库与版本、分配候选功能
                 ↓
功能设计 → reference / start / instruction / validator
                 ↓
前置公平性校准 → 稳定性验证矩阵
                 ↓
独立复核 → 原反例返修 → 宿主重放 → 冻结导出
```

一个作者持续完成一题的设计、构造和返修；复核使用独立上下文，先看公开任务。优先消融上游已经运行验证的完整功能；没有适合的独立功能时，才构造有依据且已验证可行的扩展。每题保留真实脚本、场景、资源、信号与生命周期之间的接入工作。

验收与公开 instruction 对齐。reference 必须通过，start 的基础行为必须正常且目标功能缺失；错误实现应被拒绝，合理替代实现应可通过。运行错误和超时不能算作成功检测缺陷。视觉要求需要实际查看当前候选的图片。

## 目录

| 目录 | 内容 |
|---|---|
| `pipeline/prompts/` | 仓库分配、设计、构造和独立复核 prompt |
| `pipeline/skills/godot-task-construction/` | 可单独安装的构题 skill |
| `pipeline/launch.py` | 构题的唯一启动及续跑入口 |
| `pipeline/tools/` | 批次调度、持续作者与独立复核、宿主重放和导出 |
| `pipeline/pipeline_tools/` | schema、指纹和冻结门槛 |
| `pipeline/runtime/` | Godot 执行、行为与视觉结果聚合 |
| `pipeline/host_tools/` | API relay、权限及矩阵恢复 |
| `scripts/` | 可移植配置与启动工具 |
| `experiments/kimicode/` | K3/Qwen + Kimi Code 隔离求解与轨迹记录 |
| `src/godot_task_forge_mcp/` | MCP HTTP/stdio 桥接（截图服务保留在 GameDevBench 目录） |
| `configs/mcp.*.example.json` | MCP 客户端配置模板 |
| `third_party/gamedevbench/` | 完整 benchmark runner、多个 agent 适配器与隔离运行工具 |

## 环境

构题与隔离求解使用 Linux、Python 3.10+、Git、Godot **4.4.1**、Xvfb、软件 OpenGL、`unshare`、`ip`，求解另需 Bubblewrap。安装支持 Responses provider、原生 session resume、图片工具及权限 profile 的 Codex CLI。首次使用必须通过随附的真实工具预检；CLI 不支持所需参数时应调整适配器，不能跳过预检。Kimi Code 使用独立安装的可执行文件。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GODOT_BIN=/absolute/path/to/godot
export CODEX_BIN=/absolute/path/to/codex
export TASK_PRIVATE_ROOT=/absolute/path/to/private-credentials
```

## 启动构题

1. 复制并编辑 `configs/batch.example.json`，填写模型、固定 commit 的干净仓库、每仓库候选数与 API relay 配置。候选配额不是合格保证；同源任务通过功能声明避免重复。
2. 启动只监听本机的 relay。凭据仅由宿主持有，不写入配置模板或作者工作区。

```bash
export PROVIDER_A_BASE_URL='https://your-provider.example/v1'
read -rs PROVIDER_A_API_KEY; export PROVIDER_A_API_KEY
python scripts/start_relay.py --private-root "$TASK_PRIVATE_ROOT" \
  --output /absolute/path/to/relay-logs --limit 16
```

第二、三路分别设置 `PROVIDER_B_*`、`PROVIDER_C_*`，并在 batch 配置添加对应 provider。

3. 在另一个终端创建全新工作目录。此操作固定输入、分配功能槽位，不请求模型。单批最多 128 个候选；多批使用不同工作目录和 task_prefix，并将已有功能目标填入仓库分配配置。

```bash
python scripts/prepare_batch.py --config configs/my-batch.json \
  --output /absolute/path/to/new-batch
```

4. 对配置的每一路执行初始预检和同会话恢复预检，再由宿主核对真实记录。预检会调用模型。

```bash
python /absolute/path/to/new-batch/tools/preflight_direct.py --provider a
python /absolute/path/to/new-batch/tools/resume_preflight.py --provider a --attempt 1
python /absolute/path/to/new-batch/tools/approve_preflight.py
python /absolute/path/to/new-batch/launch.py
```

成功构造的工程位于工作目录 `runs/<task_id>/tasks/`（start）、`tasks_gt/`（reference）及 `validators/`。公开求解包位于 `solver_packages/`；宿主将冻结回执写入 `accepted/`。这些是新实验的本地运行输出，不应将整个工作目录直接提交到代码仓库。

## 并发和恢复

API relay 按**实际请求**限流，任务调度另限制活跃作者；Godot 槽位覆盖引擎执行，不应覆盖整个验证矩阵。不同节点使用各自的 Godot 槽位目录；共享 API 限额时由同一 relay 控制总量。默认单路 16、Godot 32，可按资源调整。

设置工作目录 `control.json` 的 `pause_new: true` 可在调用边界暂停；保留当前会话、工程、指纹和有效证据。恢复前保留状态快照，针对具体基础设施故障或复核意见处理；不要重置失败记录或通过增加无限重试掩盖问题。`ACCEPTED`、`BLOCKED`、`INFRA_FAILED` 是不同结论。

续跑使用同一个工作目录，将 `pause_new` 改为 `false` 后再次执行 `launch.py`。已完成或终止的任务不会自动重开。新版本代码用于新建工作目录；已有批次保留其冻结的宿主代码，不能直接覆盖。

[详细流程](docs/PIPELINE.md) · [调度与恢复](pipeline/tools/SUPERVISION.md) · [求解与轨迹](experiments/kimicode/README.md)

## 代码结构与检查

调度层按职责分为四个模块：`scheduler.py` 负责分配与暂停恢复，`construction.py` 负责作者和独立复核，`replay.py` 负责最终重放，`host.py` 负责宿主进程、配置和冻结导出。只通过 `pipeline/launch.py` 启动，不需要选择历史版本的 supervisor 或额外叠加恢复脚本。

Kimi Code 求解入口和[完整 GameDevBench runner](third_party/gamedevbench/README.md) 独立保留，按需使用；构题无需加载其他 agent 适配器。求解时通过 `--dataset /absolute/path/to/dataset` 指定外部任务集。

```bash
python -m unittest discover -s tests -v
python -m compileall -q scripts pipeline experiments
```

这些离线检查覆盖工作目录准备、暂停与恢复、并发槽位和证据指纹绑定，不调用模型。真实 Codex、Godot 和渲染能力由启动前的预检验证。

## Skill

将 `pipeline/skills/godot-task-construction` 复制到自己的 skills 目录。按阶段加载参考，不必把所有历史材料塞入上下文。

## 许可证

原创代码、prompts 和 skills 使用 [Apache-2.0](LICENSE)。第三方组件保留各自许可证。外部游戏工程及素材的原有许可不因本仓库许可证而改变。
