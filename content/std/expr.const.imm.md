---
title: 立即函数
summary: consteval 函数的每次调用都必须是常量表达式；立即函数语境、立即调用、立即升级（consteval 向上传播，C++23）与 if consteval
status: done
papers: P1073R3, P1938R3, P2564R3, P2216R3, P2996R13
related: dcl.constexpr, stmt.if, expr.const.const, expr.const.defns, meta.const.eval, topics/compile-time-programming
tags: 常量求值, consteval, if consteval
updated: 2026-10-17
---

`constexpr` 函数可以在编译期调用，`consteval` 函数只能在编译期调用。后者称为**立即函数**（immediate function）：对它的每一次调用（不在立即函数语境中的）都是一次**立即调用**（immediate invocation），必须是常量表达式，在翻译期就地求值，结果直接嵌入程序。立即函数本身不生成机器码，也不能取地址带到运行期。

本节的难点不在 `consteval` 本身，而在 C++23 引入的**立即升级**（immediate-escalating，[[P2564R3]]）：如果一个 constexpr 函数模板调用了 consteval 函数，而这个调用又不是常量，该模板实例就会自动变成立即函数。也就是说，consteval 会沿调用链向上传播。

## 为什么需要 consteval

C++20 引入 `consteval`（[[P1073R3]]）有三个动机：

1. 保证编译期求值。`constexpr` 不提供这个保证；如果函数的语义要求在编译期执行（例如校验格式字符串、计算哈希作为 `switch` 的标签），就需要一种手段让运行期调用成为编译错误。
2. 不生成代码。纯编译期的辅助函数（尤其是元编程中大量实例化的函数）不需要出现在目标文件中。
3. 为静态反射铺路。反射操作（`std::meta::*`）只在编译期有意义，C++26 的反射 API 全部是 consteval 的（[[P2996R13]]）。

最著名的用例是 `std::format` 的编译期格式串检查（C++20 通过 [[P2216R3]] 作为缺陷修复加入）。`std::basic_format_string` 的构造函数是 consteval 的，因此格式串在编译期解析：

```cpp error
#include <format>
#include <string>
std::string a = std::format("{} + {}", 1, 2);   // OK
std::string b = std::format("{:d}", "str");     // error: "d" 不适用于字符串，在编译期被发现
```

## 立即函数语境与立即调用（¶1）

如果一个潜在求值的表达式或转换满足下列条件之一，它就处于**立即函数语境**（immediate function context）：

- ¶1.1 它最内层的非块作用域是某个立即函数的形参作用域，即它在 consteval 函数（或已升级的立即函数）的函数体内；
- ¶1.2 它是某个显然常量求值的表达式或转换的子表达式（[[expr.const.defns#1]]），例如 constexpr 变量的初始化器、模板实参、`static_assert` 的条件；
- ¶1.3 它所在的语句位于 consteval if 语句的 *compound-statement* 之内（`if consteval { 这里 }`）。

对立即函数的潜在求值的调用（显式或隐式），如果不在立即函数语境中，就是**立即调用**。

为什么立即函数语境中的调用不算立即调用？因为语境本身已经保证会在编译期求值。consteval 函数内部调用另一个 consteval 函数时，实参可以是外层函数的形参（不是常量），只要外层被调用时整体是常量即可。检查推迟到最外层进行，consteval 函数因此可以互相组合：

```cpp
consteval int sq(int n) { return n * n; }
consteval int quad(int n) { return sq(sq(n)); }   // OK：sq(n) 在立即函数语境中，n 不必是常量

int x = sq(3);                        // 立即调用，3 是常量 → OK，x 静态初始化为 9
int rt = 3;
int y = sq(rt);                       // error: 立即调用不是常量表达式
constexpr int (*fp)(int) = sq;        // C++23：error；C++26：见下文"取地址"
```

¶1 最后一句规定：如果聚合初始化求值了一个含有立即升级表达式的默认成员初始化器，这次聚合初始化本身就是立即调用。

```cpp
consteval int id(int i) { return i; }
struct A { int x; int y = id(x); };   // id(x)：x 是成员，不是常量 → 立即升级表达式
constexpr int k = A(42).y;            // A(42) 是立即调用，整体求值得 y == 42 → OK
int rt = 1;
int bad = A{rt}.y;                    // error: 立即调用 A{rt} 不是常量表达式
```

!!! impl "Clang 的分歧"
    本站测试的 Clang 23 连 `constexpr int k = A(42).y;` 也拒绝。它把默认成员初始化器里的 `id(x)` 当作独立的立即调用求值（报告"implicit use of 'this' pointer is only allowed within the evaluation of a call to a 'constexpr' member function"），而没有按 ¶1 末句把整个聚合初始化当作立即调用。按标准，`k` 是合法的。

聚合没有可以升级的构造函数，所以标准把整个聚合初始化当作立即调用，默认成员初始化器里的 consteval 调用在这次初始化的完整求值中检查常量性。

## 立即升级表达式（¶2）

如果一个潜在求值的表达式或转换既不是最初就处在立即函数语境中，也不是某个立即调用的子表达式，并且满足下列条件之一，它就是**立即升级的**（immediate-escalating）：

- ¶2.1 它是一个立即常量表达式（[[expr.const.const#5]]：结果是立即函数或立即对象，或指向它们）；
- ¶2.2 它是一个不是常量表达式的立即调用。

两种情形的含义相同：这里有一个只能在编译期存在的东西，而它所在的上下文本身并不保证在编译期求值。

```cpp
consteval int id(int x) { return x; }
template <auto F> constexpr auto apply_to(int i) { return F(i); }
auto p = &apply_to<id>;   // error: F(i) 是不是常量表达式的立即调用（i 是形参）
                          //        → apply_to<id> 升级为立即函数 → 不能取地址
```

"最初"（initially）一词是为了避免循环定义：¶1.1 的立即函数语境取决于表达式是否在立即函数体内，而函数是否是立即函数又取决于它体内有没有立即升级表达式，所以判断时使用升级之前的状态。

## 立即升级函数（¶3）

以下函数是**立即升级函数**（immediate-escalating function）：

- ¶3.1 未声明 `consteval` 的 lambda 的函数调用运算符；
- ¶3.2 未声明 `consteval` 的、非用户提供的预置（defaulted）函数，例如隐式的默认构造函数、`= default` 的比较运算符；
- ¶3.3 由以 constexpr 说明符定义的模板化实体实例化而来的函数（预期析构函数除外），即 constexpr 函数模板的特化、类模板的 constexpr 成员函数。

核心规则是：

!!! std
    An immediate-escalating expression shall appear only in an immediate-escalating function.

    立即升级表达式只能出现在立即升级函数中。

换句话说，**普通（非模板）constexpr 函数不会升级**，在其中出现立即升级表达式就是 ill-formed：

```cpp
consteval int sq(int n) { return n * n; }

constexpr int cf(int n) { return sq(n); }            // error: cf 不是立即升级函数

template<class T>
constexpr int tf(T n) { return sq(n); }              // OK：tf<int> 升级为立即函数
int t1 = tf(4);                                      // OK：tf(4) 是立即调用，常量
int rt = 3;
int t2 = tf(rt);                                     // error: 立即调用 tf(rt) 不是常量

auto lam = [](int n) { return sq(n); };              // lambda 调用运算符升级
int l1 = lam(2);                                     // OK
```

为什么只有这三类函数会升级？它们的共同点是，程序员无法或不方便在声明处写 `consteval`：

- 模板：同一个模板的不同实例化，有的可能需要 consteval，有的不需要，这取决于模板实参（见下面的 `f<char>` 与 `f<int>`）；
- lambda：泛型 lambda 实际上就是模板；即使不是泛型的，在 lambda 上写 `consteval` 也很少见；
- 预置函数：编译器生成的构造函数和比较运算符没有地方写 consteval，但它们可能调用成员的 consteval 函数（例如默认成员初始化器里的 consteval 调用）。

普通 constexpr 函数则是程序员手写的单一实体。如果它需要调用 consteval 函数而调用又不是常量，程序员应当明确地把它写成 consteval，标准不代为决定。

## 立即函数（¶4）

**立即函数**是指：

- ¶4.1 用 `consteval` 声明的函数；或
- ¶4.2 一个立即升级函数 F，其函数体中含有一个立即升级表达式，且该表达式最内层的非块作用域是 F 的形参作用域。

注 1：用于初始化基类或成员子对象的默认成员初始化器视为构造函数函数体的一部分。所以：

```cpp ok
consteval int id(int i) { return i; }
struct Z {
    int a = 1;
    int b = id(a);     // 对隐式默认构造函数而言，这是函数体的一部分；id(a) 不是常量 → 升级
    Z() = default;     // 非用户提供的预置函数 → 立即升级函数 → 升级为立即函数
};
Z z;                   // Z() 是立即调用：求值得 a == 1、b == 1，是常量 → OK
int f() { Z lz; return lz.b; }   // 同理 OK：每次构造都在编译期完成，结果为常量
```

要求最内层的非块作用域是 F 的形参作用域，是为了排除嵌套 lambda：lambda 体内的立即升级表达式只让 lambda 的调用运算符升级，不会穿透到外层函数。

## 标准例子精读（¶5）

```cpp
consteval int id(int i) { return i; }
constexpr char id(char c) { return c; }

template<class T>
constexpr int f(T t) {
    return t + id(t);
}

auto a = &f<char>;      // OK：f<char> 调用的是 constexpr 的 id(char)，不升级
auto b = &f<int>;       // error: f<int> 调用 consteval id(int)，id(t) 不是常量 → f<int> 是立即函数
static_assert(f(3) == 6);   // OK：立即调用，常量

template<class T>
constexpr int g(T t) {      // g<int> 不是立即函数
    return t + id(42);      // id(42) 已经是常量表达式，不是立即升级表达式
}
```

同一个模板，`f<char>` 是普通 constexpr 函数，`f<int>` 却是立即函数。这就是升级只能发生在模板实例化上的原因。

```cpp
template<class T, class F>
constexpr bool is_not(T t, F f) { return not f(t); }

consteval bool is_even(int i) { return i % 2 == 0; }

static_assert(is_not(5, is_even));   // OK
```

`is_not(5, is_even)` 把 consteval 函数作为函数指针传给一个普通的泛型函数。分析如下：

- 实参 `is_even` 这个 *id-expression* 指代立即函数，是立即常量表达式（[[expr.const.const#5]]）；但它位于 `static_assert` 的条件中，是显然常量求值的，处于立即函数语境（¶1.2），所以不是立即升级表达式。
- 在 `is_not<int, bool(*)(int)>` 的函数体里，`f(t)` 是通过函数指针形参进行的调用，静态上并没有调用立即函数，`f` 也不指代立即函数。函数体里没有立即升级表达式，所以 `is_not` 的这个特化不升级，仍是普通 constexpr 函数。
- 整个 `is_not(5, is_even)` 在常量求值中执行，`is_even` 的地址只在这次求值内部传递，从未进入运行期。

由此可见，只要 consteval 函数的地址限制在常量求值之内，它就可以穿过任意普通的 constexpr 泛型代码。

```cpp
consteval int id(int i) { return i; }
int x = 0;

template<class T>
constexpr T h(T t = id(x)) {   // h<int> 不是立即函数：
    return t;                  // 默认实参在解析时不被求值
}

template<class T>
constexpr T hh() {             // hh<int> 是立即函数：
    return h<T>();             // 调用 h<int>() 时使用了默认实参 id(x)，
}                              // 它在 hh 的函数体中被求值，且不是常量

int i = hh<int>();             // error: hh<int>() 是立即调用，求值需读取 x → 不是常量
```

默认实参属于调用者：`id(x)` 在 `hh` 中的调用表达式 `h<T>()` 处求值（[[dcl.fct.default]]），所以升级的是 `hh<int>` 而不是 `h<int>`。

```cpp
consteval int id(int i) { return i; }
struct A {
    int x;
    int y = id(x);
};

template<class T>
constexpr int k(int) {     // k<int> 不是立即函数：
    return A(42).y;        // A(42) 是聚合初始化 → 立即调用（¶1 末句），
}                          // 且是常量表达式 → 不是立即升级表达式
```

!!! impl "Clang 的分歧"
    本站测试的 Clang 23 把 `k<int>` 视为立即函数（`&k<int>` 报 "cannot take address of immediate function"），诊断称对 `id` 的调用不是常量表达式。它单独求值默认成员初始化器里的 `id(x)`（此时 `this` 不可用），没有按 ¶1 末句把整个 `A(42)` 当作立即调用。按标准，`k<int>` 不是立即函数。

### 契约与常量初始化（¶5 末尾）{{c++26}}

```cpp
constexpr int l(int c) pre(c >= 2) {
    return (c % 2 == 0) ? c / 0 : c;
}

const int i0 = l(0);   // 动态初始化；契约违反或未定义行为
const int i1 = l(1);   // 静态初始化；值为 1，或在编译期报告契约违反
const int i2 = l(2);   // 动态初始化；未定义行为
const int i3 = l(3);   // 静态初始化；值为 3
```

这个例子展示了 [[expr.const.init#4]] 的规定（判断常量初始化时，契约断言按 ignore 语义处理）的效果：

- `l(1)`：忽略前置条件后，`c` 为奇数，返回 1，是常量表达式，所以 `i1` 是静态初始化。但实际的翻译期求值可以用 enforce 等语义检查契约，此时 `1 >= 2` 不成立，导致编译期诊断。
- `l(0)`：忽略契约后求值 `0 / 0`（UB），不是常量，所以是动态初始化；运行期要么契约违反（如果检查），要么 UB。
- `l(2)`：前置条件满足，`2 / 0` 不是常量，所以是动态初始化，运行期 UB。
- `l(3)`：一切正常，静态初始化为 3。

关键在于，**契约是否会失败不影响初始化是静态还是动态的**。否则，打开或关闭契约检查就可能改变全局变量的初始化顺序，这是不可接受的。（截至写作时，本站测试的 Clang 尚未支持 C++26 契约语法。）

## if consteval

`if consteval`（C++23，[[P1938R3]]，规则见 [[stmt.if#4]]–[[stmt.if#6]]）是与立即函数配套的语句：

```cpp
if consteval { /* 在显然常量求值中执行 */ }
else         { /* 否则执行 */ }

if !consteval { /* 运行期分支 */ }   // 等价于 if consteval {} else { ... }
```

它有两个关键性质：

1. 第一个子语句处于立即函数语境（¶1.3），所以可以用非常量实参调用 consteval 函数：这样的调用不是立即调用，自身不必是常量。
2. 两个分支都必须是复合语句（带花括号），并且是控制流受限语句（不能 `goto` 进去）。

这正是 `std::is_constant_evaluated()` 做不到的：

```cpp
#include <type_traits>
consteval int sq(int n) { return n * n; }

constexpr int bad(int n) {
    if (std::is_constant_evaluated()) {
        return sq(n);       // error: 这里不是立即函数语境，sq(n) 是立即调用，n 不是常量
    }
    return n * n;
}

constexpr int good(int n) {
    if consteval {
        return sq(n);       // OK：立即函数语境
    } else {
        return n * n;
    }
}
```

在 `bad` 中，编译器在定义处就检查 `sq(n)`：`if` 的普通条件不建立任何语境，所以 `sq(n)` 是立即调用，而 `n` 不是常量，程序 ill-formed。在 `good` 中，`if consteval` 的复合语句是立即函数语境，`sq(n)` 只是普通调用，在 `good` 被常量求值时随之求值。

另外，[[meta.const.eval#1]] 正是用 `if consteval` 来规定 `std::is_constant_evaluated()` 的：它等价于 `if consteval { return true; } else { return false; }`。

!!! pitfall "`if constexpr (std::is_constant_evaluated())` 永远为真"
    `if constexpr` 的条件是显然常量求值的，所以 `is_constant_evaluated()` 在那里总是 true，运行期分支被丢弃。Clang 用 `-Wconstant-evaluated` 警告这种写法。正确的写法是 `if consteval` 或 `if (std::is_constant_evaluated())`。

## 取立即函数的地址

在 C++20/23 中，指向立即函数的指针不能作为常量表达式的结果，只能在立即函数语境内部传递（作为 consteval 函数的实参或局部变量）。C++26 用 consteval-only 值与立即对象（[[expr.const.const#1]]）重新表述了这条规则：指向立即函数的指针可以存进 constexpr 变量或用作模板实参，但不能进入运行期对象，而且在运行期代码中提到这样的变量会构成立即升级表达式。

```cpp
consteval int plus1(int x) { return x + 1; }
auto a = plus1;                 // error: 运行期变量
constexpr auto b = plus1;       // C++26：OK；C++23：error
```

## 其他约束（[[dcl.constexpr]]）

- `consteval` 只能用于函数或函数模板的声明（[[dcl.constexpr#1]]）；consteval 函数隐式 `inline`，也是 constexpr 函数。
- 析构函数、分配函数和释放函数不能是 consteval 的（[[dcl.constexpr#2]]）。语言会隐式调用它们（离开作用域、`new`/`delete` 表达式），无法保证每次调用都在常量求值中。
- 一个函数的所有声明必须一致地带或不带 `consteval`。
- 虚函数：consteval 虚函数不能覆盖非 consteval 虚函数，反之亦然（[[class.virtual]]）。

## 实现视角

!!! impl "consteval 在编译器中"
    - 立即调用在语义分析阶段就被求值并替换为结果（Clang 在 `Sema` 中处理 `ConstantExpr` 节点），不会到达代码生成。所以 consteval 函数不产生符号，链接器看不到它们。
    - 立即升级要求编译器在实例化函数体时回溯：一旦发现立即升级表达式，就把当前实例标记为立即函数，并重新检查之前对它的引用（例如取地址）。Clang 实现 P2564 后，诊断里会附注 "'f<int>' is an immediate function because its body contains a call to a consteval function"。
    - 立即函数没有代码，所以调试器无法在其中设断点；编译期调试只能依靠 `static_assert` 和编译器诊断。

## 历史与演进

!!! history "consteval 的演进"
    - C++20（[[P1073R3]]）：引入 `consteval`。规则很简单：consteval 函数的调用必须是常量表达式，除非位于另一个 consteval 函数内。人们很快发现它与泛型代码严重冲突：`std::invoke(f, args...)`、`std::ranges::transform` 这类转发函数本身是 constexpr 模板，转发调用的实参又不是常量，因此无法转发 consteval 可调用对象。
    - C++23（[[P1938R3]]）：引入 `if consteval`，解决 `is_constant_evaluated()` 无法调用 consteval 函数的问题。
    - C++23（[[P2564R3]]，作为 DR）："consteval needs to propagate up"。它引入立即升级，constexpr 模板在必要时自动变为 consteval，泛型转发的问题随之解决。
    - C++26（[[P2996R13]]）：为配合反射，引入立即常量表达式、consteval-only 值和立即对象。

## 陷阱

!!! pitfall "升级会改变函数的性质"
    在 constexpr 函数模板的某处加一个 consteval 调用，可能让某些实例化悄悄变成立即函数，进而让远处的 `auto p = &tf<int>;` 或运行期调用 `tf(runtime_value)` 报错。错误信息出现在使用处，而不是修改处。

!!! pitfall "非模板 constexpr 函数不会升级"
    `constexpr int wrap(int n) { return sq(n); }` 直接 ill-formed，因为升级只适用于模板实例化、lambda 和预置函数。解决办法是把 wrap 写成 consteval，或者使用 `if consteval`。

## 思考题

!!! question "思考题 1"
    下面哪一行是错误的？为什么？

    ```cpp
    consteval int sq(int n) { return n * n; }
    auto l1 = [](int n) { return sq(n); };
    auto l2 = [](int n) consteval { return sq(n); };
    int a = l1(2);
    int b = l2(2);
    auto p1 = +l1;
    ```

<details markdown="1">
<summary>答案</summary>

`auto p1 = +l1;` 是错的。`l1` 的调用运算符是立即升级函数（¶3.1），体内的 `sq(n)` 不是常量，因此它升级为立即函数。`+l1` 把无捕获 lambda 转换为函数指针，得到的指针指向（调用运算符对应的）立即函数。在运行期变量的初始化器里，这是一个立即升级表达式，而命名空间作用域变量的初始化不在任何立即升级函数中，所以程序 ill-formed。`a`、`b` 都是以常量为实参的立即调用，合法。
</details>

!!! question "思考题 2"
    为什么 `std::is_constant_evaluated()` 本身不是 consteval 函数，而是 constexpr 函数？

<details markdown="1">
<summary>答案</summary>

如果它是 consteval 的，那么每次调用要么是立即调用，要么位于立即函数语境中，总在编译期求值，结果永远是 true，也就无法区分当前是否处于常量求值中。它必须是一个可以在运行期调用（返回 false）的 constexpr 函数；它的规格正是用 `if consteval` 写的（[[meta.const.eval#1]]）。
</details>

## 小结

| 概念 | 要点 | 段落 |
|---|---|---|
| 立即函数语境 | consteval 函数体内、显然常量求值的子表达式、`if consteval` 块内 | ¶1 |
| 立即调用 | 立即函数语境之外对立即函数的调用；必须是常量表达式 | ¶1 |
| 立即升级表达式 | 不在立即函数语境中的立即常量表达式，或非常量的立即调用 | ¶2 |
| 立即升级函数 | 非 consteval lambda 调用运算符、非用户提供的预置函数、constexpr 模板的实例化 | ¶3 |
| 立即函数 | consteval 函数，或含立即升级表达式的立即升级函数 | ¶4 |
| `if consteval` | 第一分支是立即函数语境；`is_constant_evaluated` 由它定义 | [[stmt.if#4]] |
