---
title: 前言：名字、实体与变量
summary: 第 6 章的基础词汇：什么是名字、什么算声明、哪些东西是实体、什么是变量与局部实体，以及名字如何指代实体。
status: done
related: basic.def, basic.scope, basic.link, basic.lookup, dcl.struct.bind, dcl.contract.res
tags: 基本概念, 名字, 实体, 声明
updated: 2026-10-17
---

[basic.pre] 是整个第 6 章（[[basic]]）的词汇表。它不规定程序必须满足什么约束，只给出后面几百条规则要用到的几个最基础的名词：名字（name）、声明（declaration）、实体（entity）、变量（variable）、局部实体（local entity），以及动词指代（denote）。

为什么需要专门定义这些词？因为 C++ 的许多规则只对其中一类东西生效，而日常说法太含糊：

- 名字查找（[[basic.lookup]]）查的是名字。标号 `L:` 里的 `L` 不是名字，所以它不参与名字查找，也就不会和同名变量冲突。
- ODR（[[basic.def.odr]]）管的是可定义项，其中变量一项的边界完全由本节 ¶7 决定。非静态数据成员不是变量，所以对它谈不上 odr-use。
- lambda 捕获和 odr-usable（[[basic.def.odr#10]]）只针对局部实体。`static` 局部变量不是局部实体，所以 lambda 不捕获它也能使用。

读懂这一节，后面的条文才不会产生歧义。

## 本节在说什么（¶1–¶2）

¶1–¶2 都是注（note），没有规范效力。它们说明第 6 章介绍语言的基本概念，包括对象与名字的区别、值类别、声明与定义、类型、作用域、链接、存储期、程序的启动与终止、基础类型与复合类型；只影响语言某一部分的概念放到对应章节去讲。

## 什么是名字（¶3）

¶3 规定，**名字**（name）只有四种形式：

| 形式 | 例子 |
|---|---|
| *identifier* 记号 | `x`、`std`、`vector` |
| *conversion-function-id* | `operator int`、`operator bool` |
| *operator-function-id* | `operator+`、`operator()`、`operator new` |
| *literal-operator-id* | `operator""_km` |

但并不是所有 identifier 记号都是名字，以下三类不算（¶3.1.1–¶3.1.3）：

- 标号（*label*）的 identifier，以及 *literal-operator-id* 内部的那个后缀 identifier（`_km` 本身不是名字，整个 `operator""_km` 才是）；
- `goto` 后面的 identifier；
- *module-name*（如 `export module my.lib;` 里的 `my`、`lib`）和属性记号（如 `[[gnu::always_inline]]` 里的 `gnu`、`always_inline`）中的 identifier。

为什么要排除它们？因为它们各有自己的命名体系，不走普通的名字查找：标号只在函数内按标号规则匹配（[[stmt.label]]），模块名由模块系统解析（[[module.unit]]），属性记号由实现识别（[[dcl.attr.grammar]]）。把它们排除在名字之外，名字查找、作用域冲突、链接等规则就自然不适用于它们。

```cpp run ok
int f() {
  int x = 0;
x:                    // 标号的 identifier 不是名字：不与变量 x 冲突
  if (++x < 3) goto x;  // goto 后面的 x 也不是名字，不做名字查找
  return x;
}
int main() { return f() - 3; }
```

!!! note "关键字和宏名呢？"
    关键字不是 identifier 记号（[[lex.key]]），自然不是名字。宏名在预处理阶段就消失了（[[cpp.replace]]），翻译阶段 7 根本看不到它们。宏既不是名字也不是实体，ODR 管不到宏。不同 TU 用不同的 `-D` 选项编译同一个头文件，可能造成 ODR 违规却没有任何诊断，这就是原因之一（见 [[basic.def.odr]]）。

## 两个名字何时相同（¶4）

¶4 规定了两个名字在什么情况下**相同**（the same）：

- identifier：字符序列相同；
- *conversion-function-id*：所转换到的类型等价（[[temp.over.link]] 意义上的 equivalent），而不要求写法相同；
- *operator-function-id*：同一个运算符；
- *literal-operator-id*：同一个字面量后缀 identifier。

按第二条，在 `using I = int;` 之后，`operator I` 和 `operator int` 是同一个名字：

```cpp run ok
struct S { operator int() const { return 1; } };
using I = int;
int g(S s) { return s.operator I() + s.operator int(); }  // 同一个名字、同一个函数
int main() { return g({}) - 2; }
```

[[basic.scope.scope]] 判断两个声明是否对应（correspond）时，以名字相同为起点，进而决定重声明、冲突与重载。

## 声明引入名字（¶5）

¶5 规定每个名字都由一个**声明**（declaration）引入。这里的声明是语义上的概念，不是文法非终结符 *declaration*（Note 3 特意提醒了这一点）。它的完整清单是：

| ¶ | 声明的形式 | 例子 |
|---|---|---|
| 5.1 | *name-declaration*、*block-declaration*、*member-declaration* | `namespace N {}`、`using T = int;` |
| 5.2 | *init-declarator* | `int a = 1, *p;` 中的 `a = 1`、`*p` |
| 5.3 | 结构化绑定中的 identifier | `auto [x, y] = p;` 的 `x`、`y` |
| 5.4 | 后置条件 *result-name-introducer* 中的 identifier {{c++26}} | `post(r: r > 0)` 的 `r` |
| 5.5 | *init-capture* | `[n = 42]{}` 的 `n` |
| 5.6 | 带 *declarator* 的 *condition* | `if (int x = f())` |
| 5.7 | *member-declarator* | `struct S { int m : 3; };` 的 `m : 3` |
| 5.8 | *using-declarator* | `using std::swap;` |
| 5.9 | *parameter-declaration* | 函数形参、非类型模板形参 |
| 5.10–5.13 | *type-parameter* 以及三种模板模板形参 | `class T`、`template<class> class TT`，C++26 新增的变量模板形参和概念模板形参 |
| 5.14 | 引入名字的 *elaborated-type-specifier* | `struct Fwd*` |
| 5.15 | *class-specifier* | `struct S { };` |
| 5.16 | *enum-specifier*、*enumerator-definition* | `enum E { a };` |
| 5.17 | *exception-declaration* | `catch (std::exception& e)` |
| 5.18 | 隐式的注入类名声明 | 类 `S` 内部的 `S` |

Note 4 指出，范围 `for` 的 *for-range-declaration* 会被解释成上面的一种或多种（[[stmt.ranged]]）。

这张表列出了所有能引入名字的语法位置。后面的作用域规则（[[basic.scope.pdecl]] 的声明点）就是逐一为这些形式规定 locus 的。

!!! lawyer "一个声明可以不引入任何名字"
    ¶5 说每个名字都由某个声明引入，反过来却不成立。`static_assert(true);`、`;`（空声明）、`[[attr]];`、`using namespace std;`、显式实例化 `template class X<int>;` 都是声明，但不引入名字（[[basic.def#1]] 的 Note 1 列出了声明的这些其他效果）。

## 名字可能指代类型或模板（¶6）

¶6（注）指出，有些名字指代类型或模板。一般而言，遇到一个名字必须先查找它（[[basic.lookup]]），确定它是否指代这类实体，才能继续解析程序。C++ 文法**依赖上下文**（context-sensitive），根源就在这里：`a < b > c;` 是声明还是表达式，取决于 `a` 是不是模板名；`T * p;` 是乘法还是指针声明，取决于 `T` 是不是类型。在模板中，这个问题要推迟到实例化时才能回答，所以需要用 `typename` / `template` 消歧义（[[temp.res]]）。

## 变量（¶7）

¶7 规定，**变量**（variable）是由声明 D 引入的：

- 一个引用，但非静态数据成员除外；或
- 一个对象，

并且 D 不是模板形参的 *parameter-declaration*。

逐个排查：

| 声明 | 是变量吗 | 原因 |
|---|---|---|
| `int x;`（任意作用域） | 是 | 声明对象 |
| `static int s;`（类内） | 是 | 静态数据成员是对象的声明 |
| `int m;`（类内非静态） | **否** | 它是*非静态数据成员*，是独立的实体种类 |
| `int& r;`（类内非静态） | **否** | 是引用，但属于非静态数据成员（¶7.1 的排除） |
| `int& r = x;`（块作用域） | 是 | 引用也是变量 |
| `void f(int p)` 里的 `p` | 是 | 函数形参声明一个对象 |
| `template<int N>` 里的 `N` | **否** | 模板形参的 *parameter-declaration* 被排除 |
| `auto [a, b] = t;` 的 `a` | **否** | 结构化绑定是独立的实体种类；但这条声明另外引入了一个无名变量 `e`（[[dcl.struct.bind]]） |
| `[n = 1]{}` 的 `n` | **否**（是 *init-capture*） | ¶8 把 *init-capture* 单列为一种实体 |

为什么非静态数据成员不是变量？因为它不对应任何单独存在的存储。每个类对象里都有一份，成员本身只描述了偏移量和类型。所以 ODR 中变量必须有且只有一个定义的要求，以及 odr-use、存储期、链接等概念，对它都没有意义。静态数据成员正相反，它确实是整个程序里只有一个的对象。

为什么 `N` 不是变量？非类型模板形参在实例化中只是一个值（类类型时是一个模板形参对象，[[temp.param]]）。标量 NTTP 不能取地址，它没有存储。

## 实体与指代（¶8）

¶8 规定，**实体**（entity）是下面十五种之一：

> 变量、结构化绑定、结果绑定 {{c++26}}、函数、枚举项、类型、类型别名、非静态数据成员、位域、模板、命名空间、命名空间别名、模板形参、函数形参、*init-capture*。

有几样东西不是实体。对象不是实体：变量是实体，变量所声明的对象不是。值不是实体，表达式、语句、标号、宏、模块也都不是实体。这条边界在 C++26 静态反射中变得很重要。反射值（`std::meta::info`）可以表示实体，也可以表示值、对象、直接基类关系、数据成员描述等非实体的构造（[[basic.fundamental]]），所以 splice 规则（[[basic.splice]]）要分情况说明 designate 的是实体还是别的东西。

**底层实体**（underlying entity）：除非另有规定，实体的底层实体就是它自己。Note 6 指出，类型别名和命名空间别名的底层实体是它们所代表的类型或命名空间，与别名本身不同。

**指代**（denote）：一个名字指代的，是引入它的每个声明所声明的实体的底层实体。换句话说，名字总是穿透别名：

```cpp run ok
namespace very_long_name { int v = 1; }
namespace V = very_long_name;   // V 是命名空间别名（一个实体），其底层实体是 very_long_name
using I = int;                  // I 是类型别名，底层实体是 int

int main() {
  I i = V::v;   // 名字 V 指代的是 very_long_name，名字 I 指代的是 int
  return i - 1;
}
```

为什么要区分实体和底层实体？C++23 之前，标准对 typedef 名算不算实体说得含糊。现在别名本身也算作实体，于是它可以被声明、可以有作用域、可以被反射为一个独立的 `info` 值，`std::meta::dealias` 也才有意义。同时，名字指代底层实体这条规则保证别名在语义上是透明的，`I` 和 `int` 在类型系统里是同一个类型。[[basic.link#8]] 中两个别名声明的底层实体相同即为同一实体，[[basic.scope.scope#6]] 中 `namespace B = A; namespace B = A;` 不冲突，都依赖这个区分。

!!! lawyer "名字指代的是实体，而不是声明"
    一个名字可能由多个声明引入（如重载函数 `f(int)` 和 `f(double)` 都引入名字 `f`），这时名字指代每个声明所声明的实体。名字查找（[[basic.lookup]]）的结果是声明的集合，再由重载决议从中挑一个。所以在查找结束时，名字 `f` 指代哪个函数可能还没有唯一答案。

## 局部实体（¶9）

¶9 规定，**局部实体**（local entity）是：

- 具有自动存储期的变量（[[basic.stc.auto]]），包括块作用域的非 `static`、非 `thread_local`、非 `extern` 变量，以及函数形参；
- 结构化绑定，且其对应的变量（那个无名的 `e`）是上面这样的实体；
- 结果绑定（后置条件里的 `r`，[[dcl.contract.res]]）{{c++26}}；
- `*this` 对象（[[expr.prim.this]]）。

odr-usable（[[basic.def.odr#10]]）和 lambda 捕获（[[expr.prim.lambda.capture]]）的规则针对的就是局部实体：只有它们会遇到跨过 lambda、局部类或函数形参作用域后不能直接使用的问题。原因是它们的存储与某一次函数调用绑定在一起。局部类的成员函数、lambda 的函数体可能在另一次调用中执行，甚至在外层函数返回后才执行，那时并不存在确定的那一个 `n` 可供访问。静态存储期的变量在整个程序中只有一个，任何地方都能直接使用。

```cpp run ok
int g = 1;
void f(int n) {
  static int s = 2;
  auto l = [] { return g + s; };   // OK：g、s 不是局部实体，无需捕获
  // auto bad = [] { return n; };  // error: n 是局部实体，在 lambda 中 odr-use 却没有捕获
  (void)l; (void)n;
}
int main() { f(0); }
```

把 `*this` 列为局部实体，是为了让在 lambda 里使用成员需要捕获 `this` 这件事，与普通局部变量走同一套 odr-usable 规则（[[basic.def.odr#7]]、[[basic.def.odr#10]]）。

## 跨翻译单元的同名（¶10）

¶10 说，同一个名字用在多个翻译单元中时，是否指代同一个实体，取决于它在各 TU 中的**链接**（linkage）。这只是一句引子，具体规则在 [[basic.link]]：具有外部链接或模块链接的名字可以跨 TU 指代同一实体；具有内部链接的名字在每个 TU 里各是一个实体；无链接的名字即使在同一 TU 中，不同作用域里的也互不相干。

## 历史与演进

!!! history "这一节的演变"
    - C++98–C++20：[basic]/3–4 把值和对象也列为实体，并把名字定义为对指代实体或标号的 identifier 等的使用。也就是说，标号在名字的讨论范围之内，对象与值也被当作实体。
    - C++23：P1787R6（"Declarations and where to find them"）重写了第 6 章前半部分的作用域与查找模型，用声明引入名字的清单（今天的 ¶5）取代旧的声明区描述，名字查找和作用域冲突改用对应、潜在冲突等新术语（见 [[basic.scope]]）。
    - 当前草案（C++26）：实体清单不再包含值和对象，加入了类型别名、命名空间别名、函数形参、模板形参、*init-capture*、结果绑定等，并用底层实体处理别名；契约带来了结果绑定（¶5.4）；变量模板形参与概念模板形参进入 ¶5；静态反射让 *splice-expression* 也能命名实体（见 [[basic.def.odr]]、[[basic.splice]]）。这些措辞上的整理是分几次完成的，本站不逐一标注出处。

## 陷阱

!!! pitfall "对象不是变量"
    `new int` 创建的对象没有名字，不是变量。一个变量所声明的对象在生命周期结束后，变量作为实体依然存在于程序文本中。讨论生命周期（[[basic.life]]）时说的是对象，讨论链接、ODR、作用域时说的是变量和名字。

!!! pitfall "非静态数据成员不会被 odr-use"
    `struct S { int m; };` 中的 `m` 不是变量，所以 [[basic.def.odr#5]] 中关于变量 odr-use 的规则对它不适用。`sizeof(S::m)` 能在没有对象时使用、`S::m` 在不求值操作数里合法，都与此有关（[[expr.prim.id]]）。

## 思考题

!!! question "思考题 1"
    下面每一行中引入了哪些**变量**？哪些**实体**？

    ```cpp
    struct P { int a; static int b; int& c; };
    template<int N, class T> void f(T t, int (&arr)[N]) {
      auto [x, y] = std::pair{1, 2};
      auto l = [z = t] { return z; };
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `P::a`、`P::c`：非静态数据成员（实体），不是变量（`c` 是引用，但被 ¶7.1 排除）。
- `P::b`：静态数据成员，是变量。
- `N`、`T`：模板形参（实体）。`N` 虽然由 *parameter-declaration* 引入，但属于模板形参，不是变量。
- `t`、`arr`：函数形参，同时也是变量（声明了对象或引用）。
- `x`、`y`：结构化绑定，不是变量；但这条声明还引入了一个无名变量（[[dcl.struct.bind]] 中的 `e`）。
- `z`：*init-capture*（实体）；它在闭包类型中对应一个无名的非静态数据成员。
- `l`：变量。另有类型 `P`、函数模板 `f` 等实体。
</details>

!!! question "思考题 2"
    `static` 局部变量是局部实体吗？为什么 lambda 可以不捕获就使用它？

<details markdown="1">
<summary>答案</summary>

不是。¶9 只把自动存储期变量列为局部实体，而 `static` 局部变量具有静态存储期。odr-usable 的限制（[[basic.def.odr#10]]）只针对局部实体，所以 lambda 和局部类的成员函数都可以直接使用它。它在整个程序中只有一个，不存在属于哪一次调用的问题。
</details>

## 小结

| 概念 | 一句话 |
|---|---|
| 名字 | identifier（标号、goto 目标、模块名、属性记号除外）、`operator X`、`operator @`、`operator""_s` |
| 声明 | ¶5 的 18 种语法形式之一；不等于文法非终结符 *declaration* |
| 变量 | 由声明引入的对象或引用；排除非静态数据成员与模板形参 |
| 实体 | 15 种：变量、结构化绑定、结果绑定、函数、枚举项、类型、类型别名、非静态数据成员、位域、模板、命名空间、命名空间别名、模板形参、函数形参、*init-capture* |
| 指代 | 名字指代声明所声明实体的底层实体（穿透别名） |
| [[g:local-entity|局部实体]] | 自动存储期变量、对应的结构化绑定、结果绑定、`*this` |
