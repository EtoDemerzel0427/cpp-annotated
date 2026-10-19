---
title: 视图
summary: span 和 mdspan 是不拥有元素的句柄，只记录别人的一段存储从哪开始、有多长、按什么形状索引，与 string_view、ranges 视图各有分工。
status: done
covers: views.general
related: views.contiguous, views.multidim, containers, container.requirements, array, vector, basic.types.general, class.temporary
tags: 标准库, 视图, span, mdspan, 导读
updated: 2026-10-19
---

!!! tldr
    - `span` 和 `mdspan` 不拥有元素：它们的析构函数什么也不做，复制只复制指针和长度，所看存储的生命周期由调用者负责。
    - 它们的 const 是浅的：`const span<int>` 的元素仍然可写，只读要写成 `span<const int>`。
    - `span` 是一维连续视图，满足 `ranges::view` 和 `borrowed_range`；`mdspan` 是多维视图，不是 range。
    - 两者都没有 `operator==`，都是平凡可复制类型，惯用按值传递。
    - `dynamic_extent` 是两者共用的运行期长度标记，`<span>` 和 `<mdspan>` 都提供它。

## 一个参数接受各种连续存储

```cpp run title="span-param.cpp" ok
#include <array>
#include <span>
#include <vector>

int sum(std::span<const int> s) {
  int t = 0;
  for (int x : s) t += x;
  return t;
}

int main() {
  int raw[] = {1, 2, 3};
  std::array<int, 2> arr{4, 5};
  std::vector<int> vec{6, 7, 8, 9};
  return sum(raw) + sum(arr) + sum(vec) - 45;   // 返回 0
}
```

`sum` 不关心元素存在内建数组、`std::array` 还是 `std::vector` 里，只需要一个起点和一个长度。`std::span` 就是把 C 接口里的 `(const int* p, size_t n)` 合成了一个类型。

容器章（[[containers]]）里的其他类模板，`vector`、`deque`、`map` 等，都负责分配存储、构造和销毁元素。[views] 这一节的两个类模板不做这些事，它们只拿到一块**别人拥有**的存储，记录它从哪开始、有多长、按什么形状索引：

- `std::span<T, Extent>`（[[views.contiguous]]）：一维、连续，内容是一个指针加一个长度。
- `std::mdspan<T, Extents, Layout, Accessor>`（[[views.multidim]]）：多维。下标先经过**布局映射**（layout mapping）算出一维偏移，再经过**访问器**（accessor）得到元素的引用，两者都可以定制。

## 视图的三条约定

标准对 `span` 的定义只有一句话：

!!! std
    A `span` is a view over a contiguous sequence of objects, the storage of which is owned by some other object.

存储由另外某个对象拥有。由此得出三条约定，对 `mdspan` 同样成立。

**不拥有。** 析构函数什么也不做，复制只是复制指针和长度。它看着的存储是否还活着，完全由调用者负责。所以 `span<const int> s = make_vector();` 能编译，却在这条语句结束时就悬垂了，详见 [[views.contiguous]] 的陷阱一节和 [[class.temporary]]。

**浅 const。** `const` 只修饰视图本身的指针和长度，不修饰元素。这和 `const vector<int>` 正好相反：

<div class="compare" markdown="1">

```cpp run ok
#include <span>
void f(const std::span<int> s) {
  s[0] = 1;   // OK：元素仍可写
}
```

```cpp run error
#include <span>
void f(std::span<const int> s) {
  s[0] = 1;   // error: 元素是 const
}
```

</div>

**复制便宜。** `span` 被规定为平凡可复制类型（[[span.overview#3]]，[[basic.types.general]]）。`mdspan` 在它的访问器、布局映射和数据句柄都平凡可复制时也是（[[mdspan.mdspan.overview#5]]）。按值传参是惯用法：动态长度的 `span` 只占两个机器字，在常见 ABI 下用两个寄存器传递，比传 `const span&` 少一次间接访问。

## 几种视图的分工

| | `std::string_view` | `std::span<T>` | `std::mdspan` | ranges 视图（`views::filter` 等） |
|---|---|---|---|---|
| 条款 | [[string.view]] | [[views.contiguous]] | [[views.multidim]] | [[range.adaptors]] |
| 维数 | 1 | 1 | 任意（含 0 维） | 1 |
| 存储 | 连续字符 | 连续对象 | 由布局和访问器决定 | 任意 range |
| 元素可写 | 否 | 由 `T` 的 const 决定 | 由 `T` 和访问器决定 | 取决于底层 |
| 编译期长度 | 无 | 可选（`Extent`） | 每一维可选 | 无 |
| `ranges::view` / `borrowed_range` | 是 / 是 | 是 / 是 | 不是 range | 是 / 视情况 |
| `operator==` | 有，比较内容 | 没有 | 没有 | 视情况 |

`string_view` 不是 `span<const char>` 的别名。它带有文本语义：有 `char_traits`，有 `find`、`substr`、`starts_with`，`==` 比较内容。`span<const char>` 只是一段字节，没有 `==`（原因见 [[views.contiguous]]）。两者可以互转：`string_view` 是连续、有大小的 borrowed range，所以能隐式转换成 `span<const char>`；反方向要显式，因为 `string_view` 从 range 构造的构造函数是 `explicit` 的。

`span` 满足 `ranges::view`，因为 [[span.syn]] 把 `ranges::enable_view` 和 `ranges::enable_borrowed_range` 都特化为 `true`。后者意味着对一个右值 `span` 调用 `ranges::find`，返回的是可用的迭代器，而不是 `ranges::dangling`（[[range.range]]）。

`mdspan` 没有 `begin` 和 `end`，不是 range。它的主要接口是多维下标 `m[i, j]`，这依赖 C++23 起 `operator[]` 可以接受多个参数（[[expr.sub]]，[[P2128R6]]）。对非连续或者多个下标映射到同一元素的布局，按某种顺序遍历所有元素没有自然的定义。

## [views.general] 的两段

¶1 `<span>` 定义 `span`；`<mdspan>` 定义 `mdspan` 和配套设施：`extents`、各种布局、访问器、`submdspan`，以及较新的草案加入的多维 `copy` 和 `fill`。

¶2 `dynamic_extent` 除了由 `<span>` 提供，包含 `<mdspan>` 时也可用。它的值是 `numeric_limits<size_t>::max()`，作为长度实参时表示长度到运行期才确定。`span<int, dynamic_extent>` 和 `extents<int, 3, dynamic_extent>` 用的是同一个常量，所以只包含 `<mdspan>` 的文件也可以直接写 `std::dynamic_extent`。

## 相关的语言规则

- 元素类型转换：`span<const T>` 能从 `span<T>` 构造，`span<Base>` 不能从 `span<Derived>` 构造。库用 `is_convertible_v<U(*)[], T(*)[]>` 把允许的转换限制在限定转换上（[[conv.qual]]）。
- 字节视图：`as_bytes` 把 `span<T>` 变成 `span<const byte>`，它的合法性来自对象表示（[[basic.types.general]]）和通过 `std::byte` 访问任意对象的规则（[[basic.lval#11]]）。
- 加固：`span` 和 `mdspan` 的下标、子视图和长度检查大多写成 *Hardened preconditions*。在[[g:hardened-implementation|加固实现]]中违反它们会终止程序，在其他实现中是 UB。

| 子条款 | 内容 |
|---|---|
| [[views.contiguous]] | `<span>`：构造、子视图、元素访问、迭代器、`as_bytes` |
| [[views.multidim]] | `<mdspan>`：`extents`、布局映射与标准布局、访问器、`mdspan`、`submdspan`、多维 `copy`/`fill` |
