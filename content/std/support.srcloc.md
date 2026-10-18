---
title: 源码位置
summary: std::source_location——consteval 的 current() 如何借助默认实参在调用点求值，四个字段的取值规则（presumed 行号、由实现定义的列号、__func__ 式的函数名），以及默认成员初始化器与默认实参中的特殊约定
status: done
covers: *
papers: P1208R6
related: cpp.predefined, cpp.line, dcl.fct.default, class.mem.general, expr.const.imm, dcl.fct.def.general, expr.call
tags: 标准库, source_location, 日志, consteval
updated: 2026-10-18
---

C 时代的日志宏用 `__FILE__`、`__LINE__`、`__func__` 记录调用位置。它们的问题是：只能在**宏**里使用——如果写成普通函数 `void log(const char* msg, int line = __LINE__)`，`__LINE__` 在函数**声明处**展开，永远是声明那一行。C++20 的 `std::source_location`（[[P1208R6]]）用一个 **`consteval` 函数**加上**默认实参在调用点求值**的规则，解决了这个问题。

¶1（[source.location.syn]）：`<source_location>` 定义类 `source_location`，提供获取源码位置信息的手段。整个头文件是 freestanding 的。

## 类的形状（[support.srcloc.class.general]）

```cpp
struct source_location {
  static consteval source_location current() noexcept;
  constexpr source_location() noexcept;
  constexpr uint_least32_t line() const noexcept;
  constexpr uint_least32_t column() const noexcept;
  constexpr const char* file_name() const noexcept;
  constexpr const char* function_name() const noexcept;
private:
  uint_least32_t line_, column_;        // 仅用于说明
  const char* file_name_;               // 仅用于说明
  const char* function_name_;           // 仅用于说明
};
```

- ¶1：`source_location` 满足 `semiregular`（可默认构造、可复制）；`is_nothrow_swappable_v<source_location>` 为 `true`。注 1：设计意图是**体积小、复制高效**；复制/移动操作是否**平凡**是未指明的。
- ¶2：`file_name_` 和 `function_name_` 总是指向一个 NTBS——**永远不是空指针**，可以放心地传给 `printf("%s")`。
- ¶3：复制/移动之后，新对象的四个字段与原对象（操作前的状态）相同——对字符串字段用 `strcmp` 比较内容，不要求指针相同。

!!! impl "libc++ 只存一个指针"
    "仅用于说明"的四个成员只是规格的描述手段，实现不必照搬。libc++ 的 `source_location` 只有一个成员：指向编译器生成的静态 `__impl` 结构（含文件名、函数名、行、列）的指针，`sizeof(std::source_location) == 8`（64 位平台）。这个静态结构由 Clang 的内建函数 `__builtin_source_location()` 产生，结构的名字和字段名（`__impl`、`_M_file_name`……）是**硬编码在编译器中的**——这是库与编译器之间一个少见的直接耦合。

## `current()`：在哪里求值？（[support.srcloc.cons] ¶1–¶3）

`current()` 是 `static consteval` 的。`consteval` 意味着每次调用都必须是**立即调用**（[[g:immediate-invocation]]），在编译期求值（[[expr.const.imm]]）。¶1 区分了两种调用方式：

¶1.1：当它被一个"后缀表达式是（可带括号的）指名 `current` 的 *id-expression*"的函数调用所调用时——也就是普通的 `std::source_location::current()` 写法——返回一个具有**由实现定义的值**的 `source_location`。该值**应当**像 `__LINE__`、`__FILE__` 一样受 `#line`（[[cpp.line]]）影响。各字段的值：

| 字段 | 值 |
|---|---|
| `line_` | **预设行号**（presumed line number，[[cpp.predefined]]），从 1 开始；行号未知时鼓励用 0 |
| `column_` | 由实现定义的、表示距 `line_` 所在行开头某种偏移的值，从 1 开始；未知时鼓励用 0 |
| `file_name_` | 当前源文件的**预设名字**（[[cpp.predefined]]），NTBS |
| `function_name_` | 当前函数的名字，"如 `__func__`"（[[dcl.fct.def.general]]）；不在函数中则为空字符串 |

¶1.2：以其他方式调用时，返回**有效但未指明**的值。这一条是兜底条款：`consteval` 函数的地址不能逃逸到运行期，而且按 [[namespace.std]]，对标准库成员函数取地址本身就是未指明的（`current` 不是"可取址函数"），所以可移植程序几乎碰不到这种情形。

!!! impl "libc++ 的隐藏默认实参"
    libc++ 把 `current` 实现为 `static consteval source_location current(__bsl_ty __ptr = __builtin_source_location()) noexcept`——多了一个**带默认实参的隐藏参数**，借默认实参在调用点求值的规则把编译器内建函数"挪"到调用点。[[member.functions]] 允许实现这样增加带默认实参的参数，代价是：`(&std::source_location::current)()` 在 libc++ 下报"参数太少"。这正是标准不允许对它取地址的理由之一。

### 默认实参与默认成员初始化器（¶2）

关键在 ¶2 的 *Remarks*：

!!! std
    Any call to `current` that appears as a default argument, or as a subexpression thereof, should correspond to the location of the invocation of the function that uses the default argument.

    作为默认实参（或其子表达式）出现的 `current` 调用，**应当**对应于使用该默认实参的那次函数调用的位置。

对默认成员初始化器同理：作为默认成员初始化器出现的 `current()`，应当对应于**使用该初始化器的构造函数定义或聚合初始化**的位置。

这和核心语言的规则是一致的：[[dcl.fct.default]] 规定默认实参在**每次调用时**于调用点求值；[[class.base.init]] 规定默认成员初始化器在构造函数使用它时求值。`current()` 是立即函数，它的"立即调用"恰好发生在默认实参被代入调用点的时刻。注意 ¶2 用的是 *should*——这是对实现的推荐，而非硬性要求，但所有主流实现都照做。

```cpp run title="srcloc-log.cpp" ok
#include <cstdio>
#include <source_location>

void log(const char* msg, std::source_location loc = std::source_location::current()) {
    std::printf("%s:%u:%u [%s] %s\n", loc.file_name(), unsigned(loc.line()),
                unsigned(loc.column()), loc.function_name(), msg);
}

template<class T> void tf(T) { log("in template"); }

struct S {
    std::source_location where = std::source_location::current();
    S() {}            // where 对应这一行
    S(int) {}         // where 对应这一行
};

int main() {
    log("hello");                     // 调用点：这一行，而不是 log 的声明处
    tf(1.0);                          // 函数名由实现定义，Clang 给出 "void tf(T) [T = double]"
    S a, b(1);
    std::printf("%u %u\n", unsigned(a.where.line()), unsigned(b.where.line()));
    std::source_location here = std::source_location::current();
    log("forwarded", here);           // 显式传入：记录的是 here 的位置（¶3 例 1 中的 f(c)）
}
```

!!! pitfall "不要把 `current()` 写在函数体里再返回"
    ```cpp
    std::source_location where() { return std::source_location::current(); }
    ```
    这个函数返回的永远是 `where` 函数体内那一行。只有作为**默认实参**时，`current()` 才"穿透"到调用者。同样，`log(const char* msg, std::source_location loc = where())` 也不行——默认实参 `where()` 在调用点被求值，但 `current()` 是在 `where` 的函数体内被调用的。

!!! pitfall "变参模板与默认实参不能共存"
    `template<class... Args> void log(fmt, Args&&... args, std::source_location loc = current())` 行不通：参数包后面的形参无法被推导，也无法依靠默认实参。常见的解法是把 `source_location` 塞进第一个参数的类型里：定义 `struct format_with_loc { const char* fmt; std::source_location loc; format_with_loc(const char* f, std::source_location l = std::source_location::current()) : fmt(f), loc(l) {} };`，让 `log(format_with_loc fmt, Args&&...)` 通过**隐式转换构造函数的默认实参**捕获调用点。

### 默认构造函数（¶4）

`constexpr source_location() noexcept`：数据成员被初始化为**有效但未指明**的值。libc++ 中文件名和函数名为空字符串，行列为 0。

## 观察函数（[support.srcloc.obs]）

`line()`、`column()`、`file_name()`、`function_name()` 分别返回对应的仅用于说明的成员（¶1–¶4），全部 `constexpr noexcept`。

列号的含义完全由实现定义。Clang 给出的是被调用表达式（对默认实参而言是整个调用表达式）开始处的列号；以 1 为起点。不要指望不同编译器的列号一致。

`function_name()` 的格式同样由实现定义："如 `__func__`" 只是举例，实际上 Clang 和 GCC 返回的是类似 `__PRETTY_FUNCTION__` 的带签名的形式，例如 `"int main()"`、`"void tf(T) [T = double]"`；lambda 的函数名形如 `"auto main()::(lambda)::operator()() const"`。

```cpp run title="srcloc-line.cpp" ok
#include <cstdio>
#include <source_location>

constexpr auto here = std::source_location::current();   // 命名空间作用域：不在任何函数中
static_assert(here.function_name()[0] == '\0');          // 空字符串
static_assert(here.line() == 4);

int main() {
#line 1000 "fake.cpp"
    auto loc = std::source_location::current();           // 受 #line 影响
    std::printf("%s:%u\n", loc.file_name(), unsigned(loc.line()));   // fake.cpp:1000
}
```

## 小结

!!! summary
    - `current()` 是 `consteval` 的；作为**默认实参**时对应调用点，作为**默认成员初始化器**时对应使用它的构造函数或聚合初始化。
    - `line_` 为预设行号、`file_name_` 为预设文件名，均受 `#line` 影响；`column_` 与 `function_name_` 的格式由实现定义。
    - 两个字符串字段永不为空指针；不在函数中时 `function_name()` 为空字符串。
    - 默认构造得到"有效但未指明"的值。
    - 实现可以只存一个指针（libc++ 即如此），复制成本极低。
