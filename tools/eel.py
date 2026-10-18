#!/usr/bin/env python3
"""Print one section of the C++ working draft (eel.is/c++draft) as plain text with paragraph numbers.

    python3 tools/eel.py basic.life            # whole section incl. subsections
    python3 tools/eel.py basic.life --raw      # print cached HTML path instead

Pages are cached under .cache/eel/. Paragraphs print as "¶N", list items as "(N.M)",
code blocks are fenced with ``` so they can be read (and adapted) directly.
"""
import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "eel"


def fetch(sid):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{sid}.html"
    if not path.exists():
        req = urllib.request.Request("https://eel.is/c++draft/" + sid, headers={"User-Agent": "cpp-std-notes"})
        path.write_bytes(urllib.request.urlopen(req).read())
    return path


def replace_codeblocks(s):
    out, pos, tag = [], 0, "<span class='codeblock'>"
    while True:
        i = s.find(tag, pos)
        if i < 0:
            out.append(s[pos:])
            return "".join(out)
        out.append(s[pos:i])
        depth, j = 1, i + len(tag)
        for m in re.finditer(r"<span\b|</span>", s[j:]):
            depth += 1 if m.group(0) == "<span" else -1
            if depth == 0:
                end = j + m.start()
                break
        else:
            end = len(s)
        code = re.sub("<[^>]+>", "", s[i + len(tag):end]).strip("\n")
        out.append("\n```cpp\n" + code + "\n```\n")
        pos = end + len("</span>")


def to_text(s):
    s = s[s.find("<h1"):] if "<h1" in s else s
    s = re.sub(r"<div class='sourceLinkParent'>.*?</div>", "", s, flags=re.S)
    s = re.sub(r"<a class='index'[^>]*></a>", "", s)
    s = re.sub(r"<span class='shy'></span>", "", s)
    # headings
    s = re.sub(r"<h(\d) [^>]*>(.*?)</h\1>",
               lambda m: "\n\n" + "#" * int(m.group(1)) + " " + re.sub("<[^>]+>", "", m.group(2)) + "\n", s, flags=re.S)
    # paragraph numbers
    s = re.sub(r"<div class='para[^']*' id='([^']+)'><div class='marginalizedparent'><a class='marginalized'[^>]*>([^<]*)</a></div>",
               lambda m: f"\n\n¶{m.group(2)} ", s)
    s = re.sub(r"<li id='[^']*'><div class='marginalizedparent'[^>]*><a class='marginalized'[^>]*>([^<]*)</a></div>",
               lambda m: f"\n  {m.group(1)} ", s)
    s = re.sub(r"<li[^>]*>", "\n  • ", s)
    # code blocks
    s = replace_codeblocks(s)
    s = re.sub(r"<div class='(?:bnf|ncbnf|ncsimplebnf|simplebnf)[^']*'>", "\n[grammar]\n", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<div id='(?:note|example)-\d+' class='(note|example)'>", "\n    ", s)
    s = re.sub(r"<(?:/div|/li|/ul|/ol|ul[^>]*|ol[^>]*)>", "", s)
    s = re.sub(r"<i\s*>(.*?)</i>", r"*\1*", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace(" ", " ").replace(" ", " ").replace("\xa0", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = fetch(sys.argv[1])
    if "--raw" in sys.argv:
        print(path)
        return
    print(to_text(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
