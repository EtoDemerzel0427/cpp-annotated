---
title: 序言
summary: 声明的总语法；simple-declaration 的三段结构；"必须引入名字"规则；结构化绑定声明的说明符限制；typedef/函数/对象声明的分类；static_assert（含 C++26 自定义消息）、consteval 块、空声明与属性声明
status: done
papers: P2593R1, P2741R3, P1401R5, P1061
related: dcl, dcl.spec, dcl.decl, dcl.struct.bind, basic.def, expr.const
tags: 声明, static_assert, 语法
updated: 2026-10-17
---

[dcl.pre] 是第 9 章的"总入口"：它列出所有**声明**（*declaration*）的语法形式，并给出几条横跨所有声明的规则——一个声明怎样被拆分、什么时候它必须引入名字、什么时候它是函数声明/对象声明、以及几种"不声明任何名字"的特殊声明（`static_assert`、`consteval` 块、空声明、属性声明）的语义。

本节是 [[basic.pre]]（"什么是声明"）与 [[basic.def]]（"哪些声明是定义"）的具体化：那两节说的是抽象概念，这里给出语法。读完本节，你应能把任何一行声明分解为"属性 / 说明符 / 声明符 / 初始化器"，并判断它属于哪一类声明。

## 声明的语法总表（¶1）

¶1 声明的顶层语法分为两大类：

- ***name-declaration***：可能引入名字的声明——块声明（*block-declaration*）、无说明符函数声明、函数定义、友元类型声明、模板声明、推导指引、链接规格、命名空间定义、空声明、属性声明、模块导入声明；
- ***special-declaration***：显式实例化、显式特化、`export` 声明。

把后三者单独分出来，是因为它们**只能出现在命名空间作用域**、且各自对内层声明有额外约束（例如 [[temp.expl.spec]]、[[module.interface]]）。

*block-declaration* 是"既能出现在命名空间作用域，也能出现在块作用域"的那一部分：

| 块声明 | 例子 | 详见 |
|---|---|---|
| *simple-declaration* | `int x = 1, *p;`、`auto [a, b] = pr;` | 本节、[[dcl.spec]]、[[dcl.decl]] |
| *asm-declaration* | `asm("nop");` | [[dcl.asm]] |
| *namespace-alias-definition* | `namespace fs = std::filesystem;` | [[namespace.alias]] |
| *using-declaration* | `using std::swap;` | [[namespace.udecl]] |
| *using-enum-declaration* | `using enum Color;` | [[enum.udecl]] |
| *using-directive* | `using namespace std;` | [[namespace.udir]] |
| *static_assert-declaration* | `static_assert(N > 0);` | 本节 ¶12–14 |
| *consteval-block-declaration* {{c++26}} | `consteval { ... }` | 本节 ¶15 |
| *alias-declaration* | `using I = int;` | [[dcl.typedef]] |
| *opaque-enum-declaration* | `enum class E : int;` | [[dcl.enum]] |

反过来，**不是**块声明的那些——函数定义、模板声明、命名空间定义、链接规格、显式实例化/特化、模块导入——不能出现在函数体里。所以"局部函数定义""局部模板""局部命名空间"都不存在，这不是三条独立的规则，而是语法的直接推论。

```cpp run ok
#include <cstddef>
void f() {
    using I = int;                 // OK: alias-declaration 是块声明
    static_assert(sizeof(I) >= 2); // OK: static_assert 是块声明
    namespace s = std;             // OK: namespace-alias-definition 也是块声明
    int g(int);                    // OK: 只是声明（simple-declaration），不是定义
}
int main() { }
```

```cpp error
void f() {
    int g() { return 0; }          // error: function-definition 不是 block-declaration
}
```

¶1 中还有几个后面要用到的语法：

- *simple-declaration* 有三种形式：(a) `decl-specifier-seq init-declarator-list(opt) ;`；(b) 以属性开头时 *init-declarator-list* **不可省略**；(c) 结构化绑定声明 + 初始化器。
- *sb-identifier*：结构化绑定里的每个名字，C++26 起可以带 `...`（结构化绑定包）和属性。
- *nodeclspec-function-declaration*：`attribute-specifier-seq(opt) declarator ;`——没有任何说明符的函数声明（¶11）。

!!! note "为什么 (b) 要求有声明符"
    `[[nodiscard]] struct S;` 若按 (a) 解析，属性位于开头且无声明符——属性应属于谁？标准选择让 (b) 必须带声明符，这样开头的属性总是"属于被声明的实体"（¶4）。要给类本身加属性，应写在 *class-key* 之后：`struct [[nodiscard]] S;`（[[dcl.type.elab#2]]）。

## 嵌套作用域中的成分不算（¶2）

¶2 有些声明本身包含作用域（类定义、lambda、函数参数作用域……）。本章凡是说"声明中的某某成分"时，**只看不嵌套在内层作用域里的部分**。

这是一条"读法约定"。例如 ¶6 说"若 *decl-specifier-seq* 含有 *class-specifier* ……"，那么

```cpp
struct A { struct B { } b; } a;
```

中只有 `A` 的 *class-specifier* 是"这条声明的成分"；`B` 的 *class-specifier* 嵌套在 `A` 的类作用域里，归属于 `A` 内部的那条成员声明。没有这条约定，许多"声明中不得含有 X"的规则会意外地把 lambda 体、类体里的东西也算进来。

## 友元类型声明的消歧（¶3）

¶3 若一个 *name-declaration* 同时符合 *friend-type-declaration* 的语法，就按 *friend-type-declaration* 处理。

`friend C;` 既可以读成 *simple-declaration*（说明符 `friend` + 类型说明符 `C`，没有声明符），也可以读成 *friend-type-declaration*（`friend` *friend-type-specifier-list* `;`）。规则让它总是后者，于是 [[class.friend]] 中关于友元类型的规则（例如"若不是类类型则忽略"、C++26 的包展开 `friend Ts...;`）统一适用。详见 [[dcl.friend]]。

## 三段式：属性、说明符、声明符（¶4–5）

¶4 *simple-declaration* 和 *nodeclspec-function-declaration* 统一看作

```text
attribute-specifier-seq(opt)  decl-specifier-seq(opt)  init-declarator-list(opt) ;
```

三部分分别由 [[dcl.attr]]、[[dcl.spec]]、[[dcl.decl]] 描述。**开头的属性**属于每一个声明符所声明的实体。

!!! std
    The *attribute-specifier-seq* appertains to each of the entities declared by the *declarators* of the *init-declarator-list*.

    开头的属性作用于本声明里**每个**声明符声明的实体。

属性还有另一个位置：*declarator-id* 之后（`void f [[noreturn]] ();`），那里的属性只属于这一个实体（[[dcl.meaning]]）。标准的例子 `[[noreturn]] void f [[noreturn]] ();` 两处都写，合法——重复的 `noreturn` 并不冲突。

```cpp run ok
[[maybe_unused]] static int a, b;        // a 和 b 都是 maybe_unused
static int c [[maybe_unused]], d;        // 只有 c 是
[[noreturn]] void f [[noreturn]] ();     // OK
int main() { return d; }                 // 用一下 d，免得 -Wunused-variable
```

¶5 若 *declarator-id* 是一个**名字**（即普通标识符、运算符函数名、转换函数名、字面量运算符名），这个 *init-declarator*——进而整个声明——就**引入**这个名字。否则（*qualified-id*、析构函数名、*template-id*）不引入名字，而是**重声明/定义**一个已有的实体：

```cpp
struct S { void f(); ~S(); };
void S::f() { }        // declarator-id 是 qualified-id：不引入名字，定义已声明的 S::f
S::~S() { }            // 析构函数：不引入名字
template<class T> void g(T);
template<> void g<int>(int);   // template-id：不引入名字
```

这条规则是 [[basic.scope]] 中"声明的目标作用域""名字绑定"等概念的入口：只有引入名字的声明才会在某个作用域中**绑定**名字。

¶5 后半句给出了类型的来源：*decl-specifier-seq* 中的**定义类型说明符**（[[dcl.type]]）加上递归的声明符结构，共同描述一个类型（[[dcl.meaning]]），这个类型与 *declarator-id* 关联。注意只有**类型**说明符参与；`static`、`inline`、`constexpr` 等不影响类型（`constexpr` 的"隐含 const"是另一条规则 [[dcl.constexpr#6]] 加上去的）。

## 省略声明符：只能用于声明类或枚举（¶6）

¶6 *simple-declaration* 省略 *init-declarator-list* 的唯一情形是**声明类或枚举**：*decl-specifier-seq* 里有 *class-specifier*、带 *class-key* 的 *elaborated-type-specifier*，或 *enum-specifier*。此时（以及任何含有 *class-specifier* / *enum-specifier* 的声明中），这些说明符里的标识符也被声明（为类名、枚举名或枚举项）。并且：

!!! std
    In such cases, the *decl-specifier-seq* shall (re)introduce one or more names into the program.

    此时说明符序列必须（重新）引入至少一个名字。

```cpp
struct S;              // OK: 声明类名 S
struct T { int m; };   // OK: 定义并声明类名 T
enum E { e1 };         // OK: 声明 E 和 e1
enum { e2 };           // OK: 无名枚举，但引入了枚举项 e2
```

```cpp error
enum { };              // error: 什么名字都没引入
typedef class { };     // error: 无名类且没有 typedef 名
int;                   // error: 既不是类/枚举声明，又没有声明符
```

!!! impl "Clang 只给警告"
    对 `int;`、`enum { };`、`typedef class { };`，Clang 给出的是默认开启的**警告**（`-Wmissing-declarations` 组）而不是错误。这仍然符合标准：标准只要求"诊断"（[[intro.compliance]]），警告也是诊断。加 `-pedantic-errors` 或 `-Werror` 才会变成错误。

为什么要禁止"什么都不声明"的声明？因为它几乎总是笔误（例如漏写了变量名），而且像 `const struct U { };` 这样的写法——`const` 作用于谁？——没有合理语义。相关地，[[dcl.stc#1]] 和 [[dcl.type.cv#1]] 分别规定：出现存储类说明符或 cv 限定符时，声明符列表**不得为空**。

```cpp error
static struct T1 { };  // error: static 必须修饰被声明的变量/函数，这里没有
const struct T2 { };   // error: 同理（[dcl.type.cv]/1）
```

（这两行 Clang 同样只给警告。）

## 结构化绑定声明的限制（¶7）

¶7 带 *structured-binding-declaration* 的 *simple-declaration* 或 *condition* 称为**结构化绑定声明**（详见 [[dcl.struct.bind]]）。本节只规定其外形：

1. **说明符白名单**：每个 *decl-specifier* 只能是 `constexpr`、`constinit`、`static`、`thread_local`、`auto`、或 cv 限定符。所以 `inline auto [a, b]`、`extern auto [a, b]`、`int [a, b]`、`C auto [a, b]`（受约束占位符）都不行。
2. **至多一个包**：至多一个 *sb-identifier* 前有 `...`；若有，该声明必须声明一个模板化实体（即只能出现在模板里）{{c++26}}。
3. **初始化器形式**：只能是 `= e`、`{ e }`、`( e )` 三种，`e` 是单个 *assignment-expression*。
4. **初始化表达式的类型**：作为 *condition* 时必须是非联合体类类型 {{c++26}}；否则是数组或非联合体类类型。

```cpp run ok
#include <utility>
struct P { int a, b; };
constexpr P cp{1, 2};
constexpr auto [x, y] = cp;                         // C++26: constexpr 结构化绑定
static_assert(x == 1);

template<class T> int sum(T t) {
    auto [...xs] = t;                               // C++26: 结构化绑定包，只能在模板中
    return (0 + ... + xs);
}

int main() {
    static auto [m, n] = P{3, 4};                   // OK: static
    [[maybe_unused]] auto [u [[maybe_unused]], v] = std::pair{1, 2.0};
    return sum(P{m, n}) - 7;                        // 返回 0
}
```

```cpp error
#include <utility>
template<class T> concept C = true;
struct P { int a, b; };
C auto [a, b] = std::pair{1, 2};      // error: 受约束占位符不能用于结构化绑定
inline auto [c, d] = std::pair{1, 2}; // error: inline 不在白名单中
auto [...xs] = P{1, 2};               // error: 包只能出现在模板化实体中
```

!!! note "为什么不允许 `C auto [a, b]`"
    受约束占位符约束的是"被推导的类型"；结构化绑定中被推导的是**整个隐藏变量 e** 的类型（例如 `std::pair<int,int>`），不是 `a`、`b` 的类型。允许 `C auto` 会让读者误以为约束作用在各个绑定上。标准干脆禁止，留待将来设计。

!!! history "结构化绑定的 C++26 扩展"
    C++17 引入结构化绑定时，说明符只允许 `auto` 和 cv 限定符；C++20 起允许 `static` 与 `thread_local`。C++26 先后加入：在 *condition* 中使用结构化绑定（`if (auto [ok, v] = f())`，以整个对象的上下文转换为 `bool` 作为条件）；`constexpr` 结构化绑定；为每个绑定加属性；结构化绑定包（[[P1061]]）。

```cpp run ok
struct R { bool ok; int v; explicit operator bool() const { return ok; } };
R parse() { return {true, 42}; }
int main() {
    if (auto [ok, v] = parse())    // C++26：条件是 R 转换为 bool 的结果，不是 ok
        return v - 42;
    return 1;
}
```

## 声明的三种类别（¶8）

¶8 一条 *simple-declaration* 按如下顺序分类：

1. *decl-specifier-seq* 含 `typedef` → **typedef 声明**，每个 *declarator-id* 都是 *typedef-name*（[[dcl.typedef]]）；
2. 否则，与 *declarator-id* 关联的类型是函数类型 → **函数声明**；
3. 否则，类型是对象类型或引用类型 → **对象声明**；
4. 否则（例如类型是 `void`）→ 非良构。

注意分类是**逐个声明符**进行的：

```cpp error
int f(), x;           // OK: f 是函数声明，x 是对象声明
extern void g(),      // OK: 函数声明
    y;                // error: void 不是对象类型
```

"对象声明"这个名字容易误导：引用不是对象，但 `int& r = x;` 也归入"对象声明"。

Note 4 补充：在 typedef 声明里，*declarator-id* 是一个 *identifier*。它链接到 [[class.conv.fct]]——转换函数的名字 `operator T` 不能用 typedef 声明（`typedef int operator int;` 无意义）。

## 对象定义做了什么（¶9）

¶9 对象**定义**会预留大小和对齐合适的存储，并完成相应的初始化（[[dcl.init]]）。这句话把"定义"和"分配存储"联系了起来：`extern int x;` 不是定义，所以不分配存储；`int x;` 是定义，分配存储并做默认初始化（命名空间作用域下还会先零初始化，[[basic.start.static]]）。

## `{` 和 `=` 何时开始函数体（¶10）

¶10 函数定义是在函数声明的基础上加了函数体。以 `{` 或 `=` 开头的记号序列，若 *declarator-id* 的类型是函数类型，就当作 *function-body*（`{...}`、`= default;`、`= delete;`），否则当作初始化器。

所以 `void f() = delete;` 中的 `= delete` 是函数体，`int x = delete_me;` 中的 `=` 开始的是初始化器——判断依据是**声明符的类型**，而不是 `=` 后面跟着什么。

Note 5 指出两个推论：

- 若某声明是在模板实例化后才"变成"函数类型的，程序非良构（[[temp.spec.general]]）——例如 `template<class T> struct X { T m; }; X<int()> x;` 中成员 `m` 会变成函数类型；
- 函数定义的函数类型不能来自 *typedef-name*：`typedef void F(); F f { }` 不是函数定义。

```cpp error
typedef void F();
F f;                    // OK: 用 typedef 声明函数
F g { }                 // error: 不能用 typedef 名的函数类型来定义函数

```

```cpp error
template<class T> struct X { T m; };
X<int()> x;             // error: X<int()>::m 被实例化为函数类型
```

为什么禁止用 typedef 定义函数？因为函数定义需要**参数名**来在函数体中使用，而 typedef 的函数类型不携带参数名（参数名不是类型的一部分）。

## 无说明符的函数声明（¶11）

¶11 *nodeclspec-function-declaration*（没有任何 *decl-specifier* 的函数声明）只能声明**构造函数、析构函数或转换函数**——它们本来就没有返回类型，自然也就没有类型说明符。

Note 6 进一步指出：由于成员函数不能在类外做非定义的重声明（[[class.mfct]]），这种声明实际上只会出现在模板声明、显式实例化、显式特化中：

```cpp run ok
template<class T> struct A { A() { } operator int() { return 0; } };
template<> A<char>::A();          // 显式特化的声明（nodeclspec）
template A<int>::A();             // 显式实例化（nodeclspec）
template<> A<char>::A() { }       // 显式特化的定义（这是 function-definition）
int main() { }
```

## static_assert（¶12–14）

`static_assert` 是一个不引入任何名字的块声明，作用是在编译期检查一个条件。它可以出现在命名空间作用域、类作用域（作为 *member-declaration*）和块作用域。

### 条件（¶13）

¶13 *constant-expression* `E` 被**上下文转换为 `bool`**，转换后的表达式必须是常量表达式（[[expr.const]]）。然后：

- 若值为 `true`，**或者表达式是在模板定义的上下文中被求值**，声明无效果，消息是不求值操作数；
- 否则 `static_assert` **失败**：程序非良构；若消息是常量表达式 `M`，还要按 ¶13.2 求出消息文本。

"上下文转换为 bool"意味着**允许窄化**：`static_assert(sizeof(int[2]))` 中 `8 → true` 是窄化转换，但这里合法（C++23 起，[[P1401R5]]；之前要求"转换后的常量表达式"，不允许窄化）。

```cpp run ok
static_assert(sizeof(int[2]));     // OK: 8 上下文转换为 true（窄化也允许）
static_assert(2);                  // OK
static_assert(sizeof(long) >= 4, "long too small");
int main() { }
```

### `static_assert(false)` 在模板中（¶13）

"在模板定义的上下文中被求值"这半句是 C++23 加入的（[[P2593R1]]，作为缺陷报告应用于更早的标准）。它解决了一个多年的痛点：

```cpp run ok
#include <type_traits>
template<class T> int to_int(T t) {
    if constexpr (std::is_integral_v<T>)
        return static_cast<int>(t);
    else
        static_assert(false, "to_int: T must be integral");   // C++23 起 OK
}
int main() { return to_int(0L); }
```

在 P2593 之前，`static_assert(false)` 不依赖模板参数，按 [[temp.res]] 的"若模板没有任何有效特化则 IFNDR"规则，编译器有权（GCC 和 Clang 实际也会）在**模板定义时**就报错，即使那个分支永远不会被实例化。人们只好写 `static_assert(sizeof(T) == 0)` 或 `static_assert(always_false<T>)` 这类"伪依赖"表达式来骗过编译器。

新规则说：模板**定义**中的 `static_assert` 一律不检查，只有在**实例化**后（此时表达式不再"在模板定义的上下文中"）才检查。被 `if constexpr` 丢弃的分支里的语句不会被实例化（[[stmt.if]]），所以 `static_assert(false)` 永远不会触发。

```cpp error
template<class T> void f() { static_assert(false); }   // 定义本身 OK
template void f<int>();     // error: 显式实例化导致 static_assert 失败
void g() { static_assert(false); }   // error: 非模板，立即检查
```

!!! pitfall "这不是"模板里随便写 false""
    若 `static_assert(false)` 位于**不会被丢弃**的位置，任何实例化都会失败；而一个没有任何有效特化的模板仍可能落入 [[temp.res.general]] 的 IFNDR 规则。新规则只是让 `static_assert` 本身不再成为"模板无有效特化"的证据。

### 消息（¶12、¶13.2）{{c++26}}

¶12 *static_assert-message* 有两种：

- 语法上匹配 *unevaluated-string*（无编码前缀的字符串字面量，[[lex.string.uneval]]）时，就是字符串，文本即该字符串；
- 否则必须是一个表达式 `M`，满足 `M.size()` 可隐式转换为 `std::size_t`、`M.data()` 可隐式转换为 `const char*`。

¶13.2 仅在**断言失败时**才要求：`M.size()` 是 `size_t` 类型的转换常量表达式（值为 N），`M.data()` 是核心常量表达式（记为 D），且 `D[0]`…`D[N-1]` 都是整型常量表达式；消息文本是从 D 开始的 N 个**普通字面量编码**的代码单元。

换句话说，任何"像字符串的东西"——`std::string`、`std::string_view`、自定义的定长缓冲——都能作消息，只要能在常量求值中算出来。这是 C++26 的新特性（[[P2741R3]]）；C++23 及之前，消息只能是字符串字面量。

```cpp run ok
#include <cstddef>
struct Buf {                                   // 极简的编译期"格式化"缓冲
    char s[32]{}; std::size_t n = 0;
    constexpr Buf& operator<<(const char* p) { while (*p) s[n++] = *p++; return *this; }
    constexpr Buf& operator<<(std::size_t v) {
        char t[20]; int k = 0;
        do t[k++] = char('0' + v % 10); while (v /= 10);
        while (k) s[n++] = t[--k];
        return *this;
    }
    constexpr std::size_t size() const { return n; }
    constexpr const char* data() const { return s; }
};
template<class T> struct Wrapper {
    static_assert(sizeof(T) <= 8, Buf{} << "sizeof(T) == " << sizeof(T) << ", too big");
};
Wrapper<int> w;        // OK；若换成 Wrapper<long double>，诊断信息里会出现计算出的大小
int main() { }
```

```cpp error
#include <string>
static_assert(false, std::string("built at ") + "compile time");  // error，消息为 "built at compile time"
static_assert(false, u8"text");     // error: 不是 unevaluated-string（有编码前缀），也不是有 size()/data() 的表达式
```

!!! lawyer "消息只在失败时求值"
    断言成功时，消息是**不求值操作数**（¶13）：它只需满足 ¶12 的"可隐式转换"语法/类型要求，不需要是常量表达式。因此 `static_assert(true, some_runtime_string())` 只要类型合适就良构。¶13.2 的常量性要求只在失败路径上生效——反正那时程序已经非良构了，这些要求只影响"能否给出消息文本"。

¶14（推荐实践）：断言失败时，诊断信息应当包含消息文本。这只是推荐，标准对诊断的内容从不作强制要求。

!!! history "static_assert 的演进"
    - C++11：引入，消息必填，必须是字符串字面量。
    - C++17：消息可省略。
    - C++23：条件允许窄化转换为 `bool`（[[P1401R5]]）；模板定义中的 `static_assert(false)` 不再提前报错（[[P2593R1]]）。
    - C++26：消息可以是计算出来的（[[P2741R3]]）；同时引入 *unevaluated-string* 概念，消息字符串不允许编码前缀。

## consteval 块（¶15）{{c++26}}

¶15 `consteval { 复合语句 }` 对应的表达式 E 是

```text
[] static consteval -> void compound-statement ()
```

即"立即调用一个无捕获、static、consteval、返回 void 的 lambda"。E 必须是常量表达式。它的意义在于**副作用**：常量求值过程中可以产生**注入声明**（injected declaration，[[expr.const.reflect]]），比如用 `std::meta::define_aggregate` 为一个不完整类生成定义。

由于等价于一个 lambda 的函数体：

- 里面可以写 `return;`（返回 void）；
- 不能声明局部模板或概念（lambda 体里本来就不行）；
- 没有捕获——不能使用外层的局部变量（除非不 odr-use）。

`consteval` 块随 C++26 静态反射进入标准，此前的 C++ 里没有"在声明位置执行一段编译期代码"的语法；常见的替代是 `static_assert((some_consteval_fn(), true));` 这类技巧。截至写作时，本机 Clang 尚未实现静态反射，`consteval` 块无法验证。

```cpp
// 取自标准的例子思路（需要实现了 P2996 的编译器）
struct S;
consteval {
    std::meta::define_aggregate(^^S, {});   // 注入 S 的定义：struct S { };
}
S s;                                         // OK：S 此时已完整
```

## 空声明与属性声明（¶16–17）

¶16 **空声明**（*empty-declaration*，即单独的 `;`）没有任何效果。它让"在函数定义或命名空间后多写一个分号"成为合法：

```cpp run ok
namespace N { };          // OK: 命名空间定义 + 空声明
void f() { };             // OK: 函数定义 + 空声明（命名空间作用域）
struct S { void g() { }; };   // OK: 类内的多余分号也合法（member-declaration 允许空声明）
;;;
int main() { }
```

（`-Wextra-semi` 之类的警告会提醒这些多余分号，但它们是良构的。C++11 之前，命名空间作用域的多余分号在 C++98 语法中并不合法，许多编译器只是作为扩展接受。）

¶17 **属性声明**（*attribute-declaration*，`[[...]];`）的含义除另有规定外由实现定义 {{impl}}。目前标准属性中没有用于属性声明的；它主要为实现留出空间（例如将来的 OpenMP 指令属性）。

!!! summary "小结"
    | 规则 | 段落 | 要点 |
    |---|---|---|
    | 块声明 vs 其他 | ¶1 | 函数定义/模板/命名空间不是块声明，所以不能出现在函数体中 |
    | 三段式 | ¶4–5 | 开头属性作用于所有声明符；只有 *declarator-id* 是名字时才引入名字 |
    | 省略声明符 | ¶6 | 仅限声明类/枚举，且必须引入至少一个名字 |
    | 结构化绑定 | ¶7 | 说明符白名单：`constexpr constinit static thread_local auto` + cv |
    | 声明分类 | ¶8 | typedef → 函数 → 对象/引用 → 否则非良构，逐声明符判断 |
    | 函数体 vs 初始化器 | ¶10 | 看声明符类型；typedef 函数类型不能用于定义 |
    | static_assert | ¶12–14 | 允许窄化；模板定义中不检查；C++26 消息可计算 |
    | consteval 块 | ¶15 | 等价于立即调用的 consteval lambda，用于注入声明 |

!!! question "思考题 1"
    下面每行是良构、非良构，还是需要更多信息？

    ```cpp
    typedef struct { int x; } T, *PT;
    struct { int y; } obj;
    typedef int A, B();
    B b { }
    ```

<details markdown="1">
<summary>答案</summary>

- 第 1 行良构：定义了无名类，`T` 是它的 typedef 名（也是用于链接目的的 typedef 名，[[dcl.typedef#4]]），`PT` 是指向它的指针类型。
- 第 2 行良构：无名类 + 对象声明，引入了名字 `obj`，满足 ¶6。
- 第 3 行良构：`A` 是 `int` 的别名，`B` 是函数类型 `int()` 的别名（typedef 声明逐声明符分类，¶8）。
- 第 4 行非良构：`B` 是函数类型，`{` 开始函数体（¶10），但函数定义的类型不能来自 typedef 名（Note 5、[[dcl.fct]]）。
</details>

!!! question "思考题 2"
    为什么下面的 `static_assert` 在 C++23 中不报错，而换成 `static_assert(sizeof(T*) == 0)` 在 C++20 中却是惯用法？

    ```cpp
    template<class T> void f(T) { if constexpr (false) static_assert(false); }
    ```

<details markdown="1">
<summary>答案</summary>

C++23 起（P2593 作为 DR），模板定义上下文中的 `static_assert` 无论表达式是否依赖都不检查；`if constexpr (false)` 的分支被丢弃，实例化时也不会实例化它，所以永不触发。C++20 时 `static_assert(false)` 是非依赖的常量表达式，编译器可以在定义时直接求值并报错（而且由于模板没有有效特化，按 [[temp.res.general]] 本就是 IFNDR）；写成 `sizeof(T*) == 0` 让表达式依赖于 `T`，推迟到实例化，而丢弃分支不会被实例化。
</details>
