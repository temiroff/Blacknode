"""End-to-end dry run for the learned-nodes launch demo.

The script starts the editor backend when needed, connects to the real MCP
stdio server, creates a temporary learned RSS parser node, verifies the editor
sees it, runs a workflow that uses it, and deletes the node.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from queue import Empty, Queue
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR_URL = "http://127.0.0.1:7777"
TIMEOUT_SECONDS = 30

PARSE_RSS_CODE = """import feedparser


def run(feed):
    parsed = feedparser.parse(feed)
    entries = []
    for entry in parsed.entries:
        entries.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
        })
    return {"entries": entries}
"""

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Blacknode Demo Feed</title>
    <item>
      <title>Learned nodes appear live</title>
      <link>https://example.com/learned-nodes</link>
    </item>
  </channel>
</rss>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo_dry_run.py")
    parser.add_argument("--node-name", default="ParseRSSDryRun")
    args = parser.parse_args(argv)

    env = _demo_env()
    backend = None
    mcp = None
    stdout_q: Queue[str] = Queue()
    stderr_q: Queue[str] = Queue()
    created = False
    node_name = args.node_name

    try:
        if not _url_ok(f"{EDITOR_URL}/learned-nodes"):
            backend = _start_editor_backend(env)
            _wait_for_url(f"{EDITOR_URL}/learned-nodes", timeout=TIMEOUT_SECONDS)
            print("[demo] editor backend started")
        else:
            print("[demo] editor backend already running")

        mcp = _start_mcp(env, stdout_q, stderr_q)
        _mcp_initialize(mcp, stdout_q)
        print("[demo] MCP server connected")

        node_name = _available_node_name(args.node_name)
        create_result = _call_tool(
            mcp,
            stdout_q,
            "create_node_type",
            {
                "name": node_name,
                "description": "Parse RSS XML text into a list of entry dictionaries.",
                "inputs": ["feed:Text"],
                "outputs": ["entries:List"],
                "code": PARSE_RSS_CODE,
                "requires_network": False,
            },
            request_id=10,
        )
        if create_result.get("status") != "created":
            raise RuntimeError(f"create_node_type failed: {create_result}")
        created = True
        print(f"[demo] learned node created: {node_name}")

        _wait_for_learned_node(node_name, timeout=2.0)
        print("[demo] editor /learned-nodes sees the new node")

        workflow = _build_workflow(mcp, stdout_q, node_name)
        run_result = _call_tool(
            mcp,
            stdout_q,
            "run_workflow",
            {"workflow": workflow},
            request_id=30,
            timeout=TIMEOUT_SECONDS,
        )
        if run_result.get("ok") is False:
            raise RuntimeError(f"workflow run failed: {run_result}")
        value = run_result.get("value")
        if not isinstance(value, list) or not value or value[0].get("title") != "Learned nodes appear live":
            raise RuntimeError(f"workflow returned unexpected value: {value!r}")
        print("[demo] workflow ran through Docker-backed learned node")

        return 0
    except Exception as exc:
        print(f"[demo] FAIL: {exc}", file=sys.stderr)
        _drain_stderr(stderr_q)
        return 1
    finally:
        if created and mcp is not None:
            try:
                _call_tool(
                    mcp,
                    stdout_q,
                    "delete_learned_node",
                    {"name": node_name, "confirm": True},
                    request_id=90,
                    timeout=10,
                )
            except Exception:
                pass
        _terminate_process(mcp)
        _terminate_process(backend)


def _demo_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "python")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else os.pathsep.join([pythonpath, existing])
    env["BLACKNODE_EDITOR_URL"] = EDITOR_URL
    env["BLACKNODE_LEARNED_NODES_CONSENT"] = "1"
    env.setdefault("BLACKNODE_CONFIG_DIR", str(Path(tempfile.gettempdir()) / "blacknode-demo-dry-run"))
    env.setdefault("BLACKNODE_MCP_QUIET", "1")
    return env


def _start_editor_backend(env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "7777"],
        cwd=str(ROOT / "editor-server"),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _start_mcp(env: dict[str, str], stdout_q: Queue[str], stderr_q: Queue[str]) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        [sys.executable, "-m", "blacknode.cli", "mcp"],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding="utf-8",
    )
    threading.Thread(target=_reader_thread, args=(proc.stdout, stdout_q), daemon=True).start()
    threading.Thread(target=_reader_thread, args=(proc.stderr, stderr_q), daemon=True).start()
    return proc


def _reader_thread(stream: Any, q: Queue[str]) -> None:
    if stream is None:
        return
    for line in iter(stream.readline, ""):
        if line:
            q.put(line)
    stream.close()


def _mcp_initialize(proc: subprocess.Popen[str], stdout_q: Queue[str]) -> None:
    _send(proc, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "blacknode-learned-demo-dry-run", "version": "1.0"},
        },
    })
    response = _recv(stdout_q, expect_id=1)
    if response.get("error"):
        raise RuntimeError(response["error"])
    _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})


def _call_tool(
    proc: subprocess.Popen[str],
    stdout_q: Queue[str],
    name: str,
    arguments: dict[str, Any],
    *,
    request_id: int,
    timeout: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    _send(proc, {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    response = _recv(stdout_q, expect_id=request_id, timeout=timeout)
    if response.get("error"):
        raise RuntimeError(response["error"])
    content = response.get("result", {}).get("content", [])
    for item in content:
        if item.get("type") == "text":
            return json.loads(item["text"])
    raise RuntimeError(f"{name} returned no JSON text content: {content}")


def _send(proc: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    if proc.stdin is None:
        raise RuntimeError("MCP server stdin is unavailable")
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _recv(q: Queue[str], *, expect_id: int, timeout: float = TIMEOUT_SECONDS) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = q.get(timeout=0.2)
        except Empty:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == expect_id:
            return msg
    raise TimeoutError(f"timed out waiting for MCP response id={expect_id}")


def _build_workflow(proc: subprocess.Popen[str], stdout_q: Queue[str], node_name: str) -> dict[str, Any]:
    workflow = _call_tool(proc, stdout_q, "create_workflow", {"name": "Learned Nodes Demo Dry Run"}, request_id=20)
    workflow = _call_tool(
        proc,
        stdout_q,
        "add_node",
        {"workflow": workflow, "type_name": "Text", "params": {"value": SAMPLE_RSS}, "node_id": "feed"},
        request_id=21,
    )["workflow"]
    workflow = _call_tool(
        proc,
        stdout_q,
        "add_node",
        {"workflow": workflow, "type_name": node_name, "node_id": "parse"},
        request_id=22,
    )["workflow"]
    workflow = _call_tool(
        proc,
        stdout_q,
        "connect_nodes",
        {"workflow": workflow, "from_node": "feed", "from_port": "value", "to_node": "parse", "to_port": "feed"},
        request_id=23,
    )["workflow"]
    workflow = _call_tool(
        proc,
        stdout_q,
        "connect_nodes",
        {"workflow": workflow, "from_node": "parse", "from_port": "entries", "to_node": "out", "to_port": "value"},
        request_id=24,
    )["workflow"]
    return workflow


def _wait_for_learned_node(name: str, *, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = _get_json(f"{EDITOR_URL}/learned-nodes")
        names = {item.get("name") for item in body.get("nodes", [])}
        if name in names:
            return
        time.sleep(0.1)
    raise TimeoutError(f"{name} did not appear in /learned-nodes within {timeout:.1f}s")


def _available_node_name(base: str) -> str:
    body = _get_json(f"{EDITOR_URL}/learned-nodes")
    names = {item.get("name") for item in body.get("nodes", [])}
    if base not in names:
        return base
    suffix = int(time.time()) % 100000
    candidate = f"{base}{suffix}"
    if len(candidate) > 40:
        candidate = f"ParseRSS{suffix}"
    return candidate


def _url_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1):
            return True
    except Exception:
        return False


def _wait_for_url(url: str, *, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _url_ok(url):
            return
        time.sleep(0.25)
    raise TimeoutError(f"{url} did not become ready")


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=3) as res:
        return json.loads(res.read().decode("utf-8"))


def _drain_stderr(q: Queue[str]) -> None:
    lines = []
    while not q.empty():
        try:
            lines.append(q.get_nowait())
        except Empty:
            break
    if lines:
        print("[demo] MCP stderr:", file=sys.stderr)
        for line in lines[-20:]:
            print(f"  {line.rstrip()}", file=sys.stderr)


def _terminate_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


if __name__ == "__main__":
    sys.exit(main())
