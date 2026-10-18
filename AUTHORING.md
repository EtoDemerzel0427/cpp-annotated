# 写作规范 · C++ 标准注疏

本站的目标读者想成为 **language lawyer**：能指着标准的具体段落解释一段代码为什么良构、为什么是 UB、为什么重载决议选了这个函数。
所以每一页都要做到三件事：**准确**（以当前草案为准，段落号对得上）、**讲透**（释义 + 动机 + 上下文，而不是翻译）、**可验证**（例子能在 Compiler Explorer 里跑）。

---

## 1. 文件与命名

| 内容 | 路径 | 说明 |
|---|---|---|
| 标准条款笔记 | `content/std/<stable-name>.md` | 文件名必须是 `data/toc.json` 里的 stable name，如 `basic.life.md` |
| 章节导读 | `content/std/<clause>.md` | 如 `basic.md`：显示在第 6 章总览页顶部 |
| 专题 | `content/topics/<slug>.md` | 跨条款主题，如 `value-categories.md` |
| 工具链 | `content/toolchain/<slug>.md` | 编译、链接、ABI、构建等 |
| 提案 | `content/papers/<slug>.md` | 如 `p2996-reflection.md` |
| 术语 | `data/glossary/<任意名>.json` | 构建时合并所有文件；不同作者写不同文件，避免冲突 |
| 中文标题 | `data/zh-titles.json` | `{stable-name: 中文标题}` |

**粒度**：默认一个二级条款（如 `basic.def.odr`、`dcl.init`）一页。二级条款太大时（如 `expr.compound`、`basic.memobj`、`over.match`），按三级条款拆页（`basic.life.md`、`basic.stc.md` …），父条款可以另写一个导读页，也可以不写。
一页覆盖了若干没有单独成页的子条款时，在 frontmatter 里用 `covers` 列出它们（`covers: *` 表示覆盖全部后代），覆盖率统计会算进去。

查看完整目录结构：

```bash
python3 -c "import json;[print('  '*(e['level']-1)+e['num'],e['id'],e['title']) for e in json.load(open('data/toc.json'))['entries']]" | less
```

## 2. Frontmatter

```yaml
---
title: 对象生命周期              # 中文标题（必填）
summary: 一句话说清本节管什么      # 显示在标题下、搜索结果、链接悬停提示里（必填）
status: draft                   # stub | draft | done
covers: basic.life, basic.indet # 可选：本页一并覆盖的子条款
since: c++11                    # 可选：特性引入版本（专题/提案页常用）
papers: P0593R6, P1971R0        # 可选：相关提案（只写确定存在且相关的）
related: basic.stc, topics/object-model   # 可选：页尾"相关阅读"
tags: 对象模型, UB               # 可选
order: 10                       # 可选：专题/工具链列表中的排序
updated: 2026-10-17
---
```

`status`：`stub` = 只有骨架；`draft` = 主体已写、可能有遗漏；`done` = 覆盖本节全部规范性段落，例子和陷阱齐全，经过核对。

## 3. 语法扩展

| 写法 | 效果 |
|---|---|
| `[[basic.life]]` | 链接到条款：本站有笔记则站内链接，否则链接到 eel.is；悬停显示标题 |
| `[[basic.life#6]]` / `[[basic.life/6]]` | 链接到具体段落（显示为 `[basic.life]/6`） |
| `[[basic.life\|生命周期]]` | 自定义链接文字 |
| `[[topics/value-categories]]` | 站内其他页面 |
| `[[P2996R13]]` `[[N4950]]` `[[CWG2551]]` `[[LWG3000]]` | 提案 / 核心语言 issue / 库 issue，链接到 wg21.link |
| `[[g:odr-use]]` | 术语表词条（悬停显示定义）。只能引用已存在的词条 |
| `¶3` | 段落标记，渲染为朱色 ¶3，并生成锚点 `#p3`。每段释义以对应段落号开头 |
| `{{c++20}}` `{{c++26}}` | 版本徽章 |
| `{{ub}}` `{{ifndr}}` `{{ill-formed}}` `{{well-formed}}` `{{impl}}` `{{unspec}}` `{{erroneous}}` `{{deprecated}}` `{{removed}}` `{{dr}}` | 行为分类徽章；可带参数如 `{{removed:C++20}}` |

宏在行内代码 `` `...` `` 和代码块里不会展开。

### 提示框（admonition）

```markdown
!!! std
    标准原文的关键句（简短引用，英文原文），以及紧随其后的一句中文释义。

!!! note "可选自定义标题"
    内容需要缩进 4 空格。
```

类型：`std`（标准怎么说）、`note`、`tip`、`warning`、`pitfall`（常见误解）、`ub`、`example`、`history`（历史与演进）、`impl`（实现视角：GCC/Clang/MSVC/ABI）、`question`（思考题）、`summary`、`lawyer`（钻牛角尖的边界情况）。

折叠的答案：

```markdown
<details markdown="1">
<summary>答案</summary>

答案正文，可以有代码块。
</details>
```

### 代码块

````markdown
```cpp run title="odr.cpp" ok
int main() { }
```
````

信息串：第一个词是语言（默认 cpp）。可选标记：

- **判定**（显示在代码块右上角，并给边框着色）：`ok`（良构，行为明确）、`error`（非良构）、`ub`、`ifndr`、`unspecified`、`impl`、`eb`。整段代码只能有一个判定；混合情况不加判定，改在行尾注释里写。
- `run` 或 `godbolt`：生成 "godbolt ↗" 按钮，一键在 Compiler Explorer 中用 Clang trunk + GCC trunk、`-std=c++2c` 打开（有 `main` 时还会运行）。
  可选 `std=c++20`、`flags="-std=c++20 -O0"`、`cc=clang_trunk`（逗号分隔的 Compiler Explorer 编译器 id，如 `gsnapshot`、`clang_trunk`、`vcpp_v19_latest_x64`）。
- `title="a.cpp"`：文件名标题，适合多翻译单元的例子（每个 TU 一个代码块）。

行尾注释的约定（会被自动着色）：`// OK`、`// error: 原因`、`// UB: 原因`、`// IFNDR`。沿用标准例子的写法。

## 4. 页面结构（标准条款页）

不需要机械套用，但一页好的笔记通常包含：

1. **导读**（无标题的开头段落 + 必要时一个"为什么需要这一节"小节）：这一节解决什么问题？在整本标准里处于什么位置？读之前需要知道哪些概念（链接过去）？
2. **逐段释义**：按段落分组，用二级/三级标题组织（标题用中文概括主题，如"## 生命周期何时开始（¶2）"）。每段以 `¶N` 开头，用中文重述规则，**解释它为什么这样规定**，指出关键术语的精确含义。专有名词第一次出现时给英文：**潜在求值**（potentially-evaluated）。
3. **例子**：每条重要规则配一个最小例子，标上判定；标准自带的例子可以改编，但要加上解释，不要只贴原文。好例子展示边界：刚好合法 vs 刚好非法。
4. **实现视角**（适用时）：主流编译器怎么实现、ABI 后果、诊断长什么样、哪些规则编译器实际不检查。
5. **历史与演进**（适用时）：C++98 → 26 的变化，相关提案与 CWG issue。**只引用你确定的编号**。
6. **陷阱 / 常见误解**。
7. **思考题**（1–3 个，带折叠答案）：language lawyer 式的题目。
8. **小结**：一张表或几条要点。

专题页、工具链页更自由，但同样要求有例子、有出处（链接到条款）。

## 5. 准确性规则（最重要）

- **以当前草案为准**。动笔前先读原文：
  ```bash
  python3 tools/eel.py basic.life        # 打印条款纯文本，带 ¶ 段落号和 (2.1) 列表项号
  ```
  草案是 C++26 工作草案（含 contracts、静态反射、expansion statements、erroneous behavior 等）。凡是 C++26 新增的规则，标 `{{c++26}}` 并说明在 C++23 及之前是什么情况。
- 段落号必须与当前草案一致。引用列表项用 `¶2.3` 的形式。
- **不要编造**提案号、CWG/LWG issue 号、编译器版本号、编译器诊断原文。不确定就不写编号，改用描述（"C++20 中通过提案修改"）。
- 不要大段照抄标准原文。`!!! std` 里只引用最关键的一两句（每处不超过约 40 个英文单词），其余一律用中文释义。目的是读懂，不是翻译。
- 例子要能编译（除非标了 `error`），要符合判定。不确定某个例子在当前编译器上的表现时，说清楚"标准规定 X；截至写作时某编译器尚未实现"之类，而不是断言。
- 区分 **规范性**（normative）文字和 **注/例**（notes/examples 不具规范效力）。
- 区分 ill-formed（必须诊断）、IFNDR、UB、unspecified、implementation-defined，这是 language lawyer 的基本功。

## 6. 文风

- 中文为主，术语保留英文（ODR、odr-use、glvalue、TU…）；英文术语与中文之间不强求空格，但保持一页之内一致。
- 释义要比原文**更好懂**：先给直觉，再给精确表述；多用"换句话说"、"为什么？因为…"。
- 不写空话（"这一节非常重要"）。每句话都应该承载信息。
- 表格适合做分类对比（如各种初始化形式 × 结果）。
- 链接要多：提到另一个条款的概念就 `[[链接]]` 过去。

## 7. 构建与检查

```bash
python3 build.py            # 构建到 _site/，打印所有警告（坏链接、未知术语、未知徽章）
python3 build.py --check    # 只检查（渲染到临时目录），多人同时写作时用这个，避免互相覆盖 _site/
python3 build.py --strict   # 有警告时返回非零
python3 build.py --serve    # 构建后在 http://localhost:8766 预览
```

提交前确保自己写的页面没有警告。

## 8. 验证例子

本机有 Homebrew Clang 23（libc++），支持 `-std=c++2c`：

```bash
clang++ -std=c++2c -Wall -Wextra -pedantic -fsyntax-only x.cpp   # 检查是否良构
clang++ -std=c++2c -O0 -fsanitize=address,undefined x.cpp -o x && ./x   # 运行 / 抓 UB
```

标了 `ok` 的例子应能通过编译；标了 `error` 的例子应被拒绝（如果 Clang 接受了一个标准说非良构的程序，在正文里注明这是编译器缺陷或尚未实现）。
临时文件放在 `/tmp` 或自己的临时目录，不要放进仓库。
