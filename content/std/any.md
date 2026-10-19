---
title: 可存放任意类型的 any
summary: std::any 能装任何可复制构造的值并记住它的类型；本页讲存入时的 decay 与可复制要求、any_cast 的各种形式和失败方式、赋值的异常保证、小对象优化的限制，以及 libc++ 的实现。
status: done
covers: *
papers: P0220R1
related: variant, optional, func.wrap.func, func.wrap.move, func.wrap.copy, expr.typeid, structure.specifications, utility.arg.requirements, utilities
tags: 标准库, any, 类型擦除, 小对象优化
updated: 2026-10-19
---

!!! tldr
    - `std::any` 能装任何可复制构造的值，并记住它的类型；取值时必须用 `any_cast` 写出精确的类型，`any_cast<long>` 取不出 `int`。
    - 存入的类型是 `decay_t<T>`：字符串字面量存成 `const char*`，数组存成指针，`any` 不能装引用。
    - 只能移动的类型（如 `unique_ptr`）放不进 `any`，因为 `any` 自己必须可复制，复制时要复制所含值。
    - 引用形式的 `any_cast` 类型不符时抛 `bad_any_cast`，指针形式返回 `nullptr`。
    - 标准建议小对象不做动态分配，但这种优化只能用于移动构造不抛异常的类型，否则 `any` 的移动和 `swap` 无法保证 `noexcept`。

## any 是什么

```cpp run title="any-cast.cpp" ok
#include <any>
#include <cassert>
#include <string>

int main() {
  std::any x = 5;                       // 持有 int
  assert(std::any_cast<int>(x) == 5);   // 取出副本
  std::any_cast<int&>(x) = 10;          // 取出引用，原地修改
  assert(std::any_cast<int>(x) == 10);

  try {
    (void)std::any_cast<long>(x);       // int ≠ long
    assert(false);
  } catch (const std::bad_any_cast&) {}

  assert(std::any_cast<long>(&x) == nullptr);  // 指针形式不抛异常

  x = "Meow";                           // 存的是 const char*
  assert(x.type() == typeid(const char*));

  x.reset();
  assert(!x.has_value() && x.type() == typeid(void));
}
```

`std::any` 是一个能装任何可复制类型的值的容器，而且记得那个值是什么类型。[any.general] 的注 1 说明了它的设计意图：它可以装不同类型的值，但不在它们之间做转换，`5` 就严格地是 `int`，既不会变成 `"5"`，也不会变成 `5.0`。存进去的是什么类型，取出来就必须写什么类型。

`any` 是**类型擦除**（[[g:type-erasure]]）的典型例子：`any` 这个类型本身不带所含值的类型，复制、销毁、按类型取回这些操作都在运行时通过间接调用完成。`std::function`（[[func.wrap.func]]）用的是同一种技术。

它和 [[variant]] 都能装不同类型的值，但取舍相反：

| | `variant<Ts...>` | `any` |
|---|---|---|
| 能存哪些类型 | 编译期固定的 `Ts...` | 任何可复制构造的对象类型 |
| 存储 | 在对象内部，不允许堆分配 | 可以堆分配；小对象最好放在内部缓冲区 |
| 取值 | `get`、`visit`，编译器能检查是否穷尽 | `any_cast`，必须说出精确类型 |
| 类型信息 | 编译期的下标 | 运行时的 `type_info` |

¶1 [any.class.general] 把 `any` 是否有值、有值时是什么值，统称为它的**状态**；存放的那个实例叫**所含值**（contained value）。两个状态等价，是指都没有值，或者都有值且所含值等价。

## 存入：decay 与可复制

### 转换构造

¶5 [any.cons] 的转换构造 `template<class T> any(T&& value)` 先令 `VT` 为 `decay_t<T>`，存进去的是一个用 `std::forward<T>(value)` 直接初始化的 `VT` 对象（第 8 段）。`decay_t` 带来几个后果：

- `any a = "Meow";` 存的是 `const char*`，不是 `const char[5]`；
- 数组变成指针，函数变成函数指针；
- 存进去的永远是非引用、非 cv 的对象类型，`any` 不能装引用。

¶6 约束是 `VT` 不是 `any`，不是 `in_place_type_t` 的特化，并且 `is_copy_constructible_v<VT>` 为真。¶7 前提条件是 `VT` 满足 *Cpp17CopyConstructible*（[[utility.arg.requirements]]）。这两层要求分属不同的规格元素（[[structure.specifications]]）：

| 元素 | 内容 | 不满足时 |
|---|---|---|
| *Constraints* | 语法上能复制构造 | 构造函数不参与重载决议，`is_constructible_v<any, VT>` 为假 |
| *Preconditions* | 语义上复制得到等价的值，且不修改源对象 | 未定义行为 |

所以把 `unique_ptr` 放进 `any` 是没有可行转换的编译错误，构造函数直接从重载集中消失，而不是触发某个 `static_assert`：

```cpp run title="any-move-only.cpp" error
#include <any>
#include <memory>

std::any a = std::make_unique<int>(1);  // error: unique_ptr 不可复制
```

排除 `in_place_type_t` 是为了让 `any(std::in_place_type<int>)` 这样的调用走下面的 `in_place` 构造，而不是把标签对象本身存进去。转换构造不是 `explicit` 的，任何可复制的值都能隐式变成 `any`，这在 `any` 作函数形参时是个陷阱（见常见误解）。

### 原地构造与 make_any

¶10 `explicit any(in_place_type_t<T>, Args&&...)` 用 `args...` 直接非列表初始化一个 `VT`，约束是 `VT` 可复制构造且能从 `Args...` 构造。¶16 还有一个以 `initializer_list<U>` 开头的版本。它们适合需要多个构造实参的类型，或者能复制但不能移动的类型，不必先构造一个临时量再搬进去。

[any.nonmembers]/2 `make_any<T>(args...)` 等价于 `any(in_place_type<T>, std::forward<Args>(args)...)`，第 3 段是 `initializer_list` 版本。`make_any` 的好处是能写 `std::make_any<std::vector<int>>({1, 2, 3})`：`T` 显式给出，`initializer_list<U>` 中的 `U` 由推导得到。

[any.modifiers]/4 `emplace<T>(args...)` 先调用 `reset()`，再就地构造，返回新值的引用；约束与 `in_place` 构造相同。

```cpp run title="any-construct.cpp" ok
#include <any>
#include <cassert>
#include <complex>
#include <type_traits>
#include <vector>

struct Throws { Throws() { throw 1; } };

int main() {
  auto a = std::make_any<std::complex<double>>(1.0, 2.0);
  auto b = std::make_any<std::vector<int>>({1, 2, 3});
  assert(std::any_cast<std::vector<int>&>(b).size() == 3);

  std::any c(std::in_place_type<std::vector<int>>, 5, 42);
  assert(std::any_cast<const std::vector<int>&>(c)[4] == 42);

  auto& v = c.emplace<std::vector<int>>(2u, 7);  // 返回新值的引用
  v.push_back(8);
  assert(std::any_cast<std::vector<int>&>(c).size() == 3);

  try { a.emplace<Throws>(); } catch (int) {}
  assert(!a.has_value());  // 构造抛出后 any 一定为空

  static_assert(std::is_nothrow_move_constructible_v<std::any>);
}
```

### 为什么必须可复制

`any` 本身是可复制的类型，`any b = a;` 必须能工作。类型被擦除之后，复制 `any` 只能调用存入时记下的复制函数，而这个函数在存入的那一刻就要实例化。如果允许存入 `unique_ptr`，就只剩两种选择：

1. 复制 `any` 时在运行时发现所含值不可复制，然后抛异常。本可在编译期发现的错误被推迟到运行时，"`any` 可复制"这个类型性质也变得不可信。
2. `any` 自己不可复制。那它就不能像普通的值一样复制、按值传递，失去了意义。

标准选择在入口处拒绝：转换构造、`in_place` 构造、转换赋值、`emplace` 都带 `is_copy_constructible_v<VT>` 的约束。`std::function` 要求可调用对象可复制，原因相同；这个限制后来催生了只能移动的 `std::move_only_function`（C++23，[[func.wrap.move]]），而 `any` 至今没有标准的只移动版本。需要存只能移动的对象时，常见做法是用 `std::shared_ptr<T>` 包一层，复制的是共享所有权。

## 取值：any_cast

### 引用形式

[any.nonmembers]/4 按引用接受 `any` 的三个重载是：

```cpp
template<class T> T any_cast(const any& operand);
template<class T> T any_cast(any& operand);
template<class T> T any_cast(any&& operand);
```

设 `U` 为 `remove_cvref_t<T>`。¶6 它们返回 `static_cast<T>(*any_cast<U>(&operand))`，第三个重载先 `std::move` 再转换，也就是说内部调用指针形式再解引用。¶7 如果 `operand.type() != typeid(remove_reference_t<T>)`，抛 `bad_any_cast`。

`T` 决定怎样取：`any_cast<int>` 复制出一个 `int`；`any_cast<int&>` 返回所含值的左值引用，可以原地修改；`any_cast<const int&>` 返回只读引用；`any_cast<std::string&&>(std::move(a))` 把所含值作为右值交出来，便于移走。

¶5 还有一条 *Mandates*：三个重载分别要求 `is_constructible_v<T, const U&>`、`is_constructible_v<T, U&>`、`is_constructible_v<T, U>`。这是 const 正确性检查：从 `const any&` 取不出 `U&`，从左值 `any&` 取不出 `U&&`。它是 *Mandates* 而不是 *Constraints*：三个重载靠 `operand` 的值类别区分，`T` 写错了不会换另一个重载顶上，而是直接报错。

<div class="compare" markdown="1">

```cpp error
#include <any>
#include <string>
int main() {
  const std::any y = std::string("cat");
  // 不能用 any_cast 去掉 const
  std::any_cast<std::string&>(y);  // error
}
```

```cpp error
#include <any>
int main() {
  std::any a = 1;
  // 指针形式：T 不能是 void
  return std::any_cast<void>(&a)
         != nullptr;  // error
}
```

</div>

运行时检查用的是 `typeid(remove_reference_t<T>)`。`typeid` 忽略顶层 cv（[[expr.typeid]]），所以 `any_cast<const int&>` 能取出 `int`。没有值时 `type()` 是 `typeid(void)`，与任何对象类型都不相等，同样抛 `bad_any_cast`。

```cpp run title="any-move-out.cpp" ok
#include <any>
#include <cassert>
#include <string>

int main() {
  std::any x = std::string("Meow");
  std::string s = std::any_cast<std::string&&>(std::move(x));
  assert(s == "Meow");
  assert(x.has_value());  // 被移走的 string 仍然留在 any 里
}
```

移走之后，`any` 里还有一个处于有效但未指定状态的 `string`，`any` 本身并没有变空。

### 指针形式

[any.nonmembers]/9 按指针接受 `any` 的两个重载：

```cpp
template<class T> const T* any_cast(const any* operand) noexcept;
template<class T> T* any_cast(any* operand) noexcept;
```

`T` 不能是 `void`（*Mandates*）。¶10 如果 `operand` 非空且 `operand->type() == typeid(T)`，返回指向所含值的指针，否则返回 `nullptr`。标准的例 2 用它判断类型：`any_cast<string>(&operand) != nullptr`。

指针形式从不抛异常：空指针、没有值、类型不符都用 `nullptr` 报告。这和 `dynamic_cast` 的两种失败方式一样（指针形式得到 `nullptr`，引用形式抛 `bad_cast`），也和 variant 的 `get_if`、`get` 对应。

### bad_any_cast

[any.bad.any.cast] 的 `bad_any_cast` 公开继承 `bad_cast`，而不是直接继承 `exception`。它和 `dynamic_cast` 引用转换失败时抛的 `bad_cast` 同族，都表示运行时类型检查失败；`catch (const std::bad_cast&)` 能同时接住两者。

## 观察与重置

[any.observers]/1 `has_value()` 在有所含值时返回 `true`。第 2 段 `type()` 有值时返回 `typeid(T)`，没有值时返回 `typeid(void)`。

`type()` 依赖 RTTI。在 `-fno-rtti` 下 libc++ 不提供 `type()`，但 `any_cast` 仍然可用：它改用每个类型一个静态变量的地址作为类型标识。

[any.modifiers]/17 `reset()` 销毁所含值（如果有），之后 `has_value()` 为假。析构函数的效果如同 `reset()`（[any.cons]/22）。

## 复制、移动与赋值的异常保证

[any.cons]/2 复制构造在源对象有值时，等价于 `any(in_place_type<T>, any_cast<const T&>(other))`，可能分配内存，可能抛出 `T` 的复制构造抛出的异常。

¶4 移动构造是 `noexcept` 的。源对象有值时，新对象要么直接接管源对象的所含值，要么含有一个从该值（作为右值）移动构造出的同类型对象。这两种说法分别对应值在堆上和值在内部缓冲区的情况。标准没有规定移动之后源对象的状态：它可能为空，也可能仍有一个被移动过的值。libc++ 两种情况下都把源对象置空，但可移植的代码不能依赖这一点。

[any.assign] 的三种赋值都是先构造、再交换：

| 运算 | 效果 | 异常保证 |
|---|---|---|
| `operator=(const any& rhs)`（¶1–3） | 如同 `any(rhs).swap(*this)` | 抛出异常时没有效果 |
| `operator=(any&& rhs) noexcept`（¶4–6） | 如同 `any(std::move(rhs)).swap(*this)` | `*this` 的状态等价于 `rhs` 原来的状态 |
| `template<class T> operator=(T&& rhs)`（¶7–12） | 构造一个持有 `VT` 的临时 `any`，再与 `*this` 交换 | 抛出异常时没有效果 |

新值先完整地构造在临时对象里，再用不会抛出的 `swap` 交换。这和 variant 的赋值形成对比：variant 不能堆分配，先构造临时值需要额外的条件，所以可能失去值；`any` 可以随时在堆上构造临时值，赋值总有强异常保证。

`emplace` 则相反。[any.modifiers]/8 规定构造函数抛出时 `*this` 不含值，原来的所含值也已经销毁。这是确定的结果，不像 `variant::emplace` 那样只是允许不持有值。放弃强保证换来的是就地构造，不需要临时对象。

## 小对象优化

[any.class.general]/3 是全节最有工程意义的一段：

!!! std
    Implementations should avoid the use of dynamically allocated memory for a small contained value. However, any such small-object optimization shall only be applied to types `T` for which `is_nothrow_move_constructible_v<T>` is `true`.

第一句用的是 should，只是建议：标准没有定义多小算小，实现完全不做**小对象优化**（[[g:small-object-optimization]]，把小的值直接放在对象内部的缓冲区里）也符合标准。第二句用的是 shall，是硬性要求：移动构造可能抛出的类型不得放进内部缓冲区，不管它多小。

第二句的原因是 `any` 的移动构造、移动赋值和 `swap` 都是 `noexcept` 的。值在堆上时，移动 `any` 只是转移指针，不会抛出；值在内部缓冲区时，移动 `any` 必须真的移动构造一个 `T`，这一步如果会抛出，`noexcept` 就无法兑现。所以移动可能抛出的类型只能放在堆上。标准的例 1 说，`int` 可以放在内部缓冲区里。

在 libc++ 上可以直接看到这几种情况：

```cpp run title="any-sbo.cpp" ok
#include <any>
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Small { void* p[3]; };  // 24 字节，移动不抛出
struct Big { void* p[4]; };    // 32 字节
struct Throwing {              // 1 字节，但移动可能抛出
  Throwing() = default;
  Throwing(const Throwing&) {}
  Throwing(Throwing&&) noexcept(false) {}
};

template<class T>
int count() {
  int before = allocs;
  std::any a = T{};
  return allocs - before;
}

int main() {
  std::printf("sizeof(any)=%zu\n", sizeof(std::any));
  std::printf("int:%d Small:%d Big:%d Throwing:%d\n",
              count<int>(), count<Small>(), count<Big>(), count<Throwing>());
}
```

本机（arm64 macOS，libc++ 23）输出 `sizeof(any)=32` 和 `int:0 Small:0 Big:1 Throwing:1`。`Throwing` 只有 1 字节，却因为移动构造不是 `noexcept` 而只能堆分配。缓冲区的大小是实现细节，libstdc++ 和 MSVC 各不相同，不要依赖。

## libc++ 的实现

以下基于本机 libc++ 23 的 `<any>`。

`any` 由一个函数指针和一块联合体存储组成：

```cpp
// 简化自 libc++ <any>
class any {
  using _HandleFuncPtr = void* (*)(_Action, any const*, any*,
                                   const type_info*, const void*);
  union _Storage {
    void* __ptr;                                   // 大对象：指向堆
    alignas(void*) char __buf[3 * sizeof(void*)];  // 小对象：就地存放
  };
  _HandleFuncPtr __h_ = nullptr;                   // nullptr 表示没有值
  _Storage __s_;
};
```

64 位平台上 `sizeof(any) == 32`，`has_value()` 就是 `__h_ != nullptr`。

一个类型能放进缓冲区，要同时满足三个条件：`sizeof(T) <= 3 * sizeof(void*)`、`alignof(T) <= alignof(void*)`、`is_nothrow_move_constructible_v<T>`。第三个条件就是 [any.class.general]/3 的 shall。

每个类型 `T` 对应 `_SmallHandler<T>` 或 `_LargeHandler<T>` 的一个静态函数，用一个枚举（销毁、复制、移动、取值、取类型信息）分派操作。这相当于只有一项的手写虚表：每个 `any` 只多存一个函数指针，不需要虚表指针加堆上的多态对象。

移动时，大对象只是把 `__ptr` 抄给目标，再把源对象的 `__h_` 置空，对应 [any.cons]/4 的直接接管；小对象则在目标缓冲区里移动构造一个 `T`，再销毁源对象，对应从右值构造同类型对象。两种情况都使源对象为空。

`any_cast` 比较类型时，有 RTTI 就比较 `type_info`，没有 RTTI 就比较每个类型一个的静态变量的地址。对函数类型的 `T`，指针形式的 `any_cast` 直接返回 `nullptr`，因为 `any` 只能存函数指针，不可能存函数。大对象的构造先分配内存，构造抛出时释放，不会泄漏。

## 常见误解

!!! pitfall "以 any 作形参，类型检查就推迟到了运行时"
    `void set(std::string key, std::any value);` 能接受任何可复制的东西。`set("timeout", 30)` 存的是 `int`，读取方写 `any_cast<long>` 就会抛 `bad_any_cast`；`set("name", "bob")` 存的是 `const char*` 而不是 `std::string`，`any_cast<std::string>` 同样失败。存入方和读取方必须约定精确的类型，通常要配合 `in_place_type` 或显式构造（`std::string("bob")`）。

!!! pitfall "以为 any 能装引用或数组"
    `decay_t` 把数组变成指针、函数变成函数指针，并去掉引用和 cv。`int arr[3]; std::any a = arr;` 存的是 `int*`，一个可能悬空的指针，不是三个 `int` 的副本。

!!! pitfall "依赖被移动后的 any 为空"
    [any.cons]/4 没有规定被移动的 `any` 处于什么状态。libc++ 会把它置空，但标准允许它仍持有一个被移动过的值。需要空状态时，显式调用 `reset()`。

## 思考题

!!! question "思考题 1"
    `std::any a = 1;` 之后，`std::any_cast<int&&>(a)` 和 `std::any_cast<const int&&>(std::as_const(a))` 分别是什么结果？

<details markdown="1">
<summary>答案</summary>

都是编译错误。第一个：`a` 是非 const 左值，选中 `any_cast(any&)`，*Mandates* 要求 `is_constructible_v<int&&, int&>`，右值引用不能绑定到左值，为假。想要右值得写 `any_cast<int&&>(std::move(a))`，它选第三个重载，要求 `is_constructible_v<int&&, int>`，为真。

第二个选中 `any_cast(const any&)`，要求 `is_constructible_v<const int&&, const int&>`，同样是右值引用绑定左值，为假。*Mandates* 里的第二个类型（`const U&`、`U&`、`U`）刻画了从这个 `any` 能拿出什么值类别，`T` 只能在此基础上加 const 或者复制，不能凭空得到右值。
</details>

!!! question "思考题 2"
    一个实现完全不做小对象优化，所有值都堆分配，它符合标准吗？如果一个实现对所有 `sizeof(T) <= 16` 的类型都使用内部缓冲区呢？

<details markdown="1">
<summary>答案</summary>

前者符合：[any.class.general]/3 的第一句是 should，只是建议。后者不符合：第二句是 shall，`is_nothrow_move_constructible_v<T>` 为假的类型不得放进内部缓冲区，无论多小。违反这一条之后，`any(any&&) noexcept` 和 `swap` 都无法正确实现：移动 `any` 需要移动构造 `T`，`T` 抛出时只能调用 `std::terminate`。
</details>

## 小结

| 操作 | 要点 |
|---|---|
| 存入（转换构造、`in_place`、转换赋值、`emplace`） | 存的是 `decay_t<T>`；约束要求可复制构造；前提要求满足 *Cpp17CopyConstructible* |
| 小对象优化 | 建议（should）避免小对象的动态分配；只能（shall）用于移动不抛出的类型 |
| 复制构造、复制赋值 | 可能抛出；赋值是先构造再交换，有强异常保证 |
| 移动构造、移动赋值、`swap`、`reset` | `noexcept`；被移动的 `any` 状态未规定 |
| `emplace` | 先 `reset()` 再构造；构造抛出时 `*this` 一定为空 |
| `type()` | 有值时 `typeid(T)`，没有值时 `typeid(void)` |
| `any_cast<T>(any&)` 等引用形式 | *Mandates* 检查 const 正确性；类型不符抛 `bad_any_cast` |
| `any_cast<T>(any*)` 指针形式 | `T` 不能是 `void`；类型不符或空指针时返回 `nullptr` |
| `make_any<T>(args...)` | 等价于 `any(in_place_type<T>, args...)` |

<details class="fine" markdown="1"><summary>其余条文</summary>

[any.general]/1 只说这一节描述的组件用于对**可辨识类型**（discriminated type，[[g:discriminated-type]]）的对象进行操作，即能装不同类型的值并记住类型的类型。

[any.synop] 是头文件概要：`<any>` 包含 `<initializer_list>` 和 `<typeinfo>`，声明 `bad_any_cast`、`any`、非成员 `swap`、两个 `make_any`、三个引用形式和两个指针形式的 `any_cast`。`any` 只有默认构造函数是 `constexpr` 的，因此 `constinit std::any g;` 是可行的。

[any.bad.any.cast]/2：`bad_any_cast::what()` 返回实现定义的 NTBS。

[any.class.general]/2：非成员 `any_cast` 提供对所含值的类型安全访问。

[any.cons] 和 [any.modifiers] 中，各个 `initializer_list` 版本（¶16–21、¶9–16）与对应的普通版本相同，只是多了一个 `initializer_list<U>&` 实参；¶20 的后置条件写的只是 `*this` 含有一个值。转换赋值的约束（[any.assign]/8）没有排除 `in_place_type_t`，因为赋值不需要用标签消歧。

[any.modifiers]/19 `swap` 交换两者的状态；[any.nonmembers]/1 非成员 `swap(x, y)` 等价于 `x.swap(y)`。[any.observers]/3 的注说 `type()` 可用于与编译期已知或仅运行时已知的类型比较。

</details>
