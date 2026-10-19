---
title: 库引言
summary: 第 16 章导读：标准库分成哪些类别、分布在哪些章，库条文用什么写法写成，以及这一章对用户程序和对实现分别提出的全局约束。
status: done
covers: library.general
related: library.c, description, conventions, requirements, utility.requirements, constraints, namespace.constraints, reserved.names, conforming, intro.structure, topics/how-to-read-the-standard
tags: 导读, 库, 阅读方法
updated: 2026-10-19
---

!!! tldr
    - 第 16 章不定义任何类或函数，它是第 17–33 章库条款的总则：库条文怎么写、用户程序必须遵守什么、实现可以做什么。
    - 这一章的约束是双向的：[[constraints]] 约束程序，违反通常是 UB；[[conforming]] 约束实现，违反就是实现不符合标准。
    - 库函数规范里的 *Constraints*、*Mandates*、*Preconditions* 等标签各有确定的后果：不参与重载决议、编译错误、违反即 UB（[[description]]）。
    - 库分成 17 个类别，对应第 17–33 章，另有附录 D 的弃用设施。

第 5–15 章规定语言本身，从第 16 章开始是**标准库**。第 16 章回答的问题都与具体的库组件无关，而对所有库组件都适用：

- 能不能往 `namespace std` 里添加声明？能不能特化 `std::swap`？能不能定义一个与标准库函数同名的宏？能不能取 `&std::toupper`？
- `v.push_back(std::move(v[0]))` 是否安全？两个线程同时调用不同 `std::vector` 对象的 `const` 成员函数，会不会有数据竞争？
- 实现能不能给 `std::vector::operator[]` 加 `noexcept`？能不能给标准库函数加默认实参、加重载？

## 本章各节

| 节 | 条款 | 本站页面 | 内容 |
|---|---|---|---|
| 16.1 | [library.general] | 本页 | 库的类别与对应的章 |
| 16.2 | [library.c] | [[library.c]] | C 标准库如何纳入；C 函数在常量求值中的语义 |
| 16.3 | [description] | [[description]]、[[conventions]] | 库条文的写法：概要、函数规范的各个要素、仅用于说明的实体、位掩码类型、定制点对象 |
| 16.4.1–16.4.3 | [requirements.general]、[organization]、[using] | [[requirements]] | 头文件、模块 `std` 与 `std.compat`、独立实现、如何包含或导入、链接 |
| 16.4.4 | [utility.requirements] | [[utility.requirements]] | *Cpp17EqualityComparable* 等命名要求、可交换、*Cpp17Hash*、*Cpp17Allocator* |
| 16.4.5 | [constraints] | [[constraints]]、[[namespace.constraints]]、[[reserved.names]] | 对程序的约束：`namespace std`、保留名字、替换函数、实参的有效性、概念的语义要求 |
| 16.4.6 | [conforming] | [[conforming]] | 对实现的约束：成员与非成员函数的自由度、`constexpr`、数据竞争、异常、移出状态 |

最常用的是 [[description]]，它说明了库函数规范的读法。其次是 [[namespace.constraints]] 与 [[constraints]]，用户代码最容易在这里违规。[[conforming]] 说明实现的自由度，了解它才能写出可移植的代码。其余各节可以按需查阅。

## 本章的范围（¶1–¶2）

¶1 本章描述 **C++ 标准库**的内容、良构的 C++ 程序如何使用库，以及符合标准的实现如何提供库中的实体。

¶2 规定库的内容、以及对程序和实现双方的库要求，分布在 [[requirements]]、第 17 章 [[support]] 到第 33 章 [[exec]]，以及附录 D [[depr]]。

所以读一句库条文时，先要分清它约束的是谁。[[constraints]] 下的要求约束程序，程序违反时通常是未定义行为，编译器一般也诊断不了。[[conforming]] 下的要求约束实现，实现违反时就不符合标准。

## 库的类别（¶3）

¶3 各组件的详细规范在第 17–33 章，见表 23。右边一列是本站补充的代表性头文件，不属于表 23：

| 章 | 条款 | 类别 | 代表性内容 |
|---|---|---|---|
| 17 | [[support]] | 语言支持库 | `<cstddef>`、`<limits>`、`<new>`、`<typeinfo>`、`<exception>`、`<compare>`、`<coroutine>`、`<contracts>`、`<initializer_list>`、`<source_location>` |
| 18 | [[concepts]] | 概念库 | `<concepts>` |
| 19 | [[diagnostics]] | 诊断库 | `<stdexcept>`、`<system_error>`、`<stacktrace>`、`<debugging>` |
| 20 | [[mem]] | 内存管理库 | `<memory>`、`<memory_resource>`、`<scoped_allocator>` |
| 21 | [[meta]] | 元编程库 | `<type_traits>`、`<ratio>`、`<meta>`（反射） |
| 22 | [[utilities]] | 通用工具库 | `<utility>`、`<tuple>`、`<optional>`、`<variant>`、`<any>`、`<expected>`、`<bitset>`、`<functional>`、`<bit>` |
| 23 | [[containers]] | 容器库 | `<vector>`、`<map>`、`<flat_map>`、`<hive>`、`<inplace_vector>`、`<span>`、`<mdspan>` 等 |
| 24 | [[iterators]] | 迭代器库 | `<iterator>` |
| 25 | [[ranges]] | 范围库 | `<ranges>`、`<generator>` |
| 26 | [[algorithms]] | 算法库 | `<algorithm>`、`<numeric>`、`<execution>`（执行策略） |
| 27 | [[strings]] | 字符串库 | `<string>`、`<string_view>`、`<cstring>` |
| 28 | [[text]] | 文本处理库 | `<charconv>`、`<format>`、`<locale>`、`<regex>`、`<text_encoding>` |
| 29 | [[numerics]] | 数值库 | `<complex>`、`<random>`、`<valarray>`、`<cmath>`、`<numbers>`、`<linalg>`、`<simd>` |
| 30 | [[time]] | 时间库 | `<chrono>` |
| 31 | [[input.output]] | 输入/输出库 | `<iostream>`、`<fstream>`、`<print>`、`<filesystem>`、`<spanstream>` 等 |
| 32 | [[thread]] | 并发支持库 | `<thread>`、`<atomic>`、`<mutex>`、`<future>`、`<stop_token>`、`<rcu>`、`<hazard_pointer>` 等 |
| 33 | [[exec]] | 执行控制库 | `<execution>`（`std::execution` 的发送者与接收者） |

有些头文件跨章。例如 `<memory>` 中的特化算法在第 26 章；`<execution>` 的执行策略在第 26 章，发送者与接收者框架在第 33 章。

¶5–¶18 各用一两句话介绍每个类别。值得注意的是 ¶5：**语言支持库**提供语言本身某些部分所需的组件，例如内存分配（[[expr.new]]、[[expr.delete]]）和异常处理（[[except]]）。这里是核心语言与库的接缝：`new` 表达式调用 `operator new`，`typeid` 产生 `std::type_info`，`<=>` 的结果是 `std::strong_ordering` 等类型，协程要用 `std::coroutine_handle`，契约违反时会构造 `std::contracts::contract_violation`。这些语言规则直接依赖库中的类型。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶4 ISO/IEC/IEEE 9945:2009 描述的操作系统接口在下文中称为 POSIX。这个名字用在 [[namespace.posix]] 和 [[value.error.codes]] 中。

¶6–¶18 依次介绍其余类别。几处措辞反映了设计意图：¶9 说元编程库服务于模板和常量求值；¶11 说容器、迭代器、范围和算法库提供的是最常用的算法与数据结构的一个子集，标准从未打算包罗万象；¶12 说字符串库除了 `char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t`，还支持任何其他类字符类型的序列，这指的是 `basic_string<CharT, Traits>` 的泛型能力；¶14 说 `valarray` 支持一次处理 n 个元素，在支持的平台上可以实现为并行操作；¶16 说 iostream 是 C++ 程序输入输出的主要机制。

</details>

## 读库条文的几条要点

1. **先看标签，再看内容。** 同一句 "`T` 满足 *Cpp17CopyConstructible*"，写在 *Constraints* 下是重载决议的条件，写在 *Mandates* 下是编译错误，写在 *Preconditions* 下则违反即 UB（[[description]]）。
2. ***Equivalent to* 规定的是效果，不是实现。** 它把那段代码的全部语义传递过来，但不约束实现的手段（[[structure.specifications#4]]）。
3. **程序违反库的要求，后果几乎都是 UB。** 给 `std::sort` 一个不满足严格弱序的比较器、在 `namespace std` 里加重载、给算法传一个无效的范围，都属于这种情况（[[res.on.functions]]、[[res.on.arguments]]、[[namespace.std]]），而且编译器通常诊断不了。
4. **实现的自由度比表面上大。** 成员函数可以有额外的重载和默认实参，类可以有额外的基类，头文件可以互相包含，`noexcept` 可以加强（[[conforming]]）。可移植的代码不能依赖这些细节。
5. **很多地方是未指定的。** 名字是否声明在内联命名空间里（[[contents#2]]），类是否可平凡复制（[[library.class.props]]），能否取函数的地址（[[namespace.std#6]]），对象被移走之后的值（[[lib.types.movedfrom]]），都没有规定。

## 历史与演进

!!! history
    - C++98 的库引言已经确立了总则加各分章的结构，以及用 *Requires*、*Effects*、*Returns*、*Throws*、*Complexity* 等要素描述函数的方法。
    - C++11 为并发和移动语义加入了相应的总则：避免数据竞争（[[res.on.data.races]]）、移出状态（[[lib.types.movedfrom]]）、右值引用实参可以假定没有别名（[[res.on.arguments]]）。
    - C++20 引入概念库和 Ranges，用 *Constraints*、*Mandates*、*Preconditions* 取代 *Requires*（[[P0788R3]]），并禁止特化标准库函数模板、引入可寻址函数的概念（[[P0551R3]]）。
    - C++23 加入标准库模块 `std` 与 `std.compat`（[[P2465R3]]），并大幅扩充了独立实现必须提供的库子集。
    - C++26 加入标准库加固（[[P3471R4]]）、库中的契约断言（[[res.contract.assertions]]）、反射对库实体的限制（[[namespace.std#7]]），并把算法函数对象规定为定制点对象（[[P3136R1]]）。
