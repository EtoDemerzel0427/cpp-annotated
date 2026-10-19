---
title: 默认实参
summary: 默认实参是在调用点补上的表达式：每次调用都求值，名字却在声明处查找；它属于声明而不属于函数类型，可以在同一作用域的后续声明里补充，但不能重复给出。
status: draft
related: dcl.fct, expr.call, over.match.viable, temp.inst, class.virtual, basic.def.odr, expr.const.imm, support.srcloc
tags: 默认实参, 函数, 虚函数, source_location
updated: 2026-10-19
---

!!! tldr
    - 调用时末尾的实参缺失，编译器就在调用点补上默认实参。每次这样调用都重新求值一次。
    - 默认实参里的名字在它写下的地方查找，与调用点无关。`std::source_location::current()` 是例外中的例外，能拿到调用点的位置。
    - 默认实参不是函数类型的一部分：函数指针、`std::function`、typedef 都看不到它。
    - 同一作用域里的后续声明可以补充默认实参，但不能重复给出，值相同也不行。块作用域里的声明拥有自己独立的一套。
    - 虚函数调用按指针或引用的静态类型选默认实参，覆盖函数不会继承基类的默认实参。

## 在调用点补上的表达式（¶1–2、¶9）

```cpp run title="default-each-call.cpp" ok
#include <cstdio>
int counter = 0;
int next() { return ++counter; }
void f(int a = next()) { std::printf("%d ", a); }

int main() {
  f(); f(); f(10);   // 输出 1 2 10
}
```

¶1 函数形参声明里 `=` 后面的初始化器叫**默认实参**（[[g:default-argument|default argument]]）。模板形参的 `= …` 是默认模板实参，归 [[temp.param]] 管。注 1 说明，调用时如果末尾的实参缺失，就用默认实参补上（[[expr.call]]）。¶2 的例子：`void point(int = 3, int = 4);` 之后，`point(1)` 等价于 `point(1, 4)`，`point()` 等价于 `point(3, 4)`。

¶9 每次调用省略了对应实参，默认实参都会重新求值一次。上面的 `f()` 两次调用 `next()`，得到 1 和 2。Python 的默认参数在 `def` 时只求值一次，C++ 不是这样。

可以把默认实参想成附在某个声明上的一段表达式。编译器在调用点把这段表达式补进实参列表，被调函数本身并不知道实参是不是来自默认值。本页的其余规则都由这个模型推出。

## 名字在声明处查找（¶5）

```cpp run title="default-lookup.cpp" ok
#include <cstdio>
int a = 1;
int f(int x) { return x * 10; }
int g(int x = f(a)) { return x; }   // a 已经确定是 ::a

int main() {
  a = 2;
  {
    int a = 3;                       // 不影响默认实参
    (void)a;
    std::printf("%d\n", g());        // g(f(::a))，输出 20
  }
}
```

¶5 默认实参里的名字在默认实参出现的地方查找，语义检查也在那里做，与调用点无关。不过表达式要到调用时才求值，所以读到的是 `::a` 当时的值 2。

默认实参受到的语义约束，与用它初始化一个形参类型的变量相同，采用复制初始化（[[dcl.init]]）。因此 `explicit` 构造函数不能用来做默认实参的隐式转换：`struct E { explicit E(int); };` 之后，`void k(E e = 1);` 非良构。

### 即时调用推迟到调用点

`consteval` 函数的调用叫**即时调用**（[[g:immediate-invocation|immediate invocation]]，[[expr.const.imm]]），一般必须在出现的地方就是常量表达式。第 5 段规定了一个例外：默认实参里潜在求值的即时调用，在声明处既不求值，也不检查是否是常量表达式。

这条规则是为 `std::source_location::current()` 准备的。它是 `consteval` 函数，如果在声明处求值，得到的就是声明的位置。推迟到调用点后，[[support.srcloc]] 让它返回调用点的位置：

```cpp run title="source-location.cpp" ok
#include <cstdio>
#include <source_location>

void log(const char* msg,
         std::source_location loc =
             std::source_location::current()) {
  std::printf("%s @ line %u\n", msg,
              static_cast<unsigned>(loc.line()));
}

int main() {
  log("hello");   // 打印这一行的行号，而不是 log 的
}
```

### 类和模板里的默认实参

注 3 说明，默认实参是**完整类语境**（[[g:complete-class-context|complete-class context]]，[[class.mem]]）：成员函数的默认实参要等类定义结束后才分析，所以可以用后面才声明的成员，也可以对本类做 `sizeof`。访问检查照常进行（[[class.access]]）。

模板化函数的默认实参，名字查找和语义检查按 [[temp.inst]] 进行，也就是用到时才实例化。所以即使 `T` 没有默认构造函数，`T t = T()` 这样的默认实参也不妨碍类模板实例化，只要调用时不省略这个实参。

```cpp run title="complete-class.cpp" ok
struct S {
  void f(int x = later);          // later 在下面才声明
  void g(int x = sizeof(S));      // 此时 S 已经完整
  static constexpr int later = 5;
};
void S::f(int) {}
void S::g(int) {}

template<class T>
struct TT { void m(T t = T()) { (void)t; } };
struct NoDef { NoDef(int) {} };

int main() {
  S{}.f();
  S{}.g();
  TT<NoDef> x;          // OK：T() 还没有实例化
  x.m(NoDef(1));        // OK：没有用到默认实参
}
```

## 能写在哪里（¶3）

¶3 默认实参只能写在函数声明或 lambda 声明符的形参列表里，不能给函数形参包，也不能出现在某个形参自己的声明符内部。脚注 70 说明，这意味着函数指针、函数引用和 typedef 的声明里都不能有默认实参。

```cpp title="default-where.cpp" error
void (*pf)(int = 0);            // error: 函数指针
typedef void F(int = 0);        // error: typedef
void g(void (*cb)(int = 0));    // error: 形参的声明符内部
template<class... T>
void h(T... = 0);               // error: 形参包
auto l = [](int x = 1) { return x; };   // OK：lambda
```

函数指针不能带默认实参，是因为默认实参不在类型里，指针的类型没有地方存放它。如果允许 `void (*pf)(int = 0)`，执行 `pf = &other;` 之后这个默认值该属于谁也说不清。

默认实参里本身也可以写 lambda，例如 `void g(int x = [] { return 42; }());`。`co_await` 则不能出现在默认实参中（[[expr.await]]）。

## 跨声明累积（¶4）

¶4 先要说明**宿主作用域**（host scope，[[basic.scope.scope]]）：块作用域里的声明，宿主作用域就是那个块；其他声明的宿主作用域是它的目标作用域，例如命名空间里的函数声明就是那个命名空间。于是：

- 对非模板函数，宿主作用域相同的后续声明可以补充默认实参；
- 宿主作用域不同的声明各有一套默认实参，内层不继承外层的，外层也看不到内层的；
- 在每个声明中，有默认实参的形参后面的每个形参，都要在本声明或之前的声明里有默认实参。从形参包展开得到的形参和函数形参包除外；
- 注 2 说明，同一个形参的默认实参不能再给一次，值相同也不行（[[basic.def.odr]]）。

标准例 2 把这几条都用上了：

```cpp title="default-accumulate.cpp" error
void g(int = 0, ...);       // OK：省略号不是形参
void f(int, int);
void f(int, int = 7);       // 补充：第二个形参有了默认实参
void h() {
  f(3);                     // OK：f(3, 7)
  void f(int = 1, int);     // error: 块作用域不继承 "= 7"，
                            //   第二个形参没有默认实参
}
void m() {
  void f(int, int);         // 本块的声明，没有默认实参
  f(4);                     // error: 外层的 "= 7" 在这里看不到
  void f(int, int = 5);     // OK：在本块补充
  f(4);                     // OK：f(4, 5)
  void f(int, int = 5);     // error: 不能重复给出
}
void n() {
  f(6);                     // OK：f(6, 7)，m 里的 "= 5" 只属于 m
}
template<class... T> struct C {
  void f(int n = 0, T...);  // 包展开出的形参不需要默认实参
};
C<int> c;                   // OK：void C<int>::f(int n = 0, int)
```

块作用域里的函数声明本来就是在局部重新描述一个外部函数。按宿主作用域隔离之后，每个作用域看到的是自洽的一套默认实参，不会因为别的函数体里写了什么而改变。

¶4 末尾还有两条：

- 同一个 inline 函数在多个翻译单元中定义时，各翻译单元结束时累积的默认实参必须相同。违反时程序非良构但不要求诊断（IFNDR）：编译器和链接器都可能毫无提示。
- 如果一个友元声明给出了默认实参，它必须是函数定义，而且这个函数不能有其他声明从它可达，或者它从其他声明可达。实际效果是带默认实参的友元函数只能像隐藏友元那样只声明一次。

```cpp title="friend-default.cpp" error
struct F  { friend void fr(int = 0); };      // error: 必须是定义
struct F2 { friend void fr2(int = 0) {} };   // OK
```

## 类外定义的成员函数（¶6）

¶6 在类外定义成员函数时给出的默认实参，会加到类内声明的那一套里。有两个限制：

- 如果这样做使函数变成了默认构造函数、复制或移动构造函数、复制或移动赋值运算符，程序非良构；
- 模板化类的成员函数，默认实参只能在类内的首次声明里给出。

```cpp title="member-default.cpp" error
class C {
  void f(int i = 3);
  void g(int i, int j = 99);
  C(int x);
};
void C::f(int i = 3) {}          // error: 类内已经给过
void C::g(int i = 88, int j) {}  // OK：此后 C::g 可以无实参调用
C::C(int x = 0) {}               // error: 变成了默认构造函数

template<class T> struct T1 { void f(int); };
template<class T>
void T1<T>::f(int = 1) {}        // error: 只能在类内给出
```

特殊成员函数受限，是因为类有没有默认构造函数、复制构造函数，决定了它是否平凡、隐式声明哪些成员等性质。这些性质在类定义结束时就要确定，并在所有翻译单元中一致，不能因为某个源文件在类外补了一个默认实参就改变。

## 默认实参里不能用什么（¶7–9）

默认实参在调用者那里求值，所以凡是调用者手里没有的东西，它都不能用。

### 局部变量和 this（¶7、¶8）

¶7 是注：默认实参中不能 odr-use 局部变量（[[basic.def.odr]]）。odr-use 大致指需要变量本身存在的使用，比如读取一个非常量变量的值；放在 `sizeof` 里，或者读取常量表达式初始化的 `const int`，都不算。

```cpp title="default-local.cpp" error
void f() {
  int i;
  extern void g(int x = i);          // error: odr-use 局部变量
  extern void h(int x = sizeof(i));  // OK：未求值操作数
  const int k = 3;
  extern void p(int x = k);          // OK：读常量不是 odr-use
}
```

`g` 是命名空间里的函数，可能在 `f` 之外被调用，那时 `i` 已经不存在了。

¶8 也是注：`this` 不能出现在成员函数的默认实参中（[[expr.prim.this]]），例如 `void f(A* p = this);` 非良构。

### 其他形参（¶9）

¶9 形参不能在默认实参中被潜在求值。注 6 提醒，写在默认实参前面的形参已经在作用域内，会遮住同名的命名空间成员和类成员：

```cpp title="default-param.cpp" error
int a;
int f(int a, int b = a);          // error: 用了形参 a
typedef int I;
int g(float I, int b = I(2));     // error: 找到的是形参 I
int h(int a, int b = sizeof(a));  // OK：未求值操作数
```

禁止用前面的形参，是因为形参的初始化顺序是不确定的（[[expr.call]]），计算 `b` 的默认值时 `a` 不一定已经初始化。`g` 里的形参 `I` 遮住了类型名 `I`，`I(2)` 就成了对一个 `float` 的调用。

### 非静态成员（¶9）

默认实参中不能指称非静态成员，除非：

- ¶9.1 它出现在类成员访问表达式里，如 `obj.m`；
- ¶9.2 它用来形成成员指针，如 `&X::m`；
- ¶9.3 {{c++26}} 它是反射表达式 `^^m` 的操作数。

```cpp title="default-member.cpp" error
int b;
class X {
  int a;
  int mem1(int i = a);           // error: 没有对象提供 a
  int mem2(int i = b);           // OK：X::b，静态成员
  int mem3(int X::*p = &X::a);   // OK：成员指针
  static int b;
};
```

`mem2` 里的 `b` 是 `X::b` 而不是 `::b`，因为默认实参是完整类语境，能找到后面声明的成员。标准例 8 还说明，`[:^^a:]` 这种拼接写法同样算指称 `a`，不能用；`^^a` 本身可以。

## 默认实参不属于函数类型（¶9）

```cpp title="default-not-type.cpp" error
int f(int = 0);
void h() {
  int j = f(1);
  int k = f();            // OK：即 f(0)
}
int (*p1)(int) = &f;
int (*p2)() = &f;         // error: f 的类型是 int(int)
```

¶9 末尾明确，默认实参不是函数类型的一部分（另见 [[dcl.fct#13]]）。注 7、注 8 说明重载决议能用哪些默认实参：如果候选函数的某个声明的宿主作用域是 *S*，那么 *S* 中所有可达声明上的默认实参都可以用（[[over.match.viable]]）；但经由 using 声明找到的候选，提供默认实参的那个声明从那里不一定可达。

## 虚函数按静态类型取默认实参（¶10）

```cpp run title="virtual-default.cpp" ok
#include <cstdio>
struct A {
  virtual void v(int a = 7) { std::printf("A %d\n", a); }
  virtual ~A() = default;
};
struct B : A {
  void v(int a = 9) override { std::printf("B %d\n", a); }
};
int main() {
  B b;
  A& ra = b;
  ra.v();   // B 7：函数体按动态类型，默认实参按静态类型
  b.v();    // B 9
}
```

!!! std
    A virtual function call uses the default arguments in the declaration of the virtual function determined by the static type of the pointer or reference denoting the object.

    虚函数调用使用的默认实参，来自指针或引用的静态类型所确定的那个虚函数声明。

¶10 覆盖函数也不会从被覆盖的函数那里继承默认实参。标准例 10 里 `B::f(int)` 没写默认实参，于是 `pb->f()` 非良构，而 `pa->f()` 调用 `B::f(7)`。

默认实参是在调用点由编译器补上的，编译器在那里只知道静态类型。要按动态类型选，就得把默认实参也放进虚表或在运行时分派，这与默认实参不属于函数类型的设计相悖。所以不要在覆盖函数里另写默认实参。常见的做法是让公开的非虚函数带默认实参，再由它调用受保护的虚函数，即 NVI（non-virtual interface）惯用法。

## 实现视角

!!! impl
    - 默认实参在每个调用点展开，不影响名字修饰，也不进入 ABI。
    - 因此在头文件里改了默认值，只重新编译定义所在的源文件不够，所有调用者都要重新编译。这是库 ABI 演进中常见的问题。
    - 本机 Clang 23 的诊断：重复给出默认实参时报 "redefinition of default argument"；类外补默认实参使构造函数变成默认构造函数时报 "addition of default argument on redeclaration makes this constructor a default constructor"；类模板成员在类外补默认实参时报 "default arguments cannot be added to an out-of-line definition of a member of a class template"。

## 历史与演进

!!! history
    - C++98 已经有本节的大部分规则，包括虚函数按静态类型选默认实参。
    - C++11 的 lambda 原本不允许带默认实参，后来通过核心语言缺陷修订放开，C++14 起可用。
    - `consteval` 和 `std::source_location` 进入 C++20 后，又通过缺陷修订明确：默认实参里的即时调用推迟到调用点，不在声明处求值。
    - C++26：默认实参里可以用 `^^member` 反射非静态成员。

## 常见误解

!!! pitfall "头文件和源文件各写一次默认实参"
    头文件里声明 `void f(int x = 1);`，源文件里又定义 `void f(int x = 1) {}`，这是重复给出默认实参，非良构。默认实参只写在声明里，通常是头文件。

!!! pitfall "默认实参只求值一次"
    每次省略实参的调用都会重新求值，可以有副作用，每次的结果也可以不同，例如 `std::chrono::steady_clock::now()`。

!!! pitfall "函数指针和 `std::function` 能用上默认实参"
    它们只看类型。`f` 是 `void f(int = 0)` 时，`std::function<void()> fn = f;` 非良构。

## 思考题

!!! question "思考题 1"
    下面程序输出什么？
    ```cpp
    #include <cstdio>
    void f(int a, int b = 2);
    void f(int a = 1, int b);
    int main() {
      f();
      { void f(int, int = 20); f(10); }
      f();
    }
    void f(int a, int b) { std::printf("%d%d ", a, b); }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `12 1020 12 `。第二个声明合法：`b` 在同一宿主作用域的前一个声明里已有默认实参，满足连续性要求。累积之后 `f()` 就是 `f(1, 2)`。块里的声明有自己的一套默认实参，只有 `b = 20`，所以 `f(10)` 是 `f(10, 20)`。离开块后又回到全局那一套（第 4 段）。
</details>

!!! question "思考题 2"
    为什么 `std::source_location::current()` 作为默认实参能拿到调用点的位置，而一个普通的 `constexpr` 函数 `my_line()` 做不到？

<details markdown="1">
<summary>答案</summary>

两者都在调用点求值，区别在于 `current()` 由实现特殊处理：[[support.srcloc]] 规定它出现在默认实参中时返回调用点的位置。第 5 段保证这个即时调用不会在声明处提前求值。普通函数无从知道调用者的位置，除非它自己也带一个 `source_location` 默认实参。
</details>
