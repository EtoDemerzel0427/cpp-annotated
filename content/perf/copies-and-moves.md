---
title: 避免不必要的拷贝
summary: 用一个会计数的类型和计时找出程序里可以省掉的复制和移动：形参怎么传，返回值什么时候被省略，范围 for、结构化绑定、const、emplace、map 插入和 initializer_list 各自在哪里多做了一次复制，以及小对象为什么按值传更快。
status: draft
order: 70
group: 代码
since: c++11
papers: P1825R0, P2266R3
related: class.copy.elision, expr.prim.id.unqual, class.temporary, dcl.init.list, stmt.ranged, dcl.struct.bind, map.modifiers, intro.abstract, topics/special-members-and-elision, topics/value-categories, topics/dangling-references, perf/measuring, perf/reading-assembly, perf/allocation
tags: 性能, 复制, 移动, 复制消除, NRVO, ABI
updated: 2026-10-19
---

!!! tldr
    - 先数再改：给类型加上复制、移动计数器，或者替换 `operator new` 数分配次数。次数不受机器负载影响，比计时可靠。
    - 只读的大对象按 `const&` 传；要存下来的参数，在构造函数里按值接收再移动，在 setter 里提供 `const&` 和 `&&` 两个重载，才能复用成员已有的容量。
    - `return local;` 通常什么也不复制（NRVO）；两个分支返回不同的局部变量、返回形参、`return std::move(local);`、`return b ? x : y;` 都会多出一次移动或复制。
    - `for (auto s : v)`、`auto [k, v] = *it`、对 `const` 对象调用 `std::move`、带 `const` 成员的类、`std::initializer_list`，这些写法看起来无害，实际都会复制。
    - 小的平凡可复制类型（两三个整数、`string_view`、`span`）按值传会放进寄存器，比 `const&` 少一次内存往返，也不会和其他指针别名。

本页的测量都在同一台机器上完成：Apple M2 Pro，macOS，Homebrew Clang 23.1.3 + libc++，arm64，`clang++ -std=c++2c -O2`。写作时机器负载很高，绝对时间偏慢、偏散，所以下面主要报告三类证据：复制、移动和分配的次数，同一进程里交替测得的时间比值（三次运行的范围），以及汇编。换硬件、换编译器或标准库，数字会变。计时框架是 [[perf/measuring#harness|bench.hpp]]，`bench::compare(a, b)` 按 ABBA 顺序交替测两个版本并输出比值。

复制消除、可隐式移动这些规则本身在 [[topics/special-members-and-elision]] 和 [[topics/value-categories]] 里讲过，这里只关心它们在实际代码里省下了什么、漏掉了什么。

## 先数一数

计时会受噪声影响，次数不会。给一个类型的四个特殊成员函数各加一个计数器，就能精确知道一行代码做了几次复制、几次移动：

```cpp run title="counted.cpp" ok
#include <cstdio>
#include <map>
#include <utility>
#include <vector>

struct Counted {
  static inline int copies = 0, moves = 0;
  int v = 0;
  Counted() = default;
  Counted(int x) : v(x) {}
  Counted(const Counted& o) : v(o.v) { ++copies; }
  Counted(Counted&& o) noexcept : v(o.v) { ++moves; }
  Counted& operator=(const Counted& o) { v = o.v; ++copies; return *this; }
  Counted& operator=(Counted&& o) noexcept { v = o.v; ++moves; return *this; }
};

#define SHOW(label, ...) do {                                   \
    Counted::copies = Counted::moves = 0;                       \
    { __VA_ARGS__; }                                            \
    std::printf("%-30s copy %d  move %d\n", label,              \
                Counted::copies, Counted::moves);               \
  } while (0)

Counted one()        { Counted c(1); return c; }
Counted two(bool b)  { Counted a(1), c(2); if (b) return a; return c; }
Counted param(Counted p) { return p; }
Counted cond(bool b) { Counted a(1), c(2); return b ? a : c; }

int main() {
  SHOW("return c;", Counted r = one(); (void)r);
  SHOW("if (b) return a; return c;", Counted r = two(true); (void)r);
  SHOW("return p; (parameter)", Counted r = param(Counted(1)); (void)r);
  SHOW("return b ? a : c;", Counted r = cond(true); (void)r);

  std::vector<Counted> v;
  v.reserve(8);
  SHOW("push_back(Counted(1))", v.push_back(Counted(1)));
  SHOW("emplace_back(1)", v.emplace_back(1));
  SHOW("vector<Counted> w{1, 2, 3}", std::vector<Counted> w{1, 2, 3});

  std::vector<Counted> vs(4);
  SHOW("for (auto x : vs)", for (auto x : vs) (void)x);
  SHOW("for (const auto& x : vs)", for (const auto& x : vs) (void)x);

  std::map<int, Counted> m{{1, Counted(1)}};
  SHOW("auto [k, c] = *m.begin()", auto [k, c] = *m.begin(); (void)k; (void)c);
  SHOW("auto& [k, c] = *m.begin()", auto& [k, c] = *m.begin(); (void)k; (void)c);
}
```

本机用 `-O2` 编译运行，输出如下（`-O0` 相同，这些次数由语言规则决定，不是优化的结果）：

```text
return c;                      copy 0  move 0
if (b) return a; return c;     copy 0  move 1
return p; (parameter)          copy 0  move 1
return b ? a : c;              copy 1  move 0
push_back(Counted(1))          copy 0  move 1
emplace_back(1)                copy 0  move 0
vector<Counted> w{1, 2, 3}     copy 3  move 0
for (auto x : vs)              copy 4  move 0
for (const auto& x : vs)       copy 0  move 0
auto [k, c] = *m.begin()       copy 1  move 0
auto& [k, c] = *m.begin()      copy 0  move 0
```

后面各节逐行解释这张表。对于 `std::string`、`std::vector` 这类自己管理堆内存的类型，另一个可靠的计数是分配次数：替换全局 `operator new`，每调用一次加一。做法见 [[perf/allocation]]。

计数器有一个副作用要注意：它让复制和移动构造函数不再平凡，类型的传参方式也随之改变（见后文的 ABI 一节）。它适合回答发生了几次，不适合拿来计时。

## 传参：`const&`、`&&` 还是按值

函数只读参数时，答案很简单：大对象按 `const&`，小的平凡可复制对象按值（下一节）。难的是函数要把参数存下来的情形，比如 setter 和构造函数。常见的三种写法：

<div class="compare" markdown="1">

```cpp
struct ByRef {
  std::string m;
  void set(const std::string& s) {
    m = s;                   // 复制
  }
};
struct BySink {
  std::string m;
  void set(std::string s) {  // 按值接收
    m = std::move(s);        // 再移动
  }
};
```

```cpp
struct ByBoth {
  std::string m;
  void set(const std::string& s) {
    m = s;
  }
  void set(std::string&& s) {
    m = std::move(s);
  }
};
```

</div>

按值接收再移动的写法常被称为 sink 参数。实参是左值时它复制一次、移动一次；是右值时移动两次（或者实参是 prvalue 时，形参直接就是它的结果对象，只移动一次）。`const&` 版本对右值也要复制一次。只看次数，按值接收最多比两个重载多一次移动。

但 setter 里还有一个次数看不出来的因素：`m = s` 是复制赋值，`m` 已有的缓冲区够大时，libc++ 直接把字符复制进去，不分配。按值接收的版本先复制构造形参，这一步必然分配，然后移动赋值，丢掉 `m` 原来的缓冲区。在 setter 被反复调用的循环里，本机替换 `operator new` 数出的结果是：

| 写法 | 左值实参，分配次数/次 | 右值实参（调用方先构造一个临时 `std::string`），分配次数/次 |
|---|---|---|
| `const&` | 0 | 1（临时对象本身） |
| 按值接收 | 1 | 1 |
| `const&` + `&&` | 0 | 1 |

计时结果（`bench::compare`，三次运行的比值范围，比值大于 1 表示 B 更慢）：

| 场景 | A | B | B/A |
|---|---|---|---|
| `string(10)`，左值 | `const&` | 按值 | 1.25 |
| `string(100)`，左值 | `const&`（约 4 ns） | 按值 | 6.6 – 18 |
| `string(100)`，右值 | `const&` | 按值 | 0.91 |
| `string(100)`，右值 | `const&` | `const&` + `&&` | 0.89 |
| `vector<int>(1000)`，左值 | `const&` | 按值 | 1.3 – 1.7 |
| `vector<int>(1000)`，右值 | `const&` | 按值 | 0.51 – 0.74 |
| `vector<int>(1000)`，右值 | `const&` | `const&` + `&&` | 0.56 – 0.85 |

右值实参的时间里包含调用方构造临时对象的那次分配和复制，所以各列都不小。从表里可以读出三件事：

1. 短字符串（libc++ 中不超过 22 个字符，存在对象内部，见 [[perf/allocation]]）怎么传都只差几分之一纳秒。
2. 左值实参传给 setter，按值接收慢得多，因为它放弃了 `m` 已有的容量。这一列的波动最大，它测的主要是分配器。
3. 右值实参时，按值接收和 `&&` 重载一样快，都比 `const&` 少一次元素复制。

构造函数没有已有容量可复用，按值接收再移动只比两个重载多一次移动，换来一个函数代替 2^n 个重载，通常是合理的取舍。setter 和 `assign` 一类会反复调用的函数，`const&` + `&&` 两个重载更好。转发引用（`template<class T> void set(T&& s)`）也能做到同样的次数，代价是接口变成模板，错误信息难读。

## 小对象按值传

```cpp godbolt title="abi.cpp" flags="-std=c++2c -O2" ok
struct P { int x, y; };
int use_val(P p);
int use_ref(const P& p);
int call_val(int a, int b) { return use_val({a, b}); }
int call_ref(int a, int b) { return use_ref({a, b}); }
```

本机 `-O2` 生成的 arm64 汇编：

<div class="compare" markdown="1">

```asm
call_val:
  mov  w8, w0
  orr  x0, x8, x1, lsl #32
  b    use_val      ; 尾调用
```

```asm
call_ref:
  sub  sp, sp, #32
  stp  x29, x30, [sp, #16]
  add  x29, sp, #16
  stp  w0, w1, [sp, #8] ; 写到栈上
  add  x0, sp, #8       ; 传地址
  bl   use_ref
  ldp  x29, x30, [sp, #16]
  add  sp, sp, #32
  ret
```

</div>

按值传时，`P` 的两个 `int` 拼成一个 64 位寄存器 `x0`，调用方连栈帧都不用建。按 `const&` 传时，引用要求对象有地址，调用方只能先把它写到栈上再传指针，被调函数还要从内存读回来。

标准允许这样做的依据是 [[class.temporary#3]]：如果一个类类型的所有合格的复制、移动构造函数都是平凡的，析构函数平凡或被删除，实现可以为传参和返回值额外创建临时对象。这句话的注说明了目的，就是为了允许用寄存器传递。反过来，不满足这个条件的类型（比如 `std::unique_ptr`、`std::string`，或者上一节带计数器的 `Counted`），在 Itanium C++ ABI（Linux、macOS 都用它）下即使只有 8 字节，按值传时也是调用方在栈上建好对象再传地址。

`const&` 还有一个代价：引用可能和其他指针指向同一块内存。

```cpp godbolt title="alias.cpp" flags="-std=c++2c -O2" ok
void scale_ref(double* v, int n, const double& k) {
  for (int i = 0; i < n; ++i) v[i] *= k;
}
void scale_val(double* v, int n, double k) {
  for (int i = 0; i < n; ++i) v[i] *= k;
}
```

`scale_ref(v, n, v[0])` 是合法调用，此时第一次写 `v[0]` 就改变了 `k`。所以 Clang 为 `scale_ref` 生成了一段运行时检查（`cmp x2, x9` / `ccmp`，比较 `&k` 是否落在 `v[0..n)` 里）：不重叠时走向量化的循环，重叠时走一个每次迭代都重新 `ldr d0, [x2]` 读 `k` 的标量循环。`scale_val` 里 `k` 在寄存器 `d0` 里，没有检查，只有向量化循环。两个函数在 `k` 别名 `v` 的元素时结果也不同，这不只是性能问题。

所以 `int`、`double`、指针、迭代器、`std::string_view`、`std::span`、两三个标量组成的结构，都应该按值传。界限大致是两个寄存器（16 字节）：在 AAPCS64 和 x86-64 System V 下，不超过 16 字节的平凡可复制聚合按值传时放进寄存器；更大的按值传反而要在调用方复制一份到栈上，这时 `const&` 更便宜。

## 返回值

### 什么时候省略

上面的计数表里，`return c;` 一次复制、移动也没有。这是 NRVO（具名返回值优化）：[[class.copy.elision#1.1]] 允许在返回一个局部自动对象时，直接把它构造在调用方的结果对象里。汇编里看得很清楚：

```cpp godbolt title="nrvo.cpp" flags="-std=c++2c -O2" ok
#include <string>
#include <utility>
void fill(std::string&);
std::string nrvo()  { std::string s; fill(s); return s; }
std::string moved() { std::string s; fill(s); return std::move(s); }
```

<div class="compare" markdown="1">

```asm
nrvo:
  ...
  mov  x19, x8       ; x8：结果对象地址
  stp  xzr, xzr, [x8]
  str  xzr, [x8, #16] ; 直接在那里构造 s
  mov  x0, x8
  bl   fill
  ...
  ret
```

```asm
moved:
  sub  sp, sp, #64
  ...
  mov  x19, x8
  stp  xzr, xzr, [sp, #8] ; s 在栈上
  str  xzr, [sp, #24]
  add  x0, sp, #8
  bl   fill
  ldur q0, [sp, #8]   ; 移动：搬 24 字节
  str  q0, [x19]
  ldr  x8, [sp, #24]
  str  x8, [x19, #16]
  ...
```

</div>

`std::move(s)` 是一个 xvalue 表达式，不再是局部变量的名字，[[class.copy.elision#1.1]] 的条件不满足，NRVO 就做不成了，只能移动构造。Clang 在 `-Wall` 下对此报 `-Wpessimizing-move`。对 `std::string` 来说这次移动只是搬 24 字节；对移动开销大的类型代价更高。

### 什么时候不省略

计数表里多出一次移动或复制的四种写法：

| 写法 | 本机计数 | 原因 |
|---|---|---|
| `if (b) return a; return c;` | 移动 1 | 两个变量不能同时构造在结果对象的位置上，Clang 放弃 NRVO |
| `return p;`（`p` 是形参） | 移动 1 | 形参由调用方构造，[[class.copy.elision#1.1]] 明确排除了它 |
| `return std::move(local);` | 移动 1 | 操作数不再是名字 |
| `return b ? a : c;` | 复制 1 | 条件表达式是左值，不是可隐式移动的名字 |

前三种虽然不能省略，但仍是移动而不是复制。这是因为 `return` 的操作数如果是局部变量或形参的名字，它是**可隐式移动**（[[g:move-eligible|move-eligible]]）的，按 xvalue 处理（[[expr.prim.id.unqual#15]]）。这条规则经过几次放宽：C++20 的 [[P1825R0]] 把右值引用类型的局部变量也纳入其中，C++23 的 [[P2266R3]] 改成现在这种直接把表达式当作 xvalue 的形式。细节见 [[topics/special-members-and-elision]]。

因此对形参写 `return std::move(p);` 是多余的，Clang 用 `-Wredundant-move` 提示（本机 `-Wall` 已包含）。第四种必须改写成 `if (b) return a; return c;`，用一次移动换掉一次复制。

两个分支返回不同变量的那次移动，对 `std::string` 很便宜。对平凡可复制的大对象，移动就是复制：

```cpp godbolt title="two-returns.cpp" flags="-std=c++2c -O2" ok
#include <array>
using Arr = std::array<double, 512>;   // 4 KiB
void fill(Arr&);
Arr two(bool b) {
  Arr a, c; fill(a); fill(c);
  if (b) return a;
  return c;
}
```

本机 `-O2` 下 `two` 的末尾是 `csel x1, x21, x22, ne` 选出源地址，然后 `bl _memcpy` 复制 4096 字节。和做同样两次 `fill`、但总是 `return a;` 的版本相比，`two` 慢 1.4 – 1.8 倍（同一进程交替测量，三次运行）。

有一个反例值得一看：对这个 `Arr`，单变量的 `return std::move(a);` 在 `-O2` 下和 `return a;` 生成完全相同的代码，都只是 `mov x0, x8` 后跳到 `fill`。复制平凡可复制的对象没有可观察的副作用，按 as-if 规则（[[intro.abstract#1]]），优化器可以让 `fill` 直接写进结果对象，把那次 `memcpy` 删掉。这不是复制消除，而是普通优化，所以只对平凡类型、只在开优化时成立。

### 大的返回值走 sret

```cpp godbolt title="sret.cpp" flags="-std=c++2c -O2" ok
struct P   { int x, y; };
struct Big { double a[8]; };
P   make_p(int v)      { return {v, v + 1}; }
Big make_big(double d) {
  Big b;
  for (auto& e : b.a) e = d;
  return b;
}
```

`make_p` 把两个 `int` 拼进 `x0` 返回。`make_big` 返回 64 字节，放不进寄存器，调用方事先分配好结果对象，把地址作为隐藏参数传进来，这叫 **sret**（structure return）。arm64 用专门的 `x8` 寄存器传这个地址，x86-64 System V 用第一个参数寄存器 `rdi`，并且在 `rax` 里把它返回：

<div class="compare" markdown="1">

```asm
; arm64
make_big:
  dup.2d v0, v0[0]
  stp  q0, q0, [x8]
  stp  q0, q0, [x8, #32]
  ret
```

```asm
; x86-64 (--target=x86_64-linux-gnu)
make_big:
  mov    rax, rdi
  movlhps xmm0, xmm0
  movups [rdi + 16], xmm0
  movups [rdi], xmm0
  movups [rdi + 48], xmm0
  movups [rdi + 32], xmm0
  ret
```

</div>

sret 正是 NRVO 和 prvalue 直接初始化的物质基础：结果对象的地址在函数开始前就已知，函数可以从第一条指令起就在那里构造。所以按值返回大对象本身不贵，贵的只是让 NRVO 失效的写法。

## 循环和结构化绑定里的复制

### 范围 `for`

[[stmt.ranged#1]] 把 `for (decl : range)` 展开成一个循环，每次迭代执行 `decl = *begin;`。`decl` 写成 `auto s` 时，这是一次复制初始化，每个元素复制一次；写成 `const auto& s` 时只是绑定引用。

| 1000 个元素 | A：`const auto&` | B：`auto` | B/A |
|---|---|---|---|
| `std::string(10)`（SSO） | 约 0.47 µs | | 1.4 – 3.0 |
| `std::string(40)`（每个都分配） | 约 0.47 µs | | 160 – 220 |

Clang 的 `-Wrange-loop-construct`（`-Wall` 包含）只在 `for (const auto s : v)` 这种写法上报警，普通的 `for (auto s : v)` 不报，因为它可能是有意要一份副本。clang-tidy 的 `performance-for-range-copy` 检查覆盖这种情况。

同一个警告还能抓住另一种隐蔽的复制：

```cpp
void walk(const std::map<std::string, int>& m) {
  for (const std::pair<std::string, int>& e : m)  // 每次复制一个 pair
    (void)e;
}
```

`map` 的元素类型是 `pair<const std::string, int>`，和声明的类型差一个 `const`。引用不能直接绑定，于是每次迭代都构造一个临时的 `pair<std::string, int>`，再让引用绑定到它。本机 Clang 23 对它报 `-Wrange-loop-construct`。用 `const auto&` 或 `const value_type&` 就不会写错。

### 结构化绑定

`auto [k, v] = *it;` 看起来只是给两个成员起名字。但 [[dcl.struct.bind#1]] 规定，结构化绑定声明先引入一个无名变量 `e`，用初始化器初始化它，`k`、`v` 再指向 `e` 的成员。声明里写的 `auto` 修饰的是 `e`，所以 `auto [k, v] = *it` 复制了整个元素，`auto& [k, v]` 或 `const auto& [k, v]` 才不复制。

| 遍历 1000 个元素的 `map<string, string>`（键 33 字节，值 40 字节） | B/A |
|---|---|
| A：`for (const auto& [k, v] : m)`，B：`for (auto [k, v] : m)` | 75 – 108 |

## `const` 让移动变成复制

`std::move` 只是一个到右值引用的强制转换（[[topics/value-categories]]）。作用在 `const T` 上，得到的是 `const T&&`，`T(T&&)` 绑定不上，重载决议选中 `T(const T&)`：

```cpp run title="const-move.cpp" ok
#include <cstdio>
#include <utility>

struct Counted {
  static inline int copies = 0, moves = 0;
  Counted() = default;
  Counted(const Counted&) { ++copies; }
  Counted(Counted&&) noexcept { ++moves; }
};

struct Rec {
  const Counted id;   // const 成员
  Counted data;
};

int main() {
  const Counted c;
  Counted x = std::move(c);        // 复制
  std::printf("copy %d move %d\n", Counted::copies, Counted::moves);

  Counted::copies = Counted::moves = 0;
  Rec r{};
  Rec r2 = std::move(r);           // id 复制，data 移动
  std::printf("copy %d move %d\n", Counted::copies, Counted::moves);
}
```

输出 `copy 1 move 0` 和 `copy 1 move 1`。没有警告，也不报错，移动悄悄退化成复制。第二种更容易被忽视：类的隐式移动构造函数逐个移动成员，`const` 成员只能被复制。成员写成 `const` 还会删除隐式的复制赋值和移动赋值，类型放进 `std::vector` 后不能再被赋值。想表达不可修改，通常把成员设为 `private` 并只提供读取函数，比 `const` 成员代价小。

## 往容器里放元素

### `push_back` 和 `emplace_back`

计数表里，`push_back(Counted(1))` 先构造一个临时对象，再把它移动进容器；`emplace_back(1)` 把参数转发给构造函数，直接在容器的内存里构造，零次移动。

区别只在于实参是不是一个已经构造好的对象。`emplace_back(Counted(1))`、`emplace_back(std::move(x))` 和对应的 `push_back` 完全相同。`push_back("text")` 向 `vector<std::string>` 里添加时会先构造一个临时 `std::string` 再移动，`emplace_back("text")` 不会；短字符串时这次移动只是复制 24 字节。

`emplace_back` 调用的是显式构造，它也会接受 `push_back` 拒绝的转换，比如 `vector<std::unique_ptr<T>>::emplace_back(raw_ptr)`，以及 `vector<std::vector<int>>::emplace_back(100)` 建出一个 100 个元素的 vector。只为省一次移动而处处换成 `emplace_back`，得到的好处远小于这个风险。

### `std::initializer_list` 只能复制

计数表里，`std::vector<Counted> w{1, 2, 3}` 复制了 3 次。花括号里的元素先被复制初始化到一个类型为 `const E[N]` 的**后备数组**（backing array）里（[[dcl.init.list#5]]），`vector` 的构造函数再从这个数组复制。数组元素是 `const`，没法移动。

!!! std
    An object of type `std::initializer_list<E>` is constructed from an initializer list as if the implementation generated and materialized a prvalue of type "array of N `const E`".

    `initializer_list` 背后是一个元素为 `const E` 的数组（[[dcl.init.list#5]]）。

两个直接后果：只能移动的类型根本不能用花括号初始化容器，`std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};` 在本机 Clang 23 / libc++ 下报错（`no matching function for call to '__construct_at'`，最终要调用被删除的复制构造函数）；元素复制代价大时，改用 `reserve` 后逐个 `emplace_back`，本机计数为 0 次复制、0 次移动。后备数组的生存期问题见 [[topics/dangling-references]]。

### `map` 的插入

键已经存在时，不同的插入函数做了多少无用功？用 `map<std::string, std::string>`、33 字节的键和 64 字节的值，替换 `operator new` 计数（本机 libc++）：

| 键已存在时的调用 | 分配次数 |
|---|---|
| `m.emplace("…33 字节的字面量…", val)` | 3 |
| `m.insert({"…", val})` | 2 |
| `m.try_emplace("…", val)` | 1 |
| `m.emplace(k, val)`，`k` 是 `std::string` | 0 |
| `m.try_emplace(k, val)` | 0 |

`emplace` 的规定是用参数构造一个 `value_type`，只在键不存在时插入。键要先构造出来才能比较，libc++ 在一般情况下先分配节点、在节点里构造键和值，查到重复后再全部销毁，这就是 3 次分配（节点、键、值）的来源。参数恰好是一个 `key_type` 时，libc++ 会先用它查找，所以第四行是 0；这是 libc++ 的实现细节，不要依赖。`insert({…})` 先构造了一个临时 `pair`（键和值各分配一次）。

`try_emplace` 的规定写明了：键已存在时没有效果（[[map.modifiers#4]]），值的构造参数不会被使用，也不会被移走。剩下的 1 次分配来自它的形参类型是 `const key_type&`，字面量要先转换成一个临时 `std::string`；传进去的已经是 `std::string` 时为 0。需要插入或覆盖时用 `insert_or_assign`：键存在时赋值，不存在时直接用参数构造。`m[k] = v` 在键不存在时先默认构造一个值再赋值，并且要求值类型可默认构造。

## 用视图代替复制

```cpp
std::size_t len_ref(const std::string& s);
std::size_t len_sv(std::string_view s);

void caller() {
  len_ref("0123456789012345678901234567890123456789");  // 临时 string
  len_sv("0123456789012345678901234567890123456789");   // 指针和长度
}
```

40 个字符超过了 libc++ 的 SSO 容量，`len_ref` 的调用方必须分配一个临时 `std::string`，复制字符，调用完再释放。`len_sv` 的参数在 `x0`、`x1` 两个寄存器里，被调函数就是一条 `mov x0, x1`。本机交替测量，`len_ref` 每次 70 – 110 ns，`len_sv` 不到 1 ns。

`std::span<const T>` 对连续数组起同样的作用：一个函数既能接受 `std::vector<T>`，也能接受 `std::array` 和 C 数组，不复制，也不强迫调用方先构造某种容器。

视图不拥有数据，代价是要自己保证所指对象活得比视图久。把 `string_view` 存进成员、从函数返回指向临时 `std::string` 的 `string_view`，都是常见的悬垂来源，见 [[topics/dangling-references]]。经验做法是：视图适合做形参，存下来时转换成拥有数据的类型。

## 检查清单

| 写法 | 多出的工作 | 改法 |
|---|---|---|
| 只读的大对象按值传 | 1 次复制 | `const&` |
| 小的平凡可复制类型按 `const&` 传 | 一次内存往返，可能别名 | 按值 |
| setter 按值接收再移动，传左值 | 1 次分配（放弃已有容量） | `const&` + `&&` 重载 |
| `return std::move(local);` | 1 次移动，失去 NRVO | `return local;` |
| `return b ? x : y;` | 1 次复制 | 两个 `return` 语句 |
| 两个分支返回不同的局部变量 | 1 次移动（平凡类型是 `memcpy`） | 只用一个结果变量 |
| `for (auto s : v)` | 每个元素复制 1 次 | `const auto&` 或 `auto&` |
| `auto [k, v] = *it` | 复制整个元素 | `const auto& [k, v]` |
| `std::move` 一个 `const` 对象，或类有 `const` 成员 | 移动变成复制 | 去掉 `const` |
| `vector<T> v{a, b, c}`，`T` 复制昂贵 | 每个元素复制 1 次 | `reserve` + `emplace_back` |
| `map::emplace` / `insert`，键常常已存在 | 构造后丢弃整个节点 | `try_emplace` |
| `const std::string&` 形参接收字面量 | 1 次分配 | `std::string_view` |

找这些问题时，先用计数器或分配计数确认次数，再用 [[perf/measuring|基准]] 看它在热路径上是否值得改。Clang 的 `-Wpessimizing-move`、`-Wredundant-move`、`-Wrange-loop-construct` 都在 `-Wall` 里；读汇编的方法见 [[perf/reading-assembly]]。

!!! question "思考题"
    1. `std::optional<std::string> f() { std::string s = g(); return s; }` 会发生几次复制或移动？如果把返回类型改成 `std::string`，又是几次？
    2. 一个结构体 `struct S { int a; std::string_view b; };` 有 24 字节。在 arm64 上按值传它，会放进寄存器吗？

<details markdown="1">
<summary>答案</summary>

1. 返回类型是 `std::optional<std::string>` 时，`s` 和返回类型不同，[[class.copy.elision#1.1]] 不适用（它要求同一类型），不能 NRVO。但 `s` 仍然是可隐式移动的（[[expr.prim.id.unqual#15]]），`optional` 的转换构造函数接收 `std::string&&`，所以是 1 次移动。返回类型是 `std::string` 时，通常 NRVO，0 次；即使不省略，也是 1 次移动。

2. 不会全放进寄存器。AAPCS64 只把不超过 16 字节的复合类型放进通用寄存器，更大的复合类型由调用方复制到内存，再传它的地址。本机可以写一个 `int f(S s) { return s.a; }` 编译看：被调函数从 `x0` 指向的内存读 `a`。拆成 `f(int a, std::string_view b)` 三个寄存器就够了。

</details>
