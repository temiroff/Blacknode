from blacknode.node import node


@node(
    inputs=["query:Text", "engine:Text=duckduckgo", "num_results:Int=10"],
    outputs=["url:Text"],
    name="WebSearchURL",
)
def web_search_url(ctx: dict) -> dict:
    from urllib.parse import quote_plus

    query = quote_plus(str(ctx.get("query") or ""))
    engine = str(ctx.get("engine") or "duckduckgo").lower()
    if engine in {"google", "g"}:
        url = f"https://www.google.com/search?q={query}&num={int(ctx.get('num_results', 10))}"
    elif engine in {"bing", "b"}:
        url = f"https://www.bing.com/search?q={query}&count={int(ctx.get('num_results', 10))}"
    else:
        url = f"https://duckduckgo.com/html/?q={query}"
    return {"url": url}


@node(
    inputs=["html:Text", "base_url:Text", "limit:Int=10"],
    outputs=["results:List"],
    name="SearchResultExtractor",
)
def search_result_extractor(ctx: dict) -> dict:
    from html.parser import HTMLParser
    from urllib.parse import parse_qs, unquote, urljoin, urlparse

    class LinkParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links: list[dict[str, str]] = []
            self._href: str | None = None
            self._text: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() != "a":
                return
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self._href = href
                self._text = []

        def handle_data(self, data):
            if self._href:
                self._text.append(data)

        def handle_endtag(self, tag):
            if tag.lower() != "a" or not self._href:
                return
            title = " ".join("".join(self._text).split())
            href = self._href
            parsed = urlparse(href)
            if parsed.path == "/l/":
                href = parse_qs(parsed.query).get("uddg", [href])[0]
                href = unquote(href)
            if title and href and not href.startswith("#"):
                self.links.append({"title": title, "url": href})
            self._href = None
            self._text = []

    parser = LinkParser()
    parser.feed(str(ctx.get("html") or ""))
    base_url = str(ctx.get("base_url") or "")
    seen: set[str] = set()
    results: list[dict[str, str]] = []
    for item in parser.links:
        url = urljoin(base_url, item["url"])
        if url in seen or url.startswith("javascript:"):
            continue
        seen.add(url)
        results.append({"title": item["title"], "url": url})
        if len(results) >= int(ctx.get("limit", 10)):
            break
    return {"results": results}


@node(inputs=["results:List", "template:Text={title} - {url}"], outputs=["text:Text"], name="SearchResultsFormat")
def search_results_format(ctx: dict) -> dict:
    results = ctx.get("results") if isinstance(ctx.get("results"), list) else []
    template = str(ctx.get("template") or "{title} - {url}")
    lines = []
    for item in results:
        if isinstance(item, dict):
            lines.append(template.format(**{k: str(v) for k, v in item.items()}))
        else:
            lines.append(str(item))
    return {"text": "\n".join(lines)}
