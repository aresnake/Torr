# provider_headless.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

JSON = Dict[str, Any]


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


class HeadlessBlenderProvider:
    """
    Persistent headless Blender provider.
    Starts Blender once, keeps it alive, exchanges JSONL (1 request line -> 1 response line).
    """

    def __init__(self) -> None:
        self.blender_exe = self._resolve_blender_exe()
        self._proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._last_stderr_line: Optional[str] = None
        self._start_blender()

    def _resolve_blender_exe(self) -> str:
        be = os.environ.get("BLENDER_EXE")
        if be and os.path.exists(be):
            return be

        candidates = [
            r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
            r"D:\Blender_5.0.0_Portable\blender.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c

        raise FileNotFoundError("Blender executable not found. Set BLENDER_EXE env var to blender.exe")

    def _start_blender(self) -> None:
        if self._proc and self._proc.poll() is None:
            return

        root = Path(__file__).resolve().parents[1]
        bridge = str(root / "blender_bridge.py")
        cmd = [self.blender_exe, "-b", "--factory-startup", "--python", bridge, "--"]

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        assert self._proc.stdin and self._proc.stdout and self._proc.stderr

        # Drain stderr in background (avoid deadlocks; keep MCP stdout clean)
        def _drain_stderr(p: subprocess.Popen[str]) -> None:
            try:
                assert p.stderr
                for line in p.stderr:
                    line = line.rstrip("\n")
                    if line.strip():
                        self._last_stderr_line = line
                        eprint("[blender-stderr]", line)
            except Exception:
                pass

        threading.Thread(target=_drain_stderr, args=(self._proc,), daemon=True).start()

        # Handshake: first stdout line must be JSON
        ready = self._proc.stdout.readline().strip()
        if not ready:
            raise RuntimeError(
                f"Blender bridge did not send ready handshake. "
                f"raw_line={ready!r} bridge={bridge!r} last_stderr={self._last_stderr_line!r}"
            )
        try:
            obj = json.loads(ready)
        except Exception:
            raise RuntimeError(
                f"Blender bridge sent invalid JSON handshake. "
                f"raw_line={ready!r} bridge={bridge!r} last_stderr={self._last_stderr_line!r}"
            )
        if not obj.get("ok") or obj.get("type") != "bridge_ready":
            raise RuntimeError(f"Unexpected handshake from Blender: {obj}")

    def close(self) -> None:
        if not self._proc:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.kill()
        except Exception:
            pass
        self._proc = None

    def call(self, tool_name: str, tool_args: JSON) -> JSON:
        with self._lock:
            self._start_blender()
            assert self._proc and self._proc.stdin and self._proc.stdout

            req = {"tool": tool_name, "args": tool_args}

            try:
                self._proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except Exception as ex:
                eprint("Provider write failed, restarting Blender:", repr(ex))
                self.close()
                self._start_blender()
                assert self._proc and self._proc.stdin and self._proc.stdout
                self._proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()

            out_line = self._proc.stdout.readline().strip()
            if not out_line:
                code = self._proc.poll() if self._proc else None
                raise RuntimeError(f"Blender returned no output (exit={code}).")

            return json.loads(out_line)
