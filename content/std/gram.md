---
title: 文法摘要
summary: 附录 A 把散落在各章的产生式汇总到一处，只供参考：它接受的是合法 C++ 的超集，表达式与声明之间的消歧、名字是不是类型、访问控制和类型规则都在正文里。本页讲这些限制、gram.key 中"由声明引入的上下文相关关键字"，按章给出关键产生式的导读，并逐步拆解几段难解析的代码。
status: done
covers: *
papers: P0846R0
related: syntax, lex.pptoken, stmt.ambig, dcl.ambig.res, temp.names, dcl.attr.grammar
tags: 语法, 导读, 附录, 解析
updated: 2026-10-18
---

附录 A [gram] 是**资料性**（informative）附录：它把正文各条款开头的语法产生式按章节顺序汇总在一起，原样复制，没有新增任何规则。真正有规范效力的是正文里的那一份。所以引用语法时，应当引用正文条款（如 [[dcl.decl]]），而不是 "A.7"。

本页不重抄这份语法（它有一千多行，正文各页已经分别讲解）。本页讲三件事：

1. 附录自己声明的限制：为什么"符合这份语法"不等于"是合法 C++"；
2. [gram.key] 里的"上下文相关关键字"是什么意思；
3. 一份导读：每一章的语法从哪条产生式开始读、关键结构是什么、去哪一页看详细解释；最后拆解几段需要消歧规则才能解析的代码。

读产生式的记法（斜体非终结符、opt 下标、*X-seq* / *X-list* 等）见 [[syntax]]。

## 这份语法"不是语言的精确陈述"（gram.general ¶1）

!!! std
    "This summary of C++ grammar is intended to be an aid to comprehension. It is not an exact statement of the language."

    这份摘要只是帮助理解，并不精确地描述语言。

¶1 接着给出了两条具体的限制。

**第一，它接受的是合法 C++ 构造的超集**（accepts a superset of valid C++ constructs）。语法只管"记号排列的形状"，很多约束写在正文的文字里。例如：

```cpp error
int;                         // 符合 simple-declaration 的语法：
                             //   decl-specifier-seq init-declarator-list_opt ;
                             // 但 [dcl.pre]/6 规定只有声明类或枚举时才能省略声明符
struct A { virtual int x; }; // 符合 member-declaration 的语法；
                             // virtual 只能用于非静态成员函数 [dcl.fct.spec]
```

这两行都能被语法推导出来，却都非良构。第一行的限制在 [[dcl.pre#6]]，第二行在 [[dcl.fct.spec]]。（实测 Clang 23 对 `int;` 只给出 `-Wmissing-declarations` 警告；警告也算诊断，所以这不违反标准。）

为什么不把这些限制写进语法？因为写进去会让语法爆炸。以 *member-declaration* 为例，它的第一个备选项三个部分全是可选的：

```text
member-declaration:
    attribute-specifier-seq_opt decl-specifier-seq_opt member-declarator-list_opt ;
    ...
```

"哪些说明符可以和哪些声明符组合"如果用产生式表达，需要把说明符的每种组合拆成单独的非终结符。标准的做法是：语法宽松地描述形状，再用文字规定"shall"。

**第二，消歧规则不在语法里。** ¶1 点名了三处：[[stmt.ambig]]、[[dcl.spec]]、[[class.member.lookup]]，它们用来区分表达式和声明。此外，访问控制、二义性和类型规则用来排除"语法上合法但没有意义"的构造。

换句话说，这份语法本身是**有二义性的**：同一串记号可以有不止一棵语法树。比如 `T(x);` 既能按 *expression-statement* 推导，也能按 *declaration-statement* 推导。语法本身不告诉你选哪棵，选择规则在 [[stmt.ambig#1]]（见下文"难解析的代码"）。

!!! note "对照：不是 LR(1)，也不是上下文无关"
    C++ 的语法用一般的 BNF 写成，但实际的解析需要两样语法之外的东西：**名字查找的结果**（一个标识符是不是类型名、是不是模板名），以及**消歧规则**（两种推导都成立时选哪个）。所以主流编译器（GCC、Clang、MSVC）都用手写的递归下降解析器，在解析过程中同时做名字查找，必要时**试探性解析**（tentative parsing）：先按声明试一遍，失败再回退按表达式解析。

## 上下文相关的关键字（gram.key ¶1）

¶1 说，**typedef、namespace、类、枚举和模板声明**会向程序引入新的"上下文相关关键字"（context-dependent keywords）。随后列出的是这些非终结符：

| 非终结符 | 形式 | 由什么声明引入 | 详见 |
|---|---|---|---|
| *typedef-name* | *identifier*、*simple-template-id* | typedef、别名声明、别名模板 | [[dcl.typedef]] |
| *namespace-name* | *identifier*、*namespace-alias* | 命名空间定义 | [[namespace.def]] |
| *namespace-alias* | *identifier* | 命名空间别名定义 | [[namespace.alias]] |
| *class-name* | *identifier*、*simple-template-id* | 类声明、类模板 | [[class.name]] |
| *enum-name* | *identifier* | 枚举声明 | [[dcl.enum]] |
| *simple-template-name* | *identifier* | 模板声明 | [[temp.names]] |

这里的"关键字"不是 [[lex.key]] 意义上的关键字，那些是保留的拼写，`int` 在任何地方都是 `int`。这里说的是：一个普通的 *identifier*，一旦被某个声明引入成类型名、模板名等，它在**解析器眼里**就像关键字一样改变了后续记号的含义。例如：

```cpp run ok
struct T { T() {} };
int U(int x) { return x; }
int v = 0;

void f() { T(v); }   // T 是 class-name：声明，等价于 T v;（遮蔽全局的 v）
void g() { U(v); }   // U 不是类型名：以 ::v 为实参调用 U
```

`T(v);` 和 `U(v);` 的记号形状完全一样，`T` 和 `U` 都是 *identifier*。区别只在名字查找的结果：查找发现 `T` 是类，于是 `T` 可以充当 *class-name*，进而充当 *simple-type-specifier*，语句才有了声明的读法。这正是 [[syntax]] ¶2 讲 *X-name* 命名惯例时的意思：*X-name* 是"在上下文中有特定含义的标识符"。

这套说法来自 C 的传统。C 的 typedef 名就会改变解析：`a * b;` 在 `a` 是 typedef 名时是声明，否则是乘法表达式。C 编译器的经典做法是让词法分析器查符号表，把 typedef 名作为单独的记号种类返回给解析器（即所谓 "lexer hack"）。C++ 把这种依赖扩大到了类名、模板名和命名空间名，于是在模板中出现了它解决不了的情形：依赖名在定义处无法查找，必须由程序员用 `typename` 和 `template` 告诉解析器（[[temp.res]]、[[temp.names#7]]）。

!!! note "这张表并不完整"
    *concept-name*（[[temp.concept]]）同样是由模板声明引入的 *identifier*，但不在 [gram.key] 的列表里。别把这张表当作"所有 *X-name*"的清单；它只汇总了历史上被称为上下文相关关键字的那几个。

## 按章导读

下面每一节对应附录 A 的一个子条款。讲的是"从哪里读起、关键结构是什么"，详细内容在链接的条款页。

### 词法约定（gram.lex，对应第 5 章）

词法语法以**字符**为单位，产出**预处理记号**（*preprocessing-token*）。关键产生式：

- *preprocessing-token*：*header-name*、三个没有拼写的 *import-keyword* / *module-keyword* / *export-keyword*、*identifier*、*pp-number*、字符与字符串字面量（含用户定义的）、*preprocessing-op-or-punc*，以及兜底的"不能构成以上任何一种的单个非空白字符"。见 [[lex.pptoken]]。
- *token*：预处理之后，阶段 7 把预处理记号转换成**记号**（*token*）：*identifier*、*keyword*、*literal*、*operator-or-punctuator*。见 [[lex.token]]。
- *identifier*：基于 Unicode XID 属性，见 [[lex.name]] 和 [[uaxid]]。
- *pp-number*：故意比数值字面量宽松（`1.2.3`、`0xe+foo` 都是一个 *pp-number*），见 [[lex.ppnumber]]。
- 各种字面量：*integer-literal*、*floating-point-literal*、*character-literal*、*string-literal*（含 *raw-string*）、*user-defined-literal*，见 [[lex.literal]]。
- *universal-character-name*：`\u`、`\U`、`\u{...}`、`\N{...}` 四种形式，见 [[lex.charset]]。

!!! pitfall "词法语法不决定怎么切分记号"
    *preprocessing-token* 的产生式只说明"一个记号可以长什么样"。同一串字符可以有多种切法，实际怎么切由 [[lex.pptoken#5]] 决定：通常取**最长匹配**（[[g:maximal-munch]]），外加原始字符串、`<::`、`[::`、*header-name* 几个例外。所以 `x+++++y` 被切成 `x ++ ++ + y` 而非良构，尽管 `x ++ + ++ y` 能构成合法的表达式。

### 基础（gram.basic，对应第 6 章）

这一章的语法只有三条：*translation-unit*，以及静态反射用的 *splice-specifier*（`[: constant-expression :]`）和 *splice-specialization-specifier*。

*translation-unit* 是整个文法的**起始符号**：

```text
translation-unit:
    declaration-seq_opt
    global-module-fragment_opt module-declaration declaration-seq_opt private-module-fragment_opt
```

第一行是普通 TU；第二行是模块单元（[[module.unit]]）。一个 TU 在语法层面就是一串声明，C++ 没有"顶层语句"。见 [[basic.link]] 和 [[basic.splice]]。

### 表达式（gram.expr，对应第 7 章）

从 *primary-expression* 读起，一路向上到 *expression*。这一串产生式用嵌套**编码了优先级与结合性**，C++ 标准里没有运算符优先级表（详见 [[syntax]] 中对 *assignment-expression* 的解读）。从紧到松：

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
| 位运算、逻辑 | *and-* … *logical-or-expression* | `& ^ \| && \|\|` | [[expr.bit.and]] 等 |
| 条件 | *conditional-expression* | `?:` | [[expr.cond]] |
| 赋值 | *assignment-expression* | `=` 等、`throw`、`co_yield` | [[expr.assign]] |
| 逗号 | *expression* | `,` | [[expr.comma]] |

几处值得注意：

- *compare-expression* 夹在移位和关系之间：`a <=> b < 0` 解析为 `(a <=> b) < 0`，这是比较结果和 0 比较的惯用写法能成立的原因。
- 函数式转换 `T(x)`、`T{x}` 在 *postfix-expression* 里（以 *simple-type-specifier* 或 *typename-specifier* 开头），而 C 风格转换 `(T)x` 在 *cast-expression* 里，两者优先级不同。见 [[expr.type.conv]]。
- *assignment-expression* 的右边是 *initializer-clause*，不是 *assignment-expression*，所以 `x = {1, 2}` 在语法上成立（[[expr.assign]]）。
- *constant-expression* 在语法上就是 *conditional-expression*：常量表达式的位置上不能直接写顶层的赋值或逗号，要加括号。是否真的是常量是语义规则（[[expr.const]]）。
- *id-expression*、*unqualified-id*、*qualified-id*、*nested-name-specifier* 是"名字"的语法，表达式和声明都用它们，见 [[expr.prim.id]]。

### 语句（gram.stmt，对应第 8 章）

*statement* 的大多数备选项都以 *attribute-specifier-seq*<sub>opt</sub> 开头，但 *declaration-statement* 和 *labeled-statement* 没有：这两种语句的属性分别属于声明和标号自身的语法。关键产生式：

- *expression-statement*：`expression_opt ;`，空语句 `;` 也是它。
- *declaration-statement*：就是 *block-declaration*，所以块内只能出现 *block-declaration* 允许的声明（不能定义函数、不能声明模板）。
- *selection-statement*、*iteration-statement*、*jump-statement*：`if`/`switch`、`while`/`do`/`for`/范围 `for`、`break`/`continue`/`return`/`goto`/`co_return`。
- *expansion-statement*：`template for (...)`，见 [[stmt.expand]]。
- *assertion-statement*：`contract_assert ( conditional-expression ) ;`，见 [[stmt.contract.assert]]。
- *init-statement* 和 *condition*：带初始化的 `if`/`switch`/范围 `for`，以及条件中的声明。

总览见 [[stmt.pre]]；表达式语句与声明语句的歧义见 [[stmt.ambig]]。

### 声明（gram.dcl，对应第 9 章）

这是附录中最长的一节。读法：

1. *declaration* 分为 *name-declaration* 和 *special-declaration*（显式实例化、显式特化、`export` 声明）。*block-declaration* 是能出现在块内的那一部分。总览见 [[dcl.pre]]。
2. *simple-declaration* = *decl-specifier-seq* + *init-declarator-list* + `;`。说明符（`static`、`const`、`int`、类名…）在左边，**声明符**（*declarator*）在右边，每个声明符各自带初始化器。见 [[dcl.spec]]、[[dcl.decl]]。
3. 声明符分两层：*ptr-declarator*（前缀的 `*`、`&`、`&&`、`C::*`）和 *noptr-declarator*（后缀的 `()`、`[]`，以及括号）。后缀比前缀结合得紧，所以 `int *a[3]` 是指针数组，`int (*a)[3]` 是数组指针。见 [[dcl.meaning]]。
4. *type-id* 是"去掉名字的声明"，用 *abstract-declarator*；转换表达式里用的 *nofun-type-id* 不能表示函数类型。见 [[dcl.name]]。
5. 初始化器：*brace-or-equal-initializer*、*braced-init-list*、指派初始化器，见 [[dcl.init]]。
6. 函数定义 *function-definition*（含 `= default`、`= delete("理由")`），见 [[dcl.fct.def]]；函数契约说明符 `pre`/`post`，见 [[dcl.contract.func]]。
7. 其余：枚举 [[dcl.enum]]、命名空间 [[basic.namespace]]、`using` 声明 [[namespace.udecl]]、结构化绑定 [[dcl.struct.bind]]、链接说明 [[dcl.link]]、`asm` [[dcl.asm]]、属性与注解 [[dcl.attr]]。

!!! note "*balanced-token-seq*"
    属性实参 *attribute-argument-clause* 的内容是 *balanced-token-seq*：任意记号，只要求 `()`、`[]`、`{}` 配对。这让各编译器的厂商属性可以有自己的实参语法。

### 模块（gram.module，对应第 10 章）

*module-declaration*、*module-import-declaration*、*export-declaration*、*global-module-fragment*、*private-module-fragment*。注意产生式里用的是 *module-keyword*、*import-keyword*、*export-keyword*，而不是字面的 `module`、`import`：这三个记号由预处理器处理模块指令时生成（[[lex.pptoken#4]]），没有可见的拼写。这样，普通代码里的 `import`、`module` 仍可以作标识符使用（[[lex.name]] ¶2）。见 [[module.unit]]、[[module.import]]、[[module.interface]]。

### 类（gram.class，对应第 11 章）

- *class-specifier* = *class-head* `{` *member-specification*<sub>opt</sub> `}`；*class-head* 中依次是 *class-key*、属性、类名、`final`（*class-property-specifier*）、基类子句。见 [[class.pre]]。
- *member-declaration* 和 *member-declarator*：成员声明的语法和命名空间作用域的声明不同，它多了 *virt-specifier*（`override`、`final`）、*pure-specifier*（`= 0`）、位域（`: constant-expression`）和默认成员初始化器。见 [[class.mem]]。
- *conversion-function-id*（`operator T`），见 [[class.conv.fct]]。
- *base-clause*（[[class.derived]]）和 *ctor-initializer*（[[class.base.init]]）。

### 重载（gram.over，对应第 12 章）

只有三条：*operator-function-id*（`operator+` 等）、*operator*（可重载运算符的完整列表，含 `co_await`、`()`、`[]`、`<=>`、`new[]` 等）、*literal-operator-id*（`operator""_x`）。见 [[over.oper]]、[[over.literal]]。

### 模板（gram.temp，对应第 13 章）

- *template-declaration* = *template-head* + 声明；*template-head* = `template < template-parameter-list >` + 可选的 *requires-clause*。见 [[temp.pre]]。
- *template-parameter*：类型形参、常量形参（就是一个 *parameter-declaration*）、模板模板形参。模板模板形参现在细分为 *type-tt-parameter*、*variable-tt-parameter*、*concept-tt-parameter*，分别接受类/别名模板、变量模板和概念。见 [[temp.param]]。
- *simple-template-id*、*template-id*、*template-argument*：见 [[temp.names]]。注意 *template-argument* 的备选项中 *constant-expression* 排在 *type-id* 前面，但两者都能匹配时按 [[dcl.ambig.res#2]] 选 *type-id*。
- *requires-clause* 中的 *constraint-logical-or-expression* 只允许 *primary-expression* 用 `&&`、`||` 连接；`requires sizeof(T) > 4` 必须写成 `requires (sizeof(T) > 4)`。见 [[temp.pre]]。
- 其余：*concept-definition* [[temp.concept]]、*deduction-guide* [[temp.deduct.guide]]、*typename-specifier* [[temp.res]]、显式实例化 [[temp.explicit]]、显式特化 [[temp.expl.spec]]。

### 异常处理（gram.except，对应第 14 章）

*try-block*、*function-try-block*（可以包住构造函数的 *ctor-initializer*）、*handler*（`catch (exception-declaration)`）、*noexcept-specifier*。*throw-expression* 不在这里，它属于表达式语法（[[expr.throw]]）。见 [[except.pre]]、[[except.handle]]、[[except.spec]]。

### 预处理指令（gram.cpp，对应第 15 章）

这是一套**独立的语法**：它的输入是预处理记号，而且 *new-line* 在这里是有意义的记号（指令以行为单位）。起始符号是 *preprocessing-file*，它有两个备选项：一串 *group*（普通文件），或 *module-file*（模块单元文件：以 `module;` 开始的全局模块片段或 `module` 指令开头，此前只能有 `#line` 指令）。

- *group-part*：*control-line*（`#include`、`#embed`、`#define`、`#undef`、`#line`、`#error`、`#warning`、`#pragma`、空指令 `#`）、*if-section*（条件包含）、*text-line*（普通的一行代码）、以及 *conditionally-supported-directive*。
- *pp-module*、*pp-import*：模块和导入指令，它们没有 `#`，见 [[cpp.module]]、[[cpp.import]]。
- `__has_include`、`__has_embed`、`__has_cpp_attribute` 表达式和 `__VA_OPT__` 也在这里。

总览见 [[cpp.pre]]；条件包含 [[cpp.cond]]、宏替换 [[cpp.replace]]、`#embed` [[cpp.embed]]。

## 难解析的代码：语法之外的规则如何决定解析

下面每个例子里，语法本身都允许不止一种读法，或者给出的读法与直觉不同。每个例子都给出最终起作用的条款。

### `a < b > (c)`：比较还是模板实参列表？

语法上，`a < b > (c)` 既可以是 *relational-expression* `(a < b) > (c)`，也可以是 *postfix-expression* `a<b>(c)`（调用模板 `a` 的特化）。决定因素是 [[temp.names#7]]：`<` 只在下列情况下被当作模板实参列表的开始——它前面的名字经查找找到模板（¶7.3.2），或者是一个**非限定名，且查找找到一个或多个函数，或者什么也没找到**（¶7.3.3），或者跟在 `template` 关键字后面，等等。

```cpp run ok
template<int N> int a(int x) { return N + x; }
constexpr int b = 2;
int r1 = a < b > (3);            // a 是模板：a<b>(3)，r1 == 5

namespace n {
  int a = 1, b = 2, c = 3;
  bool r2 = (a < b) > (c);       // 这里的 a 是 int：两次比较
}
```

`namespace n` 里如果去掉括号写 `a < b > (c)`，标准上是良构的（两次比较，结果是 `false`）。但实测 Clang 23 默认报错 "chained comparison 'X < Y > Z' does not behave the same as a mathematical expression"，这是一个默认按错误处理的 `-Wparentheses` 诊断，可以用 `-Wno-parentheses` 关闭。所以上例加了括号。

¶7.3.3 中"什么也没找到也算模板"是 C++20 的改动（[[P0846R0]]），目的是让 ADL 能找到函数模板：

```cpp run ok
namespace N {
  struct S {};
  template<int> void h(S) {}
}
void t() {
  N::S s;
  h<0>(s);   // C++20 起 OK：h 查找不到任何东西，< 当作模板实参列表；
             // 随后 ADL 在 N 中找到 N::h。C++17 中这是"h 未声明"
}
```

在模板中，依赖的限定名查找不到东西，解析器无从判断，需要写 `template`（[[temp.names#7]] 的例 1：`p->template alloc<200>()`）。

### `T(x);`：声明还是表达式？

如果 `T` 是类型名，`T(x);` 有两种推导：函数式转换 `T(x)` 构成的表达式语句；或者声明一个类型为 `T`、名为 `x` 的变量，声明符外面加了一对多余的括号。[[stmt.ambig#1]] 的规则是：**能当声明就当声明**。

```cpp run error
struct T { T(int) {} T() {} };
void f() {
  int x = 1;
  T(x);        // 声明：T x;  而不是用 x 构造一个临时对象
               // error: x 重定义（与上一行的 int x 在同一作用域）
}
```

Clang 23 对 `T(x);` 给出 `-Wvexing-parse` 警告（"parentheses were disambiguated as redundant parentheses around declaration of variable named 'x'"），然后报 x 重定义。

规则的几个细节：

- 判断**只看语法**，[[stmt.ambig#3]]：除了"某个名字是不是 *type-name*"之外，名字的含义不参与消歧。消歧在先，解析在后，所以一个被判定为声明的语句可能是非良构的声明，编译器不会回头改按表达式解析。
- 有时要看完整条语句才能判断。`T(a)->m = 7;` 不可能是声明，所以它是表达式；`T(*d)(int);` 可以是声明（函数指针 `d`），所以它是声明。见 [[stmt.ambig#2]] 的例子。
- 同样的规则在声明内部也适用，这就是 "most vexing parse"：`S w(int());` 声明的是函数，不是对象（[[dcl.ambig.res#1]]）。
- 类型和表达式之间的歧义：能当 *type-id* 就当 *type-id*（[[dcl.ambig.res#2]]），所以 `X<int()>` 中的 `int()` 是函数类型，不是值初始化表达式。

!!! lawyer "`sizeof(int())` 现在是表达式"
    语法上 `sizeof(int())` 曾有两种推导：`sizeof ( type-id )`，*type-id* 为函数类型 `int()`；或 `sizeof unary-expression`，其中是带括号的值初始化表达式 `(int())`。按"能当 *type-id* 就当 *type-id*"，过去选前者，然后因为对函数类型用 `sizeof` 而非良构。

    当前草案把 `sizeof`、`alignof`、C 风格转换、`new` 的括号形式和尾置返回类型中的 *type-id* 改成了 *nofun-type-id*（[[dcl.name]]），它不能表示函数类型。于是前一种推导不再成立，歧义消失，`sizeof(int())` 就是 `sizeof(int)`。[[dcl.ambig.res#2]] 的注 2 说的就是这一点，例 2 把 `sizeof(int());` 标为 expression。这里语法本身的修改消除了歧义，不需要额外的消歧规则。截至写作时 Clang 23 仍按旧规则报 "invalid application of 'sizeof' to a function type"。详见 [[dcl.ambig.res]]。

### `>>` 结束两层模板实参列表

```cpp run
template<int> struct X {};
template<class> struct Y {};
Y<X<1>> x3;          // OK：>> 被当作两个 >
Y<X<(6>>1)>> x5;     // OK：括号内的 >> 是"嵌套的"，仍是右移
Y<X<6>>1>> x4;       // error: 第一个 >> 结束了 X<6>（也结束了 Y<...>），后面的 1>> x4 无法解析
```

按最长匹配，词法分析总是把 `>>` 切成一个记号（[[lex.pptoken#5]]）。[[temp.names#8]] 在**解析**阶段补了一条：在 *template-argument-list* 中，第一个**非嵌套**的 `>` 是结束定界符；第一个非嵌套的 `>>` 被当作两个连续的 `>`，第一个结束当前的模板实参列表。"非嵌套"指不在括号内：在 `()` 中的 `>` 和 `>>` 仍是运算符，这就是 `x5` 写法的用途。

C++11 之前没有这条规则，`Y<X<1>>` 必须写成 `Y<X<1> >`。

### `<::` 与 `[::`：二合字母和拼接的例外

`<:` 是 `[` 的二合字母（[[lex.digraph]]），`[:` 是静态反射的拼接定界符。按最长匹配，`vector<::S>` 会被切成 `vector <: :S>`，即 `vector[:S>`，于是出错。[[lex.pptoken#5]] 为此规定了例外：

- ¶5.2：`<::` 后面的字符既不是 `:` 也不是 `>` 时，`<` 单独成为一个记号；
- ¶5.3：`[::` 后面的字符不是 `:` 时（或遇到 `[:>`），`[` 单独成为一个记号，而不是拼接定界符 `[:` 的开头。

```cpp run ok
#include <vector>
struct S {};
std::vector<::S> v;   // < 单独成记号，::S 是全局限定名
int i = 1;
int arr[3];
int j = arr[::i];     // [ 单独成记号，::i 是下标
```

这是一个"语法本身没问题，问题出在记号切分"的例子：语法摘要中 *preprocessing-op-or-punc* 只列出 `<:` 和 `[:` 是合法的记号，什么时候**不**切成它们，要看 [[lex.pptoken]]。

### `[[`：属性、lambda 还是数组下标？

*attribute-specifier* 的语法写作 `[ [ attribute-list ] ]`，即**两个独立的 `[` 记号**，中间可以有空白。于是 `[[` 也可能是"下标运算符 `[` + lambda 引导符 `[`"或者"下标 + 数组字面量开头"。[[dcl.attr.grammar#9]] 直接规定：两个连续的左方括号只能用来引入 *attribute-specifier*，或出现在属性实参的 *balanced-token-seq* 中。在不允许属性的位置出现 `[[`，即使能匹配别的产生式，程序也非良构。

```cpp run
int y[5];
void f() {
  y[[] { return 2; }()] = 2;     // error: [[ 只能引入属性，即使这里不允许属性
  y[([] { return 2; }())] = 2;   // OK：加括号，[ 和 [ 不再连续
}
```

为什么不让解析器去试探？因为属性可以出现在很多位置，试探的代价大，而且"到底是哪一种"对人也难以判断。用一条简单的词法级规则一刀切，代价只是偶尔多加一对括号。

### `(a)-b`：C 风格转换还是减法？

`(a)-b` 可以是 *cast-expression* `( nofun-type-id ) cast-expression`（把 `-b` 转换为类型 `a`），也可以是 *additive-expression*（括号里的 `a` 减去 `b`）。这里没有专门的消歧条款：如果 `a` 是类型名，只有前一种推导能成立；否则只有后一种。这又是"*X-name* 依赖查找结果"的例子。在模板中，`(T::x)-b` 在 `T::x` 是依赖名时默认不是类型，要写 `(typename T::x)-b` 才是转换（[[temp.res]]）。

## 附录 A 与正文的对应

| 附录子条款 | 正文 | 本站导读 |
|---|---|---|
| A.1 [gram.general] | — | 本页 |
| A.2 [gram.key] | [[dcl.typedef]]、[[namespace.def]]、[[class.name]]、[[dcl.enum]]、[[temp.names]] | 本页 |
| A.3 [gram.lex] | 第 5 章 | [[lex]] |
| A.4 [gram.basic] | 第 6 章 | [[basic]] |
| A.5 [gram.expr] | 第 7 章 | [[expr]] |
| A.6 [gram.stmt] | 第 8 章 | [[stmt]] |
| A.7 [gram.dcl] | 第 9 章 | [[dcl]] |
| A.8 [gram.module] | 第 10 章 | [[module]] |
| A.9 [gram.class] | 第 11 章 | [[class]] |
| A.10 [gram.over] | 第 12 章 | [[over]] |
| A.11 [gram.temp] | 第 13 章 | [[temp]] |
| A.12 [gram.except] | 第 14 章 | [[except]] |
| A.13 [gram.cpp] | 第 15 章 | [[cpp]] |

## 思考题

!!! question "1. `x = y < z > w;` 中的 `<` 一定是小于号吗？"

<details markdown="1">
<summary>答案</summary>

不一定。如果 `y` 是非限定名，且查找找到一个函数模板（或者找到一个或多个函数，或者什么也没找到），按 [[temp.names#7]] ¶7.3，`<` 被当作模板实参列表的开始，`y<z>` 是 *template-id*，接下来的 `w` 就会使表达式无法解析而报错。只有查找找到的是变量等非函数实体时，它才是两次比较。
</details>

!!! question "2. 为什么说附录 A 中出现的一条产生式和正文中同名产生式不一致时，以正文为准？"

<details markdown="1">
<summary>答案</summary>

附录 A 标注为 informative（资料性），[gram.general] ¶1 明说它"不是语言的精确陈述"。规范性的语法在各条款正文中。实际上标准的 LaTeX 源码里，附录 A 是从正文的语法块自动汇总生成的，两者应当一致；如果出现差异，属于编辑错误，应当按正文理解。
</details>

!!! question "3. 下面的语句是声明还是表达式？`T(a)[5];`，`T` 是类类型。"

<details markdown="1">
<summary>答案</summary>

声明：声明一个名为 `a`、类型为"5 个 `T` 的数组"的变量。它在语法上可以是声明（声明符 `(a)[5]`），按 [[stmt.ambig#1]] 就是声明。[[stmt.ambig#2]] 的例 1 有同样的例子 `T(e)[5];`。
</details>

## 小结

!!! summary
    - 附录 A 是资料性的语法汇总，规范性的语法在正文各条款。
    - 它接受的是合法 C++ 的超集：大量约束写在正文的 "shall" 里；它也是有二义性的：表达式/声明、类型/表达式的选择由 [[stmt.ambig]]、[[dcl.ambig.res]]、[[dcl.spec]] 等规则决定。
    - [gram.key] 的"上下文相关关键字"指由声明引入的 *typedef-name*、*class-name*、*namespace-name*、*enum-name*、*simple-template-name* 等：同一个 *identifier* 属于哪个语法类别取决于名字查找，C++ 语法因此不是上下文无关的。
    - 难解析的地方大多由语法之外的规则决定：`<` 是否开始模板实参（[[temp.names#7]]）、`>>` 拆分（[[temp.names#8]]）、`<::`/`[::`（[[lex.pptoken#5]]）、`[[` 只能引入属性（[[dcl.attr.grammar#9]]）、"能当声明就当声明"（[[stmt.ambig#1]]）。
