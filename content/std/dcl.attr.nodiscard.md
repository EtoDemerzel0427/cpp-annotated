---
title: nodiscard 属性
summary: "[[nodiscard]] 标在函数、构造函数、类或枚举上，让编译器在结果被直接丢掉时给出警告；它只影响诊断，(void) 可以表示有意丢弃。"
status: done
since: c++17
papers: P0189R1, P1301R4, P1771R1, P0068R0, P2173R1, P0600R1
related: dcl.attr.grammar, expr.prop, expr.context, expr.call, expr.type.conv, expr.static.cast, expr.cast, cpp.cond
tags: 属性, 诊断, nodiscard
updated: 2026-10-19
---

!!! tldr
    - `[[nodiscard]]` 用于忽略结果几乎一定是错误的场合：没检查的错误码、刚构造就销毁的锁守卫。它只让编译器警告，不改变程序的含义。
    - 可以标在函数、lambda、构造函数上，也可以标在类或枚举类型上；标在类型上时，所有按值返回这个类型的函数都自动生效。
    - 返回 `E&`、`E*` 的函数不会因为 `E` 带了 nodiscard 而被警告，要标在函数本身上。
    - 只有结果被直接丢弃时才警告；写 `(void)f();` 或 `std::ignore = f();` 表示有意丢弃。
    - 属性可以在后来的重声明中加上，但加上之后去不掉。

## 一个忘了起名字的锁

```cpp run ok
struct [[nodiscard]] Error { int code; };
Error save();                      // 返回 nodiscard 类型

struct Lock {
  [[nodiscard]] explicit Lock(int fd) { (void)fd; }
};

void f() {
  save();                          // 警告：错误码被丢掉了
  Lock(3);                         // 警告：临时对象立刻被销毁
  Lock lk(3);                      // OK：本意是这样
  (void)lk;
}
int main() {}
```

`Lock(3);` 是一个常见错误：本意是 `Lock lk(3);`，结果只构造了一个临时对象，加锁之后立刻又解锁了。`save();` 则把一个错误码丢掉了。这两行都能编译，程序也没有未定义行为，只是几乎一定是写错了。`[[nodiscard]]` 让编译器在这类地方发出警告。本机 Clang 23 对两行分别警告 `ignoring return value of type 'Error' declared with 'nodiscard' attribute` 和 `ignoring temporary created by a constructor declared with 'nodiscard' attribute`。

这个属性只影响诊断。标准只规定在什么情况下建议实现给出警告，对程序的执行没有任何影响，满足 [[dcl.attr.grammar#8]] 的可忽略性。

## 能标在哪里（¶1–¶2）

```cpp run ok
[[nodiscard]] int compute();                            // 函数
[[nodiscard("check the error code")]] int open_file();  // 带理由
struct [[nodiscard]] Error { int code; };               // 类
enum class [[nodiscard]] Errc { ok, bad };              // 枚举

struct Lock {
  [[nodiscard]] explicit Lock(int fd);                  // 构造函数
  Lock();                                               // 这个不是
};

auto l = [] [[nodiscard]] () { return 1; };             // lambda
int main() {}
```

¶1 `nodiscard` 可以用于函数（包括构造函数，C++20 的 [[P1771R1]]）、lambda 的调用运算符（C++23 的 [[P2173R1]]），以及类或枚举的声明。它可以带一个字符串参数说明理由（C++20 的 [[P1301R4]]），编译器应把理由写进警告信息。

¶2 一个函数或类型可以先不带这个属性，在后来的重声明里加上；注 1 说明，加上以后，再后面的重声明不能把它去掉。各次声明给出的理由可以不同。

```cpp run ok
int f();
[[nodiscard]] int f();   // 从这里起 f 是 nodiscard 的
int f();                 // 去不掉
int main() {}
```

这一点和 `[[noreturn]]` 不同，后者必须出现在第一次声明上，因为它影响调用点的代码生成。`nodiscard` 只影响诊断，晚一点知道也没关系。

## 哪些调用算 nodiscard 调用（¶3）

¶3 先定义两个术语。[[g:nodiscard-type|nodiscard 类型]]（nodiscard type）是在某个可达的声明中标了 `nodiscard` 的类或枚举类型，可以带 `const`、`volatile`。[[g:nodiscard-call|nodiscard 调用]]（nodiscard call）是下面两种表达式之一：

- ¶3.1 函数调用表达式（[[expr.call]]），被调用的函数标了 `nodiscard`，或者返回类型是 nodiscard 类型；
- ¶3.2 显式类型转换，如 `T(x)`、`T{x}`、`static_cast<T>(x)`、`(T)x`（[[expr.type.conv]]、[[expr.static.cast]]、[[expr.cast]]），它通过一个标了 `nodiscard` 的构造函数构造对象，或者初始化的是一个 nodiscard 类型的对象。

有几处要注意：

1. 返回类型必须就是 nodiscard 类型本身。返回 `Error&`、`Error*`、`std::optional<Error>` 的函数，除非自己标了 `nodiscard`，否则不是 nodiscard 调用。
2. 通过函数指针调用时，编译器只看得到指针的类型。实际的编译器只按返回类型判断，不会因为指针指向一个标了 `nodiscard` 的函数而警告。
3. 构造函数的情形只覆盖显式类型转换这种表达式。`Lock lk(3);` 是声明，不是表达式，谈不上丢弃。

## 什么时候应当警告（¶4）

!!! std
    Appearance of a nodiscard call as a potentially evaluated discarded-value expression ([expr.prop]) of non-void type is discouraged unless explicitly cast to `void`.

¶4 nodiscard 调用出现在下面这样的位置时，标准建议实现给出警告，并带上理由字符串：

- 它是一个**弃值表达式**（discarded-value expression，[[expr.context]]），即结果不被使用的表达式：表达式语句 `f();`、逗号运算符的左操作数、`for` 的初始化语句和递增表达式等；
- 它是潜在求值的，所以 `sizeof(f())`、`decltype(f())` 里的 `f()` 不算；
- 它的类型不是 `void`；
- 它没有显式转换为 `void`。`(void)f();` 和 `static_cast<void>(f());` 是公认的表示有意丢弃的写法。

不能给出这种警告的实现，`__has_cpp_attribute(nodiscard)` 应为 0。

```cpp run ok
#include <tuple>
[[nodiscard]] int f();
struct [[nodiscard]] R {};
R make();
R& get();

void t() {
  f();                      // 警告
  make();                   // 警告：返回 nodiscard 类型
  R{};                      // 警告：初始化 nodiscard 类型的对象（¶3.2）
  (void)f();                // 不警告：显式丢弃
  std::ignore = f();        // 不警告：结果被使用了
  get();                    // 不警告：返回引用
  int (*fp)() = f;
  fp();                     // 不警告：通过指针调用
  (void)sizeof(f());        // 不警告：不是潜在求值
  for (f();;) break;        // 警告：初始化语句里被丢弃
}
int main() {}
```

以上注释都与本机 Clang 23 的实际表现一致。`std::ignore = f();` 在 C++26 中正式成为合法的有意丢弃写法（`std::ignore` 的赋值行为有了明确规定），它比 `(void)` 更显眼，也更容易搜索。

### 标准的例子

¶5 的例子把几种情形放在了一起：

```cpp run ok
struct [[nodiscard]] my_scopeguard { };
struct my_unique {
  my_unique() = default;                         // 不获取资源
  [[nodiscard]] my_unique(int fd) { (void)fd; }  // 获取资源
  ~my_unique() noexcept { }                      // 释放资源（如果有）
};
struct [[nodiscard]] error_info { };
error_info enable_missile_safety_mode() { return {}; }
void launch_missiles() {}

void test_missiles() {
  my_scopeguard();               // 建议警告
  (void)my_scopeguard(),         // 不建议警告：转换为 void
    launch_missiles();           // 逗号运算符，语句还没结束
  my_unique(42);                 // 建议警告：nodiscard 构造函数
  my_unique();                   // 不建议警告：这个构造函数没有标记
  enable_missile_safety_mode();  // 建议警告
  launch_missiles();
}
error_info& foo() { static error_info e; return e; }
void f() { foo(); }              // 不建议警告：返回引用
int main() { test_missiles(); f(); }
```

`my_unique(42)` 与 `my_unique()` 的区别说明了把属性标在构造函数上的用处：只有获取资源的那个构造函数，临时对象被丢掉时才值得警告。

## 用在哪里合适

- 返回错误码或状态的函数。更好的做法是把错误类型本身标上，一次标记，所有按值返回它的函数都生效。
- 只为返回值而调用的函数：`empty()`、`size()`、`std::launder`、`operator new`。`v.empty();` 常常是把 `empty` 当成了 `clear`。
- 获取资源的构造函数和工厂函数：`std::make_unique`、`std::allocator::allocate`，丢掉结果就是泄漏。
- 返回新对象而不修改原对象的函数，比如 `trimmed()` 这类接口，使用者容易以为它会就地修改。

C++20 起，标准库规范在 `operator new`、`allocate`、容器的 `empty()`、`std::launder` 等处标上了 `[[nodiscard]]`（[[P0600R1]]）。三大标准库实现用得比标准要求多得多。

!!! impl "各编译器的警告"
    - Clang：调用标了 `nodiscard` 的函数，结果被丢弃时报 `-Wunused-result`；返回 nodiscard 类型、或 nodiscard 构造函数产生的临时对象被丢弃时报 `-Wunused-value`。两者默认开启。`[[nodiscard]]` 标在返回 `void` 的函数上时，Clang 会警告这个属性被忽略。
    - GCC 统一用 `-Wunused-result`，默认开启。GCC 的 `__attribute__((warn_unused_result))` 是它的前身，但那个属性的警告不能用 `(void)` 消除，标准属性在这一点上做了改进。
    - MSVC 报 C4834 等警告。
    - 警告是推荐做法而非要求，实现可能为了减少噪音，在模板或宏展开里不警告。

## 历史与演进

!!! history
    - C++17：引入 `[[nodiscard]]`（[[P0189R1]]，源自 [[P0068R0]]），只能用于函数和类、枚举，没有参数。
    - C++20：可以带理由（[[P1301R4]]），可以用于构造函数（[[P1771R1]]），标准库开始标注（[[P0600R1]]）。
    - C++23：lambda 的调用运算符可以带属性（[[P2173R1]]）。
    - C++26：属性参数里的字符串改为不求值字符串（[[P2361R6]]），并要求不能警告的实现让 `__has_cpp_attribute` 返回 0。当前草案用 nodiscard 类型和 nodiscard 调用这两个术语来表述规则。

## 常见误解

!!! pitfall "nodiscard 能强制检查结果"
    它不会让程序非良构，也不保证一定有警告。需要强制的话，要靠类型设计（例如一个析构时检查自己是否被读过的结果类型）或者契约。

!!! pitfall "`std::lock_guard<std::mutex>(m);` 只是少了个名字"
    这一行根本不是表达式。按 [[dcl.ambig.res]]，它声明了一个名为 `m` 的局部变量，遮住了外面的互斥量。`lock_guard` 不能默认构造，所以通常会编译失败，但别的类型可能静默通过。nodiscard 构造函数在这里帮不上忙，应写成 `std::lock_guard lk(m);`。

## 思考题

!!! question "思考题"
    按 ¶3–¶4，下面哪些行建议警告？
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
      R r = make();
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `make();`：返回 nodiscard 类型，结果被丢弃，建议警告。
- `cmake();`：nodiscard 类型可以带 `const`，建议警告。
- `pmake();`：返回 `R*`，不是 nodiscard 类型，函数也没有标记，不建议警告。
- `v();`：函数标了，但表达式类型是 `void`，¶4 只管非 `void` 的情形，不建议警告。Clang 会对这个声明本身警告属性被忽略。
- `R r = make();`：结果用来初始化 `r`，不是弃值表达式，不建议警告。

本机 Clang 23 的实际警告与上面一致。
</details>
