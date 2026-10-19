---
title: 核心 UB 目录 · 第 [class] 章
summary: 第 11 章明文写出的十条未定义行为：重复析构、构造开始前或析构结束后访问成员和基类、构造和析构期间的纯虚调用、过早调用成员函数，以及对完整对象中其他部分的虚调用、typeid 和 dynamic_cast。
status: done
related: ub, class.cdtor, class.dtor, class.abstract, class.base.init
tags: UB, 附录, 类, 构造, 析构
updated: 2026-10-19
---

!!! tldr
    - 析构函数一旦被调用，对象的生命周期就结束了；对自动变量显式调用析构函数后，离开作用域时的隐式析构就是第二次析构，属于未定义行为。
    - 对有非平凡构造函数的对象，构造开始之前不能访问它的成员和基类，连取地址或转换成基类指针都不行；析构结束之后同理。
    - 构造和析构期间，对象表现得像构造函数或析构函数所属类的对象。在抽象类的构造函数里虚调用纯虚函数是未定义行为。
    - 在 B 的构造函数里，通过不属于 B 子对象的那部分完整对象做虚调用、`typeid` 或 `dynamic_cast`，是未定义行为。
    - 这些未定义行为几乎都没有运行时工具能发现，编译器警告只能覆盖最直接的写法。

Annex F 汇总了核心语言中明文写出的未定义行为，总览见 [[ub]]。它的 F.6 节对应第 11 章 [class]，共十条，几乎都和对象的构造与析构有关。

理解它们只需要一个模型。一个类对象的生命周期从构造函数执行完毕开始，到析构函数开始执行时结束（[[basic.life]]）。在这之前和之后，对象处在构造中或析构中的状态，[[class.cdtor]] 规定这时它表现得像是正在执行的那个构造函数或析构函数所属类的对象。凡是绕过这个当前类型去访问对象的操作，基本都是未定义行为。

下文的运行结果都来自本机 Clang 23（arm64 macOS），默认用 `-O0 -g -fsanitize=address,undefined` 编译；`vptr` 检查（UBSan 中检查多态对象动态类型的一项）需要另外加 `-fsanitize=vptr`。

## 重复析构

### F.6.1 对生命周期已结束的对象再次调用析构函数 {#class.dtor.no.longer.exists}

`[ub:class.dtor.no.longer.exists]` · 正文 [[class.dtor#18]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct A {
  int* p = new int(1);
  ~A() { delete p; }
};

int main() {
  A a;
  a.~A();
}   // UB：隐式析构作用于生命周期已结束的 a
```

调用析构函数会结束对象的生命周期。对自动存储期的对象显式调用析构函数后，离开作用域时还会隐式地再调用一次，这第二次调用作用在一个生命周期已经结束的对象上。唯一的补救是在离开作用域之前用 placement new 在原处重新构造一个对象。

本机运行时，ASan 报告 `attempting double-free`，栈回溯指向 `A::~A()`。常量求值中同样的操作会被拒绝，诊断是 `destroying object 'a' whose lifetime has already ended`。

## 构造开始前与析构结束后

### F.6.4 构造函数开始执行前引用对象的成员或基类 {#class.cdtor.before.ctor}

`[ub:class.cdtor.before.ctor]` · 正文 [[class.cdtor#1]]

如果一个对象有非平凡的构造函数，在构造函数开始执行之前，就不能引用它的任何非静态成员或基类子对象。如果它的构造函数都是平凡的，就没有这个限制。正文用全局对象说明这对初始化顺序的影响：

```cpp ub
struct X { int i; };
struct Y : X { Y(); };                  // 非平凡
struct A { int a; };
struct B : public A { int j; Y y; };    // 非平凡（因为成员 y）

extern B bobj;
B* pb = &bobj;                          // OK：取整个对象的地址
int* p1 = &bobj.a;                      // UB：引用了基类成员
int* p2 = &bobj.y.i;                    // UB：引用了成员的成员
A* pa = &bobj;                          // UB：转换为基类指针
B bobj;                                 // bobj 的定义（动态初始化）

extern X xobj;
int* p3 = &xobj.i;                      // OK：X 的构造函数都是平凡的
X xobj;
```

`pb`、`p1`、`p2`、`pa` 都在 `bobj` 的动态初始化之前初始化。取整个对象的地址没有问题，但取成员的地址、转换为基类指针都要引用子对象，这时 `bobj` 的构造还没有开始。

附录选的是另一个例子：在成员初始化器里，取一个尚未构造、带虚基类的成员的成员地址。

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
struct W { int j; };
struct X : virtual W {};
struct Y {
  int* p;
  X x;
  Y() : p(&x.j) {}   // UB：x 还没有构造
};

int main() { Y y; }
```

本机运行时，`vptr` 检查报告 `cast to virtual base of address … which does not point to an object of type 'X'`。要找到虚基类 `W` 中的 `j`，必须读取 `x` 里记录的虚基类偏移，而 `x` 还没有构造，这项信息还没有写进去。

### F.6.7 构造开始前或析构完成后形成指向直接成员的指针 {#class.cdtor.form.pointer}

`[ub:class.cdtor.form.pointer]` · 正文 [[class.cdtor#3]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct A { int i = 0; };
struct B {
  int* p;
  A a;
  B() : p(&a.i) {}   // UB：初始化 p 时 a 的构造尚未开始
};

int main() { B b; std::printf("%d\n", *b.p); }
```

要形成指向对象 `obj` 的直接非静态成员的指针，或者访问这个成员的值，`obj` 的构造必须已经开始，析构必须还没有完成。成员按声明顺序初始化，初始化 `p` 时 `a` 的构造还没开始。

本机编译时，Clang 给出警告 `field 'a' is uninitialized when used here [-Wuninitialized]`；运行没有报告，打印 `0`。没有虚基类时，`&a.i` 只是一个固定偏移，硬件层面没有任何问题，所以这条未定义行为很难察觉。把 `p` 声明在 `a` 之后就消除了这个问题。

### F.6.6 构造未开始或析构已完成时转换为基类指针 {#class.cdtor.convert.pointer}

`[ub:class.cdtor.convert.pointer]` · 正文 [[class.cdtor#3]]

把指向 X 的指针转换为指向它的基类 B 的指针时，X 本身，以及 X 的基类中所有派生自 B 的那些，都必须已经开始构造、尚未完成析构。虚基类让通往 B 的路径不止一条，附录用下面这个例子说明：

```cpp ub
struct A { };
struct B : virtual A { };
struct C : B { };
struct D : virtual A { D(A*); };
struct X { X(A*); };

struct E : C, D, X {
  E() : D(this),   // UB：E* → A* 可能经过 E* → D* → A*，而 D 尚未构造
                   // 写成 D((C*)this) 则是合法的：E() 已开始，C 已构造完成
        X(this) {} // OK：构造 X 时，C、B、D、A 都已构造完成
};
```

在本机给 `D` 和 `X` 的构造函数加上读取 `p` 所指对象成员的代码并运行，两处都正常打印，没有报告。Clang 通过 `E` 自己记录的虚基类偏移计算 `A*`，恰好不经过 `D`。但标准没有规定转换走哪条路径，所以这仍是未定义行为。

### F.6.5 析构函数执行完后引用对象的成员或基类 {#class.cdtor.after.dtor}

`[ub:class.cdtor.after.dtor]` · 正文 [[class.cdtor#1]]

这是 F.6.4 的镜像：对有非平凡析构函数的对象，析构完成之后同样不能引用它的成员和基类。

```cpp ub
struct X {
  int i;
  ~X();   // 非平凡
};

X& g() {
  static X x;
  return x;
}

void f() {
  X* px = &g();
  px->~X();
  int j = px->i;   // UB：析构完成后访问成员
}
```

`x` 有静态存储期，析构之后内存仍然存在，所以本机运行这类代码不会有任何报告。这个程序退出时还会再析构一次 `x`，那是 F.6.1 的未定义行为。

## 构造和析构期间的虚调用与类型查询

### F.6.2 在抽象类的构造函数或析构函数中虚调用纯虚函数 {#class.abstract.pure.virtual}

`[ub:class.abstract.pure.virtual]` · 正文 [[class.abstract#6]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
struct B;
void call(B*);

struct B {
  virtual void f() = 0;
  B() { call(this); }   // 间接地虚调用纯虚函数
};
void call(B* b) { b->f(); }   // UB：此时 *b 表现为 B 对象，B::f 是纯虚的

struct D : B { void f() override {} };

int main() { D d; }
```

构造 `D` 的 `B` 部分时，对象表现为 `B` 对象（[[class.cdtor#4]]），虚调用 `f()` 选择的是 `B` 中的最终覆盖函数，也就是纯虚的 `B::f`。直接调用和间接调用都算：在构造函数里调用一个普通函数，再由它虚调用纯虚函数，同样是未定义行为。

在构造函数里直接写 `f();` 时，本机 Clang 给出警告 `call to pure virtual member function 'f' has undefined behavior; overrides of 'f' in subclasses are not available in the constructor of 'B' [-Wcall-to-pure-virtual-from-ctor-dtor]`。上面的间接调用没有警告。运行时两种写法都会进入 B 的虚表中纯虚函数的占位项，libc++abi 打印 `Pure virtual function called!` 后中止程序。

### F.6.3 所有基类初始化完成前调用成员函数 {#class.base.init.mem.fun}

`[ub:class.base.init.mem.fun]` · 正文 [[class.base.init#18]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct A { A(int v) { std::printf("%d\n", v); } };

struct B : A {
  int j = 7;
  int f() { return j; }
  B() : A(f()) {}   // UB：基类 A 尚未初始化就调用了成员函数
};

int main() { B b; }
```

构造和析构期间可以调用成员函数，也可以对对象使用 `typeid` 和 `dynamic_cast`。但在下面三种时刻做这些操作是未定义行为：

- 在构造函数的成员初始化列表中（包括由它直接或间接调用的函数中），所有基类的初始化完成之前；
- 在构造函数的前置条件断言中；
- 在析构函数的后置条件断言中（后两种见 [[dcl.contract.func]]，C++26 的契约）。

所有基类都初始化完之后，在初始化成员时调用成员函数就是合法的，当然还没初始化的成员仍然不能读。附录的例子还演示了多继承：`D() : C(f()), i(f())` 中，第一个调用是未定义行为，因为基类 `C` 还没有初始化；第二个调用合法。

本机运行没有 sanitizer 报告，打印了一个随机值，因为此时 `j` 还没有初始化。

### F.6.8 构造或析构期间，通过对象的其他部分做虚调用 {#class.cdtor.virtual.not.x}

`[ub:class.cdtor.virtual.not.x]` · 正文 [[class.cdtor#4]]

设 x 是正在构造的对象，它可能是某个完整对象的基类子对象。在 x 的构造函数中，通过 x 本身或 x 的基类子对象做虚调用，选择的是构造函数所属类中的最终覆盖函数。如果通过显式的成员访问，把虚调用作用在完整对象中 x 以外的部分上，比如完整对象的另一个基类子对象，就是未定义行为。

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct V {
  virtual void f() { std::puts("V::f"); }
  virtual void g() { std::puts("V::g"); }
  virtual ~V() = default;
};
struct A : virtual V { void f() override { std::puts("A::f"); } };
struct B : virtual V {
  void g() override { std::puts("B::g"); }
  B(V* v, A* a) {
    f();      // V::f，不是 A::f
    g();      // B::g，不是 D::g
    v->g();   // OK：v 指向 B 的基类 V，调用 B::g
    a->f();   // UB：A 不是 B 的基类
  }
};
struct D : A, B {
  void f() override { std::puts("D::f"); }
  void g() override { std::puts("D::g"); }
  D() : B((A*)this, this) {}
};

int main() { D d; }
```

`D` 先构造基类 `A`，再构造 `B`。在 `B` 的构造函数里，`a` 指向完整对象中的 `A` 子对象，它不属于正在构造的 `B`。

本机运行依次打印 `V::f`、`B::g`、`B::g`、`V::f`。未定义的那次调用 `a->f()` 既没有调用 `A::f`，也没有调用 `D::f`，而是调用了 `V::f`：这时 A 子对象的 vptr（指向虚函数表的隐藏指针）指向的是构造 `D` 过程中使用的某张临时虚表。

### F.6.9 构造或析构期间对其他部分使用 typeid {#class.cdtor.typeid}

`[ub:class.cdtor.typeid]` · 正文 [[class.cdtor#5]]

在构造或析构期间，如果 `typeid` 的操作数指代正在构造的对象，结果是构造函数所属类的 `type_info`。前提是操作数的静态类型是这个类或它的基类，否则是未定义行为。

```cpp ub
#include <typeinfo>

struct V { virtual void f(); };
struct A : virtual V {};
struct B : virtual V { B(V*, A*); };
struct D : A, B { D() : B((A*)this, this) {} };

B::B(V* v, A* a) {
  typeid(*this);   // B 的 type_info
  typeid(*v);      // OK：V 是 B 的基类，得到 B 的 type_info
  typeid(*a);      // UB：A 不是 B 的基类
}
```

本机把这三个 `typeid` 的 `name()` 打印出来，结果都是 `1B`：未定义的那次也声称 A 子对象的类型是 B。

### F.6.10 构造或析构期间对其他部分使用 dynamic_cast {#class.cdtor.dynamic.cast}

`[ub:class.cdtor.dynamic.cast]` · 正文 [[class.cdtor#6]]

```cpp ub
struct V { virtual void f(); };
struct A : virtual V {};
struct B : virtual V { B(V*, A*); };
struct D : A, B { D() : B((A*)this, this) {} };

B::B(V* v, A* a) {
  dynamic_cast<B*>(v);   // OK：V 是 B 的基类，结果是 B*
  dynamic_cast<B*>(a);   // UB：A 不是 B 的基类
}
```

构造或析构期间，`dynamic_cast` 把正在构造的对象当作类型为构造函数所属类的最派生对象。操作数的静态类型如果不是这个类或它的基类，就是未定义行为。

本机运行时，`dynamic_cast<B*>(a)` 返回了空指针。对 F.6.8 到 F.6.10 的三个例子，ASan、UBSan 和 `vptr` 检查都没有报告。
