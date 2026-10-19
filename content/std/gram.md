---
title: 文法摘要
summary: 附录 A 把各章的语法产生式汇总在一起，只供参考：它接受的是合法 C++ 的超集，而且有二义性，一段代码怎么解析常常要靠名字查找和消歧规则来决定。
status: done
covers: *
papers: P0846R0
related: syntax, lex.pptoken, stmt.ambig, dcl.ambig.res, temp.names, dcl.attr.grammar
tags: 语法, 导读, 附录, 解析
updated: 2026-10-19
---

!!! tldr
    - 附录 A 是资料性的语法汇总，有规范效力的是正文各条款里的同一份产生式；引用语法时应当引用正文条款。
    - 这份语法接受的是合法 C++ 的超集，很多限制写在正文的文字规则里。它还有二义性，同一串记号可以有多种推导。
    - 一个标识符是类型名、模板名还是普通变量，会改变整条语句的解析，所以 C++ 的语法不是上下文无关的。
    - 难解析的地方由语法之外的规则决定：能当声明就当声明，`<` 何时开始模板实参列表，`>>` 何时拆成两个 `>`，`[[` 只能引入属性。

## 同样的记号，不同的解析

```cpp run ok
struct T { T() {} };
int U(int x) { return x; }
int v = 0;

void f() { T(v); }   // 声明：等价于 T v;，遮蔽了全局的 v
void g() { U(v); }   // 表达式：以 ::v 为实参调用 U
```

`T(v);` 和 `U(v);` 的记号排列完全一样，区别只在于名字查找的结果：`T` 是类，`U` 是函数。查找发现 `T` 是类之后，`T(v);` 才多出一种读法，即声明一个类型为 `T`、名为 `v` 的变量，声明符外面套了一对多余的括号。按 [[stmt.ambig#1]]，能当声明就当声明。本机 Clang 23 对 `f` 给出 `-Wvexing-parse` 警告，提醒括号被当成了声明符的一部分。

所以光看语法产生式，不足以确定一段 C++ 代码的含义。附录 A 自己也明说了这一点。

## 附录 A 是什么

附录 A [gram] 把正文各条款开头的语法产生式按章节顺序汇总到一处，没有新增任何规则。读产生式的记法（斜体非终结符、下标 opt、*X-seq*、*X-list* 等）见 [[syntax]]。

!!! std
    This summary of C++ grammar is intended to be an aid to comprehension. It is not an exact statement of the language.

[gram.general] ¶1 说这份摘要只是帮助理解，并不是对语言的精确陈述，并举出两方面的不精确。

### 它接受的是合法 C++ 的超集

```cpp error
int;                           // 符合 simple-declaration 的语法
struct A { virtual int x; };   // 符合 member-declaration 的语法
```

这两行都能由语法推导出来，却都非良构。第一行违反 [[dcl.pre#6]]：省略声明符只允许在声明类或枚举时出现。第二行违反 [[dcl.fct.spec]]：`virtual` 只能用于非静态成员函数。本机 Clang 23 对第二行报错，对 `int;` 只给出 `-Wmissing-declarations` 警告，警告也算诊断，所以同样符合标准。

这些约束不写进语法，是因为写进去产生式会急剧膨胀。*member-declaration* 的第一个备选项由属性、说明符序列和声明符列表组成，三部分全都可选；如果要用产生式表达哪些说明符可以和哪些声明符组合，就得把每种组合拆成单独的非终结符。标准的做法是让语法宽松地描述形状，再用 shall 规则加以限制。

### 它有二义性

同一串记号可以有不止一棵语法树，开头的 `T(v);` 就是例子。¶1 点名了三处消歧规则：[[stmt.ambig]]、[[dcl.spec]] 和 [[class.member.lookup]]，用来区分表达式和声明。此外，访问控制、二义性检查和类型规则负责排除语法上成立但没有意义的构造。

实际的编译器因此需要语法之外的两样东西：名字查找的结果，以及两种推导都成立时的选择规则。GCC、Clang、MSVC 都用手写的递归下降解析器，在解析过程中同时做名字查找，必要时先按声明试探性地解析一遍，不成功再回退按表达式解析。

## 由声明引入的名字

[gram.key] ¶1 说，typedef、命名空间、类、枚举和模板声明会向程序引入新的**上下文相关关键字**（context-dependent keywords），随后列出这些非终结符：

| 非终结符 | 形式 | 由什么声明引入 | 详见 |
|---|---|---|---|
| *typedef-name* | *identifier*、*simple-template-id* | typedef、别名声明、别名模板 | [[dcl.typedef]] |
| *namespace-name* | *identifier*、*namespace-alias* | 命名空间定义 | [[namespace.def]] |
| *namespace-alias* | *identifier* | 命名空间别名定义 | [[namespace.alias]] |
| *class-name* | *identifier*、*simple-template-id* | 类声明、类模板 | [[class.name]] |
| *enum-name* | *identifier* | 枚举声明 | [[dcl.enum]] |
| *simple-template-name* | *identifier* | 模板声明 | [[temp.names]] |

这里的关键字不是 [[lex.key]] 意义上的保留拼写，`int` 在任何地方都是 `int`。它的意思是：一个普通的标识符，被某个声明引入成类型名或模板名之后，就像关键字一样改变了后续记号的解析方式。开头的 `T` 就是这样。

这种依赖来自 C。C 的 typedef 名同样会改变解析：`a * b;` 在 `a` 是 typedef 名时是声明，否则是乘法。C 编译器的传统做法是让词法分析器查符号表，把 typedef 名作为单独的记号种类交给解析器。C++ 把这种依赖扩大到类名、模板名和命名空间名，于是在模板里出现了查符号表也解决不了的情形：依赖名在模板定义处无法查找，只能由程序员用 `typename` 和 `template` 告诉解析器（[[temp.res]]、[[temp.names#7]]）。

这张表并不完整。*concept-name*（[[temp.concept]]）也是由模板声明引入的标识符，但不在 [gram.key] 的列表里。

## 难解析的代码

下面每个例子里，语法都允许不止一种读法，或者给出的读法与直觉不同。最终起作用的是语法之外的规则。

### `T(x);`：能当声明就当声明

```cpp run error
struct T { T(int) {} T() {} };
void f() {
  int x = 1;
  T(x);        // 声明 T x;，不是用 x 构造临时对象
               // error: x 重定义
}
```

如果 `T` 是类型名，`T(x);` 既可以是以函数式转换开头的表达式语句，也可以是声明符带括号的声明。[[stmt.ambig#1]] 选择声明。本机 Clang 23 先给出 `-Wvexing-parse` 警告，再报 `x` 重定义。

这条规则有几个细节：

- 消歧只看语法（[[stmt.ambig#3]]）。除了某个名字是不是类型名，名字的其他含义不参与判断。消歧在先，所以一条被判定为声明的语句可能是非良构的声明，编译器不会回头改按表达式解析。
- 有时要看完整条语句才能判断。`T(a)->m = 7;` 不可能是声明，所以是表达式；`T(*d)(int);` 可以是声明，所以是声明。见 [[stmt.ambig#2]] 的例子。
- 同样的规则在声明内部也适用，这就是常说的 most vexing parse：`S w(int());` 声明的是函数，不是对象（[[dcl.ambig.res#1]]）。
- 类型和表达式之间的歧义按能当 *type-id* 就当 *type-id* 处理（[[dcl.ambig.res#2]]），所以 `X<int()>` 里的 `int()` 是函数类型，不是值初始化表达式。

!!! lawyer "`sizeof(int())` 现在是表达式"
    `sizeof(int())` 过去有两种推导：`sizeof ( type-id )`，其中 *type-id* 是函数类型 `int()`；或者 `sizeof unary-expression`，操作数是带括号的值初始化 `(int())`。按能当 *type-id* 就当 *type-id*，过去选前者，然后因为对函数类型用 `sizeof` 而非良构。

    当前草案把 `sizeof`、`alignof`、C 风格转换、`new` 的括号形式和尾置返回类型中的 *type-id* 改成了 *nofun-type-id*（[[dcl.name]]），它不能表示函数类型。前一种推导不再成立，歧义消失，`sizeof(int())` 就是 `sizeof(int)`。[[dcl.ambig.res#2]] 的注 2 说的正是这一点。这里是修改语法本身消除了歧义。截至写作时，Clang 23 仍按旧规则报 `invalid application of 'sizeof' to a function type`。

### `a < b > (c)`：比较还是模板实参？

```cpp run ok
template<int N> int a(int x) { return N + x; }
constexpr int b = 2;
int r1 = a < b > (3);            // a 是模板：a<b>(3)，r1 == 5

namespace n {
  int a = 1, b = 2, c = 3;
  bool r2 = (a < b) > (c);       // 这里的 a 是 int：两次比较
}
```

`a < b > (c)` 既可以是两次比较 `(a < b) > (c)`，也可以是调用模板 `a` 的特化 `a<b>(c)`。决定因素是 [[temp.names#7]]：`<` 只在某些情况下被当作模板实参列表的开始，主要是它前面的名字经查找找到了模板（¶7.3.2），或者是一个非限定名，查找找到一个或多个函数，或者什么也没找到（¶7.3.3）。

`namespace n` 里去掉括号写 `a < b > (c)`，按标准是良构的，结果是 `false`。但本机 Clang 23 默认报错 `chained comparison 'X < Y > Z' does not behave the same as a mathematical expression`，这是一个默认当作错误的 `-Wparentheses` 诊断，可以关闭。所以上例加了括号。

查找什么也没找到时也把 `<` 当作模板实参列表的开始，是 C++20 的改动（[[P0846R0]]），目的是让 ADL 能找到函数模板：

```cpp run ok
namespace N {
  struct S {};
  template<int> void h(S) {}
}
void t() {
  N::S s;
  h<0>(s);   // C++20 起 OK：h 查不到任何东西，< 开始模板实参列表，
             // 之后 ADL 在 N 中找到 N::h
}
```

按 C++17 的规则，`h` 未声明，这行非良构。本机 Clang 23 在 `-std=c++17` 下作为扩展接受，给出 `-Wc++20-extensions` 警告。

在模板里，依赖的限定名在定义处查不到东西，解析器无从判断，需要写 `template`，例如 [[temp.names#7]] 例 1 中的 `p->template alloc<200>()`。

### `>>` 结束两层模板实参列表

```cpp
template<int> struct X {};
template<class> struct Y {};
Y<X<1>> x3;          // OK：>> 当作两个 >
Y<X<(6>>1)>> x5;     // OK：括号内的 >> 仍是右移
Y<X<6>>1>> x4;       // error: 第一个 >> 结束了 X<6> 和 Y<...>，之后无法解析
```

词法分析按最长匹配（[[g:maximal-munch]]）总是把 `>>` 切成一个记号（[[lex.pptoken#5]]）。[[temp.names#8]] 在解析阶段补了一条：在模板实参列表中，第一个非嵌套的 `>` 是结束符，第一个非嵌套的 `>>` 当作两个连续的 `>`，前一个结束当前的列表。非嵌套指不在括号内，所以 `x5` 的写法可以把右移留在模板实参里。C++11 之前没有这条规则，`Y<X<1>>` 必须写成 `Y<X<1> >`。

### `<::` 和 `[::`：最长匹配的例外

```cpp run ok
#include <vector>
struct S {};
std::vector<::S> v;   // < 单独成记号，::S 是全局限定名
int i = 1;
int arr[3];
int j = arr[::i];     // [ 单独成记号，::i 是下标
```

`<:` 是 `[` 的二合字母（[[lex.digraph]]），`[:` 是静态反射的拼接定界符。按最长匹配，`vector<::S>` 会被切成 `vector <: :S>`，即 `vector[:S>`。[[lex.pptoken#5]] 为此规定了例外：

- ¶5.2：`<::` 之后的字符既不是 `:` 也不是 `>` 时，`<` 单独成为一个记号；
- ¶5.3：`[::` 之后的字符不是 `:` 时，或者遇到 `[:>` 时，`[` 单独成为一个记号。

这里语法本身没有问题，问题出在记号怎么切分。词法语法只说明一个记号可以长什么样，实际怎么切由 [[lex.pptoken#5]] 决定。最常见的后果是 `x+++++y` 被切成 `x ++ ++ + y` 而非良构，尽管 `x ++ + ++ y` 能构成合法的表达式。

### `[[` 只能引入属性

```cpp run error
int y[5];
void f() {
  y[[] { return 2; }()] = 2;     // error: [[ 只能引入属性
  y[([] { return 2; }())] = 2;   // OK：加括号后两个 [ 不再相邻
}
```

属性说明符的语法是 `[ [ attribute-list ] ]`，两个 `[` 是独立的记号。于是 `[[` 也可能是下标运算符的 `[` 加上 lambda 引导符的 `[`。[[dcl.attr.grammar#9]] 直接规定：两个连续的左方括号只能用来引入属性说明符，或者出现在属性实参里。在不允许属性的位置出现 `[[`，即使能匹配别的产生式，程序也非良构。

属性可以出现的位置很多，让解析器去试探代价大，人读起来也难以判断。用一条简单的规则一刀切，代价只是偶尔多写一对括号。

### `(a)-b`：转换还是减法？

`(a)-b` 可以是 C 风格转换（把 `-b` 转换为类型 `a`），也可以是括号里的 `a` 减去 `b`。这里没有专门的消歧条款：`a` 是类型名时只有前一种推导成立，否则只有后一种。在模板里，依赖名 `T::x` 默认不是类型，要写 `(typename T::x)-b` 才是转换（[[temp.res]]）。

## 按章导读

下表给出附录 A 每个子条款从哪条产生式读起，以及对应的正文和本站导读页。

| 附录子条款 | 起点和关键结构 | 正文 |
|---|---|---|
| A.3 [gram.lex] | *preprocessing-token* 和 *token*；各种字面量、*identifier* | [[lex]] |
| A.4 [gram.basic] | 起始符号 *translation-unit*；*splice-specifier* | [[basic]] |
| A.5 [gram.expr] | 从 *primary-expression* 一路到 *expression* | [[expr]] |
| A.6 [gram.stmt] | *statement* | [[stmt]] |
| A.7 [gram.dcl] | *declaration*、*simple-declaration*、*declarator* | [[dcl]] |
| A.8 [gram.module] | *module-declaration*、*module-import-declaration* | [[module]] |
| A.9 [gram.class] | *class-specifier*、*member-declaration* | [[class]] |
| A.10 [gram.over] | *operator-function-id*、*literal-operator-id* | [[over]] |
| A.11 [gram.temp] | *template-declaration*、*template-parameter*、*template-id* | [[temp]] |
| A.12 [gram.except] | *try-block*、*handler*、*noexcept-specifier* | [[except]] |
| A.13 [gram.cpp] | *preprocessing-file*、*group-part* | [[cpp]] |

下面只记各章语法里容易读错或值得注意的地方。

### 词法和翻译单元

- 词法语法以字符为单位，产出预处理记号；阶段 7 再把预处理记号转换成记号（[[lex.pptoken]]、[[lex.token]]）。
- *pp-number* 故意比数值字面量宽松，`1.2.3` 和 `0xe+foo` 都是一个 *pp-number*（[[lex.ppnumber]]）。
- *translation-unit* 是整个文法的起始符号，它的两个备选项分别是普通翻译单元和模块单元（[[module.unit]]）。一个翻译单元在语法上就是一串声明，C++ 没有顶层语句。

### 表达式：用嵌套表示优先级

标准里没有运算符优先级表，优先级和结合性由产生式的嵌套表示。从紧到松：

| 层级 | 非终结符 | 运算符 | 详见 |
|---|---|---|---|
| 初等 | *primary-expression* | 字面量、`this`、`( )`、名字、lambda、折叠、requires、拼接 | [[expr.prim]] |
| 后缀 | *postfix-expression* | `[]` `()` `.` `->` 后缀 `++ --`、具名转换、`typeid`、函数式转换 | [[expr.post]] |
| 一元 | *unary-expression* | 前缀 `++ --`、`* & + - ! ~`、`sizeof`、`alignof`、`co_await`、`noexcept`、`new`、`delete`、`^^` | [[expr.unary]] |
| 转换 | *cast-expression* | `( nofun-type-id ) cast-expression` | [[expr.cast]] |
| 成员指针 | *pm-expression* | `.*` `->*` | [[expr.mptr.oper]] |
| 乘、加、移位 | *multiplicative-*、*additive-*、*shift-expression* | `* / %`、`+ -`、`<< >>` | [[expr.mul]]、[[expr.add]]、[[expr.shift]] |
| 三路比较 | *compare-expression* | `<=>` | [[expr.spaceship]] |
| 关系、相等 | *relational-*、*equality-expression* | `< > <= >=`、`== !=` | [[expr.rel]]、[[expr.eq]] |
| 位运算、逻辑 | *and-* 到 *logical-or-expression* | `& ^ \| && \|\|` | [[expr.bit.and]] 等 |
| 条件 | *conditional-expression* | `?:` | [[expr.cond]] |
| 赋值 | *assignment-expression* | `=` 等、`throw`、`co_yield` | [[expr.assign]] |
| 逗号 | *expression* | `,` | [[expr.comma]] |

- *compare-expression* 夹在移位和关系之间，所以 `a <=> b < 0` 解析为 `(a <=> b) < 0`。
- 函数式转换 `T(x)`、`T{x}` 在后缀表达式里，C 风格转换 `(T)x` 在 *cast-expression* 里，两者优先级不同（[[expr.type.conv]]）。
- 赋值的右侧是 *initializer-clause*，所以 `x = {1, 2}` 在语法上成立。
- *constant-expression* 在语法上就是 *conditional-expression*，常量表达式的位置不能直接写顶层的赋值或逗号，要加括号。

### 语句和声明

- *declaration-statement* 就是 *block-declaration*，所以块里不能定义函数，也不能声明模板。
- *statement* 的多数备选项以可选的属性开头，但 *declaration-statement* 和 *labeled-statement* 没有，它们的属性属于声明和标号自己的语法。C++26 新增了 *expansion-statement*（`template for`，[[stmt.expand]]）和 *assertion-statement*（`contract_assert`，[[stmt.contract.assert]]）。
- *simple-declaration* 由左边的说明符序列和右边的声明符列表组成，每个声明符各带初始化器（[[dcl.spec]]、[[dcl.decl]]）。
- 声明符分两层：前缀的 `*`、`&`、`&&`、`C::*` 在 *ptr-declarator* 里，后缀的 `()`、`[]` 在 *noptr-declarator* 里，后缀结合得更紧。所以 `int *a[3]` 是指针的数组，`int (*a)[3]` 是指向数组的指针（[[dcl.meaning]]）。
- *type-id* 是去掉名字的声明，用 *abstract-declarator*；转换表达式里用的 *nofun-type-id* 不能表示函数类型（[[dcl.name]]）。
- 属性实参的内容是 *balanced-token-seq*：任意记号，只要求 `()`、`[]`、`{}` 配对。所以各编译器的厂商属性可以有自己的实参语法。

### 模块、类、重载、模板、异常

- 模块的产生式用的是 *module-keyword*、*import-keyword*、*export-keyword*，而不是字面的 `module`、`import`。这三个记号由预处理器处理模块指令时生成，没有可见的拼写（[[lex.pptoken#4]]），所以普通代码里 `import`、`module` 仍可以当标识符用（[[lex.name]]）。
- *member-declarator* 比命名空间作用域的声明符多出 `override`、`final`、`= 0`、位域宽度和默认成员初始化器（[[class.mem]]）。
- *operator* 列出了全部可重载的运算符，包括 `co_await`、`()`、`[]`、`<=>`、`new[]`（[[over.oper]]）。
- 模板模板形参细分为 *type-tt-parameter*、*variable-tt-parameter*、*concept-tt-parameter*，分别接受类或别名模板、变量模板和概念（[[temp.param]]）。
- *requires-clause* 里只允许用 `&&`、`||` 连接初等表达式，`requires sizeof(T) > 4` 必须写成 `requires (sizeof(T) > 4)`（[[temp.pre]]）。
- *template-argument* 的备选项中 *constant-expression* 排在 *type-id* 前面，但两者都能匹配时按 [[dcl.ambig.res#2]] 选 *type-id*。
- *throw-expression* 不在异常一章的语法里，而在表达式语法里（[[expr.throw]]）。

### 预处理指令

预处理指令是一套独立的语法：输入是预处理记号，换行在这里是有意义的记号，指令以行为单位。起始符号 *preprocessing-file* 有两个备选项：一串 *group*（普通文件），或者 *module-file*（以全局模块片段或 `module` 指令开头的模块单元文件）。*group-part* 分为控制行（`#include`、`#embed`、`#define` 等）、条件包含、普通文本行和有条件支持的指令。模块和导入指令没有 `#`（[[cpp.module]]、[[cpp.import]]）。总览见 [[cpp.pre]]。

## 思考题

!!! question "1. `x = y < z > w;` 中的 `<` 一定是小于号吗？"

<details markdown="1">
<summary>答案</summary>

不一定。如果 `y` 是非限定名，查找找到模板，或者找到一个或多个函数，或者什么也没找到，按 [[temp.names#7]] 的 ¶7.3，`<` 就开始模板实参列表，`y<z>` 是 *template-id*，接下来的 `w` 让表达式无法解析而报错。只有查找找到变量这类非函数实体时，它才是两次比较。
</details>

!!! question "2. 附录 A 的一条产生式和正文中的同名产生式不一致时，以哪个为准？"

<details markdown="1">
<summary>答案</summary>

以正文为准。附录 A 是资料性的，[gram.general] ¶1 明说它不是对语言的精确陈述，有规范效力的语法在正文各条款中。标准的源文件里附录 A 是从正文的语法块自动汇总生成的，两者本应一致；如果不一致，属于编辑错误。
</details>

!!! question "3. `T(a)[5];` 是声明还是表达式？`T` 是类类型。"

<details markdown="1">
<summary>答案</summary>

声明：声明一个名为 `a`、类型为 5 个 `T` 的数组的变量。它在语法上可以是声明（声明符 `(a)[5]`），按 [[stmt.ambig#1]] 就是声明。[[stmt.ambig#2]] 的例 1 有同样的例子 `T(e)[5];`。
</details>
