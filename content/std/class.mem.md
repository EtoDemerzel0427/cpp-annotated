---
title: 类成员
summary: 类定义的花括号里能声明什么，成员函数体为什么能看到后面的成员，数据成员在对象里怎样排列，以及成员函数、静态成员、位域、类专属 new/delete 和嵌套类的规则。
status: draft
covers: class.mem.general, class.mfct, class.mfct.non.static, class.static, class.static.general, class.static.mfct, class.static.data, class.bit, class.free, class.nest
papers: P0847R7, P1847R4
related: class.pre, class.prop, special, class.union, basic.scope.class, expr.prim.this, over.match.funcs, dcl.fct, class.access.nest, basic.def.odr
tags: 类, 成员, 布局, 位域, 静态成员, deducing this
updated: 2026-10-19
---

!!! tldr
    - 类的全部成员都在类定义里一次声明完，之后不能再添加；除了嵌套类和枚举的前置声明，同一个成员也不能在类里声明两次。
    - 成员函数体、默认实参、默认成员初始化器等是完整类上下文，在那里能看到整个类的成员，类也是完整类型；成员的类型、返回类型、数组边界则只能看到前面的声明。
    - 后声明的非静态数据成员地址更高（C++23 起与访问控制无关）；标准布局类对象的地址就是它第一个成员的地址。
    - 类内带初始化器的 `static const int` 只是声明。被 odr-use 时需要类外定义，C++17 起改用 `static constexpr` 或 `static inline` 即可。
    - 位域没有地址，布局由实现定义；类专属的 `operator new`/`operator delete` 总是静态成员。

```cpp run ok
struct Widget {
  int id = 0;                    // 非静态数据成员
  static inline int count = 0;   // 静态数据成员
  void draw() const;             // 成员函数
  static Widget make();          // 静态成员函数
  using Id = int;                // 嵌套类型
  struct Part { };               // 嵌套类
  enum Color { red, green };     // 嵌套类型，red、green 也是成员
  template<class T> void set(T); // 成员模板
  unsigned flags : 4;            // 位域
  friend void swap(Widget&, Widget&);  // 友元：不是成员
  static_assert(sizeof(int) >= 2);     // 不声明成员
};
int main() { }
```

类定义的花括号里写的内容叫**成员规格**（member-specification）。本页先讲成员规格的总规则 [class.mem.general]：什么是成员、在类里的哪些地方能看到哪些成员、数据成员怎样排列。后半部分依次讲成员函数、静态成员、位域、类专属的分配函数和嵌套类。特殊成员函数见 [[special]]，联合体见 [[class.union]]。

## 什么是成员 [class.mem.general]

### 成员的种类（¶3–¶6）

¶3 类的成员有五种：数据成员、成员函数（[[class.mfct]]）、嵌套类型、枚举项、成员模板（[[temp.mem]]）及其特化。成员模板的特化归入对应的种类：成员函数模板的特化是成员函数，成员类模板的特化是嵌套类。

¶5 各种成员的含义如下：

- **数据成员**：由 *member-declarator* 引入的非函数成员，或者匿名联合体的成员。
- **成员函数**：是函数的成员。
- **嵌套类型**：在类里声明的类、枚举，以及用 `typedef` 或 `using` 声明的类型别名。类里定义的无作用域枚举，它的枚举项也是类的成员。

¶6 用 `static` 声明的数据成员和成员函数是**静态成员**，其余的是**非静态成员**。

¶3 首先声明在类 `X` 的成员规格里的成员，是 `X` 的**直接成员**（direct member，[[g:direct-member]]），匿名联合体的成员也算。继承来的成员不是直接成员。

### 不声明成员的声明（¶4）

¶4 成员规格里有几种声明不声明新成员：友元声明、推导指引、以它们为内容的模板声明、`static_assert`、`consteval` 块、*using-declaration* 和空声明。*using-declaration* 只是把基类成员的名字引入派生类的作用域，并不让它成为派生类的直接成员。

其余的成员声明必须至少声明一个成员名，或者一个无名位域：

```cpp title="member-decls.cpp" error
struct S {
  int;                  // error: 没有声明任何东西
  int : 4;              // OK: 无名位域
  static_assert(true);  // OK: 不声明成员
  ;                     // OK: 空声明
};
```

Clang 对 `int;` 默认只给出一条 `declaration does not declare anything` 警告，加 `-pedantic-errors` 才报错。按标准这个程序非良构，警告也算满足了诊断的要求（[[intro.compliance]]）。

¶4 最后定义了一个特殊成员函数的规则反复用到的词：由某个成员声明声明的直接成员或友元，是**用户声明的**（user-declared，[[g:user-declared]]）。写了 `= default` 或 `= delete` 的函数也是用户声明的。

### 成员只能在类里声明，而且只声明一次（¶3、¶8、¶9）

¶3 类定义的成员规格声明了这个类的全部成员，不能在别处添加。类的成员集合在 `}` 处一次确定，所以布局、虚函数表、隐式声明的特殊成员函数都能在这里确定下来。

¶8 同一个成员不能在成员规格里声明两次，例外只有两个：嵌套类或成员类模板可以先声明、后定义（¶8.1）；枚举可以先用 `enum E : int;` 这样的不透明声明引入，再给出完整定义（¶8.2）。这与命名空间作用域不同，那里的函数可以重复声明。

```cpp title="no-redecl.cpp" error
struct S {
  void f();
  void f();            // error: 重复声明
  struct N;
  struct N { };        // OK: ¶8.1
  enum E : int;
  enum E : int { A };  // OK: ¶8.2
};
```

同名的成员函数只要类型有足够的差别，就是重载，不算重复声明（[[basic.scope.scope]]）。

¶9 在类定义之外重新声明成员，只能是定义、显式特化或显式实例化，而且不能是非静态数据成员：

```cpp title="out-of-class.cpp" error
struct S {
  void f();
  static int s;
  int m;
};
void S::f() { }   // OK: 定义
int S::s = 0;     // OK: 静态数据成员的定义
void S::f();      // error: 类外的重声明必须是定义
int S::m;         // error: 不能在类外重声明非静态数据成员
```

## 完整类上下文（¶10–¶11）

```cpp run title="complete-class-context.cpp" ok
struct S {
  int f() { return g() + sizeof(S); }   // 函数体
  void h(int x = k) { (void)x; }        // 默认实参
  void n() noexcept(noexcept(g())) { }  // noexcept 说明符
  int m = g();                          // 默认成员初始化器
  int g() const { return 1; }
  static constexpr int k = 42;
};
int main() {
  S s;
  return s.f() == 1 + int(sizeof(S)) ? 0 : 1;
}
```

`f` 的函数体调用了后面才声明的 `g`，还对还没定义完的 `S` 求了 `sizeof`。这都是合法的，因为函数体处在 `S` 的完整类上下文中。

¶10 类的**完整类上下文**（complete-class context，[[g:complete-class-context]]）是指类的成员规格中的以下几处：

- ¶10.1 函数体；
- ¶10.2 默认实参；
- ¶10.3 默认模板实参；
- ¶10.4 *noexcept-specifier*；
- ¶10.5 函数契约说明符（`pre`、`post`）{{c++26}}；
- ¶10.6 默认成员初始化器。

如果嵌套类定义在外围类的成员规格里，嵌套类的完整类上下文也是外围类的完整类上下文（注 4）。

¶11 在程序中的某一点 P，如果类 `C` 的定义从 P 可达（[[module.reach]]），或者 P 在 `C` 的完整类上下文中，就说 `C` 在 P 是完整的。

可以这样理解编译器的做法：处理类定义分两遍。第一遍只处理成员的声明，建立完整的成员表；到 `}` 之后再回头处理完整类上下文。所以在完整类上下文中，名字查找能找到整个类的成员，包括后面才声明的（[[basic.scope.class]]），类也是完整类型。

### 其余地方只能看到前面的声明

成员的声明部分不是完整类上下文。数据成员的类型、函数的返回类型和形参类型（包括尾随返回类型）、静态数据成员的类内初始化器、基类子句，都只能看到前面声明的成员，类在那里也不完整：

```cpp title="not-complete-context.cpp" error
struct S {
  auto f() -> decltype(g());   // error: g 还没有声明
  int g();
  char buf[sizeof(S)];         // error: S 在此不完整
  static constexpr int v = w;  // error: w 还没有声明
  static constexpr int w = 1;
};
```

这些地方决定类的形状：数据成员的类型决定布局，返回类型和形参类型决定函数的签名，进而决定重载和虚函数的覆盖关系。如果它们能依赖后面的声明，就可能出现循环依赖。函数体、默认实参这些部分不影响形状，可以安全地推迟到 `}` 之后处理。

!!! warning "Clang 没有推迟默认模板实参"
    第 10.3 项把成员模板的默认模板实参列为完整类上下文。截至写作时，Clang 23 对 `template<class U = decltype(T::m)> void z(); int m;` 仍报告 `T` 中没有成员 `m`，也就是没有推迟处理默认模板实参。依赖这一点的代码目前不可移植。

### 嵌套类的默认成员初始化器

推迟处理带来一个难题。嵌套类 `B` 的默认成员初始化器也是外围类 `A` 的完整类上下文，要到 `A` 的 `}` 之后才处理。如果在那之前就有代码要知道 `B` 能不能默认构造，答案取决于一个还没解析的初始化器：

```cpp run title="nested-dmi.cpp"
#include <type_traits>

struct A {
  struct B { int n = 0; };
  // 此时 B 的默认成员初始化器还没有处理
  static constexpr bool v =
      std::is_default_constructible_v<B>;
};

int main() { return A::v; }
```

本机 Clang 23 中 `A::v` 是 `false`。而且类型特征的结果被缓存了，到类外再问 `std::is_default_constructible_v<A::B>` 也得到 `false`。

¶15 规定默认成员初始化器不得直接或间接导致外围类的预置默认构造函数被隐式定义，也不得导致需要它的异常说明，针对的就是这类循环。但类型特征这种间接的情形，各编译器的处理并不一致：有的报错，有的像 Clang 这样静默地给出 `false`。实践中，不要在外围类的定义里对带默认成员初始化器的嵌套类用类型特征，可以把嵌套类移到外围类外面，或者给它一个用户声明的默认构造函数。

## 默认成员初始化器（¶15）

¶15 *brace-or-equal-initializer*（`= 表达式` 或 `{ … }` 形式的初始化器）只能出现在数据成员的声明中。对非静态数据成员，它给出该成员的**默认成员初始化器**（default member initializer，[[g:default-member-initializer]]）。构造函数的成员初始化列表没有提到这个成员时（[[class.base.init]]），以及聚合初始化时（[[dcl.init.aggr]]），就用它初始化成员。静态数据成员的初始化器见下文。

默认成员初始化器没有圆括号的形式：

<div class="compare" markdown="1">

```cpp error
#include <vector>
struct S {
  std::vector<int> v(10);  // error
};
```

```cpp ok
#include <vector>
struct S {
  std::vector<int> v =
      std::vector<int>(10);  // OK
  std::vector<int> w{1, 2};  // OK
};
```

</div>

左边的写法在类里会被当作一个成员函数的声明来解析，`10` 不是类型，于是报错（Clang：`expected parameter declarator`）。注意花括号形式会优先选择 `std::initializer_list` 构造函数，`w{10}` 是只含一个元素 10 的 vector。

默认成员初始化器里可以使用 `this`（[[expr.prim.this#5]]），也可以使用其他成员，包括后面才声明的成员。但成员按声明顺序初始化，读取一个还没初始化的成员仍然是错误的。

¶15 最后一句处理默认成员初始化器中的立即调用（immediate invocation，[[expr.const.imm]]），例如 `consteval` 函数的调用：它不在初始化器出现的地方求值，也不在那里检查是否为常量表达式，而是在实际使用这个初始化器的构造函数里进行。所以 `std::source_location::current()` 写在默认成员初始化器中，报告的是构造函数的位置：

```cpp run title="dmi-source-location.cpp" ok
#include <source_location>

struct S {
  std::source_location loc = std::source_location::current();
  S() { }        // 第 5 行
  S(int) { }     // 第 6 行
};

int main() {
  S a, b(1);
  return a.loc.line() == 5 && b.loc.line() == 6 ? 0 : 1;
}
```

## 成员声明的语法细节（¶1–¶2、¶12–¶19、¶25–¶26）

成员声明的语法大体和命名空间作用域的声明相同，多出几样东西：`override`、`final`（*virt-specifier*），纯说明符 `= 0`，约束非模板成员函数的尾随 *requires-clause*，位域宽度，以及 C++26 的函数契约说明符。第 2 段规定契约说明符只能出现在声明函数的成员声明中。

### `= 0` 是纯说明符还是初始化器（¶1、¶13）

`= 0` 在语法上既可以是纯说明符，也可以是初始化器。第 1 段和第 13 段按被声明者的类型区分：类型是函数类型时，`=` 引入纯说明符，否则引入初始化器。

```cpp run title="pure-or-init.cpp" ok
struct S {
  using T = void();
  T* p = 0;          // p 是指针：初始化器
  virtual T f = 0;   // f 是函数：纯说明符
};
int main() { }
```

如果成员要经过模板实例化才得到函数类型，例如 `template<class T> struct X { T m = 0; };` 用 `T = void()` 实例化，程序非良构（注 1，[[temp.spec.general]]）。

### 位域宽度取最长的表达式（¶14）

位域可以带默认成员初始化器（`int x : 8 = 42;`）。于是有一个问题：`:` 后面的宽度表达式到哪里结束？第 14 段规定取能构成常量表达式的最长记号序列。下例改编自标准例 2：

```cpp title="bitfield-parse.cpp" error
int a;
const int b = 0;
struct S {
  int x1 : 8 = 42;               // OK: "= 42" 是初始化器
  int x2 : 8 { 42 };             // OK: "{ 42 }" 是初始化器
  int y1 : true ? 8 : a = 42;    // OK: 整个都是宽度
  int y2 : true ? 8 : b = 42;    // error: 给 const int 赋值
  int y3 : (true ? 8 : b) = 42;  // OK: "= 42" 是初始化器
  int z : 1 || new int { 0 };    // OK: "{ 0 }" 属于 new 表达式
};
```

条件运算符的第三个操作数可以是赋值表达式，所以 `a = 42` 整个归入宽度。`y1` 的宽度仍是常量表达式，因为求值走 `true` 分支，`a = 42` 根本不会执行。

### 友元类型声明（¶12）

`friend class X;`、`friend T;` 这类 `friend` 后面只跟类型的声明叫 *friend-type-declaration*。第 12 段规定，语法上能匹配它的成员声明都按它解析。C++26 允许包展开，一次把一个模板形参包中的所有类型声明为友元 {{c++26}}：

```cpp run title="variadic-friend.cpp" ok
template<class... Ts>
class Passkey {
  friend Ts...;          // 包中的每个类型都是友元
  Passkey() = default;
};

struct Alice {
  static Passkey<Alice, struct Bob> key() { return {}; }
};

int main() { (void)Alice::key(); }
```

### 说明符的限制（¶16–¶19）

- ¶16 成员不能声明为 `extern`。成员不能只声明为 `thread_local`，必须同时是 `static`：非静态数据成员是对象的一部分，每个线程一份没有意义。
- ¶17 只有构造函数、析构函数和转换函数可以不写类型。C++ 没有隐式 `int`，所以 `const x;` 是非良构的。纯说明符只能用于虚函数。
- ¶18 成员声明开头的属性属于这个声明声明的每一个实体。
- ¶19 `override`、`final` 各自最多出现一次，而且只能出现在虚函数的第一次声明中，类外定义不能再写。

```cpp title="specifiers.cpp" error
struct S {
  extern int e;                // error: ¶16
  thread_local int t;          // error: ¶16，须为 static
  static thread_local int ok;  // OK
  const x;                     // error: ¶17，缺少类型
  void f() = 0;                // error: ¶17，f 不是虚函数
  virtual void g() override;   // error: g 没有覆盖任何函数
};
```

### 成员不能与类同名（¶25–¶26）

¶25 类 `T` 的静态数据成员、成员函数、类型成员、成员模板、无作用域枚举成员的枚举项、匿名联合体的成员都不能叫 `T`。构造函数没有名字，不受这条限制。

类名 `T` 已经作为注入类名（[[class.pre#2]]）出现在类作用域里，构造函数的声明语法 `T(...)` 也依赖它，同名成员会与之冲突。第 26 段只在类有用户声明的构造函数时才禁止非静态数据成员叫 `T`，这是为了兼容 C：C 代码里 `struct stat { ... };` 中出现同名成员是合法的。

```cpp title="same-name.cpp" error
struct T1 { int T1; };          // OK: 没有用户声明的构造函数
struct T2 { T2(); int T2; };    // error: ¶26
struct T3 { static int T3; };   // error: ¶25.1
struct T4 { void T4(); };       // error: ¶25.2
```

## 数据成员在对象中的布局（¶7、¶20、¶24）

### 成员的类型（¶20）

¶20 非静态数据成员的类型不能是不完整类型、抽象类类型，也不能是它们的数组。所以类 `C` 不能含有 `C` 类型的成员，但可以含有指向 `C` 的指针或引用。

这条规则也排除了 C99 的柔性数组成员（`struct S { int n; int data[]; };`），因为 `int[]` 是不完整类型。GCC 和 Clang 作为扩展接受它，开 `-pedantic` 时给出警告。

### 每个成员一个子对象，引用成员和指针一样大（¶7）

¶7 类类型的对象为每个直接非静态数据成员各含一个成员子对象。

引用是否占存储，一般情况下是未指定的（[[dcl.ref]]）。但对于类的引用成员，第 7 段作了规定：设想一个类 `D`，它与 `C` 相同，只是把每个 `T&` 成员换成 `T*`；那么 `C` 的每个成员子对象的大小、对齐和偏移都与 `D` 的对应成员相同，`C` 本身的大小和对齐也与 `D` 相同。换句话说，引用成员占的空间和指针一样。

```cpp run title="ref-member-layout.cpp" ok
struct C { int& r; char c; };
struct D { int* r; char c; };
static_assert(sizeof(C) == sizeof(D));
static_assert(alignof(C) == alignof(D));
int main() { }
```

### 后声明的成员地址更高（¶24）

```cpp run title="member-order.cpp" ok
#include <cstdio>
struct S {
  char a;   // 偏移 0
  int  b;   // 偏移 4：a 后面有 3 字节填充
  char c;   // 偏移 8，之后尾部填充到 12
public:
  int  d;
private:
  int  e;   // C++23 起：一定在 d 之后
};
int main() {
  S s{};
  bool ordered = (void*)&s.a < (void*)&s.b
              && (void*)&s.b < (void*)&s.c;
  std::printf("sizeof(S) = %zu\n", sizeof(S));
  return ordered ? 0 : 1;
}
```

¶24 的注 8 说明，非变体、非零大小的非静态数据成员按声明顺序分配，后声明的成员地址更高（[[expr.rel]]）。相邻成员之间可能因为对齐而有填充，虚函数和虚基类的管理信息（如 vptr）也会占用空间。主流 64 位平台上，上例打印 `sizeof(S) = 20`。

两个限定词的意思是：用 `[[no_unique_address]]` 声明的空成员可以是零大小的，它可能与别的成员共享地址，不参与排序；联合体的成员（变体成员）都在同一地址。

编译器不会替你重排成员。把成员按对齐从大到小排列以减少填充，是程序员的事；GCC 和 Clang 的 `-Wpadded` 可以报告插入的填充。

!!! history "C++23：不再按访问区段重排（P1847）"
    C++20 及以前只保证同一访问区段内（两个访问说明符之间）的成员按声明顺序递增，不同区段之间的相对顺序未指定。没有主流编译器利用过这项许可。C++23 的 [[P1847R4]] 删除了它，现在顺序只取决于声明顺序。

## 公共初始序列与布局兼容（¶27–¶31）

```cpp run title="tagged-union.cpp" ok
enum Kind { Int, Dbl };
struct IntNode { Kind k; int v; };
struct DblNode { Kind k; double v; };
union Node { IntNode i; DblNode d; };

int value(const Node& n) {
  switch (n.i.k) {   // 不管哪个成员活跃，都能这样读标签
    case Int: return n.i.v;
    case Dbl: return static_cast<int>(n.d.v);
  }
  return -1;
}

int main() {
  Node n;
  n.d = {Dbl, 2.5};
  return value(n) - 2;
}
```

`n.d` 是联合体的活跃成员，`value` 却通过 `n.i.k` 读标签。读联合体的非活跃成员一般是未定义行为，这里合法，靠的是公共初始序列的规则。

### 公共初始序列（¶27）

¶27 两个标准布局 struct（[[g:standard-layout-struct]]，[[class.prop]]）的**公共初始序列**（common initial sequence，[[g:common-initial-sequence]]），是从各自第一个非静态数据成员开始、按声明顺序逐对比较、一直满足以下条件的最长一段：

- ¶27.1 对应成员的类型布局兼容（[[g:layout-compatible-types]]），例如 `int` 和 `const int`；
- ¶27.2 对齐要求相同；
- ¶27.3 如果实现支持 `[[no_unique_address]]`，两个成员都没有用它声明；
- ¶27.4 要么都是宽度相同的位域，要么都不是位域。

```cpp run title="cis.cpp" ok
struct A { int a; char b; };
struct B { const int b1; volatile char b2; };  // 与 A：全部成员
struct C { int c; unsigned : 0; char b; };     // 与 A：只有第一个
struct D { int d; char b : 4; };               // 与 A：只有第一个
struct E { unsigned int e; char b; };          // 与 A：空
int main() { }
```

`C` 的第二个成员是无名位域，`D` 的第二个成员是位域，序列都在那里中断。`int` 和 `unsigned int` 不是布局兼容的类型，所以 `A` 与 `E` 的公共初始序列为空。第 27.2 项要求对齐相同，是为了排除 `alignas` 的影响：`alignas(8) int` 与 `int` 类型相同，但后面成员的偏移可能不同。

### 通过联合体读取（¶30）

¶30 标准布局联合体的活跃成员是 struct 类型 `T1` 时，可以读取另一个 struct 类型的成员 `T2` 的非静态数据成员 `m`，只要 `m` 在 `T1` 与 `T2` 的公共初始序列中。效果如同读取 `T1` 中对应的成员。

```cpp run title="union-cis.cpp" ok
struct T1 { int a, b; };
struct T2 { int c; double d; };
union U { T1 t1; T2 t2; };

int f() {
  U u = { { 1, 2 } };   // 活跃成员是 t1
  return u.t2.c;        // OK: 如同读取 u.t1.a
  // u.t2.d 不在公共初始序列中，读它是 UB
}

int main() { return f() - 1; }
```

注 10 提醒，通过非 `volatile` 的 glvalue 读取 `volatile` 对象仍然是 UB（[[dcl.type.cv]]）。`A` 与 `B` 的公共初始序列包含 `volatile char b2`，但通过 `A::b` 去读它仍是 UB。

### 布局兼容的类（¶28–¶29）

¶28 两个标准布局 struct 的公共初始序列包含了双方全部的成员，它们就是**布局兼容的类**（[[g:layout-compatible-classes]]）。¶29 两个标准布局联合体的非静态数据成员个数相同，并且对应成员（顺序任意）的类型布局兼容，它们也是布局兼容的。C++20 起可以用 `std::is_layout_compatible` 查询。

### 对象与首成员地址相同（¶31）

¶31 标准布局类的对象如果有非静态数据成员，它的地址与第一个非静态数据成员的地址相同（这个成员不是位域时），也与它的每个基类子对象的地址相同。所以标准布局 struct 中可能有填充，但不会在开头（注 11）。

这样的对象与它的第一个子对象是**指针可互转换的**（pointer-interconvertible，[[g:pointer-interconvertible]]，[[basic.compound#7]]），可以用 `reinterpret_cast` 在两者的指针之间转换，结果指向对方：

```cpp run title="pointer-interconvertible.cpp" ok
struct Base { int tag; };
struct Wrapper : Base { };                // 标准布局
struct Outer { Base first; int extra; };  // 标准布局

int main() {
  Wrapper w{{1}};
  Outer o{{2}, 3};
  Base* b1 = reinterpret_cast<Base*>(&w);  // 等价于 static_cast
  Base* b2 = reinterpret_cast<Base*>(&o);  // 指向 o.first
  return b1->tag + b2->tag - 3;
}
```

数组和它的首元素地址相同，却不是指针可互转换的（[[basic.compound#7]] 注 7）。

## 数据成员描述（¶32）{{c++26}}

¶32 为静态反射定义了**数据成员描述**（data member description，[[g:data-member-description]]）：一个六元组，依次是类型、名字（或无名）、对齐（或不指定）、位域宽度（或不是位域）、是否 `[[no_unique_address]]`、注解序列。两个描述的各分量都相同时，它们相等。

`std::meta::data_member_spec` 返回表示数据成员描述的反射，`std::meta::define_aggregate` 据此为一个不完整的类生成成员（[[meta.reflection.define.aggregate]]）。这是 C++26 用代码生成类的入口。截至写作时，本机 Clang 23 尚不支持静态反射，所以这里不给例子。

## 成员函数 [class.mfct]

### 类内定义的成员函数是 inline 的（[class.mfct] ¶1）

[[class.mfct#1]] 附属于全局模块的成员函数如果在类定义内定义，就是 `inline` 的（[[dcl.inline]]）。声明为 `inline`、`constexpr` 或 `consteval` 的成员函数当然也是。

这条规则让头文件中的类定义可以被多个翻译单元包含而不违反 ODR（[[basic.def.odr]]）。附属于全局模块是 C++20 加上的限定：在具名模块（`export module M;`）里，类定义只编译一次，类内定义的成员函数不再隐式 inline。这样修改函数体时，导入者不必重新编译。想在模块里让它可以内联，要显式写 `inline`。

### 类外定义的作用域（[class.mfct] ¶2）

[[class.mfct#2]] 在类外定义成员函数时，`X::f` 之后的部分，包括形参类型、默认实参和函数体，都在类 `X` 的作用域内查找名字。返回类型写在 `X::f` 之前，不在类作用域内，所以返回嵌套类型要写 `X::T X::g()`，或者用尾随返回类型 `auto X::g() -> T`：

```cpp run title="out-of-class-scope.cpp" ok
struct X {
  typedef int T;
  static T count;
  T g();
  void f(T);
};
X::T X::count = 1;

X::T X::g() { return count; }       // 返回类型要限定
void X::f(T t = count) { (void)t; } // T 和 count 在类作用域中找到

int main() { X x; x.f(); return x.g() - 1; }
```

### 局部类与用 typedef 声明成员函数（[class.mfct] ¶3–¶4）

[[class.mfct#3]] 局部类（定义在函数里的类）的成员函数如果要定义，必须在类定义内定义。函数里不能再定义函数，在类外也就没有地方定义它们。

[[class.mfct#4]] 可以用函数类型的 typedef 声明成员函数（但不能定义），得到的类型与直接写出声明符相同。`typedef void fvc() const;` 这样带 cv 限定的函数类型也可以这样用。

## 非静态成员函数 [class.mfct.non.static]

[[class.mfct.non.static#1]] 非静态成员函数可以用成员访问语法（`obj.f()`、`p->f()`）为它所属的类或派生类的对象调用。在类或派生类的成员里，也可以直接写 `f()`，它会被变换成 `(*this).f()`（[[expr.prim.id]]）。

C++23 起非静态成员函数分为两种（[[dcl.fct#8]]）：

- **隐式对象成员函数**（implicit object member function，[[g:implicit-object-member-function]]）：传统写法，对象通过隐式的 `this` 传入；
- **显式对象成员函数**（explicit object member function，[[g:explicit-object-member-function]]）：第一个形参前写 `this`，对象作为普通形参传入，俗称 deducing this。

### cv 限定与引用限定（[class.mfct.non.static] ¶2）

```cpp run title="ref-qualifiers.cpp" ok
#include <string>
#include <utility>

struct Buf {
  std::string s;
  std::string&       get() &       { return s; }
  const std::string& get() const & { return s; }
  std::string        get() &&      { return std::move(s); }
};

Buf make() { return {"hello"}; }

int main() {
  Buf b{"abc"};
  std::string& r = b.get();       // & 版本
  std::string  v = make().get();  // && 版本：移走内容，不会悬垂
  return r.size() == 3 && v.size() == 5 ? 0 : 1;
}
```

[[class.mfct.non.static#2]] 的注 1 说明，隐式对象成员函数可以带 cv 限定（影响 `this` 的类型）和引用限定（`&`、`&&`），两者都参与重载决议。

重载决议时，隐式对象成员函数被看作多了一个第一形参，叫**隐式对象形参**（implicit object parameter，[[g:implicit-object-parameter]]，[[over.match.funcs.general#4]]）：

| 声明 | 隐式对象形参的类型 | `this` 的类型 |
|---|---|---|
| `void f();` | `X&`（也能绑定右值，见下） | `X*` |
| `void f() const;` | `const X&` | `const X*` |
| `void f() &;` | `X&` | `X*` |
| `void f() &&;` | `X&&` | `X*` |
| `void f() const &&;` | `const X&&` | `const X*` |

没有引用限定的成员函数，隐式对象形参虽然是左值引用，也能绑定右值（[[over.match.funcs.general#5]]），所以临时对象可以调用非 `const` 成员函数，`std::string().append("x")` 能编译。引用限定让你区分这两种情况，如上例。

同名、同形参的重载要么都有引用限定，要么都没有（[[over.load]]）：

```cpp title="ref-qual-mix.cpp" error
struct C {
  void f() &;
  void f();   // error: 不能与有引用限定的重载并存
};
```

在 cv 限定为 *cv* 的隐式对象成员函数里，`this` 是类型为指向 *cv* `X` 的指针的 prvalue（[[expr.prim.this#4]]）。不能对它赋值，也不能取它的地址。引用限定不影响 `this` 的类型，在 `&&` 成员函数里 `*this` 仍是左值。C++26 起，在契约断言的谓词里，`this` 的类型会额外加上 `const`（[[expr.prim.this#3]]）。

[[class.mfct.non.static#3]] 隐式对象成员函数可以是虚函数（[[class.virtual]]）或纯虚函数（[[class.abstract]]）。

### 显式对象成员函数 {{c++23}}

```cpp run title="deducing-this.cpp" ok
#include <string>
#include <utility>

struct S {
  std::string name = "s";

  // 一个模板代替 &、const&、&&、const&& 四个重载
  template<class Self>
  auto&& get(this Self&& self) {
    return std::forward<Self>(self).name;
  }

  // 按值接收对象
  std::size_t len(this S self) { return self.name.size(); }
};

int main() {
  S s;
  const S cs;
  std::string& a = s.get();            // Self = S&
  const std::string& b = cs.get();     // Self = const S&
  std::string c = std::move(s).get();  // Self = S，返回 std::string&&
  (void)a; (void)b;
  return c == "s" && cs.len() == 1 ? 0 : 1;
}
```

C++23 的 [[P0847R7]] 允许把对象形参写成第一个形参，前面加 `this`（[[dcl.fct#7]]）。它的主要用途有：

1. 用一个模板代替按 cv 和引用限定重载的几个版本，如上例的 `get`；
2. 代替 CRTP：基类中的 `template<class Self> void f(this Self& self)` 能拿到派生类的真实类型；
3. 递归 lambda：`[](this auto self, int n) -> int { return n < 2 ? n : self(n-1) + self(n-2); }`；
4. 按值接收小对象，省去一次间接访问。

它的限制（[[dcl.fct#7]]、[[dcl.fct#8]]、[[expr.prim.this#4]]）：

- 显式对象形参只能是第一个形参，不能是函数形参包；
- 函数不能再带 cv 限定或引用限定，不能是 `static` 或 `virtual`；
- 函数体里没有 `this`，访问成员必须写 `self.name`；
- 构造函数不能有显式对象形参（[[class.ctor.general#7]]）；
- 取地址得到普通函数指针，不是成员函数指针：`&S::len` 的类型是 `std::size_t(*)(S)`。

```cpp title="deducing-this-errors.cpp" error
struct D {
  void g(this D) const;     // error: 不能有 cv 限定
  static void h(this D);    // error: 不能是 static
  virtual void i(this D&);  // error: 不能是 virtual
  void j(this D& self) { this->j(); }  // error: 不能用 this
};
```

## 静态成员 [class.static]

### 访问静态成员（[class.static.general]）

[[class.static.general#1]] 类 `X` 的静态成员 `s` 可以写成 `X::s`，不需要对象。也可以用成员访问语法 `obj.s`，这时对象表达式照样求值，副作用照常发生：

```cpp run title="static-member-access.cpp" ok
#include <cstdio>

struct process {
  static void reschedule() { }
};

process& g() {
  std::puts("g() called");
  static process p;
  return p;
}

int main() {
  process::reschedule();   // 不需要对象
  g().reschedule();        // g() 被调用，会打印
}
```

[[class.static.general#2]] 静态成员遵守普通的访问规则。`static` 只能写在类定义里的成员声明上，类外定义时不能再写。

### 静态成员函数（[class.static.mfct]）

[[class.static.mfct#2]] 静态成员函数没有 `this`，不能带 `const`、`volatile` 限定，也不能是虚函数。[[class.mfct]] 的其他规则同样适用于它。

重载决议时，静态成员函数的隐式对象形参能匹配任何对象（[[over.match.funcs.general#4]]），所以 `obj.f()` 中静态和非静态的 `f` 可以一起参与重载决议。C++23 起，`operator()` 和 `operator[]` 可以是静态成员函数（[[over.call]]、[[over.sub]]），无捕获的 lambda 也可以声明为 `static`，调用无状态的函数对象时可以省掉 `this` 参数。

### 静态数据成员（[class.static.data]）

[[class.static.data#1]] 静态数据成员不是类对象的子对象。不是 `thread_local` 的静态数据成员只有一份，由所有对象共享；`thread_local` 的每个线程一份。

[[class.static.data#2]] 静态数据成员不能是 `mutable`，也不能是无名类、局部类，或者嵌套在它们里面的类的直接成员。这些类没有链接，没有办法在类外给出定义。

```cpp title="static-data-restrictions.cpp" error
void f() {
  struct Local { static int x; };   // error: 局部类
}
struct { static int y; } anon;      // error: 无名类
struct M { static mutable int z; }; // error: 不能是 mutable
```

[[class.static.data#3]] 不是 inline 的静态数据成员，它在类里的声明不是定义，类型可以是不完整类型（`void` 除外）。定义写在命名空间作用域，定义中的初始化器处在类的作用域里，可以直接使用类的其他成员：

```cpp run title="static-data-def.cpp" ok
struct Node;
struct List {
  static Node sentinel;   // 声明时 Node 可以不完整
  static int count;
  static int limit;
};
struct Node { int v; };

Node List::sentinel{0};         // 定义：此时 Node 必须完整
int  List::count = 0;
int  List::limit = count + 10;  // count 即 List::count

int main() { return List::limit - 10; }
```

静态数据成员一旦定义就存在，即使程序从未创建这个类的对象。它的初始化和销毁按 [[basic.start.static]]、[[basic.start.dynamic]]、[[basic.start.term]] 进行。

### 哪些静态数据成员能在类内初始化（[class.static.data] ¶4）

| 情形 | 类内初始化器 | 类外定义 |
|---|---|---|
| 非 `volatile`、非 inline 的 `const` 整型或枚举 | 可以，必须是常量表达式 | 被 odr-use 时必须有，且不能再带初始化器 |
| `inline` 静态数据成员 {{c++17}} | 可以，类内声明就是定义 | 不需要 |
| `constexpr` 静态数据成员 | 必须有（`constexpr` 蕴含 `inline`） | 不需要；不带初始化器的重声明仍允许，但已弃用（[[depr.static.constexpr]]） |
| 其他 | 不能 | 被 odr-use 时必须有 |

```cpp run title="static-init-kinds.cpp" ok
#include <string>

struct S {
  static const int N = 3;                // const 整型
  static inline std::string name = "S";  // inline：任意类型
  static constexpr double pi = 3.14159;  // constexpr 蕴含 inline
  // static double e = 2.718;            // error: 不能类内初始化
  int arr[N];                            // 用 N 的值不是 odr-use
};

int main() {
  S s{};
  return int(sizeof(s.arr) / sizeof(int)) - S::N;
}
```

第一行有一个常见陷阱。`static const int N = 3;` 看上去已经定义了，其实它只是声明。如果 `N` 被 odr-use（[[g:odr-use]]），例如绑定到引用、取地址、传给 `std::max` 这类按 `const int&` 接收参数的函数，就必须在某个翻译单元里提供定义：

```cpp title="odr-use-static-const.cpp" ifndr
struct S { static const int N = 3; };

int main() {
  const int& r = S::N;  // odr-use：绑定到引用
  return r;             // IFNDR：缺少 S::N 的定义
}
```

缺少定义违反 ODR，属于不要求诊断的非良构（IFNDR）。本机 Clang 23 在 `-O0` 下链接失败（`Undefined symbols ... S::N`），在 `-O2` 下 `r` 被常量折叠，链接成功。

C++17 起的修复方法是改写成 `static constexpr int N = 3;` 或 `static inline const int N = 3;`，inline 变量（[[g:inline-variable]]）的类内声明就是定义。在头文件里定义类的常量，不再需要到某个 .cpp 里补一行定义，这是 C++17 引入 inline 变量的主要动机之一。

[[class.static.data#5]]、[[class.static.data#6]] 是两个注：被 odr-use 的静态数据成员在合法程序中恰有一个定义（inline 的则在每个用到它的翻译单元里各有一个相同的定义）；命名空间作用域中的类，其静态数据成员与类名具有相同的链接（[[basic.link]]）。

## 位域 [class.bit]

### 声明与基本限制（[class.bit] ¶1）

```cpp run title="bitfield-basics.cpp" ok
#include <type_traits>

struct Flags {
  unsigned ready : 1;
  unsigned mode  : 3;
  unsigned       : 4;   // 无名位域：4 位填充
  unsigned count : 8;
};

Flags f{};
static_assert(std::is_same_v<decltype(f.mode), unsigned>);

int main() {
  f.mode = 5;
  f.count = 200;
  return f.mode == 5 && f.count == 200 ? 0 : 1;
}
```

[[class.bit#1]] 形如 `名字 : 宽度` 的成员声明声明一个**位域**（bit-field，[[g:bit-field]]），宽度是值不小于 0 的整型常量表达式。规则如下：

- 位域不能是静态成员；
- 类型必须是整型或枚举类型（可以带 cv 限定）；
- 是不是位域不属于成员的类型，上例中 `decltype(f.mode)` 就是 `unsigned`；
- 宽度大于类型（枚举取其底层类型）的宽度时，多出的位是填充位（[[g:padding-bits]]）；
- 位域在对象中怎样分配、怎样对齐，由实现定义 {{impl}}。

注 1 说明，有的机器上位域可以跨越分配单元，有的不行；有的从右向左分配，有的从左向右。所以用位域描述硬件寄存器或网络协议的格式是不可移植的。在 Itanium ABI 的小端平台上，位域从低位开始分配；MSVC 有自己的规则，尤其是相邻位域类型不同时是否共享分配单元。

### 无名位域与零宽位域（[class.bit] ¶2）

[[class.bit#2]] 省略名字的位域是**无名位域**（unnamed bit-field，[[g:unnamed-bit-field]]），用来按外部规定的布局填充。它不是成员，不能初始化，不能带 cv 限定。

宽度为 0 的无名位域让下一个位域从新的分配单元开始。只有无名位域的宽度可以是 0。

```cpp run title="zero-width.cpp" impl
#include <cstdio>

struct A { unsigned a : 3; unsigned : 0; unsigned b : 3; };
struct B { unsigned a : 3;               unsigned b : 3; };

int main() {
  // 主流 64 位平台：8 4
  std::printf("%zu %zu\n", sizeof(A), sizeof(B));
}
```

```cpp title="bitfield-errors.cpp" error
struct C {
  static int s : 3;   // error: 不能是静态成员
  const int : 2;      // error: 无名位域不能 cv 限定
  int z : 0;          // error: 只有无名位域宽度可以为 0
  double d : 4;       // error: 必须是整型或枚举类型
};
```

零宽位域在多线程中也有用。相邻的非零宽位域属于同一个内存位置（[[intro.memory]]），两个线程分别写同一内存位置中的不同位域会构成数据竞争。用零宽位域隔开后，它们成为不同的内存位置，可以并发修改。

### 位域没有地址（[class.bit] ¶3）

[[class.bit#3]] 不能对位域使用 `&`，所以没有指向位域的指针；非 `const` 引用不能绑定到位域。用位域初始化 `const T&` 时，引用绑定到一个保存了位域值的临时对象，之后修改位域，引用看不到变化：

```cpp run title="bitfield-ref.cpp" ok
struct C { int x : 4; };

int main() {
  C c{3};
  const int& r = c.x;   // 绑定到临时对象，值为 3
  c.x = 1;
  return r == 3 ? 0 : 1;
  // int* p = &c.x;     // error: 不能取位域的地址
  // int& nr = c.x;     // error: 非 const 引用不能绑定位域
}
```

内存中最小的可寻址单位是字节（[[intro.memory]]）。一个从第 5 位开始、宽 3 位的位域没有地址可言。`std::vector<bool>` 只能返回代理对象而不是 `bool&`，也是这个原因。

### 存进去的值能不能原样读回（[class.bit] ¶4）

[[class.bit#4]] 规定了能原样读回的情形：

- 整型值（`bool` 除外）：宽度为 N 的位域，如果这个值能用一个宽度为 N、符号性与位域类型相同的整数类型表示，读回的值相等；
- `bool` 位域（任意宽度，包括 1 位）：存入 `true` 或 `false`，读回的值相等；
- 枚举值存入同类型的枚举位域：宽度足以容纳该枚举的所有值（[[dcl.enum]]）时，读回的值相等。例如 `enum BOOL { FALSE=0, TRUE=1 };` 的值域是 0 到 1，`BOOL b : 1;` 就够了。

存入不能表示的值时，位域的值由实现定义（[[expr.assign]]）：

```cpp run title="bitfield-value.cpp" impl
struct C { int x : 4; };  // 有符号 4 位：-8 到 7

int main() {
  C c{};
  c.x = 7;    // 能表示：读回 7
  c.x = 8;    // 不能表示：实现定义
  return c.x;
}
```

Clang 对第二次赋值警告 `implicit truncation from 'int' to bit-field changes value from 8 to -8`，运行时读回 -8。

`int` 位域在 C++14 之前是有符号还是无符号由实现定义，C++14 起规定为有符号。C 语言中至今仍由实现定义，C 和 C++ 共用的头文件里需要无符号位域时，应该明确写 `unsigned`。

## 类专属的 operator new 和 operator delete [class.free]

[[class.free#1]]、[[class.free#3]] 类 `T` 的分配函数（`operator new`、`operator new[]`）和解分配函数（`operator delete`、`operator delete[]`）都是静态成员，即使没有写 `static`。调用分配函数时对象还不存在，调用解分配函数时对象已经销毁，不可能有 `this`。

[[class.free#2]] 类里只要声明了 `operator new`，就会隐藏全局 `::operator new` 的所有形式，因为 *new-expression* 先在类作用域查找（[[expr.new]]）：

```cpp title="class-new-hiding.cpp" error
#include <cstddef>

class Arena;
struct B {
  void* operator new(std::size_t, Arena*);  // 只有放置形式
};
struct D1 : B { };

Arena* ap;
void foo(int i) {
  new (ap) D1;   // B::operator new(std::size_t, Arena*)
  new D1[i];     // ::operator new[](std::size_t)：没被隐藏
  new D1;        // error: ::operator new(std::size_t) 被隐藏
}
```

### 不能是虚函数，效果却像虚函数（[class.free] ¶4–¶5）

[[class.free#4]] 分配和解分配函数是静态的，所以不能是虚函数。但如果 *delete-expression* 的操作数指向一个有虚析构函数的类对象，解分配函数由动态类型的析构函数选择（[[class.dtor#15]]），效果和虚函数一样：

```cpp run title="virtual-delete.cpp" ok
#include <cstdio>
#include <new>

struct B {
  virtual ~B() = default;
  void operator delete(void* p, std::size_t) {
    std::puts("B::delete");
    ::operator delete(p);
  }
};
struct D : B {
  int payload[10];
  void operator delete(void* p) {
    std::puts("D::delete");
    ::operator delete(p);
  }
};
struct E : B {
  void log() { std::puts("E::log"); }
  void operator delete(E* p, std::destroying_delete_t) {
    p->log();
    p->~E();
    ::operator delete(p);
  }
};

int main() {
  B* bp = new D;
  delete bp;   // 打印 D::delete
  bp = new E;
  delete bp;   // 打印 E::log：由 E 的销毁型 operator delete 处理
}
```

在 Itanium ABI 中，这是通过删除析构函数（deleting destructor，修饰名中的 `D0`）实现的：`delete bp` 虚调用 `D0`，它先析构完整对象，再调用它所在类选定的 `operator delete`。

`E` 中的是 C++20 的**销毁型 operator delete**（destroying operator delete，[[g:destroying-operator-delete]]）：第一个形参是类指针而不是 `void*`，第二个形参是 `std::destroying_delete_t`。*delete-expression* 遇到它时不调用析构函数，由它自己负责析构和释放。对象后面紧跟着变长数据、要先读出大小才能释放的类，可以用它。

注 2 说明虚析构函数对数组的 `delete[]` 不起作用。通过基类指针 `delete[]` 一个派生类数组是未定义行为（[[expr.delete]]），元素大小不同，连指针运算都是错的：

```cpp title="array-delete-ub.cpp" ub
struct B { virtual ~B() = default; };
struct D : B { int extra[4]; };

int main() {
  B* bp = new D[3];
  delete[] bp;   // UB: 静态类型与动态类型不同
}
```

[[class.free#5]] 访问检查按静态类型进行，即使实际执行的是另一个解分配函数。在上面的 `virtual-delete.cpp` 中，如果 `B::operator delete` 是 `private` 的，`delete bp;` 就非良构，尽管运行时实际调用的是 `D::operator delete`。

[[class.free#6]] 没有显式 *noexcept-specifier* 的解分配函数不抛出异常。

## 嵌套类 [class.nest]

[[class.nest#1]] 在另一个类里声明的类叫**嵌套类**。嵌套类是外围类的成员，受访问控制，也能访问外围类的私有成员（[[class.access.nest]]）。但嵌套类的对象和外围类的对象没有联系，不像 Java 的非静态内部类那样隐式持有外围对象。下例改编自标准例 1：

```cpp title="nested-access.cpp" error
int x;
int y;

struct enclose {
  int x;
  static int s;

  struct inner {
    void f(int i) {
      int a = sizeof(x);  // OK: sizeof 的操作数不求值
      x = i;              // error: 没有 enclose 对象
      s = i;              // OK: enclose::s
      ::x = i;            // OK: 全局 x
      y = i;              // OK: 全局 y
      (void)a;
    }
    void g(enclose* p, int i) {
      p->x = i;           // OK: 通过对象访问
    }
  };
};

inner* p = 0;             // error: 须写 enclose::inner
```

`x = i` 中，名字查找找到 `enclose::x`，因为嵌套类的作用域在外围类之内。但非静态成员需要对象，这里的 `this` 是 `inner*`，不是 `enclose*`，所以出错。`sizeof(x)` 能通过，是因为在不求值的操作数里可以不经对象指名非静态数据成员（[[expr.prim.id]]）。

[[class.nest#2]] 嵌套类可以在外围类里定义，也可以在外围的命名空间里定义（`class E::I2 { };`）。借助这一点可以实现一种 Pimpl：头文件里只前置声明私有的嵌套类，到实现文件里再定义。

[[class.nest#3]] 嵌套类中定义的友元函数，对外围类的成员没有特殊的访问权。

## 实现视角

!!! impl "成员函数与 ABI"
    - 在 Itanium ABI 中，非静态成员函数就是以 `this` 为第一个参数的普通函数。修饰名中编码了 cv 和引用限定，如 `_ZNK1S3getEv` 中的 `K` 表示 `const`，引用限定 `&`、`&&` 分别编码为 `R`、`O`。
    - 显式对象成员函数本质上是以对象为第一个参数的函数，修饰名与隐式对象成员函数不同，`&S::f` 是普通函数指针。
    - 静态数据成员是普通的全局变量。`inline` 的静态数据成员在 ELF 上作为 COMDAT 发出，由链接器去重。

!!! impl "位域的读写"
    写位域要对整个分配单元做读、改、写：加载、移位、掩码、存回。所以标准把相邻的位域算作同一个内存位置，并发写它们是数据竞争。零宽位域或插在中间的非位域成员能把它们分到不同的内存位置，这时编译器不能生成会覆盖相邻位域的代码。

## 历史与演进

!!! history "历史与演进"
    - C++98 只允许 `static const` 整型和枚举成员在类内初始化。类内定义的成员函数是 inline 的。`int` 位域的符号性与 C 一样由实现定义。
    - C++11 加入非静态数据成员的默认成员初始化器、引用限定、`constexpr` 静态数据成员和 `override`/`final`。嵌套类成为外围类的成员，因而能访问外围类的私有成员。
    - C++14 规定 `int` 位域是有符号的，有默认成员初始化器的类也可以是聚合体。
    - C++17 加入 inline 变量，`static inline` 数据成员可以在类内定义；`constexpr` 静态数据成员隐式 inline，类外的重声明被弃用。
    - C++20 允许位域有默认成员初始化器，加入 `[[no_unique_address]]` 和销毁型 `operator delete`；具名模块里类内定义的成员函数不再隐式 inline。
    - C++23 加入显式对象成员函数（[[P0847R7]]），成员布局不再按访问区段重排（[[P1847R4]]），`operator()` 和 `operator[]` 可以是静态的。
    - C++26 加入 `friend Ts...;`、成员声明上的契约说明符、`consteval` 块和数据成员描述（反射）。当前草案还规定了引用成员的布局与指针相同（[[class.mem#7]]）。

## 常见误解

!!! pitfall "以为类内的 `static const int` 就是定义"
    它被 odr-use 时（绑定引用、取地址、传给 `std::max` 这类按引用接收参数的函数）需要类外定义，否则是 IFNDR，常见的表现是只在 `-O0` 下出现的链接错误。C++17 起改用 `static constexpr` 或 `static inline`。

!!! pitfall "以为 `&&` 成员函数里 `*this` 是右值"
    `*this` 总是左值。要把对象当作右值传下去，写 `std::move(*this)`，或者改用显式对象形参 `this Self&& self` 配合 `std::forward<Self>(self)`。

!!! pitfall "用位域描述硬件寄存器"
    位的分配顺序、能否跨越分配单元、对齐方式都由实现定义。要跨编译器、跨架构移植的代码，应该用显式的移位和掩码。

!!! pitfall "在外围类里对嵌套类用类型特征"
    嵌套类的默认成员初始化器要到外围类结束后才处理，在那之前求出的类型特征可能是错的，而且结果会被缓存，见上文。

## 思考题

!!! question "思考题 1"
    下面的类定义中哪些行有问题？

    ```cpp
    struct S {
      using F = int(int) const;
      F f;                              // (1)
      static constexpr int n = m();     // (2)
      static constexpr int m() { return 1; }
      int g(int x = m()) { return x; }  // (3)
      int arr[m()];                     // (4)
    };
    ```

<details markdown="1">
<summary>答案</summary>

- (1) OK。用带 `const` 的函数类型别名声明成员函数，等价于 `int f(int) const;`（[[class.mfct#4]]）。
- (2) 错误。静态数据成员的类内初始化器不是完整类上下文，这里 `m` 还没有声明。即使把 `m` 移到前面也不行：`m` 的函数体是完整类上下文，要到类结束后才处理，在类里用它做常量求值时，它还没有定义。
- (3) OK。默认实参是完整类上下文，可以用 `m`。
- (4) 错误。数组边界不是完整类上下文，而且和 (2) 一样，`m` 在类结束前不能用于常量求值。
</details>

!!! question "思考题 2"
    `struct A { int a; char b; };` 和 `struct B { int x; char y; short z; };` 放在一个联合体 `u` 里，`B` 是活跃成员时，读 `u.a.b` 合法吗？读 `u.a.a` 呢？如果把 `A` 的第一个成员改成 `alignas(8) int a;` 呢？

<details markdown="1">
<summary>答案</summary>

`A` 与 `B` 的公共初始序列是 `{a, b}` 和 `{x, y}`：`int` 对 `int`、`char` 对 `char`，类型布局兼容，对齐也相同。所以 `u.a.a`、`u.a.b` 都可以读，效果如同读 `u.b.x`、`u.b.y`（[[class.mem#30]]）。

如果 `A::a` 是 `alignas(8) int`，第一对成员的对齐要求不同，不满足 [[class.mem#27.2]]，公共初始序列为空，两个都不能读，读了是 UB。`alignas(8)` 确实会改变 `A` 的布局，所以这个条件不是多余的。
</details>

!!! question "思考题 3"
    为什么类专属的 `operator delete` 按静态类型检查访问权（[[class.free#5]]），而不检查运行时实际调用的那个？

<details markdown="1">
<summary>答案</summary>

访问控制是编译期的检查。编译器在 `delete bp;` 处只知道 `bp` 的静态类型是 `B*`，不知道运行时的动态类型，也就不知道会调用哪个解分配函数，只能检查按静态类型找到的 `B::operator delete`。实际调用的 `D::operator delete` 是从 `D` 的虚析构函数里调用的，是 `D` 的成员访问 `D` 自己的成员，总是可以访问。虚函数的访问规则也是这样，按调用处的静态类型检查（[[class.access.virt]]）。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 成员集合 | 由成员规格一次确定，不能在别处添加；成员不能重复声明（嵌套类、不透明枚举除外） |
| 完整类上下文 | 函数体、默认实参、默认模板实参、`noexcept`、契约说明符、默认成员初始化器：能看到整个类，类是完整的 |
| 默认成员初始化器 | 只能用 `=` 或 `{}`；其中的 `consteval` 调用在使用它的构造函数处求值 |
| 布局 | 后声明的成员地址更高，C++23 起与访问控制无关；引用成员的布局与指针相同 |
| 公共初始序列 | 两个标准布局 struct 开头布局兼容的一段，可以通过联合体的非活跃成员读取 |
| 首成员地址 | 标准布局类对象与它的第一个非位域成员、各基类子对象指针可互转换 |
| 成员函数 | 全局模块中类内定义即 inline；cv 和引用限定决定隐式对象形参；C++23 可以写显式对象形参 |
| 静态成员 | 没有 `this`；非 inline 静态数据成员的类内声明不是定义；`inline`、`constexpr` 的可以在类内定义 |
| 位域 | 整型或枚举；布局由实现定义；没有地址；无名位域不是成员；零宽位域从下一个分配单元开始 |
| 类专属 new/delete | 总是静态的；有虚析构函数时 `delete` 按动态类型选择；访问按静态类型检查；`delete[]` 不多态 |
| 嵌套类 | 是外围类的成员，但两者的对象没有隐式关联 |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶21 这一段和后面两段都是注或例。这一段指出非静态成员的使用限制见 [[expr.prim.id]]。

¶22 说明非静态成员函数的类型就是普通的函数类型，非静态数据成员的类型就是普通的对象类型，没有专门的成员函数类型或数据成员类型；成员指针类型 `int S::*` 是另一回事（[[dcl.mptr]]）。

¶23 用一个二叉树节点 `tnode` 演示了类的定义和成员访问。

[[class.static.mfct#1]] 是一个注，说明 [[class.mfct]] 的规则适用于静态成员函数。

</details>
