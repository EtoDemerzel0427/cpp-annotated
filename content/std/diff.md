---
title: 兼容性（Annex C）
summary: Annex C 逐版列出会让旧代码编译失败或悄悄改变含义的改动，外加 C++ 与 C 的差异；升级 -std 时用它和编译器的兼容性警告一起排查。
status: done
related: depr, intro.compliance, lex.key, headers, zombie.names
tags: 附录, 兼容性, 迁移, 升级
updated: 2026-10-19
---

!!! tldr
    - Annex C 回答的问题是：把 `-std=c++17` 换成更新的版本，哪些原来合法的代码会报错、变成未定义或者悄悄改变含义。
    - 各版本小节是累加的：从 C++17 升级到当前草案，要依次读 [[diff.cpp17]]、[[diff.cpp20]]、[[diff.cpp23]]、[[diff.cpp26]] 四节。
    - 附录只是资料性的摘要，以正文为准；它也不完整，以缺陷报告形式做的修正通常不登记。
    - 编译器查得出的不兼容，用 Clang 的 `-Wc++20-compat` 这类警告在旧模式下就能找到；静默改变行为的条目只能人工核对。

## 升级之后，哪些代码会坏

```cpp
int concept = 0;      // C++20 起 concept 是关键字
int requires = 0;     // 同上
int char8_t = 0;      // 同上
```

这三行在 C++17 中完全合法，换成 `-std=c++20` 就编译不过。标准把每一处这样的代价登记在 Annex C（Compatibility，兼容性）里：哪一节改了，改了什么，为什么改，对旧代码有什么影响。新特性本身不在这里，除非它占用了旧代码在用的名字或语法。

不是所有的不兼容都会报错。C++23 起，范围 `for` 的初始化表达式里的临时对象活到循环结束；C++20 起，`a == b` 可能找到反向的 `b == a` 候选，选中另一个函数。这类改动让同一段代码换了含义，编译器不会提示。

## 附录的结构

| 小节 | 页面 | 比较对象 | 条目数 |
|---|---|---|---|
| C.1 | [[diff.cpp26]] | 当前草案 vs C++26 | 3 |
| C.2 | [[diff.cpp23]] | 当前草案 vs C++23 | 21 |
| C.3 | [[diff.cpp20]] | 当前草案 vs C++20 | 18 |
| C.4 | [[diff.cpp17]] | 当前草案 vs C++17 | 35 |
| C.5 | [[diff.cpp14]] | 当前草案 vs C++14 | 19 |
| C.6 | [[diff.cpp11]] | 当前草案 vs C++11 | 7 |
| C.7 | [[diff.cpp03]] | 当前草案 vs C++03 | 39 |
| C.8 | [[diff.iso]] | C++ vs C | 39 |
| C.9 | [[diff.library]] | C++ 标准库 vs C 标准库 | — |

C.1 到 C.7 只记录各自那一步引入的不兼容，从 C.3 起各节的总述都写明是在前面各节之外（in addition to those listed above）。例如 [[diff.cpp20]] 只记 C++20 到 C++23 这一步，C++23 到 C++26 记在 [[diff.cpp23]]，C++26 之后的记在 [[diff.cpp26]]。所以评估一份 C++17 代码升级到当前草案的风险，要把 C.4 到 C.1 都读一遍。

当前草案是 C++26 之后的工作草案，所以有 [[diff.cpp26]] 这一节：它登记的是 C++26 发布后才并入的改动，将来会出现在下一版标准里，目前还没有编译器实现。

C.8 比较的是 C++ 与 C，没有点名具体的 C 版本；C.9 只讲 C++ 引入 C 标准库时做了哪些修改。

## 条目长什么样

每个条目由几个固定字段组成：

- **Affected subclause**：受影响的正文小节。判断时真正要读的是那里，附录只是摘要。
- **Change**：改了什么。
- **Rationale**：为什么改。附录的 Rationale 往往是一条规则最简短的设计动机说明。
- **Effect on original feature**：对旧代码的影响，通常是原来良构的代码变得非良构、行为改变、变成 IFNDR（非良构但不要求诊断）或变成 UB 中的一种。

[[diff.iso]] 的条目还多两个字段，Difficulty of converting（改写难度）和 How widely used（使用多广）；C++ 各版本之间的条目没有。本站的子页面按经验补上了改写难度，并把附录的例子在 Clang 23.1.3 上用新旧两个 `-std=` 分别编译，展示变化是否真的出现。

## 附录不能单独作依据

Annex C 标着 informative（资料性），和 [[ub]]、[[ifndr]] 一样不创造规则。代码在新标准下是否良构，由正文决定。由此有两点推论。

第一，它不完整。附录只收录委员会认为值得登记的不兼容。以缺陷报告（DR）形式做的修正被视为旧标准本来就该如此，通常不出现在这里；库实现细节造成的差异更不会出现。

第二，它不说明编译器怎么做。很多改动在编译器里作为 DR 应用到所有语言模式。例如 C++17 对 `auto x{1}` 的推导规则和继承构造函数语义的修改，Clang 在 `-std=c++14` 下也按新规则处理。所以切换 `-std=` 看不到变化，不说明附录写错了，可能是编译器早就统一了行为。

## 与 Annex D 的关系

Annex D [[depr]] 列的是仍然有效、但已经弃用的特性。一个特性从 Annex D 删除时，就会作为一条不兼容登记在 Annex C 里。例如 `std::auto_ptr` 在 C++11 被弃用，C++17 删除时登记为 [[diff.cpp14.depr]] ¶1；`<codecvt>` 和 `<strstream>` 的删除登记在 [[diff.cpp23.depr]]。所以各版本小节的最后一节通常是 Annex [depr]。

升级时两份附录要一起看：Annex C 说明这一版会坏什么，Annex D 预告下一版可能会坏什么。

## 升级 `-std=` 的步骤

第一步，在旧模式下打开兼容性警告。Clang 提供 `-Wc++11-compat`、`-Wc++14-compat`、`-Wc++17-compat`、`-Wc++20-compat`、`-Wc++23-compat`、`-Wc++2c-compat`，在旧模式下就能指出新模式会出问题的地方。对开头的三行：

```text
$ clang++ -std=c++17 -Wc++20-compat -fsyntax-only compat.cpp
compat.cpp:1:5: warning: 'concept' is a keyword in C++20 [-Wc++20-compat]
compat.cpp:2:5: warning: 'requires' is a keyword in C++20 [-Wc++20-compat]
compat.cpp:3:5: warning: 'char8_t' is a keyword in C++20 [-Wc++20-compat]
```

`-Wdeprecated` 则报告正在走向删除的用法（见 [[depr]]）。

第二步，逐节核对编译器查不出来的条目。有三类改动不会产生诊断：行为静默改变（上面提到的范围 `for` 临时对象、反向 `==` 候选）；变成 IFNDR（C++20 起同一函数在不同翻译单元里的默认实参必须相同）；变成 UB（C++20 起伪析构函数调用会结束对象的生命期）。这些只能靠人读。

第三步，留意新头文件。每一版都有一条 New headers：如果项目里有自己的 `<version>`、`<format>` 或 `<print>`，而 include 路径排在系统路径之前，升级后就会包含到错误的文件。

## 各版要点

| 版本差 | 最可能碰到的不兼容 |
|---|---|
| C++26 → 草案 | 可能抛出的 `operator delete` 声明非良构；指派初始化可指派基类成员，带来重载歧义；默认化赋值不能带 `const`/`&&` 限定 |
| C++23 → C++26 | 枚举与浮点或其他枚举混合运算非良构；数组之间直接比较非良构；`delete` 不完整类型非良构；`T...[n]` 变成包索引；`to_string(double)` 输出改变；移除 `<codecvt>`、`<strstream>`、`wstring_convert` |
| C++20 → C++23 | 范围 `for` 延长临时对象生命期；`return x;` 中可移动的名字变成 xvalue；下标里的逗号改变含义；`std::format` 的格式串在编译期检查 |
| C++17 → C++20 | 新关键字（`concept`、`requires`、`char8_t`、`co_*` 等）；`u8` 字面量的类型变成 `char8_t`；有用户声明构造函数的类不再是聚合；反向 `==` 候选；`throw()` 删除 |
| C++14 → C++17 | 三字符组删除；`register` 删除；`bool` 自增删除；异常说明进入类型系统；动态异常说明删除；`auto_ptr` 等删除 |
| C++11 → C++14 | 数字分隔符 `'`；`constexpr` 成员函数不再隐式 `const` |
| C++03 → C++11 | 新关键字；`>>` 可以闭合两层模板；窄化转换；`auto` 不再是存储类说明符；`export` 改作他用 |

写同时给 C 和 C++ 用的头文件时，读 [[diff.iso]] 和 [[diff.library]]。
