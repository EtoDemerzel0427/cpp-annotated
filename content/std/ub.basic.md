---
title: 核心 UB 目录 · 第 [basic] 章
summary: Annex F.2 的 22 条未定义行为：隐式对象创建、对齐、生命周期之外的指针与 glvalue、不确定值、分配函数的约定、失效指针、无序修改、数据竞争、前进保证和静态对象的析构顺序，每条给出正文出处、可编译的例子和 Clang 23 实测。
status: done
papers: P2795R5
related: ub, basic.life, intro.object, basic.indet, intro.execution, intro.races, intro.progress, basic.start.term
tags: UB, 附录, 对象模型, 生命周期, sanitizer
updated: 2026-10-19
---

!!! tldr
    - 生命周期之外的指针只能当作 `void*` 用。经由它访问成员、`delete`、转换到虚基类或做 `dynamic_cast` 都是 UB，而且运行时几乎检测不到。
    - C++26 起，读取未初始化的自动变量通常是错误行为（结果确定），只有用 `[[indeterminate]]` 显式选择不初始化时，读取才是 UB。
    - 释放后的指针不是完全不能碰：对它做间接是 UB，拿它比较、做加减或转换为 `bool` 是实现定义的。
    - `i = i++ + i` 仍是 UB，`i = i++ + 1` 自 C++17 起有定义；数据竞争会让整个程序 UB。
    - 不做任何可观察操作的循环可以被编译器假定会终止，`while (true);` 这样的平凡无限循环在 C++26 中例外。

本页是 [[ub]] 的第一部分，对应 Annex F.2。附录把第 6 章 [basic] 和第 4 章中执行模型相关小节（[[intro.object]]、[[intro.execution]]、[[intro.races]]、[[intro.progress]]）里的显式 UB 都归在 Clause [basic] 名下，本页沿用它的编号和分组。

每个条目的标题下先给出附录的 stable name 和正文出处。附录条目只是摘要，判定要落到正文段落上。例子改写成了能独立编译的形式，实测环境是 Clang 23.1.3（arm64 macOS），运行时检测统一用下面的命令：

```text
clang++ -std=c++2c -O0 -g -fsanitize=address,undefined x.cpp && ./a.out
```

常量求值指把同样的操作放进 `constexpr` 变量的初始化，看编译器是否按 [[expr.const.core#2]] 的要求拒绝它。

## 对象模型与对齐

### F.2.1 隐式创建对象无解 {#intro.object.implicit.create}

`[ub:intro.object.implicit.create]` · 正文 [[intro.object#13]]

```cpp ub
#include <cstdlib>

void f() {
  void* p = std::malloc(sizeof(int) + sizeof(float));
  *reinterpret_cast<int*>(p) = 0;
  *reinterpret_cast<float*>(p) = 0.0f;   // UB：同一位置不可能同时有一个 int 和一个 float 存活
  std::free(p);
}
```

`malloc`、`memcpy`、`std::start_lifetime_as` 等操作会**隐式创建对象**（[[g:implicitly-create-objects]]）。标准不指定创建了哪些对象，而是倒推：只要存在一组隐式生命周期类型的对象能让程序有定义，就当作创建了这组对象。如果无论怎么选都不能让后续操作有定义，程序就是 UB。

上例中 `malloc` 只创建一次对象。第一次写入要求那里有一个 `int`，第二次写入要求同一地址有一个 `float`，而赋值不会创建新对象，所以找不到可行的一组对象。在两次写入之间用 placement new 或 `std::start_lifetime_as<float>(p)` 显式换一个对象，程序就合法了。

本机实测，ASan 和 UBSan 都没有报告。这类 UB 只存在于对象模型层面，运行时没有痕迹，只有当基于类型的别名分析把两次写入重排时才会显现。

### F.2.2 找不到合适的被创建对象 {#intro.object.implicit.pointer}

`[ub:intro.object.implicit.pointer]` · 正文 [[intro.object#14]]

```cpp ub
#include <cstdlib>

struct X {
  int a, b;
  ~X() = delete;   // 被删除的析构函数：X 不是隐式生命周期类
};

X* make_x() {
  X* p = (X*)std::malloc(sizeof(X));   // 无法隐式创建 X
  p->a = 1;                            // UB：没有任何一组对象能让这句有定义
  return p;
}

struct A { int a; };
struct B { int x; };

B* make_b() {
  A* p1 = (A*)std::malloc(sizeof(A));  // 隐式创建了 A（第一次使用决定了"解"）
  p1->a = 1;
  B* p2 = (B*)p1;
  p2->x = 2;   // UB：p2 指向一个活着的 A，A 与 B 不相似（见 [expr.ref]）
  return p2;
}
```

`malloc` 这类操作还被规定为返回指向合适的被创建对象的指针。这同样是倒推：如果没有任何指针值能让程序有定义，就是 UB。附录给了两种情况：类型根本不是隐式生命周期类型，比如析构函数被删除；或者指针随后被当作另一个不相似的类型使用。

本机实测，两段都没有 sanitizer 报告。第二段中 `A` 和 `B` 的布局完全相同，机器上看不出任何问题，但标准说它是 UB。

### F.2.3 在未对齐的存储里创建对象 {#basic.align.object.alignment}

`[ub:basic.align.object.alignment]` · 正文 [[basic.align#1]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

struct alignas(4) S { int v = 1; };

int main() {
  alignas(S) char s[sizeof(S) + 1];
  S* p = new (s + 1) S();   // UB：s + 1 与 4 字节对齐差 1
  return p->v;
}
```

每个对象类型都有对齐要求，对象必须创建在满足这个要求的地址上。placement new 对传入的地址一无所知，是最容易违反这条规则的地方。

UBSan 的 alignment 检查报告 `constructor call on misaligned address ... which requires 4 byte alignment`。附录原例写的是 `new (&s+1) S()`。`&s + 1` 指向整个数组之后，越出了 `s` 的存储，与注释所说的差 1 字节不符，所以这里改成了 `s + 1`。

## 生命周期之外的指针

[[basic.life#7]] 描述了这样一段时间：存储已经分配，但对象的生命周期还没有开始；或者对象的生命周期已经结束，但存储还没有被复用或释放。这段时间里，指向这块存储的指针可以当作 `void*` 使用，下面四种用法是 UB。

### F.2.4 对生命周期之外的对象做 delete {#lifetime.outside.pointer.delete}

`[ub:lifetime.outside.pointer.delete]` · 正文 [[basic.life#7.1]]

```cpp ub
struct S {
  float f = 0;
  ~S() {}   // 非平凡
};

void f() {
  S* p = new S;
  p->~S();
  delete p;   // UB：S 的生命周期已结束
}
```

把这样的指针交给 *delete-expression* 是 UB。附录的摘要只针对带非平凡析构函数的类类型，那是旧的措辞；当前正文 ¶7.1 已经没有这个限定，不论析构函数是否平凡都是 UB。

本机实测，ASan 和 UBSan 都没有报告：内存只释放了一次，析构函数是空的。析构函数一旦释放资源，这里就成了重复释放。

### F.2.5 经由它访问成员 {#lifetime.outside.pointer.member}

`[ub:lifetime.outside.pointer.member]` · 正文 [[basic.life#7.2]]

```cpp ub
struct S { float f = 0; };

float f() {
  S s;
  S* p = &s;
  s.~S();
  return p->f;   // UB：在生命周期结束后访问非静态数据成员
}
```

经由这样的指针访问非静态数据成员或调用非静态成员函数是 UB。运行时没有报告，`s` 的栈内存还在。常量求值中 Clang 拒绝它：`read of object outside its lifetime is not allowed in a constant expression`。

### F.2.6 把它转换为虚基类指针 {#lifetime.outside.pointer.virtual}

`[ub:lifetime.outside.pointer.virtual]` · 正文 [[basic.life#7.3]]

```cpp ub
struct B {};
struct D : virtual B {};

void f() {
  D d;
  D* p = &d;
  d.~D();
  B* b = p;   // UB：转换到虚基类需要读取已死对象的虚基类偏移
}
```

转换到非虚基类只是加上一个编译期已知的偏移。转换到虚基类则要在运行时从对象中读取虚基类的偏移，而对象已经不在了。所以前者允许，后者是 UB。本机实测，ASan、UBSan 和显式加上的 `-fsanitize=vptr` 都没有报告。

### F.2.7 把它用作 dynamic_cast 的操作数 {#lifetime.outside.pointer.dynamic.cast}

`[ub:lifetime.outside.pointer.dynamic.cast]` · 正文 [[basic.life#7.4]]

```cpp ub
struct B { virtual ~B() = default; };
struct D : B {};

void f() {
  D d;
  B* bp = &d;
  d.~D();
  D* dp = dynamic_cast<D*>(bp);   // UB
}
```

`dynamic_cast` 要读取对象的动态类型信息。本机实测没有报告，`-O0` 下 `dynamic_cast` 甚至返回了非空指针：析构之后对象的虚表指针变成什么样，完全取决于实现。

## 生命周期之外的 glvalue

[[basic.life#8]] 是第 7 段的引用版本。**glvalue** 是指代一个对象或函数的表达式，例如变量名和引用。指代生命周期之外的对象的 glvalue，同样只能有限地使用。

### F.2.8 经由它访问对象 {#lifetime.outside.glvalue.access}

`[ub:lifetime.outside.glvalue.access]` · 正文 [[basic.life#8.1]]

```cpp ub
void f() {
  int x = int{10};
  using T = int;
  x.~T();      // 伪析构调用：从 C++20 起它会结束 x 的生命周期
  int y = x;   // UB：通过 glvalue 读取生命周期已结束的对象
}
```

这里的访问指读或写对象的值（[[defns.access]]）。运行时没有报告，读到的仍是 10；常量求值中 Clang 拒绝它，诊断同 F.2.5。

这个例子还说明，对标量类型的**伪析构调用**（pseudo-destructor call）不是空操作，它会结束对象的生命周期，见 [[expr.prim.id.dtor]]。

### F.2.9 经由它调用成员函数 {#lifetime.outside.glvalue.member}

`[ub:lifetime.outside.glvalue.member]` · 正文 [[basic.life#8.2]]

```cpp ub
struct A {
  void f() {}
};

void g() {
  A a;
  a.~A();
  a.f();   // UB：生命周期结束后调用非静态成员函数，即使 f 什么也不做
}
```

即使成员函数什么也不做，调用本身就是 UB。本机实测没有报告。

### F.2.10 把它绑定到虚基类的引用 {#lifetime.outside.glvalue.virtual}

`[ub:lifetime.outside.glvalue.virtual]` · 正文 [[basic.life#8.3]]

```cpp ub
struct B {};
struct D : virtual B {};

void f() {
  D d;
  d.~D();
  B& b = d;   // UB
}
```

理由与 F.2.6 相同：绑定到虚基类的引用需要在运行时读取虚基类偏移。本机实测没有报告。

### F.2.11 把它用作 dynamic_cast 或 typeid 的操作数 {#lifetime.outside.glvalue.dynamic.cast}

`[ub:lifetime.outside.glvalue.dynamic.cast]` · 正文 [[basic.life#8.4]]

```cpp ub
struct B { virtual ~B() = default; };
struct D : virtual B {};

void f() {
  D d;
  B& br = d;
  d.~D();
  D& dr = dynamic_cast<D&>(br);   // UB
}
```

本机实测没有报告。

## 复用对象的存储

### F.2.12 隐式析构时存储里已是别的类型 {#original.type.implicit.destructor}

`[ub:original.type.implicit.destructor]` · 正文 [[basic.life#11]]

```cpp ub
#include <new>

struct T {};
struct B { ~B(); };

void h() {
  B b;
  new (&b) T;   // b 的存储被一个 T 复用，b 的生命周期结束
}               // UB：此处隐式调用 B::~B()，但存储里是 T
```

自动、静态和线程存储期的对象在作用域结束时，或者在程序、线程结束时，会被隐式地调用析构函数。如果在这之前用 placement new 在它的存储里放了别的类型的对象，而原类型的析构函数是非平凡的，这次隐式析构就是 UB。因异常离开作用域时也一样。

本机实测没有报告，`~B()` 照常在那块内存上执行。修正的办法是在作用域结束前用 `new (&b) B` 放回一个 `B`。

### F.2.13 在 const 完整对象的存储里创建对象 {#creating.within.const.complete.obj}

`[ub:creating.within.const.complete.obj]` · 正文 [[basic.life#12]]

```cpp ub
#include <new>

struct B {
  B();
  ~B();
};

const B b;

void h() {
  b.~B();
  new (const_cast<B*>(&b)) const B;   // UB：在 const 完整对象的存储里重建对象
}
```

对静态、线程或自动存储期的 const 完整对象，在它占据或曾经占据的存储里创建新对象是 UB。编译器可以把这样的 const 对象放进只读段，或者把它的值当作常量传播。动态分配的 const 对象不受这一条约束，修改它们的问题见 [[ub.dcl#dcl.type.cv.modify.const.obj|F.5.1]]。

这个例子依赖外部定义，没有运行。相关的实测见 F.5.1：通过 `const_cast` 写入 `const int g = 3;`，ASan 报告 `BUS on unknown address`，因为 `g` 被放进了只读页。

## 值与指针

### F.2.14 求值产生不确定值 {#basic.indet.value}

`[ub:basic.indet.value]` · 正文 [[basic.indet#2]]

```cpp ub
void g() {
  int x [[indeterminate]];
  int y = x;   // UB：产生了不确定值
}

void h() {
  int x;       // C++26：x 持有错误值
  int y = x;   // 错误行为（EB），不是 UB
}
```

C++26 把未初始化的自动变量分成两种（[[P2795R5]]）。默认情况下，它持有一个**错误值**（erroneous value），读取它是错误行为：结果确定，但标准认定它是错误。用 `[[indeterminate]]` 显式选择不初始化时，它持有**不确定值**，读取才是 UB。附录特别写明不确定值而不只是错误值，指的就是这个区别。`unsigned char` 和 `std::byte` 另有几条例外（¶2.1–¶2.3）。

Clang 23 尚未实现 `[[indeterminate]]`，给出 `unknown attribute 'indeterminate' ignored` 警告；`-O0` 下两个函数的表现相同，都读出栈上的残留值。ASan 和 UBSan 不检查未初始化读取，那是 MSan 的工作，而 MSan 不支持 macOS。常量求值中两者都被拒绝（`read of uninitialized object is not allowed in a constant expression`），因为 [[expr.const.core#2.8]] 同时排除了 UB 和 EB。

### F.2.15 分配或释放函数违反约定 {#basic.stc.alloc.dealloc.constraint}

`[ub:basic.stc.alloc.dealloc.constraint]` · 正文 [[basic.stc.dynamic.general#3]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>
#include <cstdlib>

void* operator new(std::size_t sz) {
  return std::malloc(1);   // UB：返回的存储小于请求的大小
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  long* p = new long(1);   // 构造时就写越界了
  delete p;
}
```

程序可以替换全局的 `operator new` 和 `operator delete`，但替换函数必须遵守 [[basic.stc.dynamic.allocation]] 和 [[basic.stc.dynamic.deallocation]] 的约定，例如成功时返回至少 `size` 字节、适当对齐的非空指针。违反约定时整个程序是 UB，因为标准库和编译器都依赖这些约定。

ASan 报告 `heap-buffer-overflow`。它并不理解约定，只是越界写入正好落在了它设置的保护区上。附录列出的另外两种违例，即请求 0 字节时返回空指针和 `operator delete` 抛出异常，运行时都没有专门的检查。

### F.2.16 解引用零字节分配的结果 {#basic.stc.alloc.zero.dereference}

`[ub:basic.stc.alloc.zero.dereference]` · 正文 [[basic.stc.dynamic.allocation#2]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

int main() {
  char* c = static_cast<char*>(::operator new(0));
  c[0] = 'X';   // UB
  ::operator delete(c);
}
```

`operator new(0)` 必须返回一个非空的、与其他分配都不同的指针，但这个指针不能解引用，那里没有可用的字节。ASan 报告 `heap-buffer-overflow`，零字节的分配也有它的保护区。

### F.2.17 间接访问失效的指针 {#basic.compound.invalid.pointer}

`[ub:basic.compound.invalid.pointer]` · 正文 [[basic.compound#6.1]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
int main() {
  int* x = new int{5};
  delete x;
  int y = *x;   // UB：间接访问已释放的存储
  delete x;     // UB：double free
  return y;
}
```

存储被释放后，指向它的指针值在之后的求值中都是无效的（[[g:valid-in-the-context-of]]）。第 6.1 段规定，对无效指针做间接（`*p`、`p->m`）是 UB；第 6.2 段规定，把它转换为 `bool`、用于加减法或比较是实现定义的。常有人以为释放后的指针碰都不能碰，那并不准确。

附录的摘要把调用释放函数也列在这一条下，那是旧的措辞，正文这一段已经不再提释放。例子中的重复 `delete` 仍然是 UB，依据是 `operator delete` 的前置条件（[[new.delete.single]]）：传入的指针不能已被先前的释放调用作废。

ASan 在第一处就停下，报告 `heap-use-after-free`。常量求值中 Clang 分别给出 `read of heap allocated object that has been deleted` 和 `delete of pointer that has already been deleted`。

## 执行与并发

### F.2.18 无序的副作用 {#intro.execution.unsequenced.modification}

`[ub:intro.execution.unsequenced.modification]` · 正文 [[intro.execution#10]]

```cpp ub
void g(int i) {
  i = 7, i++, i++;   // OK：逗号运算符有序，i 变为 9
  i = i++ + 1;       // OK（C++17 起）：右操作数先于赋值
  i = i++ + i;       // UB：i++ 的副作用与右侧 i 的值计算无序
  i = i + 1;         // OK
}
```

如果对一个内存位置的副作用，与对同一位置的另一个副作用或值计算之间**无序**（unsequenced，两者之间没有任何先后规定），并且两者不是潜在并发的，行为就是未定义的。C++17 给赋值、`<<`、下标、函数调用等补充了求值顺序，所以 `i = i++ + 1` 如今有定义；但 `+` 的两个操作数之间仍然无序。

`-Wall` 下 Clang 给出 `unsequenced modification and access to 'i'` 警告（`-Wunsequenced`），运行时 sanitizer 不检查这一类。按 [[expr.const.core#2.8]]，`constexpr int f(int i) { i = i++ + i; return i; }` 的调用不应是常量表达式，但 Clang 23 只发出上面那条警告，就把 `f(1)` 当作常量算了出来。这是实现的遗漏。

### F.2.19 数据竞争 {#intro.races.data}

`[ub:intro.races.data]` · 正文 [[intro.races#17]]

```cpp ub run flags="-std=c++2c -O1 -g -fsanitize=thread" cc=clang_trunk
#include <thread>
#include <cstdio>

int count = 0;

int main() {
  auto f = [] { for (int i = 0; i < 100000; ++i) count++; };
  std::thread t1{f}, t2{f}, t3{f};   // UB：三个线程对 count 的非原子读改写互相竞争
  t1.join(); t2.join(); t3.join();
  std::printf("%d\n", count);
}
```

两个潜在并发的动作访问同一内存位置，至少一个是写，至少一个不是原子操作，并且谁也不先发生于（happens before）另一个，就构成**数据竞争**（[[g:data-race]]），整个程序是 UB。信号处理函数有专门的例外。

TSan（`-fsanitize=thread`，不能和 ASan 同时使用）报告 `WARNING: ThreadSanitizer: data race`，程序打印的数小于 300000。

### F.2.20 线程不再前进 {#intro.progress.stops}

`[ub:intro.progress.stops]` · 正文 [[intro.progress#1]]

```cpp ub
bool stop() { return false; }

void busy() {
  while (!stop());   // UB：没有可观察的进展；条件不是常量表达式，所以不是"平凡无限循环"
}

void spin() {
  while (true);      // OK（C++26）：平凡无限循环，不能被删除
}
```

实现可以假定每个线程最终会做下列事情之一：终止、调用 `std::this_thread::yield`、调用库的 I/O 函数、执行 volatile 访问、执行原子或同步操作，或者执行一个**平凡无限循环**（[[g:trivial-infinite-loop]]，C++26 新增的例外，大致是条件为常量表达式 `true` 的空循环）。一个线程如果既不终止，又不做其中任何一件事，程序就是 UB。这条规则允许编译器删除无法证明会终止的空循环。

用 `-O2 -S` 查看汇编，Clang 把 `busy` 整个编译成一条陷阱指令 `brk #0x1`：它判定这条执行路径必然导致 UB，于是不生成循环。`spin` 则被编译成跳回自身的 `b` 指令，是真正的死循环。这就是 [[stmt.iter.general]] 中平凡无限循环例外的实际效果。

## 程序终止

### F.2.21 静态对象析构期间调用 std::exit {#basic.start.main.exit.during.destruction}

`[ub:basic.start.main.exit.during.destruction]` · 正文 [[basic.start.main#4]]

```cpp ub
#include <cstdlib>

struct Exiter {
  ~Exiter() { std::exit(0); }
};

Exiter ex;

int main() {}
// UB：main 返回后析构 ex，其析构函数又调用 std::exit
```

`std::exit` 会开始销毁静态存储期和线程存储期的对象。如果调用时已经处在这个销毁过程中，就形成了重入。本机实测没有报告，程序以 0 退出；这只是一次观察结果，标准对此不作任何保证。

### F.2.22 使用已销毁的块作用域静态变量 {#basic.start.term.use.after.destruction}

`[ub:basic.start.term.use.after.destruction]` · 正文 [[basic.start.term#5]]

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

struct A {
  int v = 42;
  ~A() { v = -1; std::puts("~A"); }
};
int f() { static A a; return a.v; }

struct B { B() { f(); } };                          // 在 b 的构造中首次初始化 a
struct C { ~C() { std::printf("f() = %d\n", f()); } };

C c;
B b;   // a 在 b 的构造过程中完成构造，所以比 c 晚构造、比 c 早销毁

int main() {}
// 析构顺序：b、a、c。~C 调用 f()，控制流经过已销毁的 a 的定义：UB
```

静态对象按构造完成的逆序销毁。一个函数中的块作用域静态变量已经被销毁之后，如果某个更晚销毁的静态对象的析构函数调用了这个函数，并且控制流经过那个变量的定义，就是 UB。变量不会被重新初始化。注 2 补充，在销毁之后经由指针等方式间接使用这个变量，同样是 UB。

程序先打印 `~A`，再打印 `f() = -1`：`a` 已经析构，`f()` 读到的是析构函数写入的值。ASan 和 UBSan 都没有报告，因为 `a` 的存储是静态的，从未被释放。这就是常说的静态析构顺序问题（static destruction order fiasco）。
