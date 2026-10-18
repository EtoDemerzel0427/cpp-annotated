---
title: 作用域
summary: C++23 起的作用域模型：作用域如何嵌套、声明栖居于哪个作用域、目标作用域与名字绑定、声明何时对应与潜在冲突、各种声明的声明点（locus），以及块、函数形参、lambda、命名空间、类、枚举、模板形参、契约断言八种作用域。
status: done
covers: *
papers: P1787R6, P2169R4, P0847R7
related: basic.pre, basic.lookup, basic.link, basic.def.odr, dcl.meaning, temp.local, class.member.lookup
tags: 作用域, 名字查找, 声明, 重载
updated: 2026-10-17
---

[basic.scope] 回答两个问题：

1. 一个声明把名字放到了哪里？也就是它栖居（inhabit）在哪个作用域、目标作用域（target scope）是哪个、名字绑定（bound）到哪个作用域。名字查找（[[basic.lookup]]）随后就在这些作用域里按绑定关系查找。
2. 两个声明什么时候说的是同一个东西，什么时候会冲突？**对应**（correspond）、**对应重载**（corresponding overloads）、**潜在冲突**（potentially conflict）这几个概念决定了重声明、重载和重定义错误。

这一节在 C++23 由 P1787R6（"Declarations and where to find them"）完全重写。旧模型用声明区（declarative region）和潜在作用域（potential scope）描述名字在哪段程序文本中有效，并靠大量特例来补充。新模型把作用域本身当作一棵树上的节点，声明栖居在节点上，查找从某个程序点出发沿着树向外进行。读过 C++20 及以前标准的读者要特别注意：今天说的 scope 是程序的一个**区域**（region），不再是一个名字的有效范围。

阅读本节前需要了解 [[basic.pre]]（名字、声明、实体）。

## 作用域的基本模型（[basic.scope.scope] ¶1）

¶1 规定，程序中的声明出现在许多**作用域**（scope）中，作用域一般是**不连续的**（discontiguous）。例如同一个命名空间可以在多处打开，类的成员函数可以在类外定义，这些部分都属于同一个作用域。

- **全局作用域**（global scope）包含整个程序。
- 其他每个作用域 S 都由出现在另一个作用域中的某个声明、*parameter-declaration-clause*、语句、*handler*、*lambda-expression* 或契约断言引入，那个作用域因此**包含**（contains）S。
- 对于某个程序点，包含它的任一作用域都是它的**外围作用域**（enclosing scope），其中最小的叫**直接作用域**（immediate scope）。
- 设 S 是一个不包含程序点 P 的作用域。如果作用域 X 是 S 或包含 S，但 X 不包含 P，就说 X **介于**（intervene）P 与 S 之间。

介于其间这个概念乍看抽象，用处却很具体：[[basic.def.odr#10]] 用它判断局部变量能否在 lambda、局部类中使用；[[basic.scope.block#2]] 用它判断块里的声明是否与外层冲突。直观地说，从 S 内部向外走到 P 所在的位置，所要跨过的那些作用域边界，就是介于其间的作用域。

```cpp
void f(int n) {     // n 栖居于 f 的函数形参作用域 F
  struct A {        // 类作用域 C
    void g() {      // g 的函数形参作用域 G，函数体是块作用域 B
      n;            // 程序点 P 在 B 中。对 F 而言：G、C 都包含 P……
    }
  };
}
```

反过来看，[[basic.def.odr#10]] 问的是：从引入实体 `n` 的地方到使用它的作用域之间，有哪些介于其间的作用域。这里从 `n` 所在的 F 一路向里走到 `g` 的函数体，依次进入 f 的函数体块、C、G、B。C 和 G 不是块作用域，所以 `n` 在 `g` 中不是 odr-usable 的，`n = 2;` 这类用法非良构。

## 父作用域、栖居、目标作用域、绑定（¶2）

¶2 规定，除非另有规定：

- **¶2.1** 包含作用域 S 的最小作用域是 S 的**父作用域**（parent scope）。
- **¶2.2** 没有两个声明（重新）引入同一个实体。
- **¶2.3** 声明**栖居**（inhabit）在其 **locus**（声明点，[[basic.scope.pdecl]]）处的直接作用域。
- **¶2.4** 声明的**目标作用域**（target scope）就是它栖居的作用域。
- **¶2.5** 声明（重新）引入的名字在其目标作用域中被**绑定**（bound）到该声明。

另外两个派生概念：

- 声明的**宿主作用域**（host scope）：如果它栖居的是块作用域，就是那个块作用域；否则是它的目标作用域。
- 如果 S 是某个实体的某个声明的目标作用域，就说该实体**属于**（belongs to）作用域 S。

关键在于“除非另有规定”。默认情况下，栖居的作用域、目标作用域和绑定名字的作用域三者相同，所有的复杂情况都在例外里。Note 1 列出了这些例外：

| ¶ | 例外 | 例子 |
|---|---|---|
| 2.6 | 模板形参作用域只做其他模板形参作用域的父作用域 | 见 [[basic.scope.temp]] |
| 2.7 | 具有适当链接的对应声明声明同一实体（推翻 ¶2.2） | 两个 TU 中的 `extern int x;`（[[basic.link]]） |
| 2.8 | *template-declaration* 中的 *declaration* 栖居于与 *template-declaration* 相同的作用域 | `template<class T> void f();` 中 `f` 栖居在命名空间作用域，而非模板形参作用域 |
| 2.9 | 友元声明、模板特化的声明不绑定名字；带限定名的声明以指定的作用域为目标；其他友元声明和某些 *elaborated-type-specifier* 以更大的外围作用域为目标 | `friend void h();` 声明的是外围命名空间的 `h`，但不能直接用 `h` 找到（除非通过 ADL） |
| 2.10 | 块作用域的 `extern` 声明或函数声明以更大的外围作用域为目标，但在直接作用域中绑定名字 | `void f() { void g(); }`：`g` 属于外围命名空间，名字 `g` 只在这个块中可见 |
| 2.11 | 无作用域枚举的枚举项名字绑定在两个最内层外围作用域中 | `enum E { a };` 的 `a` 同时在 E 的枚举作用域和外围作用域 |
| 2.12 | 类名也绑定在它自己的作用域里 | 注入类名 |
| 2.13 | 匿名联合体的成员名字绑定在联合体的父作用域中 | `union { int i; float f; };` 后可以直接用 `i` |

把栖居、目标、绑定三者拆开，好处就在这里：旧标准要为每个特例写一段话，新模型只需说明这个声明栖居在 X，目标作用域是 Y，名字绑定在 Z。

```cpp run ok
namespace X {
  void p() {
    void q();     // 栖居于 p 的块作用域；目标作用域是 X（¶2.10）；名字 q 绑定在 p 的块作用域
    q();          // OK：在块作用域中找到
  }
  void r() {
    // q();       // error: q 的名字没有绑定在 X 中，这里找不到
  }
  void q() { }    // 这是同一个 X::q 的定义（目标作用域相同、对应 → 同一实体）
}
int main() { X::p(); }
```

## 对应的对象形参与签名（¶3）

¶3 为下一段的对应重载做准备，定义了两个辅助概念。

两个非静态成员函数在下列情况下有**对应的对象形参**（corresponding object parameters）：

- **¶3.1** 恰好一个是没有引用限定符的隐式对象成员函数，且两者的对象形参类型在去掉引用后相同；或
- **¶3.2** 它们的对象形参类型相同。

成员函数模板的情形（¶3.3–¶3.4）与此相同，只是把相同换成等价。

如果两个函数模板的模板形参列表长度相同、对应的模板形参等价、非对象形参类型列表与返回类型（如果有）等价，并且在都是非静态成员时有对应的对象形参，它们就有**对应的签名**（corresponding signatures）。

¶3.1 规定，恰好一个没有引用限定符时忽略引用。这条规则是为 C++23 的显式对象形参（deducing this，P0847R7）设计的。没有引用限定符的 `void f() const;` 的隐式对象形参类型视为 `const X&`，但它既能绑定左值又能绑定右值，所以它和 `void f(this const X&)`、`void f(this const X&&)` 都对应，不能共存。

## 声明何时对应（¶4）

¶4 规定，如果两个声明引入（或重新引入）相同的名字，或都声明构造函数，或都声明析构函数，它们就**对应**（correspond），除非：

- **¶4.1** 其中一个是 *using-declarator*；或
- **¶4.2** 一个声明类型（不是类型别名），另一个声明变量、非静态数据成员（匿名联合体的除外）、枚举项、函数或函数模板；或
- **¶4.3** 都声明函数或函数模板，但不是对应重载。

两个函数或函数模板声明在下列情况下是**对应重载**（corresponding overloads）：

- **¶4.4** 都声明函数，非对象形参类型列表相同（脚注 14：隐式对象形参不算在形参类型列表中），尾随 *requires-clause*（如果有）等价，且如果都是非静态成员，有对应的对象形参；或
- **¶4.5** 都声明函数模板，签名对应，*template-head* 等价，尾随 *requires-clause*（如果有）等价。

对应是整个声明匹配机制的核心。它的意思是，**这两个声明占据的是同一个名字下的同一个位置**：

- 对应且声明同一实体，就是重声明（[[basic.link#8]]）；
- 对应但声明不同实体，就是潜在冲突（¶6），通常是错误；
- 不对应，就可以共存（重载、类型与变量同名等）。

¶4.2 解释了所谓的 stat hack。C 语言允许 `struct stat` 和函数 `stat` 同名共存（POSIX 就是这么用的），C++ 为了兼容保留了这一点：类型和变量或函数不对应，所以可以同名；查找时非类型名字优先（[[basic.lookup.general#4]]）。

```cpp run ok
struct stat { int size; };
int stat(const char*, struct stat*);   // 类型与函数同名：不对应，合法
int main() {
  struct stat s{};                     // 用 elaborated-type-specifier 才能指类型
  return s.size;
}
```

Note 2 指出，即使两个声明都不绑定名字，也可能对应：

```cpp run ok
struct A {
  friend void f();      // #1：友元声明，不绑定名字，目标是全局命名空间
};
struct B {
  friend void f() {}    // 对应 #1，并定义它
};
int main() { }
```

下面加了注释的 Example 2 展示了如何判断对应重载：

```cpp error
typedef int Int;
enum E : int { a };
void f(int);                    // #1
void f(Int) {}                  // 定义 #1：形参类型列表相同（Int 就是 int）
void f(E) {}                    // OK：E 与 int 是不同类型，另一个重载

struct X {
  static void f();
  void f() const;               // error: 重声明——非对象形参类型列表都为空；一静一非静，
                                //   "都是非静态成员才比较对象形参"不适用 → 对应
  void g();
  void g() const;               // OK：对象形参类型 X& vs const X& 不同
  void g() &;                   // error: 重声明——与 void g(); 对应（¶3.1：恰好一个无引用限定符，去引用后都是 X）

  void h(this X&, int);
  void h(int) &&;               // OK：对象形参 X& vs X&&，都有"引用"，类型不同 → 另一个重载
  void j(this const X&);
  void j() const &;             // error: 重声明——对象形参都是 const X&
  void k();
  void k(this X&);              // error: 重声明——k() 无引用限定符，去引用后与 X& 相同
};
```

关于静态成员函数那一行：¶4.4 中“如果都是非静态成员，有对应的对象形参”的条件，在一个静态、一个非静态时不适用，于是只比较非对象形参类型列表。两者都为空，所以对应；又因为它们是两个不同的实体，所以冲突。不能仅凭 static 来重载，规范依据就在这里（[[over.load]]）。

!!! note "为什么 `void g() &;` 不能和 `void g();` 共存"
    这是 C++11 引入引用限定符时就有的规则（[[over.load]] 曾经单独规定不能混用有无引用限定符的重载），在新模型里可以由 ¶3.1 直接得出：无引用限定符的隐式对象成员函数既能通过左值调用，也能通过右值调用，它与任何 `&` 或 `&&` 版本都有重叠。

## 名字无关声明 `_`（¶5）{{c++26}}

¶5 规定，名字为 `_`（U+005F）的声明，如果它声明的是下列之一，就是**名字无关的**（name-independent）：

- **¶5.1** 具有自动存储期的变量（函数形参除外）；
- **¶5.2** 没有 *storage-class-specifier* 且不栖居于命名空间作用域的结构化绑定；
- **¶5.3** 结果绑定（[[dcl.contract.res]]）；
- **¶5.4** *init-capture* 引入的变量；
- **¶5.5** 非静态数据成员（匿名联合体的除外）。

*推荐做法*：实现不应对名字无关声明是否被使用发出警告。

这是 C++26 的占位符变量特性（P2169R4，"A nice placeholder with no name"）。许多代码需要一个不关心其名字的变量，如 `auto [_, value] = map.insert(...)`、`std::lock_guard _(m);`。以前每个这样的变量都得起不同的名字，否则就是重定义；现在 `_` 可以在同一作用域中重复声明。

## 潜在冲突（¶6）

¶6 规定，如果两个声明对应，并且使它们共同的名字指代不同的实体（[[basic.link]]），它们就**潜在冲突**（potentially conflict）。如果在任一作用域中，一个名字绑定到两个潜在冲突的声明 A 和 B，且 A 先于（precedes，[[basic.lookup.general]]）B，那么除非 B 是名字无关声明，否则程序非良构。

!!! std
    The program is ill-formed if, in any scope, a name is bound to two declarations A and B that potentially conflict and A precedes B, unless B is name-independent.

这一条统一了以前分散在各处的重定义、不同种类的符号、冲突的声明等错误。Note 3 指出，在同一作用域中又引入同名声明之前，可以使用只命名唯一一个名字无关声明的 *id-expression*（[[basic.lookup.general]]）。Note 4 指出，重载决议可能会考虑在多个作用域中找到的潜在冲突声明（例如通过 using 指令或运算符函数找到的），这时通常是二义的。

下面是加了注释的 Example 3：

```cpp error
void f() {
  int x,y;
  void x();             // error: x 对应 int x，但指代不同实体
  int y;                // error: 重定义（两个不同的变量）
}
enum { f };             // error: ::f 已是函数，枚举项 f 对应它（¶4.2 只豁免"类型 vs 其他"）
namespace A {}
namespace B = A;
namespace B = A;        // OK：两个别名的底层实体相同 → 同一实体，无冲突
namespace B = B;        // OK：同上
namespace A = B;        // OK（按标准）：名字 A 两次都指代命名空间 A
namespace B {}          // error: B 是别名（底层实体是 A），这里却声明一个新命名空间 B

void g() {
  int _;
  _ = 0;                // OK：唯一的 _
  int _;                // OK：名字无关声明，不冲突
  _ = 0;                // error: 查找集中有两个非函数声明 → 二义
}
void h () {
  int _;                // #1
  _ ++;                 // OK
  static int _;         // error: static 变量不是名字无关声明，与 #1 冲突
}
```

!!! impl "Clang 对 `namespace A = B;` 的处理"
    截至写作时，本机 Clang 23 对 `namespace A = B;` 这一行报 "redefinition of 'A'"。按当前草案，名字 A 的两个声明都指代命名空间 A（别名指代其底层实体，[[basic.pre#8]]），并没有使名字指代不同的实体，所以不潜在冲突，标准例子也明确标注为 OK。这是 Clang 尚未跟进的地方。其余各行 Clang 的判定与标准一致。

注意 `int _; int _;` 的语义：第二个 `_` 并不隐藏第一个，两者都存在，都在生命周期内（析构时逆序销毁），只是这个名字不能再无歧义地使用了。这对 RAII 很有用：

```cpp run ok
#include <mutex>
std::mutex m1, m2;
int main() {
  std::lock_guard _(m1);
  std::lock_guard _(m2);   // C++26：两个锁都持有到作用域结束，按声明逆序释放
}
```

## 可提名（¶7）

¶7 规定，如果一个声明先于程序点 P、不栖居于块作用域，并且其目标作用域是类、类模板或命名空间 E 所关联的作用域，或者（当 E 是命名空间时）是 E 的内联命名空间集中的任一元素（[[namespace.def]]），那么这个声明在 P 处于 E 中是**可提名的**（nominable）。

可提名描述的是能否用限定名 `E::name` 去声明或重声明（[[dcl.meaning]] 用它判断类外定义能否匹配）。下面是 Example 4：

```cpp
namespace A {
  void f() {void g();}
  inline namespace B {
    struct S {
      friend void h();
      static int i;
    };
  }
}
```

在例子末尾，`f`、`B`、`S`、`h` 的声明在 A 中可提名；`g`（栖居于块作用域）和 `i`（目标作用域是 S 的类作用域，不是 A）不可提名。`h` 虽然是在类中声明的友元，但它的目标作用域是最内层外围命名空间，也就是 `B`；而 `B` 是 `A` 的内联命名空间，所以 `h` 在 A 中可提名。

## 模板实例化中的作用域（¶8）

¶8 规定，实例化模板化实体时，模板定义的任何部分引入的作用域 S，视为由实例化出来的实体引入，并包含栖居于 S 的声明的实例化。这样，实例化后的类或函数有自己的作用域就有了明确的表述：`A<int>` 的成员栖居于 `A<int>` 的类作用域，而不是主模板的作用域。

## 声明点（[basic.scope.pdecl]）

**locus**（声明点）决定一个声明从程序的哪一点开始先于后续代码，也就是名字从哪里开始能被查找到。总的原则是，**声明在其声明符完整之后才生效**。这样初始化器能看到新名字（`int x = sizeof(x);`），而声明符本身（例如数组边界）看到的仍是外层的同名实体。

### 声明符（¶1–¶2）

¶1 规定，对于由声明符构成的声明，其 locus 紧跟在完整的声明符之后，也就是在初始化器之前。

```cpp ub
unsigned char x = 12;
void f() {
  unsigned char x = x;     // UB: 初始化器中的 x 是正在声明的 x 本身，而不是 ::x
}
```

内层 `x` 用它自己（尚未初始化的值）来初始化。初始化器在对象的生命周期之外访问它（[[basic.life]]），这是未定义行为。Clang 会警告 "variable 'x' is uninitialized when used within its own initialization"。

¶2（注）指出，在隐藏外层名字的声明的 locus 之前，外层的名字仍然可见：

```cpp run ok
const int i = 2;
void a() {
  int i[i];                                  // 数组边界里的 i 仍是外层的 const int i = 2
  static_assert(sizeof i == 2 * sizeof(int));
}
int main() { a(); }
```

在 `int i[i]` 中，声明符 `i[i]` 尚未完整，内层 `i` 还没有生效，所以边界中的 `i` 找到的是外层的常量。这里有一个细微的对比：`int x = x;` 的 locus 在 `=` 之前，`int i[i];` 的 locus 在 `]` 之后。

### 其他各种声明的 locus

| ¶ | 声明 | locus | 推论 |
|---|---|---|---|
| 1 | 声明符 | 完整声明符之后 | 初始化器中可见；声明符内不可见 |
| 3 | *class-specifier* | *class-head* 中的 identifier / *simple-template-id* 之后 | 基类列表、类体中都能用类名（`struct Node { Node* next; };`） |
| 3 | *enum-specifier* | *enum-head* 之后 | 枚举项初始化器中可用枚举名 |
| 3 | *opaque-enum-declaration* | 声明之后 | |
| 3 | *alias-declaration* | 声明之后 | `using T = T;` 右边的 T 是外层的 T |
| 4 | *using-declarator*（不命名构造函数） | 之后 | |
| 5 | *enumerator-definition* | 之后 | 自己的初始化器看不到自己 |
| 7 | 作为声明的 *elaborated-type-specifier* | 之后 | |
| 8 | 注入类名 | 类定义左花括号之后 | |
| 9 | 函数局部预定义变量（`__func__`） | 函数体之前 | |
| 10 | 结构化绑定 | *identifier-list* 之后 | 初始化器中可见（但被禁止引用，[[dcl.struct.bind]]） |
| 11 | 范围 for 的 *for-range-declaration* | *for-range-initializer* 之后 | `for (auto x : x)` 右边是外层的 x |
| 11 | 展开语句的 *for-range-declaration* {{c++26}} | *expansion-initializer* 之后 | |
| 12 | *template-parameter* | 之后 | |
| 13 | *result-name-introducer* {{c++26}} | 之后 | |
| 14 | *concept-definition* | *concept-name* 之后 | |
| 15 | 有 identifier 的 *namespace-definition* | identifier 之后 | |

下面挑几个值得细看的。

**¶5 枚举项**：locus 在 *enumerator-definition* 之后，所以枚举项自己的初始化器看到的是外层的同名实体：

```cpp run ok
const int x = 12;
void b() {
  enum { x = x };          // 右边的 x 是外层常量 12
  static_assert(x == 12);
}
int main() { b(); }
```

**¶11 范围 for**：locus 在 *for-range-initializer* 之后。与普通声明符相反，循环变量在初始化器中不可见。所以 `for (auto x : x)` 这种用同名变量遍历的写法是合法的（虽然不推荐）：

```cpp run ok
#include <vector>
std::vector<int> x = {1, 2, 3};
int main() {
  int s = 0;
  for (int x : x) s += x;   // 冒号右边的 x 是全局 vector
  return s - 6;
}
```

**¶10 结构化绑定**：locus 在 *identifier-list* 之后，所以初始化器中这些名字已经可见；[[dcl.struct.bind]] 进一步禁止初始化器引用它们：

```cpp error
struct P { int a, b; };
P p{1, 2};
void sb() {
  auto [p, q] = p;          // error: 初始化器中的 p 是正在声明的结构化绑定，而不是全局 p
}
```

**¶12 模板形参**：

```cpp run ok
typedef unsigned char T;
template<class T
  = T               // 查找到的是 typedef 名 ::T（模板形参 T 的 locus 在其声明之后）
  , T               // 查找到的是模板形参 T
    N = 0> struct A { };
static_assert(sizeof(A<int>) == 1);
int main() { }
```

**¶14 概念**：locus 在 *concept-name* 之后，于是约束表达式中外层的同名实体被隐藏。Note 3 指出，约束表达式不能使用这个 *concept-name*，因为概念在其定义完成之前不能用来构成可检查的约束。Clang 对 `template<class T> concept C = C<T>;` 报 "a concept definition cannot refer to itself"。

**¶6（注）类成员**：类成员声明之后，即使类还不完整，也能在类作用域中找到该成员名：

```cpp run ok
struct X {
  enum E { z = 16 };
  int b[X::z];          // OK：z 已声明，虽然 X 还不完整
};
int main() { }
```

**¶16（注）友元与块作用域 extern**：友元声明可以引入属于最近外围命名空间或块作用域的函数或类，但不在任何地方绑定名字（[[class.friend]]）。块作用域的函数声明和 `extern` 变量声明，声明的是属于最近外围命名空间的实体，但不在命名空间中绑定名字。

**¶17（注）**：模板的实例化点由 [[temp.point]] 规定，那是另一套规则。

## 块作用域（[basic.scope.block]）

¶1 规定，下列每一种都引入一个**块作用域**（block scope），其范围包括该语句或 *handler*：

- 选择语句（`if`、`switch`）、迭代语句（`while`、`do`、`for`、范围 `for`）、展开语句（`template for` {{c++26}}）；
- 上述语句的子语句；
- *handler*（`catch (...) { }`）；
- 复合语句，但 *handler* 的复合语句除外。

Note 1 指出，一个既是子语句又是块的东西只有一个作用域（例如 `while (c) { ... }` 的 `{ ... }` 既是子语句也是复合语句，但只算一个块作用域）。属于块作用域的变量称为**块变量**（block variable）。

为什么选择语句和迭代语句本身也引入作用域？这是为了让 `for (int i = 0; ...)`、`if (int x = f())`、`if (auto p = get(); p)` 中声明的变量在语句结束后就消失：

```cpp run ok
int i = 42;
int a[10];
int main() {
  for (int i = 0; i < 10; i++)   // 这个 i 属于 for 语句的块作用域
    a[i] = i;
  int j = i;                     // j = 42：for 的 i 已不可见
  return j - 42;
}
```

为什么 *handler* 的复合语句不另起作用域？这样 `catch (E e) { int e; }` 中的两个 `e` 就在同一作用域中，直接冲突，异常声明与 handler 体内的声明因此不能同名。

¶2 规定，如果一个非名字无关的声明在下列某个块作用域 S 中绑定名字：

- **¶2.1** *lambda-expression*、*function-body* 或 *function-try-block* 的 *compound-statement*；
- **¶2.2** 选择、迭代或展开语句的子语句（它本身不是选择、迭代或展开语句）；
- **¶2.3** *function-try-block* 的 *handler*；

并且它与某个目标作用域为 S 的父作用域的声明潜在冲突，程序就非良构。

这一条把冲突检查从同一作用域扩展到父子两层，目的是防止函数体最外层的声明悄悄隐藏形参，防止 `if`/`for` 体的最外层隐藏条件里声明的变量。这种隐藏几乎总是 bug：

```cpp error
int f();
void t1() {
  if (int x = f()) {
    int x;            // error: 与 if 条件中的 x 潜在冲突（¶2.2）
  } else {
    int x;            // error: 同上
  }
}
void t2(int p) {
  int p = 1;          // error: 函数体最外层与形参冲突（¶2.1：父作用域是函数形参作用域）
}
void t3(int p) try { } catch (...) {
  int p = 0;          // error: function-try-block 的 handler 与形参冲突（¶2.3）
}
void t4() {
  for (int i = 0; i < 3; ++i) {
    { int i = 5; (void)i; }   // OK：嵌套的块不受 ¶2 约束，正常隐藏
  }
}
```

注意 ¶2 只看直接的父作用域，再往里套一层块就是合法的隐藏。

## 函数形参作用域（[basic.scope.param]）

¶1 规定，*parameter-declaration-clause* P 引入一个**函数形参作用域**（function parameter scope），它包括 P。Note 1 指出，函数形参的值不能在 *parameter-declaration-clause* 中使用（[[dcl.fct.default]]），但它的名字可以在不求值上下文中使用。

这个作用域延伸到哪里，取决于 P 关联的是什么：

- **¶1.1** 普通函数声明符（`declarator-id` 后跟形参列表）：延伸到最近的外围 *init-declarator*、*member-declarator*、*parameter-declaration* 的声明符、*nodeclspec-function-declaration* 或 *function-definition* 的末尾，但不包括关联声明符的 locus。Note 2：成员函数的形参作用域嵌套在类作用域之内。
- **¶1.2** *lambda-declarator*：延伸到 lambda 的 *compound-statement* 末尾。
- **¶1.3** *requirement-parameter-list*：延伸到 *requires-expression* 的 *requirement-body* 末尾。
- **¶1.4** *deduction-guide*：延伸到推导指引末尾。

按 ¶1.1，作用域延伸到 *function-definition* 末尾，这意味着形参在尾置返回类型、*requires-clause*、*noexcept-specifier* 和函数体中都可见。成员函数的形参作用域嵌套在类作用域之内，这意味着类外定义的成员函数在形参列表和函数体中可以直接使用类的成员名。

```cpp error
auto tr(int n) -> decltype(n) { return n; }   // OK：尾置返回类型中可用形参
void d1(int a, int b = sizeof(a));            // OK：不求值操作数
void d2(int a, int b = a);                    // error: 默认实参中使用形参的值
template<class T> void g(T t) noexcept(noexcept(t.swap(t)));  // OK
```

## lambda 作用域（[basic.scope.lambda]）

*lambda-expression* E 引入一个 **lambda 作用域**（lambda scope），它从 E 的 *lambda-introducer* 之后开始，延伸到 E 的 *compound-statement* 末尾。

*init-capture* 栖居于 lambda 作用域（[[expr.prim.lambda.capture#6]]）。lambda 作用域从 *lambda-introducer* 之后开始，所以它包含 lambda 的形参列表、尾置返回类型和函数体，但不包含捕获列表本身之前的部分。由此可以推出：

- init-capture 的名字在 lambda 的形参列表、返回类型、函数体中都可见，`[i = 0]() mutable -> decltype(i) { return i++; }` 是合法的。
- init-capture 的初始化器中出现的同名名字指外层实体。[[expr.prim.lambda.capture]] 的 Note 2 说，`x = std::move(x)` 这种写法能工作正是因为这一点，第二个 `x` 必须绑定到外围上下文中的声明。
- 形参与 init-capture 同名是错误。在 `[a = 42](int a) { }` 中，形参与 init-capture 引入的变量同名，二者冲突。

在 odr-usable 的判断中，lambda 作用域起到门的作用（[[basic.def.odr#10]]）：外层的局部实体只有在声明了相应捕获时，才能跨过它被 odr-use。

```cpp run ok
int main() {
  int p = 1;
  auto l = [p = p + 1] { return p; };   // 内层 p 是 init-capture（值 2），初始化器中的 p 是外层变量
  auto c = [i = 0]() mutable -> decltype(i) { return i++; };  // 返回类型中可用 init-capture
  return l() - 2 + c();
}
```

## 命名空间作用域（[basic.scope.namespace]）

¶1 规定，命名空间 N 的任一 *namespace-definition* 引入一个**命名空间作用域**（namespace scope），它包括 N 的每一个 *namespace-definition* 的 *namespace-body*。此外，对于目标作用域是该作用域（或包含于该作用域）的每个非友元重声明或特化，其 *declarator-id*、*class-head-name* 或 *enum-head-name* 之后的部分也包括在该作用域中。全局作用域就是全局命名空间的命名空间作用域。

关键在后半句：**在命名空间外定义时，声明的后半部分属于目标命名空间的作用域**。所以在 `void N::f() { ... }` 的函数体中，可以不加限定地使用 N 的其他成员：

```cpp run ok
namespace Q {
  namespace V { void f(); }
  void V::f() {         // declarator-id V::f 之后的部分属于 V 的作用域
    void h();           // 声明的是 Q::V::h
  }
}
int main() { }
```

## 类作用域（[basic.scope.class]）

¶1 规定，类或类模板 C 的任一声明引入一个**类作用域**（class scope），它包括 C 的 *class-specifier* 的 *member-specification*（如果有）。同样，对于目标作用域是该作用域（或包含于该作用域）的每个非友元重声明或特化，其 *declarator-id*、*class-head-name* 或 *enum-head-name* 之后的部分也包括在内。在类外定义成员函数时，函数体能直接使用成员名，原因就在这里。

Note 1 指出，从类的 *class-specifier* 之前的程序点进行查找，在类作用域中找不到任何绑定。下面是 Example 1：

```cpp error
template<class D>
struct B {
  D::type x;            // #1
};

struct A { using type = int; };
struct C : A, B<C> {};  // error at #1: C::type not found
```

`B<C>` 作为基类在 `C` 的基类列表中实例化，此时 `C` 的类体（包括从 A 继承来的 `type`）还不在此前。基类列表位于 *class-specifier* 之中，但 `C` 的成员（包括通过继承的成员查找）在这一点还不可用，所以找不到 `C::type`。在 CRTP 中，不能在基类模板的声明部分使用派生类的成员，原因就在这里；在成员函数体中则可以使用，因为那是完整类上下文（[[class.mem]]）。

## 枚举作用域（[basic.scope.enum]）

¶1 规定，枚举 E 的任一声明引入一个**枚举作用域**（enumeration scope），它包括 E 的 *enum-specifier* 的 *enumerator-list*（如果有）。

枚举项栖居于枚举作用域。有作用域枚举（`enum class`）的枚举项名字只绑定在这里，所以必须写 `E::a`；无作用域枚举的枚举项名字同时绑定在枚举作用域和外围作用域（¶2.11 的特例），所以 `a` 和 `E::a` 都可以用。

## 模板形参作用域（[basic.scope.temp]）

¶1 规定，每个模板模板形参（*type-tt-parameter*、*variable-tt-parameter*、*concept-tt-parameter*）引入一个模板形参作用域，它包括该模板形参的 *template-head*。（所以 `template<template<class U> class TT>` 中的 `U` 只在 TT 自己的模板头里有效。）

¶2 规定，每个 *template-declaration* D 引入一个**模板形参作用域**（template parameter scope），它从 *template-parameter-list* 开始，延伸到 *template-declaration* 末尾。在 *template-parameter-list* 之外、本应栖居于该作用域的声明，改为栖居于与 D 相同的作用域。对于任何不是模板形参作用域的作用域 S，其父作用域是包含 S 且不是模板形参作用域的最小作用域。

Note 1 指出，因此只有模板形参属于模板形参作用域，也只有模板形参作用域才会以模板形参作用域为父作用域。

这样绕开模板形参作用域，是因为在 `template<class T> struct A { ... };` 中，`A` 显然应该是外围命名空间的成员，而不是模板形参作用域的成员；`A` 的类作用域的父作用域也应该是命名空间作用域。但查找时从类体内向外走，仍然要能找到 `T`，所以 [[basic.lookup.unqual]] 专门处理了经过模板形参作用域的情况。

模板形参名不能在其作用域内被重声明（[[temp.local]]）：

```cpp error
template<class T> struct A { int T; };          // error: 成员 T 遮蔽模板形参
template<class T> void ff(T) { int T = 0; }     // error: 同上
template<class T> struct S2 { void m(); };
template<class U> void S2<U>::m() { }           // OK：类外定义可以换用别的形参名
```

## 契约断言作用域（[basic.scope.contract]）{{c++26}}

¶1 规定，每个契约断言（[[basic.contract]]，即 `pre(...)`、`post(...)`、`contract_assert(...)`）C 引入一个**契约断言作用域**（contract-assertion scope），它包括 C。

¶2 规定，设一个非名字无关的 *result-name-introducer*（[[dcl.contract.res]]，即 `post(r: ...)` 中的 `r`）所在的后置条件关联于函数 F。如果它与目标作用域为下列之一的声明潜在冲突，程序非良构：

- **¶2.1** F 的函数形参作用域；或
- **¶2.2** 若关联于 *lambda-declarator*，则是该后置条件最近的外围 lambda 作用域。

```cpp
int f(int x) post(r: r > x);    // OK：结果绑定 r
int g(int r) post(r: r > 0);    // error: 结果名 r 与形参 r 冲突
auto l = [r = 1](int) post(r: r > 0) { return 1; };  // error: 与 init-capture r 冲突（lambda 作用域）
```

（截至写作时，本机 Clang 23 尚不支持契约语法，以上按标准判定，未经编译器验证。）

为什么契约断言要有自己的作用域？结果名 `r` 必须只在那个 `post(...)` 中可见，不能泄漏到函数体里。同时，[[basic.def.odr#10]] 把契约断言作用域列为可以直接穿过的作用域，所以断言里能直接使用函数形参。C++23 及以前没有契约，也就没有这种作用域。

## 实现视角

!!! impl "编译器怎么表示作用域"
    - 在 Clang 的 AST 中，作用域大致对应两种结构：解析期的 `Scope` 对象（随解析进出，用于未限定查找）和语义层的 `DeclContext`（命名空间、类、函数、枚举、lambda 闭包类等）。标准中栖居、目标、绑定的三分法，在 Clang 里体现为声明的词法上下文（lexical DeclContext）与语义上下文（semantic DeclContext）可以不同。例如类外定义的成员函数，词法上在命名空间里，语义上属于类。块作用域的 `extern` 声明、友元声明也靠这种区分实现。
    - 潜在冲突在 Clang 的诊断中有多种措辞，如 "redefinition of 'x'"、"redefinition of 'x' as different kind of symbol"、"class member cannot be redeclared"，它们对应的是同一条标准规则。
    - `-Wshadow`（GCC/Clang）对合法的隐藏给出警告（局部变量隐藏外层变量、形参或成员），标准并不禁止这些隐藏。

## 历史与演进

!!! history "从声明区到作用域树"
    - **C++98–C++20**：用声明区（declarative region）和潜在作用域（potential scope）来描述。每个名字在声明区的一部分中有效，作用域是潜在作用域减去被隐藏的部分。各种特例（类外定义、友元、块作用域 extern、注入类名、模板形参等）各有一段文字。
    - **C++23**：P1787R6 引入今天的模型。作用域是程序的区域，构成一棵树；声明栖居于某个作用域，以某个作用域为目标，在某个作用域绑定名字；对应和潜在冲突统一了重声明与冲突的判断；先于（precedes）取代了“在……之后声明”的说法，以兼容模块的可达性。同为 C++23 特性的显式对象形参（P0847R7）也纳入了对应的对象形参（¶3）。
    - **C++26**：名字无关声明 `_`（P2169R4）；契约断言作用域；展开语句（`template for`）的块作用域与 locus；结果绑定。

## 陷阱

!!! pitfall "`int x = x;` 不是用外层 x 初始化"
    locus 在声明符之后、初始化器之前，所以右边的 `x` 就是正在声明的变量本身。读取它是 UB（对自动变量而言，这是在生命周期开始前访问）。如果想用外层的 `x`，应写 `::x` 或者换个名字。

!!! pitfall "范围 for 中的 locus 与普通声明相反"
    与 `int x = x;` 相反，`for (auto x : x)` 中右边的 `x` 是外层的。两者的 locus 规则恰好相反。

!!! pitfall "函数体最外层不能重新声明形参，嵌套块却可以"
    `void f(int p) { int p; }` 是错误的，`void f(int p) { { int p; } }` 则是合法的隐藏。¶2 只检查直接的父子关系。

## 思考题

!!! question "思考题 1"
    下面哪些行非良构？

    ```cpp
    struct S {
      void a() &;
      void a() &&;
      void b();
      void b(this S);
      void c(this S&);
      void c() &&;
      static void d(int);
      void d(double);
    };
    ```

<details markdown="1">
<summary>答案</summary>

- `a() &` 与 `a() &&`：都有引用限定符，¶3.1 不适用；对象形参 `S&` 与 `S&&` 类型不同，所以不对应，OK。
- `b()` 与 `b(this S)`：`b()` 没有引用限定符，按 ¶3.1 去掉引用后比较 `S` 与 `S`，两者相同，所以对象形参对应；非对象形参类型列表都为空，所以是对应重载。结果是 **error**（重声明，且两者是不同的实体）。
- `c(this S&)` 与 `c() &&`：`c() &&` 有引用限定符，¶3.1 不适用；`S&` 与 `S&&` 不同，OK。
- `d(int)` 与 `d(double)`：非对象形参类型列表不同，所以不对应，OK（只要形参列表不同，静态与非静态成员函数可以重载）。
</details>

!!! question "思考题 2"
    ```cpp
    const int n = 3;
    void f() {
      int n[n] = {};
      int m = sizeof(n);
      enum { n2 = n };   // ?
    }
    ```
    `m` 的值是多少？`enum { n2 = n }` 合法吗？

<details markdown="1">
<summary>答案</summary>

在 `int n[n]` 中，数组边界中的 `n` 是外层常量 3（locus 在完整声明符之后），所以声明的是 `int[3]`。此后 `n` 指代这个数组，`sizeof(n) == 3 * sizeof(int)`，在 `int` 为 4 字节的平台上 `m` 是 12。`enum { n2 = n }` 中的 `n` 是那个局部数组，数组不是整型常量表达式，不能作为枚举项的初始化器，所以非良构。
</details>

## 小结

| 概念 | 要点 |
|---|---|
| 作用域 | 程序的区域，形成树；可以不连续 |
| 栖居 / 目标 / 绑定 | 默认三者相同；块作用域 extern、友元、无作用域枚举项、匿名联合体成员、注入类名是例外 |
| [[g:correspond|对应]] | 同名（或同为构造/析构），排除 using-declarator、类型 vs 非类型、非对应重载的函数 |
| 对应重载 | 非对象形参类型列表相同、requires-clause 等价、对象形参对应（模板还要求签名对应、模板头等价） |
| [[g:potentially-conflict|潜在冲突]] | 对应且指代不同实体，非良构（`_` 除外） |
| [[g:locus]] | 声明符之后（初始化器之前）；类名在 class-head 之后；枚举项在定义之后；范围 for 在初始化器之后 |
| 块作用域 | 函数体最外层不能重声明形参；if/for 体最外层不能重声明条件变量 |
| 八种作用域 | 块、函数形参、lambda、命名空间、类、枚举、模板形参、契约断言 |
