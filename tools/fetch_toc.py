#!/usr/bin/env python3
"""Fetch the table of contents of the C++ working draft from eel.is and write data/toc.json.

Usage: python3 tools/fetch_toc.py
"""
import html
import json
import re
import urllib.request
from pathlib import Path

URL = "https://eel.is/c++draft/"
ROOT = Path(__file__).resolve().parent.parent


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "cpp-std-notes toc fetcher"})
    s = urllib.request.urlopen(req).read().decode("utf-8")
    commit = re.search(r"Eelis/draft/commit/([0-9a-f]+)", s)
    generated = re.search(r"Generated on (\d{4}-\d{2}-\d{2})", s)
    pat = re.compile(
        r"<div id='([^']+)'><h([2-6]) ><a class='secnum'[^>]*>([^<]*)</a>\s*(.*?)<a class='(?:folded_)?abbr_ref'"
    )
    entries = []
    for m in pat.finditer(s):
        sid, lvl, num, title = m.groups()
        num = html.unescape(num).replace(" ", " ").replace(" ", " ").strip()
        num = re.sub(r"^Annex\s+([A-Z])\s*$", r"\1", num)
        title = html.unescape(re.sub("<[^>]+>", "", title)).strip()
        # eel.is renders every heading below depth 3 as <h4>, so derive depth from the section number
        entries.append({"id": sid, "num": num, "level": num.count(".") + 1, "title": title})
    out = {
        "source": URL,
        "draft_commit": commit.group(1) if commit else None,
        "generated": generated.group(1) if generated else None,
        "entries": entries,
    }
    path = ROOT / "data" / "toc.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} entries to {path}")


if __name__ == "__main__":
    main()
