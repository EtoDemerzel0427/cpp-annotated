---
title: 候选函数与实参列表
summary: 每种语境怎样构造候选函数集与实参列表：隐式对象形参与隐含对象实参、函数调用与代理调用函数、构造函数、转换函数、引用直接绑定、列表初始化的两阶段决议。
status: draft
covers: over.match.funcs.general, over.match.call, over.match.call.general, over.call.func, over.call.object, over.match.ctor, over.match.copy, over.match.conv, over.match.ref, over.match.list
papers: P0847R7
related: over.match, over.match.oper, over.match.class.deduct, over.match.viable, dcl.init, dcl.init.list, class.conv
tags: 重载决议, 初始化
updated: 2026-10-17
---

[[over.match]] 说"每种语境以自己的方式确定候选函数集和实参列表"，本页就是这些"方式"的集合。它是重载决议的**输入端**：候选集里没有的函数永远不可能被选中，实参列表里多出或少了一个"对象实参"，整个比较就会不同。

本页覆盖 [over.match.funcs] 下除运算符（[[over.match.oper]]）与类模板实参推导（[[over.match.class.deduct]]）以外的全部子条款：

| 子条款 | 语境 | 本页小节 |
|---|---|---|
| [over.match.funcs.general] | 通则：隐式对象形参、模板候选、被排除的候选 | §1 |
| [over.match.call] | `f(args)`：指名函数、取地址的重载集 | §2 |
| [over.call.func] | 限定/非限定调用、隐含对象实参 | §2 |
| [over.call.object] | `obj(args)`：`operator()` 与代理调用函数 | §3 |
| [over.match.ctor] | 直接/默认初始化选构造函数 | §4 |
| [over.match.copy] | 拷贝初始化中的用户定义转换 | §5 |
| [over.match.conv] | 类类型 → 非类类型的转换函数 | §6 |
| [over.match.ref] | 引用直接绑定到转换函数结果 | §7 |
| [over.match.list] | 列表初始化：先 `initializer_list` 构造函数，再全部构造函数 | §8 |

## §1 通则 [over.match.funcs.general]

### 这些"变换"只是说明手段（¶1）

¶1 后面各子条款会把源代码"改写"成别的形式（比如把 `a->f()` 规范化为 `(*a).f()`，把运算符表达式改写为函数调用，构造"代理调用函数"）。这些变换**只用于描述**重载决议，实现不必真的这样做。读这些条款时要把它们当作数学模型，而不是编译器的实际步骤。

### 隐式对象形参与隐含对象实参（¶2–¶5）

重载决议要把成员函数和非成员函数放在**同一个实参列表**上比较（例如 `a + b` 既可能匹配 `A::operator+(B)`，也可能匹配 `operator+(A, B)`）。为此标准给成员函数补一个额外的第一形参：

¶2 候选集可以同时含成员与非成员函数。若成员函数是

- ¶2.1 非构造函数的**隐式对象成员函数**（implicit object member function，即没有显式 `this` 形参的非静态成员函数），或
- ¶2.2 **静态**成员函数，且实参列表中含有隐含对象实参，

则视其有一个额外的第一形参，称为**隐式对象形参**（implicit object parameter），代表调用该成员函数的那个对象。

¶3 对应地，语境在适当时构造的实参列表会以一个**隐含对象实参**（implied object argument）开头，表示要操作的对象。

¶4 隐式对象形参的类型：

| 成员函数声明 | 隐式对象形参类型 |
|---|---|
| `void f() cv;`（无 ref-qualifier） | `cv X&` |
| `void f() cv &;` | `cv X&` |
| `void f() cv &&;` | `cv X&&` |

其中 `X` 是该函数**直接**所属的类。两个例外：

- 转换函数被视为隐含对象实参所属类的成员（这样基类的 `operator int()` 在派生类对象上调用时，对象实参是恒等匹配而不是派生到基类转换）；
- 被派生类的 *using-declaration* 引入的非转换隐式对象成员函数，视为**派生类**的成员。

静态成员函数的隐式对象形参"匹配任何对象"——因为若选中它，对象会被丢弃。注 1 补充：不为它确定任何类型，也不为它计算转换序列（[[over.best.ics#8]] 规定它与任何标准转换序列"不分优劣"）。

using-declaration 那条规则看似琐碎，实则决定了很多调用的结果：

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

| 候选 | 对象实参 `d`（`D` 左值） | 实参 `1` |
|---|---|---|
| `B::f(int)`（视为 `D` 的成员） | → `D&`：恒等 | `int`→`int`：精确匹配 |
| `D::f(long)` | → `D&`：恒等 | `int`→`long`：整型转换 |

`B::f(int)` 在第二个实参上更好、第一个实参上相同，胜出。如果没有"视为派生类成员"这条规则，`B::f(int)` 的对象形参是 `B&`，`d` 到 `B&` 是派生到基类转换（Conversion 等级），两个候选就会各赢一个实参而歧义——*using-declaration* 也就失去了"把基类重载并入派生类"的意义。

¶5 隐含对象实参与普通实参在决议中**无从区分**；但隐式对象形参保有特殊身份：**不能对它应用用户定义转换**（[[over.best.ics#9]]）。另外，对**没有 ref-qualifier** 的隐式对象成员函数，即使隐式对象形参不是 const 引用，右值也能绑定上去（只要其他方面都能转换）。注 2：实参是右值这一点不影响 ICS 的排序。

```cpp
struct S {
  void f();          // 隐式对象形参 S&
  void g() &;        // 隐式对象形参 S&，有 ref-qualifier
  void h() &&;
};
void use() {
  S{}.f();           // OK：无 ref-qualifier，右值可以绑定到 S&（特许）
  S{}.g();           // error: g 有 & 限定，右值不能绑定到 S&
  S s;
  s.h();             // error: 左值不能绑定到 S&&
}
```

这条"右值可绑定到非 const 隐式对象形参"的特许是 C++98 遗留：那时没有 ref-qualifier，`std::string("a").append("b")` 之类在临时对象上调用非 const 成员函数的写法必须合法。C++11 引入 ref-qualifier 后，给成员函数加上 `&` 就能禁止它在右值上调用。

### 只允许一次用户定义转换（¶6）

¶6 除了列表初始化以外，一个隐式转换序列里**最多只有一次**用户定义转换，因此挑选"最佳用户定义转换"有特殊规则（[[over.match.best]]、[[over.best.ics]]）。

```cpp
struct T {
  T();
};
struct C : T {
  C(int);
};
T a = 1;   // error: 不会考虑 T(C(1))——那需要两次用户定义转换
```

`1 → C` 是一次用户定义转换（构造函数 `C(int)`），`C → T` 是派生到基类，看起来"一步就够"。但拷贝初始化 `T a = 1` 的候选是 `T` 的非 explicit 构造函数（[[over.match.copy]]），即 `T()` 和 `T` 的拷贝/移动构造函数；后者要求 `1 → const T&`，这需要先构造一个 `C` 再派生到基类转换——而 [[over.best.ics#4]] 规定此时**不考虑**用户定义转换序列。

### 转换函数作为候选（¶7）

¶7 在考虑用类 `S` 的转换函数来初始化 `T` 类型对象或引用的每种场合，候选包括：

- 在 `S` 中搜索 *conversion-function-id* `operator T` 的结果（可能找到转换函数**模板**的特化，经推导得到）；
- 以及 `S` 的每个**非模板**转换函数，只要它：在 `S` 中没有被隐藏（¶7.1）、产生一个**容许类型**（permissible type，¶7.2）、（对"非 explicit"那一组而言）不是 explicit 的（¶7.3）。

每种场合（[[over.match.copy]]、[[over.match.conv]]、[[over.match.ref]]）分别定义 explicit 与非 explicit 转换函数的容许类型集合。如果初始化的是对象，`cv U` 是容许类型时，`cv2 U`、`cv2 U&`、`cv2 U&&` 也是——转换函数返回 `const U&` 也能用来初始化一个 `U` 对象。若 explicit 转换函数的容许类型集为空，explicit 候选一律丢弃。

### 模板候选（¶8）

¶8 候选是函数模板时，用模板实参推导（[[temp.over]]、[[temp.deduct]]）生成候选特化。推导失败（包括 SFINAE）的模板**不产生候选**——它不是"不可行"，而是根本不在候选集里。

一个 C++20 细节：若构造函数模板或转换函数模板的 *explicit-specifier* 是值依赖的（`explicit(!std::is_convertible_v<U, T>)`），则**先推导**，再看生成的特化是否 explicit；若语境只接受非 explicit 候选而特化是 explicit 的，就从候选集移除。这让 `std::pair`、`std::optional`、`std::tuple` 这类"条件 explicit"构造函数可以写成一个模板，而不是两个靠 SFINAE 互斥的模板。

```cpp
#include <type_traits>
struct W {
  template<class U>
  explicit(!std::is_convertible_v<U, int>) W(U) {}
};
struct P { explicit operator int() const { return 0; } };
W a = 1;       // OK：is_convertible_v<int,int>，特化非 explicit
W b(P{});      // OK：直接初始化，explicit 候选也可用
W c = P{};     // error: 特化是 explicit 的，从拷贝初始化的候选集中移除
```

脚注 92 强调：推导之后，特化的形参类型已完全确定，此后（除非另有规定）**模板特化与非模板函数一视同仁**。模板身份只在最后的决胜规则里（[[over.match.best#2.4]]、[[over.match.best#2.5]]）才重新出现。

### 两类被排除的候选（¶9）

¶9 规定了两种**不进入候选集**的函数：

1. **被定义为删除的预置移动特殊成员函数**（移动构造、移动赋值）在所有语境下都不是候选。
2. 从类 `C` **继承**来的构造函数，若第一形参是"到 `cv1 P` 的引用"，在构造 `cv2 D` 且实参恰好一个、`C` 与 `P` 引用相关、`P` 与 `D` 引用相关时，不是候选。直观地说：**继承来的"拷贝/移动样"构造函数不能用来拷贝/移动派生类对象**。

```cpp run ok
struct A {
  A() {}
  A(A&&) {}                          // #2
  template<class T> A(T&&) {}        // #3
};
struct B : A {
  using A::A;
  B(const B&) {}                     // #4
  B(B&&) = default;                  // #5：因成员 x 不可移动而被定义为删除
  struct X { X() {} X(X&&) = delete; } x;
};
int main() {
  B b1;
  B b2 = static_cast<B&&>(b1);       // 调用 #4
}
```

- #5 被定义为删除，按第 1 条**不是候选**——否则它对右值是精确匹配，会被选中然后报"使用已删除函数"；排除它之后，`const B&` 的拷贝构造 #4 接手。这正是"不可移动的类型自动回退到拷贝"能够成立的原因（C++11 发布后由缺陷报告加入）。
- #2、#3 是继承来的构造函数，`A(A&&)`/`A(T&&)`（`T` 推导为 `B`）的第一形参都引用到与 `B` 引用相关的类型，按第 2 条不是候选。否则 #3 的 `B&&` 会是精确匹配，从而"用基类的转发构造函数去构造派生类"，只初始化了基类子对象。

## §2 函数调用语法 [over.match.call]

### 两种情况（[over.match.call.general] ¶1–¶2）

¶1 对 *postfix-expression* `( expression-list )`：

- 若 *postfix-expression* 指名至少一个函数或函数模板 → 按 [over.call.func]；
- 若它表示一个类类型对象 → 按 [over.call.object]。

¶2 若 *postfix-expression* 是**重载集的地址**（`(&f)(args)`、`(&S::f)(args)`），就用这个集合按上面的方法做决议，但**不加隐含对象实参**（注 1）；若选中的是隐式对象成员函数，程序非良构——取 `&S::f` 得到的是成员指针，不能直接调用。

### 指名函数的调用 [over.call.func]

¶1 关心的是 *postfix-expression* 中（可能被任意多层括号包围）最终含有指代函数的 *id-expression* 或 {{c++26}} *splice-expression* 的情形，分为**限定调用**（`a.f()`、`p->f()`）与**非限定调用**（`f()`）。

¶2 **限定调用**：`A->B` 视为 `(*A).B`，于是所有成员调用都规范化为"对象 `.` 名字"。候选集是类成员名字查找（[[class.member.lookup]]）的结果（或 splice 指定的集合）；实参列表是调用中的实参，**前面加上 `.` 左边的操作数作为隐含对象实参**。脚注 93 提醒：对象类型上的 cv 限定对 glvalue 与类 prvalue 都有意义——这就是 `const` 对象只能调用 `const` 成员函数的机制。

¶3 **非限定调用**：候选集是名字查找（[[basic.lookup]]，包括 ADL）的结果。它要么**全是非成员**，要么**全是某个类 `T` 的成员**（名字查找不会混合二者——类作用域找到成员就停，并且此时 ADL 不进行，见 [[basic.lookup.argdep]]）。

- 非成员、splice、或重载集地址：实参列表就是调用中的实参。
- 成员：加上一个隐含对象实参：
    - 若当前类是 `T` 或派生自 `T`，且 `this` 指代它：隐含对象实参是 `(*this)`（¶3.2）；但 {{c++26}} 若该调用出现在**构造函数的前置条件**或**析构函数的后置条件**里并选中非静态成员函数，非良构（¶3.1）——那时对象尚未/不再存在。
    - 否则（如在静态成员函数里、在无关类里）：若选中非静态成员函数 → 非良构（¶3.3）；否则用一个**虚构对象**（contrived object）作隐含对象实参（¶3.4）。脚注 94 解释：这个虚构对象只用来对上隐式对象形参，所有成员函数共享同一个隐式对象形参类型，因此它不会导致选择或拒绝某个函数。

```cpp
struct C {
  void m(int);
  static void m(double);
  static void s() {
    m(1.0);          // OK：静态 m(double)；隐含对象实参是虚构的 C 对象
    m(1);            // error: 选中非静态 m(int)，但这里没有 this
  }
};
```

第二个调用值得细品：虚构对象让非静态的 `m(int)` **参与竞争并胜出**（精确匹配），然后才发现没有 `this` 而报错。重载决议不会因为"非静态函数在这里调用不了"就退而选 `m(double)`。

显式对象成员函数（C++23，[[P0847R7]]）与"隐含 `(*this)`"的配合：

```cpp
struct C {
  void f(this const C&);
  void g() const {
    f();             // OK：(*this).f()，*this 对上显式对象形参
    this->f();       // OK
    f(*this);        // error: 变成 (*this).f(*this)，实参多了一个
  }
  static void h() {
    C{}.f();         // OK
    f(C{});          // error: 虚构对象 + C{}，两个实参对一个形参，不可行
  }
};
```

注意 `f(C{})` 在静态成员函数里**不**等价于"把 `C{}` 当显式对象实参"：非限定调用总会补上隐含对象实参，显式对象形参只认这个隐含对象实参。

### 一组更刁钻的例子：取地址与 splice 的区别

标准例子（略作删减）展示了 `(C::c)()`、`(&C::c)()` 与 `c()` 的不同：

```cpp
struct C {
  void c(this const C&);    // #1
  void c() &;               // #2
  static void c(int = 0);   // #3

  void d() {
    c();                    // error: #2 与 #3 歧义（#1 也可行，但不比它们好）
    (C::c)();               // error: 同上，括号不改变"指名函数"的身份
    (&C::c)(C{});           // 选中 #1：取址形式不加隐含对象实参，C{} 对上显式对象形参
    (&C::c)();              // 选中 #3：不加对象实参，只有 #3 接受 0 个实参
    (&C::c)(*this);         // error: 选中 #2（隐式对象成员函数），而取址调用不允许
  }
};
```

`c()` 的分析：实参列表是 `(*this)`（左值 `C`）。#1 的对象形参 `const C&`，#2 的 `C&`，#3 静态、"匹配任何对象"。#2 优于 #1（[[over.ics.rank#3.2.6]]：绑定到更少 cv 的引用更好），但 #3 的对象实参与任何标准转换序列"不分优劣"（[[over.best.ics#8]]），所以 #2 与 #3 无法区分。

`(&C::c)(*this)` 中，三个候选的实参列表都是 `(*this)` 这一个实参，#2 的隐式对象形参对上它（`C&`，恒等），#1 的显式对象形参是 `const C&`，#3 要 `int`（不可行），#2 胜出——随后 ¶2 判非良构。

## §3 类对象的调用：代理调用函数 [over.call.object]

¶1 若函数调用的 *postfix-expression* `E` 求值为 `cv T` 类型的类对象，候选集**至少**包含 `T` 的函数调用运算符（在 `T` 的作用域中搜索 `operator()`）。

¶2 此外，对 `T` 中声明的每个**非 explicit** 转换函数，若其 cv 限定不少于 `cv`，且转换目标是"指向函数的指针""指向函数指针的引用"或"函数的引用"（函数类型为 `R(P1, …, Pn)`），就额外加入一个**代理调用函数**（[[g:surrogate-call-function|surrogate call function]]）：

```cpp nocheck
R call-function(conversion-type-id F, P1 a1, …, Pn an);
```

它的第一形参是转换函数的目标类型。基类中的这类转换函数也会产生代理函数，只要没被 `T` 中的声明隐藏。

¶3 实参列表是调用中的实参，**前面加上隐含对象实参 `E`**。与 `operator()` 比较时，`E` 对上其对象形参；与代理调用函数比较时，`E` 对上代理函数的**第一个形参**——即需要通过那个转换函数把对象转成函数指针/引用，这是一次**用户定义转换**。

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
  int i = a(1);     // 两个代理函数：call(fp1, int) 与 call(fp2, float)
  std::printf("%d\n", i);   // 1：第一个实参都是用户定义转换（不分优劣），第二个实参 int→int 胜出
}
```

为什么要有这种"代理"？C 程序员习惯让一个对象"像函数指针一样被调用"。没有代理函数，`a(1)` 根本不会考虑转换函数（函数调用语法不对对象做隐式转换）；有了它，转换到函数指针的类就能直接被调用，且能与 `operator()` 在同一场重载决议中公平比较。

因为对象实参到代理函数第一形参总是**用户定义转换**，而到 `operator()` 的对象形参是**标准转换**（通常是恒等），所以在其他实参相同的情况下 `operator()` 总是胜出。但代理函数仍可能在**其他实参**上赢回来，导致歧义：

```cpp
int g(int);
struct C {
  void operator()(long) const;
  using FP = int(*)(int);
  operator FP() const { return g; }
};
void use(const C& c) {
  c(1L);   // OK：operator()(long)，两个实参都不差
  c(1);    // error: 歧义——operator() 在对象实参上更好，代理函数在 int 实参上更好
}
```

!!! note "无捕获 lambda"
    无捕获 lambda 的闭包类型既有 `operator()`，又有到函数指针的非 explicit 转换函数（[[expr.prim.lambda.closure]]），所以调用它时代理调用函数也是候选。由于参数列表完全相同，`operator()` 凭对象实参上的标准转换总是胜出，代理函数从不被选中。

脚注 95 指出：这种构造可能产生彼此无法区分的代理函数（声明完全相同或只差返回类型），这时调用歧义。

## §4 构造函数初始化 [over.match.ctor]

¶1 类对象被**直接初始化**、**从同类或派生类表达式拷贝初始化**、或**默认初始化**时，由重载决议选构造函数：

| 初始化形式 | 候选 | 实参列表 |
|---|---|---|
| 直接初始化 `T t(a, b);`、`T(a)`、`static_cast<T>(a)` | `T` 的**全部**构造函数 | `a, b` |
| 默认初始化 `T t;`、`new T` | 全部构造函数 | 空 |
| 拷贝初始化 `T t = u;`（`u` 是 `T` 或派生类） | **非 explicit** 构造函数 | `u` |
| 拷贝列表初始化语境下的默认初始化 | 全部构造函数；但选中 explicit 的则非良构 | 空 |

最后一行是一个容易忽略的角落（C++11 之后由缺陷报告补上）：

```cpp
struct D { explicit D(); };
struct Agg { D d; };
D d1;                 // OK：默认初始化，explicit 构造函数可用
D d2{};               // OK：直接列表初始化
D d3 = {};            // error: 拷贝列表初始化 → 值初始化 → 选中 explicit D()
Agg a = {};           // error: 成员 d 从空列表拷贝初始化，同理
```

为什么"候选包括 explicit 但选中就报错"，而不是"干脆不把 explicit 当候选"？见 §8 的讨论——这是为了让拷贝列表初始化**不会因为 explicit 而静默改选别的构造函数**。

拷贝初始化只考虑非 explicit 构造函数：

```cpp
struct E {
  E() {}
  explicit E(const E&) {}
};
E a;
E b(a);      // OK：直接初始化
E c = a;     // error: 拷贝初始化，explicit 拷贝构造函数不是候选
```

## §5 拷贝初始化中的用户定义转换 [over.match.copy]

¶1 拷贝初始化 `cv1 T` 类型的对象（`T` 是类）、而初始化器**不是** `T` 或其派生类时（[[dcl.init]]），要用一次用户定义转换把初始化器变成 `T`。候选：

- ¶1.1 `T` 的**非 explicit 构造函数**；
- ¶1.2 若初始化器类型是类 `cv S`，还有 `S` 的转换函数：非 explicit 转换函数的容许类型是 `T` 及其派生类；explicit 转换函数的容许类型通常为空——**唯一例外**是：在 `cv3 T` 的**直接初始化**中，为了绑定到构造函数（以单个实参调用）的 `cv2 T&` 第一形参而初始化临时对象时，explicit 转换函数的容许类型与非 explicit 的相同。

¶2 两种情况下实参列表都只有一个：初始化器表达式。它与构造函数的第一形参或转换函数的对象形参比较。

经典的"构造函数 vs 转换函数"竞争：

```cpp
struct S;
struct T  { T();  T(const S&); };
struct S  { operator T(); };            // 非 const
struct S2;
struct T2 { T2(); T2(const S2&); };
struct S2 { operator T2() const; };     // const

void use() {
  S s;
  T t = s;      // OK：S::operator T()——s 绑定到 S&（隐式对象形参）优于绑定到 const S&
  S2 s2;
  T2 t2 = s2;   // error: 歧义——两个候选的实参都绑定到 const S2&，无从区分
}
```

这是"同一个转换写了两遍"的典型后果：构造函数和转换函数都能完成 `S2 → T2`，ICS 一样好，决胜规则也帮不上忙（它们既不是模板，也不是改写候选）。解决办法是只保留一个。

¶1.2 的例外让下面的代码合法（C++11 定稿前由一个缺陷报告加入）：

```cpp run ok
struct U {};
struct V { explicit operator U() const { return {}; } };
int main() {
  V v;
  U u(v);      // OK：直接初始化选 U 的拷贝/移动构造函数，其 const U&/U&& 形参所绑定的临时
               //     可以由 explicit operator U() 初始化
  (void)u;
}
```

直觉：`U u(v)` 是**显式**写出的直接初始化，程序员已经表达了"我要把 v 转成 U"的意图，应当允许 explicit 转换函数参与——就像 `static_cast<U>(v)` 一样。

## §6 由转换函数初始化非类对象 [over.match.conv]

¶1 用类类型表达式初始化**非类**类型 `cv T` 的对象时（`int i = obj;`、`double d(obj);`），候选是转换函数：

- 非 explicit 转换函数的容许类型：能经**标准转换序列**转换到 `T` 的类型；
- **直接初始化**时，explicit 转换函数的容许类型：能经（可能平凡的）**限定转换**转换到 `T` 的类型；其余场合没有。

¶2 实参列表只有初始化器表达式，与转换函数的对象形参比较。

选择时还会用到 [[over.match.best#2.2]]：若两个转换函数在对象实参上不分高下，就比较"转换结果 → 目标类型"的第二个标准转换序列：

```cpp
struct A {
  operator int();
  operator double();
} a;
int   i = a;     // OK：operator int() 之后无需转换，优于 operator double() 之后 double→int
float x = a;     // error: 歧义——int→float 与 double→float 都是 Conversion 等级
long  l = a;     // error: 歧义——int→long 与 double→long 都是 Conversion 等级
```

explicit 转换函数只在直接初始化中可用，而 explicit 的容许类型只到限定转换为止——这使得 `explicit operator bool` 能用于 `if (p)`（上下文转换到 `bool` 被定义为直接初始化 `bool t(p);`），但不能悄悄变成 `int`：

```cpp
struct P { explicit operator bool() const { return true; } };
void use(P p) {
  if (p) {}          // OK：上下文转换 = 直接初始化 bool t(p)
  bool b1(p);        // OK：直接初始化
  bool b2 = p;       // error: 拷贝初始化，explicit 转换函数不是候选
  int  n(p);         // error: 直接初始化，但 bool→int 是整型提升，不是限定转换
}
```

最后一行正是 C++11 "safe bool" 的全部意义：explicit 转换函数即便在直接初始化里也只允许"恰好到目标类型"，不会接上一个提升或转换。

## §7 引用直接绑定到转换函数结果 [over.match.ref]

¶1 按 [[dcl.init.ref]] 的规定，引用可以**直接绑定**到对初始化器调用转换函数的结果。设被初始化的引用是"到 `cv1 T` 的引用"：

- 设 `R` 是：转换为左值时，所有左值引用类型；转换为右值（或函数类型的左值）时，所有非引用类型和右值引用类型。
- 非 explicit 转换函数的容许类型：`R` 中形如 `cv T2` 或"到 `cv2 T2` 的引用"、且 `cv1 T` 与 `cv2 T2` **引用兼容**（reference-compatible）的成员；
- 直接初始化时，explicit 转换函数的容许类型：`R` 中 `T2` 可经（可能平凡的）限定转换转为 `T` 的成员；否则没有。

¶2 实参列表只有初始化器表达式。

```cpp run ok
struct Base {};
struct Derived : Base {};
struct Holder {
  Derived d;
  operator Derived&() { return d; }
};
int main() {
  Holder h;
  Base& r = h;        // 直接绑定：operator Derived&() 产生左值 Derived，Base 与 Derived 引用兼容
  return &r == &h.d ? 0 : 1;   // r 绑定到 h.d 本身，没有临时对象
}
```

"直接绑定"在这里很重要：如果转换函数返回的是**值**（`operator Derived()`），`const Base& r = h` 就绑定到一个临时对象；而 `Base& r = h` 会因为非 const 左值引用不能绑定右值而非良构。这一节只负责选择"能产生可直接绑定结果"的转换函数，非直接绑定的情形落回 [[over.match.copy]]/[[over.match.conv]] 去初始化临时对象。

## §8 列表初始化：两阶段决议 [over.match.list]

¶1 非聚合类类型 `T` 被列表初始化、且 [[dcl.init.list]] 规定按本节做重载决议时（或者按 [[over.ics.list]] 构造列表初始化序列时），分两阶段选构造函数：

- ¶1.1 **第一阶段**：若初始化列表**非空**，或 `T` **没有默认构造函数**，则只以 `T` 的**初始化列表构造函数**（第一形参为 `std::initializer_list<E>` 或其引用、其余形参都有默认实参，[[dcl.init.list#2]]）为候选，实参列表是**整个初始化列表作为单个实参**。
- ¶1.2 **第二阶段**：否则（列表为空且有默认构造函数），或第一阶段**没有可行的**初始化列表构造函数，再以 `T` 的**全部**构造函数为候选，实参列表是初始化列表的**各个元素**。

在拷贝列表初始化中，若选中 explicit 构造函数，非良构。

!!! std
    "In copy-list-initialization, if an explicit constructor is chosen, the initialization is ill-formed."

    在拷贝列表初始化中，若选中了 explicit 构造函数，则初始化非良构。

### 第一阶段的"贪婪"

只要有一个初始化列表构造函数**可行**，第二阶段就不会发生——哪怕别的构造函数匹配得好得多：

```cpp run ok
#include <vector>
#include <cassert>
int main() {
  std::vector<int> a(3);      // 直接初始化：vector(size_type)，3 个 0
  std::vector<int> b{3};      // 第一阶段：initializer_list<int> 可行 → 一个元素 3
  std::vector<int> c(3, 1);   // 3 个 1
  std::vector<int> d{3, 1};   // 两个元素 3、1
  assert(a.size() == 3 && b.size() == 1 && c.size() == 3 && d.size() == 2);
}
```

为什么设计成"先 `initializer_list` 后其他"的两阶段，而不是把所有构造函数放在一起比？因为放在一起比时，`vector<int>{3}` 中 `vector(size_type)` 需要 `int → size_t` 的转换，而 `initializer_list<int>` 是恒等——看似也会选后者；但对于 `vector<double>{3}`，`int → double` 与 `int → size_t` 都是 Conversion，就会**歧义**，或者在其他元素类型上得到违反直觉的结果。两阶段规则给出一个简单可预测的承诺："**花括号里的东西优先被当作元素**"。代价就是上面 `(3)` 与 `{3}` 的著名差异。

"可行"的门槛很低——窄化不会让初始化列表构造函数不可行（窄化在选定之后才检查），所以：

```cpp
#include <vector>
std::vector<int> v{1.5};     // error: 第一阶段选中 initializer_list<int>，double→int 是窄化
```

只有当元素**根本无法**隐式转换到 `E` 时，第一阶段才会落空：

```cpp run ok
#include <vector>
#include <string>
#include <cassert>
int main() {
  std::vector<std::string> v{3};      // 3 不能转成 string → 第一阶段无可行函数 → 第二阶段选 vector(size_type)
  assert(v.size() == 3);
}
```

### 空列表与默认构造函数

列表为空且有默认构造函数时直接进入第二阶段（实际上 [[dcl.init.list#3.5]] 在此之前就把它变成了值初始化）：

```cpp run ok
#include <initializer_list>
struct S {
  int which;
  S() : which(0) {}
  S(std::initializer_list<int>) : which(1) {}
};
int main() {
  S a{};        // 默认构造函数（值初始化）
  S b{{}};      // initializer_list 构造函数：列表非空，元素 {} 能转换为 int
  return a.which == 0 && b.which == 1 ? 0 : 1;
}
```

### 拷贝列表初始化与 explicit

与 [[over.match.ctor]]/[[over.match.copy]] 不同，拷贝列表初始化**把 explicit 构造函数也当候选**，选中了才报错（注 1）：

```cpp
struct X {
  explicit X(int);
  X(double);
};
X a = 1;      // OK：拷贝初始化只考虑非 explicit 构造函数 → X(double)
X b{1};       // OK：直接列表初始化 → X(int)
X c = {1};    // error: 拷贝列表初始化选中 explicit X(int)
```

`X a = 1` 与 `X c = {1}` 的区别是有意为之：如果 `= {1}` 也把 explicit 剔除，它就会**静默**改用 `X(double)`——作者把 `X(int)` 标成 explicit 的原意是"别隐式用我"，而不是"请改用别的构造函数"。报错比静默改选更安全。注 1 还说明：这一限制只在初始化是重载决议**最终结果**的一部分时才适用；在为别的函数的形参计算 ICS 时，选中 explicit 构造函数并不会使该函数不可行（[[over.ics.list]]）。

## 实现视角

!!! impl
    - **代理调用函数**：Clang 的诊断会把它们列为"conversion candidate of type 'int (*)(int)'"，GCC 列为"candidate: … <conversion>"，名称上能看出它们是虚构的候选。
    - **继承构造函数的排除**（¶9 第 2 条）和**删除的预置移动操作的排除**（¶9 第 1 条）在 Clang 中分别在添加候选时直接跳过，不会出现在"candidate not viable"列表里——这与"被删除的函数是候选"的一般规则形成对比，诊断里看不到它们是正常的。
    - **两阶段列表初始化**：编译器内部确实做两遍重载决议；Clang 的诊断在第一阶段失败而第二阶段也失败时，会把两轮的候选一起列出。

## 历史与演进

!!! history
    - **C++98**：隐式对象形参、虚构对象、代理调用函数、构造函数与转换函数的各类候选集已经成型。
    - **C++11**：ref-qualifier 使隐式对象形参可以是右值引用；列表初始化与两阶段决议（¶1.1/¶1.2）；被删除的预置移动操作不是候选；explicit 转换函数（`explicit operator bool`）。
    - **C++11 之后（缺陷报告）**：拷贝列表初始化语境下的默认初始化选中 explicit 构造函数时非良构。
    - **C++17**：继承构造函数改为"使基类构造函数在派生类的查找中可见"的新模型，并加入"拷贝/移动样的继承构造函数不是候选"的规则。
    - **C++20**：条件 explicit（`explicit(bool)`）及其"先推导再剔除"规则（¶8）。
    - **C++23**：显式对象形参（[[P0847R7]]）；¶2 用"隐式对象成员函数"重新措辞。
    - **C++26**：{{c++26}} *splice-expression* 指定候选集；构造函数前置条件 / 析构函数后置条件中隐式使用 `this` 调用非静态成员函数非良构（[over.call.func]/3.1，配合契约）。

## 陷阱

!!! pitfall "`vector<int>{n}` 不是 n 个元素"
    花括号优先匹配 `initializer_list` 构造函数。想要"n 个元素"，用圆括号。泛型代码里 `T{args...}` 与 `T(args...)` 语义可能截然不同，这也是 `std::make_unique` 等工厂函数统一用圆括号的原因。

!!! pitfall "把构造函数和转换函数都写上"
    `T(const S&)` 与 `S::operator T() const` 同时存在时，`T t = s;` 歧义；只是去掉 `const` 让其中一个"赢"，是在依赖 [[over.ics.rank#3.2.6]] 的细节，脆弱且难懂。只保留一个。

!!! pitfall "以为 explicit 在拷贝列表初始化中会被跳过"
    不会。`X x = {1};` 会选中 explicit 构造函数然后报错，而不是退而用一个非 explicit 构造函数。

## 思考题

!!! question "1. 在 `struct S { void f() const; static void f(int); };` 中，`s.f(1)`（`s` 是非 const 的 `S` 左值）选中哪个？为什么不会因为静态函数'没有对象形参'而产生歧义？"

<details markdown="1">
<summary>答案</summary>

只有 `static f(int)` 可行（`f() const` 实参个数不符）。静态成员函数在这里被视为有一个"匹配任何对象"的隐式对象形参（¶2.2、¶4），隐含对象实参 `s` 对上它，不计算转换序列，所以它与普通候选一样可行。若有两个候选都可行，静态函数的对象实参与另一个的对象实参"不分优劣"（[[over.best.ics#8]]），比较全看其余实参。
</details>

!!! question "2. 下面的代码为什么非良构？如何只改一个字符使它良构？"
    ```cpp nocheck
    #include <initializer_list>
    struct A { A(std::initializer_list<int>); explicit A(int, int); };
    A a = {1, 2.5};
    ```

<details markdown="1">
<summary>答案</summary>

第一阶段 `A(initializer_list<int>)` 可行（`2.5 → int` 有隐式转换，窄化不影响可行性），于是被选中，然后检查到 `2.5 → int` 是窄化，非良构（[[dcl.init.list#3.7]]）。改成 `A a = {1, 2};` 即可。注意：即使第一阶段落空，第二阶段选中 `explicit A(int, int)` 也会在拷贝列表初始化中非良构。
</details>

## 小结

!!! summary
    | 语境 | 候选 | 实参列表 | 特别规则 |
    |---|---|---|---|
    | `f(args)` 非成员 | 查找 + ADL 结果 | `args` | — |
    | `obj.f(args)` / 类内 `f(args)` | 成员查找结果 | `obj`/`(*this)`/虚构对象 + `args` | 隐式对象形参；无 `this` 时选中非静态函数非良构 |
    | `(&f)(args)` | 重载集 | `args`（无对象实参） | 选中隐式对象成员函数非良构 |
    | `obj(args)` | `operator()` + 代理调用函数 | `obj` + `args` | 代理函数的对象实参是用户定义转换 |
    | 直接/默认初始化 | 全部构造函数 | 初始化器 | — |
    | 拷贝初始化（同类） | 非 explicit 构造函数 | 初始化器 | — |
    | 拷贝初始化（异类） | 非 explicit 构造函数 + 转换函数 | 初始化器 | explicit 转换函数仅在特定直接初始化中可用 |
    | 非类目标 | 转换函数 | 初始化器 | explicit 仅限直接初始化 + 限定转换 |
    | 引用直接绑定 | 产生可直接绑定结果的转换函数 | 初始化器 | 同上 |
    | 列表初始化 | 先 `initializer_list` 构造函数，再全部 | 整个列表 / 各元素 | 拷贝列表初始化选中 explicit 非良构 |
