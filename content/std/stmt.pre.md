---
title: 语句总则、标号、表达式语句与复合语句
summary: 语句的种类；子语句与包围关系，它们决定 break、case、goto 能写在哪里；条件里的声明及其取值，包括 C++26 的结构化绑定条件；标号、表达式语句和复合语句。
status: done
covers: stmt.label, stmt.expr, stmt.block
papers: P0963R3, P2324R2, P0305R1, P2360R0
related: stmt, stmt.select, stmt.iter, stmt.dcl, basic.scope.block, dcl.struct.bind, expr.context
tags: 语句, 条件, 标号
updated: 2026-10-19
---

!!! tldr
    - `break`、`case`、`goto` 能写在哪里，由包围关系决定。包围关系建立在子语句之上，而 lambda 体不是子语句，所以这些语句都不能穿过 lambda。
    - 条件可以是表达式，也可以是一个声明。声明形式只接受 `=` 或花括号初始化，说明符只能是类型说明符和 `constexpr`；能读成声明时就按声明处理。
    - 声明形式的条件，测试的是判定变量按语境转换为 `bool` 的结果。C++26 的结构化绑定条件测试的是整个被绑定的对象，而不是某个绑定。
    - 标号的作用范围是整个函数。C++23 起标号可以放在块的末尾。`if constexpr`、`if consteval` 的分支和展开语句的体是控制流受限语句，不能从外面跳进去。
    - 表达式语句里的表达式是弃值表达式，它的副作用在下一条语句开始前全部完成。

## 语句有哪些（¶1）

¶1 除非另有规定，语句按顺序执行。一条语句之内各个求值的先后，由 [[intro.execution]] 的先序（sequenced before）规则决定：每个完整表达式都先序于下一个要求值的完整表达式。

| 语法类别 | 例子 | 详见 |
|---|---|---|
| *labeled-statement* | `L: x = 1;`、`case 3: …` | [[stmt.label]] |
| *expression-statement* | `f(x);`、`;` | [[stmt.expr]] |
| *compound-statement* | `{ … }` | [[stmt.block]] |
| *selection-statement* | `if`、`if constexpr`、`if consteval`、`switch` | [[stmt.select]] |
| *iteration-statement* | `while`、`do`、`for`、范围 `for` | [[stmt.iter]] |
| *expansion-statement* {{c++26}} | `template for (auto x : t) { }` | [[stmt.expand]] |
| *jump-statement* | `break`、`continue`、`return`、`co_return`、`goto` | [[stmt.jump]] |
| *assertion-statement* {{c++26}} | `contract_assert(p);` | [[stmt.contract.assert]] |
| *declaration-statement* | `int x = 0;` | [[stmt.dcl]] |
| *try-block* | `try { } catch (...) { }` | [[except.pre]] |

除了带标号语句和声明语句，每种语句前面都可以写一个属性序列，它作用于这条语句。标号自己的属性写在标号里，声明语句的属性属于声明本身（[[dcl.pre]]）。常见的语句属性是 `[[likely]]`、`[[unlikely]]`（[[dcl.attr.likelihood]]），以及写在空语句上的 `[[fallthrough]]`（[[dcl.attr.fallthrough]]）。

```cpp run ok
int classify(int n) {
  if (n > 0) [[likely]] {     // 属性作用于这个复合语句
    return 1;
  }
  switch (n) {
  case 0:
    [[fallthrough]];          // 属性作用于一个空语句
  case -1:
    return 0;
  default:
    return -1;
  }
}
int main() { return classify(1) == 1 ? 0 : 1; }
```

¶1 还定义了几个在多种语句里复用的语法成分：

- *init-statement*：表达式语句、简单声明，或 C++23 起的别名声明（[[P2360R0]]）。它写在 `if`、`switch`、`for`、范围 `for` 和 `template for` 的开头，总是以分号结尾，所以 `if (auto x = f(); x)` 中间有一个分号。
- *condition*：表达式，或者一个条件声明。见下文。
- *for-range-declaration* 和 *for-range-initializer*：范围 `for` 和展开语句中冒号左边的声明和右边的初始化器。

## 子语句与包围（¶2–¶3）

```cpp run error
void h(int n) {
  for (int i = 0; i < n; ++i) {
    [&] {
      if (i == 3) break;   // error: break 不在循环里
    }();
  }
}
```

`break` 写在循环的花括号里面，却不算在循环里。原因在于标准判断"在里面"用的是子语句和包围关系，而 lambda 体不是子语句。

### 子语句（¶2）

¶2 一条语句的**子语句**（[[g:substatement|substatement]]）是：

| 外层语句 | 它的子语句 |
|---|---|
| 带标号语句（¶2.1） | 标号后面的那条语句 |
| 复合语句（¶2.2） | 其中的每一条语句 |
| 选择语句（¶2.3） | 各个分支，不包括 *init-statement* |
| 迭代语句（¶2.4） | 循环体，不包括 *init-statement* |
| 展开语句（¶2.5） | 它的复合语句，不包括 *init-statement* |

注 1 指出，lambda 表达式的函数体不是它所在语句的子语句。lambda 体是另一个函数的函数体，控制流不能从那里跳到外层函数的循环或 `switch` 中。条件不是语句，自然也不是子语句。

### 包围（¶3）

¶3 语句 S1 **包围**（encloses）语句 S2，当且仅当：

- ¶3.1 S2 是 S1 的子语句；
- ¶3.2 S1 是选择、迭代或展开语句，S2 是它的 *init-statement*；
- ¶3.3 S1 是 *try-block*，S2 是它的复合语句或某个 handler 的复合语句；
- ¶3.4 或者 S1 包围某个 S3，S3 又包围 S2。

反过来说 S2 被 S1 包围。包围可以跨越任意多层，但不跨越函数边界。很多规则都用它表述：

- `break`、`continue` 必须被循环、`switch` 或展开语句包围（[[stmt.break]]、[[stmt.cont]]）；
- `case`、`default` 标号必须被 `switch` 包围（[[stmt.label#2]]）；
- 协程不得包围 `return` 语句（[[stmt.return.coroutine#1]]）；
- fallthrough 语句必须出现在包围它的 `switch` 之内（[[dcl.attr.fallthrough#1]]）。

handler 也在包围关系之内（¶3.3），所以 `catch` 块里的 `break` 可以跳出外层循环：

```cpp run ok
#include <stdexcept>
int count_until_throw(int n) {
  int i = 0;
  for (; i < n; ++i) {
    try {
      if (i == 3) throw std::runtime_error("stop");
    } catch (...) {
      break;    // OK：handler 被 try-block 包围，try-block 被 for 包围
    }
  }
  return i;
}
int main() { return count_until_throw(10) == 3 ? 0 : 1; }
```

## 条件（¶4–¶8）

`if`、`switch`、`while`、`for` 括号里的条件，规则都在这里（¶4）。`do` 的括号里只能写表达式（[[stmt.do]]）。

### 表达式还是声明（¶4、¶7）

条件可以是一个表达式，也可以声明一个变量：

```cpp run ok
int* get() { static int v; return &v; }
int main() {
  if (int* p = get()) { *p = 1; }    // = 初始化
  if (int n{3}) { (void)n; }         // 花括号初始化
  if (const int k = 4) { (void)k; }  // const 是类型说明符
}
```

条件声明只接受 `= 表达式` 或花括号初始化器，不接受圆括号初始化器。圆括号形式在这个位置会和函数声明、函数式转换产生更多歧义。

<div class="compare" markdown="1">

```cpp run ok
void g() {
  if (int n{3}) { (void)n; }
}
```

```cpp run error
void g() {
  if (int n(3)) { }  // error
}
```

</div>

¶4 还规定，条件声明的声明符不得声明函数或数组，说明符序列不得定义类或枚举。数组会退化成非空指针，作条件时永远为真；函数声明没有初始化器。在条件里定义类型则会把新的类作用域引入表达式的位置，徒增解析和作用域规则的复杂度。如果出现 `auto`，按 [[dcl.spec.auto]] 从初始化器推导类型。

```cpp run error
void f() {
  if (int a[2] = {1, 2}) { }   // error: 声明了数组
  if (struct B { explicit operator bool() const { return true; } } b{}) { }
                               // error: 在条件里定义类
}
```

¶7 如果一个条件在语法上既能读成表达式，也能读成条件声明，就按声明处理。这和 [[stmt.ambig]] 处理语句级歧义的方向一致。

```cpp run ok
struct T {
  int v;
  T(int x) : v(x) {}
  explicit operator bool() const { return v != 0; }
};
int x = 0;
int main() {
  // 可以读作把临时对象 T(x) 赋值为 5，也可以读作声明 T x = 5。
  // 按 ¶7 是声明：新的局部变量 x 遮蔽了全局的 x。
  if (T(x) = 5) {
    return x.v == 5 ? 0 : 1;   // 这里的 x 是 T 类型
  }
  return 1;
}
```

Clang 对这种写法给出 `-Wvexing-parse` 警告，说明这对括号被当成了声明符外多余的括号。

### 判定变量与条件的值（¶5–¶6）

¶5 声明形式的条件里被测试的那个变量叫**判定变量**（[[g:decision-variable|decision variable]]）。普通的条件声明中，判定变量就是声明的变量；结构化绑定形式的判定变量由 [[dcl.struct.bind]] 规定，是背后那个无名对象 *e*。

¶6 在 `switch` 以外的语句中，条件的值是判定变量（或表达式）按语境转换为 `bool` 的结果（[[conv]]），转换非良构则程序非良构。`switch` 的条件不转换为 `bool`，而是按 [[stmt.switch#2]] 转换为整型或枚举类型。

按语境转换允许使用 `explicit operator bool`。`if (auto p = make())` 测试 `std::unique_ptr`、`while (std::cin >> x)` 测试流，靠的都是这一点：

```cpp run ok
#include <memory>
std::unique_ptr<int> make(bool b) {
  return b ? std::make_unique<int>(7) : nullptr;
}
int main() {
  if (auto p = make(true)) {   // operator bool 是 explicit，这里按语境转换
    return *p == 7 ? 0 : 1;
  }
  return 1;
}
```

### 结构化绑定作为条件 {{c++26}}

C++26 之前，条件里不能写结构化绑定，只能先在 *init-statement* 里绑定，再写条件：

```cpp
if (auto [ptr, ec] = std::from_chars(b, e, v); ec == std::errc{}) { … }
```

[[P0963R3]] 允许把结构化绑定声明直接当作条件。被测试的是判定变量，也就是整个被绑定的对象 *e*，而不是某一个绑定。所以只有 *e* 本身能按语境转换为 `bool` 时，这种写法才合法。`std::from_chars_result` 在 C++26 中正是为此加了 `operator bool`，它判断 `ec == std::errc{}`。

```cpp run ok
#include <charconv>
int parse(const char* s, int len) {
  int v = 0;
  if (auto [ptr, ec] = std::from_chars(s, s + len, v)) {  // 测试 from_chars_result
    (void)ptr; (void)ec;
    return v;
  }
  return -1;
}
int main() { return parse("42", 2) == 42 ? 0 : 1; }
```

<div class="compare" markdown="1">

```cpp run ok
struct P {
  int a, b;
  explicit operator bool() const {
    return a != 0;
  }
};
int f(P p) {
  if (auto [x, y] = p)  // 测试 P 的副本
    return x + y;
  return 0;
}
```

```cpp run error
#include <tuple>
void g(std::tuple<int, int> t) {
  // tuple 不能转换为 bool
  if (auto [a, b] = t) { }  // error
}
```

</div>

对类元组类型还有一个顺序保证：先初始化 *e* 并完成它到 `bool` 的转换，再初始化各个绑定，也就是调用 `get<i>`（[[dcl.struct.bind#7]]）。类型因此可以在 `operator bool` 里检查是否有值，只在有值时才让 `get` 被调用。

### 允许的说明符（¶8）

¶8 条件和 *for-range-declaration*（包括其中的结构化绑定声明）里，每个声明说明符只能是类型说明符或 `constexpr`。`const`、`volatile`、`auto` 和类型名都是类型说明符，可以用；`static`、`thread_local`、`extern`、`inline`、`constinit`、`typedef` 都不行。

<div class="compare" markdown="1">

```cpp run ok
void f() {
  if (constexpr int n = 2) { (void)n; }
  for (const auto& c : "abc")
    (void)c;
}
```

```cpp run error
void g() {
  if (static int n = 1) { }
  for (static int i : {1, 2})
    (void)i;
}
```

</div>

!!! note "条件里声明的名字的作用域"
    条件里声明的名字从声明点一直有效到整条语句结束，`else` 分支也包括在内。它不能在子语句的最外层块里再次声明（[[basic.scope.block]]）。选择语句、迭代语句和它们的子语句各有自己的块作用域（[[stmt.select.general#2]]、[[stmt.iter.general#2]]）。

```cpp run error
void f(int* q) {
  if (int* p = q) {
    int p = 0;    // error: 与条件中的 p 冲突
  } else {
    int* p = q;   // error: else 分支也一样
  }
}
```

## 标号 [stmt.label]

### 三种标号（¶1）

¶1 标号有三种：标识符标号 `name:`、`case 常量表达式:` 和 `default:`。前面都可以写属性，属性作用于标号，而不是被标号的语句。

标识符标号唯一的用途是作为 `goto` 的目标。一个函数里不能有两个同名标号，范围是整个函数而不是块。`goto` 可以写在标号之前。

<div class="compare" markdown="1">

```cpp run error
void f(int n) {
  { L: ++n; }
  { L: --n; }   // error: 重复的标号
  goto L;
}
```

```cpp run ok
void f() {
  int x = 0;
x:              // 标号不和变量冲突
  if (++x < 3) goto x;
}
```

</div>

标号和其他名字互不干扰，所以标号 `x` 可以和变量 `x` 同名。

### 块末尾的标号 {{c++23}}

¶1 第一句说，标号可以加在一条语句上，也可以用在复合语句中的任何位置。配合 [[stmt.block]] 的语法 `{ statement-seq(opt) label-seq(opt) }`，块的末尾可以有一串标号，视为后面跟着一个空语句。C++23 之前标号必须标在某条语句上，人们只好写 `end: ;`。这项改动（[[P2324R2]]）与 C23 一致。

```cpp run ok
void g(int n) {
  if (n < 0) goto out;
  switch (n) {
  case 1:
    ++n;
  default:        // C++23 起 OK：default 位于块末尾，后面不必写 ;
  }
out:
}                 // C++23 起 OK：标号位于块末尾
```

### case 和 default 必须被 switch 包围（¶2）

¶2 带 `case` 或 `default` 标号的语句必须被某个 `switch` 包围（按上文 ¶3 的定义）。lambda 体不是子语句，所以 `switch` 里的 lambda 不能有 `case`：

```cpp run error
void f(int n) {
  switch (n) {
  case 0:
    [] {
    case 1: ;     // error: 没有被 switch 包围
    }();
  }
}
```

### 控制流受限语句（¶3）

¶3 **控制流受限语句**（[[g:control-flow-limited-statement|control-flow-limited statement]]）S 满足两点：

- ¶3.1 S 中出现的 `case`、`default` 标号，必须属于 S 内部的某个 `switch`；
- ¶3.2 S 中声明的标号，只能被 S 中的语句引用。

也就是说，控制流不能从外面进入 S，既不能 `goto` 进去，也不能由外层的 `switch` 分派进去。以下语句是控制流受限的：

- `if constexpr` 的每个子语句（[[stmt.if#2]]）：被弃置的分支可能根本不会实例化，跳进去没有意义；
- `if consteval` 的每个子语句（[[stmt.if#5]]）：一个分支用于编译期，一个用于运行期，跳进去会绕过分支选择；
- 展开语句的复合语句（[[stmt.expand#2]]）：它会被复制多份，跳转目标无法确定是哪一份。

<div class="compare" markdown="1">

```cpp run error
void g() {
  goto inside;   // error
  if constexpr (true) {
  inside: ;
  }
}
```

```cpp run ok
void h(int n) {
  if constexpr (sizeof(int) == 4) {
    if (n) goto out;   // OK：往外跳
  }
out:;
}
```

</div>

`switch` 的情形同理：`case` 写在 `switch` 里的 `if constexpr` 分支中，也是非良构的。

### 展开语句里不能有标识符标号（¶4）{{c++26}}

¶4 标识符标号不得被展开语句包围，即使 `goto` 和标号都在展开语句的体内也不行。体会按元素实例化多次，同一个标号会出现多次，违反同一函数中标号不得重复的规则。`case`、`default` 标号不受这条限制，只要它们所属的 `switch` 也在体内。

```cpp run error
void f() {
  template for (auto x : {1, 2}) {
    (void)x;
  again:          // error: 标识符标号被展开语句包围
    ;
  }
}
```

## 表达式语句 [stmt.expr]

¶1 表达式语句的形式是 `expression(opt) ;`。

- 其中的表达式是**弃值表达式**（[[g:discarded-value-expression|discarded-value expression]]，[[expr.context]]）：结果被丢弃。只有对 volatile glvalue 的几种简单形式，才会施行左值到右值转换。所以 `reg;` 对 volatile 变量做一次读取，而对普通变量的 `plain;` 什么也不做。
- 表达式语句的所有副作用都在下一条语句执行之前完成。
- 省略了表达式的 `;` 叫做**空语句**（null statement），常用作循环的空体，也是 `[[fallthrough]];` 的载体。

```cpp run ok
volatile int reg = 0;
int plain = 0;
int main() {
  reg;          // 执行一次 volatile 读
  plain;        // 什么也不做（Clang 警告结果未使用）
  (void)plain;  // 显式弃值，不再警告
  ;             // 空语句
}
```

`[[nodiscard]]` 的警告（[[dcl.attr.nodiscard]]）针对的就是函数调用作为弃值表达式的情形，表达式语句 `f();` 是最常见的一种。转换为 `void` 是表示有意丢弃结果的标准写法。

## 复合语句 [stmt.block]

¶1 **复合语句**（compound statement，又称块）把一串语句组合成一条语句：`{ statement-seq(opt) label-seq(opt) }`。末尾的标号见上文。

¶2 的注指出，复合语句定义一个块作用域（[[basic.scope.block]]）。离开块时，块内已经构造的自动变量按构造的逆序销毁（[[stmt.dcl]]）。

```cpp run ok
#include <cstdio>
struct Tr { const char* n; ~Tr() { std::printf("~%s\n", n); } };
int main() {
  Tr a{"a"};
  {
    Tr b{"b"};
    Tr c{"c"};
  }             // 打印 ~c ~b
  Tr d{"d"};
}               // 打印 ~d ~a
```

## 常见误解

!!! pitfall "`if (x = 0)` 是比较"
    它是赋值，条件的值是 0，即假。这是 C 系语言里常见的错误来源，编译器通常会警告条件中的赋值，加一层括号 `if ((x = 0))` 表示有意为之。`if (int x = 0)` 则是声明，不会和比较混淆。

!!! pitfall "lambda 里的 return 能从外层函数返回"
    不能。`break`、`continue`、`case`、`goto`、`return` 都不穿过 lambda 体，lambda 里的 `return` 只是从 lambda 返回。要让外层函数返回，需要通过返回值传递信号。

!!! pitfall "`if (auto [ok, value] = f())` 测试的是 `ok`"
    测试的是整个被绑定的对象。想测试某个成员，仍然要用 *init-statement*：`if (auto [ok, v] = f(); ok)`。

## 思考题

!!! question "思考题 1"
    下面的条件里声明了几个变量？

    ```cpp
    struct T { T(int); explicit operator bool() const; };
    int a = 1;
    void f() { while (T(a) = 2) { } }
    ```

<details markdown="1">
<summary>答案</summary>

一个，即 `T a = 2`。按 ¶7，条件既能读成表达式又能读成声明时按声明处理，`T(a)` 中的括号是声明符外多余的括号。每轮循环都构造一个新的局部 `a`，测试它，再在这一轮结束时销毁它（[[stmt.while#2]]）。全局的 `a` 根本没有用到。Clang 对这一行给出 `-Wvexing-parse` 警告。
</details>

!!! question "思考题 2"
    `switch` 里的 lambda 体中能写 fallthrough 语句吗？

    ```cpp
    void f(int n) {
      switch (n) {
      case 0: [] { [[fallthrough]]; }();
      case 1: ;
      }
    }
    ```

<details markdown="1">
<summary>答案</summary>

不能。[[dcl.attr.fallthrough#1]] 要求 fallthrough 语句出现在一个包围它的 `switch` 之内。包围关系建立在子语句之上，lambda 体不是子语句（¶2 注 1），所以这个 `switch` 不包围 lambda 体里的 fallthrough 语句，程序非良构。Clang 报 "fallthrough annotation is outside switch statement"。
</details>

!!! question "思考题 3"
    为什么 `if (auto [a, b] = std::pair{1, 2})` 非良构，而 `if (auto [p, ec] = std::from_chars(…))` 合法？

<details markdown="1">
<summary>答案</summary>

结构化绑定条件的值，是判定变量 *e*（整个对象）按语境转换为 `bool` 的结果（¶5、¶6）。`std::pair<int, int>` 没有到 `bool` 的转换，转换非良构，所以程序非良构。`std::from_chars_result` 在 C++26 中有 `operator bool`，所以合法。绑定 `a`、`b` 或 `p`、`ec` 本身从不参与测试。
</details>
