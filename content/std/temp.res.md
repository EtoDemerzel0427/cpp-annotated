---
title: 名字决议
summary: 模板定义里的名字何时查找：非依赖名在定义处绑定一次，依赖名在每个特化里再查；什么时候必须写 typename 和 template；以及允许编译器在实例化之前就拒绝模板的那组 IFNDR 规则。
status: done
covers: temp.res.general
papers: P0634R3, P0846R0, P1787R6, P2593R1
related: temp.local, temp.dep, temp.dep.res, temp.point, temp.names, basic.lookup, stmt.if, dcl.pre, topics/two-phase-lookup
tags: 模板, 名字查找, typename, 两阶段查找, IFNDR
updated: 2026-10-19
---

!!! tldr
    - 模板里不依赖模板形参的名字在定义处查找一次，结果固定下来；依赖模板形参的名字在每个特化里替换之后再查。
    - 依赖调用 `f(t)` 的普通查找也只在定义处做，实例化时只追加 ADL。所以定义之后才声明的 `f(int)` 对 `T = int` 永远不可见。
    - 依赖的限定名默认被当作值。指类型要写 `typename`，指模板要写 `template`；C++20 起在成员声明、别名、返回类型等仅类型语境里可以省略 `typename`，块作用域里仍然要写。
    - 模板如果不可能有合法的特化，或者其中不依赖模板形参的部分本身就是错的，程序 IFNDR：编译器可以在定义处报错，也可以不报。
    - C++23 起判断有无合法特化时不计失败的 `static_assert`，所以 `else static_assert(false, "...")` 是合法的写法。

## 编译器在定义处就要解析模板

```cpp
template<class T> void f(T t) {
    T::x * p;      // 乘法？还是声明指针 p？
    t.get<0>();    // 成员模板？还是 (t.get < 0) > ()？
    g(t);          // 哪个 g？
}
```

C++ 的语法依赖名字的含义：`a * b` 是表达式还是声明，`<` 是小于号还是模板实参列表的开头，都要看名字指什么。可是编译器读到这段定义时还不知道 `T` 是什么。

标准的做法是在定义处就完整地解析模板，并把其中的名字分成两类：

- **依赖名**（dependent name）：含义可能随模板实参变化的名字，比如 `T::x`、实参类型依赖于 `T` 的调用 `g(t)`。精确定义在 [[temp.dep]]。
- **非依赖名**：其余的名字。

¶1 非依赖名在模板定义处查找，结果对所有特化都一样。依赖名要在每个特化里、把模板实参替换进去之后再查找一次。这两次查找通常合称[[g:two-phase-lookup|两阶段名字查找]]，见专题 [[topics/two-phase-lookup]]。

!!! std
    If the name is dependent (as specified in [temp.dep]), it is looked up for each specialization (after substitution) because the lookup depends on a template parameter.

为了让定义处的解析能进行下去，依赖名指类型或模板时，程序员要用 `typename` 或 `template` 标明（见后文）。为了让定义处的检查有意义，¶6 又规定了一组违规：模板里不依赖模板形参的部分如果本身就错，编译器可以当场拒绝。

### 依赖调用与非依赖调用（例 2）

```cpp run ok title="two_phase.cpp"
#include <cstdio>
void f(char) { std::puts("f(char)"); }

template<class T> void g(T t) {
    f(1);        // 非依赖：此处只看得到 f(char)
    f(T(1));     // 依赖调用
    f(t);        // 依赖调用
}

enum E { e };
void f(E) { std::puts("f(E)"); }   // 在 g 之后才声明

int main() {
    g(e);        // f(char) f(E) f(E)
    g('a');      // f(char) f(char) f(char)
}
```

`f(1)` 的实参不依赖 `T`，所以它不是依赖调用。`f` 在定义处查找，只找到 `f(char)`，就此绑定，之后声明的任何 `f` 都不会改变它。

`f(T(1))` 和 `f(t)` 的实参类型依赖于 `T`，是[[g:dependent-call|依赖调用]]。它们的候选函数由两部分组成：定义处的无限定查找结果，加上定义语境和实例化语境中[[g:argument-dependent-lookup|实参依赖查找]]（ADL）的结果（[[temp.dep.candidate]]）。`g(e)` 时 `T = E`，`E` 的关联命名空间是全局命名空间，ADL 找到了后声明的 `f(E)`。`g('a')` 时 `T = char`，基本类型没有关联命名空间，ADL 什么都找不到，只剩 `f(char)`。

标准的例 2 里还有一行 `dd++;`，其中 `dd` 在模板之后才声明。`dd` 不是依赖名，定义处查找失败，程序非良构。Clang 和 GCC 不等实例化，在定义处就报告未声明的标识符：

```cpp error
template<class T> void g(T) {
    dd++;        // error: dd 不是依赖名，定义处找不到
}
double dd;
```

!!! pitfall "依赖调用的普通查找不会推迟"
    常见的误解是模板里的名字都在实例化时查找。实际上只有依赖名推迟，而且依赖调用的无限定查找仍然只在定义处做，实例化时只追加 ADL。所以 `template<class T> void g(T t) { f(t); }` 之后才声明的 `f(int)`，对 `g(1)` 永远不可见，因为 `int` 没有关联命名空间。修正方法是把 `f` 的声明移到模板之前。

### 模板实参的成员不改变绑定（例 3）

```cpp run ok
struct A {
    struct B { };
    int a;
    int Y;
};

int a;

template<class T> struct Y : T {
    struct B { };
    B b;                       // Y 自己的 B
    void f(int i) { a = i; }   // ::a，不是 A::a
    Y* p;                      // Y<T>，不是 A::Y
};

Y<A> ya;
int main() { ya.f(1); return a == 1 ? 0 : 1; }
```

`Y<A>` 的基类 `A` 恰好也有 `B`、`a`、`Y` 三个成员。但基类 `T` 依赖于模板形参，定义处的查找不搜索它（[[temp.dep.type#3]]），所以这三个名字在定义处分别绑定到 `Y::B`、`::a` 和注入类名 `Y`。实例化成 `Y<A>` 时不再重新查找。

这样模板的含义由作者在定义处看到的东西决定，不会因为用户传进来的类型而改变。要使用基类的成员，必须把名字写成依赖的，例如 `this->a` 或 `T::a`，见 [[temp.dep.res]]。

### 依赖的转换函数名（例 1）

```cpp run ok
struct A { operator int() { return 42; } };

template<class B, class T>
struct D : B {
    T get() { return operator T(); }   // 依赖名
};

int f(D<A, int> d) { return d.get(); } // 找到 A::operator int
int main() { return f({}) == 42 ? 0 : 1; }
```

`operator T` 的目标类型依赖于 `T`，按 [[temp.dep.general#2]] 它是依赖名，在特化 `D<A, int>` 中才查找，找到基类的 `A::operator int`。

## 后加的默认实参（¶2）

依赖调用的普通查找只在定义处做，那么之后的重声明给函数补上的默认实参怎么办？

```cpp ifndr
void f(int, int);
template<class T> void g(T t) { f(t); }   // 定义处只找到 f(int, int)
void f(int, int = 0);                     // 重声明，补上默认实参
void use() { g(1); }                      // IFNDR
```

¶2 如果某个声明引入了默认实参或默认模板实参，这个声明从特化的实例化点（[[temp.point]]）可达，但特化中的查找没有找到它，而考虑这个默认实参又会改变程序是否合法或者它的含义，程序就是 {{ifndr}}（ill-formed, no diagnostic required，非良构但标准不要求编译器诊断，见 [[g:ifndr]]）。

上例中 `g<int>` 的查找只找到第一个声明，它没有默认实参，`int` 又没有关联命名空间。如果考虑第二个声明的默认实参，`f(t)` 就合法了，正是 ¶2 描述的情形。标准不要求诊断，因为编译器通常把默认实参记在函数实体上，随声明累积，很难区分它来自哪一份声明。Clang 23 在这里报错，并提示 `f` 应该在调用点之前声明。

## typename：声明依赖名是类型（¶3）

```text
typename-specifier:
    typename nested-name-specifier identifier
    typename nested-name-specifier template(opt) simple-template-id
```

¶3 *typename-specifier* 指称的类型（或类模板），就是去掉 `typename` 之后那个 *simple-type-specifier* 指称的东西（[[dcl.type.simple]]）。`typename` 只是向解析器保证这里是类型，不改变查找本身。

所以注 2 特意指出，有了 `typename`，执行的仍然是普通的限定名查找（[[basic.lookup.qual]]）。如果实例化时找到的不是类型，程序非良构：

```cpp error
struct A {
    struct X { };
    int X;            // 数据成员 X 隐藏了类 X
};
struct B { struct X { }; };

template<class T> void f(T) { typename T::X x; }

void foo() {
    f(B{});           // OK: B::X 是类
    f(A{});           // error: 找到的是数据成员 A::X
}
```

详述类型说明符 `struct T::X` 用的是只找类型的查找（[[basic.lookup.elab]]），会跳过数据成员；`typename T::X` 不会。

`typename` 只能写在带嵌套名说明符的名字前，`typename int` 不合法。C++11 起它也可以用在模板之外，只是多余：

```cpp ok
struct S { using type = int; };
typename S::type x = 0;   // OK
```

## 仅类型语境：可以省略 typename 的地方（¶4–¶5）

C++17 及以前，依赖的限定名只要指类型就必须写 `typename`，只有基类列表和成员初始化器例外。C++20 的 [[P0634R3]] 注意到很多位置在语法上只可能是类型，在这些位置要求 `typename` 没有意义，于是引入了[[g:type-only-context|**仅类型语境**]]（type-only context）。

<div class="compare" markdown="1">

```cpp ok
template<class T> struct S {
  using A = T::R;      // 别名
  T::R m;              // 成员声明
  void f(T::R);        // 成员函数形参
  auto g() -> T::R;    // 尾置返回类型
};
```

```cpp error
template<class T> void f() {
  T::R local;
  // error: 块作用域不是
  // 仅类型语境，须写 typename
}
```

</div>

¶5 处于仅类型语境、终端名依赖的限定名，被当作类型。不在仅类型语境的依赖限定名则被当作非类型，除非写了 `typename`。这里的[[g:terminal-name|终端名]]指限定名中最后的那个名字，`T::R` 里的 `R`。

¶4 下列结构中的终端名处于仅类型语境：

| 段落 | 位置 | 例子 |
|---|---|---|
| ¶4.1 | *typename-specifier*、*type-requirement*、嵌套名说明符、详述类型说明符、基类说明符和成员初始化器、*using-enum-declarator* | `struct D : T::Base` |
| ¶4.2 | 友元类型声明 | `friend T::R;` |
| ¶4.3.1 | `new` 的类型 | `new T::R{}` |
| ¶4.3.2 | 别名声明的类型 | `using A = T::R;` |
| ¶4.3.3 | 转换函数的类型 | `operator T::R();` |
| ¶4.3.4 | 尾置返回类型 | `auto f() -> T::R;` |
| ¶4.3.5 | 类型模板形参的默认实参 | `template<class U = T::R>` |
| ¶4.3.6 | 四种具名转型的目标类型 | `static_cast<T::R>(x)` |
| ¶4.4.1 | 命名空间作用域的声明或函数定义 | `template<class T> T::R f();` |
| ¶4.4.2 | 成员声明 | `T::R m;` |
| ¶4.4.3 | 成员声明中的形参（默认实参内除外） | 类内 `void f(T::R);` |
| ¶4.4.4 | 声明符 id 是限定名的函数的形参 | `void S<T>::f(T::R) {}` |
| ¶4.4.5 | lambda 形参、*requires* 表达式的形参 | `[](T::R r) {}` |
| ¶4.4.6 | 常量模板形参的类型 | `template<T::R V>` |

这些位置的共同点是：如果这里不是类型，语法就不成立。表外的位置都存在合法的表达式解释，`typename` 仍然必需，包括块作用域的声明、普通命名空间作用域函数的形参、模板实参（`std::vector<typename T::R>`）、`sizeof` 和 `decltype` 的操作数。

{{c++26}} ¶4 末尾还规定，拼接说明符 `[: ... :]` 是否处于仅类型语境，按同一位置上一个假想的限定名来判断。所以 `using Alias = [:^^int:];` 不需要 `typename`。

下面的例子把表里的大部分位置放在一起：

```cpp run ok title="down_with_typename.cpp"
template<class T, class U = T::R>             // ¶4.3.5
struct S {
    T::R m;                                   // ¶4.4.2
    void f(T::R);                             // ¶4.4.3
    operator T::R();                          // ¶4.3.3
    static T::R sm;
    friend T::R;                              // ¶4.2
    using A = T::R;                           // ¶4.3.2
    auto g() -> T::R { return static_cast<T::R>(m); }   // ¶4.3.4、¶4.3.6
};
template<class T, class U> void S<T, U>::f(T::R) { }   // ¶4.4.4
template<class T, class U> T::R S<T, U>::sm{};          // ¶4.4.1

template<class T> T::R gv{};                  // ¶4.4.1
template<class T> void blk() {
    auto l = [](T::R r) { return r; };        // ¶4.4.5
    typename T::R local{};                    // 块作用域：仍须 typename
    auto* p = new T::R{};                     // ¶4.3.1
    delete p; (void)l; (void)local;
}

struct X { using R = int; };
template struct S<X>;
template void blk<X>();
int main() { }
```

### 形参在哪个作用域，决定能否省略

¶4.4.3 和 ¶4.4.4 只覆盖成员函数和限定名声明的函数。普通命名空间作用域函数的形参不在表里，结果完全不同：

```cpp ifndr
template<class T> T::R f();          // OK: 命名空间作用域声明的返回类型
template<class T> void f(T::R);      // IFNDR: 声明了一个 void 变量模板
```

第二行的 `f` 不是限定名，它的形参不在仅类型语境，`T::R` 被当作表达式。于是 `void f(T::R)` 被解析成类型为 `void`、用 `(T::R)` 直接初始化的变量模板。`void` 变量不可能有合法特化，按 ¶6.1 是 IFNDR。Clang 23 在这里报告变量具有不完整类型 `void`。

为什么区别对待？在命名空间作用域，`int x(expr);` 是合法的直接初始化，所以 `void f(T::R);` 确实可能是变量声明。而类内不允许用圆括号初始化成员，`S<T>::f(...)` 这样的限定声明也只能是函数，那里的形参不可能被误读成初始化器。

块作用域同理，而且更容易看错：

```cpp error
template<typename T> void f() {
    void (*pf)(T::X);   // OK: void* 变量 pf，用 T::X 初始化
    void g(T::X);       // error: 试图声明 void 变量 g
}
```

第一行不是函数指针。`T::X` 被当作表达式，`void (*pf)(T::X)` 声明的是 `void*` 类型的变量 `pf`，用 `T::X` 直接初始化。

### 不在仅类型语境的依赖名被当作值（例 6）

```cpp error
template <class T> void f(int i) {
    T::x * i;           // 表达式（乘法），不是声明变量 i
}

struct Foo { typedef int x; };
struct Bar { static int const x = 5; };

int main() {
    f<Bar>(1);          // OK
    f<Foo>(1);          // error: Foo::x 是类型
}
```

`T::x * i` 在定义处已经被解析为乘法。实例化 `f<Foo>` 时查找找到的是类型，与解析结果矛盾，程序非良构。

¶5 还有一句：如果 *using-declarator* 的终端名依赖并且带了 `typename`，那么指向它的名字被当作 *typedef-name*。

```cpp run ok
template<class T> struct Base { using type = T; };
template<class T> struct D : Base<T> {
    using typename Base<T>::type;   // 带 typename 的依赖 using 声明
    type x{};                       // type 被当作 typedef-name
};
D<int> d;
int main() { }
```

## template：声明依赖名是模板

`typename` 解决的是类型，`template` 解决的是 `<`。规则在 [[temp.names#7]]：`<` 只在前面的名字被查到是模板、前面写了 `template` 关键字，或者满足几种语法条件时，才开始模板实参列表。依赖的成员名在定义处查不到，所以要写 `template`：

<div class="compare" markdown="1">

```cpp error
template<class T> void f(T* p) {
  T* q = p->alloc<200>();
  // error: < 被当作小于号
}
```

```cpp ok
template<class T> void f(T* p) {
  T* q = p->template alloc<200>();
  T::template adjust<100>();
}
```

</div>

不写 `template` 时，`p->alloc<200>()` 被解析为 `(p->alloc < 200) > ()`，而 `()` 不是表达式。几种不需要 `template` 的情形：

- 无限定名的查找找到了函数，或者什么都没找到。C++20 的 [[P0846R0]] 加上了这一条，所以 `get<0>(t)` 在看不到任何 `get` 模板时也能解析。
- 名字是仅类型语境中的终端名（¶7.3.4），例如 `typename T::Y<int>`、成员声明 `T::Y<int> m;`。
- 名字是当前实例化的成员，查找在定义处就找到了模板。

已经能查到模板时多写一个 `template` 也是良构的（[[temp.names#11]]）。

!!! impl "Clang 尚未实现 ¶7.3.4"
    按当前草案，`typename T::Y<int>`、类内 `T::Y<long> b;`、`using Z = T::Y<char>;` 都不需要 `template`。Clang 23 对这三种写法仍然报错，要求加上 `template`。可移植的代码继续写 `typename T::template Y<int>`。

## 在实例化之前检查模板（¶6）

¶6 [[g:templated-entity|模板化实体]]（模板，以及模板里定义的一切）的合法性可以在任何实例化之前检查。注 3 指出了前提：有了 `typename` 和 `template`，编译器知道哪些名字是类型、哪些是模板，就能检查每个模板的语法。

随后 ¶6 列出了一组 IFNDR 情形。它们给了编译器在定义处报错的许可，但不强制。

### 不可能有合法特化（¶6.1）

¶6.1 对某个模板化实体，或其中某条 constexpr if 语句的子语句，无法生成任何合法的特化（不计失败的 `static_assert`），而最内层的外围模板又没有被实例化，程序就是 IFNDR。

不可能有合法特化，意思是不论模板实参是什么，这段代码都是错的。例如前面被解析成 `void` 变量模板的 `void f(T::R)`，又如数组界必为负数的 `int a[-int(sizeof(T))];`。这种模板没有存在的意义，标准允许编译器提前拒绝。不强制诊断，是因为证明不存在任何合法特化在一般情况下不可判定。

如果模板确实被实例化了，错误就按普通规则处理：程序非良构，必须诊断。

### static_assert(false) {{c++23}}

¶6.1 里不计失败的 `static_assert` 这半句，是 C++23 的 [[P2593R1]] 加上的：

```cpp run ok title="static_assert_false.cpp"
#include <type_traits>
template<class T> int classify(T) {
    if constexpr (std::is_integral_v<T>)            return 1;
    else if constexpr (std::is_floating_point_v<T>) return 2;
    else static_assert(false, "unsupported type");  // C++23 起 OK
}
int a = classify(1), b = classify(1.0);

template<class T> void never_used() { static_assert(false); }  // OK: 从未实例化
int main() { }
```

C++23 之前，`else static_assert(false, ...)` 这条子语句不可能有合法特化，整个程序 IFNDR，实践中 GCC 和 Clang 会在定义处直接报告断言失败。程序员只好写一个依赖于 `T` 的假条件：

```cpp
template<class> inline constexpr bool dependent_false = false;
// ...
else static_assert(dependent_false<T>, "unsupported type");
```

这个写法之所以可行，是因为 `dependent_false<T>` 依赖于 `T`，理论上某个显式特化可以让它为 `true`，于是存在合法特化。

C++23 的规定更直接。[[dcl.pre#13]] 规定在模板定义中求值的 `static_assert` 不起作用，¶6 判断有无合法特化时又不计失败的断言。被丢弃的 constexpr if 分支不会被实例化（[[stmt.if#2]]），断言永远不会求值；真正被选中的分支在实例化时求值，失败就照常报错：

```cpp error
template<class T> int f(T) {
    if constexpr (sizeof(T) == 4) return 1;
    else static_assert(false, "unsupported type");
}
int c = f('a');   // error: f<char> 走到 else 分支，断言失败
```

P2593R1 是按缺陷报告处理的，编译器在更早的语言模式下通常也采用新行为。

!!! lawyer "不依赖模板形参的 static_assert 也被推迟"
    [[dcl.pre#13]] 不区分条件是否依赖模板形参。所以 `template<class T> void f(T) { static_assert(sizeof(int) == 0); }` 在定义处不报错，只有 `f` 被实例化时才失败，Clang 23 的行为与此一致。这也只在模板里成立：非模板函数中的 `if constexpr (false) { static_assert(false); }` 照样触发，因为模板之外被丢弃的语句仍要完整检查。

### 不依赖模板形参的部分必须现在就对（¶6.7–¶6.8）

¶6.7 设想在模板定义的右花括号之后立刻做一次实例化。如果这次假想的实例化会因为某个不依赖模板形参的结构而非良构（失败的 `static_assert` 除外），程序 IFNDR。不依赖模板形参的结构此时已经有确定的含义，它现在错，在任何实例化中都错。

<div class="compare" markdown="1">

```cpp error
template<class T> void f() {
  int* p = 1;
  // int 不能初始化 int*
}
```

```cpp error
struct Inc;
template<class T> int f(T) {
  return sizeof(Inc);  // 此处不完整
}
struct Inc { int x; };
```

</div>

右边的例子里，即使 `f` 的所有实例化都发生在 `Inc` 完整之后，紧随定义的那次假想实例化中 `Inc` 仍不完整，所以 IFNDR。Clang 23 对两个例子都在定义处报错。

¶6.8 关心的是含义：一个结构在假想实例化中合法，但它的解释与任何一次实际实例化中的解释不同，程序也是 IFNDR。注 4 列出了几种典型情形：

- ¶6.9 非依赖名用到的类型在定义处不完整，在实例化处已经完整；
- ¶6.10 定义处查找找到了一个包展开形式的 *using-declaration*，而实例化时对应的包为空，什么都找不到；
- ¶6.11 实例化用到了定义模板时还不存在的默认实参或默认模板实参；
- ¶6.12 实例化中的常量求值用到了定义模板时还没有定义的 const 整型或无作用域枚举对象的值、constexpr 对象的值、引用的值或 constexpr 函数的定义；
- ¶6.13 非依赖的 *simple-template-id* 所指的特化，来自定义模板时还没定义的部分特化，或者是那时还没声明的显式特化。

¶6.12 的一个例子：

```cpp ifndr
constexpr int k();
template<class T> void f() { int a[k()]; (void)a; }   // 定义处 k 未定义
constexpr int k() { return 3; }
template void f<int>();                                  // 实例化处 k() == 3
```

在定义处，调用未定义的 constexpr 函数不是常量表达式，`int a[k()]` 是变长数组，在标准 C++ 中非良构；在实例化处它是 `int[3]`。两处解释不同，所以 IFNDR。Clang 23 在定义处就把它当作变长数组（Clang 扩展），给出 `-Wvla-cxx-extension` 警告，可见它确实在定义处固定了解释。

这些规则背后的想法是：不依赖模板形参的结构，含义在定义处就应该确定，之后的声明不应改变它。编译器可以在定义处立即解析和绑定（GCC、Clang），也可以推迟到实例化（旧版 MSVC）。凡是两种策略会得出不同结果的程序，都被规定为 IFNDR，所以合法程序的含义不取决于编译器选哪种策略。

### 其余几种情形（¶6.2–¶6.6）

- ¶6.2 {{c++26}} 展开语句（`template for`，[[stmt.expand]]）的循环体对每个元素实例化一次。如果它没有被实例化过（例如遍历空 tuple），而它又不可能合法，程序 IFNDR。
- ¶6.3 默认模板实参不可能产生合法特化，而且从未在任何实例化中用到。
- ¶6.4 别名模板（[[temp.alias]]）没有任何合法特化，而且程序中从未指名过它的特化。
- ¶6.5 某个约束表达式的规范形式里有一个原子约束，对它的任何满足性检查都不可能良构，而它又从未被检查过。
- ¶6.6 变参模板的每个合法特化都要求模板形参包为空。只能用空包实例化的模板没有必要写成变参。例如成员 `void operator++(int, T... t);`：后置 `++` 只能有一个 `int` 形参，包必须为空。Clang 23 直接报错。

### 哪些错误可以提前诊断（例 7）

注 5 说，模板被实例化后，错误按标准的其他规则诊断，确切的诊断时机属于实现质量问题。例 7 标出了哪些错误可以在实例化之前诊断：

```cpp
int j;
template<class T> class X {
    void f(T t, int i, char* p) {
        t = i;          // 依赖：只有实例化 X::f 且赋值非法时才诊断
        p = i;          // 非依赖：即使 X::f 未被实例化，也可以诊断
        p = j;          // 同上
        X<T>::g(t);     // OK: g 是当前实例化的成员
        X<T>::h();      // 可以提前诊断：当前实例化中没有 h，也没有依赖基类
    }
    void g(T t) {
        +;              // 语法错误：可以提前诊断
    }
};
```

`X<T>::h()` 可以提前诊断，依据是 [[temp.dep.type#5]]：限定名的查找上下文是当前实例化（模板内部对 `X<T>` 自身的指称，见 [[temp.dep]]），并且没有依赖基类时，查不到的名字不是依赖名，在定义处就能确定它不存在。如果 `X` 有依赖基类，`h` 可能来自那里，只能等到实例化。

## 默认实参和 noexcept 说明符（¶7）

¶7 注 6 说明，就名字查找而言，函数模板和类模板成员函数的默认实参与 *noexcept-specifier* 被当作定义（[[temp.decls]]）。它们和函数体一样，用到时才单独实例化（[[temp.inst]]），其中的名字也按本页的两阶段规则查找。所以 [[temp.point]] 要为它们单独规定实例化点。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 第一句处理同一个模板有多个声明的情况（例如通过模块导入看到了同一定义的多个副本）：名字从 `T` 的某个未指明的声明中它出现的位置开始查找，这个声明要么就是 `D` 本身，要么从 `D` 可达，并且从它出发不再能到达另一个含有这次使用的 `T` 的声明。直观地说就是最新的那份含有这个名字的声明。普通代码可以简单理解为：名字从它在模板定义中出现的位置开始查找。

注 1 补充了两点。一些依赖名在解析时也会先查一次，用来判断它是否依赖，或者决定后面的 `<` 是否开始模板实参列表（[[temp.names#7]]）；真正决定它指什么的仍是实例化时那次查找。*using-declarator* 在特化中永远不是依赖的，所以特化中的查找会把它替换为它指名的声明（[[basic.lookup.general]]）。

</details>

!!! impl "三大编译器的两阶段查找"
    - Clang 和 GCC 在看到模板定义时就构建完整的语法树，绑定非依赖名，依赖的部分保留为依赖节点，实例化时替换。¶6 允许它们在定义处报错，它们大量使用这一许可：`p = i`、未声明的标识符、不完整类型等。
    - MSVC 过去把模板体保存为记号序列，实例化时才解析，因此长期接受不写 `typename`、直接使用依赖基类成员这类不合规的代码（见 [[temp.dep.res]]）。VS 2017 起的 `/permissive-` 模式实现了符合标准的两阶段查找，`/Zc:twoPhase-` 可以关掉它。
    - Clang 的 `-fdelayed-template-parsing` 模仿 MSVC 的旧行为，把函数模板体推迟到翻译单元末尾才解析。这不符合标准，在 C++20 及以后的模式下 Clang 会警告该选项已弃用。

!!! history "历史与演进"
    | 版本 | 变化 |
    |---|---|
    | C++98 | 已有两阶段查找、`typename` 和 `template` 消歧义、不可能有合法特化即 IFNDR；`typename` 只能用在模板内 |
    | C++11 | `typename` 和 `template` 前缀可以用在模板之外 |
    | C++17 | constexpr if 的被丢弃子语句不实例化，¶6.1 随之按 constexpr if 子语句单独判断 |
    | C++20 | [[P0634R3]] 引入仅类型语境；[[P0846R0]] 让查找无果的 `name<...>(args)` 也按模板解析 |
    | C++23 | [[P1787R6]] 用组成名字、终端名、查找上下文等概念重写了名字查找；[[P2593R1]] 让失败的 `static_assert` 不计入有无合法特化的判断 |
    | C++26 | 展开语句（¶6.2）；拼接说明符纳入仅类型语境 |

## 常见误解

!!! pitfall "typename 会让查找只找类型"
    不会。`typename T::X` 照常做限定名查找，找到数据成员就报错（注 2）。需要只找类型时用详述类型说明符 `struct T::X`。

!!! pitfall "C++20 起 typename 可以全部省略"
    只有仅类型语境可以省略。块作用域的声明、普通命名空间作用域函数的形参、模板实参、`sizeof` 和 `decltype` 的操作数中仍然要写，因为这些位置都存在合法的表达式解释。

!!! pitfall "在一个编译器上能编译，模板就没问题"
    ¶6 的情形大多是 IFNDR，Clang 和 GCC 能发现一部分，MSVC 的宽松模式几乎全部放过。代码换一个编译器或升级版本后报错，常常就是撞上了 ¶6。

## 思考题

!!! question "思考题 1"
    下面的代码在 C++20 下是否良构？若不是，属于哪一类错误？
    ```cpp
    template<class T> struct S {
        void f(T::type);
    };
    template<class T> void g(T::type);
    ```

<details markdown="1">
<summary>答案</summary>

`S::f` 的形参属于 ¶4.4.3（成员声明中的形参），处于仅类型语境，`T::type` 被当作类型，良构。

`g` 是命名空间作用域的函数模板，名字 `g` 不是限定名，它的形参不属于 ¶4.4 的任何一项。`T::type` 被当作表达式，`void g(T::type);` 被解析为用 `T::type` 初始化的 `void` 变量模板，不可能有合法特化，按 ¶6.1 是 IFNDR（例 5 第二行就是这个例子）。要写成 `template<class T> void g(typename T::type);`。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> void f() {
        if constexpr (false) {
            int* p = 1;
        }
    }
    ```
    `f` 从未被实例化。这个程序良构吗？把 `int* p = 1;` 换成 `static_assert(false);` 呢？

<details markdown="1">
<summary>答案</summary>

`int* p = 1;` 不依赖模板形参，在 ¶6.7 所说的紧随定义的假想实例化中就非良构，即使它位于被丢弃的分支里。constexpr if 只是不实例化被丢弃的分支，不会让不依赖模板形参的错误变得合法。所以程序 IFNDR，Clang 和 GCC 实际在定义处报错。

换成 `static_assert(false);` 则良构（C++23 起，[[P2593R1]]）：¶6.1 和 ¶6.7 都排除了失败的 `static_assert`，而被丢弃的分支永远不会被实例化。
</details>

!!! question "思考题 3"
    为什么标准不规定模板中不依赖模板形参的错误必须在定义处诊断，而是规定为 IFNDR？

<details markdown="1">
<summary>答案</summary>

第一，不存在合法特化是对所有可能的模板实参的断言，一般情况下不可判定，无法要求诊断。第二，标准希望推迟解析的实现（旧版 MSVC、Clang 的 `-fdelayed-template-parsing`）仍然可以符合标准。第三，¶6.8 一类问题要对比定义处和实例化处两个语境，要求诊断就意味着每次实例化都要重新检查所有不依赖模板形参的结构，代价很高。IFNDR 把责任交给程序员，同时允许好的实现尽早报错。
</details>

## 小结

| 规则 | 段落 | 后果 |
|---|---|---|
| 非依赖名在定义处查找、绑定一次 | ¶1 | 之后的声明不影响它 |
| 依赖名在每个特化里替换后再查 | ¶1 | 依赖调用在实例化时只追加 ADL，见 [[temp.dep.res]] |
| 可达但未被找到的默认实参改变了含义 | ¶2 | {{ifndr}} |
| `typename` 照常做限定名查找 | ¶3 | 找到非类型则非良构 |
| 仅类型语境中的依赖限定名被当作类型 | ¶4–¶5 | 可以省略 `typename`（C++20） |
| 其他位置的依赖限定名被当作非类型 | ¶5 | `T::x * i` 是乘法 |
| 不可能有合法特化（不计失败的 `static_assert`） | ¶6.1–¶6.6 | {{ifndr}} |
| 不依赖模板形参的结构在假想实例化中非良构或含义不同 | ¶6.7–¶6.8 | {{ifndr}} |
| 默认实参和 noexcept 说明符被当作定义 | ¶7 | 用到时才实例化 |
