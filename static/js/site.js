/* C++ 标准注疏 · 全站交互：主题、侧栏、搜索、悬停提示、代码复制、目录高亮 */
(function () {
  "use strict";
  var body = document.body;
  var ROOT = body.dataset.root || "";
  var PAGE = body.dataset.page || "";
  var NAV = window.NAV || { clauses: [], collections: {}, groups: {} };
  var EEL = "https://eel.is/c++draft/";
  var EN = document.documentElement.lang === "en";   // English edition: en/<kind>/<slug>.html
  var NAV_EN = window.NAV_EN || {};
  var CLAUSES = (EN ? NAV_EN.clauses : NAV.clauses) || [];   // English clause tree only exists once a note is translated
  var STD = EN ? "en/std/" : "std/";

  function store(k, v) {
    try { if (v === undefined) return localStorage.getItem("cppstd." + k); localStorage.setItem("cppstd." + k, v); } catch (e) { return null; }
  }
  function el(tag, attrs, html) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (html != null) n.innerHTML = html;
    return n;
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  /* ---------------- theme ---------------- */
  var themeBtn = document.querySelector(".theme-toggle");
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var cur = document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store("theme", next);
  });

  /* ---------------- sidebar ---------------- */
  var sidebar = document.getElementById("sidebar");
  var navToggle = document.querySelector(".nav-toggle");
  if (navToggle) navToggle.addEventListener("click", function () { body.classList.toggle("nav-open"); });
  document.addEventListener("click", function (e) {
    if (body.classList.contains("nav-open") && !sidebar.contains(e.target) && !navToggle.contains(e.target)) body.classList.remove("nav-open");
  });

  function hasPage(n) { return !!n.p; }
  function subtreeHasPage(n) {
    if (n._hp !== undefined) return n._hp;
    var r = hasPage(n);
    if (n.c) for (var i = 0; i < n.c.length; i++) if (subtreeHasPage(n.c[i])) r = true;
    return (n._hp = r);
  }
  function findPath(nodes, id, path) {
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.i === id) return path.concat([n]);
      if (n.c) { var r = findPath(n.c, id, path.concat([n])); if (r) return r; }
    }
    return null;
  }
  var curPath = findPath(CLAUSES, PAGE, []) || [];
  var openSet = {};
  curPath.forEach(function (n) { openSet[n.i] = true; });

  function nodeHref(n, depth) {
    if (n.u) return { href: ROOT + n.u, local: true };
    if (depth === 0 || n.p) return { href: ROOT + STD + n.i + ".html", local: true };
    return { href: EEL + n.i, local: false };
  }
  function renderTree(nodes, depth) {
    var ul = el("ul", depth === 0 ? { class: "sb-tree" } : null);
    nodes.forEach(function (n) {
      var li = el("li");
      if (!subtreeHasPage(n) && depth > 0) li.className = "empty";
      if (openSet[n.i]) li.classList.add("open");
      var row = el("div", { class: "sb-row" });
      var caret = el("button", { class: "sb-caret" + (n.c ? "" : " spacer"), type: "button", "aria-label": EN ? "Expand" : "展开" }, "▶");
      var h = nodeHref(n, depth);
      var cls = "sb-link " + (h.local ? "has-page" : "no-page") + (n.p ? " st-" + n.p : "");
      if (depth === 0) cls = "sb-link" + (subtreeHasPage(n) ? " has-page" : "") ;
      if (n.i === PAGE) { cls += " current"; row.classList.add("current"); }
      var tip = n.t + "  [" + n.i + "]" + (n.h ? (EN ? "\nexplained on the [" + n.h + "] page" : "\n在 [" + n.h + "] 页中讲解") : h.local ? "" : "  ↗ eel.is");
      var a = el("a", { class: cls, href: h.href, title: tip },
        '<span class="n">' + esc(n.n) + '</span><span class="l">' + esc(EN ? n.t : n.z || n.t) + "</span>");
      if (!h.local) { a.target = "_blank"; a.rel = "noopener"; }
      row.appendChild(caret); row.appendChild(a); li.appendChild(row);
      if (n.c) {
        var built = false;
        var build = function () { if (!built) { li.appendChild(renderTree(n.c, depth + 1)); built = true; } };
        if (li.classList.contains("open")) build();
        caret.addEventListener("click", function () { build(); li.classList.toggle("open"); });
      }
      ul.appendChild(li);
    });
    return ul;
  }

  var TABS = [
    { k: "lang", label: "核心语言" }, { k: "lib", label: "标准库" }, { k: "annex", label: "附录" },
    { k: "topics", label: "专题" }, { k: "patterns", label: "模式" }, { k: "perf", label: "性能" },
    { k: "toolchain", label: "工程" }, { k: "history", label: "沿革" }, { k: "papers", label: "提案" },
    { k: "exams", label: "考卷" }
  ];
  if (EN) {
    var EN_LABEL = { topics: "Topics", patterns: "Patterns", perf: "Performance", toolchain: "Engineering", history: "History", papers: "Papers", exams: "Quizzes" };
    TABS = (NAV_EN.clauses ? [{ k: "lang", label: "Core" }, { k: "lib", label: "Library" }, { k: "annex", label: "Annexes" }] : [])
      .concat(Object.keys(NAV_EN).filter(function (k) { return k !== "clauses"; }).map(function (k) { return { k: k, label: EN_LABEL[k] || k }; }));
  }
  function defaultTab() {
    var act = body.dataset.active;
    if (EN && curPath.length) return NAV.groups[curPath[0].i] || "lang";
    if (EN) return NAV_EN[act] && act !== "clauses" ? act : (TABS[0] && TABS[0].k);
    if (curPath.length) return NAV.groups[curPath[0].i] || "lang";
    if (act === "topics" || act === "patterns" || act === "perf" || act === "toolchain" || act === "history" || act === "papers" || act === "exams") return act;
    return store("tab") || "lang";
  }
  function renderSidebar(tab) {
    if (!sidebar) return;
    sidebar.innerHTML = "";
    var tabs = el("div", { class: "sb-tabs", role: "tablist" });
    TABS.forEach(function (t) {
      var b = el("button", { class: "sb-tab", type: "button", role: "tab", "aria-selected": String(t.k === tab) }, t.label);
      b.addEventListener("click", function () { store("tab", t.k); renderSidebar(t.k); });
      tabs.appendChild(b);
    });
    sidebar.appendChild(tabs);
    if (tab === "lang" || tab === "lib" || tab === "annex") {
      sidebar.classList.remove("sb-hide-empty");
      sidebar.appendChild(el("div", { class: "sb-legend" },
        EN ? '<span><i class="dot"></i>own page</span><span><i class="dot hollow"></i>explained on a parent page</span>'
           : '<span><i class="dot"></i>独立成页</span><span><i class="dot hollow"></i>在上级条款页中讲解</span>'));
      var nodes = CLAUSES.filter(function (c) { return NAV.groups[c.i] === tab; });
      sidebar.appendChild(renderTree(nodes, 0));
    } else {
      sidebar.classList.remove("sb-hide-empty");
      var items = (EN ? NAV_EN[tab] : NAV.collections && NAV.collections[tab]) || [];
      if (!items.length) { sidebar.appendChild(el("div", { class: "sb-empty" }, EN ? "Nothing here yet." : "还没有内容。")); return; }
      var ul = el("ul", { class: "sb-plain" });
      var lastG = "";
      items.forEach(function (it) {
        if (it.g && it.g !== lastG) { ul.appendChild(el("li", { class: "sb-group" }, esc(it.g))); lastG = it.g; }
        var cur = PAGE === it.u.replace(/\.html$/, "");
        ul.appendChild(el("li", null, '<a href="' + ROOT + it.u + '"' + (cur ? ' class="current"' : "") + ">" + esc(it.t) + "</a>"));
      });
      sidebar.appendChild(ul);
    }
    var cur = sidebar.querySelector(".sb-row.current, .sb-plain a.current");
    if (cur) cur.scrollIntoView({ block: "center" });
  }
  renderSidebar(defaultTab());

  /* ---------------- search ---------------- */
  var modal = document.querySelector(".search-modal");
  var input = modal && modal.querySelector(".search-input");
  var list = modal && modal.querySelector(".search-results");
  var DATA = null;
  function loadSearch(cb) {
    if (DATA) return cb();
    var sc = document.createElement("script");
    sc.src = ROOT + "static/js/search-data.js";
    sc.onload = function () {
      DATA = (window.SEARCH || []).filter(function (it) { return EN ? it.l === "en" || !!it.s : it.l !== "en"; });
      // the English edition has no clause notes: every stable name goes to the draft itself, under its English title
      if (EN) {
        var have = {};
        DATA.forEach(function (it) { if (it.l === "en" && it.s) have[it.s] = true; });
        DATA = DATA.filter(function (it) { return it.l === "en" || !have[it.s]; });
      }
      if (EN) DATA = DATA.map(function (it) {
        return it.l === "en" ? it : { t: it.e || it.t, s: it.s, n: it.n, u: EEL + it.s, k: it.k === "clause" ? "clause" : "eel" };
      });
      cb();
    };
    sc.onerror = function () { DATA = []; cb(); };
    document.head.appendChild(sc);
  }
  var sel = 0, results = [];
  var KIND = EN ? { clause: "clause ↗", topics: "topic", patterns: "pattern", perf: "performance", toolchain: "engineering", history: "history", papers: "paper", std: "note", exams: "quiz", term: "term", eel: "draft ↗" }
               : { std: "笔记", clause: "章", topics: "专题", patterns: "模式", perf: "性能", toolchain: "工程", history: "沿革", papers: "提案", term: "术语", eel: "原文 ↗" };

  function openSearch() {
    if (!modal) return;
    modal.hidden = false; input.value = ""; input.focus();
    loadSearch(function () { doSearch(input.value); });
  }
  function closeSearch() { if (modal) modal.hidden = true; }
  document.querySelectorAll(".search-btn").forEach(function (b) { b.addEventListener("click", openSearch); });
  if (modal) modal.addEventListener("click", function (e) { if (e.target === modal) closeSearch(); });
  document.addEventListener("keydown", function (e) {
    var t = e.target, typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
    if ((e.key === "/" && !typing) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) { e.preventDefault(); openSearch(); }
    else if (e.key === "Escape") { closeSearch(); body.classList.remove("nav-open"); }
  });

  function score(it, terms, q) {
    var s = (it.s || "").toLowerCase(), t = (it.t || "").toLowerCase(), en = (it.e || "").toLowerCase();
    var h = (it.h || "").toLowerCase(), x = (it.x || "").toLowerCase();
    var total = 0;
    if (s && s === q) total += 2000;
    else if (s && s.indexOf(q) === 0) total += 600 - s.length;
    for (var i = 0; i < terms.length; i++) {
      var w = terms[i], best = 0;
      if (s.indexOf(w) >= 0) best = Math.max(best, 300);
      if (t.indexOf(w) >= 0) best = Math.max(best, t.indexOf(w) === 0 ? 260 : 200);
      if (en.indexOf(w) >= 0) best = Math.max(best, 150);
      if (h.indexOf(w) >= 0) best = Math.max(best, 80);
      if (x.indexOf(w) >= 0) best = Math.max(best, 30);
      if (!best) return 0;
      total += best;
    }
    if (it.k !== "eel") total += 40;
    return total;
  }
  function hl(text, terms) {
    var s = esc(text);
    terms.forEach(function (w) {
      if (w.length < 1) return;
      var re = new RegExp("(" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      s = s.replace(re, "<mark>$1</mark>");
    });
    return s;
  }
  function doSearch(q) {
    if (!DATA) return;
    q = q.trim().toLowerCase();
    var terms = q.split(/\s+/).filter(Boolean);
    if (!terms.length) {
      results = DATA.filter(function (it) { return it.k === "clause"; }).slice(0, 40);
    } else {
      results = DATA.map(function (it) { return { it: it, sc: score(it, terms, q) }; })
        .filter(function (r) { return r.sc > 0; })
        .sort(function (a, b) { return b.sc - a.sc; })
        .slice(0, 50).map(function (r) { return r.it; });
    }
    sel = 0;
    list.innerHTML = results.length ? "" : EN ? '<li class="search-empty">Nothing found. Try a stable name such as <code>temp.deduct</code>.</li>'
      : '<li class="search-empty">没有找到。试试 stable name，比如 <code>temp.deduct</code>。</li>';
    results.forEach(function (it, i) {
      var href = /^https?:/.test(it.u) ? it.u : ROOT + it.u;
      var ext = /^https?:/.test(it.u);
      var li = el("li", { class: (i === 0 ? "sel " : "") + (ext ? "ext" : "") });
      li.innerHTML = '<a href="' + esc(href) + '"' + (ext ? ' target="_blank" rel="noopener"' : "") + ">" +
        '<span class="r-t">' + (it.n ? '<span class="r-num">' + esc(it.n) + "</span>" : "") + hl(it.t, terms) +
        (it.s ? '<span class="r-s">[' + hl(it.s, terms) + "]</span>" : "") + "</span>" +
        '<span class="r-k">' + (KIND[it.k] || it.k) + "</span>" +
        '<span class="r-x">' + hl(it.e && it.e !== it.t ? it.e + (it.x ? " — " + it.x : "") : (it.x || it.h || ""), terms) + "</span></a>";
      li.addEventListener("mousemove", function () { setSel(i); });
      list.appendChild(li);
    });
  }
  function setSel(i) {
    var lis = list.querySelectorAll("li");
    if (!lis.length) return;
    sel = (i + lis.length) % lis.length;
    lis.forEach(function (li, j) { li.classList.toggle("sel", j === sel); });
    lis[sel].scrollIntoView({ block: "nearest" });
  }
  if (input) {
    input.addEventListener("input", function () { doSearch(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSel(sel + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setSel(sel - 1); }
      else if (e.key === "Enter") {
        var a = list.querySelectorAll("li")[sel];
        a = a && a.querySelector("a");
        if (a) { if (a.target === "_blank") window.open(a.href, "_blank", "noopener"); else location.href = a.href; closeSearch(); }
      }
    });
  }

  /* ---------------- tooltips ---------------- */
  var tip = document.querySelector(".tip");
  var tipTimer;
  document.addEventListener("mouseover", function (e) {
    var a = e.target.closest && e.target.closest("[data-tip]");
    if (!a || !tip) return;
    clearTimeout(tipTimer);
    tipTimer = setTimeout(function () {
      tip.textContent = a.dataset.tip;
      tip.hidden = false;
      var r = a.getBoundingClientRect(), tr = tip.getBoundingClientRect();
      var x = Math.min(Math.max(8, r.left), innerWidth - tr.width - 8);
      var y = r.bottom + 8;
      if (y + tr.height > innerHeight - 8) y = r.top - tr.height - 8;
      tip.style.left = x + "px"; tip.style.top = y + "px";
    }, 180);
  });
  document.addEventListener("mouseout", function (e) {
    var a = e.target.closest && e.target.closest("[data-tip]");
    if (a) { clearTimeout(tipTimer); tip.hidden = true; }
  });

  /* ---------------- code copy ---------------- */
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".code-btn.copy");
    if (!b) return;
    var code = b.closest("figure").querySelector("pre").innerText;
    var done = function () { b.textContent = EN ? "Copied" : "已复制"; setTimeout(function () { b.textContent = EN ? "Copy" : "复制"; }, 1200); };
    if (navigator.clipboard) navigator.clipboard.writeText(code).then(done, function () {});
    else { var t = el("textarea"); t.value = code; document.body.appendChild(t); t.select(); try { document.execCommand("copy"); done(); } catch (x) {} t.remove(); }
  });

  /* ---------------- page toc scroll-spy ---------------- */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".page-toc a"));
  if (tocLinks.length && "IntersectionObserver" in window) {
    var map = {};
    tocLinks.forEach(function (a) { map[decodeURIComponent(a.hash.slice(1))] = a; });
    var visible = {};
    var obs = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) { visible[en.target.id] = en.isIntersecting; });
      var first = null;
      document.querySelectorAll(".prose h2[id], .prose h3[id]").forEach(function (h) { if (!first && visible[h.id]) first = h.id; });
      if (first) tocLinks.forEach(function (a) { a.classList.toggle("active", a === map[first]); });
    }, { rootMargin: "-60px 0px -65% 0px" });
    document.querySelectorAll(".prose h2[id], .prose h3[id]").forEach(function (h) { obs.observe(h); });
  }

  /* ---------------- glossary filter ---------------- */
  var gf = document.querySelector(".gloss-filter");
  if (gf) gf.addEventListener("input", function () {
    var q = gf.value.trim().toLowerCase();
    document.querySelectorAll(".term").forEach(function (t) { t.hidden = q && t.textContent.toLowerCase().indexOf(q) < 0; });
  });

  /* ---------------- exams: <div class="quiz" data-kind="verdict|choice|open" data-answer="…"> ---------------- */
  var quizzes = Array.prototype.slice.call(document.querySelectorAll(".prose .quiz"));
  if (quizzes.length) (function () {
    var VERDICT = EN ? [["ok", "well-formed"], ["error", "ill-formed"], ["ub", "undefined behavior"], ["ifndr", "IFNDR"],
                        ["unspecified", "unspecified"], ["impl", "implementation-defined"], ["eb", "erroneous behavior"]]
                     : [["ok", "良构"], ["error", "非良构"], ["ub", "未定义行为"], ["ifndr", "IFNDR"],
                        ["unspecified", "未指明"], ["impl", "实现定义"], ["eb", "错误行为"]];
    var KEY = "exam." + PAGE;
    var state = {};
    try { state = JSON.parse(store(KEY) || "{}") || {}; } catch (e) { state = {}; }
    function save() { store(KEY, JSON.stringify(state)); }

    var bar = el("div", { class: "quiz-bar", role: "status" });
    quizzes[0].parentNode.insertBefore(bar, quizzes[0].parentNode.firstChild);
    function refresh() {
      var done = 0, right = 0;
      quizzes.forEach(function (q, i) { var s = state[i]; if (s) { done++; if (s.ok) right++; } });
      var pct = done ? Math.round(100 * right / quizzes.length) : 0;
      bar.innerHTML = '<span class="qb-prog"><b>' + done + "</b> / " + quizzes.length + (EN ? " answered" : " 已答") + "</span>" +
        '<span class="qb-score">' + (EN ? "Correct " : "答对 ") + "<b>" + right + "</b></span>" +
        (done === quizzes.length ? '<span class="qb-final">' + (EN ? "Score " : "得分 ") + pct + "</span>" : "") +
        '<button type="button" class="qb-reset">' + (EN ? "Start over" : "重做") + "</button>";
      bar.querySelector(".qb-reset").addEventListener("click", function () {
        if (!confirm(EN ? "Clear all your answers on this quiz?" : "清除本卷的全部作答记录？")) return;
        state = {}; save(); location.reload();
      });
    }

    quizzes.forEach(function (q, i) {
      var kind = q.dataset.kind || "verdict";
      var answer = (q.dataset.answer || "").trim();
      var key = q.querySelector("details.quiz-key");
      var num = el("span", { class: "quiz-num" }, EN ? "Question " + (i + 1) : "第 " + (i + 1) + " 题");
      q.insertBefore(num, q.firstChild);
      q.id = q.id || "q" + (i + 1);
      var opts = el("div", { class: "quiz-opts" });
      if (key) q.insertBefore(opts, key); else q.appendChild(opts);
      var choices = kind === "verdict" ? VERDICT.filter(function (v) {
        return !q.dataset.options || q.dataset.options.split(/[\s,]+/).indexOf(v[0]) >= 0;
      }) : kind === "choice" ? (q.dataset.options || "A B C D").split(/[\s,]+/).map(function (c) { return [c, c]; }) : [];

      function finish(pick, ok, restoring) {
        state[i] = { p: pick, ok: ok };
        if (!restoring) save();
        q.classList.add("answered", ok ? "right" : "wrong");
        if (kind === "open") opts.innerHTML = '<span class="quiz-self ' + (ok ? "ok" : "no") + '">' + (EN ? (ok ? "Self-graded: correct" : "Self-graded: not correct") : "自评：" + (ok ? "答对" : "没答对")) + "</span>";
        opts.querySelectorAll("button").forEach(function (b) {
          b.disabled = true;
          if (b.dataset.v === answer) b.classList.add("is-answer");
          if (b.dataset.v === pick && pick !== answer) b.classList.add("is-wrong");
        });
        if (key) key.open = true;
        refresh();
      }

      if (choices.length) {
        choices.forEach(function (c) {
          var b = el("button", { type: "button", class: "quiz-opt", "data-v": c[0] }, esc(c[1]));
          b.addEventListener("click", function () { finish(c[0], c[0] === answer); });
          opts.appendChild(b);
        });
        if (state[i]) finish(state[i].p, state[i].ok, true);
      } else {  // open question: reveal, then grade yourself
        var reveal = el("button", { type: "button", class: "quiz-opt" }, EN ? "Show the answer" : "想好了，看答案");
        var yes = el("button", { type: "button", class: "quiz-opt self", "data-v": "y", hidden: "" }, EN ? "I got it right" : "我答对了");
        var no = el("button", { type: "button", class: "quiz-opt self", "data-v": "n", hidden: "" }, EN ? "I got it wrong" : "没答对");
        answer = "y";
        reveal.addEventListener("click", function () { reveal.hidden = true; yes.hidden = no.hidden = false; if (key) key.open = true; });
        yes.addEventListener("click", function () { finish("y", true); });
        no.addEventListener("click", function () { finish("n", false); });
        opts.appendChild(reveal); opts.appendChild(yes); opts.appendChild(no);
        if (state[i]) { reveal.hidden = true; yes.hidden = no.hidden = false; finish(state[i].p, state[i].ok, true); }
      }
    });
    refresh();
  })();

  /* ---------------- "also in English" banner, for readers whose browser's first language isn't Chinese ---------------- */
  var banner = document.querySelector(".lang-banner");
  if (banner && store("langBanner") !== "off") {
    var lang = (navigator.languages && navigator.languages[0]) || navigator.language || "";
    if (!/^zh\b/i.test(lang)) banner.hidden = false;
    banner.querySelector(".lang-banner-close").addEventListener("click", function () { banner.hidden = true; store("langBanner", "off"); });
  }

  /* ---------------- embedded video: platform tabs ---------------- */
  document.querySelectorAll("figure.video").forEach(function (fig) {
    var frame = fig.querySelector("iframe");
    fig.querySelectorAll(".video-tabs button").forEach(function (b, _, all) {
      b.addEventListener("click", function () {
        if (b.getAttribute("aria-selected") === "true") return;
        all.forEach(function (o) { o.setAttribute("aria-selected", o === b ? "true" : "false"); });
        frame.src = b.dataset.src;
      });
    });
  });

  /* ---------------- live reload (local preview only) ---------------- */
  if (/^(localhost|127\.0\.0\.1)$/.test(location.hostname)) {
    var lastBuild = null;
    setInterval(function () {
      fetch(ROOT + "static/build-id.txt", { cache: "no-store" }).then(function (r) { return r.ok ? r.text() : null; })
        .then(function (id) {
          if (!id) return;
          if (lastBuild && id !== lastBuild) location.reload();
          lastBuild = id;
        }, function () {});
    }, 2000);
  }
})();
