---
title: uses_allocator 与 uses-allocator 构造
summary: 容器怎样把自己的分配器传给元素的构造函数：allocator_arg 标签、uses_allocator 特征、前置与后置两种约定，以及对 pair 的逐成员处理。
status: done
covers: allocator.tag, allocator.uses.trait, allocator.uses.construction
related: allocator.traits, mem.poly.allocator.class, allocator.adaptor, tuple, pairs, dcl.init.list, memory
tags: 标准库, 分配器, uses-allocator, pmr
papers: P0591R4
updated: 2026-10-19
---

!!! tldr
    - uses-allocator 构造是一个约定：容器构造元素时，如果元素类型使用兼容的分配器，就把容器的分配器也传给元素的构造函数。
    - 元素是否使用分配器由 `uses_allocator<T, Alloc>` 判断，默认看 `T::allocator_type` 能否由 `Alloc` 转换得到。
    - 分配器有两种传法：前置约定 `T(allocator_arg, alloc, args...)` 优先，其次是后置约定 `T(args..., alloc)`；声称使用分配器却两种都不支持，程序非良构。
    - `pair` 自己不使用分配器，但 uses-allocator 构造会穿过它，把分配器分别传给 `first` 和 `second`。
    - 只有 `polymorphic_allocator`、`scoped_allocator_adaptor` 这类分配器的 `construct` 执行这个约定；`std::allocator` 不执行。

## 分配器要传到元素里

```cpp run ok
#include <cassert>
#include <memory_resource>
#include <string>
#include <utility>
#include <vector>

using S = std::pmr::string;

int main() {
  std::pmr::monotonic_buffer_resource mr;
  std::pmr::vector<std::pair<S, S>> v(&mr);
  v.emplace_back("a string long enough to avoid SSO",
                 "another string long enough to avoid SSO");
  // 分配器穿过 pair，分别传给 first 和 second
  assert(v[0].first.get_allocator().resource() == &mr);
  assert(v[0].second.get_allocator().resource() == &mr);

  std::vector<std::pair<S, S>> w;   // 外层用 std::allocator
  w.emplace_back("x", "y");
  assert(w[0].first.get_allocator().resource() ==
         std::pmr::get_default_resource());
}
```

`v` 的缓冲区来自 `mr`，每个字符串的字符缓冲区也来自 `mr`。`emplace_back` 只给了两个字符串字面量，没有提到分配器，是 `v` 的分配器在构造元素时自动把自己传了进去。用 arena 分配器的目的是局部性和批量释放，如果元素各自从全局堆分配，这个目的就只实现了一半。

`w` 用的是 `std::allocator`，它的 `construct` 只做普通的 `construct_at`，所以元素里的字符串用的是默认资源。

这个自动传递的约定叫**uses-allocator 构造**（[[g:uses-allocator-construction]]）。它由三部分组成：一个标签类型 `allocator_arg_t`，一个特征 `uses_allocator`，以及一组改写构造实参的函数。执行它的是 `polymorphic_allocator::construct`（[[mem.poly.allocator.class]]）和 `scoped_allocator_adaptor::construct`（[[allocator.adaptor]]）；`tuple` 等类型的 `allocator_arg_t` 构造函数也用它构造各个元素。

## 标签 `allocator_arg_t` [allocator.tag]

```cpp
struct allocator_arg_t { explicit allocator_arg_t() = default; };
inline constexpr allocator_arg_t allocator_arg{};
```

¶1 `allocator_arg_t` 是一个空类，用作区分构造函数重载的唯一类型。`tuple` 等类型有以 `allocator_arg_t` 为第一个形参、紧跟一个分配器形参的构造函数。

需要标签是因为单看实参类型无法区分。`tuple<A, B>` 有构造函数 `tuple(const A&, const B&)`，如果 `A` 恰好是分配器类型，排在第一位的分配器和普通的第一个元素就分不清了。加一个专门的类型放在最前面，二义性就消失了。

默认构造函数是 `explicit` 的，所以 `{}` 不能隐式转换成这个标签：

```cpp run error
#include <memory>
void f(std::allocator_arg_t);
void g() {
  f(std::allocator_arg);   // OK
  f({});                   // error: 不能用 {} 隐式构造标签
}
```

否则，一个想把 `{}` 当作空的第一个元素传入的调用，可能悄悄选中带分配器的重载。`in_place_t`、`nullopt_t` 等标签也是这样设计的。

## 特征 `uses_allocator` [allocator.uses.trait]

¶1 如果 `T::allocator_type` 存在并且是一个类型，同时 `is_convertible_v<Alloc, T::allocator_type>` 为真，`uses_allocator<T, Alloc>` 派生自 `true_type`，否则派生自 `false_type`。

程序可以为自己定义的类型（[[g:program-defined-type]]）把它特化为 `true_type`，前提是这个类型没有 `allocator_type` 成员，但确实可以用下面两种方式之一接受分配器：

- ¶1.1 构造函数的第一个实参类型是 `allocator_arg_t`，第二个是 `Alloc`，这叫**前置约定**（leading-allocator convention）；
- ¶1.2 构造函数的最后一个实参类型是 `Alloc`，这叫**后置约定**（trailing-allocator convention）。

标准库里的 `std::tuple` 就是这样：它没有 `allocator_type`，但标准为它把 `uses_allocator` 特化为 `true_type`。

## uses-allocator 构造 [allocator.uses.construction]

### 定义与三种情形（¶1–¶3）

¶1 用分配器 `alloc` 和实参 `args...` 对类型 `T` 做 uses-allocator 构造，意思是：如果 `T` 使用与 `alloc` 兼容的分配器，就把 `alloc` 传给 `T` 的构造函数。效果等价于用 `make_obj_using_allocator<T>(alloc, args...)` 的值初始化对象。

¶2 分三种情形，按顺序检查：

1. `T` 不使用兼容的分配器：忽略 `alloc`；
2. 否则，如果能调用 `T(allocator_arg_t{}, alloc, args...)`：用前置约定；
3. 否则，如果能调用 `T(args..., alloc)`：用后置约定。

¶3 `uses_allocator_construction_args` 接收分配器和实参列表，把改写后的实参列表装进一个 `tuple` 返回。它对 `pair` 有专门的重载，把 uses-allocator 构造分别用于 `first` 和 `second`。`make_obj_using_allocator` 和 `uninitialized_construct_using_allocator` 用改写后的实参构造 `T`，前者返回一个值，后者在给定的地址上构造。注 1 提醒，`T` 不能推导，调用时必须显式写出。

```cpp run ok
#include <cassert>
#include <memory>
#include <memory_resource>
#include <string>
#include <utility>
#include <vector>

using Alloc = std::pmr::polymorphic_allocator<>;

struct Leading {   // 前置约定
  using allocator_type = Alloc;
  Leading(std::allocator_arg_t, const Alloc& a, int x)
      : alloc(a), v(x) {}
  Alloc alloc;
  int v;
};

struct Trailing {  // 后置约定
  using allocator_type = Alloc;
  Trailing(int x, const Alloc& a = {}) : alloc(a), v(x) {}
  Alloc alloc;
  int v;
};

int main() {
  std::pmr::monotonic_buffer_resource mr;
  Alloc pa(&mr);

  static_assert(std::uses_allocator_v<Leading, Alloc>);
  auto l = std::make_obj_using_allocator<Leading>(pa, 1);   // Leading(allocator_arg, pa, 1)
  auto t = std::make_obj_using_allocator<Trailing>(pa, 2);  // Trailing(2, pa)
  assert(l.alloc.resource() == &mr);
  assert(t.alloc.resource() == &mr);
}
```

这组函数是 C++20 由 [[P0591R4]] 加入的。此前 `scoped_allocator_adaptor::construct` 和 `polymorphic_allocator::construct` 各自用一大段几乎相同的文字描述这套逻辑，对 `pair` 还要分别写好几个 `construct` 重载；现在两者都委托给 `uses_allocator_construction_args`。

### 一般类型的改写规则（¶4–¶5）

¶4 这个重载要求 `remove_cv_t<T>` 不是 `pair` 的特化。

¶5 返回值按下表决定，`UA` 指 `uses_allocator_v<remove_cv_t<T>, Alloc>`：

| | 条件 | 返回 |
|---|---|---|
| ¶5.1 | `UA` 为假，且 `is_constructible_v<T, Args...>` | `forward_as_tuple(std::forward<Args>(args)...)` |
| ¶5.2 | `UA` 为真，且 `is_constructible_v<T, allocator_arg_t, const Alloc&, Args...>` | `tuple<allocator_arg_t, const Alloc&, Args&&...>(allocator_arg, alloc, args...)` |
| ¶5.3 | `UA` 为真，且 `is_constructible_v<T, Args..., const Alloc&>` | `forward_as_tuple(args..., alloc)` |
| ¶5.4 | 其他 | 程序 {{ill-formed}} |

¶5.4 的用意见注 2：防止分配器悄悄地没有传进去。一个类型通过 `allocator_type` 声称自己使用分配器，却没有任何接受分配器的构造函数，多半是写错了。与其退回不带分配器的构造、让元素从全局堆分配，不如直接报错。

```cpp run error
#include <memory>
#include <memory_resource>
struct Liar {
  using allocator_type = std::pmr::polymorphic_allocator<>;
  Liar(int) {}   // 没有接受分配器的构造函数
};
std::pmr::polymorphic_allocator<> pa;
auto x = std::make_obj_using_allocator<Liar>(pa, 1);   // error: ¶5.4
```

libc++ 用一条 `static_assert` 报告这个错误，消息是 "If uses_allocator_v<Type> is true, the type has to be allocator-constructible"。

### `pair` 的处理（¶6–¶22）

`pair` 没有 `allocator_type`，也没有 `uses_allocator` 特化，它本身不使用分配器，但它的成员可能使用。所以 `pair` 的各个重载最后都归结为**分段构造**（piecewise construction）：把 `first` 和 `second` 的实参分别改写。这些重载都要求 `remove_cv_t<T>` 是 `pair` 的特化，所以构造 `const pair<A, B>` 时也走这条路径（[[LWG3677]]）。

| 段落 | 实参形式 | 改写为 |
|---|---|---|
| ¶6–¶8 | `(alloc, piecewise_construct, x, y)` | 对 `x` 的元素递归调用 `uses_allocator_construction_args<T1>`，对 `y` 调用 `<T2>`，返回 `make_tuple(piecewise_construct, 新的 x, 新的 y)` |
| ¶9–¶10 | `(alloc)` | 两个空 `tuple` |
| ¶11–¶12 | `(alloc, u, v)` | `forward_as_tuple(u)` 和 `forward_as_tuple(v)` |
| ¶13–¶16 | `(alloc, pr)`，`pr` 是 `pair<U, V>` 的左值或右值 | 分别取出 `first` 和 `second` |
| ¶17–¶18 | `(alloc, p)`，`p` 满足 `pair-like` 但不是 `ranges::subrange` | 用 `get<0>`、`get<1>` 拆开（[[LWG3821]]） |
| ¶19–¶22 | `(alloc, u)`，`u` 不能拆开 | 见下文 |

最后一种情形处理的是能转换为 `pair`、但本身不是 `pair` 也不满足 `pair-like` 的对象，比如一个有 `operator pair<A, B>()` 的类。¶20 的约束用一个说明用的函数模板 `FUN(const pair<A, B>&)` 来排除 `pair` 及其派生类，那些情形由前面的重载处理；`ranges::subrange` 虽然满足 `pair-like`，也走这一条。

这样的 `u` 没法拆开分别传给两个成员。¶21 的办法是返回一个代理对象：说明用的类 `pair-constructor` 保存 `alloc` 和对 `u` 的引用，并提供到 `pair` 的转换函数。¶22 返回 `make_tuple(pc)`。

目标对象最后由 `pc` 初始化时，转换函数才被调用。它先把 `u` 转换成一个临时 `pair`，再对这个临时对象调用 `make_obj_using_allocator`，也就是递归地走从 `pair` 右值构造的路径。这样，转换被推迟到了构造的时刻，返回的 `tuple` 里只装了一个廉价的代理。

### 两个构造函数（¶23–¶24）

¶23 `make_obj_using_allocator<T>(alloc, args...)` 等价于 `make_from_tuple<T>(uses_allocator_construction_args<T>(alloc, args...))`。

¶24 `uninitialized_construct_using_allocator(p, alloc, args...)` 等价于用 `apply` 把改写后的实参展开，交给 `construct_at(p, ...)`。`polymorphic_allocator::construct` 做的就是这件事。

## 思考题

!!! question "思考题 1"
    一个类型同时有 `T(allocator_arg_t, const A&, int)` 和 `T(int, const A&)`，uses-allocator 构造选哪一个？

<details markdown="1">
<summary>答案</summary>

前置形式。¶5.2 先于 ¶5.3 检查，只要 `is_constructible_v<T, allocator_arg_t, const Alloc&, Args...>` 成立，就不会再看后置形式。
</details>

!!! question "思考题 2"
    `std::pmr::vector<std::pmr::vector<int>>` 中，内层 vector 是否从外层的资源分配？`std::vector<std::pmr::vector<int>>` 呢？

<details markdown="1">
<summary>答案</summary>

前者是。外层的 `polymorphic_allocator::construct` 对元素做 uses-allocator 构造；`pmr::vector<int>` 的 `allocator_type` 是 `polymorphic_allocator<int>`，可以由 `polymorphic_allocator<pmr::vector<int>>` 转换得到，于是外层的资源按后置约定传了进去。

后者不是。外层用的是 `std::allocator`，`allocator_traits` 的 `construct` 只调用 `construct_at`，不做 uses-allocator 构造。内层 vector 使用默认构造的 `polymorphic_allocator`，也就是 `get_default_resource()` 返回的资源。
</details>
