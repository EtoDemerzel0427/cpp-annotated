---
title: 声明的总语法
summary: 声明有哪些语法形式、哪些能写在函数体里；一条声明怎样分成属性、说明符、声明符，何时引入名字；typedef、函数、对象三类声明；结构化绑定的外形限制；static_assert 与 consteval 块。
status: done
papers: P2593R1, P2741R3, P1401R5, P1061
related: dcl, dcl.spec, dcl.decl, dcl.struct.bind, basic.def, expr.const
tags: 声明, static_assert, 语法
updated: 2026-10-19
---

!!! tldr
    - 函数定义、模板、命名空间定义都不是块声明，所以不能写在函数体里；`using`、`static_assert`、命名空间别名可以。
    - 声明开头的属性属于每个被声明的实体；只有声明符是一个简单名字时，声明才引入这个名字。
    - 一条声明里的每个声明符单独分类：带 `typedef` 的是 typedef 声明，类型是函数类型的是函数声明，否则是对象声明，类型是 `void` 之类的则非良构。
    - 没有声明符的声明只能用来声明类或枚举，而且必须引入至少一个名字。
    - `static_assert` 的条件允许窄化转换为 `bool`；模板定义里的 `static_assert(false)` 只在实例化时检查（C++23）；消息可以是编译期算出来的字符串（C++26）。

## 一条声明分成三段（¶4–5）

```cpp run ok
[[maybe_unused]] static int a, b;        // a 和 b 都带 maybe_unused
static int c [[maybe_unused]], d;        // 只有 c 带
[[noreturn]] void f [[noreturn]] ();     // OK：两处都写也可以
int main() { return d; }
```

¶4 *simple-declaration* 统一看作三段：

```text
attribute-specifier-seq(opt)  decl-specifier-seq(opt)  init-declarator-list(opt) ;
```

三段分别由 [[dcl.attr]]、[[dcl.spec]]、[[dcl.decl]] 描述。开头的属性**属于每一个声明符所声明的实体**。写在名字（*declarator-id*）后面的属性只属于这一个实体（[[dcl.meaning]]）。同一个属性两处都写不冲突，所以上例中 `f` 的写法是合法的。

¶5 如果 *declarator-id* 是一个名字，也就是标识符、运算符函数名、转换函数名或字面量运算符名，这个声明就**引入**这个名字。否则，它是限定名、析构函数名或 *template-id*，不引入名字，而是重新声明或定义一个已有的实体：

```cpp
struct S { void f(); ~S(); };
void S::f() { }                  // 限定名：定义已声明的 S::f，不引入名字
S::~S() { }                      // 析构函数：不引入名字
template<class T> void g(T);
template<> void g<int>(int);     // template-id：不引入名字
```

[[basic.scope]] 里名字绑定到哪个作用域的规则，都以这一条为起点：只有引入名字的声明才会在作用域中绑定名字。

¶5 后半句说明了类型从哪里来：说明符序列里的类型说明符（[[dcl.type]]）加上声明符的递归结构，共同描述一个类型（[[dcl.meaning]]）。`static`、`inline` 这类说明符不参与。

## 哪些声明能写在函数体里（¶1）

```cpp run ok
void f() {
    using I = int;                 // 别名声明
    static_assert(sizeof(I) >= 2); // static_assert
    namespace s = std;             // 命名空间别名
    int g(int);                    // 函数声明（不是定义）
}
int main() { }
```

¶1 列出了声明的全部语法形式。其中**块声明**（*block-declaration*）既能出现在命名空间作用域，也能出现在块里：

| 块声明 | 例子 | 详见 |
|---|---|---|
| *simple-declaration* | `int x = 1, *p;`、`auto [a, b] = pr;` | 本页、[[dcl.spec]]、[[dcl.decl]] |
| *asm-declaration* | `asm("nop");` | [[dcl.asm]] |
| *namespace-alias-definition* | `namespace fs = std::filesystem;` | [[namespace.alias]] |
| *using-declaration* | `using std::swap;` | [[namespace.udecl]] |
| *using-enum-declaration* | `using enum Color;` | [[enum.udecl]] |
| *using-directive* | `using namespace std;` | [[namespace.udir]] |
| *static_assert-declaration* | `static_assert(N > 0);` | 本页 |
| *consteval-block-declaration* {{c++26}} | `consteval { ... }` | 本页 |
| *alias-declaration* | `using I = int;` | [[dcl.typedef]] |
| *opaque-enum-declaration* | `enum class E : int;` | [[dcl.enum]] |

函数定义、模板声明、推导指引、命名空间定义、链接规格、模块导入、显式实例化与显式特化、`export` 声明都不在这张表里，所以都不能写在函数体中。局部函数定义、局部模板、局部命名空间之所以不存在，都是这个语法的直接结果。

```cpp error
void f() {
    int g() { return 0; }          // error: 函数定义不是块声明
}
```

## typedef、函数还是对象（¶8–11）

¶8 一条 *simple-declaration* 按以下顺序分类：

1. 说明符序列里有 `typedef`：**typedef 声明**，每个 *declarator-id* 都是 typedef 名（[[dcl.typedef]]）；
2. 否则，与 *declarator-id* 关联的类型是函数类型：**函数声明**；
3. 否则，类型是对象类型或引用类型：**对象声明**；
4. 否则（例如类型是 `void`），程序非良构。

分类按声明符逐个进行：

```cpp error
int f(), x;           // OK: f 是函数声明，x 是对象声明
extern void g(),      // OK: 函数声明
    y;                // error: void 不是对象类型
```

引用不是对象，但 `int& r = x;` 也归入对象声明。

¶9 对象定义为对象预留大小和对齐都合适的存储，并完成相应的初始化（[[dcl.init]]）。所以 `extern int x;` 不是定义，不分配存储；`int x;` 是定义。

¶10 函数定义是在函数声明后面加上函数体。以 `{` 或 `=` 开头的记号序列，如果 *declarator-id* 的类型是函数类型，就当作函数体（`{...}`、`= default;`、`= delete;`），否则当作初始化器。判断依据是声明符的类型，与 `=` 后面写了什么无关。

注 5 由此给出两个推论。一个声明如果在模板实例化后才变成函数类型，程序非良构（[[temp.spec.general]]）。函数定义的函数类型也不能来自 typedef 名，因为函数体要用参数名访问参数，而参数名不是类型的一部分：

<div class="compare" markdown="1">

```cpp error
typedef void F();
F f;      // OK: 用 typedef 声明函数
F g { }   // error: 不能这样定义函数
```

```cpp error
template<class T>
struct X { T m; };
X<int()> x;  // error: 成员 m 成了
             // 函数类型 int()
```

</div>

¶11 没有任何说明符的函数声明（*nodeclspec-function-declaration*）只能声明构造函数、析构函数或转换函数，它们本来就没有返回类型。成员函数不能在类外做非定义的重声明（[[class.mfct]]），所以这种声明实际上只出现在模板相关的场合（注 6）：

```cpp run ok
template<class T> struct A { A() { } operator int() { return 0; } };
template<> A<char>::A();          // 显式特化的声明
template A<int>::A();             // 显式实例化
template<> A<char>::A() { }       // 显式特化的定义
int main() { }
```

## 没有声明符的声明（¶6）

```cpp
struct S;              // 声明类名 S
struct T { int m; };   // 定义并声明类名 T
enum E { e1 };         // 声明 E 和 e1
enum { e2 };           // 无名枚举，但引入了枚举项 e2
```

¶6 只有在**声明类或枚举**时，*simple-declaration* 才能省略声明符列表，也就是说明符序列里有类定义、带 `class`/`struct`/`union` 关键字的详述类型说明符，或枚举定义。这时这些说明符里的标识符被声明为类名、枚举名或枚举项。并且这条声明必须（重新）引入至少一个名字：

```cpp error
enum { };              // error: 什么名字都没引入
typedef class { };     // error: 无名类，也没有 typedef 名
int;                   // error: 不是类或枚举声明，又没有声明符
static struct T1 { };  // error: static 没有可修饰的对象（[[dcl.stc#1]]）
const struct T2 { };   // error: const 同理（[[dcl.type.cv#1]]）
```

什么也不声明的声明几乎总是笔误，比如漏写了变量名；`const struct T2 { };` 里的 `const` 也找不到作用对象。本机 Clang 23 对这五行都只给出默认开启的警告（`-Wmissing-declarations` 组），这符合标准，警告也是诊断（[[intro.compliance]]），加 `-pedantic-errors` 会变成错误。

## 结构化绑定的外形（¶7）

¶7 带 *structured-binding-declaration* 的 *simple-declaration* 或条件叫做**结构化绑定声明**（[[g:structured-binding-declaration|structured binding declaration]]），它的语义在 [[dcl.struct.bind]]。本节只限制外形：

1. 说明符只能是 `constexpr`、`constinit`、`static`、`thread_local`、`auto` 和 cv 限定符。所以 `inline auto [a, b]`、`extern auto [a, b]`、`int [a, b]`、受约束的 `C auto [a, b]` 都不行。
2. 至多一个名字前面带 `...`（结构化绑定包）；带了的话，这个声明必须声明一个模板化实体，也就是只能出现在模板里 {{c++26}}。
3. 初始化器只能是 `= e`、`{ e }`、`( e )` 三种形式。
4. 用作条件时，`e` 必须是非联合体类类型 {{c++26}}；否则是数组或非联合体类类型。

```cpp run ok
#include <utility>
struct P { int a, b; };
constexpr P cp{1, 2};
constexpr auto [x, y] = cp;                // C++26: constexpr 结构化绑定
static_assert(x == 1);

template<class T> int sum(T t) {
    auto [...xs] = t;                      // C++26: 结构化绑定包，只能在模板里
    return (0 + ... + xs);
}

int main() {
    static auto [m, n] = P{3, 4};          // C++20 起可以 static
    [[maybe_unused]] auto [u [[maybe_unused]], v] = std::pair{1, 2.0};
    return sum(P{m, n}) - 7;               // 返回 0
}
```

```cpp error
#include <utility>
template<class T> concept C = true;
struct P { int a, b; };
C auto [a, b] = std::pair{1, 2};      // error: 不能用受约束的占位符
inline auto [c, d] = std::pair{1, 2}; // error: inline 不在允许的说明符里
auto [...xs] = P{1, 2};               // error: 包只能出现在模板化实体中
```

受约束的 `C auto` 被禁止，是因为结构化绑定里被推导的是整个隐藏变量的类型（例如 `std::pair<int, int>`），而不是 `a`、`b` 的类型。允许它会让读者以为约束作用在每个绑定上。

C++26 还允许在条件里使用结构化绑定，这时条件的值是整个对象按语境转换为 `bool` 的结果，不是第一个绑定：

```cpp run ok
struct R { bool ok; int v; explicit operator bool() const { return ok; } };
R parse() { return {true, 42}; }
int main() {
    if (auto [ok, v] = parse())    // 条件是 R 转换为 bool 的结果
        return v - 42;
    return 1;
}
```

!!! history "结构化绑定说明符的演进"
    C++17 引入结构化绑定时只允许 `auto` 和 cv 限定符，C++20 起允许 `static` 和 `thread_local`。C++26 又加入了条件中的结构化绑定、`constexpr` 结构化绑定、给每个绑定加属性，以及结构化绑定包（[[P1061]]）。

## static_assert（¶12–14）

`static_assert` 在编译期检查一个条件，不引入任何名字，可以写在命名空间作用域、类里和块里。

### 条件（¶13）

¶13 条件 `E` [[g:contextually-converted-to-bool|按语境转换为 bool]]，转换后的表达式必须是常量表达式（[[expr.const]]）。值为 `true` 时，声明没有效果；值为 `false` 时，这条 `static_assert` **失败**，程序非良构。

按语境转换允许窄化，所以 `static_assert(sizeof(int[2]));` 里 8 转换为 `true` 是合法的。这是 C++23 的改动（[[P1401R5]]），此前要求的转换不允许窄化。

```cpp run ok
static_assert(sizeof(int[2]));     // OK: 8 → true，窄化也允许
static_assert(2);                  // OK
static_assert(sizeof(long) >= 4, "long too small");
int main() { }
```

### 模板里的 static_assert(false)

¶13 还规定，表达式在模板定义的上下文中求值时，声明同样没有效果。这半句是 C++23 加入的（[[P2593R1]]），并作为缺陷报告适用于更早的标准模式。它让下面这种写法成为可能：

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

在此之前，`static_assert(false)` 不依赖模板参数，编译器在模板定义时就可以求值并报错，即使那个分支永远不会实例化，GCC 和 Clang 也确实这样做。人们只好写 `static_assert(sizeof(T) == 0)` 或 `static_assert(always_false<T>)`，人为制造依赖来推迟检查。

现在模板定义里的 `static_assert` 一律不检查，实例化之后才检查。被 `if constexpr` 丢弃的分支不会实例化（[[stmt.if]]），其中的 `static_assert(false)` 也就永远不会触发：

```cpp error
template<class T> void f() { static_assert(false); }   // 定义本身 OK
template void f<int>();     // error: 实例化时 static_assert 失败
void g() { static_assert(false); }   // error: 不在模板里，立即检查
```

### 消息（¶12、¶13.2）{{c++26}}

¶12 消息有两种写法。语法上能匹配[[g:unevaluated-string|不求值字符串]]（没有编码前缀的字符串字面量，[[lex.string.uneval]]）时，它就是字符串。否则它必须是一个表达式 `M`，`M.size()` 能隐式转换为 `std::size_t`，`M.data()` 能隐式转换为 `const char*`。

¶13.2 断言失败时，`M.size()` 必须是常量表达式，记它的值为 N；`M.data()` 也必须能在常量求值中算出，消息文本就是从它开始的 N 个字符。

所以 `std::string`、`std::string_view` 或者自己写的定长缓冲都能作消息，只要能在编译期算出来（[[P2741R3]]）。C++23 及以前，消息只能是字符串字面量。

```cpp run ok
#include <cstddef>
struct Buf {                                   // 极简的编译期格式化缓冲
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
Wrapper<int> w;        // OK
int main() { }
```

把 `Wrapper<int>` 换成 16 字节的类型，本机 Clang 23 的报错信息以计算出的消息 `sizeof(T) == 16, too big` 结尾。

```cpp error
#include <string>
static_assert(false, std::string("built at ") + "compile time");  // error: 消息是 built at compile time
static_assert(false, u8"text");     // error: 不求值字符串不能有编码前缀
```

断言成功时，消息是不求值操作数，只需满足 ¶12 的类型要求，不必是常量表达式。¶14 建议实现在断言失败的诊断中包含消息文本；这只是建议，标准从不规定诊断的具体内容。

!!! history "static_assert 的演进"
    - C++11：引入，消息必填，只能是字符串字面量。
    - C++17：消息可以省略。
    - C++23：条件允许窄化（[[P1401R5]]）；模板定义里的 `static_assert(false)` 不再提前报错（[[P2593R1]]）。
    - C++26：消息可以是编译期算出的字符串（[[P2741R3]]）；消息字符串不允许带编码前缀。

## consteval 块（¶15）{{c++26}}

¶15 `consteval { 复合语句 }` 相当于求值下面这个表达式，它必须是常量表达式：

```text
[] static consteval -> void compound-statement ()
```

也就是立即调用一个无捕获、`static`、`consteval`、返回 `void` 的 lambda。它的用处在于副作用：常量求值时可以产生**注入声明**（injected declaration，[[expr.const.reflect]]），例如用 `std::meta::define_aggregate` 给一个不完整的类生成定义。

因为它等价于 lambda 的函数体，里面可以写 `return;`，但不能声明局部模板或概念。

```cpp
struct S;
consteval {
    std::meta::define_aggregate(^^S, {});   // 注入 S 的定义 struct S { };
}
S s;                                         // OK：S 已经完整
```

`consteval` 块随 C++26 的静态反射一起进入标准。截至写作时，本机 Clang 23 还没有实现静态反射，这个例子未经编译验证。

## 常见误解

!!! pitfall "模板里的 static_assert(false) 想写在哪里都行"
    它只在实例化时检查。如果它所在的位置不会被丢弃，任何实例化都会失败；一个没有任何有效特化的模板，仍可能落入 [[temp.res.general]] 的 IFNDR 规则。

!!! pitfall "开头的属性只属于第一个变量"
    `[[maybe_unused]] int a, b;` 中属性属于 `a` 和 `b` 两者。只想标记其中一个时，把属性写在那个名字后面：`int a [[maybe_unused]], b;`。

## 思考题

!!! question "思考题 1"
    下面每行是良构还是非良构？
    ```cpp
    typedef struct { int x; } T, *PT;
    struct { int y; } obj;
    typedef int A, B();
    B b { }
    ```

<details markdown="1">
<summary>答案</summary>

- 第 1 行良构：定义无名类，`T` 是它的 typedef 名（同时是用于链接目的的 typedef 名，[[dcl.typedef#4]]），`PT` 是指向它的指针类型。
- 第 2 行良构：无名类加一个对象声明，引入了名字 `obj`，满足 ¶6。
- 第 3 行良构：`A` 是 `int` 的别名，`B` 是函数类型 `int()` 的别名，逐个声明符分类（¶8）。
- 第 4 行非良构：`B` 是函数类型，`{` 开始的是函数体（¶10），但函数定义的类型不能来自 typedef 名（注 5）。
</details>

!!! question "思考题 2"
    为什么 `template<class T> void f(T) { if constexpr (false) static_assert(false); }` 在 C++23 中不报错，而在 C++20 中惯用写法是 `static_assert(sizeof(T*) == 0)`？

<details markdown="1">
<summary>答案</summary>

C++23 起，模板定义上下文中的 `static_assert` 都不检查；`if constexpr (false)` 的分支被丢弃，实例化时也不会实例化它，所以永远不会触发。按 C++20 的规则，`static_assert(false)` 是不依赖模板参数的常量表达式，编译器可以在定义时直接求值并报错。写成 `sizeof(T*) == 0` 让表达式依赖 `T`，检查推迟到实例化，而被丢弃的分支不会实例化。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶2 有些声明本身包含作用域，如类定义、lambda、函数参数列表。第 9 章说到声明的某个成分时，只指不嵌套在这些内层作用域里的部分。例如 `struct A { struct B { } b; } a;` 中，只有 `A` 的类定义是这条声明的成分，`B` 的类定义属于 `A` 里的成员声明。否则"声明中不得含有 X"这类规则会把 lambda 体、类体里的内容也算进来。

¶3 一个声明如果符合友元类型声明（*friend-type-declaration*）的语法，就按友元类型声明处理。`friend C;` 因此不会被读成没有声明符的 *simple-declaration*，见 [[dcl.friend]]。

注 4：typedef 声明的 *declarator-id* 是一个标识符，所以不能用 typedef 声明 `operator int` 这样的转换函数名（[[class.conv.fct]]）。

¶16 空声明（单独一个 `;`）没有任何效果。因此在命名空间作用域多写的分号，如 `namespace N { };`、`void f() { };` 后面的分号，都是良构的。C++98 的语法没有空声明，这些多余的分号当时只是作为扩展被接受。

¶17 属性声明（`[[...]];`）的含义除另有规定外由实现定义 {{impl}}。标准属性都不用于属性声明。

</details>
