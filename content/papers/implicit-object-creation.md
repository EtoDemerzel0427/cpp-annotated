---
title: 隐式创建对象（P0593）
summary: C++20 以缺陷修复的形式规定 malloc、operator new、memcpy 等操作会按需创建对象，让 C 风格的底层代码有了定义；这一页讲它要解决的问题、被否决的几种方案、最终措辞，以及后来为什么还需要 std::start_lifetime_as。
status: draft
order: 12
group: 核心语言
since: c++20
papers: P0593R6, CWG2325, CWG2382, CWG2489, CWG2605, LWG4064, P2590R2, P2674R1, CWG3042
related: intro.object, basic.life, class.prop, obj.lifetime, ptr.launder, diff.cpp17, basic.lval, topics/object-model, topics/type-punning, topics/undefined-behavior, topics/allocators-and-pmr
tags: 提案, 对象模型, 生命周期, malloc, memcpy, DR, UB
updated: 2026-10-19
---

!!! tldr
    - C++17 的条文里，`malloc` 返回的内存中没有任何对象，`p->a = 1` 严格来说是 UB；`std::vector` 那样在分配的存储上做指针运算也没有定义。编译器从未利用这一点，问题出在规则本身。
    - [[P0593R6]] 规定一批操作会隐式创建对象：只创建隐式生存期类型的对象，而且创建哪些对象，由之后的代码怎样使用这块存储决定，前提是这样能让程序有定义。
    - 委员会否决了存储即对象的方案，因为它会让基于类型的别名分析失效；它也没有让类型双关合法，旧对象的值不会传给新对象。
    - 语言部分作为缺陷修复进入 C++20，库函数 `std::start_lifetime_as` 推迟到 C++23（[[P2590R2]]）。它仍然需要，因为隐式创建只发生在少数几个操作上，而且不会改变已有指针的指向。
    - 这类 UB 没有工具能可靠地检查：UBSan、ASan 都看不见，Clang 的 TypeSanitizer 按访问类型检查，与 C++ 的对象模型并不一致。

## 问题：有内存，没有对象

一个再普通不过的 C 函数，放进 C++ 编译：

```cpp run title="make-x.cpp" ok
#include <cstdio>
#include <cstdlib>

struct X { int a, b; };

X* make_x() {
  X* p = (X*)std::malloc(sizeof(struct X));
  p->a = 1;   // C++17 的条文：没有 X 对象，UB
  p->b = 2;   // C++20 起：OK
  return p;
}

int main() {
  X* x = make_x();
  std::printf("%d\n", x->a + x->b);
  std::free(x);
}
```

C++ 的**对象**（object）是有类型、有生命周期的实体，不等于一块字节（见 [[topics/object-model]]）。C++17 列出了创建对象的全部途径：定义、*new-expression*、切换联合体的活跃成员、创建临时对象。`malloc` 不在其中，所以 `p` 不指向任何 `X`，`p->a` 访问的是一个不存在的 `int` 子对象。

这不是孤例。[[P0593R6]] 的动机一节举了三类代码：

1. 上面这样的 C 惯用法；
2. 从磁盘或网络读进一个字节缓冲区，知道里面是某个结构体的表示，于是 `reinterpret_cast<Foo*>(buf)` 去读；
3. 自己实现一个类似 `std::vector` 的容器：用 `::operator new` 分配原始存储，在上面逐个构造元素，再用 `T*` 做指针运算。

第三类最出人意料。指针运算只在数组对象内部有定义（[[expr.add]]），而 `::operator new` 返回的存储里没有数组对象，于是 `begin() + i`、`end() - begin()` 全都没有定义。按 C++17 的字面规则，`std::vector` 不能用标准 C++ 实现。这个缺口最早以核心语言问题 [[CWG2325]] 的形式提出，[[P0593R6]] 是它的解决方案。

### 编译器的立场

这几类代码在所有实现上都能正常工作。本机 Clang 23 分别用 `-std=c++17` 和 `-std=c++20` 以 `-O2` 编译上面的 `make_x`，生成的汇编逐字节相同：调用 `malloc`，然后一条 8 字节的存储同时写入 1 和 2。

论文对此的解释是：编译器看不到 `malloc` 内部，也就不能假设它没有创建对象；创建对象本身在机器上又没有任何动作。所以编译器生成的代码必须在 `malloc` 恰好创建了正确对象的情况下也是对的。现状已经是这样，标准只需要把它写下来。难点在于怎样写，才不至于连带放开不该放开的东西。

## 设计空间

### 方案一：存储即对象

最简单的规则是：任何依赖某个对象存在的地方，那个对象就自动存在。字节就是对象，换个类型去写就换了对象。这和 C 的**有效类型**（effective type）规则大体一致：`malloc` 的内存没有声明类型，第一次用什么类型写入，就获得什么类型（两种模型的对比见 [[topics/object-model]]）。

论文否决了这个方案，理由是它会削弱**基于类型的别名分析**（type-based alias analysis，TBAA）：编译器假设不同标量类型的左值不会指向同一个对象，从而省掉重新加载。

```cpp run title="tbaa.cpp" ok
int f(int* i, float* x) {
  *i = 1;
  *x = 2.0f;   // 不可能修改 *i 所在的 int 对象
  return *i;   // 编译器直接返回 1
}
```

本机 Clang 23 `-O2` 把 `return *i` 编译成常量 1；加上 `-fno-strict-aliasing` 后才从内存重新加载。这个优化的依据是 [[basic.lval#11]]：通过 `float` 左值不能访问 `int` 对象。如果 `*x = 2.0f` 可以在原地变出一个 `float` 对象，这条依据就不成立了。论文还指出，C 委员会为有效类型与 TBAA 的冲突（C 的缺陷报告 236）先后采纳过至少四种互不相容的解释，近二十年没有好的解法，所以不走这条路。

这个选择留下了一个可见的差异：C 允许的内存池写法，在 C++ 里仍然是 UB。

```cpp run title="reuse.cpp" ub
#include <cstdio>
#include <cstdlib>

int main() {
  void* m = std::malloc(8);
  *static_cast<int*>(m) = 1;      // malloc 隐式创建 int
  *static_cast<float*>(m) = 2.0f; // UB：这里没有 float 对象
  std::printf("%g\n", *static_cast<float*>(m));
  std::free(m);
}
```

`malloc` 只能在被调用的那一刻创建一组对象，`int` 和 `float` 不能同时占据同一处存储，所以没有任何一组对象能让两次写入都有定义。在 C 里，第二次写入只是改变了有效类型。要在 C++ 里复用，必须在第二次写入前显式创建新对象，例如 `::new (m) float(2.0f)`。C 的有效类型规则能否用隐式创建完整表达，至今还是一个未解决的核心问题（[[CWG3042]]）。

### 方案二：只让分配函数预知未来

第二种思路只给 `malloc`、`operator new` 特权：它们知道这块存储将来怎样被使用，并创建恰好需要的对象。论文认为这还不够。内存池会把同一块分配反复用于不同对象，这种复用发生在 C++ 代码里，编译器看得见，也需要同样的能力。

所以论文要求一个显式的标记，说明从这里开始创建对象。`malloc` 是一个现成的标记；对于复用的存储，需要另外的标记。早期版本提议过一个库函数 `std::bless(void* p, size_t n)`。R5 根据库设计组的审查意见删去了它，理由是，`new (p) std::byte[n]` 已经能起同样的作用：字节数组的生命周期开始时会在其中隐式创建对象。这依赖于 [[CWG2382]]：它规定不分配内存的 placement new 创建数组时不能有额外开销，`new (p) std::byte[n]` 恰好占用 `[p, p + n)`。有类型的版本则改名为 `start_lifetime_as`，后文再讲。

### 方案三：成员访问即创建

论文的 R2 曾提议，对联合体做成员访问本身就足以隐式创建对象。一位实现者提出反对后，R3 删掉了这一条。`reinterpret_cast` 也从来不在考虑之列：指针转换不创建对象。

### 哪些类型可以隐式创建

隐式地创建一个对象，前提是这件事不需要运行任何代码。论文据此提出两个条件：创建这个类型的对象不运行代码；销毁它也不运行代码。一个维护不变量的类型，不应该凭空出现。

这两个条件只看对象本身，不看子对象。数组对象本身的创建和销毁不运行代码（元素的另当别论），聚合类也可以这样看。最终的**隐式生存期类型**（[[g:implicit-lifetime-type|implicit-lifetime type]]，[[basic.types.general#7]]）包括标量、隐式生存期类、任意数组，以及它们的 cv 限定版本。**隐式生存期类**（[[g:implicit-lifetime-class|implicit-lifetime class]]，[[class.prop#8]]）是：

- 析构函数不是用户提供的聚合类；或者
- 至少有一个平凡的合格构造函数（默认、复制、移动都算），并且析构函数平凡且未被删除的类。

只要求一个平凡构造函数，而不是要求默认构造和复制构造都平凡，是 R2 根据研究组意见放宽的：只有平凡默认构造函数的类型适合逐成员赋值来构造，只有平凡复制构造函数的类型适合从磁盘上的表示复制进来。聚合类是 R4 按演化组的意见加入的。第一个条件里的析构函数限制是 [[CWG2605]] 后来补上的。C++23 的 `std::is_implicit_lifetime`（[[P2674R1]]）可以直接查询：

```cpp run title="implicit-lifetime.cpp" ok
#include <memory>
#include <string>
#include <type_traits>

struct Pod { int a; double b; };
struct Agg { int n; std::unique_ptr<int> p; };
struct AggDtor { int n; ~AggDtor() {} };
struct Ctor { int x; Ctor() = default; Ctor(int); };
struct Rule0 { std::string s; Rule0(); };

static_assert(std::is_implicit_lifetime_v<Pod>);
static_assert(std::is_implicit_lifetime_v<Agg>);
static_assert(!std::is_implicit_lifetime_v<AggDtor>);
static_assert(std::is_implicit_lifetime_v<Ctor>);
static_assert(!std::is_implicit_lifetime_v<Rule0>);
static_assert(std::is_implicit_lifetime_v<std::string[4]>);
static_assert(!std::is_implicit_lifetime_v<std::string>);

int main() {}
```

`Agg` 含有一个 `unique_ptr`，仍然是隐式生存期类型，因为它是聚合类，自己的析构函数不是用户提供的。但隐式创建一个 `Agg` 并不会开始 `p` 的生命周期（[[intro.object#13]] 注 4），`p` 仍要用 placement new 构造。`std::string[4]` 同理：数组对象可以隐式出现，四个 `string` 元素不会。`AggDtor` 是 [[CWG2605]] 排除的情形，本机 Clang 23 已经按这一修正实现。

## 最终规则

### 按需创建

[[intro.object#13]] 是整个提案的核心：

!!! std
    For each operation that is specified as implicitly creating objects, that operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types ([basic.types.general]) in its specified region of storage if doing so would result in the program having defined behavior.

被规定为**隐式创建对象**（[[g:implicitly-create-objects|implicitly create objects]]）的操作，在它的存储区域里创建零个或多个隐式生存期类型的对象，选择的标准是这样做能让程序有定义的行为。没有这样一组对象时，程序是 UB；有多组时，创建哪一组是未指定的。

要创建哪些对象，可以取决于之后才执行到的代码：

```cpp run title="choose.cpp" ok
#include <cstdio>
#include <cstdlib>

int main(int argc, char**) {
  void* m = std::malloc(2 * sizeof(double));
  if (argc > 1) {                 // malloc 创建了 double
    double* d = static_cast<double*>(m);
    *d = 1.5;
    std::printf("%g\n", *d);
  } else {                        // malloc 创建了 int[2]
    int* p = static_cast<int*>(m);
    p[0] = 1;
    p[1] = 2;                     // 指针运算需要数组对象
    std::printf("%d\n", p[0] + p[1]);
  }
  std::free(m);
}
```

哪个分支执行，取决于运行时的参数，而 `malloc` 在分支之前就被调用了。规则的意思是：对实际发生的那一次执行，存在一组对象使它有定义，那么 `malloc` 就创建了那组对象。论文把这一点概括为一个观察：改变隐式创建的对象集合，只能改变一次执行是否有定义，不能改变它的行为。正因为如此，这个看似要预知未来的规则不需要编译器做任何事。

论文用 `std::vector<int>` 说明多组对象并存的情形。`reserve(4)` 之后只 `push_back` 三次，那么在分配的存储里创建 `int[3]` 或 `int[4]` 都能让程序有定义，两种解释给出同样的行为；再 `push_back` 一次，就只剩 `int[4]` 这一种。

### 返回哪个指针

只创建对象还不够，`malloc` 返回的指针还得指向正确的对象。上例的 `else` 分支里，需要的是指向 `int[2]` 第一个元素的指针，而不是指向数组本身的指针，否则 `static_cast<int*>(m)` 得不到能做下标运算的 `int*`（数组和它的首元素不是**指针可互转**的，[[basic.compound#7]]）。

R6 为此加入了 [[intro.object#14]]：有些操作还会产生一个指向**合适的已创建对象**（[[g:suitable-created-object|suitable created object]]）的指针，即从地址恰好在区域起点的已创建对象里选一个，选择标准同样是让程序有定义。`malloc`、`calloc`、`realloc`、`aligned_alloc`（[[c.malloc#4]]、[[c.malloc#7]]）和所有名为 `operator new`、`operator new[]` 的函数（[[intro.object#16]]）都是这样。

字节数组的生命周期开始时也会隐式创建对象，但这种操作没有返回值，从数组退化来的指针仍然指向数组元素。这就是为什么字节缓冲区里的对象要用 `std::launder` 才能拿到，详见 [[topics/object-model]] 中 `launder` 一节。

### 措辞改了哪里

| 条款 | 改动 |
|---|---|
| [[intro.object#1]] | 创建对象的途径加上隐式创建对象的操作 |
| [[intro.object#13]]–[[intro.object#16]] | 隐式创建的规则、合适的已创建对象、字节数组和 `operator new` |
| [[basic.types.general#7]]、[[class.prop#8]] | 定义隐式生存期类型和隐式生存期类 |
| [[c.malloc#4]]、[[c.malloc#7]] | `malloc` 一族隐式创建对象；`calloc` 在清零前、`realloc` 在复制前创建 |
| [[cstring.syn#3]] | `memcpy`、`memmove` 在复制前于目标区域隐式创建对象 |
| [[allocator.members]] ¶5 | `allocator<T>::allocate(n)` 只创建 `T[n]` 数组对象，不开始元素的生命周期 |
| [[bit.cast]] ¶3 | 结果里嵌套的对象被隐式创建（用于含联合体的类型） |
| [[class.copy.ctor#16]] 等 | 平凡的联合体复制同时复制对象结构 |
| [[basic.life#2]]、[[expr.call#4]] | 伪析构函数调用结束对象的生命周期 |

`allocate` 一行是 R6 为了和 C++20 的 constexpr 容器协调而改的：如果 `allocate` 可以创建任意一组对象，编译期求值器就无法跟踪；规定它只创建一个 `T[n]`，指针运算有了数组可依，编译期也能精确建模。用户自己的分配器复用存储时，可以用 `new (p) std::byte[n * sizeof(T)]` 满足同样的要求。

### 没有让类型双关合法

隐式创建很容易被误读为字节可以随便当作任何类型来读。论文专门用一节说明它不是：

```cpp run title="no-pun.cpp" ub
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>

int main() {
  void* m = std::malloc(4);
  *static_cast<int*>(m) = 0x3f800000;  // OK：malloc 创建了 int
  ::new (m) std::byte[4];              // OK：在其中隐式创建对象
  float* f = std::launder(static_cast<float*>(m));
  std::printf("%g\n", *f);             // UB：float 的值不确定
  std::free(m);
}
```

`new (m) std::byte[4]` 之后，确实可以有一个 `float` 隐式出现，`*f` 也确实指向它。但对象的值只在它自己的生命周期内有意义（[[basic.life#5]]）：`int` 的生命周期因存储被复用而结束，它的值随之消失；新创建的 `float` 的值是不确定的，读取不确定值是 UB（[[basic.indet]]）。这保住了 TBAA 的前提：读某个标量类型，不会读到之前以无关标量类型写入的值。想要按另一种类型解释字节，用 `std::memcpy` 或 `std::bit_cast`（见 [[topics/type-punning]]）。

同样的考虑决定了联合体的复制：

```cpp run title="union-copy.cpp" ub
union U { int n; float f; };

float pun(int n) {
  U u = {.n = n};
  U u2 = u;      // u2 的活跃成员也是 n
  return u2.f;   // UB：f 不在生命周期内
}

int main() { return pun(1) > 0; }
```

平凡的联合体复制构造函数只复制字节。按 C++17 的字面规则，`u2` 没有任何活跃成员。论文考虑过两种修法：让复制同时复制对象结构，`u2` 的活跃成员是 `n`；或者让复制隐式创建对象，那么 `u2.f` 就成了一次位转换。它选了前者，理由是保持等式推理（`u2` 应当和 `u` 一样），并让位转换显式写成 `std::bit_cast`。结果写在 [[class.copy.ctor#16]] 和 [[class.copy.assign]] 里。

### 常量求值中不创建

[[intro.object#16]] 开头的 *Except during constant evaluation* 把常量求值排除在外。论文的理由是常量求值本来就对对象创建很保守，一些实现支持它的代价很高；常量表达式里禁止 `reinterpret_cast`，大部分情况下也观察不到差别。

<div class="compare" markdown="1">

```cpp error
#include <memory>
constexpr int g() {
  std::allocator<int> al;
  int* p = al.allocate(2);
  p[0] = 1;   // 元素不在生命周期内
  int r = p[0];
  al.deallocate(p, 2);
  return r;
}
static_assert(g() == 1);
```

```cpp ok
#include <memory>
constexpr int h() {
  std::allocator<int> al;
  int* p = al.allocate(2);
  std::construct_at(p, 1);
  int r = p[0];
  std::destroy_at(p);
  al.deallocate(p, 2);
  return r;
}
static_assert(h() == 1);
```

</div>

`allocate` 只开始数组对象的生命周期，不开始元素的生命周期（[[allocator.members]] ¶5），常量求值中又没有隐式创建可以补上，所以 `p[0]` 是一个不在生命周期内的 `int`。本机 Clang 23 拒绝左边，指出 `p[0] = 1` 是对生命周期外对象的赋值。在编译期，元素必须用 `std::construct_at` 逐个创建。

### 伪析构函数调用

论文顺带修正了一处不一致。泛型代码写 `p->~T()`，`T` 为 `int` 时叫**伪析构函数调用**（[[g:pseudo-destructor|pseudo-destructor]]），C++17 规定它没有效果。论文认为这是错误：既然对象可以隐式出现，也应当能明确地结束。C++20 起，伪析构函数调用会结束标量对象的生命周期（[[expr.call#4]]）。论文为此加了一条 Annex C 条目：之后再读这个对象是 UB，常量求值里能观察到，见 [[diff.cpp17.basic#1]] 和 [[diff.cpp17]] 页面的说明。

### 以缺陷修复进入 C++20

论文没能在 C++20 的截止日期前完成库部分的审查，于是作者把它拆成两半：给既有写法赋予定义的语言规则，作为缺陷修复（DR）并入 C++20，同时回应了一条要求 C++20 采纳隐式对象创建的国家成员体意见；DR 意味着它也适用于更早的标准模式。新增的库函数 `start_lifetime_as` 推迟到 C++23。DR 的含义见 [[papers/how-to-read-a-paper|如何读一篇提案]]。这也是为什么 `make_x` 在 `-std=c++17` 下同样应当视为有定义。

## 之后的修正

[[CWG2489]] 删掉了 `char` 数组。[[P0593R6]] 原本规定 `char`、`unsigned char`、`std::byte` 三种数组开始生命周期时都会隐式创建对象，但只有后两种能为其中的对象**提供存储**（[[g:provides-storage|provides storage]]，[[intro.object#3]]）。两处措辞不一致，修正的结果是 `char` 数组不再隐式创建对象。缓冲区应当一律声明为 `unsigned char` 或 `std::byte`（见 [[intro.object]] 页的陷阱）。

[[CWG2605]] 收紧了聚合类：析构函数由用户提供的聚合类不再是隐式生存期类，因为销毁它要运行代码，违反了论文自己的第二个条件。

[[LWG4064]] 澄清了 `memcpy` 的返回值。原措辞只说 `memcpy` 在目标区域隐式创建对象，没说它的返回值指向谁，于是 `*static_cast<int*>(std::memcpy(buf, &x, 4))` 是否还需要 `std::launder` 有争议。修正后 [[cstring.syn#3]] 规定 `memcpy`、`memmove` 返回指向合适的已创建对象的指针。

## 为什么还需要 start_lifetime_as

库的那一半由 [[P2590R2]] 补进 C++23，就是 `std::start_lifetime_as<T>(p)` 和 `start_lifetime_as_array<T>(p, n)`（[[obj.lifetime#5]]）：在 `p` 处创建一个 `T` 对象，对象表示就是原有的字节，返回指向它的指针。P2590R2 给出了隐式创建覆盖不到的两类情形。

第一类是存储不来自标准规定的那几个函数。`mmap`、`VirtualAlloc` 可以由实现规定为隐式创建对象，但实际上通常没有这样的文档；用户自己写的内存池更是如此，复用发生在编译器看得见的 C++ 代码里。

第二类是字节已经在缓冲区里。这时问题不在于有没有对象，而在于手里的指针指向谁。[[P0593R6]] 第 3.7 节认为，`new char[N]` 隐式创建了合适的 `Foo`，因此 `reinterpret_cast<Foo*>(buffer.get())` 有定义；[[P2590R2]] 第 1.2 节对同一段代码的判断是 UB。按当前措辞，后者是对的：`char` 数组不再隐式创建对象（[[CWG2489]]），而且 `reinterpret_cast` 得到的指针仍然指向数组元素，不指向那个 `Foo`（[[expr.static.cast#12]]）。

<div class="compare" markdown="1">

```cpp ub
#include <cstring>
struct Header { int len, kind; };

int len(unsigned char* buf) {
  auto* h =
    reinterpret_cast<Header*>(buf);
  return h->len;  // 不指向 Header
}
```

```cpp ok
#include <cstring>
#include <new>
struct Header { int len, kind; };

int len(unsigned char* buf) {
  void* v = std::memmove(
    buf, buf, sizeof(Header));
  auto* h = std::launder(
    static_cast<Header*>(v));
  return h->len;
}
```

</div>

两段都假设 `buf` 已对齐、前 8 个字节是一个合法的 `Header` 表示。右边是 C++20 能写出的替代：`memmove` 把字节复制到临时区域，在目标处隐式创建对象，再复制回去，字节不变，对象有了。[[LWG4064]] 之后它的返回值本身就指向 `Header`，`launder` 不再必要，留着也无害。本机 Clang 23 `-O2` 把右边的 `memmove` 和 `launder` 全部消掉，函数只剩一条加载指令，和左边相同。

`start_lifetime_as` 给这个写法起了名字，并且不访问存储，对只读映射的内存也能用：

```cpp
struct Header { int len, kind; };

int len(const unsigned char* buf) {
  return std::start_lifetime_as<Header>(buf)->len;
}
```

截至写作时，本机 Clang 23 自带的 libc++ 还没有提供 `std::start_lifetime_as`（没有 `__cpp_lib_start_lifetime_as`），这段代码没有经过编译验证。`std::is_implicit_lifetime` 已经提供。它与 `launder` 的分工、数组版本的细节见 [[obj.lifetime]] 和 [[topics/type-punning]]。

## 能不能检查出来

隐式创建只决定一次执行有没有定义，在机器上不对应任何动作，所以动态工具很难检查。本机 Clang 23 的观察：

- `-fsanitize=address,undefined` 对 `reuse.cpp`、`no-pun.cpp`、`union-copy.cpp` 都不报告，前两个分别打印 `2` 和 `1`。
- `-fsanitize=type`（TypeSanitizer）报告了 `reuse.cpp` 里第二次写入和随后的读取，也报告了 `no-pun.cpp` 以 `float` 读取上次以 `int` 写入的存储。但它检查的是访问类型与上次写入类型是否相符，近似于优化器使用的别名规则，而不是 C++ 的对象模型：把 `reuse.cpp` 的第二次写入改成合法的 `::new (m) float(2.0f)`，它照样报告；上面左边那段缺少 `launder` 的读取，它不报告。

!!! impl
    实际的风险来自优化器而不是检查工具。TBAA 依据的是不同类型的对象不重叠；只要程序在复用存储时用 placement new、`memcpy` 或 `start_lifetime_as` 把新对象明确地创建出来，编译器就不会把旧类型的写入和新类型的读取当作互不相关。

## 思考题

!!! question "这段代码有定义吗？"
    ```cpp
    struct P { int x, y; };
    int f() {
      alignas(P) char buf[sizeof(P)];
      P* p = reinterpret_cast<P*>(buf);
      p->x = 1;
      return p->x;
    }
    ```

<details markdown="1">
<summary>答案</summary>

没有定义。`char` 数组开始生命周期时不会隐式创建对象（[[intro.object#16]]，[[CWG2489]] 之后只有 `unsigned char` 和 `std::byte`），`buf` 里没有 `P`。即使改成 `unsigned char`，`reinterpret_cast` 得到的指针仍然指向 `buf[0]`，需要 `std::launder` 才能指向隐式创建的 `P`。最简单的写法是 `P* p = ::new (buf) P;`，配合 `unsigned char` 或 `std::byte` 缓冲区。

</details>

!!! question "`malloc` 能同时让下面两种用法都有定义吗？"
    ```cpp
    void* m = std::malloc(sizeof(int));
    *static_cast<int*>(m) = 1;
    unsigned u = *static_cast<unsigned*>(m);
    ```

<details markdown="1">
<summary>答案</summary>

有定义。`malloc` 创建一个 `int`，第二行写入它。第三行通过 `unsigned` 左值读 `int` 对象，[[basic.lval#11]] 允许通过对应的无符号类型访问，读到的值是 1。这里不需要第二个对象，所以和 `reuse.cpp` 不同。

</details>

## 小结

| 问题 | 结论 | 出处 |
|---|---|---|
| 哪些操作隐式创建对象 | `malloc` 一族、`operator new`、`unsigned char`/`std::byte` 数组开始生命周期、`memcpy`/`memmove`、`bit_cast`、`start_lifetime_as` | [[intro.object#16]]、[[c.malloc#4]]、[[cstring.syn#3]]、[[obj.lifetime#5]] |
| 创建哪些对象 | 能让程序有定义的那一组；没有就是 UB | [[intro.object#13]] |
| 什么类型能被隐式创建 | 标量、数组、平凡构造加平凡析构的类、析构函数非用户提供的聚合类 | [[basic.types.general#7]]、[[class.prop#8]] |
| 类型双关合法了吗 | 没有，新对象的值不确定 | [[basic.life#5]] |
| 常量求值中 | 不发生 | [[intro.object#16]] |
| 进入标准的方式 | 语言部分是 C++20 的 DR，库部分是 C++23 的 [[P2590R2]] | |
