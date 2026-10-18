---
title: 通用工具库
summary: 第 22 章导读——<utility>、pair/tuple、optional/variant/any/expected 四大"词汇类型"、bitset、<functional> 与 <bit>；以及读懂库条文必备的 Constraints / Mandates / Preconditions / Hardened preconditions 四级契约
status: done
covers: utilities.general
related: library, structure.specifications, utility, pairs, tuple, optional, variant, any, expected, bitset, function.objects, bit, class.union, class.prop
tags: 导读, 标准库, 词汇类型
updated: 2026-10-18
---

第 22 章 [utilities] 是标准库里**最"杂"也最常用**的一章：它没有一个统一的主题，收录的是"几乎每个 C++ 程序都会用到、又不属于容器/算法/IO 任何一类"的小组件。¶1 自己的说法很朴素——这些工具"在 C++ 程序中普遍有用"，其中一部分还被标准库的其他部分当作积木使用（`std::forward` 与 `std::move` 遍布整个库，`std::pair` 是关联容器的 `value_type`，`std::invoke` 是所有"可调用"参数的统一语义）。

对 language lawyer 来说，这一章的价值远不止"会用"：`optional`、`variant`、`expected` 的条文是**标准如何用库措辞驾驭核心语言规则**的教科书——条件平凡的特殊成员、条件 `explicit`、条件 `noexcept`、用约束剔除候选、用 *Mandates* 制造硬错误……几乎所有库规范技巧都在这里集中出现。读懂它们，也就读懂了整个库的"法律文体"。

## 本章地图（¶1，Table 66）

| 节 | 条款 | 头文件 | 内容 |
|---|---|---|---|
| 22.2 | [[utility]] | `<utility>` | `swap`、`exchange`、`forward`/`forward_like`/`move`、`as_const`、`declval`、整数安全比较 `cmp_*`/`in_range`、`to_underlying`、`unreachable`；{{c++26}} `constant_wrapper`（[[const.wrap.class]]） |
| 22.3 | [[pairs]] | （`<utility>`） | `pair`、`piecewise_construct` |
| 22.4 | [[tuple]] | `<tuple>` | `tuple`、*tuple-like* 协议、`apply`、`make_from_tuple` |
| 22.5 | [[optional]] | `<optional>` | `optional<T>`；{{c++26}} `optional<T&>` |
| 22.6 | [[variant]] | `<variant>` | 类型安全的联合体 `variant`、`visit` |
| 22.7 | [[any]] | `<any>` | 类型擦除的值容器 `any` |
| 22.8 | [[expected]] | `<expected>` | {{c++23}} `expected<T, E>`：值或错误 |
| 22.9 | [[bitset]] | `<bitset>` | 定长位集 |
| 22.10 | [[function.objects]] | `<functional>` | *INVOKE*、`reference_wrapper`、运算符函数对象、`bind`/`bind_front`/`not_fn`、`function`/`move_only_function`/`copyable_function`/`function_ref`、搜索器、`hash` |
| 22.11 | [[bit]] | `<bit>` | `bit_cast`、`byteswap`、2 的幂、旋转、计数 |
| 22.12 | [[stdbit.h.syn]] | `<stdbit.h>` | {{c++26}} C23 位操作头文件 |

!!! note "已经搬走的东西"
    老版本标准（C++17/20）的 [utilities] 还包括智能指针与内存工具、`<type_traits>`、`<ratio>`、`<chrono>`、`<charconv>`、`<format>`、执行策略、`type_index` 等。如今它们分散在别处：内存相关在 [[mem]]，类型特征在 [[meta]]，`<charconv>` 和 `<format>` 在第 28 章 [[text]]（见 [[charconv]]、[[format]]），执行策略在 [[execpol]]（算法库），`type_index` 在 [[type.index]]（语言支持库），时间库在 [[time]]。引用旧版条款号（如"C++20 [format]"在 20.20）时请注意这一点。

## 四个"词汇类型"：一张对照表

`optional`、`variant`、`any`、`expected` 常被合称**词汇类型**（vocabulary types）——它们的价值在于让不同库的接口能用同一种类型说同一件事。它们的设计取舍可以放在一张表里看：

| | `optional<T>` | `variant<Ts...>` | `any` | `expected<T, E>` |
|---|---|---|---|---|
| 存什么 | 一个 `T` 或"无" | 恰好一个 `Ts_i` | 任意可复制类型 | 一个 `T` 或一个 `E` |
| 存储 | 对象内（不分配） | 对象内（不分配） | 可能堆分配（鼓励小对象优化） | 对象内（不分配） |
| "空"状态 | `nullopt`，正常状态 | `valueless_by_exception()`，只能由异常造成 | 空 `any`，正常状态 | **无**：永远有值或有错 |
| 错误访问 | `operator*` 是 hardened 前置条件；`value()` 抛 `bad_optional_access` | `get` 抛 `bad_variant_access`；`get_if` 返回空指针 | `any_cast` 抛 `bad_any_cast` 或返回空指针 | `operator*` 是 hardened 前置条件；`value()` 抛 `bad_expected_access<E>` |
| 平凡性 | 特殊成员随 `T` 条件平凡 | 随全部 `Ts` 条件平凡 | 不平凡 | 随 `T`、`E` 条件平凡 |
| 底层核心规则 | [[class.union]] 的变体成员 + 手动生命周期 | 同左 | 类型擦除 | 同 optional |

前三行是设计，后两行才是这一章法律上真正的看点：**一个库类模板如何让自己的拷贝构造函数"在 `T` 平凡时恰好平凡"**？答案是 C++20 起的"条件平凡特殊成员"技术——在类中声明多个*预期*特殊成员函数（prospective destructor 等），用 *requires-clause* 选择其中一个（[[class.dtor]]、[[special]]），再配合 [[class.union]] 中"联合体的特殊成员默认被弃置，除非所有变体成员的相应函数平凡"的规则。细节见 [[optional.optional]] 与 [[variant.variant]]；为什么平凡性如此重要（`memcpy`、寄存器传参、`std::bit_cast` 的适用性），见 [[class.prop]]。

## 读库条文的前置知识：函数语义的元素

库条文的每个函数都按 [[structure.specifications#3]] 规定的固定元素书写。这些元素的**违规后果完全不同**，这是读本章任何一页的第一把钥匙：

| 元素 | 不满足时的后果 | 典型实现手段 |
|---|---|---|
| *Constraints* | 该函数**静默地不可行**（不参与重载决议），不报错——SFINAE 友好 | `requires` 子句、`enable_if` |
| *Mandates* | 程序**非良构**，必须诊断 | `static_assert`；需要先被重载决议选中才报错时，用约束 + `= delete` |
| *Constant When* | 不满足时调用**不是**常量子表达式 | — |
| *Preconditions* | **未定义行为** | 可用契约断言表达（[[dcl.contract.func]]） |
| *Hardened preconditions* | 在 **hardened 实现**中，函数产生任何可观察副作用之前，以 *terminating* 语义求值对应的契约断言；在非 hardened 实现中违反即 **UB** | 契约断言 / 库内部断言 |
| *Effects* / *Returns* / *Throws* / *Remarks* | 行为描述本身 | — |

{{c++26}} 引入的 hardened preconditions 对本章影响极大：`optional::operator*`、`expected::operator->`、`bitset::operator[]` 等"不检查"的访问函数，过去都是普通前置条件（违反即 UB）；现在它们被升级为 hardened preconditions——同一份代码，在开启了 hardening 的标准库下会确定地终止，而不再是静默 UB。libc++ 通过 `_LIBCPP_HARDENING_MODE` 宏（`fast`/`extensive`/`debug`）提供这种模式。

!!! pitfall "Constraints 与 Mandates 别混"
    `std::get<T>(variant)` 要求 `T` 在 `Ts...` 中恰好出现一次——这是 *Mandates*，违反直接编译错误，而不是"这个重载不可行、换一个"。反过来，`optional<T>` 的转换构造函数用的是 *Constraints*：条件不满足时只是这个构造函数退出重载决议，可能有别的构造函数接手，也可能让 `is_constructible_v` 平静地返回 `false`。判断一个库接口能否用于 SFINAE/概念检测，看的就是这个区别。

另一个反复出现的措辞是 **"Equivalent to"**：[[structure.specifications#4]] 规定，若 *Effects* 写成"等价于某段代码"，则先施加本函数自己的 *Constraints*/*Mandates*，然后该代码段的语义（包括它会调用哪些函数、抛什么异常、是否 `constexpr`）就是本函数的语义。本章大量函数（`std::apply`、`optional::value_or`、`expected` 的单子操作）都用这种方式定义。

## 推荐阅读顺序

1. [[utility]]：`move`/`forward`/`declval` 是阅读其余所有条文的基础词汇；`cmp_less` 等整数比较函数解决的是 [[expr.arith.conv]] 留下的老坑。
2. [[func.require]]：*INVOKE* 的定义——`apply`、`visit`、`bind`、`function`、`optional::and_then` 都以它为语义基础。
3. [[pairs]] → [[tuple]]：*tuple-like* 协议，以及它与结构化绑定 [[dcl.struct.bind]] 的关系。
4. [[optional.optional]] → [[variant.variant]] → [[expected.expected]]：同一套条件平凡性技术的三次变奏；[[any]] 作为"类型擦除"的对照组。
5. [[func.wrap]]：四种多态函数包装器的取舍。
6. [[bit]]：`bit_cast` 是"合法类型双关"的标准答案，与 [[basic.lval]] 的别名规则、[[class.union]] 的"读非活跃成员是 UB"对照阅读。

!!! question "思考题"
    1. `std::optional<int>` 是平凡可复制的吗？`std::optional<std::string>` 呢？标准是在哪里、用什么措辞保证前者的？
    2. 为什么 `std::get<int>(std::variant<int, int>{})` 是编译错误，而 `std::get<0>(...)` 没问题？这对应哪种元素？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 是，不是。[optional.ctor] 规定"若 `is_trivially_copy_constructible_v<T>` 为 `true`，则此构造函数是平凡的"，移动构造、拷贝/移动赋值有类似条款，[optional.dtor] 规定"若 `is_trivially_destructible_v<T>` 为 `true`，则此析构函数是平凡的"。`int` 满足全部条件，于是 `optional<int>` 满足 [[class.prop]] 对平凡可复制类的定义；`string` 的拷贝构造与析构都不平凡，所以 `optional<string>` 不是。详见 [[optional.optional]]。
2. 按类型取值要求 `T` 在 `Ts...` 中恰好出现一次，这是 *Mandates*，违反即非良构；按下标取值只要求 `I < sizeof...(Ts)`。详见 [[variant]]。

</details>

!!! summary "要点"
    - [utilities] 是"通用积木"的集合；`<charconv>`、`<format>`、智能指针、类型特征等已迁出本章。
    - 读库条文先认元素：*Constraints* → 不可行；*Mandates* → 非良构；*Preconditions* → UB；*Hardened preconditions* → hardened 实现中终止，否则 UB。
    - `optional`/`variant`/`expected` 的特殊成员"随元素类型条件平凡"，底层是 [[class.union]] 的变体成员规则加 C++20 的预期特殊成员与约束。
