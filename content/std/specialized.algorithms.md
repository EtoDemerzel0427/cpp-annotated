---
title: 特化的 <memory> 算法
summary: 在未初始化的存储上创建和销毁对象的算法：异常时自动销毁已构造的对象、目标迭代器为什么必须不抛异常、默认初始化与值初始化的区别、uninitialized_move 失败后源对象的状态，以及 construct_at、destroy_at、destroy。
status: done
covers: *
papers: P0040R3, P0784R7, P0896R4, P2283R2
related: basic.life, expr.new, intro.object, allocator.traits, default.allocator, algorithms.requirements, iterator.concepts
tags: 标准库, 算法, 未初始化存储, placement new, 异常安全, constexpr
updated: 2026-10-19
---

!!! tldr
    - 普通算法向已经存在的对象赋值；本节的算法用 placement new 在原始存储上创建对象，或者结束对象的生命期。
    - 构造到一半抛出异常时，已经构造好的对象会被自动销毁，然后异常继续传播。
    - 目标迭代器必须是前向迭代器，而且自增、比较、解引用都不能抛异常，因为回滚时要再走一遍目标区间。
    - `uninitialized_default_construct` 对 `int` 这类类型什么也不做，`uninitialized_value_construct` 会把它们置零。
    - `construct_at` 让常量求值中也能在指定位置构造对象，`std::vector` 能在 C++20 成为 `constexpr` 靠的就是它。

## 赋值与构造的区别

```cpp run title="uninit_rollback.cpp" flags="-std=c++2c -fsanitize=address,undefined" ok
#include <cassert>
#include <memory>
#include <stdexcept>
#include <string>

static int live = 0;
struct T {
    std::string s;
    explicit T(const std::string& x) : s(x) {
        if (x == "boom") throw std::runtime_error("boom");
        ++live;
    }
    T(const T& o) : T(o.s) {}
    ~T() { --live; }
};

int main() {
    std::string src[] = {"a", "b", "boom", "c"};
    alignas(T) unsigned char buf[sizeof(T) * 4];   // 原始存储，没有 T 对象
    T* p = reinterpret_cast<T*>(buf);
    try {
        // 第 3 个构造抛出异常
        std::uninitialized_copy(std::begin(src), std::end(src), p);
    } catch (const std::runtime_error&) {
        assert(live == 0);   // 已构造的 "a"、"b" 已被自动销毁
    }
}
```

`buf` 只是一块字节，里面没有 `T` 对象。对它执行 `std::copy` 意味着向不存在的对象赋值，是未定义行为（[[basic.life]]）。`std::uninitialized_copy` 则在每个位置用 placement new（[[expr.new]]）创建一个新对象。

`vector`、`optional`、内存池这类自己管理存储的组件，都由这几个算法搭成。例如 `vector` 扩容时，大致就是在新存储上 `uninitialized_move`（或复制），再 `destroy` 旧存储上的元素。

## 总则（[specialized.algorithms.general]）

¶1 本节的内容声明在 `<memory>` 中。

!!! std
    Unless otherwise specified, if an exception is thrown in the following algorithms, objects constructed by a placement *new-expression* are destroyed in an unspecified order before allowing the exception to propagate.

¶2 规定了异常时的行为：已经用 placement new 构造好的对象，在异常继续传播之前以未指定的顺序销毁。对目标区间来说，要么全部构造成功，要么回到没有对象的状态。调用者不必自己记录构造到了第几个，上面的例子里 `live` 回到了 0。

¶3 注 1 提醒，这些算法在一块存储上创建新对象时，原来占用这块存储的对象生命期就结束了（[[basic.life]]）。

¶4 定义了两个仅用于说明的函数模板：

```cpp
template<class T>
  constexpr void* voidify(T& obj) noexcept {
    return addressof(obj);
  }

template<class I>
  constexpr decltype(auto) deref-move(I& it) {
    if constexpr (is_lvalue_reference_v<decltype(*it)>)
      return std::move(*it);
    else
      return *it;
  }
```

`voidify` 用 `addressof` 而不用 `&`，是为了不受重载的 `operator&` 影响。返回 `void*`，是为了让 `::new (p) T` 调用全局的 placement 分配函数，不让类自己定义的 `operator new` 介入。

`addressof(obj)` 隐式转换为 `void*`，`obj` 是 const 对象时这个转换不合法。所以不能在 const 迭代器指向的位置上构造对象。本机 libc++ 对 `std::uninitialized_fill(const int*, const int*, 1)` 报错 `static_cast from 'const int *' to 'void *' is not allowed`。早期的措辞用 `const_cast` 去掉了 cv 限定，允许这样做，后来改成了现在的写法。

*deref-move* 在 `*it` 是左值引用时移动它，否则（例如迭代器返回纯右值）直接使用 `*it` 的结果。这比无条件写 `std::move(*it)` 更准确。

## 目标迭代器不能抛异常（[special.mem.concepts]）

¶2 的回滚要求实现在异常发生后，从头再遍历一遍已构造的目标区间，逐个销毁。这对目标迭代器提出了两个要求：

- 它必须是前向迭代器，能多趟遍历；
- 它的自增、复制、比较、解引用都不能抛异常。回滚过程中再抛一个异常，回滚就无法完成。

`std` 中的版本把这个要求写在模板形参名 `NoThrowForwardIterator` 上（[[algorithms.requirements#4]] 的 ¶4.5）。`ranges` 版本用一组仅用于说明的概念表达：*nothrow-input-iterator*、*nothrow-forward-iterator*、*nothrow-sentinel-for* 等，C++26 的并行版本还用到 *nothrow-random-access-iterator* 等。

¶1 定义 *nothrow-input-iterator* 时还要求 `iter_reference_t<I>` 是左值引用，去掉 cv 和引用后就是值类型。构造的目标必须是真实的存储，返回代理对象的迭代器不行。

不抛异常这部分是语义要求（¶2、¶4 等），编译器无法检查。各条的注说明，这些概念允许对应的标准迭代器概念中的某些操作抛异常，区别只在于类型是否 model 这个概念。

## 默认构造与值构造（[uninitialized.construct.default]、[uninitialized.construct.value]）

两者的效果分别等价于：

```cpp
for (; first != last; ++first)
  ::new (voidify(*first)) iterator_traits<I>::value_type;    // 默认构造
for (; first != last; ++first)
  ::new (voidify(*first)) iterator_traits<I>::value_type();  // 值构造
```

区别只有一对 `()`。

默认初始化对 `int` 这类类型什么也不做，对象的值是存储里原有的内容。对分配器得到的动态存储来说，那是**不确定值**，读取它是 {{ub}}。C++26 的错误值只适用于自动存储期的对象，见 [[basic.indet]]。值初始化则把这些对象置零。

`make_unique_for_overwrite`、不需要初始化内容的缓冲区等场合用默认构造，省掉清零的开销。

`_n` 版本返回构造结束的位置；`ranges` 的 `_n` 版本通过 `counted_iterator` 定义。

## `uninitialized_copy` 与 `uninitialized_move`（[uninitialized.copy]、[uninitialized.move]）

[uninitialized.copy] ¶1 的前置条件是目标区间与源区间完全不重叠。`std::copy` 允许某些重叠，这里任何重叠都不允许：目标是未初始化的存储，本来就不应该与现有对象重合。¶2 的效果是在每个目标位置执行 `::new (voidify(*result)) value_type(*first)`。

`ranges` 版本（¶4–¶5）接受两个区间，任一个耗尽就停止，返回 `{输入位置, 输出位置}`。输出有终点，不会写越界。

`uninitialized_move` 的结构相同，只是用 *deref-move*（`std` 版本）或 `ranges::iter_move`（`ranges` 版本）取得源对象。[uninitialized.move] ¶5、¶10 的注说明：抛出异常时，源区间中的某些对象处于有效但未指定的状态。目标区间被回滚了，可已经被移走的源对象回不来。

这就是 `vector` 扩容时的两难。用 `uninitialized_move` 可能失去强异常保证，所以 `vector` 只在元素的移动构造是 `noexcept`（或者元素不可复制）时才移动，否则复制，这就是 `move_if_noexcept` 的用途。

[uninitialized.move] ¶7 经典的 `uninitialized_move_n` 返回 `{first, result}` 一对位置，而 `uninitialized_copy_n` 只返回 `result`。

## `uninitialized_fill`（[uninitialized.fill]）

¶1 在每个位置执行 `::new (voidify(*first)) value_type(x)`，用 `x` 复制构造。

## `construct_at`（[specialized.construct]）{{c++20}}

```cpp
template<class T, class... Args>
  constexpr T* construct_at(T* location, Args&&... args);
```

¶1 *Constraints*：`T` 不是边界未知的数组，而且 `::new (declval<void*>()) T(declval<Args>()...)` 良构。¶2 *Mandates*：`T` 是数组类型时不能有构造实参。¶3 `T` 是数组时执行 `::new (voidify(*location)) T[1]()`，对整个数组值初始化；否则执行 `::new (voidify(*location)) T(std::forward<Args>(args)...)`。

C++20 允许在常量表达式中使用 `std::construct_at` 和 `std::allocator<T>::allocate`，但不允许直接写 placement new（[[P0784R7]]）。`std::vector` 能在 C++20 成为 `constexpr`，靠的就是 `construct_at`。C++26 起常量表达式中也可以直接写 placement new，本机 Clang 23 已经支持。

`construct_at` 用圆括号初始化，所以 `construct_at<Agg>(p, 1, 2)` 对聚合也可以用，C++20 起聚合支持圆括号初始化（[[dcl.init.general]]）。

## `destroy_at`、`destroy`、`destroy_n`（[specialized.destroy]）

¶1 `destroy_at(location)` 对数组类型逐个销毁其元素（C++20 起支持数组），否则调用 `location->~T()`。

¶2 `destroy(first, last)` 对每个元素调用 `destroy_at(addressof(*first))`，从前往后进行。数组和标准容器析构时一般按逆序销毁元素，这里的顺序正好相反。

¶3 `ranges` 版本的 `destroy` 只要求 *nothrow-input-iterator*。销毁不需要回滚，单趟遍历就够了。

```cpp run title="construct_at_constexpr.cpp" ok
#include <memory>

struct Agg { int x, y; };

constexpr int f() {
    std::allocator<int> a;
    int* p = a.allocate(3);
    int src[3] = {1, 2, 3};
    std::uninitialized_copy(src, src + 3, p);  // C++26 起 constexpr
    std::destroy_at(p);
    std::construct_at(p, 10);                  // 替换第一个元素
    int r = p[0] + p[1] + p[2];
    std::destroy(p, p + 3);
    a.deallocate(p, 3);
    return r;
}
static_assert(f() == 15);

constexpr int g() {
    std::allocator<Agg> a;
    Agg* p = a.allocate(1);
    std::construct_at(p, 1, 2);                // 聚合的圆括号初始化
    int r = p->y;
    std::destroy_at(p);
    a.deallocate(p, 1);
    return r;
}
static_assert(g() == 2);

int main() {}
```

!!! history "演进"
    - C++98：`uninitialized_copy`、`uninitialized_fill`、`uninitialized_fill_n`；
    - C++17：`uninitialized_default_construct`、`uninitialized_value_construct`、`uninitialized_move`、`destroy_at`、`destroy`（[[P0040R3]]），以及并行重载；
    - C++20：`construct_at`，`destroy` 系列成为 `constexpr`（[[P0784R7]]），`ranges` 版本（[[P0896R4]]），`destroy_at` 支持数组；
    - C++26：`uninitialized_*` 全部成为 `constexpr`（[[P2283R2]]），以及并行的 `ranges` 版本。

## 思考题

!!! question "思考题 1"
    为什么 `uninitialized_copy` 的 `std` 版本只要求源是输入迭代器，目标却必须是 `NoThrowForwardIterator`？

<details markdown="1">
<summary>答案</summary>

源只需要读一遍。目标在异常发生时要回头销毁已构造的对象（¶2），所以必须能多趟遍历；回滚过程中迭代器操作也不能抛异常，否则回滚无法完成。这正是 `NoThrow` 的含义（[[algorithms.requirements#4]] 的 ¶4.5）。
</details>

!!! question "思考题 2"
    对一块已经存放着 `std::string` 对象的存储调用 `std::uninitialized_fill`，会发生什么？

<details markdown="1">
<summary>答案</summary>

placement new 在这块存储上创建新对象，原来的 `string` 生命期结束（¶3 注 1），但它的析构函数没有被调用，它持有的堆内存就泄漏了。按 [[basic.life]]，不调用析构函数本身不是未定义行为，只要程序不依赖析构函数的副作用；但这几乎总是 bug。正确做法是先 `destroy` 再 `uninitialized_fill`，或者直接用 `fill` 赋值。
</details>

## 小结

| 算法 | 如何初始化 | 前置条件 | 异常时 |
|---|---|---|---|
| `uninitialized_default_construct` | 默认初始化，`int` 等不清零 | 无 | 回滚 |
| `uninitialized_value_construct` | 值初始化 | 无 | 回滚 |
| `uninitialized_copy`、`_n` | 复制构造 | 不重叠 | 回滚 |
| `uninitialized_move`、`_n` | 移动构造（*deref-move*） | 不重叠 | 回滚；源对象可能已被移走 |
| `uninitialized_fill`、`_n` | 由 `x` 复制构造 | 无 | 回滚 |
| `construct_at` | `T(args...)` 圆括号；数组值初始化 | 无 | 异常直接传播 |
| `destroy_at`、`destroy`、`destroy_n` | 不适用 | 无 | 从前往后销毁 |
