---
title: 类模板 reference_wrapper
summary: reference_wrapper<T> 是一个可复制、可赋值、平凡可复制的引用包装，ref/cref 用它告诉 bind、make_pair 等组件按引用保存实参；本页讲它的构造约束怎样拒绝右值、调用与比较的语义，以及它与 common_reference 的配合。
status: done
covers: *
papers: P2944R3, P2655R3, P0357R3, LWG2993
related: func.require, function.objects, func.bind, tuple, pairs, meta, class.prop, basic.types, over.match, temp.deduct.guide, dcl.init.ref
tags: 标准库, functional, reference_wrapper, ref, cref, CTAD
updated: 2026-10-19
---

!!! tldr
    - `reference_wrapper<T>` 内部就是一个 `T*`。它可以复制、放进容器；赋值让它改为引用另一个对象，而不是给被引用者赋值。它保证是平凡可复制的。
    - 构造函数用一对说明用函数 `FUN(T&)` / `FUN(T&&) = delete` 做约束：右值、需要物化临时量的转换都被拒绝，并且是不参与重载决议，而不是可行但弃置。
    - `std::ref(x)`、`std::cref(x)` 生成它，用来让 `bind`、`thread`、`make_pair`、`make_tuple` 等默认按值保存的组件改为按引用保存。`ref(42)` 这类右值调用是编译错误。
    - 调用 `rw(args...)` 等于 *INVOKE*(`rw.get()`, args...)。C++26 起 `==`、`<=>` 比较的是被引用的值，不是地址。
    - C++23 起 `common_reference_t<reference_wrapper<int>&, int&>` 是 `int&`。

## 一个可以重新绑定的引用

```cpp run title="refwrap_tour.cpp" ok
#include <functional>
#include <type_traits>
#include <vector>
#include <algorithm>
#include <cstdio>
int main() {
  int a = 3, b = 1, c = 2;
  std::vector<std::reference_wrapper<int>> v{a, b, c};
  std::ranges::sort(v, std::less<int>{});      // 经 operator int& 比较被引用的值
  v[0].get() = 100;                            // v[0] 引用的是 b
  std::printf("%d %d %d\n", a, b, c);          // 3 100 2

  std::reference_wrapper rw = a;               // CTAD：reference_wrapper<int>
  std::printf("%d\n", rw == 3);                // C++26：比较被引用的值，打印 1
  rw = c;                                      // 改为引用 c，a 不变
  std::printf("%d %d\n", a, rw.get());         // 3 2
}
```

C++ 的引用不是对象：不能重新绑定（`r = x` 是给被引用者赋值），不能放进 `std::vector`，也不能默认构造。`reference_wrapper<T>` 把对 `T` 的引用包装成一个对象。它可以复制，可以按值传递而不复制被引用者，赋值改变的是它引用谁。

它在标准库里最重要的用途是明确表示按引用传递。`std::bind`、`std::thread`、`std::make_pair`、`std::make_tuple` 默认对实参做退化（decay）后按值保存，要让它们保存引用，就传 `std::ref(x)`。

## 基本性质 [refwrap.general]

| 成员 | 说明 |
|---|---|
| `using type = T;` | 被引用的类型 |
| `template<class U> reference_wrapper(U&&)` | 唯一的绑定构造函数，带约束（见下节） |
| 复制构造、复制赋值 | `noexcept`，复制的是引用谁 |
| `operator T&()`、`get()` | 取回引用 |
| `operator()(ArgTypes&&...)` | 经 *INVOKE* 调用被引用的可调用物 |
| `operator==`、`operator<=>` 各三个 | C++26 新增，隐藏友元 |
| `reference_wrapper(T&) -> reference_wrapper<T>` | 推导指引 |

所有成员都是 `constexpr`。没有默认构造函数，因为引用必须绑定到某个东西。

¶1 `reference_wrapper<T>` 满足 *Cpp17CopyConstructible* 和 *Cpp17CopyAssignable*，包装的是对 `T` 类型的对象或函数的引用。`T` 可以是函数类型：`reference_wrapper<int(int)>` 是合法的，调用它就是调用那个函数。

¶2 `reference_wrapper<T>` 是**平凡可复制**类型（[[g:trivially-copyable-type]]，[[basic.types]]），即可以用 `memcpy` 复制其对象表示的类型。所以可以 `std::bit_cast` 它、把它放进 `std::atomic`，按值传参时 ABI 上通常用寄存器传递。类概要里写出了复制构造函数和复制赋值运算符，但概要只描述接口，¶2 要求它们是平凡的。libc++ 的做法是根本不声明它们，类里只有一个 `type* __f_;` 成员。

¶3 `T` 可以是不完整类型，所以可以在类定义内部写 `std::vector<std::reference_wrapper<Node>> children;`。注 1 提醒，在 `T` 不完整时使用比较运算符，约束检查的结果可能在不同的实例化点不同，程序因此成为非良构、不要求诊断（[[temp.point]]、[[temp.constr.atomic]]）。

## 构造函数为什么是模板 [refwrap.const]

直观的设计是两个构造函数：`reference_wrapper(T&)` 接受左值，`reference_wrapper(T&&) = delete` 拒绝右值。C++11 正是这样写的。问题在于弃置函数照样参与重载决议：

```cpp run title="old_design_ambiguity.cpp" error
struct Old {             // 模拟 C++11 的设计
  Old(int&) {}
  Old(int&&) = delete;
};
struct from_int { from_int(int) {} };
void meow(Old) {}
void meow(from_int) {}
int main() { meow(0); }  // error: 歧义，两个用户定义转换都可行
```

对实参 `0`，`Old(int&&)` 虽然被弃置，但它让从 `0` 到 `Old` 的用户定义转换成为可行的，于是和到 `from_int` 的转换打成平手。被弃置的函数只在被选中之后才报错，选不选它由重载决议决定。

¶1 当前的构造函数是一个带约束的模板 `template<class U> reference_wrapper(U&& u)`。约束借助一对说明用函数：

!!! std
    Let *FUN* denote the exposition-only functions `void FUN(T&) noexcept; void FUN(T&&) = delete;`

¶2 约束要求：表达式 *FUN*(declval&lt;U&gt;()) 良构，并且 `remove_cvref_t<U>` 不是 `reference_wrapper` 本身。换句话说，拿实参去调用这对重载，只有选中 `FUN(T&)` 时构造函数才参与重载决议：

- 实参是 `T` 左值：精确匹配 `FUN(T&)`，可行。
- 实参是右值：`FUN(T&&)` 更好（右值优先绑定右值引用，[[over.ics.rank]]），它被弃置，调用非良构，约束不满足。构造函数根本不是候选。
- 实参是能隐式转换为 `T&` 的类类型（例如有 `operator int&()` 的类）：`FUN(T&)` 经用户定义转换可行。旧设计做不到这一点。
- 实参本身是 `reference_wrapper`：第二个条件排除它，交给复制构造函数。

[[LWG2993]] 把构造函数改成了这种形式，开头的歧义随之消失：

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
static_assert(!std::is_constructible_v<std::reference_wrapper<const int>, int>);  // 右值：被约束挡掉
static_assert(std::is_constructible_v<std::reference_wrapper<const int>, const int&>);
int main() {
  meow(0);                            // 打印 from_int，没有歧义
  Holder h;
  std::reference_wrapper<int> r = h;  // OK：FUN(h) 经转换函数选中 FUN(int&)
  r.get() = 8;
  std::printf("%d\n", h.value);       // 8
}
```

第二个约束也不能省。从一个非 const 左值 `reference_wrapper` 复制时，模板构造函数（`U = reference_wrapper&`）比复制构造函数（形参 `const reference_wrapper&`）匹配得更好，而 `FUN(rw)` 又能经 `operator T&` 成立。没有这个约束，复制就会被模板接管，变成先转换成 `T&` 再取地址。

¶3 构造的效果如同先写 `T& r = std::forward<U>(u);`，再保存对 `r` 的引用。¶4 它的 `noexcept` 与 `FUN(declval<U>())` 一致：如果绑定 `T&` 需要调用一个可能抛异常的转换函数，构造函数也可能抛异常。¶5 复制构造函数保存对 `x.get()` 的引用。

## 赋值、访问与调用

赋值（[refwrap.assign]）。复制赋值之后，`*this` 保存对 `x.get()` 的引用。也就是重新绑定，而不是给被引用者赋值，这是它与 `T&` 的根本区别。

访问（[refwrap.access]）。`operator T&()` 和 `get()` 都返回保存的引用。隐式转换让 `reference_wrapper<int>` 能直接传给接受 `int&` 或 `int` 的函数。成员访问不会触发隐式转换，`rw.member` 不合法，要写 `rw.get().member`。

调用（[refwrap.invoke]）。`operator()` 返回 *INVOKE*(`get()`, `std::forward<ArgTypes>(args)...`)（[[func.require]]），返回类型是 `invoke_result_t<T&, ArgTypes...>`。它要求（Mandates）`T` 是完整类型。因为走 *INVOKE*，`reference_wrapper<int (S::*)()>` 这样包装成员指针的也能调用。

`operator()` 让 `std::ref(f)` 本身成为一个可调用物。把一个有状态、不可复制或复制代价高的函数对象交给按值接收的 `std::for_each`、`std::thread`、`std::function` 时，传 `std::ref(f)` 可以避免复制，状态的修改也会反映在原对象上。

## 比较 [refwrap.comparisons] {{c++26}}

C++26 之前，`rw1 == rw2` 能否编译取决于 `T` 的 `operator==` 能不能经隐式转换找到。对 `int` 可以，内建的 `==` 经 `operator int&` 转换就能用；对 `std::string` 不行，它的 `operator==` 是模板，而模板实参推导不考虑用户定义转换。[[P2944R3]] 加上了三对隐藏友元（[[g:hidden-friend]]，只能经 ADL 找到的友元函数）：

| 运算符 | 形参 | 约束 |
|---|---|---|
| `==`、`<=>` | `(reference_wrapper, reference_wrapper)` | `x.get() == y.get()` 良构且可转为 `bool`；*synth-three-way*(x.get(), y.get()) 良构 |
| `==`、`<=>` | `(reference_wrapper, const T&)` | 同上，右侧换成 `y` |
| `==`、`<=>` | `(reference_wrapper, reference_wrapper<const T>)` | 同上，另要求 `is_const_v<T>` 为 false |

比较的是被引用的值，不是地址。想知道两个包装是否引用同一个对象，写 `&a.get() == &b.get()`。

`<=>` 用的 *synth-three-way* 是库内部的说明用工具（[[expos.only.entity]]）：类型有 `<=>` 就用它，否则用 `<` 合成一个 `weak_ordering`。所以只定义了 `<` 的旧类型也能用 `<=>` 比较。

第三对要求 `T` 不是 const。`T` 本身是 const 时，`reference_wrapper<const T>` 就是 `reference_wrapper<T>`，这对重载会和第一对签名相同。

## `ref` 与 `cref` [refwrap.helpers]

```cpp
template<class T> constexpr reference_wrapper<T>       ref(T&) noexcept;
template<class T> constexpr reference_wrapper<const T> cref(const T&) noexcept;
template<class T> void ref(const T&&) = delete;
template<class T> void cref(const T&&) = delete;
template<class T> constexpr reference_wrapper<T>       ref(reference_wrapper<T>) noexcept;
template<class T> constexpr reference_wrapper<const T> cref(reference_wrapper<T>) noexcept;
```

对左值，它们返回包装。对右值，`const T&&` 版本匹配得更好而它被弃置，所以 `std::ref(42)`、`std::cref(std::string("x"))` 都是编译错误，避免了包装一个马上销毁的临时量。这里写 `const T&&` 而不是 `T&&`，是因为模板里的 `T&&` 是转发引用，会把左值也接过去。弃置的两个声明在 `<functional>` 的概要里（[[functional.syn]]）。

实参已经是 `reference_wrapper` 时不再套一层：`ref(ref(x))` 仍是 `reference_wrapper<T>`，`cref(ref(x))` 是 `reference_wrapper<const T>`。¶1 这些函数模板的 `T` 同样可以是不完整类型。

```cpp run title="ref_rvalue.cpp" error
#include <functional>
int main() {
  auto r = std::ref(42);                     // error: 调用了被弃置的 ref(const T&&)
  std::reference_wrapper<const int> c(42);   // error: FUN 约束不满足，没有可行的构造函数
}
```

### 哪些组件认得 `reference_wrapper`

有几处库规则会把 `reference_wrapper<T>` 识别出来，当作 `T&` 处理：

- `make_pair`、`make_tuple` 用 `unwrap_ref_decay_t` 计算元素类型：`make_pair(std::ref(x), 1)` 得到 `pair<int&, int>`（[[pairs]]、[[tuple]]）。
- `bind` 的绑定实参是 `reference_wrapper<T>` 时，调用时作为 `T&` 传出（[[func.bind.bind#7]]）。
- *INVOKE* 的 ¶1.2、¶1.5 分支对 `reference_wrapper` 直接调用 `.get()`（[[func.require]]）。

`std::thread` 和 `bind_front` 没有专门的解包规则。它们保存 `reference_wrapper` 本身，调用时把它交出去，再靠 `operator T&` 隐式转换为 `T&`。

## 与 `common_reference` 的配合 [refwrap.common.ref]

C++20 里 `common_reference_t<reference_wrapper<int>&, int&>` 是 `int`，一个值类型。这让 `reference_wrapper` 的范围与普通范围组合时，在 `common_reference_with` 之类的概念下表现别扭。C++23 的 [[P2655R3]] 为 `basic_common_reference` 增加了两个偏特化，结果变成了 `int&`：

```cpp run ok
#include <functional>
#include <type_traits>
static_assert(std::is_same_v<
    std::common_reference_t<std::reference_wrapper<int>&, int&>, int&>);
int main() {}
```

偏特化的条件是：一侧 `R` 是 `reference_wrapper`，`common_reference_t<typename R::type&, TQ>` 存在，并且 `R`（带上原来的限定）能转换成它。这时 `type` 就是 `common_reference_t<typename R::type&, TQual<T>>`。条件还要求这一关系只在一个方向上成立，否则两个参数都是 `reference_wrapper` 时，两个偏特化会同时匹配而产生歧义。

## 类模板实参推导

推导指引 `reference_wrapper(T&) -> reference_wrapper<T>` 让 `std::reference_wrapper rw = x;` 推导为 `reference_wrapper<int>`（[[temp.deduct.guide]]）。没有它就推不出来：构造函数模板 `reference_wrapper(U&&)` 里的 `U` 与类模板形参 `T` 无关。

## 历史与演进

!!! history
    - C++11：从 TR1 引入，构造函数是 `reference_wrapper(T&)` 加弃置的 `reference_wrapper(T&&)`。
    - C++17：增加推导指引；*INVOKE* 直接识别 `reference_wrapper`。
    - C++20：成为 `constexpr`；构造函数改为 `FUN` 约束的模板（[[LWG2993]]）；`T` 允许是不完整类型（[[P0357R3]]）。
    - C++23：`basic_common_reference` 的偏特化（[[P2655R3]]）。
    - C++26：`==` 与 `<=>`（[[P2944R3]]）。

## 思考题

!!! question "思考题 1"
    `std::reference_wrapper<const std::string> r = "hello";` 能编译吗？用一个 `std::string_view` 左值来初始化呢？

<details markdown="1">
<summary>答案</summary>

都不能。对 `"hello"`，`FUN(const string&)` 和 `FUN(const string&&)` 都要先经用户定义转换构造一个临时 `std::string`；两个转换序列用同一个转换函数，再比较后面的引用绑定，右值绑定到右值引用更好，于是选中被弃置的 `FUN(T&&)`，约束不满足。

`string_view` 到 `string` 的转换是 `explicit` 的，`FUN` 的两个重载都不可行，同样不满足约束。凡是需要物化临时量才能绑定的情形，`FUN` 都会拒绝。
</details>

!!! question "思考题 2"
    为什么 `std::function<void()> f = std::ref(callable);` 是一种常见的优化写法？它有什么风险？

<details markdown="1">
<summary>答案</summary>

`reference_wrapper` 只有一个指针大小并且平凡可复制，`std::function` 的实现通常能把它放进内部的小缓冲区而不做堆分配；复制 `f` 也只复制一个指针，而不是复制可能很大的 `callable`。

风险在生命周期：`f` 不拥有 `callable`，`callable` 先销毁，`f` 就悬垂了。C++26 的 `std::function_ref` 把这种不拥有目标的调用做成了专门的类型（[[func.wrap.ref]]）。
</details>
