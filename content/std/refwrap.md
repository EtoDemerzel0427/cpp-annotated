---
title: 类模板 reference_wrapper
summary: 可复制、可赋值、平凡可复制的“引用”；用 FUN(T&)/FUN(T&&) 的约束技巧拒绝绑定右值，经 INVOKE 转发调用，C++26 起可直接比较；ref/cref 会解包，并为 common_reference 提供特化
status: done
covers: *
papers: P2944R3, P2655R3, LWG2993
related: func.require, function.objects, func.bind, tuple, pairs, meta, class.prop, basic.types, over.match, temp.deduct.guide, dcl.init.ref
tags: 标准库, functional, reference_wrapper, ref, cref, CTAD
updated: 2026-10-18
---

C++ 的引用不是对象：不能重新绑定（`r = x` 是给被引用者赋值），不能放进 `std::vector`，不能默认构造。`reference_wrapper<T>` 把“对 `T` 的引用”包装成一个**真正的对象**：可以复制、可以赋值（赋值改变的是“引用谁”）、可以放进容器、可以按值传递而不复制被引用者。它的实现就是一个 `T*`。

它在标准库里最重要的用途是**显式表达“按引用传”**：`std::bind`、`std::thread`、`std::make_pair`、`std::make_tuple` 默认按值保存实参（对实参做 decay），想让它们保存引用，就传 `std::ref(x)`。

前置知识：*INVOKE*（[[func.require]]）、平凡可复制类型（[[g:trivially-copyable-type]]，[[basic.types]]、[[class.prop]]）、引用初始化（[[dcl.init.ref]]）。

## 类概要与基本性质（[refwrap.general]）

成员一览（不逐字照抄概要）：

| 成员 | 说明 |
|---|---|
| `using type = T;` | 被引用的类型 |
| `template<class U> constexpr reference_wrapper(U&&) noexcept(see below);` | 唯一的“绑定”构造函数，带约束 |
| 复制构造 / 复制赋值 | `constexpr`、`noexcept`，复制的是“引用谁” |
| `constexpr operator T&() const noexcept;` / `constexpr T& get() const noexcept;` | 取回引用 |
| `template<class... A> operator()(A&&...) const` | 经 *INVOKE* 调用被引用的可调用物 |
| `friend operator==` / `operator<=>`（各三个） | C++26 新增的比较 |
| `template<class T> reference_wrapper(T&) -> reference_wrapper<T>;` | 推导指引 |

注意**没有默认构造函数**——引用必须绑定到某个东西。所有成员都是 `constexpr`。

¶1：`reference_wrapper<T>` 是 *Cpp17CopyConstructible* 且 *Cpp17CopyAssignable* 的、对 `T` 类型**对象或函数**的引用的包装。`T` 可以是函数类型：`reference_wrapper<int(int)>` 合法，调用它就调用那个函数。

!!! std
    reference_wrapper&lt;T&gt; is a trivially copyable type.

¶2 规定它是**平凡可复制类型**（[[basic.types]]）。这是一个可观察的、可移植的保证：可以 `memcpy` 它、可以放进要求平凡可复制的 `std::atomic`、`std::bit_cast` 它，按值传参时 ABI 上通常用寄存器传递。概要里**声明**了复制构造函数和复制赋值运算符，看起来像是用户提供的——但概要中的声明只描述接口，¶2 要求实现让它们平凡（通常的做法是根本不声明，让编译器隐式生成；libc++ 的 `__functional/reference_wrapper.h` 正是如此，类里只有一个 `type* __f_;` 成员）。

¶3：`T` 可以是**不完整类型**。所以可以在类定义内部声明 `std::vector<std::reference_wrapper<Node>> children;`。注 1 提醒：在 `T` 不完整时使用比较运算符，可能因约束检查的结果在不同实例化点不同而成为 IFNDR（[[temp.point]]、[[temp.constr.atomic]]）。

## 构造：用 `FUN` 拒绝右值（[refwrap.const]）

这是本节最有法律味道的一段。构造函数是一个**模板**，接受任意 `U&&`：

!!! std
    Let *FUN* denote the exposition-only functions `void FUN(T&) noexcept; void FUN(T&&) = delete;` Constraints: The expression *FUN*(declval&lt;U&gt;()) is well-formed and is_same_v&lt;remove_cvref_t&lt;U&gt;, reference_wrapper&gt; is false.

¶2 的约束翻译成人话：**拿 `U` 类型的表达式去调用一对重载 `FUN(T&)` / `FUN(T&&) = delete`，如果重载决议选中了 `FUN(T&)` 且调用良构，构造函数才可行**。

- 实参是 `T` 左值：精确匹配 `FUN(T&)`，OK。
- 实参是右值（如字面量 `42` 对 `reference_wrapper<const int>`）：`FUN(T&&)` 更好（右值优先绑定右值引用，[[over.ics.rank]]），而它是弃置的——调用非良构，**约束不满足**，构造函数不参与重载决议。
- 实参是能**隐式转换为 `T&`** 的类类型（例如有 `operator int&()` 的类）：`FUN(T&)` 通过用户定义转换可行，OK。这是旧设计做不到的。
- 实参本身就是 `reference_wrapper`：第二个条件排除它，让复制构造函数接手。

¶3 **Effects**：如同 `T& r = std::forward<U>(u);` 然后存下 `r` 的地址。¶4：`noexcept` 与 `FUN(declval<U>())` 一致——绑定 `T&` 时若需要调用可能抛出的转换函数，构造函数也就可能抛出。

### 为什么不直接写 `reference_wrapper(T&)` + `reference_wrapper(T&&) = delete`？

C++11 的原始设计正是这两个构造函数。问题在于**弃置函数照样参与重载决议**：`reference_wrapper(T&&) = delete` 的存在让编译器认为“从右值到 `reference_wrapper<T>` 存在一个用户定义转换”，于是在其他函数的重载决议里，它会和别的转换打成平手：

```cpp run title="old_design_ambiguity.cpp" error
struct Old {             // 模拟 C++11 的设计
  Old(int&) {}
  Old(int&&) = delete;
};
struct from_int { from_int(int) {} };
void meow(Old) {}
void meow(from_int) {}
int main() { meow(0); }  // error：歧义——两个都是“可行的”用户定义转换
```

[[LWG2993]] 把构造函数改为带约束的模板，右值时构造函数**根本不可行**，歧义消失：

```cpp run title="fun_trick.cpp" ok
#include <functional>
#include <type_traits>
#include <cstdio>
struct from_int { from_int(int) {} };
void meow(std::reference_wrapper<int>) { std::puts("ref"); }
void meow(from_int) { std::puts("from_int"); }

struct Holder {
  int value = 7;
  operator int&() { return value; }   // 能产生 int 左值
};
static_assert(!std::is_constructible_v<std::reference_wrapper<const int>, int>);   // 右值：被约束挡掉
static_assert(std::is_constructible_v<std::reference_wrapper<const int>, const int&>);
static_assert(!std::is_convertible_v<int, std::reference_wrapper<int>>);           // trait 也如实回答
int main() {
  meow(0);                            // from_int：无歧义
  Holder h;
  std::reference_wrapper<int> r = h;  // OK：FUN(h) 经转换函数选中 FUN(int&)
  r.get() = 8;
  std::printf("%d\n", h.value);       // 8
}
```

顺带，`is_convertible_v<int, reference_wrapper<int>>` 在旧设计下是 `false`（弃置函数让转换非良构），但“存在一个被弃置的候选”这件事仍会污染重载决议——这正是“trait 说不行、重载决议却当它可行”的不一致。约束模板让两者口径统一。

!!! note "为什么第二个约束必不可少"
    若没有 `!is_same_v<remove_cvref_t<U>, reference_wrapper>`，从一个**非 const 左值** `reference_wrapper` 复制时，模板构造函数（`U = reference_wrapper&`，绑定不加 const）会比复制构造函数（`const reference_wrapper&`）更匹配，而 `FUN(rw)` 又能经 `operator T&` 成立——复制就会被这个模板“劫持”，变成“先转换成 `T&` 再取地址”。第二个约束保证复制永远走那个平凡、`noexcept` 的复制构造函数。

¶5 复制构造函数：存储对 `x.get()` 的引用。

## 赋值、访问与调用（[refwrap.assign]、[refwrap.access]、[refwrap.invoke]）

- [refwrap.assign]/1：复制赋值的后置条件是 `*this` 存储对 `x.get()` 的引用——**重新绑定**，而不是给被引用者赋值。这是它与 `T&` 的根本差别。
- [refwrap.access]：`operator T&()` 与 `get()` 都返回存储的引用。隐式转换让 `reference_wrapper<int>` 能直接传给接受 `int&`/`int` 的函数；但成员访问（`rw.member`）不会触发隐式转换，得写 `rw.get().member`。
- [refwrap.invoke]：`operator()` 的返回值是 `INVOKE(get(), std::forward<ArgTypes>(args)...)`，¶1 **Mandates** `T` 是完整类型。返回类型 `invoke_result_t<T&, ArgTypes...>`、`noexcept(is_nothrow_invocable_v<T&, ArgTypes...>)`。因为走 *INVOKE*，`reference_wrapper<int (S::*)()>` 之类也能被调用。

`operator()` 让 `std::ref(functor)` 本身就是一个可调用物：把一个**有状态、不可复制或复制代价高**的函数对象交给按值接收的算法（`std::for_each`、`std::thread`、`std::function`）时，传 `std::ref(f)` 可以避免复制，并让状态的修改反映在原对象上。

## 比较（[refwrap.comparisons]）{{c++26}}

C++26 之前，`rw1 == rw2` 能否编译取决于 `T` 的 `operator==` 是否是可以经隐式转换找到的非模板函数——对 `int` 能工作（内建 `==` 经 `operator int&` 转换），对 `std::string` 就不行（`operator==` 是模板，模板实参推导不考虑用户定义转换）。[[P2944R3]] 为它加上了三对隐藏友元：

| 运算符 | 形参 | Constraints |
|---|---|---|
| `==` / `<=>` | `(reference_wrapper, reference_wrapper)` | `x.get() == y.get()` 良构且可转 `bool` / *synth-three-way* 良构 |
| `==` / `<=>` | `(reference_wrapper, const T&)` | 同上，右侧为 `y` |
| `==` / `<=>` | `(reference_wrapper, reference_wrapper<const T>)` | 另要求 `!is_const_v<T>` |

- 比较的是**被引用的值**，不是地址。想比较“是否引用同一个对象”，写 `&a.get() == &b.get()`。
- `<=>` 使用 *synth-three-way*（库在 [[expos.only.entity]] 中定义的说明用工具：有 `<=>` 用 `<=>`，否则用 `<` 合成 `weak_ordering`），所以只有 `<` 的旧类型也能用。
- 第三对的 `!is_const_v<T>` 是为了避免 `reference_wrapper<const T>` 与自己比较时与第一对重载重复。
- 它们都是隐藏友元（[[g:hidden-friend]]），只能经 ADL 找到，不会污染命名空间。

## `ref` 与 `cref`（[refwrap.helpers]）

```cpp
template<class T> constexpr reference_wrapper<T>       ref(T&) noexcept;
template<class T> constexpr reference_wrapper<const T> cref(const T&) noexcept;
template<class T> void ref(const T&&) = delete;
template<class T> void cref(const T&&) = delete;
template<class T> constexpr reference_wrapper<T>       ref(reference_wrapper<T>) noexcept;
template<class T> constexpr reference_wrapper<const T> cref(reference_wrapper<T>) noexcept;
```

- 对左值返回包装；对右值，`const T&&` 版本更匹配，而它被弃置——`std::ref(42)`、`std::cref(std::string("x"))` 都是编译期错误，防住了“包装一个马上要死的临时量”。（这里用 `const T&&` 而不是 `T&&`，是因为 `T&&` 在模板里是转发引用，会把左值也吃掉。）
- 对 `reference_wrapper` 实参，**不再套一层**：`ref(ref(x))` 仍是 `reference_wrapper<T>`，`cref(ref(x))` 是 `reference_wrapper<const T>`。
- ¶1：这些函数模板的 `T` 可以是不完整类型。

```cpp run title="ref_rvalue.cpp" error
#include <functional>
int main() {
  auto r = std::ref(42);                     // error：调用了被弃置的 ref(const T&&)
  std::reference_wrapper<const int> c(42);   // error：FUN 约束不满足，没有可行构造函数
}
```

### 被库“解包”的地方

`reference_wrapper` 作为“我要引用”的信号，在多处被识别并解包为 `T&`：

- `make_pair`、`make_tuple` 用 `unwrap_ref_decay_t`：`make_pair(std::ref(x), 1)` 得到 `pair<int&, int>`（[[pairs]]、[[tuple]]）；
- `bind` 的绑定实参若是 `reference_wrapper<T>`，调用时作为 `T&` 传出（[[func.bind]] ¶7.1）；
- *INVOKE* 的 ¶1.2、¶1.5 直接对 `reference_wrapper` 调用 `.get()`（[[func.require]]）。

而 `std::thread`、`bind_front` 没有专门的解包规则——它们存储 `reference_wrapper` 本身，调用时交出 `reference_wrapper` 对象，靠它的 `operator T&` 隐式转换为 `T&`。

## 与 `common_reference` 的配合（[refwrap.common.ref]）

C++20 的 `common_reference_t<reference_wrapper<int>&, int&>` 原本是 `int`（一个值类型），导致 `vector<reference_wrapper<int>>` 与 `vector<int>` 之类的范围组合在 `common_reference_with` 等概念下表现别扭。[[P2655R3]] 为 `basic_common_reference` 增加了两个偏特化：

- 说明用变量模板 *is-ref-wrapper* 识别 `reference_wrapper` 特化；
- 概念 *ref-wrap-common-reference-exists-with*&lt;R, T, RQ, TQ&gt; 要求 `R` 是 `reference_wrapper`、`common_reference_t<typename R::type&, TQ>` 存在、且 `RQ` 可转换为它；
- 当这一关系**只在一个方向**成立时（`requires (... && !...)`，避免两个参数都是 `reference_wrapper` 时两个偏特化同时匹配而歧义），`type` 就是 `common_reference_t<typename R::type&, TQual<T>>`。

效果：`common_reference_t<reference_wrapper<int>&, int&>` 是 `int&`。

## CTAD

推导指引 `reference_wrapper(T&) -> reference_wrapper<T>;` 让 `std::reference_wrapper rw = x;` 推导为 `reference_wrapper<int>`（[[temp.deduct.guide]]）。没有它，构造函数模板 `reference_wrapper(U&&)` 中的 `U` 与类模板形参 `T` 无关，隐式推导指引推不出 `T`。

## 综合示例

```cpp run title="refwrap_tour.cpp" ok
#include <functional>
#include <type_traits>
#include <vector>
#include <algorithm>
#include <cstdio>
static_assert(std::is_trivially_copyable_v<std::reference_wrapper<int>>);   // ¶2
int main() {
  int a = 3, b = 1, c = 2;
  std::vector<std::reference_wrapper<int>> v{a, b, c};
  std::ranges::sort(v, std::less<int>{});      // 经 operator int& 比较被引用的值
  v[0].get() = 100;                            // v[0] 引用的是 b
  std::printf("%d %d %d\n", a, b, c);          // 3 100 2

  std::reference_wrapper rw = a;               // CTAD：reference_wrapper<int>
  static_assert(std::is_same_v<decltype(rw), std::reference_wrapper<int>>);
  std::printf("%d\n", rw == 3);                // C++26：比较被引用的值
  rw = c;                                      // 重新绑定，a 不变
  std::printf("%d %d\n", a, rw.get());         // 3 2

  static_assert(std::is_same_v<std::common_reference_t<std::reference_wrapper<int>&, int&>, int&>);
}
```

## libc++ 实现笔记

`__functional/reference_wrapper.h`：

- 唯一数据成员 `type* __f_;`，复制操作全部隐式生成，因而平凡。
- `FUN` 被实现为私有静态成员 `static void __fun(_Tp&) _NOEXCEPT; static void __fun(_Tp&&) = delete;`，构造函数模板用 `__void_t<decltype(__fun(std::declval<_Up>()))>` 加 `enable_if` 做约束——一个条文里的说明用函数，几乎原样落地。
- 存储时用 `std::addressof`，所以被引用类型重载了 `operator&` 也无妨。
- C++26 的比较运算符用 `requires` 子句实现，`<=>` 走 `__synth_three_way`。
- 基类 `__weak_result_type<_Tp>` 是为 C++17 之前的 `result_type`、`argument_type` 等成员类型准备的遗留设施（这些成员在 C++20 被移除）。

## 历史演进

!!! history
    - **C++11**：从 TR1 引入，带 `reference_wrapper(T&)` + 弃置的 `reference_wrapper(T&&)`。
    - **C++17**：增加推导指引；*INVOKE* 直接识别 `reference_wrapper`。
    - **C++20**：全面 `constexpr`；构造函数改为 `FUN` 约束模板（[[LWG2993]]）；`T` 允许不完整（`ref`/`cref` 同样）。
    - **C++23**：`basic_common_reference` 特化（[[P2655R3]]）。
    - **C++26**：`==` / `<=>`（[[P2944R3]]）。

## 思考题

!!! question "思考题 1"
    `std::reference_wrapper<const std::string> r = "hello";` 能编译吗？`std::reference_wrapper<const std::string> r = some_std_string_view;` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

都不能。`FUN(declval<const char(&)[6]>())`：`FUN(const string&)` 需要先构造一个临时 `std::string`——即实参转换后成为右值，而 `FUN(const string&&)` 对这个转换结果同样可行且更好（绑定右值），它是弃置的，调用非良构，约束不满足。`string_view` 到 `string` 是 `explicit` 转换，`FUN` 两个重载都不可行，同样不满足约束。这正是 `FUN` 设计的目的：凡是需要物化临时量才能绑定的情形一律拒绝。
</details>

!!! question "思考题 2"
    为什么 `std::function<void()> f = std::ref(callable);` 是一个常见的优化手法？它有什么风险？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`reference_wrapper` 只有一个指针大小，且是平凡可复制的，`std::function` 的实现通常能把它放进小缓冲区（SBO）而不做堆分配；复制 `f` 也只是复制指针，而不是复制可能很大的 `callable`。风险是生命周期：`f` 不拥有 `callable`，`callable` 先销毁就成了悬垂引用。C++26 的 `std::function_ref` 把这种“非拥有调用”做成了专门的类型（[[func.wrap.ref]]）。
</details>

## 小结

!!! summary
    | 要点 | 内容 |
    |---|---|
    | 本质 | 一个 `T*`；可复制、可赋值（重新绑定）、平凡可复制；`T` 可不完整 |
    | 构造约束 | `FUN(T&)` / `FUN(T&&) = delete`：拒绝右值与需要临时量的转换，允许经转换函数得到的左值；不参与重载决议而非“可行但弃置” |
    | 访问 | `get()`、`operator T&`；成员访问不会隐式转换 |
    | 调用 | `operator()` = *INVOKE*(`get()`, args...)，Mandates `T` 完整 |
    | 比较（C++26） | 比较被引用的值；`<=>` 用 *synth-three-way*；隐藏友元 |
    | `ref`/`cref` | 右值版本弃置；对 `reference_wrapper` 不再嵌套 |
    | 解包 | `make_pair`/`make_tuple`、`bind`、*INVOKE* 识别它 |
    | `common_reference` | `common_reference_t<reference_wrapper<int>&, int&>` 为 `int&`（C++23） |
