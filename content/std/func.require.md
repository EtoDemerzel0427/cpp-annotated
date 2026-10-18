---
title: 函数对象的要求：INVOKE 与调用包装器
summary: 标准库所有“调用一个可调用物”的地方都归结为 INVOKE(f, t1, …, tN) 这一条七分支的定义；INVOKE<R> 再加上返回值转换（C++23 起禁止把引用绑到临时量）；在此之上定义调用包装器、参数转发调用包装器、完美转发调用包装器与简单调用包装器，以及 std::invoke / invoke_r
status: done
covers: func.def, func.invoke
papers: P1065R2, P2136R3, P2255R2
related: function.objects, refwrap, func.bind, func.bind.partial, func.not.fn, func.memfn, func.wrap, meta, expr.mptr.oper, expr.call, over.call.object, defns.expression.equivalent
tags: 标准库, functional, INVOKE, invoke, 调用包装器, 成员指针
updated: 2026-10-18
---

`<functional>` 里几乎每一个组件——`std::invoke`、`reference_wrapper::operator()`、`bind`、`bind_front`、`not_fn`、`mem_fn`、`function`、`move_only_function`——以及 `<type_traits>` 里的 `is_invocable` / `invoke_result`、`<ranges>` 里的投影、`<thread>` 的线程函数、`std::apply`、`std::visit`……它们的规格说明最后都落到同一个**仅用于说明**（exposition-only）的伪函数上：***INVOKE*(f, t1, t2, …, tN)**。

这是因为 C++ 里“可以被调用的东西”并不统一：普通函数、函数指针、带 `operator()` 的类（含 lambda 闭包）、能转换成函数指针的类，用的是 `f(args...)`；而**成员指针**必须写成 `(obj.*pmf)(args...)` 或 `obj.*pmd`，对象还可能是指针、智能指针或 `reference_wrapper`。[func.require] 把这一切抹平，让库的规格可以只写一句“returns *INVOKE*(…)”。

本页覆盖三个相邻子条款：

| 子条款 | 内容 |
|---|---|
| [func.def] | 术语：调用签名、可调用类型/对象、调用包装器、目标对象、绑定实参实体、状态实体 |
| [func.require] | *INVOKE*、*INVOKE*&lt;R&gt;，以及调用包装器的四个层级 |
| [func.invoke] | `std::invoke`、`std::invoke_r` |

前置知识：成员指针运算符 `.*` / `->*`（[[expr.mptr.oper]]）、函数调用表达式（[[expr.call]]）与类对象调用（[[over.call.object]]）、*表达式等价*（[[g:expression-equivalent]]，[[defns.expression.equivalent]]）。

## 术语（[func.def]）

¶2–¶4 先定义三个基础概念：

- **调用签名**（[[g:call-signature]] / *call signature*）：返回类型名后跟一个括号括起来的实参类型列表，例如 `int(double, char)`。`std::function<R(Args...)>` 的模板实参就是一个调用签名。
- **可调用类型**（[[g:callable-type]] / *callable type*）：**函数对象类型**（[[function.objects]]：可以出现在函数调用的 *postfix-expression* 位置的对象类型）**或者成员指针类型**。
- **可调用对象**（*callable object*）：可调用类型的对象。

注意两者的差别：成员指针**不是**函数对象类型——`pmf(obj)` 不是合法表达式——但它是可调用类型。“可调用”这个概念正是为了把成员指针纳入进来，而纳入的手段就是下面的 *INVOKE*。

¶5–¶8 定义调用包装器家族的基本词汇：

- **调用包装器类型**（[[g:call-wrapper]] / *call wrapper type*）持有一个**目标对象**（[[g:target-object]] / *target object*）——一个可调用对象，或“代表”可调用对象的对象（例如 `reference_wrapper` 存的是指针，但代表被引用的那个可调用物）——并支持一个把调用转发给它的调用操作。**调用包装器**就是这种类型的对象。
- 调用包装器还可以持有一串预先存好、调用时一起传过去的对象和引用，统称**绑定实参实体**（[[g:bound-argument-entities]] / *bound argument entities*）——`bind_front(f, 1, 2)` 里的 `1`、`2`。
- 目标对象与绑定实参实体合称**状态实体**（[[g:state-entities]] / *state entities*）。后面“复制包装器 = 逐个复制状态实体”“完美转发状态实体”都是基于这个词。

## *INVOKE*(f, t1, …, tN)：七个分支（[func.require]/1）

¶1 的定义按顺序尝试七个分支，前三个处理**成员函数指针**，接着三个处理**数据成员指针**，最后一个是“其他一切”：

!!! std
    Define *INVOKE*(f, t1, t2, …, tN) as follows: (t1.\*f)(t2, …, tN) when f is a pointer to a member function of a class T and is_same_v&lt;T, remove_cvref_t&lt;decltype(t1)&gt;&gt; || is_base_of_v&lt;T, remove_cvref_t&lt;decltype(t1)&gt;&gt; is true; …

| 分支 | f 是 | t1 的条件 | 展开为 |
|---|---|---|---|
| ¶1.1 | `T` 的成员函数指针 | `remove_cvref_t<decltype(t1)>` 是 `T` 或派生自 `T` | `(t1.*f)(t2, …, tN)` |
| ¶1.2 | 同上 | `remove_cvref_t<decltype(t1)>` 是 `reference_wrapper` 的特化 | `(t1.get().*f)(t2, …, tN)` |
| ¶1.3 | 同上 | 前两条都不满足 | `((*t1).*f)(t2, …, tN)` |
| ¶1.4 | `T` 的数据成员指针，且 N = 1 | 是 `T` 或派生自 `T` | `t1.*f` |
| ¶1.5 | 同上 | 是 `reference_wrapper` 的特化 | `t1.get().*f` |
| ¶1.6 | 同上 | 前两条都不满足 | `(*t1).*f` |
| ¶1.7 | 其余所有情形 | — | `f(t1, t2, …, tN)` |

逐条细读：

**对象本身（¶1.1 / ¶1.4）。** 判定用的是 `is_base_of_v`，它对**私有基类和有歧义的基类也为 true**。所以 `D` 私有继承 `B` 时，`INVOKE(&B::v, d)` 会选中 ¶1.4，展开为 `d.*(&B::v)`——这个表达式因访问检查而非良构；它**不会**“退一步”落到 ¶1.6 去尝试 `(*d).*f`。分支的选择只看类型关系，选中之后表达式成不成立是另一回事。

**`reference_wrapper`（¶1.2 / ¶1.5）。** 这两条是 C++17 之后才加进来的（以前 `reference_wrapper` 走 ¶1.3 的 `*t1`，而 `reference_wrapper` 并没有 `operator*`，于是按当时的条文 `invoke(&S::f, std::ref(s))` 是非良构的）。注意 `t1.get()` 永远是左值，所以通过 `reference_wrapper` 调用时 `&&` 限定的成员函数不可用。

**“像指针的东西”（¶1.3 / ¶1.6）。** 只要 `*t1` 合法即可——裸指针、`unique_ptr`、`shared_ptr`、迭代器、`optional`（!）都行。这里没有任何“必须是指针”的约束，这正是 `std::invoke(&Widget::draw, widgets_iterator)` 能工作的原因。

**数据成员指针要求 N = 1（¶1.4–¶1.6）。** 多传了实参，就不满足这三条的前提，落到 ¶1.7 的 `f(t1, t2)`，而成员指针不能这样调用——非良构。

**值类别如何传播。** ¶1.1 / ¶1.4 直接用 `t1.*f`，因此 `t1` 的值类别被保留：对右值对象取数据成员得到 xvalue（`int&&`），对 `const` 左值得到 `const int&`（规则见 [[expr.mptr.oper]]）；对右值对象调用成员函数会选中 `&&` 限定的重载。而 ¶1.6 的 `*t1` 一般是左值，所以通过指针访问永远得到左值。

**¶1.7 是普通函数调用。** 它覆盖函数、函数引用、函数指针、带 `operator()` 的类、以及能隐式转换为函数指针的类（经由 [[over.call.object]] 的代理调用函数）——这正是 [[function.objects]] ¶1 脚注里“函数对象类型”的三种形态。

```cpp run title="invoke_bullets.cpp" ok
#include <functional>
#include <memory>
#include <utility>
#include <type_traits>
#include <cstdio>
struct Base { int v = 1; int get() const { return v; } };
struct Derived : Base {};
int main() {
  Derived d;
  std::unique_ptr<Base> up = std::make_unique<Base>();
  auto pmf = &Base::get;
  auto pmd = &Base::v;
  std::printf("%d\n", std::invoke(pmf, d));             // (1.1) d.*pmf，Derived 派生自 Base
  std::printf("%d\n", std::invoke(pmf, std::ref(d)));   // (1.2) d.get().*pmf
  std::printf("%d\n", std::invoke(pmf, &d));            // (1.3) (*&d).*pmf
  std::printf("%d\n", std::invoke(pmf, up));            // (1.3) (*up).*pmf，任何“像指针”的东西都行
  std::invoke(pmd, d) = 42;                             // (1.4) 左值对象 -> int&
  std::printf("%d\n", d.v);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, Derived{})), int&&>);  // 右值对象 -> xvalue
  static_assert(std::is_same_v<decltype(std::invoke(pmd, &d)), int&>);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, std::as_const(d))), const int&>);
}
```

```cpp run title="invoke_edges.cpp" ok
#include <functional>
#include <type_traits>
struct S { void f() && {} };
static_assert(std::is_invocable_v<decltype(&S::f), S>);    // 右值 t1：选中 && 限定成员
static_assert(!std::is_invocable_v<decltype(&S::f), S&>);  // 左值 t1：不行

struct B { int v; };
struct D : private B {};
static_assert(!std::is_invocable_v<int B::*, D&>);         // 选中 (1.4)，访问失败；不会退回 (1.6)
static_assert(!std::is_invocable_v<int B::*, B&, int>);    // 数据成员指针多给实参 -> (1.7) -> 非良构
int main() {}
```

!!! ub "空成员指针"
    `INVOKE` 对 `f` 的值不做任何检查。若 `f` 是空的成员指针，`t1.*f` 按 [[expr.mptr.oper]] 是未定义行为 {{ub}}；若 ¶1.3 的 `t1` 是空指针，`*t1` 同样是 {{ub}}。`std::invoke` 不会替你兜底。

## *INVOKE*&lt;R&gt;：带返回类型的版本（¶2）

!!! std
    Define *INVOKE*&lt;R&gt;(f, t1, t2, …, tN) as static_cast&lt;void&gt;(*INVOKE*(f, t1, t2, …, tN)) if R is cv void, otherwise *INVOKE*(f, t1, t2, …, tN) implicitly converted to R.

¶2 分两种情形：

1. **`R` 是 cv `void`**：结果被 `static_cast<void>` 丢弃。所以 `std::function<void()>` 可以包装一个返回 `int` 的函数——返回值被静默扔掉（`[[nodiscard]]` 也不会触发，因为显式转换到 `void` 正是抑制它的标准写法）。
2. **否则**：结果**隐式转换**为 `R`——相当于复制初始化一个 `R`，所以 `explicit` 转换不算数。这与 `is_convertible` 的判定口径一致。

¶2 的最后一句是 C++23 加进来的（[[P2255R2]]）：

!!! std
    If reference_converts_from_temporary_v&lt;R, decltype(*INVOKE*(f, t1, t2, …, tN))&gt; is true, *INVOKE*&lt;R&gt;(f, t1, t2, …, tN) is ill-formed.

也就是说，若 `R` 是引用类型，而调用结果需要先**物化一个临时量**才能绑定到 `R` 上（例如函数返回 `int` 纯右值，`R` 是 `const int&`），那么 *INVOKE*&lt;R&gt; 直接**非良构**。理由很简单：这个临时量在 *INVOKE*&lt;R&gt; 结束时就死了，返回的引用必然悬垂。在此之前，`std::function<const int&()> f = []{ return 42; };` 能编译通过，调用 `f()` 就得到悬垂引用——一个只能在运行期（甚至 sanitizer 才能）发现的 bug；现在它在编译期被拒绝（`function` 的构造函数约束用的就是这套判定，详见 [[func.wrap.func]]）。

还要注意 ¶2 的措辞带来的连锁效应：[[meta]] 里 `is_invocable_r` 的定义是“*INVOKE*&lt;R&gt;(declval&lt;Fn&gt;(), declval&lt;ArgTypes&gt;()...) 作为不求值操作数是良构的”。所以按标准，`is_invocable_r_v<const int&, int()>` 应当是 **false**，`std::invoke_r<const int&>(f)` 应当因约束不满足而**不参与重载决议**。

!!! impl "libc++ 的现状"
    截至本文编写时（LLVM 23），libc++ 尚未实现这一条：`__functional/invoke.h` 里 `invoke_r` 的实现留着一条 `// TODO: Use reference_converts_from_temporary_v once implemented` 注释，对应的 `static_assert` 被替换成了 `static_assert(true, ...)`；`__type_traits/invoke.h` 里的 `__is_invocable_r_v` 也只检查可转换性。于是在 libc++ 上 `is_invocable_r_v<const int&, int()>` 仍为 `true`。
    
    不过 `std::invoke_r<const int&>(f)` 实际上还是会被拒绝——原因不在库，而在核心语言：C++26 起 `return` 语句把返回的引用绑定到临时表达式是非良构的（[[stmt.return#6]]），Clang 23 报 “returning reference to local temporary object”，错误指向 libc++ 的 `invoke_r` 函数体内部。结果相同，但路径不同：标准要求的是 SFINAE 友好的“不可行”，libc++ 给的是函数体里的硬错误。

```cpp run title="invoke_r_dangling.cpp" error
#include <functional>
int f() { return 42; }
const int& r = std::invoke_r<const int&>(f);   // 按标准：INVOKE<const int&> 非良构
int main() {}
```

## 调用包装器的四个层级（¶3–¶8）

¶3 起，标准给调用包装器定义了逐层加强的几个概念。`bind`、`bind_front`、`not_fn`、`mem_fn` 的 *Returns* 都只说“返回一个 X 调用包装器，调用模式为……”，具体语义全靠这里的定义。

### 所有调用包装器：可移动、可析构（¶3 前半）

!!! std
    Every call wrapper meets the *Cpp17MoveConstructible* and *Cpp17Destructible* requirements.

这是最低保证。是否可复制取决于状态实体（见 ¶7）。

### 参数转发调用包装器（¶3）

**参数转发调用包装器**（[[g:argument-forwarding-call-wrapper]] / *argument forwarding call wrapper*）能接受任意实参列表，并把实参**以引用形式**交给目标对象：右值实参作为右值引用、左值实参作为左值引用。注 1 指出典型实现就是一个 `template<class... UnBoundArgs> R operator()(UnBoundArgs&&...) cv-qual;`——即转发引用（[[g:forwarding-reference]]）。

`std::bind` 的返回值就是这一层：调用时传入的实参被完美转发，但**状态实体**（绑定的函数与实参）怎么交出去由 [[func.bind]] 自己规定——总是作为 `cv TDi&` **左值**交出去。

### 完美转发调用包装器与调用模式（¶4、¶5）

!!! std
    A *perfect forwarding call wrapper* is an argument forwarding call wrapper that forwards its state entities to the underlying call expression.

**完美转发调用包装器**（[[g:perfect-forwarding-call-wrapper]] / *perfect forwarding call wrapper*）在参数转发之上，**连状态实体也一起转发**：包装器本身作为左值被调用时，类型为 `T` 的状态实体以 `cv T&` 交出；否则（作为右值被调用）以 `cv T&&` 交出；`cv` 是包装器自身的 cv 限定——但**不能是 `volatile`**（对 `volatile` 包装器的调用没有定义）。

¶5 定义**调用模式**（[[g:call-pattern]] / *call pattern*）：对完美转发调用包装器做一次后缀调用，与“把调用模式里的实参和状态实体替换成按上述规则转发后的引用”所得的表达式**表达式等价**（[[g:expression-equivalent]]）。例如 `bind_front` 的调用模式是 `invoke(fd, bound_args..., call_args...)`（[[func.bind.partial]]），于是：

- `g(x)` ≡ `invoke(static_cast<FD&>(fd), static_cast<BoundArgs&>(bound_args)..., x)`；
- `std::move(g)(x)` ≡ `invoke(static_cast<FD&&>(fd), static_cast<BoundArgs&&>(bound_args)..., x)`；
- `std::as_const(g)(x)` ≡ 用 `const FD&` / `const BoundArgs&`。

“表达式等价”是很强的要求：两个表达式要**同时**良构或非良构、`noexcept` 性质相同、是否常量子表达式相同、效果相同。由此推出一个容易被忽视的结论：

!!! lawyer "被弃置的调用运算符：不许“退而求其次”"
    设目标对象 `F` 有 `void operator()() const;` 和 `void operator()() = delete;`。对**非 const 左值**包装器 `g` 调用 `g()`，调用模式里的 `fd` 是 `F&`，重载决议选中被弃置的非 const 版本——所以 `g()` 必须**非良构**。
    
    如果实现只是朴素地写四个带 SFINAE 的 `operator()`（`&`、`const&`、`&&`、`const&&`），非 const 的那个因 SFINAE 退出，`g()` 就会悄悄选中包装器的 `const&` 重载，转而调用目标的 const 版本——**与调用模式不再表达式等价**。因此实现必须在“对应 cv/引用限定下调用模式不良构”时把那个重载**显式弃置**，而不是让它消失。libc++ 的 `__functional/perfect_forward.h` 正是这样：每个限定版本都配一个 `enable_if_t<!is_invocable_v<...>>` 的 `= delete` 兄弟。

```cpp run title="no_fallback.cpp" error
#include <functional>
struct F {
  void operator()() const {}
  void operator()() = delete;
};
int main() {
  auto g = std::bind_front(F{});
  g();          // error：调用模式中 fd 是 F&，选中被弃置的非 const 版本；不会退回 const 版本
}
```

（`const auto g = std::bind_front(F{}); g();` 则是良构的，调用 const 版本。`std::bind` 不是完美转发调用包装器，但它的规格同样要求 `cv FD&`，libc++ 在这一点上的偏差见 [[func.bind]]。）

### 简单调用包装器（¶6）

**简单调用包装器**（[[g:simple-call-wrapper]] / *simple call wrapper*）是满足 *Cpp17CopyConstructible* 与 *Cpp17CopyAssignable*、且复制构造、移动构造、赋值运算符都是**不抛异常的 constexpr 函数**的完美转发调用包装器。标准库里只有 `mem_fn` 返回这一层（[[func.memfn]]）——它唯一的状态是一个成员指针，自然可以无条件地复制、赋值。

### 复制/移动语义与类型同一性（¶7、¶8）

!!! std
    The copy/move constructor of an argument forwarding call wrapper has the same apparent semantics as if memberwise copy/move of its state entities were performed.

¶7：参数转发调用包装器的复制/移动构造函数“看起来就像”逐个复制/移动状态实体。注 2 点明推论：异常说明与 `constexpr` 性质都与隐式定义的版本一致。实际效果：

- 绑定了 `unique_ptr` 的 `bind_front` 结果**只可移动、不可复制**；
- 所有状态实体都是 nothrow move 的，包装器的移动构造就是 `noexcept`（这决定了它放进 `vector` 后扩容时是移动还是复制）。

注意 ¶7 只约束**构造函数**；赋值运算符除了“简单调用包装器”外并没有统一要求——各组件自己规定（或不规定）。

¶8：同一个标准库函数模板返回的参数转发调用包装器，**只要状态实体类型相同，类型就相同**。所以 `std::bind_front(add, 1)` 与 `std::bind_front(mul, 2)`（`add`、`mul` 都是 `int(int, int)`，退化后都是 `int(*)(int, int)`）是同一类型，可以出现在条件运算符的两个分支里、存进同一个变量。而两个不同的 lambda 闭包类型不同，绑定它们得到的包装器类型也不同。

```cpp run title="wrapper_types.cpp" ok
#include <functional>
#include <memory>
#include <type_traits>
int add(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }
static_assert(std::is_same_v<decltype(std::bind_front(add, 1)), decltype(std::bind_front(mul, 2))>);
using Owning = decltype(std::bind_front(add, std::make_unique<int>()));
static_assert(!std::is_copy_constructible_v<Owning>);   // ¶7：状态实体只能移动
static_assert(std::is_move_constructible_v<Owning>);
int main() {
  bool c = true;
  auto g = c ? std::bind_front(add, 1) : std::bind_front(mul, 2);   // ¶8：同一类型
  return g(1) - 2;
}
```

## `std::invoke` 与 `std::invoke_r`（[func.invoke]）

```cpp
template<class F, class... Args>
  constexpr invoke_result_t<F, Args...> invoke(F&& f, Args&&... args)
    noexcept(is_nothrow_invocable_v<F, Args...>);
template<class R, class F, class... Args>
  constexpr R invoke_r(F&& f, Args&&... args)
    noexcept(is_nothrow_invocable_r_v<R, F, Args...>);
```

- ¶1 / ¶3 **Constraints**：`is_invocable_v<F, Args...>` / `is_invocable_r_v<R, F, Args...>`。这意味着不可调用时它们**不参与重载决议**——对 SFINAE 友好，可以放在 `requires` 表达式里探测。
- ¶2 / ¶4 **Returns**：*INVOKE* / *INVOKE*&lt;R&gt;，实参原样完美转发。
- 返回类型 `invoke_result_t` 精确保留了 *INVOKE* 表达式的类型与值类别（`decltype` 语义），所以 `invoke(pmd, std::move(obj))` 返回 `int&&`。
- `noexcept` 条件直接取自 [[meta]] 中的 `is_nothrow_invocable(_r)`，后者正是用“*INVOKE* 表达式已知不抛异常”定义的。
- 两者都是 **freestanding** 的，也都是 `constexpr`：`invoke` 在 C++17 引入，C++20 起成为 `constexpr`（[[P1065R2]]）；`invoke_r` 是 C++23 新增的（[[P2136R3]]），从一开始就是 `constexpr`。

`invoke` 与 [[meta]] 的关系可以这样记：**`<type_traits>` 回答“能不能调、调出来什么类型、抛不抛”，`std::invoke` 负责“真的去调”，两边用的是同一个 *INVOKE* 定义**。`invoke_result_t<F, Args...>` 就是 `decltype(std::invoke(declval<F>(), declval<Args>()...))`。

```cpp run title="constexpr_invoke.cpp" ok
#include <functional>
struct Emp { int id; double salary; };
constexpr int sq(int x) { return x * x; }
static_assert(std::invoke(sq, 5) == 25);                     // C++20 起 constexpr
static_assert(std::invoke(&Emp::id, Emp{3, 1.0}) == 3);      // 数据成员指针也行
static_assert(std::invoke_r<long>(sq, 3) == 9L);             // INVOKE<long>：结果隐式转换为 long
int main() {}
```

!!! pitfall "`invoke_r<void>` 会吞掉返回值"
    `std::invoke_r<void>(f)` 等于 `static_cast<void>(std::invoke(f))`。当你写泛型代码、`R` 由用户指定时，`R = void` 会把一个可能携带错误码的返回值静默丢弃，`[[nodiscard]]` 也帮不上忙。

## libc++ 实现笔记

- **`__type_traits/invoke.h`**：libc++ 的内部 `std::__invoke`、`__invoke_result_t`、`__is_invocable_v` 等都定义在这里。在 Clang 上（`__has_builtin(__builtin_invoke)`），它们直接转发给编译器内建的 **`__builtin_invoke`**——编译器自己实现 *INVOKE* 的七个分支，省掉大量模板实例化，编译速度和诊断信息都更好。没有这个内建时，回退到经典实现：六个 `__enable_if_bullet1` … `__enable_if_bullet6` 别名模板逐条对应 ¶1.1–¶1.6，外加 ¶1.7 的兜底重载，与标准条文几乎一一对应（细节差异：回退实现用 `__decay_t` 而不是 `remove_cvref_t` 判定 `t1` 的类型，对类类型二者等价）。
- **`__functional/invoke.h`**：公开的 `std::invoke`（`_LIBCPP_CONSTEXPR_SINCE_CXX20`）与 `std::invoke_r`（C++23，用 `if constexpr (is_void_v<_Result>)` 分出 `void` 情形）。前文提到的 `reference_converts_from_temporary` 的 TODO 就在这里。
- **`__functional/perfect_forward.h`**：`__perfect_forward_impl` 是 libc++ 对“完美转发调用包装器”的通用实现，`not_fn`、`bind_front`、`bind_back` 都派生自它；四种限定的 `operator()` 各配一个 `= delete` 版本，落实上文“不许退而求其次”的要求。

## 历史演进

!!! history
    - **C++11**：*INVOKE* 作为说明用伪函数进入标准（源自 TR1；当时只有对象、指针两种 `t1` 形态），服务于 `bind`、`function`、`thread`、`result_of`。
    - **C++17**：`std::invoke` 成为公开函数；`result_of` 被 `invoke_result` 取代；*INVOKE* 增加 `reference_wrapper` 的两条分支（¶1.2、¶1.5）。
    - **C++20**：`invoke`、`reference_wrapper`、`bind`、`not_fn`、`mem_fn` 等全面 `constexpr`（[[P1065R2]]）；`bind_front` 引入，“完美转发调用包装器 / 调用模式”的规格写法随之定型。
    - **C++23**：`invoke_r`（[[P2136R3]]）；*INVOKE*&lt;R&gt; 禁止把引用绑到临时量（[[P2255R2]]）。

## 思考题

!!! question "思考题 1"
    `std::optional<Widget> o = ...; std::invoke(&Widget::draw, o);` 能编译吗？如果能，走的是哪个分支？`o` 为空时会怎样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

能编译。`optional<Widget>` 既不是 `Widget`、不派生自 `Widget`，也不是 `reference_wrapper`，于是落到 ¶1.3：`((*o).*f)()`。`optional` 恰好有 `operator*`，所以表达式良构。`o` 为空时 `*o` 违反 `optional::operator*` 的前置条件（C++26 中这是一条 hardened precondition：在 hardened 实现中会触发契约违约，否则是未定义行为）。*INVOKE* 不关心 `*t1` 的语义，只要语法上成立。
</details>

!!! question "思考题 2"
    `is_invocable_r_v<const std::string&, std::string(*)()>` 按当前草案应为何值？`is_invocable_r_v<std::string_view, std::string(*)()>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一个为 **false**：调用结果是 `std::string` 纯右值，绑定到 `const std::string&` 需要物化临时量，`reference_converts_from_temporary_v` 为 true，按 ¶2 *INVOKE*&lt;R&gt; 非良构，[[meta]] 中的 `is_invocable_r` 随之为 false（libc++ 目前仍给出 true，见上文）。

第二个为 **true**：`R = string_view` 不是引用类型，`reference_converts_from_temporary` 只针对引用 `R`，这一条管不到。`string_view` 照样指向一个马上要销毁的临时 `string`——这条规则只防得住“引用绑定临时量”，防不住“视图类型指向临时量”。
</details>

!!! question "思考题 3"
    为什么 `mem_fn` 的结果可以是“简单调用包装器”，而 `bind_front` 的结果不行？

<details markdown="1">
<summary>展开查看答案与解析</summary>

简单调用包装器（¶6）要求无条件可复制构造、可复制赋值，且这些操作 `constexpr`、不抛异常。`mem_fn` 唯一的状态实体是一个成员指针，天然满足。`bind_front` 的状态实体是用户提供的任意类型——可能只能移动（`unique_ptr`）、复制可能抛异常（`std::string`）、可能不可赋值（含引用成员的 lambda）——所以标准只能给出 ¶7 的“逐成员复制/移动”语义。
</details>

## 小结

!!! summary
    | 概念 | 要点 |
    |---|---|
    | 可调用类型 | 函数对象类型 ∪ 成员指针类型 |
    | *INVOKE* ¶1.1–1.3 | 成员函数指针：对象/派生对象 → `reference_wrapper` → 其余一律 `*t1` |
    | *INVOKE* ¶1.4–1.6 | 数据成员指针，仅 N = 1；值类别随 `t1` |
    | *INVOKE* ¶1.7 | 其余一律 `f(t1, …, tN)` |
    | *INVOKE*&lt;R&gt; | `void` → 丢弃；否则隐式转换；引用绑临时量 → 非良构（C++23） |
    | 调用包装器 | 至少可移动、可析构 |
    | 参数转发调用包装器 | 调用实参以引用转发（`bind`） |
    | 完美转发调用包装器 | 连状态实体也按包装器的值类别/const 转发；与调用模式表达式等价，不可“回退”（`bind_front`、`not_fn`） |
    | 简单调用包装器 | 再加无条件可复制、constexpr noexcept 的复制/移动/赋值（`mem_fn`） |
    | `invoke` / `invoke_r` | Constraints 保证 SFINAE 友好；`constexpr`；与 `is_invocable` 族同源 |
