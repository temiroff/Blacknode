from blacknode.node import node


@node(inputs=["path:Text", "encoding:Text"], outputs=["text:Text"], name="FileRead")
def file_read(ctx: dict) -> dict:
    with open(ctx.get("path", ""), encoding=ctx.get("encoding", "utf-8")) as f:
        return {"text": f.read()}


@node(inputs=["path:Text", "text:Text", "encoding:Text"], outputs=["path:Text"], name="FileWrite")
def file_write(ctx: dict) -> dict:
    from pathlib import Path

    path = Path(str(ctx.get("path", ""))).expanduser()
    full_path = path if path.is_absolute() else Path.cwd() / path
    full_path = full_path.resolve()
    with open(full_path, "w", encoding=ctx.get("encoding", "utf-8")) as f:
        f.write(ctx.get("text", ""))
    return {"path": str(full_path)}


@node(inputs=["url:Text", "headers:Dict", "timeout:Float=20"], outputs=["text:Text", "status:Int"], name="HTTPGet")
def http_get(ctx: dict) -> dict:
    import urllib.request
    url = ctx.get("url", "")
    headers = ctx.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    headers = dict(headers)
    default_agent = "Blacknode/0.1 (https://github.com/temiroff/Blacknode; 1102304+temiroff@users.noreply.github.com)"
    headers.setdefault("User-Agent", default_agent)
    headers.setdefault("Api-User-Agent", default_agent)
    headers.setdefault("Accept", "application/json,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8")
    headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    timeout = float(ctx.get("timeout", 20))
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return {"text": resp.read().decode(), "status": resp.status}


@node(inputs=["text:Text"], outputs=["data:Dict"], name="JSONParse")
def json_parse(ctx: dict) -> dict:
    import json
    return {"data": json.loads(ctx.get("text", "{}"))}


@node(inputs=["data:Dict", "indent:Int"], outputs=["text:Text"], name="JSONDump")
def json_dump(ctx: dict) -> dict:
    import json
    return {"text": json.dumps(ctx.get("data"), indent=ctx.get("indent", 2))}
