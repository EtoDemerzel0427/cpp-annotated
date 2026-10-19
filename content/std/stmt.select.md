---
title: 选择语句：if、if constexpr、if consteval、switch
summary: if 和 switch 怎样选择分支：带初始化器的写法、if constexpr 的弃置语句、if consteval 的立即函数语境，以及 switch 的条件类型、case 常量和不能跳过初始化的限制。
status: done
covers: stmt.select.general, stmt.if, stmt.switch
since: c++98
papers: P0292R2, P0305R1, P1401R5, P1938R3, P2593R1
related: stmt.pre, stmt.label, stmt.dcl, temp.res.general, dcl.spec.auto, expr.const, dcl.attr.fallthrough
tags: 语句, if constexpr, 模板, 常量求值
updated: 2026-10-19
---

!!! tldr
    - `if (init; cond)` 和 `switch (init; cond)` 相当于外面套一层花括号，初始化器里的变量活到整条语句结束，`else` 分支里也能用。
    - `if constexpr` 的条件为假时，那个分支是弃置语句：在模板里它不被实例化；在模板外它照样要通过全部语义检查。
    - `if consteval` 的第一个分支是立即函数语境，可以把运行期参数传给 `consteval` 函数；`if (std::is_constant_evaluated())` 做不到这一点。
    - `switch` 的条件先做整型提升，每个 `case` 常量都按提升后的类型转换，不允许窄化，也不能重复。
    - 从 `switch` 的条件跳到 `case` 标号算一次跳转，不能绕过一个带初始化器的局部变量。

C++ 只有两种选择语句：`if` 和 `switch`。`if` 后来又有了三个变体，各自解决一个实际问题：

| 形式 | 引入 | 解决的问题 |
|---|---|---|
| `if (init; cond)`、`switch (init; cond)` | C++17 | 只在判断里用到的变量，作用域恰好覆盖这条语句 |
| `if constexpr (cond)` | C++17 | 在模板里按编译期条件丢掉一个分支，不实例化它 |
| `if consteval { }` | C++23 | 区分常量求值和运行期，并在编译期分支里调用 `consteval` 函数 |

条件本身的规则（声明形式的条件、判定变量、按语境转换为 `bool`）在 [[stmt.pre]]。

## 每个分支都是一个作用域 [stmt.select.general]

```cpp ok
void f(bool b) {
    if (b)
        int i = 1;   // i 只在这个分支里
    else
        int i = 2;   // 另一个作用域里的另一个 i
}
```

¶1 选择语句有五种语法形式：带或不带 `constexpr`、带或不带 `else` 的 `if`，带或不带 `!`、带或不带 `else` 的 `if consteval`，以及 `switch`。圆括号里可选的 *init-statement* 本身以分号结尾，所以 `if (x; y)` 里的分号属于 *init-statement*，不是分隔符。

¶2 每条选择语句，以及它的每个子语句，都有自己的块作用域（[[basic.scope.block]]）。所以分支即使不是花括号括起来的复合语句，也是一个独立的作用域。上面两个 `i` 互不冲突，`if` 之后也都看不见。

外层那个作用域容纳 *init-statement* 和条件里声明的名字，所以条件里声明的变量不能在分支的最外层再声明一次（例子见 [[stmt.pre]]）。

## if 的执行 [stmt.if]

¶1 条件为 `true` 时执行第一个子语句；有 `else` 且条件为 `false` 时执行第二个子语句。

通过标号跳进第一个子语句时，条件不求值，`else` 分支也不执行：

```cpp run ok
#include <cstdio>
int main() {
    int n = 0;
    goto in;
    if (++n > 100) {     // 条件不求值，n 保持 0
    in:
        std::puts("then");
    } else {
        std::puts("else");   // 不执行
    }
    return n;            // 0
}
```

同一段还解决了悬空 else 的歧义：`else` 与最近的、还没有配 `else` 的 `if` 结合，与缩进无关。

```cpp run ok
int sign(int a, int b) {
    if (a > 0)
        if (b > 0) return 1;
        else return 2;   // 属于 if (b > 0)
    return 3;
}
int main() { return sign(-1, 5) == 3 ? 0 : 1; }
```

Clang 在 `-Wall` 下对这种写法给出 `-Wdangling-else` 警告，建议加花括号。

## 带初始化器的 if 和 switch {{c++17}}

C++17 之前，先取值、再判断、再使用的写法只能把变量留在外层作用域，或者手写一对花括号。现在可以写成：

```cpp run ok
#include <map>
#include <string>
std::map<std::string, int> table{{"a", 1}};
int lookup(const std::string& k) {
    if (auto it = table.find(k); it != table.end())
        return it->second;
    else
        return -static_cast<int>(table.size());
}   // it 在 else 里也可见，离开 if 后不可见
int main() { return lookup("a") == 1 ? 0 : 1; }
```

¶3 `if (init-statement condition) ...` 等价于

```text
{
    init-statement
    if (condition) statement [else statement]
}
```

区别只有一点：*init-statement* 与条件处在同一个作用域。按字面改写，两者位于嵌套作用域，条件里可以重新声明同名变量；按真实规则，这是重复声明：

```cpp error
void f() {
    if (int x = 1; int x = 2) { }   // error: x 重复声明
}
```

[[stmt.switch#7]] 对 `switch` 作了同样的规定：

```cpp run ok
#include <cctype>
int classify(const char* s) {
    switch (char c = s[0];
            std::isdigit(static_cast<unsigned char>(c)) ? 1 : 0) {
    case 1:  return c - '0';
    default: return -1;
    }
}
int main() { return classify("7") == 7 ? 0 : 1; }
```

*init-statement* 可以是表达式语句、简单声明，C++23 起也可以是别名声明：

```cpp ok
#include <vector>
int g(const std::vector<int>& v) {
    if (using T = std::vector<int>::size_type; T n = v.size())
        return static_cast<int>(n);
    return 0;
}
```

!!! pitfall "没有名字的 lock_guard"
    `if (std::lock_guard{m}; ready)` 里的 `std::lock_guard{m};` 不是声明，而是一个表达式语句：它创建一个临时对象，到分号处就析构了，所以判断 `ready` 时锁已经释放。要写成 `if (std::lock_guard lk{m}; ready)`。

## if constexpr {{c++17}}

### 条件

¶2 写成 `if constexpr` 的 `if` 叫 **constexpr if 语句**。它的条件先按语境转换为 `bool`，转换后的表达式必须是常量表达式。

措辞的顺序有讲究。C++17 要求条件是 `bool` 类型的转换后常量表达式（converted constant expression，[[expr.const.const]]），而转换后常量表达式不允许窄化，`unsigned` 到 `bool` 恰好是窄化，所以 `if constexpr (flags & 4)` 原本是非良构的。C++23 的 [[P1401R5]] 改成了现在的写法，允许窄化：

```cpp ok
constexpr unsigned flags = 4;
void f() {
    if constexpr (flags & 4) { }        // unsigned → bool，C++23 起 OK
    if constexpr (sizeof(int[2])) { }   // 标准例 1：size_t → bool
}
```

本机 Clang 23 在 `-std=c++17` 下也接受第一行，没有给出诊断。

### 弃置语句

如果转换后的条件为 `false`，第一个子语句就是**弃置语句**（[[g:discarded-statement|discarded statement]]）；否则第二个子语句（如果有）是弃置语句。

在模板里，这一点最有用。实例化外围的模板化实体时，如果条件已经不再依赖模板参数的值，弃置语句就不被实例化：

```cpp run ok
#include <string>
#include <type_traits>
template<class T>
std::string to_str(const T& t) {
    if constexpr (std::is_arithmetic_v<T>)
        return std::to_string(t);   // T = std::string 时不实例化
    else
        return std::string(t);      // T = int 时不实例化
}
int main() {
    return to_str(42) == "42" && to_str(std::string("x")) == "x" ? 0 : 1;
}
```

两个分支各自只对一部分 `T` 合法。没有 `if constexpr` 时，这需要两个重载加上 SFINAE 或标签分派。可变参数模板的递归也因此不再需要单独写一个终止重载（标准例 2 的前半）：

```cpp run ok
#include <cstdio>
void handle(int v) { std::printf("%d\n", v); }
template<typename T, typename... Rest>
void g(T&& p, Rest&&... rs) {
    handle(p);
    if constexpr (sizeof...(rs) > 0)
        g(rs...);       // 参数包为空时从不实例化
}
int main() { g(1, 2, 3); }
```

### 模板外：照常检查

模板外没有实例化可言，弃置语句照样要通过名字查找、类型检查等全部语义检查。`if constexpr` 不是预处理器的 `#if`。

<div class="compare" markdown="1">

```cpp error
void g() {
    if constexpr (false) {
        undeclared();  // error: 未声明
    }
}
```

```cpp error
void q() {
    if constexpr (true) { }
    else { int* p = 1.0; } // error
}
```

</div>

不过有两个效果在模板外同样成立：

- 弃置语句里的 odr-use（需要实体有定义的那种使用，见 [[basic.def.odr]]）不要求被使用的实体有定义（¶2 的注 1）。
- 弃置语句里的 `return` 不参与返回类型推导（[[dcl.spec.auto#4]]）。

```cpp run ok
#include <type_traits>
extern int x;                  // 没有定义
int f() {
    if constexpr (true)
        return 0;
    else if (x)                // 在弃置语句里 odr-use x：不需要定义
        return x;
    else
        return -x;
}
auto h() {
    if constexpr (true) return 1;
    else return 2.0;           // 不参与推导
}
static_assert(std::is_same_v<decltype(h()), int>);
int main() { return f(); }
```

`f` 是标准例 2 的后半。`else if (x)` 里的 `if` 是普通 `if`，整个 `if (x) ... else ...` 都在弃置语句里。

| 效果 | 依据 | 模板内 | 模板外 |
|---|---|---|---|
| 不被实例化 | [[stmt.if#2]] | 是（条件实例化后不依赖值时） | 不适用，照常检查 |
| odr-use 不要求定义 | [[stmt.if#2]] 注 1 | 是 | 是 |
| `return` 不参与推导 | [[dcl.spec.auto#4]] | 是 | 是 |

### 模板里的 static_assert(false) {{c++23}}

不被实例化不等于不检查。模板里的弃置分支仍会被解析，不依赖模板参数的错误编译器通常在定义处就会报告。按 [[temp.res.general#6]]，如果一个 constexpr if 的子语句不可能产生任何有效的特化，程序是非良构的，且不要求诊断。

这条规则过去让 `static_assert(false, ...)` 不能出现在弃置分支里。C++23 的 [[P2593R1]] 让 [[temp.res.general#6]] 忽略失败的 `static_assert`，并规定模板里的 `static_assert` 只在实例化时才算失败，于是可以直接这样写：

```cpp ok
#include <type_traits>
template<class T>
int code(T) {
    if constexpr (std::is_integral_v<T>)
        return 1;
    else
        static_assert(false, "unsupported type");   // 只有 else 被实例化时才触发
}
int a = code(1);
```

在此之前，只能写 `static_assert(sizeof(T) == 0)` 这类依赖 `T` 的条件来绕开。模板外就没有这层保护，弃置语句里的 `static_assert(false)` 照样触发：

```cpp error
void h3() {
    if constexpr (false) { static_assert(false); }   // error
}
```

!!! lawyer "条件在外层实例化后仍然依赖值"
    如果 `if constexpr` 在泛型 lambda 里，条件依赖 lambda 自己的参数类型，那么外层模板实例化时条件仍依赖值，两个分支都保留下来。等到 lambda 的 `operator()` 被实例化，才丢掉弃置的那个：

    ```cpp
    template<class T> void outer(T) {
        [](auto u) {
            if constexpr (sizeof(u) > 100) u.nonexistent();
        }(0);                  // u 是 int：此时才丢弃该分支
    }
    template void outer(int);  // OK
    ```

### 不能跳进分支

¶2 的最后一句规定，constexpr if 的每个子语句都是控制流受限语句（[[g:control-flow-limited-statement|control-flow-limited statement]]，[[stmt.label#3]]）：不能从外面 `goto` 进去，外层 `switch` 的 `case` 标号也不能放在里面。否则一个可能不存在的分支就可能成为跳转目标。例子见 [[stmt.pre]]。

!!! pitfall "`else if` 不会自动变成 `else if constexpr`"
    ```cpp
    if constexpr (A) { ... }
    else if (B) { ... }            // 普通 if：两个分支都会被实例化
    else if constexpr (B) { ... }  // 这才是编译期选择
    ```

!!! pitfall "`if constexpr (std::is_constant_evaluated())` 永远为真"
    `if constexpr` 的条件本身就是显然常量求值的（[[g:manifestly-constant-evaluated|manifestly constant-evaluated]]，[[expr.const.defns]]），所以这里的 `std::is_constant_evaluated()` 总是 `true`。Clang 对此给出 `-Wconstant-evaluated` 警告。要用 `if consteval`，或普通的 `if (std::is_constant_evaluated())`。

!!! note "协程"
    协程里不能出现 `return` 语句，即使它位于弃置语句里也不行（[[stmt.return.coroutine#1]] 的注）。所以不能用 `if constexpr` 在协程里按条件保留一个普通的 `return`。

## if consteval {{c++23}}

```cpp run ok
consteval int sq_ct(int x) { return x * x; }
constexpr int sq(int x) {
    if consteval {
        return sq_ct(x);   // OK：x 不是常量也可以
    } else {
        return x * x;      // 运行期路径
    }
}
static_assert(sq(3) == 9);   // 走第一个分支
int main(int argc, char**) {
    return sq(argc) == 1 ? 0 : 1;   // 走 else
}
```

¶4 写成 `if consteval` 的 `if` 叫 **consteval if 语句**。它没有条件，也没有 *init-statement*，而且分支必须是复合语句。

¶5 如果 consteval if 语句在显然常量求值的语境中求值（例如 `static_assert` 的条件、`constexpr` 变量的初始化器），执行第一个子语句；否则执行 `else` 分支（如果有）。两个子语句都是控制流受限语句。

关键在 ¶5 的注 2：第一个子语句是[[g:immediate-function-context|立即函数语境]]（[[expr.const.imm]]）。`consteval` 函数是只能在编译期调用的函数，通常每次调用本身都必须是常量表达式；在立即函数语境里则没有这个要求。普通的 `if (std::is_constant_evaluated())` 没有这一层效果：

```cpp error
#include <type_traits>
consteval int sq_ct(int x) { return x * x; }
constexpr int sq(int x) {
    if (std::is_constant_evaluated())
        return sq_ct(x);   // error: 不是立即函数语境，x 不是常量
    return x * x;
}
```

这也解释了为什么 `if consteval` 被设计成一种语句而不是一个布尔表达式：处于立即函数语境是一段代码的属性，要附着在语法上；而是否在常量求值中，也不该是一个能存进变量、传来传去的值。

花括号是强制的。标准例 3 说明了原因：如果 `if consteval` 的分支可以是任意语句，悬空 else 的歧义会更难察觉。

```cpp error
constexpr int f(int x) {
    if consteval return x;   // error: 必须是复合语句
    else return 0;
}
```

¶6 `if ! consteval { A }` 不是 consteval if 语句，而是等价于 `if consteval { } else { A }`；`if ! consteval { A } else B` 等价于 `if consteval B else { A }`。所以 `if !consteval` 的第一个分支不是立即函数语境，它的 `else` 分支才是。

```cpp error
consteval int sq_ct(int x) { return x * x; }
constexpr int h(int x) {
    if !consteval { return -1; }
    return sq_ct(x);   // error: 这里不是立即函数语境
}
```

## switch [stmt.switch]

### 条件和 case 常量

```cpp error
void f(unsigned u, unsigned char c, int i) {
    switch (u) { case -1: break; }   // error: 窄化
    switch (c) { case 300: break; }  // OK: c 提升为 int
    switch (i) { case 1.0: break; }  // error: double → int
    switch (i) { case 'a': case 97: break; } // error: 重复
}
```

¶1–¶2 `switch` 根据条件的值把控制转到若干语句之一。条件的值按下面的步骤确定：

1. 条件是表达式时取表达式的值，是声明时取判定变量的值（[[stmt.pre#5]]）。这里不转换为 `bool`。
2. 值必须是整型、枚举或类类型。类类型要按语境隐式转换为整型或枚举类型，这要求类恰好有一个合适的非 explicit 转换函数。
3. 如果得到的类型会做整型提升，就转换为提升后的类型，例如 `unsigned char`、`short`、`bool` 变成 `int`。结果叫条件的调整后类型（adjusted type）。

每个 `case` 后的常量表达式必须是调整后类型的[[g:converted-constant-expression|转换后常量表达式]]，所以不允许窄化，也不允许浮点到整型的转换。同一个 `switch` 里，转换后的 case 值不能重复。上例的四行正好对应这几条。

作用域枚举与整数之间没有隐式转换，所以 `case` 只能写枚举项：

```cpp error
enum class E { a, b };
void g(E e) {
    switch (e) {
    case E::a: break;   // OK
    case 0: break;      // error: int 不能隐式转换为 E
    }
}
```

类类型的条件：

```cpp ok
struct Code {
    int v;
    operator int() const { return v; }
};
int f(Code c) {
    switch (c) {   // 按语境隐式转换为 int
    case 1: return 10;
    default: return 0;
    }
}
```

¶3 一个 `switch` 里最多有一个 `default:`。¶4 `switch` 可以嵌套，`case` 和 `default` 标号属于包围它的最小的那个 `switch`。

### 执行与贯穿

¶5 执行 `switch` 时先求值条件。有 case 常量等于条件，就跳到那个标号；没有就跳到 `default`；连 `default` 也没有，`switch` 里的语句一条也不执行。

¶6 标号本身不改变控制流，执行会越过下一个 `case` 标号继续往下走，这叫贯穿（fall through）。要离开 `switch`，用 `break`（[[stmt.break]]）。有意贯穿时，写 `[[fallthrough]];`（[[dcl.attr.fallthrough]]）来消除 `-Wimplicit-fallthrough` 警告。

`case` 标号不必出现在 `switch` 体的顶层，只要被这个 `switch` 包围就行（[[stmt.label#2]]）。最有名的例子是 Duff's device，标号位于 `do` 循环体内：

```cpp ok
void send(volatile short* to, const short* from, int count) {
    int n = (count + 7) / 8;
    switch (count % 8) {
    case 0: do { *to = *from++;
    case 7:      *to = *from++;
    case 6:      *to = *from++;
    case 5:      *to = *from++;
    case 4:      *to = *from++;
    case 3:      *to = *from++;
    case 2:      *to = *from++;
    case 1:      *to = *from++;
            } while (--n > 0);
    }
}
```

中间隔着控制流受限语句（如 `if constexpr` 的分支）时就不行了。

### 不能跳过初始化

```cpp error
#include <string>
int f(int k) {
    switch (k) {
    case 0:
        std::string s = "zero";  // 作用域延伸到 switch 末尾
        return 0;
    case 1:                      // error: 绕过了 s 的初始化
        return 1;
    }
    return -1;
}
```

从条件跳到 `case` 标号算一次跳转，所以适用 [[stmt.dcl#2]]：跳转不能越过一个局部变量的声明，进入它的作用域，除非这个变量是[[g:vacuous-initialization|空初始化]]的，也就是默认初始化且什么都不做（例如 `int x;`）。

修复办法是给这个 case 加一对花括号，把变量限制在自己的块里：

<div class="compare" markdown="1">

```cpp ok
#include <string>
int f(int k) {
    switch (k) {
    case 0: {
        std::string s = "zero";
        return (int)s.size();
    }
    case 1:
        return 1;
    }
    return -1;
}
```

```cpp ok
void g(int k) {
    switch (k) {
    case 0:
        int x;   // 空初始化
        x = 1;
        (void)x;
        break;
    case 1:
        x = 2;   // OK：只是赋值
        (void)x;
        break;
    }
}
```

</div>

## 实现视角

!!! impl "if constexpr 的检查时机"
    GCC、Clang、MSVC 都在模板定义时解析两个分支，实例化时只替换选中的分支。弃置分支里依赖模板参数的错误永远不会报告，不依赖模板参数的明显错误通常在定义时就报告。标准只保证不实例化，不保证不检查，所以同一段弃置代码在不同编译器上报错的时机可能不同。

!!! impl "switch 的代码生成"
    case 值密集时，编译器通常生成跳转表，用条件值做下标取目标地址；稀疏时生成比较树。GCC 和 Clang 支持区间 case `case 1 ... 5:`，这是 GNU 扩展，不是标准 C++。对枚举做 `switch` 却没覆盖全部枚举项、也没有 `default` 时，`-Wswitch`（在 `-Wall` 中）会给出警告。

## 历史

!!! history
    - C++98 已经有声明形式的条件、类类型的 `switch` 条件，以及不能跳过初始化的规则。
    - C++17 加入 `if constexpr`（[[P0292R2]]）、带初始化器的 `if`/`switch`（[[P0305R1]]）和 `[[fallthrough]]`。
    - C++23 加入 `if consteval`（[[P1938R3]]），允许 `if constexpr` 的条件窄化到 `bool`（[[P1401R5]]），允许 *init-statement* 是别名声明，并让未实例化模板中的 `static_assert(false)` 合法（[[P2593R1]]）。
    - C++26 允许条件是结构化绑定声明（见 [[stmt.pre]]）。

## 思考题

!!! question "1. 下面的程序良构吗？`f<int>` 的返回类型是什么？"
    ```cpp
    template<class T> auto f() {
        if constexpr (sizeof(T) > 1) return 1;
        else return 'c';
    }
    auto x = f<int>();
    auto y = f<char>();
    ```

<details markdown="1">
<summary>答案</summary>

良构。每个特化里，弃置的 `return` 不参与返回类型推导（[[dcl.spec.auto#4]]），弃置分支也不被实例化。`f<int>` 返回 `int`，`f<char>` 返回 `char`：同一个模板的不同特化可以推导出不同的返回类型。
</details>

!!! question "2. 执行 `f(1)` 会发生什么？"
    ```cpp
    int f(int k) {
        switch (k) {
            int x = 42;       // ①
        case 1:
            return x;
        }
        return 0;
    }
    ```

<details markdown="1">
<summary>答案</summary>

程序非良构，根本不会执行。从条件跳到 `case 1` 会进入 `x` 的作用域而绕过它的初始化，违反 [[stmt.dcl#2]]。如果改成 `int x;`，程序良构，但 `return x;` 读的是没有初始化的 `int`：C++26 中这是错误行为（erroneous behavior，读到一个错误值，见 [[basic.indet]]），之前是未定义行为。
</details>

!!! question "3. `if consteval` 的第一个分支调用一个普通 `constexpr` 函数，后者再把运行期参数传给 `consteval` 函数。可以吗？"

<details markdown="1">
<summary>答案</summary>

不可以，除非那个函数会被立即升级（例如它是 constexpr 函数模板或 lambda，见 [[expr.const.imm]]）。立即函数语境只覆盖 `if consteval` 第一个分支自身的代码，不会传递到它调用的函数里。被调用的普通 `constexpr` 函数里，`consteval` 调用仍须是常量表达式，否则在那个函数的定义处就非良构。
</details>

## 小结

| 形式 | 条件 | 关键规则 |
|---|---|---|
| `if (c)` | 按语境转换为 `bool` | 经标号进入第一个分支时不求值条件、不执行 `else`；`else` 与最近的未配对 `if` 结合 |
| `if (init; c)` | 同上 | 相当于外套一层块；init 与 c 在同一作用域 |
| `if constexpr (c)` | 转换为 `bool` 后是常量表达式，允许窄化 | 模板内弃置分支不实例化；模板外照常检查；odr-use 不要求定义；`return` 不参与推导；不能跳进分支 |
| `if consteval { }` | 无，看是否显然常量求值 | 分支必须是复合语句；第一个分支是立即函数语境；`if !consteval` 是改写 |
| `switch (c)` | 整型、枚举或类类型，再做整型提升 | case 是调整后类型的转换后常量表达式，不得重复；最多一个 `default`；不能跳过非空初始化 |
