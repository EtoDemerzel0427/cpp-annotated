---
title: indirect
summary: C++26 的 indirect<T>：放在堆上的 T，却有 T 的值语义，复制时复制 T，const 会传播，可以按值比较和散列，只有被移动后才可能无值；以及构造、赋值、交换与分配器传播的规则。
status: draft
covers: *
since: c++26
related: mem.composite.types, polymorphic, allocator.traits, allocator.uses, unique.ptr, expr.spaceship
tags: 标准库, indirect, 值语义, C++26, 分配器
papers: P3019R14
updated: 2026-10-19
---

!!! tldr
    - `indirect<T>` 用起来像一个 `T` 类型的成员：复制时复制 `T`，`const indirect<T>` 只给出 `const T&`，`==` 和 `<=>` 比较的是 `T` 的值。
    - 它没有空状态。默认构造也会分配内存并构造一个 `T`；只有被移动之后才会无值。
    - 复制、默认构造等对 `T` 的要求写成 *Mandates* 而不是 *Constraints*，所以 `T` 可以不完整，代价是 `is_copy_constructible_v<indirect<T>>` 对不可复制的 `T` 也为真。
    - 复制赋值在分配器相等时直接对 `T` 赋值，否则先构造新对象再销毁旧对象；移动赋值之后源对象总是无值。
    - 比较时，无值对象小于任何有值对象，两个无值对象相等。

`indirect<T, Allocator = allocator<T>>` 的设计动机见 [[mem.composite.types]]。截至写作时本机 libc++ 尚未实现它，下面的示例都没有经过编译验证。

## 用法

```cpp
#include <memory>
#include <string>
#include <vector>

struct Expr;                                    // 递归类型
struct Binary { char op; std::indirect<Expr> lhs, rhs; };
struct Expr { std::string name; std::vector<Binary> children; };

struct Widget {
    std::indirect<std::string> name{"widget"};
    void rename(const char* s) { *name = s; }
    std::size_t len() const { return name->size(); }   // name-> 是 const std::string*
};

int main() {
    Widget a;
    Widget b = a;                               // 隐式复制构造：复制 string
    b.rename("other");                          // a 不受影响
    Widget c = std::move(a);
    bool gone = a.name.valueless_after_move();  // true
    a.name = std::string("revived");            // 从值赋值，重新有值
    bool eq = (a.name == std::string("revived"));   // 与 T 比较：true
}
```

`Binary` 声明 `indirect<Expr>` 成员时 `Expr` 还不完整，这是允许的。`Widget` 不需要手写任何特殊成员函数：隐式的复制构造复制被拥有的字符串，隐式的移动构造接管指针，`len()` 这个 `const` 成员函数里 `*name` 是 `const std::string&`。

## 概述 [indirect.general]

¶1 `indirect` 对象管理一个**被拥有对象**（owned object）的生命周期。没有被拥有对象时，它是**无值的**（valueless，[[g:valueless]]）。只有被移动之后才可能变为无值。

¶2 `allocator_traits<Allocator>::value_type` 必须与 `T` 相同，否则非良构。¶3 以分配器 `a` 用 `args...` 构造被拥有对象，指调用 `allocator_traits<Allocator>::construct(a, p, args...)`，其中 `p` 来自 `allocator_traits<Allocator>::allocate`。所以 `pmr::indirect<T>` 会对 `T` 做 uses-allocator 构造（[[allocator.uses]]），比如被拥有的 `pmr::string` 也从同一个内存资源分配。

¶4 说明用的成员 *alloc* 只能通过赋值或 `swap` 替换，是否替换由分配器的 `propagate_on_container_copy_assignment`、`propagate_on_container_move_assignment`、`propagate_on_container_swap` 决定，规则与容器相同（[[allocator.traits]]）。下文分别简称 POCCA、POCMA、POCS。

¶5 `T` 不能是非对象类型、数组、`in_place_t`、`in_place_type_t` 的特化或 cv 限定类型。¶6 `T` 可以是不完整类型。¶7 `Allocator` 须满足 *Cpp17Allocator*。¶8 程序声明 `indirect` 的显式特化或偏特化，行为未定义。

说明用的数据成员只有 `pointer p` 和 `Allocator alloc`，对空的分配器类型，实现通常可以让 `indirect<T>` 与一个指针一样大。

## 构造 [indirect.ctor]

¶2 所有构造函数除非 `allocate` 或 `construct` 抛出，否则不抛出。

| 构造函数 | 要求 | 效果 |
|---|---|---|
| `indirect()`（¶3–¶5） | *Constraints*：分配器可默认构造；*Mandates*：`T` 可默认构造 | 值初始化地构造一个 `T` |
| `indirect(allocator_arg_t, a)`（¶6–¶7） | *Mandates*：`T` 可默认构造 | 同上，使用 `a` |
| 复制构造（¶8–¶9） | *Mandates*：`T` 可复制构造 | 分配器取 `select_on_container_copy_construction(other.alloc)`；`other` 无值则结果无值，否则复制 `*other` |
| 带分配器的复制（¶10–¶11） | 同上 | 使用给定的 `a` |
| 移动构造，`noexcept`（¶12–¶13） | 无 | 移动分配器，接管 `other` 的指针；之后 `other` 无值 |
| 带分配器的移动（¶14–¶16） | *Mandates*：`is_always_equal` 为假时 `T` 完整 | 分配器相等则接管指针，否则用 `*std::move(other)` 构造新对象；之后 `other` 无值 |
| `indirect(U&& u)`（¶17–¶20） | *Constraints*：`U` 不是 `indirect` 或 `in_place_t`，`is_constructible_v<T, U>` | 用 `std::forward<U>(u)` 构造 |
| `indirect(in_place_t, us...)`（¶21–¶24） | *Constraints*：`is_constructible_v<T, Us...>` | 就地构造 |
| `indirect(in_place_t, ilist, us...)`（¶25–¶28） | *Constraints*：`is_constructible_v<T, initializer_list<I>&, Us...>` | 就地构造 |

¶3–¶5 默认构造会分配内存并构造 `T`，这与默认为空的 `unique_ptr` 不同。

除了复制和移动，所有构造函数都是 `explicit` 的，包括默认构造函数。`indirect<std::string> s = "hi";` 不行，要写 `indirect<std::string> s("hi");`，这样就不会有看不见的堆分配。

!!! lawyer "explicit 默认构造函数与聚合初始化"
    聚合体中没有显式初始化、也没有默认成员初始化器的成员，按 [[dcl.init.aggr]] 从空初始化列表复制初始化，而复制列表初始化不能选中 `explicit` 构造函数。所以 `struct A { std::indirect<int> p; int x; }; A a{};` 和 `A b{.x = 1};` 都是非良构的，`A a;` 则可以。本机用一个带 `explicit` 默认构造函数的替身类验证，Clang 23 报告 `chosen constructor is explicit in copy-initialization`。给成员写上默认成员初始化器，如 `std::indirect<int> p{};`，就没有这个问题。

¶8 复制构造函数对 `T` 的要求是 *Mandates*，而不是 *Constraints*。*Constraints* 要在重载决议时检查 `T`，那时 `T` 可能还不完整；*Mandates* 只在函数真正实例化时检查。代价是对不可复制的 `T`，`is_copy_constructible_v<indirect<T>>` 仍然为真，真正复制时才报错。

¶12 移动构造无条件 `noexcept`：它总是接管指针，`other` 变为无值。无值状态正是为此付出的代价。

推导指引 `indirect(Value) -> indirect<Value>`；`indirect(allocator_arg_t, Allocator, Value)` 推导出重绑定到 `Value` 的分配器。

## 析构 [indirect.dtor]

¶1 *Mandates*：`T` 是完整类型。¶2 如果不是无值，用 `allocator_traits::destroy` 销毁被拥有对象，再释放存储。和 `unique_ptr` 做 pimpl 时一样，外层类的析构函数要定义在 `Impl` 完整的地方。

## 赋值 [indirect.assign]

### 复制赋值（¶1–¶4）

¶1 *Mandates*：`T` 可复制赋值且可复制构造。¶2 自赋值时没有效果，否则：

- ¶2.1 如果 POCCA 为真，分配器需要更新。
- ¶2.2 `other` 无值：`*this` 也变为无值，原来的对象销毁并释放。
- ¶2.3 否则，如果两个分配器相等且 `*this` 不是无值：等价于 `**this = *other`，直接对被拥有对象做复制赋值，复用已有的存储。
- ¶2.4 否则，用 `*this` 的分配器（需要更新时用 `other` 的）构造一个新对象作为 `*other` 的副本。
- ¶2.5、¶2.6 销毁并释放原来的对象，需要更新时替换分配器。

¶4 抛出异常时，`valueless_after_move()` 的结果不变。异常来自 `T` 的复制构造函数时没有效果；来自 `T` 的复制赋值时，被拥有对象的状态取决于 `T` 的复制赋值本身的异常安全保证。

这是一个折中：能复用存储时直接赋值，速度快，但只有 `T` 的赋值运算符本身的保证；不能复用时先构造新对象再销毁旧对象，给出强异常保证。

### 移动赋值（¶5–¶9）

`noexcept(POCMA || is_always_equal)`。¶5 POCMA 和 `is_always_equal` 都为假时，*Mandates* 要求 `T` 可移动构造，因为分配器不等时只能构造一个新对象（[[LWG4251]] 把这条要求从可复制构造放宽为可移动构造）。

- ¶6.3 分配器需要更新或两者相等时，`*this` 接管 `other` 的被拥有对象。
- ¶6.4 否则，用 `*this` 的分配器，以 `other` 的被拥有对象为右值构造一个新对象。

¶7 无论走哪条路，赋值之后 `other` 都是无值的。¶9 抛出异常时 `*this` 和 `other` 都没有变化。

### 从值赋值（¶10–¶12）

`template<class U = T> indirect& operator=(U&& u)`：¶10 *Constraints* 要求 `U` 不是 `indirect`，`T` 可以从 `U` 构造也可以从 `U` 赋值。¶11 `*this` 无值时用 `u` 构造一个新对象，否则等价于 `**this = std::forward<U>(u)`。让一个无值对象重新有值，可以用它，也可以赋给它另一个有值的 `indirect`。

## 观察器 [indirect.obs]

```cpp
constexpr const T&  operator*() const &  noexcept;
constexpr T&        operator*() &        noexcept;
constexpr const T&& operator*() const && noexcept;
constexpr T&&       operator*() &&       noexcept;
constexpr const_pointer operator->() const noexcept;
constexpr pointer       operator->() noexcept;
```

`const indirect<T>` 的 `operator*` 返回 `const T&`，`operator->` 返回 `const_pointer`，这就是 `const` 传播。¶3–¶4 右值 `indirect` 解引用得到 `T&&`，所以 `auto x = *std::move(ind);` 会移动被拥有对象，`ind` 本身仍然有值，只是对象处于被移动后的状态。

¶1、¶3、¶5 解引用的前置条件是 `*this` 不是无值，违反它是 UB。¶7 `valueless_after_move()` 查询是否无值，¶8 `get_allocator()` 返回 *alloc*。

## 交换 [indirect.swap]

`noexcept(POCS || is_always_equal)`。¶1 前置条件：POCS 为真时分配器可交换，否则两个分配器必须相等。与容器一样，分配器不相等又不传播时交换是 UB。¶2 交换的是两个对象的状态，即被拥有对象的指针或无值状态；注 1 指出不会对被拥有对象调用 `swap`。

## 比较与散列 [indirect.relops] [indirect.comp.with.t] [indirect.hash]

`indirect` 按值比较：

- [indirect.relops] ¶1–¶2 两个 `indirect` 的 `==`：任一方无值时，返回两者是否都无值；否则返回 `*lhs == *rhs`。*Mandates* 要求 `*lhs == *rhs` 良构且可转换为 `bool`。
- ¶3 `<=>`：任一方无值时返回 `!lhs.valueless_after_move() <=> !rhs.valueless_after_move()`，即无值者小于有值者；否则返回 *synth-three-way*`(*lhs, *rhs)`。*synth-three-way* 在 `T` 只有 `<` 时也能工作（[[expr.spaceship]]）。
- [indirect.comp.with.t] 与一个 `T` 的值比较：`lhs` 无值时 `==` 为 `false`，`<=>` 为 `strong_ordering::less`。

[indirect.hash] ¶1 `hash<indirect<T, Allocator>>` 当且仅当 `hash<T>` 启用时启用。有值时结果等于 `hash<T>()(*i)`，无值时是一个由实现定义的值。成员函数不保证是 `noexcept`。

## 思考题

!!! question "思考题 1"
    `indirect` 的移动赋值在分配器不等时要构造一个新对象，`other` 的对象其实还在。为什么后置条件仍然规定 `other` 无值？

<details markdown="1">
<summary>答案</summary>

为了让结果与分配器无关。如果副本路径上保留 `other` 的对象，调用者看到的状态就取决于两个分配器是否相等，这是一个运行期才知道的条件。统一置为无值，调用者总是看到同一个结果，同时也释放了 `other` 占用的存储。
</details>

!!! question "思考题 2"
    `std::is_copy_constructible_v<std::indirect<std::unique_ptr<int>>>` 是什么？

<details markdown="1">
<summary>答案</summary>

`true`。复制构造函数没有 *Constraints*，只有 *Mandates*（¶8），所以它参与重载决议，特征检测报告可以复制；真正实例化复制构造函数时才因为 *Mandates* 不满足而非良构。这是支持不完整 `T` 的代价，`std::vector<std::unique_ptr<int>>` 的特征检测也有同样的现象。
</details>

## 小结

- `indirect<T>` 是堆上的 `T` 加上值语义：复制 `T`、按值比较和散列、`const` 与值类别都会传播。
- 默认构造会分配并构造 `T`；没有空状态，只有被移动后的无值状态。
- 复制赋值在能复用存储时直接赋值，否则先构造后销毁；移动赋值在分配器相等或传播时接管指针，之后源对象总是无值。
- 比较时无值对象最小，两个无值对象相等。
- 许多要求是 *Mandates* 而不是 *Constraints*，以支持不完整类型。
