---
title: C++ 对象模型：存储、对象、生命周期、指针值
summary: 把抽象机里的四层东西分开看——存储（字节与存续期）、对象（类型在创建时定死）、生命周期（运行期属性）、指针值（指向"谁"而不只是"哪里"）；隐式对象创建、提供存储、std::launder 的真正用途、指针值的四种状态与"出身"式规则、与 C 有效类型模型的对比，以及一组分级谜题
status: draft
order: 12
since: c++98
papers: P0593R6, P0137R1, P2590R2
related: intro.object, intro.memory, basic.stc, basic.life, basic.compound, basic.lval, basic.indet, basic.types.trivial, ptr.launder, obj.lifetime, expr.add, expr.eq, expr.reinterpret.cast, topics/type-punning, topics/dangling-references, topics/undefined-behavior
tags: 对象模型, 生命周期, 指针, launder, 专题
updated: 2026-10-18
---

几乎所有"这段代码到底合不合法"的争论，最后都归结到一个问题：**在那个时刻、那个地址上，到底有没有一个对象？手里的指针指向的是不是它？**

C 程序员习惯的心智模型是"内存就是一个大字节数组，指针就是下标"。C++ 标准描述的抽象机不是这样的。它至少有四层彼此独立的东西：

| 层 | 是什么 | 由谁规定 | 一句话 |
|---|---|---|---|
| 存储（storage） | 字节、内存位置，以及一段存储从获得到释放的**存续期** | [[intro.memory]]、[[basic.stc]] | "那里有内存" |
| 对象（object） | 占据一块存储、带有**在创建时确定**的类型的实体 | [[intro.object]] | "那里有一个 `T`" |
| 生命周期（lifetime） | 对象的一个**运行期属性**：从初始化完成到析构开始/存储被复用 | [[basic.life]] | "那个 `T` 现在活着" |
| 指针值（pointer value） | 指向某个对象、越过某个对象末尾、空、或无效 | [[basic.compound]] | "我手里的指针指的是那个 `T`" |

四层之间**没有自动的对应**：有存储不等于有对象；有对象不等于它在生命周期内；指针表示的地址上有一个活着的 `T`，也不等于这个指针**指向**它。本专题沿这四层往上走一遍，把散落在 [[intro.object]]、[[basic.life]]、[[basic.compound]]、[[basic.lval]]、[[expr.add]]、[[ptr.launder]] 里的规则串起来，最后用一组谜题检验。

```text
  ┌───────────────────────── 存储区（region of storage）──────────────────────┐
  │  存续期：从分配函数返回 / 进入块 / 程序启动  ……  到释放 / 离开块 / 程序结束    │
  │                                                                          │
  │   ┌──── 对象 o₁: int ────┐          ┌──── 对象 o₂: float ────┐            │
  │   │ 生命周期 [t₁, t₂)     │ 复用存储 →│ 生命周期 [t₂, …)       │            │
  │   └──────────────────────┘          └───────────────────────┘            │
  └──────────────────────────────────────────────────────────────────────────┘
      int* p  ── 指向 o₁ ──（o₁ 结束后：仍"指向"o₁，只能有限使用）
      float* q ── 指向 o₂（由 placement new 的返回值或 std::launder 得到）
```

## 第一层：存储

[[intro.memory]] 把内存描述为连续的**字节**序列，每个字节有唯一的地址；[[basic.stc]] 规定了四种**存储期**（静态、线程、自动、动态），它们决定一块存储的**存续期**（*duration of the region of storage*）何时开始、何时结束。

存储本身不带类型。一块 `malloc` 来的内存、一个 `unsigned char` 数组、一段栈上的局部变量空间，都只是"可以放对象的地方"。存储层面的问题只有两个：**存储还在不在**（存续期），以及**对齐和大小够不够**（[[basic.align]]）。

存续期是指针有效性的基准。当前草案用"指针值在某求值的上下文中**有效**"（[[basic.compound#6]]）来表达：指针所指/所越过的对象的**存储**正处于存续期内，这个指针在该求值中才是有效的——注意这里关心的是存储，不是对象的生命周期。

## 第二层：对象

### 对象从哪里来

[[intro.object#1]] 给出了**全部**五种创建对象的途径：

1. 定义（`int x;`）；
2. *new-expression*（包括 placement new）；
3. **隐式创建对象**的操作（C++20 起，见下文）；
4. 隐式改变联合体的活跃成员（`u.f = 1.0f;`，[[class.union#5]]）；
5. 临时对象被创建时（[[conv.rval]]、[[class.temporary]]）。

除此之外**没有别的途径**。特别是：类型转换不创建对象，`reinterpret_cast` 不创建对象，写一个值不创建对象（这与 C 不同，见后文），`std::launder` 也不创建对象。

对象的**类型在创建时确定**，终生不变（¶1："The properties of an object are determined when the object is created."）。想让同一块存储"变成另一种类型"，唯一的办法是在那里**创建一个新对象**，旧对象的生命周期随之结束。

### 嵌套、子对象、提供存储

对象之间有三种包含关系，后面判断 `launder` 是否需要、地址是否可以相同时都要用到：

- **子对象**（¶2）：成员、基类子对象、数组元素。若在一个子对象 *e* 的存储上**精确地**创建同类型的新对象，且外层对象活着、*e* 不是潜在重叠子对象，新对象就成为外层对象的子对象（"对应直接子对象"）——这是 `std::optional`、`std::variant` 式"原地重建成员"合法的基础。
- **提供存储**（¶3）：完整对象被创建在一个 `unsigned char[N]` 或 `std::byte[N]` 数组里时，该数组为它**提供存储**——数组本身的生命周期**不**结束。注意清单里没有 `char`：在 `char` 数组里 placement new 一个对象，是**复用**了数组元素的存储，那些 `char` 元素的生命周期随之结束。
- **嵌套于**（¶4）：子对象关系与提供存储关系的传递闭包。

细节、标准例子与边界在 [[intro.object]] 中逐段讨论。

## 第三层：生命周期

生命周期是**对象**（和引用）的运行期属性（[[basic.life#2]]）：

- **开始**：获得了满足 `T` 大小和对齐的存储，**并且**初始化（若有）已完成——包括"空初始化"（*vacuous initialization*，一个平凡默认构造函数什么也不做）。
- **结束**：非类类型——对象被销毁；类类型——**析构函数调用开始**时；或者存储被**释放**，或被一个**不嵌套于它**的对象**复用**。

由此可以得到几个经常被混淆的区分：

| 状态 | 例子 | 可以做什么 |
|---|---|---|
| 存储存在、对象尚未存在 | `operator new` 返回、构造函数尚未运行（且未被隐式创建） | 当作 `void*` 用 |
| 对象在生命周期内、值不确定 | `int* p = new int;` 之后的 `*p` | 写入；读取是 UB（[[basic.indet]]） |
| 对象在生命周期内、值是错误值 | `int x;` 之后的 `x`（C++26） | 写入；读取是**错误行为** |
| 对象在构造/析构期间 | 构造函数体内的 `*this` | 受 [[class.cdtor]] 约束 |
| 对象生命周期已结束、存储仍在 | `p->~T();` 之后 | 只能有限地使用指针/glvalue（[[basic.life#7]]、[[basic.life#8]]） |
| 存储已释放 | `delete p;` 之后 | 指针值在之后的求值中**无效**（[[basic.compound#6]]） |

"值不确定"与"不在生命周期内"是两回事：前者对象**存在**，只是读它的值有问题；后者连"它"都谈不上，访问它（读或写）都是 UB（[[basic.life#8]] ¶8.1）。

!!! note "生命周期之外的指针仍然“指向”原来的对象"
    [[basic.compound#3]] 的脚注说得很直白：对于不在生命周期内的对象，指针所"表示的地址"是它**将要**或**曾经**占据的第一个字节。指针值的身份并不因为对象死亡而改变。正因为如此，[[basic.life#10]] 才需要一条专门的规则，说明旧指针**何时自动指向**在原地新建的对象（透明可替换），以及不满足条件时要靠 `std::launder`。

## 隐式对象创建：C 风格代码的合法性来源 {{c++20}}

C++17 及以前，`malloc` 不在创建对象的清单里，于是

```cpp run title="malloc-struct.cpp" ok
#include <cstdlib>
struct Pt { int x, y; };
int main() {
  Pt* p = static_cast<Pt*>(std::malloc(sizeof(Pt)));
  p->x = 1;       // C++17：p 不指向任何对象 → UB；C++20：OK
  p->y = 2;
  int r = p->x + p->y;
  std::free(p);
  return r == 3 ? 0 : 1;
}
```

在字面意义上是 UB。[[P0593R6]] 作为缺陷修复引入了**隐式对象创建**（[[intro.object#13]]–[[intro.object#16]]）：

!!! std
    That operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types in its specified region of storage if doing so would result in the program having defined behavior.

    被规定为"隐式创建对象"的操作，会在其存储区域中创建零个或多个**隐式生存期类型**的对象并开始其生命周期——只要这样做能让程序具有定义行为。

这是一种"天使般的非确定性"：抽象机在 `malloc` 那一刻"预知"程序之后怎么用这块内存，恰好创建出让这些使用合法的对象。几个要点：

- 只创建**隐式生存期类型**（[[basic.types.general#7]]：标量、隐式生存期类、数组）。`std::string` 不会被隐式创建——非平凡类型必须用 *new-expression*。
- 如果**没有**任何对象集合能让程序有定义行为，程序就是 UB；如果有多个，选哪个未指定。
- 有些操作还额外**返回指向"合适的已创建对象"的指针**（¶14）——`malloc`、`operator new`、`memcpy` 都是；而"`unsigned char` 数组开始生命周期"这种操作**没有返回值**，所以你手里从数组退化来的指针仍然指向数组元素。这正是后面 `std::launder` 出场的地方。

隐式创建对象的操作一览：

| 操作 | 出处 | 返回指向已创建对象的指针？ |
|---|---|---|
| `unsigned char[N]` / `std::byte[N]` 的生命周期开始 | [[intro.object#16]] | 否（数组为这些对象提供存储） |
| 调用 `operator new` / `operator new[]` | [[intro.object#16]] | 是 |
| `malloc`、`calloc`、`realloc`、`aligned_alloc` | [[c.malloc#4]] | 是 |
| `memcpy`、`memmove` | [[cstring.syn#3]] | 是（返回目标指针） |
| `std::bit_cast` | [[bit.cast]] | 结果中的嵌套对象 |
| `std::allocator<T>::allocate` | [[allocator.members]] | 创建 `T[n]` 数组，不开始元素生命周期 |
| `std::start_lifetime_as<T>` {{c++23}} | [[obj.lifetime]] | 是，且保留原有字节 |

隐式创建在**常量求值期间不发生**（¶16 "Except during constant evaluation"）——编译期求值器要精确追踪每个对象，不玩"天使般的猜测"。

## 第四层：指针值

### 指针值不是地址

[[basic.compound#3]] 规定每个指针类型的值恰好是以下四者之一：

1. **指向**某个对象或函数的指针；
2. 越过某个对象**末尾**的指针（past-the-end）；
3. 该类型的**空指针值**；
4. **无效指针值**。

前两类指针"表示"一个地址，但**值不等于地址**。最经典的例子是标准的注 2：

!!! std
    A pointer past the end of an object is not considered to point to an unrelated object of the object's type, even if the unrelated object is located at that address.

    越过对象末尾的指针不被认为指向一个恰好位于该地址的无关同类型对象。

```cpp run title="past-end.cpp" ub
#include <cstdio>
int x = 1, y = 2;
int main() {
  int* p = &x + 1;              // x 的尾后指针：OK
  int* q = &y;
  if (p == q) {                 // 未指定（[expr.eq]/4.1）：可能相等
    *p = 10;                    // UB：p 不指向 y，尾后指针不可解引用
    std::printf("y = %d\n", y);
  }
}
```

本机 Clang 23 在 `-O0` 和 `-O2` 下都把 `x`、`y` 相邻放置并打印 `y = 10`——Clang 在这里**没有**利用这条 UB。但这只说明"当前没被利用"：基于出身的别名分析完全有权认定"`p` 不可能别名 `y`"，从而让随后对 `y` 的读取直接使用旧值 `2`——这类现象在其他编译器上有过公开报告。标准的立场很明确：两个指针**比较相等**（同一地址）并不让它们**指向同一个对象**。

### 指针只能在"它的数组"里移动

[[expr.add#4]] 把指针算术限制在**同一个数组对象**（非数组对象视为单元素数组）的 `[0, n]` 范围内，越界即 UB；[[expr.add#6]] 进一步要求指针类型与数组元素类型**相似**：

```cpp
int arr[5] = {1, 2, 3, 4, 5};
unsigned* p = reinterpret_cast<unsigned*>(arr + 1);
unsigned k = *p;      // OK：int 对象可经由 unsigned 左值访问（[basic.lval]/11.2）
unsigned* q = p + 1;  // UB：p 指向的是 int 数组的元素，unsigned 与 int 不相似
```

（这是 [[expr.add]] 的标准例子。）两条规则合起来，相当于一个"出身"（provenance）规则的雏形：**指针记得它属于哪个数组**，不能靠算术"走"到别的对象里去。

### "可经由指针到达"与 `std::launder`

[[basic.compound#8]] 定义：经由一个指向对象 *x* 的指针**可到达**的字节，是与 *x* 指针可互转的某个对象 *y* 所占据的字节（若 *y* 是数组元素，则是整个直接外围数组的字节）。这个概念唯一的用途就是约束 `std::launder`（[[ptr.launder#2]]）：结果能到达的字节，必须都能经由实参到达。

为什么要这条？因为它保护了一个重要的优化：

```cpp
struct X { int a[2]; int b; };
void f(X& x, int* p);   // 若 p 来自 &x.a[0]，编译器可以假设 *p 及其算术结果碰不到 x.b
```

如果允许 `std::launder(&x.a[0] + 2)` 拿到 `x.b`，编译器就无法再基于"指针困在它的数组里"做别名分析。可到达性把 `launder` 的能力限制在"同一组可达字节内换一个指向"。

### 在某求值上下文中有效 {{c++26}}

当前草案（[[basic.compound#6]]）不再说"存储释放时所有指向它的指针**变成**无效指针值"，而是把有效性定义为**指针值与求值之间的关系**：在存储存续期内发生的求值中，指向/越过其中对象的指针是有效的。在无效的上下文中：

- 通过它**间接**（`*p`）：UB；
- 用于布尔转换、一元 `+`、加减、比较：**实现定义**；
- 复制它、传递它：**没有限制**。

C++23 中，连"复制一个已被释放的指针"都是实现定义的；新模型让无锁数据结构里"比较一个可能已被释放的指针"这类代码至少不再是理论上的地雷。详见 [[basic.compound]] 中"与 C++23 的区别"一节。

### 整数与字节中的指针：天使般的选择

指针也可以"绕路"回来：

- **整数 → 指针**（[[expr.reinterpret.cast#5]]）：若该整数值能由某些指针值转换得到，结果是"所有能让程序有定义行为的指针值中**未指定的一个**"；
- **字节 → 指针**（[[basic.types.trivial#1]]）：`memcpy` 进一个指针对象的字节使它"获得"一个值表示，其值是对应子集中"能让程序有定义行为的"未指定成员——而一个值表示可以对应**多个**指针值（注 1：可能指向多个存续期不相交的存储区中的对象）。

两处都沿用了隐式对象创建的"天使般选择"：只要存在一种解释让程序合法，就按那种解释来。这与 C 委员会正在推进的"PNVI-ae-udi"出身模型思路相近，但 C++ 的措辞没有显式的"暴露"（exposure）概念。

!!! impl
    编译器对 `inttoptr` 的出身语义至今没有完全一致的实现。LLVM 曾有过多起与整数↔指针往返相关的错误优化报告。对工程而言：整数往返 `reinterpret_cast<T*>(reinterpret_cast<std::uintptr_t>(p))` 取回**原来那个**指针是安全的；用整数算术"跨对象"拿到别的对象的指针，即使标准措辞看起来允许，也是最不该依赖的那一类代码。

## 指针何时"指向新对象"：`std::launder` 的完整决策

把上面几层合起来，就能精确回答 `std::launder` 什么时候需要。先记住它**做什么**：

!!! std
    *Returns*: A value of type T* that points to X.

    `std::launder(p)`：前提是 `p` 表示的地址上有一个类型与 `T` 相似、在生命周期内的对象 *X*（且满足可到达性）；返回**指向 X** 的指针。

它不创建对象、不改变字节、不产生任何机器指令；它只是把一个"地址对、但指向不对"的指针值，换成"指向那里实际存在的对象"的指针值，同时作为一道优化屏障，告诉编译器不要沿用对旧对象的已知事实（典型的是 `const` 成员和虚表指针）。

```text
你有一个指针 p，地址处现在有一个活着的对象 X。p 指向 X 吗？

├─ p 是 placement new / operator new / malloc / memcpy / start_lifetime_as 的返回值？
│     → 是，直接用。
├─ X 是在 p 原来所指对象 O 的存储上新建的？
│     ├─ O 可被 X 透明替换（[basic.life]/9）？
│     │     → p 自动指向 X（[basic.life]/10），不需要 launder。
│     └─ 否（O 是 const 完整对象 / 类型不同 / O 是基类子对象 / 不是精确覆盖 …）
│           → 需要 std::launder(p)。
├─ p 是从别的对象的指针 cast 来的（例如字节缓冲区 → T*）？
│     ├─ 两者指针可互转（[basic.compound]/7）？ → static_cast/reinterpret_cast 已改变指向，不需要。
│     └─ 否 → p 仍指向原对象（如 buf[0]），需要 std::launder。
└─ 其他 → 先确认 X 真的存在、且字节可经由 p 到达；否则 launder 也救不了。
```

透明可替换的条件（[[basic.life#9]]）在 C++20 放宽后已经很宽松：两个完整对象类型相同（忽略顶层 cv）、存储精确重叠、原对象**不是 const**；或者两者是对应直接子对象、外层完整对象不是 const（或该子对象是 `mutable` 的）。所以在 C++20 及以后，**需要 `launder` 的典型场景只剩下**：

1. 在**字节缓冲区**里创建对象后，从缓冲区本身（而不是 placement new 的返回值）重新取得指向它的指针——`std::optional`、`std::variant`、small-buffer optimization 的实现里最常见；
2. 原对象是 **const 完整对象**（动态存储期的；静态/自动存储期的 const 对象上新建对象本身就是 UB，[[basic.life#12]]）；
3. 原对象是**基类子对象**，或新对象类型不同。

```cpp run title="sbo.cpp" ok
#include <new>
#include <string>
#include <utility>

template <class T>
class Box {                                   // 极简的"可空盒子"
  alignas(T) unsigned char buf_[sizeof(T)];   // buf_ 为 T 提供存储（[intro.object]/3）
  bool full_ = false;
  T* ptr() { return std::launder(reinterpret_cast<T*>(buf_)); }   // 需要 launder
public:
  template <class... A> void emplace(A&&... a) {
    reset();
    ::new (static_cast<void*>(buf_)) T(std::forward<A>(a)...);   // 返回值可直接用，但我们没存
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

`reinterpret_cast<T*>(buf_)` 的值仍指向 `buf_[0]`（一个 `unsigned char`）——`unsigned char` 数组与 `T` 不是指针可互转的（[[basic.compound#7]]），而 [[expr.static.cast#12]] 规定此时"指针值不因转换而改变"。所以没有 `launder` 的版本，在标准意义上是在通过 `T` 类型的 glvalue 访问一个 `unsigned char` 对象。所有主流编译器对省略 `launder` 的版本都生成同样的代码，但那是"碰巧能用"。

!!! tip "最省事的做法：保存 placement new 的返回值"
    `T* p = ::new (buf_) T(...);` 的返回值**就是**指向新对象的指针，不需要任何 `launder`。代价只是多存一个指针。标准库实现为了节省这几个字节，才在每次访问时 `launder`。

## 与 C 的有效类型模型对比

C 没有"创建对象"的概念，而是用**有效类型**（effective type，C17 6.5p6）来约束别名：

| 问题 | C | C++ |
|---|---|---|
| 一块 `malloc` 的内存是什么类型？ | 没有声明类型；第一次以非字符类型左值**写入**时获得有效类型 | `malloc` 当场隐式创建"恰好合适"的对象 |
| 换一种类型使用同一块 `malloc` 内存？ | 用新类型写入即可改变有效类型 | 必须创建新对象（placement new、再次隐式创建），旧对象生命周期结束 |
| 声明的变量能换类型吗？ | 不能（有效类型即声明类型） | 能：在其存储上创建新对象（若不是 const、析构时类型一致，[[basic.life#11]]） |
| union 读非活跃成员 | 合法：按新类型重新解释字节 | UB（常量求值中必须诊断） |
| 指针值 | 地址 + 出身（C 的出身模型仍在技术规范阶段） | 指向**对象**；`launder`、透明替换、可到达性都围绕"指向谁"展开 |
| 非平凡类型 | 不存在 | 只能由 *new-expression* 等显式创建 |

在"平凡数据 + `malloc`/`memcpy`"这个交集里，两种模型给出相同的结论——这正是 P0593 的设计目标。分歧出现在 C 没有的东西上：构造函数、`const` 对象、基类子对象、`std::launder`。所以把 C 的直觉直接搬到 C++，在 POD 代码里通常没事，在泛型容器、内存池、序列化库里就会撞墙。

## 分级谜题

以下每题问：标注的那一行是良构且行为明确、UB、还是其他？先自己判断再展开答案。

### 入门

**谜题 1**

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

**UB**，但原因不是"没有对象"。`malloc` 隐式创建了 `P` 及其子对象 `x`、`y`（C++20 起），所以 `p->y` 指代的是一个**存在且在生命周期内**的 `int`。问题在于它的值：`malloc` 得到的存储具有**动态存储期**，其字节是**不确定值**（[[basic.indet#1]] ¶1.1），读取不确定值是 UB（¶2）。注意这与自动变量不同——`int y; return y;` 在 C++26 中是**错误行为**而非 UB。
</details>

**谜题 2**

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

**OK**（C++20 起），`r == 2`。`*s` 是动态存储期的**非 const** 完整对象；新对象类型相同、精确覆盖原存储，满足透明可替换（[[basic.life#9]] ¶9.1），于是 `s` 自动指向新对象（¶10）。C++17 的措辞中，"含 const 成员或引用成员"会阻止透明替换，这里需要 `std::launder`；C++20 删除了这一条件。

变体：若写成 `const S* s = new const S{1};`，则原对象是 **const 完整对象**，¶9.1.1 不满足，需要 `std::launder(s)->id`（这正是 [[ptr.launder]] 的标准例子）。若 `S` 是一个**自动存储期的 const 局部变量**，在其存储上新建对象本身就是 UB（[[basic.life#12]]），`launder` 也救不了。
</details>

**谜题 3**

```cpp
#include <new>
int h() {
  alignas(int) unsigned char buf[sizeof(int)];
  new (buf) int(42);
  return *reinterpret_cast<int*>(buf);     // ?
}
```

<details markdown="1">
<summary>答案</summary>

**UB（按标准）**。`reinterpret_cast<int*>(buf)` 等价于 `static_cast<int*>(static_cast<void*>(buf))`（[[expr.reinterpret.cast#7]]）；`buf[0]` 与新建的 `int` 不是指针可互转的，所以结果仍**指向 `buf[0]`**（[[expr.static.cast#12]]）。解引用得到一个指代 `unsigned char` 对象的 `int` 左值，读取违反 [[basic.lval#11]]。修正：`*std::launder(reinterpret_cast<int*>(buf))`，或保存 placement new 的返回值。本机 Clang 23 对两个版本生成完全相同的代码。
</details>

### 进阶

**谜题 4**

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

**UB**。`u.f = 2.0f` 是对联合体成员的内建赋值，按 [[class.union#5]] 隐式创建 `f` 对象并使其成为活跃成员，`i` 的生命周期随之结束（存储被复用，[[basic.life#2]] ¶2.5）。`p` 仍然"指向" `u.i` 这个已死亡的对象；`*p` 读取一个不在生命周期内的对象，违反 [[basic.life#8]] ¶8.1。

有趣的是，改成 `return *reinterpret_cast<float*>(p);` 反而是**合法的**（返回 `2`）：`u.i` 与 `u` 指针可互转，`u` 与 `u.f` 也指针可互转（[[basic.compound#7]] ¶7.2、¶7.4），所以经由 `void*` 的转换产生**指向 `u.f`** 的指针（[[expr.static.cast#12]]），读到的是活跃成员的值 `2.0f`，再转换为 `int`。对生命周期之外的对象的指针做这种转换不在 [[basic.life#7]] 禁止之列。
</details>

**谜题 5**

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

**OK**，返回 `5`。`H` 是标准布局类，`h` 与其第一个非静态数据成员 `h.tag` 指针可互转（[[basic.compound#7]] ¶7.3），所以 `reinterpret_cast` 的结果**指向 `h.tag`**（[[expr.static.cast#12]]）。这是 C 风格"结构体首成员当作头部"惯用法在 C++ 中的合法依据。若 `H` 不是标准布局（例如成员访问控制混杂、有虚函数），结论就变成"指针值不变，仍指向 `h`"，`*pt = 5` 是 UB。
</details>

**谜题 6**

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

`(*pb)[1]` **OK**，`(*pa)[1]` **UB**。

数组与其第一个元素**不是**指针可互转的（[[basic.compound#7]] 注 7），所以 `pa` 仍然指向 `arr[0]` 这个 `int`，只是类型是 `int(*)[4]`——`*pa` 是一个指代 `int` 对象的 `int[4]` 左值，后续的数组到指针转换没有一个数组对象可依。

`std::launder(pa)` 的前提：地址上有一个类型相似于 `int[4]`、在生命周期内的对象——`arr` 本身就在那里；可到达性：经由结果可到达 `arr` 的 16 个字节，而经由 `pa`（指向数组元素 `arr[0]`）可到达的是"直接外围数组"即 `arr` 的全部字节（[[basic.compound#8]]）。两个前提都满足，`pb` 指向 `arr`。这是 `launder` 的"另一种"用途：不是对付新建对象，而是在指针不可互转的地方**换一个指向**。
</details>

### 律师级

**谜题 7**

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

**UB**。`p` 是尾后指针，不指向任何对象，经由它**不可到达**任何字节（[[basic.compound#8]] 只对"指向对象的指针"定义可到达性）。`std::launder` 的前提要求结果可到达的字节（`x.b` 的 4 个字节）都能经由实参到达，不满足，于是违反前置条件（库 UB）。这正是可到达性规则要保护的优化：一个从 `x.a` 派生的指针，永远碰不到 `x.b`。要拿 `x.b` 的指针，写 `&x.b`，或者从**指向 `x` 的指针**出发。
</details>

**谜题 8**

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

按当前措辞，进入 `if` 时**有定义**，返回 `10`——这与上面 `&x + 1` 的例子形成对照。

[[expr.reinterpret.cast#5]]：整数值 `n + sizeof(int)` 能由指针值转换得到（`&x + 1` 和 `&y` 都转换成它），结果是"能让程序有定义行为的指针值中未指定的一个"。选指向 `y` 的指针能让 `*p = 10` 合法，所以抽象机就选它。通过**指针算术**做不到的事（尾后指针永远不指向 `y`），通过**整数往返**却可以——这是天使般选择的直接推论。

工程上不要这样写：`inttoptr` 的出身语义正是编译器错误优化报告的高发区，"标准允许"和"所有编译器都正确实现"之间还有距离。
</details>

## 小结

| 问题 | 去哪层找答案 | 关键条款 |
|---|---|---|
| 内存还在吗？ | 存储 / 存续期 | [[basic.stc]]、[[basic.compound#6]] |
| 那里有没有对象？是什么类型？ | 对象 | [[intro.object#1]]、[[intro.object#13]] |
| 对象活着吗？ | 生命周期 | [[basic.life#2]]、[[basic.life#7]]、[[basic.life#8]] |
| 值能读吗？ | 值 | [[basic.indet]] |
| 我的指针指向它吗？ | 指针值 | [[basic.compound#3]]、[[basic.compound#7]]、[[expr.static.cast#12]] |
| 能通过这个类型访问它吗？ | 访问 | [[basic.lval#11]]，见 [[topics/type-punning]] |
| 旧指针会自动指向新对象吗？ | 透明替换 | [[basic.life#9]]、[[basic.life#10]] |
| 不会怎么办？ | `std::launder` | [[ptr.launder]] |

!!! summary
    - **存储、对象、生命周期、指针值是四件事**。绝大多数"看起来没问题"的 UB，都是把其中两层混为一谈：把"有内存"当成"有对象"，把"地址相同"当成"指向同一对象"。
    - **对象只有五个来源**；`reinterpret_cast`、写入、`launder` 都不在其中。C++20 的隐式对象创建让 `malloc`/`memcpy` 式代码合法，但只对隐式生存期类型、只在特定操作中发生。
    - **指针值记得自己指向谁**：尾后指针不指向相邻对象，指针算术困在自己的数组里，`reinterpret_cast` 只有在指针可互转时才改变指向。
    - **`std::launder` 只换指向，不造对象**；C++20 之后它主要用于字节缓冲区和 const/基类子对象被替换的场景。保存 placement new 的返回值往往是更简单的替代。
