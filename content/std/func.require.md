---
title: 函数对象的要求：INVOKE 与调用包装器
summary: 标准库里凡是要调用一个可调用物的地方，都归结为 INVOKE(f, t1, …, tN) 这个七分支的定义；本页讲它、它的带返回类型版本 INVOKE<R>、std::invoke / invoke_r，以及 bind、bind_front、not_fn、mem_fn 所依赖的几层调用包装器概念。
status: done
covers: func.def, func.invoke
papers: P1065R2, P2136R3, P2255R2
related: function.objects, refwrap, func.bind, func.bind.partial, func.not.fn, func.memfn, func.wrap, meta, expr.mptr.oper, expr.call, over.call.object, defns.expression.equivalent
tags: 标准库, functional, INVOKE, invoke, 调用包装器, 成员指针
updated: 2026-10-19
---

!!! tldr
    - 成员指针不能写成 `f(obj)` 来调用。*INVOKE* 把成员函数指针、数据成员指针和普通可调用物统一成一种调用，`std::invoke`、`function`、`bind`、`is_invocable` 等都按它来规定。
    - *INVOKE* 按顺序试七个分支：对象本身、`reference_wrapper`、其余一律解引用 `*t1`；数据成员指针只接受一个实参。分支只按类型挑选，挑中之后表达式不合法就是不合法，不会退到下一支。
    - *INVOKE*&lt;R&gt; 把结果隐式转换成 `R`，`R` 为 `void` 时丢弃结果。C++23 起，如果转换要把引用绑到临时量上，就是非良构的。
    - 调用包装器分几层：参数转发（`bind`）、完美转发（`bind_front`、`not_fn`，连存储的状态也按包装器的值类别转发）、简单（`mem_fn`，无条件可复制）。
    - 完美转发调用包装器与它的调用模式表达式等价：目标对象的某个重载被弃置时，包装器不能偷偷改用另一个重载。

## 为什么需要 *INVOKE*

```cpp
struct Widget { int id; void draw() const; };
void free_draw(const Widget&);

Widget w; Widget* p = &w;
free_draw(w);          // 普通函数：f(args...)
(w.*&Widget::draw)();  // 成员函数指针：(obj.*pmf)(args...)
(p->*&Widget::draw)(); // 通过指针：(ptr->*pmf)(args...)
w.*&Widget::id;        // 数据成员指针：obj.*pmd
```

C++ 里能被调用的东西写法不统一。函数、函数指针、lambda 用 `f(args...)`；成员指针要写成 `(obj.*pmf)(args...)` 或 `obj.*pmd`（[[expr.mptr.oper]]），而对象一侧还可能是指针、智能指针或 `reference_wrapper`。

标准为此定义了一个仅用于说明（exposition-only）的伪函数 ***INVOKE*(f, t1, …, tN)**，把上面这些情形统一成一种写法。`std::invoke`、`reference_wrapper::operator()`、`bind`、`bind_front`、`not_fn`、`mem_fn`、`function`、`move_only_function`，`<type_traits>` 的 `is_invocable` 和 `invoke_result`，`std::apply`、`std::visit`、`std::thread`、ranges 算法的投影，它们的规格最后都写成 returns *INVOKE*(…)。

## 术语 [func.def]

**调用签名**（[[g:call-signature]]，call signature）是返回类型后跟一个括号括起来的实参类型列表，例如 `int(double, char)`。`std::function<R(Args...)>` 的模板实参就是一个调用签名。

**可调用类型**（[[g:callable-type]]，callable type）是函数对象类型或成员指针类型。函数对象类型指能出现在函数调用的后缀表达式位置的对象类型（[[function.objects]]）。成员指针不是函数对象类型，`pmf(obj)` 不是合法表达式，但它是可调用类型。可调用类型的对象叫**可调用对象**（callable object）。

**调用包装器类型**（[[g:call-wrapper]]，call wrapper type）持有一个**目标对象**（[[g:target-object]]，target object），并提供一个把调用转发给它的调用操作。目标对象是一个可调用对象，或者代表一个可调用对象的对象：`reference_wrapper` 里存的是指针，但它代表的是被引用的那个可调用物。调用包装器类型的对象叫**调用包装器**。

调用包装器还可以存一串对象和引用，调用时作为实参一起传给目标，它们统称**绑定实参实体**（[[g:bound-argument-entities]]，bound argument entities），例如 `bind_front(f, 1, 2)` 里的 `1` 和 `2`。目标对象和绑定实参实体合称**状态实体**（[[g:state-entities]]，state entities）。

## *INVOKE* 的七个分支 [func.require]

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
  std::printf("%d\n", std::invoke(pmf, d));             // ¶1.1 d.*pmf，Derived 派生自 Base
  std::printf("%d\n", std::invoke(pmf, std::ref(d)));   // ¶1.2 d.get().*pmf
  std::printf("%d\n", std::invoke(pmf, &d));            // ¶1.3 (*&d).*pmf
  std::printf("%d\n", std::invoke(pmf, up));            // ¶1.3 (*up).*pmf
  std::invoke(pmd, d) = 42;                             // ¶1.4 左值对象，得到 int&
  std::printf("%d\n", d.v);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, Derived{})), int&&>);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, &d)), int&>);
  static_assert(std::is_same_v<decltype(std::invoke(pmd, std::as_const(d))), const int&>);
}
```

¶1 *INVOKE*(f, t1, t2, …, tN) 按顺序试下面七个分支。前三个处理成员函数指针，接着三个处理数据成员指针，最后一个处理其余一切。表中 `U` 是 `remove_cvref_t<decltype(t1)>`，`T` 是成员指针所属的类：

| 分支 | f 是 | 条件 | 展开为 |
|---|---|---|---|
| ¶1.1 | `T` 的成员函数指针 | `U` 是 `T` 或 `T` 的派生类 | `(t1.*f)(t2, …, tN)` |
| ¶1.2 | 同上 | `U` 是 `reference_wrapper` 的特化 | `(t1.get().*f)(t2, …, tN)` |
| ¶1.3 | 同上 | 前两条都不满足 | `((*t1).*f)(t2, …, tN)` |
| ¶1.4 | `T` 的数据成员指针，且 N = 1 | `U` 是 `T` 或 `T` 的派生类 | `t1.*f` |
| ¶1.5 | 同上 | `U` 是 `reference_wrapper` 的特化 | `t1.get().*f` |
| ¶1.6 | 同上 | 前两条都不满足 | `(*t1).*f` |
| ¶1.7 | 其余所有情形 | | `f(t1, t2, …, tN)` |

几个细节：

- 第三支只要求 `*t1` 合法。裸指针、`unique_ptr`、`shared_ptr`、迭代器，甚至 `optional`，都会走 ¶1.3 或 ¶1.6。这里没有必须是指针的约束。
- 值类别随 `t1` 传播。¶1.1 和 ¶1.4 直接写 `t1.*f`，所以右值对象取数据成员得到 xvalue（`int&&`），`const` 左值得到 `const int&`，右值对象调用成员函数会选中 `&&` 限定的重载。走 ¶1.6 时 `*t1` 一般是左值，所以通过指针访问总是得到左值。`t1.get()` 也总是左值，因此通过 `reference_wrapper` 调用不到 `&&` 限定的成员函数。
- 数据成员指针只接受一个实参。多给了实参，¶1.4–¶1.6 的前提 N = 1 不成立，落到 ¶1.7 的 `f(t1, t2)`，而成员指针不能这样调用，于是非良构。
- ¶1.7 是普通的函数调用。它覆盖函数、函数引用、函数指针、带 `operator()` 的类，以及能隐式转换成函数指针的类（经由代理调用函数，见 [[over.call.object]]）。

### 分支只看类型

¶1.1 和 ¶1.4 用 `is_base_of_v` 判断派生关系，而 `is_base_of_v` 对私有基类和有歧义的基类也是 true。所以 `D` 私有继承 `B` 时，`INVOKE(&B::v, d)` 选中 ¶1.4，展开为 `d.*(&B::v)`，这个表达式因访问检查失败而非良构。它不会退一步去试 ¶1.6 的 `(*d).*f`。

```cpp run title="invoke_edges.cpp" ok
#include <functional>
#include <type_traits>
struct S { void f() && {} };
static_assert(std::is_invocable_v<decltype(&S::f), S>);    // 右值 t1：选中 && 限定成员
static_assert(!std::is_invocable_v<decltype(&S::f), S&>);  // 左值 t1：不行

struct B { int v; };
struct D : private B {};
static_assert(!std::is_invocable_v<int B::*, D&>);         // 选中 ¶1.4，访问失败；不会退到 ¶1.6
static_assert(!std::is_invocable_v<int B::*, B&, int>);    // 多给实参：落到 ¶1.7，非良构
int main() {}
```

!!! ub "空成员指针与空对象指针"
    *INVOKE* 不检查 `f` 和 `t1` 的值。`f` 是空成员指针时，`t1.*f` 是未定义行为（[[expr.mptr.oper]]）；走 ¶1.3 时 `t1` 是空指针，`*t1` 也是未定义行为。`std::invoke` 不会替你检查。

## *INVOKE*&lt;R&gt;：指定返回类型

很多组件知道调用结果要变成什么类型。`std::function<long(int)>` 包装一个返回 `int` 的函数时，结果要转换成 `long`；`std::function<void()>` 包装同一个函数时，结果直接丢掉。

¶2 *INVOKE*&lt;R&gt;(f, t1, …, tN) 就是为此定义的：

- `R` 是 cv `void` 时，它是 `static_cast<void>(INVOKE(f, t1, …, tN))`，结果被丢弃。显式转换到 `void` 也会抑制 `[[nodiscard]]` 警告。
- 否则，它是 *INVOKE*(f, t1, …, tN) 隐式转换为 `R`。隐式转换相当于复制初始化，`explicit` 转换函数不算数，口径与 `is_convertible` 一致。

### 不许把引用绑到临时量（C++23）

```cpp
std::function<const int&()> f = [] { return 42; };
const int& r = f();   // C++20：编译通过，r 悬垂
                      // C++23 起：f 的构造被拒绝
```

lambda 返回 `int` 纯右值。要把它转换成 `const int&`，必须先物化一个临时 `int`，这个临时量在 `f()` 返回时就销毁了。C++23 起 ¶2 的最后一句规定（[[P2255R2]]）：

!!! std
    If reference_converts_from_temporary_v&lt;R, decltype(*INVOKE*(f, t1, t2, …, tN))&gt; is true, *INVOKE*&lt;R&gt;(f, t1, t2, …, tN) is ill-formed.

`reference_converts_from_temporary_v<R, X>` 在 `R` 是引用类型、并且用 `X` 类型的表达式初始化 `R` 会把它绑到临时量上时为 true（[[meta]]）。`is_invocable_r` 是按 *INVOKE*&lt;R&gt; 是否良构来定义的，所以按标准 `is_invocable_r_v<const int&, int(*)()>` 是 false，`function` 的构造函数约束（[[func.wrap.func]]）和 `invoke_r` 都会拒绝这种组合。

这条规则只管引用。`is_invocable_r_v<std::string_view, std::string(*)()>` 仍然是 true，尽管得到的 `string_view` 指向一个马上销毁的临时 `string`。

!!! impl "libc++ 尚未实现这条约束"
    本机 libc++（LLVM 23）里，`is_invocable_r_v<const int&, int(*)()>` 仍为 true；`__functional/invoke.h` 的 `invoke_r` 里留着一条 `TODO: Use reference_converts_from_temporary_v once implemented` 注释。

    `std::invoke_r<const int&>(f)` 实际上还是会被拒绝，原因在核心语言：C++26 起 `return` 语句把返回的引用绑到临时量上是非良构的（[[stmt.return#6]]）。Clang 报 returning reference to local temporary object，错误位置在 libc++ 的 `invoke_r` 函数体内。标准要求的是约束不满足、不参与重载决议，libc++ 给出的是函数体里的硬错误。前面 `std::function<const int&()>` 的例子在本机也被拒绝，原因相同。

```cpp run title="invoke_r_dangling.cpp" error
#include <functional>
int f() { return 42; }
const int& r = std::invoke_r<const int&>(f);   // error: INVOKE<const int&> 非良构
int main() {}
```

## `std::invoke` 与 `std::invoke_r` [func.invoke]

```cpp
template<class F, class... Args>
  constexpr invoke_result_t<F, Args...> invoke(F&& f, Args&&... args)
    noexcept(is_nothrow_invocable_v<F, Args...>);
template<class R, class F, class... Args>
  constexpr R invoke_r(F&& f, Args&&... args)
    noexcept(is_nothrow_invocable_r_v<R, F, Args...>);
```

这两个函数把 *INVOKE* 和 *INVOKE*&lt;R&gt; 变成了可以直接调用的函数，实参原样完美转发（第 2、4 段）。它们的约束分别是 `is_invocable_v<F, Args...>` 和 `is_invocable_r_v<R, F, Args...>`（第 1、3 段）。不可调用时它们不参与重载决议，因此可以在 `requires` 表达式里探测。

`<type_traits>` 回答能不能调、结果是什么类型、会不会抛异常，`std::invoke` 负责真正去调，两边用的是同一个 *INVOKE* 定义。返回类型 `invoke_result_t<F, Args...>` 就是 *INVOKE* 表达式的 `decltype`，保留了值类别，所以 `invoke(pmd, std::move(obj))` 返回 `int&&`。`noexcept` 条件取自 `is_nothrow_invocable`。

`invoke` 在 C++17 加入，C++20 起是 `constexpr`（[[P1065R2]]）。`invoke_r` 在 C++23 加入（[[P2136R3]]），一开始就是 `constexpr`。两者在独立实现（freestanding）中也必须提供。

```cpp run title="constexpr_invoke.cpp" ok
#include <functional>
struct Emp { int id; double salary; };
constexpr int sq(int x) { return x * x; }
static_assert(std::invoke(sq, 5) == 25);                     // C++20 起 constexpr
static_assert(std::invoke(&Emp::id, Emp{3, 1.0}) == 3);      // 数据成员指针
static_assert(std::invoke_r<long>(sq, 3) == 9L);             // 结果隐式转换为 long
int main() {}
```

## 调用包装器的几个层级

`bind`、`bind_front`、`not_fn`、`mem_fn` 的规格只说返回某一层调用包装器、调用模式是什么，具体语义都在 ¶3–¶8 里。

| 层级 | 增加的要求 | 标准库中的例子 |
|---|---|---|
| 调用包装器 | 可移动构造、可析构 | 所有 |
| 参数转发调用包装器 | 调用实参以引用转发 | `bind` |
| 完美转发调用包装器 | 状态实体也按包装器的值类别和 const 转发 | `bind_front`、`bind_back`、`not_fn` |
| 简单调用包装器 | 无条件可复制、可赋值，相关操作 `constexpr` 且不抛异常 | `mem_fn` |

### 参数转发调用包装器（¶3）

¶3 所有调用包装器都满足 *Cpp17MoveConstructible* 和 *Cpp17Destructible*。是否可复制取决于状态实体（见 ¶7）。

**参数转发调用包装器**（[[g:argument-forwarding-call-wrapper]]，argument forwarding call wrapper）能接受任意实参列表，并把实参以引用形式交给目标：右值实参作为右值引用，左值实参作为左值引用。注 1 说明，典型实现是一个形如 `template<class... UnBoundArgs> R operator()(UnBoundArgs&&...) cv-qual;` 的调用运算符，参数是转发引用（[[g:forwarding-reference]]）。

`std::bind` 的结果属于这一层。调用时传入的实参被完美转发，而绑定的函数和实参总是作为左值交出去，具体见 [[func.bind]]。

### 完美转发调用包装器与调用模式（¶4、¶5）

¶4 **完美转发调用包装器**（[[g:perfect-forwarding-call-wrapper]]，perfect forwarding call wrapper）在参数转发之上，把状态实体也一起转发。包装器作为左值被调用时，类型为 `T` 的状态实体以 `cv T&` 交出，否则以 `cv T&&` 交出。`cv` 是包装器自身的 cv 限定，不能含 `volatile`。

¶5 **调用模式**（[[g:call-pattern]]，call pattern）规定完美转发调用包装器被调用时的语义。对包装器的一次后缀调用，与把调用模式里的实参和状态实体替换成上述引用后得到的表达式[[g:expression-equivalent|表达式等价]]。例如 `bind_front` 的调用模式是 `invoke(fd, bound_args..., call_args...)`（[[func.bind.partial]]），于是对 `auto g = std::bind_front(f, a);`：

- `g(x)` 等价于 `invoke(static_cast<FD&>(fd), static_cast<BoundArgs&>(bound_args)..., x)`；
- `std::move(g)(x)` 等价于用 `FD&&`、`BoundArgs&&` 的版本；
- `std::as_const(g)(x)` 等价于用 `const FD&`、`const BoundArgs&` 的版本。

表达式等价要求两个表达式同时良构或同时非良构，`noexcept` 性质相同，是否为常量子表达式相同，效果相同。由此得出一个容易忽视的结论：

```cpp run title="no_fallback.cpp" error
#include <functional>
struct F {
  void operator()() const {}
  void operator()() = delete;
};
int main() {
  auto g = std::bind_front(F{});
  g();   // error: fd 是 F&，选中被弃置的非 const 版本
}
```

`g` 是非 const 左值，调用模式里的 `fd` 是 `F&`，重载决议选中被弃置的非 const `operator()`，所以 `g()` 必须是非良构的。如果改成 `const auto g = ...`，`g()` 就是良构的，调用 const 版本。

如果实现只是写四个带约束的 `operator()`（`&`、`const&`、`&&`、`const&&`），非 const 的那个会因约束不满足而退出，`g()` 就悄悄选中包装器的 `const&` 版本，转而调用目标的 const 重载，不再与调用模式表达式等价。所以实现必须在调用模式不良构时把对应的重载显式弃置，而不是让它消失。libc++ 的 `__functional/perfect_forward.h` 正是这样做的：每个限定版本都配一个 `= delete` 的版本。

### 简单调用包装器（¶6）

¶6 **简单调用包装器**（[[g:simple-call-wrapper]]，simple call wrapper）是满足 *Cpp17CopyConstructible* 和 *Cpp17CopyAssignable* 的完美转发调用包装器，并且复制构造、移动构造和赋值运算符都是不抛异常的 `constexpr` 函数。标准库中只有 `mem_fn` 返回这一层（[[func.memfn]]）：它唯一的状态是一个成员指针，自然可以无条件复制和赋值。

`bind_front` 做不到这一点，因为它的状态实体是用户提供的任意类型：可能只能移动（`unique_ptr`），复制可能抛异常（`std::string`），也可能不可赋值（含引用成员的 lambda）。

### 复制、移动与类型同一性（¶7、¶8）

¶7 参数转发调用包装器的复制和移动构造函数，看起来就像逐个复制或移动它的状态实体。注 2 指出，因此它们的异常说明和 `constexpr` 性质都与隐式定义的版本一致。绑定了 `unique_ptr` 的 `bind_front` 结果只能移动；所有状态实体都能不抛异常地移动时，包装器的移动构造是 `noexcept` 的，这决定了它放进 `vector` 后扩容时是移动还是复制。¶7 只约束构造函数，赋值运算符由各个组件自己规定。

¶8 同一个标准库函数模板返回的参数转发调用包装器，只要状态实体的类型相同，类型就相同。`add` 和 `mul` 都是 `int(int, int)`，退化后都是 `int(*)(int, int)`，所以 `std::bind_front(add, 1)` 和 `std::bind_front(mul, 2)` 是同一类型，可以放在条件运算符的两个分支里。两个不同的 lambda 闭包类型不同，绑定它们得到的包装器类型也不同。

```cpp run title="wrapper_types.cpp" ok
#include <functional>
#include <memory>
#include <type_traits>
int add(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }
static_assert(std::is_same_v<decltype(std::bind_front(add, 1)),
                             decltype(std::bind_front(mul, 2))>);   // ¶8
using Owning = decltype(std::bind_front(add, std::make_unique<int>()));
static_assert(!std::is_copy_constructible_v<Owning>);   // ¶7：状态实体只能移动
static_assert(std::is_move_constructible_v<Owning>);
int main() {
  bool c = true;
  auto g = c ? std::bind_front(add, 1) : std::bind_front(mul, 2);   // 同一类型
  return g(1) - 2;
}
```

!!! impl "libc++ 怎样实现 *INVOKE*"
    libc++ 的内部 `std::__invoke`、`__invoke_result_t` 等定义在 `__type_traits/invoke.h`。在 Clang 上它们直接转发给编译器内建的 `__builtin_invoke`，由编译器自己实现七个分支，省掉大量模板实例化。没有这个内建时，回退实现用六个别名模板逐条对应 ¶1.1–¶1.6，再加一个 ¶1.7 的兜底重载，与条文几乎一一对应。

## 历史与演进

!!! history
    - C++11：*INVOKE* 从 TR1 进入标准，服务于 `bind`、`function`、`thread`、`result_of`。当时对象一侧只分对象本身和其余（解引用）两种。
    - C++17：`std::invoke` 成为公开函数，`invoke_result` 取代 `result_of`。*INVOKE* 增加 `reference_wrapper` 的两个分支 ¶1.2、¶1.5（[[LWG2219]]）。在此之前 `reference_wrapper` 走解引用分支，而它没有 `operator*`，按条文 `invoke(&S::f, std::ref(s))` 是非良构的。
    - C++20：`invoke`、`reference_wrapper`、`bind`、`not_fn`、`mem_fn` 等成为 `constexpr`（[[P1065R2]]）；`bind_front` 加入，完美转发调用包装器和调用模式的写法随之定型。
    - C++23：加入 `invoke_r`（[[P2136R3]]）；*INVOKE*&lt;R&gt; 禁止把引用绑到临时量（[[P2255R2]]）。

## 常见误解

!!! pitfall "`invoke_r<void>` 只是换了个返回类型"
    `std::invoke_r<void>(f)` 等于 `static_cast<void>(std::invoke(f))`。泛型代码里 `R` 由用户指定时，`R = void` 会把一个可能携带错误码的返回值静默丢弃，`[[nodiscard]]` 也不会报警。

## 思考题

!!! question "思考题 1"
    `std::optional<Widget> o = ...; std::invoke(&Widget::draw, o);` 能编译吗？走的是哪个分支？`o` 为空时会怎样？

<details markdown="1">
<summary>答案</summary>

能编译。`optional<Widget>` 既不是 `Widget` 或其派生类，也不是 `reference_wrapper`，于是落到 ¶1.3，展开为 `((*o).*f)()`。`optional` 恰好有 `operator*`，表达式良构。

`o` 为空时，`*o` 违反 `optional::operator*` 的前置条件。C++26 中这是一条加固前置条件：加固实现会以契约违反终止程序，其他实现中是未定义行为。*INVOKE* 只要求 `*t1` 在语法上成立，不关心它的语义。
</details>

!!! question "思考题 2"
    按当前草案，`is_invocable_r_v<const std::string&, std::string(*)()>` 是什么值？`is_invocable_r_v<std::string_view, std::string(*)()>` 呢？

<details markdown="1">
<summary>答案</summary>

第一个是 false。调用结果是 `std::string` 纯右值，绑定到 `const std::string&` 需要物化临时量，`reference_converts_from_temporary_v` 为 true，按 ¶2 *INVOKE*&lt;R&gt; 非良构，`is_invocable_r` 随之为 false。本机 libc++ 尚未实现这一条，仍然给出 true。

第二个是 true。`string_view` 不是引用类型，这条规则管不到它，尽管结果同样指向一个马上销毁的临时量。
</details>
