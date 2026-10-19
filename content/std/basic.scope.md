---
title: 作用域
summary: 作用域是程序中的一段区域；本页讲声明从哪一点开始生效、名字被放进哪个作用域，以及两个同名声明什么时候是重声明、什么时候构成重载、什么时候冲突。
status: done
covers: *
papers: P1787R6, P2169R4, P0847R7
related: basic.pre, basic.lookup, basic.lookup.unqual, basic.link, basic.def.odr, dcl.meaning, temp.local, class.member.lookup
tags: 作用域, 名字查找, 声明, 重载
updated: 2026-10-19
---

!!! tldr
    - 作用域是程序文本中的一段区域，作用域互相嵌套成一棵树。名字查找从使用处出发，沿这棵树向外找。
    - 声明从它的声明点开始生效。变量的声明点在完整声明符之后、初始化器之前，所以 `int x = x;` 右边的 `x` 是它自己；范围 `for` 的声明点在冒号右边的表达式之后，所以 `for (int x : x)` 右边的 `x` 是外层的。
    - 同一作用域里的两个同名声明，要么声明同一个实体（重声明），要么构成重载，要么冲突。判断依据是对应与潜在冲突两个概念。
    - 函数体最外层不能重新声明形参，`if`、`for` 体的最外层不能重新声明条件里的变量；再套一层块就可以。
    - C++26 起，局部变量、结构化绑定等可以反复命名为 `_` 而不冲突。

## 作用域是一段程序区域 [basic.scope.scope]

```cpp
int a;                          // 全局作用域
namespace N {                   // N 的命名空间作用域
  struct S {                    // S 的类作用域
    void f(int p) {             // f 的函数形参作用域，p 在这里
                                // 函数体是一个块作用域
      for (int i = 0; i < p; ++i) {  // for 语句的块作用域，i 在这里
        int k = i;              // 循环体又是一个块作用域
      }
    }
  };
}
```

¶1 程序中的声明出现在一个个**作用域**（scope）里。**全局作用域**（global scope）包含整个程序；其他每个作用域都由另一个作用域中的某个声明、形参列表、语句、`catch` 子句、lambda 表达式或契约断言引入，引入它的那个作用域就**包含**（contains）它。于是所有作用域组成一棵树，根是全局作用域。

作用域一般是不连续的。同一个命名空间可以在多处打开，成员函数可以在类外定义，这些片段都属于同一个作用域。

对程序中的某个位置，包含它的作用域都叫它的**外围作用域**（enclosing scope），其中最小的叫它的**直接作用域**（immediate scope）。上例中 `int k` 处的直接作用域是循环体的块作用域。

C++ 一共有八种作用域，后文逐一说明：

| 作用域 | 由什么引入 | 详见 |
|---|---|---|
| 块作用域 | 复合语句；`if`、`switch`、循环语句及其子语句；`catch` 子句 | [[basic.scope.block]] |
| 函数形参作用域 | 形参列表 | [[basic.scope.param]] |
| lambda 作用域 | lambda 表达式 | [[basic.scope.lambda]] |
| 命名空间作用域 | 命名空间定义；全局作用域也属于这一种 | [[basic.scope.namespace]]、[[basic.scope.class]] |
| 类作用域 | 类定义 | [[basic.scope.class]] |
| 枚举作用域 | 枚举定义 | [[basic.scope.enum]] |
| 模板形参作用域 | 模板声明 | [[basic.scope.temp]] |
| 契约断言作用域 {{c++26}} | `pre`、`post`、`contract_assert` | [[basic.scope.contract]] |

### 介于其间的作用域

¶1 最后定义了一个关系。设作用域 S 不包含程序点 P，如果作用域 X 是 S 或包含 S，但不包含 P，就说 X **介于**（intervene）P 与 S 之间。直观地说，从 S 出发一层层向外走，直到碰到一个包含 P 的作用域为止，途中经过的作用域（包括 S 自己）都介于其间。

这个概念主要用来判断能否在某处使用外层函数的局部变量（[[g:odr-usable]]，[[basic.def.odr#10]]）：

```cpp run error
void f(int n) {
  struct L {
    int g() { return n; }       // error
  };
  auto h = [] { return n; };    // error
  auto k = [=] { return n; };   // OK
}
```

从 `g` 的函数体向外走到包含 `n` 的作用域，途中经过 `g` 的函数体、`g` 的函数形参作用域、`L` 的类作用域和 `f` 的函数体。规则只允许介于其间的是块作用域、契约断言作用域、lambda 或 requires 表达式的形参作用域，或者捕获了该变量的 lambda 的 lambda 作用域。类作用域和普通函数的形参作用域都不在其列，所以 `g` 不能使用 `n`；`h` 没有捕获 `n`，也不能使用；`k` 用 `[=]` 捕获，可以。

## 声明从哪里开始生效 [basic.scope.pdecl]

每个声明都有一个**声明点**（[[g:locus]]，locus）。名字查找只能找到声明点在使用处之前的声明（精确的说法见 [[basic.lookup#2|先于]]）。对变量、函数这类以声明符构成的声明，声明点规定如下。

¶1 声明点紧跟在完整的声明符之后，也就是在初始化器之前。

<div class="compare" markdown="1">

```cpp ub
unsigned char x = 12;
void f() {
  unsigned char x = x;
  // 右边的 x 是正在声明的 x
}
```

```cpp run ok
const int i = 2;
void g() {
  int i[i];
  // 方括号里的 i 是外层的 i
  static_assert(sizeof i
                == 2 * sizeof(int));
}
```

</div>

左边，内层 `x` 的声明点在 `=` 之前，初始化器里的 `x` 就是内层 `x` 自己。此时它的生命期还没有开始，读取它是未定义行为（[[basic.life]]）。这不属于 C++26 的错误行为：错误行为针对的是生命期已经开始、只是还没有初始化的变量（[[basic.indet]]）。Clang 对这一行给出 `-Wuninitialized` 警告。

¶2 右边，声明符 `i[i]` 写到 `]` 才完整，方括号里的 `i` 还找不到内层的 `i`，只能找到外层的常量 2。这是一条注：外层的名字在隐藏它的声明的声明点之前一直可见。

### 其他声明的声明点（¶3–¶15）

| 段 | 声明 | 声明点 | 推论 |
|---|---|---|---|
| 3 | 类定义 | 类头中的类名之后 | 基类列表和类体中都能用类名：`struct Node { Node* next; };` |
| 3 | 枚举定义 | 枚举头之后 | 枚举项的初始化器中可以用枚举名 |
| 3 | 不透明枚举声明、别名声明 | 整个声明之后 | `using T = T;` 右边的 `T` 是外层的 `T` |
| 4 | using 声明符（不指名构造函数） | 它之后 | |
| 5 | 枚举项定义 | 它之后 | 枚举项自己的初始化器看不到自己 |
| 7 | 作为声明的详述类型说明符（`struct X;`） | 它之后 | |
| 8 | 注入类名（类名在自己类中的那份绑定） | 类定义的左花括号之后 | |
| 9 | `__func__` | 函数体之前 | |
| 10 | 结构化绑定 | 方括号中的名字列表之后 | 初始化器中已经可见，但不允许引用（[[dcl.struct.bind]]） |
| 11 | 范围 `for` 和展开语句 {{c++26}} 的循环变量 | 冒号右边的表达式之后 | `for (int x : x)` 右边的 `x` 是外层的 |
| 12 | 模板形参 | 它之后 | |
| 13 | 后置条件的结果名 {{c++26}} | 它之后 | |
| 14 | 概念定义 | 概念名之后 | |
| 15 | 带名字的命名空间定义 | 名字之后 | |

枚举项与普通变量正好相反，它的声明点在整个定义之后：

```cpp run ok
const int x = 12;
void b() {
  enum { x = x };          // 右边的 x 是外层常量 12
  static_assert(x == 12);
}
int main() { b(); }
```

范围 `for` 也是这样。循环变量在冒号右边不可见，所以用同名变量遍历是合法的，虽然不值得推荐：

```cpp run ok
#include <vector>
std::vector<int> x = {1, 2, 3};
int main() {
  int s = 0;
  for (int x : x) s += x;   // 冒号右边的 x 是全局的 vector
  return s - 6;
}
```

结构化绑定的声明点在名字列表之后，初始化器里的同名名字因此指向正在声明的绑定，而 [[dcl.struct.bind]] 禁止这样引用：

```cpp error
struct P { int a, b; };
P p{1, 2};
void sb() {
  auto [p, q] = p;   // error: 初始化器中的 p 是正在声明的绑定
}
```

模板形参在自己的默认实参里还不可见，在后面的形参里已经可见：

```cpp run ok
typedef unsigned char T;
template<class T
  = T               // 外层的 typedef ::T
  , T               // 模板形参 T
    N = 0> struct A { };
static_assert(sizeof(A<int>) == 1);
int main() { }
```

¶14 概念名的声明点在概念名之后，所以概念的约束表达式会把外层的同名实体隐藏掉；注 3 又规定约束表达式不能使用这个概念名，概念不能递归定义。Clang 对 `template<class T> concept C = C<T>;` 报告 concept definition cannot refer to itself。

¶6 类的成员一经声明，就能在类作用域中找到，即使类还没有定义完：

```cpp run ok
struct X {
  enum E { z = 16 };
  int b[X::z];          // OK：z 已经声明
};
int main() { }
```

¶16 是一条注，重申后文的两种特殊情况：友元声明可以引入属于外层命名空间或块作用域的函数或类，但不在任何地方绑定名字（[[class.friend]]）；块作用域中的函数声明和 `extern` 变量声明，引入的实体属于最近的外层命名空间，名字却不绑定在那个命名空间中。

## 声明放进哪个作用域：栖居、目标与绑定

```cpp run ok
namespace X {
  void p() {
    void q();     // 声明的是 X::q，但名字 q 只在 p 的函数体里能找到
    q();          // OK
  }
  void r() {
    // q();       // error: 这里找不到 q
  }
  void q() { }    // 定义同一个 X::q
}
int main() { X::p(); }
```

块里的 `void q();` 声明的函数属于命名空间 `X`，名字却只在这个块里能找到。要描述这类情况，标准把一个声明和作用域的关系拆成三件事。

¶2 除非另有规定：

- ¶2.1 包含作用域 S 的最小作用域是 S 的**父作用域**（parent scope）；
- ¶2.2 两个声明不会（重新）引入同一个实体；
- ¶2.3 声明**栖居**（[[g:inhabit]]）于它的声明点处的直接作用域；
- ¶2.4 声明的**目标作用域**（[[g:target-scope]]）就是它栖居的作用域；
- ¶2.5 声明引入的名字在它的目标作用域中**绑定**（bound）到它。

此外，声明栖居于块作用域时，它的**宿主作用域**（host scope）就是那个块作用域，否则是它的目标作用域。如果作用域 S 是某个实体的某个声明的目标作用域，就说这个实体**属于**（belongs to）S。

默认情况下，栖居、目标和绑定是同一个作用域。所有复杂情况都是例外，注 1 列出了它们：

| 条目 | 例外 | 例子 |
|---|---|---|
| 2.6 | 模板形参作用域只做其他模板形参作用域的父作用域 | 见 [[basic.scope.temp]] |
| 2.7 | 具有适当链接的对应声明声明同一实体 | 两个翻译单元中的 `extern int x;`（[[basic.link]]） |
| 2.8 | 模板声明里的那个声明栖居于模板声明所在的作用域 | `template<class T> void f();` 中的 `f` 栖居于命名空间作用域 |
| 2.9 | 友元声明和模板特化的声明不绑定名字；带限定名的声明以限定名指定的作用域为目标；其他友元声明和某些详述类型说明符以更外层的作用域为目标 | `friend void h();` 声明外层命名空间的 `h`，但普通查找找不到它，只有 ADL 能找到 |
| 2.10 | 块作用域的 `extern` 声明和函数声明以更外层的作用域为目标，名字却绑定在直接作用域中 | 上例的 `void q();` |
| 2.11 | 无作用域枚举的枚举项名字绑定在最内层的两个外围作用域中 | `enum E { a };` 之后，`a` 和 `E::a` 都能用 |
| 2.12 | 类名也绑定在类自己的作用域中 | [[g:injected-class-name]] |
| 2.13 | 匿名联合体成员的名字绑定在联合体的父作用域中 | `union { int i; float f; };` 之后可以直接用 `i` |

## 同名声明：重声明、重载还是冲突

```cpp run ok
typedef int Int;
enum E : int { a };
void f(int);        // #1
void f(Int) {}      // 定义 #1：Int 就是 int
void f(E) {}        // 另一个重载：E 和 int 是不同的类型
int main() {}
```

同一个作用域里出现两个同名声明，结果有三种：它们声明同一个实体（重声明），它们是同一个名字下的不同重载，或者它们冲突而使程序非良构。标准用**对应**（[[g:correspond]]）和**潜在冲突**（[[g:potentially-conflict]]）两个概念来判断。

### 对应（¶4）

¶4 如果两个声明（重新）引入相同的名字，或者都声明构造函数，或者都声明析构函数，它们就**对应**，除非：

- ¶4.1 其中一个是 using 声明符；
- ¶4.2 一个声明类型（不是类型别名），另一个声明变量、非静态数据成员（匿名联合体的除外）、枚举项、函数或函数模板；
- ¶4.3 两个都声明函数或函数模板，但不是对应重载。

两个函数声明是**对应重载**（corresponding overloads），条件是：

- ¶4.4 两者的形参类型列表相同（不计对象形参，脚注 14），尾随 requires 子句（如果有）等价，如果都是非静态成员函数，对象形参还要对应（见下）；
- ¶4.5 函数模板则要求签名对应、模板头等价、尾随 requires 子句等价。

对应的意思是，两个声明占据同一个名字下的同一个位置。于是：

- 对应且声明同一实体，就是重声明（[[basic.link#8]]）；
- 对应但声明不同实体，就是潜在冲突（见下文），程序非良构；
- 不对应，就可以共存，例如形参不同的重载。

¶4.2 来自对 C 的兼容。C 允许结构体 `stat` 和函数 `stat` 同名共存，POSIX 正是这么用的。在 C++ 里类型和函数不对应，所以可以同名；查找时非类型的名字优先（[[basic.lookup#4]]），要指类型必须写 `struct stat`：

```cpp run ok
struct stat { int size; };
int stat(const char*, struct stat*);   // 类型与函数同名，合法
int main() {
  struct stat s{};
  return s.size;
}
```

注 2 指出，即使两个声明都不绑定名字，也可以对应：

```cpp run ok
struct A {
  friend void f();      // #1：不绑定名字，目标是全局命名空间
};
struct B {
  friend void f() {}    // 与 #1 对应，并定义它
};
int main() { }
```

### 成员函数的对象形参（¶3）

非静态成员函数还要比较对象形参，也就是 `*this` 的类型。C++23 的显式对象形参（`this X& self`，[[P0847R7]]）让这件事变得复杂，于是第 3 段专门作了定义。

¶3 两个非静态成员函数在下列情况下有**对应的对象形参**（corresponding object parameters）：

- ¶3.1 恰好一个是没有引用限定符的隐式对象成员函数，并且两者的对象形参类型去掉引用之后相同；
- ¶3.2 两者的对象形参类型相同。

成员函数模板的规则（第 3.3、3.4 项）相同，只是把相同换成等价。两个函数模板的模板形参列表长度相同、对应的模板形参等价、非对象形参类型列表和返回类型等价，并且是成员时对象形参对应，就说它们有**对应的签名**（corresponding signatures）。

第 3.1 项为什么要去掉引用？没有引用限定符的 `void g();`，左值和右值对象都能调用，它与 `&` 版本、`&&` 版本都有重叠，所以不能与任何一个共存。下面是标准的例 2，加了注释：

```cpp error
struct X {
  static void f();
  void f() const;          // error: 重声明
  void g();
  void g() const;          // OK：对象形参 X& 与 const X& 不同
  void g() &;              // error: 与 g() 对应

  void h(this X&, int);
  void h(int) &&;          // OK：X& 与 X&& 不同
  void j(this const X&);
  void j() const &;        // error: 都是 const X&
  void k();
  void k(this X&);         // error: 与 k() 对应
};
```

- `f`：一个静态、一个非静态，第 4.4 项中比较对象形参的条件只适用于两者都是非静态成员的情况，于是只比较非对象形参，两者都为空，所以对应。它们是两个不同的实体，因而冲突。不能只靠 `static` 重载，依据就在这里（[[over.load]]）。
- `g() &`：`g()` 没有引用限定符，按第 3.1 项去掉引用后两者都是 `X`，对应。
- `h`：两个都带引用，第 3.1 项不适用；`X&` 与 `X&&` 不同，不对应。
- `k(this X&)`：`k()` 没有引用限定符，去掉引用后同为 `X`，对应。

### 潜在冲突（¶6）

¶6 如果两个声明对应，并且使它们共同的名字指代不同的实体，它们就**潜在冲突**。

!!! std
    The program is ill-formed if, in any scope, a name is bound to two declarations A and B that potentially conflict and A precedes B ([basic.lookup]), unless B is name-independent.

在任何作用域中，如果一个名字绑定到两个潜在冲突的声明，程序就非良构，除非后一个是名字无关声明（见下一节）。重定义、同名不同种类的符号、冲突的声明，都是这一条。标准的例 3：

```cpp error
void f() {
  int x,y;
  void x();             // error: x 对应 int x，但指代不同实体
  int y;                // error: 重定义
}
enum { f };             // error: 枚举项 f 与函数 ::f 对应
namespace A {}
namespace B = A;
namespace B = A;        // OK：两次都指命名空间 A
namespace B = B;        // OK：同上
namespace A = B;        // OK：名字 A 两次都指命名空间 A
namespace B {}          // error: B 是 A 的别名，这里却声明新的命名空间 B
```

`enum { f }` 出错，是因为第 4.2 项只豁免类型与非类型的组合，枚举项和函数都不是类型。

!!! impl "Clang 拒绝 `namespace A = B;`"
    本机 Clang 23 对 `namespace A = B;` 报告 redefinition of 'A'。按当前草案，别名指代它的底层实体（[[basic.pre#8]]），名字 `A` 的两个声明都指命名空间 `A`，不潜在冲突，标准例子也标为 OK。这一行是 Clang 与标准不一致的地方，其余各行 Clang 的判定与标准一致。

注 4 提醒，经由 using 指令或运算符查找，可能从不同作用域找到潜在冲突的声明，这时它们会一起进入重载决议，结果通常是二义的。

### 名字无关声明 `_`（¶5）{{c++26}}

```cpp run ok
#include <mutex>
std::mutex m1, m2;
int main() {
  std::lock_guard _(m1);
  std::lock_guard _(m2);   // 两个锁都持有到作用域结束
}
```

很多变量只为了副作用而存在，名字无关紧要，例如上面的锁、`auto [_, ok] = s.insert(v);` 中不需要的部分。C++26 之前，同一作用域中的每个这样的变量都得起不同的名字（[[P2169R4]]）。

¶5 名字是 `_` 的声明，如果声明的是下列之一，就是**名字无关的**（name-independent）：

- ¶5.1 自动存储期的变量，函数形参除外；
- ¶5.2 结构化绑定，不带存储类说明符，也不栖居于命名空间作用域；
- ¶5.3 后置条件的结果绑定（[[dcl.contract.res]]）；
- ¶5.4 init-capture 引入的变量；
- ¶5.5 非静态数据成员，匿名联合体的成员除外。

按第 6 段，后声明的那个是名字无关声明时不算冲突。两个 `_` 都存在，都活到作用域结束，按声明的逆序销毁；只是名字 `_` 此后不能再无歧义地使用（注 3）：

```cpp error
void g() {
  int _;
  _ = 0;                // OK：只有一个 _
  int _;                // OK：名字无关声明
  _ = 0;                // error: 两个 _，查找有二义
}
void h() {
  int _;                // #1
  _++;                  // OK
  static int _;         // error: 静态变量不是名字无关声明，与 #1 冲突
}
```

¶5 还有一条建议：实现不应对名字无关声明是否被使用发出警告。

## 块作用域 [basic.scope.block]

¶1 下列每一种都引入一个**块作用域**（block scope），范围就是它自己：

- ¶1.1 选择语句（`if`、`switch`）、循环语句、展开语句（`template for` {{c++26}}）；
- ¶1.2 这些语句的子语句；
- ¶1.3 `catch` 子句（handler）；
- ¶1.4 复合语句，但 `catch` 子句的复合语句除外。

注 1 补充，一个子语句如果本身就是复合语句，只算一个块作用域。属于块作用域的变量叫**块变量**（block variable）。

选择语句和循环语句本身也引入作用域，所以 `for (int i = 0; ...)`、`if (auto p = get(); p)` 中声明的变量在语句结束时就消失了：

```cpp run ok
int i = 42;
int a[10];
int main() {
  for (int i = 0; i < 10; i++)   // 这个 i 属于 for 语句的块作用域
    a[i] = i;
  int j = i;                     // j == 42：for 的 i 已经不可见
  return j - 42;
}
```

`catch` 子句的复合语句不另起作用域，因此 `catch (E e) { int e; }` 里的两个 `e` 在同一个作用域中，直接冲突。

### 不能在最外层重新声明（¶2）

¶2 在下列块作用域 S 中，如果一个声明（不是名字无关声明）与目标作用域为 S 的父作用域的某个声明潜在冲突，程序非良构：

- ¶2.1 lambda、函数体或函数 try 块的复合语句；
- ¶2.2 选择、循环、展开语句的子语句，且这个子语句本身不是选择、循环或展开语句；
- ¶2.3 函数 try 块的 `catch` 子句。

普通的隐藏是允许的，这一条专门禁止三种隐藏：函数体最外层隐藏形参，`if`、`for` 体最外层隐藏条件里的变量，函数 try 块的 `catch` 隐藏形参。这些隐藏几乎都是笔误：

```cpp error
int f();
void t1() {
  if (int x = f()) {
    int x;            // error: 与条件中的 x 冲突
  } else {
    int x;            // error: 同上
  }
}
void t2(int p) {
  int p = 1;          // error: 函数体最外层与形参冲突
}
void t3(int p) try { } catch (...) {
  int p = 0;          // error: 函数 try 块的 catch 与形参冲突
}
void t4() {
  for (int i = 0; i < 3; ++i) {
    { int i = 5; (void)i; }   // OK：再套一层块，正常隐藏
  }
}
```

这一条只看直接的父作用域，再往里套一层块就是合法的隐藏。

## 函数形参作用域 [basic.scope.param]

¶1 每个形参列表引入一个**函数形参作用域**（function parameter scope）。它延伸到哪里，取决于形参列表属于什么：

- ¶1.1 普通函数的声明符：延伸到整个声明或函数定义的末尾，但不包括这个声明符自己的声明点。注 2 补充，成员函数的形参作用域嵌套在类作用域之内；
- ¶1.2 lambda：延伸到 lambda 函数体的末尾；
- ¶1.3 requires 表达式的形参列表：延伸到 requires 表达式的末尾；
- ¶1.4 推导指引：延伸到推导指引的末尾。

所以形参在尾置返回类型、requires 子句、`noexcept` 说明符和函数体中都可见。注 1 提醒，形参列表里不能使用形参的值（[[dcl.fct.default]]），但可以出现在不求值的操作数里：

```cpp error
auto tr(int n) -> decltype(n) { return n; }   // OK：尾置返回类型中可用形参
void d1(int a, int b = sizeof(a));            // OK：不求值操作数
void d2(int a, int b = a);                    // error: 默认实参使用了形参的值
template<class T> void g(T t) noexcept(noexcept(t.swap(t)));  // OK
```

## lambda 作用域 [basic.scope.lambda]

lambda 表达式引入一个 **lambda 作用域**（lambda scope），它从方括号括起的捕获部分（lambda-introducer）之后开始，到函数体末尾结束。整个捕获列表，包括 init-capture 的初始化器，都在 lambda 作用域之外；但 [[expr.prim.lambda.capture#6]] 专门规定，init-capture 声明的变量栖居于 lambda 作用域。由此可以推出：

- init-capture 的初始化器里出现的同名名字指外层的实体，`[x = std::move(x)]` 能工作就是因为这一点；
- init-capture 的名字在形参列表、返回类型和函数体中都可见；
- 形参与 init-capture 同名会冲突，`[a = 42](int a) { }` 非良构。

```cpp run ok
int main() {
  int p = 1;
  auto l = [p = p + 1] { return p; };  // 初始化器里的 p 是外层变量，l() == 2
  auto c = [i = 0]() mutable -> decltype(i) { return i++; };
  return l() - 2 + c();
}
```

lambda 作用域也是判断能否使用外层局部变量的关口（见上文介于其间的作用域）：只有 lambda 捕获了某个局部变量，或者有默认捕获，这个变量才能在 lambda 里被 odr-use。

## 命名空间作用域与类作用域

¶1（[basic.scope.namespace]）一个命名空间的每个定义都引入同一个**命名空间作用域**（namespace scope），包括它所有定义的命名空间体。全局作用域就是全局命名空间的命名空间作用域。

¶1（[basic.scope.class]）类或类模板的每个声明都引入一个**类作用域**（class scope），包括类定义中的成员列表。

两条都有同样的后半句：如果一个重声明或特化（不是友元）的目标作用域是这个作用域或在它之内，那么这个声明中被声明的名字之后的部分也属于这个作用域。所以在类外或命名空间外定义成员时，函数名之后的形参列表、尾置返回类型和函数体都可以不加限定地使用那个类或命名空间的成员，而写在函数名之前的返回类型不行：

```cpp run ok
namespace Q {
  namespace V { void f(); }
  void V::f() {         // V::f 之后的部分属于 V 的作用域
    void h();           // 声明的是 Q::V::h
  }
}
struct S { using T = int; T get(); };
S::T S::get() {         // 返回类型在 S::get 之前，要写 S::T
  T t = 0;              // 函数体里直接用 T
  return t;
}
int main() { }
```

友元声明被排除在外，所以 `friend void A::f(F);` 中的 `F` 不会自动在 `A` 中查找；[[basic.lookup.unqual#6]] 为它单独作了规定。

类作用域只覆盖类定义里的成员列表。注 1 指出，从类定义之前的位置做查找，在类作用域中什么也找不到。标准的例 1：

```cpp error
template<class D>
struct B {
  D::type x;            // #1
};

struct A { using type = int; };
struct C : A, B<C> {};  // error at #1: C::type not found
```

`B<C>` 是在 `C` 的基类列表中被用到而实例化的，它的实例化点在 `C` 的定义之前（[[temp.point]]）。从那里查找 `C::type`，`C` 的类作用域里什么也找不到，从 `A` 继承来的 `type` 也一样。所以 CRTP 的基类模板不能在成员声明里使用派生类的成员。成员函数体可以，因为函数体在派生类定义完成之后才实例化。

## 枚举作用域 [basic.scope.enum]

¶1 每个枚举声明引入一个**枚举作用域**（enumeration scope），包括枚举定义中的枚举项列表。

枚举项都栖居于枚举作用域。有作用域枚举（`enum class`）的枚举项名字只绑定在这里，所以必须写 `E::a`；无作用域枚举的枚举项名字还绑定在外层作用域，所以 `a` 和 `E::a` 都能用。

## 模板形参作用域 [basic.scope.temp]

¶2 每个模板声明引入一个**模板形参作用域**（template parameter scope），从模板形参列表开始，到整个模板声明结束。

这个作用域有一点特殊。在 `template<class T> struct A { ... };` 中，`A` 显然应该是外层命名空间的成员，而不是模板形参作用域的成员；`A` 的类作用域的父作用域也应该是那个命名空间。所以第 2 段规定：

- 写在模板形参列表之外、本应栖居于模板形参作用域的声明，改为栖居于模板声明所在的作用域；
- 一个不是模板形参作用域的作用域，它的父作用域是包含它的、不是模板形参作用域的最小作用域。

注 1 总结，只有模板形参属于模板形参作用域，也只有模板形参作用域会以模板形参作用域为父作用域。从类体内向外查找时仍然要找到 `T`，[[basic.lookup.unqual]] 和 [[temp.local#7]] 专门规定了何时考虑模板形参作用域。

¶1 模板模板形参自己的形参列表也引入一个模板形参作用域，只覆盖它自己的模板头。`template<template<class U> class TT>` 中的 `U` 只在 `TT` 的模板头里有效。

模板形参的名字不能在它的作用域内重新声明（[[temp.local]]）：

```cpp error
template<class T> struct A { int T; };          // error: 成员 T 与模板形参同名
template<class T> void ff(T) { int T = 0; }     // error: 同上
template<class T> struct S2 { void m(); };
template<class U> void S2<U>::m() { }           // OK：类外定义可以换用别的形参名
```

## 契约断言作用域 [basic.scope.contract] {{c++26}}

¶1 每个契约断言（`pre(...)`、`post(...)`、`contract_assert(...)`，[[basic.contract]]）引入一个**契约断言作用域**（contract-assertion scope），范围就是这个断言。

后置条件可以给返回值起名字，如 `post(r: r > 0)` 中的 `r`。有了这个作用域，`r` 只在这个后置条件里可见，不会漏到函数体中。同时，契约断言作用域可以被穿过去使用外层的局部实体（[[basic.def.odr#10]]），所以断言里能直接用函数形参。

¶2 结果名如果不是名字无关的，又与下列作用域中的声明潜在冲突，程序非良构：

- ¶2.1 所属函数的函数形参作用域；
- ¶2.2 如果后置条件属于 lambda，则是最近的外围 lambda 作用域。

```cpp
int f(int x) post(r: r > x);    // OK
int g(int r) post(r: r > 0);    // error: 结果名 r 与形参 r 冲突
auto l = [r = 1](int) post(r: r > 0) { return 1; };  // error: 与 init-capture r 冲突
```

截至写作时本机 Clang 23 不支持契约语法，这段代码按标准分析，没有经过编译验证。

## 可提名（¶7）

¶7 在程序点 P，一个声明如果满足下面三条，就说它在类、类模板或命名空间 E 中是**可提名的**（nominable）：

- 它先于 P；
- 它不栖居于块作用域；
- 它的目标作用域是 E 的作用域；E 是命名空间时，也可以是 E 的内联命名空间集合中的某一个（[[namespace.def]]）。

可提名决定能否用 `E::name` 的形式重声明或在外部定义它（[[dcl.meaning]]）。标准的例 4：

```cpp run ok
namespace A {
  void f() {void g();}
  inline namespace B {
    struct S {
      friend void h();
      static int i;
    };
  }
}
int main() { }
```

例子末尾，`f`、`B`、`S`、`h` 的声明在 `A` 中可提名，`g` 和 `i` 不可提名。`g` 栖居于块作用域；`i` 的目标作用域是 `S` 的类作用域。`h` 虽然写在类里，但友元声明的目标是最近的外层命名空间 `B`，而 `B` 是 `A` 的内联命名空间。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶8（[basic.scope.scope]）实例化一个模板化实体时，模板定义中引入的作用域视为由实例化出的实体引入，并包含其中声明的实例化。例如 `A<int>` 的成员栖居于 `A<int>` 的类作用域。

¶17（[basic.scope.pdecl]）是一条注：模板的实例化点另由 [[temp.point]] 规定。

</details>

## 实现视角

!!! impl "编译器怎么表示作用域"
    - Clang 的 AST 用两种结构对应作用域：解析时随进随出的 `Scope` 对象，用于无限定查找；以及语义层的 `DeclContext`（命名空间、类、函数、枚举、lambda 的闭包类等）。一个声明的词法上下文和语义上下文可以不同，例如类外定义的成员函数词法上在命名空间里，语义上属于类。这对应标准中栖居与目标作用域的区分。
    - 潜在冲突在 Clang 中有好几种措辞，如 redefinition of 'x'、redefinition of 'x' as different kind of symbol、class member cannot be redeclared，它们对应的都是 [[basic.scope.scope#6]] 这一条。
    - `-Wshadow` 对合法的隐藏给出警告，例如局部变量隐藏外层变量或成员。标准并不禁止这些隐藏。

## 历史与演进

!!! history "从声明区到作用域树"
    - C++20 及以前，标准用声明区（declarative region）和潜在作用域（potential scope）描述名字在哪段文本中有效，作用域指的是名字的有效范围。类外定义、友元、块作用域 `extern`、注入类名、模板形参等特殊情况各有一段文字，彼此之间有不少漏洞。
    - C++23 由 [[P1787R6]] 改成今天的模型：作用域是程序的一段区域，构成一棵树；栖居、目标、绑定三者分开描述；对应与潜在冲突统一了重声明和冲突的判断。同一时期的显式对象形参（[[P0847R7]]）带来了对应的对象形参这一定义。
    - C++26 加入了名字无关声明 `_`（[[P2169R4]]）、契约断言作用域和展开语句。

## 常见误解

!!! pitfall "`int x = x;` 用外层的 x 初始化"
    声明点在声明符之后、初始化器之前，右边的 `x` 就是正在声明的变量本身，读取它是未定义行为。要用外层的变量，写 `::x` 或者换个名字。范围 `for` 恰好相反，`for (int x : x)` 右边的 `x` 是外层的。

!!! pitfall "函数体里不能隐藏形参"
    只有函数体的最外层不能。`void f(int p) { int p; }` 非良构，`void f(int p) { { int p; } }` 是合法的隐藏。

!!! pitfall "成员函数可以只靠 `static` 或引用限定符的有无来重载"
    `static void f();` 与 `void f() const;` 对应，不能共存；`void g();` 与 `void g() &;` 也不能共存。要按值类别重载，所有版本都必须带引用限定符。

## 思考题

!!! question "思考题 1"
    下面哪些成员声明非良构？

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

- `a() &` 与 `a() &&`：都有引用限定符，第 3.1 项不适用；`S&` 与 `S&&` 不同，不对应，OK。
- `b()` 与 `b(this S)`：`b()` 没有引用限定符，按第 3.1 项去掉引用后两者都是 `S`，对象形参对应；非对象形参都为空，所以是对应重载。它们是两个不同的实体，非良构。
- `c(this S&)` 与 `c() &&`：`c() &&` 有引用限定符，第 3.1 项不适用；`S&` 与 `S&&` 不同，OK。
- `d(int)` 与 `d(double)`：非对象形参不同，不对应，OK。

Clang 23 只对 `b(this S)` 报错。
</details>

!!! question "思考题 2"
    ```cpp
    const int n = 3;
    void f() {
      int n[n] = {};
      int m = sizeof(n);
      enum { n2 = n };
    }
    ```
    `m` 的值是多少？`enum { n2 = n }` 合法吗？

<details markdown="1">
<summary>答案</summary>

`int n[n]` 的声明点在完整声明符之后，方括号里的 `n` 是外层常量 3，声明的是 `int[3]`。此后 `n` 指这个数组，`m == 3 * sizeof(int)`，在 `int` 为 4 字节的平台上是 12。

`enum { n2 = n }` 中的 `n` 是那个局部数组，不是整型常量表达式，不能做枚举项的初始化器，所以非良构。
</details>
