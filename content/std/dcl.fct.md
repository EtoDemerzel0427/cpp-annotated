---
title: 函数声明符
summary: 函数类型由哪些部分组成，形参类型怎样调整，以及省略号、显式对象形参、带 cv/ref 限定的函数类型和简写函数模板的规则。
status: draft
since: c++98
papers: P0012R1, P0847R7, P3176R1
related: dcl.decl, dcl.fct.default, dcl.fct.def, over.match.funcs, expr.call, except.spec, conv.fctptr, dcl.spec.auto, temp.variadic, expr.prim.lambda, depr.ellipsis.comma
tags: 函数类型, 形参, noexcept, deducing this, 简写函数模板
updated: 2026-10-19
---

!!! tldr
    - 函数类型由返回类型、调整后的形参类型列表（含有无省略号）、cv 限定、引用限定和 `noexcept` 组成。默认实参、requires 子句、契约和形参名都不属于类型。
    - 形参类型进入函数类型前要调整：数组和函数变成指针，顶层 cv 被删掉。所以 `f(int)` 和 `f(const int)` 是同一个函数。
    - `void f(int...)` 是 C 风格可变参数函数，不是形参包，这种不带逗号的写法 C++26 起弃用。
    - 显式对象形参 `this Self&& self`（C++23）只能是成员函数的第一个形参，函数不能再带 cv/ref 限定，也不能是 `static` 或 `virtual`。
    - `int() const` 这样的函数类型只能用来声明成员函数、构成成员指针、写在 typedef 里或当模板实参，不能形成普通指针或引用。

## 函数类型由什么组成（¶1、¶13）

```cpp run title="fn-type-parts.cpp" ok
#include <type_traits>

// 返回类型上的 const 也算（Clang 警告它没有效果）
static_assert(!std::is_same_v<const int(), int()>);
// noexcept 属于类型（C++17 起）
static_assert(!std::is_same_v<void() noexcept, void()>);

void nf() noexcept {}
void (*pf)() = nf;   // OK：可以丢掉 noexcept（[conv.fctptr]）
// void (*pnf)() noexcept = pf;  // error: 不能凭空加上 noexcept

int main() {}
```

¶13 函数类型包含返回类型、形参类型列表、引用限定符、cv 限定符序列和异常规格。默认实参（[[dcl.fct.default]]）和尾置 requires 子句不属于函数类型。注 6 说明，用函数初始化或赋值给函数指针、函数引用、成员函数指针时，检查的就是这个类型。

| 组成部分 | 例子 | 属于函数类型？ |
|---|---|---|
| 返回类型（包括它的 cv） | `int` 与 `const int` | 是 |
| 形参类型列表（调整后） | `(int, char*)` | 是 |
| 有无省略号 | `(int, ...)` | 是 |
| cv 限定 | `() const` | 是 |
| 引用限定 | `() &&` | 是 |
| 异常规格 | `noexcept` | 是，C++17 起 |
| 默认实参 | `(int = 0)` | 否 |
| 尾置 requires 子句 | `requires C<T>` | 否 |
| 契约说明符 | `pre(x > 0)` | 否（[[dcl.contract]]） |
| 形参名 | `(int x)` | 否 |

由此可以推出几件常用的事：

- 默认实参不随函数指针传递。`int f(int = 0);` 之后，`int (*p)() = &f;` 非良构，因为 `f` 的类型是 `int(int)`。
- 同一函数的各个声明必须有兼容的异常规格，也不能只靠 `noexcept` 区分重载（[[except.spec]]）。
- 模板可以从函数指针类型中推导 `noexcept`：`template<bool NE> void g(void(*)() noexcept(NE));`。
- requires 子句虽然不在类型里，两个只有约束不同的函数模板声明仍然不对应（[[basic.scope.scope]]），是两个不同的模板。

```cpp title="noexcept-redecl.cpp" error
void ne() noexcept;
void ne();              // error: 缺少 noexcept
void ov(int) noexcept;
void ov(int);           // error: 不能只靠 noexcept 重载
```

¶1 给出了函数声明符的形式。在声明 `T D` 中，如果 `D` 形如 `D1 ( 形参声明子句 ) cv ref noexcept 属性 尾置返回类型`，那么 `D` 声明的是函数，其类型是"函数（形参类型列表）cv ref，返回 `U`"，异常规格不抛出（[[except.spec]]）时再加上 `noexcept`。返回类型 `U` 按下面的方法确定：

- 有尾置返回类型时，`T` 必须恰好是 `auto`，`U` 就是尾置返回类型（¶1.3）；
- 转换函数 `operator int()` 的返回类型由名字决定，见 [[class.conv.fct]]（¶1.1、¶1.4）；
- 其他情况下 `U` 就是 `T`（¶1.5）。

末尾的属性属于函数类型。形参前的属性属于该形参（第 2 段）。

## 形参类型的调整（¶5）

```cpp title="param-adjust.cpp" error
void f(char*);              // #1
void f(char[]) {}           // 定义 #1：char[] → char*
void f(const char*) {}      // OK：另一个重载
void f(char* const) {}      // error: 重定义 #1

void g(char(*)[2]);         // #2
void g(char[3][2]) {}       // 定义 #2：只调整最外层
void g(char[3][3]) {}       // OK：另一个重载

void h(int x(const int));   // #3：函数 → 函数指针
void h(int (*)(int)) {}     // 定义 #3
```

¶5 函数的类型按三步确定：

1. 每个形参（包括函数形参包）的类型由它自己的声明确定；
2. 类型为"`T` 的数组"或函数类型 `T` 的形参，**调整**为"指向 `T` 的指针"；
3. 删去每个形参类型的顶层 cv 限定符。

得到的类型列表，加上有无省略号或函数形参包，就是函数的**形参类型列表**（parameter-type-list）。两个声明是不是同一个函数、函数指针能否匹配，比较的都是它。

这三步各有原因。数组和函数都不能按值传递，`f(char[])` 在 C 里就一直表示传指针，代价是丢掉了长度。顶层 const 只决定函数体能否修改自己的形参副本，调用者看不出区别；如果它属于类型，`f(int)` 和 `f(const int)` 就成了调用时无法区分的两个重载。

注 3 指出，调整只影响函数类型，不改变形参本身的类型。在函数体内 `const int x` 仍然是 const 的：

```cpp run title="adjust-not-param.cpp" ok
#include <type_traits>

void f(const int x) {
  // 形参本身仍是 const
  static_assert(std::is_same_v<decltype(x), const int>);
}
void f(int);   // 同一个函数的重声明

// 第二个形参里的 const 不在顶层，保留
static_assert(std::is_same_v<int(*)(const int p, decltype(p)*),
                             int(*)(int, const int*)>);
int main() { f(1); }
```

所以常见的写法是在头文件里声明 `void set(int v);`，在源文件里定义 `void set(const int v) { … }`，防止函数体误改形参。

## 形参列表

### 空列表与 `(void)`（¶3）

¶3 形参声明子句决定调用时可以传哪些实参，以及它们怎样转换成形参（[[expr.call]]）。子句为空时，函数不接受实参。C 里 `int f();` 曾表示形参未指定，C23 才与 C++ 一致。

只有一个无名形参、类型与 `void` 相同时，也表示空形参列表。除此之外，形参不能是 cv `void` 类型：

```cpp title="void-param.cpp" error
using V = void;
void g0(V);          // OK：零个形参
void p(void, int);   // error: void 必须是唯一的形参
void q(void x);      // error: void 形参不能有名字

template<class T> struct S3 { void f(T); };
S3<void> z;          // error: f 有一个 void 类型的形参
```

最后一行说明，模板实例化时替换出来的 `void` 不会把形参列表变成空的。标准例 1 进一步区分了依赖类型和非依赖类型：

```cpp title="void-t-param.cpp"
#include <type_traits>
template<class T>
struct S  { void f(std::void_t<T*>); };    // 依赖于 T
S<int> x;            // 按标准：error，f 有 void 形参

template<class T>
struct S2 { void f(std::void_t<int*>); };  // 不依赖 T
S2<int> y;           // OK：f 没有形参
```

`std::void_t<int*>` 在声明时就是 `void`，所以 `S2::f` 一开始就是零形参函数。`std::void_t<T*>` 要等实例化才知道是 `void`，那时它已经是一个形参了。本机 Clang 23 接受 `S<int>`，并允许以 `x.f()` 无实参调用，与标准不一致。

volatile 限定的形参类型已弃用（[[depr.volatile.type]]）。

### 省略号（¶4、¶6、¶27）

¶4 形参声明子句以省略号或函数形参包结尾时，实参个数不能少于既没有默认实参、也不是形参包的形参个数。¶6 形参类型列表带省略号的函数叫**可变参数函数**（vararg function），`printf` 是典型例子。传给省略号的实参先经过默认实参提升（[[expr.call]]），在函数里用 `<cstdarg>` 的 `va_start`、`va_arg` 读取：

```cpp run title="vararg.cpp" ok
#include <cstdarg>

int sum(int n, ...) {
  std::va_list ap;
  va_start(ap, n);
  int s = 0;
  for (int i = 0; i < n; ++i) s += va_arg(ap, int);
  va_end(ap);
  return s;
}
void all(...) {}   // C++ 一直允许只有省略号；C 到 C23 才允许

int main() {
  all(1, "two", 3.0);
  return sum(3, 1, 2, 3) == 6 ? 0 : 1;
}
```

在语法上说得通的地方，`...` 与 `, ...` 同义。问题在于不加逗号时，`...` 也可能是在声明形参包。第 27 段这样消除歧义：如果形参类型命名了一个还没展开的模板形参包，或者含有 `auto`，`...` 就属于这个形参，声明函数形参包；否则它是 C 风格的省略号。

```cpp title="ellipsis-ambig.cpp" ok
template<class... T> void a(T...); // 形参包
template<class T>    void b(T...); // b(T, ...)，已弃用
void c(auto...);                   // 形参包
void d(int...);                    // d(int, ...)，已弃用
int main() {}
```

`b` 和 `d` 看起来像形参包，实际上是可变参数函数。C++26 因此弃用了不带逗号的省略号（第 4 段末句，[[depr.ellipsis.comma]]，[[P3176R1]]），新代码一律写 `, ...`。本机 Clang 23 对 `b`、`d` 发出 `-Wdeprecated-missing-comma-variadic-parameter` 警告。

### 函数形参包（¶26）

¶26 声明符里带 `...` 的只能是形参声明。它出现在函数的形参声明子句里时声明**函数形参包**，出现在模板形参列表里时声明模板形参包（[[temp.param]]）。函数形参包本身是一个包展开（[[temp.variadic]]）。

```cpp run title="fn-param-pack.cpp" ok
// t 是函数指针的包
template<typename... T>
void f(T (* ...t)(int, int)) { (void)sizeof...(t); }

int add(int, int) { return 0; }
float subtract(int, int) { return 0; }
int main() { f(add, subtract); }   // T = {int, float}
```

## 返回类型与函数定义的限制（¶16–19）

¶16 返回类型必须是非数组的对象类型、引用类型或 cv `void`。函数不能返回数组或函数，但可以返回指向它们的指针或引用。注 8 说明，占位符类型的数组也算数组类型。

¶18 不能在返回类型或形参类型中定义新类型。C 允许在形参里定义结构体，但这样定义的类型只在原型内可见，几乎没有用处。

```cpp title="return-type.cpp" error
int arr()[3];             // error: 不能返回数组
int fn()();               // error: 不能返回函数
auto ok() -> int(*)[3];   // OK：返回指向数组的指针
auto ok2() -> int(&)();   // OK：返回函数引用

struct A { virtual void f() = 0; };
A g();                    // OK：只是声明，不检查抽象类

void def(struct S {} s);  // error: 在形参类型中定义类型
struct S2 {} ret();       // error: 在返回类型中定义类型
```

返回抽象类的函数可以声明，C++20 起只在定义和调用处检查。

¶17 volatile 限定的返回类型已弃用（[[depr.volatile.type]]）。

¶19 函数类型的 typedef 可以用来声明函数，但不能用来定义函数，因为 typedef 里没有形参名：

```cpp title="typedef-fn.cpp" error
typedef void F();
F fv;            // OK：等价于 void fv();
F fv {}          // error: 不能用 typedef 定义函数
void fv() {}     // OK：fv 的定义
```

## 显式对象形参 {{c++23}}（¶7–10）

普通的非静态成员函数有一个隐含的形参，代表调用它的对象，重载决议把它叫做**隐式对象形参**（[[g:implicit-object-parameter|implicit object parameter]]，[[over.match.funcs]]）。函数后面的 `const`、`&`、`&&` 描述的就是这个形参的类型。C++23 允许把它写出来：

```cpp run title="deducing-this.cpp" ok
#include <cstdio>
#include <type_traits>
#include <utility>

struct C {
  int v = 1;
  void f(this C& self) { self.v++; }   // 体内没有 this
  template<class Self>
  int g(this Self&& self, int k) {     // 一份代码覆盖 &、const&、&&
    return std::forward<Self>(self).v + k;
  }
};
// 取地址得到普通函数指针，不是成员函数指针
static_assert(std::is_same_v<decltype(&C::f), void (*)(C&)>);

struct Base {
  template<class Self>
  auto name(this const Self&) { return Self::tag; }
};
struct D1 : Base { static constexpr const char* tag = "D1"; };

int main() {
  C c;
  c.f();
  auto pf = &C::f;
  pf(c);                                   // 像普通函数一样调用
  std::printf("%d %d %d\n", c.v, c.g(10), std::move(c).g(20));  // 3 13 23
  std::printf("%s\n", D1{}.name());        // D1：Self 推导为 D1

  auto fib = [](this auto const& self, int n) -> int {   // 递归 lambda
    return n < 2 ? n : self(n - 1) + self(n - 2);
  };
  std::printf("%d\n", fib(10));            // 55
}
```

`Base::name` 不用 CRTP 就拿到了派生类类型；`fib` 是一个能调用自身的 lambda。

¶7 带 `this` 说明符的形参声明叫**显式对象形参声明**。它只能作为形参列表的第一个形参，并且只能出现在：

- ¶7.1 成员函数或成员函数模板的声明中；
- ¶7.2 模板化成员函数的显式实例化或显式特化中；
- ¶7.3 lambda 声明符中（[[expr.prim.lambda]]）。

带显式对象形参的成员函数不能有 cv 限定符或引用限定符，也不能声明为 `static` 或 `virtual`。文法上 `this` 和默认实参不能出现在同一个形参声明里（第 2 段），所以显式对象形参也不能有默认实参。

```cpp title="deducing-this-bad.cpp" error
struct C {
  void h(this C) const;          // error: 不能有 cv 限定
  void i(this C&) &;             // error: 不能有引用限定
  static void s(this C);         // error: 不能是 static
  virtual void v(this C&);       // error: 不能是 virtual
  void k(int, this C&);          // error: 只能是第一个形参
  template<class... Ts>
  void p(this Ts...);            // error: 不能是形参包
  void b(this C& self) {
    this->k(1, self);            // error: 体内不能用 this
  }
};
void free_fn(this int);          // error: 只能用于成员函数
```

禁止 cv 和 ref 限定，是因为对象的类型已经写在 `this` 形参上，再写一遍既多余又可能矛盾。禁止 `virtual`，是因为显式对象形参常常是模板（`this Self&&`），而函数模板不能是虚函数；即使不是模板，对象参数也可以按值传递，与虚调用的机制不相容。函数体里不能使用 `this` 由 [[expr.prim.this]] 规定。

¶8–10 定义了几个名词：

- 用显式对象形参声明引入的形参叫**显式对象形参**（[[g:explicit-object-parameter|explicit object parameter]]），它不能是函数形参包；
- 有显式对象形参的非静态成员函数叫**显式对象成员函数**，没有的叫**隐式对象成员函数**；
- 两者合称**对象参数**（[[g:object-parameter|object parameter]]）；
- 其余形参都是**非对象参数**，它们调整后的类型组成**非对象形参类型列表**。比较两个成员函数的签名时用的就是它（[[basic.scope.scope]]）。

## 带 cv 或 ref 限定的函数类型（¶11–12）

`int(int) const`、`void() &&` 这样的类型确实存在，它就是 `const` 成员函数去掉所属类之后的类型。这类类型常被称为可憎函数类型（abominable function types），因为它几乎在哪里都不能用。

¶11 这样的函数类型，包括通过 typedef 名得到的，只能出现在：

- ¶11.1 非静态成员函数的类型；
- ¶11.2 成员指针所指的函数类型，如 `int (S::*)(int) const`；
- ¶11.3 函数 typedef 或别名声明的顶层类型，如 `using F = int(int) const;`；
- ¶11.4 类型模板形参的默认实参；
- ¶11.5 类型模板形参的模板实参，如 `std::is_function<int() const>`；
- ¶11.6 {{c++26}} 反射表达式 `^^` 的操作数。

```cpp title="abominable.cpp" error
#include <type_traits>
typedef int FIC(int) const;
FIC f;                // error: 不是成员函数
FIC* pf;              // error: 不能形成普通指针
struct S {
  FIC f;              // OK：声明 int f(int) const
};
FIC S::*pm = &S::f;   // OK：成员指针
static_assert(std::is_function_v<FIC>);  // OK：模板实参
```

元编程里需要逐一匹配这些形式，所以 `std::is_function` 的朴素实现要写 48 个偏特化：cv 的 4 种 × 引用限定的 3 种 × noexcept 的 2 种 × 有无省略号的 2 种。

¶12 函数声明符里的 cv 限定，与在函数类型外面加 cv 是两回事，后者直接被忽略。注 5 说明，带 cv 限定符序列的函数类型并不是 cv 限定类型，C++ 里不存在 cv 限定的函数类型。

```cpp title="const-fn-typedef.cpp" ok
#include <type_traits>
typedef void F();
struct S {
  const F f;     // 等价于 void f();，不是 void f() const
};
void S::f() {}
static_assert(std::is_same_v<decltype(&S::f), void (S::*)()>);
int main() {}
```

本机 Clang 23 对 `const F f;` 给出警告，说 const 没有效果。

## 简写函数模板 {{c++20}}（¶22–25）

```cpp run title="abbrev.cpp" ok
#include <concepts>
#include <type_traits>

void g1(const std::integral auto*, std::floating_point auto&);
// 等价于 template<std::integral T, std::floating_point U>
//        void g1(const T*, U&);
template<> void g1<int>(const int*, double&);   // 可以显式特化

auto sum(auto... xs) { return (xs + ... + 0); } // 引入模板形参包
static_assert(std::is_same_v<decltype(sum(1, 2L)), long>);

int main() { return sum(1, 2, 3) - 6; }
```

¶23 形参类型里含有泛型形参类型占位符（`auto` 或 `C auto`，[[dcl.spec.auto]]）的函数声明叫**简写函数模板**（[[g:abbreviated-function-template|abbreviated function template]]）。它相当于一个函数模板，每个占位符按出现顺序引入一个虚构的类型模板形参：

- `auto` 引入无约束的类型形参，`C auto` 引入带约束 `C` 的类型形参；
- 对应的形参是函数形参包时，引入的是模板形参包；
- 占位符含 `decltype(auto)` 时程序非良构。

标准说这样的声明与完整写法功能上等价但不等价（functionally equivalent but not equivalent，[[temp.over.link]]）：两种写法接受同样的调用，却不是同一个模板的两个声明，所以不能用一种写法声明、用另一种写法定义。

¶24 简写函数模板也可以带模板头，虚构的形参排在显式写出的模板形参之后：

```cpp run title="abbrev-head.cpp" ok
#include <concepts>
template<typename T, std::integral U>
void g(T, U, std::integral auto) {}
// 即 template<typename T, std::integral U, std::integral W>
//    void g(T, U, W);

int main() {
  g<double, int, long>(1.0, 2, 3L);  // 第三个实参对应 auto
}
```

¶25 块作用域里的函数声明不能声明简写函数模板，因为模板只能在命名空间或类作用域声明（[[temp.pre]]）：

```cpp title="abbrev-bad.cpp" error
void f(decltype(auto) x);      // error: 不能用 decltype(auto)
void blk() { void h(auto); }   // error: 块作用域
```

¶22 不是函数模板特化的函数叫**非模板函数**。注 11 提醒，函数模板本身不是函数。类模板的成员函数实例化后是非模板函数：它是模板化的，却不是某个函数模板的特化。重载决议在其余条件相同时优先选非模板函数（[[over.match.best]]），用的就是这个区分。

## 实现视角

!!! impl
    - 名字修饰（Itanium ABI）：顶层 cv 被删掉，所以 `f(int)` 与 `f(const int)` 都修饰为 `_Z1fi`。`noexcept` 函数类型带 `Do` 前缀，`void k(void(*)() noexcept)` 修饰为 `_Z1kPDoFvvE`。显式对象成员函数在嵌套名里多一个 `H`，`C::f(this C&)` 修饰为 `_ZNH1C1fERS_`。以上均由本机 Clang 23 输出确认。
    - C++17 把 `noexcept` 纳入类型后，以 `noexcept` 函数指针为形参的函数修饰名变了，这是少数影响 ABI 的语言改动之一。GCC 为此提供 `-Wnoexcept-type` 警告。
    - 显式对象成员函数在调用约定上就是以对象为第一个实参的普通函数。
    - 可变参数函数的调用约定与普通函数不同：x86-64 System V 用 `%al` 传递所用向量寄存器的个数；Apple 的 AArch64 平台把所有可变实参放在栈上。所以用缺少 `...` 的错误原型调用可变参数函数，在 Apple Silicon 上会得到错误结果。

## 历史与演进

!!! history
    - C++98：形参类型调整、cv 限定成员函数都已存在。动态异常规格 `throw(T)` 不属于函数类型。
    - C++11：尾置返回类型、引用限定符、`noexcept`、函数形参包。
    - C++17：`noexcept` 成为函数类型的一部分（[[P0012R1]]）；动态异常规格被移除，C++20 又移除了 `throw()`。
    - C++20：简写函数模板；volatile 形参和返回类型弃用；抽象类返回类型只在定义和调用处检查。
    - C++23：显式对象形参（[[P0847R7]]）。
    - C++26：不带逗号的省略号弃用（[[P3176R1]]）；带 cv/ref 限定的函数类型可以作为 `^^` 的操作数。

## 常见误解

!!! pitfall "`void f(int a[10])` 能保留数组长度"
    长度在调整时就丢掉了。`sizeof(a)` 是指针的大小，任何 `int*` 都能传进来。要保留长度，用 `int (&a)[10]` 或 `std::span<int, 10>`。

!!! pitfall "带默认实参的函数能当零参数函数用"
    默认实参不是类型的一部分。`f` 是 `int f(int = 0)` 时，`std::function<int()> fn = f;` 非良构。需要包一层 lambda：`[] { return f(); }`。

!!! pitfall "`int f(int...)` 是形参包"
    它是 `int f(int, ...)`，C 风格的可变参数函数，C++26 起这种写法已弃用。形参包要写成 `template<class... T> int f(T...)` 或 `int f(auto...)`。

!!! pitfall "按值的显式对象形参会修改原对象"
    `void f(this C self)` 每次调用都复制对象，函数体修改的是副本。对小型值类型这正合适，在其他场合可能是隐蔽的错误。

## 思考题

!!! question "思考题 1"
    下面哪些声明是同一个函数的重声明？
    ```cpp
    void f(int (*)[5]);
    void f(int [][5]);
    void f(int [5][5]);
    void f(int (*const)[5]);
    void f(const int (*)[5]);
    void f(int [5][6]);
    ```

<details markdown="1">
<summary>答案</summary>

前四个是同一个函数。数组形参只调整最外层，`int [][5]` 和 `int [5][5]` 都变成 `int (*)[5]`；`int (*const)[5]` 的 const 在顶层，被删掉。第五个的 const 修饰的是元素，不在顶层，所以是另一个重载。第六个调整为 `int (*)[6]`，也是另一个重载（第 5 段）。
</details>

!!! question "思考题 2"
    为什么 `struct S { void f() const; }; using T = decltype(&S::f);` 合法，而 `using U = std::remove_pointer_t<void (*)() const>;` 非良构？

<details markdown="1">
<summary>答案</summary>

`decltype(&S::f)` 是 `void (S::*)() const`，`void() const` 作为成员指针所指的类型出现，属于第 11.2 项允许的位置。`void (*)() const` 试图形成指向这种类型的普通指针，不在第 11 段的列表里。出错的是写下这个类型本身，与 `remove_pointer_t` 无关。
</details>

!!! question "思考题 3"
    有 `struct B { virtual void f(); };`。`struct D : B { void f(this B&); };` 和 `struct D2 : B { void f(this D2&); };` 分别是否良构？

<details markdown="1">
<summary>答案</summary>

派生类的成员函数如果与基类虚函数的声明对应，就覆盖它，从而成为虚函数（[[class.virtual#2]]）。两个成员函数对应，要求对象参数对应：其中恰有一个是不带引用限定的隐式对象成员函数时，比较去掉引用后的对象参数类型（[[basic.scope.scope#3]]）。

`D::f(this B&)` 的对象参数去掉引用后是 `B`，与 `B::f` 的隐式对象形参相同，于是 `D::f` 覆盖 `B::f` 成为虚函数。显式对象成员函数不能是虚函数（第 7 段），所以非良构。

`D2::f(this D2&)` 的对象参数是 `D2`，与 `B` 不同，按字面不覆盖，只是隐藏了 `B::f`，看起来应当良构。本机 Clang 23 对两者都报 "an explicit object parameter cannot appear in a virtual function"，后一种与上面的字面推理不一致。需要虚分派时，仍然应该用隐式对象成员函数。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶2 是形参声明子句的文法：可以为空，可以只有 `...`，可以是形参列表后跟 `, ...` 或（已弃用的）`...`。每个形参声明可以带属性、`this`、默认实参，但 `this` 和默认实参不能同时出现。

¶14 是例子：`int fseek(FILE*, long, int);` 声明一个接受三个实参、返回 `int` 的函数。¶15 是注：同一作用域里一个名字可以表示多个函数，这就是重载（[[over]]）。

¶20 形参名是可选的。名字出现在函数定义中时，它命名该形参。注 9 补充，定义里也可以省略形参名（常用于未使用的形参），各个声明里的形参名不必相同。

¶21 是例子，比较了 `*fpi(int)`（返回 `int*` 的函数）与 `(*pif)(const char*, const char*)`（函数指针）：前者按 `*(fpi(int))` 结合，与表达式里先调用再解引用的写法一致。注 10 建议复杂的返回类型用 typedef 或尾置返回类型来写，例如 `auto fpif(int) -> int(*)(int);`，以及返回类型依赖形参的 `auto add(T t, U u) -> decltype(t + u)`。

</details>
