#!/usr/bin/env python3
"""Kimi Code solver using an OpenAI-compatible K3 endpoint.

The CLI is driven through its JSON-RPC wire protocol so that tool use remains
fully agentic while token and cache usage are retained for benchmark accounting.
"""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import tempfile
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from gamedevbench.src.base_solver import BaseSolver
from gamedevbench.src.utils.data_types import SolverResult, TokenUsage


class KimiCodeSolver(BaseSolver):
    """Run Kimi Code headlessly against an experiment-scoped K3 API."""

    SUPPORTS_MCP = False
    SUPPORTS_SYSTEM_PROMPT = False
    SUPPORTS_EFFORT = False

    def __init__(
        self,
        timeout_seconds: Optional[int] = 600,
        debug: bool = False,
        use_mcp: bool = False,
        use_runtime_video: bool = False,
        model: Optional[str] = None,
    ):
        super().__init__(timeout_seconds, debug, use_mcp, use_runtime_video)
        self.model = model or "kimi-k3"

    @staticmethod
    def is_rate_limit_error(error_message: str) -> bool:
        lowered = error_message.lower()
        return any(
            marker in lowered
            for marker in (
                "rate limit",
                "rate_limit",
                "ratelimit",
                "quota exceeded",
                "too many requests",
                "status code 429",
                "http 429",
            )
        )

    @staticmethod
    def _coerce_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(path)

    @classmethod
    def _save_session_checkpoint(
        cls,
        checkpoint_dir: Path,
        *,
        session_id: str,
        model: str,
        timeout_seconds: Optional[int],
        duration_seconds: float,
        usage: TokenUsage,
        resumed: bool,
        status: str,
    ) -> None:
        """Mark the CLI session store as a durable experiment session."""
        share_dir = checkpoint_dir / "kimi_share"
        if not share_dir.is_dir() or share_dir.is_symlink():
            raise RuntimeError(
                "Kimi session checkpoint is missing its private session store"
            )
        cls._atomic_json(
            checkpoint_dir / "session.json",
            {
                "schema_version": 1,
                "status": status,
                "session_id": session_id,
                "model": model,
                "timeout_seconds": timeout_seconds,
                "duration_seconds": duration_seconds,
                "usage_lower_bound": usage.to_dict(),
                "resumed_from_checkpoint": resumed,
            },
        )
        ready = checkpoint_dir / "SESSION_READY"
        temporary = checkpoint_dir / f".SESSION_READY.{uuid.uuid4().hex}.tmp"
        temporary.write_text("ready\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(ready)

    @classmethod
    def _parse_wire(cls, raw_output: str) -> tuple[TokenUsage, str, bool, str]:
        """Return usage, final text, RPC success, and a terminal RPC error."""
        events: list[dict[str, Any]] = []
        completed = False
        rpc_error = ""
        buffer = ""

        def consume(candidate: str) -> None:
            nonlocal completed, rpc_error
            try:
                message = json.loads(candidate, strict=False)
            except json.JSONDecodeError:
                return
            if message.get("id") in {"1", 1}:
                if "result" in message:
                    result = message.get("result")
                    status = result.get("status") if isinstance(result, dict) else None
                    completed = status == "finished"
                    rpc_error = (
                        "" if completed else f"Kimi terminal status: {status or 'unknown'}"
                    )
                elif "error" in message:
                    completed = False
                    rpc_error = json.dumps(
                        message.get("error"), ensure_ascii=False
                    )[:1000]
            if message.get("method") == "event":
                params = message.get("params")
                if isinstance(params, dict):
                    events.append(params)

        for line in raw_output.splitlines():
            if line.lstrip().startswith('{"jsonrpc"'):
                if buffer:
                    consume(buffer)
                buffer = line
            elif buffer:
                # Tool output can contain literal control characters/newlines.
                buffer += "\n" + line
        if buffer:
            consume(buffer)

        scoped_events: list[tuple[str, dict[str, Any]]] = []

        def unwrap(event: dict[str, Any], scope: str) -> None:
            event_type = event.get("type")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            if event_type == "SubagentEvent":
                inner = payload.get("event")
                if isinstance(inner, dict):
                    child_id = str(
                        payload.get("agent_id")
                        or payload.get("parent_tool_call_id")
                        or "unknown"
                    )
                    unwrap(inner, f"{scope}/{child_id}")
                return
            scoped_events.append((scope, {"type": event_type, "payload": payload}))

        for event in events:
            unwrap(event, "root")

        # StatusUpdate contains the completed usage for one LLM message. Root
        # and subagent streams can interleave, so deduplicate by scope/message.
        step_number: defaultdict[str, int] = defaultdict(int)
        usage_records: dict[tuple[str, str], dict[str, Any]] = {}
        root_text: list[str] = []
        final_text = ""
        for scope, event in scoped_events:
            event_type = event["type"]
            payload = event["payload"]
            if event_type == "StepBegin":
                step_number[scope] += 1
                if scope == "root":
                    root_text = []
            elif event_type == "StepRetry":
                # Discard partial content from the failed streamed attempt.
                if scope == "root":
                    root_text = []
            elif event_type == "StatusUpdate":
                token_usage = payload.get("token_usage")
                if isinstance(token_usage, dict):
                    message_id = payload.get("message_id")
                    record_id = (
                        f"message:{message_id}"
                        if message_id
                        else f"step:{step_number[scope]}"
                    )
                    usage_records[(scope, record_id)] = token_usage
            elif event_type == "ContentPart" and scope == "root":
                if payload.get("type") == "text" and payload.get("text"):
                    root_text.append(str(payload["text"]))
            elif event_type == "TurnEnd" and scope == "root" and root_text:
                final_text = "".join(root_text)

        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        for token_usage in usage_records.values():
            other = cls._coerce_int(token_usage.get("input_other"))
            cache_read = cls._coerce_int(token_usage.get("input_cache_read"))
            cache_write = cls._coerce_int(
                token_usage.get("input_cache_creation")
            )
            output = cls._coerce_int(token_usage.get("output"))
            total_input += other + cache_read + cache_write
            total_output += output
            total_cache_read += cache_read
            total_cache_write += cache_write

        usage = TokenUsage(
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            cache_read_tokens=total_cache_read,
            cache_write_tokens=total_cache_write,
        )
        return usage, final_text, completed, rpc_error

    @staticmethod
    def _signal_process_group(
        process: subprocess.Popen[bytes], sig: signal.Signals
    ) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    @classmethod
    def _drain_and_reap(
        cls,
        process: subprocess.Popen[bytes],
        *,
        timed_out: bool,
    ) -> tuple[bytes, bytes]:
        """Close the wire cleanly, escalating only when the CLI will not exit."""
        if timed_out and process.poll() is None and process.stdin is not None:
            cancel_request = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "cancel",
                    "id": "cancel-1",
                    "params": None,
                },
                separators=(",", ":"),
            )
            try:
                process.stdin.write((cancel_request + "\n").encode("utf-8"))
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass

        if process.stdin is not None:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            # communicate() otherwise tries to flush the closed stream.
            process.stdin = None

        try:
            return process.communicate(timeout=10 if timed_out else 15)
        except subprocess.TimeoutExpired:
            pass

        for sig, wait_seconds in (
            (signal.SIGINT, 5),
            (signal.SIGTERM, 5),
            (signal.SIGKILL, 5),
        ):
            cls._signal_process_group(process, sig)
            try:
                return process.communicate(timeout=wait_seconds)
            except subprocess.TimeoutExpired:
                continue
        return b"", b""

    def _run_wire_attempt(
        self,
        *,
        cli: str,
        config_path: Path,
        prompt: str,
        environment: dict[str, str],
        deadline: Optional[float],
        session_id: str,
    ) -> tuple[bytes, bytes, bool, str, bool]:
        """Run one CLI session and return raw output plus its RPC terminal state."""
        initialize_request = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": "initialize-1",
                "params": {
                    "protocol_version": "1.10",
                    "client": {"name": "gamedevbench", "version": "1"},
                    "capabilities": {
                        "supports_question": False,
                        "supports_plan_mode": False,
                    },
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        prompt_request = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "prompt",
                "id": "1",
                "params": {"user_input": prompt},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        command = [
            cli,
            "--config-file",
            str(config_path),
            "--wire",
            "--yolo",
            "--afk",
            "--max-retries-per-step",
            "5",
            "--session",
            session_id,
        ]

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd(),
            env=environment,
            start_new_session=True,
        )
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        timed_out = False
        terminal_response = False
        completed_rpc = False
        live_rpc_error = ""
        prompt_sent = False
        selector: Optional[selectors.BaseSelector] = None
        try:
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            process.stdin.write((initialize_request + "\n").encode("utf-8"))
            process.stdin.flush()

            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ, stdout_chunks)
            selector.register(process.stderr, selectors.EVENT_READ, stderr_chunks)
            stdout_scan = b""

            while selector.get_map():
                if deadline is not None and time.monotonic() >= deadline:
                    timed_out = True
                    break
                ready = selector.select(timeout=0.5)
                if not ready and process.poll() is not None:
                    ready = [
                        (key, selectors.EVENT_READ)
                        for key in list(selector.get_map().values())
                    ]
                for key, _ in ready:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    target = key.data
                    target.append(chunk)
                    if target is stdout_chunks:
                        stdout_scan += chunk
                        while b"\n" in stdout_scan:
                            raw_line, stdout_scan = stdout_scan.split(b"\n", 1)
                            try:
                                candidate = json.loads(
                                    raw_line.decode("utf-8", errors="replace"),
                                    strict=False,
                                )
                            except json.JSONDecodeError:
                                continue
                            if candidate.get("id") == "initialize-1":
                                if "result" in candidate:
                                    if not prompt_sent:
                                        try:
                                            # Kimi has loaded the provider config by
                                            # initialization time. Remove the file
                                            # before any model-controlled tool runs.
                                            config_path.unlink(missing_ok=True)
                                            process.stdin.write(
                                                (prompt_request + "\n").encode(
                                                    "utf-8"
                                                )
                                            )
                                            process.stdin.flush()
                                            prompt_sent = True
                                        except (BrokenPipeError, OSError, ValueError) as error:
                                            terminal_response = True
                                            live_rpc_error = (
                                                "Kimi setup failed before prompt: "
                                                f"{error}"
                                            )
                                elif "error" in candidate:
                                    terminal_response = True
                                    live_rpc_error = "Kimi initialize failed: " + json.dumps(
                                        candidate.get("error"), ensure_ascii=False
                                    )[:1000]
                            if candidate.get("id") in {"1", 1} and (
                                "result" in candidate or "error" in candidate
                            ):
                                terminal_response = True
                                if "result" in candidate:
                                    result = candidate.get("result")
                                    status = (
                                        result.get("status")
                                        if isinstance(result, dict)
                                        else None
                                    )
                                    completed_rpc = status == "finished"
                                    if not completed_rpc:
                                        live_rpc_error = (
                                            "Kimi terminal status: "
                                            f"{status or 'unknown'}"
                                        )
                                else:
                                    live_rpc_error = json.dumps(
                                        candidate.get("error"), ensure_ascii=False
                                    )[:1000]
                                break
                    if terminal_response:
                        break
                if terminal_response:
                    break
        finally:
            if selector is not None:
                selector.close()
            tail_stdout, tail_stderr = self._drain_and_reap(
                process, timed_out=timed_out
            )
            config_path.unlink(missing_ok=True)
            if tail_stdout:
                stdout_chunks.append(tail_stdout)
            if tail_stderr:
                stderr_chunks.append(tail_stderr)

        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)
        _, _, parsed_complete, parsed_error = self._parse_wire(
            stdout.decode("utf-8", errors="replace")
        )
        return (
            stdout,
            stderr,
            completed_rpc or parsed_complete,
            live_rpc_error or parsed_error,
            timed_out,
        )

    @staticmethod
    def _is_transient_rpc_failure(error: str, stderr: str) -> bool:
        diagnostic = (error + "\n" + stderr).lower()
        return any(
            marker in diagnostic
            for marker in (
                "incomplete chunked read",
                "peer closed connection",
                "connection reset",
                "connection aborted",
                "server disconnected",
                "read timeout",
                "connect timeout",
                "network is unreachable",
                "temporary failure in name resolution",
                "remote protocol error",
                "api connection error",
                "api timeout error",
                "temporarily unavailable",
                "internal server error",
                "bad gateway",
                "service unavailable",
                "gateway timeout",
                "status code 500",
                "status code 502",
                "status code 503",
                "status code 504",
                "http 500",
                "http 502",
                "http 503",
                "http 504",
            )
        )

    def solve_task(self) -> SolverResult:
        config = self.load_config()
        if not config:
            return SolverResult(False, "Could not load task configuration", 0.0)

        api_key = os.environ.get("K3_API_KEY", "")
        base_url = os.environ.get("K3_BASE_URL", "").rstrip("/")
        cli = os.environ.get("GAMEDEVBENCH_KIMI_CLI", "kimi")
        if not api_key or not base_url:
            return SolverResult(
                False,
                "K3_API_KEY and K3_BASE_URL are required",
                0.0,
                model=self.model,
            )

        prompt = self.get_task_prompt(config) + (
            "\n\nExecution constraints for this benchmark run: do not start "
            "background processes. If you use the Agent tool, set "
            "run_in_background=false and wait for every subagent to finish "
            "before your final response. Ensure all requested files are written "
            "to the workspace and verify the implementation before finishing."
        )
        kimi_config = {
            "default_model": "model",
            "default_yolo": True,
            "default_thinking": True,
            "providers": {
                "gamedevbench": {
                    "type": "openai_legacy",
                    "base_url": base_url,
                    "api_key": api_key,
                }
            },
            "models": {
                "model": {
                    "provider": "gamedevbench",
                    "model": self.model,
                    "capabilities": ["image_in", "thinking"],
                    "max_context_size": int(
                        os.environ.get("KIMI_MODEL_MAX_CONTEXT_SIZE", "262144")
                    ),
                }
            },
        }

        start = time.monotonic()
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        timed_out = False

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="gdb-kimi-", delete=False
            ) as handle:
                json.dump(kimi_config, handle, ensure_ascii=False)
                config_path = Path(handle.name)
            config_path.chmod(0o600)

            environment = os.environ.copy()
            for key in (
                "OPENAI_API_KEY",
                "OPENAI_BASE_URL",
                "KIMI_API_KEY",
                "KIMI_BASE_URL",
                "K3_API_KEY",
                "K3_BASE_URL",
            ):
                environment.pop(key, None)
            checkpoint_value = os.environ.get(
                "GAMEDEVBENCH_KIMI_CHECKPOINT_DIR", ""
            ).strip()
            checkpoint_dir = Path(checkpoint_value) if checkpoint_value else None
            share_dir = (
                checkpoint_dir / "kimi_share"
                if checkpoint_dir is not None
                else Path.home() / ".kimi"
            )
            share_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            environment.update(
                {
                    "KIMI_MODEL_MAX_CONTEXT_SIZE": "262144",
                    "KIMI_SHARE_DIR": str(share_dir),
                    "CUDA_VISIBLE_DEVICES": "",
                    "NVIDIA_VISIBLE_DEVICES": "void",
                }
            )

            deadline = (
                start + self.timeout_seconds if self.timeout_seconds else None
            )
            completed_rpc = False
            rpc_error = ""
            last_attempt_diagnostic = ""
            interrupted_attempts = 0
            resume_session_id = os.environ.get(
                "GAMEDEVBENCH_KIMI_RESUME_SESSION_ID", ""
            ).strip()
            session_id = resume_session_id or uuid.uuid4().hex
            resumed_from_checkpoint = bool(resume_session_id)
            try:
                configured_attempts = int(
                    os.environ.get("KIMI_SESSION_ATTEMPTS", "2")
                )
            except ValueError:
                configured_attempts = 2
            max_session_attempts = min(8, max(1, configured_attempts))
            resume_prompt = (
                "Resume the original task from the existing context. Do not repeat "
                "completed inspection or planning; make a best-judgment "
                "implementation now. Your next tool action must write the requested "
                "project changes to /workspace. Then validate the project headlessly "
                "with GODOT_EXEC_PATH, fix any reported errors, and finish only after "
                "the changes are saved and validation succeeds."
            )

            for attempt in range(max_session_attempts):
                # Each resumed CLI process loads a fresh short-lived config.
                # It is unlinked immediately after the initialize handshake.
                config_path.write_text(
                    json.dumps(kimi_config, ensure_ascii=False),
                    encoding="utf-8",
                )
                config_path.chmod(0o600)
                attempt_prompt = (
                    prompt
                    if attempt == 0 and not resumed_from_checkpoint
                    else resume_prompt
                )
                attempt_stdout, attempt_stderr, attempt_ok, attempt_error, attempt_timeout = (
                    self._run_wire_attempt(
                        cli=cli,
                        config_path=config_path,
                        prompt=attempt_prompt,
                        environment=environment,
                        deadline=deadline,
                        session_id=session_id,
                    )
                )
                stdout_chunks.append(attempt_stdout)
                stderr_chunks.append(
                    f"\n[gamedevbench kimi session attempt {attempt + 1}/"
                    f"{max_session_attempts}]\n".encode("utf-8")
                    + attempt_stderr
                )
                completed_rpc = attempt_ok
                rpc_error = attempt_error
                last_attempt_diagnostic = attempt_stderr.decode(
                    "utf-8", errors="replace"
                )
                timed_out = attempt_timeout
                if completed_rpc or timed_out:
                    break
                if not self._is_transient_rpc_failure(
                    rpc_error, last_attempt_diagnostic
                ):
                    break
                interrupted_attempts += 1
                if attempt + 1 >= max_session_attempts:
                    break
                backoff = min(15.0, 2.0 ** attempt)
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    backoff = min(backoff, max(0.0, remaining))
                time.sleep(backoff)

            duration = time.monotonic() - start
            raw_stdout = b"\n".join(stdout_chunks).decode(
                "utf-8", errors="replace"
            )
            stderr = b"\n".join(stderr_chunks).decode(
                "utf-8", errors="replace"
            )
            if api_key:
                stderr = stderr.replace(api_key, "<redacted>")
            usage, final_text, parsed_complete, parsed_rpc_error = self._parse_wire(
                raw_stdout
            )
            completed_rpc = completed_rpc or parsed_complete
            rpc_error = "" if completed_rpc else rpc_error
            if api_key and rpc_error:
                rpc_error = rpc_error.replace(api_key, "<redacted>")
            has_usage = usage.total_tokens > 0
            internal_retries = raw_stdout.count(
                '"type":"StepRetry"'
            ) + raw_stdout.count(
                '"type": "StepRetry"'
            )
            usage_incomplete = (
                not completed_rpc
                or timed_out
                or interrupted_attempts > 0
                or internal_retries > 0
            )
            stdout = (
                raw_stdout.replace(api_key, "<redacted>")
                if api_key
                else raw_stdout
            )
            usage_note = ""
            if usage_incomplete:
                usage_note = (
                    " [usage_incomplete=true; reported token counts are lower "
                    f"bounds; interrupted_sessions={interrupted_attempts}; "
                    f"internal_step_retries={internal_retries}]"
                )

            if timed_out:
                message = f"Kimi Code execution timed out after {self.timeout_seconds}s"
            elif rpc_error:
                message = f"Kimi Code RPC failed: {rpc_error}"
            elif not completed_rpc:
                diagnostic = last_attempt_diagnostic.strip()[-1000:]
                if api_key and diagnostic:
                    diagnostic = diagnostic.replace(api_key, "<redacted>")
                message = "Kimi Code exited without a completed RPC response"
                if diagnostic:
                    message += f": {diagnostic}"
            else:
                message = final_text or "Task completed"
            message += usage_note
            if api_key:
                message = message.replace(api_key, "<redacted>")

            is_rate_limited = self.is_rate_limit_error(message + "\n" + stderr)
            is_infrastructure_error = is_rate_limited or (
                not completed_rpc
                and not timed_out
                and self._is_transient_rpc_failure(
                    rpc_error, last_attempt_diagnostic
                )
            )

            if checkpoint_dir is not None:
                self._save_session_checkpoint(
                    checkpoint_dir,
                    session_id=session_id,
                    model=self.model,
                    timeout_seconds=self.timeout_seconds,
                    duration_seconds=duration,
                    usage=usage,
                    resumed=resumed_from_checkpoint,
                    status=("timed_out_resumable" if timed_out else "completed" if completed_rpc else "interrupted"),
                )

            return SolverResult(
                success=completed_rpc and not timed_out,
                message=message,
                duration_seconds=duration,
                stdout=stdout,
                stderr=stderr,
                is_rate_limited=is_rate_limited,
                is_infrastructure_error=is_infrastructure_error,
                token_usage=usage if has_usage else None,
                model=self.model,
                # Pricing is intentionally not guessed; token classes are
                # recorded so the experiment can apply its actual contract.
                cost_usd=0.0,
            )
        except FileNotFoundError:
            return SolverResult(
                False,
                f"Kimi Code CLI not found: {cli}",
                time.monotonic() - start,
                model=self.model,
            )
        except Exception as error:
            message = f"Error invoking Kimi Code: {error}"
            return SolverResult(
                False,
                message,
                time.monotonic() - start,
                is_rate_limited=self.is_rate_limit_error(message),
                model=self.model,
            )
        finally:
            if "config_path" in locals():
                config_path.unlink(missing_ok=True)
