---
title: 选择语句：if、if constexpr、if consteval、switch
summary: 选择语句的语法与块作用域；if 的执行规则与悬空 else；带初始化器的 if/switch（C++17）；if constexpr 与弃置语句；if consteval（C++23）；switch 的条件类型、case 常量与跳过初始化的限制。
status: draft
covers: stmt.select.general, stmt.if, stmt.switch
since: c++98
papers: P0292R2, P0305R1, P1401R5, P1938R3, P2593R1
related: stmt.pre, stmt.label, stmt.dcl, temp.res.general, dcl.spec.auto, expr.const, dcl.attr.fallthrough
tags: 语句, if constexpr, 模板, 常量求值
updated: 2026-10-17
---

选择语句"从若干控制流中选一条"。C++ 只有两种：`if` 和 `switch`。但 `if` 在三十年间长出了三个变体，每个都解决一个实际问题：

| 形式 | 引入 | 解决的问题 |
|---|---|---|
| `if (init; cond)` / `switch (init; cond)` | C++17 | 让只在判断中用到的变量的作用域恰好覆盖这条语句 |
| `if constexpr (cond)` | C++17 | 在模板里按编译期条件**丢弃**一个分支，不实例化它（取代大量 SFINAE/标签分派） |
| `if consteval { }` | C++23 | 区分"正在常量求值"与"运行期"，并且在编译期分支里可以调用 `consteval` 函数 |

本页覆盖 [[stmt.select.general]]、[[stmt.if]]、[[stmt.switch]]。条件（*condition*）本身的规则——声明形式、判定变量、按语境转换为 bool——在 [[stmt.pre]]。

## 语法与作用域 [stmt.select.general]

¶1 选择语句的五种语法形式：

```text
if constexpr(opt) ( init-statement(opt) condition ) statement
if constexpr(opt) ( init-statement(opt) condition ) statement else statement
if !(opt) consteval compound-statement
if !(opt) consteval compound-statement else statement
switch ( init-statement(opt) condition ) statement
```

*init-statement* 以分号结尾（注 1），所以 `if (x; y)` 中的分号属于 *init-statement*，而不是分隔符。

¶2（注 2）**每个选择语句以及它的每个子语句都有一个块作用域**（[[basic.scope.block]]）。所以即便分支不是复合语句，它也是一个独立的作用域：

```cpp ok
void f(bool b) {
    if (b)
        int i = 1;   // i 的作用域只是这个子语句
    else
        int i = 2;   // 另一个作用域里的另一个 i
    // i 在这里不可见
}
```

这条注释的规范依据在 [[basic.scope.block]]：选择语句本身引入一个块作用域（容纳 *init-statement* 和 *condition* 中声明的名字），每个子语句又各自引入一个。后者使得条件中声明的变量不能在子语句的最外层被重新声明（例子见 [[stmt.pre]]）。

## if 语句 [stmt.if]

### 基本语义与悬空 else（¶1）

¶1 条件为 `true` 执行第一个子语句；有 `else` 且条件为 `false` 执行第二个子语句。

两条不那么显然的规定：

1. **如果通过标号进入第一个子语句**，条件不求值，第二个子语句也不执行。也就是说 `goto` 进 then 分支之后，执行完 then 分支就离开整个 `if`，不会"顺带"执行 else。
2. **悬空 else**（dangling else）：在带 `else` 的形式中，如果第一个子语句本身也是 `if`，那么这个内层 `if` 必须带 `else`。脚注说得更直白："`else` 与最近的、尚未配 `else` 的 `if` 结合"。这是一条语法消歧规则，而不是额外的约束。

```cpp run ok
#include <cstdio>
int main() {
    int n = 0;
    goto in;
    if (++n > 100) {     // 条件不会被求值：n 保持 0
    in:
        std::puts("then");
    } else {
        std::puts("else");   // 不执行
    }
    return n;            // 0
}
```

```cpp run ok
int sign(int a, int b) {
    if (a > 0)
        if (b > 0) return 1;
        else return 2;   // 这个 else 属于 if (b > 0)，与缩进无关
    return 3;
}
int main() { return sign(-1, 5) == 3 ? 0 : 1; }
```

Clang 对这种写法有 `-Wdangling-else` 警告，建议加花括号。

### 带初始化器的 if（¶3）{{c++17}}

¶3 `if (init-statement condition) ...` 等价于

```text
{
    init-statement
    if (condition) statement [else statement]
}
```

**但** *init-statement* 与 *condition* 处于**同一个作用域**。这个但书有两个后果：

- 不能在条件里重新声明 *init-statement* 中声明过的名字（若按字面改写，两者在嵌套作用域中，内层声明会合法地遮蔽外层）；
- *init-statement* 中的变量在两个分支中都可见，并且**活到整个 `if` 语句结束**（包括 `else` 分支执行完毕）。

动机：C++17 之前，"获取—判断—使用"模式只能把变量泄漏到外层作用域，或者手写一对花括号：

```cpp run ok
#include <map>
#include <mutex>
#include <string>
std::map<std::string, int> table{{"a", 1}};
std::mutex m;
int lookup(const std::string& k) {
    if (std::lock_guard lk(m); true) { }            // 锁的作用域恰好是这条 if
    if (auto it = table.find(k); it != table.end()) // it 只在这条 if（含 else）中可见
        return it->second;
    else
        return -static_cast<int>(table.size());     // else 分支里也能用 it、table
}
int main() { return lookup("a") == 1 ? 0 : 1; }
```

```cpp error
void f() {
    if (int x = 1; int x = 2) { }   // error: init-statement 与 condition 同一作用域，x 重复声明
}
```

*init-statement* 可以是表达式语句、简单声明，或（C++23 起）别名声明：

```cpp ok
#include <vector>
int g(const std::vector<int>& v) {
    if (using T = std::vector<int>::size_type; T n = v.size())   // C++23 起允许 alias-declaration
        return static_cast<int>(n);
    return 0;
}
```

!!! pitfall "init-statement 中的无名临时对象"
    `if (std::lock_guard{m}; ready)` 中的 `std::lock_guard{m};` **不是声明**（声明符不能以 `{` 开头），而是一个表达式语句：它创建一个临时 `lock_guard`，在这个完整表达式结束时立即析构——锁在判断 `ready` 之前就已经释放了。Clang 对此会给出"忽略了由 nodiscard 构造函数创建的临时对象"之类的警告（libc++ 把 `lock_guard` 的构造函数标为 `[[nodiscard]]`）。必须给变量起名字：`if (std::lock_guard lk{m}; ready)`。

### if constexpr（¶2）{{c++17}}

#### 条件：常量表达式，允许窄化

¶2 形如 `if constexpr` 的 `if` 称为 **constexpr if 语句**。它的条件**按语境转换为 bool**，转换后的表达式必须是常量表达式（[[expr.const.const]]）。

注意措辞是"先转换、再要求常量"，而不是"转换后的常量表达式"（*converted constant expression*）。区别在于：*converted constant expression* 禁止窄化转换，而 `int → bool` 是窄化转换。C++17/20 中条件是"bool 类型的按语境转换的常量表达式"，因此 `if constexpr (flags & 4)` 是**非良构**的，必须写 `if constexpr ((flags & 4) != 0)`。C++23（[[P1401R5]]）放宽了这一点，标准的例 1 `if constexpr (sizeof(int[2]))` 就是专门演示"允许窄化"的。

```cpp ok
constexpr unsigned flags = 4;
void f() {
    if constexpr (flags & 4) { }          // C++23 起 OK：int → bool 的窄化被允许
    if constexpr (sizeof(int[2])) { }     // 标准例 1：size_t → bool
}
```

#### 弃置语句

若转换后的条件为 `false`，第一个子语句是**弃置语句**（[[g:discarded-statement|discarded statement]]）；否则第二个子语句（如果有）是弃置语句。"弃置"带来三个效果，它们**适用范围不同**，这是理解 `if constexpr` 的关键：

| 效果 | 规范依据 | 模板内 | 模板外 |
|---|---|---|---|
| 弃置分支**不被实例化** | [[stmt.if#2]] | 是（条件实例化后不依赖值时） | 不适用：非模板代码没有"实例化"，弃置分支照常做完整的语义检查 |
| 弃置分支中的 odr-use **不要求实体有定义** | [[stmt.if#2]] 注 1、[[basic.def.odr]] | 是 | 是 |
| 弃置分支中的 `return` **不参与返回类型推导** | [[dcl.spec.auto#4]] | 是 | 是 |

**模板外**：弃置分支仍然要通过名字查找、类型检查等一切语义检查。`if constexpr` 不是预处理器的 `#if`。

```cpp error
void g() {
    if constexpr (false) {
        undeclared();          // error: 非模板中，弃置分支仍需通过名字查找
    }
}
```

```cpp error
void q() {
    if constexpr (true) { }
    else { int* p = 1.0; }     // error: 弃置分支仍做类型检查
}
```

但 odr-use 和返回类型推导在模板外同样受益——这正是标准例 2 后半部分想说明的：

```cpp run ok
#include <type_traits>
extern int x;                  // 没有定义
int f() {
    if constexpr (true)
        return 0;
    else if (x)                // odr-use 了 x，但在弃置语句中：不需要 x 的定义
        return x;
    else
        return -x;
}
auto h() {
    if constexpr (true) return 1;
    else return 2.0;           // 弃置的 return 不参与推导：返回类型是 int，而不是"推导冲突"
}
static_assert(std::is_same_v<decltype(h()), int>);
int main() { return f(); }
```

注意例 2 里 `else if (x)` 中的 `if` 是**普通 if**，整个 `if (x) ... else ...` 都在弃置语句里。

**模板内**：在实例化外围的模板化实体（[[temp.pre]]）时，如果条件在实例化之后**不再依赖值**（not value-dependent），弃置的子语句**不被实例化**。这才是 `if constexpr` 真正的威力：

```cpp run ok
#include <string>
#include <type_traits>
template<class T>
std::string to_str(const T& t) {
    if constexpr (std::is_arithmetic_v<T>)
        return std::to_string(t);   // T = std::string 时不实例化：否则 to_string(string) 不存在
    else
        return std::string(t);      // T = int 时不实例化：否则 string(int) 非良构
}
int main() {
    return to_str(42) == "42" && to_str(std::string("x")) == "x" ? 0 : 1;
}
```

标准例 2 前半部分是递归可变参数模板的经典终止写法：

```cpp run ok
#include <cstdio>
void handle(int v) { std::printf("%d\n", v); }
template<typename T, typename... Rest>
void g(T&& p, Rest&&... rs) {
    handle(p);
    if constexpr (sizeof...(rs) > 0)
        g(rs...);                  // 空参数包时从不实例化，因此不需要单独写 g() 重载
}
int main() { g(1, 2, 3); }
```

#### "不实例化"不等于"不检查"

模板中的弃置分支仍然会被**解析**，对其中**不依赖模板参数**的构造，编译器可以（也通常会）在模板定义时就检查。更重要的是 [[temp.res.general#6]]：如果模板中某个 constexpr if 子语句**不可能产生任何有效的特化**、且外围模板未被实例化，程序是 IFNDR。

经典的例外是 `static_assert(false)`：C++23 起（[[P2593R1]]，作为缺陷报告追溯适用），[[temp.res.general#6]] 在判断"能否产生有效特化"时**忽略失败的 `static_assert` 声明**。于是"在弃置分支里写 `static_assert(false, ...)` 报告不支持的类型"这一惯用法终于合法了；在此之前人们必须写 `static_assert(sizeof(T) == 0)` 或 `static_assert(always_false<T>)` 之类依赖于 `T` 的条件。

```cpp ok
#include <type_traits>
template<class T>
int code(T) {
    if constexpr (std::is_integral_v<T>)
        return 1;
    else
        static_assert(false, "unsupported type");   // C++23 起 OK：只有 else 分支被实例化时才触发
}
int a = code(1);
```

而在模板之外，`static_assert(false)` 即使位于弃置语句里也会触发，因为非模板代码中的弃置语句照常检查：

```cpp error
void h3() {
    if constexpr (false) { static_assert(false); }   // error: 模板外，静态断言照常求值
}
```

!!! lawyer "嵌套模板：条件在外层实例化后仍然依赖值"
    "不实例化"的前提是条件在实例化后**不依赖值**。若 `if constexpr` 位于泛型 lambda 中、条件依赖 lambda 自己的模板参数，那么在外层模板实例化时，条件仍然依赖值，两个分支都会作为（lambda 的）模板定义的一部分被保留下来，直到 lambda 的 `operator()` 被实例化时才做选择：

    ```cpp
    template<class T> void outer(T) {
        [](auto u) {
            if constexpr (sizeof(u) > 100) u.nonexistent();   // 外层实例化时条件仍依赖值
        }(0);                                                // u = int：此时才丢弃该分支
    }
    template void outer(int);   // OK
    ```

#### 弃置分支是控制流受限语句

constexpr if 的每个子语句都是**控制流受限语句**（[[stmt.label#3]]）：不能从外面 `goto` 进去，不能被外层 `switch` 的 `case` 分派进去。否则，"弃置的分支不存在"这一模型就会被破坏。例子见 [[stmt.pre]] 中"控制流受限语句"一节。

!!! pitfall "`else if` 不会自动变成 `else if constexpr`"
    ```cpp
    if constexpr (A) { ... }
    else if (B) { ... }          // 这是普通 if，B 在运行期求值；两个分支都会被实例化
    else if constexpr (B) { ... } // 这才是编译期选择
    ```
    在模板里写漏 `constexpr` 的后果是：本应被丢弃的分支被实例化，产生莫名其妙的编译错误。

!!! pitfall "`if constexpr (std::is_constant_evaluated())` 永远为真"
    `if constexpr` 的条件本身是**明显常量求值**的（[[expr.const.defns]]），所以 `std::is_constant_evaluated()` 在这里总返回 `true`，函数在运行期调用时也走"编译期"分支。Clang 和 GCC 都会对此给出警告。正确的写法是 `if consteval`（见下文）或普通 `if (std::is_constant_evaluated())`。

!!! note "协程与弃置语句"
    [[stmt.return.coroutine#1]] 的注明确说：判断"协程不得包围 `return` 语句"时，`return` 是否位于弃置语句中**无关紧要**。所以不能用 `if constexpr` 让一个函数"有时是协程、有时是普通函数"。

### if consteval（¶4–¶6）{{c++23}}

#### 形式（¶4）

¶4 形如 `if consteval` 的 `if` 称为 **consteval if 语句**。它**没有条件**（也没有 *init-statement*），而且其中的语句（两个分支）**必须是复合语句**。

强制花括号的原因见标准例 3：如果允许 `if consteval stmt; else ...`，悬空 else 的问题会以更隐蔽的方式出现。现在 `else ;` 不是复合语句，所以它不能属于 `if consteval`，也不能属于外层 `if`（外层 `if` 的第一个子语句已经结束了），程序非良构。

```cpp error
constexpr int f(int x) {
    if consteval return x;        // error: 必须是复合语句
    else return 0;
}
```

#### 语义（¶5）

¶5 如果 consteval if 语句在**明显常量求值**（manifestly constant-evaluated，[[expr.const.defns]]）的语境中被求值，执行第一个子语句；否则执行 `else` 分支（如果有）。

关键在注 2：**第一个子语句是即时函数语境**（immediate function context，[[expr.const.imm]]）。在即时函数语境里可以调用 `consteval` 函数而不要求调用本身是常量表达式。这正是 `if consteval` 相对于 `if (std::is_constant_evaluated())` 的决定性优势：

```cpp run ok
consteval int sq_ct(int x) { return x * x; }
constexpr int sq(int x) {
    if consteval {
        return sq_ct(x);        // OK: 即时函数语境中可以把非常量参数 x 传给 consteval 函数
    } else {
        return x * x;           // 运行期路径
    }
}
static_assert(sq(3) == 9);      // 常量求值：走第一个分支
int main(int argc, char**) { return sq(argc) == 1 ? 0 : 1; }   // 运行期：走 else 分支
```

```cpp error
#include <type_traits>
consteval int sq_ct(int x) { return x * x; }
constexpr int sq(int x) {
    if (std::is_constant_evaluated())
        return sq_ct(x);        // error: 不是即时函数语境，sq_ct(x) 必须是常量表达式，而 x 不是常量
    return x * x;
}
```

两个子语句同样是**控制流受限语句**。

#### if !consteval（¶6）

¶6 `if ! consteval { A }` 不是 consteval if 语句本身，而是等价于 `if consteval { } else { A }`；`if ! consteval { A } else B` 等价于 `if consteval B else { A }`。

推论：在 `if !consteval` 的**第一个**子语句里，不是即时函数语境；它的 `else` 分支才是。

```cpp error
consteval int sq_ct(int x) { return x * x; }
constexpr int h(int x) {
    if !consteval { return -1; }
    return sq_ct(x);            // error: if !consteval 之后的代码不是即时函数语境
}
```

!!! note "为什么 `if consteval` 没有条件"
    设计上也可以把它写成 `if (std::is_constant_evaluated())` 的语法糖，但那样无法把"第一个分支是即时函数语境"这一属性挂在语法上。另外，"是否常量求值"不是一个普通的布尔值：它不能被存进变量、传给其他函数后再测试。让它成为一种语句形式，就杜绝了这些误用。

## switch 语句 [stmt.switch]

### 条件的类型与 case 常量（¶1–¶2）

¶1 `switch` 根据条件的值把控制转移到若干语句之一。

¶2 规定了条件的取值与类型转换：

1. 条件是表达式时，值就是表达式的值；是声明时，值是**判定变量**的值（[[stmt.pre#5]]）——注意**不**转换为 bool。
2. 值必须是**整型、枚举或类类型**。类类型时，**按语境隐式转换**（contextually implicitly converted，[[conv.general]]）为整型或枚举类型：类中必须**恰好有一个**目标类型合适的非 explicit 转换函数。
3. 如果（转换后的）类型会进行**整型提升**，条件转换为提升后的类型（例如 `char`、`short`、`bool` → `int`）。这个提升后的类型称为"调整后的类型"（adjusted type）。
4. 每个 `case` 后的常量表达式必须是**调整后类型的转换后常量表达式**（converted constant expression，[[expr.const.const#8]]）。转换后常量表达式**禁止窄化**、禁止浮点到整型转换。
5. 同一 `switch` 中，转换后的 case 值**不得重复**。

```cpp error
void f(unsigned u, unsigned char c, int i) {
    switch (u) { case -1: break; }          // error: -1 → unsigned 是窄化
    switch (c) { case 300: break; }         // OK: c 提升为 int，300 可表示
    switch (i) { case 1.0: break; }         // error: double → int 不允许出现在转换后常量表达式中
    switch (i) { case 'a': case 97: break; } // error: 转换后都是 97，重复
}
```

作用域枚举不能隐式转换为整数，整数也不能隐式转换为作用域枚举，所以 `switch` 作用域枚举时 case 必须写枚举项：

```cpp error
enum class E { a, b };
void g(E e) {
    switch (e) {
    case E::a: break;     // OK
    case 0: break;        // error: int 不能隐式转换为 E
    }
}
```

类类型的条件：

```cpp ok
struct Code {
    int v;
    operator int() const { return v; }   // 唯一的非 explicit 到整型的转换函数
};
int f(Code c) {
    switch (c) {          // 按语境隐式转换为 int
    case 1: return 10;
    default: return 0;
    }
}
```

### default 与嵌套（¶3–¶4）

¶3 一个 `switch` 中最多一个 `default:`。

¶4 `switch` 可以嵌套；`case`/`default` 标号属于**包围它的最小的** `switch`。

### 执行（¶5–¶6）

¶5 执行 `switch` 时先求值条件；若某个 case 常量等于条件，控制转到该 case 标号后的语句；否则若有 `default`，转到 `default`；否则 `switch` 中的语句一条都不执行。

¶6 `case`/`default` 标号**本身不改变控制流**——控制流越过标号继续向下（"贯穿"，fall through）。要离开 `switch` 用 `break`（[[stmt.break]]）。注 1 强调：`case` 标号**不必**出现在 `switch` 体的顶层语句上，也可以深入到嵌套语句里。最著名的例子是 Duff's device：

```cpp ok
void send(volatile short* to, const short* from, int count) {
    int n = (count + 7) / 8;
    switch (count % 8) {
    case 0: do { *to = *from++;
    case 7:      *to = *from++;      // case 标号位于 do 循环体内部
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

这之所以合法，是因为 `case` 只要求被 `switch` **包围**（[[stmt.label#2]]），而 `do` 循环体是 `switch` 体的（间接）子语句。反过来，如果中间隔着一个**控制流受限语句**（如 `if constexpr` 的分支），就不行了。

有意贯穿时，用 `[[fallthrough]];` 标注（[[dcl.attr.fallthrough]]），以抑制编译器的 `-Wimplicit-fallthrough` 类警告。fallthrough 语句之后执行的下一条语句必须是同一 `switch` 的 `case`/`default` 标号语句，否则非良构。

### 跳过初始化

从 `switch` 的条件跳到 `case` 标号**被视为一次跳转**（[[stmt.dcl]] 脚注）。因此 [[stmt.dcl#2]] 的规则适用：跳转不得使一个**非 vacuous 初始化**的自动变量从"未活跃"变为"活跃"。最常见的报错：

```cpp error
#include <string>
int f(int k) {
    switch (k) {
    case 0:
        std::string s = "zero";   // s 的作用域延伸到 switch 体末尾
        return 0;
    case 1:                       // error: 跳到这里会绕过 s 的初始化
        return 1;
    }
    return -1;
}
```

`int x;`（默认初始化、vacuous initialization）不会触发这个错误，`int x = 0;` 会。修复方法是用花括号把 case 的局部变量关进自己的块：

```cpp ok
#include <string>
int f(int k) {
    switch (k) {
    case 0: {
        std::string s = "zero";   // s 的作用域到这个块结束为止
        return static_cast<int>(s.size());
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
        int x;          // vacuous initialization：允许被跳过
        x = 1;
        (void)x;
        break;
    case 1:
        x = 2;          // OK（x 在作用域内，但从未被初始化过：此处只是赋值）
        (void)x;
        break;
    }
}
```

### 带初始化器的 switch（¶7）{{c++17}}

¶7 与 `if` 相同：`switch (init-statement condition) statement` 等价于外面套一层块，但 *init-statement* 与 *condition* 同一作用域。

```cpp run ok
#include <cctype>
int classify(const char* s) {
    switch (char c = s[0]; std::isdigit(static_cast<unsigned char>(c)) ? 1 : 0) {
    case 1:  return c - '0';
    default: return -1;
    }
}
int main() { return classify("7") == 7 ? 0 : 1; }
```

## 实现视角

!!! impl "if constexpr 与模板实例化"
    GCC、Clang、MSVC 都在模板定义时解析两个分支、建立 AST，在实例化时只对选中的分支做替换（substitution）。因此弃置分支中依赖模板参数的错误永远不会被报告，而不依赖模板参数的明显错误（比如调用一个根本未声明且没有依赖参数的函数）通常在定义时就被报告。MSVC 在历史上的非两阶段查找模式下会把更多检查推迟到实例化时，因此同一段弃置代码在不同编译器上被报告的时机可能不同——但标准只保证"不实例化"，不保证"不检查"。

!!! impl "switch 的代码生成"
    case 值密集时，编译器通常生成**跳转表**（jump table：用条件值做下标取目标地址）；稀疏时生成二分比较树或比较链。`[[likely]]`/`[[unlikely]]` 可以标在 case 标号后的语句上，影响分支布局。GCC 和 Clang 都支持 GNU 扩展 `case 1 ... 5:`（区间 case），这不是标准 C++。

!!! impl "警告"
    `-Wswitch`（Clang/GCC 的 `-Wall` 中包含）在 `switch` 一个枚举且未覆盖所有枚举项、又没有 `default` 时警告；`-Wimplicit-fallthrough` 对未标注的贯穿警告。对 `if constexpr (std::is_constant_evaluated())`，Clang 有 `-Wconstant-evaluated`。

## 历史与演进

!!! history
    - **C++98**：`if`/`switch`，条件可以是声明；`switch` 条件的类类型需能转换为整型；跳过初始化的规则已经存在。
    - **C++11**：`switch` 条件允许作用域枚举；case 常量的要求随着 constexpr 的引入改写为"转换后常量表达式"。
    - **C++17**：`if constexpr`（[[P0292R2]]）；`if`/`switch` 的 *init-statement*（[[P0305R1]]）；`[[fallthrough]]`。
    - **C++20**：`[[likely]]`/`[[unlikely]]`。
    - **C++23**：`if consteval`（[[P1938R3]]）；`if constexpr` 的条件允许窄化到 bool（[[P1401R5]]）；*init-statement* 允许别名声明；复合语句末尾的标号，使 `default:` 可以直接出现在 `}` 前；`static_assert(false)` 在未实例化的模板中不再导致 IFNDR（[[P2593R1]]）。
    - **C++26**：条件可以是结构化绑定声明（见 [[stmt.pre]]）。

## 陷阱

!!! pitfall "条件中的声明 vs. init-statement 的生命周期"
    `if (auto p = f())` 中的 `p` 和 `if (auto p = f(); p)` 中的 `p` 生命周期相同：都持续到整条 `if`（含 else）结束。区别仅在于前者用 `p` 本身做判断，后者可以写任意条件。

!!! pitfall "switch 不能处理字符串"
    条件必须是整型/枚举/可转换的类类型。想 `switch` 字符串，常见做法是先哈希（`constexpr` 哈希函数可以让 case 标号也用同一个函数计算），但要自己处理冲突。

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

良构。对每个特化，弃置的 `return` 不参与返回类型推导（[[dcl.spec.auto#4]]），并且在模板中弃置分支不被实例化。`f<int>` 返回 `int`，`f<char>` 返回 `char`。同一个模板的不同特化可以有不同的推导返回类型。
</details>

!!! question "2. 下面的 switch 中，执行 f(1) 会发生什么？"
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

程序非良构，根本不会执行。① 是 `switch` 体中第一个 `case` 之前的声明语句，它永远不会被顺序执行到；从条件跳到 `case 1` 会使 `x`（初始化不是 vacuous 的）从不活跃变为活跃，违反 [[stmt.dcl#2]]（从条件到 case 标号视为跳转）。若改成 `int x;`，程序良构，但 `return x;` 读取的是一个未经初始化的 `int`：在 C++26 中这是**错误行为**（erroneous behavior，读到的是错误值，见 [[basic.indet]]），在之前的标准中是 UB。
</details>

!!! question "3. `if consteval` 的第一个分支里调用一个 `constexpr` 函数，该函数里又调用 `consteval` 函数，参数是运行期值。这样可以吗？"

<details markdown="1">
<summary>答案</summary>

不行（除非那个 `constexpr` 函数本身是**即时升级**的，即 constexpr 函数模板、lambda 等，见 [[expr.const.imm]]）。"即时函数语境"只覆盖 `if consteval` 第一个子语句**本身的代码**，不会传递到它调用的其他函数里去：被调用的普通 `constexpr` 函数内部的 `consteval` 调用仍须是常量表达式，否则在那个函数的定义处就是非良构的。
</details>

## 小结

| 形式 | 条件 | 关键规则 |
|---|---|---|
| `if (c)` | 按语境转换为 bool | 通过标号进入 then 分支时不求值条件、不执行 else；else 与最近的未配对 if 结合 |
| `if (init; c)` | 同上 | 等价于外套一层块；init 与 c 同一作用域；init 中的变量活到整个 if 结束 |
| `if constexpr (c)` | 按语境转换为 bool 后为常量表达式（C++23 起允许窄化） | 弃置分支：模板内不实例化；odr-use 不需定义；return 不参与推导；模板外仍做完整检查；分支是控制流受限语句 |
| `if consteval { }` | 无（取决于是否明显常量求值） | 分支必须是复合语句；第一个分支是即时函数语境；`if !consteval` 是改写 |
| `switch (c)` | 整型/枚举/类（按语境隐式转换），再整型提升 | case 是调整后类型的转换后常量表达式，不得重复；最多一个 default；从条件到 case 视为跳转，不得绕过非 vacuous 初始化 |
