---
title: 核心 UB 目录 · 第 [class] 章
summary: Annex F.6 的 10 条：重复析构、构造/析构中调用纯虚函数、基类初始化完成前调用成员函数、构造开始前/析构结束后引用成员与基类、在构造/析构中对"别人的"子对象做虚调用、typeid 与 dynamic_cast——正文出处、例子与 Clang 23 实测。
status: draft
related: ub, class.cdtor, class.dtor, class.abstract, class.base.init
tags: UB, 附录, 类, 构造, 析构
updated: 2026-10-18
---

这一页是 [[ub]] 的一部分，对应 Annex F.6：第 11 章 [class] 中的显式 UB。它们几乎都围绕同一个主题：对象**正在构造**或**正在析构**时，它的"类型"是一个随时间变化的量——[[class.cdtor]] 规定在构造函数执行期间，对象表现得像是构造函数所属类的对象。凡是绕过这个"当前类型"的访问，基本都是 UB。实测环境同 [[ub.basic]]，必要时加 `-fsanitize=vptr`。

### F.6.1 [ub:class.dtor.no.longer.exists] {#class.dtor.no.longer.exists}

**对生命周期已结束的对象再次调用析构函数** · 正文 [[class.dtor#18]]

析构函数一旦被调用，对象的生命周期就结束了。对自动存储期的对象显式调用析构函数后，作用域结束时还会**隐式**再调一次——除非你在此之前用 placement new 放回一个新对象。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct A {
  int* p = new int(1);
  ~A() { delete p; }
};

int main() {
  A a;
  a.~A();
}   // UB：隐式析构作用于生命周期已结束的 a
```

**实测**：ASan 报 `attempting double-free`，栈回溯指向 `A::~A()`。**常量求值**被拒：`destroying object 'a' whose lifetime has already ended`。

### F.6.2 [ub:class.abstract.pure.virtual] {#class.abstract.pure.virtual}

**在抽象类的构造/析构函数中对正在构造/析构的对象虚调用纯虚函数** · 正文 [[class.abstract#6]]

构造 B 期间，对象的动态类型就是 B（[[class.cdtor#4]]），虚调用 `f()` 会解析到 `B::f`——而它是纯虚的。"直接或间接"都算：在构造函数里调用一个普通成员函数，再由它虚调用纯虚函数，同样是 UB。

```cpp ub run flags="-std=c++2c -O0" cc=clang_trunk
struct B;
void call(B*);

struct B {
  virtual void f() = 0;
  B() { call(this); }   // 间接地虚调用纯虚函数
};
void call(B* b) { b->f(); }   // UB：此时 *b 的动态类型是 B，B::f 是纯虚的

struct D : B { void f() override {} };

int main() { D d; }
```

**实测**：直接在构造函数里写 `f();` 时，Clang 编译期警告 `call to pure virtual member function 'f' has undefined behavior; overrides of 'f' in subclasses are not available in the constructor of 'B' [-Wcall-to-pure-virtual-from-ctor-dtor]`；间接调用则没有警告。运行时两种写法都会进入 B 的虚表里纯虚函数的占位项，libc++abi 打印 `Pure virtual function called!` 后 abort。

### F.6.3 [ub:class.base.init.mem.fun] {#class.base.init.mem.fun}

**所有基类的 mem-initializer 完成前调用成员函数** · 正文 [[class.base.init#18]]

在 *ctor-initializer* 里（或在由它直接、间接调用的函数里），**所有基类**初始化完成之前，调用成员函数、对该对象用 `typeid` 或 `dynamic_cast` 都是 UB。基类都初始化完之后，初始化成员时调用成员函数就是合法的——尽管那时还没初始化的成员当然不能读。当前草案在同一段又加了两种情况：构造函数的**前置条件断言**和析构函数的**后置条件断言**中做这些操作，同样是 UB（[[dcl.contract.func]]）。

```cpp ub run flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct A { A(int v) { std::printf("%d\n", v); } };

struct B : A {
  int j = 7;
  int f() { return j; }
  B() : A(f()) {}   // UB：基类 A 尚未初始化就调用了成员函数
};

int main() { B b; }
```

**实测**：无 sanitizer 报告，打印了一个随机值（本次是 `1107296256`）——此时 `j` 还没有被初始化。附录的例子还演示了多继承的情形：`D() : C(f()), i(f())` 中第一个调用 UB（基类 C 还没初始化），第二个合法。

### F.6.4 [ub:class.cdtor.before.ctor] {#class.cdtor.before.ctor}

**构造函数开始执行前引用对象的非静态成员或基类** · 正文 [[class.cdtor#1]]

对**有非平凡构造函数**的对象，构造开始之前就不能"碰"它的成员和基类子对象——连取地址都不行。若所有构造函数都是平凡的，则没有这个限制。正文用一个全局对象的例子说明这对静态初始化顺序的影响：

```cpp ub
struct X { int i; };
struct Y : X { Y(); };                  // 非平凡
struct A { int a; };
struct B : public A { int j; Y y; };    // 非平凡（因为成员 y）

extern B bobj;
B* pb = &bobj;                          // OK：取整个对象的地址
int* p1 = &bobj.a;                      // UB：引用了基类成员
int* p2 = &bobj.y.i;                    // UB：引用了成员的成员
A* pa = &bobj;                          // UB：上行转换到基类
B bobj;                                 // bobj 的定义（动态初始化）

extern X xobj;
int* p3 = &xobj.i;                      // OK：X 的构造函数都是平凡的
X xobj;
```

附录选的是另一个例子：成员初始化器里取一个**尚未构造**的、带虚基类的成员的成员地址。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
struct W { int j; };
struct X : virtual W {};
struct Y {
  int* p;
  X x;
  Y() : p(&x.j) {}   // UB：x 还没有构造
};

int main() { Y y; }
```

**实测**：`-fsanitize=vptr` 命中：`cast to virtual base of address … which does not point to an object of type 'X'`，并注明 `object has invalid vptr`——要找到虚基类 W 里的 `j`，必须读 `x` 的虚基类偏移，而 `x` 的 vptr 还没写。

### F.6.5 [ub:class.cdtor.after.dtor] {#class.cdtor.after.dtor}

**析构函数执行完后引用对象的非静态成员或基类** · 正文 [[class.cdtor#1]]

F.6.4 的镜像：对有非平凡析构函数的对象，析构完成之后同样不能引用它的成员和基类。

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

**实测**：无报告（`x` 是静态存储，内存仍在）。顺带一提，这个程序在退出时还会对 `x` 再调用一次析构函数，那是 F.6.1 的 UB。

### F.6.6 [ub:class.cdtor.convert.pointer] {#class.cdtor.convert.pointer}

**构造未开始或析构已完成时，把指针转换为基类指针** · 正文 [[class.cdtor#3]]

把指向 X 的指针转换为指向其基类 B 的指针时，X 以及 X 的所有"通往 B 的"基类都必须已经开始构造、尚未完成析构。虚基类让"通往 B 的路径"变得不唯一，于是有了附录这个经典的格子图例子：

```cpp ub
struct A { };
struct B : virtual A { };
struct C : B { };
struct D : virtual A { D(A*); };
struct X { X(A*); };

struct E : C, D, X {
  E() : D(this),   // UB：E* → A* 可能走 E* → D* → A*，而 D 尚未构造
                   // 写成 D((C*)this) 则是合法的：E() 已开始，C 已构造完成
        X(this) {} // OK：构造 X 时，C/B/D/A 都已构造完成
};
```

**实测**：在本机给 D 和 X 的构造函数加上读取 `p->a` 的代码并运行，两处都正常打印、没有报告——Clang 通过 E 自己的虚基类偏移计算 `A*`，恰好不经过 D。但标准没有规定转换走哪条路径，所以仍是 UB。

### F.6.7 [ub:class.cdtor.form.pointer] {#class.cdtor.form.pointer}

**构造开始前或析构完成后形成指向直接非静态成员的指针** · 正文 [[class.cdtor#3]]

要形成指向对象 `obj` 的直接非静态成员的指针（或访问该成员的值），`obj` 的构造必须已经开始、析构尚未完成。

```cpp ub run flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

struct A { int i = 0; };
struct B {
  int* p;
  A a;
  B() : p(&a.i) {}   // UB：初始化 p 时 a 的构造尚未开始
};

int main() { B b; std::printf("%d\n", *b.p); }
```

**实测**：无报告，打印 `0`。在没有虚基类的情况下，`&a.i` 只是一个固定偏移，硬件层面毫无问题——这正是这条 UB 难以察觉的原因。把 `p` 声明在 `a` 之后即可消除 UB。

### F.6.8 [ub:class.cdtor.virtual.not.x] {#class.cdtor.virtual.not.x}

**在构造/析构期间，通过"不属于 x 的那部分"做虚调用** · 正文 [[class.cdtor#4]]

构造 x（一个基类子对象）期间，通过 x 自己或 x 的基类子对象做虚调用，解析到构造函数所属类的最终覆盖函数；但若通过显式成员访问，把调用作用在**完整对象中 x 以外的部分**上（例如完整对象的另一个基类子对象），则 UB——那部分对象的"当前类型"处在一个标准没有定义的状态。

```cpp ub run flags="-std=c++2c -O0" cc=clang_trunk
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
    v->g();   // OK：v 是 B 的基类 V，调用 B::g
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

**实测**：依次打印 `V::f`、`B::g`、`B::g`、`V::f`——UB 的那次调用 `a->f()` 既不是 `A::f` 也不是 `D::f`，而是 `V::f`：A 子对象的 vptr 此时指向的是 D 构造过程中的某张"构造虚表"。

### F.6.9 [ub:class.cdtor.typeid] {#class.cdtor.typeid}

**构造/析构期间对该对象用 typeid，而操作数的静态类型不是构造函数所属类或其基类** · 正文 [[class.cdtor#5]]

在构造/析构期间，`typeid` 作用于正在构造的对象时给出构造函数所属类的 `type_info`。前提是操作数的静态类型是该类或其基类。

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

**实测**：把这段与 F.6.8 合在一起运行，`typeid(*a).name()` 打印 `1B`——它声称 A 子对象的类型是 B。

### F.6.10 [ub:class.cdtor.dynamic.cast] {#class.cdtor.dynamic.cast}

**构造/析构期间对该对象做 dynamic_cast，而操作数的静态类型不是构造函数所属类或其基类** · 正文 [[class.cdtor#6]]

构造/析构期间，正在构造的对象被视为"类型为构造函数所属类的最派生对象"。操作数的静态类型若不是该类或其基类，则 UB。

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

**实测**：同样合并运行时，`dynamic_cast<B*>(a)` 返回了空指针。ASan/UBSan/vptr 检查对 F.6.8–F.6.10 都没有报告。
