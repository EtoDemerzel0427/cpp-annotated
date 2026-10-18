# C++ 标准注疏 · The Annotated C++ Standard

逐条精读 C++ 标准（[eel.is/c++draft](https://eel.is/c++draft/) 工作草案）的中文学习站：每一节给出释义、动机与上下文、可在 Compiler Explorer 中运行的例子，以及专题、工具链和提案解读。

纯静态站点，Python 生成，无前端构建步骤。

## 本地运行

```bash
pip install markdown pygments
python3 build.py --serve        # http://localhost:8766
```

`_site/` 是构建产物（不入库）。打开 `_site/index.html` 也能直接浏览。

## 部署到 GitHub Pages

推到 GitHub 后，在仓库 Settings → Pages 里把 Source 设为 **GitHub Actions**。`.github/workflows/pages.yml` 会在每次推送 `main` 时构建并发布。

## 目录

```
build.py                 静态站点生成器（Markdown → HTML，代码高亮、交叉引用、搜索索引、覆盖率）
AUTHORING.md             写作规范：语法扩展、页面结构、准确性规则
content/std/             标准条款笔记，文件名 = stable name（如 basic.life.md）
content/topics/          专题
content/toolchain/       工具链
content/papers/          提案解读
content/_home.md         首页正文
data/toc.json            草案完整目录（tools/fetch_toc.py 生成）
data/zh-titles.json      条款中文标题
data/glossary/*.json     术语表（构建时合并）
static/                  CSS / JS / 图标
tools/fetch_toc.py       从 eel.is 更新目录
tools/eel.py             把某一条款打印成带段落号的纯文本，写作时对照原文用
```

## 更新草案版本

```bash
python3 tools/fetch_toc.py   # 刷新 data/toc.json；之后 build.py 会对已失效的 stable name 给出警告
```
