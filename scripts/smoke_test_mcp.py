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
        instructions = init_resp.get("result", {}).get("instructions", "")
        if "Use built-in nodes whenever they can solve the task" not in instructions:
            print("[smoke] FAIL: server instructions are missing the learned-node creation rule")
            return 1

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
            "get_editor_graph", "save_editor_workflow",
            "list_saved_workflows", "load_saved_workflow_in_editor",
            "organize_editor_graph", "rename_editor_tab", "close_editor_tab",
            "run_template_in_editor",
            "create_node_type", "list_learned_nodes", "delete_learned_node",
            "get_learned_node_source", "promote_learned_node",
        }
        missing = expected - set(names)
        if missing:
            print(f"[smoke] FAIL: missing expected tools: {sorted(missing)}")
            return 1

        # 4. prompts/list
        send(proc, {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"})
        prompts_resp = recv(stdout_q, expect_id=3)
        if "error" in prompts_resp:
            print(f"[smoke] FAIL: prompts/list returned error: {prompts_resp['error']}")
            return 1
        prompts = prompts_resp.get("result", {}).get("prompts", [])
        prompt_names = sorted(p["name"] for p in prompts)
        if "blacknode_workflow_builder" not in prompt_names:
            print(f"[smoke] FAIL: missing blacknode_workflow_builder prompt: {prompt_names}")
            return 1

        # 5. resources/list
        send(proc, {"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
        resources_resp = recv(stdout_q, expect_id=4)
        if "error" in resources_resp:
            print(f"[smoke] FAIL: resources/list returned error: {resources_resp['error']}")
            return 1
        resources = resources_resp.get("result", {}).get("resources", [])
        uris = sorted(r["uri"] for r in resources)
        print(f"[smoke] resources/list returned {len(resources)} resources: {', '.join(uris)}")
        expected_resources = {
            "blacknode://agent-instructions",
            "blacknode://nodes",
            "blacknode://templates",
            "blacknode://workflows",
            "blacknode://editor/graph",
        }
        missing_resources = expected_resources - set(uris)
        if missing_resources:
            print(f"[smoke] FAIL: missing expected resources: {sorted(missing_resources)}")
            return 1

        # 6. read the MCP agent instructions resource
        send(proc, {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "blacknode://agent-instructions"},
        })
        instructions_resource_resp = recv(stdout_q, expect_id=5)
        if "error" in instructions_resource_resp:
            print(f"[smoke] FAIL: agent instructions resource returned error: {instructions_resource_resp['error']}")
            return 1
        instructions_content = instructions_resource_resp.get("result", {}).get("contents", [])
        instructions_text = json.dumps(instructions_content)
        if "create_node_type" not in instructions_text or "one-off Python" not in instructions_text:
            print(f"[smoke] FAIL: agent instructions resource is missing the learned-node rule: {instructions_content}")
            return 1

        # 7. read a static resource
        send(proc, {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "resources/read",
            "params": {"uri": "blacknode://templates"},
        })
        resource_read_resp = recv(stdout_q, expect_id=6)
        if "error" in resource_read_resp:
            print(f"[smoke] FAIL: resources/read returned error: {resource_read_resp['error']}")
            return 1
        contents = resource_read_resp.get("result", {}).get("contents", [])
        template_body = None
        for item in contents:
            if item.get("text"):
                try:
                    template_body = json.loads(item["text"])
                    break
                except json.JSONDecodeError:
                    continue
        if not template_body or template_body.get("count", 0) < 1:
            print(f"[smoke] FAIL: templates resource returned no parseable templates: {contents}")
            return 1

        # 8. call list_nodes
        send(proc, {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "list_nodes", "arguments": {}},
        })
        call_resp = recv(stdout_q, expect_id=7)
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
