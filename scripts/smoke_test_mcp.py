"""End-to-end smoke test for the Blacknode MCP server.

Spawns ``blacknode mcp`` as a subprocess, performs the MCP handshake,
lists tools, and calls ``list_nodes`` to confirm the server is healthy.
Exits 0 on success, 1 on failure. Prints a concise report.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from queue import Empty, Queue


CMD = ["blacknode", "mcp"]
TIMEOUT_S = 15


def reader_thread(stream, q: Queue):
    for line in iter(stream.readline, ""):
        if line:
            q.put(line)
    stream.close()


def send(proc, payload):
    line = json.dumps(payload) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()


def recv(q: Queue, expect_id=None, timeout=TIMEOUT_S):
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
        if expect_id is None or msg.get("id") == expect_id:
            return msg
    raise TimeoutError(f"timed out waiting for id={expect_id}")


def main() -> int:
    print(f"[smoke] launching: {' '.join(CMD)}")
    try:
        proc = subprocess.Popen(
            CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
        )
    except FileNotFoundError:
        print("[smoke] FAIL: 'blacknode' CLI not found on PATH")
        print("        Run: pip install -e .")
        return 1

    stdout_q: Queue[str] = Queue()
    stderr_q: Queue[str] = Queue()
    threading.Thread(target=reader_thread, args=(proc.stdout, stdout_q), daemon=True).start()
    threading.Thread(target=reader_thread, args=(proc.stderr, stderr_q), daemon=True).start()

    try:
        # 1. initialize
        send(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "blacknode-smoke", "version": "1.0"},
            },
        })
        init_resp = recv(stdout_q, expect_id=1)
        if "error" in init_resp:
            print(f"[smoke] FAIL: initialize returned error: {init_resp['error']}")
            return 1
        server_info = init_resp.get("result", {}).get("serverInfo", {})
        print(f"[smoke] connected to: {server_info.get('name', '?')} v{server_info.get('version', '?')}")

        # 2. initialized notification (no id)
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3. tools/list
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools_resp = recv(stdout_q, expect_id=2)
        if "error" in tools_resp:
            print(f"[smoke] FAIL: tools/list returned error: {tools_resp['error']}")
            return 1
        tools = tools_resp.get("result", {}).get("tools", [])
        names = sorted(t["name"] for t in tools)
        print(f"[smoke] tools/list returned {len(tools)} tools: {', '.join(names)}")

        expected = {
            "list_nodes", "get_node_schema", "list_templates",
            "load_workflow", "create_workflow", "add_node",
            "connect_nodes", "validate_workflow", "run_workflow",
            "export_python", "create_editor_workflow_tab",
            "open_workflow_in_editor_tab", "cook_editor_node",
        }
        missing = expected - set(names)
        if missing:
            print(f"[smoke] FAIL: missing expected tools: {sorted(missing)}")
            return 1

        # 4. call list_nodes
        send(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_nodes", "arguments": {}},
        })
        call_resp = recv(stdout_q, expect_id=3)
        if "error" in call_resp:
            print(f"[smoke] FAIL: list_nodes call returned error: {call_resp['error']}")
            return 1
        content = call_resp.get("result", {}).get("content", [])
        # FastMCP wraps the dict result as a TextContent with JSON
        body = None
        for item in content:
            if item.get("type") == "text":
                try:
                    body = json.loads(item["text"])
                    break
                except json.JSONDecodeError:
                    continue
        if not body:
            print(f"[smoke] FAIL: list_nodes returned no parseable content: {content}")
            return 1
        node_count = body.get("count", 0)
        categories = sorted((body.get("by_category") or {}).keys())
        print(f"[smoke] list_nodes returned {node_count} nodes across categories: {', '.join(categories)}")

        if node_count < 10:
            print("[smoke] FAIL: expected at least 10 registered node types")
            return 1

        print("[smoke] OK: MCP server is healthy")
        return 0
    except TimeoutError as exc:
        print(f"[smoke] FAIL: {exc}")
        # drain stderr for diagnosis
        leftovers = []
        while not stderr_q.empty():
            try:
                leftovers.append(stderr_q.get_nowait())
            except Empty:
                break
        if leftovers:
            print("[smoke] server stderr:")
            for line in leftovers[-20:]:
                print("  ", line.rstrip())
        return 1
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
