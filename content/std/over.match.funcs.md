---
title: 候选函数与实参列表
summary: 重载决议的输入从哪里来：函数调用、调用类对象、构造对象、用户定义转换、列表初始化等各种语境分别把哪些函数当候选，实参列表又是什么。
status: done
covers: over.match.funcs.general, over.match.call, over.match.call.general, over.call.func, over.call.object, over.match.ctor, over.match.copy, over.match.conv, over.match.ref, over.match.list
papers: P0847R7
related: over.match, over.match.oper, over.match.class.deduct, over.match.viable, dcl.init, dcl.init.list, class.conv
tags: 重载决议, 初始化
updated: 2026-10-19
---

!!! tldr
    - 成员函数在重载决议中多出一个隐式对象形参，调用的对象作为第一个实参与它匹配。这样成员函数和非成员函数可以在同一个实参列表上比较。
    - 隐式对象形参上不做用户定义转换；没有引用限定符的成员函数，右值也能绑定到它的非 const 隐式对象形参。
    - 类内的非限定调用 `f()` 会补上 `(*this)`；没有 `this` 时补一个虚构对象，选中非静态成员函数就报错，不会退而改选静态函数。
    - 初始化时选构造函数还是转换函数，取决于初始化的形式：拷贝初始化只看非 explicit 的，直接初始化看全部。
    - 列表初始化分两阶段：先只看 `std::initializer_list` 构造函数，没有可行的才看全部构造函数；拷贝列表初始化选中 explicit 构造函数时报错，而不是改选别的。

重载决议从一组**候选函数**（candidate functions）和一个**实参列表**出发，先筛出可行函数（[[over.match.viable]]），再挑出最佳的一个（[[over.match.best]]）。候选集里没有的函数不可能被选中；实参列表多一个或少一个对象实参，比较的结果也会不同。

候选集和实参列表怎么确定，取决于重载决议发生的语境：

| 语境 | 候选 | 实参列表 |
|---|---|---|
| 函数调用 `f(args)`、`obj.f(args)` | 名字查找的结果 | `args`，成员函数前面加对象 |
| 调用类对象 `obj(args)` | `operator()` 和代理调用函数 | `obj` 加 `args` |
| 选择构造函数 `T t(args)`、`T t;` | `T` 的构造函数 | `args` |
| 用户定义转换 `T t = s;`，`s` 不是 `T` | `T` 的构造函数和 `s` 的转换函数 | `s` |
| 转换到非类类型 `int i = s;` | `s` 的转换函数 | `s` |
| 引用直接绑定 `T& r = s;` | `s` 的转换函数 | `s` |
| 列表初始化 `T t{args}` | 先 `initializer_list` 构造函数，再全部 | 整个列表，或各个元素 |

运算符表达式和类模板实参推导也是重载决议的语境，分别见 [[over.match.oper]] 和 [[over.match.class.deduct]]。

## 隐式对象形参 [over.match.funcs.general]

`a + b` 既可能匹配成员 `A::operator+(B)`，也可能匹配非成员 `operator+(A, B)`。要把它们放在一起比较，两者的形参个数得对上。标准的办法是给成员函数补一个形参。

¶2 如果成员函数是构造函数以外的**隐式对象成员函数**（[[g:implicit-object-member-function|implicit object member function]]，没有显式 `this` 形参的非静态成员函数），或者是静态成员函数而实参列表里有对象实参，就认为它有一个额外的第一形参，叫做**隐式对象形参**（[[g:implicit-object-parameter|implicit object parameter]]），代表调用这个成员函数的对象。

¶3 相应地，语境构造的实参列表会以一个**隐含对象实参**（[[g:implied-object-argument|implied object argument]]）开头，表示要操作的对象。`obj.f(1)` 的实参列表就是 `(obj, 1)`。

¶4 隐式对象形参的类型由成员函数的 cv 限定和引用限定决定，其中 `X` 是函数直接所属的类：

| 成员函数声明 | 隐式对象形参类型 |
|---|---|
| `void f() cv;` 或 `void f() cv &;` | `cv X&` |
| `void f() cv &&;` | `cv X&&` |

静态成员函数的隐式对象形参匹配任何对象，因为选中它时对象会被丢弃。标准不为它确定类型，也不为它计算转换序列（注 1）；比较时它与任何转换序列不分优劣（[[over.best.ics#8]]）。

还有两个例外，都是为了让 `X` 取调用对象的类而不是函数声明所在的类：

- 转换函数视为隐含对象实参所属类的成员；
- 派生类用 *using-declaration* 引入的基类成员函数（转换函数除外），视为派生类的成员。

第二条决定了下面的结果：

```cpp run ok
#include <cstdio>
struct B {
  void f(int)  { std::puts("B::f(int)"); }
};
struct D : B {
  using B::f;
  void f(long) { std::puts("D::f(long)"); }
};
int main() {
  D d;
  d.f(1);   // B::f(int)
}
```

| 候选 | 对象实参 `d` | 实参 `1` |
|---|---|---|
| `B::f(int)`，视为 `D` 的成员 | 到 `D&`：恒等 | `int` 到 `int`：精确匹配 |
| `D::f(long)` | 到 `D&`：恒等 | `int` 到 `long`：整型转换 |

`B::f(int)` 在第二个实参上更好，胜出。如果它的隐式对象形参是 `B&`，`d` 到 `B&` 就是派生到基类转换，两个候选各赢一个实参，调用有歧义。*using-declaration* 也就无法把基类的重载并入派生类了。

### 隐式对象形参的两个特殊之处（¶5）

¶5 隐含对象实参与其他实参一视同仁，但隐式对象形参上**不能应用用户定义转换**（[[over.best.ics#9]]）。调用 `s.f()` 时，编译器不会先把 `s` 转换成别的类再调用那个类的成员。

另外，对没有引用限定符的成员函数，即使隐式对象形参是非 const 的左值引用，右值也能绑定上去：

```cpp error
struct S {
  void f();      // 隐式对象形参 S&
  void g() &;    // 隐式对象形参 S&，有引用限定符
  void h() &&;   // 隐式对象形参 S&&
};
void use() {
  S{}.f();       // OK：没有引用限定符，右值可以绑定到 S&
  S{}.g();       // error: g 有 & 限定，右值不能绑定
  S s;
  s.h();         // error: 左值不能绑定到 S&&
}
```

这条特许来自 C++98：那时还没有引用限定符，`std::string("a").append("b")` 这类在临时对象上调用非 const 成员函数的写法必须合法。C++11 起，给成员函数加上 `&` 就能禁止在右值上调用它。

## 函数调用 [over.call.func]

### 调用的两种形式（[over.match.call.general]）

¶1 对函数调用 `E(args)`，如果 `E` 指名一个或多个函数（或函数模板），按 [over.call.func] 处理；如果 `E` 是一个类对象，按下一节的 [over.call.object] 处理。

### 限定调用与非限定调用（[over.call.func] ¶1–¶3）

¶2 **限定调用**指 `a.f(args)` 和 `p->f(args)`。`p->f` 一律看作 `(*p).f`。候选集是在 `a` 的类里做成员名字查找（[[class.member.lookup]]）的结果，实参列表是 `args` 前面加上 `.` 左边的操作数，它就是隐含对象实参。对象类型上的 cv 限定在决议中有意义，`const` 对象只能调用 `const` 成员函数，靠的就是这一点。

¶3 **非限定调用**指 `f(args)`。候选集是普通名字查找的结果（[[basic.lookup]]），可能包括实参依赖查找。这个结果要么全是非成员函数，要么全是某个类 `T` 的成员：在类作用域里找到成员时，查找就停止，也不再做实参依赖查找（[[basic.lookup.argdep]]）。

- 候选是非成员函数时，实参列表就是 `args`。
- 候选是成员函数时，要补一个隐含对象实参。如果当前在 `T`（或其派生类）的非静态成员函数里，`this` 可用，补的是 `(*this)`（¶3.2）。
- 否则，例如在静态成员函数里，补的是一个 `T` 类型的**虚构对象**（contrived object），它只用来对上隐式对象形参（¶3.4）。如果决议选中了非静态成员函数，调用非良构（¶3.3）。

```cpp error
struct C {
  void m(int);
  static void m(double);
  static void s() {
    m(1.0);   // OK：选中静态的 m(double)
    m(1);     // error: 选中非静态的 m(int)，但这里没有 this
  }
};
```

第二个调用里，虚构对象让非静态的 `m(int)` 参与竞争并以精确匹配胜出，之后才发现没有 `this`。重载决议不会因为非静态函数在这里不能调用，就改选 `m(double)`。虚构对象与所有成员函数的隐式对象形参都同样匹配，所以它本身不会让哪个函数被选中或被排除（脚注 94）。

{{c++26}} 构造函数的前置条件里对象还没有构造完，析构函数的后置条件里对象已经销毁。在这两处写非限定调用并选中非静态成员函数，同样非良构（¶3.1）；写成 `this->f()` 则可以。

### 显式对象形参 {{c++23}}

C++23 允许把对象形参显式写出来：`void f(this const C& self)`（[[P0847R7]]）。这种**显式对象成员函数**的第一个形参本身就对应隐含对象实参：

```cpp error
struct C {
  void f(this const C&);
  void g() const {
    f();          // OK：(*this).f()
    this->f();    // OK
    f(*this);     // error: 实际是 (*this).f(*this)，多了一个实参
  }
  static void h() {
    C{}.f();      // OK
    f(C{});       // error: 虚构对象 + C{}，两个实参对一个形参
  }
};
```

在静态成员函数里，`f(C{})` 不会把 `C{}` 当作显式对象实参。非限定调用总会补上隐含对象实参，显式对象形参只对应它。

### 取地址后调用（[over.match.call.general] ¶2）

¶2 如果被调用的是一个重载集的地址，例如 `(&f)(args)` 或 `(&C::f)(args)`，就在这个集合上做决议，但不补隐含对象实参（注 1）。如果选中的是隐式对象成员函数，程序非良构，因为 `&C::f` 得到的是成员指针，不能直接调用。

标准的例子（节选）把几种写法放在一起：

```cpp error
struct C {
  void c(this const C&);    // #1
  void c() &;               // #2
  static void c(int = 0);   // #3

  void d() {
    c();              // error: #2 与 #3 歧义
    (C::c)();         // error: 同上，括号不改变指名函数的身份
    (&C::c)(C{});     // 选中 #1：不补对象实参，C{} 对应显式对象形参
    (&C::c)();        // 选中 #3：只有 #3 接受 0 个实参
    (&C::c)(*this);   // error: 选中 #2，而取地址调用不能调用隐式对象成员函数
  }
};
```

`c()` 的实参列表是 `(*this)`，一个 `C` 左值。#2 的隐式对象形参是 `C&`，#1 的显式对象形参是 `const C&`，绑定到 cv 限定更少的引用更好，所以 #2 优于 #1（[[over.ics.rank#3.2.6]]）。#3 是静态的，它的对象形参与任何转换序列不分优劣，所以 #2 与 #3 无法区分。

## 调用类对象 [over.call.object]

¶1 如果 `E(args)` 中的 `E` 是 `cv T` 类型的类对象，候选至少包括 `T` 的函数调用运算符 `operator()`。

¶2 此外，`T` 的每个非 explicit 转换函数，如果转换目标是函数指针、函数指针的引用或函数的引用，cv 限定也不少于 `cv`，就额外产生一个**代理调用函数**（[[g:surrogate-call-function|surrogate call function]]）。设目标的函数类型是 `R(P1, …, Pn)`，代理调用函数相当于：

```cpp
R call-function(conversion-type-id F, P1 a1, …, Pn an);
```

它的第一个形参是转换函数的目标类型。基类里的这类转换函数同样产生代理调用函数，只要没被 `T` 中的声明隐藏。

¶3 实参列表是 `args` 前面加上 `E`。与 `operator()` 比较时，`E` 对应其对象形参；与代理调用函数比较时，`E` 对应第一个形参 `F`，这需要经过转换函数，是一次用户定义转换。

```cpp run ok
#include <cstdio>
int f1(int)   { return 1; }
int f2(float) { return 2; }
typedef int (*fp1)(int);
typedef int (*fp2)(float);
struct A {
  operator fp1() { return f1; }
  operator fp2() { return f2; }
} a;
int main() {
  std::printf("%d\n", a(1));   // 1：经由 fp1 调用 f1
}
```

两个代理调用函数是 `call(fp1, int)` 和 `call(fp2, float)`。第一个实参都要经过用户定义转换，不分优劣；第二个实参上 `int` 到 `int` 胜出，所以调用 `f1`。

代理调用函数让能转换成函数指针的类对象可以直接调用，并且与 `operator()` 在同一次决议里比较。对象实参到 `operator()` 的对象形参通常是恒等转换，到代理调用函数则是用户定义转换，所以其他实参相同时 `operator()` 胜出。但代理调用函数可能在别的实参上占优，结果是歧义：

```cpp error
int g(int);
struct C {
  void operator()(long) const;
  using FP = int(*)(int);
  operator FP() const { return g; }
};
void use(const C& c) {
  c(1L);   // OK：operator()(long)
  c(1);    // error: 歧义：operator() 在对象实参上更好，代理调用函数在 int 实参上更好
}
```

无捕获 lambda 的闭包类型既有 `operator()`，又有到函数指针的非 explicit 转换函数（[[expr.prim.lambda.closure]]），所以调用它时代理调用函数也是候选。两者形参完全相同，`operator()` 凭对象实参总是胜出。

## 选择构造函数 [over.match.ctor]

¶1 类对象被直接初始化、默认初始化，或者从同类（或派生类）的表达式拷贝初始化时，用重载决议选择构造函数：

| 初始化形式 | 候选 | 实参列表 |
|---|---|---|
| 直接初始化：`T t(a, b);`、`T(a)`、`static_cast<T>(a)` | 全部构造函数 | `a, b` |
| 默认初始化：`T t;`、`new T` | 全部构造函数 | 空 |
| 拷贝初始化：`T t = u;`，`u` 的类型是 `T` 或其派生类 | 非 explicit 构造函数 | `u` |

拷贝初始化只考虑非 explicit 构造函数：

```cpp error
struct E {
  E() {}
  explicit E(const E&) {}
};
E a;
E b(a);    // OK：直接初始化
E c = a;   // error: 拷贝初始化，explicit 拷贝构造函数不是候选
```

拷贝列表初始化里的默认初始化是一个特例：所有构造函数都是候选，但选中 explicit 的就非良构。

```cpp error
struct D { explicit D(); };
struct Agg { D d; };
D d1;          // OK：默认初始化
D d2{};        // OK：直接列表初始化
D d3 = {};     // error: 拷贝列表初始化，选中了 explicit D()
Agg a = {};    // error: 成员 d 从空列表拷贝初始化，同理
```

## 用户定义转换 [over.match.copy]

### 只允许一次用户定义转换（[over.match.funcs.general] ¶6）

**用户定义转换**指调用一个转换构造函数或转换函数完成的类型转换。¶6 除列表初始化以外，一个隐式转换序列里最多只有一次用户定义转换，所以要专门的规则从多个可能的用户定义转换中挑一个。

```cpp error
struct T { T(); };
struct C : T { C(int); };
T a = 1;   // error: 不会考虑 T(C(1))
```

`1` 到 `C` 是一次用户定义转换，`C` 到 `T` 是派生到基类转换，看起来只差一步。但 `T a = 1` 的候选是 `T` 的非 explicit 构造函数，用 `1` 去初始化拷贝构造函数的 `const T&` 形参需要先构造一个 `C`，而 [[over.best.ics#4]] 规定这里不考虑用户定义转换。

### 构造函数与转换函数同台竞争（¶1–¶2）

¶1 拷贝初始化 `cv1 T` 类型的对象（`T` 是类），而初始化器的类型不是 `T` 或其派生类时，候选有两类：

- ¶1.1 `T` 的非 explicit 构造函数；
- ¶1.2 如果初始化器的类型是类 `cv S`，还有 `S` 的转换函数，只要它转换出的是 `T` 或 `T` 的派生类。

¶2 实参列表只有一个实参，就是初始化器。它与构造函数的第一个形参比较，或者与转换函数的对象形参比较。

```cpp error
struct S;
struct T  { T();  T(const S&); };
struct S  { operator T(); };          // 非 const
struct S2;
struct T2 { T2(); T2(const S2&); };
struct S2 { operator T2() const; };   // const

void use() {
  S s;
  T t = s;      // OK：选 S::operator T()
  S2 s2;
  T2 t2 = s2;   // error: 歧义
}
```

`T t = s` 中，`s` 绑定到转换函数的隐式对象形参 `S&`，比绑定到构造函数的 `const S&` 更好。`T2 t2 = s2` 中，两个候选的实参都绑定到 `const S2&`，无法区分。同一个转换写两遍（构造函数一次、转换函数一次），结果就是这样，只保留一个即可。

### 哪些转换函数是候选（[over.match.funcs.general] ¶7）

¶7 每当要考虑类 `S` 的转换函数来初始化 `T` 类型的对象或引用时，候选包括在 `S` 中查找 `operator T` 的结果，可能是由转换函数模板推导出的特化。此外，`S` 中每个满足以下条件的非模板转换函数也是候选：

- ¶7.1 在 `S` 中没有被隐藏；
- ¶7.2 转换结果是一个**容许类型**（[[g:permissible-type|permissible type]]）；
- ¶7.3 对于非 explicit 那一组，它本身不是 explicit 的。

每种语境分别规定 explicit 和非 explicit 转换函数的容许类型：上面的 [over.match.copy]，以及下面的 [over.match.conv] 和 [over.match.ref]。初始化对象时，如果 `cv U` 是容许类型，`cv2 U`、`cv2 U&`、`cv2 U&&` 也都是，所以返回 `const U&` 的转换函数也能用来初始化 `U` 对象。explicit 转换函数的容许类型集为空时，explicit 候选一律丢弃。

### explicit 转换函数的例外（¶1.2）

在 [over.match.copy] 里，explicit 转换函数通常没有容许类型。唯一的例外是：直接初始化 `cv3 T` 对象时，用单个实参调用构造函数，需要初始化一个临时对象去绑定构造函数的 `cv2 T&` 第一形参，这时 explicit 转换函数与非 explicit 的容许类型相同。

```cpp run ok
struct U {};
struct V { explicit operator U() const { return {}; } };
int main() {
  V v;
  U u(v);    // OK：直接初始化，选 U 的拷贝或移动构造函数，
             //     形参绑定的临时对象由 explicit operator U() 初始化
  (void)u;
}
```

`U u(v)` 是明确写出的直接初始化，程序员已经表达了把 `v` 转成 `U` 的意图，所以允许 explicit 转换函数参与，就像 `static_cast<U>(v)` 一样。

## 转换到非类类型 [over.match.conv]

¶1 用类类型的表达式初始化非类类型 `cv T` 的对象时，例如 `int i = obj;`、`double d(obj);`，候选是转换函数：

- 非 explicit 转换函数的容许类型：能经标准转换序列转换到 `T` 的类型；
- explicit 转换函数的容许类型：只在直接初始化中有，是能经限定转换（可以是平凡的）转换到 `T` 的类型，也就是说必须恰好转换出 `T`，最多差 cv 限定。

¶2 实参列表只有初始化器，与转换函数的对象形参比较。

两个转换函数在对象实参上打平时，比较转换结果到目标类型的第二个标准转换序列（[[over.match.best#2.2]]）：

```cpp error
struct A {
  operator int();
  operator double();
} a;
int   i = a;   // OK：operator int() 之后不需要转换
float x = a;   // error: 歧义：int 到 float、double 到 float 都是转换等级
long  l = a;   // error: 歧义：同上
```

explicit 转换函数只能精确转换到目标类型，所以 `explicit operator bool` 能用于 `if (p)`，却不会悄悄变成 `int`。`if` 的条件是上下文转换到 `bool`，定义为直接初始化 `bool t(p);`：

```cpp error
struct P { explicit operator bool() const { return true; } };
void use(P p) {
  if (p) {}     // OK：相当于直接初始化 bool t(p)
  bool b1(p);   // OK：直接初始化
  bool b2 = p;  // error: 拷贝初始化，explicit 转换函数不是候选
  int  n(p);    // error: 直接初始化，但 bool 到 int 是整型提升，不是限定转换
}
```

## 引用直接绑定到转换结果 [over.match.ref]

¶1 按 [[dcl.init.ref]] 的规定，引用可以直接绑定到转换函数的结果，不经过临时对象。设被初始化的是到 `cv1 T` 的引用：

- 要绑定左值时，考虑转换出左值引用类型的转换函数；要绑定右值时，考虑转换出非引用类型或右值引用类型的转换函数。
- 非 explicit 转换函数的容许类型：上述类型中，去掉引用后的 `cv2 T2` 与 `cv1 T` 引用兼容（reference-compatible，[[dcl.init.ref]]）的那些，也就是 `T2` 是 `T` 或其派生类，且 cv 限定不多于 `cv1`。
- explicit 转换函数的容许类型：只在直接初始化中有，要求 `T2` 能经限定转换转换到 `T`。

¶2 实参列表只有初始化器。

```cpp run ok
struct Base {};
struct Derived : Base {};
struct Holder {
  Derived d;
  operator Derived&() { return d; }
};
int main() {
  Holder h;
  Base& r = h;                  // 直接绑定：operator Derived&() 产生 Derived 左值
  return &r == &h.d ? 0 : 1;    // r 就绑定在 h.d 上，没有临时对象
}
```

如果转换函数返回的是值 `operator Derived()`，`const Base& r = h` 会绑定到一个临时对象，`Base& r = h` 则非良构，因为非 const 左值引用不能绑定右值。不能直接绑定的情形交给 [[over.match.copy]] 或 [[over.match.conv]] 去初始化临时对象。

## 列表初始化 [over.match.list]

¶1 非聚合类类型 `T` 被列表初始化时，分两个阶段选择构造函数：

- ¶1.1 第一阶段：如果初始化列表非空，或 `T` 没有默认构造函数，只以 `T` 的**初始化列表构造函数**为候选，也就是第一个形参是 `std::initializer_list<E>`（或其引用）、其余形参都有默认实参的构造函数（[[dcl.init.list]]）。整个初始化列表作为一个实参。
- ¶1.2 第二阶段：如果列表为空且有默认构造函数，或者第一阶段没有可行的函数，就以 `T` 的全部构造函数为候选，实参列表是初始化列表的各个元素。

### 花括号里的内容优先当作元素

只要有一个初始化列表构造函数可行，就不进入第二阶段，哪怕别的构造函数匹配得更好：

```cpp run ok
#include <vector>
#include <cassert>
int main() {
  std::vector<int> a(3);      // vector(size_type)：3 个 0
  std::vector<int> b{3};      // 第一阶段：initializer_list<int> 可行，一个元素 3
  std::vector<int> c(3, 1);   // 3 个 1
  std::vector<int> d{3, 1};   // 两个元素 3、1
  assert(a.size() == 3 && b.size() == 1 && c.size() == 3 && d.size() == 2);
}
```

如果把所有构造函数放在一起比较，`vector<double>{3}` 中 `int` 到 `double` 和 `int` 到 `size_t` 都是转换等级，结果会是歧义；换一种元素类型又可能得到另一种意外的结果。两阶段规则给出一个简单可预测的保证：花括号里的内容优先当作元素。代价是 `(3)` 和 `{3}` 的那个著名差异。

可行的门槛很低。窄化不会让初始化列表构造函数不可行，选定之后才检查窄化：

```cpp error
#include <vector>
std::vector<int> v{1.5};   // error: 选中 initializer_list<int>，double 到 int 是窄化
```

只有元素根本不能隐式转换到 `E` 时，第一阶段才会落空：

```cpp run ok
#include <vector>
#include <string>
#include <cassert>
int main() {
  std::vector<std::string> v{3};   // 3 不能转换成 string，进入第二阶段
  assert(v.size() == 3);           // 选中 vector(size_type)
}
```

列表为空而有默认构造函数时直接进入第二阶段。实际上 [[dcl.init.list#3.5]] 在此之前就已经把这种情况变成了值初始化：

```cpp run ok
#include <initializer_list>
struct S {
  int which;
  S() : which(0) {}
  S(std::initializer_list<int>) : which(1) {}
};
int main() {
  S a{};     // 默认构造函数
  S b{{}};   // 列表非空，元素 {} 能转换成 int：initializer_list 构造函数
  return a.which == 0 && b.which == 1 ? 0 : 1;
}
```

### 拷贝列表初始化与 explicit

!!! std
    "In copy-list-initialization, if an explicit constructor is chosen, the initialization is ill-formed."

    在拷贝列表初始化中，如果选中的是 explicit 构造函数，初始化非良构。

这与 [over.match.ctor]、[over.match.copy] 不同：那里拷贝初始化干脆不把 explicit 构造函数当候选。拷贝列表初始化则把它们当候选，选中了才报错（注 1）：

```cpp error
struct X {
  explicit X(int);
  X(double);
};
X a = 1;     // OK：拷贝初始化只考虑非 explicit 构造函数，选 X(double)
X b{1};      // OK：直接列表初始化，选 X(int)
X c = {1};   // error: 拷贝列表初始化选中了 explicit X(int)
```

`X a = 1` 和 `X c = {1}` 的区别是有意的。如果 `= {1}` 也把 explicit 构造函数剔除，它就会静默改用 `X(double)`。作者把 `X(int)` 标成 explicit，本意是不允许隐式使用它，而不是让编译器换一个构造函数。报错比静默改选更安全。

注 1 还说明，这一限制只在这次初始化是重载决议最终结果的一部分时才适用。为另一个函数的形参构造转换序列时，选中 explicit 构造函数不会让那个函数不可行（[[over.ics.list]]），例子见 [[over.match.viable]]。

## 模板候选与被排除的候选 [over.match.funcs.general]

### 模板候选（¶8）

¶8 候选是函数模板时，用模板实参推导（[[temp.over]]、[[temp.deduct]]）生成特化作为候选。推导失败的模板不产生候选：它不是不可行，而是根本不在候选集里。推导完成后，特化的形参类型已经完全确定，此后除另有规定外，特化与非模板函数一视同仁（脚注 92）。模板身份只在最后的决胜规则里才重新起作用（[[over.match.best#2.4]]、[[over.match.best#2.5]]）。

构造函数模板或转换函数模板的 `explicit(条件)` 依赖模板实参时，先推导，再看生成的特化是不是 explicit。如果语境只接受非 explicit 的候选而特化是 explicit 的，就把它从候选集中移除。`std::pair`、`std::optional` 这类条件 explicit 的构造函数因此只需写一个模板：

```cpp error
#include <type_traits>
struct W {
  template<class U>
  explicit(!std::is_convertible_v<U, int>) W(U) {}
};
struct P { explicit operator int() const { return 0; } };
W a = 1;      // OK：int 可以隐式转换到 int，特化不是 explicit
W b(P{});     // OK：直接初始化，explicit 候选也可用
W c = P{};    // error: 特化是 explicit 的，从拷贝初始化的候选集中移除
```

### 两类不当候选的函数（¶9）

¶9 有两类函数在任何语境下都不进入候选集：

1. 被定义为删除的预置移动构造函数和移动赋值运算符；
2. 从基类 `C` 继承来的、第一个形参是到 `cv1 P` 的引用的构造函数，在用恰好一个实参构造 `cv2 D` 对象、且 `C` 与 `P` 引用相关、`P` 与 `D` 引用相关时。直观地说，继承来的形似拷贝或移动的构造函数，不能用来拷贝或移动派生类对象。

```cpp run ok
#include <cstdio>
struct A {
  A() {}
  A(A&&) { std::puts("#2"); }
  template<class T> A(T&&) { std::puts("#3"); }
};
struct B : A {
  using A::A;
  B(const B&) { std::puts("#4"); }
  B(B&&) = default;   // #5：成员 x 不可移动，被定义为删除
  struct X { X() {} X(X&&) = delete; } x;
};
int main() {
  B b1;
  B b2 = static_cast<B&&>(b1);   // 打印 #4
}
```

- #5 被定义为删除，按第 1 条不是候选。否则它对右值是精确匹配，会被选中，然后报告使用了已删除的函数。排除它之后由拷贝构造函数 #4 接手，不可移动的类型因此能自动退回到拷贝。
- #2 和 #3（`T` 推导为 `B`）是继承来的构造函数，第一个形参都引用与 `B` 引用相关的类型，按第 2 条不是候选。否则 #3 的 `B&&` 是精确匹配，结果是用基类的转发构造函数构造派生类对象，只初始化了基类子对象。

本机 Clang 23 对 #5 给出 `-Wdefaulted-function-deleted` 警告，程序照常编译并打印 `#4`。

<details class="fine" markdown="1"><summary>其余条文</summary>

[over.match.funcs.general] ¶1：各子条款对源代码做的变换（把 `a->f()` 改写为 `(*a).f()`、把运算符改写为函数调用、构造代理调用函数等）只是描述重载决议的手段，实现不必真的这样做。

[over.call.object] 脚注 95：代理调用函数之间可能无法区分（声明完全相同，或只差返回类型），这时调用有歧义。

</details>

## 历史与演进

!!! history
    - C++98 已经有隐式对象形参、虚构对象、代理调用函数，以及构造函数与转换函数的各类候选集。
    - C++11 加入了引用限定符（隐式对象形参可以是右值引用）、列表初始化及其两阶段决议、explicit 转换函数，以及被删除的预置移动操作不当候选的规则。
    - C++17 改用新的继承构造函数模型，并加入继承来的形似拷贝或移动的构造函数不当候选的规则。
    - C++20 加入条件 explicit（`explicit(bool)`）及其先推导、再剔除的规则。
    - C++23 加入显式对象形参（[[P0847R7]]）。
    - C++26 允许用 *splice-expression* 指定候选集，并禁止在构造函数前置条件、析构函数后置条件里以隐含的 `this` 调用非静态成员函数。

## 常见误解

!!! pitfall "`vector<int>{n}` 是 n 个元素"
    花括号优先匹配 `initializer_list` 构造函数，`vector<int>{n}` 是一个元素。要 n 个元素，用圆括号。泛型代码里 `T{args...}` 和 `T(args...)` 的含义可能完全不同，`std::make_unique` 等工厂函数因此统一用圆括号。

!!! pitfall "拷贝列表初始化会跳过 explicit 构造函数"
    不会。`X x = {1};` 选中 explicit 构造函数后报错，而不是改用一个非 explicit 构造函数。

!!! pitfall "构造函数和转换函数都写上更保险"
    `T(const S&)` 与 `S::operator T() const` 同时存在时，`T t = s;` 有歧义。靠去掉 `const` 让其中一个胜出，依赖的是引用绑定的细节，脆弱难懂。只保留一个。

## 思考题

!!! question "思考题 1"
    在 `struct S { void f() const; static void f(int); };` 中，`s.f(1)`（`s` 是非 const 的 `S` 左值）选中哪个函数？静态函数没有真正的对象形参，会不会因此产生歧义？

<details markdown="1">
<summary>答案</summary>

只有静态的 `f(int)` 可行，`f() const` 实参个数不对。静态成员函数在这里视为有一个匹配任何对象的隐式对象形参（¶2.2、¶4），对象实参 `s` 与它对应，不计算转换序列。如果两个候选都可行，静态函数在对象实参上与另一个不分优劣（[[over.best.ics#8]]），比较完全取决于其余实参。
</details>

!!! question "思考题 2"
    下面的代码为什么非良构？只改一个字符怎样让它良构？
    ```cpp
    #include <initializer_list>
    struct A { A(std::initializer_list<int>); explicit A(int, int); };
    A a = {1, 2.5};
    ```

<details markdown="1">
<summary>答案</summary>

第一阶段 `A(initializer_list<int>)` 可行，因为 `2.5` 能隐式转换到 `int`，窄化不影响可行性。它被选中，然后发现 `2.5` 到 `int` 是窄化，非良构（[[dcl.init.list#3.7]]）。改成 `A a = {1, 2};` 即可。即使第一阶段落空，第二阶段选中 `explicit A(int, int)` 在拷贝列表初始化中同样非良构。
</details>
