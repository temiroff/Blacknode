from blacknode.node import node


@node(inputs=["path:Text", "encoding:Text"], outputs=["text:Text"], name="FileRead")
def file_read(ctx: dict) -> dict:
    with open(ctx.get("path", ""), encoding=ctx.get("encoding", "utf-8")) as f:
        return {"text": f.read()}


@node(inputs=["path:Text", "text:Text", "encoding:Text"], outputs=["path:Text"], name="FileWrite")
def file_write(ctx: dict) -> dict:
    path = ctx.get("path", "")
    with open(path, "w", encoding=ctx.get("encoding", "utf-8")) as f:
        f.write(ctx.get("text", ""))
    return {"path": path}


@node(inputs=["url:Text", "headers:Dict"], outputs=["text:Text", "status:Int"], name="HTTPGet")
def http_get(ctx: dict) -> dict:
    import urllib.request
    url     = ctx.get("url", "")
    headers = ctx.get("headers", {})
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return {"text": resp.read().decode(), "status": resp.status}


@node(inputs=["text:Text"], outputs=["data:Dict"], name="JSONParse")
def json_parse(ctx: dict) -> dict:
    import json
    return {"data": json.loads(ctx.get("text", "{}"))}


@node(inputs=["data:Dict", "indent:Int"], outputs=["text:Text"], name="JSONDump")
def json_dump(ctx: dict) -> dict:
    import json
    return {"text": json.dumps(ctx.get("data"), indent=ctx.get("indent", 2))}
