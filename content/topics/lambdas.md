---
title: lambda 与闭包
summary: 一个 lambda 表达式到底创建了什么：编译器写出的闭包类，捕获的规则和代价，调用运算符的各种形态，闭包类型的唯一性带来的 ODR 问题，以及捕获造成的悬垂。
status: done
order: 72
since: c++11
papers: P0018R3, P0806R2, P0624R2, P0315R4, P0428R2, P0780R2, P1091R3, P1169R4, P0847R7, P0170R1
related: expr.prim.lambda, basic.def.odr, depr.capture.this, temp.alias, associative.reqmts.general, topics/dangling-references, topics/type-deduction, topics/compile-time-programming
tags: lambda, 闭包, 捕获, ODR, 悬垂, 专题
updated: 2026-10-19
---

!!! tldr
    - lambda 表达式定义一个无名的类（闭包类型），并创建它的一个对象（闭包对象）。按值捕获的变量是这个类的数据成员，lambda 体是它的 `operator()`。
    - 按值捕获在创建闭包时复制一份快照，按引用捕获只是别名。静态存储期的变量从不被捕获，`[=]` 在成员函数里捕获的是指针 `this`，不是对象。
    - 调用运算符默认是 `const` 的；`auto` 形参让它成为成员模板；C++23 的 `this auto self` 让 lambda 能递归调用自己。
    - 每个 lambda 表达式都是一个独一无二的类型，连 `decltype([]{})` 也是。在头文件里把 lambda 的类型用于命名空间作用域的别名，会让各个翻译单元看到不同的类型。
    - 闭包只要可能活得比当前作用域长，就不要按引用捕获局部变量，也不要按值捕获指针、`string_view` 这类不拥有对象的值。

## 编译器替你写的类

```cpp
int n = 10, total = 0;
auto f = [n, &total](int x) {
  total += x * n;
  return total;
};
f(1);   // total == 10
```

标准规定，lambda 表达式是一个纯右值，它的类型是一个独一无二的无名类，叫做**闭包类型**（[[g:closure-type|closure type]]，[[expr.prim.lambda.closure#1]]）；求值它得到的对象叫做**闭包对象**（[[g:closure-object|closure object]]，[[expr.prim.lambda.general#2]]）。上面这段代码大致等价于右边的写法：

<div class="compare" markdown="1">

```cpp
auto f = [n, &total](int x) {
  total += x * n;
  return total;
};
```

```cpp
class __lambda_1 {
  int __n;         // 按值：一份副本
  int& __total;    // 按引用：示意
public:
  __lambda_1(int& n, int& total)
    : __n(n), __total(total) {}
  int operator()(int x) const {
    __total += x * __n;
    return __total;
  }
};
auto f = __lambda_1{n, total};
```

</div>

这只是一个模型。真正的闭包类型没有这样的构造函数，成员也没有名字；按引用捕获时是否有数据成员是未指定的（[[expr.prim.lambda.capture#12]]）。不过 lambda 的绝大多数性质都能从这个模型推出来：

| lambda 的写法 | 闭包类型里对应的东西 | 出处 |
|---|---|---|
| 按值捕获 `[n]`、`[=]` | 一个与 `n` 同类型（保留 `const`）的无名数据成员 | [[expr.prim.lambda.capture#10]] |
| 按引用捕获 `[&total]`、`[&]` | 通常是一个指针或引用成员，标准不作规定 | [[expr.prim.lambda.capture#12]] |
| lambda 体 | public、inline 的 `operator()` | [[expr.prim.lambda.closure#5]] |
| 默认 | `operator()` 是 `const` 成员函数 | [[expr.prim.lambda.closure#7]] |
| `mutable` | `operator()` 不是 `const` | 同上 |
| `static` {{c++23}} | `operator()` 是静态成员函数 | 同上 |
| `auto` 形参、`<class T>` | `operator()` 是成员函数模板 | [[expr.prim.lambda.closure#5]] |
| 没有捕获 | 多一个到函数指针的转换函数 | [[expr.prim.lambda.closure#11]] |

模型里的 `operator()` 是 `const` 的，却能修改 `total`。原因是 const 成员函数里不能改的是成员本身，`__total` 是引用，被修改的是它指代的外部变量。lambda 也是这样：`[&total]` 的 lambda 不写 `mutable` 也能改 `total`。

各个特性的完整规则见 [[expr.prim.lambda]]，这里只讲怎样用这个模型理解和避开问题。

## 闭包类型的性质

### 每个 lambda 都是一个新类型

```cpp run title="unique.cpp" ok
#include <type_traits>
int main() {
  auto a = [] { return 1; };
  auto b = [] { return 1; };
  static_assert(!std::is_same_v<decltype(a), decltype(b)>);
  static_assert(!std::is_same_v<decltype([] {}), decltype([] {})>);   // C++20
  return a() - b();
}
```

两个逐字相同的 lambda 表达式也是两个类，就像写了两次 `struct {}`。所以闭包的类型只能靠 `auto`、`decltype` 或模板实参推导得到，存进统一类型的变量时要用 `std::function` 这样的类型擦除包装。

### 不是聚合，特殊成员看有没有捕获

闭包类型不是聚合（[[expr.prim.lambda.closure#4]]），不能用 `decltype(f){…}` 伪造一个闭包对象。它的默认构造函数和赋值运算符取决于有没有捕获（[[expr.prim.lambda.closure#17]]）：

| | 无捕获 | 有捕获 |
|---|---|---|
| 默认构造 | 可以 {{c++20}} | 不可以 |
| 复制、移动构造 | 可以 | 可以（成员不可复制时只能移动） |
| 复制赋值 | 可以 {{c++20}} | 弃置 |
| 移动赋值 | 可以 {{c++20}} | 不声明，赋值时选中弃置的复制赋值 |

本机 Clang 23 用 `<type_traits>` 验证：无捕获的闭包 `is_default_constructible`、`is_copy_assignable` 都为真，`is_empty` 为真；捕获一个 `int` 后两者都为假；捕获一个 `std::unique_ptr` 后 `is_copy_constructible` 为假、`is_move_constructible` 为真。

有捕获的闭包不能赋值，这在把 lambda 放进容器的模板实参时会碰到，见最后一节。

### 大小

闭包的大小就是它的数据成员加上对齐。本机 Clang 23（arm64，libc++）测得：

| lambda | `sizeof` | 说明 |
|---|---|---|
| `[] {}` | 1 | 空类 |
| `[a] { return a; }` | 4 | 一个 `int` 成员 |
| `[a, d] { return a + d; }` | 16 | `int` + `double`，按 8 对齐 |
| `[&a] { return a; }` | 8 | 一个指针 |
| `[&a, &b]`、`[&]` 用到 `a`、`b` | 16 | 每个按引用捕获的变量一个指针 |
| `[=] { return N + 1; }`，`const int N = 10` | 1 | 没有捕获 `N` 的成员，见下文 |
| `[=] { return &N; }` | 4 | 取地址，必须有成员 |
| `[s]`，`std::string s` | 24 | 一个 `std::string` |
| `[this]` | 8 | 一个指针 |
| `[*this]`，对象有三个 `int` | 12 | 整个对象的副本 |

标准允许闭包类型的大小、对齐、是否可平凡复制、是否标准布局因实现而异（[[expr.prim.lambda.closure#4]]），不要依赖这些数字。

## 捕获

### 按值是快照，按引用是别名

```cpp run title="snapshot.cpp" ok
#include <cstdio>
int main() {
  int x = 1;
  auto byval = [x] { return x; };    // 此刻复制 x
  auto byref = [&x] { return x; };   // 记住 x 本身
  x = 2;
  std::printf("%d %d\n", byval(), byref());   // 1 2
}
```

按值捕获的成员在求值 lambda 表达式时直接初始化（[[expr.prim.lambda.capture#16]]），此后与原变量无关。之后调用多少次、原变量怎么变，`byval` 看到的都是创建时的值。

### 用到什么才捕获什么

写了**默认捕获**（capture-default）`[=]` 或 `[&]` 时，编译器只捕获 lambda 体里实际用名字引用、并且会被求值的外层局部实体（[[expr.prim.lambda.capture#7]]）。没有用到的变量不会进闭包。

能被捕获的只有**局部实体**（[[g:local-entity|local entity]]）：自动存储期的变量、结构化绑定，以及成员函数里的 `*this`。全局变量和静态局部变量不需要也不能捕获，lambda 体直接访问原来的对象：

```cpp run title="static.cpp" ok
#include <cstdio>
int g_count = 0;
int main() {
  static int s = 1;
  auto l = [=] { return s + g_count; };   // 什么也没捕获
  s = 10;
  g_count = 5;
  std::printf("%d %zu\n", l(), sizeof l);   // 15 1
}
```

`[=]` 看起来像是复制了一切，但 `s` 和 `g_count` 都不是局部实体，`l()` 读到的是调用时的值 15，闭包的大小是 1。

常量是另一个特例。读取一个常量的值不算 [[g:odr-use]]（以需要变量本身存在的方式使用它，例如取地址、绑定引用），编译器直接用它的值。所以不写捕获也能在 lambda 里读常量，而 `[=]` 下读常量虽然算作隐式捕获，按 [[expr.prim.lambda.capture#11]] 指代的仍是外层的变量，实现可以不为它分配成员。这就是上表中 `[=] { return N + 1; }` 大小为 1 的原因。一旦取地址或绑定到 `const int&` 形参（例如传给 `std::max`），就必须真正捕获。

### `this` 与 `*this`

成员函数里的 lambda 访问成员 `id`，实际访问的是 `this->id`。被捕获的是指针 `this`，也就是按引用捕获了整个对象：

```cpp run title="this.cpp" ub
#include <cstdio>
#include <functional>
#include <memory>
struct Widget {
  int id = 7;
  std::function<int()> getter() {
    return [=] { return id; };   // 捕获 this，不是 id 的副本
  }
};
int main() {
  auto w = std::make_unique<Widget>();
  auto g = w->getter();
  w.reset();
  std::printf("%d\n", g());      // UB：通过悬垂的 this 读成员
}
```

`[=]` 让人以为对象被复制了，所以 C++20 弃用了 `[=]` 隐式捕获 `this`（[[expr.prim.lambda.capture#7]]、[[depr.capture.this]]，[[P0806R2]]）。本机 Clang 23 在 `-std=c++20` 及以上给出 `-Wdeprecated-this-capture` 警告，`-std=c++17` 下没有；ASan 在 `g()` 处报告 heap-use-after-free。

两种明确的写法：

<div class="compare" markdown="1">

```cpp
// 按引用：对象必须活得更久
return [=, this] { return id; };
```

```cpp
// C++17：复制整个对象
return [*this] { return id; };
```

</div>

`[*this]` 把对象复制进闭包（[[P0018R3]]），之后对象被销毁或修改都与闭包无关；代价是复制整个对象，对大对象或不可复制的对象不适用。异步回调里常见的另一种做法是捕获一个 `shared_ptr`（例如 `[self = shared_from_this()]`），让闭包共同拥有对象。

### init-capture 与移动捕获

`[name = 初始化器]` 叫做 **init-capture**，如同在闭包里声明了一个 `auto name = 初始化器;` 的成员（[[expr.prim.lambda.capture#6]]）。它解决了两个问题：给成员起一个不同的名字或用任意表达式初始化，以及把只能移动的对象移进闭包。

```cpp run title="move-capture.cpp" ok
#include <cstdio>
#include <memory>
#include <vector>
int main() {
  auto buf = std::make_unique<std::vector<int>>(1000, 1);
  auto task = [b = std::move(buf)] { return b->size(); };   // 闭包拥有缓冲区
  std::printf("%d %zu\n", buf == nullptr, task());          // 1 1000
}
```

按值捕获了只能移动的成员，闭包的复制构造函数就是弃置的，闭包也只能移动。`std::function` 要求可调用对象可复制，所以 `std::function<std::size_t()> f = std::move(task);` 非良构，本机 libc++ 报告调用了闭包被隐式弃置的复制构造函数。C++23 的 `std::move_only_function` 就是为这种情形设计的，本机 libc++（Clang 23）还没有提供它。

init-capture 还有两点与简单捕获不同：

- 它按 `auto` 推导，去掉顶层 `const`：`const std::string s;` 时 `[s]` 的成员是 `const std::string`，`[s = s]` 的成员是 `std::string`。
- 显式捕获的成员按捕获列表的顺序初始化（[[expr.prim.lambda.capture#15]]），所以 `[n = v.size(), v = std::move(v)]` 先取大小再移动，顺序反过来就会读到移走后的对象。

### 结构化绑定和包

C++20 起结构化绑定是可以捕获的局部实体（[[P1091R3]]），形参包可以用 init-capture 整体移进闭包（[[P0780R2]]）：

```cpp run title="pack.cpp" ok
#include <utility>
template<class... Ts> constexpr auto bind_all(Ts... ts) {
  return [...xs = std::move(ts)](auto f) { return f(xs...); };   // init-capture 包
}
static_assert(bind_all(1, 2, 3)([](int a, int b, int c) { return a + b + c; }) == 6);

int sum_pair() {
  auto [p, q] = std::pair{1, 2};
  return [p, &q] { return p + q; }();   // 捕获结构化绑定
}
int main() { return sum_pair() - 3; }
```

本机 Clang 23 在 `-std=c++17` 下对这两种写法都只给出 C++20 扩展警告。包展开中 `...` 的位置规则见 [[expr.prim.lambda.capture#18]] 和 [[expr.prim.lambda]]。

## 调用运算符

### `const` 与 `mutable`

调用运算符默认是 `const` 的，所以按值捕获的成员在 lambda 体里不能修改。`mutable` 去掉这个 `const`，闭包就成了带状态的函数对象：

```cpp run title="mutable.cpp" ok
#include <algorithm>
#include <cstdio>
#include <vector>
int main() {
  auto counter = [n = 0]() mutable { return ++n; };
  std::vector<int> v(3);
  std::generate(v.begin(), v.end(), counter);   // 按值传入，修改的是副本
  std::printf("%d %d %d | %d\n", v[0], v[1], v[2], counter());   // 1 2 3 | 1
}
```

状态存在闭包对象里，复制闭包就复制了状态。标准算法大多按值接收函数对象，`counter` 本身的 `n` 没有变，所以最后一次调用返回 1。需要在调用方看到状态时，按引用捕获外部变量，或传 `std::ref(counter)`。

<div class="compare" markdown="1">

```cpp
auto d = [n = 0] { return ++n; };
// error: operator() 是 const，
// 成员 n 不能修改
```

```cpp
const auto c = [n = 0]() mutable {
  return ++n;
};
c();   // error: 非 const 的 operator()
       // 不能在 const 对象上调用
```

</div>

### 泛型 lambda 与模板 lambda

形参里有 `auto` 的 lambda 叫做**泛型 lambda**（[[g:generic-lambda|generic lambda]]），它的 `operator()` 是一个成员函数模板，每个 `auto` 生成一个模板形参（[[expr.prim.lambda.closure#5]]）。C++20 起还可以直接写模板形参列表（[[P0428R2]]）：

```cpp run title="generic.cpp" ok
#include <cstdio>
#include <vector>
int main() {
  auto count = [](auto&&... args) { return sizeof...(args); };   // template<class... Ts>
  auto first = []<class T>(const std::vector<T>& v) -> T { return v.front(); };
  auto make  = []<class T>() { return T{42}; };                   // T 无法推导
  std::printf("%zu %d %g\n", count(1, 'a', "s"), first(std::vector{7, 8}),
              make.operator()<double>());
}
```

模板形参列表适合三种情形：需要类型的名字（`T`），需要约束形参的形状（`const std::vector<T>&`），或者完美转发时想写 `std::forward<T>(x)` 而不是 `std::forward<decltype(x)>(x)`。模板形参无法从实参推导时，只能像 `make.operator()<double>()` 这样显式写出，这种 lambda 通常不如改写成普通函数模板。

泛型 lambda 的 `auto` 形参按模板实参推导的规则推导，与函数模板完全相同，见 [[topics/type-deduction]]。

### `constexpr`、`consteval`、`static`

| 写法 | 含义 |
|---|---|
| 不写 | 满足 constexpr 函数的要求时，`operator()` 自动是 constexpr {{c++17}}（[[P0170R1]]） |
| `constexpr` | 要求它是 constexpr 函数 |
| `consteval` {{c++20}} | `operator()` 是立即函数，只能在编译期调用 |
| `static` {{c++23}} | `operator()` 是静态成员函数，不能有捕获（[[P1169R4]]） |

```cpp run title="specifiers.cpp" ok
auto sq = [](int x) { return x * x; };   // 隐式 constexpr
static_assert(sq(4) == 16);
auto inc = [](int x) consteval { return x + 1; };
static_assert(inc(1) == 2);
auto twice = [](int x) static { return 2 * x; };
static_assert(decltype(twice)::operator()(3) == 6);   // 不需要对象
int main() { return twice(0); }
```

无捕获 lambda 的非静态 `operator()` 仍要接收一个指向空闭包的对象参数。`static` 去掉这个参数，常用于标准库算法的比较器、投影这类无状态函数对象。更多编译期计算的用法见 [[topics/compile-time-programming]]。

### 递归：显式对象参数

闭包类型没有名字，lambda 体里的 `this` 又指外层对象，所以 C++23 之前 lambda 没有直接的办法调用自己。C++23 的显式对象参数（[[P0847R7]]）让第一个形参就是闭包对象本身：

<div class="compare" markdown="1">

```cpp
// C++14：把自己当实参传进去
auto fib = [](auto& self, int n)
    -> int {
  return n < 2 ? n
       : self(self, n - 1)
       + self(self, n - 2);
};
fib(fib, 20);   // 6765
```

```cpp
// C++23：this auto self
auto fib = [](this auto self, int n)
    -> int {
  return n < 2 ? n
       : self(n - 1) + self(n - 2);
};
fib(20);        // 6765
```

</div>

两个版本都显式写了 `-> int`。这里只有一条 `return`，递归调用就在其中，此时返回类型还没有推导出来，调用它非良构（[[dcl.spec.auto.general#13]]）。如果先写 `if (n < 2) return n;`，后面的递归调用就能使用已经推导出的类型。

另一种常见写法是 `std::function<int(int)> fib = [&fib](int n) {…};`，它可行，但每次递归都经过类型擦除的间接调用，而且闭包按引用捕获了 `fib` 自己，`fib` 被复制或移走后容易悬垂。

`self` 按值传递时每层递归复制一次闭包；有捕获时写 `this const auto& self` 可以避免复制。

## 转换为函数指针

没有捕获、不是泛型、没有显式对象参数的 lambda 可以隐式转换为同签名的函数指针（[[expr.prim.lambda.closure#11]]）。函数指针只是一个地址，没有地方存放捕获的状态，所以有捕获的 lambda 不能转换。

```cpp run title="fnptr.cpp" ok
#include <cstdio>
#include <cstdlib>
int main() {
  int a[] = {3, 1, 2};
  std::qsort(a, 3, sizeof(int), [](const void* l, const void* r) {   // 转换为函数指针
    int x = *static_cast<const int*>(l), y = *static_cast<const int*>(r);
    return (x > y) - (x < y);
  });
  auto p = +[](int i) { return i * 2; };   // 一元 + 触发转换，p 的类型是 int(*)(int)
  std::printf("%d %d %d %d\n", a[0], a[1], a[2], p(21));   // 1 2 3 42
}
```

C 风格的回调接口通常带一个 `void*` 用户数据参数，有状态的 lambda 可以把状态放在那里传进去，回调本身仍用无捕获 lambda。无捕获的泛型 lambda 有转换函数模板，规则见 [[expr.prim.lambda]]。

## 未求值语境与 ODR

C++20 起 lambda 可以出现在 `decltype`、`sizeof` 这样的未求值操作数里（[[P0315R4]]），加上无捕获闭包可以默认构造（[[P0624R2]]），`decltype([](int a, int b) { return a > b; })` 就能直接当作比较器类型。但每次出现都是一个新类型，在别名模板里也一样：`template<class T> using A = decltype([] {});` 中 `A<int>` 和 `A<char>` 是不同的闭包类型（[[temp.alias#5]]）。

把这种别名写进头文件，问题就来了：

```cpp title="cmp.h"
#include <set>
using ByDesc = decltype([](int a, int b) { return a > b; });
using DescSet = std::set<int, ByDesc>;
int largest(const DescSet& s);
```

```cpp title="a.cpp"
#include "cmp.h"
int largest(const DescSet& s) { return *s.begin(); }
```

```cpp title="b.cpp" ifndr
#include "cmp.h"
#include <cstdio>
int main() { DescSet s{1, 3, 2}; std::printf("%d\n", largest(s)); }
```

`cmp.h` 被包含两次，lambda 表达式就出现了两次，`a.cpp` 和 `b.cpp` 里的 `ByDesc` 是两个不同的类型。于是两个文件里的 `largest` 形参类型不同，是两个不同的函数：`b.cpp` 调用的那个从来没有定义，按 [[basic.def.odr#12]] 程序非良构，不要求诊断。本机 Clang 23 给 `largest` 内部链接，并警告 "function 'largest' has internal linkage but is not defined"，链接时报 undefined symbol。

ODR 对 lambda 的保证只覆盖可以在多个翻译单元里重复定义的实体（**可定义项**，[[g:definable-item|definable item]]：inline 函数和变量、类、模板等）的定义内部：这些定义里对应的 lambda 被视为同一个闭包类型（[[basic.def.odr#16]]、[[basic.def.odr#18]]）。命名空间作用域的类型别名不是可定义项，得不到这个保证。修正的办法是让 lambda 出现在 inline 变量的初始化器里：

```cpp title="cmp.h" ok
#include <set>
inline constexpr auto by_desc = [](int a, int b) { return a > b; };
using DescSet = std::set<int, decltype(by_desc)>;
int largest(const DescSet& s);
```

这样各个翻译单元里 `by_desc` 是同一个变量，类型也是同一个闭包类型。本机 Clang 23 生成的是外部链接的符号，`c++filt` 还原为 `largest(std::__1::set<int, by_desc::'lambda'(int, int) const, ...> const&)`，闭包类型以变量 `by_desc` 命名，程序正常链接，输出 3。

<details class="fine" markdown="1"><summary>其他相关规则</summary>

- inline 函数体里的 lambda 是安全的：函数定义在多个翻译单元中出现时，表现如同只有一个定义（[[basic.def.odr#19]] 例 8 的 `f`）。
- inline 函数的默认实参里的 lambda 则不受保护，每个翻译单元得到不同的闭包类型，程序非良构，不要求诊断（同一例子中的 `g`）。类定义里成员函数的默认实参例外（例子中的 `X::h`）。
- 按 [[basic.def.odr#18]]，写在类定义里的 lambda（例如 `struct H { using type = decltype([](int a, int b) { return a > b; }); };`）也应当在各个翻译单元中是同一个类型。本机 Clang 23 对这种写法仍给出内部的修饰名，上面的例子照样链接失败，所以目前用 inline 变量更稳妥。

</details>

## 悬垂与捕获的生命周期

闭包对象就是普通对象：按值捕获的成员随闭包一起构造、复制和析构。

```cpp run title="lifetime.cpp" ok
#include <cstdio>
struct T {
  T() { std::puts("T()"); }
  T(const T&) { std::puts("T(const T&)"); }
  T(T&&) noexcept { std::puts("T(T&&)"); }
  ~T() { std::puts("~T()"); }
};
int main() {
  T t;                            // T()
  {
    auto l = [t] {};              // T(const T&)：创建闭包时复制
    auto l2 = l;                  // T(const T&)：复制闭包就复制成员
  }                               // ~T() ~T()：两个闭包析构
  {
    auto m = [u = static_cast<T&&>(t)] {};   // T(T&&)
  }                               // ~T()
}                                 // ~T()：t 本身
```

按值捕获能保证的只有成员自己的寿命。成员本身是一个不拥有对象的值时，闭包照样悬垂。三种常见的情形：

1. 按引用捕获局部变量，闭包被返回、存储或交给另一个线程，见 [[topics/dangling-references]] 第 7 节。
2. 成员函数里 `[=]` 或 `[this]` 捕获的 `this`，对象先于闭包销毁，见上文的 `this.cpp`。
3. 按值捕获了指针、`std::string_view`、`std::span`、迭代器，它们指向的对象先死。

```cpp run title="view-capture.cpp" ub
#include <cstdio>
#include <functional>
#include <string>
#include <string_view>
std::function<std::size_t()> make() {
  std::string name = "a name long enough to live on the heap";
  std::string_view sv = name;
  return [sv] { return sv.size() + sv[0]; };   // 复制的是视图，不是字符串
}
int main() { std::printf("%zu\n", make()()); }  // UB：name 已经销毁
```

本机 Clang 23 对这段代码没有警告，ASan 在 `sv[0]` 处报告 heap-use-after-free。闭包要活得比当前作用域长时，只捕获拥有对象的值：`std::string`、容器、`unique_ptr`、`shared_ptr`，或者 `[*this]`。按引用捕获的实体在其生命周期结束后再调用闭包，[[expr.prim.lambda.capture#17]] 的注指出这很可能导致 UB。

## 用作容器的比较器和哈希

```cpp run title="containers.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <unordered_set>
struct Point { int x, y; };
int main() {
  // 无捕获：类型就够了，容器自己默认构造比较器（C++20）
  std::set<std::string, decltype([](const std::string& a, const std::string& b) {
             return a.size() < b.size(); })> by_len{"ccc", "a", "bb"};
  std::printf("%s\n", by_len.begin()->c_str());   // a

  auto h  = [](const Point& p) { return std::hash<int>{}(p.x) ^ (std::hash<int>{}(p.y) << 1); };
  auto eq = [](const Point& a, const Point& b) { return a.x == b.x && a.y == b.y; };
  std::unordered_set<Point, decltype(h), decltype(eq)> pts{{1, 2}, {1, 2}, {3, 4}};
  std::printf("%zu\n", pts.size());                // 2

  // 有捕获：必须把比较器对象传给构造函数
  int pivot = 10;
  auto near = [pivot](int a, int b) { return std::abs(a - pivot) < std::abs(b - pivot); };
  std::set<int, decltype(near)> s(near);
  s.insert({3, 12, 20});
  std::printf("%d\n", *s.begin());                 // 12
}
```

无捕获的 lambda 类型可以默认构造，所以 `std::set<K, decltype(lambda)>` 不需要传比较器对象。C++20 之前闭包不能默认构造，只能写 `std::set<K, decltype(cmp)> s(cmp);`。

有捕获的比较器有两处限制：

- 不能默认构造，`std::set<int, decltype(near)> s2;` 非良构。关联容器的默认构造函数要求比较器满足 *Cpp17DefaultConstructible*（[[associative.reqmts.general#20]]）。
- 不能赋值。本机 libc++ 的 `set` 复制赋值时会给比较器赋值，`s2 = s;` 报错 "cannot be assigned because its copy assignment operator is implicitly deleted"。

所以需要状态、又需要容器可赋值时，把比较器写成一个有名字的类；它还能定义 `is_transparent` 来启用异构查找，这一点 lambda 也做不到，因为闭包类型里不能加嵌套类型。

## 思考题

!!! question "1"
    下面两个闭包的 `sizeof` 在 Clang 上各是多少？为什么不同？
    ```cpp
    void f() {
      const int N = 10;
      auto a = [=] { return N * 2; };
      auto b = [=] { const int& r = N; return r; };
    }
    ```

<details markdown="1">
<summary>答案</summary>

本机 Clang 23 上 `a` 是 1，`b` 是 4。两个 lambda 都隐式捕获了 `N`：`N` 在体内被潜在求值地引用，这就满足 [[expr.prim.lambda.capture#7]]。区别在于是否 odr-use。`N * 2` 只读常量的值，不是 odr-use，按 [[expr.prim.lambda.capture#11]] 指代外层的 `N`，Clang 没有为它分配成员；`const int& r = N` 绑定引用是 odr-use，引用必须绑定到闭包里的那个副本，所以要有一个 `int` 成员。标准不规定闭包的大小（[[expr.prim.lambda.closure#4]]）。
</details>

!!! question "2"
    `auto l = [v = std::vector<int>(100)]() mutable { v.push_back(1); };` 之后，`std::function<void()> f = l;` 和 `std::function<void()> g = std::move(l);` 分别做了什么？`l` 还能用吗？

<details markdown="1">
<summary>答案</summary>

两者都合法，`vector` 可以复制，所以闭包可以复制。`f = l` 复制整个闭包，`f` 里有一个独立的 100 元素 `vector`；`g = std::move(l)` 移动闭包，`l` 的成员 `v` 被移走，处于有效但未指定的状态（libc++ 上是空的）。`l` 仍然可以调用，因为闭包对象还活着，只是它的 `v` 已经不是原来的内容。闭包的复制和移动就是成员的逐一复制和移动（[[expr.prim.lambda.closure#17]]）。
</details>

!!! question "3"
    C++23 之前，为什么不能这样写递归 lambda？
    ```cpp
    auto fact = [](int n) { return n < 2 ? 1 : n * fact(n - 1); };
    ```

<details markdown="1">
<summary>答案</summary>

`fact` 用 `auto` 声明，它的类型要从初始化器推导，而初始化器里又用到了 `fact`。类型还没推导出来就用名字指代它，程序非良构（[[dcl.spec.auto.general#13]]），本机 Clang 23 报 "variable 'fact' declared with deduced type 'auto' cannot appear in its own initializer"。改成 `[&fact]` 也无济于事，问题不在捕获，而在类型推导。

lambda 体又不在闭包类型的作用域里，没有名字能指代闭包自己。所以 C++23 引入 `this auto self`，C++14 的办法是把闭包自己作为实参传进去，或者改用 `std::function` 这样类型事先已知的变量。
</details>
