---
title: 属性
summary: 属性 [[...]] 的写法、它属于哪个实体或语句、不认识的属性为什么被忽略、标准属性为什么删掉也不影响正确性，以及 deprecated、fallthrough、maybe_unused、likely、noreturn、indeterminate 和 C++26 注解。
status: done
covers: dcl.attr.grammar, dcl.attr.deprecated, dcl.attr.fallthrough, dcl.attr.indet, dcl.attr.likelihood, dcl.attr.unused, dcl.attr.noreturn, dcl.attr.annotation
papers: N2761, P0028R4, P0283R2, P2552R3, P2156R1, P0188R1, P0212R1, P0479R5, P2795R5, P3394R4, P2361R6, P2173R1
related: dcl.align, dcl.attr.assume, dcl.attr.nodiscard, dcl.attr.nouniqueaddr, cpp.cond, basic.indet, stmt.switch, stmt.expand, intro.abstract, expr.const.reflect
tags: 属性, 注解, 诊断, 优化提示
updated: 2026-10-19
---

!!! tldr
    - 属性写在哪里就属于谁：声明开头的属于被声明的实体，名字后面的属于那个名字，语句前面的属于那条语句。
    - 编译器不认识的属性会被忽略，所以一份代码可以同时写上几家编译器的厂商属性；拼错的标准属性也会被静默忽略。
    - 标准属性只提供可以忽略的信息：把它们删掉，程序不会出现新的行为。`[[noreturn]]` 函数返回、`[[assume]]` 条件为假则是未定义行为。
    - 两个相邻的 `[` 只能用来开启属性，`a[[] { return 0; }()]` 即使中间加了空格也是错的。
    - C++26 的注解 `[[=expr]]` 不是给编译器的提示，而是挂在声明上、供静态反射读取的常量。

## 属性是什么

```cpp
__attribute__((noreturn)) void die1();   // GCC、Clang 的写法
__declspec(noreturn) void die2();        // MSVC 的写法
[[noreturn]] void die3();                // 标准写法，C++11 起
```

**属性**（attribute）给声明、语句或类型附加一条额外的信息，比如这个函数不会返回、这个返回值不该被丢掉、这个分支很少执行。C++11 之前，每家编译器都有自己的写法。C++11 引入了统一的 `[[...]]` 语法，把最常用的几种信息定为标准属性，同时给厂商属性留出了 `[[gnu::...]]`、`[[clang::...]]`、`[[msvc::...]]` 这样带命名空间的位置。

¶1 标准把属性和 C++26 的**注解**（annotation，见下文）放在同一套语法里，统称为给类型、变量、名字、契约断言、块乃至翻译单元附加的信息。`alignas(...)`（[[dcl.align]]）在语法上也是一种 *attribute-specifier*，所以它能出现的位置与属性相同。

一个 `[[...]]` 叫做 *attribute-specifier*，里面是逗号分隔的属性列表。每个属性由一个**属性记号**（attribute-token）和可选的括号参数组成，记号可以带命名空间：

```text
[[ noreturn ]]                       属性记号 noreturn，无参数
[[ deprecated("用 g2") ]]            带参数
[[ gnu::always_inline, gnu::hot ]]   带命名空间的厂商属性，两个
[[ using gnu: always_inline, hot ]]  同上，省去重复的命名空间
[[ =42 ]]                            C++26 注解
```

## 写在哪里，就属于谁（¶7）

```cpp run ok
[[nodiscard]] int f1();        // 声明开头：属于被声明的实体 f1
int f2 [[nodiscard]] ();       // 紧跟名字：属于 f2
struct [[deprecated]] S {};    // class-key 之后：属于类 S
enum E { a [[deprecated]] };   // 枚举量之后：属于枚举量 a
void g(int n) {
  if (n) [[unlikely]] { }      // 语句之前：属于这条语句
}
int main() {}
```

¶7 每个属性序列都**属于**（appertain to）某个实体或语句，属于谁完全由它出现的语法位置决定，具体规定分散在 [[stmt.pre]]、[[dcl.pre]]、[[dcl.meaning]] 等处。如果序列中某个属性不允许用于它所属的东西，程序非良构：`[[noreturn]] int a;` 必须报错，因为 `noreturn` 只能用于函数。

位置规则最容易在 `if` 上写错。`if (c) [[likely]] stmt;` 里的属性属于 then 分支的语句；写成 `if ([[likely]] c)` 是语法错误，条件表达式前面不能放属性。

¶7 还有两条限制。属于友元声明的属性序列，要求那个友元声明是定义；属性也不能属于显式实例化（注 4，[[temp.explicit]]）。

<div class="compare" markdown="1">

```cpp error
struct S1 {
  [[deprecated]]
  friend void fr1();  // error: 不是定义
};
```

```cpp ok
struct S2 {
  [[nodiscard]]
  friend int fr2(S2) { return 1; }  // OK
};
```

</div>

非定义的友元声明可能是那个函数的第一次声明，却藏在某个类里。如果允许它带属性，不同的类就能给同一个函数加上互相矛盾的属性。

## 语法细节（¶2–¶6）

¶2 `using` 前缀（C++17，[[P0028R4]]）把后面每个属性记号都当作加了 `N::`。厂商属性常常成组出现，这样可以省去重复的命名空间。用了前缀之后，列表里就不能再写带命名空间的记号：

```cpp run error
[[using CC: opt(1), debug]]   // 等同于 [[CC::opt(1), CC::debug]]
  void f() {}
[[using CC: CC::opt(1)]]      // error: using 前缀后不能再写 CC::
  void h() {}
```

`CC` 是虚构的命名空间，Clang 会对 `f` 上的两个属性给出未知属性被忽略的警告。

¶4 列出了几条零碎的规则：

- `[[]]`、`[[,]]` 这样不含任何属性的写法没有效果；列表中属性的顺序无关紧要。
- 属性记号里出现的关键字被当作普通标识符，所以厂商可以定义 `[[gnu::const]]` 这样的属性。
- 属性记号不做名字查找。`[[noreturn]]` 里的 `noreturn` 不是一个声明过的名字，和作用域里有没有叫 `noreturn` 的东西无关。
- 属性后面的 `...` 是包展开，但只有该属性的规范允许时才能写；标准属性都不允许。¶6 规定注解后面的 `...` 也是包展开。
- 括号里的参数是任意一串括号配对的记号，具体形式由每个属性自己规定（¶3）。这让厂商属性可以有任意复杂的参数。

¶5 是一条注：除非另有规定，标准规定的属性记号不能用作宏名（[[cpp.replace.general]]）。`#define noreturn` 会破坏所有 `[[noreturn]]`。

## 不认识的属性被忽略（¶8）

```cpp run ok
[[gnu::always_inline, msvc::forceinline]]
inline int add(int a, int b) { return a + b; }

[[unknown_attr]] int x;   // 被忽略，Clang 给出警告

int main() { return add(0, 0) + x; }
```

¶8 标准没有规定的属性记号，行为由实现定义；实现不认识的记号会被忽略。所以上面的代码在 GCC、Clang、MSVC 上都能编译，每家只理会自己的属性。C++11 原本允许实现拒绝不认识的属性，C++17 的 [[P0283R2]] 改成了必须忽略。

忽略的代价是拼写错误也被吞掉了：`[[nodicard]]` 少了一个 s，编译器不会报错，只会给一条 `-Wunknown-attributes`（Clang）或 `-Wattributes`（GCC）警告。

标准属性则不同。注 5 指出，标准属性用在了不允许的对象上，或者参数不符合它的语法，程序就是非良构的。所以 `[[noreturn]] int a;` 必须诊断，`[[vendor::noreturn]] int a;` 怎么处理由厂商决定。

### 保留的名字（¶8.1–¶8.2）

下面两类属性记号保留给将来的标准使用，自己的属性不要这样起名：

- ¶8.1 不带命名空间、标准里又没有规定的记号，如 `[[my_attr]]`。自己的属性应写成 `[[mycompany::my_attr]]`。
- ¶8.2 命名空间是 `std` 后跟零个或多个数字的记号，如 `[[std::x]]`、`[[std23::x]]`。

标准还建议每个实现为自己的属性命名空间选一个有辨识度的名字，如 `gnu`、`clang`、`msvc`。

## 删掉标准属性不会产生新行为（¶8 注 6）

!!! std
    The *attribute*s specified in [dcl.attr] have optional semantics: given a well-formed program, removing all instances of any one of those *attribute*s results in a program whose set of possible executions ([intro.abstract]) for a given input is a subset of those of the original program for the same input…

从一个良构程序里删掉某一种标准属性的全部实例，得到的程序在同一输入下的可能执行，是原程序可能执行的子集（不考虑实现对这个属性另外作出的保证）。换句话说，删掉标准属性只会让行为更确定，不会出现原来不可能发生的事。逐个看：

| 删掉的属性 | 原程序 | 删掉以后 |
|---|---|---|
| `nodiscard`、`deprecated`、`maybe_unused`、`fallthrough`、`likely` | 只影响警告和优化 | 可能执行不变 |
| `assume(e)` | `e` 为假时是 UB，任何执行都可能 | 正常执行，是子集 |
| `noreturn` | 函数返回是 UB | 正常返回，是子集 |
| `indeterminate` | 读取未初始化变量是 UB | 变成错误行为，是子集 |
| `no_unique_address` | 布局可能变化 | 布局本来就由实现决定，新布局在允许范围内 |

这条规则的实际意义是：标准属性不能用来改变程序的含义，真正影响语义的特性要有自己的语法。它只约束标准属性。厂商属性可以任意改变语义，例如 `[[gnu::packed]]` 改变布局，`[[clang::trivial_abi]]` 改变调用约定。

## `[[` 只能开启属性（¶9）

```cpp run error
void f() {
  int y[5];
  y[[] { return 2; }()] = 2;     // error: [[ 只能开启属性
  y[ [] { return 2; }()] = 2;    // error: 空格不能把两个 [ 分开
  y[([] { return 2; })()] = 2;   // OK：用圆括号隔开
  int i [[vendor::attr([[]])]];  // OK：属性参数里可以出现 [[
  (void)i;
}
```

¶9 两个连续的 `[` 记号只能出现在两个地方：开启一个 *attribute-specifier*，或者在属性参数内部。注 7 补充，即使这个位置根本不允许出现属性，或者这两个括号按另一种语法本可以配对，程序也是非良构的。

规则说的是记号，所以中间的空白不起作用。属性能出现的位置太多，如果要靠上下文判断 `[[` 是属性还是下标里的 lambda，解析器可能需要向前看任意远。标准干脆在这一层一刀切。下标里要放 lambda 时，用圆括号把它包起来。

## 标准属性一览

`__has_cpp_attribute(name)` 可以在预处理阶段检测属性是否受支持（[[cpp.cond#5]]）。对标准属性，结果是 0 或下表中的值。各属性的推荐做法都要求：如果实现并不真正利用这个属性（不给警告，也不做优化），就应该返回 0。

| 属性 | 用于 | 作用 | 引入 | `__has_cpp_attribute` |
|---|---|---|---|---|
| `alignas` | 变量、数据成员、类 | 对齐要求，见 [[dcl.align]] | C++11 | 不是属性记号 |
| `assume(expr)` | 空语句 | 优化假设，见 [[dcl.attr.assume]] | C++23 | 202207 |
| `deprecated("msg")` | 类、别名、变量、函数、命名空间、枚举、枚举量、概念等 | 使用时警告 | C++14 | 201309 |
| `fallthrough` | 空语句 | 标明有意的 case 贯穿 | C++17 | 201603 |
| `indeterminate` | 自动变量、函数形参 | 退出错误值机制 | C++26 | 202403 |
| `likely` / `unlikely` | 语句、标签 | 分支概率提示 | C++20 | 201803 |
| `maybe_unused` | 实体、结构化绑定、标签 | 不报未使用警告 | C++17 | 201603 |
| `nodiscard("msg")` | 函数、类、枚举、构造函数 | 丢弃结果时警告，见 [[dcl.attr.nodiscard]] | C++17 | 201907 |
| `noreturn` | 函数 | 函数不返回 | C++11 | 200809 |
| `no_unique_address` | 非静态数据成员 | 允许与其他成员重叠，见 [[dcl.attr.nouniqueaddr]] | C++20 | 201803 |

在本机 Clang 23 上，除 `indeterminate` 返回 0（尚未实现）外，其余都返回表中的值。

## deprecated：标记不再推荐使用的东西

```cpp run ok
[[deprecated("use g2() instead")]] void g1();
void g2();
enum Mode { fast, safe, legacy [[deprecated]] };
namespace [[deprecated]] old_api { inline int v = 1; }

void use() {
  g2();                // OK
  g1();                // 警告：use g2() instead
  Mode m = legacy;     // 警告
  int x = old_api::v;  // 警告
  (void)m; (void)x;
}
```

[dcl.attr.deprecated] ¶1 `deprecated` 标记仍然可以使用、但出于某种原因不鼓励使用的名字或实体，比如已经过时或不安全的接口。括号里的字符串用来说明理由或推荐替代品。

¶2 它可以用于类、类型别名、变量、非静态数据成员、函数、命名空间、枚举、枚举量、概念和模板特化。

¶3 一个实体可以先不带这个属性声明，后来在重声明里加上；反过来也行，但一旦被标记为弃用，后面的重声明不能取消它。各次声明给出的理由字符串可以不同。

¶4 标准建议：程序在声明之外引用这个名字或实体时，如果位置在带属性的声明之后，实现应给出诊断，并带上理由字符串。声明和重声明本身不触发警告。

## fallthrough：有意的贯穿

```cpp run error
void g(), h(), i();
void f(int n) {
  switch (n) {
  case 1:
  case 2:
    g();
    [[fallthrough]];          // OK：下一条语句带 case 3
  case 3:
    do {
      [[fallthrough]];        // error: 下一条语句在循环之外
    } while (false);
  case 5:
    h();                      // 未标注的贯穿：可以警告
  case 4:
    i();
    [[fallthrough]];          // error: 后面没有 case 标签
  }
}
```

`switch` 的一个分支执行完后如果没有 `break`，会接着执行下一个分支，这叫贯穿。贯穿常常是忘了写 `break`，所以编译器会对它警告（Clang 的 `-Wimplicit-fallthrough`）。`[[fallthrough]];` 用来声明这次贯穿是有意的。

[dcl.attr.fallthrough] ¶1 `fallthrough` 只能用于空语句，这样的语句叫做[[g:fallthrough-statement|贯穿语句]]（fallthrough statement）。它必须满足：

- 位于某个 `switch` 语句（[[stmt.switch]]）之内；
- 它之后下一条将要执行的语句，必须带有同一个 `switch` 的 `case` 或 `default` 标签，否则程序非良构；
- 如果它在一个循环里，那条语句还必须属于循环体的同一次执行，不能借循环跳到下一个标签；
- {{c++26}} 如果它在一个展开语句（`template for`，[[stmt.expand]]）里，它所属的 `switch` 也必须在这个展开语句里面，不能从展开出的一份代码贯穿到另一份。

最后一个分支末尾的 `[[fallthrough]];` 是常见错误，有人为了格式统一也写上，但它后面没有标签，程序非良构。Clang 的诊断是 `fallthrough annotation does not directly precede switch label`。

¶2 标准建议：贯穿语句应当压制这处贯穿的警告；如果贯穿语句在运行时根本不可能执行到，实现应当警告。相邻的两个标签之间没有语句（上例的 `case 1:` 和 `case 2:`），本来就不会有警告，不需要标注。

## maybe_unused：有意不用

```cpp run ok
#include <cassert>
[[maybe_unused]] static void f([[maybe_unused]] bool thing1,
                               [[maybe_unused]] bool thing2) {
  [[maybe_unused]] bool b = thing1 && thing2;
  assert(b);               // 定义了 NDEBUG 时 b 没有被使用
}
int main() {}
```

[dcl.attr.unused] ¶1 `maybe_unused` 表示一个名字、标签或实体可能是有意不使用的，常见于只在某些编译配置下才用到的变量和函数。

¶2 它可以用于类、类型别名、变量、结构化绑定声明或其中单个绑定、契约的结果绑定（[[dcl.contract.res]]）、非静态数据成员、函数、枚举、枚举量，以及标识符标签（[[stmt.label]]）。¶3 可以在后来的重声明中加上，从第一个带它的声明起生效。

¶4 标准建议：对带这个属性的实体和标签，实现不要报告用了或没用。对没有带属性的结构化绑定声明 `auto [a, b] = ...;`，只有全部绑定都没用到时才应警告。未使用警告本身不是标准里的概念，所以这个属性的效果完全落在推荐做法上。

## likely 与 unlikely：分支概率提示 {{c++20}}

```cpp run ok
void g(int);
int f(int n) {
  if (n > 5) [[unlikely]] {   // 认为 n > 5 极少发生
    g(0);
    return n * 2 + 1;
  }
  switch (n) {
  case 1:
    g(1);
    [[fallthrough]];
  [[likely]] case 2:          // 认为 n == 2 远比其他值常见
    g(2);
    break;
  }
  return 3;
}
int main() {}
```

[dcl.attr.likelihood] ¶1 `likely` 和 `unlikely` 用于语句或标签，不带参数，也不能出现在同一个属性序列里。

¶2 这一段是注，说明设计意图：实现可以按照包含 `likely` 的执行路径比其他路径可能得多来优化，`unlikely` 反之。编译器通常把它们转成分支权重，效果类似 `__builtin_expect`，区别在于它们标在语句上，而不是表达式上。注 2 提醒，用得太多反而会让性能变差。

一条执行路径包含某个标签，当且仅当它跳转到这个标签。上例中从 `case 1` 贯穿进 `case 2` 的路径没有跳转到 `case 2`，所以 `[[likely]]` 只描述 `switch` 直接跳到 `case 2` 的情形。

## noreturn：函数不返回

```cpp run ub
[[noreturn]] void f() {
  throw "error";             // OK：抛异常不算返回
}
[[noreturn]] void q(int i) {
  if (i > 0)
    throw "positive";
}                            // i <= 0 时会返回
int main() {
  try { f(); } catch (...) {}
  try { q(0); } catch (...) {}   // UB：q 返回了
}
```

[dcl.attr.noreturn] ¶1 `noreturn` 表示函数不会返回，可以用于函数和 lambda 的调用运算符（后者是 C++23，[[P2173R1]]）。`std::abort`、`std::exit`、`std::terminate`、`std::unreachable` 都带这个属性。

编译器知道一个调用不会返回，就可以不为调用之后生成代码，也可以据此判断后面的代码不可达、不再警告缺少 `return`。所以 ¶1 要求：只要有一个声明带了 `noreturn`，函数的第一次声明就必须带，否则先看到的调用点已经按会返回编译了。一个翻译单元带、另一个不带，程序非良构，不要求诊断（IFNDR，编译器不必报错，程序也没有任何保证）。

¶2 带 `noreturn` 的函数如果某次调用真的返回了，行为是[[g:runtime-undefined-behavior|运行期未定义]]的：在普通执行中是 UB；在常量求值中，由实现决定是否让这个表达式因此不算常量。注 1 说明，抛出异常不算返回，所以 `noreturn` 和 `noexcept` 毫无关系。

¶3 标准建议：函数可能返回时，实现应给出警告。对上面的 `q`，Clang 的警告是 `function declared 'noreturn' should not return`。

## indeterminate：退出错误值机制 {{c++26}}

```cpp
void f(int);
void g() {
  int x [[indeterminate]], y;
  f(y);   // 错误行为
  f(x);   // 未定义行为
}
```

C++26 把读取未初始化的自动变量从 UB 改成了[[g:erroneous-behavior|错误行为]]（[[basic.indet]]，[[P2795R5]]）：变量得到一个由实现选择的错误值，读它是错误，但结果有定义，编译器不能假设它不发生。代价是编译器可能要真的给每个这样的变量写入一个值。`[[indeterminate]]` 用来对单个变量关掉这一机制。

[dcl.attr.indet] ¶1 它可以用于自动存储期的块变量的定义，或函数声明中的形参，不带参数。它让这个对象的存储一开始是不确定的（indeterminate），而不是错误的（erroneous）。于是上例中读 `y` 是错误行为，读 `x` 是未定义行为（¶3 注 1）。

形参也能用，是因为按值传递的类对象形参是一个新的自动对象。如果它的构造函数没有初始化某个成员，这个成员在 C++26 中会得到错误值。¶2 要求形参上的这个属性必须写在函数的第一次声明上；两个翻译单元的第一次声明一个带、一个不带，程序 IFNDR。

只有在测量证明写入错误值的开销不可接受时才值得用它。典型场景是栈上马上会被填满的大缓冲区，比如 `char buf [[indeterminate]] [65536];` 之后紧跟一次 `read()`。

!!! impl "实现状态"
    本机 Clang 23 还没有实现这个属性，`__has_cpp_attribute(indeterminate)` 为 0，`[[indeterminate]]` 被当作未知属性忽略。按上面的可忽略性规则，这是允许的。GCC 和 Clang 早就有 `-ftrivial-auto-var-init=zero|pattern` 选项，给所有自动变量写入初值；Clang 另有 `[[clang::uninitialized]]` 用于逐个变量退出。

## 注解：给反射读取的数据 {{c++26}}

```cpp
struct [[=1]] S {};   // 注解：值为 1 的常量
[[=2, =3, =2]] void g();
void g [[=4, =2]] ();  // g 一共有 5 个注解
```

注解是 C++26 静态反射的配套特性（[[P3394R4]]）。它在声明上挂一个编译期常量，程序再用 `std::meta::annotations_of`（[[meta.reflection.annotation]]）读出来。属性是给编译器看的，注解则是给程序自己看的。例如序列化库可以读取成员上的 `[[=rename("id")]]` 来决定输出的字段名。

[dcl.attr.annotation] ¶1 注解可以用于基类说明符，或以下实体的声明：类型、类型别名、变量、函数、非 `void` 类型的函数形参、命名空间、枚举量、非静态数据成员。例外有两种：写在块作用域里、声明的却是外层命名空间实体的声明（如函数体内的 `extern int x;`，¶1.1 所说的宿主作用域与目标作用域不同），以及非定义的友元声明；对函数形参，按它所在的函数声明来判断。函数定义的形参上的注解，同时属于函数形参和函数体里的那个变量（注 1）。

¶2 注解的值是 `std::meta::reflect_constant(expr)` 的结果，叫做注解的**底层常量**（underlying constant），所以 `expr` 必须是常量表达式，类型必须能作为常量模板实参（[[g:structural-type|结构类型]]）。

¶3 每个注解都是独立的一个，相同的值不会合并。上例中 `g` 的两个声明上一共写了 5 个注解，它就有 5 个。同一个模板的不同实例化，各有各的注解。

¶4 对注解的替换不在立即语境中，所以注解里的替换失败是硬错误，不会像 SFINAE 那样只把候选函数丢掉：

```cpp
template<class T>
  [[=T::type()]] void f(T t);
void f(int);

void g() {
  f(0);     // OK：非模板 f(int) 胜出
  f('0');   // error: 选中模板，替换进注解得到无效表达式
}
```

注解只是附在声明上的数据，不属于函数签名，不应该左右重载决议。

!!! impl "实现状态"
    本机 Clang 23（Homebrew，libc++）尚未实现静态反射：`[[=1]]` 无法解析，也没有 `<meta>` 头。本节例子按标准原文分析，没有经过编译验证。

## 历史与演进

!!! history
    - C++11：属性语法（[[N2761]]），`noreturn`、`carries_dependency`、`alignas`。不认识的属性如何处理由实现决定。
    - C++14：`deprecated`。
    - C++17：`fallthrough`（[[P0188R1]]）、`nodiscard`、`maybe_unused`（[[P0212R1]]）；`using` 前缀（[[P0028R4]]）；不认识的属性必须忽略（[[P0283R2]]）；命名空间和枚举量可以带属性。
    - C++20：`likely`/`unlikely`（[[P0479R5]]）、`no_unique_address`；`nodiscard` 可以带理由、可以用于构造函数。
    - C++23：`assume`；lambda 的调用运算符可以带属性（[[P2173R1]]）；同一个属性列表里允许重复同一个属性（[[P2156R1]]），如 `[[nodiscard, nodiscard]]`。
    - C++26：`indeterminate`（[[P2795R5]]）；注解（[[P3394R4]]）；`carries_dependency` 被删除；属性参数里的字符串改为不求值字符串（[[P2361R6]]）；重新表述了标准属性的可忽略性，并要求实现不利用某个属性时 `__has_cpp_attribute` 返回 0（[[P2552R3]]）；单个结构化绑定可以带属性。当前草案还允许 `maybe_unused` 用于标签。

## 常见误解

!!! pitfall "属性不改变语义"
    这只对标准属性成立。厂商属性可以改变布局、调用约定和大小，可忽略性规则只约束 [dcl.attr] 中规定的属性。

!!! pitfall "`[[noreturn]]` 表示不抛异常"
    它只承诺不返回，抛异常完全可以，而且是 `noreturn` 函数结束的常见方式之一。

## 思考题

!!! question "思考题 1"
    下面每一行是非良构，还是会被忽略？
    ```cpp
    [[noreturn]] int a;
    [[gnu::noreturn]] int b;
    [[nodiscard]] [[nodiscard]] int c();
    [[my_attr]] int d;
    [[std::my_attr]] int e;
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：非良构。`noreturn` 只能用于函数（¶7、注 5），本机 Clang 报错。
- `b`：`gnu::noreturn` 是厂商属性，行为由实现定义，标准不要求诊断。本机 Clang 给出警告 `'noreturn' only applies to function types` 后忽略它。
- `c`：良构。两个独立的 `[[...]]` 重复同一属性一直是允许的；C++23 起在同一个列表里写两次也允许。
- `d`：被忽略。但不带命名空间、标准没有规定的记号是保留给将来的（¶8.1），不应该这样起名。
- `e`：被忽略，`std` 命名空间的记号同样是保留的（¶8.2）。
</details>

!!! question "思考题 2"
    为什么 `assume` 可以做成标准属性，而 C++26 的契约断言 `pre(expr)` 有自己的语法？

<details markdown="1">
<summary>答案</summary>

因为可忽略性规则（¶8 注 6）。删掉 `[[assume(e)]]`，原来 `e` 为假时的 UB 变成了有定义的执行，可能执行只会变少。契约检查失败时可能终止程序；删掉断言，程序就会继续执行下去，这是原程序里不可能出现的执行，不再是子集。所以契约不能是一个可以忽略的属性。
</details>
