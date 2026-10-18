---
title: 核心 UB 目录 · 第 [expr] 章
summary: Annex F.3 的 34 条：溢出与除零、严格别名、无效表示、浮点/整数转换越界、各类 cast 的错误目标、空指针与越界指针、new/delete 不匹配、成员指针、移位、重叠赋值——逐条给出正文出处、改写后的例子，以及 UBSan/ASan 与常量求值的实测结果。
status: draft
related: ub, ub.basic, expr.pre, basic.lval, expr.static.cast, expr.delete, expr.add, expr.const.core
tags: UB, 附录, 表达式, 别名, sanitizer
updated: 2026-10-18
---

这一页是 [[ub]] 的第二部分，对应 Annex F.3：第 7 章 [expr] 中的显式 UB，外加附录归到这里的 [[basic.lval]]（严格别名）。这是 UB 最密集的一章，也是 sanitizer 最能发挥作用的一章——算术类 UB 几乎都能被 UBSan 抓到，而"类型不对"类 UB 大多抓不到。

实测环境与 [[ub.basic]] 相同：Clang 23.1.3，arm64 macOS，`-std=c++2c -O0 -g -fsanitize=address,undefined`。有两点本机特有的注意事项：

- 本机的 `-fsanitize=undefined` **不含** `vptr` 检查（多态类型的下行转换检查），要显式加 `-fsanitize=vptr`；
- macOS 上 ASan 默认关闭 new/delete 形式不匹配的检查，要设 `ASAN_OPTIONS=alloc_dealloc_mismatch=1`。

## 算术

### F.3.1 [ub:expr.expr.eval] {#expr.expr.eval}

**结果在数学上无定义或超出类型的可表示范围** · 正文 [[expr.pre#4]]

这是整数溢出 UB 的总出处：有符号整数运算的数学结果放不进结果类型就是 UB。无符号整数不受影响——它们的运算本来就定义为模 2ⁿ（[[basic.fundamental]]）。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <limits>
#include <cstdio>

int main(int argc, char**) {
  int m = std::numeric_limits<int>::max() - 1 + argc;   // 运行时才知道的 INT_MAX
  int x1 = m + 1;                                       // UB：2147483647 + 1 不可表示
  int n = std::numeric_limits<int>::min() + argc - 1;
  int x2 = n / -argc;                                   // UB：-2147483648 / -1 不可表示
  std::printf("%d %d\n", x1, x2);
}
```

**实测**：UBSan 两处都命中：`signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'`、`division of -2147483648 by -1 cannot be represented in type 'int'`。**常量求值**：`constexpr int x = INT_MAX + 1;` 被拒，`value 2147483648 is outside the range of representable values of type 'int'`。

### F.3.28 [ub:expr.mul.div.by.zero] {#expr.mul.div.by.zero}

**除以零** · 正文 [[expr.mul#4]]

`/` 或 `%` 的第二操作数为零即 UB——**不分整数和浮点**。附录的注释说，在浮点类型能表示无穷的系统上 `1.0 / 0.0` "不是 UB"，但正文 [[expr.mul#4]] 的措辞并没有这个例外；IEEE 754 给出 `+inf` 是实现的行为，不是标准的保证。

```cpp ub
int f(int d) {
  return 1 / d;   // d == 0 时 UB
}

double g(double d) {
  return 1.0 / d; // d == 0.0 时，按正文同样是 UB
}
```

**实测**：整数版 UBSan 报 `division by zero`。**常量求值**：`f(0)` 与 `constexpr double d = 1.0 / 0.0;` 都被拒（`division by zero`）；后者另有 [[expr.const.core#2.9]] 兜底——有限操作数产生非有限结果的算术本来就不是常量表达式。

### F.3.29 [ub:expr.mul.representable.type.result] {#expr.mul.representable.type.result}

**商不可表示时，a/b 与 a%b 都是 UB** · 正文 [[expr.mul#4]]

`(a/b)*b + a%b == a` 这个恒等式只在 `a/b` 可表示时成立。唯一的反例是 `INT_MIN / -1`（及其他有符号类型的对应情形）。注意 `INT_MIN % -1` 的数学结果是 0，完全可表示，但标准**同样**规定它是 UB——因为硬件往往用同一条除法指令同时算商和余数。

```cpp ub
#include <limits>

int q(int a, int b) { return a / b; }
int r(int a, int b) { return a % b; }

int main() {
  constexpr int m = std::numeric_limits<int>::min();
  int x = q(m, -1);   // UB：商 2147483648 不可表示
  int y = r(m, -1);   // UB：即使余数 0 可表示
}
```

**实测**：UBSan 对两者都报告，`%` 那一处的措辞也是 `division of -2147483648 by -1 cannot be represented in type 'int'`；本机打印 `-2147483648 0`。**常量求值**中 `INT_MIN % -1` 同样被拒（`value 2147483648 is outside the range of representable values`）。在 x86 上 `idiv` 遇到这种情况会触发除法异常（SIGFPE）；本机 arm64 的 `sdiv` 不陷入，只是安静地给出 `INT_MIN`。

### F.3.33 [ub:expr.shift.neg.and.width] {#expr.shift.neg.and.width}

**移位量为负或不小于位宽** · 正文 [[expr.shift#1]]

位宽指的是**提升后**的左操作数的位宽：`char c; c << 20` 是对 `int` 移位，合法。C++20 起有符号移位改为按补码定义，`-1 << 1`、`1 << 31` 都不再是 UB；剩下的 UB 只有移位量越界这一种。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int main(int argc, char**) {
  int s = 31 + argc;
  int y1 = 1 << s;       // UB：移位量 32 等于 int 的位宽
  int y2 = 1 << -argc;   // UB：移位量为负
  int ok = 1 << 31;      // OK（C++20 起）：结果是 INT_MIN
  std::printf("%d %d %d\n", y1, y2, ok);
}
```

**实测**：UBSan 报 `shift exponent 32 is too large for 32-bit type 'int'` 与 `shift exponent -1 is negative`。**常量求值**分别被拒：`shift count 32 >= width of type 'int' (32 bits)`、`negative shift count -1`。

## 别名与值表示

### F.3.2 [ub:expr.basic.lvalue.strict.aliasing.violation] {#expr.basic.lvalue.strict.aliasing.violation}

**通过不可访问的类型读写对象（严格别名）** · 正文 [[basic.lval#11]]

对象只能通过与其动态类型**相似**的类型、对应的有/无符号类型，或 `char`/`unsigned char`/`std::byte` 的 glvalue 访问（[[g:type-accessible]]）。这条规则让编译器可以假定 `int*` 和 `float*` 不指向同一处。

```cpp ub run flags="-std=c++2c -O2" cc=clang_trunk
#include <cstdio>

int foo(float* f, int* i) {
  *i = 1;
  *f = 0.f;    // UB：通过 float 类型的 glvalue 写一个 int 对象
  return *i;   // 编译器可以假定 *f 没有改动 *i，直接返回 1
}

int main() {
  int x = 0;
  x = foo(reinterpret_cast<float*>(&x), &x);
  std::printf("%d\n", x);
}
```

**实测**：`-O0` 打印 `0`，`-O2` 打印 `1`，`-O2 -fno-strict-aliasing` 又打印 `0`——这是"优化等级改变程序输出"的教科书例子。ASan/UBSan 不检查别名规则；Clang 单独的 TypeSanitizer（`-fsanitize=type`，不在 `undefined` 组里）在本机能抓到：`TypeSanitizer: type-aliasing-violation … WRITE of size 4 … with type float accesses an existing object of type int`。

### F.3.3 [ub:expr.basic.lvalue.union.initialization] {#expr.basic.lvalue.union.initialization}

**用不是该联合类型对象的实参调用联合的默认复制/移动** · 正文 [[basic.lval#11]]

联合的隐式复制/移动是逐字节拷贝"对象表示"，它能这么做的前提是源确实是一个活着的同类型联合对象。

```cpp ub
union U { int x; };

void f() {
  alignas(U) char u[sizeof(U)] = {};
  U o = reinterpret_cast<U&>(u);   // UB：实参不指代一个 U 对象
}
```

**实测**：无报告。

### F.3.5 [ub:conv.lval.valid.representation] {#conv.lval.valid.representation}

**对值表示无效的对象做左值到右值转换** · 正文 [[conv.lval#3]]

读取一个对象时，其位模式必须是该类型的合法值表示。`bool` 是最典型的例子：在主流 ABI 中只有 0 和 1 是合法表示。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstring>
#include <cstdio>

bool f() {
  bool b = true;
  char c = 42;
  std::memcpy(&b, &c, 1);
  return b;   // UB：42 不是 bool 的合法值表示
}

int main() {
  bool b = f();
  std::printf("%d %d\n", (int)b, b ? 1 : 0);
}
```

**实测**：UBSan 的 `bool` 检查命中：`load of value 42, which is not a valid value for type 'bool'`。**常量求值**：`std::bit_cast<bool>((unsigned char)42)` 被拒，`value 42 cannot be represented in type 'bool'`。

### F.3.34 [ub:expr.assign.overlap] {#expr.assign.overlap}

**赋值的源与目标存储部分重叠** · 正文 [[expr.assign#7]]

若被存储的值是从另一个与目标存储重叠的对象读出来的，则重叠必须**完全一致且类型相同**（也就是自赋值 `x = x`），否则 UB。这允许编译器用不考虑重叠的方式实现赋值（类比 `memcpy` 与 `memmove`）。

```cpp ub run flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

int main() {
  int x = 0x01020304;
  char* c = reinterpret_cast<char*>(&x);
  x = *c;   // UB：源（x 的第一个字节）与目标 x 部分重叠
  std::printf("%d\n", x);
}
```

**实测**：无报告；本机（小端）打印 `4`。

## 浮点与整数转换

### F.3.6 [ub:conv.double.out.of.range] {#conv.double.out.of.range}

**浮点转换时源值超出目标类型范围** · 正文 [[conv.double#2]]

`double` 转 `float`：能精确表示就精确；落在两个相邻可表示值之间就由实现选一个；否则 UB。关键在"范围"：IEEE 754 的 `float` 能表示 ±∞，于是任何有限的 `double` 都落在两个相邻 `float` 值之间（最坏也在 `FLT_MAX` 与 `+inf` 之间），结果是实现定义的选择而非 UB。只有在没有无穷的浮点格式上，`DBL_MAX` 转 `float` 才是 UB。

```cpp ub
#include <limits>

int main() {
  double d2 = std::numeric_limits<double>::max();
  float f = d2;   // IEEE 754 平台上不是 UB（结果由实现在 FLT_MAX 与 +inf 中选择）
  int i = d2;     // UB：见 F.3.7，DBL_MAX 不能表示为 int
}
```

**实测**：UBSan 只对 `int` 那一行报 `1.79769e+308 is outside the range of representable values of type 'int'`。**常量求值**：用 `DBL_MAX` 初始化一个 `constexpr float` 被 Clang 接受，与上面的分析一致。

### F.3.7 [ub:conv.fpint.float.not.represented] {#conv.fpint.float.not.represented}

**浮点转整数时截断后的值不可表示** · 正文 [[conv.fpint#1]]

浮点转整数先截断小数部分，若截断后的值放不进目标类型就是 UB。注意这与整数之间的窄化不同（整数转换从 C++20 起总是有定义的，按模运算）。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <limits>
#include <cstdio>

int main() {
  volatile double d = (double)std::numeric_limits<int>::max() + 1;
  int x1 = d;   // UB：2147483648 不能表示为 int
  std::printf("%d\n", x1);
}
```

**实测**：UBSan 的 `float-cast-overflow` 命中：`2.14748e+09 is outside the range of representable values of type 'int'`。**常量求值**被拒：`value 1.0E+300 is outside the range of representable values of type 'const int'`。

### F.3.8 [ub:conv.fpint.int.not.represented] {#conv.fpint.int.not.represented}

**整数转浮点时值超出浮点类型范围** · 正文 [[conv.fpint#2]]

与 F.3.6 同理，只在浮点类型的范围有限（没有无穷）时才可能触发。IEEE 754 `float` 的最大有限值约为 3.4×10³⁸，远大于任何 64 位整数，所以在主流平台上这一条基本不会遇到。

```cpp ub
int main() {
  unsigned long long x2 = -1;   // OK：无符号回绕，得到 2⁶⁴−1
  float f = x2;                 // 仅在 float 没有无穷、且最大值小于 2⁶⁴−1 的系统上是 UB
}
```

### F.3.17 [ub:expr.static.cast.fp.outside.range] {#expr.static.cast.fp.outside.range}

**显式浮点转换时值超出目标范围** · 正文 [[expr.static.cast#9]]

这是 F.3.6 的 `static_cast` 版本，规则逐字相同。

```cpp ub
#include <cfloat>

void f() {
  double d = FLT_MAX;
  d *= 16;
  float f = static_cast<float>(d);   // 仅在 float 不能表示 +inf 的系统上是 UB
}
```

**实测**：在 IEEE 754 的本机上，`static_assert(static_cast<float>(FLT_MAX * 16.0) > FLT_MAX)` 通过常量求值——结果是 `+inf`。

## 函数调用与成员访问

### F.3.11 [ub:expr.call.different.type] {#expr.call.different.type}

**通过类型不调用兼容的表达式调用函数** · 正文 [[expr.call#6]]

调用表达式的函数类型必须与被调函数**定义**的类型调用兼容（[[g:call-compatible]]）：相同，或者只差一个"`noexcept` 可以去掉"的函数指针转换。用 `reinterpret_cast` 换函数指针类型再调用是 UB——参数可能经由完全不同的寄存器传递。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

using f_int = int (*)(int);
int f1(float x) { std::printf("%f\n", x); return 10; }

int main() {
  return reinterpret_cast<f_int>(f1)(20);   // UB：表达式的函数类型与 f1 的定义不同
}
```

**实测**：UBSan 的 `function` 检查命中：`call to function f1(float) through pointer to incorrect function type 'int (*)(int)'`。程序随后打印了一个与 20 无关的浮点数——`int` 实参放在整数寄存器里，`f1` 却从浮点寄存器取值。常量求值里根本不允许 `reinterpret_cast`，所以此类 UB 不会出现在常量表达式中。

### F.3.12 [ub:expr.ref.member.not.similar] {#expr.ref.member.not.similar}

**E1.E2 中 E1 指代的对象类型与 E1 的类型不相似** · 正文 [[expr.ref#10]]

成员访问要求左边真的是那个类型的对象。正文的例子更有启发性：同一个 `D d`，`static_cast<B&>(d).j` 是合法的（它真的指向 B 子对象），`reinterpret_cast<B&>(d).j` 则是 UB（它指向 d 的起始地址，那里是 A 子对象）。

```cpp ub
struct A { int i; };
struct B { int j; };

A a;
int x = reinterpret_cast<B&>(a).j;   // UB：a 是 A，不是 B
```

**实测**：无报告（A 与 B 布局相同，读出了 `a.i`）。

### F.3.27 [ub:expr.mptr.oper.member.func.null] {#expr.mptr.oper.member.func.null}

**.* 的第二操作数是空成员指针** · 正文 [[expr.mptr.oper#6]]

附录的 stable name 带 "func"，但正文的规则对数据成员指针和成员函数指针一视同仁。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct S { int f() { return 1; } };

int main() {
  S cs;
  int (S::*pm)() = nullptr;
  return (cs.*pm)();   // UB：第二操作数是空成员指针值
}
```

**实测**：ASan 报 `SEGV on unknown address 0x000000000000 (pc 0x000000000000 …)`——跳转到了地址 0。**常量求值**被拒（`subexpression not valid in a constant expression`）。

### F.3.26 [ub:expr.mptr.oper.not.contain.member] {#expr.mptr.oper.not.contain.member}

**.* 的对象表达式不含该成员** · 正文 [[expr.mptr.oper#4]]

E1 的结果对象类型必须与 E1 的类型相似，且其最派生对象必须含有 E2 所指的成员。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct B {};
struct D : B { int x; };

int main() {
  B* b = new B;
  D* d = static_cast<D*>(b);   // 本身已是 UB（F.3.18）
  int D::*p = &D::x;
  (*d).*p = 1;                 // UB：动态类型 B 不含 x
  delete b;
}
```

**实测**：ASan 报 `heap-buffer-overflow`（写到了 1 字节的 B 之后）。**常量求值**在更早的 `static_cast` 处就停下：`cannot cast object of dynamic type 'B' to type 'D'`。

## 类型转换

### F.3.9 [ub:conv.ptr.virtual.base] {#conv.ptr.virtual.base}

**把不指向有效对象的派生类指针转成虚基类指针** · 正文 [[conv.ptr#3]]

到虚基类的转换要读对象内的虚基类偏移，所以指针必须指向生命周期内（或正在构造/析构中）的、类型相似的对象。past-the-end 指针不行。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct B { int b; };
struct D : virtual B {};

int main() {
  D ds[1];
  B* b = &ds[1];   // UB：&ds[1] 是 past-the-end 指针，不指向对象
  return b != nullptr;
}
```

**实测**：ASan 报 `stack-buffer-overflow`——转换时去读了 `ds` 之后那块内存里的"vptr"。这是少数能被 ASan 间接抓到的"纯转换"类 UB。

### F.3.10 [ub:conv.member.missing.member] {#conv.member.missing.member}

**基类成员指针转派生类成员指针，而派生类不可能含该成员** · 正文 [[conv.mem#2]]

成员指针的隐式转换方向是"基 → 派生"（与对象指针相反）。若原成员根本不在 D 里（例如它是另一个派生类的成员，先被 `static_cast` 到基类再转回来），结果 UB。

```cpp ub
struct B {};
struct D1 : B { int d1; };
struct D2 : B {};

void f() {
  int (D1::*pd1) = &D1::d1;
  int (B::*pb) = static_cast<int (B::*)>(pd1);   // OK：见 F.3.19 的条件
  int (D2::*pd2) = pb;                           // UB：D2 不含 d1
}
```

**实测**：无报告。给 `D2` 加一个成员并通过 `pd2` 读取，本机读到了那个成员的值——成员指针只是一个偏移量。

### F.3.15 [ub:expr.static.cast.base.class] {#expr.static.cast.base.class}

**引用的 static_cast 下行转换：对象实际不是 D** · 正文 [[expr.static.cast#2]]

`static_cast<D&>(b)` 不做运行时检查，它只是假定 `b` 确实是某个 D 对象的基类子对象并调整偏移。假设错了就是 UB。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
struct B { virtual ~B() = default; };
struct D1 : B {};
struct D2 : B { int x = 0; };

int main() {
  D1 d;
  B& b = d;
  D2& r = static_cast<D2&>(b);   // UB：b 指代的是 D1 的基类子对象
  return r.x;
}
```

**实测**：加上 `-fsanitize=vptr` 后 UBSan 命中：`downcast of address … which does not point to an object of type 'D2'`。只用 `address,undefined` 时，报告来自随后的越界读（ASan `stack-buffer-overflow`）。vptr 检查只适用于多态类型；附录原例里的 B 没有虚函数，那就没有任何工具能在运行时发现它。**常量求值**被拒：`cannot cast object of dynamic type 'D1' to type 'D2'`。

### F.3.18 [ub:expr.static.cast.downcast.wrong.derived.type] {#expr.static.cast.downcast.wrong.derived.type}

**指针的 static_cast 下行转换：该位置没有外围的 D 对象** · 正文 [[expr.static.cast#10]]

F.3.15 的指针版本。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
struct B { virtual ~B() = default; };
struct D1 : B {};
struct D2 : B { int x = 0; };

int main() {
  B* bp = new D1;
  D2* p = static_cast<D2*>(bp);   // UB：bp 指向的 B 不是某个 D2 的子对象
  int r = p->x;
  delete bp;
  return r;
}
```

**实测**：`-fsanitize=vptr` 报 `downcast of address … which does not point to an object of type 'D2'`，接着报 `member access within address … which does not point to an object of type 'D2'`；不加 vptr 时 ASan 在 `p->x` 处报 `heap-buffer-overflow`。

### F.3.19 [ub:expr.static.cast.does.not.contain.original.member] {#expr.static.cast.does.not.contain.original.member}

**派生类成员指针 static_cast 到基类，而该基类与原成员无关** · 正文 [[expr.static.cast#11]]

"派生 → 基"方向的成员指针转换需要显式 `static_cast`。结果合法的条件是：B 含有原成员，或 B 是含有原成员的类的基类或派生类（后者正是 F.3.10 例子中合法的那一步）。

```cpp ub
struct A { char c; };
struct B { int i; };
struct D : A, B {};

int main() {
  char D::*p1 = &D::c;                        // c 是 A 的成员
  char B::*p2 = static_cast<char B::*>(p1);   // UB：B 不含 c，也与 A 无继承关系
}
```

### F.3.16 [ub:expr.static.cast.enum.outside.range] {#expr.static.cast.enum.outside.range}

**转换到无固定底层类型的枚举时值超出枚举值范围** · 正文 [[expr.static.cast#8]]

无固定底层类型的枚举，其**值范围**（[[dcl.enum]]）是能容纳所有枚举量的最小位域范围，而不是枚举量本身的集合。`enum A { e1 = 1, e2 }` 的值范围是 0–3，所以 `static_cast<A>(3)` 合法，`static_cast<A>(4)` 才是 UB。有固定底层类型（`enum class`、`enum E : int`）的枚举没有这个问题。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

enum A { e1 = 1, e2 };   // 值范围 [0, 3]

int main(int argc, char**) {
  A ok = static_cast<A>(3);          // OK：在值范围内，虽然不等于任何枚举量
  A a  = static_cast<A>(3 + argc);   // UB：4 超出值范围
  std::printf("%d %d\n", (int)ok, (int)a);
}
```

**实测**：UBSan 的 `enum` 检查在**读取**时命中：`load of value 4, which is not a valid value for type 'A'`（它不在转换处检查）。**常量求值**在转换处就拒绝：`integer value 4 is outside the valid range of values [0, 3] for the enumeration type 'A'`——这条诊断把"值范围"的含义说得很清楚。

### F.3.13 [ub:expr.dynamic.cast.pointer.lifetime] {#expr.dynamic.cast.pointer.lifetime}

**对不指向合适存活对象的非空指针做 dynamic_cast** · 正文 [[expr.dynamic.cast#7]]

`dynamic_cast` 的运行时检查要读对象的 vptr，所以操作数必须指向类型相似、在生命周期内（或构造/析构中）的对象。

```cpp ub
struct B { virtual ~B() = default; };

void f() {
  B bs[1];
  B* dp = dynamic_cast<B*>(bs + 1);   // UB：bs + 1 是 past-the-end 指针
}
```

**实测**：无报告，返回了非空指针。原因很朴素：转换到**同一个类型**时 `dynamic_cast` 不需要做运行时检查，Clang 直接返回操作数，根本没有读内存。换成需要运行时检查的目标类型，就会去读 past-the-end 处的"vptr"。

### F.3.14 [ub:expr.dynamic.cast.glvalue.lifetime] {#expr.dynamic.cast.glvalue.lifetime}

**对不指代合适存活对象的 glvalue 做 dynamic_cast** · 正文 [[expr.dynamic.cast#7]]

```cpp ub
struct B { virtual ~B() = default; };

void f() {
  B bs[1];
  B& dr = dynamic_cast<B&>(bs[1]);   // UB（bs[1] 本身已是对 past-the-end 指针的间接，见 F.3.20）
}
```

## 指针、new 与 delete

### F.3.20 [ub:expr.unary.dereference] {#expr.unary.dereference}

**对不指向对象或函数的指针做间接** · 正文 [[expr.unary.op#1]]

`*p` 要求 `p` 指向对象或函数，`typeid` 是唯一例外。空指针和 past-the-end 指针都不指向对象，所以 `*nullptr`、`*end` 都是 UB——**即使结果马上被 `&` 取回地址**（这一点 C 与 C++ 不同：C 规定 `&*p` 不求值 `*`）。注意指向生命周期外对象的指针**可以**间接（[[basic.life]] 的"有限使用"），那是另一组规则。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
int f(int* p) { return *p; }

int main() {
  return f(nullptr);   // UB：解引用空指针
}
```

**实测**：UBSan 的 `null` 检查报 `load of null pointer of type 'int'`，随后 ASan 报 `SEGV on unknown address 0x000000000000`。**常量求值**被拒：`dereferencing a null pointer is not allowed in a constant expression`。

### F.3.30 [ub:expr.add.out.of.bounds] {#expr.add.out.of.bounds}

**创建越界指针** · 正文 [[expr.add#4.3]]

指针算术的结果只能落在数组的 `[0, n]` 区间内（`n` 即 past-the-end）。**仅仅算出**越界指针就是 UB，不需要解引用。非数组对象被当作单元素数组。

```cpp ub
static const int arrs[10]{};
static const int arrs2[10][10]{};

void f() {
  const int* end = arrs + 10;          // OK：past-the-end
  const int* y = arrs + 11;            // UB：创建越界指针
  const int (*z)[10] = arrs2 + 11;     // UB：同上，元素类型是 int[10]
}
```

**实测**：运行时**无报告**——UBSan 的 `pointer-overflow` 只检查地址回绕，ASan 只检查实际访问。真正读 `a[10]` 时 UBSan 的 `bounds` 检查（`index 10 out of bounds for type 'int[10]'`）和 ASan 才会命中。**常量求值**则直接拒绝创建：`cannot refer to element 11 of array of 10 elements in a constant expression`。

### F.3.31 [ub:expr.add.sub.diff.pointers] {#expr.add.sub.diff.pointers}

**两个不属于同一数组的指针相减** · 正文 [[expr.add#5.3]]

```cpp ub
#include <cstddef>

void f() {
  int x[2];
  int y[2];
  std::ptrdiff_t off = x - y;   // UB：x 与 y 是不同的数组
}
```

**实测**：运行时无报告（本机打印 `-8`，即两个栈数组相差 8 个 `int`）。**常量求值**被拒，Clang 的措辞是 `arithmetic involving unrelated objects '&x[0]' and '&y[0]' has unspecified value`。

### F.3.32 [ub:expr.add.not.similar] {#expr.add.not.similar}

**指针算术中指针类型与数组元素类型不相似** · 正文 [[expr.add#6]]

指针算术按"数组元素"计步。若 `p` 的类型是 `T*` 而它实际指向的数组元素类型与 `T` 不相似，`p + 1` 就是 UB——最常见的形式是用基类指针遍历派生类数组。

```cpp ub
#include <cstddef>

struct S     { int i; };
struct T : S { double d; };

int sum(const S* s, std::size_t count) {
  int r = 0;
  for (const S* end = s + count; s != end; ++s)   // UB：s 实际指向 T[] 的元素
    r += s->i;
  return r;
}

int main() {
  T test[5]{};
  return sum(test, 5);
}
```

正文的例子说明了这条规则的"苛刻"：`reinterpret_cast<unsigned int*>(arr + 1)` 读一次是合法的（有/无符号对应类型可以别名），但再 `+ 1` 就是 UB，因为 `unsigned int` 与 `int` 不相似。

**实测**：无报告。`sizeof(S)` 是 4、`sizeof(T)` 是 16，`++s` 走 4 字节，后续元素读到的是 `T` 内部的填充与 `double` 的字节。

### F.3.21 [ub:expr.new.non.allocating.null] {#expr.new.non.allocating.null}

**非分配形式的 placement new 得到空指针** · 正文 [[expr.new#22]]

`operator new(std::size_t, void*)` 这类非分配形式（[[new.delete.placement]]）不能返回空，所以传空指针给 placement new 是 UB。（用户也不能替换这个函数——它在 `<new>` 中定义且不可替换；附录的第一个例子写的是一个替换品，那本身就违反了库的规则。）

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

struct A { int x; };

int main() {
  char* p = nullptr;
  A* a = new (p) A;   // UB：非分配形式的 new 得到空指针
  return a != nullptr;
}
```

**实测**：UBSan 报 `constructor call on null pointer of type 'A'`。

### F.3.22 [ub:expr.delete.mismatch] {#expr.delete.mismatch}

**单对象 delete 的操作数不来自单对象 new** · 正文 [[expr.delete#2]]

单对象 `delete p` 的 `p` 只能是空指针、来自非数组 *new-expression* 的指针，或其基类子对象的指针。

!!! lawyer "附录与正文对不上"
    在当前草案中，正文 [[expr.delete#2]] 把 `[ub:expr.delete.mismatch]` 挂在**单对象** delete 那一句上，把 `[ub:expr.delete.array.mismatch]` 挂在**数组** delete 那一句上；而 Annex F 中这两个条目的摘要和例子恰好反了过来（F.3.22 写的是"对单对象 new 的结果用数组 delete"）。两种情况都是 UB，结论不受影响，但引用时以正文为准。本页按正文的挂法给例子。

```cpp ub
int main() {
  int* x = new int[10];
  delete x;   // UB：单对象 delete，操作数来自数组 new
}
```

**实测**：Clang 编译期警告 `'delete' applied to a pointer that was allocated with 'new[]'; did you mean 'delete[]'? [-Wmismatched-new-delete]`。运行时 macOS 上的 ASan 默认不查，设 `ASAN_OPTIONS=alloc_dealloc_mismatch=1` 后报 `alloc-dealloc-mismatch (operator new [] vs operator delete)`。**常量求值**被拒。

### F.3.23 [ub:expr.delete.array.mismatch] {#expr.delete.array.mismatch}

**数组 delete 的操作数不来自数组 new** · 正文 [[expr.delete#2]]

`delete[] p` 的 `p` 只能是空指针或来自（非 placement 的）数组 *new-expression* 的指针。注意是"来自数组 new"，**不包括**指向其中某个元素或基类子对象的指针。

```cpp ub
int main() {
  int* x = new int;
  delete[] x;   // UB：数组 delete，操作数来自单对象 new
}
```

**实测**：编译期警告 `'delete[]' applied to a pointer that was allocated with 'new'; did you mean 'delete'?`；`alloc_dealloc_mismatch=1` 时 ASan 报 `alloc-dealloc-mismatch (operator new vs operator delete [])`；**常量求值**被拒。

### F.3.24 [ub:expr.delete.dynamic.type.differ] {#expr.delete.dynamic.type.differ}

**通过没有虚析构函数的基类指针 delete 派生类对象** · 正文 [[expr.delete#3]]

单对象 delete 时，静态类型与动态类型不相似，且选中的不是销毁型 `operator delete`（*destroying operator delete*），则静态类型必须是动态类型的基类并且有虚析构函数。

```cpp ub
struct B { int a; };
struct D : B { int b; };

void f() {
  B* b = new D;
  delete b;   // UB：B 没有虚析构函数
}
```

**实测**：单继承时**无报告**——`B` 恰好位于 `D` 的起始地址，释放的指针是对的，只是 `~D` 没被调用。换成多继承（`struct D : A, B`，删除 `B*`）后，ASan 报 `attempting free on address which was not malloc()-ed`：传给 `operator delete` 的是 B 子对象的地址，不是分配的起点。**常量求值**被拒：`delete of object with dynamic type 'D' through pointer to base class type 'B' with non-virtual destructor`。

### F.3.25 [ub:expr.delete.dynamic.array.dynamic.type.differ] {#expr.delete.dynamic.array.dynamic.type.differ}

**数组 delete 时动态类型与静态类型不相似** · 正文 [[expr.delete#3]]

数组没有"多态删除"：即使 B 有虚析构函数，`delete[]` 一个指向 `D[]` 的 `B*` 也是 UB——实现需要知道元素大小才能逐个析构，而元素大小来自静态类型。

```cpp ub
struct B { virtual ~B() = default; int x; };
struct D : B { int y; };

void f(int n) {
  D* dp = new D[n];
  delete[] dp;   // OK
  B* bp = new D[n];
  delete[] bp;   // UB：即使有虚析构函数
}
```

**实测**：本机运行无报告。在这个例子里 `sizeof(D) == sizeof(B) == 16`（Itanium ABI 让 `y` 复用了 B 的尾部填充），步长恰好没错；但把派生类换成 `sizeof` 为 24 的类型后，本机运行同样没有任何报告——"没出事"不说明任何问题。
