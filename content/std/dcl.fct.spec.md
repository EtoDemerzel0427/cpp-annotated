---
title: 函数说明符
summary: virtual 与 explicit / explicit(bool) 的适用位置；explicit(bool) 的常量表达式要求，以及它对 C++17 代码造成的一处语法不兼容
status: done
since: c++98
papers: P0892R2
related: class.virtual, class.conv.ctor, class.conv.fct, over.match.copy, over.match.list, temp.deduct.guide
tags: 声明, 说明符, explicit, virtual
updated: 2026-10-17
---

**函数说明符**（*function-specifier*）只有两个：`virtual` 和 *explicit-specifier*（`explicit` 或 `explicit(常量表达式)`）。两者都只能用在函数声明上，并且都只能出现在类定义内。本节只规定它们的语法位置，语义分别在 [[class.virtual]]（虚函数与覆盖）和 [[class.conv.ctor]] / [[class.conv.fct]]（转换构造函数与转换函数）中规定。

C++98 时 `inline` 也是函数说明符。C++17 起 `inline` 可以用于变量，因此移到了独立的 [[dcl.inline]]。

## 适用范围与重复（¶1）

¶1 函数说明符只能用于函数声明。一个说明符序列中至多有一个 *explicit-specifier*、至多有一个 `virtual`。

```cpp error
virtual int x;                     // error: virtual 只能用于函数
struct S {
    explicit explicit(true) S(int);   // error: 两个 explicit-specifier
    virtual virtual void f();         // error: virtual 重复（Clang 仅警告）
};
```

## virtual（¶2）

¶2 `virtual` 只能用于非静态成员函数的初始声明，也就是类定义中的那个声明，不能出现在类外定义上：

```cpp run ok
struct B {
    virtual void f();       // 初始声明：在这里写 virtual
    virtual ~B() = default;
};
void B::f() { }             // 类外定义：不能再写 virtual
int main() { B b; b.f(); }
```

```cpp error
struct B { virtual void f(); static void g(); };
virtual void B::f() { }            // error: 不是初始声明
struct C { virtual static void g(); };   // error: 静态成员函数不能是虚的
virtual void free_function();      // error: 不是成员函数
struct D { friend virtual void h(); };   // error: 友元声明的函数不是 D 的成员
```

为什么只能写在初始声明上？因为一个函数是否为虚函数属于类布局（vtable 槽位）的一部分，类定义完成时就必须确定；类外定义只提供函数体，不应该也不能改变类的结构。

本节没有提到的一点是：派生类中覆盖虚函数的函数不需要写 `virtual`，它自动就是虚函数（[[class.virtual#2]]）。推荐写 `override`（它是 *virt-specifier*，不是函数说明符），让编译器检查它确实覆盖了某个虚函数。

## explicit（¶3–4）

¶3 *explicit-specifier* 只能用于类定义内的构造函数或转换函数的声明。（推导指引也可以带 *explicit-specifier*，但那属于 *deduction-guide* 自己的语法，见 [[temp.deduct.guide]]。）

```cpp error
struct S {
    explicit S(int);
    explicit void f();     // error: 不是构造函数或转换函数
};
explicit S::S(int) { }     // error: 不在类定义内
```

`explicit` 的效果简述如下，细节见所链接的条款：

- explicit 构造函数不参与复制初始化（`T x = a;`、按值传参、按值返回）和复制列表初始化（`T x = {a, b};`），只参与直接初始化和显式转换（[[class.conv.ctor]]、[[over.match.copy]]、[[over.match.list]]）。
- explicit 转换函数只用于直接初始化、显式转换，以及上下文转换为 bool（`if (x)`、`!x`、`x && y`）。`explicit operator bool()` 惯用法正是以此为基础（[[class.conv.fct]]）。

```cpp run ok
struct Handle {
    explicit Handle(int fd) : fd(fd) { }
    explicit operator bool() const { return fd >= 0; }
    int fd;
};
void take(Handle) { }
int main() {
    Handle h(3);              // OK: 直接初始化
    Handle h2{4};             // OK: 直接列表初始化
    // Handle h3 = 5;         // error: 复制初始化不考虑 explicit 构造函数
    // take(6);               // error: 参数是复制初始化
    take(Handle(6));          // OK: 显式转换
    if (h) { }                // OK: 上下文转换为 bool 可以用 explicit operator bool
    // bool b = h;            // error: 复制初始化不考虑 explicit 转换函数
    bool b2 = static_cast<bool>(h2);
    return b2 ? 0 : 1;
}
```

C++11 起，`explicit` 对多参数构造函数也有意义：它阻止 `T x = {a, b};` 和 `return {a, b};` 这类复制列表初始化。

### explicit(bool) {{c++20}}

¶4 *explicit-specifier* 中的常量表达式必须是上下文转换为 bool 的常量表达式（[[expr.const]]）。不带表达式的 `explicit` 等价于 `explicit(true)`。表达式为 `true` 时函数是 explicit 的，否则不是。

上下文转换为 bool 的常量表达式（*contextually converted constant expression of type bool*）不允许窄化。这一点和 `static_assert`、`if constexpr` 的条件不同，后两者从 C++23 起允许窄化（[[dcl.pre#13]]）：

```cpp error
struct S {
    explicit(sizeof(char[2])) S(char);  // error: 2 → bool 是窄化转换
    explicit(sizeof(char)) S(bool);     // OK: 1 → true 不窄化
    explicit(2 > 1) S(int);             // OK: 本来就是 bool
};
```

`explicit(bool)` 解决的是条件性 explicit 的问题。C++17 中，`std::pair<T1, T2>` 的转换构造函数应当满足这样的要求：`U1→T1` 和 `U2→T2` 都能隐式转换时，它是隐式的，否则是 explicit 的。没有 `explicit(bool)` 时，只能写两个几乎相同的构造函数，用 SFINAE 让它们互斥地启用；有了它，一个构造函数就够了：

```cpp run ok
#include <type_traits>
#include <string>
template<class T>
struct Wrapper {
    T value;
    template<class U>
        requires std::is_constructible_v<T, U>
    explicit(!std::is_convertible_v<U, T>)      // 仅当 U 不能隐式转换为 T 时 explicit
    Wrapper(U&& u) : value(static_cast<U&&>(u)) { }
};

struct Path { explicit Path(const char*) { } };

int main() {
    Wrapper<std::string> a = "hello";       // OK: const char* → string 是隐式的，构造函数非 explicit
    Wrapper<Path> b("dir");                 // OK: 直接初始化
    // Wrapper<Path> c = "dir";             // error: const char* → Path 是 explicit 的，于是 Wrapper 也是
    (void)a; (void)b;
}
```

标准库中 `std::pair`、`std::tuple`、`std::optional`、`std::expected` 等类型的构造函数都按这种方式规定为 `explicit(see below)`。

### `(` 总是属于 explicit-specifier

¶4 最后一句规定，紧跟在 `explicit` 后面的 `(` 总是解析为 *explicit-specifier* 的一部分。这消除了歧义，但也造成了 C++17 到 C++20 的一处不兼容。C++17 中构造函数的声明符可以加括号，`explicit (S)(const S&);` 是一个合法的 explicit 复制构造函数声明；C++20 起它被解析为 `explicit(S)`，而 `S` 不是表达式，于是非良构（[[diff.cpp17.class#1]]）。如果想保留带括号的声明符，可以写成 `explicit(true) (S)(const S&);`。转换函数 `explicit (operator int)();` 同理。

```cpp error
struct S {
    explicit (S)(const S&);    // C++17: OK，声明符 (S) 加了括号；C++20 起 error
};
```

!!! impl "实现视角"
    - `explicit(expr)` 中的表达式可以是值依赖的，在模板实例化时求值。Clang 对窄化的诊断文本类似 "explicit specifier argument evaluates to 2, which cannot be narrowed to type 'bool'"。
    - `explicit` 不影响函数的类型、mangled 名或 ABI，它只是重载决议阶段的一个过滤条件。因此不能用 `explicit` 来区分重载。

!!! history "历史与演进"
    - C++98：函数说明符有 `virtual`、`explicit`、`inline` 三个。其中 `explicit` 仅用于单参数构造函数，实际作用于转换构造函数。
    - C++11：`explicit` 可用于转换函数（`explicit operator bool`）；`explicit` 构造函数影响列表初始化，因此对多参数构造函数也有意义。`override`/`final` 以 *virt-specifier* 的形式加入，它们不是函数说明符。
    - C++17：`inline` 可用于变量，从函数说明符中移出，成为独立的 *decl-specifier*；推导指引可以是 `explicit` 的。
    - C++20：`explicit(bool)`（[[P0892R2]]）；虚函数可以是 `constexpr`。

!!! pitfall "常见误解"
    - 误以为派生类的覆盖函数要写 virtual 才是虚函数。其实不需要，覆盖函数自动是虚函数，写 `override` 更好。
    - 误以为 explicit 只对单参数构造函数有意义。C++11 起它也阻止复制列表初始化。
    - 误以为 explicit 转换函数完全不能隐式使用。上下文转换为 bool 是例外。

!!! summary "小结"
    | 说明符 | 适用 | 位置 | 效果 |
    |---|---|---|---|
    | `virtual` | 非静态成员函数 | 只在类内初始声明 | 动态派发（[[class.virtual]]） |
    | `explicit` / `explicit(true)` | 构造函数、转换函数 | 只在类定义内 | 不参与复制初始化 / 隐式转换 |
    | `explicit(false)` | 同上 | 同上 | 等于没写 |
    | `explicit(expr)` | 同上 | 同上 | `expr` 必须是不窄化的 bool 常量表达式 |

!!! question "思考题"
    下面两个变量的初始化是否良构？

    ```cpp
    struct A { explicit A(int, int); };
    A f() { return {1, 2}; }
    A a{1, 2};
    ```

<details markdown="1">
<summary>答案</summary>

`return {1, 2};` 是复制列表初始化。重载决议会考虑 explicit 构造函数，但如果选中的是 explicit 构造函数，程序就非良构（[[over.match.list]]）。所以 `f` 非良构。`A a{1, 2};` 是直接列表初始化，良构。注意，考虑但选中即报错，与根本不考虑是两回事：如果还有一个非 explicit 的 `A(long, long)`，`return {1, 2};` 依然会选中更匹配的 explicit `A(int, int)` 并报错，而不会退而选择 `A(long, long)`。
</details>
