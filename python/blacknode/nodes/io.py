"""IO nodes: FileRead, FileWrite, HTTPGet, JSONParse, JSONDump."""
from blacknode.node import node


@node(inputs=["path", "encoding"], outputs=["text"], name="FileRead")
def file_read(ctx: dict) -> dict:
    path = ctx.get("path", "")
    enc  = ctx.get("encoding", "utf-8")
    with open(path, encoding=enc) as f:
        return {"text": f.read()}


@node(inputs=["path", "text", "encoding"], outputs=["path"], name="FileWrite")
def file_write(ctx: dict) -> dict:
    path = ctx.get("path", "")
    text = ctx.get("text", "")
    enc  = ctx.get("encoding", "utf-8")
    with open(path, "w", encoding=enc) as f:
        f.write(text)
    return {"path": path}


@node(inputs=["url", "headers"], outputs=["text", "status"], name="HTTPGet")
def http_get(ctx: dict) -> dict:
    import urllib.request, json as _json
    url     = ctx.get("url", "")
    headers = ctx.get("headers", {})
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return {"text": resp.read().decode(), "status": resp.status}


@node(inputs=["text"], outputs=["data"], name="JSONParse")
def json_parse(ctx: dict) -> dict:
    import json
    return {"data": json.loads(ctx.get("text", "{}"))}


@node(inputs=["data", "indent"], outputs=["text"], name="JSONDump")
def json_dump(ctx: dict) -> dict:
    import json
    indent = ctx.get("indent", 2)
    return {"text": json.dumps(ctx.get("data"), indent=indent)}
