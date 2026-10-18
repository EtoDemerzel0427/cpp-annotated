---
title: 常量求值语境
summary: is_constant_evaluated() 等价于 if consteval 的布尔版本，判断"当前是否处于明显常量求值"；C++26 的 consteval 函数 is_within_lifetime(p) 判断指针所指对象是否在生存期内（可用于在编译期探测联合体的活跃成员），以及它"只能问常量求值中诞生的对象"的限制
status: draft
covers: meta.const.eval
papers: P0595R2, P2641R4
related: expr.const, stmt.if, basic.life, class.union, meta.reflection
tags: 标准库, constexpr, consteval, 常量求值, 生存期
updated: 2026-10-18
---

`constexpr` 函数既可以在编译期执行，也可以在运行期执行。有时同一个函数需要在两种情况下走不同的路：编译期不能调用 `memset`、不能读联合体的非活跃成员、不能用内联汇编，运行期则希望用这些快速路径。[meta.const.eval] 提供了两个"看一眼自己身处何处"的工具。

## `is_constant_evaluated`（¶1–¶2）

```cpp
constexpr bool is_constant_evaluated() noexcept;
```

¶1 *Effects*：等价于

```cpp
if consteval {
  return true;
} else {
  return false;
}
```

这条规格是 C++23 引入 `if consteval`（[[stmt.if]]）之后改写的；C++20 由 [[P0595R2]] 引入这个函数时，它被定义为"当调用发生在**明显常量求值**（[[g:manifestly-constant-evaluated]]）的表达式或转换中时返回 `true`"。两种表述的效果相同：**它问的是"包含这次调用的最外层求值是不是明显常量求值"**，而不是"这次调用的结果能不能在编译期算出来"。

明显常量求值的语境由 [[expr.const]] 列出，包括：常量表达式（`static_assert`、数组边界、模板实参、`constexpr` 变量的初始化器）、`if constexpr` 的条件、`consteval` 函数的调用、**常量初始化**的尝试（包括 `const` 整型变量和静态存储期变量的初始化器）等。

```cpp run title="is-constant-evaluated.cpp" ok
#include <cstdio>
#include <cstring>
#include <type_traits>

constexpr void zero(unsigned char* p, int n) {
    if (std::is_constant_evaluated()) {          // 不能写成 if constexpr
        for (int k = 0; k < n; ++k) p[k] = 0;
    } else {
        std::memset(p, 0, n);                    // memset 不是核心常量表达式
    }
}

constexpr int f() {
    unsigned char b[4] = {1, 2, 3, 4};
    zero(b, 4);
    return b[0] + b[3];
}
static_assert(f() == 0);                         // 编译期走循环

constexpr int where() { return std::is_constant_evaluated(); }

int main() {
    const int a = where();   // 尝试常量初始化：明显常量求值 → 1
    int b = where();         // 普通初始化：运行期调用 → 0
    std::printf("%d %d %d\n", f(), a, b);        // 0 1 0
}
```

`a` 与 `b` 的对照说明：同一个 `constexpr` 函数调用，结果取决于**调用所在的语境**，而不是函数本身。

!!! pitfall "`if constexpr (std::is_constant_evaluated())` 恒为真"
    ¶2 例子里的注释特意写着 "should not be a constexpr if statement"。`if constexpr` 的条件本身就是明显常量求值的，所以 `is_constant_evaluated()` 在那里**永远**返回 `true`，运行期分支被整个丢弃。Clang 对此给出警告：

    ```cpp run title="if-constexpr-trap.cpp"
    #include <type_traits>

    constexpr int g() {
        if constexpr (std::is_constant_evaluated()) return 1;   // warning: will always evaluate to 'true'
        else return 2;
    }

    int main() { return g(); }   // 运行期调用也返回 1
    ```

    诊断原文："'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression [-Wconstant-evaluated]"。C++23 之后，直接写 `if consteval { ... } else { ... }` 更清晰，也不会犯这个错——`if consteval` 的分支还可以调用 `consteval` 函数，而 `if (std::is_constant_evaluated())` 的分支不行。

!!! impl "libc++"
    实现就是一行内建：`return __builtin_is_constant_evaluated();`。

## `is_within_lifetime` {{c++26}}（¶3–¶6）

```cpp
template<class U = void, class T>
  consteval bool is_within_lifetime(const T* p) noexcept;
```

它由 [[P2641R4]] 引入，是一个 **`consteval`** 函数——只能在常量求值中调用（[[g:immediate-function]]）。

- ¶3 *Mandates*：`static_cast<const volatile U*>(p)` 良构。
- ¶4 *Returns*：若 `p` 指向一个处于其生存期内（[[basic.life]]）的对象，**并且** `static_cast<const volatile U*>(p)` 是常量子表达式，则为 `true`；否则 `false`。
- ¶5 *Remarks*：在把表达式 `E` 作为核心常量表达式求值的过程中，除非 `p` 指向**可用于常量表达式**的对象，或指向一个其完整对象的生存期**在 `E` 之内开始**的对象，否则对它的调用非良构。

### 动机：在编译期探测联合体的活跃成员

常量求值中读取联合体的非活跃成员不是常量表达式（[[expr.const]]），运行期这样做则通常"能用"（实现上就是读字节）。于是"一个省空间的 `optional<bool>`"在两边需要不同的实现——¶6 的例子：

```cpp run title="opt-bool.cpp" ok
#include <type_traits>

struct OptBool {
    union { bool b; char c; };

    // 假设 sizeof(bool) == sizeof(char)，且 true/false 的值表示不同于 2
    constexpr OptBool() : c(2) { }
    constexpr OptBool(bool b) : b(b) { }

    constexpr auto has_value() const -> bool {
        if consteval {
            return std::is_within_lifetime(&b);   // 编译期：不能读 c，就问 b 是否活跃
        } else {
            return c != 2;                        // 运行期：读 c 的字节
        }
    }

    constexpr auto operator*() const -> const bool& { return b; }
};

constexpr OptBool disengaged;
constexpr OptBool engaged(true);
static_assert(!disengaged.has_value());
static_assert(engaged.has_value());
static_assert(*engaged);

int main() { OptBool o; return o.has_value(); }
```

注意运行期分支 `c != 2` 在 `b` 是活跃成员时读取非活跃成员 `c`——按语言规则这是 UB 的类型双关（[[class.union]]），例子注释里的"假设"正是在承认它依赖实现的常见行为。`is_within_lifetime` 的价值在于至少让**编译期**路径是严格合法的。

### "生存期内"包括值不确定的对象

`is_within_lifetime` 只问生存期，不问值是否已初始化：

```cpp run title="within-lifetime-indeterminate.cpp" ok
#include <type_traits>

consteval bool probe() {
    int* p = new int;                        // 默认初始化：值不确定，但对象已在生存期内
    bool r = std::is_within_lifetime(p);
    delete p;
    return r;
}
static_assert(probe());

int main() {}
```

### ¶5 的限制：只能问"自己人"

为什么不能拿任意指针去问？因为常量求值器只了解**在常量求值中诞生**或**可用于常量表达式**的对象的状态。一个普通的全局变量 `int g;`，编译器在编译期根本不知道运行期它是否被销毁、被 placement-new 重建过。所以：

```cpp run title="within-lifetime-global.cpp" error
#include <type_traits>

int g;
constexpr bool b = std::is_within_lifetime(&g);   // error: g 不可用于常量表达式，生存期也不在本次求值中开始

int main() {}
```

Clang 的诊断是 "read of non-const variable 'g' is not allowed in a constant expression"。

### 模板形参 `U`

当前草案中函数模板多了一个前置的模板形参 `U`（默认 `void`），并把 "`static_cast<const volatile U*>(p)` 是常量子表达式" 加进了返回条件。`U = void` 时这个转换总是可行的，行为与原始提案相同；显式给出 `U` 时，这个附加条件让同一次调用还能回答"`p` 能否在常量求值中 `static_cast` 为 `U*`"——例如从基类指针向下转换到派生类，只有当对象真的是那个派生类时才是常量子表达式（[[expr.static.cast]]、[[expr.const]]）。

!!! impl "libc++ 与草案的差别"
    本地 libc++ 的声明是 `template <class _Tp> consteval bool is_within_lifetime(const _Tp* __p) noexcept`，只有一个模板形参，内部调用 `__builtin_is_within_lifetime(__p)`；在 `__has_builtin(__builtin_is_within_lifetime)` 时定义，并给出 `__cpp_lib_is_within_lifetime` = `202306L`。因此在这套工具链上 `std::is_within_lifetime<int>(&x)` 里的 `int` 绑定的是 `T` 而不是 `U`——草案中的 `U` 形参尚未实现。

## 思考题

!!! question "思考题"
    下面的 `n` 在运行期打印什么？

    ```cpp
    constexpr int sz() { return std::is_constant_evaluated() ? 16 : 4096; }
    int main() {
        int n = sz();
        static int m = sz();
        std::printf("%d %d\n", n, m);
    }
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

`n` 是 `4096`：自动存储期非 `const` 变量的初始化不是明显常量求值。`m` 是 `16`：静态存储期变量的初始化会先**尝试常量初始化**（[[basic.start.static]]），这次尝试是明显常量求值的（[[expr.const]]），它成功了，于是 `m` 被常量初始化为 16。这正是 `is_constant_evaluated` 容易引起困惑之处——同一个调用式，结果取决于它所在的初始化语境。
</details>

## 小结

| 函数 | 何时为真 | 要点 |
|---|---|---|
| `is_constant_evaluated()` | 包含调用的求值是明显常量求值 | 等价于 `if consteval`；勿放进 `if constexpr` |
| `is_within_lifetime(p)` | `p` 所指对象在生存期内（且到 `U*` 的转换是常量子表达式）| `consteval`；只能问可用于常量表达式或在本次求值中诞生的对象；libc++ 尚无 `U` 形参 |
