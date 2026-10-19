---
title: 源码位置
summary: std::source_location 用 consteval 的 current() 加上默认实参在调用点求值的规则，让普通函数也能记录调用者的文件、行号和函数名；以及各字段的取值规则和默认成员初始化器中的约定。
status: done
covers: *
papers: P1208R6
related: cpp.predefined, cpp.line, dcl.fct.default, class.mem.general, expr.const.imm, dcl.fct.def.general, expr.call
tags: 标准库, source_location, 日志, consteval
updated: 2026-10-19
---

!!! tldr
    - 把 `std::source_location::current()` 写成函数的默认实参，得到的是调用者的位置，不是函数声明的位置。写在函数体里，得到的就是函数体那一行。
    - 写成默认成员初始化器时，得到的是使用它的构造函数或聚合初始化的位置。
    - 行号和文件名与 `__LINE__`、`__FILE__` 一致，受 `#line` 影响；列号和函数名的格式由实现定义。
    - 两个字符串字段永远不是空指针；不在任何函数里时，函数名是空字符串。

## 记录调用者的位置

```cpp run title="srcloc-log.cpp" ok
#include <cstdio>
#include <source_location>

void log(const char* msg,
         std::source_location loc = std::source_location::current()) {
  std::printf("%s:%u [%s] %s\n", loc.file_name(), unsigned(loc.line()),
              loc.function_name(), msg);
}

template<class T> void tf(T) { log("in template"); }

int main() {
  log("hello");   // 记录的是这一行，不是 log 的声明处
  tf(1.0);
  [] { log("lambda"); }();
}
```

本机 Clang 23 的输出：

```text
srcloc-log.cpp:13 [int main()] hello
srcloc-log.cpp:10 [void tf(T) [T = double]] in template
srcloc-log.cpp:15 [auto main()::(lambda)::operator()() const] lambda
```

C 风格的日志宏用 `__FILE__`、`__LINE__`、`__func__` 记录位置，但它们只在宏里有用。写成普通函数的默认实参 `int line = __LINE__`，宏在声明处展开，记录的永远是声明那一行。

`std::source_location`（C++20，[[P1208R6]]）解决了这个问题。它依赖两条规则：默认实参在每次调用时、在调用点求值（[[dcl.fct.default]]）；`current()` 是 `consteval` 函数，每次调用都在编译期求值，记录的是它被求值的位置（[[expr.const.imm]]）。两者结合，`current()` 记录的就是调用点。

## 类的形状 [support.srcloc.class.general]

```cpp
struct source_location {
  static consteval source_location current() noexcept;
  constexpr source_location() noexcept;
  constexpr source_location(const source_location&) noexcept = default;
  constexpr source_location& operator=(const source_location&) noexcept = default;

  constexpr uint_least32_t line() const noexcept;
  constexpr uint_least32_t column() const noexcept;
  constexpr const char* file_name() const noexcept;
  constexpr const char* function_name() const noexcept;
private:
  uint_least32_t line_, column_;              // 仅用于说明
  const char* file_name_; const char* function_name_;   // 仅用于说明
};
```

`<source_location>` 只定义这一个类（[source.location.syn]），整个头文件是 freestanding 的。

¶1 `source_location` 满足 `semiregular`（可默认构造、可复制），`is_nothrow_swappable_v<source_location>` 为 `true`。注 1 说明设计意图是体积小、复制快，复制和移动操作是否平凡是未指定的。

¶2 `file_name_` 和 `function_name_` 总是指向一个空终止字节串，从不为空指针，可以直接交给 `printf("%s")`。

¶3 复制或移动之后，新对象的四个字段与原对象相同。字符串字段按 `strcmp` 比较内容，不要求指针相同。

!!! impl "libc++ 只存一个指针"
    说明用的四个成员只是规格的描述手段。libc++ 的 `source_location` 只有一个成员，指向编译器生成的一个静态结构，里面存着文件名、函数名、行和列，所以本机 `sizeof(std::source_location)` 是 8。这个结构由 Clang 的内建函数 `__builtin_source_location()` 产生，结构和字段的名字写死在编译器里，库与编译器在这里直接耦合。

## `current()` 的取值 [support.srcloc.cons]

¶1.1 以普通的写法调用 `current()`（被调用的后缀表达式是指名 `current` 的 *id-expression*，可以带括号）时，返回一个值由实现定义的 `source_location`。这个值应当像 `__LINE__`、`__FILE__` 一样受 `#line` 影响（[[cpp.line]]）。各字段的取值：

| 字段 | 值 |
|---|---|
| `line_` | 预设行号（[[cpp.predefined]]），从 1 开始；行号未知时鼓励用 0 |
| `column_` | 由实现定义，表示距行首的某种偏移，从 1 开始；未知时鼓励用 0 |
| `file_name_` | 当前源文件的预设名字（[[cpp.predefined]]） |
| `function_name_` | 当前函数的名字，类似 `__func__`（[[dcl.fct.def.general]]）；不在函数里时为空字符串 |

函数名的格式由实现定义。Clang 和 GCC 实际给出的是带签名的形式，类似 `__PRETTY_FUNCTION__`，见开头的输出。列号同样由实现定义，不同编译器的结果不要指望一致。

```cpp run title="srcloc-line.cpp" ok
#include <cstdio>
#include <source_location>

constexpr auto here = std::source_location::current();
static_assert(here.line() == 4);
static_assert(here.function_name()[0] == '\0');  // 不在函数中：空字符串

int main() {
#line 1000 "fake.cpp"
  auto loc = std::source_location::current();
  std::printf("%s:%u\n", loc.file_name(), unsigned(loc.line()));
}
```

程序打印 `fake.cpp:1000`。所有观察函数都是 `constexpr` 的，结果可以用在 `static_assert` 里（[support.srcloc.obs]）。

¶1.2 以其他方式调用时，返回的字段是有效但未指定的值。这是兜底条款，可移植程序几乎碰不到：`current` 是 `consteval` 函数，不能在立即调用之外取地址，本机 Clang 对 `&std::source_location::current` 报 "cannot take address of consteval function"。

¶4 默认构造函数把字段初始化为有效但未指定的值。本机 libc++ 中两个字符串为空串，行列为 0。

### 默认实参和默认成员初始化器（¶2）

!!! std
    Any call to `current` that appears as a default argument ([dcl.fct.default]), or as a subexpression thereof, should correspond to the location of the invocation of the function that uses the default argument ([expr.call]).

¶2 `current()` 作为默认实参或其子表达式出现时，应当对应使用这个默认实参的那次函数调用的位置。作为默认成员初始化器（[[class.mem.general]]）出现时，应当对应使用这个初始化器的构造函数定义或聚合初始化的位置。

这两条与核心语言一致：默认实参在调用点求值，默认成员初始化器在构造函数使用它时求值。条文用的是 should，是对实现的建议，主流实现都照做。

```cpp run title="srcloc-member.cpp" ok
#include <cstdio>
#include <source_location>

struct S {
  std::source_location where = std::source_location::current();
  int x = 0;
  S() {}          // a.where 指向这一行（第 7 行）
  S(int v) : x(v) {}   // b.where 指向这一行（第 8 行）
};
struct Agg { std::source_location where = std::source_location::current(); };

int main() {
  S a, b(1);
  Agg g{};        // 聚合初始化：指向这一行（第 14 行）
  std::printf("%u %u %u\n", unsigned(a.where.line()),
              unsigned(b.where.line()), unsigned(g.where.line()));
}
```

本机打印 `7 8 14`。第 3 段的标准例子还演示了另一点：显式传入一个 `source_location`，比如 `f(c)`，记录的就是 `c` 自己的位置。

!!! pitfall "包一层函数就失效"
    ```cpp
    std::source_location where() { return std::source_location::current(); }
    void log(const char* msg, std::source_location loc = where());
    ```
    `where()` 返回的永远是它函数体里那一行。默认实参 `where()` 确实在调用点求值，但 `current()` 是在 `where` 的函数体里被调用的。只有 `current()` 本身直接出现在默认实参里，才会对应到调用点。

!!! pitfall "变参模板放不下默认实参"
    `template<class... Args> void log(const char* fmt, Args&&... args, std::source_location loc = std::source_location::current())` 行不通：函数参数包后面的形参无法推导，调用时实参全被包吞掉。常见的做法是把位置放进第一个参数的类型里：

    ```cpp
    struct fmt_loc {
      const char* fmt;
      std::source_location loc;
      fmt_loc(const char* f,
              std::source_location l = std::source_location::current())
        : fmt(f), loc(l) {}
    };
    template<class... Args> void log(fmt_loc f, Args&&... args);
    ```

    调用 `log("x = {}", x)` 时，`"x = {}"` 隐式转换为 `fmt_loc`，转换构造函数的默认实参在调用点求值。
