from __future__ import annotations

import re
from html.parser import HTMLParser

from blacknode.node import Int, List, Text, node


@node(
    name="RegexExtract",
    category="Community",
    inputs={"text": Text, "pattern": Text, "limit": Int(default=20)},
    outputs={"matches": List[Text], "count": Int},
)
def regex_extract(text: str, pattern: str, limit: int = 20) -> dict:
    matches = re.findall(pattern or "", text or "")
    values = ["".join(match) if isinstance(match, tuple) else str(match) for match in matches[: int(limit or 20)]]
    return {"matches": values, "count": len(values)}


@node(
    name="HTMLTitleExtract",
    category="Community",
    inputs={"html": Text},
    outputs={"title": Text},
)
def html_title_extract(html: str) -> str:
    class TitleParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_title = False
            self.parts: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "title":
                self.in_title = True

        def handle_endtag(self, tag):
            if tag.lower() == "title":
                self.in_title = False

        def handle_data(self, data):
            if self.in_title:
                self.parts.append(data)

    parser = TitleParser()
    parser.feed(html or "")
    return " ".join("".join(parser.parts).split())
