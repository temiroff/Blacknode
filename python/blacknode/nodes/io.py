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


@node(inputs=["path:Text", "pattern:Text=*", "recursive:Bool=true"], outputs=["files:List", "count:Int"], name="DirectoryList")
def directory_list(ctx: dict) -> dict:
    from pathlib import Path

    root = Path(str(ctx.get("path") or ".")).expanduser().resolve()
    pattern = str(ctx.get("pattern") or "*")
    recursive = bool(ctx.get("recursive", True))
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    files = [str(path) for path in iterator if path.is_file()]
    return {"files": files, "count": len(files)}


@node(inputs=["path:Text"], outputs=["exists:Bool", "is_file:Bool", "is_dir:Bool", "size:Int"], name="FileInfo")
def file_info(ctx: dict) -> dict:
    from pathlib import Path

    path = Path(str(ctx.get("path") or "")).expanduser()
    resolved = path if path.is_absolute() else Path.cwd() / path
    exists = resolved.exists()
    return {
        "exists": exists,
        "is_file": resolved.is_file() if exists else False,
        "is_dir": resolved.is_dir() if exists else False,
        "size": resolved.stat().st_size if exists and resolved.is_file() else 0,
    }


@node(inputs=["path:Text", "encoding:Text=utf-8"], outputs=["rows:List", "count:Int"], name="CSVRead")
def csv_read(ctx: dict) -> dict:
    import csv

    with open(str(ctx.get("path") or ""), newline="", encoding=ctx.get("encoding") or "utf-8") as f:
        rows = list(csv.DictReader(f))
    return {"rows": rows, "count": len(rows)}


@node(inputs=["path:Text", "rows:List", "encoding:Text=utf-8"], outputs=["path:Text", "count:Int"], name="CSVWrite")
def csv_write(ctx: dict) -> dict:
    import csv
    from pathlib import Path

    rows = ctx.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    fieldnames: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(str(key))

    path = Path(str(ctx.get("path") or "")).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=ctx.get("encoding") or "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row if isinstance(row, dict) else {"value": row})
    return {"path": str(path), "count": len(rows)}
