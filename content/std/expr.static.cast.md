---
title: static_cast
summary: static_cast 能做哪些转换：凡是能隐式转换或能直接初始化的都能做，此外还能做大多数标准转换的逆（向下转换、void* 到 T*、整数到枚举等），以及每一种情形在什么时候是未定义行为。
status: done
papers: P0137R1, P0960R3, P2738R1
related: expr.cast, expr.dynamic.cast, expr.reinterpret.cast, expr.const.cast, conv, over.best.ics, dcl.init, dcl.init.ref, dcl.enum, conv.ptr, conv.mem, basic.compound, topics/casts, topics/value-categories
tags: 类型转换, 继承, 枚举, 指针, 移动语义, UB
updated: 2026-10-19
---

!!! tldr
    - 能隐式转换的，或者能用 `T t(e);` 直接初始化的，`static_cast<T>(e)` 都能做，包括调用 `explicit` 构造函数和窄化转换。
    - 它还能做大多数标准转换的逆：基类指针到派生类指针、`void*` 到 `T*`、整数到枚举、派生类成员指针到基类成员指针。这些反向转换不做任何检查，类型不对就是未定义行为。
    - `std::move(x)` 就是 `static_cast<T&&>(x)`：它只改变值类别，本身不移动任何东西。
    - 它不能去掉 `const`、不能在无关的指针类型之间转换、不能在指针和整数之间转换，也不能经过虚基类向下转换。
    - 经 `void*` 中转的 `static_cast` 和 `reinterpret_cast` 完全等价，并不能绕过严格别名规则。

## 一个关键字，两个方向

```cpp run title="static-cast-overview.cpp" ok
struct Base { virtual ~Base() = default; };
struct Derived : Base { int extra = 42; };
enum class Color { red, green };

int main() {
  double d = 3.9;
  int i = static_cast<int>(d);              // 截断为 3
  int c = static_cast<int>(Color::green);   // 1
  Derived obj;
  Base* pb = &obj;                          // 隐式向上转换
  auto* pd = static_cast<Derived*>(pb);     // 显式向下转换，不检查
  return i == 3 && c == 1 && pd->extra == 42 ? 0 : 1;
}
```

前两次转换是正方向的：`double` 到 `int` 本来就能隐式发生，写出 `static_cast` 只是表明意图。第三次是反方向的：派生类指针到基类指针是隐式转换，`static_cast` 允许把它倒过来，但不检查 `*pb` 是否真的是 `Derived`。

整节的结构就是这两个方向。第 2–5 段处理正方向和几种特殊情形，按先后顺序匹配；第 6 段说其余情况下只允许第 7–12 段列出的几种反向转换，除此之外都不行。

## 结果的值类别（¶1）

¶1 结果的值类别只由 `T` 决定：

| `T` | 结果 |
|---|---|
| 左值引用，或函数的右值引用 | 左值 |
| 对象的右值引用 | 亡值（xvalue） |
| 非引用类型 | prvalue |

这与函数调用的规则（[[expr.call#15]]）一致：返回 `T&&` 的函数调用也是亡值。

## 能初始化就能转换（¶5）

¶5 是适用面最宽的一条。不属于 ¶2–¶4 时，只要满足下面任何一条，表达式 `E` 就能转换为 `T`：

1. 存在从 `E` 到 `T` 的隐式转换序列（[[over.best.ics]]）；
2. 用 `E` 直接初始化一个 `T` 类型的对象或引用时，重载决议能找到至少一个可行函数（[[over.match.viable]]），这样 `explicit` 构造函数和 `explicit` 转换函数也算在内；
3. {{c++20}} `T` 是聚合类型，存在从 `E` 到它第一个元素的类型的隐式转换序列。这是为了配合圆括号初始化聚合（[[P0960R3]]）。

`T` 是引用类型时，效果如同声明 `T t(E);` 再使用 `t`；否则结果对象从 `E` 直接初始化。

```cpp run title="static-cast-init.cpp" ok
struct Ex { explicit Ex(int) {} };
struct Conv { explicit operator int() const { return 7; } };
struct Agg { int a; double b; };

int main() {
  double d = static_cast<double>(3);    // 隐式转换
  long l = static_cast<long>(3.9);      // 浮点到整数，截断
  Ex e = static_cast<Ex>(1);            // explicit 构造函数
  int i = static_cast<int>(Conv{});     // explicit 转换函数
  Agg g = static_cast<Agg>(1);          // C++20：初始化第一个元素 a
  const int& cr = static_cast<const int&>(42);  // 如同 const int& t(42);
  (void)e;
  return d == 3.0 && l == 3 && i == 7 && g.a == 1 && cr == 42 ? 0 : 1;
}
```

窄化转换只在列表初始化中被禁止（[[dcl.init.list]]）。`static_cast<int>(3.9)` 走的是直接初始化，所以允许。

注 3 提醒，把类类型的表达式转换到不可访问或有二义的基类是非良构的。

!!! lawyer "Clang 与注 4"
    注 4 说，`T` 是未知边界数组 `U[]` 时，这次直接初始化把表达式的类型定为 `U[1]`。所以 `decltype(static_cast<int[]>(1))` 应当是 `int[1]`。本机 Clang 23 给出的是 `int[]`，与标准不一致。

## 丢弃一个值（¶4）

¶4 任何表达式都可以转换为 `void`，这时操作数是一个**弃值表达式**（discarded-value expression，计算出来但不使用其值的表达式，[[expr.context]]）。

```cpp run title="cast-to-void.cpp" ok
[[nodiscard]] int compute() { return 42; }

int main() {
  static_cast<void>(compute());   // 明确丢弃，不触发 nodiscard 警告
  int unused = 0;
  (void)unused;                   // C 风格写法，效果相同
}
```

注 1 说明这样的转换没有结果，因为它是一个 `void` 类型的 prvalue。注 2 说明，如果值在一个临时对象里，这个临时对象照常在完整表达式结束时析构。

## `std::move` 的本质（¶3）

¶3 类型为 `T1` 的左值可以转换为 `T2&&`，条件是 `T2` 与 `T1` **引用兼容**（reference-compatible，[[dcl.init.ref]]），大致是说 `T2` 是 `T1` 本身或它的基类，cv 限定不少于 `T1`。结果指代这个对象，或者它的那个基类子对象。`T2` 是不可访问或有二义的基类时，非良构。

```cpp run title="lvalue-to-xvalue.cpp" ok
#include <string>

struct B {};
struct D : B {};
struct BF { int b : 3; };

int main() {
  std::string s = "hello";
  std::string t = static_cast<std::string&&>(s);  // 等同于 std::move(s)
  D d;
  B&& br = static_cast<B&&>(d);      // 指代 d 的 B 子对象
  BF bf{1};
  int&& r = static_cast<int&&>(bf.b);  // 位域：先读出值，绑定到临时量
  (void)br;
  return t == "hello" && r == 1 ? 0 : 1;
}
```

`std::move(x)` 的实现就是 `static_cast<std::remove_reference_t<T>&&>(x)`。它把左值变成亡值，让重载决议选中移动构造函数或移动赋值运算符；真正的移动发生在那个函数里。

引用不能绑定到位域，所以操作数是位域时，先把它的值读出来，用得到的 prvalue 继续本节其余的规则，最终绑定到一个临时量。

## 反方向的转换（¶6）

¶6 不属于 ¶2–¶5 时，先对操作数做左值到右值、数组到指针、函数到指针转换，然后只允许 ¶7–¶12 列出的转换。这些基本上都是某个隐式转换的逆：

| 条文 | 转换 | 对应的正方向 |
|---|---|---|
| ¶7 | 有作用域枚举到整数、浮点 | 无，有作用域枚举故意不隐式转换 |
| ¶8 | 整数、枚举、浮点到枚举 | 无作用域枚举到整数 |
| ¶9 | 浮点到任意其他浮点 | 浮点转换（[[conv.double]]） |
| ¶10 | 基类指针到派生类指针 | 派生类指针到基类指针（[[conv.ptr]]） |
| ¶11 | 派生类成员指针到基类成员指针 | 基类成员指针到派生类成员指针（[[conv.mem]]） |
| ¶12 | `void*` 到 `T*` | `T*` 到 `void*`（[[conv.ptr]]） |

¶2 处理引用的向下转换，与 ¶10 的指针版本规则相同，下面放在一起讲。

## 向下转换（¶2、¶10）

¶10 类型为指向 *cv1* `B` 的指针可以转换为指向 *cv2* `D` 的指针，其中 `D` 是从 `B` 派生的完整类，*cv2* 不少于 *cv1*。空指针转换为空指针。如果 `*p` 确实是某个 `D` 对象的基类子对象，结果指向这个外围的 `D` 对象；否则行为未定义。

¶2 是引用的版本：*cv1* `B` 的左值可以转换为 *cv2* `D&`，亡值可以转换为 *cv2* `D&&`，限制和后果都与 ¶10 相同。

<div class="compare" markdown="1">

```cpp run ok
struct B {};
struct D : B { int extra = 42; };

int main() {
  D d;
  B& br = d;
  D& dr = static_cast<D&>(br);
  // OK：br 确实是 D 的子对象
  return dr.extra == 42 ? 0 : 1;
}
```

```cpp run ub
struct B {};
struct D : B { int extra = 42; };

int main() {
  B b;
  D& dr = static_cast<D&>(b);
  // UB: b 不是任何 D 的子对象
  return dr.extra;
}
```

</div>

右边的程序在本机 AddressSanitizer 下报告 stack-buffer-overflow：`dr.extra` 读的是 `b` 后面的栈内存。

下面几种情况在编译期就是错误：

```cpp title="ptr-downcast-rules.cpp" error
struct VB {};
struct VD : virtual VB {};
struct B {};
struct PD : private B {};
struct A {};
struct L : A {};
struct R : A {};
struct M : L, R {};

VD* f(VB* p) { return static_cast<VD*>(p); }  // error: 经过虚基类
PD* g(B* p)  { return static_cast<PD*>(p); }  // error: 私有基类
M*  h(A* p)  { return static_cast<M*>(p); }   // error: A 是 M 的二义基类
M*  k(L* p)  { return static_cast<M*>(p); }   // OK
```

`static_cast` 只能在编译期加减一个固定的偏移。虚基类子对象的位置取决于整个对象的类型：`VD` 单独存在时，`VB` 子对象在某个偏移处；`VD` 作为另一个类的基类时，`VB` 可能在别处。编译期算不出偏移，所以禁止。这种情况要用 [[expr.dynamic.cast]]。

| | `static_cast<D*>(pb)` | `dynamic_cast<D*>(pb)` |
|---|---|---|
| 检查 | 无 | 运行期检查动态类型 |
| 类型不对时 | 未定义行为 | 空指针 |
| 要求多态类型 | 否 | 是 |
| 经过虚基类 | 非良构 | 可以 |
| 交叉转换 | 非良构 | 可以 |
| 代价 | 加减一个常量，偏移非零时还要先判空 | 调用运行时库 |

判空是必要的：空指针转换后还必须是空指针，不能减去偏移。所以多重继承下即使是 `static_cast`，也不是零开销。

## 枚举（¶7、¶8）

¶7 有作用域枚举可以转换为整数类型，结果等同于先转换到枚举的底层类型，再转换到目标类型。也可以转换为浮点类型，结果等同于把原值直接转换为该浮点类型。

```cpp run title="scoped-enum-out.cpp" ok
enum class Color : unsigned char { red = 1, big = 200 };

int main() {
  int a = static_cast<int>(Color::big);          // 200
  auto b = static_cast<signed char>(Color::big); // 200 → -56
  double c = static_cast<double>(Color::red);    // 1.0
  return a == 200 && b == -56 && c == 1.0 ? 0 : 1;
}
```

`b` 的值先是 `unsigned char` 的 200，再转换为 `signed char`。C++20 起整数转换按模 2<sup>8</sup> 取值（[[conv.integral]]），结果是确定的 -56。

¶8 整数或枚举类型的值可以转换为完整的枚举类型，结果取决于枚举有没有**固定底层类型**（fixed underlying type）。有作用域枚举总是有；无作用域枚举写了 `: 类型` 才有。

- 有固定底层类型：值先经整型提升或整型转换变成底层类型，再变成枚举。任何底层类型的值都是合法的枚举值，所以这总是有定义的。
- 没有固定底层类型：原值在枚举的**值域**（range of enumeration values，[[dcl.enum]]）内时不变，否则行为未定义。

值域是能容纳所有枚举符的最小位域的取值范围。`enum E { a, b, c };` 的枚举符是 0 到 2，需要 2 位，值域是 0 到 3：

```cpp title="enum-range.cpp" error
enum E { a, b, c };            // 值域 [0, 3]
enum F : unsigned char { x };  // 固定底层类型

constexpr E e1 = static_cast<E>(3);    // OK：在值域内
constexpr E e2 = static_cast<E>(4);    // error: UB，常量求值中被拒绝
constexpr F f1 = static_cast<F>(255);  // OK
constexpr F f2 = static_cast<F>(300);  // OK：先转换为 unsigned char 44
```

本机 Clang 报告 integer value 4 is outside the valid range of values [0, 3]。运行期不检查。

为什么要有值域：没有固定底层类型的枚举，编译器可以假设它的值总在值域内，用更窄的类型存储，或者在 `switch` 覆盖整个值域时省掉默认分支。有固定底层类型的枚举则相当于带了具名常量的整数类型，常用作强类型的 ID 或位标志，必须能容纳任何值。

¶8 最后还允许浮点值转换为枚举：先把原值转换为底层类型（[[conv.fpint]]，向零截断，超出范围是未定义行为），再转换为枚举。

## 浮点之间（¶9）

¶9 浮点 prvalue 可以转换为任何其他浮点类型：

- 源值在目标类型中能精确表示时，结果就是这个值；
- 源值落在目标类型两个相邻的值之间时，结果是二者之一，选哪个由实现定义，通常按当前舍入模式；
- 否则行为未定义。

这一条在 C++23 之后变得必要。C++23 引入了扩展浮点类型（`std::float16_t`、`std::bfloat16_t` 等，[[basic.extended.fp]]），它们之间的隐式转换只允许不降低精度等级（[[conv.double]]）。`double` 到 `std::float16_t` 不能隐式进行，只能靠 `static_cast`。

!!! lawyer "IEEE 754 下的超出范围"
    目标类型能表示无穷大时，`+inf` 也是它的一个值，于是 `1e300` 落在 `FLT_MAX` 和 `+inf` 两个相邻值之间，按第二条是实现定义的选择，而不是未定义行为。本机 Clang 在常量求值中接受 `constexpr float f = static_cast<float>(1e300);`，结果是 `+inf`。对没有无穷大的浮点格式，第三条才真正适用。

## 成员指针（¶11）

¶11 `D` 的成员指针（类型为 *cv1* `T`）可以转换为 `B` 的成员指针（类型为 *cv2* `T`），其中 `B` 是 `D` 的基类，*cv2* 不少于 *cv1*。注 5 提醒，函数类型没有 cv 限定，所以这里的 cv 只对数据成员有意义。

方向与指针相反。隐式的成员指针转换是基类到派生类（[[conv.mem]]）：`B` 的成员也是 `D` 的成员，`int B::*` 用在任何 `D` 对象上都安全。`static_cast` 允许倒过来，从 `int D::*` 到 `int B::*`。

```cpp run title="pm-upcast.cpp" ok
struct B { int b = 1; };
struct D : B { int d = 2; };

int main() {
  int D::* pmd = &D::d;
  int B::* pmb = static_cast<int B::*>(pmd);
  D obj;
  B& br = obj;
  return br.*pmb == 2 ? 0 : 1;   // OK：br 的动态类型 D 有成员 d
}
```

`B` 包含原成员，或者是包含原成员的类的基类时，结果指向原成员；否则行为未定义。注 6 补充，`B` 本身不必有这个成员，但之后用这个成员指针访问时，对象的动态类型必须有它（[[expr.mptr.oper]]）。上面如果 `br` 指代一个单纯的 `B` 对象，`br.*pmb` 就是未定义行为。MFC 的消息映射就依靠这条规则，把派生类的成员函数指针存成基类的成员函数指针。

## `void*` 到 `T*`（¶12）

¶12 指向 *cv1* `void` 的指针可以转换为指向 *cv2* `T` 的指针，`T` 是对象类型，*cv2* 不少于 *cv1*。结果分三种情况：

1. 原指针值是某个字节的地址，而这个地址不满足 `T` 的对齐要求：结果指针值未指定。
2. 否则，原指针指向对象 *a*，并且有一个类型与 `T` 相似、与 *a* **指针可互转**（pointer-interconvertible，[[basic.compound]]）的对象 *b*：结果指向 *b*。
3. 否则，指针值不变。

指针可互转是指两个对象可以用同一个地址互相到达，例如同一个对象、联合体和它的成员、标准布局类对象和它的第一个非静态数据成员。

```cpp run title="void-to-T.cpp" ok
struct S { int first; double second; };   // 标准布局

int main() {
  S s{1, 2.0};
  void* vp = &s;
  int* pi = static_cast<int*>(vp);  // s 与 s.first 可互转：pi 指向 s.first
  *pi = 10;
  int x = 5;
  void* vx = &x;
  int* px = static_cast<int*>(vx);  // 往返：得到原来的指针
  return s.first == 10 && px == &x ? 0 : 1;
}
```

第 2 条体现了 C++17（[[P0137R1]]）以来的对象模型：指针不只是一个地址，还记着它指向哪个对象。第 3 条的意思是，地址上没有可以互转过去的 `T` 对象时，结果仍然指向原来的对象，只是类型变成了 `T*`。通过它访问对象，就可能违反[[basic.lval#11|严格别名规则]]：

```cpp run title="void-to-T-alias.cpp" ub
int main() {
  float f = 1.0f;
  void* vp = &f;
  int* pi = static_cast<int*>(vp);  // 合法：指针值不变，仍指向 f
  return *pi;                       // UB: 用 int 左值读取 float 对象
}
```

对象指针之间的 `reinterpret_cast<T*>(p)` 正是用这两步 `static_cast` 定义的（[[expr.reinterpret.cast#7]]）。所以经 `void*` 中转并不比 `reinterpret_cast` 更安全，两者完全等价。要重新解释一个对象的位模式，用 `std::bit_cast` 或 `std::memcpy`（[[topics/type-punning]]）。

### 常量求值中的 `void*` 到 `T*` {{c++26}}

C++26（[[P2738R1]]）允许常量求值中把 `void*` 转换为 `T*`，前提是指针确实指向一个类型与 `T` 相似的对象。这样 `std::any`、类型擦除的函数包装器之类可以在编译期工作。

```cpp run title="constexpr-void-cast.cpp" ok
constexpr int f() {
  int x = 42;
  void* p = &x;
  return *static_cast<int*>(p);
}
static_assert(f() == 42);

int main() {}
```

本机 Clang 在 `-std=c++23` 下拒绝这个例子，在 `-std=c++2c` 下接受。

## `static_cast` 不能做的事

```cpp title="static-cast-no.cpp" error
struct A {};
struct B {};

void f(const int* cp, int* ip, A* pa, void (*fp)()) {
  static_cast<int*>(cp);    // error: 去掉 const，用 const_cast
  static_cast<long*>(ip);   // error: 无关的指针类型
  static_cast<B*>(pa);      // error: 没有继承关系
  static_cast<long>(ip);    // error: 指针到整数，用 reinterpret_cast
  static_cast<void*>(fp);   // error: 函数指针到 void*
}
```

后三种需要 `reinterpret_cast`（[[expr.reinterpret.cast]]）。函数指针到对象指针的转换是有条件支持的，主流平台都支持。

## 历史与演进

!!! history
    - C++98：引入四个具名转换，取代 C 风格转换的大部分用途。
    - C++11：加入第 3 段的左值到右值引用转换，为移动语义服务；加入有作用域枚举及第 7 段的转换。
    - C++17：[[P0137R1]] 引入指针可互转和指针指向对象的模型，第 12 段改写为现在的形式。无固定底层类型的枚举超出值域的转换，从结果未指定改为未定义行为。
    - C++20：第 5 段增加聚合第一个元素的情形（[[P0960R3]]）；有符号整数采用二进制补码，整数转换的结果变得确定。
    - C++23：扩展浮点类型让第 9 段的显式浮点转换成为必需。
    - C++26：常量求值中允许 `void*` 到 `T*`（[[P2738R1]]）。

## 常见误解

!!! pitfall "类型写错的向下转换总会出点错"
    `static_cast<Derived*>(base_ptr)` 在类型不对时不会失败，只会得到一个偏移错误的指针，之后的访问是未定义行为。不能保证类型的地方用 `dynamic_cast`，或者在调试构建里用 `assert(dynamic_cast<D*>(p))` 检查。

!!! pitfall "任何整数都能 static_cast 成枚举"
    对没有固定底层类型的枚举，超出值域就是未定义行为。从网络或文件读入的整数转换为枚举之前，要么给枚举指定底层类型，要么先检查范围。

!!! pitfall "经 void* 中转可以合法地做类型双关"
    `static_cast<int*>(static_cast<void*>(&f))` 和 `reinterpret_cast<int*>(&f)` 完全等价，用结果读取 `f` 都违反严格别名规则。

## 思考题

!!! question "思考题 1"
    `struct B {}; struct D : B {}; B b;` 下，`D&& r = static_cast<D&&>(std::move(b));` 是否良构？行为如何？

<details markdown="1">
<summary>答案</summary>

良构。第 2 段允许 *cv1* `B` 的亡值转换为 *cv2* `D&&`，这里 `D` 以非虚、可访问、无二义的方式派生自 `B`。

但 `b` 不是任何 `D` 对象的基类子对象，所以行为未定义。即使之后不使用 `r`，转换本身就已经是未定义行为。
</details>

!!! question "思考题 2"
    `enum class E : int { a }; float f = 3.9f;` 下，`static_cast<E>(f)` 是否合法？结果是什么？`static_cast<E>(1e20f)` 呢？

<details markdown="1">
<summary>答案</summary>

合法（第 8 段最后一句）。先把 3.9f 转换为底层类型 `int`，向零截断得到 3（[[conv.fpint]]），再转换为 `E`，结果是值为 3 的 `E`。

`1e20f` 截断后超出 `int` 的范围，[[conv.fpint]] 规定这是未定义行为。
</details>

!!! question "思考题 3"
    为什么 `static_cast<int B::*>(&D::d)` 可以，而 `int B::* p = &D::d;` 不行？哪个方向是安全的？

<details markdown="1">
<summary>答案</summary>

隐式的成员指针转换是 `int B::*` 到 `int D::*`：`B` 的成员都是 `D` 的成员，用在任何 `D` 对象上都安全。反方向不是对每个 `B` 对象都有意义，单纯的 `B` 对象没有成员 `d`，所以只能显式 `static_cast`（¶11），由程序员保证使用时对象的动态类型有这个成员。

这与对象指针恰好相反：`D*` 到 `B*` 是安全的隐式转换，`B*` 到 `D*` 需要 `static_cast`。
</details>

## 小结

!!! summary
    | 条文 | 转换 | 出错时 |
    |---|---|---|
    | ¶2、¶10 | 基类引用、指针到派生类 | 不是真的子对象：UB；虚基类、不可访问、二义：非良构 |
    | ¶3 | 左值到 `T&&`（`std::move`） | 不可访问或二义基类：非良构 |
    | ¶4 | 任意表达式到 `void` | 无 |
    | ¶5 | 隐式转换、explicit 构造或转换函数、聚合首元素 | 按初始化规则 |
    | ¶7 | 有作用域枚举到整数、浮点 | 无 |
    | ¶8 | 整数、枚举、浮点到枚举 | 无固定底层类型且超出值域：UB |
    | ¶9 | 浮点到浮点 | 介于两值之间：实现定义；超出范围：UB |
    | ¶11 | `T D::*` 到 `T B::*` | 不含原成员：UB |
    | ¶12 | `void*` 到 `T*` | 未对齐：值未指定；没有可互转的对象：指针值不变 |
