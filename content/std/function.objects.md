---
title: 函数对象
summary: <functional> 的总览：函数对象类型的定义、算术/比较/逻辑/位运算函数对象及其 void 透明特化、指针上的严格全序保证、compare_three_way、ranges:: 概念约束比较器与 identity
status: done
covers: function.objects.general, functional.syn, arithmetic.operations, arithmetic.operations.general, arithmetic.operations.plus, arithmetic.operations.minus, arithmetic.operations.multiplies, arithmetic.operations.divides, arithmetic.operations.modulus, arithmetic.operations.negate, comparisons, comparisons.general, comparisons.equal.to, comparisons.not.equal.to, comparisons.greater, comparisons.less, comparisons.greater.equal, comparisons.less.equal, comparisons.three.way, logical.operations, logical.operations.general, logical.operations.and, logical.operations.or, logical.operations.not, bitwise.operations, bitwise.operations.general, bitwise.operations.and, bitwise.operations.or, bitwise.operations.xor, bitwise.operations.not, range.cmp, func.identity
papers: N3421, N3657, P0919R3, P1690R1, P0896R4
related: func.require, refwrap, func.bind, func.bind.partial, func.not.fn, func.memfn, func.wrap, func.search, unord.hash, expr.rel, expr.call, over.call.object, concepts, cmp, defns.order.ptr
tags: 标准库, functional, 函数对象, 透明比较器, 异构查找, 指针全序
updated: 2026-10-18
---

[function.objects]（22.10）是 `<functional>` 头文件的全部内容。它一头连着核心语言——什么样的类型能放在函数调用表达式的左边（[[expr.call]]、[[over.call.object]]）——一头连着整个算法库与容器库：`sort` 的比较器、`set` 的 `Compare`、`unordered_map` 的 `Hash`、`ranges::sort` 的投影，全是函数对象。

本节内容很多，本站按主题拆成几页：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [function.objects.general]、[functional.syn] | 函数对象类型的定义、头文件概要 | 本页 |
| [func.def]、[func.require]、[func.invoke] | *INVOKE*、调用包装器、`std::invoke` | [[func.require]] |
| [refwrap] | `reference_wrapper`、`ref`/`cref` | [[refwrap]] |
| [arithmetic.operations]、[comparisons]、[range.cmp]、[logical.operations]、[bitwise.operations]、[func.identity] | 运算符函数对象 | 本页 |
| [func.not.fn]、[func.bind.partial]、[func.bind]、[func.memfn] | `not_fn`、`bind_front`/`bind_back`、`bind`、`mem_fn` | [[func.bind]] 等 |
| [func.wrap] | `function`、`move_only_function`、`copyable_function`、`function_ref` | [[func.wrap]] |
| [func.search] | 搜索器 | [[func.search]] |
| [unord.hash] | `std::hash` | [[unord.hash]] |

## 函数对象类型（[function.objects.general]）

!!! std
    A *function object type* is an object type that can be the type of the *postfix-expression* in a function call.

¶1 的定义是**纯语法性**的：只要某个对象类型的对象能出现在 `x(args...)` 的 `x` 位置，它就是**函数对象类型**（[[g:function-object-type]] / *function object type*），其对象就是**函数对象**。脚注列出了三种形态：

1. **函数指针**——`int(*)(int)`；
2. 有成员 `operator()` 的类类型——包括所有 lambda 的闭包类型（[[expr.prim.lambda.closure]]）；
3. 有**到函数指针的转换函数**的类类型——经 [[over.call.object]] 的“代理调用函数”机制被调用。

注意**函数类型本身不是**函数对象类型（函数不是对象），**成员指针也不是**（`pmf(obj)` 不合法）。把成员指针也纳入“可以被调用”的概念要靠 [[func.require]] 的“可调用类型”与 *INVOKE*。

¶1 后半句给出动机：凡是你本来会给算法模板传函数指针的地方，接口都设计成接受函数对象——这样既能传函数指针，也能传任意函数对象。后者的好处不只是“能带状态”：函数对象的 `operator()` 是**类型的一部分**，模板对每个比较器类型单独实例化，调用可以直接内联；而函数指针是一个运行时值，`sort(v.begin(), v.end(), &cmp)` 里编译器必须证明指针恒定才能内联。这就是“`std::sort` 比 `qsort` 快”的经典解释。

## 头文件概要要点（[functional.syn]）

不逐条复述概要，只提几个值得法律眼光的地方：

- **几乎全部 freestanding**：`invoke`、`reference_wrapper`、所有运算符函数对象、`identity`、`not_fn`、`bind_front`/`bind_back`、`bind` 与占位符、`mem_fn`、`function_ref`、`default_searcher`、`hash` 都标了 `// freestanding`。不在其内的是 `function`、`move_only_function`、`copyable_function`、`bad_function_call`（需要动态分配或异常）以及两个 Boyer–Moore 搜索器（需要哈希表）。
- 所有运算符类模板都写成 `template<class T = void> struct plus;`，并各自显式特化了 `plus<void>`——这就是下文的**透明函数对象**。所以 `std::plus<>` 与 `std::plus<void>` 是同一个类型。
- `ref(const T&&) = delete;`、`cref(const T&&) = delete;`：用弃置函数拒绝右值（[[refwrap]]）。
- 末尾定义了几个仅用于说明的工具：概念 *callable*、*nothrow-callable*，别名 *call-result-t*，以及 `decayed-typeof<f>`（`decltype(auto(f))`），供本节及其他条款（例如 [[func.wrap.ref]]）使用。
- ¶1、¶2 的两个例子（`transform(..., plus<double>())`、`transform(..., negate<double>())`）是注释性的示例，不具规范效力。

## 运算符函数对象：`T` 版本与 `void` 版本

[arithmetic.operations]、[comparisons]、[logical.operations]、[bitwise.operations] 的结构完全一致，可以一起读。每个运算符 `@` 对应一个类模板，各有两种形态：

| 类别 | 类模板 | 对应运算符 | `T` 版本返回 |
|---|---|---|---|
| 算术（[[expr.mul]]、[[expr.add]]、[[expr.unary.op]]） | `plus` `minus` `multiplies` `divides` `modulus` `negate` | `+ - * / %` 一元 `-` | `T` |
| 比较（[[expr.rel]]、[[expr.eq]]） | `equal_to` `not_equal_to` `greater` `less` `greater_equal` `less_equal` | `== != > < >= <=` | `bool` |
| 逻辑（[[expr.log.and]]、[[expr.log.or]]） | `logical_and` `logical_or` `logical_not` | `&& \|\| !` | `bool` |
| 位运算（[[expr.bit.and]]、[[expr.or]]、[[expr.xor]]） | `bit_and` `bit_or` `bit_xor` `bit_not` | `& \| ^ ~` | `T` |

**`T` 版本**（例如 [arithmetic.operations.plus]）：

```cpp
template<class T = void> struct plus {
  constexpr T operator()(const T& x, const T& y) const;   // Returns: x + y
};
```

两个参数都是 `const T&`，返回 `T`（比较/逻辑类是 `bool`）。实参先**转换到 `T`**，再做运算，结果再**转换到返回类型**。

**`void` 版本**（例如 `plus<void>`）：

```cpp
template<> struct plus<void> {
  template<class T, class U> constexpr auto operator()(T&& t, U&& u) const
    -> decltype(std::forward<T>(t) + std::forward<U>(u));
  using is_transparent = unspecified;
};
```

参数是两个独立推导的转发引用，返回类型是 `decltype` 推出来的**表达式本身的类型**，不做任何额外转换。尾置返回类型还带来一个副作用：`t + u` 不合法时，`operator()` 因替换失败而**不可行**——`plus<>` 对 SFINAE 友好。

二者的差别在实际代码里会咬人：

```cpp run title="plus_int_truncates.cpp" ok
#include <functional>
#include <numeric>
#include <vector>
#include <cstdio>
int main() {
  std::vector<double> v{0.5, 0.5, 0.5, 0.5};
  double a = std::accumulate(v.begin(), v.end(), 0.0, std::plus<int>());  // 每一步都截断成 int
  double b = std::accumulate(v.begin(), v.end(), 0.0, std::plus<>());     // double + double
  std::printf("%g %g\n", a, b);                                           // 0 2
}
```

`plus<int>` 的形参是 `const int&`，`0.0` 与 `0.5` 都先被转换成 `int 0`——而这个转换发生在标准库头文件内部，`-Wall -Wextra` 都不会警告。`void` 版本没有这个问题，这也是“除非有理由，否则写 `std::plus<>{}`”的原因。

!!! note "说明性：这些函数对象没有 `noexcept`"
    条文没有给 `operator()` 写 `noexcept`。实现可以加强（[[res.on.exception.handling]] 允许给非虚函数加上不抛异常说明），libc++ 的 `void` 版本就带有 `noexcept(noexcept(t < u))`，`T` 版本则没有。可移植代码不应依赖它们的 `noexcept` 性质。

## 透明函数对象与异构查找

每个 `void` 特化都有一个成员 `using is_transparent = unspecified;`。这个类型别名本身不参与运算，它是一个**标签**：告诉关联容器“这个比较器可以直接比较不同类型的实参”。具有 `is_transparent` 的比较器常被称为**透明比较器**（[[g:transparent-comparator]] / *transparent comparator*）。

有序关联容器（[[associative.reqmts]]）的 `find`、`count`、`contains`、`lower_bound`、`upper_bound`、`equal_range` 都有一组成员模板重载 `template<class K> iterator find(const K& x);`，它们**只有在 `Compare::is_transparent` 合法且表示一个类型时才参与重载决议**。于是：

```cpp run title="heterogeneous_lookup.cpp" ok
#include <functional>
#include <set>
#include <string>
#include <string_view>
#include <cstdio>
int main() {
  std::set<std::string, std::less<>> s{"apple", "banana"};
  std::string_view key = "banana";
  std::printf("%d\n", s.contains(key));              // 直接用 string_view 比较，不构造 std::string
  std::printf("%d\n", s.find("apple") != s.end());   // const char* 也一样
}
```

```cpp run title="non_transparent.cpp" error
#include <set>
#include <string>
#include <string_view>
int main() {
  std::set<std::string> s{"apple"};                  // Compare = less<std::string>，不透明
  std::string_view key = "apple";
  return s.contains(key);                            // error：只有 contains(const key_type&)，
}                                                    // 而 string_view 不能隐式转换为 std::string
```

为什么默认的 `std::less<Key>` 不能直接“升级”成透明的？因为透明会**改变语义**：`less<std::string>` 先把实参转换成 `std::string` 再比较；透明版本则用 `const char* < std::string` 这样的混合比较，二者对同一组实参可能给出不同的序（极端例子：自定义类型的转换构造函数做了规范化处理）。所以标准让用户**显式**选择透明比较器，容器只认 `is_transparent` 这个明确的标签。

无序容器（[[unord.req]]）也在 C++20 获得异构查找（[[P0919R3]]、[[P1690R1]]），但条件更严：**哈希函数和相等谓词都必须透明**，因为一个不透明的哈希会对 `string_view` 和 `std::string` 算出不同的值。`std::hash<std::string>` 本身并不透明，需要自己写一个带 `is_transparent` 的哈希（见 [[unord.hash]]）。

!!! history
    透明运算符函数对象（`less<>` 等 `void` 特化）由 [[N3421]] 引入 C++14；有序关联容器的异构查找由 [[N3657]] 引入 C++14；无序容器的异构查找是 C++20 的 [[P0919R3]] 与 [[P1690R1]]。

## 指针比较的严格全序（[comparisons.general]/2）

内建 `<` 比较指针时，只有“同一数组的元素”“同一对象的成员”等情形有规定的结果；其他情况——比如两个不相关的全局变量的地址——[[expr.rel#4]]、[[expr.rel#5]] 规定结果是**未指明的**（{{unspec}}）。这对需要把指针当键的 `std::set<T*>`、`std::map<T*, V>` 是致命的：未指明的结果不保证满足严格弱序的传递性，容器的不变式就可能被破坏。

¶2 为此给库函数对象加了一道保证：

!!! std
    For templates less, greater, less_equal, and greater_equal, the specializations for any pointer type yield a result consistent with the implementation-defined strict total order over pointers.

这里的“由实现定义的指针严格全序”见 [[defns.order.ptr]]：一个覆盖**所有**指针值的严格全序，且与内建运算符给出的偏序一致。所以：

- `less<T*>`、`greater<T*>`、`less_equal<T*>`、`greater_equal<T*>` 对**任意**两个指针都有确定（由实现定义）的结果；内建 `<` 有定义的地方，二者结果相同（注 1）。
- 对 `void` 特化 `less<>` 等，若调用运算符最终调用的是**比较指针的内建运算符**，结果同样与该全序一致。这是 C++17 时期修补的（[[LWG2450]]），在此之前 `less<>` 对指针没有这个保证。
- `equal_to`、`not_equal_to` 不在列表中——指针相等比较本来就总有定义。

在主流平台上地址空间是平坦的，编译器生成的 `<` 本来就是按地址数值比较，所以 libc++ 的 `less<T>` 就是直接写 `return __x < __y;`——全序由编译器“免费”提供。但这只在**运行期**成立：

```cpp run title="ptr_total_order.cpp" ok
#include <functional>
#include <cstdio>
int a, b;
int main() {
  int* p = &a; int* q = &b;
  bool x = std::less<int*>{}(p, q);
  bool y = std::less<int*>{}(q, p);
  std::printf("%d\n", x != y);           // 1：恰好一个为真
  std::printf("%d\n", std::less<>{}(p, q) == x);
}
```

```cpp run title="ptr_order_constexpr.cpp" error
#include <functional>
int a, b;
constexpr bool r = std::less<int*>{}(&a, &b);   // error：不是常量表达式
```

!!! lawyer "常量求值里的全序"
    `less<T*>::operator()` 是 `constexpr` 函数，但“由实现定义的全序”在编译期并没有已知的取值。[[expr.const]] 把“结果未指明的关系运算”排除在常量表达式之外，Clang 对上例给出的注释正是 “comparison between pointers to unrelated objects '&a' and '&b' has unspecified value”。所以实践中，对不相关指针调用 `less` 不是常量表达式；对同一数组内的指针则没有问题。

## `compare_three_way`（[comparisons.three.way]）

`compare_three_way` 是 `<=>` 的函数对象，它**不是**模板（没有 `T` 版本），本身就是透明的。

- ¶1 **Constraints**：`T` 与 `U` 满足 `three_way_comparable_with`（[[cmp.concept]]）。
- ¶2 **Preconditions**：若表达式调用的是比较指针的内建 `<=>`，从 `T`、`U` 到指针类型 `P` 的转换要**保持相等性**（[[concepts.equality]]）；否则 `T`、`U` 要**实现**（model）`three_way_comparable_with`。违反即 UB。
- ¶3 **Effects**：比较指针时按严格全序返回 `strong_ordering::less/greater/equal`；否则就是 `t <=> u`。

¶2 的“转换保持相等性”是为了堵一个洞：如果某个类类型能转换成指针、但每次转换结果不一样，那“全序”就没有意义了。

## 概念约束的比较器 `ranges::less` 等（[range.cmp]）

C++20 的 Ranges（[[P0896R4]]）在 `std::ranges` 命名空间里提供了六个**非模板**的比较器 `ranges::equal_to`、`not_equal_to`、`greater`、`less`、`greater_equal`、`less_equal`。它们与 `std::less<>` 的区别不在于“能比较什么类型”，而在于**语义契约**：

| | `std::less<>` | `std::ranges::less` |
|---|---|---|
| 可调用条件 | `t < u` 合法即可（SFINAE） | ¶8 Constraints：`totally_ordered_with<T, U>` |
| 语义要求 | 无 | ¶9 Preconditions：`T`、`U` 实现 `totally_ordered_with`，且三歧性成立 |
| 使用的运算符 | 只用 `<` | 只用 `<`（`greater` 交换参数，`*_equal` 取反） |
| 返回类型 | `decltype(t < u)` | `bool` |
| 指针 | 内建比较走全序 | 同样走全序（¶10.1） |

`totally_ordered_with` 要求**全部六个**比较运算符都存在且结果可转换为 `bool`，还要求跨类型的 `common_reference` 存在（[[concepts.compare]]）。所以一个只定义了 `operator<` 的类型可以用 `std::less<>`，却不能用 `ranges::less`：

```cpp run title="ranges_less_constraint.cpp" ok
#include <functional>
#include <cstdio>
struct V {
  int x;
  friend bool operator<(V a, V b) { return a.x < b.x; }   // 只有 <
};
static_assert(!std::totally_ordered<V>);
static_assert(!std::is_invocable_v<std::ranges::less, V, V>);   // 约束不满足：不参与重载决议
int main() {
  V a{1}, b{2};
  std::printf("%d\n", std::less<>{}(a, b));   // OK：只要求 a < b 合法
}
```

这不是吹毛求疵。`ranges::sort` 等算法要求比较器满足 `strict_weak_order`，其中隐含“`<` 与 `==`、`>` 等是同一套序关系”的假设；`ranges::less` 用约束把“只给了一个 `<` 的半成品类型”挡在门外。至于实现：libc++ 的 `__functional/ranges_operations.h` 里，`ranges::less_equal` 就是 `!(u < t)`，`ranges::greater` 是 `u < t`——与条文 ¶7、¶12、¶14 的“Equivalent to”逐字对应，**只调用 `<`**，从不调用用户的 `<=`、`>`。

¶9 末尾还有一条三歧性前置条件：对任意 `ET`、`EU`，`less(ET, EU)`、`less(EU, ET)`、`equal_to(ET, EU)` **恰好一个**为真。这是对用户类型的**语义**要求，编译器无法检查；违反它（例如 `double` 里的 NaN）就是 {{ub}}。所以 `ranges::sort` 一个含 NaN 的 `vector<double>` 在法律上是未定义行为——尽管 `double` 满足 `totally_ordered` 概念的**语法**部分。

`ranges::equal_to`（¶1–¶3）与 `compare_three_way` 一样，比较指针时按全序判定（两指针都不“先于”对方即相等）。

## `identity`（[func.identity]）

```cpp
struct identity {
  template<class T> constexpr T&& operator()(T&& t) const noexcept;  // return std::forward<T>(t);
  using is_transparent = unspecified;
};
```

`std::identity` 原样返回实参（**保留值类别**，返回 `T&&` 而不是值）。它是所有 Ranges 算法**投影**参数的默认值：`ranges::sort(r, comp, proj = {})` 里 `proj` 默认就是 `identity{}`。它有 `is_transparent`，所以也能当作一个透明的“键提取器”。

```cpp run title="projection.cpp" ok
#include <functional>
#include <algorithm>
#include <vector>
#include <cstdio>
struct Emp { int id; double salary; };
int main() {
  std::vector<Emp> v{{3, 10}, {1, 30}, {2, 20}};
  std::ranges::sort(v, std::ranges::less{}, &Emp::salary);   // 投影：成员指针经 std::invoke 调用
  std::vector<int> w{3, 1, 2};
  std::ranges::sort(w, {}, std::identity{});                 // 等价于不写投影
  std::printf("%d %d\n", v[0].id, w[0]);                     // 3 1
}
```

!!! pitfall "identity 返回引用"
    `auto&& r = std::identity{}(make_string());` 中，`identity` 返回的是对临时量的 `std::string&&`，临时量在完整表达式结束时销毁，`r` 悬垂。它和 `std::move`、`std::forward` 一样，只是一个“透传引用”的函数，不延长生命期。

## 已被移除的旧设施

C++98 的 `<functional>` 里还有 `unary_function`/`binary_function` 基类、`bind1st`/`bind2nd`、`ptr_fun`、`mem_fun`/`mem_fun_ref`、`not1`/`not2` 等。前几项在 C++11 被弃用、C++17 中移除（[[N4190]]）；`not1`/`not2` 在 C++17 被弃用、C++20 中移除。它们的功能分别被 lambda、`bind`/`bind_front`、`mem_fn`、`not_fn` 取代（[[func.bind]]）。libc++ 仍保留这些头文件（如 `__functional/binder1st.h`），但只在旧标准模式或显式开启时才提供。

## 思考题

!!! question "思考题 1"
    `std::set<int*>` 里存了一些指向不同堆对象的指针。用内建 `<` 写一个比较器 `[](int* a, int* b){ return a < b; }` 换掉默认的 `std::less<int*>`，在标准意义上有什么区别？

<details markdown="1">
<summary>展开查看答案与解析</summary>

默认的 `std::less<int*>` 按 [comparisons.general]/2 给出由实现定义的严格全序，容器的严格弱序要求一定满足。自写的 lambda 直接用内建 `<`，对不同对象的指针按 [[expr.rel#5]] 结果**未指明**，无法保证传递性与一致性，因此 [[associative.reqmts]] 对 `Compare` 的严格弱序要求不能确证成立——标准意义上程序的行为没有保证。主流平台上二者生成的代码完全相同，但这正是“实践中没问题”与“标准保证”的区别。
</details>

!!! question "思考题 2"
    为什么 `ranges::less` 被设计成普通类，而不是像 `std::less` 那样带一个默认为 `void` 的模板参数？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`std::less<T>` 的 `T` 版本只是“先把实参转换为 `T` 再比较”，在 C++14 有了透明的 `less<>` 之后它已经几乎没有存在价值，只是为了兼容而保留。Ranges 从零设计，直接只提供“透明 + 概念约束”的一种形态；而且作为非模板的普通类，`ranges::less{}` 写起来更短，作为算法默认实参（`Comp comp = {}`）时也不需要写模板实参。
</details>

## 小结

!!! summary
    | 要点 | 内容 |
    |---|---|
    | 函数对象类型 | 能放在 `x(...)` 中 `x` 位置的对象类型：函数指针、有 `operator()` 的类、能转换为函数指针的类 |
    | `T` 版本 | `const T&` 形参，先转换为 `T`；返回 `T` 或 `bool` |
    | `void` 版本 | 转发引用 + `decltype` 返回，SFINAE 友好，带 `is_transparent` |
    | 透明比较器 | 开启关联容器的异构查找；无序容器还要求哈希也透明 |
    | 指针全序 | `less`/`greater`/`less_equal`/`greater_equal` 对任意指针给出由实现定义的严格全序；`void` 版本在调用内建指针比较时同样如此；常量求值中不可用 |
    | `compare_three_way` | `<=>` 的函数对象，约束 `three_way_comparable_with`，指针走全序 |
    | `ranges::less` 等 | 约束 `totally_ordered_with`；只调用 `<`；三歧性是前置条件 |
    | `identity` | 原样转发，Ranges 投影的默认值 |
