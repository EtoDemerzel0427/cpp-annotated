---
title: 关键字
summary: 82 个保留为关键字的拼写（C++26 新增 contract_assert）、模块指令的三个占位关键字、属性记号中的例外，以及同样不能用作名字的 and、or 等单词形式的运算符。
status: done
related: lex.name, lex.digraph, dcl.attr.grammar, cpp.replace.general, cpp.import
tags: 关键字, 词法
updated: 2026-10-19
---

!!! tldr
    - 表 5 列出的 82 个拼写在阶段 6 之后一律是关键字，不能用作任何名字；唯一的例外是属性记号，如 `[[gnu::const]]` 中的 `const`。
    - 预处理阶段还没有关键字，所以 `#if new` 里的 `new` 只是一个值为 0 的标识符。
    - 关键字不能定义成宏，`#define private public` 是非良构的。
    - `override`、`final`、`pre`、`post` 不是关键字，是特殊含义标识符；`and`、`or` 等也不是关键字，是运算符记号，但同样不能用作名字。

## 关键字从哪个阶段开始存在

```cpp run title="if-keyword.cpp" ok
#if int == 0 && new == 0     // 预处理时 int、new 只是标识符，值为 0
int ok = 1;
#endif
int main() { return ok - 1; }
```

在阶段 3 到 5，关键字和标识符都是标识符预处理记号；到阶段 6 转换成记号时，表 5 中的拼写才成为[[g:keyword|关键字]]（keyword，[[lex.phases]]）。所以 `#if` 里的 `int`、`new` 和其他标识符一样替换成 0。

[[lex.key]] 的文法是：

```
keyword:
    any identifier listed in Table 5
    import-keyword
    module-keyword
    export-keyword
```

后三个是预处理器处理 `import`、`module` 指令时产生的占位记号，没有拼写（[[lex.pptoken#4]]、[[cpp.import]]、[[cpp.module]]）。有了它们，语法能区分作为模块指令开头的 `import` 和名叫 `import` 的普通标识符。`export` 在表 5 里也是普通关键字，*export-keyword* 则专指模块指令开头的那个 `export`。

## 表 5 中的关键字（¶1）

¶1 表 5 中的标识符保留作关键字，即在阶段 6 和 7 中无条件地当作关键字，只在属性记号（*attribute-token*）中除外。注 1：`register` 目前没有用途，保留供将来使用。

当前草案共有 82 个关键字：

```
alignas      alignof      asm          auto         bool         break
case         catch        char         char8_t      char16_t     char32_t
class        co_await     co_return    co_yield     concept      const
const_cast   consteval    constexpr    constinit    continue     contract_assert
decltype     default      delete       do           double       dynamic_cast
else         enum         explicit     export       extern       false
float        for          friend       goto         if           inline
int          long         mutable      namespace    new          noexcept
nullptr      operator     private      protected    public       register
reinterpret_cast          requires     return       short        signed
sizeof       static       static_assert             static_cast  struct
switch       template     this         thread_local throw        true
try          typedef      typeid       typename     union        unsigned
using        virtual      void         volatile     wchar_t      while
```

下面这些不在表中，却常被当作关键字：

| 拼写 | 实际身份 |
|---|---|
| `override`、`final`、`import`、`module`、`pre`、`post` | 特殊含义标识符（[[lex.name#2]]） |
| `and`、`or`、`not`、`bitand`、`compl` 等 | 替代记号，属于运算符和标点（[[lex.digraph]]、¶3） |
| `main` | 普通标识符，有专门的规则（[[basic.start.main]]） |
| `std` | 普通标识符，受标准库的保留规则约束 |
| `size_t`、`nullptr_t`、`int8_t` | 标准库中的类型别名 |
| `restrict`、`_Bool`、`_Atomic`、`typeof` | C 的关键字，C++ 中没有 |
| `__restrict`、`__attribute__`、`__declspec` | 实现的扩展，用的是保留标识符（[[lex.name#4]]） |

### 关键字不能用作名字

无条件当作关键字，意味着即使在不会产生歧义的位置，关键字也不能用作名字：

```cpp title="keyword-as-name.cpp" error
struct S { int class; };      // error: class 是关键字
int contract_assert = 0;      // error（C++26）：contract_assert 是关键字
void f(int new);              // error
```

本机 Clang 23 还没有把 `contract_assert` 识别为关键字，第二行能通过编译，这是实现进度的问题。特殊含义标识符与此不同，它们在特定位置以外都是普通标识符。

### 例外：属性记号

属性记号中的关键字不当作关键字，例如 `gnu::const` 里的 `const`。[[dcl.attr.grammar]] 进一步规定，属性记号中符合标识符语法的关键字或替代记号都视为标识符。

```cpp run title="attr-keyword.cpp" ok
[[gnu::const]] int square(int x);      // const 在这里是标识符
[[gnu::noreturn]] void die();
int main() {}
```

厂商属性的名字往往来自已有的编译器扩展，其中不少和关键字同名；而属性名所在的位置没有歧义，所以允许。

### `register`：没有用途但保留

C++11 弃用了 `register` 存储类说明符，C++17 把它删除，`register int x;` 从此非良构。但 `register` 仍在关键字表里，将来可以给它新的含义而不破坏现有代码。`auto`（C++11 改作类型推导）和 `export`（C++11 删除导出模板，C++20 用于模块）都走过这条路。

```cpp title="register.cpp" error
void f() {
  register int x = 0;   // error（C++17 起）：register 不再是存储类说明符
}
```

## 关键字不能定义成宏（¶2）

¶2 的注 2 说，关键字不能用作宏名（[[cpp.replace.general]]）。

```cpp title="keyword-macro.cpp" error
#define private public    // error: 宏名与关键字相同
class A { private: int secret = 1; };
int peek(A& a) { return a.secret; }
```

规范依据是 [[cpp.replace.general#9]]：翻译单元不得 `#define` 或 `#undef` 与关键字、特殊含义标识符、标准属性名拼写相同的宏名，只有 `likely` 和 `unlikely` 可以定义成函数式宏。C++23 中这条规则写在标准库条款 [[macro.names]] 里，当前草案把它移到了预处理条款，成为一条普通的、违反即须诊断的规则。本机 Clang 23 只在 `-pedantic` 下给出 `-Wkeyword-macro` 警告，默认模式下不诊断，照样编译通过。

`#define private public` 曾是测试代码访问私有成员的常见手法。它的问题不只是绕过访问控制：这个翻译单元看到的类定义与其他翻译单元的记号序列不同，违反 ODR（[[basic.def.odr]]）；C++23 之前，不同访问控制的成员在内存中的先后顺序没有规定，把 `private` 换成 `public` 还可能真的改变类的布局。更一般地，重定义关键字会让标准库头文件的行为无法预测。

## 单词形式的运算符也保留（¶3）

¶3 表 6 中某些运算符和标点的替代表示（[[lex.digraph]]）同样保留，不能另作他用：

```
and     and_eq    bitand    bitor    compl    not
not_eq  or        or_eq     xor      xor_eq
```

它们不在表 5 里，不是关键字，而是运算符或标点记号，但效果上和关键字一样，不能用作名字。

## 历史与演进

!!! history
    | 版本 | 新增关键字 |
    |---|---|
    | C++98 | 基础集合，包括旧含义的 `export`、`register`、`auto` |
    | C++11 | `alignas` `alignof` `char16_t` `char32_t` `constexpr` `decltype` `noexcept` `nullptr` `static_assert` `thread_local`（[[diff.cpp03.lex]]） |
    | C++20 | `char8_t` `concept` `consteval` `constinit` `co_await` `co_yield` `co_return` `requires`（[[diff.cpp17.lex]]） |
    | C++26 | `contract_assert`（[[diff.cpp23.lex]]，契约见 [[P2900R14]]） |

    改变含义而没有删除的有：`auto`（C++11 从存储类说明符改为类型推导）、`export`（C++11 删除导出模板，C++20 用于模块）、`register`（C++17 删除存储类说明符，保留拼写）。

    断言语句不叫 `assert`，是因为 `assert` 是 `<cassert>` 里的宏，不可能成为关键字。

## 常见误解

!!! pitfall "C 代码里的变量名"
    C 代码常用 `new`、`class`、`template`、`this`、`delete`、`private` 作变量名或结构体成员名，这些代码按 C++ 编译都会失败（[[diff.lex]]）。要在 C++ 中使用的 C 头文件需要避开这些名字。

!!! pitfall "`override` 是关键字，`and` 是普通名字"
    正好相反。`int override = 0;` 完全合法，`struct S { int and; };` 非良构。

## 思考题

!!! question "思考题"
    C++26 的契约为什么把断言语句做成关键字 `contract_assert`，而把前置、后置条件做成特殊含义标识符 `pre`、`post`？

<details markdown="1">
<summary>答案</summary>

`pre` 和 `post` 出现在函数声明符之后，例如 `int f(int x) pre(x > 0);`。这个位置原本只能出现 `override`、`final`、`noexcept`、`requires`、`= 0`、`{` 等少数几种东西，靠上下文就能识别，所以可以做成特殊含义标识符，不破坏名叫 `pre`、`post` 的现有变量。

断言语句出现在语句的位置，而那里 `name(expr);` 本来就是一个合法的函数调用语句，靠上下文无法区分，只能用关键字。为了不和现有代码以及 `<cassert>` 的 `assert` 宏冲突，选了一个不太可能被用作名字的拼写 `contract_assert`。
</details>
