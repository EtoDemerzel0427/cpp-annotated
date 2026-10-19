#!/usr/bin/env python3
"""Build the static site: content/**.md + data/*.json  ->  _site/

    python3 build.py            # build into _site/
    python3 build.py --serve    # build, then serve _site/ on http://localhost:8766
    python3 build.py --serve --watch   # ...and rebuild + live-reload whenever content changes
    python3 build.py --check    # render everything into a temp dir and report warnings only

Requires: pip install markdown pygments
"""
import base64
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify_unicode
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
DATA = ROOT / "data"
STATIC = ROOT / "static"
OUT = ROOT / "_site"
EEL = "https://eel.is/c++draft/"
SITE_NAME = "C++ 标准注疏"
SITE_SUB = "The Annotated C++ Standard"

COLLECTIONS = {
    "topics": ("专题", "跨越多个条款的主题：把散落在标准各处的规则串成一条线。"),
    "patterns": ("惯用法与模式", "C++ 里常用的惯用法和设计模式：每一个解决什么问题，用哪些语言规则实现，代价是什么，现代 C++ 又给了哪些替代写法。"),
    "perf": ("性能", "C++ 性能调优：先学会测量，再看编译器能做什么、做不到什么，内存、拷贝、分支和构建层面的优化各值多少，每个结论都有本机实测。"),
    "toolchain": ("工具链与工程", "编译器、链接器、ABI、构建系统，以及组织一个 C++ 项目的工程实践：物理设计、库边界、依赖、测试、调试和静态分析。"),
    "history": ("沿革", "一个特性或一个库是怎么走到今天的：早期的尝试、委员会里的争论与妥协、被否决的方案、后来的转机，以及还在进行中的工作。"),
    "papers": ("提案", "WG21 提案解读：一个特性从动机、设计取舍到最终措辞的来龙去脉。"),
}

STATUS = {
    "stub": ("骨架", "stub"),
    "draft": ("草稿", "draft"),
    "done": ("完成", "done"),
}

BADGES = {
    "ub": ("UB", "undefined behavior · 未定义行为", "bad"),
    "ifndr": ("IFNDR", "ill-formed, no diagnostic required · 非良构且不要求诊断", "bad"),
    "ill-formed": ("ill-formed", "非良构：实现必须给出诊断", "warn"),
    "well-formed": ("well-formed", "良构", "good"),
    "impl": ("impl-defined", "implementation-defined · 实现定义，且实现须写入文档", "info"),
    "unspec": ("unspecified", "unspecified · 未指定行为，实现无须文档化", "info"),
    "erroneous": ("EB", "erroneous behavior · 错误行为 (C++26)", "warn"),
    "deprecated": ("deprecated", "已弃用", "warn"),
    "removed": ("removed", "已移除", "bad"),
    "dr": ("DR", "defect report：以缺陷报告形式回溯适用于旧标准", "info"),
}
VERDICTS = {
    "ok": ("✓ 良构", "good"),
    "error": ("✗ 非良构", "warn"),
    "ub": ("☠ 未定义行为", "bad"),
    "ifndr": ("☠ IFNDR", "bad"),
    "unspecified": ("? 未指明", "info"),
    "impl": ("? 实现定义", "info"),
    "eb": ("⚠ 错误行为", "warn"),
}
ADMONITION_TITLES = {
    "tldr": "本节要点",
    "std": "标准原文",
    "note": "注",
    "tip": "提示",
    "warning": "注意",
    "ub": "未定义行为",
    "example": "例",
    "history": "历史与演进",
    "impl": "实现视角",
    "pitfall": "陷阱",
    "question": "思考题",
    "summary": "小结",
    "lawyer": "Language Lawyer",
}

WARNINGS = []
ASSET_VERSION = dt.datetime.now().strftime("%Y%m%d%H%M%S")  # cache-busting query for CSS/JS


def warn(msg):
    WARNINGS.append(msg)


# --------------------------------------------------------------------------- data

def load_toc():
    d = json.loads((DATA / "toc.json").read_text(encoding="utf-8"))
    entries = d["entries"]
    stack = []
    for i, e in enumerate(entries):
        e["order"] = i
        while stack and stack[-1]["level"] >= e["level"]:
            stack.pop()
        e["parent"] = stack[-1]["id"] if stack else None
        e["clause"] = stack[0]["id"] if stack else e["id"]
        e["children"] = []
        if stack:
            stack[-1]["children"].append(e["id"])
        stack.append(e)
    by_id = {e["id"]: e for e in entries}
    return d, entries, by_id


def clause_group(clause_entry):
    num = clause_entry["num"]
    if num.isdigit():
        n = int(num)
        if n <= 15:
            return "lang"
        return "lib"
    return "annex"


def parse_frontmatter(text):
    meta = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line and not line.lstrip().startswith("#"):
                    k, v = line.split(":", 1)
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    meta[k.strip()] = v
            text = text[end + 4:].lstrip("\n")
    return meta, text


def split_list(v):
    if not v:
        return []
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [x.strip().strip("\"'") for x in v.split(",") if x.strip()]


# --------------------------------------------------------------------------- markdown

FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})([^\n]*)\n(.*?)\n\1\2[ \t]*$", re.M | re.S)
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1", re.S)
XREF_RE = re.compile(r"\[\[([^\[\]|\\]+?)(?:\\?\|([^\[\]]+?))?\]\]")  # `\|` allowed inside tables
BADGE_RE = re.compile(r"\{\{([a-z0-9+\-]+)(?::([^{}]+))?\}\}", re.I)
VERSION_RE = re.compile(r"^c\+\+(\d\d|2[a-c])$", re.I)
PAPER_RE = re.compile(r"^(P\d{3,4}(?:R\d+)?|N\d{3,4}|CWG\d+|LWG\d+|EWG\d+|LEWG\d+|CWG|LWG)$", re.I)
ADMON_RE = re.compile(r'^([ \t]*)(!!!|\?\?\?\+?)[ \t]+([\w-]+)[ \t]*$', re.M)


class Ctx:
    """Everything a page renderer needs to resolve links."""

    def __init__(self, by_id, pages, glossary, zh):
        self.by_id = by_id
        self.pages = pages          # key -> page dict (key: "std/basic.life", "topics/foo")
        self.std_pages = {p["id"]: p for p in pages.values() if p["kind"] == "std"}
        self.glossary = glossary    # slug -> entry
        self.zh = zh
        # stable names that have no page of their own but are covered by another page (`covers:`)
        self.covered = {}
        for p in self.std_pages.values():
            for c in p["covers"]:
                if c == "*":
                    stack = list(by_id[p["id"]]["children"]) if p["id"] in by_id else []
                    while stack:
                        cid = stack.pop()
                        self.covered.setdefault(cid, p)
                        stack.extend(by_id[cid]["children"])
                else:
                    self.covered.setdefault(c, p)
        for sid in list(self.covered):
            if sid in self.std_pages:
                del self.covered[sid]
        # covered subclauses whose page has a heading naming them -> linkable as page#sid
        self.sections = set()
        for p in self.std_pages.values():
            covers = {sid for sid, q in self.covered.items() if q is p}
            if covers:
                self.sections |= {sid for _, sid in section_heads(FENCE_RE.sub("", p["src"]), covers)}
        self.parent = {c: e["id"] for e in by_id.values() for c in e["children"]}

    def section_of(self, sid):
        """The covered subclause itself or its nearest ancestor that has a heading on the covering page."""
        page = self.covered.get(sid)
        while sid and page and self.covered.get(sid) is page:
            if sid in self.sections:
                return sid
            sid = self.parent.get(sid)
        return None


SECTION_HEAD_RE = re.compile(r"^\s{0,3}#{2,6} .*$", re.M)


def section_heads(src, covers):
    """(line start offset, stable name) for each heading that names a covered subclause, first occurrence only."""
    out, seen = [], set()
    for m in SECTION_HEAD_RE.finditer(src):
        named = [x for x in re.findall(r"\[\[?([A-Za-z][\w.]*)", m.group(0)) if x in covers]
        if named and named[0] not in seen:
            seen.add(named[0])
            out.append((m.start(), named[0]))
    return out


def godbolt_url(code, lang, opts):
    std = opts.get("std", "c++2c")
    flags = opts.get("flags", f"-std={std} -O2 -Wall -Wextra -pedantic")
    compilers = opts.get("cc", "clang_trunk,gsnapshot").split(",")
    language = "c++" if lang in ("cpp", "c++") else lang
    session = {
        "id": 1,
        "language": language,
        "source": code,
        "compilers": [{"id": c, "options": flags} for c in compilers],
    }
    if re.search(r"\bint\s+main\s*\(", code):
        session["executors"] = [{
            "compiler": {"id": compilers[0], "options": flags, "libs": []},
            "compilerVisible": False,
            "compilerOutputVisible": True,
            "argumentsVisible": False,
            "stdinVisible": False,
        }]
    state = {"sessions": [session]}
    b64 = base64.urlsafe_b64encode(json.dumps(state, separators=(",", ":")).encode()).decode()
    return "https://godbolt.org/clientstate/" + b64


def parse_info(info):
    info = info.strip()
    m = re.match(r"([\w+#-]*)\s*(.*)", info)
    lang, rest = m.group(1) or "text", m.group(2)
    opts, flags = {}, set()
    for k, v1, v2, bare in re.findall(r'(\w+)=(?:"([^"]*)"|(\S+))|(\S+)', rest):
        if k:
            opts[k] = v1 or v2
        elif bare:
            flags.add(bare.strip("{}").lower())
    return lang.lower(), opts, flags


CODE_FMT = HtmlFormatter(nowrap=True)
LANG_LABELS = {"cpp": "C++", "c": "C", "python": "Python", "bash": "Shell", "sh": "Shell", "console": "Shell",
               "cmake": "CMake", "asm": "ASM", "nasm": "ASM", "llvm": "LLVM IR", "text": "", "json": "JSON"}


def mark_comments(code_html):
    def repl(m):
        cls, body = m.group(1), m.group(2)
        txt = html.unescape(body)
        extra = ""
        if re.search(r"(//|/\*)\s*(error|ill-formed|错误|编译失败|非良构)", txt, re.I):
            extra = " c-err"
        elif re.search(r"(//|/\*)\s*(UB|undefined|未定义|IFNDR)", txt):
            extra = " c-ub"
        elif re.search(r"(//|/\*)\s*(OK|ok|well-formed|正确|合法)\b", txt):
            extra = " c-ok"
        return f'<span class="{cls}{extra}">{body}</span>'
    return re.sub(r'<span class="(c1|cm|c)">(.*?)</span>', repl, code_html, flags=re.S)


def render_code(code, info):
    lang, opts, flags = parse_info(info)
    if lang in ("c++", "cxx", "cc", "hpp", ""):
        lang = "cpp"
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        lexer = TextLexer()
    body = highlight(code, lexer, CODE_FMT)
    if lang in ("cpp", "c"):
        body = mark_comments(body)
    # one span per line so CSS can number lines; pygments closes its spans at line ends
    lines = body.rstrip().split("\n")
    numbered = len(lines) > 2
    if numbered:
        body = "\n".join(f'<span class="ln">{l}</span>' for l in lines)
    head = [f'<span class="code-lang">{LANG_LABELS[lang]}</span>'] if LANG_LABELS.get(lang) else []
    if opts.get("title"):
        head.append(f'<span class="code-title">{html.escape(opts["title"])}</span>')
    verdict = None
    for f in flags:
        if f in VERDICTS:
            verdict = f
    if verdict:
        label, tone = VERDICTS[verdict]
        head.append(f'<span class="verdict tone-{tone}">{label}</span>')
    tools = []
    if lang in ("cpp", "c") and ("godbolt" in flags or "run" in flags):
        tools.append(
            f'<a class="code-btn" href="{html.escape(godbolt_url(code, lang, opts))}" target="_blank" rel="noopener" '
            f'title="在 Compiler Explorer 中打开">godbolt ↗</a>'
        )
    tools.append('<button class="code-btn copy" type="button" title="复制代码">复制</button>')
    cls = f"code lang-{lang}" + (f" verdict-{verdict}" if verdict else "") + (" numbered" if numbered else "")
    return (
        f'<figure class="{cls}"><figcaption>{"".join(head)}<span class="code-tools">{"".join(tools)}</span></figcaption>'
        f'<pre><code>{body.rstrip()}</code></pre></figure>'
    )


def xref_html(target, text, ctx, page_key):
    target = target.strip()
    # glossary
    if target.startswith("g:"):
        slug = target[2:].strip()
        g = ctx.glossary.get(slug)
        if not g:
            warn(f"{page_key}: unknown glossary term [[{target}]]")
            return html.escape(text or slug)
        label = text or g["en"]
        tip = re.sub(r"<[^>]+>", "", g.get("zh", "")) + " — " + re.sub(r"\[\[|\]\]|`|\*", "", g.get("def", ""))[:220]
        return (f'<a class="xref gloss" href="{{ROOT}}glossary.html#{slug}" '
                f'data-tip="{html.escape(tip)}">{html.escape(label)}</a>')
    # papers & issues
    if PAPER_RE.match(target):
        t = target.upper()
        url = "https://wg21.link/" + t.lower()
        return f'<a class="xref paper" href="{url}" target="_blank" rel="noopener">{html.escape(text or t)}</a>'
    # site pages: topics/foo, toolchain/bar
    if "/" in target and target.split("/")[0] in COLLECTIONS:
        key, _, frag = target.partition("#")
        p = ctx.pages.get(key)
        if not p:
            warn(f"{page_key}: link to missing page [[{target}]]")
            return html.escape(text or target)
        href = "{ROOT}" + p["url"] + (("#" + frag) if frag else "")
        return f'<a class="xref page" href="{href}">{html.escape(text or p["title"])}</a>'
    # stable names: basic.life, basic.life#5, basic.life/5
    m = re.match(r"^([A-Za-z][\w.:-]*?)(?:[#/]([\w.\-]+))?$", target)
    if not m:
        warn(f"{page_key}: bad xref [[{target}]]")
        return html.escape(text or target)
    sid, para = m.group(1), m.group(2)
    label = text or (f"[{sid}]/{para}" if para else f"[{sid}]")
    entry = ctx.by_id.get(sid)
    title = ""
    if entry:
        zh = ctx.zh.get(sid)
        title = f'{entry["num"]} {entry["title"]}' + (f" · {zh}" if zh else "")
    if sid in ctx.std_pages:
        p = ctx.std_pages[sid]
        if para and re.match(r"^\d+(\.\d+)*$", para):
            frag = "#p" + para.split(".")[0]
        else:
            frag = f"#{para}" if para else ""
        href = "{ROOT}" + p["url"] + frag
        tip = title + (" — " + p.get("summary", "") if p.get("summary") else "")
        return f'<a class="xref std local" href="{href}" data-tip="{html.escape(tip)}">{html.escape(label)}</a>'
    if sid in ctx.covered:
        p = ctx.covered[sid]
        tip = title + f" — 见本站 [{p['id']}] {p['title']}"
        frag = (f"#{sid}-p" + para.split(".")[0] if para and re.match(r"^\d+(\.\d+)*$", para)
                else f"#{ctx.section_of(sid)}" if ctx.section_of(sid) else "")
        return f'<a class="xref std local" href="{{ROOT}}{p["url"]}{frag}" data-tip="{html.escape(tip)}">{html.escape(label)}</a>'
    if not entry:
        # stable names deeper than the TOC are fine; just point at eel.is
        if not re.match(r"^[a-z][a-z0-9_.]*$", sid):
            warn(f"{page_key}: suspicious stable name [[{target}]]")
    href = EEL + sid + (f"#{para}" if para else "")
    return (f'<a class="xref std ext" href="{href}" target="_blank" rel="noopener" '
            f'data-tip="{html.escape(title or "eel.is/c++draft/" + sid)}">{html.escape(label)}</a>')


def badge_html(name, arg, page_key):
    n = name.lower()
    m = VERSION_RE.match(n)
    if m:
        v = m.group(1)
        return f'<span class="badge ver" title="自 C++{v} 起">C++{v}</span>'
    if n in BADGES:
        label, tip, tone = BADGES[n]
        if arg:
            label = f"{label} {arg}"
        return f'<span class="badge tone-{tone}" title="{html.escape(tip)}">{html.escape(label)}</span>'
    warn(f"{page_key}: unknown badge {{{{{name}}}}}")
    return html.escape("{{" + name + "}}")


def expand_inline(text, ctx, page_key):
    """Expand [[xref]] and {{badge}} macros outside inline code spans."""
    out, pos = [], 0
    for m in INLINE_CODE_RE.finditer(text):
        out.append(_expand(text[pos:m.start()], ctx, page_key))
        out.append(m.group(0))
        pos = m.end()
    out.append(_expand(text[pos:], ctx, page_key))
    return "".join(out)


def _expand(s, ctx, page_key):
    s = XREF_RE.sub(lambda m: xref_html(m.group(1), m.group(2), ctx, page_key), s)
    s = BADGE_RE.sub(lambda m: badge_html(m.group(1), m.group(2), page_key), s)
    return s


def para_anchors(s, covers=(), start=None):
    """`¶3` becomes an anchor #p3 pointing at the standard paragraph.

    On a page that also covers other subclauses, a heading that names one of them (`[class.access.base]`)
    switches the current subclause; its paragraphs additionally get #class.access.base-p3, so that
    [[class.access.base#3]] can land on the right ¶ even though several subclauses restart at ¶1.
    """
    seen, seen_sub, cur = set(), set(), start

    def repl(m):
        n = re.match(r"\d+", m.group(1)).group(0)
        attr = "" if n in seen else f' id="p{n}"'
        seen.add(n)
        extra = ""
        if cur and (cur, n) not in seen_sub:
            seen_sub.add((cur, n))
            extra = f'<span class="sub-anchor" id="{cur}-p{n}"></span>'
        return f'{extra}<span class="para"{attr}>¶{m.group(1)}</span>'

    lines = s.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r'<a class="sec-anchor" id="([^"]+)"></a>', line)
        if m:
            cur = m.group(1)
        lines[i] = re.sub(r"¶(\d+(?:[.\-–]\d+)*)", repl, line)
    return "\n".join(lines)


def render_markdown(src, ctx, page_key):
    blocks = []

    def stash(m):
        indent, _, info, code = m.group(1), m.group(2), m.group(3), m.group(4)
        if indent:
            code = "\n".join(l[len(indent):] if l.startswith(indent) else l.lstrip() for l in code.split("\n"))
        blocks.append(render_code(code, info))
        return f"{indent}XCODEBLOCKX{len(blocks) - 1}X"

    src = FENCE_RE.sub(stash, src)
    page = ctx.pages.get(page_key)
    covers = {sid for sid, p in ctx.covered.items() if p is page} if page else set()
    for pos, sid in reversed(section_heads(src, covers)):
        src = src[:pos] + f'<a class="sec-anchor" id="{sid}"></a>\n\n' + src[pos:]
    # a `"` inside an admonition title cannot be escaped; render `\"` as a plain quote instead of showing the backslash
    src = re.sub(r'^([ \t]*!!! [\w-]+ ".*)$', lambda m: m.group(1).replace('\\"', '"'), src, flags=re.M)
    src = ADMON_RE.sub(
        lambda m: f'{m.group(1)}{m.group(2)} {m.group(3)} "{admonition_title(m.group(3))}"', src)
    src = expand_inline(src, ctx, page_key)
    # a page usually opens with its own [x.general] subclause without a heading naming it
    start = page["id"] + ".general" if page and page.get("id", "") + ".general" in covers else None
    src = para_anchors(src, covers, start)
    md = markdown.Markdown(
        extensions=["extra", "admonition", "sane_lists", "toc"],
        extension_configs={"toc": {"slugify": slugify_unicode, "toc_depth": "2-3", "permalink": "#",
                                   "permalink_class": "anchor", "permalink_title": "链接到此处"}},
    )
    out = md.convert(src)
    # `\|` is the way to write a pipe inside inline code in a table cell; drop the escape in the output
    out = re.sub(r"<code>([^<]*)</code>", lambda m: "<code>" + m.group(1).replace("\\|", "|") + "</code>", out)
    for i, b in enumerate(blocks):
        out = out.replace(f"<p>XCODEBLOCKX{i}X</p>", b).replace(f"XCODEBLOCKX{i}X", b)
    return out, md.toc_tokens


def admonition_title(kind):
    return ADMONITION_TITLES.get(kind, kind.capitalize())


# --------------------------------------------------------------------------- templates

def esc(s):
    return html.escape(s or "", quote=True)


def toc_html(tokens):
    if not tokens:
        return ""

    def walk(ts):
        items = []
        for t in ts:
            name = re.sub(r"<[^>]+>", "", html.unescape(t["name"])).rstrip("#").strip()
            sub = walk(t["children"]) if t.get("children") else ""
            items.append(f'<li><a href="#{t["id"]}">{esc(name)}</a>{sub}</li>')
        return "<ul>" + "".join(items) + "</ul>"

    return f'<nav class="page-toc" aria-label="本页目录"><div class="page-toc-title">本页目录</div>{walk(tokens)}</nav>'


def layout(*, title, body, root, active="", toc="", desc="", page_id="", body_class=""):
    full_title = f"{title} · {SITE_NAME}" if title != SITE_NAME else f"{SITE_NAME} · {SITE_SUB}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc or SITE_SUB)}">
<link rel="icon" href="{root}static/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap">
<link rel="stylesheet" href="{root}static/css/site.css?v={ASSET_VERSION}">
<script>try{{var t=localStorage.getItem('cppstd.theme');if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
</head>
<body class="{body_class}" data-root="{root}" data-page="{esc(page_id)}" data-active="{esc(active)}">
<header class="topbar">
  <button class="icon-btn nav-toggle" type="button" aria-label="打开导航" aria-controls="sidebar">☰</button>
  <a class="brand" href="{root}index.html"><span class="brand-mark">§</span><span class="brand-name">{SITE_NAME}</span><span class="brand-sub">{SITE_SUB}</span></a>
  <nav class="topnav">
    <a href="{root}std/index.html" data-nav="std">标准</a>
    <a href="{root}topics/index.html" data-nav="topics">专题</a>
    <a href="{root}patterns/index.html" data-nav="patterns">模式</a>
    <a href="{root}perf/index.html" data-nav="perf">性能</a>
    <a href="{root}toolchain/index.html" data-nav="toolchain">工程</a>
    <a href="{root}history/index.html" data-nav="history">沿革</a>
    <a href="{root}papers/index.html" data-nav="papers">提案</a>
    <a href="{root}exercises.html" data-nav="exercises">习题</a>
    <a href="{root}glossary.html" data-nav="glossary">术语</a>
  </nav>
  <button class="search-btn" type="button" aria-label="搜索"><span>搜索 stable name / 关键词</span><kbd>/</kbd></button>
  <button class="icon-btn theme-toggle" type="button" aria-label="切换明暗主题">◐</button>
</header>
<div class="shell">
  <aside class="sidebar" id="sidebar" aria-label="导航"></aside>
  <main class="main">
    <article class="content">
{body}
    </article>
    {toc}
  </main>
</div>
<div class="search-modal" hidden>
  <div class="search-panel" role="dialog" aria-label="搜索">
    <input class="search-input" type="search" placeholder="输入 stable name（如 basic.life）、标题或关键词…" autocomplete="off" spellcheck="false">
    <ul class="search-results"></ul>
    <div class="search-foot"><span><kbd>↑</kbd><kbd>↓</kbd> 选择</span><span><kbd>↵</kbd> 打开</span><span><kbd>esc</kbd> 关闭</span></div>
  </div>
</div>
<div class="tip" hidden></div>
<script src="{root}static/js/nav-data.js?v={ASSET_VERSION}"></script>
<script src="{root}static/js/site.js?v={ASSET_VERSION}" defer></script>
</body>
</html>
"""


def status_badge(status):
    label, cls = STATUS.get(status, STATUS["draft"])
    return f'<span class="status status-{cls}">{label}</span>'


def breadcrumbs(entry, by_id, zh, root, pages_std):
    chain = []
    e = entry
    while e:
        chain.append(e)
        e = by_id.get(e["parent"]) if e["parent"] else None
    chain.reverse()
    parts = [f'<a href="{root}std/index.html">标准</a>']
    for c in chain[:-1]:
        href = f"{root}std/{c['id']}.html" if (c["level"] == 1 or c["id"] in pages_std) else EEL + c["id"]
        parts.append(f'<a href="{href}">{esc(c["num"])} {esc(zh.get(c["id"]) or c["title"])}</a>')
    return '<nav class="crumbs">' + '<span class="sep">/</span>'.join(parts) + "</nav>"


def entry_link(e, root, ctx, show_num=True):
    zh = ctx.zh.get(e["id"])
    label = f'{esc(e["title"])}' + (f' <span class="zh">{esc(zh)}</span>' if zh else "")
    num = f'<span class="num">{esc(e["num"])}</span>' if show_num else ""
    sn = f'<span class="sn">[{esc(e["id"])}]</span>'
    if e["id"] in ctx.std_pages:
        p = ctx.std_pages[e["id"]]
        return (f'<a class="sec has-page" href="{root}{p["url"]}">{num}<span class="t">{label}</span>{sn}'
                f'{status_badge(p.get("status", "draft"))}</a>')
    if e["id"] in ctx.covered:
        p = ctx.covered[e["id"]]
        return (f'<a class="sec has-page covered" href="{root}{p["url"]}" title="在 [{esc(p["id"])}] 页中讲解">{num}<span class="t">{label}</span>{sn}</a>')
    return (f'<a class="sec no-page" href="{EEL}{e["id"]}" target="_blank" rel="noopener">{num}'
            f'<span class="t">{label}</span>{sn}<span class="ext-mark">↗</span></a>')


def children_block(entry, root, ctx, title="本节结构"):
    if not entry["children"]:
        return ""

    def walk(ids):
        lis = []
        for cid in ids:
            c = ctx.by_id[cid]
            lis.append(f"<li>{entry_link(c, root, ctx)}{walk(c['children']) if c['children'] else ''}</li>")
        return "<ul>" + "".join(lis) + "</ul>"

    return f'<section class="children"><h2 id="children">{title}</h2><div class="sec-tree">{walk(entry["children"])}</div></section>'


# --------------------------------------------------------------------------- build

def collect_pages(by_id):
    pages = {}
    for path in sorted(CONTENT.rglob("*.md")):
        rel = path.relative_to(CONTENT)
        if rel.name.startswith("_") or rel.parts[0] not in ("std", *COLLECTIONS):
            continue
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        kind = rel.parts[0]
        pid = rel.stem
        key = f"{kind}/{pid}"
        p = {
            "key": key, "kind": kind, "id": pid, "src": body, "path": str(rel),
            "title": meta.get("title") or pid, "summary": meta.get("summary", ""),
            "status": meta.get("status", "draft"), "tags": split_list(meta.get("tags")),
            "since": meta.get("since", ""), "papers": split_list(meta.get("papers")),
            "related": split_list(meta.get("related")), "order": float(meta.get("order", 999)),
            "updated": meta.get("updated", ""), "covers": split_list(meta.get("covers")), "group": meta.get("group", ""),
            "url": f"{kind}/{pid}.html",
        }
        if kind == "std" and pid not in by_id:
            warn(f"{rel}: '{pid}' is not a stable name in data/toc.json")
        if p["status"] not in STATUS:
            warn(f"{rel}: unknown status '{p['status']}'")
        pages[key] = p
    return pages


def extract_questions(html_s):
    """The `!!! question` admonitions of a rendered page (balanced <div> scan)."""
    out = []
    for m in re.finditer(r'<div class="admonition question">', html_s):
        depth, pos = 0, m.start()
        for d in re.finditer(r"<div\b|</div>", html_s[pos:]):
            depth += 1 if d.group(0) == "<div" else -1
            if depth == 0:
                out.append(html_s[pos:pos + d.end()])
                break
    return out


def exercises_page(exercises):
    """Every 思考题 on the site, grouped by section, each linking back to its page."""
    root = ""
    sections, total = {}, 0
    for ex in exercises:
        sections.setdefault(ex["section"], {}).setdefault(ex["key"], ex)
    parts = []
    for sec, by_page in sections.items():
        n = sum(len(e["qs"]) for e in by_page.values())
        total += n
        rows = []
        for e in by_page.values():
            qs = "".join(q.replace("{ROOT}", root) for q in e["qs"])
            rows.append(f'<section class="ex-page"><h3><a href="{root}{e["url"]}">{esc(e["title"])}</a></h3>{qs}</section>')
        parts.append(f'<h2 id="{slugify_unicode(sec, "-")}">{esc(sec)} <small>{n} 题</small></h2>' + "".join(rows))
    head = (f'<header class="page-head"><h1>习题</h1><p class="page-summary">全站各页的思考题汇总，共 {total} 题，按栏目和页面排列。'
            f'答案都折叠在题目下面，点题目上方的页面标题可以回到原文。</p></header>')
    return layout(title="习题", root=root, active="exercises", page_id="exercises",
                  body=head + f'<div class="prose exercises">{"".join(parts)}</div>')


def plain_text(html_s):
    t = re.sub(r"<figure class=\"code.*?</figure>", " ", html_s, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def rel_root(url):
    return "../" * url.count("/")


def build():
    global OUT
    if "--check" in sys.argv:
        import tempfile
        OUT = Path(tempfile.mkdtemp(prefix="cppstd-check-"))
    if OUT.exists():
        for child in OUT.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    OUT.mkdir(exist_ok=True)
    shutil.copytree(STATIC, OUT / "static")

    toc_meta, entries, by_id = load_toc()
    zh = json.loads((DATA / "zh-titles.json").read_text(encoding="utf-8")) if (DATA / "zh-titles.json").exists() else {}
    gloss_list = []
    for gp in sorted((DATA / "glossary").glob("*.json")):
        try:
            gloss_list.extend(json.loads(gp.read_text(encoding="utf-8")))
        except json.JSONDecodeError as ex:
            warn(f"{gp.relative_to(ROOT)}: invalid JSON ({ex})")
    glossary = {}
    for g in gloss_list:
        slug = g.get("id") or slugify_unicode(g["en"], "-")
        g["id"] = slug
        if slug in glossary:
            warn(f"glossary: duplicate term {slug}")
        glossary[slug] = g

    pages = collect_pages(by_id)
    ctx = Ctx(by_id, pages, glossary, zh)
    clauses = [e for e in entries if e["level"] == 1]
    search = []
    exercises = []

    # ---- std pages
    std_sorted = sorted((p for p in pages.values() if p["kind"] == "std"),
                        key=lambda p: by_id[p["id"]]["order"] if p["id"] in by_id else 10**9)
    clause_ids = {c["id"] for c in clauses}
    for i, p in enumerate(std_sorted):
        if p["id"] in clause_ids:
            continue  # rendered as clause overview below
        root = rel_root(p["url"])
        body_html, toks = render_markdown(p["src"], ctx, p["key"])
        e = by_id.get(p["id"])
        qs = extract_questions(body_html)
        if qs:
            top = p["id"]
            while ctx.parent.get(top):
                top = ctx.parent[top]
            sec = {"lang": "核心语言", "lib": "标准库", "annex": "附录"}.get(clause_group(by_id[top]) if top in by_id else "", "标准")
            exercises.append({"section": "标准 · " + sec, "key": p["key"], "url": p["url"], "title": f'{p["title"]} [{p["id"]}]', "qs": qs})
        body_html = body_html.replace("{ROOT}", root)
        head = []
        if e:
            head.append(breadcrumbs(e, by_id, zh, root, ctx.std_pages))
        num = esc(e["num"]) if e else ""
        en = esc(e["title"]) if e else ""
        meta_bits = [f'<a class="sn-chip" href="{EEL}{p["id"]}" target="_blank" rel="noopener" title="在 eel.is 阅读标准原文">[{esc(p["id"])}] ↗</a>',
                     status_badge(p["status"])]
        if p["since"]:
            meta_bits.append(badge_html(p["since"], None, p["key"]) if VERSION_RE.match(p["since"]) else esc(p["since"]))
        for pp in p["papers"]:
            meta_bits.append(xref_html(pp, None, ctx, p["key"]))
        head.append(f'<header class="page-head"><div class="page-num">{num}</div><h1>{esc(p["title"])}</h1>'
                    f'<div class="page-en">{en}</div>'
                    + (f'<p class="page-summary">{esc(p["summary"])}</p>' if p["summary"] else "")
                    + f'<div class="page-meta">{"".join(meta_bits)}</div></header>')
        tail = []
        if e:
            tail.append(children_block(e, root, ctx))
        if p["related"]:
            tail.append(related_block(p["related"], ctx, p["key"], root))
        prev_p = next((q for q in reversed(std_sorted[:i]) if q["id"] not in clause_ids), None)
        next_p = next((q for q in std_sorted[i + 1:] if q["id"] not in clause_ids), None)
        tail.append(pager(prev_p, next_p, root, ctx))
        tail.append(source_note(p, toc_meta))
        page = layout(title=f'{p["title"]} [{p["id"]}]', body="".join(head) + f'<div class="prose">{body_html}</div>' + "".join(tail),
                      root=root, active="std", toc=toc_html(toks), desc=p["summary"], page_id=p["id"])
        write(p["url"], page)
        search.append(search_item(p, body_html, toks, e, zh))

    # ---- clause overview pages
    for c in clauses:
        url = f"std/{c['id']}.html"
        root = rel_root(url)
        intro, toks = "", []
        cp = ctx.std_pages.get(c["id"])
        if cp:
            intro, toks = render_markdown(cp["src"], ctx, cp["key"])
            intro = f'<div class="prose">{intro.replace("{ROOT}", root)}</div>'
        covered, total = coverage(c, by_id, ctx)
        title_zh = zh.get(c["id"]) or c["title"]
        head = (f'<nav class="crumbs"><a href="{root}std/index.html">标准</a></nav>'
                f'<header class="page-head"><div class="page-num">{"第 " + c["num"] + " 章" if c["num"].isdigit() else "附录 " + c["num"]}</div>'
                f'<h1>{esc(title_zh)}</h1><div class="page-en">{esc(c["title"])}</div>'
                + (f'<p class="page-summary">{esc(cp["summary"])}</p>' if cp and cp["summary"] else "")
                + f'<div class="page-meta"><a class="sn-chip" href="{EEL}{c["id"]}" target="_blank" rel="noopener">[{esc(c["id"])}] ↗</a>'
                  f'{progress_bar(covered, total)}</div></header>')
        body = head + intro + children_block(c, root, ctx, title="条款一览")
        write(url, layout(title=f'{title_zh} [{c["id"]}]', body=body, root=root, active="std",
                          toc=toc_html(toks), page_id=c["id"]))
        search.append({"t": title_zh, "e": c["title"], "s": c["id"], "n": c["num"], "u": url, "k": "clause", "x": cp["summary"] if cp else ""})

    # ---- std index
    write("std/index.html", std_index(clauses, by_id, ctx, toc_meta))

    # ---- collections
    for kind, (label, blurb) in COLLECTIONS.items():
        items = sorted((p for p in pages.values() if p["kind"] == kind), key=lambda p: (p["order"], p["title"]))
        for i, p in enumerate(items):
            root = rel_root(p["url"])
            body_html, toks = render_markdown(p["src"], ctx, p["key"])
            qs = extract_questions(body_html)
            if qs:
                exercises.append({"section": label, "key": p["key"], "url": p["url"], "title": p["title"], "qs": qs})
            body_html = body_html.replace("{ROOT}", root)
            meta_bits = [status_badge(p["status"])]
            if p["since"]:
                meta_bits.append(badge_html(p["since"], None, p["key"]) if VERSION_RE.match(p["since"]) else esc(p["since"]))
            for pp in p["papers"]:
                meta_bits.append(xref_html(pp, None, ctx, p["key"]))
            for t in p["tags"]:
                meta_bits.append(f'<span class="tag">{esc(t)}</span>')
            head = (f'<nav class="crumbs"><a href="{root}{kind}/index.html">{label}</a></nav>'
                    f'<header class="page-head"><h1>{esc(p["title"])}</h1>'
                    + (f'<p class="page-summary">{esc(p["summary"])}</p>' if p["summary"] else "")
                    + f'<div class="page-meta">{"".join(meta_bits)}</div></header>')
            tail = []
            if p["related"]:
                tail.append(related_block(p["related"], ctx, p["key"], root))
            tail.append(pager(items[i - 1] if i else None, items[i + 1] if i + 1 < len(items) else None, root, ctx))
            write(p["url"], layout(title=p["title"], body=head + f'<div class="prose">{body_html}</div>' + "".join(tail),
                                   root=root, active=kind, toc=toc_html(toks), desc=p["summary"], page_id=p["key"]))
            search.append(search_item(p, body_html, toks, None, zh))
        write(f"{kind}/index.html", collection_index(kind, label, blurb, items))

    # ---- glossary, home
    write("glossary.html", glossary_page(gloss_list, ctx))
    exercises.sort(key=lambda e: 0 if e["section"].startswith("标准") else 1 + list(COLLECTIONS.values()).index(
        next(v for v in COLLECTIONS.values() if v[0] == e["section"])))
    write("exercises.html", exercises_page(exercises))
    for g in gloss_list:
        search.append({"t": g["en"], "e": g.get("zh", ""), "s": "", "u": f"glossary.html#{g['id']}", "k": "term",
                       "x": re.sub(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), g.get("def", ""))[:160]})
    write("index.html", home_page(clauses, by_id, ctx, pages, toc_meta))

    # ---- uncovered stable names are searchable too (link to eel.is)
    have = {s["s"] for s in search if s.get("s")}
    for e in entries:
        if e["id"] not in have:
            it = {"t": zh.get(e["id"]) or e["title"], "s": e["id"], "n": e["num"], "u": EEL + e["id"], "k": "eel"}
            if zh.get(e["id"]):
                it["e"] = e["title"]
            search.append(it)

    nav = {
        "clauses": [nav_node(c, by_id, ctx) for c in clauses],
        "collections": {k: [{"t": p["title"], "u": p["url"], "st": p["status"], "g": p.get("group", "")}
                            for p in sorted((p for p in pages.values() if p["kind"] == k), key=lambda p: (p["order"], p["title"]))]
                        for k in COLLECTIONS},
        "groups": {c["id"]: clause_group(c) for c in clauses},
    }
    (OUT / "static/js/nav-data.js").write_text(
        "window.NAV=" + json.dumps(nav, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (OUT / "static/js/search-data.js").write_text(
        "window.SEARCH=" + json.dumps(search, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    (OUT / "static/build-id.txt").write_text(str(dt.datetime.now().timestamp()))

    n_std = len(ctx.std_pages)
    print(f"built {len(pages)} pages ({n_std} std, " +
          ", ".join(f"{sum(1 for p in pages.values() if p['kind'] == k)} {k}" for k in COLLECTIONS) +
          f"), {len(gloss_list)} glossary terms -> {OUT}")
    for w in WARNINGS:
        print("  warning:", w)
    if "--check" in sys.argv:
        shutil.rmtree(OUT, ignore_errors=True)
    return 1 if "--strict" in sys.argv and WARNINGS else 0


def nav_node(e, by_id, ctx):
    n = {"i": e["id"], "n": e["num"], "t": e["title"]}
    if ctx.zh.get(e["id"]):
        n["z"] = ctx.zh[e["id"]]
    if e["id"] in ctx.std_pages:
        n["p"] = ctx.std_pages[e["id"]]["status"]
    elif e["id"] in ctx.covered:
        n["p"] = "cov"
        sec = ctx.section_of(e["id"])
        n["u"] = ctx.covered[e["id"]]["url"] + (f"#{sec}" if sec else "")
        n["h"] = ctx.covered[e["id"]]["id"]
    if e["children"]:
        n["c"] = [nav_node(by_id[c], by_id, ctx) for c in e["children"]]
    return n


def coverage(e, by_id, ctx):
    """(covered, total) over this entry's descendants; a section counts as covered if it or an ancestor
    below the clause has a page that lists it in `covers`, or has its own page."""
    covered = total = 0
    covers_all = set()
    for p in ctx.std_pages.values():
        for c in p["covers"]:
            covers_all.add(c)

    def walk(eid, inherited):
        nonlocal covered, total
        x = by_id[eid]
        has = eid in ctx.std_pages or eid in covers_all or inherited
        total += 1
        covered += 1 if has else 0
        page = ctx.std_pages.get(eid)
        inh = inherited or bool(page and "*" in page["covers"])
        for c in x["children"]:
            walk(c, inh)

    own = ctx.std_pages.get(e["id"])
    for c in e["children"]:
        walk(c, bool(own and "*" in own["covers"]))
    if not e["children"]:
        total, covered = 1, 1 if e["id"] in ctx.std_pages else 0
    return covered, total


def progress_bar(covered, total):
    pct = 0 if not total else round(100 * covered / total)
    return (f'<span class="progress" title="{covered}/{total} 个条款已有笔记"><span class="bar"><span style="width:{pct}%"></span></span>'
            f'<span class="pct">{covered}/{total}</span></span>')


def related_block(rel, ctx, key, root):
    items = "".join(f"<li>{xref_html(r, None, ctx, key)}</li>" for r in rel).replace("{ROOT}", root)
    return f'<section class="related"><h2 id="related">相关阅读</h2><ul>{items}</ul></section>'


def pager(prev_p, next_p, root, ctx):
    def card(p, cls, label):
        if not p:
            return f'<span class="pager-{cls}"></span>'
        sn = f' <span class="sn">[{esc(p["id"])}]</span>' if p["kind"] == "std" else ""
        return f'<a class="pager-{cls}" href="{root}{p["url"]}"><span class="pager-label">{label}</span><span class="pager-title">{esc(p["title"])}{sn}</span></a>'
    return f'<nav class="pager">{card(prev_p, "prev", "← 上一篇")}{card(next_p, "next", "下一篇 →")}</nav>'


def source_note(p, toc_meta):
    commit = toc_meta.get("draft_commit") or ""
    return (f'<footer class="page-foot">标准原文以 <a href="{EEL}{p["id"]}" target="_blank" rel="noopener">eel.is/c++draft/{esc(p["id"])}</a> 为准'
            f'（工作草案 {esc(toc_meta.get("generated") or "")}，commit <code>{esc(commit[:10])}</code>）。'
            f'本页为学习笔记，叙述以释义为主，段落号 ¶ 对应草案段落。'
            + (f' 最后更新 {esc(p["updated"])}。' if p["updated"] else "") + '</footer>')


def search_item(p, body_html, toks, e, zh):
    heads = []

    def walk(ts):
        for t in ts:
            heads.append(re.sub(r"<[^>]+>", "", html.unescape(t["name"])).rstrip("#").strip())
            walk(t.get("children", []))
    walk(toks)
    item = {"t": p["title"], "u": p["url"], "k": p["kind"], "x": (p["summary"] or plain_text(body_html))[:200],
            "h": " · ".join(heads)[:400]}
    if e:
        item.update({"s": e["id"], "e": e["title"], "n": e["num"]})
    return item


def std_index(clauses, by_id, ctx, toc_meta):
    root = "../"
    groups = {"lang": ("核心语言", "Core language · 第 1–15 章"), "lib": ("标准库", "Library · 第 16–33 章"),
              "annex": ("附录", "Annexes A–G")}
    out = [f'<header class="page-head"><h1>标准逐节</h1><div class="page-en">ISO/IEC 14882 working draft, section by section</div>'
           f'<p class="page-summary">按标准自身的章节结构组织。加粗条目已有笔记，灰色条目（↗）直接链接到 eel.is 原文。'
           f'草案版本：{esc(toc_meta.get("generated") or "")}（<a href="https://github.com/Eelis/draft/commit/{esc(toc_meta.get("draft_commit") or "")}" target="_blank" rel="noopener">{esc((toc_meta.get("draft_commit") or "")[:10])}</a>）。</p></header>']
    for g, (name, sub) in groups.items():
        cards = []
        for c in clauses:
            if clause_group(c) != g:
                continue
            cov, tot = coverage(c, by_id, ctx)
            title = ctx.zh.get(c["id"]) or c["title"]
            cards.append(f'<a class="clause-card" href="{root}std/{c["id"]}.html"><span class="num">{esc(c["num"])}</span>'
                         f'<span class="t">{esc(title)}</span><span class="en">{esc(c["title"])} <span class="sn">[{esc(c["id"])}]</span></span>'
                         f'{progress_bar(cov, tot)}</a>')
        out.append(f'<section class="clause-group"><h2 id="{g}">{name} <small>{sub}</small></h2><div class="clause-grid">{"".join(cards)}</div></section>')
    return layout(title="标准逐节", body="".join(out), root=root, active="std", page_id="std-index")


def collection_index(kind, label, blurb, items):
    root = "../"
    if items:
        def card(p):
            return (f'<a class="topic-card" href="{root}{p["url"]}"><span class="t">{esc(p["title"])}</span>'
                    f'<span class="s">{esc(p["summary"])}</span><span class="m">{status_badge(p["status"])}'
                    + "".join(f'<span class="tag">{esc(t)}</span>' for t in p["tags"][:4]) + '</span></a>')
        groups = {}
        for p in items:  # groups keep the order of their first page
            groups.setdefault(p.get("group", ""), []).append(p)
        body = "".join((f'<h2 class="coll-group">{esc(g)}</h2>' if g else "")
                       + f'<div class="topic-grid">{"".join(card(p) for p in ps)}</div>' for g, ps in groups.items())
    else:
        body = '<p class="empty">这一栏还在准备中。</p>'
    return layout(title=label, root=root, active=kind, page_id=f"{kind}-index",
                  body=f'<header class="page-head"><h1>{label}</h1><p class="page-summary">{esc(blurb)}</p></header>{body}')


def glossary_page(gloss_list, ctx):
    root = ""
    rows = []
    for g in sorted(gloss_list, key=lambda g: g["en"].lower()):
        d, _ = render_markdown(g.get("def", ""), ctx, "glossary")
        d = d.replace("{ROOT}", root)
        ref = xref_html(g["ref"], None, ctx, "glossary").replace("{ROOT}", root) if g.get("ref") else ""
        rows.append(f'<div class="term" id="{esc(g["id"])}"><dt><span class="en">{esc(g["en"])}</span>'
                    f'<span class="zh">{esc(g.get("zh", ""))}</span>{ref}</dt><dd>{d}</dd></div>')
    body = (f'<header class="page-head"><h1>术语表</h1><div class="page-en">Glossary</div>'
            f'<p class="page-summary">标准术语的中英对照与释义。正文中带虚线下划线的术语可悬停查看定义。</p>'
            f'<div class="page-meta"><input class="gloss-filter" type="search" placeholder="筛选术语…"></div></header>'
            f'<dl class="glossary">{"".join(rows)}</dl>')
    return layout(title="术语表", body=body, root=root, active="glossary", page_id="glossary")


def home_page(clauses, by_id, ctx, pages, toc_meta):
    root = ""
    tot_cov = tot_all = 0
    rows = []
    for c in clauses:
        cov, tot = coverage(c, by_id, ctx)
        tot_cov += cov
        tot_all += tot
    home_md = CONTENT / "_home.md"
    intro = ""
    if home_md.exists():
        intro, _ = render_markdown(parse_frontmatter(home_md.read_text(encoding="utf-8"))[1], ctx, "home")
        intro = intro.replace("{ROOT}", root)
    lang = [c for c in clauses if clause_group(c) == "lang"]
    for c in lang:
        cov, tot = coverage(c, by_id, ctx)
        rows.append(f'<a class="cov-row" href="std/{c["id"]}.html"><span class="num">{esc(c["num"])}</span>'
                    f'<span class="t">{esc(ctx.zh.get(c["id"]) or c["title"])}</span>{progress_bar(cov, tot)}</a>')
    recent = sorted((p for p in pages.values() if p["kind"] != "std" or p["id"] not in {c["id"] for c in clauses}),
                    key=lambda p: p.get("updated", ""), reverse=True)[:8]
    counts = {k: sum(1 for p in pages.values() if p["kind"] == k) for k in ("std", *COLLECTIONS)}
    body = f"""
<section class="hero">
  <div class="hero-mark">§</div>
  <h1>{SITE_NAME}</h1>
  <p class="hero-en">{SITE_SUB}</p>
  <p class="hero-lede">逐条读 C++ 标准：每一节给出条文的<strong>释义</strong>，补上标准不写的<strong>设计动机与条款关联</strong>，再用能直接编译运行的<strong>例子</strong>把规则落到实处。</p>
  <button class="hero-search search-btn" type="button"><span>检索条款或关键词：如 <code>basic.life</code>、<code>dcl.init.list</code>、<code>over.match.best</code></span><kbd>/</kbd></button>
  <div class="hero-stats">
    <div><b>{counts['std']}</b><span>条款笔记</span></div>
    <div><b>{counts['topics']}</b><span>专题</span></div>
    <div><b>{counts['patterns']}</b><span>惯用法与模式</span></div>
    <div><b>{counts['toolchain']}</b><span>工具链</span></div>
    <div><b>{counts['history']}</b><span>沿革</span></div>
    <div><b>{len(ctx.glossary)}</b><span>术语</span></div>
    <div><b>{round(100 * tot_cov / max(tot_all, 1))}%</b><span>条款覆盖</span></div>
  </div>
</section>
<div class="prose home-intro">{intro}</div>
<section class="home-cov"><h2 id="coverage">核心语言覆盖进度</h2><div class="cov-list">{''.join(rows)}</div>
<p class="more"><a href="std/index.html">全部章节（含标准库与附录）→</a></p></section>
"""
    return layout(title=SITE_NAME, body=body, root=root, active="home", page_id="home", body_class="home")


def write(rel, text):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def snapshot():
    files = [ROOT / "build.py"]
    for d in (CONTENT, DATA, STATIC):
        files.extend(p for p in d.rglob("*") if p.is_file())
    return {str(p): p.stat().st_mtime for p in files if p.exists()}


def watch_loop():
    import time
    last = snapshot()
    while True:
        time.sleep(1.5)
        cur = snapshot()
        me = str(ROOT / "build.py")
        if cur.get(me) != last.get(me):
            print("build.py changed, restarting")
            os.execv(sys.executable, [sys.executable] + sys.argv)  # pick up the new generator code
        if cur != last:
            last = cur
            WARNINGS.clear()
            try:
                build()
            except Exception as ex:  # a page may be half-written; try again on the next change
                print("  build failed:", ex)


if __name__ == "__main__":
    code = build()
    if "--watch" in sys.argv:
        import threading
        threading.Thread(target=watch_loop, daemon=True).start()
    if "--serve" in sys.argv:
        import functools
        import http.server
        port = 8766
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        print(f"serving on http://localhost:{port}")
        http.server.ThreadingHTTPServer(("", port), handler).serve_forever()
    sys.exit(code)
