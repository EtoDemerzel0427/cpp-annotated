---
title: nodiscard 属性
summary: nodiscard 可标在函数、lambda、类/枚举类型和构造函数上；"nodiscard 调用"被作为潜在求值的弃值表达式时应当警告；可带理由字符串；转换为 void 可显式丢弃；返回引用的函数不会因返回类型而成为 nodiscard 调用
status: done
since: c++17
papers: P0189R1, P1301R4, P1771R1, P0068R0, P2173R1, P0600R1
related: dcl.attr.grammar, expr.prop, expr.context, expr.call, expr.type.conv, expr.static.cast, expr.cast, cpp.cond
tags: 属性, 诊断, nodiscard
updated: 2026-10-17
---

`[[nodiscard]]` 用来表达"**忽略这个结果几乎肯定是 bug**"：没有检查的错误码、获取后立刻被销毁的锁、`v.empty()` 被误以为是 `v.clear()`……它是纯粹的**诊断**属性：标准只规定什么情况下"鼓励"实现给出警告，对程序语义没有任何影响（[[dcl.attr.grammar#8]] 的可忽略性）。

本节的规范性内容不多，难点在于精确理解**什么算一次"nodiscard 调用"**以及**什么算"丢弃"**。

## 用在哪里，带什么参数（¶1）

¶1：`nodiscard` 可以用于：

- **函数**（包括构造函数，C++20，[[P1771R1]]）；
- **lambda 的调用运算符**（C++23 起 lambda 可以带属性，[[P2173R1]]）；
- **类或枚举的声明**。

可以带一个参数 `( unevaluated-string )`（C++20，[[P1301R4]]），作为警告中给出的理由。

```cpp title="nodiscard-where.cpp" ok
[[nodiscard]] int compute();                              // 函数
[[nodiscard("check the error code")]] int open_file();    // 带理由
struct [[nodiscard]] Error { int code; };                 // 类
enum class [[nodiscard]] Errc { ok, bad };                // 枚举

struct Lock {
    [[nodiscard]] explicit Lock(int fd);                  // 构造函数
    Lock();                                               // 这个不是
};

auto l = [] [[nodiscard]] () { return 1; };               // lambda 调用运算符

int main() {}
```

## 重声明（¶2）

¶2：没有 `nodiscard` 的名字或实体可以在之后的重声明中加上它，反之亦然。注 1：一旦被标记，后来的重声明**不会去掉**这个标记。不同形式（有无理由、理由不同）的重声明都允许。

```cpp title="nodiscard-redecl.cpp" ok
int f();
[[nodiscard]] int f();    // 从此 f 是 nodiscard 的
int f();                  // 不会去掉标记
[[nodiscard("other reason")]] int f();   // 允许不同的理由

int main() {}
```

这与 `[[noreturn]]` 必须出现在第一次声明中形成对比：`noreturn` 影响代码生成，必须在第一次调用前就知道；`nodiscard` 只影响诊断，晚一点知道也无妨。

## nodiscard 类型与 nodiscard 调用（¶3）

¶3 定义两个术语：

[[g:nodiscard-type|nodiscard 类型]]（nodiscard type）：在某个**可达**声明中被标记为 `nodiscard` 的类或枚举类型（可以带 cv 限定）。

[[g:nodiscard-call|nodiscard 调用]]（nodiscard call）是以下之一：

- ¶3.1：一个**函数调用表达式**（[[expr.call]]），它调用的函数在某个可达声明中被标记 `nodiscard`，**或者**其返回类型是 nodiscard 类型；
- ¶3.2：一个**显式类型转换**（[[expr.type.conv]]、[[expr.static.cast]]、[[expr.cast]]），它通过某个被标记 `nodiscard` 的**构造函数**构造对象，**或者**初始化一个 nodiscard 类型的对象。

几个精确之处：

1. **返回类型必须恰好是** nodiscard 类型（可带 cv）——返回 `Error&`、`Error*`、`std::optional<Error>` 都**不是** nodiscard 调用（除非函数本身被标记）。
2. 判断依据是被调用的**函数**：通过函数指针调用时，编译器不知道指向的是哪个函数，只能看返回类型。
3. 构造函数的情况只覆盖**显式类型转换**——`Lock(1)`、`Lock{1}`、`static_cast<Lock>(1)`。声明一个变量 `Lock lk(1);` 不是表达式，谈不上丢弃。

## 什么时候应当警告（¶4）

¶4 推荐做法：

!!! std
    Appearance of a nodiscard call as a potentially evaluated discarded-value expression of non-void type is discouraged unless explicitly cast to `void`.

    nodiscard 调用作为**潜在求值**的、**非 void 类型**的**弃值表达式**出现是不被鼓励的，除非显式转换为 `void`。

实现应当在这种情况下警告；如果实现做不到，`__has_cpp_attribute(nodiscard)` 应为 0。注 2：通常是因为丢弃 nodiscard 调用的结果会有出人意料的后果。理由字符串应当出现在警告信息中。

逐一拆解条件：

- **弃值表达式**（discarded-value expression，[[expr.context]]）：表达式语句 `f();`、逗号运算符的左操作数、`for` 的 *init-statement* 和递增表达式、转换为 `void` 的操作数……
- **潜在求值**：`sizeof(f())`、`decltype(f())` 中的 `f()` 不是潜在求值的，不警告。
- **非 void 类型**：结果类型为 `void` 时没有东西可丢。
- **除非显式转换为 void**：`(void)f();`、`static_cast<void>(f());` 是公认的"我知道我在丢弃"写法。

标准例 1（补全后可编译）：

```cpp title="nodiscard-example.cpp" ok
struct [[nodiscard]] my_scopeguard { };
struct my_unique {
    my_unique() = default;                      // 不获取资源
    [[nodiscard]] my_unique(int fd) { (void)fd; }   // 获取资源
    ~my_unique() noexcept { }                   // 释放资源（如果有）
};
struct [[nodiscard]] error_info { };
error_info enable_missile_safety_mode() { return {}; }
void launch_missiles() {}

void test_missiles() {
    my_scopeguard();                 // 鼓励警告：nodiscard 类型的临时对象被丢弃
    (void)my_scopeguard(),           // 不鼓励警告：转换为 void
        launch_missiles();           // 逗号运算符，语句继续
    my_unique(42);                   // 鼓励警告：nodiscard 构造函数
    my_unique();                     // 不鼓励警告：这个构造函数不是 nodiscard
    enable_missile_safety_mode();    // 鼓励警告：返回 nodiscard 类型
    launch_missiles();
}

error_info& foo() { static error_info e; return e; }
void f() { foo(); }                  // 不鼓励警告：返回引用，不是 nodiscard 调用

int main() { test_missiles(); f(); }
```

`my_unique(42);` 是一个经典 bug：本意是 `my_unique u(42);`，结果只构造了一个立刻被销毁的临时对象，资源获取又释放。锁守卫 `std::lock_guard<std::mutex>(m);` 是同一类错误——事实上 `std::lock_guard<std::mutex>(m);` 更糟，它会被解析为**声明**一个名为 `m` 的变量（[[dcl.ambig.res]]），而 `std::lock_guard<std::mutex>{m};` 才是临时对象。

更多边界：

```cpp title="nodiscard-edges.cpp" ok
#include <tuple>

[[nodiscard]] int f();
enum class [[nodiscard]] Errc { ok, bad };
Errc op();

void t() {
    f();                          // 警告
    op();                         // 警告：返回 nodiscard 枚举类型
    (void)f();                    // 不警告
    static_cast<void>(f());       // 不警告
    std::ignore = f();            // 不警告：结果被使用了（赋值给 std::ignore）
    int (*fp)() = f;
    fp();                         // 不警告：通过指针调用，不知道是哪个函数，返回类型 int 不是 nodiscard 类型
    (void)sizeof(f());            // 不警告：不是潜在求值
    f(), 1;                       // 警告：逗号左操作数是弃值表达式
    for (f();;) break;            // 警告：init-statement 中的弃值表达式
}

int main() {}
```

`std::ignore = f();` 是 C++26 中被正式认可（`std::ignore` 的赋值语义被规范化）的"有意丢弃"写法，比 `(void)` 更显眼、更容易搜索。

## 用法建议与标准库

`nodiscard` 最适合：

- 返回**错误码**或**状态**的函数——但更好的做法是把错误类型本身标为 nodiscard（`struct [[nodiscard]] Error`），一次标记，所有返回它的函数自动生效；
- **纯函数**（无副作用，只为返回值而调用）：`empty()`、`size()`、`std::launder`、`operator new`；
- 获取资源的**构造函数**和**工厂函数**：`std::make_unique`、`std::allocator::allocate`（丢弃就是泄漏）；
- 返回新对象而不修改原对象的函数：比如 `string.trim()` 风格的接口，用户很容易误以为它就地修改。

C++20 的标准库规范开始在 `operator new`、`allocate`、容器的 `empty()`、`std::launder` 等处标注 `[[nodiscard]]`（[[P0600R1]]）。三大标准库实现都远比标准要求更积极地使用它（libc++ 的 `_LIBCPP_NODISCARD`、MSVC STL 的 `_NODISCARD`）。

## 实现视角

!!! impl "警告类别"
    - **Clang**：调用 nodiscard 函数被丢弃时报 `-Wunused-result`（"ignoring return value of function declared with 'nodiscard' attribute"）；返回 nodiscard 类型、nodiscard 构造函数的临时对象被丢弃时报 `-Wunused-value`；理由字符串附在信息末尾。两者默认开启。
    - **GCC** 统一用 `-Wunused-result`，默认开启。GCC 的 `__attribute__((warn_unused_result))` 是 nodiscard 的前身，但它在 GCC 中**不能**被 `(void)` 压制——这是标准属性特意做出的改进。
    - **MSVC** 报 C4834（丢弃 nodiscard 函数的返回值）等警告。
    - 警告是推荐做法而非要求：在模板中、宏展开中，实现可能为了减少噪音而不警告。

## 历史与演进

!!! history "C++17 → C++26"
    - **C++17**：引入 `[[nodiscard]]`（[[P0189R1]]，源于 [[P0068R0]] 对 `[[unused]]`、`[[nodiscard]]`、`[[fallthrough]]` 的提议）。只能用于函数和类/枚举，无参数。
    - **C++20**：可带理由字符串（[[P1301R4]]）；可用于构造函数（[[P1771R1]]）；标准库规范开始标注（[[P0600R1]]）。
    - **C++23**：lambda 调用运算符可带属性（[[P2173R1]]）。
    - **C++26**：属性参数中的字符串改为不求值字符串（[[P2361R6]]）；规范改写为"nodiscard 类型 / nodiscard 调用"的形式，并加入"不能警告则 `__has_cpp_attribute` 应为 0"的推荐做法。

## 陷阱

!!! pitfall "返回引用的函数不受类型上的 nodiscard 保护"
    `struct [[nodiscard]] E {}; E& get();` —— `get();` 不会触发警告。若需要，给函数本身加 `[[nodiscard]]`。

!!! pitfall "`std::lock_guard<std::mutex>(m);` 是声明不是临时对象"
    nodiscard 构造函数救不了它：这一行声明了一个名为 `m` 的局部变量（遮蔽了外面的 mutex），还要求 `lock_guard` 可默认构造——通常会编译失败，但类似的类型可能静默通过。用花括号或给变量起名。

!!! pitfall "nodiscard 不是语义约束"
    它不会让程序非良构，也不保证一定有警告。需要强制检查结果的，用类型系统（例如析构时检查"是否被检查过"的结果类型）或契约。

## 思考题

!!! question "思考题"
    对下面每一行，按 ¶3–¶4 判断是否"鼓励警告"：

    ```cpp
    struct [[nodiscard]] R {};
    R make();
    const R cmake();
    R* pmake();
    [[nodiscard]] void v();
    void t() {
        make();
        cmake();
        pmake();
        v();
        R{};
        R r = make();
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `make();`：返回 nodiscard 类型 `R`，是 nodiscard 调用，弃值 → 鼓励警告。
- `cmake();`：返回 `const R`，nodiscard 类型可以带 cv → 鼓励警告。
- `pmake();`：返回 `R*`，不是 nodiscard 类型，函数也没标记 → 不鼓励。
- `v();`：函数被标记，但表达式类型是 `void`，¶4 只针对非 void 类型 → 不鼓励（实现通常会对 `void` 函数上的 `[[nodiscard]]` 本身给出警告）。
- `R{};`：显式类型转换初始化一个 nodiscard 类型的对象（¶3.2）→ 鼓励警告。
- `R r = make();`：结果被用于初始化，不是弃值表达式 → 不鼓励。
</details>

## 小结

!!! summary "要点"
    - 用于函数、lambda、构造函数、类、枚举；可带理由字符串；可以后来加上，不能后来去掉。
    - nodiscard 调用 = 调用被标记的函数，或返回类型恰好是 nodiscard 类型，或通过 nodiscard 构造函数 / nodiscard 类型的显式类型转换。
    - 作为潜在求值、非 void 的弃值表达式时鼓励警告；`(void)` 或 `std::ignore =` 可显式丢弃。
    - 返回引用、指针的函数不因类型而成为 nodiscard 调用；函数指针调用只看返回类型。
