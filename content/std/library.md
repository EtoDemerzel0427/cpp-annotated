---
title: 库引言
summary: 第 16 章导读。这一章是标准库部分的总纲：库由哪些类别组成，库条文用什么写法写成（Constraints / Mandates / Preconditions……），对用户程序和实现各提出了哪些全局性的约束（namespace std、保留名字、数据竞争、异常、移出状态）。读懂这一章，才能读懂第 17–33 章的每一个库函数。
status: done
covers: library.general
related: library.c, description, conventions, requirements, utility.requirements, constraints, namespace.constraints, reserved.names, conforming, intro.structure, topics/how-to-read-the-standard
tags: 导读, 库, 阅读方法
updated: 2026-10-18
---

标准的前半部分（第 5–15 章）规定语言，从第 16 章开始是**标准库**。第 16 章 [library] 本身不定义任何类或函数，它是后面十七章库条款的总则，相当于一部法典的总则编。它回答三类问题：

1. **怎么读**：库条款的写法与核心语言完全不同（*Mandates:*、*Preconditions:*、*Effects: Equivalent to:*……），每个标签都有确定的法律后果。不懂这套写法，就容易以为 *Preconditions* 会被检查，以为 *Mandates* 能被 SFINAE 探测，这两种理解都是错的。
2. **用户能做什么、不能做什么**：能不能往 `namespace std` 里加东西？能不能特化 `std::swap`？能不能 `#define` 一个和标准库同名的宏？能不能取 `&std::toupper`？能不能 `v.push_back(std::move(v[0]))`？这些经典的 language lawyer 问题，答案全在这一章。
3. **实现能做什么、不能做什么**：实现能不能给 `std::vector::operator[]` 加 `noexcept`？能不能加默认实参？能不能让 `std::pair` 不可平凡复制？标准库函数之间会不会产生数据竞争？

## 本章地图

| 节 | 条款 | 本站页面 | 回答的问题 |
|---|---|---|---|
| 16.1 | [library.general] | 本页 | 库包含哪些类别、分布在哪些章 |
| 16.2 | [library.c] | [[library.c]] | C 标准库如何纳入；C 函数在常量求值中的语义 |
| 16.3 | [description] | [[description]]、[[conventions]] | **库条文的写法**：概要、要求、函数规范的十四种要素；exposition only、位掩码类型、CPO、独立项…… |
| 16.4.1–16.4.3 | [requirements.general]、[organization]、[using] | [[requirements]] | 库的内容、头文件、模块 `std` / `std.compat`、独立实现、如何 include / import、链接 |
| 16.4.4 | [utility.requirements] | [[utility.requirements]] | *Cpp17EqualityComparable* 等命名要求表、可交换、*Cpp17NullablePointer*、*Cpp17Hash*、*Cpp17Allocator* |
| 16.4.5 | [constraints] | [[constraints]]、[[namespace.constraints]]、[[reserved.names]] | **对程序的约束**：namespace std、保留名字、替换函数、处理函数、实参有效性、对象访问、概念的语义要求 |
| 16.4.6 | [conforming] | [[conforming]] | **对实现的约束**：头文件、宏、成员/非成员函数的自由度、constexpr、数据竞争、异常、契约断言、移出状态 |

建议的阅读顺序：先读 [[description]]（最重要），再读 [[namespace.constraints]] 与 [[constraints]]（用户最常踩的坑），然后读 [[conforming]]（理解了实现的自由度，才能写出可移植的代码），其余按需查阅。

## 本章的范围（¶1–¶2）

¶1 本章描述 **C++ 标准库**的内容、良构的 C++ 程序如何使用库，以及符合标准的实现如何提供库中的实体。

¶2 接下来的子条款描述库的描述方法（[[description]]）和组织（[[organization]]）。[[requirements]]、第 17 章（[[support]]）到第 33 章（[[exec]]），以及附录 D（[[depr]]），规定库的内容，以及对良构程序和符合标准的实现双方的库要求和约束。

注意“双方”二字：第 16 章的约束是**双向**的。[[constraints]] 约束程序，违反通常是 UB；[[conforming]] 约束实现，违反则实现不符合标准。理解库条款时，始终要问这句话是在约束谁。

## 库的类别（¶3）

¶3 库中各组件的详细规范在第 17–33 章，见表 23：

| 章 | stable name | 类别 | 代表性内容 |
|---|---|---|---|
| 17 | [[support]] | 语言支持库 | `<cstddef>`、`<limits>`、`<new>`、`<typeinfo>`、`<exception>`、`<compare>`、`<coroutine>`、`<contracts>`、`<initializer_list>`、`<source_location>` |
| 18 | [[concepts]] | 概念库 | `<concepts>` |
| 19 | [[diagnostics]] | 诊断库 | `<stdexcept>`、`<system_error>`、`<stacktrace>`、`<debugging>` |
| 20 | [[mem]] | 内存管理库 | `<memory>`、`<memory_resource>`、`<scoped_allocator>` |
| 21 | [[meta]] | 元编程库 | `<type_traits>`、`<ratio>`、`<meta>`（反射） |
| 22 | [[utilities]] | 通用工具库 | `<utility>`、`<tuple>`、`<optional>`、`<variant>`、`<any>`、`<expected>`、`<bitset>`、`<functional>`、`<bit>` |
| 23 | [[containers]] | 容器库 | `<vector>`、`<map>`、`<flat_map>`、`<hive>`、`<inplace_vector>`、`<span>`、`<mdspan>`…… |
| 24 | [[iterators]] | 迭代器库 | `<iterator>` |
| 25 | [[ranges]] | 范围库 | `<ranges>`、`<generator>` |
| 26 | [[algorithms]] | 算法库 | `<algorithm>`、`<numeric>`、`<execution>`（执行策略） |
| 27 | [[strings]] | 字符串库 | `<string>`、`<string_view>`、`<cstring>` |
| 28 | [[text]] | 文本处理库 | `<charconv>`、`<format>`、`<locale>`、`<regex>`、`<text_encoding>` |
| 29 | [[numerics]] | 数值库 | `<complex>`、`<random>`、`<valarray>`、`<cmath>`、`<numbers>`、`<linalg>`、`<simd>` |
| 30 | [[time]] | 时间库 | `<chrono>` |
| 31 | [[input.output]] | 输入/输出库 | `<iostream>`、`<fstream>`、`<print>`、`<filesystem>`、`<spanstream>`…… |
| 32 | [[thread]] | 并发支持库 | `<thread>`、`<atomic>`、`<mutex>`、`<future>`、`<stop_token>`、`<rcu>`、`<hazard_pointer>`…… |
| 33 | [[exec]] | 执行控制库 | `<execution>`（`std::execution` 发送者/接收者） |

（“代表性内容”一列是本站为便于定位而补充的，不属于表 23。个别头文件跨章，例如 `<memory>` 的特化算法在第 26 章，`<execution>` 的执行策略在第 26 章、发送者/接收者框架在第 33 章。）

¶4 ISO/IEC/IEEE 9945:2009 描述的操作系统接口下文称为 **POSIX**。（这个定义主要用于 [[namespace.posix]] 与 [[value.error.codes]]。）

## 各类别的一句话简介（¶5–¶18）

¶5–¶18 逐一简介各类别，其中有几句值得多看一眼：

- **¶5 语言支持库**提供 C++ 语言本身某些部分所需的组件，例如内存分配（[[expr.new]]、[[expr.delete]]）和异常处理（[[except]]）。这里是核心语言与库的接缝：`new` 表达式调用 `operator new`，`typeid` 产生 `std::type_info`，`<=>` 返回 `std::strong_ordering`，范围 `for` 中有 `std::initializer_list`，协程中有 `std::coroutine_handle`，契约违反时有 `std::contracts::contract_violation`。语言规则直接依赖这些库类型。
- **¶6 概念库**描述程序可以用来在编译期验证模板实参、基于类型属性做函数分派的组件。
- **¶9 元编程库**描述用于模板以及常量求值的设施，包括类型萃取、整数序列和有理数算术。“常量求值”一词呼应了 C++26 的反射（`<meta>`）。
- **¶10 通用工具库**包括供其他库组件使用的组件，例如用于动态存储管理的预定义存储分配器（[[basic.stc.dynamic]]），以及作为 C++ 程序基础设施的组件，如 tuple 和函数包装器。
- **¶11** 容器、迭代器、范围和算法库为程序提供了“最广泛使用的算法与数据结构的一个子集”。标准从未声称要包罗万象。
- **¶12 字符串库**支持 `char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 序列，以及“任何其他类字符类型”的序列，后者指的是 `basic_string<CharT, Traits>` 的泛型能力。
- **¶14 数值库**中，`valarray` 组件支持一次处理 n 个元素（n-at-a-time），在支持的平台上可能实现为并行操作。这是 C++98 时代为向量机设计留下的遗产。
- **¶16 输入/输出库**：iostream 是 C++ 程序输入输出的“主要机制”。
- **¶17 并发支持库**：创建与管理线程，原子操作、互斥、线程间通信。
- **¶18 执行控制库**：支持函数对象执行的组件，即 C++26 的 `std::execution`。

## 读库条文的五条要点

在进入各节之前，先给出几条贯穿全部库条款的阅读要点，细节在后续页面分别展开：

1. **先看标签，再看内容。** 同一句“`T` 满足 *Cpp17CopyConstructible*”，放在 *Constraints* 下是重载决议条件，放在 *Mandates* 下是编译错误，放在 *Preconditions* 下则违反即 UB（[[description]]）。
2. **Equivalent to 是规范，不是实现。** 它传递被调函数的全部要素，但不约束实现手段（[[structure.specifications#4]]）。
3. **默认是 UB。** 程序违反库的要求时，例如给 `std::sort` 一个不是严格弱序的比较器、在 `namespace std` 里加重载、往算法里传无效范围，后果几乎都是未定义行为（[[res.on.functions]]、[[res.on.arguments]]、[[namespace.std]]），而且编译器通常诊断不了。
4. **实现的自由度比你想的大。** 成员函数可以有额外的重载和默认实参，非成员函数可以 `inline`，类可以有额外的基类，头文件可以互相包含，`noexcept` 可以加强（[[conforming]]）。可移植的代码不能依赖这些表面上看到的细节。
5. **未指明的地方很多。** 名字是否在内联命名空间中（[[contents#2]]）、类是否可平凡复制（[[library.class.props]]）、能否取函数地址（[[namespace.std#6]]）、移出后的值（[[lib.types.movedfrom]]），都是未指明的。

## 历史与演进

- **C++98**：第 17 章 [lib.library] 已经确立了“总则 + 各分章”的结构，以及 *Requires / Effects / Returns / Throws / Complexity / Notes* 的函数描述方法。
- **C++11**：新增数据竞争避免（[[res.on.data.races]]）、移出状态（[[lib.types.movedfrom]]）、右值引用实参的唯一性假定（[[res.on.arguments]]）等与并发和移动语义相关的总则。
- **C++20**：概念库与 Ranges 进入标准，引入 *Constraints* / *Mandates* / *Preconditions* 等要素（[[P0788R3]]）、*Cpp17* 命名前缀、定制点对象；禁止特化标准库函数模板，引入可寻址函数的概念（[[P0551R3]]）。
- **C++23**：标准库模块 `std` 与 `std.compat`（[[P2465R3]]）；独立实现的库子集大幅扩充，改为逐条标注 *freestanding*。
- **C++26**：标准库加固（*Hardened preconditions*，[[P3471R4]]）、库中的契约断言（[[res.contract.assertions]]）、反射对库实体的限制（[[namespace.std#7]]）、算法函数对象正式成为 CPO（[[P3136R1]]）。

## 小结

!!! summary "核心要点"
    - 第 16 章是库的总则，包括描述方法（怎么读）、对程序的约束（用户的义务）和对实现的约束（实现的义务与自由）。
    - 库分 17 个类别，对应第 17–33 章，另有附录 D 的弃用设施。
    - 语言支持库是语言与库的接缝，核心语言规则直接依赖其中的类型与函数。
    - 读库条文的关键在 [[description]]：每个要素标签都有确定的法律后果。
