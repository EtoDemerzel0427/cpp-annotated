---
title: 模板实参推导
summary: 编译器怎样补全函数模板的模板实参：先代入显式实参，再推导、补默认值、检查约束，最后整体代入；代入时出现无效类型或表达式，候选被安静地剔除（SFINAE），但只限直接语境。另含取地址、转换函数模板、偏序和从声明推导四种推导场合。
status: done
covers: temp.deduct.general, temp.deduct.funcaddr, temp.deduct.conv, temp.deduct.partial, temp.deduct.decl
papers: N2634, P0315R4
related: temp.deduct.call, temp.deduct.type, temp.fct.spec, temp.over, temp.func.order, temp.inst, temp.constr.constr, over.match.best, topics/type-deduction
tags: 模板, 模板实参推导, SFINAE, 偏序
updated: 2026-10-19
---

!!! tldr
    - 推导的核心是拿用模板形参写成的类型 `P` 去匹配一个实际类型 `A`。调用、取地址、转换函数、偏序、声明特化，只是 `P` 和 `A` 的来源不同。
    - 一次推导按固定步骤进行：代入显式实参，推导，补默认模板实参，检查约束，检查非依赖形参的转换，最后把全部实参代入函数类型。任何一步失败，这个模板就不再是候选。
    - SFINAE：代入产生无效类型或表达式时，只是推导失败，不报错。但只限签名本身（直接语境）里的错误；为此实例化的类模板、lambda 函数体里的错误都是硬错误。
    - 代入按词法顺序进行，遇到失败就停。把返回类型从前置改成尾置，可能把 SFINAE 变成硬错误。
    - 偏序判断两个模板谁更特殊：用一个模板的变换形式去推导另一个，双向各做一次。

## 推导在做什么

```cpp
template<class T> const T& max(const T& a, const T& b);

int x = max(1, 2);   // 没有写 <int>，编译器推出 T = int
```

调用函数模板时没有写出的模板实参，由编译器从使用中推出来，这叫**模板实参推导**（template argument deduction）。上例中，编译器拿形参类型 `const T&`（记作 `P`）去对照实参类型 `int`（记作 `A`），求出让两者一致的 `T`。

所有推导场合的核心都是这种 `P` 对 `A` 的结构匹配，规则在 [[temp.deduct.type]]。各场合的区别只在于 `P`、`A` 从哪里来、比较前做哪些调整。最常见的从函数调用推导见 [[temp.deduct.call]]；下面先讲推导前后的整体流程（[temp.deduct.general]），再讲其余四种场合。

## 一次推导的步骤（¶1–¶6）

¶1 引用函数模板特化时，所有模板实参都必须有值：显式指定、从使用中推导，或者取默认模板实参（[[temp.fct.spec]]）。

```cpp
template<class U, class V> U convert(V v);

void g(double d) {
    int i = convert<int>(d);      // 调用 convert<int, double>(double)
    int c = convert<char>(d);     // 调用 convert<char, double>(double)
}
```

函数调用中，¶2–¶6 规定的步骤是：

1. 代入显式写出的模板实参（¶2）；
2. 调整函数形参类型：数组变指针、函数变函数指针、去掉顶层 cv（¶3）；
3. 用调整后的函数类型做推导（¶5，具体规则见 [[temp.deduct.call]]）；
4. 没推导出来的模板形参，取默认模板实参（¶5）；
5. 把全部模板实参代入模板形参列表（¶5）；
6. 检查约束（¶5）；
7. 检查非依赖形参能否从实参隐式转换（¶5）；
8. 把全部模板实参代入函数类型（¶5）。

任何一步得到无效的结果，推导就失败，这个模板不为本次调用提供候选。¶6 总结说，代入函数类型发生两次：开头代入显式实参，结尾代入推导出的和默认的实参。

### 显式实参的代入（¶2–¶4）

¶2 写了显式模板实参列表时，如果这个 *template-id*（C++26 起也可以是拼接特化说明符）不合法（[[temp.names]]），推导失败；否则把这些实参代入对应的模板形参。

¶3 代入之后做 [[dcl.fct]] 规定的形参类型调整，例如 `void(const int, int[5])` 变成 `void(int, int*)`。注 1 提醒，形参的顶层 `const` 不影响函数类型，但仍影响函数体里那个形参变量的类型：

```cpp run ok
#include <type_traits>
template <class T> void f(T t) {
    static_assert(std::is_const_v<decltype(t)> == std::is_const_v<T>);
}
template <class Z> void h(Z, Z*) { }

int main() {
    f<int>(1);          // 函数类型 void(int)，t 不是 const
    f<const int>(1);    // 函数类型 void(int)，t 是 const
    h<const int>(1, 0); // 函数类型 void(int, const int*)

    static_assert(std::is_same_v<decltype(&f<const int>), void(*)(int)>);
    static_assert(std::is_same_v<decltype(&h<const int>), void(*)(int, const int*)>);
}
```

`h<const int>` 的第一个形参是 `const int`，顶层 `const` 被去掉；第二个形参是 `const int*`，这个 `const` 不在顶层，保留。

¶4 注 2 指出，`f<int>(1)` 和 `f<const int>(1)` 调用的是两个不同的函数，尽管函数类型相同。它们有各自的地址和各自的静态变量。

### 默认模板实参（¶5）

¶5 推导完成后，如果某个模板实参没有推导出来，而对应的模板形参有默认实参，就把前面已经确定的模板实参代入这个默认实参来得到它。代入结果无效时推导失败。

```cpp
template <class T, class U = double>
void f(T t = 0, U u = 0);

void g() {
    f(1, 'c');        // f<int, char>(1, 'c')
    f(1);             // f<int, double>(1, 0)：U 取默认模板实参
    f();              // error: T 无法推导
    f<int>();         // f<int, double>(0, 0)
    f<int, char>();   // f<int, char>(0, 0)
}
```

`f()` 失败，是因为函数的默认实参 `T t = 0` 不参与推导（[[temp.deduct.type#22]]）：默认实参的类型本身就取决于 `T`。

### 约束和非依赖形参先于最终代入（¶5）

¶5 接着规定：

- 全部模板实参确定后，先代入模板形参列表（比如常量模板形参的类型），无效则推导失败。
- 函数模板有关联约束时，检查是否满足（[[temp.constr.constr]]），不满足则推导失败。
- 在函数调用中，对每个有实参的形参，如果它的类型在代入任何显式实参之前就不依赖模板形参，检查实参能否隐式转换为这个类型，不能则推导失败。注 3 说明，其余形参的转换留给重载决议去检查。
- 都通过了，才把模板实参代入函数类型。

约束和非依赖形参的检查都排在代入函数类型之前。代入函数类型可能要实例化别的模板，而实例化里的错误是硬错误；先做便宜、不需要实例化的检查，可以在实例化之前就淘汰候选：

```cpp ok
template <class T> struct Z {
    typedef typename T::x xx;          // 对 T = int 或 A 实例化都会出错
};
template <class T> concept C = requires { typename T::A; };

template <C T> typename Z<T>::xx f(void *, T);   // #1
template <class T> void f(int, T);               // #2

struct A {} a;
struct ZZ {
    template <class T, class = typename Z<T>::xx> operator T *();
    operator int();
};

int main() {
    ZZ zz;
    f(1, a);    // OK：调用 #2
    f(zz, 42);  // OK：调用 #2
}
```

- `f(1, a)`：#1 的第一个形参 `void*` 不依赖模板形参，`1` 不能转换为 `void*`，推导在这里失败，返回类型 `Z<A>::xx` 根本不会被代入。否则实例化 `Z<A>` 会因为没有 `A::x` 而报硬错误。
- `f(zz, 42)`：`T = int`，约束 `C<int>` 不满足，推导失败。如果先检查转换，`zz` 到 `void*` 的转换会考虑 `operator T*()`，要代入 `Z<void>::xx`，同样是硬错误。

早期的规则是先代入整个函数类型，再在重载决议里检查转换，很多本该被淘汰的候选在代入返回类型时就触发了硬错误。C++20 引入约束时，[[CWG2369]] 把检查调整成了今天的顺序。

## SFINAE（¶7–¶12）

### 代入失败不是错误

```cpp ok
template<typename T>
T* fun(T&& v);   // #1

void fun(...);   // #2

void test() {
    int i = 0;
    fun(i);      // 调用 #2
}
```

`fun(i)` 中 `i` 是左值，`T` 推导为 `int&`（[[temp.deduct.call]]），代入返回类型得到指向引用的指针 `int&*`，这个类型不存在。但程序没有报错：#1 只是推导失败、退出了候选，调用落到 #2 上。

这种行为常被称为 [[g:sfinae|**SFINAE**]]，即 Substitution Failure Is Not An Error（代入失败不是错误）。这个缩写出自 *C++ Templates* 一书，标准本身不用它。推导失败的模板不提供候选函数，这一后果规定在 [[temp.over]]。

失败的不一定是类型，也可以是表达式：

```cpp run ok
struct X { };
struct Y { Y(X) { } };

template <class T> auto f(T t1, T t2) -> decltype(t1 + t2);   // #1
X f(Y, Y);                                                    // #2

X x1, x2;
X x3 = f(x1, x2);   // #1 推导失败（X + X 无效），调用 #2

int main() { }
```

`decltype(t1 + t2)` 把支持 `+` 这一要求写进了签名。这是 C++11 引入的**表达式 SFINAE**（[[N2634]]），在此之前只有类型的失败（如 `typename T::type`）才能可靠地算作推导失败。C++20 起，同样的要求通常用约束（[[temp.constr]]）表达。

### 哪些位置会代入（¶7）

¶7 定义了[[g:deduction-substitution-loci|**推导代入位置**]]（deduction substitution loci），即推导时要做代入的地方：

- ¶7.1 函数类型，但不含 *noexcept-specifier*；
- ¶7.2 *explicit-specifier*（`explicit(bool)`）；
- ¶7.3 模板形参的声明；
- ¶7.4 部分特化的模板实参列表（[[temp.spec.partial.general]]）。

代入发生在这些位置用到的所有类型和表达式中，既包括数组界、常量模板实参这样的常量表达式，也包括 `sizeof`、`decltype` 里的一般表达式。

注 4 指出，异常说明和函数契约断言不在这些位置里。它们只在被实例化时才代入，那时出错，程序就是非良构的：

```cpp error
template<class T> void f(T) noexcept(T::value);
void f(...);
void t() { f(0); }   // error: 选中模板后实例化 noexcept，int::value 无效
```

### 只有直接语境中的错误才是推导失败（¶8）

¶8 代入产生无效的类型或表达式时，推导失败。无效指的是：用代入后的实参在同一处直接写出来，会是要求诊断的非良构代码。注 5 补充，访问检查也是代入的一部分。

但这条规则有范围限制：只有出现在推导代入位置的[[g:immediate-context|**直接语境**]]（immediate context）中的无效类型和表达式，才导致推导失败。直接语境就是推导代入位置本身，不包括其中 lambda 表达式的函数体，也不包括[[g:separately-instantiated-construct|单独实例化的构造]]（比如类模板特化、默认实参）。

```cpp error
template<class T> struct Wrap { using type = typename T::value_type; };

template<class T> typename Wrap<T>::type first(T);   // #1
template<class T> void first(...);                   // #2

void t() { first<int>(0); }   // error: 错误在 Wrap<int> 的类体里
```

代入 `Wrap<int>::type` 要先实例化 `Wrap<int>`，`int::value_type` 的错误发生在类模板的实例化里。注 6、注 7 说明，代入引发的这类效果（实例化模板特化、生成隐式定义的函数等）不在直接语境中，其中的错误会让程序非良构。

所以 `Wrap` 本身要能妥善处理没有 `value_type` 的类型，比如用一个受约束的部分特化，只在合法时才提供 `type`：

```cpp ok
template<class T> struct Safe { };                                    // 没有 type
template<class T> requires requires { typename T::value_type; }
struct Safe<T> { using type = typename T::value_type; };

template<class T> typename Safe<T>::type first(T);   // #1
template<class T> void first(...);                   // #2

void t() { first<int>(0); }   // OK：Safe<int> 合法地没有 type，调用 #2
```

标准库 trait 就是这样做到 SFINAE 友好的：`std::common_type<A, B>`、`std::invoke_result<F, Args...>` 无解时只是没有 `type` 成员，而不是在类体里报错。

访问检查属于代入，所以访问失败也是推导失败：

```cpp ok
class P { using secret = int; };                             // 私有

template<class T> auto probe(T*) -> typename T::secret;      // 访问失败：推导失败
template<class T> char probe(...);

static_assert(sizeof(probe<P>(nullptr)) == 1);               // 选了 probe(...)
```

### 语句不在直接语境中（¶9）

¶9 注 8 指出，任何语句都不在直接语境中。C++20 起 lambda 可以出现在不求值操作数里（[[P0315R4]]），签名中于是可以出现 lambda，而 lambda 的函数体由语句组成：

```cpp
template <class T>
    auto f(T) -> decltype([]() { T::invalid; } ());
void f(...);
f(0);              // error：lambda 函数体里的错误不在直接语境中

template <class T, std::size_t = sizeof([]() { T::invalid; })>
    void g(T);
void g(...);
g(0);              // error：同上

template <class T>
    auto h(T) -> decltype([x = T::invalid]() { });
void h(...);
h(0);              // OK：init-capture 的初始化器在直接语境中，调用 h(...)

template <class T>
    auto i(T) -> decltype([]() -> typename T::invalid { });
void i(...);
i(0);              // OK：lambda 的返回类型在直接语境中，调用 i(...)

template <class T>
    auto j(T t) -> decltype([](auto x) -> decltype(x.invalid) { } (t));
void j(...);
j(0);              // OK：泛型 lambda 的返回类型推导失败，调用表达式无效，调用 j(...)
```

lambda 的声明部分（捕获的初始化器、形参、返回类型）在直接语境中，函数体不在。本机 Clang 23 对 `f(0)`、`g(0)` 报错，其余三个调用都能编译。

### 代入按词法顺序进行（¶7）

!!! std
    The substitution proceeds in lexical order and stops when a condition that causes deduction to fail is encountered.

代入按源码中出现的先后进行，遇到导致推导失败的情况就停下。规定顺序，是因为代入可能触发实例化，而实例化可能产生硬错误。先遇到的失败，能让后面的部分免于代入：

```cpp
template <class T> struct A { using X = typename T::X; };

template <class T> typename T::X f(typename A<T>::X);
template <class T> void f(...) { }

template <class T> auto g(typename A<T>::X) -> typename T::X;
template <class T> void g(...) { }

void x() {
    f<int>(0);    // OK：先代入返回类型 int::X，失败，停止
    g<int>(0);    // error：先代入形参类型，实例化 A<int>，其中 int::X 是硬错误
}
```

`f` 和 `g` 唯一的区别是返回类型写在前面还是后面：尾置返回类型在词法上位于形参之后。`f<int>` 在返回类型处就失败了，`A<int>` 从未实例化。本机 Clang 23 只对 `g<int>(0)` 报错。

¶7 最后一句：如果对同一个函数模板的不同声明做代入，会导致模板实例化以不同的顺序发生或者根本不发生，程序 IFNDR（非良构，不要求诊断）。例如把上面的两种写法用作同一个模板 `h` 的两次声明，`h<int>(0)` 就属于这种情况。

这个顺序规则由 [[CWG1227]] 作为 C++14 的缺陷报告明确下来。此前标准只说代入发生在所有类型和表达式中，各编译器的顺序不一。

### 推导失败的常见原因（¶11–¶12）

¶11 注 9 列出了推导失败的常见原因。这只是一个不完整的提示列表，规范性的规则只有 ¶8 那一条。

| ¶ | 原因 | 例子 |
|---|---|---|
| 11.1 | 展开含多个包的包展开，而包的长度不同 | `pair<A, B>...`，`A`、`B` 不等长 |
| 11.2 | 创建元素为 `void`、函数或引用的数组，或大小为零或负数的数组 | `template<class T> int f(T[5]); f<void>(0);` |
| 11.3 | 在限定名中使用非类、非枚举类型 | `template<class T> int f(typename T::B*); f<int>(0);` |
| 11.4 | 限定名里的类型没有该成员，或成员的种类不对 | 见下 |
| 11.5 | 创建指向引用的指针 | `T*`，`T = int&` |
| 11.6 | 创建对 `void` 的引用 | `T&`，`T = void` |
| 11.7 | `T` 不是类类型时创建指向 `T` 成员的指针 | `template<class T> int f(int T::*); f<int>(0);` |
| 11.8 | 给常量模板形参无效的类型 | 用非结构化类型的值作常量模板实参 |
| 11.9 | 模板实参表达式或函数声明中的表达式做了无效转换 | `template<class T, T*> int f(int); f<int, 1>(0);` |
| 11.10 | 创建形参为 `void`、或返回函数或数组的函数类型 | `T(int)`，`T = int[3]` |
| 11.11 | 给 lambda 调用运算符的显式对象形参不允许的类型 | — |

¶11.4 的几种情形：

```cpp ok
template <int I> struct X { };
template <template <class T> class> struct Z { };
template <class T> void f(typename T::Y*) { }
template <class T> void g(X<T::N>*) { }
template <class T> void h(Z<T::template TT>*) { }
template <class T> void f(...) { }
template <class T> void g(...) { }
template <class T> void h(...) { }

struct A { };
struct B { int Y; };
struct C { typedef int N; };
struct D { typedef int TT; };

int main() {        // 每一行第一个模板都推导失败，调用 (...) 版本
    f<A>(0);        // A 没有成员 Y
    f<B>(0);        // B::Y 不是类型
    g<C>(0);        // C::N 不是值
    h<D>(0);        // D::TT 不是模板
}
```

标准原文把 `h` 的形参写作 `Z<T::TT>*`，本机 Clang 23 要求加上 `template` 消歧义，这里照此改写。

¶12 常量模板实参需要窄化转换时，代入也会失败：

```cpp
template <int> int f(int);
template <signed char> int f(int);
int i1 = f<1000>(0);    // OK：1000 转 signed char 是窄化，第二个模板推导失败
int i2 = f<1>(0);       // error: 二义，1 不需要窄化，两个模板都可行
```

这里假定 `signed char` 表示不了 1000。

## 取函数模板的地址（[temp.deduct.funcaddr]）

```cpp ok
template<class T> T twice(T x) { return x + x; }
int    (*pf)(int)    = twice;       // T = int：从目标类型推导
double (*pd)(double) = &twice;      // T = double
auto pa = &twice<long>;             // 没有目标类型：只能显式指定
void take(int (*)(int));
void use() { take(twice); }         // 目标是形参类型
```

¶1 取一个重载集（其中有函数模板）的地址时，可以从目标类型推导模板实参。目标类型是被初始化的指针或引用、被赋值的左操作数、函数形参、转型的目标类型等（[[over.over]]）。有目标时，以函数模板的函数类型为 `P`、目标类型为 `A`，按 [[temp.deduct.type]] 推导。没有目标时，`P` 和 `A` 都是空集，模板实参只能来自显式实参和默认值：

```cpp error
template<class T> T twice(T x) { return x + x; }
auto pa = &twice;                   // error: 没有目标，T 无法推导
```

¶2 函数模板返回类型里的占位类型（`auto`）是非推导语境。推导成功后，返回类型由实例化函数体确定：

```cpp ok
template<class T> auto ret(T x) { return x; }
int (*pr)(int) = ret;   // T 从形参推导为 int；返回类型实例化后为 int
```

## 转换函数模板（[temp.deduct.conv]）

```cpp run ok
#include <cstdio>
struct Any {
    template<class T> operator T() const { std::puts("operator T"); return T(); }
};
struct Ref {
    template<class T> operator T&() { static T t{}; std::puts("operator T&"); return t; }
};

int main() {
    Any a;
    int x = a;            // T = int
    double d = a;         // T = double
    Ref r;
    int y = r;            // P = T&，¶2：用 T 比较，T = int
    const int& cy = r;    // A = const int&，¶4：用 const int 比较，T = const int
    (void)x; (void)d; (void)y; (void)cy;
}
```

¶1 推导转换函数模板 `operator T()` 的模板实参时，以它的返回类型为 `P`，以需要转换到的类型为 `A`，按 [[temp.deduct.type]] 进行。如果这个转换函数是在重载决议中被考虑的（[[over.match.funcs]]），比较之前还要做下面的调整。它们和调用推导中的调整方向相反：调用时 `P` 是形参、`A` 是实参；这里 `P` 是转换产出的类型，`A` 是需要的类型。

| ¶ | 调整 |
|---|---|
| 2 | `P` 是引用类型：用它引用的类型代替 `P` |
| 3 | `A` 不是引用类型时：`P` 是数组则换成指针，是函数则换成函数指针，否则去掉 `P` 的顶层 cv |
| 4 | 去掉 `A` 的顶层 cv；`A` 是引用类型时，用它引用的类型 |
| 5 | 推导出的 `A` 一般要与 `A` 相同。推导本会失败时，可以忽略三种差异：原 `A` 是引用时被引用类型的 cv（5.1）；原 `A` 是可能抛出的函数指针或成员函数指针时的异常说明（5.2）；可以由限定转换恢复的 cv（5.3）。忽略之后若有多种可能，推导失败 |

像 `Any` 这样能转换成任何类型的类，会让大量重载决议变得二义，实际代码中应当避免。

## 偏序中的推导（[temp.deduct.partial]）

两个函数模板都能匹配一次调用时，[[g:partial-ordering|偏序]]（partial ordering，[[temp.func.order]]）决定哪一个更特殊。偏序还用于确定显式特化、显式实例化属于哪个模板（[[temp.deduct.decl]]），以及取重载函数模板的地址。[[temp.func.order]] 规定怎样把模板变换成一个具体的形式：每个模板形参换成一个独有的合成类型、值或模板。本节规定变换之后怎样推导。

```cpp run ok
#include <cstdio>
template<class... Args>           void f(Args...)     { std::puts("#1"); }
template<class T1, class... Args> void f(T1, Args...) { std::puts("#2"); }
template<class T1, class T2>      void f(T1, T2)      { std::puts("#3"); }

int main() {
    f();          // #1：只有 #1 可行
    f(1, 2, 3);   // #2：#2 比 #1 更特殊
    f(1, 2);      // #3：不变参的 #3 比变参的 #1、#2 更特殊
}
```

### 双向推导（¶1–¶4、¶8、¶10）

¶2 每个模板都有原始的函数类型和变换后的函数类型。以一个模板的变换形式为实参模板、另一个模板的原始形式为形参模板做推导，再交换角色做一次。

直观地说，偏序要回答：模板 1 能接受的每一种实参，模板 2 是否也都能接受？如果用模板 1 的任意实例都能推导出模板 2，模板 2 至少和模板 1 一样通用，也就是模板 1 至少和模板 2 一样特殊。

¶3 拿来比较的类型取决于场合：

- ¶3.1 函数调用：有对应实参的那些函数形参的类型。默认实参不算实参（脚注 112），它们只在函数选定之后才成为实参；
- ¶3.2 调用转换函数：转换函数模板的返回类型；
- ¶3.3 其他场合：整个函数类型。

¶4 形参模板的每个类型与实参模板中对应的类型，分别作为 `P` 和 `A`。

¶8 如果 `A` 来自函数形参包而 `P` 不是包，推导失败。否则按 [[temp.deduct.type]] 推导；`P` 是函数形参包时，它与实参模板中剩下的每个形参类型逐一比较。对某个类型推导成功，就说实参模板的这个类型至少与形参模板的对应类型一样特殊。

¶10 如果用于定序的每一对类型中，`F` 的类型都至少与 `G` 的一样特殊，就说 `F` [[g:at-least-as-specialized|**至少与 `G` 一样特殊**]]（at least as specialized as）。`F` 至少与 `G` 一样特殊而反过来不成立时，`F` **比 `G` 更特殊**（more specialized）。

### 比较前的调整和引用的决胜（¶5–¶7、¶9）

比较之前，`P` 和 `A` 先做这些调整：

- ¶5 是引用类型的，换成它引用的类型；
- ¶6 如果 `P` 和 `A` 原来都是引用，记下哪一个 cv 限定更多，留给 ¶9 用；
- ¶7 去掉两者的顶层 cv。

¶9 如果调整后两个类型完全相同，并且 `P`、`A` 原来都是引用，还要再比两点：实参模板中是左值引用而形参模板中不是时，形参类型不算至少一样特殊（¶9.1）；否则，实参模板中的类型 cv 限定更多时，形参类型也不算至少一样特殊（¶9.2）。

```cpp run ok
#include <cstdio>
template<class T> void q(T&&) { std::puts("q(T&&)"); }
template<class T> void q(T&)  { std::puts("q(T&)"); }

int main() {
    int i = 0;
    q(i);    // q(T&)：两个都推导出 q(int&)，¶9.1 判 T& 更特殊
    q(0);    // q(T&&)：q(T&) 不可行
}
```

### 尾随包和用不到的形参（¶11–¶13）

¶11 如果按上面的方法 `F` 与 `G` 互相至少一样特殊，而 `G` 有一个尾随函数形参包、`F` 中没有形参与之对应，`F` 也没有尾随函数形参包，那么 `F` 更特殊。这处理的是只有一个实参时 `f(T)` 与 `f(T, Args...)` 的比较：那个包没有对应的实参，在 ¶3.1 的比较里不出现。

¶12 一般来说，有模板形参没有值时推导失败。但在偏序中，一个模板形参只要不出现在用于定序的类型里，就可以没有值。注 2 说明，出现在非推导语境中也算出现。

```cpp ok
template <class T> T f(int);            // #1
template <class T, class U> T f(U);     // #2
void g() {
    f<int>(1);                          // 调用 #1
}
```

两个都可行，用于定序的只有有实参的形参类型：#1 是 `int`，#2 是 `U`。用 #1 的 `int` 推导 #2 的 `U`，成功，`T` 不出现在比较的类型里，不需要值。反过来用合成类型推导 #1 的 `int`，失败。所以 #1 更特殊。

¶13 注 3 指出，含模板形参包的函数模板的偏序，与包推导出了几个实参无关：

```cpp run ok
#include <cstdio>
template<class...> struct Tuple { };
template<class... Types>           void g(Tuple<Types...>)      { std::puts("#1"); }
template<class T1, class... Types> void g(Tuple<T1, Types...>)  { std::puts("#2"); }
template<class T1, class... Types> void g(Tuple<T1, Types&...>) { std::puts("#3"); }

int main() {
    g(Tuple<>());              // #1
    g(Tuple<int, float>());    // #2
    g(Tuple<int, float&>());   // #3
    g(Tuple<int>());           // #3：Types 为空，#2、#3 都匹配，#3 更特殊
}
```

最后一行中，`Types&...` 和 `Types...` 都推导为空包，看起来没有区别。但偏序比较的是模式而不是推出了几个元素，`Types&...` 比 `Types...` 更特殊。

## 从函数声明推导（[temp.deduct.decl]）

```cpp ok
template<class T> void f(T) { }      // #1
template<class T> void f(T*) { }     // #2
template<> void f(int*) { }          // 两个都匹配，#2 更特殊：这是 #2 的 f<int>
template void f(double*);            // 同理：实例化 #2 的 f<double>
```

¶1 如果一个声明的 *declarator-id* 指的是某个函数模板特化，就要通过推导确定它指的是哪个特化。这用于显式实例化、显式特化和一部分友元声明，也用于判断一个解分配函数模板的特化是否与某个放置分配函数相配（[[basic.stc.dynamic.deallocation]]、[[expr.new]]）。`P` 是候选函数模板的类型，`A` 是声明中的函数类型（或者与放置分配函数相配的解分配函数类型），按 [[temp.deduct.type]] 推导。

¶2 在考虑偏序之后，如果一个匹配的模板都没有，或者有不止一个，推导失败；在声明中，程序非良构：

```cpp error
template<class T> void f(T, int);
template<class T> void f(int, T);
template<> void f(int, int);   // error: 两个模板都匹配，偏序分不出高下
```

特化属于哪个模板，取决于声明时哪些模板可见。[[temp.expl.spec]] 中特化位置改变调用结果的例子就是这个机制造成的。

[[temp.deduct.type#10]] 对这里的推导有一条特殊调整：顶层形参是转发引用 `T&&`、而 `A` 是左值引用时，把 `P` 当作 `T`。于是 `template<> void f(int&)` 能被识别为 `template<class T> void f(T&&)` 的 `f<int&>`。

## 实现视角

!!! impl "编译器怎样实现 SFINAE"
    - 编译器在代入期间捕获诊断：直接语境中产生的错误不输出，而是转成推导失败（Clang 内部称为 SFINAE trap）。一旦开始实例化类模板、生成隐式成员这类非直接语境的工作，捕获暂停，诊断照常输出。这正对应 ¶8 的注 6、注 7。
    - 报没有匹配的函数时，编译器会在附注里列出被剔除的候选及原因（Clang 写作 substitution failure），这是调试 SFINAE 的主要手段。
    - 大量基于 `std::enable_if` 的重载代价很高，每个候选都要完整代入一次。约束在 ¶5 的约束检查那一步就能淘汰候选，满足性的结果还会被缓存，通常更快，诊断也更清楚。

## 常见误解

!!! pitfall "写在签名里就在直接语境中"
    `typename Wrap<T>::type` 写在签名里，错误却发生在 `Wrap<T>` 的类体里，不在直接语境中，是硬错误。同样，`decltype(T{})` 中如果 `T` 的默认构造函数是隐式定义的，而它的定义非良构（例如某个成员不能默认构造），隐式定义的生成也不在直接语境中。

!!! pitfall "`auto` 返回类型参与 SFINAE"
    `template<class T> auto size_of(const T& c) { return c.size(); }` 的返回类型要实例化函数体才能得到，而函数体不在直接语境中。用不合适的类型调用它会在实例化函数体时报硬错误。需要 SFINAE 时写 `-> decltype(c.size())`，或者用约束。

## 思考题

!!! question "思考题 1"
    以下哪些调用会导致硬错误？
    ```cpp
    template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };
    template<class T> typename Bad<T>::type a(T);     void a(...);
    template<class T> decltype(Bad<T>{}) b(T);        void b(...);
    template<class T, class = typename T::type> void c(T); void c(...);
    void t() { a(1); b(1); c(1); }
    ```

<details markdown="1">
<summary>答案</summary>

`a(1)`：代入 `Bad<int>::type` 要实例化 `Bad<int>`，类体里的 `static_assert` 失败，不在直接语境中，是硬错误。

`b(1)`：`Bad<int>{}` 需要完整类型，同样要实例化 `Bad<int>`，是硬错误。

`c(1)`：`int::type` 直接写在模板形参列表里（¶7.3 的代入位置），属于在限定名中使用非类类型（¶11.3），推导失败，调用 `c(...)`，没有错误。

本机 Clang 23 分别编译三个调用，结果与此一致。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> void f(T*, const T&);   // #1
    template<class T> void f(T, T&);          // #2
    ```
    `int i; f(&i, i);` 调用哪一个？

<details markdown="1">
<summary>答案</summary>

调用 #1。#1 推导出 `T = int`，形参为 `(int*, const int&)`。#2 从第一个实参推导出 `T = int*`，从第二个推导出 `T = int`，冲突，推导失败。只剩 #1 可行，根本轮不到偏序。偏序只在两个模板都推导成功时才起作用。
</details>
