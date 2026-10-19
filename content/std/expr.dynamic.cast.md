---
title: dynamic_cast
summary: 唯一在运行期检查对象实际类型的转换：什么时候能写、哪些情形在编译期就完成、向下转换和交叉转换怎样检查、失败时得到什么，以及它在构造期间、常量求值中和 ABI 层面的表现。
status: done
papers: P1327R1
related: expr.static.cast, expr.typeid, class.cdtor, class.virtual, class.derived, intro.object, bad.cast, basic.life, topics/casts
tags: 类型转换, RTTI, 多态, 继承
updated: 2026-10-19
---

!!! tldr
    - `dynamic_cast` 在运行期查看对象的实际类型，转换成功就得到指向目标子对象的指针或引用，失败时指针版本得到空指针，引用版本抛出 `std::bad_cast`。
    - 向上转换和同类型转换在编译期完成，不需要虚函数；其余情形要求操作数是多态类型，也就是至少有一个虚函数的类。
    - 运行期检查只走 public 继承路径，能做向下转换，也能做 `static_cast` 做不到的交叉转换和从虚基类向下转换。
    - 交给 `dynamic_cast` 的指针必须指向一个活着的对象；悬垂指针是未定义行为，不会安全地返回空指针。
    - 在基类的构造函数和析构函数里，对象被当作基类本身，向派生类的转换总会失败。

## 带检查的向下转换

```cpp run title="dyn-intro.cpp" ok
struct Shape { virtual ~Shape() = default; };
struct Circle : Shape { int r = 1; };
struct Square : Shape {};

int radius(Shape* s) {
  if (auto* c = dynamic_cast<Circle*>(s))
    return c->r;          // s 确实指向一个 Circle
  return 0;               // 不是 Circle：得到空指针
}

int main() {
  Circle c;
  Square q;
  return radius(&c) == 1 && radius(&q) == 0 ? 0 : 1;
}
```

`static_cast<Circle*>(s)` 也能编译，但它相信程序员：`s` 实际指向 `Square` 时，结果就是一个错误的指针。`dynamic_cast` 在运行期查看 `*s` 的**动态类型**（dynamic type，对象实际的类型，与表达式的静态类型相对），判断它里面是否真的有一个 `Circle`。

能做这个检查，是因为 `Shape` 有虚函数。有虚函数的类叫**多态类**（polymorphic class，[[class.virtual]]），它的对象里存着一个指向虚表的指针，虚表里有类型信息（RTTI）。没有虚函数的类，对象里没有这份信息，`dynamic_cast` 也就无从检查。

## 能写成什么样（¶1、¶2、¶5）

¶1 `dynamic_cast<T>(v)` 中的 `T` 必须是下面两种之一：

- 指向完整类类型的指针或引用；
- 指向（可能带 cv 限定的）`void` 的指针。

`dynamic_cast` 也不能去掉 `const` 或 `volatile`（[[expr.const.cast#6]]），需要的话再套一层 `const_cast`。

¶2 操作数的形式要和 `T` 对应，结果的值类别也随之确定：

| `T` | 操作数 `v` | 结果 |
|---|---|---|
| 指针类型 | 指向完整类类型的指针，prvalue | prvalue |
| 左值引用 `C&` | 完整类类型的左值 | 左值 |
| 右值引用 `C&&` | 完整类类型的 glvalue | 亡值（xvalue） |

右值引用的版本也接受 prvalue 操作数：prvalue 作为运算符的操作数时，会先经过[[g:temporary-materialization-conversion|临时量实质化]]成为亡值（[[basic.lval#7]]）。

¶5 下一节的两种情形之外，`v` 必须是多态类型的指针或 glvalue。

```cpp title="dyn-requirements.cpp" error
struct V { virtual ~V() = default; };
struct D : V {};
struct Inc;
struct N {};
struct M : N {};

void f(const V* cv, V* v, N* n, Inc* pi) {
  dynamic_cast<D*>(cv);        // error: 去掉了 const
  dynamic_cast<const D*>(cv);  // OK
  dynamic_cast<int*>(v);       // error: int 不是类类型
  dynamic_cast<D>(*v);         // error: T 必须是指针或引用
  dynamic_cast<M*>(n);         // error: N 不是多态类型（¶5）
  dynamic_cast<D&>(V{});       // error: 左值引用要求左值
  dynamic_cast<D&&>(V{});      // OK：prvalue 先实质化
  dynamic_cast<Inc*>(v);       // error: 目标类不完整
  dynamic_cast<V*>(pi);        // error: 操作数指向不完整类
}
```

## 在编译期完成的情形（¶3、¶4）

¶3 `v` 的类型与 `T` 相同（忽略 cv 限定）时，结果就是 `v`，必要时加上 cv 限定。

¶4 从派生类向基类的转换，即**向上转换**（upcast），结果指向 `v` 所指 `D` 对象中唯一的那个 `B` 子对象；`v` 为空时结果为空。引用的情形相同。`B` 是 `D` 的不可访问或有二义的基类时，程序非良构。

```cpp run title="dyn-upcast.cpp" ok
struct B {};
struct D : B {};

void foo(D* dp) {
  B* bp = dynamic_cast<B*>(dp);   // 等价于 B* bp = dp;
  (void)bp;
}

int main() { D d; foo(&d); }
```

这就是标准的例 1。`B` 没有虚函数也可以，因为向上转换和隐式转换完全一样，偏移在编译期就能算出来。这条规则的用处是让泛型代码里的 `dynamic_cast` 两个方向都能写。

脚注 45 补充了一点：`v` 所在的完整对象里可能还有别的 `B` 子对象，但它们不在考虑之内，向上转换只从 `v` 的静态类型 `D` 出发。

## 运行期检查（¶6–¶10）

### 空指针与悬垂指针（¶6、¶7）

¶6 `v` 是空指针值时，结果是空指针值。

¶7 `v` 必须指向一个类型与 `v` 所指类型[[g:similar-types|相似]]、并且处于生命期内或正在构造、析构的对象，否则行为未定义。glvalue 操作数同样如此。

```cpp run title="dyn-dangling.cpp" ub
struct B { virtual ~B() = default; };
struct D : B {};

int main() {
  B* p = new D;
  delete p;
  D* d = dynamic_cast<D*>(p);   // UB: *p 已经不在生命期内
  return d != nullptr;
}
```

`dynamic_cast` 要先读对象里的虚表指针，而这时那块内存已经释放，虚表指针也就不存在了。本机 AddressSanitizer 在这一行报告 heap-use-after-free。所以 `dynamic_cast` 不能用来检查指针是否还有效，经 `reinterpret_cast` 得到的类型不对的指针同样不行（参见 [[basic.life#7]]）。

### 找回整个对象：转换到 `void*`（¶8）

¶8 `T` 是指向 `void` 的指针时，结果指向 `v` 所指的**最派生对象**（most derived object，不是任何其他对象的子对象的那个完整对象，[[intro.object]]）。

```cpp run title="dyn-void.cpp" ok
struct A { virtual ~A() = default; int a; };
struct B { virtual ~B() = default; int b; };
struct D : A, B {};

int main() {
  D d;
  B* pb = &d;                          // 指向 B 子对象
  void* whole = dynamic_cast<void*>(pb);
  return whole == static_cast<void*>(&d)
      && static_cast<void*>(pb) != whole ? 0 : 1;
}
```

在多重继承中，`B` 子对象不在 `d` 的起始地址。`static_cast<void*>(pb)` 只是换个类型，地址不变；`dynamic_cast<void*>(pb)` 才能找回整个对象的起点。需要用地址判断两个基类指针是否指向同一个对象时，这是唯一可移植的办法。

### 检查的算法（¶8、¶9）

其余情形都要做运行期检查。设 `C` 是 `T` 所指或所引用的类，第 9 段规定的检查逻辑上分三步：

1. ¶9.1 **向下转换**：在 `v` 所在的最派生对象中，如果 `v` 指向某个 `C` 对象的 public 基类子对象，而且从 `v` 所指子对象派生出的 `C` 对象只有一个，结果指向这个 `C` 对象。
2. ¶9.2 **交叉转换**（cross-cast）：否则，如果 `v` 指向最派生对象的一个 public 基类子对象，并且最派生对象的类型有一个无二义的 public 基类 `C`，结果指向最派生对象的这个 `C` 子对象。
3. ¶9.3 否则检查失败。

第一步从 `v` 所指的子对象出发，沿包含它的那条继承链往派生方向找。第二步先走到最派生对象，再看整个对象里有没有唯一的 public `C`，所以可以转到另一个继承分支上。两步都只认 public 继承：私有继承关系在运行期是看不见的。

```cpp run title="dyn-cross.cpp" ok
struct Shape { virtual ~Shape() = default; };
struct Drawable {
  virtual ~Drawable() = default;
  virtual int draw() const = 0;
};
struct Circle : Shape, Drawable {
  int draw() const override { return 1; }
};
struct Square : Shape {};

int main() {
  Circle c;
  Square s;
  Shape* p1 = &c;
  Shape* p2 = &s;
  auto* down = dynamic_cast<Circle*>(p1);    // ¶9.1：成功
  auto* side = dynamic_cast<Drawable*>(p1);  // ¶9.2：成功
  auto* none = dynamic_cast<Drawable*>(p2);  // 失败：空指针
  return down == &c && side && side->draw() == 1
      && none == nullptr ? 0 : 1;
}
```

`Shape` 和 `Drawable` 之间没有继承关系，所以 `static_cast<Drawable*>(p1)` 是非良构的；`reinterpret_cast` 能编译，但得到的指针并不指向 `Drawable` 子对象。交叉转换只有 `dynamic_cast` 能做。

### 失败的结果（¶10）

¶10 转换到指针类型失败时，结果是目标类型的空指针值。转换到引用类型失败时，抛出一个能被 `std::bad_cast`（[[bad.cast]]）处理器捕获的异常，因为引用没有空值可用。

```cpp run title="dyn-bad-cast.cpp" ok
#include <typeinfo>

struct B { virtual ~B() = default; };
struct D : B {};

int main() {
  B b;
  try {
    D& d = dynamic_cast<D&>(b);   // b 不是 D：抛出 std::bad_cast
    (void)d;
    return 1;
  } catch (const std::bad_cast&) {
    return 0;
  }
}
```

### 私有继承、虚基类和重复的子对象

标准的例 2 把这些边界情况放在了一起。下面是可以编译的改编版，原文中非良构和会抛异常的两行改成了注释：

```cpp run title="dyn-std-example.cpp" ok
class A { virtual void f() {} };
class B { virtual void g() {} };
class D : public virtual A, private B {};

void g() {
  D  d;
  B* bp = (B*)&d;                // C 风格转换可以无视私有继承
  A* ap = &d;                    // public 派生，不需要转换
  // D& dr = dynamic_cast<D&>(*bp);  // 失败，抛出 bad_cast
  ap = dynamic_cast<A*>(bp);     // 失败：B 不是 D 的 public 基类
  bp = dynamic_cast<B*>(ap);     // 失败：D 的 B 基类不是 public
  ap = dynamic_cast<A*>(&d);     // 成功：¶4 向上转换
  // bp = dynamic_cast<B*>(&d);  // 非良构：向上转换到私有基类
}

class E : public D, public B {};
class F : public E, public D {};

void h() {
  F  f;
  A* ap  = &f;                   // 成功：A 是虚基类，F 里只有一个
  D* dp  = dynamic_cast<D*>(ap); // 失败，空指针：F 里有两个 D
  // E* ep = (E*)ap;             // 非良构：不能从虚基类向下转换
  E* ep1 = dynamic_cast<E*>(ap); // 成功：F 里只有一个 E
  (void)dp; (void)ep1;
}

int main() { g(); h(); }
```

从中可以读出三点：

- 对象里确实有 `B` 子对象，但它经由私有继承得到，第 9 段的两步都不认，转换失败。向上转换到私有基类则在编译期就是错误，不会推迟到运行期。
- 虚基类子对象相对于整个对象的偏移在编译期未知，所以 `static_cast` 和 C 风格转换都不能从虚基类向下转换（[[expr.static.cast#10]]）；`dynamic_cast` 在运行期查对象布局，可以做到。
- `F` 有两个 `D` 子对象，从共享的唯一 `A` 出发不知道该选哪一个，9.1 和 9.2 两项都不满足，转换失败。

本机 Clang 编译这段代码时，对 `E` 和 `F` 各给一条 direct base is inaccessible due to ambiguity 警告，这正是重复子对象的提示。

## 构造与析构期间

第 10 段之后的注 1 指向 [[class.cdtor#6]]：在构造函数或析构函数里（包括它们直接或间接调用的函数），如果操作数指向正在构造或析构的对象，这个对象被当作一个最派生对象，类型就是当前构造函数或析构函数所属的类。

```cpp run title="dyn-ctor.cpp" ok
struct V { virtual ~V() = default; };
struct D;
struct B : V { B(); bool saw_d = true; };
struct D : B {};

B::B() {
  V* v = this;
  saw_d = dynamic_cast<D*>(v) != nullptr;  // 失败：此时对象被当作 B
}

int main() {
  D d;
  V* v = &d;
  bool after = dynamic_cast<D*>(v) != nullptr;  // 构造完成后：成功
  return !d.saw_d && after ? 0 : 1;
}
```

这和构造期间虚函数按当前类分派（[[class.cdtor#4]]）是同一个道理：派生类的部分还没有构造，不能让任何机制访问到它。实现上，构造 `B` 期间对象的虚表指针指向的就是 `B` 的虚表。

[[class.cdtor#6]] 还规定，如果操作数指向正在构造的对象，而它的静态类型既不是当前类也不是当前类的基类，行为未定义。

## 常量求值

C++20 起（[[P1327R1]]），`dynamic_cast` 可以出现在常量表达式中。常量求值器知道每个对象的确切类型，检查是精确的：

```cpp run title="dyn-constexpr.cpp" ok
struct B { virtual ~B() = default; };
struct D : B {};
struct E : B {};

constexpr bool test() {
  D d;
  B* p = &d;
  return dynamic_cast<D*>(p) != nullptr
      && dynamic_cast<E*>(p) == nullptr;
}
static_assert(test());

int main() {}
```

有两种情况不是核心常量表达式（[[expr.const.core#2]]）：

- ¶2.30 操作数引用的对象的动态类型在编译期未知，例如函数形参引用的对象；
- ¶2.31 转换失败要抛出 `std::bad_cast`，而这里看不到这个异常类型的定义（例如没有包含 `<typeinfo>`）。C++26 允许在常量求值中抛出和捕获异常，所以看得到定义时，失败的引用转换可以在编译期被捕获。

## 实现视角

!!! impl "Itanium C++ ABI 中的 dynamic_cast"
    GCC 和 Clang 在 Linux、macOS 上使用的 Itanium C++ ABI 这样实现各种情形：

    - 向上转换：编译期算出偏移，生成的代码与 `static_cast` 相同；经过虚基类时从虚表读偏移。不需要 RTTI。
    - 转换到 `void*`：虚表里有一个 offset-to-top 槽，记录当前子对象到最派生对象起点的距离，加上它即可。也不需要 RTTI。本机 Clang 在 `-fno-rtti` 下仍接受 `dynamic_cast<void*>`，但拒绝其他需要运行期检查的 `dynamic_cast`。
    - 向下转换和交叉转换：调用运行时库函数 `__dynamic_cast`。它先用 offset-to-top 找到最派生对象，再从最派生对象的 `type_info` 出发遍历整个继承图，找 `C` 的 public 子对象并检查唯一性。编译器会额外传入一个静态算出的提示，用来加速常见情况。
    - 遍历中要比较 `type_info`。类型名在程序中唯一时比较指针即可；某些平台和动态库配置下要比较名字字符串，代价更高。

!!! impl "final 类的快速路径"
    目标类是 `final` 时，最派生对象只能是它本身，检查可以简化为比较对象的虚表指针是否等于 `C` 的虚表地址。本机 Clang 以 `--target=x86_64-linux-gnu -O2` 编译 `dynamic_cast<D*>(b)`（`D` 为 `final`）时生成的就是一次指针比较；以默认的 macOS 目标编译时仍调用 `__dynamic_cast`。能否这样做取决于虚表在整个程序中是否唯一，所以与目标平台和链接模型有关。

非 final 的 `dynamic_cast` 要调用运行时库并遍历继承图，通常比一次虚函数调用贵得多。性能敏感的代码常用替代方案：在基类里放一个返回类型标签的虚函数，再 `static_cast`；或者用 `std::variant` 代替继承体系。LLVM 自己的 `isa<>`、`dyn_cast<>` 就是手写标签加 `static_cast`，LLVM 本身以 `-fno-rtti` 编译。

## 历史与演进

!!! history
    - C++98：`dynamic_cast` 与 RTTI 一同标准化。
    - C++11：目标类型可以是右值引用，结果是亡值。
    - C++20：可以用在常量表达式中（[[P1327R1]]）。

## 常见误解

!!! pitfall "用 dynamic_cast 检查指针是否还有效"
    对已经析构的对象做 `dynamic_cast` 是未定义行为（¶7），它不会返回空指针，而是读取已经释放的内存。

!!! pitfall "对象里有那个基类，转换就一定成功"
    私有或保护继承的路径在运行期检查中不算数，转换会失败；向上转换到这样的基类则直接编译失败。

!!! pitfall "基类构造函数里转换到派生类"
    在基类的构造函数或析构函数里，`dynamic_cast<Derived*>(this)` 总是得到空指针。这是规则规定的行为，不是编译器的问题。

!!! pitfall "跨动态库的 dynamic_cast 意外失败"
    同一个类在两个动态库里各有一份 `type_info`（例如符号可见性设成了隐藏）时，某些平台上类型比较会失败，`dynamic_cast` 返回空指针。标准不涉及动态库，但这是实践中 `dynamic_cast` 意外失败的常见原因。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct L { virtual ~L(); };
    struct R { virtual ~R(); };
    struct X : L, R {};
    struct Y : X, R {};   // Y 里有两个 R
    ```
    `Y y; L* pl = static_cast<X*>(&y);` 之后，`dynamic_cast<R*>(pl)` 的结果是什么？

<details markdown="1">
<summary>答案</summary>

¶9.1 不适用：`pl` 指向的 `L` 子对象不是任何 `R` 的一部分，`L` 和 `R` 没有继承关系。¶9.2 也不适用：最派生对象 `Y` 有两个 `R` 子对象（一个经过 `X`，一个直接继承），`R` 是有二义的基类。检查失败，结果是空指针。

想拿到经过 `X` 的那个 `R`，先 `dynamic_cast<X*>(pl)`（¶9.1 成功），再隐式向上转换到 `R*`。
</details>

!!! question "思考题 2"
    为什么 `dynamic_cast<void*>(p)` 要求 `*p` 是多态类型，而 `static_cast<void*>(p)` 不要求？两者的结果什么时候不同？

<details markdown="1">
<summary>答案</summary>

`dynamic_cast<void*>` 要找的是最派生对象的起点，必须在运行期知道 `*p` 属于哪个更大的对象，只有多态对象通过虚表携带这一信息。`static_cast<void*>(p)` 只改变指针的类型，不关心更大的对象。

`*p` 是某个对象中不在起始位置的基类子对象时，比如多重继承中的第二个基类，两者的值不同。
</details>

## 小结

!!! summary
    | 情形 | 条文 | 需要多态 | 可能失败 |
    |---|---|---|---|
    | 同类型 | ¶3 | 否 | 否 |
    | 向上转换 | ¶4 | 否 | 否；基类不可访问或有二义时编译期非良构 |
    | 转换到 `void*` | ¶8 | 是 | 否 |
    | 向下转换 | ¶9.1 | 是 | 是 |
    | 交叉转换 | ¶9.2 | 是 | 是 |
    | 失败 | ¶10 | | 指针得到空指针，引用抛出 `std::bad_cast` |
    | 操作数不指向活着的对象 | ¶7 | | 未定义行为 |
