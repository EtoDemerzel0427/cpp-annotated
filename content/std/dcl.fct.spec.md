---
title: 函数说明符
summary: 函数说明符只有 virtual 和 explicit 两个：它们能写在哪些声明上，explicit(bool) 怎样按条件决定是否 explicit，以及 explicit 后面的括号造成的一处 C++20 不兼容。
status: done
since: c++98
papers: P0892R2
related: class.virtual, class.conv.ctor, class.conv.fct, over.match.copy, over.match.list, temp.deduct.guide
tags: 声明, 说明符, explicit, virtual
updated: 2026-10-19
---

!!! tldr
    - 函数说明符只有 `virtual` 和 `explicit` 两个，都只能写在类定义里的成员函数声明上，不能写在类外定义上。
    - `virtual` 只用于非静态成员函数的初始声明；派生类里的覆盖函数不写 `virtual` 也是虚函数。
    - `explicit` 只用于构造函数和转换函数，让它们不参与隐式转换和复制初始化。
    - C++20 的 `explicit(条件)` 按一个 bool 常量表达式决定函数是否 explicit；这个表达式不允许窄化。
    - `explicit` 后面紧跟的 `(` 一律当作 `explicit(条件)` 的开头，所以 C++17 的 `explicit (S)(const S&);` 在 C++20 中不再合法。

C++ 的**函数说明符**（*function-specifier*）只剩两个：`virtual` 和 *explicit-specifier*（`explicit` 或 `explicit(常量表达式)`）。这一节只规定它们能写在哪里，语义分别在 [[class.virtual]]（虚函数与覆盖）和 [[class.conv.ctor]]、[[class.conv.fct]]（转换构造函数与转换函数）。C++17 之前 `inline` 也是函数说明符；它后来也能用于变量，于是有了单独的 [[dcl.inline]]。

## 只能用于函数，且不能重复（¶1）

```cpp error
virtual int x;                        // error: virtual 只能用于函数
struct S {
    explicit explicit(true) S(int);   // error: 两个 explicit-specifier
    virtual virtual void f();         // error: virtual 重复（Clang 只给警告）
};
```

¶1 函数说明符只能出现在函数声明中。一个声明的说明符序列里，*explicit-specifier* 和 `virtual` 都至多出现一次。

## virtual 写在类内的初始声明上（¶2）

```cpp run ok
struct B {
    virtual void f();       // 初始声明：在这里写 virtual
    virtual ~B() = default;
};
void B::f() { }             // 类外定义：不能再写 virtual
int main() { B b; b.f(); }
```

¶2 `virtual` 只能用于非静态成员函数的**初始声明**，也就是类定义里第一次声明它的那一处。下面每一行都违反了这条规则：

```cpp error
struct B { virtual void f(); };
virtual void B::f() { }                  // error: 类外定义不是初始声明
struct C { virtual static void g(); };   // error: 静态成员函数不能是虚的
virtual void free_function();            // error: 不是成员函数
struct D { friend virtual void h(); };   // error: 友元函数不是 D 的成员
```

一个函数是不是虚函数，决定了类里要不要有虚表指针、虚表里有哪些槽位，类定义结束时就必须确定。类外定义只提供函数体，不能再改变类的结构。

派生类中覆盖了基类虚函数的函数，即使不写 `virtual` 也是虚函数（[[class.virtual#2]]）。推荐在覆盖函数上写 `override`，它是 *virt-specifier*，不是函数说明符，作用是让编译器检查这个函数确实覆盖了某个虚函数。

## explicit 用于构造函数和转换函数（¶3）

```cpp run ok
struct Handle {
    explicit Handle(int fd) : fd(fd) { }
    explicit operator bool() const { return fd >= 0; }
    int fd;
};
void take(Handle) { }
int main() {
    Handle h(3);           // OK: 直接初始化
    Handle h2{4};          // OK: 直接列表初始化
    // Handle h3 = 5;      // error: 复制初始化
    // take(6);            // error: 传参也是复制初始化
    // Handle h4 = {7};    // error: 选中了 explicit 构造函数
    take(Handle(6));       // OK: 显式转换
    if (h) { }             // OK: 按上下文转换为 bool
    // bool b = h;         // error: 复制初始化
    bool b2 = static_cast<bool>(h2);
    return b2 ? 0 : 1;
}
```

¶3 *explicit-specifier* 只能用在类定义内、构造函数或转换函数的声明上。类外定义不能再写 `explicit`，普通成员函数也不能写：

```cpp error
struct S {
    explicit S(int);
    explicit void f();     // error: 不是构造函数或转换函数
};
explicit S::S(int) { }     // error: 不在类定义内
```

推导指引也可以带 *explicit-specifier*，那是推导指引自己的语法，见 [[temp.deduct.guide]]。

`explicit` 的效果分散在初始化和重载决议的各节，归纳起来是：

- **复制初始化**（`T x = a;`、按值传参、按值返回）不考虑 explicit 构造函数（[[over.match.copy]]）。
- **复制列表初始化**（`T x = {a, b};`、`return {a, b};`）会把 explicit 构造函数也放进重载决议；如果最后选中的是它，程序非良构（[[over.match.list]]）。
- 直接初始化、直接列表初始化和显式转换可以使用 explicit 构造函数。
- explicit 转换函数只用于直接初始化、显式转换，以及按上下文转换为 bool（`if (x)`、`!x`、`x && y`）。`explicit operator bool()` 的惯用法就靠这一点（[[class.conv.fct]]）。

因为第二条，`explicit` 对多参数构造函数同样有意义：它禁止 `T x = {a, b};` 和 `return {a, b};` 这类写法。

## explicit(条件) {{c++20}}

### 用一个构造函数表达条件性 explicit

```cpp run ok
#include <type_traits>
#include <string>
template<class T>
struct Wrapper {
    T value;
    template<class U>
        requires std::is_constructible_v<T, U>
    explicit(!std::is_convertible_v<U, T>)   // U 不能隐式转换为 T 时才 explicit
    Wrapper(U&& u) : value(static_cast<U&&>(u)) { }
};

struct Path { explicit Path(const char*) { } };

int main() {
    Wrapper<std::string> a = "hello";   // OK: const char* 能隐式转换为 string
    Wrapper<Path> b("dir");             // OK: 直接初始化
    // Wrapper<Path> c = "dir";         // error: 这个特化的构造函数是 explicit 的
    (void)a; (void)b;
}
```

`Wrapper<T>` 想做到：`U` 能隐式转换成 `T` 时，`Wrapper<T>` 也能从 `U` 隐式构造；否则只能显式构造。C++17 里只能写两个几乎一样的构造函数，一个带 `explicit`、一个不带，再用 SFINAE 让它们互斥。`explicit(条件)` 让一个构造函数就够了（[[P0892R2]]）。标准库的 `std::pair`、`std::tuple`、`std::optional`、`std::expected` 等的构造函数都写成 `explicit(see below)`，指的就是这种条件。

### 条件必须是不窄化的 bool 常量（¶4）

¶4 括号里的表达式必须是**按上下文转换为 bool 的常量表达式**（contextually converted constant expression of type bool，[[expr.const.const]]）。值为 `true` 时函数是 explicit 的，否则不是。不带括号的 `explicit` 等价于 `explicit(true)`。

这种常量表达式不允许窄化转换，所以 `explicit(2)` 不行：

```cpp error
struct S {
    explicit(sizeof(char[2])) S(char);  // error: 2 → bool 是窄化转换
    explicit(sizeof(char)) S(bool);     // OK: 1 → true 不窄化
    explicit(2 > 1) S(int);             // OK: 本来就是 bool
};
```

`static_assert` 和 `if constexpr` 的条件则不同，C++23 起允许窄化到 bool（[[dcl.pre#13]]），`static_assert(sizeof(char[2]))` 是合法的。

### 括号总是属于 explicit

¶4 最后一句规定，紧跟在 `explicit` 后面的 `(` 一律解析为 *explicit-specifier* 的一部分。这消除了歧义，代价是一处 C++17 到 C++20 的不兼容（[[diff.cpp17.class#1]]）：

```cpp error
struct S {
    explicit (S)(const S&);   // C++17: explicit 复制构造函数，声明符加了括号
                              // C++20: 被读成 explicit(S)，S 不是表达式，error
};
```

C++17 允许给构造函数的声明符加括号，所以这一行原本是一个 explicit 复制构造函数。现在要保留括号，就写 `explicit(true) (S)(const S&);`。

!!! impl "实现视角"
    - `explicit(条件)` 中的表达式可以依赖模板参数，在实例化时求值。本机 Clang 23 对窄化的诊断是 "explicit specifier argument evaluates to 2, which cannot be narrowed to type 'bool'"。
    - `explicit` 不属于函数类型，也不进入修饰名，只是重载决议时的一个过滤条件，所以不能靠有无 `explicit` 来重载。

!!! history "历史与演进"
    - C++98：函数说明符有 `virtual`、`explicit`、`inline` 三个，`explicit` 只对构造函数有效。
    - C++11：`explicit` 可用于转换函数；列表初始化出现后，`explicit` 对多参数构造函数也有了意义。`override` 和 `final` 以 *virt-specifier* 的形式加入。
    - C++17：`inline` 可用于变量，不再是函数说明符；推导指引可以带 `explicit`。
    - C++20：`explicit(条件)`（[[P0892R2]]）；虚函数可以是 `constexpr`。

!!! pitfall "常见误解"
    - 覆盖函数要写 `virtual` 才是虚函数：不需要，覆盖函数自动是虚函数，写 `override` 更好。
    - explicit 只对单参数构造函数有意义：C++11 起它也影响复制列表初始化。
    - explicit 转换函数完全不能隐式使用：按上下文转换为 bool 是例外。

!!! summary "小结"
    | 说明符 | 适用于 | 位置 | 效果 |
    |---|---|---|---|
    | `virtual` | 非静态成员函数 | 只在类内初始声明 | 动态派发（[[class.virtual]]） |
    | `explicit`、`explicit(true)` | 构造函数、转换函数 | 只在类定义内 | 不用于复制初始化和隐式转换 |
    | `explicit(false)` | 同上 | 同上 | 等于没写 |
    | `explicit(条件)` | 同上 | 同上 | 条件必须是不窄化的 bool 常量表达式 |

!!! question "思考题"
    下面的 `return` 语句和变量 `a` 的初始化是否良构？

    ```cpp
    struct A { explicit A(int, int); A(long, long); };
    A f() { return {1, 2}; }
    A a{1, 2};
    ```

<details markdown="1">
<summary>答案</summary>

`return {1, 2};` 是复制列表初始化。重载决议同时考虑 `A(int, int)` 和 `A(long, long)`，前者匹配得更好，被选中；它是 explicit 的，所以 `f` 非良构（[[over.match.list]]）。编译器不会退而选择 `A(long, long)`，本机 Clang 23 报 "chosen constructor is explicit in copy-initialization"。

`A a{1, 2};` 是直接列表初始化，可以使用 explicit 构造函数，良构。
</details>
