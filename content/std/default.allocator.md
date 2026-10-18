---
title: 默认分配器 std::allocator
summary: std::allocator<T> 的完整契约——经由 ::operator new 取得存储但"何时、几次"未指明，只开始数组对象而不开始元素的生命周期；allocate_at_least 与 deallocate 的大小匹配前置条件；constexpr 中的瞬时分配；历次被删减的成员
status: done
covers: default.allocator.general, allocator.members, allocator.globals
related: allocator.traits, basic.stc.dynamic, new.delete, expr.new, expr.const, intro.object, basic.life
tags: 标准库, 分配器, allocator, constexpr
papers: P0784R7, P0401R6, P2868R3
updated: 2026-10-18
---

`std::allocator<T>` 是所有标准容器的默认分配器，也是"最小分配器"的标准范例。它的接口在 C++11 之后被**逐步削减**到只剩下必需的部分——今天的完整定义只有十来行：

```cpp
template<class T> class allocator {
public:
  using value_type                             = T;
  using size_type                              = size_t;
  using difference_type                        = ptrdiff_t;
  using propagate_on_container_move_assignment = true_type;

  constexpr allocator() noexcept;
  constexpr allocator(const allocator&) noexcept;
  template<class U> constexpr allocator(const allocator<U>&) noexcept;
  constexpr ~allocator();
  constexpr allocator& operator=(const allocator&) = default;

  constexpr T* allocate(size_t n);
  constexpr allocation_result<T*> allocate_at_least(size_t n);
  constexpr void deallocate(T* p, size_t n);
};
```

所有其他东西（`pointer`、`rebind`、`construct`、`max_size`……）都由 [[allocator.traits]] 补全。

## 概述（[default.allocator.general]）

- ¶1：所有特化都满足**分配器完整性要求**（[[allocator.requirements.completeness]]）：即使 `T` 不完整，`allocator<T>` 本身也是完整类型，可以用来实例化 `vector<T>` 的类定义。这是 C++17 允许 `vector`/`list`/`forward_list` 使用不完整元素类型的前提。
- ¶2：`allocator_traits<allocator<T>>::is_always_equal::value` 对任何 `T` 为真。

¶2 的写法值得注意：它说的是 **traits** 的值，而不是 `allocator` 的成员。C++17 曾给 `allocator` 加了 `is_always_equal` 成员 typedef，C++23 将其弃用（因为它会被派生类继承——派生自 `std::allocator` 的有状态分配器会**错误地**声称自己总相等），C++26 由 [[P2868R3]] 移除。现在这个值来自 traits 的默认规则：`allocator` 是空类，`is_empty<allocator<T>>` 为真。

`propagate_on_container_move_assignment` 是 `true_type`。对一个总相等的分配器这似乎多余，但它让容器可以无条件走"释放自己的、偷对方的"路径，而无需比较分配器。

### 被移除的成员

| 成员 | 状态 |
|---|---|
| `pointer`、`const_pointer`、`reference`、`const_reference`、`rebind`、`address`、`max_size`、`construct`、`destroy`、`allocate(n, hint)` | C++17 弃用，C++20 移除 |
| 显式特化 `allocator<void>` | C++17 弃用，C++20 移除（主模板 `allocator<void>` 仍可实例化类定义） |
| `is_always_equal` | C++23 弃用，C++26 移除 |

它们全部可由 `allocator_traits` 的默认值得到，留着只会诱导用户绕过 traits 直接调用。

## 成员函数（[allocator.members]）

### ¶1：线程安全与分配顺序

!!! std "[allocator.members]/1"
    Except for the destructor, member functions of the default allocator shall not introduce data races as a result of concurrent calls to those member functions from different threads.

    除析构函数外，默认分配器的成员函数不得因来自不同线程的并发调用而引入数据竞争。

后半句规定：对**同一单元存储**的分配和释放调用构成一个全序，每次释放**先发生于**该序中下一次分配。直觉：内存块被释放后再被别的线程分配到，前一个线程对它的所有写入对后一个线程可见、不构成数据竞争——这是 [[new.delete.dataraces]] 对 `operator new`/`operator delete` 同样的保证在分配器层面的复述。

### `allocate`（¶2–¶5）

- ¶2 *Mandates*：`T` 不是不完整类型。（`allocator<T>` 的类定义可以对不完整 `T` 实例化，但 `allocate` 不行——它要 `sizeof(T)`。）
- ¶3 *Returns*：指向 `n` 个 `T` 的数组的首元素的指针。
- ¶4 *Throws*：若 `numeric_limits<size_t>::max() / sizeof(T) < n`，抛出 `bad_array_new_length`；存储无法取得时抛出 `bad_alloc`。
- ¶5 *Remarks*：存储通过调用 `::operator new` 获得，但**未指明何时、调用多少次**。此函数开始**数组对象**的生命周期，但不开始任何**数组元素**的生命周期。

¶5 的两句话各有深意。

**"何时、几次未指明"** 赋予实现合并或省略分配的自由，与 [[expr.new]] 中允许编译器省略或合并 *new-expression* 的分配调用相对应。后果是：如果你替换了全局 `operator new` 来计数，`std::allocator` 的调用次数不一定与 `operator new` 的调用次数一一对应。（实践中 libc++ 是一次 `allocate` 对应一次 `operator new`；在常量求值之外它调用的是 `__builtin_operator_new`，这个内建函数的意义正是告诉 Clang "这次调用享有 *new-expression* 同样的省略许可"。）

**"开始数组对象的生命周期，但不开始元素的生命周期"** 把 `allocate` 精确地定位在对象模型中：

- 数组对象存在，所以返回的 `T*` 指向**数组元素**（尽管该元素尚未在生命周期内），可以合法地做指针算术遍历 `[p, p + n]`（[[expr.add]] 要求指针算术在一个数组对象内）。这是 C++20 [[P0593R6]] 修补的一个老问题：此前 `vector` 的实现在严格意义上一直在对"不存在的数组"做指针算术。
- 元素不存在，所以必须用 `construct_at`/`allocator_traits::construct` 逐个构造（[[basic.life]] 中关于生命周期开始的规则）；读写未构造的元素是 {{ub}}。

```cpp title="allocator-lifetime.cpp" ok
#include <memory>
#include <string>

constexpr bool f() {
    std::allocator<std::string> a;
    std::string* p = a.allocate(2);   // 数组对象 string[2] 的生命周期开始，元素没有
    std::construct_at(p, "x");        // 只构造 p[0]
    bool r = p[0] == "x";
    // p[1] 从未构造；p + 2 是合法的尾后指针
    std::destroy_at(p);
    a.deallocate(p, 2);
    return r;
}
static_assert(f());

int main() {}
```

### `allocate_at_least`（¶6–¶9）{{c++23}}

与 `allocate` 相同，但返回 `allocation_result<T*>{ptr, count}`，`count >= n`（[[P0401R6]]）。它的意义见 [[allocator.traits]]。标准允许 `count` 大于 `n`，但不要求——libc++ 目前总是返回恰好 `n`（底层 `operator new` 无法报告实际块大小）：

```cpp title="allocate-at-least.cpp" ok
#include <memory>
#include <new>
#include <cstdio>
#include <limits>

int main() {
    std::allocator<int> a;
    auto [p, n] = a.allocate_at_least(5);     // allocation_result 是聚合，可结构化绑定
    std::printf("asked 5, got %zu\n", n);     // libc++：5
    a.deallocate(p, 5);                       // 第二个实参可以是 [5, n] 中任意值
    try {
        (void)a.allocate(std::numeric_limits<std::size_t>::max() / 2);
    } catch (const std::bad_array_new_length&) {
        std::puts("bad_array_new_length");    // max / sizeof(int) < n
    }
    static_assert(std::allocator<int>() == std::allocator<long>());
    static_assert(std::allocator_traits<std::allocator<int>>::is_always_equal::value);
}
```

### `deallocate`（¶10–¶12）

¶10 的前置条件要求**大小匹配**：

- (10.1) 若 `p` 来自 `allocate_at_least`，返回值为 `ret`、请求为 `req`，则 `p == ret.ptr` 且 `req <= n <= ret.count`；
- (10.2) 否则 `p` 来自 `allocate`，且 `n` 等于当初传给 `allocate` 的值。

违反即 {{ub}}。这不是吹毛求疵：`::operator delete` 有**带大小**的版本（sized deallocation，C++14），实现可以把 `n * sizeof(T)` 直接传给它，而 tcmalloc、jemalloc 等分配器会用这个大小**直接定位尺寸档位**而不查元数据——传错大小会破坏堆。

¶12：使用 `::operator delete`，但**何时**调用未指明。

## 运算符（[allocator.globals]）

`operator==(const allocator<T>&, const allocator<U>&)` 总是返回 `true`（`!=` 由 C++20 的重写规则生成）。不同 `T` 的 `allocator` 也相等：一个可以释放另一个分配的内存（当然要经过 rebind）。

## 常量求值中的 `std::allocator`

C++20 起 `allocate`/`deallocate` 是 `constexpr` 的（[[P0784R7]]），这是 `constexpr std::vector`、`constexpr std::string` 的基础。常量求值中的分配必须是**瞬时**的（[[g:transient-allocation]]，[[expr.const]]）：在同一次求值内释放，不能"泄漏"到运行期。

```cpp title="constexpr-leak.cpp" error
#include <memory>
constexpr int* leak() {
    std::allocator<int> a;
    int* p = a.allocate(1);
    std::construct_at(p, 7);
    return p;                      // 存储没有在常量求值内释放
}
constexpr int* q = leak();         // error: 不是常量表达式
```

Clang 的诊断："pointer to subobject of heap-allocated object is not a constant expression"，并指出"heap allocation performed here"。

注意常量求值中**只有** `std::allocator<T>::allocate` 和可替换的全局 `operator new`（经由 *new-expression*）能分配；自定义分配器若想在常量求值中使用，必须在内部委托给 `std::allocator`。

## 思考题

<details markdown="1">
<summary>1. 从 `std::allocator<int>` 派生一个带计数器成员的分配器 `Counting<int>`，在 C++17 下 `allocator_traits<Counting<int>>::is_always_equal` 是什么？C++26 呢？</summary>

C++17 中 `std::allocator` 有成员 `using is_always_equal = true_type;`，被 `Counting` 继承，traits 优先采用 `Alloc::is_always_equal`，于是为真——这是个谎言（`Counting` 非空、有状态），容器移动赋值会无条件偷缓冲区。这正是该成员被弃用和移除的原因。C++26 中继承不到这个成员，traits 退回 `is_empty<Counting<int>>`，为假。
</details>

<details markdown="1">
<summary>2. `a.deallocate(p, n)` 时把 `n` 传成 0 会怎样？</summary>

除非当初就是 `allocate(0)`，否则违反 ¶10 前置条件，{{ub}}。实践中若实现调用 sized `operator delete(p, 0)`，使用尺寸档位定位的分配器会把块放进错误的空闲链表。
</details>

## 小结

- `std::allocator<T>`：空类、总相等、POCMA 为真；其余接口由 `allocator_traits` 补全。
- `allocate`：可能抛 `bad_array_new_length` 或 `bad_alloc`；经 `::operator new` 但次数与时机未指明；开始数组对象而非元素的生命周期。
- `deallocate`：大小必须匹配（`allocate_at_least` 时可在 `[req, count]` 之间）。
- `constexpr`：常量求值中的分配必须在同一次求值内释放。
