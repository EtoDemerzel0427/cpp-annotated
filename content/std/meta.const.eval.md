---
title: 常量求值语境
summary: is_constant_evaluated() 判断当前调用是否处在明显常量求值中；C++26 的 is_within_lifetime(p) 在编译期判断指针所指的对象是否在生存期内。
status: draft
covers: meta.const.eval
papers: P0595R2, P2641R4
related: expr.const, stmt.if, basic.life, class.union, meta.reflection
tags: 标准库, constexpr, consteval, 常量求值, 生存期
updated: 2026-10-19
---

!!! tldr
    - `std::is_constant_evaluated()` 等价于 `if consteval` 的布尔版本：调用处在明显常量求值中时返回 `true`。
    - 结果取决于调用所在的语境，而不是函数本身：同一个调用用来初始化静态变量时可能得到 `true`，初始化局部变量时得到 `false`。
    - 不要写 `if constexpr (std::is_constant_evaluated())`，它永远为真。C++23 起直接用 `if consteval`。
    - C++26 的 `std::is_within_lifetime(p)` 是 `consteval` 函数，判断 `p` 所指的对象是否在生存期内，可以在编译期判断联合体的哪个成员是活跃的。
    - `is_within_lifetime` 只能询问可用于常量表达式的对象，或者在本次常量求值中创建的对象。

`constexpr` 函数既可以在编译期执行，也可以在运行时执行。有些操作只能在其中一边做：编译期不能调用 `memset`、不能读联合体的非活跃成员、不能用内联汇编，运行时却希望用这些更快的写法。[meta.const.eval] 中的两个函数让代码知道自己正处在哪一边。

## `is_constant_evaluated`

```cpp
constexpr bool is_constant_evaluated() noexcept;
```

¶1 规定它的效果等价于

```cpp
if consteval {
  return true;
} else {
  return false;
}
```

也就是说，如果这次调用处在[[g:manifestly-constant-evaluated|明显常量求值]]（manifestly constant-evaluated）中，结果为 `true`。明显常量求值的情形由 [[expr.const]] 列出，包括常量表达式（`static_assert` 的条件、数组边界、模板实参、`constexpr` 变量的初始化器）、`if constexpr` 的条件、对 `consteval` 函数的调用，以及静态存储期变量和 `const` 整型变量初始化时对常量初始化的尝试。

```cpp run title="is-constant-evaluated.cpp" ok
#include <cstdio>
#include <cstring>
#include <type_traits>

constexpr void zero(unsigned char* p, int n) {
  if (std::is_constant_evaluated()) {
    for (int k = 0; k < n; ++k) p[k] = 0;
  } else {
    std::memset(p, 0, n);  // 不是核心常量表达式
  }
}

constexpr int f() {
  unsigned char b[4] = {1, 2, 3, 4};
  zero(b, 4);
  return b[0] + b[3];
}
static_assert(f() == 0);  // 编译期走循环

constexpr int where() { return std::is_constant_evaluated(); }

int main() {
  const int a = where();  // 尝试常量初始化：1
  int b = where();        // 运行时调用：0
  std::printf("%d %d %d\n", f(), a, b);  // 0 1 0
}
```

`zero` 改编自标准的例 1（第 2 段）：编译期用循环清零，运行时调用 `memset`。`a` 和 `b` 的对比说明，同一个函数调用的结果取决于调用出现在哪里。`a` 是 `const int`，它的初始化器会先作为常量表达式尝试求值，这次求值是明显常量求值；`b` 的初始化只是普通的运行时调用。

!!! history
    C++20 由 [[P0595R2]] 引入这个函数时，规定它在明显常量求值中返回 `true`。C++23 加入 `if consteval`（[[stmt.if]]）后，规格改写为上面的等价形式，含义没有变。

### 不要放进 `if constexpr`

¶2 例子中的注释特意说明，那个 `if` 不应该写成 `if constexpr`。`if constexpr` 的条件本身就是明显常量求值，所以 `is_constant_evaluated()` 在那里总是返回 `true`，运行时分支被整个丢弃：

```cpp run title="if-constexpr-trap.cpp"
#include <type_traits>

constexpr int g() {
  if constexpr (std::is_constant_evaluated())  // 总是 true
    return 1;
  else
    return 2;
}

int main() { return g(); }  // 运行时调用也返回 1
```

Clang 对此给出 `-Wconstant-evaluated` 警告，指出 `std::is_constant_evaluated` 在明显常量求值的表达式中总是求值为 `true`。这段代码是良构的，只是逻辑不对，所以没有标判定。

C++23 起应该直接写 `if consteval { … } else { … }`，不会犯这个错误。`if consteval` 还有一个好处：它的第一个分支可以调用 `consteval` 函数，`if (std::is_constant_evaluated())` 的分支不行。

!!! impl "libc++"
    libc++ 的实现只有一行：`return __builtin_is_constant_evaluated();`。

## `is_within_lifetime` {{c++26}}

```cpp
template<class U = void, class T>
  consteval bool is_within_lifetime(const T* p) noexcept;
```

这个函数由 [[P2641R4]] 引入。它是 `consteval` 函数，即[[g:immediate-function|立即函数]]，只能在常量求值中调用。

### 动机：编译期判断联合体的活跃成员

常量求值中读取联合体的非活跃成员不是常量表达式（[[expr.const]]），编译器会拒绝。下面的例子来自第 6 段，它用一个 `bool` 和一个 `char` 组成的联合体实现了只占一个字节的可选 `bool`：

```cpp run title="opt-bool.cpp" ok
#include <type_traits>

struct OptBool {
  union { bool b; char c; };

  // 假设 sizeof(bool) == sizeof(char)，
  // 且 true、false 的值表示都不同于 2
  constexpr OptBool() : c(2) {}
  constexpr OptBool(bool b) : b(b) {}

  constexpr auto has_value() const -> bool {
    if consteval {
      return std::is_within_lifetime(&b);  // 编译期：不能读 c
    } else {
      return c != 2;  // 运行时：读 c
    }
  }

  constexpr auto operator*() const -> const bool& { return b; }
};

constexpr OptBool disengaged;
constexpr OptBool engaged(true);
static_assert(!disengaged.has_value());
static_assert(engaged.has_value());
static_assert(*engaged);

int main() {
  OptBool o;
  return o.has_value();
}
```

编译期不能读 `c` 来判断有没有值，于是改问 `b` 是否在生存期内，也就是 `b` 是不是活跃成员。运行时分支读取 `c`，当活跃成员是 `b` 时，这就是读取非活跃成员。例子的注释列出了它所依赖的实现性质；普通代码不应模仿这种写法，`is_within_lifetime` 至少保证了编译期那条路径是严格合法的。

### 返回值与限制

¶3：`static_cast<const volatile U*>(p)` 必须良构（*Mandates*）。

¶4：如果 `p` 指向一个在其生存期内（[[basic.life]]）的对象，而且 `static_cast<const volatile U*>(p)` 是常量子表达式，返回 `true`；否则返回 `false`。

它只问生存期，不问值是否已经确定。用 `new int` 默认初始化的对象值不确定，但已经在生存期内：

```cpp run title="within-lifetime-indeterminate.cpp" ok
#include <type_traits>

consteval bool probe() {
  int* p = new int;  // 值不确定，但对象已在生存期内
  bool r = std::is_within_lifetime(p);
  delete p;
  return r;
}
static_assert(probe());

int main() {}
```

¶5 限制了能问哪些对象：在把表达式 `E` 作为核心常量表达式求值的过程中，`p` 必须指向一个[[g:usable-in-constant-expressions|可用于常量表达式]]的对象，或者指向一个完整对象的生存期在 `E` 之内开始的对象，否则调用非良构。

原因在于，常量求值器只知道这两类对象的状态。对于一个普通的全局变量，编译器在编译期无从知道运行时它是否已被销毁、是否被 placement new 重新创建过：

```cpp run title="within-lifetime-global.cpp" error
#include <type_traits>

int g;
constexpr bool b = std::is_within_lifetime(&g);  // error

int main() {}
```

Clang 拒绝这段代码，附注说明在常量表达式中不允许读取非 const 变量 `g`。

### 模板形参 `U`

当前草案的函数模板多了一个前置的模板形参 `U`，默认为 `void`，并在返回条件中加了一条：`static_cast<const volatile U*>(p)` 必须是常量子表达式。`U` 为 `void` 时这个转换总是可行的，行为与原始提案相同。

显式给出 `U` 时，同一次调用还能回答 `p` 能否在常量求值中转换为 `U*`。例如从基类指针向下转换到派生类指针，只有对象确实是那个派生类时，这个 `static_cast` 才是常量子表达式（[[expr.static.cast]]、[[expr.const]]）。

!!! impl "libc++ 尚未实现 `U`"
    本机 libc++ 的声明只有一个模板形参 `template <class _Tp> consteval bool is_within_lifetime(const _Tp* __p) noexcept`，内部调用 `__builtin_is_within_lifetime`，特性测试宏 `__cpp_lib_is_within_lifetime` 为 `202306L`，而当前草案中是 `202603L`。所以在这套工具链上，`std::is_within_lifetime<int>(&x)` 中的 `int` 绑定的是 `T` 而不是 `U`。

## 思考题

!!! question "思考题"
    下面的程序打印什么？

    ```cpp run ok
    #include <cstdio>
    #include <type_traits>

    constexpr int sz() {
      return std::is_constant_evaluated() ? 16 : 4096;
    }

    int main() {
      int n = sz();
      static int m = sz();
      std::printf("%d %d\n", n, m);
    }
    ```

<details markdown="1">
<summary>答案</summary>

打印 `4096 16`（本机 Clang 23 验证）。

`n` 是自动存储期的非 `const` 变量，它的初始化不是明显常量求值，所以得到 `4096`。`m` 是静态存储期变量，初始化时会先尝试常量初始化（[[basic.start.static]]），这次尝试是明显常量求值（[[expr.const]]），而且成功了，所以 `m` 被常量初始化为 16。
</details>

## 速查

| 函数 | 何时为 `true` | 要点 |
|---|---|---|
| `is_constant_evaluated()` | 调用处在明显常量求值中 | 等价于 `if consteval`；不要放进 `if constexpr` |
| `is_within_lifetime(p)` {{c++26}} | `p` 所指对象在生存期内，且到 `U*` 的转换是常量子表达式 | `consteval`；只能问可用于常量表达式或在本次求值中创建的对象 |
