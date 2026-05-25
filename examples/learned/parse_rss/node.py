import feedparser


def run(feed):
    parsed = feedparser.parse(feed)
    entries = []
    for entry in parsed.entries:
        entries.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "summary": entry.get("summary", ""),
            "published": entry.get("published", ""),
        })
    return {"entries": entries}
