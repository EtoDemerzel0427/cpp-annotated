---
title: indirect
summary: C++26 的 indirect<T>：堆上存放一个 T、却拥有 T 的值语义——深拷贝、const 传播、按值比较与散列；只有被移动后才可能无值；构造、赋值与分配器传播的逐段规则
status: done
covers: *
since: c++26
related: mem.composite.types, polymorphic, allocator.traits, allocator.uses, unique.ptr, expr.spaceship
tags: 标准库, indirect, 值语义, C++26, 分配器
papers: P3019R14
updated: 2026-10-18
---

`indirect<T, Allocator = allocator<T>>` 是一个"放在堆上的 `T`"。设计动机见 [[mem.composite.types]]。本页逐段解读 [indirect] 的全部子条款。

## 概述（[indirect.general]）

- ¶1：`indirect` 对象管理一个**被拥有对象**的生命周期。没有被拥有对象时称为**无值**（valueless，[[g:valueless]]）；**只有被移动之后**才可能变为无值。
- ¶2：`allocator_traits<Allocator>::value_type` 必须与 `T` 相同，否则 {{ill-formed}}；对象使用 `Allocator` 分配和释放被拥有对象的存储。
- ¶3：用 `args...` 以分配器 `a` "构造被拥有对象"，指调用 `allocator_traits<Allocator>::construct(a, p, args...)`，其中 `p` 来自 `allocator_traits<Allocator>::allocate`。因此 `pmr::indirect<T>` 会对 `T` 做 uses-allocator 构造（[[allocator.uses]]）。
- ¶4：成员 *alloc* 只能通过赋值或 `swap` 被替换，规则与容器相同（POCCA/POCMA/POCS，[[allocator.traits]]）。
- ¶5：`T` 不能是非对象类型、数组、`in_place_t`、`in_place_type_t` 的特化或 cv 限定类型。
- ¶6：**`T` 可以是不完整类型**。¶7：`Allocator` 须满足 *Cpp17Allocator*。¶8：显式或偏特化 `indirect` 是 {{ub}}。

说明用的数据成员只有两个：`pointer p` 与 `Allocator alloc`。所以对 `std::allocator`，`sizeof(indirect<T>) == sizeof(T*)`（实现可以对空分配器做空基优化）。

## 构造（[indirect.ctor]）

¶2：所有构造函数除非 `allocate` 或 `construct` 抛出，否则不抛出。

| 构造函数 | 约束 / Mandates | 效果 |
|---|---|---|
| `indirect()`（¶3–¶5） | *Constraints* 分配器可默认构造；*Mandates* `T` 可默认构造 | 值初始化地构造一个 `T`——**不是**空的 |
| `indirect(allocator_arg_t, a)`（¶6–¶7） | *Mandates* `T` 可默认构造 | 同上，用 `a` |
| 复制 `indirect(const indirect&)`（¶8–¶9） | *Mandates* `T` 可复制构造 | *alloc* 取 `select_on_container_copy_construction(other.alloc)`；`other` 无值则 `*this` 无值，否则用 `*other` 复制构造 |
| 带分配器的复制（¶10–¶11） | 同上 | 用给定的 `a` |
| 移动 `indirect(indirect&&) noexcept`（¶12–¶13） | — | 移动分配器，**偷走**指针；后置条件：`other` 无值 |
| 带分配器的移动（¶14–¶16） | *Mandates* `is_always_equal` 为假时 `T` 完整 | 分配器相等则偷指针，否则用 `*std::move(other)` 构造新对象；`noexcept(is_always_equal)`；后置条件：`other` 无值 |
| `indirect(U&& u)`（¶17–¶18） | *Constraints* `U` 不是 `indirect` 或 `in_place_t`、`is_constructible_v<T, U>` | 用 `std::forward<U>(u)` 构造 |
| `indirect(in_place_t, us...)`（¶21–¶22） | `is_constructible_v<T, Us...>` | 就地构造 |
| `initializer_list` 版本（¶25–¶28） | `is_constructible_v<T, initializer_list<I>&, Us...>` | 就地构造 |

几个值得注意的点：

- **默认构造会分配。** `indirect<T>` 没有"空"的默认状态，默认构造必然调用 `allocate` 与 `T` 的默认构造函数。这与 `unique_ptr` 默认为空截然不同。
- 所有带实参的构造函数都是 `explicit`——`indirect<std::string> s = "hi";` 不行，要写 `indirect<std::string> s("hi");`。这避免了"一次看不见的堆分配"。
- **复制构造函数的 *Mandates***：`is_copy_constructible_v<T>` 是 *Mandates* 而不是 *Constraints*——所以对不可复制的 `T`，`is_copy_constructible_v<indirect<T>>` 仍然为 **true**（复制构造函数被声明了），真正调用时才报错。这是为了支持不完整类型：*Constraints* 要在重载决议时检查 `T`，那时 `T` 可能还不完整。
- 移动构造是无条件 `noexcept` 的：它总是偷指针，`other` 变为无值。代价就是"无值"状态的存在。

推导指引：`indirect(Value) -> indirect<Value>`；`indirect(allocator_arg_t, Allocator, Value)` 推导出重绑定到 `Value` 的分配器。

## 析构（[indirect.dtor]）

¶1 *Mandates*：`T` 是完整类型。¶2：若非无值，用 `allocator_traits::destroy` 销毁被拥有对象，再释放存储。

和 `unique_ptr` 一样，pimpl 中要在 `Impl` 完整的地方定义外层类的析构函数。

## 赋值（[indirect.assign]）

### 复制赋值（¶1–¶4）

*Mandates*：`T` 可复制赋值且可复制构造。若 `addressof(other) == this`，无效果。否则：

- (2.1) 若 POCCA 为真，分配器"需要更新"；
- (2.2) `other` 无值：`*this` 变为无值，原有对象被销毁、释放；
- (2.3) 否则，若 `alloc == other.alloc` 且 `*this` 不是无值：等价于 `**this = *other`——**直接对被拥有对象做复制赋值**，复用已有存储；
- (2.4) 否则，用 `allocator_traits::construct` 以 `*other` 构造一个**新**对象（使用 `*this` 的分配器，或在需要更新时使用 `other` 的分配器）；
- (2.5) 旧对象（若有）销毁并释放；(2.6) 需要更新时替换分配器。

¶4 *Remarks*：若抛出异常，`valueless_after_move()` 的结果不变；`T` 的复制构造函数抛出时无效果；`T` 的复制赋值抛出时，被拥有对象的状态取决于 `T` 自己的复制赋值的异常安全保证。

这是一个精心的折中：能复用存储时就做 `T` 的赋值（快，但只有 `T` 赋值本身的异常保证），不能复用时就"先构造新的、再销毁旧的"（强异常保证）。

### 移动赋值（¶5–¶9）

`noexcept(POCMA || is_always_equal)`。*Mandates*：若 POCMA 与 `is_always_equal` 都为假，`T` 可移动构造——在分配器不等时只能逐个移动构造（这条 *Mandates* 由 [[LWG4251]] 从"可复制构造"放宽为"可移动构造"）。

- (6.3) 若分配器需要更新或二者相等：`*this` **接管** `other` 的被拥有对象；
- (6.4) 否则：用 `*this` 的分配器，以 `other` 的被拥有对象作右值构造一个新对象；
- ¶7 后置条件：`other` 无值——**即使**走的是 (6.4) 的"构造副本"路径，`other` 也被置为无值（它的对象被销毁、释放）。
- ¶9：抛出异常时 `*this` 与 `other` 都无效果。

### 从值赋值（¶10–¶12）

`template<class U = T> indirect& operator=(U&& u)`：*Constraints* `U` 不是 `indirect`、`T` 可从 `U` 构造且可从 `U` 赋值。`*this` 无值时用 `u` 构造新对象（这是**唯一能让无值对象重新获得值**的途径之一，另一个是被赋值另一个有值的 `indirect`）；否则等价于 `**this = std::forward<U>(u)`。

## 观察器（[indirect.obs]）

```cpp
constexpr const T&  operator*() const &  noexcept;
constexpr T&        operator*() &        noexcept;
constexpr const T&& operator*() const && noexcept;
constexpr T&&       operator*() &&       noexcept;
constexpr const_pointer operator->() const noexcept;
constexpr pointer       operator->() noexcept;
constexpr bool valueless_after_move() const noexcept;
constexpr allocator_type get_allocator() const noexcept;
```

- **const 传播**：`const indirect<T>` 的 `operator*` 返回 `const T&`，`operator->` 返回 `const_pointer`。这是相对 `unique_ptr` 的核心改进。
- **值类别传播**：右值 `indirect` 解引用得到 `T&&`，所以 `auto x = *std::move(ind);` 会移动被拥有对象（`indirect` 仍有值，只是对象处于被移动后的状态）。
- 前置条件（¶1、¶3、¶5）：`*this` 不是无值。这是普通前置条件，违反是 {{ub}}。

## 交换（[indirect.swap]）

`noexcept(POCS || is_always_equal)`。¶1 前置条件：POCS 为真时分配器可交换；**否则 `get_allocator() == other.get_allocator()`**——与容器相同，分配器不等且不传播时交换是 {{ub}}。¶2：交换状态（被拥有对象或无值状态），注 1：**不**对被拥有对象调用 `swap`——只交换指针。

## 比较（[indirect.relops]、[indirect.comp.with.t]）

`indirect` 按**值**比较：

- `lhs == rhs`（`indirect<U, AA>` 与 `indirect<T, A>` 之间）：任一方无值时返回 `lhs.valueless_after_move() == rhs.valueless_after_move()`（两个无值对象相等）；否则 `*lhs == *rhs`。*Mandates* `*lhs == *rhs` 良构且可转换为 `bool`。[[LWG4325]] 使其对不完整类型也可用（`noexcept` 规格与返回类型推迟计算）。
- `lhs <=> rhs`：任一方无值时返回 `!lhs.valueless_after_move() <=> !rhs.valueless_after_move()`——**无值者小于有值者**；否则 *synth-three-way*`(*lhs, *rhs)`（[[expr.spaceship]] 意义下的合成三路比较，`T` 只有 `<` 也行）。
- 与 `T` 比较：`lhs == rhs` 在 `lhs` 无值时为 `false`；`lhs <=> rhs` 在 `lhs` 无值时为 `strong_ordering::less`。

## 散列（[indirect.hash]）

`hash<indirect<T, Allocator>>` 当且仅当 `hash<T>` 启用时启用；有值时等于 `hash<T>()(*i)`，无值时是一个由实现定义的值。成员函数不保证 `noexcept`。

## 示例

```cpp title="indirect-pimpl.cpp" ok
#include <memory>
#include <string>
#include <vector>
#include <cassert>

struct Expr;                                    // 递归类型：Expr 里有 Expr
struct Binary { char op; std::indirect<Expr> lhs, rhs; };
struct Expr {
    std::string name;
    std::vector<Binary> children;
};

struct Widget {
    std::indirect<std::string> name{"widget"};
    void rename(const char* s) { *name = s; }
    std::size_t len() const { return name->size(); }   // const 成员函数里 name-> 是 const std::string*
    // *name = "x";                                     // 若在 const 成员函数中写：error，const 传播
};

int main() {
    Widget a;
    Widget b = a;                                 // 隐式复制构造：深拷贝
    b.rename("other");
    assert(*a.name == "widget" && *b.name == "other");
    Widget c = std::move(a);
    assert(a.name.valueless_after_move());        // 被移动后无值
    a.name = std::string("revived");              // 从值赋值：重新获得值
    assert(a.name == std::string("revived"));     // 与 T 比较
}
```

（本机 libc++ 尚未实现 `std::indirect`，此例未在本地编译验证。）

## 思考题

<details markdown="1">
<summary>1. 为什么 `indirect` 的移动赋值后置条件是"`other` 无值"，即使在分配器不等、只能构造副本的路径上也是如此？</summary>

为了让语义与分配器无关：无论走哪条路径，调用者看到的都是"`other` 被移空"。若在副本路径上保留 `other` 的对象（只是移动后的状态），用户代码就会因分配器是否相等这一运行期因素而观察到不同的状态。统一置为无值也释放了 `other` 占用的存储。
</details>

<details markdown="1">
<summary>2. `std::is_copy_constructible_v<std::indirect<std::unique_ptr<int>>>` 是什么？</summary>

`true`。复制构造函数没有 *Constraints*，只有 *Mandates*（¶8），所以它参与重载决议、特征检测报告可复制；真正实例化复制构造函数时才因 *Mandates* 不满足而 {{ill-formed}}。这是为支持不完整 `T` 付出的代价（类似 `std::vector<T>` 对不可复制 `T` 的特征检测结果）。
</details>

## 小结

- `indirect<T>` = 堆上的 `T` + 值语义：深拷贝、按值比较与散列、const 与值类别传播。
- 默认构造会分配并构造 `T`；没有空状态，只有"移动后无值"。
- 复制赋值在能复用存储时直接赋值，否则先构造后销毁；移动赋值在分配器相等或传播时偷指针。
- 比较中无值对象最小、两个无值对象相等。
- 许多要求是 *Mandates* 而非 *Constraints*，以支持不完整类型。
