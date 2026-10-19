---
title: 核心 UB 目录 · 第 [expr] 章
summary: 第 7 章明文写出的 34 条未定义行为：溢出与除零、移位、浮点与整数转换越界、空指针与越界指针、严格别名与无效的值表示、各种 cast 的错误目标、成员指针、new 与 delete 不配对，以及它们在 sanitizer 和常量求值中的表现。
status: done
related: ub, ub.basic, expr.pre, basic.lval, expr.static.cast, expr.delete, expr.add, expr.const.core
tags: UB, 附录, 表达式, 别名, sanitizer
updated: 2026-10-19
---

!!! tldr
    - 算术类的未定义行为（有符号溢出、除以零、`INT_MIN / -1`、移位量为负或不小于位宽）UBSan 基本都能发现，常量求值也一定会拒绝。
    - 指针算术的结果只能落在同一数组的下标 0 到 n 之间；只是算出一个越界指针就已经是未定义行为，不需要解引用。
    - 类型不对的访问（严格别名、错误的 `static_cast` 下行转换、对象类型与表达式类型不符）大多没有运行时工具能发现，后果往往在开启优化后才显现。
    - new 和 delete 的形式必须配对；通过基类指针 delete 要求基类有虚析构函数，数组 delete 则完全不允许多态。
    - 浮点转换只在值超出目标类型的范围时才是未定义行为。IEEE 754 的浮点类型能表示无穷，所以 `double` 转 `float` 不会触发，浮点转整数则会。

Annex F 汇总了核心语言中明文写出的未定义行为，总览见 [[ub]]。它的 F.3 节对应第 7 章 [expr]，另外包括 [[basic.lval]] 中的严格别名规则，共 34 条，是未定义行为最密集的一节。下面按主题分组，不按附录编号排列。

下文的运行结果都来自本机 Clang 23（arm64 macOS），默认用 `-O0 -g -fsanitize=address,undefined` 编译，也就是同时开启 ASan（检查内存访问）和 UBSan（检查一部分未定义行为）。本机环境有两点要注意：

- 本机的 `-fsanitize=undefined` 不包含 `vptr` 检查（检查多态对象的动态类型），要另外加 `-fsanitize=vptr`；
- macOS 上 ASan 默认不检查 new 和 delete 形式不配对，要设置环境变量 `ASAN_OPTIONS=alloc_dealloc_mismatch=1`。

常量求值指把同样的操作放进 `constexpr` 变量的初始化里。按 [[expr.const.core]]，编译器必须拒绝其中的核心语言未定义行为，所以这是标准层面唯一保证能发现这些错误的手段。

## 算术

### F.3.1 结果在数学上无定义或超出类型的范围 {#expr.expr.eval}

`[ub:expr.expr.eval]` · 正文 [[expr.pre#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
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

表达式求值时，如果结果在数学上没有定义，或者不在结果类型能表示的范围内，就是未定义行为。这是有符号整数溢出的总出处。无符号整数不受影响，它们的运算本来就定义为对 2ⁿ 取模（[[basic.fundamental]]）。

本机运行时，UBSan 两处都报告了：`signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'` 和 `division of -2147483648 by -1 cannot be represented in type 'int'`。常量求值中 `INT_MAX + 1` 被拒绝，诊断是 `value 2147483648 is outside the range of representable values of type 'int'`。

### F.3.28 除以零 {#expr.mul.div.by.zero}

`[ub:expr.mul.div.by.zero]` · 正文 [[expr.mul#4]]

```cpp ub
int f(int d) {
  return 1 / d;    // d == 0 时 UB
}

double g(double d) {
  return 1.0 / d;  // d == 0.0 时，按正文同样是 UB
}
```

`/` 或 `%` 的第二个操作数为零就是未定义行为，整数和浮点都一样。附录的例子注释说，在浮点类型能表示无穷的系统上 `1.0 / 0.0` 不是未定义行为，但正文 [[expr.mul#4]] 没有这个例外。IEEE 754 给出 `+inf` 是实现的行为，不是标准的保证。

本机运行整数版本时，UBSan 报告 `division by zero`。常量求值中 `f(0)` 和 `1.0 / 0.0` 都被拒绝，诊断是 `division by zero`。后者另有 [[expr.const.core#2.9]] 兜底：操作数有限而结果不是有限值的浮点运算，本来就不是常量表达式。

### F.3.29 商不可表示时，a/b 和 a%b 都是未定义行为 {#expr.mul.representable.type.result}

`[ub:expr.mul.representable.type.result]` · 正文 [[expr.mul#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <climits>
#include <cstdio>

int q(int a, int b) { return a / b; }
int r(int a, int b) { return a % b; }

int main() {
  std::printf("%d %d\n", q(INT_MIN, -1), r(INT_MIN, -1));   // UB：两者都是
}
```

如果商 `a/b` 能用结果类型表示，`(a/b)*b + a%b` 等于 `a`；否则 `a/b` 和 `a%b` 都是未定义行为。对 `int` 来说，唯一的反例是 `INT_MIN / -1`。`INT_MIN % -1` 的数学结果是 0，完全可以表示，标准仍然规定它是未定义行为。一个常见的解释是：硬件通常用同一条除法指令同时算出商和余数，商溢出时余数也拿不到。

本机运行时，UBSan 对两者都报告，`%` 那一处的措辞也是 `division of -2147483648 by -1 cannot be represented in type 'int'`，程序打印 `-2147483648 0`。常量求值中 `INT_MIN % -1` 同样被拒绝。在 x86 上，`idiv` 指令遇到这种情况会触发除法异常（SIGFPE）；本机 arm64 的 `sdiv` 不会陷入，只是给出 `INT_MIN`。

### F.3.33 移位量为负或不小于位宽 {#expr.shift.neg.and.width}

`[ub:expr.shift.neg.and.width]` · 正文 [[expr.shift#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int main(int argc, char**) {
  int s = 31 + argc;
  int y1 = 1 << s;       // UB：移位量 32 等于 int 的位宽
  int y2 = 1 << -argc;   // UB：移位量为负
  int ok = 1 << 31;      // OK（C++20 起）：结果是 INT_MIN
  std::printf("%d %d %d\n", y1, y2, ok);
}
```

这里的位宽指整数提升之后左操作数的位宽，所以 `char c; c << 20` 是对 `int` 移位，没有问题。C++20 起，有符号数的移位按补码定义，`-1 << 1`、`1 << 31` 都不再是未定义行为；剩下的只有移位量越界这一种。

本机运行时，UBSan 报告 `shift exponent 32 is too large for 32-bit type 'int'` 和 `shift exponent -1 is negative`。常量求值中两者分别被拒绝，诊断是 `shift count 32 >= width of type 'int' (32 bits)` 和 `negative shift count -1`。

## 浮点与整数转换

这一组的四条规则形式相同：转换的源值超出目标类型能表示的范围时是未定义行为。关键在于范围怎么算。IEEE 754 的浮点类型能表示 ±∞，于是任何有限值都落在它的范围之内。

### F.3.6 浮点转换时源值超出目标类型的范围 {#conv.double.out.of.range}

`[ub:conv.double.out.of.range]` · 正文 [[conv.double#2]]

```cpp ub
#include <limits>

int main() {
  double d2 = std::numeric_limits<double>::max();
  float f = d2;   // IEEE 754 平台上不是 UB（结果由实现在 FLT_MAX 与 +inf 中选择）
  int i = d2;     // UB：见 F.3.7，DBL_MAX 不能表示为 int
}
```

`double` 转 `float` 时，值能精确表示就精确转换；落在两个相邻的可表示值之间，就由实现选择其中一个；否则是未定义行为。IEEE 754 的 `float` 能表示 +∞，所以任何有限的 `double` 最坏也落在 `FLT_MAX` 和 +∞ 之间，结果是实现定义的选择。只有在没有无穷的浮点格式上，`DBL_MAX` 转 `float` 才是未定义行为。

本机运行时，UBSan 只对 `int` 那一行报告 `1.79769e+308 is outside the range of representable values of type 'int'`。用 `DBL_MAX` 初始化一个 `constexpr float`，Clang 接受，与上面的分析一致。

### F.3.7 浮点转整数时截断后的值不可表示 {#conv.fpint.float.not.represented}

`[ub:conv.fpint.float.not.represented]` · 正文 [[conv.fpint#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <limits>
#include <cstdio>

int main() {
  volatile double d = (double)std::numeric_limits<int>::max() + 1;
  int x1 = d;   // UB：2147483648 不能表示为 int
  std::printf("%d\n", x1);
}
```

浮点转整数时先截去小数部分，截断后的值放不进目标类型就是未定义行为。这与整数之间的转换不同：整数转换从 C++20 起总是有定义的，结果按模运算得到。

本机运行时，UBSan 的 `float-cast-overflow` 检查报告 `2.14748e+09 is outside the range of representable values of type 'int'`。常量求值中用 `1e300` 初始化 `constexpr int` 被拒绝，诊断是 `value 1.0E+300 is outside the range of representable values of type 'const int'`。

### F.3.8 整数转浮点时值超出浮点类型的范围 {#conv.fpint.int.not.represented}

`[ub:conv.fpint.int.not.represented]` · 正文 [[conv.fpint#2]]

```cpp ub
int main() {
  unsigned long long x2 = -1;   // OK：无符号回绕，得到 2⁶⁴−1
  float f = x2;                 // 仅在 float 没有无穷、且最大值小于 2⁶⁴−1 的系统上是 UB
}
```

与 F.3.6 同理，只有浮点类型的范围有限（没有无穷）时才可能触发。IEEE 754 `float` 的最大有限值约为 3.4×10³⁸，远大于任何 64 位整数，所以在主流平台上不会遇到这一条。

### F.3.17 显式浮点转换时值超出目标范围 {#expr.static.cast.fp.outside.range}

`[ub:expr.static.cast.fp.outside.range]` · 正文 [[expr.static.cast#9]]

```cpp ub
#include <cfloat>

void f() {
  double d = FLT_MAX;
  d *= 16;
  float f = static_cast<float>(d);   // 仅在 float 不能表示 +inf 的系统上是 UB
}
```

这是 F.3.6 的 `static_cast` 版本，规则相同。在本机这样的 IEEE 754 平台上，`static_assert(static_cast<float>(FLT_MAX * 16.0) > FLT_MAX)` 在常量求值中通过，结果是 +∞。

## 解引用与指针算术

### F.3.20 对不指向对象或函数的指针做间接 {#expr.unary.dereference}

`[ub:expr.unary.dereference]` · 正文 [[expr.unary.op#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
int f(int* p) { return *p; }

int main() {
  return f(nullptr);   // UB：解引用空指针
}
```

`*p` 要求 `p` 指向一个对象或函数，唯一的例外是 `typeid` 的操作数（[[expr.typeid]]）。空指针和越过末尾的指针（past-the-end pointer，指向数组最后一个元素之后的位置）都不指向对象，所以 `*nullptr`、`*end` 都是未定义行为，即使结果马上被 `&` 取回地址。这一点与 C 不同：C 规定 `&*p` 中的 `*` 和 `&` 都不求值。

指向生命周期之外的对象的指针，可以做间接（正文的注 1），之后能做什么由 [[basic.life]] 规定，那是另一组规则。

本机运行时，UBSan 报告 `load of null pointer of type 'int'`，随后 ASan 报告 `SEGV on unknown address 0x000000000000`。常量求值中被拒绝，诊断是 `dereferencing a null pointer is not allowed in a constant expression`。

### F.3.4 求值一个不再能指代对象的引用 {#expr.type.reference.lifetime}

`[ub:expr.type.reference.lifetime]` · 正文 [[expr.type#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int main() {
  int* ip = new int(5);
  int& i = *ip;
  delete ip;
  std::printf("%d\n", i);   // UB：i 指代的对象已被释放
}
```

一个引用类型的表达式指代某个对象 X。只有当一个指向 X 的指针在这里仍然有效时，表达式才指代 X；否则求值它就是未定义行为。`delete ip` 之后，指向那块存储的指针都成了无效指针值（[[basic.compound]]），所以 `i` 也不能再使用。附录的例子只写了一句 `i;`，说明不需要读取值，单是求值这个引用就已经是未定义行为。

本机运行时，ASan 报告 `heap-use-after-free`。

### F.3.30 创建越界指针 {#expr.add.out.of.bounds}

`[ub:expr.add.out.of.bounds]` · 正文 [[expr.add#4.3]]

```cpp ub
static const int arrs[10]{};
static const int arrs2[10][10]{};

void f() {
  const int* end = arrs + 10;          // OK：越过末尾的指针
  const int* y = arrs + 11;            // UB：创建越界指针
  const int (*z)[10] = arrs2 + 11;     // UB：同上，元素类型是 int[10]
}
```

指针加减整数的结果只能落在同一数组的下标 0 到 n 之间，n 就是越过末尾的位置。只要算出越界的指针就是未定义行为，不需要解引用。不是数组元素的对象，在这里被当作只有一个元素的数组。

本机运行时没有任何报告。UBSan 的 `pointer-overflow` 检查只检查地址回绕，ASan 只检查实际的内存访问；真正读取 `arrs[10]` 时，UBSan 的 `bounds` 检查和 ASan 才会报告。常量求值则在创建时就拒绝，诊断是 `cannot refer to element 11 of array of 10 elements in a constant expression`。

### F.3.31 两个不属于同一数组的指针相减 {#expr.add.sub.diff.pointers}

`[ub:expr.add.sub.diff.pointers]` · 正文 [[expr.add#5.3]]

```cpp ub
#include <cstddef>

void f() {
  int x[2];
  int y[2];
  std::ptrdiff_t off = x - y;   // UB：x 与 y 是不同的数组
}
```

本机运行同样的代码并打印 `off`，没有任何报告，结果是 `-8`，也就是两个栈上数组之间隔了 8 个 `int`。常量求值中被拒绝，Clang 的诊断是 `arithmetic involving unrelated objects '&x[0]' and '&y[0]' has unspecified value`。

### F.3.32 指针类型与数组元素类型不相似 {#expr.add.not.similar}

`[ub:expr.add.not.similar]` · 正文 [[expr.add#6]]

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

指针算术以数组元素为单位移动。如果 `p` 的类型是 `T*`，而它实际指向的数组元素的类型与 `T` 不相似（[[g:similar-types]]，大致是去掉各层 cv 限定后类型相同），`p + 1` 就是未定义行为。最常见的形式是用基类指针遍历派生类数组。

正文的例子说明这条规则相当严格：`reinterpret_cast<unsigned int*>(arr + 1)` 读一次是合法的，因为有符号和无符号的对应类型可以互相访问；但再 `+ 1` 就是未定义行为，因为 `unsigned int` 与 `int` 不相似。

本机运行没有报告。`sizeof(S)` 是 4，`sizeof(T)` 是 16，`++s` 每次只前进 4 字节，后面的元素读到的是 `T` 内部的填充和 `double` 的字节。

## 别名与值表示

### F.3.2 通过不允许的类型访问对象（严格别名） {#expr.basic.lvalue.strict.aliasing.violation}

`[ub:expr.basic.lvalue.strict.aliasing.violation]` · 正文 [[basic.lval#11]]

```cpp run ub flags="-std=c++2c -O2" cc=clang_trunk
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

一个对象只能通过与它的动态类型相似的类型、对应的有符号或无符号类型，或者 `char`、`unsigned char`、`std::byte` 类型的 glvalue 来访问（[[g:type-accessible]]）。这条规则让编译器可以假定 `int*` 和 `float*` 不指向同一个对象。

本机用 `-O0` 编译时打印 `0`，`-O2` 时打印 `1`，`-O2 -fno-strict-aliasing` 时又打印 `0`：优化等级改变了程序的输出。ASan 和 UBSan 都不检查别名规则；Clang 另有一个 TypeSanitizer（`-fsanitize=type`，不在 `undefined` 组里），本机用它能发现这个问题，报告 `type-aliasing-violation`，并说明 `WRITE of size 4 … with type float accesses an existing object of type int`。

### F.3.3 用不是联合对象的实参调用联合的默认复制或移动 {#expr.basic.lvalue.union.initialization}

`[ub:expr.basic.lvalue.union.initialization]` · 正文 [[basic.lval#11]]

```cpp ub
union U { int x; };

void f() {
  alignas(U) char u[sizeof(U)] = {};
  U o = reinterpret_cast<U&>(u);   // UB：实参不指代一个 U 对象
}
```

联合的默认复制和移动操作直接复制对象表示（对象在内存中的全部字节），不需要知道哪个成员是活跃的。这样做的前提是实参真的是一个生命周期内的同类型联合对象。

本机运行没有任何报告。

### F.3.5 对值表示无效的对象做左值到右值转换 {#conv.lval.valid.representation}

`[ub:conv.lval.valid.representation]` · 正文 [[conv.lval#3]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstring>
#include <cstdio>

bool f() {
  bool b = true;
  char c = 42;
  std::memcpy(&b, &c, 1);
  return b;   // UB：42 不是 bool 的有效值表示
}

int main() {
  bool b = f();
  std::printf("%d %d\n", (int)b, b ? 1 : 0);
}
```

左值到右值转换就是读取对象的值。读取时，对象的位模式必须是该类型的一个有效的值表示（[[g:value-representation]]）。`bool` 是最典型的例子：主流 ABI 中只有 0 和 1 是有效的表示。

本机运行时，UBSan 的 `bool` 检查报告 `load of value 42, which is not a valid value for type 'bool'`。常量求值中 `std::bit_cast<bool>((unsigned char)42)` 被拒绝，诊断是 `value 42 cannot be represented in type 'bool'`。

### F.3.34 赋值的源与目标存储部分重叠 {#expr.assign.overlap}

`[ub:expr.assign.overlap]` · 正文 [[expr.assign#7]]

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

int main() {
  int x = 0x01020304;
  char* c = reinterpret_cast<char*>(&x);
  x = *c;   // UB：源（x 的第一个字节）与目标 x 部分重叠
  std::printf("%d\n", x);
}
```

如果要存进对象的值是从另一个与目标存储有重叠的对象中读出来的，重叠必须完全一致，并且两者类型相同，也就是自赋值 `x = x`；否则是未定义行为。这让编译器可以不考虑重叠地实现赋值，类似 `memcpy` 与 `memmove` 的区别。

本机运行没有报告，打印 `4`（小端序下 `x` 的第一个字节是 `0x04`）。

## 类型转换

### F.3.15 引用的 static_cast 下行转换，而对象实际不是目标类型 {#expr.static.cast.base.class}

`[ub:expr.static.cast.base.class]` · 正文 [[expr.static.cast#2]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
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

`static_cast<D&>(b)` 不做运行时检查，它假定 `b` 确实是某个 D 对象的基类子对象，然后按编译期已知的偏移调整地址。假定不成立就是未定义行为。需要运行时检查时应该用 `dynamic_cast`。

加上 `-fsanitize=vptr` 后，UBSan 报告 `downcast of address … which does not point to an object of type 'D2'`。只用 `address,undefined` 时，报告来自随后的越界读取（ASan 的 `stack-buffer-overflow`）。`vptr` 检查只适用于多态类型；附录原例中的 B 没有虚函数，那样就没有任何工具能在运行时发现问题。常量求值中被拒绝，诊断是 `cannot cast object of dynamic type 'D1' to type 'D2'`。

### F.3.18 指针的 static_cast 下行转换，而该位置没有目标类型的对象 {#expr.static.cast.downcast.wrong.derived.type}

`[ub:expr.static.cast.downcast.wrong.derived.type]` · 正文 [[expr.static.cast#10]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined,vptr" cc=clang_trunk
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

这是 F.3.15 的指针版本。本机运行时，`vptr` 检查先报告 `downcast of address … which does not point to an object of type 'D2'`，再报告 `member access within address … which does not point to an object of type 'D2'`。不加 `vptr` 时，ASan 在 `p->x` 处报告 `heap-buffer-overflow`。

### F.3.16 转换到没有固定底层类型的枚举，而值超出范围 {#expr.static.cast.enum.outside.range}

`[ub:expr.static.cast.enum.outside.range]` · 正文 [[expr.static.cast#8]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

enum A { e1 = 1, e2 };   // 值的范围是 [0, 3]

int main(int argc, char**) {
  A ok = static_cast<A>(3);          // OK：在范围内，虽然不等于任何枚举量
  A a  = static_cast<A>(3 + argc);   // UB：4 超出范围
  std::printf("%d %d\n", (int)ok, (int)a);
}
```

没有固定底层类型的枚举，它的值的范围（[[dcl.enum]]）是能容纳所有枚举量的最小位域的范围，而不是枚举量本身的集合。`enum A { e1 = 1, e2 }` 的枚举量是 1 和 2，需要 2 位，所以范围是 0 到 3：`static_cast<A>(3)` 合法，`static_cast<A>(4)` 才是未定义行为。有固定底层类型的枚举（`enum class`，或者 `enum E : int`）没有这个问题，底层类型的任何值都可以。

本机运行时，UBSan 的 `enum` 检查在读取处报告 `load of value 4, which is not a valid value for type 'A'`，它不检查转换本身。常量求值在转换处就拒绝，诊断是 `integer value 4 is outside the valid range of values [0, 3] for the enumeration type 'A'`。

### F.3.9 把不指向有效对象的派生类指针转换为虚基类指针 {#conv.ptr.virtual.base}

`[ub:conv.ptr.virtual.base]` · 正文 [[conv.ptr#3]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct B { int b; };
struct D : virtual B {};

int main() {
  D ds[1];
  B* b = &ds[1];   // UB：&ds[1] 是越过末尾的指针，不指向对象
  return b != nullptr;
}
```

转换到虚基类需要读取对象里记录的虚基类偏移，所以指针必须指向一个生命周期内（或正在构造、析构中）的对象。越过末尾的指针不指向对象。

本机运行时，ASan 报告 `stack-buffer-overflow`：转换时读取了 `ds` 之后那块内存。这是少数能被 ASan 间接发现的纯转换类未定义行为。

### F.3.13 对不指向合适对象的非空指针做 dynamic_cast {#expr.dynamic.cast.pointer.lifetime}

`[ub:expr.dynamic.cast.pointer.lifetime]` · 正文 [[expr.dynamic.cast#7]]

```cpp ub
struct B { virtual ~B() = default; };

void f() {
  B bs[1];
  B* dp = dynamic_cast<B*>(bs + 1);   // UB：bs + 1 是越过末尾的指针
}
```

`dynamic_cast` 的运行时检查要读取对象的动态类型信息，所以操作数必须指向一个类型合适、在生命周期内（或正在构造、析构中）的对象。

本机运行没有报告，返回了非空指针。原因是转换到同一个类型时 `dynamic_cast` 不需要运行时检查，Clang 直接返回操作数，根本没有读内存。换成需要运行时检查的目标类型，就会去读越过末尾处的内存。

### F.3.14 对不指代合适对象的 glvalue 做 dynamic_cast {#expr.dynamic.cast.glvalue.lifetime}

`[ub:expr.dynamic.cast.glvalue.lifetime]` · 正文 [[expr.dynamic.cast#7]]

```cpp ub
struct B { virtual ~B() = default; };

void f() {
  B bs[1];
  B& dr = dynamic_cast<B&>(bs[1]);   // UB（bs[1] 本身已是 F.3.20 的 UB）
}
```

这是 F.3.13 的引用版本。

### F.3.10 基类成员指针转换为派生类成员指针，而派生类不可能含有该成员 {#conv.member.missing.member}

`[ub:conv.member.missing.member]` · 正文 [[conv.mem#2]]

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

成员指针的隐式转换方向是从基类到派生类，与对象指针相反：基类的成员一定也是派生类的成员。但如果原来的成员根本不在派生类里，比如它是另一个派生类的成员，先被 `static_cast` 到基类再转换回来，结果就是未定义行为。

本机运行没有报告。给 `D2` 加一个成员并通过 `pd2` 读取，读到的就是那个成员的值，因为成员指针在实现中只是一个偏移量。

### F.3.19 派生类成员指针 static_cast 到与原成员无关的基类 {#expr.static.cast.does.not.contain.original.member}

`[ub:expr.static.cast.does.not.contain.original.member]` · 正文 [[expr.static.cast#11]]

```cpp ub
struct A { char c; };
struct B { int i; };
struct D : A, B {};

int main() {
  char D::*p1 = &D::c;                        // c 是 A 的成员
  char B::*p2 = static_cast<char B::*>(p1);   // UB：B 不含 c，也与 A 无继承关系
}
```

从派生类到基类方向的成员指针转换需要显式 `static_cast`。结果合法的条件是：B 含有原来的成员，或者 B 是含有原来成员的那个类的基类或派生类。F.3.10 例子中合法的那一步就属于后一种。

## 函数调用与成员访问

### F.3.11 通过类型不兼容的表达式调用函数 {#expr.call.different.type}

`[ub:expr.call.different.type]` · 正文 [[expr.call#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

using f_int = int (*)(int);
int f1(float x) { std::printf("%f\n", x); return 10; }

int main() {
  return reinterpret_cast<f_int>(f1)(20);   // UB：表达式的函数类型与 f1 的定义不同
}
```

调用表达式的函数类型必须与被调函数定义的类型调用兼容（[[g:call-compatible]]）：类型相同，或者只差一个可以去掉 `noexcept` 的函数指针转换。用 `reinterpret_cast` 换了函数指针的类型再调用，就是未定义行为，因为不同类型的参数可能通过完全不同的寄存器传递。

本机编译时，Clang 给出 `-Wcast-function-type-mismatch` 警告。运行时，UBSan 的 `function` 检查报告 `call to function f1(float) through pointer to incorrect function type 'int (*)(int)'`。程序随后打印了一个与 20 无关的浮点数：`int` 实参放在整数寄存器里，`f1` 却从浮点寄存器取值。常量求值中根本不允许 `reinterpret_cast`，所以这类未定义行为不会出现在常量表达式中。

### F.3.12 E1.E2 中 E1 指代的对象与 E1 的类型不相似 {#expr.ref.member.not.similar}

`[ub:expr.ref.member.not.similar]` · 正文 [[expr.ref#10]]

```cpp ub
struct A { int i; };
struct B { int j; };

A a;
int x = reinterpret_cast<B&>(a).j;   // UB：a 是 A，不是 B
```

成员访问要求点号左边真的是那个类型的对象。正文的例子更能说明问题：对 `struct D : A, B {}` 的对象 `d`，`static_cast<B&>(d).j` 合法，因为它确实指代 `d` 的 B 子对象；`reinterpret_cast<B&>(d).j` 是未定义行为，因为它指代的是 `d` 的起始地址，那里是 A 子对象。

本机运行没有报告。A 和 B 的布局相同，读出的是 `a.i` 的值。

### F.3.26 .* 的对象表达式不含有该成员 {#expr.mptr.oper.not.contain.member}

`[ub:expr.mptr.oper.not.contain.member]` · 正文 [[expr.mptr.oper#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
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

`E1.*E2` 中，E1 的结果必须是一个类型与 E1 相似的对象，并且它的最派生对象含有 E2 所指的成员。

本机运行时，ASan 报告 `heap-buffer-overflow`，写到了只有 1 字节的 B 对象之后。常量求值在更早的 `static_cast` 处就停下了，诊断是 `cannot cast object of dynamic type 'B' to type 'D'`。

### F.3.27 .* 的第二个操作数是空成员指针 {#expr.mptr.oper.member.func.null}

`[ub:expr.mptr.oper.member.func.null]` · 正文 [[expr.mptr.oper#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
struct S { int f() { return 1; } };

int main() {
  S cs;
  int (S::*pm)() = nullptr;
  return (cs.*pm)();   // UB：第二个操作数是空成员指针值
}
```

附录条目的名字里有 func，但正文的规则对数据成员指针和成员函数指针一视同仁。

本机运行时，ASan 报告 `SEGV on unknown address 0x000000000000 (pc 0x000000000000 …)`，程序跳转到了地址 0。常量求值中被拒绝，诊断是 `subexpression not valid in a constant expression`。

## new 与 delete

### F.3.21 非分配形式的 placement new 得到空指针 {#expr.new.non.allocating.null}

`[ub:expr.new.non.allocating.null]` · 正文 [[expr.new#22]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

struct A { int x; };

int main() {
  char* p = nullptr;
  A* a = new (p) A;   // UB：非分配形式的 new 得到空指针
  return a != nullptr;
}
```

`new (p) T` 调用的 `operator new(std::size_t, void*)` 不分配内存，只把 `p` 原样返回（[[new.delete.placement]]）。这种非分配形式不能返回空指针，所以把空指针传给 placement new 就是未定义行为。

附录的第一个例子写了一个返回空指针的 `operator new(std::size_t, void*)`。这个函数在 `<new>` 中定义且不可替换，自己定义它本身就违反了库的规则，所以这里只用附录的第二个例子。

本机运行时，UBSan 报告 `constructor call on null pointer of type 'A'`。

### F.3.22 单对象 delete 的操作数不来自单对象 new {#expr.delete.mismatch}

`[ub:expr.delete.mismatch]` · 正文 [[expr.delete#2]]

```cpp ub
int main() {
  int* x = new int[10];
  delete x;   // UB：单对象 delete，操作数来自数组 new
}
```

单对象 `delete p` 中，`p` 只能是空指针、来自非数组 *new-expression* 的指针，或者指向这样创建的对象的某个基类子对象的指针。

!!! lawyer "附录与正文对不上"
    在当前草案中，正文 [[expr.delete#2]] 把 `[ub:expr.delete.mismatch]` 挂在单对象 delete 那一句上，把 `[ub:expr.delete.array.mismatch]` 挂在数组 delete 那一句上；而 Annex F 中这两个条目的摘要和例子恰好反了过来（F.3.22 写的是对单对象 new 的结果用数组 delete）。两种情况都是未定义行为，结论不受影响，但引用时以正文为准。本页按正文的挂法给例子。

本机编译时，Clang 给出警告 `'delete' applied to a pointer that was allocated with 'new[]'; did you mean 'delete[]'? [-Wmismatched-new-delete]`。运行时，设置 `ASAN_OPTIONS=alloc_dealloc_mismatch=1` 后，ASan 报告 `alloc-dealloc-mismatch (operator new [] vs operator delete)`。常量求值中被拒绝，诊断是 `non-array delete used to delete pointer to array object of type 'int[10]'`。

### F.3.23 数组 delete 的操作数不来自数组 new {#expr.delete.array.mismatch}

`[ub:expr.delete.array.mismatch]` · 正文 [[expr.delete#2]]

```cpp ub
int main() {
  int* x = new int;
  delete[] x;   // UB：数组 delete，操作数来自单对象 new
}
```

`delete[] p` 中，`p` 只能是空指针，或者来自一个数组 *new-expression*（分配函数不是非分配形式）的指针。注意必须是这个指针本身，指向其中某个元素或基类子对象的指针都不行。

本机编译时，Clang 给出警告 `'delete[]' applied to a pointer that was allocated with 'new'; did you mean 'delete'?`。运行时，设置 `alloc_dealloc_mismatch=1` 后，ASan 报告 `alloc-dealloc-mismatch (operator new vs operator delete [])`。常量求值中被拒绝，诊断是 `array delete used to delete pointer to non-array object of type 'int'`。

### F.3.24 通过没有虚析构函数的基类指针 delete 派生类对象 {#expr.delete.dynamic.type.differ}

`[ub:expr.delete.dynamic.type.differ]` · 正文 [[expr.delete#3]]

```cpp ub
struct B { int a; };
struct D : B { int b; };

void f() {
  B* b = new D;
  delete b;   // UB：B 没有虚析构函数
}
```

单对象 delete 中，如果被删除对象的静态类型与动态类型不相似，并且选中的释放函数不是销毁型 `operator delete`（destroying operator delete，它自己负责调用析构函数），那么静态类型必须是动态类型的基类，而且必须有虚析构函数，否则是未定义行为。

本机运行单继承的版本没有报告：`B` 恰好位于 `D` 的起始地址，释放的指针是对的，只是 `~D` 没有被调用。换成多继承（`struct D : A0, B`，删除 `B*`）后，ASan 报告 `attempting free on address which was not malloc()-ed`：传给 `operator delete` 的是 B 子对象的地址，不是分配的起始地址。常量求值中被拒绝，诊断是 `delete of object with dynamic type 'D' through pointer to base class type 'B' with non-virtual destructor`。

### F.3.25 数组 delete 时动态类型与静态类型不相似 {#expr.delete.dynamic.array.dynamic.type.differ}

`[ub:expr.delete.dynamic.array.dynamic.type.differ]` · 正文 [[expr.delete#3]]

```cpp ub
struct B { virtual ~B() = default; int x; };
struct D : B { int y; };

void f(int n) {
  D* dp = new D[n];
  delete[] dp;   // OK
  B* bp = new D[n];
  delete[] bp;   // UB：即使 B 有虚析构函数
}
```

数组没有多态删除：即使 B 有虚析构函数，用 `delete[]` 删除一个指向 `D` 数组的 `B*` 也是未定义行为。逐个析构元素需要知道元素的大小，而实现只能从静态类型得到它。

本机运行这类代码没有报告。在这个例子里，`sizeof(D)` 和 `sizeof(B)` 都是 16（Itanium ABI 让 `y` 占用了 B 尾部的填充），步长恰好没错。把派生类换成更大的类型（本机 `sizeof` 为 32）后运行，同样没有任何报告。没出问题不能说明代码是对的。
