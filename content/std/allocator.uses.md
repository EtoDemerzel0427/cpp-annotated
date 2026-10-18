---
title: uses_allocator 与 uses-allocator 构造
summary: 分配器如何"向下传递"给元素：allocator_arg 标签、uses_allocator 特征、前置/后置两种构造约定，以及 uses_allocator_construction_args 对 pair 的逐成员递归处理
status: done
covers: allocator.tag, allocator.uses.trait, allocator.uses.construction
related: allocator.traits, mem.poly.allocator.class, allocator.adaptor, tuple, pairs, dcl.init.list, memory
tags: 标准库, 分配器, uses-allocator, pmr
papers: P0591R4
updated: 2026-10-18
---

容器用分配器给**自己的**存储分配内存，这很直观。但如果元素本身也要分配内存呢？`std::pmr::vector<std::pmr::string>` 里，`vector` 的缓冲区来自某个 `memory_resource`；我们通常希望每个 `string` 的字符缓冲区**也**来自同一个资源——否则用 arena 分配器的全部意义（局部性、批量释放）就丢了一半。

这就需要一个协议：容器在构造元素时，**检测**元素是否"使用分配器"，若是，就把自己的分配器以约定的方式塞进构造函数实参。这个协议就是 **uses-allocator 构造**（[[g:uses-allocator-construction]]），本节定义它的三个部件：

1. `allocator_arg_t` 标签（[allocator.tag]）；
2. `uses_allocator<T, Alloc>` 特征（[allocator.uses.trait]）；
3. 把普通构造实参改写成"带分配器的实参"的函数族（[allocator.uses.construction]）。

谁是这个协议的使用者？`polymorphic_allocator::construct`（[[mem.poly.allocator.class]]）、`scoped_allocator_adaptor::construct`（[[allocator.adaptor]]），以及 `tuple`、`pair`、`optional` 等带 `allocator_arg_t` 构造函数的类型。注意 `std::allocator` **不**参与——它的 `construct`（经由 [[allocator.traits]] 的默认实现）就是普通的 `construct_at`。

## `allocator_arg_t`（[allocator.tag]）

```cpp
struct allocator_arg_t { explicit allocator_arg_t() = default; };
inline constexpr allocator_arg_t allocator_arg{};
```

¶1：它是一个空类，作为唯一类型用于区分构造函数和函数重载。`tuple` 等类型有以 `allocator_arg_t` 为第一个形参、紧跟一个分配器形参的构造函数。

为什么需要标签？考虑 `tuple<A, B>` 的构造函数 `tuple(const A&, const B&)`。若 `A` 恰好就是分配器类型，"把分配器放在最前面"就和"普通的第一个元素"无法区分。标签类型从类型系统层面消除了二义性。

**为什么默认构造函数是 `explicit`？** 这阻止了用 `{}` 隐式造出标签：

```cpp title="allocator-arg-explicit.cpp" error
#include <memory>
void f(std::allocator_arg_t);
void g() {
    f(std::allocator_arg);   // OK
    f({});                   // error: explicit 默认构造函数不能用于复制列表初始化
}
```

如果 `f({}, x)` 能匹配 `(allocator_arg_t, Alloc)`，一个原本想传"空的第一个元素"的调用就可能悄悄选中带分配器的重载。`explicit` 默认构造函数使复制列表初始化 `{}` 不考虑它（[[over.match.list]]），从而杜绝这种意外。`in_place_t`、`nullopt_t` 等标签都采用同样的设计。

## `uses_allocator` 特征（[allocator.uses.trait]）

¶1 规定 `uses_allocator<T, Alloc>`：若 `T::allocator_type` 存在且 `is_convertible_v<Alloc, T::allocator_type>`，派生自 `true_type`，否则派生自 `false_type`。

程序**可以**为程序定义类型（[[g:program-defined-type]]）特化它为 `true_type`，条件是该类型虽没有 `allocator_type` 成员，但确实能以如下方式之一用分配器构造：

- (1.1) 第一个实参类型是 `allocator_arg_t`、第二个是 `Alloc`（**前置约定**，leading-allocator convention）；
- (1.2) 最后一个实参类型是 `Alloc`（**后置约定**，trailing-allocator convention）。

标准库自身的例子：`std::tuple` 没有 `allocator_type`，但标准为它特化了 `uses_allocator<tuple<Types...>, Alloc>` 为 `true_type`；`std::function` 在 C++17 去掉分配器支持时，相应的特化也一并移除了。

## uses-allocator 构造（[allocator.uses.construction]）

### ¶1–¶3：定义与三种约定

¶1：以分配器 `alloc` 和实参 `args...` 对类型 `T` 进行 uses-allocator 构造，是指**若 `T` 使用与 `alloc` 兼容的分配器类型，就把 `alloc` 传给 `T` 的构造函数**；它等价于用 `make_obj_using_allocator<T>(alloc, args...)` 的值初始化对象。

¶2 列出三种情况：

1. `T` 不使用兼容的分配器——忽略 `alloc`；
2. 否则若 `T(allocator_arg_t{}, alloc, args...)` 可调用——选**前置**形式；
3. 否则若 `T(args..., alloc)` 可调用——选**后置**形式。

注意顺序：前置约定**优先**于后置约定。

¶3：`uses_allocator_construction_args` 接收分配器与实参列表，以 `tuple` 的形式返回改写后的实参列表；另外有一组重载专门处理 `pair`，把 uses-allocator 构造**分别**应用到 `first` 与 `second`。`make_obj_using_allocator` 和 `uninitialized_construct_using_allocator` 则把改写后的实参应用于构造（前者返回值，后者就地构造）。注 1：`T` 不能推导，必须显式给出。

这组函数是 C++20 由 [[P0591R4]] 引入的。在此之前，`scoped_allocator_adaptor::construct` 与 `polymorphic_allocator::construct` 各自用一大段几乎相同的文字描述这个逻辑，而且对 `pair` 的处理只能靠为 `construct` 写多个 `pair` 重载；现在它们都统一委托给 `uses_allocator_construction_args`。

### 非 `pair` 版本（¶4–¶5）

*Constraints*：`remove_cv_t<T>` 不是 `pair` 的特化。返回值按 ¶5：

| 条件 | 返回 |
|---|---|
| (5.1) `uses_allocator_v<remove_cv_t<T>, Alloc>` 为假，且 `is_constructible_v<T, Args...>` | `forward_as_tuple(std::forward<Args>(args)...)` |
| (5.2) 为真，且 `is_constructible_v<T, allocator_arg_t, const Alloc&, Args...>` | `tuple<allocator_arg_t, const Alloc&, Args&&...>(allocator_arg, alloc, args...)` |
| (5.3) 为真，且 `is_constructible_v<T, Args..., const Alloc&>` | `forward_as_tuple(args..., alloc)` |
| (5.4) 其他 | 程序 {{ill-formed}} |

(5.4) 的注 2 解释了它的用意：**防止"静默地没传分配器"**。如果一个类型声称自己使用分配器（`uses_allocator` 为真），却没有任何接受分配器的构造函数，那很可能是个 bug；与其悄悄退回不带分配器的构造、让元素从全局堆分配，不如直接报错。

```cpp title="uses-allocator.cpp" ok
#include <memory>
#include <memory_resource>
#include <string>
#include <utility>
#include <vector>
#include <cassert>

// 前置分配器约定
struct Leading {
    using allocator_type = std::pmr::polymorphic_allocator<>;
    allocator_type alloc;
    int v;
    Leading(std::allocator_arg_t, const allocator_type& a, int x) : alloc(a), v(x) {}
};
// 后置分配器约定
struct Trailing {
    using allocator_type = std::pmr::polymorphic_allocator<>;
    allocator_type alloc;
    int v;
    Trailing(int x, const allocator_type& a = {}) : alloc(a), v(x) {}
};

int main() {
    std::pmr::monotonic_buffer_resource mr;
    std::pmr::polymorphic_allocator<> pa(&mr);

    static_assert(std::uses_allocator_v<Leading, decltype(pa)>);
    auto l = std::make_obj_using_allocator<Leading>(pa, 1);   // Leading(allocator_arg, pa, 1)
    auto t = std::make_obj_using_allocator<Trailing>(pa, 2);  // Trailing(2, pa)
    assert(l.alloc.resource() == &mr && t.alloc.resource() == &mr);

    // pair 被特殊处理：分配器被分别传给 first 和 second
    std::pmr::vector<std::pair<std::pmr::string, std::pmr::string>> v(&mr);
    v.emplace_back("a fairly long string to defeat SSO", "another fairly long string......");
    assert(v[0].first.get_allocator().resource() == &mr);
    assert(v[0].second.get_allocator().resource() == &mr);
}
```

```cpp title="uses-allocator-liar.cpp" error
#include <memory>
#include <memory_resource>
struct Liar {
    using allocator_type = std::pmr::polymorphic_allocator<>;  // 声称使用分配器
    Liar(int) {}                                               // 却没有任何接受分配器的构造函数
};
std::pmr::polymorphic_allocator<> pa;
auto x = std::make_obj_using_allocator<Liar>(pa, 1);           // error: ¶5.4
```

libc++ 的诊断是一条 `static_assert`："If uses_allocator_v<Type> is true, the type has to be allocator-constructible"。

### `pair` 版本（¶6–¶22）

`pair` 本身**不使用分配器**（没有 `allocator_type`，也没有 `uses_allocator` 特化），但它的成员可能使用。于是 `pair` 的各重载（*Constraints* 均为 `remove_cv_t<T>` 是 `pair` 的特化）都归结为**分段构造**（piecewise construction）：

- ¶6–¶8：`(alloc, piecewise_construct, x, y)` 是基础情形——对 `x` 的元素递归调用 `uses_allocator_construction_args<T1>`，对 `y` 调用 `<T2>`，返回 `make_tuple(piecewise_construct, 新x, 新y)`；
- ¶9–¶10：无实参 → 两个空 tuple；
- ¶11–¶12：`(alloc, u, v)` → `forward_as_tuple(u)`、`forward_as_tuple(v)`；
- ¶13–¶16：从 `pair<U, V>` 的左值/右值/const 版本拷贝或移动；
- ¶17–¶18：从任意 **pair-like** 对象（满足 `pair-like` 概念，但排除 `ranges::subrange`）用 `get<0>`、`get<1>` 拆分——这是 [[LWG3821]] 补上的；
- ¶19–¶22：剩下的单实参情形。

注意约束写的是 `remove_cv_t<T>`：构造 `const pair<A, B>` 时同样走 `pair` 路径。这是 [[LWG3677]] 的修正——此前 cv 限定的 `pair` 会落入非 `pair` 版本，分配器根本传不到成员里。

#### ¶19–¶22：`pair-constructor` 技巧

单实参重载要处理这样的情形：`u` 不是 `pair`，也不是 pair-like，但它**可以转换**为 `pair`（例如某个类有 `operator pair<A, B>()`）。此时没法把 `u` "拆开"分别传给 `first` 和 `second`。

¶20 的约束要求：`u` 是 `subrange`，或者 `u` 不满足 `pair-like` 且 `FUN(u)` 不良构——`FUN` 是 `template<class A, class B> void FUN(const pair<A, B>&)`，"`FUN(u)` 良构"意味着 `u` 本身就是某个 `pair` 的特化或从它派生，这些情况由前面的重载处理。

¶21 定义的说明用类 `pair-constructor` 持有 `alloc` 和对 `u` 的引用，并提供 `operator pair-type()`：转换时先把 `u` 转换为 `pair-type`，再对这个**临时 pair**做 `make_obj_using_allocator<pair-type>(alloc_, ...)`——也就是递归地走"从 `pair` 右值构造"的路径。¶22 返回 `make_tuple(pc)`。最终 `T` 由 `pc` 初始化时，转换函数才被调用，它产出的（已经用分配器构造好的）`pair` 再用来初始化目标对象。

这是一个"把转换推迟到构造时刻"的技巧：返回的 tuple 只装了一个廉价的代理对象。

### `make_obj_using_allocator` 与 `uninitialized_construct_using_allocator`（¶23–¶24）

- ¶23：`make_obj_using_allocator<T>(alloc, args...)` 等价于 `make_from_tuple<T>(uses_allocator_construction_args<T>(alloc, args...))`；
- ¶24：`uninitialized_construct_using_allocator(p, alloc, args...)` 等价于用 `apply` 把改写后的实参展开给 `construct_at(p, ...)`。

后者是 `polymorphic_allocator::construct` 的实质内容。

## 思考题

<details markdown="1">
<summary>1. 一个类型同时有 `T(allocator_arg_t, const A&, int)` 和 `T(int, const A&)`，uses-allocator 构造选哪个？</summary>

选前置形式。¶5.2 先于 ¶5.3 检查，只要 `is_constructible_v<T, allocator_arg_t, const Alloc&, Args...>` 成立，就不会再看后置形式。
</details>

<details markdown="1">
<summary>2. `std::pmr::vector<std::pmr::vector<int>>` 中内层 vector 是否从外层的资源分配？`std::vector<std::pmr::vector<int>>` 呢？</summary>

前者是：外层的 `polymorphic_allocator::construct` 对元素做 uses-allocator 构造，`pmr::vector<int>` 的 `allocator_type` 是 `polymorphic_allocator<int>`，可由 `polymorphic_allocator<pmr::vector<int>>` 转换而来，于是外层资源被传入（后置约定）。

后者不是：外层用的是 `std::allocator`，`allocator_traits<std::allocator<...>>::construct` 退回 `construct_at`，**根本不执行** uses-allocator 构造；内层 vector 各自用默认构造的 `polymorphic_allocator`，即 `get_default_resource()`。
</details>

## 小结

- `allocator_arg_t` 是带 `explicit` 默认构造函数的标签，`{}` 不能冒充它。
- `uses_allocator<T, A>`：看 `T::allocator_type` 是否可由 `A` 转换得到；程序可对自定义类型特化。
- 改写顺序：不使用分配器 → 原样；前置约定优先；后置约定其次；声称使用却无法构造 → {{ill-formed}}。
- `pair` 不使用分配器，但 uses-allocator 构造会**穿透** `pair`，逐成员递归；cv `pair`、pair-like 对象、可转换为 `pair` 的对象都有专门处理。
- 只有 `polymorphic_allocator`、`scoped_allocator_adaptor` 这类分配器的 `construct` 会执行 uses-allocator 构造，`std::allocator` 不会。
