---
title: 类模板 optional
summary: optional<T> 主模板逐条精读：合法被包含类型、converts-from-any-cvref 与转换构造的约束清单、explicit(see below)、条件平凡的特殊成员（以及 libc++ 的基类阶梯与 C++20 受约束预期析构函数两种实现手法）、赋值与 emplace 的异常保证、value() 与加固的 operator*、value_or、单子操作、C++26 的 range 支持与 constexpr
status: draft
covers: *
papers: P0220R1, P0602, P0848, P0798, P3168, P2988, P3471
related: optional, optional.optional.ref, expected.expected, variant.variant, class.union, class.prop, class.dtor, special, class.copy.ctor, dcl.init.general, structure.specifications, basic.life, over.match.best
tags: 标准库, optional, 平凡性, 特殊成员函数, 单子操作, 加固
updated: 2026-10-18
---

[optional.optional] 是 `optional<T>` 主模板的完整规格，也是整个标准库里"**如何把一个包装类型写得和被包装类型一样好用**"的教科书。它要同时满足几条相互拉扯的需求：

- **零开销**：`optional<int>` 应当和 `struct { int v; bool b; }` 一样可以按字节复制、放进寄存器传参、做 `constexpr` 变量——这要求它的特殊成员函数在 `T` 平凡时**也是平凡的**；
- **完美转发构造**：`optional<std::string> s = "abc";` 要像 `std::string s = "abc";` 一样自然，`explicit` 与否要和 `T` 的构造函数一致；
- **不和自己打架**：`optional<U>` → `optional<T>` 的转换，不能和"把整个 `optional<U>` 当作 `T` 的构造实参"的路径冲突；
- **异常安全**：赋值失败时 `has_value()` 不能处于半更新状态。

本页按子条款顺序走一遍：[optional.optional.general] → [optional.ctor] → [optional.dtor] → [optional.assign] → [optional.swap] → [optional.iterators] → [optional.observe] → [optional.monadic] → [optional.mod]。总览、比较运算符、`hash` 见 [[optional]]；引用偏特化 `optional<T&>` 见 [[optional.optional.ref]]。

## 数据模型与合法的被包含类型（[optional.optional.general]）

规范用一个仅用于说明的匿名联合体描述存储：

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

¶1 给出两个定义：

!!! std
    An instance of `optional<T>` is said to *contain a value* when and only when its member *val* is active ([class.union.general]); *val* is referred to as its *contained value*.

    `optional<T>` 的实例**含有值**，当且仅当成员 *val* 是活跃成员；*val* 称为它的**被包含值**。

这把"有值"直接挂到了核心语言的**活跃成员**概念上（[[class.union]]）：*val* 的生命周期开始 ⇔ 有值；生命周期结束 ⇔ 无值。¶1 还规定被包含值**嵌套于**（nested within，[[intro.object]]）optional 对象之中——这保证了被包含值的存储由 optional 提供，指针运算与别名分析的规则都按"子对象级"处理。

注意成员类型是 `remove_cv_t<T>` 而不是 `T`。对 `optional<const int>`，*val* 的类型是 `int`：`emplace`、`reset` 后重新构造等操作要在同一块存储上销毁旧值、`construct_at` 新值，存储类型不带 cv 限定，就不必操心"在 const 对象的存储上重建对象"这类 [[basic.life]] 的边角规则，新对象可以干净地**透明替换**旧对象。公开接口（`operator*` 等）仍然按 `T` 返回，所以用户看到的依然是 `const int&`。

¶2 定义**合法的被包含类型**（[[g:valid-contained-type]]）：

!!! std
    A type `X` is a *valid contained type* for `optional` if `X` is an lvalue reference type or a complete non-array object type, and `remove_cvref_t<X>` is a type other than `in_place_t` or `nullopt_t`.

    若 `X` 是左值引用类型，或是完整的非数组对象类型，且 `remove_cvref_t<X>` 不是 `in_place_t`、`nullopt_t`，则 `X` 是 optional 的合法被包含类型。

用非法类型实例化 `optional` 的特化，程序**非良构**（必须诊断）。逐项看排除了什么：

- `void`、函数类型：不是对象类型；
- 数组：`optional<int[3]>` 不行——数组不能被复制初始化、不能赋值，整个接口都对不上；
- 右值引用：`optional<int&&>` 不行；左值引用 `optional<int&>` 自 C++26 起合法，但由偏特化 [[optional.optional.ref]] 处理；
- `in_place_t`、`nullopt_t`：它们是 `optional` 构造函数的**标签**，若允许作为被包含类型，`optional<nullopt_t>(nullopt)` 就无法区分"构造空 optional"与"构造含一个 nullopt 的 optional"。

此外，若 `T` 是对象类型，它必须满足 *Cpp17Destructible*——这是一条普通的库要求，违反是 {{ub}}（[[res.on.functions]]），不保证诊断。libc++ 在类内用一串 `static_assert` 检查这些条件（`in_place_t`、`nullopt_t`、右值引用、不可析构、数组），所以实践中你总能得到清晰的报错。

## 构造函数（[optional.ctor]）

### *converts-from-any-cvref*（¶1）

¶1 先定义一个仅用于说明的变量模板：

```cpp
template<class T, class W>
constexpr bool converts-from-any-cvref =  // exposition only
  disjunction_v<is_constructible<T, W&>, is_convertible<W&, T>,
                is_constructible<T, W>, is_convertible<W, T>,
                is_constructible<T, const W&>, is_convertible<const W&, T>,
                is_constructible<T, const W>, is_convertible<const W, T>>;
```

即：**`T` 能否从 `W` 的任意一种 cv/引用限定形式构造或转换而来**。它被用来回答这样一个问题：当 `W = optional<U>` 时，`T` 是不是"本来就能吃下一整个 `optional<U>`"？如果是，`optional<T>` 的 `optional<U>` 转换构造函数就应当让路（见下文 ¶28）。[[expected.expected]] 也借用这个变量模板。

### 默认构造与 `nullopt` 构造（¶2–3）

`optional()` 与 `optional(nullopt_t)` 都是 `noexcept` 的，后置条件"不含值"。¶3 *Remarks*：

!!! std
    No contained value is initialized. For every object type `T` these constructors are constexpr constructors ([dcl.constexpr]).

    不初始化被包含值。对**每一个**对象类型 `T`，这两个构造函数都是 constexpr 构造函数。

"每一个"包括非字面类型：`T` 自己的构造函数从未被调用，所以 `constinit std::optional<std::mutex> m;` 这种静态初始化是有保证的。实现上，libc++ 的存储基类在联合体里放了一个 `char __null_state_` 成员，默认构造时激活它——使得 constexpr 构造函数总有一个合法的活跃成员可以初始化。

### 复制与移动构造（¶4–12）

复制构造（¶4–7）：若 `rhs` 有值，用 `rhs.`*val* **直接非列表初始化**（[[g:direct-non-list-initialization]]）自己的 *val*。¶7 是关键：

!!! std
    This constructor is defined as deleted unless `is_copy_constructible_v<T>` is `true`. If `is_trivially_copy_constructible_v<T>` is `true`, this constructor is trivial.

    除非 `is_copy_constructible_v<T>` 为真，否则此构造函数被定义为弃置的。若 `is_trivially_copy_constructible_v<T>` 为真，此构造函数是平凡的。

移动构造（¶8–12）的写法不同：¶8 是 *Constraints*（`is_move_constructible_v<T>`），不是"定义为弃置"。差别在于：弃置的函数**仍参与重载决议**（被选中才报错），而不满足 *Constraints* 的函数**根本不参与**。对移动构造来说这很要紧——当 `T` 不可移动时，`optional<T>` 的移动构造"消失"，右值实参会退而选择复制构造函数（若 `T` 可复制），这与核心语言对"没有移动构造函数的类"的处理一致（[[class.copy.ctor]]）。¶12：`noexcept` 规格等价于 `is_nothrow_move_constructible_v<T>`；`T` 平凡可移动构造时它是平凡的。¶9 还特意说明 `rhs.has_value()` **不变**——被移动的 optional 仍然"有值"，只是那个值处于被移出状态。

### `in_place` 构造（¶13–22）

`optional(in_place_t, Args&&...)` 与 `optional(in_place_t, initializer_list<U>, Args&&...)`：*Constraints* 为对应的 `is_constructible_v`，效果是用实参直接非列表初始化 *val*。它们总是 `explicit`。¶17/¶22 *Remarks*：若 `T` 被选中的构造函数是 constexpr 构造函数，则这个构造函数也是。

### 从 `U&&` 构造（¶23–27）

这是最常用的构造函数：`optional<std::string> s = "abc";`。

```cpp
template<class U = remove_cv_t<T>>
  constexpr explicit(see below) optional(U&& v);
```

¶23 *Constraints*：

- (23.1) `is_constructible_v<T, U>`；
- (23.2) `remove_cvref_t<U>` 不是 `in_place_t`（否则会劫持 `optional(in_place)` 这种调用）；
- (23.3) `remove_cvref_t<U>` 不是 `optional` 本身（否则会和复制/移动构造竞争——非 const 左值 `optional&` 匹配 `U&&` 比匹配 `const optional&` 更好！）；
- (23.4) 若 `T` 是 cv `bool`，`remove_cvref_t<U>` 不是 `optional` 的特化。

(23.4) 的道理：`bool` 可以从 `optional<int>` **直接初始化**（经由 `explicit operator bool`），所以 `is_constructible_v<bool, optional<int>>` 为真。没有这一条，`optional<bool> b{std::optional<int>{}}` 会走 `U&&` 构造，得到"含有 `false` 的 optional"——而所有人的直觉都是"空 optional 转换为空 optional"。

¶27：`explicit` 中的表达式等价于 `!is_convertible_v<U, T>`。这就是 C++20 `explicit(bool)` 的用武之地：**`T` 能从 `U` 隐式转换，`optional<T>` 就能从 `U` 隐式构造**。

```cpp run title="explicit.cpp" error
#include <optional>
#include <string>
#include <vector>

std::optional<std::string> s = "abc";             // OK：const char* → string 可隐式转换，构造函数非 explicit
std::optional<std::vector<int>> v1{3};            // OK：直接初始化，explicit 构造函数可用
std::optional<std::vector<int>> v2 = 3;           // error: vector(size_t) 是 explicit，故 optional(U&&) 也是 explicit
int main() {}
```

默认模板实参是 `remove_cv_t<T>` 而不是 `T`：当实参是 `{...}` 这种无法推导类型的花括号列表时，`U` 取默认值。`optional<const Foo> o = {1, 2};` 中 `U = Foo`，`Foo&&` 从 `{1, 2}` 构造临时量后再移动进来；若默认是 `const Foo`，参数类型 `const Foo&&` 会阻止从临时量移动。

### 从 `optional<U>` 转换构造（¶28–37）

```cpp
template<class U> constexpr explicit(see below) optional(const optional<U>& rhs);
template<class U> constexpr explicit(see below) optional(optional<U>&& rhs);
```

¶28 *Constraints*（以 `const&` 版本为例）：

- (28.1) `is_constructible_v<T, const U&>`；
- (28.2) 若 `T` **不是** cv `bool`，则 *converts-from-any-cvref*`<T, optional<U>>` 为 `false`。

(28.2) 是整个 optional 设计中最微妙的一条。考虑 `T` 本身就能从 `optional<U>` 构造的情况——最典型的是 `std::any`：

```cpp run title="any_vs_optional.cpp" ok
#include <any>
#include <cassert>
#include <optional>

int main() {
  std::optional<int> empty;

  // T = std::any 可以从任何东西构造，包括 optional<int> 本身
  std::optional<std::any> a = empty;
  assert(a.has_value());                         // 有值！值是一个装着空 optional<int> 的 any
  assert(a->type() == typeid(std::optional<int>));

  // T = bool 被特殊对待：走"转换构造"，空就是空
  std::optional<bool> b = empty;
  assert(!b.has_value());

  std::optional<long> c = std::optional<int>(42);  // 普通情况：逐值转换
  assert(c && *c == 42);
}
```

`optional<any>` 从 `optional<int>` 构造有两种可能的语义：(a) 逐值转换（空→空，有值→`any(int)`）；(b) 把整个 `optional<int>` 塞进 `any`。两条路都"能编译"，标准选择了 (b)：只要 `T` 能从 `optional<U>` 的任意 cvref 形式构造或转换，转换构造函数就**退出**，交给 `optional(U&&)` 处理。理由是保持与 `T` 本身行为一致——`std::any x = empty;` 本来就是把 `optional<int>` 装进去，`optional<any>` 不应改变这层语义。

`bool` 是例外（"if `T` is not cv `bool`"）：`bool` 能从 `optional<U>` 直接初始化纯属 `explicit operator bool` 的副作用，没有人想要"把 optional 的有无变成 bool 值"，所以对 `bool` 保留逐值转换语义；配合 (23.4) 一起，`optional<bool>` 从 `optional<U>` 构造就只会走转换构造。

¶32/¶37：`explicit` 分别等价于 `!is_convertible_v<const U&, T>`、`!is_convertible_v<U, T>`。¶34 同样强调 `rhs.has_value()` 不变。

!!! impl "libc++：两套重载代替 explicit(bool)"
    libc++ 的 `<optional>` 要同时支持 C++17，所以这些"条件 explicit"的构造函数都写成**两个**重载：一个隐式、一个 `explicit`，分别用 `enable_if_t<_CheckOptionalLikeCtor<...>::__enable_implicit<_Up>()>` / `__enable_explicit` 互斥地启用（代码注释标着 LWG2756，正是引入条件 explicit 的那个 issue）。其中 `__check_constructible_from_opt` 就是 *converts-from-any-cvref* 的实现，`__check_assignable_from_opt` 对应赋值的 (19.4)–(19.7)。`optional(U&&)` 还带有 `noexcept(is_nothrow_constructible_v<_Tp, _Up>)`，注释为 `// strengthened`——标准允许实现给非虚函数加强 `noexcept`（[[res.on.exception.handling]]）。

## 条件平凡：让 `optional<int>` 平凡可复制

把散落各处的 *Remarks* 收集起来：

| 特殊成员 | 何时平凡 | 段落 |
|---|---|---|
| 复制构造 | `is_trivially_copy_constructible_v<T>` | [optional.ctor] ¶7 |
| 移动构造 | `is_trivially_move_constructible_v<T>` | [optional.ctor] ¶12 |
| 析构 | `is_trivially_destructible_v<T>` | [optional.dtor] ¶2 |
| 复制赋值 | `T` 平凡可复制构造 ∧ 平凡可复制赋值 ∧ 平凡可析构 | [optional.assign] ¶7 |
| 移动赋值 | `T` 平凡可移动构造 ∧ 平凡可移动赋值 ∧ 平凡可析构 | [optional.assign] ¶13 |

（赋值的条件额外要求 `T` 平凡可析构，因为非平凡的赋值需要在"有值→无值"时调用析构函数。）

按 [[class.prop]]，一个类是**平凡可复制**的（[[g:trivially-copyable-class]]），当且仅当它至少有一个合格的复制/移动操作、所有合格的复制/移动构造与赋值都是平凡的、并且有平凡且未弃置的析构函数。上表的五条保证合在一起意味着：**`T` 平凡可复制 ⇒ `optional<T>` 平凡可复制**。

```cpp
static_assert(std::is_trivially_copyable_v<std::optional<int>>);
static_assert(!std::is_trivially_copyable_v<std::optional<std::string>>);
```

这不是锦上添花。平凡可复制意味着 `optional<int>` 可以用 `memcpy` 复制、可以作为 `std::atomic` 的模板实参、可以 `std::bit_cast`，并且在 Itanium C++ ABI 下**可以在寄存器中传递和返回**——一个返回 `optional<int>` 的函数和返回 `struct {int; bool;}` 的函数生成同样的代码。C++17 最初的 `optional` 并没有这些保证，是 [[P0602]] 以缺陷报告的形式补上的。

### 难点：类模板的特殊成员怎么"有条件地平凡"

问题在于：`optional<T>` 的析构函数在 `T = std::string` 时必须是 `if (engaged) val.~T();`，在 `T = int` 时却必须是平凡的。一个用户提供的函数永远不是平凡的，哪怕函数体为空。C++17 里只能靠**基类分派**，C++20 起可以靠**受约束的特殊成员函数**。

**C++17 手法：基类阶梯（libc++ `<optional>` 的做法）**

libc++ 把 `optional<T>` 搭成一条继承链，每一层只负责一种特殊成员，用一个 `bool` 模板参数在"平凡版本（`= default`）"与"手写版本"之间分派：

```text
__optional_destruct_base<T, is_trivially_destructible<T>>        // 析构：平凡版不写析构函数；非平凡版 if (__engaged_) __val_.~T()
  └ __optional_storage_base<T, is_reference<T>>                 // has_value、__get、__construct、__assign_from 等公用操作
    └ __optional_copy_base<T, is_trivially_copy_constructible_v<T>>
      └ __optional_move_base<T, is_trivially_move_constructible_v<T>>
        └ __optional_copy_assign_base<T, 平凡析构 && 平凡复制构造 && 平凡复制赋值>
          └ __optional_move_assign_base<T, 平凡析构 && 平凡移动构造 && 平凡移动赋值>
            └ __optional_iterator_base<T>                       // C++26：begin/end
              └ optional<T>  （另外私有继承 __sfinae_ctor_base / __sfinae_assign_base 来"弃置"复制/移动）
```

`optional<T>` 自己的复制构造、赋值等全部 `= default`，它们是否平凡、是否弃置，完全由基类决定——隐式定义的特殊成员是否平凡，取决于每个基类和成员对应的那个操作是否平凡（[[class.copy.ctor]]）。真正"弃置"复制构造的工作交给 `__sfinae_ctor_base<is_copy_constructible<T>, is_move_constructible<T>>`：它在条件为假时把对应构造函数声明为 `= delete`，从而让派生类的 defaulted 版本也被定义为弃置。注意两个 `bool` 的取值和标准条文一一对应：比如复制赋值阶梯的条件正是 [optional.assign] ¶7 的三个 trait 的合取。

**C++20 手法：多个预期特殊成员 + requires**

C++20 的 [[P0848]] 允许一个类声明**多个**带不同约束的预期析构函数（[[g:prospective-destructor]]，见 [[class.dtor]]）和多个复制/移动构造函数；重载决议在类完整时挑出"合格的"那一个（[[g:eligible-special-member-function]]，见 [[special]]），平凡性只看合格者。于是条件平凡可以直接写在一个类里：

```cpp run title="cond_trivial.cpp" ok
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

  // 两个预期析构函数：约束决定谁被选中
  constexpr ~Opt() requires std::is_trivially_destructible_v<T> = default;
  constexpr ~Opt() { if (engaged) val.~T(); }

  // 两个复制构造函数：平凡版本 vs 手写版本
  Opt(const Opt&) requires std::is_trivially_copy_constructible_v<T> = default;
  constexpr Opt(const Opt& o) : engaged(o.engaged) {
    if (engaged) std::construct_at(std::addressof(val), o.val);
  }
  // （赋值运算符同理，此处省略）
  Opt& operator=(const Opt&) = delete;
};

static_assert(std::is_trivially_destructible_v<Opt<int>>);
static_assert(std::is_trivially_copy_constructible_v<Opt<int>>);
static_assert(!std::is_trivially_destructible_v<Opt<std::string>>);
static_assert(!std::is_trivially_copy_constructible_v<Opt<std::string>>);

int main() {
  Opt<std::string> a(std::string(100, 'x'));
  Opt<std::string> b = a;
}
```

当 `T = int` 时两个析构函数都满足约束，但带约束的那个**更受约束**，被选中；当 `T = std::string` 时只有无约束的那个满足。libc++ 的 `<optional>` 至今保留基类阶梯（它还要服务 C++17 模式，而且改动布局继承结构会牵涉 ABI），而后来编写的 `<expected>` 就直接用了 C++20 手法（`__expected/expected.h` 中多对 `= default` / 手写的特殊成员，见 [[expected.expected]]）。

!!! note "为什么联合体在这里是必需的"
    `union { T val; }` 的作用是**抑制自动构造与析构**：联合体成员不会被隐式构造，含非平凡成员的联合体其析构函数也不会去销毁成员（在 C++26 之前，这样的联合体析构函数被定义为弃置，外层类必须提供自己的析构函数——这正是上面"手写版本"析构函数的由来）。详见 [[class.union]]。

## 析构函数（[optional.dtor]）

¶1：若 `is_trivially_destructible_v<T>` 为假且 `*this` 有值，调用 *val*`.T::~T()`。¶2：若 `T` 可平凡析构，此析构函数平凡。析构函数是 `constexpr` 的，因此 `optional<std::string>` 可以在常量求值中创建和销毁。

## 赋值（[optional.assign]）

### 与 `nullopt` 赋值（¶1–3）

有值则销毁，否则无操作；`noexcept`。和 `reset()` 等价。

### 复制赋值与移动赋值（¶4–13）

规范用一张 2×2 表格描述（表 67、表 68）：

| | `*this` 有值 | `*this` 无值 |
|---|---|---|
| `rhs` 有值 | 把 `rhs.`*val* **赋值**给 *val* | 用 `rhs.`*val* **直接非列表初始化** *val* |
| `rhs` 无值 | 调用 *val*`.T::~T()` 销毁 | 无操作 |

注意"两边都有值"时调用的是 `T` 的**赋值运算符**而不是先销毁再构造——这保留了 `T` 自己的赋值语义（例如 `std::vector` 赋值时复用已有容量）。

¶7 / ¶13 的异常安全规则：

!!! std
    If any exception is thrown, the result of the expression `this->has_value()` remains unchanged.

    若抛出异常，`this->has_value()` 的结果保持不变。

这是一种很弱但很实用的保证：`optional` 不会因为异常而"丢掉"或"凭空多出"一个值。至于值本身处于什么状态，则由 `T` 自己的复制构造（无值→有值情况下抛出：无效果）或复制赋值（有值→有值情况下抛出：由 `T` 的异常保证决定）说了算。

复制赋值"除非 `T` 可复制构造**且**可复制赋值，否则定义为弃置"——两个都要，因为表格里两种操作都可能用到。移动赋值则用 *Constraints*（¶8），`noexcept` 规格是 `is_nothrow_move_assignable_v<T> && is_nothrow_move_constructible_v<T>`（¶12）。

### 从 `U&&` 赋值（¶14–18）

```cpp
template<class U = remove_cv_t<T>> constexpr optional& operator=(U&& v);
```

¶14 *Constraints*：

- (14.1) `remove_cvref_t<U>` 不是 `optional`；
- (14.2) `conjunction_v<is_scalar<T>, is_same<T, decay_t<U>>>` 为**假**；
- (14.3) `is_constructible_v<T, U>`；
- (14.4) `is_assignable_v<T&, U>`。

(14.2) 专门为 `o = {}` 而设。`{}` 无法推导 `U`，于是 `U` 取默认值 `remove_cv_t<T>`。若 `T` 是标量（`int`、指针……），没有 (14.2) 的话 `operator=(int&&)` 从 `{}` 得到 `int(0)` 是一个**标准转换序列**，比 `operator=(optional&&)` 所需的用户定义转换更好，`o = {}` 就会把 `o` 设成"含有 0"而不是重置。(14.2) 把这条路堵死。对非标量的 `T`，两边都是用户定义转换且不可区分，[[over.match.best]] 的"非模板优于模板"规则让 `operator=(optional&&)` 胜出——同样是重置：

```cpp run title="assign_braces.cpp" ok
#include <cassert>
#include <optional>
#include <string>

int main() {
  std::optional<int> i = 5;
  i = {};                       // 重置：operator=(U&&) 被 (14.2) 排除
  assert(!i);

  std::optional<std::string> s = "hello";
  s = {};                       // 也是重置：模板与非模板同样好，非模板胜出
  assert(!s);
}
```

¶15：有值则 `val = std::forward<U>(v)`，否则直接非列表初始化。

### 从 `optional<U>` 赋值（¶19–28）

约束是构造版本的超集：除了 `T` 能从 `const U&`（或 `U`）构造与赋值、*converts-from-any-cvref*`<T, optional<U>>` 为假之外，(19.4)–(19.7) 还要求 `T&` **不能**从 `optional<U>` 的四种 cvref 形式赋值。道理与构造相同：若 `T` 本身就能"吃下"一个 `optional<U>`（比如 `T = std::any`），这个赋值运算符让路，交给 `operator=(U&&)` 把整个 optional 赋给 *val*。（注意这里**没有** `bool` 例外：`bool` 不能从 `optional<U>` 赋值，所以不需要。）效果见表 69、表 70，结构与复制赋值一致。

### `emplace`（¶29–40）

```cpp
template<class... Args> constexpr T& emplace(Args&&... args);
```

¶30：先 `*this = nullopt`，然后直接非列表初始化 *val*。¶32 返回 *val* 的引用，方便 `auto& x = o.emplace(...)`。¶34：

!!! std
    If an exception is thrown during the call to `T`'s constructor, `*this` does not contain a value, and the previous *val* (if any) has been destroyed.

    若 `T` 的构造函数抛出异常，`*this` 不含值，且之前的 *val*（若有）已被销毁。

这是**基本保证**而非强保证：`emplace` 失败后旧值没了。这是有意为之——`emplace` 的意义就是**原地**构造，不允许出现"新值和旧值同时存在"的临时副本；要强保证，请先构造好一个 `T` 再 `o = std::move(t)`。与之对比，[[expected.expected]] 的 `emplace` 干脆要求构造 `noexcept`，以维持它的"永不为空"不变式。

## swap（[optional.swap]）

¶1 *Mandates*：`is_move_constructible_v<T>`（违反则非良构）。¶2 *Preconditions*：`T` 满足 *Cpp17Swappable*（[[swappable.requirements]]）。表 71：

- 两边都有值：调用 `swap(val, rhs.val)`（经 ADL 找到的 swap）；
- 只有一边有值：用 `std::move` 把值移动构造到另一边，再销毁原处的值；
- 都无值：无操作。

¶5 `noexcept` 等价于 `is_nothrow_move_constructible_v<T> && is_nothrow_swappable_v<T>`。¶6 同样保证抛异常时两边的 `has_value()` 不变。

## 迭代器支持 {{c++26}}（[optional.iterators]）

C++26 起 `optional<T>` 是一个**最多含一个元素的范围**（[[P3168]]）。¶1：`iterator` / `const_iterator` 是实现定义的类型，满足 `contiguous_iterator`、*Cpp17RandomAccessIterator* 与 constexpr 迭代器的要求，值类型 `remove_cv_t<T>`，引用类型分别为 `T&`、`const T&`。¶2：容器迭代器的全部要求同样适用。¶3：

!!! std
    Any operation that initializes or destroys the contained value of an optional object invalidates all iterators into that object.

    任何初始化或销毁被包含值的操作都会使指向该对象的所有迭代器失效。

¶4 `begin()`：有值时指向被包含值，否则是尾后迭代器。¶5 `end()` 返回 `begin() + has_value()`——把 `bool` 当作 0/1 加上去，非常直白。

```cpp title="optional_range.cpp" ok
#include <cstdio>
#include <optional>
#include <ranges>

int main() {
  std::optional<int> o = 7;
  for (int& v : o) v *= 6;                         // 0 或 1 次迭代
  std::printf("%d\n", *o);

  std::optional<int> e;
  for (int v : e) std::printf("never %d\n", v);
  static_assert(std::ranges::contiguous_range<std::optional<int>>);
  static_assert(std::ranges::view<std::optional<int>>);
  std::printf("%zu %zu\n", std::ranges::size(o), std::ranges::size(e));
}
```

!!! impl "libc++ 状态"
    libc++ 23 已实现 [optional.iterators]，但放在实验性开关之后：`_LIBCPP_HAS_EXPERIMENTAL_OPTIONAL_ITERATOR` 由 `_LIBCPP_HAS_EXPERIMENTAL_LIBRARY` 决定，要用 `-fexperimental-library` 编译，`__cpp_lib_optional_range_support`（202406L）也只在此时定义。上例在本机 clang 23 + libc++ 用 `-std=c++2c -fexperimental-library` 编译通过并输出 `42` 与 `1 0`；不加该开关时 `for (int& v : o)` 报"no viable 'begin' function"。迭代器类型在默认 ABI 下是 `__capacity_aware_iterator<T*, optional<T>, 1>`，启用 `_LIBCPP_ABI_BOUNDED_ITERATORS_IN_OPTIONAL` 时改为带边界检查的 `__bounded_iter`。

因为 `enable_view<optional<T>>` 为真（[[optional]]），`optional` 可以直接放进管道：`opt | std::views::transform(f)`。在 range 世界里，`optional<T>` 与 `views::single` 的区别是它可以为空、可以就地修改。

## 观察器（[optional.observe]）

### `operator->` 与 `operator*`：加固前置条件（¶1–8）

```cpp
constexpr const T* operator->() const noexcept;   constexpr T* operator->() noexcept;
constexpr const T& operator*() const & noexcept;  constexpr T& operator*() & noexcept;
constexpr T&& operator*() && noexcept;            constexpr const T&& operator*() const && noexcept;
```

它们全部带有 *Hardened preconditions*：`has_value()` 为真（¶1、¶4、¶7）。按 [[structure.specifications]]：

- 在**加固实现**（[[g:hardened-implementation]]）中，调用时先以终止语义检查这个条件，违反即契约违反、程序终止，不会有任何别的可观察副作用；
- 在非加固实现中，违反是 {{ub}}。

这是 C++26 标准库加固（[[P3471]]）的一部分：`*opt` 解引用空 optional 是现实中常见的内存安全漏洞（读到的是联合体里未初始化或已销毁的存储），加固后它变成确定性终止。

```cpp title="hardened.cpp"
#include <cstdio>
#include <optional>

int main() {
  std::optional<int> o;
  try {
    (void)o.value();                // 抛 bad_optional_access
  } catch (const std::bad_optional_access& e) {
    std::puts("caught");
  }
  int x = *o;                       // 违反加固前置条件
  std::printf("%d\n", x);
}
```

本机 libc++ 23 的实测：默认（非加固）编译，程序打印一个无意义的值并"正常"退出——这正是 UB 最可怕的样子；加 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 后在 `*o` 处陷入（`SIGTRAP`）；用 `_LIBCPP_HARDENING_MODE_DEBUG` 则先打印 `libc++ Hardening assertion this->has_value() failed: optional operator* called on a disengaged value` 再终止。libc++ 用的检查宏是 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS`，在 fast / extensive / debug 三种加固模式下都启用。

¶2 `operator->` 返回 `addressof(val)`——用 `addressof` 而不是 `&val`，以免 `T` 重载了一元 `&`。¶8 的右值版本返回 `std::move(val)`，类型是 `T&&`。

!!! ub "右值 optional 的 `*` 与悬垂引用"
    ```cpp
    std::optional<std::string> make();
    const std::string& s = *make();   // UB（后续使用时）：引用绑定到临时 optional 内部
    std::puts(s.c_str());             // 临时 optional 已在完整表达式结束时销毁
    ```
    `*make()` 是返回 `std::string&&` 的函数调用，不是成员访问表达式，所以**不会**触发临时量生存期延长（[[class.temporary]]）。同样的坑也存在于 `value()` 的右值重载。要么按值接住（`std::string s = *make();`），要么先把 optional 存进变量。

### `operator bool` 与 `has_value`（¶9–12）

都返回"是否有值"。`operator bool` 是 `explicit` 的，因此 `if (o)`、`!o`、`o && x` 可以，`int n = o;`、`o + 1` 不行（[[g:contextually-converted-to-bool]]）。

### `value()`：会抛异常的访问（¶13–14）

```cpp
return has_value() ? val : throw bad_optional_access();
```

这是"Effects: Equivalent to"的写法，一句话交代全部语义：有值返回引用，无值抛 `bad_optional_access`（[[optional]]）。`value()` 没有前置条件，是**完全定义**的。在独立实现中它被弃置（概要注释 `// freestanding-deleted`）。

`operator*` 与 `value()` 的取舍：前者是"我知道一定有值"的零开销访问（加固后变为检查+终止），后者是"如果没有值，请抛异常让上层处理"。

### `value_or`（¶15–18）

```cpp
template<class U = remove_cv_t<T>> constexpr T value_or(U&& v) const &;
template<class U = remove_cv_t<T>> constexpr T value_or(U&& v) &&;
```

- ¶15 *Mandates*：`is_copy_constructible_v<T> && is_convertible_v<U&&, T>`；右值版本（¶17）要求可移动构造。这些是 *Mandates*——不满足时是**硬错误**，不是 SFINAE。libc++ 用 `static_assert` 实现（"optional<T>::value_or: T must be copy constructible"）。
- ¶16 效果：`has_value() ? val : static_cast<T>(std::forward<U>(v))`。

两个值得注意的点：

1. **返回 `T` 按值**。即便 optional 有值，也会复制一份。对大对象，`opt ? *opt : fallback` 的引用写法可能更省。
2. **默认实参 `U = remove_cv_t<T>`** 让 `o.value_or({})` 成立：`{}` 无法推导，`U` 取 `remove_cv_t<T>`，于是参数是 `T&&`，从 `{}` 值初始化。

## 单子操作 {{c++23}}（[optional.monadic]）

[[P0798]] 为 `optional` 加入三个高阶函数，让"可能失败的计算链"不必写成层层嵌套的 `if`。每个函数都有 `&`、`const&`、`&&`、`const&&` 四个重载（`or_else` 只有两个），区别只在于把 *val* 以何种值类别交给 `f`。

### `and_then`（¶1–6）

¶1 令 `U = invoke_result_t<F, decltype((val))>`。¶2 *Mandates*：`remove_cvref_t<U>` 是 `optional` 的特化。效果：

```cpp
if (*this) return invoke(std::forward<F>(f), val);
else       return remove_cvref_t<U>();
```

`f` 自己返回一个 optional——适合"下一步也可能失败"。返回类型就是 `f` 的返回类型（去掉 cvref），可以和原 optional 的值类型不同。

### `transform`（¶7–12）

¶7 令 `U = remove_cv_t<invoke_result_t<F, decltype((val))>>`。¶8 *Mandates*：

!!! std
    `U` is a valid contained type for `optional`. The declaration `U u(invoke(std::forward<F>(f), val));` is well-formed for some invented variable `u`.

    `U` 是 optional 的合法被包含类型，并且声明 `U u(invoke(std::forward<F>(f), val));` 良构。

紧跟着的注 1：**不要求 `U` 可移动**。¶9 *Returns*：一个 `optional<U>`，其被包含值以 `invoke(std::forward<F>(f), val)` **直接非列表初始化**。

这里的措辞非常讲究。为什么不直接写"Equivalent to: `return optional<U>(in_place, invoke(...))`"？因为那样 `invoke` 的结果要先绑定到 `in_place` 构造函数的 `Args&&` 参数上——prvalue 会被物化成临时量，再从临时量**移动**构造 *val*，于是要求 `U` 可移动。而"*val* 以 `invoke(...)` 直接非列表初始化"意味着 prvalue 直接初始化目标对象（C++17 保证的复制消除，见 [[dcl.init.general]] 中关于 prvalue 初始化器的规则），`U` 可以是不可移动类型。"Mandates: `U u(invoke(...))` 良构"同样是在说"按直接非列表初始化检查"——而不是"`U` 可从 `U&&` 构造"。

```cpp run title="transform.cpp" ok
#include <cassert>
#include <optional>
#include <type_traits>

struct Pinned {                       // 既不能复制也不能移动
  int v;
  explicit Pinned(int x) : v(x) {}
  Pinned(Pinned&&) = delete;
};

struct Point { int x, y; };

int main() {
  std::optional<int> o = 21;

  // transform 的结果直接在新 optional 的存储里构造：不需要 U 可移动
  auto p = o.transform([](int i) { return Pinned(i * 2); });
  static_assert(std::is_same_v<decltype(p), std::optional<Pinned>>);
  assert(p->v == 42);

  // C++26：f 返回左值引用 → 结果是 optional<int&>
  std::optional<Point> pt = Point{1, 2};
  auto rx = pt.transform([](Point& q) -> int& { return q.x; });
  static_assert(std::is_same_v<decltype(rx), std::optional<int&>>);
  *rx = 100;
  assert(pt->x == 100);

  // and_then：f 自己返回 optional，用于"可能失败的下一步"
  auto half = [](int i) -> std::optional<int> {
    if (i % 2) return std::nullopt;
    return i / 2;
  };
  assert(std::optional<int>(8).and_then(half).and_then(half) == 2);
  assert(!std::optional<int>(6).and_then(half).and_then(half));

  // or_else：f 无参，返回同类型 optional
  auto r = std::optional<int>{}.or_else([] { return std::optional<int>(-1); });
  assert(r == -1);
}
```

!!! impl "libc++ 如何做到“直接初始化”"
    普通的构造函数接口做不到"把一个函数调用的 prvalue 直接塞进联合体成员"——一旦经过函数参数，prvalue 就被物化了。libc++ 的办法是给 `optional` 加一个私有标签构造函数 `optional(__optional_construct_from_invoke_tag, F&& f, Args&&... args)`，一路传到 `__optional_destruct_base`，在**成员初始化器**里调用：`__val_(std::invoke(std::forward<_Fp>(__f), std::forward<_Args>(__args)...))`。`invoke` 的返回值 prvalue 直接初始化 `__val_`，复制消除得以保证。`<expected>` 里的 `__expected_construct_in_place_from_invoke_tag` 是同一个技巧。

C++26 带来的变化：合法被包含类型包含了左值引用，所以 `f` 返回 `int&` 时 `U = int&`，结果是 `optional<int&>`（上例）。在 C++23 中 `U = int&` 违反 *Mandates*，是硬错误。若 `f` 返回 `void`、数组、`nullopt_t` 或右值引用，仍然违反 *Mandates*。

### `or_else`（¶13–18）

```cpp
template<class F> constexpr optional or_else(F&& f) const &;
template<class F> constexpr optional or_else(F&& f) &&;
```

¶13 *Constraints*：`F` 满足 `invocable`（**无参**调用），`T` 满足 `copy_constructible`（右值版本为 `move_constructible`）。¶14 *Mandates*：`f()` 的返回类型去掉 cvref 后**正好是 `optional`**（同一个 `optional<T>`）。效果：有值返回 `*this`（的副本），否则返回 `f()`。

`or_else` 与另外两个的不对称值得注意：它的 `invocable` 与 `copy_constructible` 是 *Constraints*，返回类型检查是 *Mandates*；而 `and_then` / `transform` 只有 *Mandates*。因此 `requires { o.or_else(g); }` 能对"`g` 不能无参调用"给出 `false`，但对"`and_then` 的 `f` 返回类型不对"只能得到硬错误——单子操作不适合用作 SFINAE 探测。

## 修改器（[optional.mod]）

`reset()`：有值则调用 *val*`.T::~T()`，后置条件无值；`noexcept`。

## constexpr：几乎一切都能在编译期做

`optional<T>` 的每一个成员函数都声明为 `constexpr`。实际能否在常量求值中使用，取决于它调用的 `T` 的操作：

- 默认构造、`nullopt` 构造对**任意**对象类型都是 constexpr 构造函数（¶3）；
- 析构函数 constexpr，配合 C++20 的 constexpr `std::string`，`optional<std::string>` 可以在 consteval 上下文中完整走完生命周期；
- 赋值、`emplace`、`reset` 在规范中用"调用析构函数""直接非列表初始化"描述，实现靠 `std::construct_at` / `std::destroy_at`（[[specialized.construct]]）完成，它们在常量求值中合法。

```cpp run title="constexpr.cpp" ok
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

constexpr std::optional<int> g = 42;      // 字面类型的 optional 可做 constexpr 变量
static_assert(*g == 42 && g.value_or(0) == 42);
int main() {}
```

在常量求值中违反 `operator*` 的前置条件（解引用空 optional）会访问非活跃联合体成员，这本身就是核心语言的 UB，因此不是常量表达式（[[expr.const]]）——编译器**必须**诊断。

## 常见误区

!!! pitfall "被移出的 optional 仍然“有值”"
    `auto b = std::move(a);` 之后 `a.has_value()` **不变**（[optional.ctor] ¶9）。`a` 里是一个被移出状态的 `T`，而不是空 optional。想清空请显式 `a.reset()`。

!!! pitfall "`optional<T>` 与 `T*` 的语义不同"
    `optional<T>` 拥有并内嵌它的值，复制 optional 就复制值；`T*` 只是指向别处。用 optional 代替"可空指针参数"时，`f(std::optional<BigObject>)` 每次调用都复制大对象——这时要么用 `const BigObject*`，要么用 C++26 的 `optional<const BigObject&>`（[[optional.optional.ref]]）。

!!! pitfall "`optional<T>` 的 `sizeof`"
    `sizeof(optional<double>)` 通常是 16，而非 9：额外的 `bool` 加上对齐填充。在大数组中存 `optional<T>` 可能使内存翻倍，此时可以考虑用哨兵值或单独的位图。

## 思考题

!!! question "思考题 1"
    `std::optional<std::any> a = std::optional<int>{};` 中 `a.has_value()` 是什么？如果把 `std::any` 换成 `bool` 呢？标准中哪几条约束决定了这两个结果？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`optional<any>`：`true`。`std::any` 能从 `optional<int>` 的任何 cvref 形式构造，*converts-from-any-cvref*`<any, optional<int>>` 为真，(28.2)/(33.2) 使两个 `optional<U>` 转换构造函数不参与重载决议，剩下 `optional(U&&)`（`U = optional<int>`，(23.3) 只排除 `optional<any>` 自身），于是 *val* 被初始化为装着空 `optional<int>` 的 `any`。

`optional<bool>`：`false`（无值）。(28.2) 对 cv `bool` 不生效，转换构造函数可行；同时 (23.4) 排除了 `optional(U&&)`。所以逐值转换，空→空。
</details>

!!! question "思考题 2"
    为什么 `transform` 的 *Returns* 不简单写成 "Equivalent to: `return optional<U>(in_place, invoke(std::forward<F>(f), val));`"？写成这样会让哪类 `f` 失效？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`in_place` 构造函数的参数是转发引用 `Args&&...`，`invoke(...)` 返回的 prvalue 绑定到引用参数时会被**物化**为临时对象，随后 *val* 由这个 xvalue 移动构造——要求 `U` 可移动构造。若 `f` 返回不可移动的类型（如持有 `std::mutex` 的类、或像 `Pinned` 那样删除了移动构造的类），等价代码就非良构。标准改为"*val* 以 `invoke(...)` 直接非列表初始化"，借助 C++17 保证的复制消除，prvalue 直接构造目标对象；注 1 "There is no requirement that `U` is movable" 点明了这一意图。实现上需要私有的"从 invoke 构造"标签构造函数。
</details>

!!! question "思考题 3"
    `optional<int>` 是平凡可复制的。那么 `optional<const int>` 呢？`optional<std::unique_ptr<int>>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`optional<const int>`：复制/移动构造与析构都平凡（`const int` 可平凡复制构造、可平凡析构），但 `const int` 不可赋值，于是复制赋值被定义为弃置（[optional.assign] ¶7 要求 `is_copy_assignable_v<T>`），移动赋值不参与重载决议。按 [[class.prop]]，平凡可复制只要求"至少一个合格的复制/移动操作，且所有合格者平凡"，弃置的不合格，所以按标准对各特殊成员的描述推下来，它**应当是平凡可复制的**。

但本机 libc++ 23 给出 `is_trivially_copyable_v<std::optional<const int>> == false`，诊断是"has a non-trivially-copyable base `__optional_iterator_base<const int>`"。原因在基类阶梯：`__optional_copy_assign_base` 的条件里 `is_trivially_copy_assignable_v<const int>` 为假，于是选中了带**用户提供**的 `operator=` 的版本；真正把赋值"弃置"的是更外层的 `__sfinae_assign_base`。中间那个基类仍然拥有一个合格且非平凡的复制赋值，整个类就不再平凡可复制。这是 C++17 手法的一个边角缺陷——C++20 的受约束特殊成员写法不会有这个问题。

`optional<unique_ptr<int>>`：`unique_ptr` 的移动构造非平凡，析构也非平凡，所以不是。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 存储 | 说明用 `union { remove_cv_t<T> val; }`；有值 ⇔ *val* 是活跃成员 |
| 合法被包含类型 | 完整非数组对象类型或左值引用；非 `in_place_t`/`nullopt_t`；否则非良构 |
| `optional(U&&)` | 4 条约束；`explicit(!is_convertible_v<U, T>)`；默认 `U = remove_cv_t<T>` |
| `optional(optional<U>)` | `T` 能吃下整个 `optional<U>` 时让路（*converts-from-any-cvref*），`bool` 例外 |
| 条件平凡 | 5 个特殊成员各自随 `T` 平凡；`T` 平凡可复制 ⇒ `optional<T>` 平凡可复制 |
| 实现手法 | libc++ optional：基类阶梯；C++20：受约束的多个预期特殊成员 |
| 赋值 | 2×2 表；抛异常时 `has_value()` 不变；`o = {}` 总是重置 |
| `emplace` | 先销毁再构造；失败后为空（基本保证）；返回 `T&` |
| `*` / `->` | 加固前置条件：加固实现终止，否则 UB |
| `value()` | 无值抛 `bad_optional_access`；独立实现中弃置 |
| `value_or` | *Mandates*；按值返回 `T` |
| 单子操作 | `and_then` 返回 optional；`transform` 直接初始化、不要求可移动、C++26 可产生 `optional<T&>`；`or_else` 无参 |
| 迭代器 | C++26 contiguous 范围，0 或 1 个元素；libc++ 需 `-fexperimental-library` |
