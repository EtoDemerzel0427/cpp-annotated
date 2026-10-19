---
title: 类模板 optional
summary: optional<T> 主模板的完整规格：存储模型、各个构造函数的约束、特殊成员何时平凡、赋值与 emplace 的异常保证、访问值的几种方式、单子操作和 C++26 的范围支持。
status: draft
covers: *
papers: P0220R1, P0602, P0848, P0798, P3168, P2988, P3471
related: optional, optional.optional.ref, expected.expected, variant.variant, class.union, class.prop, class.dtor, special, class.copy.ctor, dcl.init.general, structure.specifications, basic.life, over.match.best
tags: 标准库, optional, 平凡性, 特殊成员函数, 单子操作, 加固
updated: 2026-10-19
---

!!! tldr
    - `optional<T>` 在自身内部存放一个 `T` 和一个有无值的标志，不做堆分配；有值就是内部那个联合体成员处于活跃状态。
    - `optional<T>` 能否从某个类型隐式构造，跟 `T` 能否从它隐式转换一致；`T` 本身就能从 `optional<U>` 构造时（如 `std::any`），转换构造函数让路，`bool` 例外。
    - `T` 平凡可复制时 `optional<T>` 也平凡可复制，可以 `memcpy`、在寄存器里传递。
    - 赋值或 `swap` 抛出异常时 `has_value()` 不变；`emplace` 抛出异常后 optional 为空，旧值已经销毁。
    - `*o` 和 `o->` 在 C++26 有加固前置条件：加固实现检查并终止，否则是 UB；`value()` 无值时抛 `bad_optional_access`。

`optional<T>` 表示一个也许不存在的 `T`。总览、比较运算符和 `hash` 见 [[optional]]；C++26 的引用偏特化 `optional<T&>` 见 [[optional.optional.ref]]。

## 存储：一个联合体加一个标志 [optional.optional.general]

```cpp run ok
#include <cassert>
#include <optional>
#include <string>

int main() {
  std::optional<std::string> o;      // 空
  assert(!o.has_value());
  o = "hi";                          // 在 o 内部构造一个 string
  assert(o && *o == "hi");
}
```

规范用一个仅用于说明（exposition only）的匿名联合体描述存储：

```cpp
template<class T>
class optional {
  // …
private:
  union {
    remove_cv_t<T> val;       // exposition only
  };
};
```

¶1 当且仅当成员 *val* 是联合体的活跃成员（[[class.union]]）时，说 `optional<T>` **含有值**（contains a value），*val* 称为它的**被包含值**（contained value）。被包含值嵌套于（nested within，[[intro.object]]）optional 对象之中，所以它的存储就在 optional 对象里，不在堆上。

联合体在这里的作用是抑制自动的构造和析构：联合体成员不会被隐式构造，也不会被隐式销毁。何时在这块存储上创建 `T`、何时调用 `val.~T()`，完全由 optional 自己的成员函数决定。

*val* 的类型是 `remove_cv_t<T>` 而不是 `T`。对 `optional<const int>`，存储里放的是 `int`，`emplace` 等操作在同一块存储上销毁旧值、构造新值时，不会遇到在 const 对象的存储上重建对象这类 [[basic.life]] 的限制。公开接口仍然按 `T` 返回，用户看到的是 `const int&`。

### 哪些类型可以放进 optional（¶2）

¶2 如果 `X` 是左值引用类型，或者是完整的非数组对象类型，并且 `remove_cvref_t<X>` 不是 `in_place_t` 或 `nullopt_t`，`X` 就是 optional 的**合法被包含类型**（[[g:valid-contained-type]]）。用其他类型实例化 `optional` 的程序是非良构的，编译器必须报错。

| 类型 | 能否放进 optional | 原因 |
|---|---|---|
| `void`、函数类型 | 不能 | 不是对象类型 |
| `int[3]` | 不能 | 数组不能复制初始化和赋值，接口对不上 |
| `int&&` | 不能 | 右值引用被排除 |
| `int&` | C++26 起可以 | 由偏特化 [[optional.optional.ref]] 处理 |
| `nullopt_t`、`in_place_t` | 不能 | 它们是构造函数的标签，否则 `optional<nullopt_t>(nullopt)` 有歧义 |

此外，对象类型 `T` 必须满足 *Cpp17Destructible*。这是一条普通的库要求，违反它是 {{ub}}（[[res.on.functions]]），标准不保证诊断。libc++ 在类内用一串 `static_assert` 检查上面这些条件，实践中总能得到清楚的报错。

## 构造函数 [optional.ctor]

### 空 optional（¶2–3）

`optional()` 与 `optional(nullopt_t)` 都是 `noexcept` 的，构造出的对象不含值。

¶3 这两个构造函数不初始化被包含值。对每一个对象类型 `T`，它们都是 constexpr 构造函数，包括 `T` 不是字面类型的情况，因为 `T` 的构造函数根本没有被调用。所以 `constinit std::optional<std::mutex> m;` 一定是静态初始化。

### 复制与移动（¶4–12）

¶4 复制构造时，如果 `rhs` 有值，就用 `rhs.`*val* **直接非列表初始化**（[[g:direct-non-list-initialization]]）自己的 *val*，也就是 `T val(rhs.val);` 这种形式。

¶7 如果 `is_copy_constructible_v<T>` 为假，复制构造函数被定义为弃置（deleted）的；如果 `T` 可平凡复制构造，它是平凡的。

¶8 移动构造函数的写法不同，用的是 *Constraints*：`is_move_constructible_v<T>` 为假时，它不参与重载决议。弃置的函数仍然参与重载决议，被选中才报错；不满足 *Constraints* 的函数根本不是候选（[[structure.specifications]]）。所以 `T` 不可移动但可复制时，右值 optional 会退而使用复制构造函数，这和核心语言对没有移动构造函数的类的处理一致（[[class.copy.ctor]]）。

¶9 移动之后 `rhs.has_value()` 不变：被移动的 optional 仍然有值，只是那个值处于被移出的状态。¶12 移动构造函数的 `noexcept` 等价于 `is_nothrow_move_constructible_v<T>`，`T` 可平凡移动构造时它是平凡的。

### `in_place` 构造（¶13–22）

`optional(in_place_t, Args&&...)` 和带 `initializer_list` 的版本用给定的实参直接构造 *val*，可以构造不可移动的类型。它们总是 `explicit` 的。¶17、¶22 规定，如果为初始化选中的 `T` 的构造函数是 constexpr 的，这个构造函数也是。

```cpp
std::optional<std::mutex> m(std::in_place);          // 在 optional 内部构造 mutex
std::optional<std::vector<int>> v(std::in_place, {1, 2, 3});
```

### 从一个值构造（¶23–27）

最常用的是这个构造函数，`std::optional<std::string> s = "abc";` 用的就是它：

```cpp
template<class U = remove_cv_t<T>>
  constexpr explicit(see below) optional(U&& v);
```

¶27 `explicit` 中的条件等价于 `!is_convertible_v<U, T>`。换句话说，`T` 能从 `U` 隐式转换，`optional<T>` 就能从 `U` 隐式构造；`T` 的对应构造函数是 explicit 的，这个构造函数也是。

```cpp run error
#include <optional>
#include <string>
#include <vector>

std::optional<std::string> s = "abc";       // OK
std::optional<std::vector<int>> v1{3};      // OK：直接初始化
std::optional<std::vector<int>> v2 = 3;     // error: vector(size_t) 是 explicit 的
int main() {}
```

¶23 它有四条约束：

- ¶23.1 `is_constructible_v<T, U>`；
- ¶23.2 `remove_cvref_t<U>` 不是 `in_place_t`，否则会抢走 `optional(in_place)` 这样的调用；
- ¶23.3 `remove_cvref_t<U>` 不是这个 optional 类型本身，否则非 const 左值 `optional&` 匹配 `U&&` 比匹配 `const optional&` 更好，会抢走复制构造；
- ¶23.4 如果 `T` 是 cv `bool`，`remove_cvref_t<U>` 不是 `optional` 的特化。

¶23.4 的原因是 `bool` 可以经由 `explicit operator bool` 从 `optional<int>` 直接初始化，`is_constructible_v<bool, optional<int>>` 为真。没有这一条，`std::optional<bool> b{std::optional<int>{}}` 会得到一个含有 `false` 的 optional，而人们期望的是空 optional 转换成空 optional。

默认模板实参 `U = remove_cv_t<T>` 用于实参是花括号列表、`U` 无法推导的情况，例如 `std::optional<const Foo> o({1, 2});`。这时参数类型是 `Foo&&`，`{1, 2}` 先构造一个临时 `Foo`，再从它移动构造 *val*。如果默认值是 `T`，参数类型是 `const Foo&&`，只能复制。本机 libc++ 23 的这个构造函数仍然写成 `_Up = _Tp`，上面这行代码调用的是 `Foo` 的复制构造函数。

### 从另一个 optional 转换（¶1、¶28–37）

```cpp
template<class U> constexpr explicit(see below) optional(const optional<U>& rhs);
template<class U> constexpr explicit(see below) optional(optional<U>&& rhs);
```

这两个构造函数逐值转换：`rhs` 为空则结果为空，否则用 `*rhs` 构造 *val*。¶30、¶35 规定 `rhs.has_value()` 不变；¶32、¶37 的 `explicit` 条件分别是 `!is_convertible_v<const U&, T>` 和 `!is_convertible_v<U, T>`。

难点在于有些 `T` 本身就能从整个 `optional<U>` 构造，最典型的是 `std::any`：

```cpp run ok
#include <any>
#include <cassert>
#include <optional>

int main() {
  std::optional<int> empty;

  std::optional<std::any> a = empty;
  assert(a.has_value());             // 装着一个空 optional<int> 的 any
  assert(a->type() == typeid(std::optional<int>));

  std::optional<bool> b = empty;     // bool 例外：空就是空
  assert(!b.has_value());

  std::optional<long> c = std::optional<int>(42);
  assert(c && *c == 42);             // 普通情况：逐值转换
}
```

`optional<any>` 从 `optional<int>` 构造有两种说得通的语义：逐值转换，或者把整个 `optional<int>` 装进 `any`。标准选了后者，理由是保持与 `T` 本身一致：`std::any x = empty;` 本来就是把 `optional<int>` 装进去。

¶1 为此标准定义了一个仅用于说明的变量模板 *converts-from-any-cvref*`<T, W>`：`T` 能否从 `W&`、`W`、`const W&`、`const W` 中的任何一种构造或隐式转换而来。¶28.2 和 ¶33.2 规定，如果 `T` 不是 cv `bool`，*converts-from-any-cvref*`<T, optional<U>>` 必须为假。于是 `T = std::any` 时转换构造函数不参与重载决议，剩下 `optional(U&&)` 把整个 `optional<int>` 交给 `any`。

`bool` 例外，因为 `bool` 能从 `optional<U>` 初始化只是 `explicit operator bool` 的副作用，没有人想把有无值变成一个 `bool` 值。配合 ¶23.4，`optional<bool>` 从 `optional<U>` 构造时只会走逐值转换。[[expected.expected]] 也借用了 *converts-from-any-cvref*。

!!! impl "libc++：两套重载代替 explicit(bool)"
    libc++ 的 `<optional>` 还要支持 C++17，而 `explicit(bool)` 是 C++20 才有的。所以这些条件 explicit 的构造函数都写成两个重载，一个隐式、一个 `explicit`，用互斥的 `enable_if` 条件启用。其中 `__check_constructible_from_opt` 就是 *converts-from-any-cvref*。`optional(U&&)` 还加了标准没有要求的 `noexcept`，库实现可以给非虚函数加强异常规格（[[res.on.exception.handling]]）。

## 特殊成员何时平凡

```cpp run ok
#include <optional>
#include <string>
#include <type_traits>

static_assert(std::is_trivially_copyable_v<std::optional<int>>);
static_assert(!std::is_trivially_copyable_v<std::optional<std::string>>);
int main() {}
```

一个类是**平凡可复制**的（[[g:trivially-copyable-class]]），当且仅当它至少有一个合格的复制或移动操作，所有合格的复制、移动操作都是平凡的，而且析构函数平凡且未被弃置（[[class.prop]]）。平凡可复制的类型可以用 `memcpy` 复制，可以用于 `std::bit_cast` 和 `std::atomic`。在 Itanium C++ ABI 下，它还可以放在寄存器里传递和返回，返回 `optional<int>` 的函数和返回 `struct { int v; bool b; }` 的函数生成同样的代码。

标准把各特殊成员的平凡条件分散写在 *Remarks* 里：

| 特殊成员 | 何时平凡 | 出处 |
|---|---|---|
| 复制构造 | `T` 可平凡复制构造 | [[optional.ctor#7]] |
| 移动构造 | `T` 可平凡移动构造 | [[optional.ctor#12]] |
| 析构 | `T` 可平凡析构 | [[optional.dtor#2]] |
| 复制赋值 | `T` 可平凡复制构造、平凡复制赋值、平凡析构 | [[optional.assign#7]] |
| 移动赋值 | `T` 可平凡移动构造、平凡移动赋值、平凡析构 | [[optional.assign#13]] |

赋值的条件里多了平凡析构，因为赋值在 `rhs` 为空时要销毁 `*this` 的值，平凡的赋值不会去调用析构函数。五条合在一起，`T` 平凡可复制就意味着 `optional<T>` 平凡可复制。C++17 最初的规格没有这些保证，是 [[P0602]] 补上的。

[optional.dtor] 本身只有两段。¶1 如果 `T` 不可平凡析构而 `*this` 有值，析构函数调用 *val*`.T::~T()`；¶2 `T` 可平凡析构时这个析构函数是平凡的。

### 怎样让类模板的特殊成员有条件地平凡

`T = std::string` 时，析构函数必须写成 `if (engaged) val.~T();`；`T = int` 时，它又必须是平凡的。可是用户提供的函数永远不平凡，哪怕函数体为空。

C++20 的 [[P0848]] 解决了这个问题。一个类可以声明多个带不同约束的预期析构函数（[[g:prospective-destructor]]，见 [[class.dtor]]），以及多个复制、移动构造函数；类完整时，满足约束且最受约束的那个成为**合格**的特殊成员（[[g:eligible-special-member-function]]，见 [[special]]），平凡性只看合格的那个：

```cpp run ok
#include <memory>
#include <string>
#include <type_traits>

template<class T>
class Opt {
  union { T val; };
  bool engaged = false;
public:
  constexpr Opt() noexcept {}
  constexpr Opt(const T& v) : val(v), engaged(true) {}

  // 两个预期析构函数，由约束决定选哪个
  constexpr ~Opt()
    requires std::is_trivially_destructible_v<T>
    = default;
  constexpr ~Opt() { if (engaged) val.~T(); }

  // 两个复制构造函数：平凡版本和手写版本
  Opt(const Opt&)
    requires std::is_trivially_copy_constructible_v<T>
    = default;
  constexpr Opt(const Opt& o) : engaged(o.engaged) {
    if (engaged)
      std::construct_at(std::addressof(val), o.val);
  }
  Opt& operator=(const Opt&) = delete;  // 赋值同理，从略
};

static_assert(std::is_trivially_destructible_v<Opt<int>>);
static_assert(std::is_trivially_copy_constructible_v<Opt<int>>);
static_assert(!std::is_trivially_destructible_v<Opt<std::string>>);

int main() {
  Opt<std::string> a(std::string(100, 'x'));
  Opt<std::string> b = a;
}
```

`T = int` 时两个析构函数都满足约束，带约束的那个更受约束，被选中；`T = std::string` 时只有无约束的那个满足。

!!! impl "libc++：基类阶梯"
    C++17 没有受约束的特殊成员，只能靠基类分派。libc++ 的 `optional<T>` 至今沿用这种写法（它还要服务 C++17 模式，改继承结构也会影响 ABI）：一条继承链上每一层只负责一种特殊成员，用一个 `bool` 模板参数在 `= default` 的平凡版本和手写版本之间选择，例如 `__optional_destruct_base<T, is_trivially_destructible<T>>`、`__optional_copy_base`、`__optional_copy_assign_base` 等。`optional<T>` 自己的特殊成员全部 `= default`，是否平凡由基类决定。后来编写的 `<expected>` 直接用了 C++20 的受约束写法。

    这种写法有一个边角缺陷。按标准推导，`optional<const int>` 应当是平凡可复制的：复制赋值被弃置，不算合格，其余合格的操作都平凡。但本机 libc++ 23 给出 `is_trivially_copyable_v<std::optional<const int>>` 为假，理由是某个基类不可平凡复制：负责复制赋值的那一层因为 `const int` 不可平凡复制赋值而选了手写版本，真正弃置赋值的是更外层的基类，中间那层留下了一个合格且非平凡的复制赋值。

## 赋值 [optional.assign]

### 复制赋值与移动赋值（¶1–13）

¶1 `o = nullopt` 在有值时销毁值，否则什么也不做，和 `reset()` 等价。

复制赋值和移动赋值的效果由一张 2×2 的表规定（¶4 的表 67、¶9 的表 68）：

| | `*this` 有值 | `*this` 无值 |
|---|---|---|
| `rhs` 有值 | 把 `rhs.`*val* 赋值给 *val* | 用 `rhs.`*val* 直接非列表初始化 *val* |
| `rhs` 无值 | 调用 *val*`.T::~T()` 销毁 | 无操作 |

两边都有值时调用的是 `T` 的赋值运算符，而不是先销毁再构造，这保留了 `T` 自己的赋值语义，例如 `std::vector` 赋值时复用已有的容量。

¶7、¶13 规定了异常保证：抛出异常时 `this->has_value()` 的结果不变。optional 不会因为异常丢掉一个值或多出一个值；值本身处于什么状态，由 `T` 的构造函数或赋值运算符的异常保证决定。

¶7 复制赋值除非 `T` 既可复制构造又可复制赋值，否则被定义为弃置，因为表中两种操作都可能用到。¶8 移动赋值用的是 *Constraints*，¶12 它的 `noexcept` 等价于 `is_nothrow_move_assignable_v<T> && is_nothrow_move_constructible_v<T>`。

### 从一个值赋值，以及 `o = {}`（¶14–18）

```cpp
template<class U = remove_cv_t<T>> constexpr optional& operator=(U&& v);
```

¶15 有值时把 `v` 赋给 *val*，否则用 `v` 构造 *val*。¶14 的约束中，¶14.1、¶14.3、¶14.4 很直接：`U` 不是这个 optional 类型，`T` 能从 `U` 构造，`T&` 能从 `U` 赋值。

¶14.2 要求 `conjunction_v<is_scalar<T>, is_same<T, decay_t<U>>>` 为假，它专门为 `o = {}` 而设：

```cpp run ok
#include <cassert>
#include <optional>
#include <string>

int main() {
  std::optional<int> i = 5;
  i = {};                     // 重置
  assert(!i);

  std::optional<std::string> s = "hello";
  s = {};                     // 也是重置
  assert(!s);
}
```

`{}` 无法推导 `U`，所以 `U` 取默认值 `remove_cv_t<T>`。如果 `T` 是 `int` 这样的标量，`operator=(int&&)` 从 `{}` 得到 `0` 只需标准转换，比 `operator=(optional&&)` 需要的用户定义转换更好，`i = {}` 就会变成存入 0。¶14.2 把这个候选排除掉。`T` 不是标量时，两个候选都需要用户定义转换、不分上下，[[over.match.best]] 规定非模板优于模板，`operator=(optional&&)` 胜出，结果同样是重置。

### 从另一个 optional 赋值（¶19–28）

约束比对应的构造函数更多。除了 `T` 能从 `*rhs` 构造和赋值、*converts-from-any-cvref*`<T, optional<U>>` 为假之外，¶19.4–¶19.7 还要求 `T&` 不能从 `optional<U>` 的四种 cv、引用形式赋值。道理和构造相同：`T` 本身能接收整个 `optional<U>` 时（例如 `std::any`），这个运算符让路，交给 `operator=(U&&)`。这里没有 `bool` 例外，因为 `bool` 不能从 `optional<U>` 赋值。效果见表 69、表 70，结构与复制赋值一致。

### `emplace`（¶29–40）

```cpp
template<class... Args> constexpr T& emplace(Args&&... args);
```

¶30 `emplace` 先执行 `*this = nullopt`，再用实参直接构造 *val*；¶32 返回 *val* 的引用，可以写 `auto& x = o.emplace(...)`。

¶34 如果 `T` 的构造函数抛出异常，`*this` 不含值，之前的值（如果有）已经销毁。这只是基本保证：`emplace` 的意义是原地构造，不允许新旧两个值同时存在。需要强保证时，先构造好一个 `T`，再 `o = std::move(t)`。相比之下，[[expected.expected]] 的 `emplace` 要求构造是 `noexcept` 的，以维持它永远有值的不变式。

## swap [optional.swap]

¶1 `swap` 要求 `is_move_constructible_v<T>`，这是 *Mandates*，不满足则非良构；¶2 还要求 `T` 满足 *Cpp17Swappable*（[[swappable.requirements]]）。效果见表 71：

- 两边都有值，调用 `swap(val, rhs.val)`，这个 `swap` 经由实参依赖查找找到；
- 只有一边有值，把值移动构造到另一边，再销毁原处的值；
- 两边都无值，什么也不做。

¶5 `noexcept` 等价于 `is_nothrow_move_constructible_v<T> && is_nothrow_swappable_v<T>`。¶6 抛出异常时两边的 `has_value()` 都不变。

## 访问值 [optional.observe]

### `*` 和 `->`：加固前置条件（¶1–8）

```cpp
constexpr T& operator*() & noexcept;         // 另有 const&、&&、const&& 版本
constexpr T* operator->() noexcept;          // 另有 const 版本
```

¶1、¶4、¶7 规定它们都有**加固前置条件**（hardened precondition）`has_value()`。按 [[structure.specifications]]，在**加固实现**（[[g:hardened-implementation]]，由实现定义是否开启）中，调用前先检查这个条件，违反时以终止程序的语义处理契约违反；在非加固实现中，违反它是 {{ub}}。

```cpp
#include <cstdio>
#include <optional>

int main() {
  std::optional<int> o;
  try {
    (void)o.value();          // 抛 bad_optional_access
  } catch (const std::bad_optional_access&) {
    std::puts("caught");
  }
  int x = *o;                 // 违反加固前置条件
  std::printf("%d\n", x);
}
```

本机 libc++ 23 默认（非加固）编译，程序打印一个无意义的值后正常退出。加上 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 后，程序在 `*o` 处陷入（SIGTRAP）；用 `_LIBCPP_HARDENING_MODE_DEBUG` 则先打印一条说明 `operator*` 作用于空 optional 的消息再终止。这是 C++26 标准库加固（[[P3471]]）的一部分。

¶2 `operator->` 返回 `addressof(val)`，不用 `&val`，以免 `T` 重载了一元 `&`。¶8 右值版本的 `*` 返回 `std::move(val)`，类型是 `T&&`。

!!! ub "右值 optional 的 `*` 会产生悬垂引用"
    ```cpp
    std::optional<std::string> make();
    const std::string& s = *make();   // 引用绑定到临时 optional 的内部
    std::puts(s.c_str());             // UB：临时 optional 已经销毁
    ```
    `*make()` 是一次返回 `std::string&&` 的函数调用，不是直接绑定到临时对象，所以不会延长临时 optional 的生存期（[[class.temporary]]）。`value()` 的右值重载也一样。应当按值接住（`std::string s = *make();`），或者先把 optional 存进变量。

### `has_value`、`operator bool`、`value()`（¶9–14）

¶9–12 `has_value()` 和 `operator bool` 都返回是否有值。`operator bool` 是 `explicit` 的，所以 `if (o)`、`!o` 可以写，`int n = o;` 不行（[[g:contextually-converted-to-bool]]）。

¶13 `value()` 的效果等价于：

```cpp
return has_value() ? val : throw bad_optional_access();
```

`value()` 没有前置条件，行为总是有定义的。在独立实现（没有操作系统支持的实现）中它是弃置的，概要里标注为 *freestanding-deleted*。两者的分工是：`*o` 用于确信有值的场合，没有检查开销（加固后变成检查加终止）；`value()` 用于希望无值时抛异常、交给上层处理的场合。

### `value_or`（¶15–18）

```cpp
template<class U = remove_cv_t<T>> constexpr T value_or(U&& v) const &;
template<class U = remove_cv_t<T>> constexpr T value_or(U&& v) &&;
```

¶16 效果等价于 `has_value() ? val : static_cast<T>(std::forward<U>(v))`。¶15 要求 `T` 可复制构造且 `U&&` 可隐式转换为 `T`，右值版本（¶17）要求 `T` 可移动构造。这些是 *Mandates*，不满足时是硬错误，不是替换失败。

`value_or` 按值返回 `T`，即使 optional 有值也会复制一份，对大对象可以改写成 `o ? *o : fallback`。默认实参 `U = remove_cv_t<T>` 让 `o.value_or({})` 成立：`{}` 无法推导，参数类型就是 `T&&`，从 `{}` 值初始化。

## 单子操作 [optional.monadic] {{c++23}}

```cpp run ok
#include <cassert>
#include <optional>
#include <type_traits>

struct Pinned {               // 既不能复制也不能移动
  int v;
  explicit Pinned(int x) : v(x) {}
  Pinned(Pinned&&) = delete;
};

struct Point { int x, y; };

int main() {
  // and_then：f 自己返回 optional，用于可能失败的下一步
  auto half = [](int i) -> std::optional<int> {
    if (i % 2) return std::nullopt;
    return i / 2;
  };
  assert(std::optional(8).and_then(half).and_then(half) == 2);
  assert(!std::optional(6).and_then(half).and_then(half));

  // transform：结果直接在新 optional 里构造，不要求可移动
  std::optional<int> o = 21;
  auto p = o.transform([](int i) { return Pinned(i * 2); });
  assert(p->v == 42);

  // C++26：f 返回左值引用，结果是 optional<int&>
  std::optional<Point> pt = Point{1, 2};
  auto rx = pt.transform([](Point& q) -> int& { return q.x; });
  static_assert(std::is_same_v<decltype(rx), std::optional<int&>>);
  *rx = 100;
  assert(pt->x == 100);

  // or_else：f 无参，返回同类型的 optional
  auto r = std::optional<int>{}.or_else(
      [] { return std::optional<int>(-1); });
  assert(r == -1);
}
```

[[P0798]] 加入了三个成员函数，让一串可能失败的计算不必写成层层嵌套的 `if`。`and_then` 和 `transform` 各有 `&`、`const&`、`&&`、`const&&` 四个重载，区别只在于把 *val* 以什么值类别交给 `f`；`or_else` 只有 `const&` 和 `&&` 两个。

### `and_then`（¶1–6）

¶1 令 `U` 为 `invoke_result_t<F, decltype((val))>`。¶2 要求 `remove_cvref_t<U>` 是 `optional` 的特化（*Mandates*）。¶3 有值时返回 `invoke(std::forward<F>(f), val)`，否则返回空的 `remove_cvref_t<U>`。结果的值类型可以和原 optional 不同。

### `transform`（¶7–12）

¶7 令 `U` 为 `remove_cv_t<invoke_result_t<F, decltype((val))>>`。¶8 要求 `U` 是合法被包含类型，并且声明 `U u(invoke(std::forward<F>(f), val));` 良构。注 1 说明，不要求 `U` 可移动。

¶9 有值时，返回一个 `optional<U>`，它的被包含值以 `invoke(std::forward<F>(f), val)` 直接非列表初始化。标准没有写成等价于 `return optional<U>(in_place, invoke(...));`，因为那样 `invoke` 返回的纯右值要先绑定到 `in_place` 构造函数的引用参数上，被物化成临时对象，再从它移动构造 *val*，于是要求 `U` 可移动。按现在的写法，纯右值直接初始化目标对象（[[dcl.init.general]]），上例中不可移动的 `Pinned` 也能作为结果。

!!! impl "libc++ 如何做到直接初始化"
    一个函数调用的纯右值一旦经过函数参数传递就会被物化，普通的构造函数接口做不到直接初始化。libc++ 给 `optional` 加了一个私有的标签构造函数，把 `f` 和实参一路传到存储基类，在成员初始化器里写 `__val_(std::invoke(std::forward<_Fp>(__f), ...))`，纯右值就直接初始化了 `__val_`。`<expected>` 用的是同一个技巧。

C++26 起左值引用也是合法被包含类型，所以 `f` 返回 `int&` 时 `U = int&`，结果是 `optional<int&>`（上例）。在 C++23 中这违反 *Mandates*，是硬错误。`f` 返回 `void`、数组、`nullopt_t` 或右值引用仍然违反 *Mandates*。

### `or_else`（¶13–18）

¶13 要求 `F` 满足 `invocable`（无参可调用），`T` 满足 `copy_constructible`（右值版本 ¶16 为 `move_constructible`），这些是 *Constraints*。¶14 要求 `f()` 的返回类型去掉 cv 和引用后正好是这个 `optional<T>`，这是 *Mandates*。¶15 有值时返回 `*this` 的副本，否则返回 `f()`。

因为 `or_else` 的部分条件是 *Constraints*，`requires { o.or_else(g); }` 能对不可无参调用的 `g` 给出 `false`；而 `and_then` 和 `transform` 只有 *Mandates*，返回类型不对时只能得到硬错误。所以单子操作不适合用来做替换失败式的探测。

## 范围支持 [optional.iterators] {{c++26}}

```cpp
#include <cstdio>
#include <optional>
#include <ranges>

int main() {
  std::optional<int> o = 7;
  for (int& v : o) v *= 6;          // 0 次或 1 次迭代
  std::printf("%d\n", *o);

  std::optional<int> e;
  for (int v : e) std::printf("never %d\n", v);
  static_assert(std::ranges::contiguous_range<std::optional<int>>);
  static_assert(std::ranges::view<std::optional<int>>);
  std::printf("%zu %zu\n", std::ranges::size(o), std::ranges::size(e));
}
```

C++26 起 `optional<T>` 是一个最多含一个元素的范围（[[P3168]]）。¶1 `iterator` 和 `const_iterator` 是实现定义的类型，满足 `contiguous_iterator`，值类型是 `remove_cv_t<T>`，引用类型分别是 `T&` 和 `const T&`。¶2 容器迭代器的全部要求同样适用。

¶4 有值时 `begin()` 指向被包含值，否则是尾后迭代器；¶5 `end()` 返回 `begin() + has_value()`，把 `bool` 当作 0 或 1 加上去。¶3 任何初始化或销毁被包含值的操作都会使指向这个 optional 的所有迭代器失效。

[[optional]] 中 `enable_view<optional<T>>` 为真，所以 optional 可以直接放进管道，例如 `opt | std::views::transform(f)`。它和 `views::single` 的区别是可以为空、可以就地修改。

本机 libc++ 23 把这部分放在实验性开关之后，要加 `-fexperimental-library` 才能编译上例，输出 `42` 和 `1 0`；不加时 `for (int& v : o)` 找不到 `begin`。所以上例没有标判定。

## 修改器与 constexpr [optional.mod]

¶1 `reset()` 在有值时调用 *val*`.T::~T()`，否则什么也不做；¶2 之后 optional 不含值。它是 `noexcept` 的。

`optional<T>` 的每个成员函数都声明为 `constexpr`，实际能否在常量求值中使用取决于它调用的 `T` 的操作。实现用 `std::construct_at` 和 `std::destroy_at`（[[specialized.construct]]）完成存储上的构造和销毁，它们在常量求值中合法：

```cpp run ok
#include <optional>
#include <string>

constexpr std::size_t f() {
  std::optional<std::string> s;
  s.emplace("constexpr");
  s = std::nullopt;
  s = "again";
  return s->size();
}
static_assert(f() == 5);

constexpr std::optional<int> g = 42;
static_assert(*g == 42 && g.value_or(0) == 42);
int main() {}
```

在常量求值中解引用空 optional 会读取联合体的非活跃成员，这是核心语言的 UB，所以那样的表达式不是常量表达式（[[expr.const]]），编译器必须报错。

## 常见误解

!!! pitfall "被移出的 optional 是空的"
    `auto b = std::move(a);` 之后 `a.has_value()` 不变（¶9）。`a` 里是一个被移出状态的 `T`，不是空 optional。想清空就显式调用 `a.reset()`。

!!! pitfall "`optional<T>` 可以代替可空指针参数"
    `optional<T>` 拥有并内嵌它的值，复制 optional 就复制值。`f(std::optional<BigObject>)` 每次调用都会复制大对象。这时应当用 `const BigObject*`，或者 C++26 的 `optional<const BigObject&>`（[[optional.optional.ref]]）。

!!! pitfall "`optional<double>` 只比 `double` 多一个字节"
    额外的 `bool` 加上对齐填充，`sizeof(optional<double>)` 通常是 16。大数组里存 `optional<T>` 可能让内存翻倍，可以考虑哨兵值或单独的位图。

## 思考题

!!! question "思考题 1"
    `std::optional<std::any> a = std::optional<int>{};` 之后 `a.has_value()` 是什么？把 `std::any` 换成 `bool` 呢？哪几条约束决定了这两个结果？

<details markdown="1">
<summary>答案</summary>

`optional<any>` 有值。`std::any` 能从 `optional<int>` 的任何形式构造，*converts-from-any-cvref*`<any, optional<int>>` 为真，¶28.2 和 ¶33.2 使两个转换构造函数不参与重载决议。剩下 `optional(U&&)`，`U = optional<int>`，¶23.3 只排除 `optional<any>` 自身，于是 *val* 被初始化为装着空 `optional<int>` 的 `any`。

`optional<bool>` 无值。¶28.2 对 cv `bool` 不生效，转换构造函数可行；¶23.4 又排除了 `optional(U&&)`。所以逐值转换，空变成空。
</details>

!!! question "思考题 2"
    如果 `transform` 的 *Returns* 写成等价于 `return optional<U>(in_place, invoke(std::forward<F>(f), val));`，哪类 `f` 会失效？

<details markdown="1">
<summary>答案</summary>

返回不可移动类型的 `f`，例如返回持有 `std::mutex` 的类，或者像 `Pinned` 那样删除了移动构造函数的类。`in_place` 构造函数的参数是转发引用，`invoke(...)` 的纯右值绑定到它时被物化为临时对象，*val* 再从这个临时对象移动构造。现在的写法要求 *val* 直接以 `invoke(...)` 初始化，纯右值直接构造目标对象，注 1 也点明不要求 `U` 可移动。
</details>

!!! question "思考题 3"
    `optional<unique_ptr<int>>` 是平凡可复制的吗？

<details markdown="1">
<summary>答案</summary>

不是。`unique_ptr` 的移动构造和析构都不平凡，按 [[optional.ctor#12]] 和 [[optional.dtor#2]]，`optional<unique_ptr<int>>` 的移动构造和析构也不平凡，而平凡可复制要求析构函数平凡。
</details>
