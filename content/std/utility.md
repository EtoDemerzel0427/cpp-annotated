---
title: 工具组件
summary: <utility> 的十来个小函数——swap、exchange、forward/forward_like/move/move_if_noexcept、as_const、declval、整数安全比较 cmp_*/in_range、to_underlying、unreachable 与 observable_checkpoint——每一个都在给某条核心语言规则"打补丁"或"起名字"
status: done
covers: utility.syn, utility.swap, utility.exchange, forward, utility.as.const, declval, utility.intcmp, utility.underlying, utility.undefined
papers: P2445R1, P0586R2, P1682R3, P0627R6, P0007R1
related: utilities, const.wrap.class, pairs, tuple, dcl.ref, temp.deduct.call, expr.arith.conv, dcl.attr.assume, concept.swappable, swappable.requirements, intro.abstract, depr.relops
tags: 标准库, utility, 移动语义, 完美转发, swap, UB
updated: 2026-10-18
---

[utility] 是整个标准库里**最薄、却被调用得最频繁**的一层。这里的函数几乎都只有一两行实现——`std::move` 就是一个 `static_cast`，`std::forward` 也是——但它们存在的意义不在于"做了什么计算"，而在于**给核心语言里某条难以直接书写的规则起一个名字**：

- `std::move` / `std::forward` 是给"把左值当右值用"、"按推导结果恢复值类别"这两件事起的名字，背后是 [[dcl.ref]] 的引用折叠和 [[temp.deduct.call]] 的转发引用推导；
- `std::declval` 是给"在 [[g:unevaluated-operand]] 里凭空造出一个某类型的表达式"起的名字；
- `std::cmp_less` 等是给"数学意义上的整数比较"起的名字——内建的 `<` 由于 [[expr.arith.conv]] 的 [[g:usual-arithmetic-conversions]]，`-1 < 0u` 为 `false`；
- `std::unreachable` 是给"这里是 UB"起的名字，与 `[[assume]]`（[[dcl.attr.assume]]）是一对。

本页覆盖 [utility] 的全部子条款，唯独 {{c++26}} `std::constant_wrapper` 单独成页（[[const.wrap.class]]）。

| 子条款 | 内容 |
|---|---|
| [utility.syn] | `<utility>` 概要（全部 freestanding） |
| [utility.swap] | `swap`（含数组重载） |
| [utility.exchange] | `exchange` |
| [forward] | `forward`、`forward_like`、`move`、`move_if_noexcept` |
| [utility.as.const] | `as_const` |
| [declval] | `declval` |
| [utility.intcmp] | `cmp_equal` 等六个比较函数与 `in_range` |
| [utility.underlying] | `to_underlying` |
| [utility.undefined] | `unreachable`、`observable_checkpoint` |
| [const.wrap.class] | `constant_wrapper`、`cw`（见 [[const.wrap.class]]） |

## `<utility>` 概要里有什么（[utility.syn]）

¶1 只有一句话：`<utility>` 包含"在库的其余部分到处使用"的基础函数与类模板。概要第一行注释是 `// all freestanding`——整个头文件在 [[g:freestanding-implementation]] 中也必须提供，这对内核、嵌入式代码很重要：你永远可以用 `std::move`、`std::swap`、`std::pair`。

除了本页讨论的函数，概要还声明（或要求可见）这些东西，它们的规范在别处：

- `#include <compare>` 与 `#include <initializer_list>`——所以只包含 `<utility>` 就能用 `std::strong_ordering` 和 `std::initializer_list`；
- `integer_sequence` / `index_sequence` / `make_index_sequence` 等（[[intseq]]），以及当前草案中为 `integer_sequence` 提供的 `tuple_size` / `tuple_element` / `get`（[intseq.binding]，让 `auto [...is] = std::make_index_sequence<N>{};` 这样的结构化绑定包成为可能）；
- `pair` 及其比较、`swap`、`make_pair`、元组式访问，以及 `pair` 的 `common_type` / `basic_common_reference` 特化（[[pairs]]）；
- `piecewise_construct_t`、`in_place_t`、`in_place_type_t<T>`、`in_place_index_t<I>`——几个"标签类型"，构造函数用它们消歧义；它们都有 `explicit` 的预置默认构造函数，防止 `{}` 被意外地当成标签；
- `monostate` 及其比较与 `hash<monostate>`（规范在 [[variant.monostate]]）；
- 暴露于说明的 `constexpr-param` 概念与 `cw-operators`（见 [[const.wrap.class]]）。

!!! history "std::rel_ops 去哪了"
    C++98 在 `<utility>` 里提供了 `namespace std::rel_ops`：只要你写了 `==` 和 `<`，`using namespace std::rel_ops;` 就能"白送" `!=`、`>`、`<=`、`>=`。它在 C++20 随三路比较的库支持一起被**弃用**，条文从 [utility] 搬到了附录 D 的 [[depr.relops]]——**至今（当前草案）仍然存在**，并没有被移除；附录 D 的内容是规范性的，实现必须提供，只是不鼓励使用。libc++ 在 `__utility/rel_ops.h` 中把这四个模板标为 `_LIBCPP_DEPRECATED_IN_CXX20`，C++20 起使用会得到 `-Wdeprecated-declarations` 警告。
    
    它被弃用的根本原因：`rel_ops` 是对**所有** `T` 都匹配的无约束模板，一旦 `using namespace` 就会污染重载集合；而 C++20 的重写候选（[[over.match.oper]]）让 `a != b` 自动改写成 `!(a == b)`，`<=>` 一个运算符就能派生出四个关系运算符，`rel_ops` 失去了存在价值。一个 lawyer 级的细节：C++20 下即使 `using namespace std::rel_ops;`，`a != b` 也会选中由成员 `operator==` 重写出来的候选而不是 `rel_ops::operator!=`——[[over.match.best]] 中"非模板优于模板特化"这一条排在"非重写优于重写"之前，所以重写出的非模板候选胜出。

## `swap`：交换两个值（[utility.swap]）

### 主模板：约束与前置条件的分工（¶1–¶4）

```cpp
template<class T>
  constexpr void swap(T& a, T& b) noexcept(see below);
```

这是标准库规范"四级契约"的一个教科书例子（见 [[structure.specifications]]）：

- ¶1 *Constraints*：`is_move_constructible_v<T>` 且 `is_move_assignable_v<T>` 为 `true`。不满足时，这个模板**不参与重载决议**——对不可移动的类型，`std::swap` 是"不存在"的，`is_swappable_v<T>` 能如实地得到 `false`，而不是在函数体内部爆出一个硬错误。
- ¶2 *Preconditions*：`T` 满足 *Cpp17MoveConstructible* 与 *Cpp17MoveAssignable*。这是**语义**要求（例如移动构造后，新对象的值等于源对象原来的值），编译器检查不了；违反就是 UB。
- ¶3 *Effects*：交换 `a` 与 `b` 的值。标准没有规定"必须用三次 move"，但实现几乎都这样写（libc++ 的 `__utility/swap.h`：`_Tp __t(std::move(__x)); __x = std::move(__y); __y = std::move(__t);`）。
- ¶4 *Remarks*：异常规格等价于 `is_nothrow_move_constructible_v<T> && is_nothrow_move_assignable_v<T>`。

注意这里 *Constraints* 的价值：它让 `std::swap` 对 SFINAE 友好。libc++ 用 `__enable_if_t<is_move_constructible<_Tp>::value && is_move_assignable<_Tp>::value>` 作返回类型来实现它（为了兼容 C++03 模式，没有用 `requires`）。

### 数组重载（¶5–¶7）

```cpp
template<class T, size_t N>
  constexpr void swap(T (&a)[N], T (&b)[N]) noexcept(is_nothrow_swappable_v<T>);
```

¶5 约束 `is_swappable_v<T>`；¶6 前置条件是每对 `a[i]`、`b[i]` 都**可交换**（*swappable with*，[[swappable.requirements]]）；¶7 效果"如同" `swap_ranges(a, a + N, b)`。注意异常规格用的是 `is_nothrow_swappable_v<T>` 而不是"可 nothrow 移动"——数组元素是**逐个交换**的，元素类型可能有自己的 `swap`。

### "两步 swap" 与 `ranges::swap`

`std::swap(a, b)` 是**限定调用**，只会找到 `std` 里的模板，看不见用户在自己命名空间里为某个类型写的高效 `swap`。泛型代码的传统写法是所谓的 **std::swap 两步法**（[[g:swap-two-step]]）：

```cpp run title="swap_two_step.cpp" ok
#include <utility>
#include <concepts>
#include <cstdio>

namespace lib {
  struct Widget {
    int* p;
    friend void swap(Widget& a, Widget& b) noexcept {   // 自定义 swap：只交换指针
      std::puts("lib::swap");
      std::swap(a.p, b.p);
    }
  };
}

template<class T>
void generic_swap(T& a, T& b) {
  using std::swap;   // 第一步：把 std::swap 拉进来做后备
  swap(a, b);        // 第二步：非限定调用，ADL 可以找到 lib::swap
}

int main() {
  int x = 1, y = 2;
  lib::Widget a{&x}, b{&y};
  std::swap(a, b);           // 限定调用：只会用 std::swap（三次 move），不打印
  generic_swap(a, b);        // 打印 lib::swap
  std::ranges::swap(a, b);   // CPO：自动做 ADL，打印 lib::swap
  int arr1[2]{1, 2}, arr2[2]{3, 4};
  generic_swap(arr1, arr2);  // 数组重载：逐元素交换
  std::printf("%d %d\n", *a.p, arr1[0]);   // 2 3
}
```

两步法依赖两件事：非限定名字查找 + [[g:argument-dependent-lookup]] 找到 `lib::swap`；若 ADL 什么都没找到，`using` 引入的 `std::swap` 兜底。如果两者都可行，重载决议会更偏好更特化的那一个（用户的非模板 `swap` 胜过 `std::swap` 模板）。标准库自己在需要交换元素时也遵循这个约定——[[swappable.requirements]] 中"*swappable with*"的定义就是"在一个包含 `using std::swap;` 的上下文里非限定调用 `swap(t, u)` 有效且语义正确"。

两步法的问题是容易忘、容易写错（写成 `std::swap(a, b)` 就失效了）。C++20 的 `std::ranges::swap`（[[concept.swappable]]）是一个**定制点对象**（[[g:customization-point-object]]）：它是一个函数对象，内部先做"只看 ADL、屏蔽 `std::swap` 本身"的查找，找不到时退回到数组逐元素交换或三次移动。因为它是对象而不是函数，`ranges::swap(a, b)` 这个限定调用本身就**关闭了**对它的 ADL，反过来在它内部替你把 ADL 做了——这就是 CPO 的设计模式。

!!! lawyer "为什么 std::swap 不是 CPO"
    `std::swap` 的签名在 C++98 就定下来了，库内部和用户代码都有大量"为某类型在 `namespace std` 中声明 `swap` 重载/特化"的老写法（现在已不被允许为函数模板添加特化）。把它改成对象会破坏取地址、显式模板实参等现有用法。所以 C++20 选择新开一个 `ranges::swap`，而让 `std::swap` 保持函数模板。

## `exchange`：取旧值、放新值（[utility.exchange]）

```cpp
template<class T, class U = T>
  constexpr T exchange(T& obj, U&& new_val) noexcept(see below);
```

¶1 效果等价于"把 `obj` 移出到 `old_val`、把 `new_val` 转发赋给 `obj`、返回 `old_val`"。¶2 异常规格为 `is_nothrow_move_constructible_v<T> && is_nothrow_assignable_v<T&, U>`。

两个设计细节：

- **`U` 的默认模板实参是 `T`**。这让 `std::exchange(v, {})` 能工作：花括号初始化列表不能推导出模板形参，有了默认实参 `U = T`，`{}` 就被当成 `T&&` 的实参处理。
- 它是写移动构造/移动赋值的利器——"把指针偷过来，同时把源置空"一行搞定：

```cpp run title="exchange.cpp" ok
#include <utility>
#include <cstdio>

class Buffer {
  int* data_ = nullptr;
public:
  explicit Buffer(int n) : data_(new int[n]{}) {}
  Buffer(Buffer&& o) noexcept : data_(std::exchange(o.data_, nullptr)) {}
  Buffer& operator=(Buffer&& o) noexcept {
    delete[] std::exchange(data_, std::exchange(o.data_, nullptr));
    return *this;
  }
  ~Buffer() { delete[] data_; }
  bool empty() const { return data_ == nullptr; }
};

int main() {
  Buffer a(4);
  Buffer b = std::move(a);
  Buffer c(2);
  c = std::move(b);
  std::printf("%d %d %d\n", a.empty(), b.empty(), c.empty());   // 1 1 0
}
```

## 转发与移动（[forward]）

¶1 说明这一组函数的目的："简化对左值应用移动语义"以及"简化转发函数的实现"，并且**全部是信号安全的**（*signal-safe*，可以在信号处理函数里调用，见 [[support.signal]]）。

### 前置知识：转发引用与引用折叠

先把两条核心规则摆在桌上：

1. **转发引用**（[[g:forwarding-reference]]，[[temp.deduct.call#3]]）：函数模板形参写成 `T&&`（`T` 是该函数模板自己的类型模板形参、且无 cv 限定）时，如果实参是左值，`T` 被推导为**左值引用类型** `A&`；是右值则推导为 `A`。
2. **引用折叠**（[[g:reference-collapsing]]，[[dcl.ref#7]]）：通过模板形参或 typedef 形成"引用的引用"时，`A& &`、`A& &&`、`A&& &` 都折叠成 `A&`，只有 `A&& &&` 折叠成 `A&&`。

于是在 `template<class T> void f(T&& x)` 里，`T` 本身**编码了实参原来的值类别**：左值 → `T = A&`，右值 → `T = A`。但 `x` 作为具名变量永远是左值（[[basic.lval]]）。`std::forward<T>(x)` 的工作就是把这份编码"解码"回来。

### `forward`（¶2–¶4）

```cpp
template<class T> constexpr T&& forward(remove_reference_t<T>& t) noexcept;
template<class T> constexpr T&& forward(remove_reference_t<T>&& t) noexcept;
```

¶3 两个重载都只是 `static_cast<T&&>(t)`。代入引用折叠：

| `T` | `T&&` 折叠后 | `forward<T>(x)` 的值类别 |
|---|---|---|
| `A&`（实参原是左值） | `A&` | 左值 |
| `A`（实参原是右值） | `A&&` | xvalue |
| `A&&`（显式指定） | `A&&` | xvalue |

两个关键设计：

- **形参是 `remove_reference_t<T>&`，处于非推导语境**（[[temp.deduct.type]]）。所以 `forward` **必须显式写出模板实参**——`std::forward(x)` 无法推导，编译失败。这是刻意的：如果允许推导，`T` 就会从 `x`（一个左值）推导出来，信息早已丢失。
- **第二个重载接受右值**，用于转发一个"本身是右值的表达式"（例如 `std::forward<T>(std::move(obj).member)` 这类场合）。¶2 *Mandates*：对第二个重载，`is_lvalue_reference_v<T>` 为 `false`——把一个右值"转发成左值"几乎一定是 bug（会制造指向临时量的左值引用），所以直接判为非良构：

```cpp run title="forward_mandates.cpp" error
#include <utility>
int main() {
  int i = 0;
  (void)std::forward<int&>(std::move(i));   // error: 违反 Mandates
}
```

libc++（`__utility/forward.h`）用 `static_assert(!is_lvalue_reference<_Tp>::value, "cannot forward an rvalue as an lvalue")` 实现这个 *Mandates*。

¶4 的例子展示了完美转发的经典用途：`factory<A>(2, 1.414)` 中 `A1` 推导为 `int`，`2` 以右值转发给 `A(int&, const double&)`，绑定失败；`factory<A>(i, 1.414)` 中 `A1` 推导为 `int&`，以左值转发，成功。

### `forward_like`：按"另一个对象"的值类别转发 {{c++23}}（¶5–¶9）

`forward` 回答的是"**这个**东西原来是左值还是右值"。但常见的需求是：**我拿到一个对象 `self`（可能是 `const`、可能是右值），要把它的一个成员或它所拥有的某个东西按 `self` 的值类别和 const 性转发出去**。成员访问 `std::forward<Self>(self).m` 能做到一部分，但如果"拥有的东西"是通过指针间接拿到的（`*self.ptr`、`(*container)[i]`），值类别就丢了。`forward_like<T>(x)` 正是为此而生（[[P2445R1]]）：

¶6 定义了两个元函数：

- *COPY_CONST*(A, B)：若 `A` 是 const 类型则为 `const B`，否则为 `B`；
- *OVERRIDE_REF*(A, B)：若 `A` 是右值引用类型则为 `remove_reference_t<B>&&`，否则为 `B&`；
- `V` = *OVERRIDE_REF*(`T&&`, *COPY_CONST*(`remove_reference_t<T>`, `remove_reference_t<U>`))。

¶7 返回 `static_cast<V>(x)`。翻译成人话：**const 性取两者之并（`T` 是 const 就加上 const），引用种类完全由 `T` 决定（`x` 自己原来是什么引用被无视）**。¶5 *Mandates*：`T` 必须是可引用类型（[[g:referenceable-type]]），`forward_like<void>` 之类非良构。

```cpp run title="forward_like.cpp" ok
#include <utility>
#include <type_traits>
#include <string>

struct Holder {
  std::string name;
  template<class Self>
  auto&& get(this Self&& self) { return std::forward_like<Self>(self.name); }
};

int main() {
  Holder h{"abc"};
  const Holder ch{"xyz"};
  static_assert(std::is_same_v<decltype(h.get()), std::string&>);
  static_assert(std::is_same_v<decltype(std::move(h).get()), std::string&&>);
  static_assert(std::is_same_v<decltype(ch.get()), const std::string&>);
  static_assert(std::is_same_v<decltype(std::move(ch).get()), const std::string&&>);

  int i = 0;
  static_assert(std::is_same_v<decltype(std::forward<int&>(i)), int&>);
  static_assert(std::is_same_v<decltype(std::forward<int>(i)), int&&>);
  static_assert(std::is_same_v<decltype(std::forward_like<const int&>(i)), const int&>);
  static_assert(std::is_same_v<decltype(std::forward_like<int>(i)), int&&>);
  std::string s = std::move(h).get();   // 从 h.name 移动构造
  return s == "abc" ? 0 : 1;
}
```

它和 C++23 的显式对象形参（*deducing this*，[[dcl.fct]]）是天生一对：`Self` 精确编码了调用对象的 cv 与值类别，`forward_like<Self>` 把这份编码"传染"给成员。¶9 的标准例子展示的正是"成员是指针、所拥有的元素在容器里"的场景：`std::move(a)[0]` 得到 `string&&`，`as_const(a)[1]` 得到 `const string&`，不能绑定到非 const 的 `string&`。

!!! impl "libc++ 的实现"
    `__utility/forward_like.h` 几乎逐字翻译了 ¶6：`_CopyConst`、`_OverrideRef` 两个别名模板，外加形参上的 `_LIBCPP_LIFETIMEBOUND`（让 Clang 能对"返回值引用了临时实参"给出悬垂警告）。同一文件里还有一个内部工具 `__forward_as<T, As>`：按 `T` 的值类别把对象转成**基类** `As` 的引用，用于 deducing this 场景下"确保调用的是基类成员而不是派生类同名成员"。

### `move`（¶10–¶11）

```cpp
template<class T> constexpr remove_reference_t<T>&& move(T&& t) noexcept;
```

¶10 返回 `static_cast<remove_reference_t<T>&&>(t)`。`std::move` **不移动任何东西**——它只是一个到 xvalue 的转换，让后续的重载决议能选中移动构造/移动赋值。真正"移动"的是被选中的那个函数。

两个常被忽略的后果：

- `std::move` 作用于 `const` 对象得到 `const T&&`，它不能绑定到 `T&&`，于是重载决议**静默地选中复制构造函数**。`const std::string s; auto t = std::move(s);` 是一次复制。
- `return std::move(local);` 通常是负优化：它把 `local` 变成 xvalue，**阻止了 NRVO**（[[class.copy.elision]]）；而且自 C++11 起 `return local;` 本来就会优先按右值处理（[[g:implicitly-movable-entity]]，[[expr.prim.id.unqual]]）。

### `move_if_noexcept`（¶12）

```cpp
template<class T> constexpr conditional_t<
    !is_nothrow_move_constructible_v<T> && is_copy_constructible_v<T>, const T&, T&&>
  move_if_noexcept(T& x) noexcept;
```

¶12 返回 `std::move(x)`，但返回类型是**有条件的**：如果 `T` 的移动构造可能抛出、而它又可复制，就返回 `const T&`（于是调用方会**复制**）；否则返回 `T&&`。

它是为**强异常保证**服务的：`std::vector` 扩容时要把旧元素搬到新缓冲区。如果用可能抛异常的移动构造，搬到一半抛出，旧缓冲区里的元素已经被"掏空"，无法回滚；复制则不会破坏原件。所以 `vector` 用 `move_if_noexcept` 搬运元素——这就是"移动构造函数一定要写 `noexcept`"这条工程建议的出处。对只能移动（不可复制）的类型，没得选，返回 `T&&`，强保证降级为基本保证。

```cpp run title="move_if_noexcept.cpp" ok
#include <utility>
#include <type_traits>

struct ThrowingMove {
  ThrowingMove() = default;
  ThrowingMove(const ThrowingMove&) {}
  ThrowingMove(ThrowingMove&&) {}            // 没有 noexcept
};
struct NoexceptMove {
  NoexceptMove() = default;
  NoexceptMove(const NoexceptMove&) {}
  NoexceptMove(NoexceptMove&&) noexcept {}
};
struct MoveOnly {
  MoveOnly() = default;
  MoveOnly(MoveOnly&&) {}                    // 可能抛出，但不可复制
};

ThrowingMove a; NoexceptMove b; MoveOnly c;
static_assert(std::is_same_v<decltype(std::move_if_noexcept(a)), const ThrowingMove&>);
static_assert(std::is_same_v<decltype(std::move_if_noexcept(b)), NoexceptMove&&>);
static_assert(std::is_same_v<decltype(std::move_if_noexcept(c)), MoveOnly&&>);
int main() {}
```

## `as_const`（[utility.as.const]）

```cpp
template<class T> constexpr add_const_t<T>& as_const(T& t) noexcept;
template<class T> void as_const(const T&&) = delete;
```

¶1 返回 `t`，类型变成 const 左值引用——比 `const_cast<const T&>(x)` 好写、也不会被误读成"去掉 const"。典型用途：强制选中 const 重载（例如 Qt 风格的写时复制容器要避免触发 detach），或在 range-for 里避免意外修改。

概要里的第二个声明是**被弃置的右值重载**。对非 const 的右值，`T&` 本来就绑定不了；但对 **const 右值**（例如返回 `const X` 的函数调用），`T` 会被推导为 `const X`（[[temp.deduct.call]]），`const X&` 是能绑定右值的——`as_const` 就会返回一个指向临时量的引用。弃置的 `as_const(const T&&)` 对任何右值都是更好的匹配，堵住了这个洞，同时让所有右值实参都得到明确的"调用了被弃置的函数"诊断：

```cpp run title="as_const_rvalue.cpp" error
#include <utility>
#include <string>
std::string make();
int main() {
  std::string s = "x";
  const std::string& r = std::as_const(s);   // OK
  auto&& bad = std::as_const(make());         // error: 选中被弃置的 as_const(const T&&)
  (void)r; (void)bad;
}
```

## `declval`：只活在未求值语境里的函数（[declval]）

```cpp
template<class T> add_rvalue_reference_t<T> declval() noexcept;    // as unevaluated operand
```

¶1 它的唯一目的是"简化出现在未求值操作数中的表达式的书写"。在 `decltype`、`sizeof`、`noexcept`、`requires` 等语境（[[g:unevaluated-operand]]，[[expr.context]]）里，我们常常需要一个"类型为 `T` 的表达式"，但 `T` 可能没有默认构造函数、可能是抽象类、甚至不完整，没法写 `T()`。`declval<T>()` 无条件地"假装"返回一个 `T&&`。

!!! std "[declval]/2"
    *Mandates*: This function is not odr-used ([basic.def.odr]).

    *Mandates* 意味着违反时程序**非良构、必须诊断**：只要 `declval` 被 [[g:odr-use]]（即出现在潜在求值的表达式里），就是编译错误。

为什么能这样规定？因为 `declval` **根本没有定义**（或者说定义里只有一个必然失败的断言）——它从来不应被调用。返回类型选 `add_rvalue_reference_t<T>` 而不是 `T`，有三个好处：

1. `T` 可以是不完整类型、抽象类、数组或函数类型——返回 `T` 本身对这些类型都不合法；¶3 明确说 `T` 可以是不完整类型；
2. `declval<T>()` 是 xvalue，`declval<T&>()` 是左值（引用折叠），于是 `declval<T>()` / `declval<T&>()` / `declval<const T&>()` 能精确表达"什么值类别、什么 cv 的 `T` 表达式"；
3. 不会牵扯临时对象——如果返回 `T`，结果就是类类型的 prvalue，在某些语境下会物化临时对象并要求析构函数可用（[[dcl.type.decltype]] 只为 `decltype` 的操作数开了"不引入临时对象"的豁免）；返回引用则完全绕开了这个问题。

`void` 的情况：`add_rvalue_reference_t<void>` 是 `void`，所以 `declval<void>()` 是一个 `void` 表达式，这也是用 `add_rvalue_reference_t` 而不是直接写 `T&&` 的原因（`void&&` 不合法）。

```cpp run title="declval.cpp" error
#include <utility>
#include <type_traits>
struct NoDefault { NoDefault(int); int f() const; };
// 未求值操作数中使用 declval：OK
using R = decltype(std::declval<const NoDefault&>().f());
static_assert(std::is_same_v<R, int>);
static_assert(noexcept(std::declval<NoDefault>()));
struct Incomplete;
using X = decltype(std::declval<Incomplete>());   // OK：T 可以是不完整类型
int main() {
  auto x = std::declval<int>();   // error: declval 被 odr-use，违反 Mandates
  (void)x;
}
```

!!! impl "libc++ 如何让 Mandates 生效"
    `__utility/declval.h` 的 `declval` **有函数体**，里面是 `static_assert(!__is_same(_Tp, _Tp), "std::declval can only be used in an unevaluated context. ...")`。条件依赖于 `_Tp`，所以只在函数体被**实例化**时才求值——而函数模板的定义只有在被 odr-use 时才会隐式实例化（[[temp.inst]]）。未求值语境里的使用不会 odr-use，也就不实例化函数体，断言永远不触发。这是用"实例化时机"实现"odr-use 检测"的标准技巧。返回类型则通过两个重载的 `__declval<T>(0)`（`int` 版返回 `T&&`、`long` 版返回 `T`）来处理 `void` 等不可引用类型，效果等价于 `add_rvalue_reference_t<T>`，但避免了实例化一个类模板。

¶4 的例子 `decltype(static_cast<To>(declval<From>())) convert(From&&);` 展示了 `declval` 与 [[g:sfinae]] 的经典组合：返回类型中的表达式无效时，`convert` 被从候选集中剔除。

## 整数比较：数学意义上的 `<`（[utility.intcmp]）

### 为什么需要它们

内建比较运算符对算术操作数先做 [[g:usual-arithmetic-conversions]]（[[expr.arith.conv]]）。当一个操作数是有符号、另一个是无符号，且无符号类型的整数转换秩不低于有符号类型时，有符号操作数被转换为**无符号类型**——`-1` 变成 `UINT_MAX`：

```cpp run title="intcmp.cpp" ok
#include <utility>
#include <cstdint>

static_assert(!(-1 < 0u));                      // 内建 <：-1 先被转换为 UINT_MAX
static_assert(std::cmp_less(-1, 0u));           // 数学意义上的比较
static_assert(short{-1} < (unsigned short)0);   // 两边都先提升为 int，没有陷阱

static_assert(!std::cmp_equal(-1, UINT32_MAX));
static_assert(std::in_range<std::uint8_t>(255));
static_assert(!std::in_range<std::uint8_t>(256));
static_assert(!std::in_range<unsigned>(-1));
int main() {}
```

（第三行说明陷阱不总是出现：`short` 与 `unsigned short` 先经整数提升都变成 `int`。是否中招取决于具体类型的宽度，这正是它难以肉眼识别的原因。编译器的 `-Wsign-compare` 能警告前者。）

### 条文（¶1–¶10）

¶1 / ¶4 / ¶9 的 *Mandates*：每个类型必须是**有符号或无符号整数类型**（[[basic.fundamental]]）。¶2 给出 `cmp_equal` 的规范实现：

- 两边符号性相同 → 直接用 `==`（此时常规算术转换不会改变数学值）；
- `T` 有符号、`U` 无符号 → `t < 0` 则必不相等，否则把 `t` 转成 `make_unsigned_t<T>` 再比；
- 反之对称。

¶5 的 `cmp_less` 结构相同（`t < 0` 时 `t` 必然更小）。¶3、¶6–¶8 把另外四个函数定义为前两者的组合（`cmp_greater(t, u)` 就是 `cmp_less(u, t)`，等等）。¶10 `in_range<R>(t)`：`t` 落在 `[numeric_limits<R>::min(), numeric_limits<R>::max()]` 内——判断"转换到 `R` 是否保值"的标准写法。

¶11 注：这些函数**不能**用于 `byte`、`char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 和 `bool`。它们虽然是整型（*integral type*），却不属于"有符号/无符号整数类型"（[[basic.fundamental]]）——`char` 的符号性由实现定义，字符类型和 `bool` 的"数值比较"本身语义可疑，标准干脆拒绝。

```cpp run title="intcmp_char.cpp" error
#include <utility>
int main() {
  bool b1 = std::cmp_less('a', 98);    // error: char 不是有符号/无符号整数类型
  bool b2 = std::cmp_equal(true, 1);   // error: bool 同理
  (void)b1; (void)b2;
}
```

!!! impl "libc++：Mandates 实现成了约束，还多了一条快速路径"
    标准写的是 *Mandates*（硬错误），libc++ 的 `__utility/cmp.h` 却把要求写成模板形参上的概念 `__signed_or_unsigned_integer`——也就是**约束**。结果都是编译失败（诊断变成 "no matching function"），但可被 SFINAE 探测：`requires { std::cmp_less('a', 1); }` 在 libc++ 上得到 `false`，而按标准它应当是一个硬错误。可移植代码不应依赖这种差异。
    
    另外，libc++ 在符号不同、但两个类型都能无损提升到 `int`（或 `long long`）时，直接 `static_cast` 后比较，省掉分支；这是"如同"规则（[[g:as-if-rule]]）允许的优化。

## `to_underlying`（[utility.underlying]）

¶1 返回 `static_cast<underlying_type_t<T>>(value)`。它只是把一个常见的冗长写法起了名字（[[P1682R3]]），但有一点实际价值：**类型永远正确**。手写 `static_cast<int>(e)` 在有人把枚举的底层类型（[[g:underlying-type]]，[[dcl.enum]]）从 `int` 改成 `std::uint64_t` 后会悄悄截断，`to_underlying` 不会。

```cpp run title="to_underlying.cpp" ok
#include <utility>
#include <cstdint>
#include <cstdio>

enum class Color : std::uint8_t { red = 1, green = 2 };

int main() {
  auto v = std::to_underlying(Color::green);
  static_assert(std::is_same_v<decltype(v), std::uint8_t>);
  std::printf("%d\n", v);          // 2（uint8_t 经默认实参提升为 int）
}
```

注意概要中没有给 `to_underlying` 写约束：对非枚举类型调用，`underlying_type_t<T>` 不是合法类型，于是在返回类型的替换中失败——这在实际效果上是 SFINAE 友好的，但标准没有用 *Constraints* 明说。

## 显式的 UB 与可观察检查点（[utility.undefined]）

### `unreachable`（¶1–¶2）

```cpp
[[noreturn]] void unreachable();
```

!!! std "[utility.undefined]/1"
    *Preconditions*: `false` is `true`.

    前置条件"`false` 为 `true`"永远不可能满足，所以——注 1 说得明白——**调用 `unreachable` 的行为是未定义的**。

这是标准库里最"法律化"的一行条文：它没有发明新的 UB 机制，而是借用"违反前置条件即 UB"（[[structure.specifications]]）这一通则，造出一个**必然违反前置条件**的函数。效果和 GCC/Clang 的 `__builtin_unreachable()`、MSVC 的 `__assume(false)` 相同（libc++ 的 `__utility/unreachable.h` 正是调用 `__builtin_unreachable()`，在启用断言时先 `_LIBCPP_ASSERT_INTERNAL(false, ...)`）。

用途：告诉优化器"控制流不会到这里"。最典型的是 `switch` 的 `default` 分支：

```cpp run title="unreachable.cpp" ub
#include <utility>
#include <cstdio>

int decode(int tag) {
  switch (tag) {
  case 0: return 10;
  case 1: return 20;
  default: std::unreachable();   // 断言调用方永远不会传其他值
  }
}

int main(int argc, char**) {
  std::printf("%d\n", decode(argc - 1));   // 无参数运行：argc == 1 → 10，OK
  std::printf("%d\n", decode(argc + 5));   // UB：到达 unreachable
}
```

本机实测：`-O0 -fsanitize=undefined` 下 UBSan 报告 "execution reached an unreachable program point" 并终止；而 `-O2` 下第二行**静默地打印了 20**——优化器认为 `tag` 只可能是 0 或 1，把 `switch` 化简成了一次比较。这正是 UB 的"后果不受约束"：编译器并没有"出错"，是程序先违约了。

!!! note "unreachable 与 [[assume]] 的关系"
    `[[assume(expr)]]`（[[dcl.attr.assume]]）是 C++23 的核心语言版本：若 [[g:assumption]] 在该处求值不为 `true`，行为未定义。两者可以互相表达——`if (!cond) std::unreachable();` 与 `[[assume(cond)]];` 给优化器的信息类似。但有三个区别：
    
    - `[[assume]]` 的表达式**不求值**（它是未求值操作数，副作用不会发生），`if (!cond)` 中的 `cond` 会被求值；
    - `[[assume]]` 是属性，忽略它不改变程序含义；`unreachable()` 是函数调用，是 `[[noreturn]]` 的，编译器据此可以不对"函数末尾无 return"发出警告；
    - `unreachable()` 是一条语句、可以放在任何地方（如 `default:` 分支），表达"这条路径不存在"；`[[assume]]` 表达"这个条件成立"。
    
    在 C++26 契约（[[basic.contract]]）出现后，"我认为这件事永远成立"的**可检查**版本应该写成 `contract_assert(cond);`；`unreachable` 与 `[[assume]]` 则是"我向编译器担保、出错后果自负"的**不可检查**版本，只应在性能关键且有充分证据时使用。

### `observable_checkpoint` {{c++26}}（¶3）

```cpp
void observable_checkpoint() noexcept;
```

¶3 效果：建立一个**可观察检查点**（[[g:observable-checkpoint]]，[[intro.abstract]]）。它是 C++26 "UB 不能时间旅行"规则的库接口：按新的 [[intro.abstract]]，如果执行中出现 UB，只有**最后一个可观察检查点之后**的行为不受约束，之前已经发生的可观察行为必须如实发生。调用 `std::observable_checkpoint()` 就是在程序里手工插一个"存档点"——例如在一段可能有 UB 的代码前先把日志刷出去，保证日志不会被优化器"连坐"抹掉。它和 `unreachable` 放在同一个子条款里，正好构成一对：一个制造 UB，一个限制 UB 的波及范围。

## 常见误区

!!! pitfall "易错点清单"
    - **`std::move` 不移动**，`std::forward` 也不"转发"任何东西——它们都只是 `static_cast`。对 `const` 对象 `std::move` 得到的是复制。
    - **`std::forward` 必须显式写模板实参**，而且应写转发引用形参的那个 `T`（`std::forward<T>(x)`），不是 `decltype(x)` 以外的随便什么类型。对 `auto&&` 变量，用 `std::forward<decltype(x)>(x)`。
    - **同一个对象不要 forward/move 两次**：第一次之后它可能已被掏空（处于 [[g:valid-but-unspecified-state]]）。
    - **泛型代码中写 `std::swap(a, b)`** 会绕过用户的 `swap`；要么用两步法，要么用 `std::ranges::swap`。
    - **`cmp_less` 不接受 `char`/`bool`**；对字符先转成合适的整数类型再比较。
    - **`declval` 只能出现在未求值语境**；写在 `if constexpr` 的条件里也算潜在求值（条件是常量表达式，会被求值）。
    - **`unreachable` 不是断言**：发布构建里它不会报告任何东西，只会让优化器更激进。想要"调试时报错"，用 `assert` 或 `contract_assert`。

## 历史演进

!!! history "从 C++11 到 C++26"
    - **C++11**：右值引用进入语言，`<utility>` 新增 `move`、`forward`、`move_if_noexcept`、`declval`；`swap` 从 `<algorithm>` 移到 `<utility>`，并得到 `noexcept` 规格与数组重载。
    - **C++14**：`exchange`；`forward`/`move` 成为 `constexpr`。
    - **C++17**：`as_const`（[[P0007R1]]）；`std::swap` 改为受约束（不可移动类型时不参与重载决议），同时引入 `is_swappable` 系列特征。
    - **C++20**：`cmp_equal` 等整数比较函数与 `in_range`（[[P0586R2]]）；`swap`、`exchange` 成为 `constexpr`；`ranges::swap` CPO；`rel_ops` 弃用并移入附录 D。
    - **C++23**：`forward_like`（[[P2445R1]]）、`to_underlying`（[[P1682R3]]）、`unreachable`（[[P0627R6]]）。
    - **C++26**：`observable_checkpoint`；`constant_wrapper` / `cw`（[[const.wrap.class]]）。
    - **当前草案**中还能看到 `integer_sequence` 的结构化绑定支持（libc++ 23 的 `__cpp_lib_integer_sequence` 已是 `202511L`），以及 `monostate` 经 `<utility>` 可得。

## 思考题

!!! question "思考题 1"
    下面的 `wrapper` 想把实参完美转发给 `g`。它有什么问题？
    ```cpp
    template<class T> void wrapper(T&& x) { g(std::forward<T&&>(x)); }
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

结果其实是**正确的**，只是写法多余。实参为左值时 `T = A&`，`T&&` 折叠为 `A&`，`forward<A&>(x)` 返回 `A&`；实参为右值时 `T = A`，`T&&` 为 `A&&`，`forward<A&&>(x)` 返回 `static_cast<A&& &&>(x)` 即 `A&&`——与 `forward<A>(x)` 相同。按 [[dcl.ref#7]] 的引用折叠，`forward<T>` 与 `forward<T&&>` 在转发引用场景下等价。惯用写法是 `std::forward<T>(x)`；`std::forward<decltype(x)>(x)` 对 `auto&&` 形参同样正确，原理也是这一张折叠表。
</details>

!!! question "思考题 2"
    `std::cmp_less(x, y)` 对 `int x`、`long long y` 的结果，是否可能与 `x < y` 不同？对 `unsigned x`、`long long y` 呢？对 `unsigned long long x`、`long long y` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一种：同为有符号，¶5 的第一个分支直接 `t < u`，结果一定相同。第二种：`unsigned` 与 `long long`，在 `long long` 比 `unsigned` 宽的平台上（几乎所有平台），常规算术转换把 `unsigned` 转为 `long long`，数学值不变，所以内建 `<` 也是对的，二者相同。第三种：`unsigned long long` 与 `long long` 秩相同，有符号一侧被转换为 `unsigned long long`，`y = -1` 时内建 `x < y` 对任何 `x` 都可能为 `true`，而 `cmp_less(x, -1)` 恒为 `false`——这里两者不同。规则见 [[expr.arith.conv#1]]。
</details>

!!! question "思考题 3"
    为什么 `declval` 的返回类型是 `add_rvalue_reference_t<T>` 而不是 `T&&`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

因为 `T` 可能是 `void` 或带 cv 的 `void`、或者"可憎函数类型"（带 cv/引用限定的函数类型，[[dcl.fct]]），这些都不是可引用类型，`T&&` 会直接造成替换失败甚至硬错误；`add_rvalue_reference_t<T>` 对不可引用类型原样返回 `T`。这样 `declval<void>()` 是合法的 `void` 表达式，可以出现在 `decltype(declval<void>())` 之类的元编程里。对可引用类型，两者完全相同。
</details>

## 小结

!!! summary "核心要点"
    | 函数 | 本质 | 关键契约 |
    |---|---|---|
    | `swap` | 三次 move（或用户 ADL 版本） | *Constraints*：可移动构造与赋值；数组版按 `is_nothrow_swappable` |
    | `exchange` | 取旧值放新值 | `U = T` 默认实参支持 `exchange(x, {})` |
    | `forward<T>` | `static_cast<T&&>` + 引用折叠 | 非推导语境，必须显式实参；右值版 *Mandates* `T` 非左值引用 |
    | `forward_like<T>` | const 取并，引用种类随 `T` | *Mandates*：`T` 可引用 |
    | `move` | 转换为 xvalue | 不移动；`const` 对象会退化为复制 |
    | `move_if_noexcept` | 有条件的 `move` | 移动可能抛出且可复制 → `const T&` |
    | `as_const` | 加 const | 右值重载弃置，防悬垂 |
    | `declval` | 未求值语境中的"某类型表达式" | *Mandates*：不得 odr-use |
    | `cmp_*` / `in_range` | 数学意义上的整数比较 | *Mandates*：有符号/无符号整数类型，排除字符与 `bool` |
    | `to_underlying` | 转为底层类型 | 类型永远正确 |
    | `unreachable` | 显式 UB | 前置条件 `false` 为 `true` |
    | `observable_checkpoint` | 可观察检查点 | 限制 UB 的"时间旅行" |
