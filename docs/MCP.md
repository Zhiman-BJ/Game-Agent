# MCP 工具

本仓库包含 Godot 截图 MCP 和 HTTP → stdio 工具桥接。后者连接使用者已有的 HTTP MCP 服务，本身不提供游戏编辑功能。

## 安装

在仓库根目录，使用 Python 3.10+：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[mcp,benchmark]'
```

采用 editable 安装后，CLI 可从任意目录启动；构题脚本仍从本仓库 checkout 运行。原创代码使用 Apache-2.0，GameDevBench 派生组件保留其 MIT 许可证。

## Godot 截图

源码：`third_party/gamedevbench/gamedevbench/src/mcp_server.py`。

客户端使用 `configs/mcp.stdio.example.json` 的 `mcpServers` 配置形式，将其中 Python 和 Godot 路径替换为真实绝对路径。不同客户端可能使用不同配置格式；命令和参数相同：

```bash
export GODOT_EXEC_PATH=/absolute/path/to/godot
python -m gamedevbench.src.mcp_server
# 等价安装入口：gamedevbench-mcp
```

唯一工具 `godot-screenshot` 接收 `project_dir`（含 `project.godot` 的目录），可选 `display`，返回压缩图片或错误说明。它打开 Godot **编辑器**截图，不负责操控游戏、运行 validator 或判定任务通过。

- Linux：需要 Godot、Xvfb、ffmpeg 及可用的渲染环境；服务为截图启动虚拟显示。
- macOS：使用 `osascript` 和 `screencapture`，需要系统屏幕录制权限。设置 `GODOT_SCREENSHOT_DISPLAY=1` 使用主屏；截图覆盖所选屏幕。

日志写入 stderr，stdout 只承载 MCP 协议。截图默认等待编辑器加载 8 秒；大型工程应结合实际加载情况验证截图内容。

## HTTP/stdio 桥接

源码：`src/godot_task_forge_mcp/http_stdio_bridge.py`。

```bash
game-mcp-bridge --url http://127.0.0.1:6601/mcp --timeout 60
# 可省略某些工具，并拒绝通过桥接调用它们：
game-mcp-bridge --url http://127.0.0.1:6601/mcp --exclude-tools tool_a,tool_b
```

客户端配置见 `configs/mcp.http-bridge.example.json`。如需请求头，从私有环境提供 `MCP_HTTP_HEADERS_JSON`（JSON 字符串对象），不要在已提交的配置中填写凭据。

桥接转发工具列表（含分页）和工具调用，保留 `structuredContent`、图片及 `isError`；每次操作建立并关闭远端会话。它不转发 resources、prompts、服务端通知、sampling，也不保证跨调用的远端会话状态。只对 localhost 绕过代理，远程地址保留用户代理配置。

## Agent 接入范围

完整 runner 保留各 agent 的 MCP 能力声明。Codex、Claude Code、Gemini 和 OpenHands 中的截图启动配置使用运行 runner 的 Python 解释器，需在该解释器环境安装本项目及 MCP extra。已有客户端配置不会自动被覆盖；原先使用 `uv run gamedevbench-mcp` 的配置可手动换成上述命令。

OpenCode 和 Mini SWE 仍需各自客户端配置。`experiments/kimicode/run.py` 的 Kimi Code 隔离实验入口保持 `use_mcp=False`，没有在此次整理中改变实验条件。CLI/SDK 应由使用者另外安装；保留适配器不代表已验证每一种外部客户端版本。

## 验证

```bash
python -m unittest discover -s tests -v
```

MCP 检查在安装 extra 后运行，覆盖 stdio 初始化、工具发现、输入错误处理，以及本地 HTTP 服务的转发、结构化输出和工具排除。它们不调用模型，也不替代 Godot 实机截图验收。
