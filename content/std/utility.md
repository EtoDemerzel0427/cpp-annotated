---
title: 工具组件
summary: <utility> 里的小函数：move、forward、forward_like、move_if_noexcept、swap、exchange、as_const、declval、整数安全比较 cmp_less 等、to_underlying、unreachable 和 observable_checkpoint；它们大多只有一两行实现，作用是给某条语言规则起一个名字。
status: done
covers: utility.syn, utility.swap, utility.exchange, forward, utility.as.const, declval, utility.intcmp, utility.underlying, utility.undefined
papers: P2445R1, P0586R2, P1682R3, P0627R6, P0007R1
related: utilities, const.wrap.class, pairs, tuple, dcl.ref, temp.deduct.call, expr.arith.conv, dcl.attr.assume, concept.swappable, swappable.requirements, intro.abstract, depr.relops
tags: 标准库, utility, 移动语义, 完美转发, swap, UB
updated: 2026-10-19
---

!!! tldr
    - `std::move` 和 `std::forward` 都只是 `static_cast`，本身不移动任何东西；对 `const` 对象 `std::move` 之后得到的是复制。
    - `std::forward<T>(x)` 必须显式写出模板实参，它依靠引用折叠把转发引用推导出的 `T` 还原成实参原来的值类别。
    - 泛型代码中交换两个值，要么先 `using std::swap;` 再非限定调用 `swap(a, b)`，要么用 `std::ranges::swap`；直接写 `std::swap(a, b)` 会绕过类型自己的 `swap`。
    - `std::cmp_less(-1, 0u)` 为真，而内建的 `-1 < 0u` 为假；`cmp_*` 不接受 `char` 和 `bool`。
    - 调用 `std::unreachable()` 是未定义行为，它的用途是告诉优化器这条路径不存在；`std::declval` 只能出现在未求值操作数中，否则编译失败。

[utility] 中的函数几乎都只有一两行实现，`std::move` 就是一个 `static_cast`。它们的价值在于给一条不好直接书写的语言规则起一个名字：`move` 是把左值当作右值使用，`forward` 是按推导结果恢复值类别，`declval` 是在未求值操作数中凭空得到一个某类型的表达式，`cmp_less` 是数学意义上的整数比较，`unreachable` 是这里不可能执行到。

[utility] 中的 {{c++26}} `constant_wrapper` 另见 [[const.wrap.class]]。

¶1 [utility.syn] 说明 `<utility>` 包含在库的其余部分到处用到的基础函数和类模板，整个头文件都是 freestanding 的，在没有操作系统的环境中也可以使用。

## `move`：把左值当作右值 [forward]

```cpp run title="move.cpp" ok
#include <string>
#include <utility>
#include <cstdio>

int main() {
  std::string a = "hello";
  std::string b = std::move(a);      // 选中移动构造函数
  const std::string c = "world";
  std::string d = std::move(c);      // const std::string&& 只能绑定到复制构造函数的形参
  std::printf("[%s] [%s]\n", b.c_str(), c.c_str());   // [hello] [world]
}
```

```cpp
template<class T> constexpr remove_reference_t<T>&& move(T&& t) noexcept;
```

¶10 `std::move(t)` 返回 `static_cast<remove_reference_t<T>&&>(t)`，也就是把实参转换成 xvalue。真正移动资源的是之后被重载决议选中的移动构造函数或移动赋值运算符，`std::move` 只是让它们能被选中。

由此有两个常被忽略的后果：

- `std::move` 作用于 `const` 对象得到 `const T&&`，它不能绑定到移动构造函数的 `T&&` 形参，于是重载决议选中复制构造函数。上例中的 `d` 是复制来的，`c` 原样保留。
- `return std::move(local);` 通常比 `return local;` 更差。后者允许编译器省略复制（NRVO，[[class.copy.elision]]），而且即使不省略，`local` 作为可隐式移动的实体（[[g:implicitly-movable-entity]]）也会优先按右值处理；前者让返回表达式不再是一个名字，反而阻止了省略。

¶1 本子条款的函数都是信号安全的，可以在信号处理函数中调用（[[support.signal]]）。

## `forward`：恢复实参的值类别

### 转发引用与引用折叠

```cpp
template<class T>
void wrapper(T&& x) {
  target(std::forward<T>(x));   // 实参是左值就转发左值，是右值就转发右值
}
```

`std::forward` 依赖两条核心语言规则：

1. **转发引用**（[[g:forwarding-reference]]，[[temp.deduct.call#3]]）：函数模板的形参写成 `T&&`，且 `T` 是这个函数模板自己的、无 cv 限定的类型模板形参时，实参为左值则 `T` 推导为左值引用类型 `A&`，实参为右值则 `T` 推导为 `A`。
2. **引用折叠**（[[g:reference-collapsing]]，[[dcl.ref#7]]）：通过模板形参或类型别名形成引用的引用时，只要有一个 `&`，结果就是左值引用；只有 `&& &&` 得到右值引用。

于是在 `wrapper` 中，`T` 记录了实参原来的值类别。但 `x` 是一个有名字的变量，作为表达式它总是左值（[[basic.lval]]）。`std::forward<T>(x)` 的任务就是按 `T` 把值类别还原回来。

### 定义（¶2–¶4）

```cpp
template<class T> constexpr T&& forward(remove_reference_t<T>& t) noexcept;
template<class T> constexpr T&& forward(remove_reference_t<T>&& t) noexcept;
```

¶3 两个重载都返回 `static_cast<T&&>(t)`。代入引用折叠：

| `T` | `T&&` 折叠后 | `forward<T>(x)` 的值类别 |
|---|---|---|
| `A&`（实参原是左值） | `A&` | 左值 |
| `A`（实参原是右值） | `A&&` | xvalue |
| `A&&`（显式指定） | `A&&` | xvalue |

形参类型 `remove_reference_t<T>&` 中的 `T` 处于非推导语境（[[temp.deduct.type]]），所以 `forward` 必须显式写出模板实参，`std::forward(x)` 无法编译。这是有意的：如果允许推导，`T` 就会从左值 `x` 推导出来，原来的值类别信息早已丢失。

第二个重载接受右值，用于转发一个本身就是右值的表达式。¶2 规定它的 `T` 不能是左值引用类型（*Mandates*），因为把右值转发成左值几乎一定是错误，会得到一个指向临时对象的左值引用：

```cpp run title="forward_mandates.cpp" error
#include <utility>
int main() {
  int i = 0;
  (void)std::forward<int&>(std::move(i));   // error: 把右值转发成左值，违反 Mandates
}
```

libc++ 用一条 `static_assert` 实现这项要求，诊断是 "cannot forward an rvalue as an lvalue"。

¶4 标准的例子展示了完美转发的效果：`factory<A>(2, 1.414)` 中 `A1` 推导为 `int`，`2` 作为右值转发给 `A(int&, const double&)`，绑定失败；`factory<A>(i, 1.414)` 中 `A1` 推导为 `int&`，`i` 作为左值转发，绑定成功。

### `forward_like`：按另一个对象的值类别转发 {{c++23}}（¶5–¶9）

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
  std::string s = std::move(h).get();   // 从 h.name 移动构造
  return s == "abc" ? 0 : 1;
}
```

`forward` 回答的是这个东西原来是左值还是右值。常见的另一种需求是：拿到一个对象 `self`，要把它的某个成员，或者它通过指针拥有的某个东西，按 `self` 的值类别和 const 性转发出去。成员访问 `std::forward<Self>(self).m` 能处理直接成员，但经过指针间接得到的东西（`*self.ptr`、`(*container)[i]`）就丢失了这些信息。`forward_like<T>(x)`（[[P2445R1]]）解决的就是这个问题。

¶6 结果类型按两条规则确定：如果 `T` 是 const 的，结果加上 `const`；结果是左值引用还是右值引用完全由 `T` 决定，`x` 自己原来是哪种引用不起作用。¶7 返回值是把 `x` `static_cast` 到这个类型。¶5 `T` 必须是可引用类型（[[g:referenceable-type]]），`forward_like<void>` 非良构。

它和 C++23 的显式对象形参（[[dcl.fct]]）是天然的搭配：`Self` 精确记录了调用对象的 cv 限定和值类别，`forward_like<Self>` 把它们传给成员。¶9 的标准例子展示的正是成员是指针、元素在容器里的情况：`std::move(a)[0]` 得到 `string&&`，`as_const(a)[1]` 得到 `const string&`，不能绑定到非 const 的 `string&`。

### `move_if_noexcept`（¶12）

```cpp
template<class T> constexpr conditional_t<
    !is_nothrow_move_constructible_v<T> && is_copy_constructible_v<T>, const T&, T&&>
  move_if_noexcept(T& x) noexcept;
```

¶12 它返回 `std::move(x)`，但返回类型有条件：如果 `T` 的移动构造可能抛出异常而 `T` 又可复制，返回 `const T&`，调用方因此会复制；否则返回 `T&&`。

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

它服务于强异常保证。`std::vector` 扩容时要把旧元素搬到新缓冲区，如果用可能抛出的移动构造，搬到一半抛出异常时，旧缓冲区中的元素已经被移走，无法回滚；复制则不会破坏原来的元素。所以 `vector` 用 `move_if_noexcept` 搬运元素，这就是移动构造函数应当声明 `noexcept` 的原因。只能移动、不能复制的类型别无选择，返回 `T&&`，强保证降级为基本保证。

## `swap`：交换两个值 [utility.swap]

### 两步法与 `ranges::swap`

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
  using std::swap;   // 第一步：引入 std::swap 作为后备
  swap(a, b);        // 第二步：非限定调用，ADL 可以找到 lib::swap
}

int main() {
  int x = 1, y = 2;
  lib::Widget a{&x}, b{&y};
  std::swap(a, b);           // 限定调用：只用 std::swap（三次移动），不打印
  generic_swap(a, b);        // 打印 lib::swap
  std::ranges::swap(a, b);   // 打印 lib::swap
  int arr1[2]{1, 2}, arr2[2]{3, 4};
  generic_swap(arr1, arr2);  // 数组重载：逐元素交换
  std::printf("%d %d\n", *a.p, arr1[0]);   // 2 3
}
```

`std::swap(a, b)` 是限定调用，只会找到 `std` 中的模板，看不到用户为自己的类型写的高效 `swap`。泛型代码的传统写法是 **std::swap 两步法**（[[g:swap-two-step]]）：先 `using std::swap;`，再非限定地调用 `swap(a, b)`。实参依赖查找（[[g:argument-dependent-lookup]]）能找到 `lib::swap`；找不到时，`std::swap` 兜底。两者都可行时，非模板的 `lib::swap` 胜过模板 `std::swap`。[[swappable.requirements]] 对可交换的定义就是在这样的语境中调用 `swap(t, u)` 有效且语义正确。

两步法容易忘记，也容易写错。C++20 的 `std::ranges::swap`（[[concept.swappable]]）是一个**定制点对象**（[[g:customization-point-object]]）：它是函数对象，内部替你做了只看 ADL 的查找，找不到时再退回逐元素交换或三次移动。`std::swap` 本身没有改成这样的对象，因为现有代码会对它取地址、显式指定模板实参，改动会破坏这些用法。

### 主模板（¶1–¶4）

```cpp
template<class T>
  constexpr void swap(T& a, T& b) noexcept(see below);
```

这是标准库元素分工的一个典型例子（见 [[structure.specifications]]）：

- ¶1 *Constraints*：`is_move_constructible_v<T>` 和 `is_move_assignable_v<T>` 都为真。不满足时这个模板不参与重载决议，`is_swappable_v<T>` 能如实得到 `false`，而不是在函数体内部出现硬错误。
- ¶2 *Preconditions*：`T` 满足 *Cpp17MoveConstructible* 和 *Cpp17MoveAssignable*。这是编译器无法检查的语义要求，例如移动构造之后新对象的值等于源对象原来的值。违反是未定义行为。
- ¶3 *Effects*：交换 `a` 和 `b` 的值。标准没有规定怎样交换，实现通常是三次移动。
- ¶4 异常规格等价于 `is_nothrow_move_constructible_v<T> && is_nothrow_move_assignable_v<T>`。

### 数组重载（¶5–¶7）

```cpp
template<class T, size_t N>
  constexpr void swap(T (&a)[N], T (&b)[N]) noexcept(is_nothrow_swappable_v<T>);
```

¶5 它要求 `is_swappable_v<T>`；¶6 每对 `a[i]`、`b[i]` 都必须可交换；¶7 效果如同 `swap_ranges(a, a + N, b)`。异常规格用的是 `is_nothrow_swappable_v<T>`，因为元素是逐个交换的，元素类型可能有自己的 `swap`。

## `exchange`：取出旧值、放入新值 [utility.exchange]

```cpp
template<class T, class U = T>
  constexpr T exchange(T& obj, U&& new_val) noexcept(see below);
```

¶1 效果等价于先把 `obj` 移出到 `old_val`，再把 `new_val` 转发赋值给 `obj`，最后返回 `old_val`。¶2 异常规格为 `is_nothrow_move_constructible_v<T> && is_nothrow_assignable_v<T&, U>`。

`U` 的默认模板实参是 `T`，所以 `std::exchange(v, {})` 也能工作：花括号列表无法推导模板形参，有了默认实参，`{}` 就按 `T&&` 处理。

它最常见的用途是写移动操作，一行完成把指针拿过来并把源置空：

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

## `as_const` [utility.as.const]

```cpp
template<class T> constexpr add_const_t<T>& as_const(T& t) noexcept;
template<class T> void as_const(const T&&) = delete;
```

¶1 `as_const(t)` 返回 `t`，类型变为 const 左值引用。它比 `const_cast<const T&>(x)` 好写，也不会被误读成去掉 const。常见用途是强制选中 const 重载，例如避免写时复制的容器因非 const 访问而复制数据。

第二个声明是被弃置的右值重载。非 const 的右值本来就绑定不到 `T&`；但对 const 右值，例如返回 `const X` 的函数调用，`T` 会推导为 `const X`（[[temp.deduct.call]]），而 `const X&` 能绑定右值，`as_const` 就会返回一个指向临时对象的引用。弃置的 `as_const(const T&&)` 对所有右值都是更好的匹配，堵住了这个漏洞：

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

## `declval`：只用于未求值操作数 [declval]

```cpp
template<class T> add_rvalue_reference_t<T> declval() noexcept;    // as unevaluated operand
```

¶1 `decltype`、`sizeof`、`noexcept`、`requires` 的操作数是**未求值操作数**（[[g:unevaluated-operand]]）：其中的表达式只做类型检查，不会执行。在这些地方经常需要一个类型为 `T` 的表达式，但 `T` 可能没有默认构造函数、可能是抽象类，甚至不完整，写不出 `T()`。`declval<T>()` 无条件地给出这样一个表达式。

```cpp run title="declval.cpp" error
#include <utility>
#include <type_traits>
struct NoDefault { NoDefault(int); int f() const; };

using R = decltype(std::declval<const NoDefault&>().f());   // OK：未求值操作数
static_assert(std::is_same_v<R, int>);
struct Incomplete;
using X = decltype(std::declval<Incomplete>());             // OK：T 可以不完整（¶3）

int main() {
  auto x = std::declval<int>();   // error: declval 被 odr-use
  (void)x;
}
```

!!! std
    *Mandates*: This function is not odr-used ([basic.def.odr]).

¶2 只要 `declval` 被 ODR 使用（[[g:odr-use]]），也就是出现在潜在求值的表达式中，程序就非良构，编译器必须报错。`declval` 只是用来写类型的工具，从来不应被调用。

返回类型选 `add_rvalue_reference_t<T>` 而不是 `T`，有两个好处：

1. ¶3 `T` 可以是不完整类型、抽象类、数组或函数类型，而这些类型都不能作为函数的返回类型；
2. `declval<T>()` 是 xvalue，`declval<T&>()` 是左值，`declval<const T&>()` 是 const 左值，可以精确表达需要什么值类别和 cv 限定的表达式。

用 `add_rvalue_reference_t<T>` 而不直接写 `T&&`，是因为它对 `void` 这类不可引用的类型原样返回 `T`：`declval<void>()` 是一个合法的 `void` 表达式，而 `void&&` 不合法。

!!! impl "libc++ 怎样检查 ODR 使用"
    libc++ 的 `declval` 有函数体，里面是一条条件依赖于 `_Tp` 的 `static_assert`，例如 `!__is_same(_Tp, _Tp)`，它只在函数体被实例化时求值。函数模板的定义只在被 ODR 使用时才隐式实例化（[[temp.inst]]），未求值操作数中的使用不会触发实例化，所以断言只在违规时失败。返回类型则借助两个重载的 `__declval<T>(0)` 计算，效果等同于 `add_rvalue_reference_t<T>`。

¶4 标准的例子 `decltype(static_cast<To>(declval<From>())) convert(From&&);` 展示了 `declval` 与 SFINAE（[[g:sfinae]]）的配合：返回类型中的表达式无效时，`convert` 被排除出候选函数集。

## 整数比较 [utility.intcmp]

```cpp run title="intcmp.cpp" ok
#include <utility>
#include <cstdint>

static_assert(!(-1 < 0u));                      // 内建 <：-1 先被转换成 UINT_MAX
static_assert(std::cmp_less(-1, 0u));           // 数学意义上的比较
static_assert(short{-1} < (unsigned short)0);   // 两边都先提升为 int，结果正确

static_assert(!std::cmp_equal(-1, UINT32_MAX));
static_assert(std::in_range<std::uint8_t>(255));
static_assert(!std::in_range<std::uint8_t>(256));
static_assert(!std::in_range<unsigned>(-1));
int main() {}
```

内建比较运算符先对两个操作数做寻常算术转换（[[g:usual-arithmetic-conversions]]，[[expr.arith.conv]]）。一个操作数有符号、另一个无符号，而无符号类型的等级不低于有符号类型时，有符号的一方被转换成无符号类型，`-1` 变成 `UINT_MAX`。第三行说明这个问题不总是出现：`short` 和 `unsigned short` 都先提升为 `int`。是否出错取决于具体类型的宽度，所以肉眼很难发现。对变量做这种比较时，Clang 的 `-Wsign-compare`（`-Wextra` 包含）会给出警告；上面的常量表达式则没有警告。

¶2 `cmp_equal` 的定义是：两边符号性相同时直接用 `==`，此时转换不会改变数学值；有符号的一方小于 0 时必然不等；否则把有符号的一方转成对应的无符号类型再比较。¶5 `cmp_less` 的结构相同，有符号一方小于 0 时它必然更小。¶3、¶6–¶8 用这两个函数定义另外四个，例如 `cmp_greater(t, u)` 就是 `cmp_less(u, t)`。¶10 `in_range<R>(t)` 判断 `t` 是否落在 `R` 的取值范围内，也就是转换到 `R` 能否保持值不变。

¶1、¶4、¶9 要求所有类型都是有符号或无符号整数类型（*Mandates*，[[basic.fundamental]]）。¶11 注 1 指出，`byte`、`char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 和 `bool` 都不能用：它们是整型，却不属于有符号或无符号整数类型。

```cpp run title="intcmp_char.cpp" error
#include <utility>
int main() {
  bool b1 = std::cmp_less('a', 98);    // error: char 不是有符号或无符号整数类型
  bool b2 = std::cmp_equal(true, 1);   // error: bool 同理
  (void)b1; (void)b2;
}
```

!!! impl "libc++ 把 Mandates 实现成了约束"
    标准写的是 *Mandates*，libc++ 却用模板形参上的概念表达这项要求，诊断因此是 no matching function。区别在于约束可以被探测：在模板中写 `requires (T t) { std::cmp_less(t, 1); }`，libc++ 对 `T = char` 得到 `false`，而按标准这次调用应当是硬错误。可移植的代码不应依赖这种差异。

## `to_underlying` [utility.underlying]

```cpp run title="to_underlying.cpp" ok
#include <utility>
#include <cstdint>
#include <cstdio>
#include <type_traits>

enum class Color : std::uint8_t { red = 1, green = 2 };

int main() {
  auto v = std::to_underlying(Color::green);
  static_assert(std::is_same_v<decltype(v), std::uint8_t>);
  std::printf("%d\n", v);   // 2（uint8_t 作为可变实参提升为 int）
}
```

¶1 `to_underlying(e)` 返回 `static_cast<underlying_type_t<T>>(e)`（[[P1682R3]]）。它只是给一个常见写法起了名字，但有一个实际好处：类型总是对的。手写的 `static_cast<int>(e)` 在有人把枚举的底层类型（[[g:underlying-type]]，[[dcl.enum]]）从 `int` 改成 `std::uint64_t` 后会悄悄截断，`to_underlying` 不会。

标准没有给它写约束。对非枚举类型调用时，`underlying_type_t<T>` 不是合法的类型，替换返回类型时失败，所以实际效果上它对 SFINAE 友好。

## 显式的 UB 与可观察检查点 [utility.undefined]

### `unreachable`（¶1–¶2）

```cpp
[[noreturn]] void unreachable();
```

!!! std
    *Preconditions*: `false` is `true`.

¶1 这个前置条件永远不可能满足，所以调用 `unreachable` 的行为是未定义的（注 1）。标准没有为它发明新机制，而是借用了违反前置条件即为未定义行为的通则（[[structure.specifications]]）。它的效果相当于 GCC 和 Clang 的 `__builtin_unreachable()`、MSVC 的 `__assume(false)`（[[P0627R6]]）。

```cpp run title="unreachable.cpp" ub
#include <utility>
#include <cstdio>

int decode(int tag) {
  switch (tag) {
  case 0: return 10;
  case 1: return 20;
  default: std::unreachable();   // 断言调用方不会传其他值
  }
}

int main(int argc, char**) {
  std::printf("%d\n", decode(argc - 1));   // 不带参数运行时 argc == 1，得到 10
  std::printf("%d\n", decode(argc + 5));   // UB：执行到 unreachable
}
```

它告诉优化器控制流不会到达这里。本机 Clang 23 在 `-O0 -fsanitize=undefined` 下，UBSan 报告 "execution reached an unreachable program point" 并终止；在 `-O2` 下第二行打印了 20：优化器认定 `tag` 只可能是 0 或 1，把 `switch` 化简成了一次比较。

`unreachable()` 与 `[[assume(expr)]]`（[[dcl.attr.assume]]）给优化器的信息相近，`if (!cond) std::unreachable();` 与 `[[assume(cond)]];` 效果类似，但有三点不同：

- `[[assume]]` 中的表达式不求值，副作用不会发生；`if (!cond)` 中的 `cond` 会被求值。
- `[[assume]]` 是属性，表达某个条件成立；`unreachable()` 是一次 `[[noreturn]]` 的函数调用，表达这条路径不存在，可以放在 `default:` 这样的位置。
- 忽略 `[[assume]]` 不改变程序含义，编译器也可以不使用它的信息。

两者都是不检查的承诺，出错的后果由程序员承担。想要一个可以检查的版本，应当写 C++26 的 `contract_assert(cond);`（[[basic.contract]]）或 `assert`。

### `observable_checkpoint` {{c++26}}（¶3）

```cpp
void observable_checkpoint() noexcept;
```

¶3 它建立一个**可观察检查点**（[[g:observable-checkpoint]]，[[intro.abstract]]）。C++26 规定，执行中出现未定义行为时，只有最后一个检查点之后的行为不受约束，之前已经发生的可观察行为必须如实产生。在一段可能有未定义行为的代码之前调用 `std::observable_checkpoint()`，例如在写出日志之后，就能保证这条日志不会因为后面的未定义行为而被优化掉。它和 `unreachable` 正好相对：一个制造未定义行为，一个限制未定义行为的影响范围。

## `<utility>` 里的其他内容 [utility.syn]

概要中还声明或包含了这些内容，规定在别处：

- `#include <compare>` 和 `#include <initializer_list>`，所以只包含 `<utility>` 就能使用 `std::strong_ordering` 和 `std::initializer_list`；
- `integer_sequence`、`index_sequence`、`make_index_sequence` 等（[[intseq]]），以及让 `auto [...is] = std::make_index_sequence<N>{};` 这种结构化绑定包成立的 `tuple_size`、`tuple_element`、`get`；
- `pair` 及其比较、`swap`、`make_pair`、类元组访问（[[pairs]]）；
- 标签类型 `piecewise_construct_t`、`in_place_t`、`in_place_type_t<T>`、`in_place_index_t<I>`，构造函数用它们区分不同的构造方式。它们的默认构造函数都是 `explicit` 的，防止 `{}` 被意外地当作标签；
- `monostate` 及其比较和 `hash<monostate>`（[[variant.monostate]]）。

!!! history "std::rel_ops"
    C++98 的 `<utility>` 提供了 `std::rel_ops`：写好 `==` 和 `<` 之后，`using namespace std::rel_ops;` 就能得到 `!=`、`>`、`<=`、`>=`。它是对所有类型都匹配的无约束模板，一旦引入就会干扰重载决议。C++20 的重写候选（[[over.match.oper]]）让 `a != b` 自动改写成 `!(a == b)`，`<=>` 一个运算符就能导出四个关系运算符，`rel_ops` 因此被弃用，移到了附录 [[depr.relops]]。它仍在标准中，实现必须提供；本机 libc++ 在使用它的运算符时给出 `-Wdeprecated-declarations` 警告。

## 常见误解

!!! pitfall "以为 `declval` 可以用在 `if constexpr` 的条件里"
    `if constexpr` 的条件是一个常量表达式，会被求值，不是未求值操作数。在那里调用 `declval` 同样是 ODR 使用，程序非良构。需要时把它包进 `decltype`、`sizeof` 或 `requires`。

!!! pitfall "对同一个对象 `forward` 或 `move` 两次"
    第一次之后对象可能已经被移走，处于有效但未指定的状态（[[g:valid-but-unspecified-state]]）。完美转发时，每个形参应当只被 `std::forward` 一次。

!!! pitfall "把 `unreachable` 当作断言"
    发布构建中它不会报告任何东西，只会让优化器做出更激进的假设。需要在调试时报错，用 `assert` 或 `contract_assert`。

## 思考题

!!! question "思考题 1"
    下面的 `wrapper` 想把实参完美转发给 `g`。写成 `std::forward<T&&>` 有问题吗？
    ```cpp
    template<class T> void wrapper(T&& x) { g(std::forward<T&&>(x)); }
    ```

<details markdown="1">
<summary>答案</summary>

结果是正确的，只是写法多余。实参为左值时 `T = A&`，`T&&` 折叠为 `A&`，`forward<A&>(x)` 返回 `A&`；实参为右值时 `T = A`，`T&&` 为 `A&&`，`forward<A&&>(x)` 返回 `A&&`，与 `forward<A>(x)` 相同。根据 [[dcl.ref#7]] 的引用折叠，两种写法在转发引用中等价。惯用写法是 `std::forward<T>(x)`；对 `auto&&` 变量写 `std::forward<decltype(x)>(x)`，原理相同。
</details>

!!! question "思考题 2"
    `std::cmp_less(x, y)` 和内建的 `x < y` 在下面三种情况下可能得到不同结果吗？`int x, long long y`；`unsigned x, long long y`；`unsigned long long x, long long y`。

<details markdown="1">
<summary>答案</summary>

第一种不会：两边都有符号，第 5 段的第一个分支就是 `t < u`。第二种在 `long long` 比 `unsigned` 宽的平台上（几乎所有平台）也不会：寻常算术转换把 `unsigned` 转成 `long long`，数学值不变。第三种会：两者等级相同，`long long` 一方被转换成 `unsigned long long`。例如 `y = -1` 时它变成 `ULLONG_MAX`，内建的 `x < y` 对除 `ULLONG_MAX` 以外的所有 `x` 都为真，而 `cmp_less(x, -1)` 总是假。规则见 [[expr.arith.conv#1]]。
</details>

!!! question "思考题 3"
    为什么 `declval` 的返回类型写成 `add_rvalue_reference_t<T>` 而不是 `T&&`？

<details markdown="1">
<summary>答案</summary>

`T` 可能是 `void`（或带 cv 的 `void`），也可能是带 cv 或引用限定的函数类型，如 `int() const`。这些都不是可引用类型（[[g:referenceable-type]]），写 `T&&` 会造成替换失败。`add_rvalue_reference_t<T>` 对不可引用类型原样返回 `T`，于是 `decltype(declval<void>())` 是合法的，可以出现在元编程中。对可引用类型，两种写法完全相同。
</details>
