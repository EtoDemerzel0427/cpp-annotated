---
title: 视图
summary: 23.7 导读——span 与 mdspan 为什么放在容器章：它们不拥有元素，只把"别人的一段连续存储"包装成带长度（或多维形状）的句柄；与 string_view、ranges 视图的分工，以及读这一节需要先掌握的几条核心语言规则
status: done
covers: views.general
related: views.contiguous, views.multidim, containers, container.requirements, array, vector, basic.types.general, class.temporary
tags: 标准库, 视图, span, mdspan, 导读
updated: 2026-10-18
---

[views] 是容器章（[[containers]]）里唯一**不管元素生命周期**的一节。前面的 `vector`、`deque`、`map` 都负责分配存储、构造和销毁元素；这里的两个类模板只做一件事：拿到一块**别人拥有**的存储，告诉你"从哪开始、有多长、按什么形状索引"。

- `std::span<T, Extent>`（[[views.contiguous]]）：一维、连续、指针 + 长度；
- `std::mdspan<T, Extents, Layout, Accessor>`（[[views.multidim]]）：多维、形状与内存布局可定制，下标经过一个**映射函数**（layout mapping）算出偏移，再经过一个**访问器**（accessor）变成引用。

它们被放进容器章而不是 ranges 章（第 25 章），是历史和分类上的双重原因：`span` 在 C++20 进入标准时被当作"连续容器的轻量替身"，它的迭代器要满足容器迭代器的全部要求（[span.iterators] ¶2 直接引用 [[container.reqmts]]）；`mdspan` 则根本不是 range——它没有 `begin`/`end`。

## 本节两段话（[views.general]）

¶1 只是目录：`<span>` 定义 `span`，`<mdspan>` 定义 `mdspan` 及其配套设施（`extents`、各种 layout、accessor、`submdspan`，以及 C++26 之后加入的多维 `copy`/`fill`）。

¶2 规定 `dynamic_extent` 除了在 `<span>` 里，**包含 `<mdspan>` 时也可用**。这不是随手一提：`extents<int, 3, dynamic_extent>` 里的 `dynamic_extent` 就是 `span` 用的那个 `numeric_limits<size_t>::max()`，两套设施共用同一个"动态"哨兵值。只包含 `<mdspan>` 的翻译单元可以直接写 `std::dynamic_extent`，不必额外包含 `<span>`。

!!! std
    In addition to being available via inclusion of the `<span>` header, `dynamic_extent` is available when the header `<mdspan>` is included.
    `dynamic_extent` 除了经由 `<span>` 提供外，包含 `<mdspan>` 时也可用。

## "视图"在这里是什么意思

标准对 `span` 的定义只有一句话（[span.overview] ¶1）：

!!! std
    A `span` is a view over a contiguous sequence of objects, the storage of which is owned by some other object.
    `span` 是一段连续对象序列上的视图，这段存储由**另外某个对象**拥有。

拆开来是三条工程约定：

1. **不拥有**：`span`/`mdspan` 的析构函数什么都不做，复制它们只是复制指针和长度。于是"它看着的那块存储是否还活着"完全是调用者的责任——这正是悬垂（dangling）问题的根源，详见 [[views.contiguous]] 的陷阱一节和 [[class.temporary]]。
2. **浅 const**：`const span<int>` 的 `const` 只修饰"指针 + 长度"这两个成员，不修饰元素；想要只读，得写 `span<const int>`。`mdspan` 同理。这和 `const vector<int>`（深 const）截然相反。
3. **O(1) 复制、平凡可复制**：`span` 被规定为 trivially copyable（[span.overview] ¶3，[[basic.types.general]]）；`mdspan` 在其 accessor、mapping、数据句柄都平凡可复制时也是（[mdspan.mdspan.overview] ¶5）。按值传参是惯用法，比传 `const span&` 更好——两个寄存器就装下了。

## 三类"视图"的分工

| | `std::string_view` | `std::span<T>` | `std::mdspan<T, E, L, A>` | ranges 视图（`views::filter` 等） |
|---|---|---|---|---|
| 所在条款 | [[string.view]]（第 27 章） | [[views.contiguous]] | [[views.multidim]] | [[range.adaptors]]（第 25 章） |
| 维数 | 1 | 1 | 任意 rank（含 0） | 1 |
| 存储要求 | 连续字符 | 连续对象 | 任意，由 layout + accessor 决定 | 任意 range |
| 元素可写？ | 否（总是只读） | 由 `T` 的 const 决定 | 由 `T`/accessor 决定 | 视底层而定 |
| 编译期长度 | 无 | 可选（`Extent`） | 每一维可选 | 无 |
| `ranges::view` / `borrowed_range` | 是 / 是 | 是 / 是 | **不是 range** | 是 / 视情况 |
| 有 `operator==`？ | 有（比较内容） | **没有** | **没有** | 视情况 |

几点值得展开：

- **`string_view` 不是 `span<const char>` 的别名**。它额外承担了"文本"语义：有 `char_traits`、有 `find`/`substr`/`starts_with`、有按内容比较的 `==`。`span<const char>` 只是字节序列，连 `==` 都没有（理由见 [[views.contiguous]]）。两者可以互转：`span<const char>` 能从 `string_view` 隐式构造（`string_view` 是连续、有大小的 borrowed range）；反方向则必须显式，因为 `string_view` 的 range 构造函数是 `explicit` 的。
- **`span` 满足 `ranges::view`**：[span.syn] 特化了 `ranges::enable_view` 与 `ranges::enable_borrowed_range`。于是对右值 `span` 调用 `ranges::find` 拿到的是真正的迭代器，不是 `ranges::dangling`。视图与 borrowed range 的定义在第 25 章（[[range.view]]、[[range.range]]）。
- **`mdspan` 刻意不是 range**：多维下标 `m[i, j]` 才是它的主接口；"把所有元素按某种顺序走一遍"对非连续、非唯一的 layout 根本没有自然定义。

## 读这一节需要的核心语言前置

- **限定转换与"相似类型"**：`span<const T>` 能从 `span<T>` 构造，但 `span<Base>` 不能从 `span<Derived>` 构造——库用 `is_convertible_v<U(*)[], T(*)[]>` 这个技巧把允许的转换卡死在**限定转换**（[[conv.qual]]）上。
- **对象表示与类型可访问性**：`as_bytes`/`as_writable_bytes` 把任意 `span<T>` 变成 `span<const byte>`/`span<byte>`，它的合法性完全建立在 [[basic.types.general]] 的"对象表示"和 [[basic.lval]] ¶11 的 type-accessible 规则上。
- **临时对象的生命周期**：`span<const int> s = make_vector();` 能编译，却立刻悬垂（[[class.temporary]]）。
- **多维下标运算符**：`m[i, j]` 依赖 C++23 起 [[expr.sub]] 允许重载的 `operator[]` 接受多个参数（[[P2128R6]]）。
- **库条款的五种要求**：*Constraints*、*Mandates*、*Preconditions*、*Hardened preconditions* 的法律后果见 [[mem]] 导读。`span` 和 `mdspan` 是标准库加固（hardening）的主要对象：几乎所有下标、子视图和尺寸检查都写成了 *Hardened preconditions*，在[[g:hardened-implementation|加固实现]]中违反会以终止语义报告。

## 本节地图

| 子条款 | 内容 | 本站笔记 |
|---|---|---|
| [views.general] | 本页 | — |
| [views.contiguous] | `<span>` 概要、`span` 的构造/子视图/元素访问/迭代器、`as_bytes` | [[views.contiguous]] |
| [views.multidim] | `extents`、layout mapping 要求与五种标准 layout、accessor policy、`mdspan`、`submdspan`、多维 `copy`/`fill` | [[views.multidim]] |

!!! summary
    - 视图 = 不拥有存储的句柄；生命周期是调用者的事。
    - `span` 是一维连续视图，满足 `ranges::view` 与 `borrowed_range`；`mdspan` 是多维视图，不是 range。
    - 两者都是浅 const、O(1) 复制，惯用按值传递。
    - `dynamic_extent` 是两者共用的"运行期决定"哨兵，`<span>` 和 `<mdspan>` 都提供它。
