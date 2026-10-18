---
title: 契约违反处理支持
summary: <contracts> 头文件——assertion_kind / evaluation_semantic / detection_mode 三个枚举、只能由实现创建的 contract_violation 及其六个观察函数，以及在自定义处理函数中转调默认处理函数的 invoke_default_contract_violation_handler
status: done
covers: *
since: c++26
papers: P2900
related: basic.contract, basic.contract.eval, basic.contract.handler, dcl.contract.func, stmt.contract.assert, support.srcloc, dcl.fct.def.replace
tags: 标准库, 契约, C++26
updated: 2026-10-18
---

C++26 的契约断言（`pre`、`post`、`contract_assert`）是核心语言特性，规则在 [[basic.contract]]。当一个契约断言在**检查语义**（observe、enforce）下被判定违反时，实现会创建一个描述该违反的对象，并以它为实参调用**契约违反处理函数** `::handle_contract_violation`（[[basic.contract.handler]]）。本节定义的就是这个"描述违反的对象"的类型，以及配套的枚举。

¶1（[contracts.syn]）：`<contracts>` 定义用于报告契约违反信息（[[basic.contract.eval]]）的类型。整个头文件是 freestanding 的，所有名字位于嵌套命名空间 `std::contracts` 中。

```cpp
namespace std::contracts {
  enum class assertion_kind      : unspecified { pre = 1, post = 2, assert = 3 };
  enum class evaluation_semantic : unspecified { ignore = 1, observe = 2, enforce = 3, quick_enforce = 4 };
  enum class detection_mode      : unspecified { predicate_false = 1, evaluation_exception = 2 };

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

!!! warning "编译器支持"
    截至本文编写时，本机的 Clang 23 + libc++ 尚不支持契约断言（`pre(...)` 语法报错，也没有 `<contracts>` 头文件），因此本页的代码无法在本地验证，仅按标准条文书写。

## 三个枚举（[support.contract.enum]）

三个枚举都是**作用域枚举**，底层类型**未指明**，枚举项的值从 **1** 开始显式给出。

¶1 *推荐实践*：如果实现提供了**由实现定义的**额外枚举项，它们的值应当**不小于 1000**。这为实现扩展（例如额外的求值语义、额外的检测方式）预留了空间，也避免与标准将来新增的枚举项冲突。

### `assertion_kind`（¶2）

对应契约断言的语法形式（[[basic.contract.general]]）：

| 枚举项 | 含义 |
|---|---|
| `pre` | 前置条件断言（[[dcl.contract.func]]） |
| `post` | 后置条件断言 |
| `assert` | *assertion-statement*，即 `contract_assert(...)`（[[stmt.contract.assert]]） |

### `evaluation_semantic`（¶3）

对应契约断言可能采用的求值语义（[[basic.contract.eval]]）：

| 枚举项 | 含义 | 处理函数是否会被调用 |
|---|---|---|
| `ignore` | 不检查谓词 | 否 |
| `observe` | 检查；违反时调用处理函数，处理函数返回后**继续执行** | 是 |
| `enforce` | 检查；违反时调用处理函数，返回后**契约终止**程序 | 是 |
| `quick_enforce` | 检查；违反时**不调用**处理函数，直接契约终止 | 否 |

所以在标准语义下，处理函数通过 `semantic()` 只会看到 `observe` 或 `enforce`；看到 `ignore` 或 `quick_enforce` 只可能出现在实现扩展的情形中。

### `detection_mode`（¶4）

违反是如何被识别出来的：

| 枚举项 | 含义 |
|---|---|
| `predicate_false` | 谓词求值为 `false`，**或者"本会"求值为 `false`** |
| `evaluation_exception` | 谓词求值过程中出现了**未捕获的异常** |

"本会求值为 `false`"对应 [[basic.contract.eval#5]]：检查语义下谓词**是否真的被求值是未指明的**，实现可以用一个产生相同值但没有副作用的替代求值来判断（注 3）。`evaluation_exception` 的情形下，按 [[basic.contract.eval#12]]，处理函数在该异常的一个**活动的隐式 handler** 中被调用，于是那个异常是当前处理的异常，可以用 `std::current_exception()` 取得并检查或重抛（[[propagation]]）。

## `contract_violation`（[support.contract.violation]）

¶1：`contract_violation` 定义了这样一种对象的类型：表示在以某种求值语义对契约断言求值期间**检测到的一次契约违反**。

- **只能由实现创建**：没有用户可访问的构造函数，复制构造和复制赋值被删除。处理函数只能通过 `const contract_violation&` 接触它。
- **析构函数是否为虚是由实现定义的**（概要中的 *see below*）。这允许实现从 `contract_violation` 派生出携带额外信息的内部类型，并让用户通过 `dynamic_cast` 去探测——如果析构函数是虚的。

### 六个观察函数（¶2–¶9）

| 函数 | 返回 | 说明 |
|---|---|---|
| `comment()` | 由实现定义的 NTMBS，使用普通字面量编码（¶2） | 推荐实践（¶3）：包含被违反断言谓词的**文本表示**，或者在不希望存储文本时为空串。注 1：可以是截断、重新格式化或概括的形式，预处理之前或之后均可 |
| `detection_mode()` | 识别违反的方式（¶4） | 见上表 |
| `is_terminating()` | 求值语义是否为**终止语义**（¶5） | enforce 和 quick-enforce 是终止语义（[[basic.contract.eval]]） |
| `kind()` | 被违反断言的语法形式（¶6） | |
| `location()` | 值由实现定义的 `source_location`（¶7） | 推荐实践（¶8）：默认构造的 `source_location`，或标识被违反断言的值；¶8.1 若可能，**前置条件**违反应返回**函数调用处**的位置；¶8.2 否则返回契约断言本身的位置 |
| `semantic()` | 被违反断言求值时所用的求值语义（¶9） | |

几点值得推敲的地方：

- `comment()` 的内容完全由实现决定，¶3 只是推荐。实现可以为了缩小二进制体积而一律返回空字符串——不要让程序逻辑依赖它。
- ¶8.1 让前置条件违反指向**调用者**：违反前置条件是**调用方**的错误，日志里应当显示是谁传了坏参数，而不是被调函数的声明在哪里。这与 [[support.srcloc]] 中默认实参对应调用点的设计思想一致。但"若可能"二字说明这不是保证：间接调用（函数指针、虚函数）时，实现可能无法得知调用点。
- `is_terminating()` 让处理函数在不枚举所有语义（包括实现扩展的）的情况下知道"返回之后程序会不会被终止"。

## 转调默认处理函数（[support.contract.invoke]）

```cpp
void invoke_default_contract_violation_handler(const contract_violation& v);
```

¶1 *Effects*：以 `v` 为实参调用**默认契约违反处理函数**（[[basic.contract.handler]]）。

为什么需要这个函数？[[basic.contract.handler]] 注 1 说：**没有任何标准库头文件提供默认处理函数的声明**；而一旦程序替换了 `::handle_contract_violation`，默认版本就再也无法通过名字调用了（替换发生在程序启动之前，[[dcl.fct.def.replace]]）。这个函数提供了一个"后门"，让自定义处理函数可以**装饰**默认行为，而不是完全取代它：

```cpp
#include <contracts>
#include <cstdio>

// 仅当实现允许替换处理函数时有效（是否可替换由实现定义；
// 可用 __cpp_lib_replaceable_contract_violation_handler 检测，见 [version.syn]）
void handle_contract_violation(const std::contracts::contract_violation& v) {
    if (v.kind() == std::contracts::assertion_kind::pre)
        std::fputs("[app] precondition violated by caller\n", stderr);
    // 其余工作（格式化诊断、限速……）交给实现的默认处理函数
    std::contracts::invoke_default_contract_violation_handler(v);
}
```

（此例按标准条文书写，见上方关于编译器支持的说明。）

## 小结

!!! summary
    - `<contracts>` 全部 freestanding，名字位于 `std::contracts`。
    - 三个作用域枚举，值从 1 开始；实现扩展的枚举项建议 ≥ 1000。
    - 处理函数在标准语义下只会看到 `observe` 与 `enforce`；`quick_enforce` 不调用处理函数。
    - `contract_violation` 只能由实现创建、不可复制；析构函数是否为虚由实现定义。
    - `comment()` 与 `location()` 的值由实现定义；推荐前置条件违反报告调用点位置。
    - `invoke_default_contract_violation_handler` 让替换后的处理函数仍能调用默认处理函数。
