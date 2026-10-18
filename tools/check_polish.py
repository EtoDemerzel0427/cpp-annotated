#!/usr/bin/env python3
"""Check that a "language polish" edit did not change content.

Compares a page's committed version (git HEAD, or --base REV) with the working copy and
reports every structural element that was added or removed: code blocks (must be
byte-identical), [[cross references]], {{badges}}, ¶ paragraph markers, admonitions,
headings, and frontmatter fields.

    python3 tools/check_polish.py content/topics/value-categories.md
    python3 tools/check_polish.py --base HEAD~3 content/std/*.md
"""
import re
import subprocess
import sys
from collections import Counter

FENCE = re.compile(r"^([ \t]*)(`{3,}|~{3,})([^\n]*)\n(.*?)\n\1\2[ \t]*$", re.M | re.S)


def extract(text):
    code = [m.group(0).strip() for m in FENCE.finditer(text)]
    prose = FENCE.sub("", text)
    fm = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        for line in text[4:end].splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return {
        "code blocks": Counter(code),
        "inline code": Counter(re.findall(r"`[^`\n]+`", prose)),
        "xrefs": Counter(re.findall(r"\[\[([^\[\]|\\]+)", prose)),
        "badges": Counter(re.findall(r"\{\{[^{}]+\}\}", prose)),
        "¶ markers": Counter(re.findall(r"¶\d+(?:\.\d+)*", prose)),
        "admonitions": Counter(re.findall(r"^\s*!!! (\w+)", prose, re.M)),
        "headings": Counter(len(h) for h in re.findall(r"^(#{2,4}) ", prose, re.M)),
        "frontmatter": Counter(f"{k}: {v}" for k, v in fm.items() if k not in ("summary", "title")),
    }


def main():
    args = sys.argv[1:]
    base = "HEAD"
    if args[:1] == ["--base"]:
        base, args = args[1], args[2:]
    bad = 0
    for path in args:
        try:
            old = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError:
            print(f"{path}: not in {base}, skipped")
            continue
        try:
            new = open(path, encoding="utf-8").read()
        except UnicodeDecodeError as ex:
            print(f"{path}: NOT VALID UTF-8 ({ex}) — restore with `git checkout HEAD -- {path}` and redo the edit")
            bad += 1
            continue
        a, b = extract(old), extract(new)
        problems = []
        for key in a:
            lost, added = a[key] - b[key], b[key] - a[key]
            if key == "code blocks":
                if lost or added:
                    problems.append(f"  code blocks: {sum(lost.values())} removed/changed, {sum(added.values())} added/changed")
                    for c in list(lost)[:3]:
                        problems.append("    - " + c.splitlines()[0] + " … " + (c.splitlines()[1] if len(c.splitlines()) > 1 else ""))
                continue
            if lost:
                problems.append(f"  {key} removed: " + ", ".join(f"{k}×{v}" if v > 1 else str(k) for k, v in lost.items()))
            if added and key not in ("xrefs", "inline code"):
                problems.append(f"  {key} added: " + ", ".join(str(k) for k in added))
        print(f"{path}: " + ("OK" if not problems else "CONTENT CHANGED"))
        print("\n".join(problems))
        bad += bool(problems)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
