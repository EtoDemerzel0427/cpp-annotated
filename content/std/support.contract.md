---
title: 契约违反处理支持
summary: 头文件 <contracts> 提供契约违反处理函数要用的类型：描述一次违反的 contract_violation、三个枚举，以及转调默认处理函数的 invoke_default_contract_violation_handler。
status: done
covers: *
since: c++26
papers: P2900
related: basic.contract, basic.contract.eval, basic.contract.handler, dcl.contract.func, stmt.contract.assert, support.srcloc, dcl.fct.def.replace
tags: 标准库, 契约, C++26
updated: 2026-10-19
---

!!! tldr
    - 契约断言被违反时，实现创建一个 `std::contracts::contract_violation` 对象，把它交给契约违反处理函数 `::handle_contract_violation`。
    - 这个对象只能由实现创建，不能复制；处理函数通过六个成员函数读出断言种类、求值语义、检测方式、位置和谓词文本。
    - 在标准的四种求值语义里，只有 observe 和 enforce 会调用处理函数，而且只在运行时调用。
    - 自定义处理函数可以用 `invoke_default_contract_violation_handler` 再调用实现的默认处理函数。
    - 整个 `<contracts>` 都是 freestanding 的，名字都在 `std::contracts` 里。

C++26 的**契约断言**（contract assertion）是核心语言特性：函数声明上的 `pre`、`post` 和语句 `contract_assert`，规则见 [[basic.contract]]。每次求值一个契约断言，都采用四种**求值语义**之一：ignore 不检查；observe、enforce、quick-enforce 检查谓词，其中 enforce 和 quick-enforce 在违反时终止程序（[[basic.contract.eval]]）。

断言被违反、而语义是 observe 或 enforce 时，实现调用**契约违反处理函数**，即全局函数 `::handle_contract_violation`（[[basic.contract.handler]]）。本节定义的是传给它的那个参数的类型。

!!! warning "编译器支持"
    截至写作时，本机 Clang 23 + libc++ 还不支持契约：`pre(...)` 语法报错，也没有 `<contracts>` 头文件。本页的代码按标准条文书写，没有经过编译验证。

## 一个自定义处理函数

```cpp
#include <contracts>
#include <cstdio>
namespace sc = std::contracts;

// 只有在实现允许替换处理函数时才能这样写
void handle_contract_violation(const sc::contract_violation& v) {
  std::fprintf(stderr, "%s:%u: %s 违反: %s\n",
               v.location().file_name(),
               static_cast<unsigned>(v.location().line()),
               v.kind() == sc::assertion_kind::pre ? "前置条件" : "断言",
               v.comment());
  if (v.detection_mode() == sc::detection_mode::evaluation_exception)
    std::fputs("  谓词抛出了异常\n", stderr);
}
```

处理函数接收一个 `const contract_violation&`，从中读出这次违反的全部信息。它返回之后会发生什么，取决于求值语义：observe 下程序从断言处继续执行，enforce 下程序被终止。enforce 下处理函数也可以抛出异常，以此避免终止（[[basic.contract.eval#16]] 的注）。

处理函数能否被替换由实现定义（[[basic.contract.handler#3]]），可以用特性测试宏 `__cpp_lib_replaceable_contract_violation_handler` 检查（[[support.limits]]）。实现不允许替换时，写出上面这个定义的程序是 IFNDR，也就是非良构但编译器不必报告。

## `<contracts>` 的内容 [contracts.syn]

¶1 头文件 `<contracts>` 定义用于报告契约违反信息的类型。整个头文件是 freestanding 的，也就是说独立实现（没有操作系统支持的实现）同样要提供它。

```cpp
namespace std::contracts {
  enum class assertion_kind : unspecified {
    pre = 1, post = 2, assert = 3 };
  enum class evaluation_semantic : unspecified {
    ignore = 1, observe = 2, enforce = 3, quick_enforce = 4 };
  enum class detection_mode : unspecified {
    predicate_false = 1, evaluation_exception = 2 };

  class contract_violation {
    // 没有用户可访问的构造函数
  public:
    contract_violation(const contract_violation&) = delete;
    contract_violation& operator=(const contract_violation&) = delete;
    /* see below */ ~contract_violation();

    const char* comment() const noexcept;
    contracts::detection_mode detection_mode() const noexcept;
    bool is_terminating() const noexcept;
    assertion_kind kind() const noexcept;
    source_location location() const noexcept;
    evaluation_semantic semantic() const noexcept;
  };

  void invoke_default_contract_violation_handler(const contract_violation&);
}
```

## 三个枚举 [support.contract.enum]

三个枚举都是作用域枚举，底层类型未指定，枚举项的值从 1 开始显式给出。

¶2 `assertion_kind` 对应契约断言的三种写法（[[basic.contract.general]]）：

| 枚举项 | 含义 |
|---|---|
| `pre` | 前置条件断言（[[dcl.contract.func]]） |
| `post` | 后置条件断言 |
| `assert` | 断言语句 `contract_assert(...)`（[[stmt.contract.assert]]） |

¶3 `evaluation_semantic` 对应四种求值语义：

| 枚举项 | 违反时 | 调用处理函数 |
|---|---|---|
| `ignore` | 不检查，不会发现违反 | 否 |
| `observe` | 调用处理函数，返回后继续执行 | 是 |
| `enforce` | 调用处理函数，返回后终止程序 | 是 |
| `quick_enforce` | 直接终止程序 | 否 |

所以按标准语义，处理函数里 `semantic()` 只会是 `observe` 或 `enforce`。常量求值中的违反也不调用处理函数，而是变成编译期诊断（[[basic.contract.eval#8]]）。另外两个枚举项存在，是为了完整描述语义，也给实现扩展留出余地。

¶4 `detection_mode` 说明违反是怎样被发现的：

| 枚举项 | 含义 |
|---|---|
| `predicate_false` | 谓词求值为 `false`，或者如果求值将会得到 `false` |
| `evaluation_exception` | 谓词求值时抛出了异常，没有在谓词内部被捕获 |

“或者将会得到 `false`”这半句来自 [[basic.contract.eval#5]]：检查型语义下，谓词是否真的被求值是未指定的，实现可以改用一个结果相同、没有副作用的求值来判断。

谓词抛出异常时，处理函数在这个异常的一个活动的隐式 handler 中被调用（[[basic.contract.eval#12]]）。所以在处理函数里，这个异常就是当前正在处理的异常，可以用 `std::current_exception()` 取得，也可以用 `throw;` 重新抛出。

¶1 是一条建议：实现如果提供额外的枚举项，它们的值应当不小于 1000，以免与标准将来新增的枚举项冲突。

## `contract_violation` [support.contract.violation]

¶1 `contract_violation` 的对象表示一次契约违反：某个契约断言以某种求值语义求值时，检测到了违反。这类对象只能由实现创建，程序没有可用的构造函数，复制构造和复制赋值都被删除。处理函数只能通过引用访问它，对象的生命期持续到处理函数返回（[[basic.contract.eval#11]]）。

析构函数是否为虚函数由实现定义。实现因此可以从它派生出带有额外信息的内部类型。

六个成员函数都是 `const noexcept` 的：

| 函数 | 返回值 |
|---|---|
| `kind()`（¶6） | 被违反断言的写法 |
| `semantic()`（¶9） | 这次求值采用的语义 |
| `is_terminating()`（¶5） | 语义是否为终止型（enforce、quick-enforce） |
| `detection_mode()`（¶4） | 违反是怎样被发现的 |
| `comment()`（¶2–¶3） | 由实现定义的字符串，使用普通字面量编码 |
| `location()`（¶7–¶8） | 由实现定义的 `source_location` |

¶5 有了 `is_terminating()`，处理函数不必枚举所有语义（包括实现扩展的语义），就能知道返回之后程序会不会被终止。

¶2 `comment()` 返回一个以空字符结尾的多字节字符串。¶3 建议它包含被违反谓词的文本，或者在不想存储文本时为空串。注 1 说明这段文本可以截断、重新排版或概括，可以取预处理之前或之后的形式。这些都只是建议，实现为了减小二进制体积，完全可以一律返回空串，程序逻辑不要依赖它。

¶7 `location()` 的值也由实现定义。¶8 建议它要么是默认构造的 `source_location`，要么标识被违反的断言：

- ¶8.1 如果可能，前置条件违反应当返回函数调用处的位置；
- ¶8.2 否则返回契约断言本身的位置。

前置条件指向调用处，是因为违反前置条件是调用方的错误，日志应当指出谁传了错误的参数。如果可能这几个字说明这不是保证：通过函数指针或虚函数调用时，实现未必知道调用点。

## 转调默认处理函数 [support.contract.invoke]

```cpp
void invoke_default_contract_violation_handler(const contract_violation& v);
```

¶1 效果是以 `v` 为实参调用**默认契约违反处理函数**，即实现自带的处理函数（[[basic.contract.handler]]）。

需要这个函数，是因为没有任何标准库头文件声明默认处理函数（[[basic.contract.handler#1]] 注 1），而程序一旦替换了 `::handle_contract_violation`，就再也无法用名字调用原来的版本。有了它，自定义处理函数可以在默认行为之前或之后加上自己的处理，而不必整个重写：

```cpp
#include <contracts>
#include <cstdio>

void handle_contract_violation(const std::contracts::contract_violation& v) {
  if (v.kind() == std::contracts::assertion_kind::pre)
    std::fputs("[app] 调用方违反了前置条件\n", stderr);
  // 格式化输出、限速等工作交给默认处理函数
  std::contracts::invoke_default_contract_violation_handler(v);
}
```

[[basic.contract.handler#2]] 建议默认处理函数格式化输出违反信息，对重复发生的 observe 违反限速，然后正常返回。
