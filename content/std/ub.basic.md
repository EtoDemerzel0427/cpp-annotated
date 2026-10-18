---
title: 核心 UB 目录 · 第 [basic] 章
summary: Annex F.2 的 22 条：隐式对象创建、对齐、生命周期之外的指针与 glvalue、不确定值、分配函数契约、失效指针、无序修改、数据竞争、前进保证、静态对象析构顺序——逐条给出正文出处、改写后的例子与 Clang 23 实测。
status: draft
related: ub, basic.life, intro.object, basic.indet, intro.execution, intro.races, intro.progress, basic.start.term
tags: UB, 附录, 对象模型, 生命周期, sanitizer
updated: 2026-10-18
---

这一页是 [[ub]] 的第一部分，对应 Annex F.2，收录正文第 6 章 [basic] 以及第 4 章 [intro] 中执行模型相关小节（[[intro.object]]、[[intro.execution]]、[[intro.races]]、[[intro.progress]]）里的显式 UB。附录把这些都归在"Clause [basic]"名下，我们沿用它的编号与分组。

每个条目的格式：标题是附录给的 stable name（`[ub:…]`），随后是中文要点、**正文出处**（附录条目只是摘要，判定要落到正文段落上），一段改写过、能独立编译的例子，以及 Clang 23.1.3（arm64 macOS）上的实测。实测统一用：

```text
clang++ -std=c++2c -O0 -g -fsanitize=address,undefined x.cpp && ./a.out
```

"常量求值"指把同样的操作放进 `constexpr` 变量的初始化里，看编译器是否按 [[expr.const.core#2]] 的要求拒绝它。总说明与全表见 [[ub]]。

## 对象模型与对齐

### F.2.1 [ub:intro.object.implicit.create] {#intro.object.implicit.create}

**隐式创建无解** · 正文 [[intro.object#13]]

`malloc`、`memcpy`、`std::start_lifetime_as` 等操作会**隐式创建对象**（[[g:implicitly-create-objects]]）：标准允许实现"倒推"——只要存在一组隐式生命周期类型的对象，能让程序有定义，就当作这组对象被创建了。反过来，如果**无论怎么选都不能**让后续操作有定义，程序就是 UB。

```cpp ub
#include <cstdlib>

void f() {
  void* p = std::malloc(sizeof(int) + sizeof(float));
  *reinterpret_cast<int*>(p) = 0;
  *reinterpret_cast<float*>(p) = 0.0f;   // UB：同一位置不可能同时有一个 int 和一个 float 存活
  std::free(p);
}
```

注意这里的"无解"是对**整段后续执行**而言的：`malloc` 只创建一次对象。第一句写 `int` 要求那里有 `int`，第二句写 `float` 要求那里有 `float`，两者占用同一地址又都没有被重新创建（赋值不创建对象），所以找不到可行解。如果中间用 placement new 或 `std::start_lifetime_as<float>(p)` 显式换一个对象，就合法了。

**实测**：ASan/UBSan 无报告。这类 UB 完全是"对象模型层面"的，运行时没有任何可检测的痕迹，只在别名分析（TBAA）把两次写重排时才会显形。

### F.2.2 [ub:intro.object.implicit.pointer] {#intro.object.implicit.pointer}

**找不到合适的被创建对象** · 正文 [[intro.object#14]]

在隐式创建之后，有些操作（如 `malloc` 的返回值）还被规定为"产生指向**合适的被创建对象**的指针"。同样是倒推：若没有任何指针值能让程序有定义，则 UB。附录给了两种情况：类型根本不是隐式生命周期类型（例如析构函数被删除），或者指针随后被当作另一个不相似的类型使用。

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

**实测**：两段都没有任何 sanitizer 报告。第二段是典型的"标准说 UB、机器上看不出来"——A 和 B 布局完全相同。

### F.2.3 [ub:basic.align.object.alignment] {#basic.align.object.alignment}

**在未对齐的存储里创建对象** · 正文 [[basic.align#1]]

每个对象类型都有对齐要求；对象必须被创建在满足该对齐的地址上。placement new 是最容易违反它的地方，因为它对传入的地址一无所知。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

struct alignas(4) S { int v = 1; };

int main() {
  alignas(S) char s[sizeof(S) + 1];
  S* p = new (s + 1) S();   // UB：s + 1 与 4 字节对齐差 1
  return p->v;
}
```

**实测**：UBSan 的 `alignment` 检查命中：`runtime error: constructor call on misaligned address 0x…601 for type 'S *', which requires 4 byte alignment`。（附录原例写的是 `new (&s+1) S()`，`&s + 1` 是"整个数组之后"的地址，跨出了 `s` 的存储；这里改为 `s + 1`，表达的才是附录注释里说的"差 1 字节"。）

## 生命周期之外的指针（[basic.life] ¶7）

[[basic.life#7]] 描述的是这样一个窗口：存储已经分配但对象还没开始生命周期，或者对象生命周期已结束但存储尚未被复用或释放。这时指向那块存储的指针"可以用，但只能有限地用"——当 `void*` 用没问题，下面四种用法是 UB。

### F.2.4 [ub:lifetime.outside.pointer.delete] {#lifetime.outside.pointer.delete}

**对已结束生命周期的对象做 delete** · 正文 [[basic.life#7.1]]

对象将是或曾是**带非平凡析构函数**的类类型时，把这样的指针交给 *delete-expression* 是 UB。（析构函数平凡时这一款不适用；但 delete 还会再"析构"一次，对 trivially destructible 类型这是无操作的。）

```cpp ub
struct S {
  float f = 0;
  ~S() {}   // 非平凡
};

void f() {
  S* p = new S;
  p->~S();
  delete p;   // UB：生命周期已结束，且 S 有非平凡析构函数
}
```

**实测**：ASan/UBSan 无报告——内存只释放了一次，析构函数是空的，运行时什么也看不出。析构函数一旦释放资源，它就成了 double free。

### F.2.5 [ub:lifetime.outside.pointer.member] {#lifetime.outside.pointer.member}

**通过这种指针访问非静态成员或调用非静态成员函数** · 正文 [[basic.life#7.2]]

```cpp ub
struct S { float f = 0; };

float f() {
  S s;
  S* p = &s;
  s.~S();
  return p->f;   // UB：在生命周期结束后访问非静态数据成员
}
```

**实测**：运行时无报告（`s` 的栈内存还在）。**常量求值**下 Clang 拒绝：`read of object outside its lifetime is not allowed in a constant expression`。

### F.2.6 [ub:lifetime.outside.pointer.virtual] {#lifetime.outside.pointer.virtual}

**把这种指针转换为指向虚基类的指针** · 正文 [[basic.life#7.3]]

到非虚基类的转换只是加一个编译期已知的偏移；到**虚基类**的转换则要在运行时读对象里的 vptr/vbase offset——而对象已经不在了。所以前者允许、后者 UB。

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

**实测**：ASan/UBSan（含显式加上的 `-fsanitize=vptr`）均无报告。

### F.2.7 [ub:lifetime.outside.pointer.dynamic.cast] {#lifetime.outside.pointer.dynamic.cast}

**把这种指针作为 dynamic_cast 的操作数** · 正文 [[basic.life#7.4]]

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

**实测**：无报告。在本机 `-O0` 下 `dynamic_cast` 甚至返回了非空——析构过程中 vptr 被改写成什么样，完全取决于实现。

## 生命周期之外的 glvalue（[basic.life] ¶8）

[[basic.life#8]] 是 ¶7 的引用版：一个指代已死（或未生）对象的 glvalue，同样只能有限地使用。

### F.2.8 [ub:lifetime.outside.glvalue.access] {#lifetime.outside.glvalue.access}

**用这种 glvalue 访问对象** · 正文 [[basic.life#8.1]]

这里的"访问"是 [[defns.access]] 意义上的读或写对象的值。

```cpp ub
void f() {
  int x = int{10};
  using T = int;
  x.~T();      // 伪析构调用：从 C++20 起它会结束 x 的生命周期
  int y = x;   // UB：通过 glvalue 读取生命周期已结束的对象
}
```

**实测**：运行时无报告（读到的仍是 10）。**常量求值**下被拒：`read of object outside its lifetime is not allowed in a constant expression`。这条例子同时提醒：伪析构调用（*pseudo-destructor call*）不再是无操作——C++20 起它对标量也会结束生命周期，见 [[expr.prim.id.dtor]]。

### F.2.9 [ub:lifetime.outside.glvalue.member] {#lifetime.outside.glvalue.member}

**用这种 glvalue 调用非静态成员函数** · 正文 [[basic.life#8.2]]

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

**实测**：无报告。

### F.2.10 [ub:lifetime.outside.glvalue.virtual] {#lifetime.outside.glvalue.virtual}

**把这种 glvalue 绑定到虚基类的引用** · 正文 [[basic.life#8.3]]

与 F.2.6 同理：绑定到虚基类引用需要运行时查虚基类偏移。

```cpp ub
struct B {};
struct D : virtual B {};

void f() {
  D d;
  d.~D();
  B& b = d;   // UB
}
```

**实测**：无报告。

### F.2.11 [ub:lifetime.outside.glvalue.dynamic.cast] {#lifetime.outside.glvalue.dynamic.cast}

**把这种 glvalue 用作 dynamic_cast 或 typeid 的操作数** · 正文 [[basic.life#8.4]]

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

**实测**：无报告。

## 替换存储里的对象

### F.2.12 [ub:original.type.implicit.destructor] {#original.type.implicit.destructor}

**隐式析构时，那块存储里已不是原类型的对象** · 正文 [[basic.life#11]]

自动、静态、线程存储期的对象，在作用域结束（或程序/线程结束）时会被**隐式**调用析构函数。如果此前你用 placement new 在它的存储里放了别的类型的对象，而原类型的析构函数又是非平凡的，那次隐式析构就是 UB。即使是因异常离开作用域也一样。

```cpp ub
#include <new>

struct T {};
struct B { ~B(); };

void h() {
  B b;
  new (&b) T;   // b 的存储被一个 T 复用，b 的生命周期结束
}               // UB：此处隐式调用 B::~B()，但存储里是 T
```

**实测**：无报告；`~B()` 照常在那块内存上执行。修复办法是在作用域结束前再 `new (&b) B` 放回一个 B。

### F.2.13 [ub:creating.within.const.complete.obj] {#creating.within.const.complete.obj}

**在 const 完整对象的存储里创建新对象** · 正文 [[basic.life#12]]

对静态、线程、自动存储期的 **const 完整对象**，在它占据（或曾占据）的存储里创建新对象是 UB。理由是编译器可以把 const 对象放进只读段，或者把它的值当常量传播。动态分配的 const 对象不在此列（那是 F.5.1 的修改问题）。

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

**实测**：未运行（例子依赖外部定义）。同类问题见 F.5.1：本机把 `const int g = 3;` 通过 `const_cast` 写入，ASan 直接报 `BUS on unknown address`——`g` 被放进了只读页。

## 值与指针

### F.2.14 [ub:basic.indet.value] {#basic.indet.value}

**求值产生不确定值** · 正文 [[basic.indet#2]]

C++26 把"未初始化的自动变量"一分为二（[[P2795]]）：默认情况下它持有**错误值**（*erroneous value*），读取它是**错误行为**（EB，有定义但"是错的"）；只有用 `[[indeterminate]]` 显式选择退出时，它才持有**不确定值**，读取它才是 UB。附录强调"不确定值（而不只是错误值）"正是这个区别。`unsigned char`/`std::byte` 有若干例外（¶2.1–¶2.3）。

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

**实测**：Clang 23 尚未实现 `[[indeterminate]]`（`warning: unknown attribute 'indeterminate' ignored`）；在 `-O0` 下两种写法表现相同，都读出了栈上的残留值。ASan/UBSan 不检查未初始化读取（那是 MSan 的工作，而 MSan 不支持 macOS）。**常量求值**下两者都被拒：`read of uninitialized object is not allowed in a constant expression`——[[expr.const.core#2.8]] 同时排除了 UB 和 EB。

### F.2.15 [ub:basic.stc.alloc.dealloc.constraint] {#basic.stc.alloc.dealloc.constraint}

**分配/释放函数不满足语义约束** · 正文 [[basic.stc.dynamic.general#3]]

用户可以替换全局 `operator new`/`operator delete`，但替换品必须满足 [[basic.stc.dynamic.allocation]] 与 [[basic.stc.dynamic.deallocation]] 的契约：成功时返回至少 `size` 字节、适当对齐的非空指针；`operator delete` 不得以异常退出……违反契约则整个程序 UB——标准库和编译器都依赖这些契约。

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

**实测**：ASan 报 `heap-buffer-overflow`——不是因为它理解了契约，而是越界写正好落在它的红区上。附录的另外两种违例（`sz == 0` 时返回 `nullptr`、`operator delete` 抛异常）运行时都没有专门检查。

### F.2.16 [ub:basic.stc.alloc.zero.dereference] {#basic.stc.alloc.zero.dereference}

**解引用零字节分配返回的指针** · 正文 [[basic.stc.dynamic.allocation#2]]

`operator new(0)` 必须返回一个非空、彼此不同的指针，但这个指针**不能解引用**——那里没有可用的字节。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <new>

int main() {
  char* c = static_cast<char*>(::operator new(0));
  c[0] = 'X';   // UB
  ::operator delete(c);
}
```

**实测**：ASan 报 `heap-buffer-overflow`（它把零字节分配也包上红区）。附录原例用了 `0z` 字面量（[[lex.icon]] 的 `z` 后缀，C++23 起）。

### F.2.17 [ub:basic.compound.invalid.pointer] {#basic.compound.invalid.pointer}

**用失效指针做间接或释放** · 正文 [[basic.compound#6.1]]

存储被释放后，指向它的指针值变成**在当前求值中无效**（[[g:valid-in-the-context-of]]）。对它做间接（`*p`、`p->`）或再交给释放函数是 UB；而做相等比较、`+`、转 `bool` 等是**实现定义**的（¶6.2）——这一点常被误记为"use-after-free 的指针碰都不能碰"。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
int main() {
  int* x = new int{5};
  delete x;
  int y = *x;   // UB：间接访问已释放的存储
  delete x;     // UB：double free
  return y;
}
```

**实测**：ASan 在第一处就停下：`heap-use-after-free`。**常量求值**下 Clang 分别给出 `read of heap allocated object that has been deleted` 与 `delete of pointer that has already been deleted`。

## 执行与并发

### F.2.18 [ub:intro.execution.unsequenced.modification] {#intro.execution.unsequenced.modification}

**无序的副作用** · 正文 [[intro.execution#10]]

对同一内存位置的一个副作用，若与另一个副作用、或与对同一位置值的计算**无序**（*unsequenced*），且两者并非潜在并发，则 UB。C++17 给 `=`、`<<`、`[]`、函数调用等补上了大量顺序规则，所以 `i = i++ + 1` 如今是有定义的，但 `+` 的两个操作数之间仍然无序。

```cpp ub
void g(int i) {
  i = 7, i++, i++;   // OK：逗号运算符有序，i 变为 9
  i = i++ + 1;       // OK（C++17 起）：右操作数先于赋值
  i = i++ + i;       // UB：i++ 的副作用与右侧 i 的值计算无序
  i = i + 1;         // OK
}
```

**实测**：`-Wall` 下 Clang 给出 `warning: unsequenced modification and access to 'i' [-Wunsequenced]`；运行时 sanitizer 不检查。值得注意的是**常量求值**：按 [[expr.const.core#2.8]]，`constexpr int f(int i) { i = i++ + i; return i; }` 的调用不应是常量表达式，但 Clang 23 只发了上面那条警告就把 `f(1)` 当常量算了出来——这是实现的缺口，不能把"constexpr 能过"当作"没有 UB"的证明。

### F.2.19 [ub:intro.races.data] {#intro.races.data}

**数据竞争** · 正文 [[intro.races#17]]

两个**潜在并发**的冲突动作（至少一个是写），至少一个不是原子的，且互不 *happens before*，构成数据竞争（[[g:data-race]]），整个程序 UB。信号处理函数有专门的例外。

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

**实测**：TSan（`-fsanitize=thread`，不能与 ASan 同时用）报 `WARNING: ThreadSanitizer: data race`；程序打印的数小于 300000（本次是 106896）。

### F.2.20 [ub:intro.progress.stops] {#intro.progress.stops}

**线程不再前进** · 正文 [[intro.progress#1]]

实现可以假定每个线程最终会做以下之一：终止、调用 `yield`、做库 I/O、volatile 访问、原子/同步操作，或执行一个**平凡无限循环**（[[g:trivial-infinite-loop]]，C++26 起的豁免）。一个既不终止、又不做任何这些事的线程让程序 UB。这条规则的目的是允许编译器删除"证明不了会终止"的空循环。

```cpp ub
bool stop() { return false; }

void busy() {
  while (!stop());   // UB：没有可观察的进展；条件不是常量表达式，所以不是"平凡无限循环"
}

void spin() {
  while (true);      // OK（C++26）：平凡无限循环，不能被删除
}
```

**实测**（`-O2 -S`）：Clang 把 `busy` 整个编译成一条 `brk #0x1` 陷阱指令——它判定这条执行路径必然 UB，于是不生成循环；而 `spin` 被编译成一条跳回自身的 `b` 指令，是真正的死循环。这就是 [[stmt.iter.general]] 中"平凡无限循环"豁免的实际效果。

## 程序终止

### F.2.21 [ub:basic.start.main.exit.during.destruction] {#basic.start.main.exit.during.destruction}

**在静态/线程存储期对象析构期间调用 std::exit** · 正文 [[basic.start.main#4]]

`std::exit` 会开始销毁静态对象；如果当时已经在这个销毁过程里，就形成重入。

```cpp ub
#include <cstdlib>

struct Exiter {
  ~Exiter() { std::exit(0); }
};

Exiter ex;

int main() {}
// UB：main 返回后析构 ex，其析构函数又调用 std::exit
```

**实测**：无报告，本机上程序打印析构函数里的输出后以 0 退出。这只是一次观察结果，标准对此不作任何保证。

### F.2.22 [ub:basic.start.term.use.after.destruction] {#basic.start.term.use.after.destruction}

**使用已销毁的块作用域静态变量** · 正文 [[basic.start.term#5]]

静态对象按构造完成的**逆序**销毁。如果一个函数里的块作用域静态变量已经被销毁，而某个更晚销毁的静态对象的析构函数又调用了这个函数、控制流经过那个变量的定义，就是 UB（变量不会被"重新初始化"）。通过指针间接使用已销毁的块变量同样是 UB（这一句在正文里是注）。

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

**实测**：先打印 `~A`，再打印 `f() = -1`——`a` 已经被析构，`f()` 读到了析构函数写进去的"墓碑值"；ASan/UBSan 无报告（`a` 的存储是静态的，从未被释放）。这就是常说的"静态析构顺序灾难"（*static destruction order fiasco*）。
