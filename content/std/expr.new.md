---
title: new 表达式
summary: new 表达式怎样分配存储并初始化对象：被分配类型与结果类型、数组边界与 bad_array_new_length、分配函数的查找与实参、数组开销、初始化抛异常时调用哪个释放函数，以及编译器何时可以不分配。
status: draft
papers: N3664, P0035R4, P0145R3, P0784R7, P1009R2, P2747R2
related: expr.delete, basic.stc.dynamic, basic.life, intro.object, class.free, new.delete, dcl.init, expr.const.core, basic.align
tags: new, operator new, 动态内存, placement new, 对齐, 分配省略
updated: 2026-10-19
---

!!! tldr
    - `new T(args)` 分两步：先调用分配函数 `operator new` 取得存储，再在上面初始化对象。分配先于实参求值，构造抛异常时由 *new-expression* 调用对应的释放函数归还内存。
    - `new T` 做默认初始化，`int` 和简单结构体的值不确定；要零值写 `new T()` 或 `new T{}`。
    - 数组 new 只有第一维可以是运行时的值。运行时的负数或过大的长度应抛出 `std::bad_array_new_length`，Clang 实际抛出的是 `std::bad_alloc`。
    - 类类型先在类作用域里找 `operator new`，找到任何一个就隐藏全局版本；`::new` 只找全局。
    - 编译器可以省略或合并对可替换全局 `operator new` 的调用，常量求值中则总是省略，这是 `constexpr` 里能用 `new` 的基础。

`new T(args)` 看起来像一次调用，实际做了两件事：调用一个**分配函数**（allocation function，名为 `operator new` 或 `operator new[]`，[[g:allocation-function]]）取得原始存储，再在这块存储上初始化一个对象。与之配对的**释放函数**（deallocation function）名为 `operator delete` 或 `operator delete[]`。

标准库提供了全局版本（[[new.delete]]），程序可以替换它们，也可以给类写专属版本（[[class.free]]）。分配函数和释放函数本身的要求在 [[basic.stc.dynamic]]，释放对象用的 `delete` 表达式见 [[expr.delete]]。

## 两步：分配与初始化

```cpp run ok
#include <cstdio>
#include <new>

struct W {
  explicit W(int) { std::puts("  W ctor"); }
  static void* operator new(std::size_t n) {
    std::puts("  allocate");
    return ::operator new(n);
  }
  static void operator delete(void* p) {
    std::puts("  deallocate");
    ::operator delete(p);
  }
};
int arg() { std::puts("  evaluate initializer"); return 1; }

int main() {
  delete new W(arg());
}
```

输出顺序一定是 allocate、evaluate initializer、W ctor、deallocate。¶12 规定 *new-expression* 通过调用分配函数获得存储：被分配类型不是数组时调用 `operator new`，是数组时调用 `operator new[]`。

¶25 规定了两条先后关系：分配函数的调用先于 *new-initializer* 中表达式的求值；对象的初始化先于整个表达式的值计算。第一条是 C++17 加的（[[P0145R3]]），此前 `new T(f())` 中先分配还是先调用 `f()` 是未指定的。它也意味着，即使初始化器的求值抛出异常，存储也已经分配了，这时由 ¶27 负责归还（见下文）。

### new T、new T() 与 new T{}（¶24）

¶24 省略 *new-initializer* 时，对象做**默认初始化**（[[g:default-initialization]]）；否则按直接初始化的规则处理初始化器（[[dcl.init]]）。由此产生了一个常见的差别：

| 写法 | 初始化方式 | `struct Pt { int x, y; }` | `int` | 有用户提供默认构造函数的类 |
|---|---|---|---|---|
| `new T` | 默认初始化 | 成员值不确定 | 值不确定 | 调用默认构造函数 |
| `new T()` | 值初始化 | 零初始化 | 0 | 调用默认构造函数，不先清零 |
| `new T{}` | 列表初始化 | 成员为 0 | 0 | 调用默认构造函数 |

```cpp run ok
#include <cstdio>
struct Pt { int x, y; };
int main() {
  Pt* p1 = new Pt;         // x、y 的值不确定，读取是 UB
  Pt* p2 = new Pt();       // 值初始化：x = y = 0
  Pt* p3 = new Pt{};       // 聚合初始化：x = y = 0
  int* i1 = new int[4];    // 4 个不确定值
  int* i2 = new int[4]();  // 4 个 0
  std::printf("%d %d %d %d %d\n", p2->x, p2->y, p3->x, p3->y, i2[3]);
  delete p1; delete p2; delete p3; delete[] i1; delete[] i2;
}
```

C++26 把读取未初始化的自动变量改成了错误行为（erroneous behavior，[[basic.indet]]），这只针对自动存储期。`new int` 得到的动态存储期对象仍然是不确定值，读取它仍是 UB。

## 被分配类型与结果（¶1–¶2、¶10–¶11）

¶1 *new-expression* 要创建的对象类型叫做**被分配类型**（allocated type，[[g:allocated-type]]）。它必须是完整的对象类型，不能是抽象类或抽象类的数组。引用不是对象，所以不能 `new` 一个引用（注 1）。类型可以带 cv 限定，`new const int(5)` 创建的就是 `const int` 对象（注 2）。

```cpp error
struct Abs { virtual void f() = 0; };
struct Inc;
void g(int n) {
  auto a = new int&(n);   // error: 引用不是对象
  auto b = new Abs;       // error: 抽象类
  auto c = new Abs[2];    // error: 抽象类的数组
  auto d = new Inc;       // error: 不完整类型
  auto e = new void;      // error: void 是不完整类型
}
```

¶10 创建的对象具有动态存储期（[[basic.stc.dynamic]]），生命周期不受创建它的作用域限制。

¶11 结果是 prvalue。被分配类型是 `T` 的数组时，结果类型是 `T*`，指向首元素；否则结果是指向被分配类型的指针。所以 `new int` 和 `new int[10]` 的类型都是 `int*`，`new int[i][10]` 的类型是 `int (*)[10]`（注 7）。

```cpp ok
#include <type_traits>
auto p1 = new const int(5);
static_assert(std::is_same_v<decltype(p1), const int*>);   // cv 限定保留
auto p2 = new int*[3];                                     // 3 个 int*，结果是 int**
static_assert(std::is_same_v<decltype(p2), int**>);
```

!!! pitfall "typedef 掩盖的数组 new"
    ```cpp
    using Buf = char[64];
    char* p = new Buf;    // 这是数组 new
    delete p;             // UB: 必须用 delete[]
    ```
    ¶11 说明，类型名指代数组类型时也算数组。被分配类型是数组就调用 `operator new[]`，也就必须配 `delete[]`，与写法无关（[[expr.delete#2]]）。

### auto 与类模板实参推导（¶2）

¶2 类型里出现 `auto`、`decltype(auto)` 或者省略了实参的类模板名时，被分配类型按虚构的声明 `T x init;` 推导，`init` 就是 *new-initializer*。

<div class="compare" markdown="1">

```cpp ok
template<class T>
struct A { A(T, T) {} };
auto x = new auto('a');  // char*
auto y = new A{1, 2};    // A<int>*
auto w = new auto{42};   // int*
```

```cpp error
auto a = new auto;
// error: 没有初始化器
auto b = new auto(1, 2);
// error: auto x(1, 2); 无法推导
auto c = new auto{1, 2};
// error: auto x{1, 2}; 非良构
```

</div>

### 文法上的两个陷阱（¶3–¶5）

¶3 类型部分（*new-type-id*）取尽可能长的声明符序列，所以 `new int * i` 读作 `(new int*) i`，是语法错误，不会读成 `(new int) * i`。

¶4 是一个注：`new int(*[10])()` 读作 `(new int)(*[10])()`，把 `(*[10])` 当成了 `int` 的初始化器，非良构。要分配函数指针数组这类复合类型，把整个类型放进括号：`new (int (*[10])())`。

¶5 数组声明符后面的属性属于对应的数组类型。

## 数组 new（¶6–¶9、¶26）

### 只有第一维可以是变量（¶6）

¶6 第一维是普通表达式，可以是运行时的值，也可以是 0；之后各维必须是值大于零的 `std::size_t` 常量表达式。

| `int n = 42;` | 结果 |
|---|---|
| `new float[n][5]` | OK，结果类型 `float(*)[5]` |
| `new float[5][n]` | 非良构：第二维不是常量 |
| `new float[0]` | OK：零个元素的数组 |
| `new float[n][0]` | 非良构：第二维必须大于零 |

结果是指向首元素的指针，首元素的类型（这里是 `float[5]`）必须在编译期完整已知，指针运算才有意义。C++ 没有 C99 那样的变长数组类型。

本机 Clang 23 对 `new float[n][0]` 只在 `-pedantic` 下给出 `zero size arrays are an extension` 警告。警告也算诊断，所以这符合标准，但默认配置下这段代码会作为扩展通过编译。

### 未知边界（¶7）{{c++20}}

¶7 类型是未知边界数组时，必须有初始化器，元素个数由初始化器决定。这条规则来自 C++20 的 [[P1009R2]]，作为缺陷报告适用于更早的标准。

<div class="compare" markdown="1">

```cpp ok
auto a = new int[]{1, 2, 3};   // 3 个
auto b = new char[]("hello");  // 6 个
auto c = new int[](1, 2);      // 2 个
```

```cpp error
auto a = new int[];
// error: 必须有初始化器
```

</div>

### 无效的长度（¶8）

¶8 第一维表达式隐式转换为 `std::size_t`。下面几种情况下它的值**无效**：

- ¶8.1 转换之前是负数；
- ¶8.2 表达式是类类型，经转换函数得到的值在转换为 `size_t` 之前是负数（脚注 53：转成 `size_t` 之后就看不出负数了）；
- ¶8.3 对象的总大小会超过实现定义的上限，比如 `n * sizeof(T)` 溢出；
- ¶8.4 初始化器给出的元素个数（字符串字面量算上结尾的 `'\0'`）比数组的元素还多。

值无效时，如果这个表达式是常量表达式，程序非良构（¶8.5）。否则不调用分配函数（¶8.6）：本该调用的分配函数不抛异常（如 `std::nothrow` 版本）时，结果是空指针；否则抛出一个能被 `std::bad_array_new_length` 类型的 handler 捕获的异常。

```cpp error
auto a = new int[-1];          // error: 常量且为负
auto b = new int[2]{1, 2, 3};  // error: 初始化器多于元素
```

```cpp run ok
#include <new>
#include <cstdio>
int main(int argc, char**) {
  int n = -argc;                          // 运行时的 -1
  try {
    int* p = new int[n];
    delete[] p;
  } catch (const std::bad_array_new_length&) {
    std::puts("bad_array_new_length");    // 标准要求走这里
  } catch (const std::bad_alloc&) {
    std::puts("bad_alloc");               // Clang 23 实际走这里
  }
  int* q = new (std::nothrow) int[n];     // 不抛异常的版本：结果为空
  std::puts(q ? "non-null" : "null");
}
```

!!! warning "Clang 的偏差"
    本机 Clang 23 的做法是把无效的大小换成 `SIZE_MAX`，照常调用 `operator new[]`，于是抛出普通的 `std::bad_alloc`，只捕获 `bad_array_new_length` 的代码会漏掉它。这也违反了不调用分配函数的要求：用户替换的 `operator new[]` 会收到一个 `SIZE_MAX` 的请求。初始化器过多的情形（¶8.4）也一样。加上 `-fsanitize=address` 时，ASan 会直接报告 `requested allocation size ... exceeds maximum supported size` 并终止程序。GCC 调用 Itanium ABI 的运行时函数 `__cxa_throw_bad_array_new_length` 实现 ¶8.6。

长度为 0 时照常调用分配函数，分配一个没有元素的数组。

### 没有被初始化器覆盖的元素（¶9）

¶9 长度不是常量、而又给了初始化列表时，编译器不知道列表会不会填满数组，所以要检查一个假想元素的初始化是否合法：花括号列表时，假想元素从 `{}` 复制初始化；圆括号列表时，假想元素做值初始化。

```cpp error
struct E { explicit E(); E(int); };
struct NoDef { NoDef(int); };
void f(int n) {
  auto a = new E[n]{1, 2};       // error: 剩余元素从 {} 复制初始化，不能用 explicit 构造函数
  auto b = new NoDef[n](1, 2);   // error: 剩余元素要值初始化，NoDef 没有默认构造函数
  auto c = new NoDef[2]{1, 2};   // OK：长度是常量，正好填满
}
```

### 数组 new 需要析构函数（¶26）

¶26 创建类类型对象的数组时，析构函数被**潜在调用**（[[g:potentially-invoked]]）。第 k 个元素构造时抛出异常，前面已经构造好的元素要逆序析构，所以即使从不 `delete[]`，`new T[n]` 也要求析构函数可访问、未被删除。

```cpp error
struct P { private: ~P() = default; public: P() = default; };
P* a = new P;      // OK：单个对象不需要析构函数
P* b = new P[2];   // error: 析构函数是私有的
```

## 调用哪个分配函数（¶13、¶17、¶19–¶21）

### 先找类作用域（¶13）

¶13 被分配类型是类类型 `T`（或它的数组），且表达式没有以 `::` 开头时，先在 `T` 的作用域里查找分配函数的名字（包括基类）。没有找到，或者写了 `::new`，就在全局作用域查找。

这是名字查找，不是重载决议失败后的回退：类作用域里只要有任何 `operator new`，全局版本就被隐藏了。

<div class="compare" markdown="1">

```cpp ok
#include <cstddef>
struct A {
  static void* operator new(
      std::size_t, int);
};
A* p = new (1) A;   // OK
A* q = ::new A;     // OK：只查全局
```

```cpp error
#include <cstddef>
struct A {
  static void* operator new(
      std::size_t, int);
};
A* p = new A;
// error: 全局版本被隐藏
```

</div>

所以一个类如果只写了 placement 版本，通常还要写出普通版本，或者用 `using` 把全局版本引进来（[[class.free]]）。

### 实参怎样组装（¶19–¶21）

¶19 *new-expression* 可以用 `new (args...) T` 的形式给分配函数传额外实参，这样的表达式叫做 **placement new-expression**（[[g:placement-new-expression]]）。标准里的 placement 泛指这种额外实参，不只是 `new (ptr) T`；`new (std::nothrow) T` 也是 placement new。

¶20 对组装出来的调用做重载决议：

1. 第一个实参是请求的字节数，类型为 `std::size_t`；
2. 如果类型的对齐要求超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（称为 new-extended 对齐，[[basic.align]]），下一个实参是对齐值，类型为 `std::align_val_t`；
3. placement 实参依次跟在后面。

找不到匹配的函数时再试一次：原来带对齐实参的就去掉它（¶20.1），原来不带的就加上（¶20.2）。这样只提供了 `operator new(size_t)` 的类仍然能 `new` 一个过对齐的类型（只是不再保证对齐），只提供对齐版本的类也能 `new` 普通类型。

¶21 的例子把四种情况写成了调用：

| 表达式 | 一般类型调用 | new-extended 对齐时调用 |
|---|---|---|
| `new T` | `operator new(sizeof(T))` | `operator new(sizeof(T), std::align_val_t(alignof(T)))` |
| `new(2,f) T` | `operator new(sizeof(T), 2, f)` | `operator new(sizeof(T), std::align_val_t(alignof(T)), 2, f)` |
| `new T[5]` | `operator new[](sizeof(T) * 5 + x)` | `operator new[](sizeof(T) * 5 + x, std::align_val_t(alignof(T)))` |
| `new(2,f) T[5]` | `operator new[](sizeof(T) * 5 + x, 2, f)` | `operator new[](sizeof(T) * 5 + x, std::align_val_t(alignof(T)), 2, f)` |

（找不到时再试另一列。）

```cpp run ok
#include <cstdio>
#include <cstdlib>
#include <new>

struct alignas(64) Line { char c[64]; };   // 64 超过默认的 new 对齐

void* operator new(std::size_t n, std::align_val_t a) {
  std::printf("operator new(%zu, align_val_t{%zu})\n", n, static_cast<std::size_t>(a));
  if (void* p = std::aligned_alloc(static_cast<std::size_t>(a), n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }

int main() {
  std::printf("default new alignment = %zu\n", __STDCPP_DEFAULT_NEW_ALIGNMENT__);
  Line* l = new Line;     // 第二个实参是 std::align_val_t(64)
  delete l;               // delete 也优先选带 align_val_t 的版本
}
```

本机（macOS arm64）输出 `default new alignment = 16` 和 `operator new(64, align_val_t{64})`。C++17 的 [[P0035R4]] 之前，`new` 完全不看 `alignas`，只调用 `operator new(64)`，返回的存储只保证基础对齐，过对齐的 SIMD 类型因此经常出错。

### 数组开销（¶17、¶21）

上表中的 *x* 是**数组分配开销**：一个非负的未指定值，数组 new 的结果相对于 `operator new[]` 的返回值偏移这么多。它可以出现在所有数组 new 中，包括调用用户 placement 分配函数的情形，唯一的例外是标准库的 `operator new[](std::size_t, void*)`。每次的开销可以不同。

¶17 第一个实参不能小于对象的大小；只有对象是数组、且分配函数不是 `operator new[](size_t, void*)` 这样的不分配形式时，才可以更大，多出的就是 *x*。对 `char`、`unsigned char`、`std::byte` 数组，*x* 还必须是一个对齐值的整数倍：所有大小不超过该数组的对象类型中，最严格的基础对齐。注 9 解释了原因：先 `new char[sizeof(T)]` 再在里面放置一个 `T` 是常见写法，开销不能破坏这块存储的对齐。

!!! impl "数组 cookie"
    实践中 *x* 几乎只有一个用途：在数组前面记录元素个数，叫做 **cookie**，让 `delete[] p` 知道要析构多少个元素。

    - Itanium C++ ABI（x86-64 Linux/macOS、AArch64 Linux）：元素类型有非平凡析构函数，或者选中的 `operator delete[]` 需要 `size_t` 形参时才加 cookie。cookie 大小是 `max(sizeof(size_t), alignof(T))`，元素个数存在紧挨首元素之前。`struct NT { int x; ~NT(); }` 在 x86-64 上，`new NT[5]` 请求 5 × 4 + 8 = 28 字节，结果指针偏移 8。
    - ARM C++ ABI（32 位 ARM，以及 Apple arm64）：cookie 是两个 `size_t`，依次存元素大小和元素个数。
    - 析构平凡的元素类型通常没有 cookie，`new int[4]` 恰好请求 16 字节。
    - MSVC 同样为有非平凡析构函数的元素类型记录元素个数。
    - `operator new[](size_t, void*)` 不加 cookie；用户自定义的 placement `operator new[]` 可能加，这时 `new (buf) T[n]` 会用掉比 `n * sizeof(T)` 更多的字节。

    这就是 `new[]` 必须配 `delete[]` 的实际原因：`delete` 不会去读 cookie，传给 `operator delete` 的指针比真正的分配地址偏了 8 或 16 字节；反过来，对单个对象用 `delete[]` 会去读一个不存在的 cookie。

```cpp run impl
#include <cstdio>
#include <cstdlib>
#include <new>

struct Trivial { int x; };
struct NonTrivial { int x; ~NonTrivial() {} };

void* last;
void* operator new[](std::size_t n) {
  std::printf("operator new[](%zu)\n", n);
  return last = std::malloc(n);
}
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t n) noexcept {
  std::printf("operator delete[](p, %zu)\n", n);
  std::free(p);
}

int main() {
  auto* a = new Trivial[4];
  std::printf("  offset = %td\n", (char*)a - (char*)last);
  delete[] a;
  auto* b = new NonTrivial[5];
  std::printf("  offset = %td\n", (char*)b - (char*)last);
  delete[] b;
}
```

本机（macOS arm64）输出 `operator new[](16)`、`offset = 0`、`operator new[](36)`、`offset = 16`、`operator delete[](p, 36)`。在 x86-64 Linux 上第二次分配是 28 字节，偏移 8。第一次 `delete[]` 调用不带大小的版本，第二次调用带大小的版本，选择规则见 [[expr.delete#9]]。

## 分配失败（¶22–¶23）

¶22 注 10：不带 `noexcept` 的分配函数用抛出 `std::bad_alloc` 表示失败；`noexcept` 的分配函数用返回空指针表示失败。

分配函数返回空指针时，不做初始化，也不调用释放函数，*new-expression* 的值是空指针。所以 `new (std::nothrow) T(args)` 失败时，`T` 的构造函数根本不会被调用。

例外是不分配形式 `operator new(size_t, void*)`（[[new.delete.placement]]）：它返回空指针，也就是写了 `new (nullptr) T`，行为未定义。把它单独定为 UB，编译器就不必在每次 `new (p) T` 之前检查 `p` 是否为空。

```cpp ub
#include <new>
int main() {
  void* p = nullptr;
  int* q = ::new (p) int(1);   // UB: 不分配形式的 placement new 得到空指针
  (void)q;
}
```

¶23 注 11：返回非空指针时，它指向一块大小足够、对齐合适的存储。对数组来说，对象的地址不一定等于这块存储的地址，因为前面可能有 cookie。

## 初始化失败时归还内存（¶27–¶32）

```cpp run ok
#include <cstdio>
#include <new>

struct Arena { alignas(16) char buf[256]; std::size_t used = 0; };

struct Widget {
  int v;
  explicit Widget(int v) : v(v) { if (v < 0) throw v; }

  static void* operator new(std::size_t n) {
    std::printf("  Widget::operator new(%zu)\n", n);
    return ::operator new(n);
  }
  static void operator delete(void* p) noexcept {
    std::puts("  Widget::operator delete(void*)");
    ::operator delete(p);
  }
  static void* operator new(std::size_t n, Arena& a) {
    std::printf("  Widget::operator new(%zu, Arena&)\n", n);
    void* p = a.buf + a.used; a.used += n; return p;
  }
  static void operator delete(void*, Arena&) noexcept {   // 与上面的 placement 版本配对
    std::puts("  Widget::operator delete(void*, Arena&)");
  }
};

int main() {
  std::puts("new Widget(-1):");
  try { new Widget(-1); } catch (int) { std::puts("  caught"); }

  Arena a;
  std::puts("new (a) Widget(-2):");
  try { new (a) Widget(-2); } catch (int) { std::puts("  caught"); }
}
```

两次构造都抛出异常。第一次调用了普通的 `operator delete(void*)`，第二次调用了与 placement 版本配对的 `operator delete(void*, Arena&)`，然后异常才被 `catch` 捕获。

¶27 初始化的任何部分（包括求值初始化器和调用构造函数）以异常结束时，如果能找到匹配的释放函数，就用它归还存储，然后异常继续向外传播。找不到无歧义的匹配函数时，异常照样传播，但存储不归还。注 13 指出，这对 `new (buf) T` 这类不真正分配内存的形式是合适的，对其他形式则多半意味着内存泄漏。

¶28 释放函数的查找方式与分配函数相同：类类型先查类作用域，`::new` 只查全局。

¶29 普通（非 placement）的分配函数按 `delete` 表达式的规则选释放函数（[[expr.delete]]）；placement 分配函数按 ¶30 选。无论哪种，选中的释放函数都必须未被删除，并且在 *new-expression* 处可以访问。

### placement 分配函数配哪个释放函数（¶30–¶31）

¶30 候选释放函数中，去掉第一个形参（分配函数的 `size_t`、释放函数的 `void*`）后，形参类型列表必须与分配函数完全相同。函数模板先通过实参推导换成特化，约束不满足的候选被去掉。恰好剩下一个就选它，否则不选任何函数。比分配函数多一个形参的释放函数永远不匹配，即使那个形参有默认实参（注 14）。

如果选中的是一个**普通释放函数**（[[g:usual-deallocation-function]]），程序非良构。例 7 说明了原因：

```cpp error
#include <cstddef>
struct S {
  static void* operator new(std::size_t, std::size_t);   // placement 分配函数
  static void operator delete(void*, std::size_t);       // 普通的带大小释放函数
};
S* p = new (0) S;   // error
```

去掉第一个形参后两者都是 `(size_t)`，形式上匹配。但释放函数的第二个形参表示对象的大小，placement new 传过去的却是实参 `0`，含义完全不同。标准选择直接报错，而不是悄悄传错实参。

例 8–10 处理模板和约束，这部分是 C++23 之后的新措辞。例 8 中唯一的候选是模板 `template<int = 0> void operator delete(void*, A&)`，推导后与分配函数匹配，被选中。例 9 中模板和非模板都匹配，剩下两个候选，于是不选任何函数，程序仍然良构，只是构造抛异常时不归还存储。例 10 用 `requires (I > 0)` 排除了模板，剩下的非模板被选中。

¶32 释放函数的第一个实参是分配函数返回的指针；placement 释放函数还会收到与分配时相同的 placement 实参。

## 省略和合并分配（¶14–¶16、¶18）

¶14 实现可以省略对可替换的全局分配函数的调用，改由实现自己提供存储，或者扩展另一次 *new-expression* 的分配。

```cpp ok
int f() {
  int* p = new int(42);   // Clang -O2 下整个函数变成 return 42
  int r = *p;
  delete p;
  return r;
}
```

替换的 `operator new` 可能有打印、计数之类的副作用，所以在 C++14 之前，按 as-if 规则编译器不能删除一对多余的 `new`/`delete`。[[N3664]] 明确允许省略这些调用，即使用户替换了分配函数，它也可能根本不被调用。这只适用于 *new-expression* 调用的可替换全局分配函数；类专属的 `operator new`、直接写的 `::operator new(n)` 调用和 placement 形式都不在此列。

¶16 实现还可以把两次分配合并成一次：扩展 `e1` 的分配，同时为 `e2` 提供存储。前提是合并与否看不出区别，条件包括 `e1` 先于 `e2` 求值、`e1` 拿到存储后 `e2` 一定求值、两者调用同一个可替换全局分配函数、抛出的异常会先被同一个 handler 捕获、两个指针都会被 `delete`，并且 `e2` 在 `delete` `e1` 之前求值。标准例 5 中，第二次分配放在 `try` 块里时不能合并，因为合并会改变分配失败时由哪个 handler 捕获。¶18 规定合并后的大小不超过各次分配之和加上必要的对齐填充。

## 常量求值中的 new（¶15）{{c++20}}

¶15 常量求值中，对可替换分配函数的调用总是被省略，存储由编译器提供。C++20 起（[[P0784R7]]），常量求值里可以用 `new`，但分配的存储必须在同一次常量求值中用 `delete` 释放，叫做**暂时分配**（[[g:transient-allocation]]）。

<div class="compare" markdown="1">

```cpp ok
constexpr int sum(int n) {
  int* p = new int[n];
  int s = 0;
  for (int i = 0; i < n; ++i)
    s += (p[i] = i);
  delete[] p;   // 同一次求值中释放
  return s;
}
static_assert(sum(10) == 45);
```

```cpp error
constexpr int* leak() {
  return new int(1);
}
constexpr int* q = leak();
// error: 分配逃出了常量求值
```

</div>

{{c++26}} C++26 起（[[P2747R2]]），`operator new(size_t, void*)` 也是 `constexpr` 的，常量求值中可以用 placement new，条件是指针指向合适类型的对象（[[expr.const.core]]）。`std::construct_at` 从此不再需要编译器特殊处理。

```cpp ok
#include <memory>
#include <new>
constexpr int g() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  ::new (static_cast<void*>(p)) int(7);   // C++26：常量求值中可用
  int r = *p;
  std::destroy_at(p);
  al.deallocate(p, 1);
  return r;
}
static_assert(g() == 7);
```

## placement new 与 const 对象

被分配类型可以是任何完整对象类型，*new-expression* 本身不关心目标存储里原来是什么。但 [[basic.life#12]] 规定，在静态、线程或自动存储期的 const 完整对象的存储上创建新对象是 UB，因为编译器可以假设这些对象的值不变，甚至把它们放进只读段。

<div class="compare" markdown="1">

```cpp ub
#include <new>
struct S { int m; };
const S cs{1};
int main() {
  ::new (const_cast<S*>(&cs)) S{2};
  // UB: 静态存储期的 const 对象
}
```

```cpp run ok
#include <new>
struct S { int m; };
int main() {
  const S* p = new const S{1};
  ::new (const_cast<S*>(p)) S{2};
  p = std::launder(p);
  int r = p->m;
  delete p;
  return r == 2 ? 0 : 1;
}
```

</div>

动态存储期的 const 对象不受这条限制。但旧对象是 const 完整对象，不能被透明替换（[[basic.life#9]]），所以要先用 `std::launder` 才能通过旧指针访问新对象。

## 历史与演进

!!! history
    - C++98 已有 placement 语法、`std::nothrow` 和数组开销 *x*；负的数组长度是 UB。
    - C++11 加入花括号初始化器和 `new auto(x)`，负数或过大的数组长度改为抛出新增的 `std::bad_array_new_length`。
    - C++14 的 [[N3664]] 允许省略和合并对可替换全局分配函数的调用。
    - C++17 的 [[P0035R4]] 加入对齐 new；[[P0145R3]] 规定分配先于初始化器求值；`new A{1, 2}` 也可以做类模板实参推导。
    - C++20 的 [[P0784R7]] 允许常量求值中使用 `new`；[[P1009R2]] 允许未知边界数组的 new；圆括号聚合初始化让 `new int[](1, 2)` 成立。
    - C++26 的 [[P2747R2]] 允许常量求值中使用 placement new。

## 常见误解

!!! pitfall "以为 `new T` 会清零"
    `new int`、`new Pt`（聚合）、`new int[n]` 都只做默认初始化，值不确定。需要零值时写 `new T()`、`new T{}` 或 `new int[n]()`。

!!! pitfall "以为替换的 `operator new` 一定会被调用"
    ¶14 允许省略对可替换全局分配函数的调用。用替换 `operator new` 统计分配次数的测试，开优化后可能得到更少的计数。

!!! pitfall "以为 `new (buf) T[n]` 正好用 `n * sizeof(T)` 字节"
    标准库的 `operator new[](size_t, void*)` 不加开销，但用户定义的 placement `operator new[]` 可能加。不要假设数组 placement new 的结果等于 `buf`。

## 思考题

!!! question "思考题 1"
    `int n = 0;` 时 `new int[n]` 返回什么？能对结果解引用吗？需要 `delete[]` 吗？

<details markdown="1">
<summary>答案</summary>

¶8 末尾规定长度为 0 时照常调用分配函数。[[basic.stc.dynamic.allocation]] 要求即使请求 0 字节，成功的分配也返回一个非空、与其他存活分配都不同的指针。零元素数组没有首元素，结果不指向任何对象，解引用是 UB；但这次分配是真实的，必须 `delete[]`，否则会泄漏。
</details>

!!! question "思考题 2"
    `new (std::nothrow) T(f())` 中，如果分配失败返回空，`f()` 会被调用吗？如果分配成功而 `f()` 抛出异常，会怎样？

<details markdown="1">
<summary>答案</summary>

按 ¶25，分配先于初始化器求值。分配失败返回空时，¶22 规定不做初始化，`f()` 是初始化的一部分，所以不会被调用。

分配成功而 `f()` 抛异常，属于 ¶27 所说的初始化以异常结束。`std::nothrow` 版本是 placement 分配函数，按 ¶30 找到标准库提供的 `operator delete(void*, const std::nothrow_t&)`，用它归还存储，然后异常继续传播。
</details>

## 小结

| 阶段 | 段落 | 规则 |
|---|---|---|
| 类型 | ¶1–¶2 | 完整对象类型，非抽象，可带 cv；`auto` 和类模板按 `T x init;` 推导 |
| 数组长度 | ¶6–¶9 | 只有第一维可以是变量；无效长度：常量则非良构，运行时则抛 `bad_array_new_length` 或得到空指针 |
| 结果 | ¶11 | 数组得到首元素指针，否则得到对象指针 |
| 查找 | ¶13、¶28 | 类类型先查类作用域并隐藏全局；`::new` 只查全局 |
| 实参 | ¶17、¶20–¶21 | 大小（数组可含开销）、可能的 `align_val_t`、placement 实参；找不到时换一种再试 |
| 省略与合并 | ¶14–¶18 | 只针对可替换全局分配函数；常量求值中总是省略 |
| 失败 | ¶22 | 返回空则不初始化；不分配形式返回空是 UB |
| 初始化 | ¶24–¶25 | 无初始化器则默认初始化；分配先于初始化器求值 |
| 清理 | ¶26–¶32 | 初始化抛异常时调用匹配的释放函数；placement 要求形参列表一致，匹配到普通释放函数则非良构 |
