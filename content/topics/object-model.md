---
title: C++ 对象模型：存储、对象、生命周期、指针值
summary: 把抽象机里的存储、对象、生命周期和指针值分开看，并据此判断一块内存上有没有对象、手里的指针指不指向它、什么时候需要 std::launder。
status: draft
order: 12
since: c++98
papers: P0593R6, P0137R1, P2590R2
related: intro.object, intro.memory, basic.stc, basic.life, basic.compound, basic.lval, basic.indet, basic.types.trivial, ptr.launder, obj.lifetime, expr.add, expr.eq, expr.reinterpret.cast, topics/type-punning, topics/dangling-references, topics/undefined-behavior
tags: 对象模型, 生命周期, 指针, launder, 专题
updated: 2026-10-19
---

!!! tldr
    - 存储、对象、生命周期、指针值是四件不同的事：有内存不等于有对象，有对象不等于它活着，地址相同也不等于指针指向它。
    - 对象只有五种来源；类型转换、写入一个值、`std::launder` 都不创建对象。C++20 起 `malloc`、`memcpy` 等操作会隐式创建对象，这让 C 风格的代码有了定义。
    - 指针值记得自己指向哪个对象：尾后指针不指向相邻的对象，指针算术不能走出自己的数组，`reinterpret_cast` 只有在两个对象指针可互转时才改变指向。
    - `std::launder` 不创建对象，只把一个地址正确、但指向旧对象的指针换成指向新对象的指针。最省事的替代办法是保存 placement new 的返回值。

## 同一个地址，两种结论

<div class="compare" markdown="1">

```cpp run ok
#include <new>
int a() {
  alignas(int) unsigned char
    buf[sizeof(int)];
  int* p = new (buf) int(42);
  return *p;      // OK
}
```

```cpp run ub
#include <new>
int b() {
  alignas(int) unsigned char
    buf[sizeof(int)];
  new (buf) int(42);
  return *reinterpret_cast<int*>(buf);
  // UB：指针仍指向 buf[0]
}
```

</div>

两个函数在同一个地址上放了同一个 `int`，本机 Clang 23 `-O2` 也把它们编译成完全相同的代码：直接返回 42。但标准认为左边合法、右边是未定义行为。

差别在于指针指向谁。左边的 `p` 是 placement new 返回的，指向新建的 `int`。右边的指针由 `buf` 转换而来，按规则仍然指向数组元素 `buf[0]`，于是是在通过 `int` 类型的左值读一个 `unsigned char` 对象。要讲清楚这一点，需要把 C++ 抽象机里的四层东西分开：

| 层 | 是什么 | 规定在 |
|---|---|---|
| 存储 | 字节，以及一段存储从获得到释放的存续期 | [[intro.memory]]、[[basic.stc]] |
| 对象 | 占据一块存储、类型在创建时就确定的实体 | [[intro.object]] |
| 生命周期 | 对象的运行期属性：从初始化完成到析构开始或存储被复用 | [[basic.life]] |
| 指针值 | 指向某个对象、越过某个对象末尾、空、或无效 | [[basic.compound]] |

C 程序员习惯把内存看作一个大字节数组，把指针看作下标。在 C++ 里这四层之间没有自动的对应关系，下面逐层往上看。

## 存储

[[intro.memory]] 把内存描述为一串连续的字节，每个字节有唯一的地址。[[basic.stc]] 规定了四种存储期（静态、线程、自动、动态），它们决定一块存储的**存续期**（duration of the region of storage）何时开始、何时结束：程序启动或进入块时开始，程序结束、离开块或释放时结束。

存储本身不带类型。`malloc` 来的内存、一个 `unsigned char` 数组、栈上一个局部变量的空间，都只是可以放对象的地方。存储层面只有两个问题：存储还在不在，以及大小和对齐够不够（[[basic.align]]）。

指针是否可用，以存储为准而不是以对象为准。这一点在下文的指针值一节展开。

## 对象

### 对象从哪里来

[[intro.object#1]] 列出了创建对象的全部途径，一共五种：

1. 定义，如 `int x;`；
2. *new-expression*，包括 placement new；
3. 隐式创建对象的操作（C++20 起，见下文）；
4. 隐式改变联合体的活跃成员，如 `u.f = 1.0f;`（[[class.union#5]]）；
5. 创建临时对象（[[conv.rval]]、[[class.temporary]]）。

除此之外没有别的途径。类型转换不创建对象，向一块内存写入一个值不创建对象（这一点与 C 不同，见后文），`std::launder` 也不创建对象。

对象的性质在创建时确定，类型终生不变。想让同一块存储换一种类型使用，唯一的办法是在那里创建一个新对象，旧对象的生命周期随之结束。

### 子对象与提供存储

对象之间有三种包含关系，判断地址能否相同、要不要 `launder` 时都会用到：

- **子对象**（subobject，[[intro.object#2]]）：成员、基类子对象、数组元素。如果在子对象 *e* 的存储上精确地创建一个同类型的新对象，外层对象活着，*e* 也不是潜在重叠子对象，那么新对象成为外层对象的子对象，叫做 *e* 的[[g:corresponding-direct-subobjects|对应直接子对象]]。`std::optional` 一类类型原地重建成员就依赖这一条。
- **提供存储**（provides storage，[[intro.object#3]]）：完整对象创建在一个 `unsigned char[N]` 或 `std::byte[N]` 数组里时，数组为它提供存储，数组本身的生命周期不结束。`char` 数组不在此列：在 `char` 数组里 placement new 一个对象，复用了数组元素的存储，那些 `char` 元素的生命周期就结束了。
- **嵌套于**（nested within，[[intro.object#4]]）：前两种关系的传递闭包。

标准例子和边界情况见 [[intro.object]]。

## 生命周期

**生命周期**（lifetime）是对象和引用的运行期属性（[[basic.life#2]]）。`T` 类型对象的生命周期在两个条件都满足时开始：获得了大小和对齐合适的存储，并且初始化已经完成。如果默认初始化什么也没做，比如选中的是平凡默认构造函数，这叫**空初始化**（vacuous initialization），也算完成。

生命周期在下列情况结束：非类类型的对象被销毁；类类型对象的析构函数调用开始；或者存储被释放，或被一个不嵌套于它的对象复用。

把存储、对象和生命周期放在一起，得到下面几种容易混淆的状态：

| 状态 | 例子 | 可以做什么 |
|---|---|---|
| 有存储，还没有对象 | `operator new` 刚返回，构造函数还没运行（也没有隐式创建） | 当作 `void*` 用 |
| 对象活着，值不确定 | `int* p = new int;` 之后的 `*p` | 写入；读取是 UB（[[basic.indet]]） |
| 对象活着，值是错误值 | `int x;` 之后的 `x`（C++26） | 写入；读取是错误行为 |
| 正在构造或析构 | 构造函数体内的 `*this` | 受 [[class.cdtor]] 约束 |
| 生命周期已结束，存储还在 | `p->~T();` 之后 | 指针和 glvalue 只能有限地使用（[[basic.life#7]]、[[basic.life#8]]） |
| 存储已释放 | `delete p;` 之后 | 指针在之后的求值中无效（[[basic.compound#6]]） |

值不确定和不在生命周期内是两回事。前者对象存在，只是它的值不能读；后者对象已经不在了，读和写都是 UB（[[basic.life#8]] ¶8.1）。

对象死后，指向它的指针并不因此改变。按 [[basic.compound#3]] 的脚注，指向不在生命周期内的对象的指针，表示的是该对象将要或曾经占据的第一个字节。所以在原地新建对象之后，需要一条规则说明旧指针什么时候自动指向新对象，这就是后文的透明替换。

## 隐式对象创建 {{c++20}}

```cpp run title="malloc-struct.cpp" ok
#include <cstdlib>
struct Pt { int x, y; };
int main() {
  Pt* p = static_cast<Pt*>(std::malloc(sizeof(Pt)));
  p->x = 1;       // C++17 的字面规则：没有对象，UB；C++20：OK
  p->y = 2;
  int r = p->x + p->y;
  std::free(p);
  return r == 3 ? 0 : 1;
}
```

C++17 及以前，`malloc` 不在创建对象的五种途径里，按字面规则 `p` 不指向任何对象，`p->x = 1` 是 UB。[[P0593R6]] 以缺陷修复的形式引入了**隐式对象创建**（[[intro.object#13]]–[[intro.object#16]]）：

!!! std
    That operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types in its specified region of storage if doing so would result in the program having defined behavior.

被规定为隐式创建对象的操作，会在它的存储区域里创建零个或多个对象并开始它们的生命周期，前提是这样做能让程序具有定义行为。可以把它理解为抽象机在 `malloc` 那一刻预知了程序之后怎样使用这块内存，并恰好创建出让这些使用合法的对象。

- 只创建**隐式生存期类型**（implicit-lifetime type）的对象：标量、隐式生存期类、数组（[[basic.types.general#7]]）。隐式生存期类是析构函数不由用户提供的聚合体，或者至少有一个平凡的合格构造函数、析构函数平凡且未被删除的类（[[class.prop#8]]）。`std::string` 不会被隐式创建，非平凡类型只能用 *new-expression*。
- 如果没有任何一组对象能让程序有定义行为，程序就是 UB；有多组可选时，选哪一组未指定。
- 有些操作还会返回指向合适的已创建对象的指针（[[intro.object#14]]），如 `malloc`、`operator new`、`memcpy`。`unsigned char` 数组开始生命周期这种操作没有返回值，从数组退化来的指针仍然指向数组元素。这正是开头右边那段代码的问题。
- 常量求值期间不发生隐式创建（[[intro.object#16]]）。编译期求值器要精确追踪每一个对象。

隐式创建对象的操作：

| 操作 | 出处 | 是否返回指向已创建对象的指针 |
|---|---|---|
| `unsigned char[N]` 或 `std::byte[N]` 开始生命周期 | [[intro.object#16]] | 否，数组为这些对象提供存储 |
| 调用 `operator new`、`operator new[]` | [[intro.object#16]] | 是 |
| `malloc`、`calloc`、`realloc`、`aligned_alloc` | [[c.malloc#4]] | 是 |
| `memcpy`、`memmove` | [[cstring.syn#3]] | 是 |
| `std::bit_cast` | [[bit.cast]] | 在结果中创建嵌套对象 |
| `std::allocator<T>::allocate` | [[allocator.members]] | 创建 `T[n]` 数组，不开始元素的生命周期 |
| `std::start_lifetime_as<T>` {{c++23}} | [[obj.lifetime]] | 是，并保留原有的字节 |

## 指针值

### 指针值不是地址

[[basic.compound#3]] 规定，指针类型的值恰好是下列四者之一：指向某个对象或函数的指针；越过某个对象末尾的指针（尾后指针）；该类型的空指针值；无效指针值。前两类指针表示一个地址，但值本身不只是地址。

```cpp run title="past-end.cpp" ub
#include <cstdio>
int x = 1, y = 2;
int main() {
  int* p = &x + 1;              // x 的尾后指针：OK
  int* q = &y;
  if (p == q) {                 // 结果未指定，可能相等
    *p = 10;                    // UB：p 不指向 y
    std::printf("y = %d\n", y);
  }
}
```

!!! std
    A pointer past the end of an object is not considered to point to an unrelated object of the object's type, even if the unrelated object is located at that address.

尾后指针不指向恰好位于那个地址的另一个同类型对象（[[basic.compound#3]] 注 2）。所以 `p == q` 成立也不说明 `p` 指向 `y`，而尾后指针不能解引用。

本机 Clang 23 `-O2` 把 `x`、`y` 相邻放置，程序打印 `y = 10`，没有利用这条 UB。但基于来源的别名分析完全可以认定 `p` 不可能别名 `y`，从而让随后读取 `y` 直接使用旧值 2。

### 指针算术不能走出自己的数组

[[expr.add#4]] 把指针算术限制在同一个数组对象的 `[0, n]` 范围内，不是数组元素的对象视为单元素数组，越界即 UB。[[expr.add#6]] 还要求指针类型与数组元素类型相似。下面是该条款的标准例子：

```cpp
int arr[5] = {1, 2, 3, 4, 5};
unsigned* p = reinterpret_cast<unsigned*>(arr + 1);
unsigned k = *p;      // OK：int 对象可以经由 unsigned 左值访问（[basic.lval]/11.2）
unsigned* q = p + 1;  // UB：p 指向 int 数组的元素，unsigned 与 int 不相似
```

两条规则合起来，就是一个来源（provenance）规则的雏形：指针记得它属于哪个数组，不能靠算术走到别的对象里去。

### 指针可互转与可到达性

`reinterpret_cast` 什么时候会改变指针的指向？要看两个对象是否**指针可互转**（pointer-interconvertible，[[basic.compound#7]]）：同一个对象；联合体与它的非静态数据成员；标准布局类对象与它的第一个非静态数据成员或任一基类子对象；以及由此传递得到的对。指针可互转的两个对象地址相同，可以用 `reinterpret_cast` 从指向一个的指针得到指向另一个的指针（[[expr.static.cast#12]]）。不可互转时，转换不改变指针值。数组与它的第一个元素地址相同，但不是指针可互转的。

[[basic.compound#8]] 又定义了**经由指针可到达**（reachable through）的字节：指向对象 *x* 的指针，能到达与 *x* 指针可互转的某个对象 *y* 所占的字节；*y* 是数组元素时，能到达整个直接外围数组的字节。这个概念只用来约束 `std::launder`（[[ptr.launder#2]]）：结果能到达的字节，必须都能经由实参到达。

这条限制保护了一种重要的优化：

```cpp
struct X { int a[2]; int b; };
void f(X& x, int* p);   // 若 p 来自 &x.a[0]，编译器可以假设 *p 及其算术结果碰不到 x.b
```

如果 `std::launder(&x.a[0] + 2)` 能拿到 `x.b`，编译器就不能再假设指针困在自己的数组里。可到达性把 `launder` 的能力限制在同一组可达字节内换一个指向。

### 存储结束之后的指针

按当前草案的 [[basic.compound#6]]，指针是否有效是指针值与某次求值之间的关系：一个指向（或越过）对象 *O* 的指针，在 *O* 的存储存续期之内发生的求值中是[[g:valid-in-the-context-of|有效的]]。在无效的上下文中：

- 通过它间接访问（`*p`）是 UB；
- 用于布尔转换、一元 `+`、加减、比较，行为由实现定义；
- 复制它、传递它，没有限制。

这是 C++23 之后的新措辞。C++23 规定存储结束时所有指向它的指针都变成无效指针值，连复制都是实现定义的。新措辞让无锁数据结构里比较一个可能已被释放的指针这类代码不再落入实现定义的范围。详见 [[basic.compound]]。

### 从整数和字节得到的指针

指针也可以从整数或字节恢复出来：

- 整数转指针（[[expr.reinterpret.cast#5]]）：如果这个整数能由某些指针值转换得到，结果是其中能让程序有定义行为的那些指针值中未指定的一个。
- 字节转指针（[[basic.types.trivial#1]]）：`memcpy` 进一个指针对象的字节，会让它获得一个值表示，值是对应集合里能让程序有定义行为的未指定成员。一个值表示可以对应多个指针值，它们可以指向存续期互不相交的不同存储区中的对象。

两处都沿用了隐式对象创建的思路：只要存在一种让程序合法的解释，就按那种解释来。这与 C 委员会的出身模型（PNVI-ae-udi）思路相近，但 C++ 的措辞没有显式的暴露（exposure）概念。

!!! impl
    编译器对整数转指针的来源语义还没有完全一致的实现，LLVM 有过多起与整数和指针往返相关的错误优化报告。工程上，`reinterpret_cast<T*>(reinterpret_cast<std::uintptr_t>(p))` 取回原来的那个指针是安全的；用整数算术跨对象拿到别的对象的指针，即使措辞允许，也不应依赖。

## 什么时候需要 `std::launder`

!!! std
    *Returns*: A value of type T* that points to X.

`std::launder(p)` 的前提是：`p` 表示的地址上有一个类型与 `T` 相似、在生命周期内的对象 *X*，并且结果能到达的字节都能经由 `p` 到达。它返回指向 *X* 的指针（[[ptr.launder]]）。它不创建对象，不改变字节，也不生成机器指令，只是把一个地址对、指向不对的指针值换成指向那里实际存在的对象的指针值。对优化器来说，它还是一道屏障，阻止编译器沿用关于旧对象的已知事实，典型的是 `const` 成员和虚表指针。

在原地新建对象后，旧指针在满足条件时会自动指向新对象。这个条件叫**透明可替换**（transparently replaceable，[[basic.life#9]]）：两者是类型相同（忽略顶层 cv）、存储精确重叠的完整对象，并且原对象不是 const；或者两者是对应直接子对象，并且外层完整对象不是 const（或者该子对象是 `mutable` 成员）。满足时，按 [[basic.life#10]]，原来的指针、引用和名字都自动指向新对象。

判断手里的指针 `p` 是否指向地址上现存的对象 *X*：

```text
p 是 placement new / operator new / malloc / memcpy / start_lifetime_as 的返回值？
  → 是，直接用。
X 是在 p 原来指向的对象 O 的存储上新建的？
  ├─ O 可被 X 透明替换（[basic.life]/9）→ p 自动指向 X，不需要 launder。
  └─ 否（O 是 const 完整对象、类型不同、O 是基类子对象……）→ 需要 std::launder(p)。
p 是从别的对象的指针转换来的（例如字节缓冲区 → T*）？
  ├─ 两个对象指针可互转 → 转换已经改变了指向，不需要。
  └─ 否 → p 仍指向原对象（如 buf[0]），需要 std::launder。
其他 → 先确认 X 真的存在、字节可经由 p 到达；否则 launder 也没有用。
```

C++20 之后透明替换的条件已经相当宽松，需要 `launder` 的场景主要剩下三种：

1. 在字节缓冲区里创建对象后，从缓冲区本身而不是 placement new 的返回值重新取得指向它的指针。`std::optional`、`std::variant` 和小缓冲区优化的实现里最常见。
2. 原对象是动态存储期的 const 完整对象。静态、线程或自动存储期的 const 完整对象，在它的存储上新建对象本身就是 UB（[[basic.life#12]]），`launder` 也无济于事。
3. 原对象是基类子对象，或者新对象类型不同。

```cpp run title="sbo.cpp" ok
#include <new>
#include <string>
#include <utility>

template <class T>
class Box {                                   // 极简的可空盒子
  alignas(T) unsigned char buf_[sizeof(T)];   // buf_ 为 T 提供存储
  bool full_ = false;
  T* ptr() { return std::launder(reinterpret_cast<T*>(buf_)); }   // 需要 launder
public:
  template <class... A> void emplace(A&&... a) {
    reset();
    ::new (static_cast<void*>(buf_)) T(std::forward<A>(a)...);   // 返回值没有保存
    full_ = true;
  }
  void reset() { if (full_) { ptr()->~T(); full_ = false; } }
  T& get() { return *ptr(); }
  ~Box() { reset(); }
};

int main() {
  Box<std::string> b;
  b.emplace("hello, object model");
  b.emplace(3, 'x');                          // 析构旧对象，在同一 buf_ 中建新对象
  return b.get() == "xxx" ? 0 : 1;
}
```

`unsigned char` 数组与 `T` 不是指针可互转的，所以 `reinterpret_cast<T*>(buf_)` 的值仍指向 `buf_[0]`（[[expr.static.cast#12]]）。去掉 `launder`，就是在通过 `T` 类型的 glvalue 访问一个 `unsigned char` 对象。主流编译器对两种写法生成同样的代码，但没有 `launder` 的版本只是碰巧能用。

!!! tip "保存 placement new 的返回值"
    `T* p = ::new (buf_) T(...);` 的返回值就是指向新对象的指针，不需要 `launder`，代价是多存一个指针。标准库实现为了省下这几个字节，才在每次访问时调用 `launder`。

## 与 C 的有效类型模型对比

C 没有创建对象的概念，而是用**有效类型**（effective type，C17 6.5p6）约束别名：

| 问题 | C | C++ |
|---|---|---|
| `malloc` 的内存是什么类型 | 没有声明类型；第一次以非字符类型左值写入时获得有效类型 | `malloc` 当场隐式创建合适的对象 |
| 换一种类型使用同一块 `malloc` 内存 | 用新类型写入即可改变有效类型 | 必须创建新对象，旧对象生命周期结束 |
| 声明的变量能换类型吗 | 不能，有效类型就是声明类型 | 能：在其存储上创建新对象（不是 const，且析构时类型一致，[[basic.life#11]]） |
| 读联合体的非活跃成员 | 合法，按新类型重新解释字节 | UB，常量求值中必须诊断 |
| 指针值 | 地址加来源（C 的来源模型仍在技术规范阶段） | 指向对象；`launder`、透明替换、可到达性都围绕指向谁展开 |
| 非平凡类型 | 不存在 | 只能由 *new-expression* 等显式创建 |

在平凡数据加 `malloc`、`memcpy` 的范围内，两种模型给出相同的结论，这正是 P0593 的设计目标。分歧出在 C 没有的东西上：构造函数、const 对象、基类子对象、`std::launder`。把 C 的直觉搬到 C++，在 POD 代码里通常没事，在泛型容器、内存池、序列化库里就会出错。

## 谜题

每题问标注的那一行是良构且行为明确，还是 UB。

!!! question "谜题 1"
    ```cpp
    #include <cstdlib>
    struct P { int x, y; };
    int f() {
      P* p = static_cast<P*>(std::malloc(sizeof(P)));
      p->x = 1;
      return p->y;        // ?
    }
    ```

<details markdown="1">
<summary>答案</summary>

UB，但原因不是没有对象。C++20 起 `malloc` 隐式创建了 `P` 及其子对象 `x`、`y`，`p->y` 指代的是一个存在且活着的 `int`。问题在于它的值：动态存储期的存储，字节的初值是不确定值（[[basic.indet#1]] ¶1.1），读取不确定值是 UB（¶2）。自动变量不同，`int y; return y;` 在 C++26 中是错误行为而不是 UB。
</details>

!!! question "谜题 2"
    ```cpp
    #include <new>
    struct S { const int id; };
    int g() {
      S* s = new S{1};
      s->~S();
      new (s) S{2};
      int r = s->id;     // ?
      delete s;
      return r;
    }
    ```

<details markdown="1">
<summary>答案</summary>

C++20 起 OK，`r == 2`。`*s` 是动态存储期的非 const 完整对象，新对象类型相同、精确覆盖原存储，满足透明可替换（[[basic.life#9]] ¶9.1），于是 `s` 自动指向新对象（¶10）。C++17 的措辞里，含 const 成员或引用成员会阻止透明替换，这里需要 `std::launder`；C++20 删去了这个条件。

如果写成 `const S* s = new const S{1};`，原对象是 const 完整对象，第 9.1.1 项不满足，需要 `std::launder(s)->id`，这正是 [[ptr.launder]] 的标准例子。如果 `s` 指向一个自动存储期的 const 局部变量，在其存储上新建对象本身就是 UB（[[basic.life#12]]）。
</details>

!!! question "谜题 3"
    ```cpp
    union U { int i; float f; };
    int k() {
      U u{.i = 1};
      int* p = &u.i;
      u.f = 2.0f;
      return *p;          // ?
    }
    ```

<details markdown="1">
<summary>答案</summary>

UB。`u.f = 2.0f` 是对联合体成员的内建赋值，按 [[class.union#5]] 隐式创建 `f` 并使它成为活跃成员，`i` 的存储被复用，生命周期结束（[[basic.life#2]] ¶2.5）。`p` 仍然指向已经死去的 `u.i`，`*p` 读取一个不在生命周期内的对象，违反 [[basic.life#8]] ¶8.1。
</details>

!!! question "谜题 4"
    ```cpp
    struct H { int tag; double d; };
    int m() {
      H h{1, 2.0};
      int* pt = reinterpret_cast<int*>(&h);
      *pt = 5;           // ?
      return h.tag;
    }
    ```

<details markdown="1">
<summary>答案</summary>

OK，返回 5。`H` 是标准布局类，`h` 与第一个非静态数据成员 `h.tag` 指针可互转（[[basic.compound#7]] ¶7.3），所以 `reinterpret_cast` 的结果指向 `h.tag`（[[expr.static.cast#12]]）。C 里把结构体的第一个成员当作头部的惯用法，在 C++ 中以此为依据。如果 `H` 不是标准布局类（例如有虚函数），指针值不变，仍指向 `h`，`*pt = 5` 就是 UB。
</details>

!!! question "谜题 5"
    ```cpp
    #include <new>
    int n() {
      int arr[4] = {1, 2, 3, 4};
      auto pa = reinterpret_cast<int(*)[4]>(&arr[0]);
      auto pb = std::launder(pa);
      return (*pb)[1];    // ?   换成 (*pa)[1] 呢？
    }
    ```

<details markdown="1">
<summary>答案</summary>

`(*pb)[1]` 是 OK 的，`(*pa)[1]` 是 UB。

数组与它的第一个元素不是指针可互转的（[[basic.compound#7]] 注 7），所以 `pa` 仍指向 `arr[0]` 这个 `int`，只是类型变成了 `int(*)[4]`。`*pa` 是一个指代 `int` 对象的 `int[4]` 左值，接下来的数组到指针转换没有数组对象可依。

`std::launder(pa)` 的两个前提都满足：地址上有一个类型为 `int[4]`、活着的对象 `arr`；经由 `pa` 可到达的是 `arr[0]` 的直接外围数组 `arr` 的全部字节（[[basic.compound#8]]），覆盖了结果能到达的字节。所以 `pb` 指向 `arr`。这是 `launder` 的另一种用途：在指针不可互转的地方换一个指向。
</details>

!!! question "谜题 6"
    ```cpp
    #include <new>
    struct X { int a[2]; int b; };
    int q(X& x) {
      int* p = &x.a[0] + 2;           // a 的尾后指针；假设无填充，地址等于 &x.b
      return *std::launder(p);        // ?
    }
    ```

<details markdown="1">
<summary>答案</summary>

UB。`p` 是尾后指针，不指向任何对象，可到达性只对指向对象的指针定义，所以经由 `p` 到达不了任何字节（[[basic.compound#8]]）。`std::launder` 要求结果能到达的字节（`x.b` 的 4 个字节）都能经由实参到达，前置条件不满足。这正是可到达性要保护的优化：从 `x.a` 派生的指针碰不到 `x.b`。要得到 `x.b` 的指针，就写 `&x.b`，或者从指向 `x` 的指针出发。
</details>

!!! question "谜题 7"
    ```cpp
    #include <cstdint>
    int x = 1, y = 2;
    int r() {
      auto n = reinterpret_cast<std::uintptr_t>(&x);
      int* p = reinterpret_cast<int*>(n + sizeof(int));
      if (p == &y) { *p = 10; return y; }    // ?
      return 0;
    }
    ```

<details markdown="1">
<summary>答案</summary>

按当前措辞，进入 `if` 时有定义，返回 10。这与前面 `&x + 1` 的例子形成对照。

按 [[expr.reinterpret.cast#5]]，整数值 `n + sizeof(int)` 能由指针值转换得到（`&x + 1` 和 `&y` 都转换成它），结果是其中能让程序有定义行为的指针值中未指定的一个。选指向 `y` 的指针能让 `*p = 10` 合法，抽象机就选它。指针算术做不到的事（尾后指针永远不指向 `y`），整数往返却可以。

工程上不要这样写。整数转指针的来源语义正是错误优化报告集中的地方。
</details>

## 小结

| 问题 | 看哪一层 | 关键条款 |
|---|---|---|
| 内存还在吗 | 存储 | [[basic.stc]]、[[basic.compound#6]] |
| 那里有对象吗，什么类型 | 对象 | [[intro.object#1]]、[[intro.object#13]] |
| 对象活着吗 | 生命周期 | [[basic.life#2]]、[[basic.life#7]]、[[basic.life#8]] |
| 值能读吗 | 值 | [[basic.indet]] |
| 我的指针指向它吗 | 指针值 | [[basic.compound#3]]、[[basic.compound#7]]、[[expr.static.cast#12]] |
| 能用这个类型访问它吗 | 访问 | [[basic.lval#11]]，见 [[topics/type-punning]] |
| 旧指针会自动指向新对象吗 | 透明替换 | [[basic.life#9]]、[[basic.life#10]] |
| 不会怎么办 | `std::launder` | [[ptr.launder]] |
