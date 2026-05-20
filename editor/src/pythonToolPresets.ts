export interface PythonToolPreset {
  type: 'PythonFn'
  params: {
    code: string
    name: string
    description: string
    label: string
  }
}

const webSearchCode = `def run(query: str) -> str:
    import html
    import json
    import re
    import urllib.parse
    import urllib.request

    encoded = urllib.parse.quote_plus(str(query))

    def fetch(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Blacknode/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def clean(value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
        return re.sub(r"\\s+", " ", value).strip()

    try:
        instant_url = "https://api.duckduckgo.com/?q=" + encoded + "&format=json&no_html=1&skip_disambig=1"
        data = json.loads(fetch(instant_url))
        for key in ("AbstractText", "Definition", "Answer"):
            text = clean(str(data.get(key) or ""))
            if text:
                return text

        pending = list(data.get("RelatedTopics", []))
        while pending:
            item = pending.pop(0)
            pending.extend(item.get("Topics", []))
            text = clean(str(item.get("Text") or ""))
            if text:
                return text
    except Exception:
        pass

    page = fetch("https://duckduckgo.com/html/?q=" + encoded)
    titles = [clean(match) for match in re.findall(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', page, re.I | re.S)]
    snippets = [
        clean(a or b)
        for a, b in re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
            page,
            re.I | re.S,
        )
    ]
    results = []
    for i, title in enumerate(titles[:3]):
        if not title:
            continue
        snippet = snippets[i] if i < len(snippets) else ""
        results.append(str(i + 1) + ". " + title + ((" - " + snippet) if snippet else ""))
    return "\\n".join(results) if results else "No web snippets found for: " + str(query)
`

const fetchUrlCode = `def run(url: str, max_chars: int = 6000) -> str:
    import html
    import re
    import urllib.request

    limit = max(200, min(int(max_chars), 20000))
    req = urllib.request.Request(str(url), headers={"User-Agent": "Mozilla/5.0 Blacknode/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read(limit * 3)
        text = raw.decode("utf-8", errors="replace")

    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\\s+", " ", text).strip()
    return text[:limit]
`

const calculatorCode = `def run(expression: str) -> str:
    import ast
    import math
    import operator

    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    funcs = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    funcs.update({"abs": abs, "round": round, "min": min, "max": max})

    def eval_node(node):
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](eval_node(node.operand))
        if isinstance(node, ast.Name) and node.id in funcs:
            return funcs[node.id]
        if isinstance(node, ast.Call):
            fn = eval_node(node.func)
            args = [eval_node(arg) for arg in node.args]
            return fn(*args)
        raise ValueError("unsupported expression")

    return str(eval_node(ast.parse(str(expression), mode="eval")))
`

const currentTimeCode = `def run(timezone: str = "local") -> str:
    from datetime import datetime, timezone as dt_timezone

    zone = (timezone or "local").strip()
    if zone.lower() in {"utc", "z"}:
        return datetime.now(dt_timezone.utc).isoformat(timespec="seconds")
    if zone.lower() in {"", "local"}:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(zone)).isoformat(timespec="seconds")
    except Exception as exc:
        raise ValueError("unknown timezone '" + str(timezone) + "': " + str(exc)) from exc
`

const regexExtractCode = `def run(text: str, pattern: str, max_matches: int = 10) -> str:
    import re

    matches = re.findall(str(pattern), str(text), flags=re.MULTILINE)
    limit = max(1, min(int(max_matches), 50))
    rows = []
    for match in matches[:limit]:
        if isinstance(match, tuple):
            rows.append(" | ".join(str(part) for part in match))
        else:
            rows.append(str(match))
    return "\\n".join(rows) if rows else "No matches"
`

const jsonLookupCode = `def run(json_text: str, path: str = "") -> str:
    import json

    value = json.loads(str(json_text))
    if path:
        for part in str(path).split("."):
            if isinstance(value, list):
                value = value[int(part)]
            elif isinstance(value, dict):
                value = value[part]
            else:
                raise ValueError("cannot descend into " + type(value).__name__)
    return json.dumps(value, indent=2, ensure_ascii=False)
`

const textStatsCode = `def run(text: str) -> str:
    import json
    import re

    value = str(text)
    words = re.findall(r"\\b\\w+\\b", value)
    stats = {
        "characters": len(value),
        "words": len(words),
        "lines": value.count("\\n") + (1 if value else 0),
        "rough_tokens": max(1, round(len(value) / 4)) if value else 0,
    }
    return json.dumps(stats, indent=2)
`

function preset(name: string, description: string, code: string): PythonToolPreset {
  return { type: 'PythonFn', params: { code, name, description, label: name } }
}

export const PYTHON_TOOL_PRESETS: Record<string, PythonToolPreset> = {
  web_search: preset('web_search', 'Search DuckDuckGo and return a compact answer or top snippets.', webSearchCode),
  fetch_url: preset('fetch_url', 'Fetch a URL and return readable page text.', fetchUrlCode),
  calculator: preset('calculator', 'Evaluate a safe math expression with common math functions.', calculatorCode),
  current_time: preset('current_time', 'Return current date and time for local, UTC, or an IANA timezone.', currentTimeCode),
  regex_extract: preset('regex_extract', 'Extract regex matches from text.', regexExtractCode),
  json_lookup: preset('json_lookup', 'Read JSON and return a value by dotted path.', jsonLookupCode),
  text_stats: preset('text_stats', 'Count characters, words, lines, and rough tokens in text.', textStatsCode),
}

export const PYTHON_TOOL_TYPES = Object.keys(PYTHON_TOOL_PRESETS)

export function isPythonToolPreset(type: string): boolean {
  return type in PYTHON_TOOL_PRESETS
}

export function resolvePythonToolPreset(type: string): PythonToolPreset | null {
  return PYTHON_TOOL_PRESETS[type] ?? null
}
