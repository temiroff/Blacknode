from blacknode.node import node


@node(
    inputs=[
        "method:Text=GET",
        "url:Text",
        "headers:Dict",
        "body:Text",
        "json_body:Dict",
        "timeout:Float=20",
    ],
    outputs=["text:Text", "status:Int", "headers:Dict", "data:Dict"],
    name="HTTPRequest",
)
def http_request(ctx: dict) -> dict:
    import json
    import urllib.error
    import urllib.request

    method = str(ctx.get("method") or "GET").upper()
    url = str(ctx.get("url") or "")
    headers = ctx.get("headers") if isinstance(ctx.get("headers"), dict) else {}
    headers = dict(headers or {})
    data = None
    json_body = ctx.get("json_body")
    if isinstance(json_body, dict) and json_body:
        data = json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif ctx.get("body") not in (None, ""):
        data = str(ctx.get("body")).encode("utf-8")

    default_agent = "Blacknode/0.1 (https://github.com/temiroff/Blacknode)"
    headers.setdefault("User-Agent", default_agent)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=float(ctx.get("timeout", 20))) as response:
            text = response.read().decode("utf-8", errors="replace")
            response_headers = dict(response.headers.items())
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        response_headers = dict(exc.headers.items())
        status = int(exc.code)

    parsed: dict = {}
    try:
        parsed = json.loads(text)
    except Exception:
        pass
    return {"text": text, "status": status, "headers": response_headers, "data": parsed}


@node(
    inputs=["base_url:Text", "path:Text", "query:Dict", "headers:Dict"],
    outputs=["url:Text", "headers:Dict"],
    name="APIRequestBuilder",
)
def api_request_builder(ctx: dict) -> dict:
    from urllib.parse import urlencode

    base_url = str(ctx.get("base_url") or "").rstrip("/")
    path = str(ctx.get("path") or "").lstrip("/")
    query = ctx.get("query") if isinstance(ctx.get("query"), dict) else {}
    url = f"{base_url}/{path}" if path else base_url
    if query:
        url = f"{url}?{urlencode(query, doseq=True)}"
    headers = ctx.get("headers") if isinstance(ctx.get("headers"), dict) else {}
    return {"url": url, "headers": dict(headers or {})}
