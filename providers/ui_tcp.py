# providers/ui_tcp.py
from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Dict, Optional

JSON = Dict[str, Any]


@dataclass
class UiTcpConfig:
    host: str = "127.0.0.1"
    port: int = 61888
    timeout_s: float = 3.0


class UiTcpBlenderProvider:
    """
    Provider that talks to a running Blender UI instance via the TCP bridge (ui_bridge_tcp.py).
    Protocol: newline-delimited JSON request/response.
    """

    def __init__(self, cfg: Optional[UiTcpConfig] = None):
        self.cfg = cfg or UiTcpConfig()
        self._snap_i = 0

    def _new_snapshot_id(self) -> str:
        self._snap_i += 1
        return f"U{self._snap_i}"

    def _send(self, method: str, params: Optional[JSON] = None) -> JSON:
        req = {"method": method, "params": params or {}}
        data = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")

        with socket.create_connection((self.cfg.host, self.cfg.port), timeout=self.cfg.timeout_s) as s:
            s.sendall(data)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk

        raw = buf.decode("utf-8", errors="replace").strip()
        if not raw:
            return {"ok": False, "error_type": "empty_response", "error_message": "UI bridge returned empty response."}

        try:
            obj = json.loads(raw)
        except Exception as e:
            return {"ok": False, "error_type": "json_decode", "error_message": str(e), "raw": raw}

        # Normalize to ok envelope (bridge already does, but keep safe)
        if isinstance(obj, dict) and "ok" not in obj:
            obj["ok"] = True
        return obj

    # ---- MCP-facing methods (underscore naming) ----

    def system_info(self) -> JSON:
        # UI bridge doesn't expose paths yet; keep minimal
        ping = self._send("ping", {})
        return {
            "ok": True,
            "provider": "ui_tcp",
            "host": self.cfg.host,
            "port": self.cfg.port,
            "blender": ping.get("blender"),
        }

    def world_health(self) -> JSON:
        ping = self._send("ping", {})
        return {"ok": bool(ping.get("ok")), "provider_ok": bool(ping.get("ok")), "details": ping}

    def world_reset(self, seed: int = 0) -> JSON:
        # seed ignored in UI bridge for now
        return self._send("world_reset", {"seed": seed})

    def world_observe(self, level: str = "compact") -> JSON:
        # level ignored in UI bridge for now
        return self._send("world_observe", {"level": level})

    def world_mutate(self, dsl_version: str, batch: Any) -> JSON:
        # not implemented on bridge yet; will return ok:false
        return self._send("world_mutate", {"dsl_version": dsl_version, "batch": batch})

    def world_observe_diff(self, from_id: str, to_id: str) -> JSON:
        # diff is server-side today in headless snapshot store; UI provider doesn't have snapshot ids yet
        return {"ok": False, "error_type": "not_supported", "error_message": "observe_diff not supported for ui_tcp provider yet."}

    def get_info(self) -> JSON:
        ping = self._send("ping", {})
        info = {
            "provider": "ui_tcp",
            "host": self.cfg.host,
            "port": self.cfg.port,
            "blender": ping.get("blender"),
        }
        if "ok" in ping:
            info["ok"] = bool(ping.get("ok"))
        else:
            info["ok"] = True
        return info

    def health(self) -> JSON:
        ping = self._send("ping", {})
        ok = bool(ping.get("ok"))
        return {"ok": ok, "provider_ok": ok, "details": ping}

    def call(self, tool_name: str, tool_args: JSON) -> JSON:
        if tool_name == "system_info":
            return self.get_info()
        if tool_name == "world_health":
            return self.health()
        if tool_name == "world_reset":
            seed = int(tool_args.get("seed", 0)) if isinstance(tool_args, dict) else 0
            out = self._send("world_reset", {"seed": seed})
            if "ok" not in out:
                out["ok"] = True
            if "snapshot_id" not in out:
                out["snapshot_id"] = self._new_snapshot_id()
            return out
        if tool_name == "world_observe":
            level = tool_args.get("level", "compact") if isinstance(tool_args, dict) else "compact"
            out = self._send("world_observe", {"level": level})
            if "ok" not in out:
                out["ok"] = True
            if "snapshot_id" not in out:
                out["snapshot_id"] = self._new_snapshot_id()
            return out
        if tool_name == "world_mutate":
            dsl_version = tool_args.get("dsl_version") if isinstance(tool_args, dict) else None
            batch = tool_args.get("batch") if isinstance(tool_args, dict) else None
            out = self._send("world_mutate", {"dsl_version": dsl_version, "batch": batch})
            if "ok" not in out:
                out["ok"] = True
            if "snapshot_id" not in out:
                out["snapshot_id"] = self._new_snapshot_id()
            return out
        if tool_name == "world_observe_diff":
            return {
                "ok": False,
                "error_type": "not_supported",
                "error_message": "observe_diff not supported for ui_tcp provider yet.",
            }
        return {"ok": False, "error_type": "unknown_tool", "error_message": f"Unknown tool: {tool_name}"}
