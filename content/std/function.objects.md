---
title: 函数对象
summary: <functional> 中最基础的部分：什么是函数对象类型，plus、less 等运算符函数对象的 T 版本与透明的 void 版本，指针比较的严格全序，compare_three_way，带概念约束的 ranges::less 等，以及 identity。
status: done
covers: function.objects.general, functional.syn, arithmetic.operations, arithmetic.operations.general, arithmetic.operations.plus, arithmetic.operations.minus, arithmetic.operations.multiplies, arithmetic.operations.divides, arithmetic.operations.modulus, arithmetic.operations.negate, comparisons, comparisons.general, comparisons.equal.to, comparisons.not.equal.to, comparisons.greater, comparisons.less, comparisons.greater.equal, comparisons.less.equal, comparisons.three.way, logical.operations, logical.operations.general, logical.operations.and, logical.operations.or, logical.operations.not, bitwise.operations, bitwise.operations.general, bitwise.operations.and, bitwise.operations.or, bitwise.operations.xor, bitwise.operations.not, range.cmp, func.identity
papers: N3421, N3657, P0919R3, P1690R1, P0896R4
related: func.require, refwrap, func.bind, func.bind.partial, func.not.fn, func.memfn, func.wrap, func.search, unord.hash, expr.rel, expr.call, over.call.object, concepts, cmp, defns.order.ptr
tags: 标准库, functional, 函数对象, 透明比较器, 异构查找, 指针全序
updated: 2026-10-19
---

!!! tldr
    - 函数对象类型是能写在函数调用 `x(args...)` 中 `x` 位置的对象类型：函数指针、有 `operator()` 的类、能转换为函数指针的类。
    - `std::plus<int>` 先把实参转换为 `int` 再相加；`std::plus<>`（即 `plus<void>`）完美转发实参，结果类型由表达式本身决定，一般应当优先使用后者。
    - `void` 版本带有 `is_transparent` 标签，用作 `std::set` 的比较器时，可以直接用 `string_view` 之类的其他类型查找，不必构造键类型的临时对象。
    - 内建 `<` 比较不相关的指针，结果是未指定的；`std::less<T*>` 等保证给出一个由实现定义的严格全序，所以 `std::set<T*>` 是可靠的。
    - `std::ranges::less` 等要求类型满足 `totally_ordered_with`，只定义了 `<` 的类型不能使用；`std::identity` 原样返回实参，是 Ranges 算法投影的默认值。

[function.objects] 是 `<functional>` 头文件的全部内容。本页讲函数对象的定义和运算符函数对象，其余部分另有专页：

| 子条款 | 内容 | 页面 |
|---|---|---|
| [func.def]、[func.require]、[func.invoke] | *INVOKE*、调用包装器、`std::invoke` | [[func.require]] |
| [refwrap] | `reference_wrapper`、`ref`、`cref` | [[refwrap]] |
| [func.not.fn]、[func.bind.partial]、[func.bind]、[func.memfn] | `not_fn`、`bind_front`、`bind_back`、`bind`、`mem_fn` | [[func.bind]] 等 |
| [func.wrap] | `function`、`move_only_function`、`copyable_function`、`function_ref` | [[func.wrap]] |
| [func.search] | 搜索器 | [[func.search]] |
| [unord.hash] | `std::hash` | [[unord.hash]] |

## 函数对象类型 [function.objects.general]

```cpp run ok
#include <algorithm>
#include <functional>
#include <vector>

bool desc(int a, int b) { return a > b; }

int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(v.begin(), v.end(), desc);                   // 函数指针
  std::sort(v.begin(), v.end(), std::greater<>{});       // 类对象
  std::sort(v.begin(), v.end(),
            [](int a, int b) { return a > b; });         // lambda
}
```

三次调用传给 `sort` 的东西类型各不相同，`sort` 对它们一视同仁，只要求能写 `comp(a, b)`。

!!! std
    A *function object type* is an object type that can be the type of the *postfix-expression* in a function call.

¶1 能作为函数调用中后缀表达式的类型的对象类型，叫做**函数对象类型**（[[g:function-object-type]]），它的对象叫做**函数对象**。这个定义只看语法。脚注列出了三种情形：

1. 函数指针，如 `int(*)(int)`；
2. 有成员 `operator()` 的类类型，包括所有 lambda 的闭包类型（[[expr.prim.lambda.closure]]）；
3. 能转换为函数指针的类类型，调用时经由代理调用函数（[[over.call.object]]）。

函数类型本身不是函数对象类型，因为函数不是对象。成员指针也不是，`pmf(obj)` 不合法。把成员指针也纳入可调用的范围，靠的是 [[func.require]] 的可调用类型和 *INVOKE*。

¶1 后半句说明了设计意图：本来需要给算法传函数指针的地方，接口一律设计成接受函数对象，这样既能传函数指针，也能传任意函数对象。

函数对象的好处不只是能带状态。类的 `operator()` 是类型的一部分，模板为每个比较器类型单独实例化，调用可以直接内联。函数指针是运行时的值，编译器要先确定指针指向哪个函数才能内联。这是 `std::sort` 通常比 `qsort` 快的原因之一。

## 头文件 [functional.syn]

概要中值得注意的几点：

- 几乎所有内容都标了 `// freestanding`，包括 `invoke`、`reference_wrapper`、全部运算符函数对象、`identity`、`not_fn`、`bind_front`、`bind`、`mem_fn` 和 `hash`。不在其中的是 `function`、`move_only_function`、`copyable_function`、`bad_function_call`，以及两个 Boyer–Moore 搜索器。
- 运算符函数对象都声明为 `template<class T = void> struct plus;`，并对 `void` 显式特化。所以 `std::plus<>` 和 `std::plus<void>` 是同一个类型。
- `ref(const T&&)` 和 `cref(const T&&)` 被声明为弃置，以拒绝右值实参（[[refwrap]]）。
- 末尾定义了几个仅用于说明的工具，如概念 *callable*、别名 *call-result-t*，供 [[func.wrap.ref]] 等条款使用。

## 运算符函数对象：`T` 版本与 `void` 版本

[arithmetic.operations]、[comparisons]、[logical.operations]、[bitwise.operations] 的结构完全相同。每个运算符对应一个类模板：

| 类别 | 类模板 | 运算符 | `T` 版本返回 |
|---|---|---|---|
| 算术 | `plus`、`minus`、`multiplies`、`divides`、`modulus`、`negate` | `+ - * / %`、一元 `-` | `T` |
| 比较 | `equal_to`、`not_equal_to`、`greater`、`less`、`greater_equal`、`less_equal` | `== != > < >= <=` | `bool` |
| 逻辑 | `logical_and`、`logical_or`、`logical_not` | `&& \|\| !` | `bool` |
| 位运算 | `bit_and`、`bit_or`、`bit_xor`、`bit_not` | `& \| ^ ~` | `T` |

```cpp run ok
#include <cstdio>
#include <functional>
#include <numeric>
#include <vector>

int main() {
  std::vector<double> v{0.5, 0.5, 0.5, 0.5};
  double a = std::accumulate(v.begin(), v.end(), 0.0,
                             std::plus<int>());  // 每一步都截断成 int
  double b = std::accumulate(v.begin(), v.end(), 0.0,
                             std::plus<>());     // double + double
  std::printf("%g %g\n", a, b);                  // 0 2
}
```

以 `plus` 为例，[arithmetic.operations.plus] 给出两种形态。

`T` 版本（¶1）的两个形参都是 `const T&`，返回 `T`，效果是 `x + y`。实参先转换为 `T`，运算结果再转换为返回类型：

```cpp
template<class T = void> struct plus {
  constexpr T operator()(const T& x, const T& y) const;
};
```

`void` 版本（¶2）的两个形参是各自推导的转发引用，返回类型是表达式本身的类型，不做额外的转换：

```cpp
template<> struct plus<void> {
  template<class T, class U> constexpr auto operator()(T&& t, U&& u) const
    -> decltype(std::forward<T>(t) + std::forward<U>(u));
  using is_transparent = unspecified;
};
```

上例中 `plus<int>` 的形参是 `const int&`，`0.0` 和 `0.5` 都先被转换为 `int` 的 0。这个转换发生在标准库内部，`-Wall -Wextra` 也不会警告。`void` 版本没有这个问题，所以除非确实需要先转换，应当写 `std::plus<>{}`。

`void` 版本的尾置返回类型还有一个作用：`t + u` 不合法时，替换失败，`operator()` 不参与重载决议，而不是在函数体内报错。

!!! note "这些函数对象没有 `noexcept`"
    条文没有给 `operator()` 标 `noexcept`。实现可以给非虚函数加上不抛异常的说明（[[res.on.exception.handling]]）。libc++ 的 `void` 版本带有 `noexcept(noexcept(t + u))` 这样的说明，`T` 版本没有。可移植的代码不应依赖它们是否 `noexcept`。

## 透明比较器与异构查找

<div class="compare" markdown="1">

```cpp run ok
#include <set>
#include <string>
#include <string_view>
#include <functional>
int main() {
  std::set<std::string, std::less<>>
    s{"apple"};
  std::string_view key = "apple";
  return s.contains(key);   // OK
}
```

```cpp run error
#include <set>
#include <string>
#include <string_view>
int main() {
  std::set<std::string> s{"apple"};
  std::string_view key = "apple";
  return s.contains(key);
  // error: 没有匹配的 contains
}
```

</div>

每个 `void` 特化都有成员 `using is_transparent = unspecified;`。这个别名不参与运算，只是一个标签，表示这个比较器可以直接比较不同类型的实参。带有这个标签的比较器叫做**透明比较器**（[[g:transparent-comparator]]）。

有序关联容器（[[associative.reqmts]]）的 `find`、`count`、`contains`、`lower_bound`、`upper_bound`、`equal_range` 都有一组成员模板，如 `template<class K> iterator find(const K& x);`。只有 `Compare::is_transparent` 存在并且是一个类型时，这些模板才参与重载决议。

左边的比较器是 `less<>`，`contains` 直接拿 `string_view` 和元素比较，不构造 `std::string`。右边的比较器是默认的 `less<std::string>`，只有 `contains(const key_type&)`，而 `string_view` 不能隐式转换为 `std::string`，于是没有可用的函数。

默认的 `less<Key>` 不会自动变成透明的，因为透明会改变语义。`less<std::string>` 先把实参转换为 `std::string` 再比较；透明版本直接用 `const char*` 与 `std::string` 的混合比较。如果某个类型的转换构造函数做了规范化（例如转成小写），两种比较可能给出不同的结果。所以标准让用户显式选择透明比较器。

C++20 起无序容器（[[unord.req]]）也支持异构查找（[[P0919R3]]、[[P1690R1]]），但要求哈希函数和相等谓词都是透明的，否则对 `string_view` 和 `std::string` 可能算出不同的哈希值。`std::hash<std::string>` 本身不透明，需要自己写一个带 `is_transparent` 的哈希（见 [[unord.hash]]）。

!!! history
    透明的运算符函数对象（`less<>` 等 `void` 特化）由 [[N3421]] 加入 C++14，有序关联容器的异构查找由 [[N3657]] 加入 C++14，无序容器的异构查找是 C++20 的 [[P0919R3]] 和 [[P1690R1]]。

## 指针比较的严格全序 [comparisons.general]

```cpp run ok
#include <cstdio>
#include <functional>
int a, b;
int main() {
  int* p = &a;
  int* q = &b;
  bool x = std::less<int*>{}(p, q);
  bool y = std::less<int*>{}(q, p);
  std::printf("%d\n", x != y);                     // 1：恰好一个为真
  std::printf("%d\n", std::less<>{}(p, q) == x);   // 1
}
```

用内建 `<` 比较指针时，只有指向同一数组的元素、同一对象的成员等情形有规定的结果。比较两个不相关的全局变量的地址，结果是未指定的（[[expr.rel#5]]）。`std::set<T*>`、`std::map<T*, V>` 需要比较器满足严格弱序，未指定的结果不能保证传递性，容器的不变式就可能被破坏。

¶2 为此给库函数对象加了一条保证：

!!! std
    For templates `less`, `greater`, `less_equal`, and `greater_equal`, the specializations for any pointer type yield a result consistent with the implementation-defined strict total order over pointers.

由实现定义的指针严格全序见 [[defns.order.ptr]]：它覆盖所有指针值，并且与内建运算符已有定义的那部分结果一致。所以：

- `less<T*>`、`greater<T*>`、`less_equal<T*>`、`greater_equal<T*>` 对任意两个指针都给出确定的结果。注 1 说明，内建 `<` 有定义时，两者结果相同。
- 对 `less<void>` 等，如果调用运算符最终用的是比较指针的内建运算符，结果也与这个全序一致。这一点是 [[LWG2450]] 补上的。
- `equal_to` 和 `not_equal_to` 不在列表中，因为指针的相等比较总有定义。

在地址空间平坦的主流平台上，编译器生成的 `<` 本来就按地址数值比较，所以 libc++ 的 `less<T>` 直接写 `return __x < __y;`。但这只在运行时成立：

```cpp run error
#include <functional>
int a, b;
constexpr bool r = std::less<int*>{}(&a, &b);
// error: 不是常量表达式
```

!!! lawyer "常量求值中没有这个全序"
    `less<T*>::operator()` 是 `constexpr` 函数，但由实现定义的全序在编译期没有已知的值。[[expr.const]] 规定，结果未指定的关系比较不是常量表达式。Clang 对上例给出的注释是 `comparison between pointers to unrelated objects '&a' and '&b' has unspecified value`。比较同一数组中的指针则没有问题。

## `compare_three_way` [comparisons.three.way]

`compare_three_way` 是 `<=>` 对应的函数对象。它不是模板，没有 `T` 版本，本身就是透明的。

- ¶1 *Constraints*：`T` 和 `U` 满足 `three_way_comparable_with`（[[cmp.concept]]），不满足时 `operator()` 不参与重载决议。
- ¶2 *Preconditions*（前置条件，违反时是 UB）：如果表达式调用的是比较指针的内建 `<=>`，从 `T`、`U` 到指针类型的转换必须保持相等性（[[concepts.equality]]），也就是相等的输入总是转换出相等的指针；否则 `T` 和 `U` 必须满足 `three_way_comparable_with` 的语义要求。
- ¶3 比较指针时按严格全序返回 `strong_ordering::less`、`greater` 或 `equal`；其他情况就是 `t <=> u`。

¶2 对转换的要求是必要的：如果某个类类型可以转换为指针，而每次转换的结果不同，按全序比较就没有意义。

## 带概念约束的比较器 [range.cmp]

```cpp run ok
#include <cstdio>
#include <functional>
#include <type_traits>

struct V {
  int x;
  friend bool operator<(V a, V b) { return a.x < b.x; }   // 只有 <
};
static_assert(!std::totally_ordered<V>);
static_assert(!std::is_invocable_v<std::ranges::less, V, V>);

int main() {
  V a{1}, b{2};
  std::printf("%d\n", std::less<>{}(a, b));   // OK：只要求 a < b 合法
}
```

C++20 的 Ranges（[[P0896R4]]）在 `std::ranges` 中提供了六个非模板的比较器：`equal_to`、`not_equal_to`、`greater`、`less`、`greater_equal`、`less_equal`。它们与 `std::less<>` 的区别在于对类型的要求：

| | `std::less<>` | `std::ranges::less` |
|---|---|---|
| 可调用的条件 | `t < u` 合法 | ¶8 *Constraints*：`totally_ordered_with<T, U>` |
| 语义要求 | 无 | ¶9 *Preconditions*：满足 `totally_ordered_with` 的语义要求，且三者恰有其一 |
| 返回类型 | `decltype(t < u)` | `bool` |
| 指针 | 内建比较时按全序 | 同样按全序（¶10.1） |

`totally_ordered_with` 要求六个比较运算符都存在，结果都能当作 `bool` 使用，跨类型时还要求有公共引用类型（[[concepts.compare]]）。所以只定义了 `operator<` 的 `V` 能用 `std::less<>`，不能用 `ranges::less`。

虽然要求六个运算符都存在，实际只调用 `<`：¶7 `ranges::greater` 是交换实参后的 `less`，¶12 `greater_equal` 是 `!less(t, u)`，¶14 `less_equal` 是 `!less(u, t)`。`ranges::sort` 等算法假设 `<` 与 `==`、`>` 等描述的是同一个顺序，概念约束挡住了只提供 `<` 的类型。

¶9 最后一句要求，对任意两个值，`less(a, b)`、`less(b, a)`、`equal_to(a, b)` 恰好一个为真。这是对值的语义要求，编译器无法检查。`double` 满足 `totally_ordered` 的语法要求，但 NaN 与任何值比较都不满足这一条，所以用 `ranges::sort` 排序含 NaN 的 `vector<double>`，会违反前置条件。

¶1–¶3 `ranges::equal_to` 要求 `equality_comparable_with`；比较指针时同样按全序判断，两个指针谁也不排在对方前面就相等。¶4–¶5 `ranges::not_equal_to` 是它的否定。

## `identity` [func.identity]

```cpp
struct identity {
  template<class T> constexpr T&& operator()(T&& t) const noexcept;
  using is_transparent = unspecified;
};
```

¶1 `std::identity` 返回 `std::forward<T>(t)`，原样转发实参，保留值类别。它是所有 Ranges 算法投影参数的默认值：`ranges::sort(r, comp, proj)` 中的 `proj` 默认就是 `identity{}`。

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <functional>
#include <vector>

struct Emp { int id; double salary; };

int main() {
  std::vector<Emp> v{{3, 10}, {1, 30}, {2, 20}};
  // 投影：成员指针经 std::invoke 调用
  std::ranges::sort(v, std::ranges::less{}, &Emp::salary);
  std::vector<int> w{3, 1, 2};
  std::ranges::sort(w, {}, std::identity{});   // 等于不写投影
  std::printf("%d %d\n", v[0].id, w[0]);       // 3 1
}
```

!!! pitfall "`identity` 返回的是引用"
    `auto&& r = std::identity{}(make_string());` 中，`identity` 返回指向临时对象的 `std::string&&`。临时对象在完整表达式结束时销毁，`r` 悬垂。`identity` 和 `std::move`、`std::forward` 一样只是传递引用，不延长生命期。

## 已经移除的旧设施

C++98 的 `<functional>` 还有基类 `unary_function`、`binary_function`，以及 `bind1st`、`bind2nd`、`ptr_fun`、`mem_fun`、`mem_fun_ref`、`not1`、`not2` 等。除 `not1`、`not2` 外，它们在 C++11 被弃用，在 C++17 被移除（[[N4190]]）；`not1`、`not2` 在 C++17 被弃用，在 C++20 被移除。它们分别被 lambda、`bind`、`bind_front`、`mem_fn`、`not_fn` 取代（[[func.bind]]）。

## 思考题

!!! question "思考题 1"
    `std::set<int*>` 中存放着指向不同堆对象的指针。如果把默认的 `std::less<int*>` 换成 `[](int* a, int* b) { return a < b; }`，在标准意义上有什么区别？

<details markdown="1">
<summary>答案</summary>

默认的 `std::less<int*>` 按 [comparisons.general] ¶2 给出由实现定义的严格全序，满足容器对严格弱序的要求。

自己写的 lambda 直接用内建 `<`。对指向不同对象的指针，结果是未指定的（[[expr.rel#5]]），不能保证传递性和一致性，[[associative.reqmts]] 对 `Compare` 的要求就无法保证成立，程序的行为没有保证。主流平台上两者生成的代码相同，区别在于前者有标准的保证，后者只是碰巧可行。
</details>

!!! question "思考题 2"
    为什么 `ranges::less` 设计成普通类，而不像 `std::less` 那样带一个默认为 `void` 的模板参数？

<details markdown="1">
<summary>答案</summary>

`std::less<T>` 的 `T` 版本只是先把实参转换为 `T` 再比较。C++14 有了透明的 `less<>` 之后，它主要是为了兼容旧代码而保留。Ranges 是重新设计的，只需要透明且带概念约束的一种形态。做成普通类之后，`ranges::less{}` 写起来更短，用作算法的默认实参（`Comp comp = {}`）时也不必写模板实参。
</details>
