#!/usr/bin/env python3
"""Verify every WG21 paper / issue number cited in content/ against the official wg21.link index.

    python3 tools/check_refs.py            # report unknown numbers
    python3 tools/check_refs.py --titles   # also print the official title of every citation, for a relevance check

The index (https://wg21.link/index.json, ~10 MB) is cached in .cache/wg21-index.json; delete it to refresh.
A bare number without revision (P2300) is valid if any revision exists.
"""
import collections
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "wg21-index.json"
REF = re.compile(r"\b(P\d{4}R\d+|P\d{4}|N\d{4}|CWG\d+|LWG\d+)\b")


def load_index():
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request("https://wg21.link/index.json", headers={"User-Agent": "cpp-std-notes"})
        CACHE.write_bytes(urllib.request.urlopen(req).read())
    return {k.upper(): v for k, v in json.loads(CACHE.read_text()).items()}


def lookup(idx, ref):
    if ref in idx:
        return ref, idx[ref]
    revs = [k for k in idx if re.fullmatch(ref + r"R\d+", k)]
    if not revs:
        return None, None
    latest = max(revs, key=lambda k: int(k.rsplit("R", 1)[1]))
    return latest, idx[latest]


def main():
    idx = load_index()
    refs = collections.defaultdict(set)
    for f in sorted((ROOT / "content").rglob("*.md")):
        for m in REF.finditer(f.read_text(encoding="utf-8")):
            refs[m.group(1).upper()].add(str(f.relative_to(ROOT / "content")))
    bad = 0
    for ref in sorted(refs):
        key, entry = lookup(idx, ref)
        if not entry:
            bad += 1
            print(f"UNKNOWN  {ref:12} in {', '.join(sorted(refs[ref])[:4])}")
        elif "--titles" in sys.argv:
            print(f"{ref:12} {entry.get('title')}  ({len(refs[ref])} page(s))")
    print(f"{len(refs)} distinct references, {bad} unknown")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
