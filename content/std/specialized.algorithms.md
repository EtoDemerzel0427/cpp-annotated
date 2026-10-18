---
title: 特化的 <memory> 算法
summary: 在未初始化存储上构造/销毁对象的算法——异常时自动销毁已构造对象、voidify 与 deref-move 的作用、NoThrowForwardIterator 与 nothrow-* 说明用概念为何必须“不抛”、default/value 构造的区别、uninitialized_copy/move/fill 的重叠前置条件与 uninitialized_move 失败后源对象的状态、construct_at/destroy_at/destroy 的 constexpr 化与数组支持
status: done
covers: *
papers: P0040R3, P0784R7, P0896R4, P2283R2
related: basic.life, expr.new, intro.object, allocator.traits, default.allocator, algorithms.requirements, iterator.concepts
tags: 标准库, 算法, 未初始化存储, placement new, 异常安全, constexpr
updated: 2026-10-18
---

普通算法向**已存在的对象**赋值；本节的算法在**原始存储**上**创建**对象（经由 placement new，[[expr.new]]）或结束对象的生命期。它们是实现 `vector`、`optional`、内存池这类“自己管理存储”的组件的积木：`vector::reserve` 后的扩容搬迁就是 `uninitialized_move` + `destroy`。

区分“赋值”与“构造”在对象模型上至关重要：对一块没有对象的存储执行 `*p = x` 是 {{ub}}（没有对象可赋值，[[basic.life]]）；反过来对一块已有对象的存储再次 placement new，会结束原对象的生命期而不调用其析构函数。

## 总则（[specialized.algorithms.general]）

¶1：内容声明于 `<memory>`。

¶2——**异常安全**：

!!! std
    Unless otherwise specified, if an exception is thrown in the following algorithms, objects constructed by a placement *new-expression* are destroyed in an unspecified order before allowing the exception to propagate.

即：要么全部构造成功，要么已经构造的对象被销毁、存储恢复为“无对象”状态（强异常保证，针对目标区间而言）。调用者不必自己记录构造到了第几个。

¶3 注 1：这些算法在存储上创建新对象时，原先占据该存储的对象（包括潜在重叠子对象）的生命期结束（[[basic.life]]）。

¶4 定义两个仅用于说明的函数模板：

```cpp
template<class T>
  constexpr void* voidify(T& obj) noexcept { return addressof(obj); }

template<class I>
  constexpr decltype(auto) deref-move(I& it) {
    if constexpr (is_lvalue_reference_v<decltype(*it)>) return std::move(*it);
    else return *it;
  }
```

- `voidify` 用 `addressof` 而不是 `&`，是为了绕过重载的 `operator&`；返回 `void*` 是为了调用全局的 `::new (void*) T`，不让类自定义的 placement `operator new` 介入。注意它是**隐式**转换为 `void*`——这意味着 `obj` 若是 const 对象，转换非良构。早期的措辞用 `const_cast` 去掉了 cv，允许经由 `const T*` 构造对象；后来改成现在的写法，**不再允许**向 const 迭代器所指的存储构造对象。本机 libc++ 对 `std::uninitialized_fill(const int*, const int*, 1)` 报 “static_cast from 'const int *' to 'void *' is not allowed”。
- *deref-move*：`*it` 是左值引用时移动它，否则（如代理/纯右值）直接用其结果——比无条件 `std::move(*it)` 更正确。

## 特殊内存概念（[special.mem.concepts]）

ranges 版本用一组仅用于说明的概念约束：*nothrow-input-iterator*、*nothrow-sentinel-for*、*nothrow-sized-sentinel-for*、*nothrow-input-range*、*nothrow-forward-iterator*、*nothrow-forward-range*，以及 C++26 并行版所需的 *nothrow-bidirectional-iterator*、*nothrow-random-access-iterator*、*nothrow-sized-random-access-range*。

¶1 的定义还要求 *nothrow-input-iterator* 的 `iter_reference_t` 是**左值引用**且去掉 cvref 后就是值类型——构造目标必须是真实存储，代理迭代器不行。

“nothrow”部分是**纯语义**要求（¶2 等）：迭代器的自增、复制、比较、解引用不抛异常。注 1 等说明这些概念“允许”某些对应标准概念的操作抛出——区别只在 model 与否。为什么必须不抛？¶2 的回滚保证需要在异常发生后**再遍历一遍**已构造的区间去销毁它们；若此时迭代器操作又抛出，回滚就无法完成。经典版本对应的是 [[algorithms.requirements#4]] 中形参名 `NoThrowForwardIterator` 的要求（¶4.5）。

注意目标迭代器必须是**前向**的（多趟）：回滚要从头再走一遍。

## 默认构造与值构造（[uninitialized.construct.default]、[uninitialized.construct.value]）

```cpp
for (; first != last; ++first)
  ::new (voidify(*first)) iterator_traits<NoThrowForwardIterator>::value_type;    // default
  ::new (voidify(*first)) iterator_traits<NoThrowForwardIterator>::value_type();  // value
```

区别就是 `()`：**默认初始化**对 `int` 等平凡类型不做任何事——对象保留存储原有的字节值；对通过分配器得到的动态存储，那是**不确定值**，读取是 {{ub}}（C++26 的“错误值”只适用于自动存储期对象，见 [[basic.indet]]）；**值初始化**把它们置零。`make_unique_for_overwrite`、`vector` 不初始化的扩容等场景用的是前者——省掉清零开销。

`_n` 版本返回终点；ranges 版本通过 `counted_iterator` 定义。

## `uninitialized_copy`（[uninitialized.copy]）

- ¶1 *Preconditions*：`result + [0, (last − first))` 与 `[first, last)` **不重叠**（与 `copy` 不同，任何重叠都不允许——目标是未初始化存储，本来就不该与已有对象重叠）；
- ¶2 *Effects*：逐个 `::new (voidify(*result)) value_type(*first)`；
- ranges 版（¶4–¶5）接受**两个**区间，在任一耗尽时停止，返回 `{in, out}`——输出有界，不会越界写。

## `uninitialized_move`（[uninitialized.move]）

与 `uninitialized_copy` 同构，用 *deref-move*（经典版）或 `ranges::iter_move`（ranges 版）。¶5、¶10 的注说明：若抛出异常，`[first, last)` 中的某些源对象处于**有效但未指明**的状态——目标区间被回滚了，但已经被移走的源对象回不来。

这就是 `vector` 扩容时的经典两难：用 `uninitialized_move` 可能丢失强异常保证，所以 `vector` 只在移动构造 `noexcept`（或不可复制）时才移动，否则复制（`move_if_noexcept`）。

经典版 `uninitialized_move_n` 返回 `pair{first, result}`（¶7），这一点与 `uninitialized_copy_n` 只返回 `result` 不同。

## `uninitialized_fill`（[uninitialized.fill]）

逐个 `::new (voidify(*first)) value_type(x)`。

```cpp run title="uninit_rollback.cpp" flags="-std=c++2c -fsanitize=address,undefined" ok
#include <cassert>
#include <memory>
#include <stdexcept>
#include <string>

static int live = 0;
struct T {
    std::string s;
    explicit T(const std::string& x) : s(x) { if (x == "boom") throw std::runtime_error("boom"); ++live; }
    T(const T& o) : T(o.s) {}
    ~T() { --live; }
};

int main() {
    std::string src[] = {"a", "b", "boom", "c"};
    alignas(T) unsigned char buf[sizeof(T) * 4];
    T* p = reinterpret_cast<T*>(buf);
    try {
        std::uninitialized_copy(std::begin(src), std::end(src), p);  // 第 3 个构造抛异常
    } catch (const std::runtime_error&) {
        assert(live == 0);   // 已构造的 "a"、"b" 被自动销毁（¶2）
    }
}
```

## `construct_at`（[specialized.construct]）{{c++20}}

```cpp
template<class T, class... Args>
  constexpr T* construct_at(T* location, Args&&... args);
```

- ¶1 *Constraints*：`T` 不是无界数组；`::new (declval<void*>()) T(declval<Args>()...)` 良构；
- ¶2 *Mandates*：若 `T` 是数组类型，`sizeof...(Args)` 为零；
- ¶3 *Effects*：数组类型时为 `::new (voidify(*location)) T[1]()`（值初始化整个数组），否则为 `::new (voidify(*location)) T(std::forward<Args>(args)...)`。

`construct_at` 存在的意义是**在常量求值中使用 placement new**：C++20 起常量表达式允许 `std::construct_at` 和 `std::allocator<T>::allocate`，但（直到 C++26 放开 constexpr placement new 之前）不允许直接写 placement new（[[P0784R7]]）。`std::vector` 能在 C++20 中 `constexpr` 就靠它。

注意它用的是**圆括号初始化**：`construct_at<Agg>(p, 1, 2)` 对聚合在 C++20 起合法（聚合的圆括号初始化，[[dcl.init.general]]）。

## `destroy_at`、`destroy`、`destroy_n`（[specialized.destroy]）

¶1：`destroy_at(location)` 对数组类型递归销毁每个元素（C++20 起支持数组），否则调用 `location->~T()`。`destroy(first, last)` 对每个元素调用 `destroy_at(addressof(*first))`，按**从前到后**的顺序——注意这与数组/容器析构时“逆序销毁”的惯例相反。

ranges 版的 `destroy` 要求 *nothrow-input-iterator*——只需输入迭代器，因为销毁不需要回滚。

```cpp run title="construct_at_constexpr.cpp" ok
#include <memory>

constexpr int f() {
    std::allocator<int> a;
    int* p = a.allocate(3);
    int src[3] = {1, 2, 3};
    std::uninitialized_copy(src, src + 3, p);   // C++26 起 constexpr
    std::construct_at(p, 10);                   // 先 destroy_at 再 construct_at 才是“替换”
    int r = p[0] + p[1] + p[2];
    std::destroy(p, p + 3);
    a.deallocate(p, 3);
    return r;
}
static_assert(f() == 15);

int main() {}
```

（上例对 `int` 省略了 `destroy_at(p)`——平凡析构的对象可以直接在其存储上构造新对象来结束旧对象的生命期。）

!!! history "演进"
    - C++98：`uninitialized_copy`、`uninitialized_fill`、`uninitialized_fill_n`；
    - C++17：`uninitialized_default_construct`、`uninitialized_value_construct`、`uninitialized_move`、`destroy_at`、`destroy`（[[P0040R3]]），以及并行重载；
    - C++20：`construct_at`、`constexpr` 的 `destroy*`（[[P0784R7]]），ranges 版本（[[P0896R4]]），`destroy_at` 支持数组；
    - C++26：`uninitialized_*` 整体 `constexpr`（[[P2283R2]]），并行 ranges 版本。

## 思考题

<details markdown="1">
<summary>1. 为什么 `uninitialized_copy` 的经典版只要求输入是 `InputIterator`，而输出必须是 `NoThrowForwardIterator`？</summary>

输入只读一遍。输出需要在异常时**回头**销毁已构造的对象（¶2），所以必须多趟（前向），而且回滚过程中迭代器操作不能抛出，否则回滚无法完成——这正是 `NoThrow` 的含义（[[algorithms.requirements#4]] ¶4.5）。
</details>

<details markdown="1">
<summary>2. 对一个已经存放着 `std::string` 对象的存储调用 `std::uninitialized_fill`，会发生什么？</summary>

placement new 在该存储上创建新对象，原 `string` 的生命期结束（¶3 注 1、[[basic.life]]），**但其析构函数没有被调用**——它持有的堆内存泄漏。按 [[basic.life]]，不调用析构函数本身不是 UB，只要程序不依赖析构的副作用；但这几乎总是 bug。正确做法是先 `destroy` 再 `uninitialized_fill`，或直接用 `fill`（赋值）。
</details>

## 小结

| 算法 | 初始化方式 | 重叠/前置条件 | 异常 |
|---|---|---|---|
| `uninitialized_default_construct` | 默认初始化（平凡类型不清零） | — | 回滚 |
| `uninitialized_value_construct` | 值初始化 | — | 回滚 |
| `uninitialized_copy` / `_n` | 复制构造 | 不重叠 | 回滚 |
| `uninitialized_move` / `_n` | 移动构造（*deref-move*） | 不重叠 | 回滚；源对象可能已被移走 |
| `uninitialized_fill` / `_n` | 由 `x` 复制构造 | — | 回滚 |
| `construct_at` | `T(args...)` 圆括号；数组值初始化 | — | 传播 |
| `destroy_at` / `destroy` / `destroy_n` | — | — | 从前到后销毁 |
