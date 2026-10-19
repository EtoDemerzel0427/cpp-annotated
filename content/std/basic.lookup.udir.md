---
title: using 指令与命名空间别名中的查找
summary: 在 using namespace 和 namespace A = 中，查找命名空间名以及前缀里的名字时只考虑命名空间，同名的变量和类型一律跳过。
status: done
related: basic.lookup, namespace.udir, namespace.alias, basic.lookup.qual, basic.lookup.unqual, basic.namespace
tags: 名字查找, 命名空间, using 指令
updated: 2026-10-19
---

!!! tldr
    - 在 `using namespace X::Y;` 和 `namespace A = X::Y;` 中，`X` 和 `Y` 都只按命名空间名查找，命名空间别名也算。
    - 同名的局部变量、成员类在这里不会挡住命名空间。
    - 普通的 `X::` 还要考虑类型，这里连类型也跳过，因为类里不可能有命名空间。

## 只考虑命名空间名（¶1）

```cpp run error
namespace X { namespace Y { int v = 1; } }

struct S {
    struct X { struct Y {}; };          // 类作用域里的同名类 X
    int f() {
        using namespace X::Y;           // OK：X 只考虑命名空间，找到 ::X
        namespace Z = X::Y;             // OK：同上
        return v + Z::v;                // ::X::Y::v
    }
    int g() {
        return X::Y::v;                 // error: 普通查找找到类 S::X，S::X::Y 里没有 v
    }
};

void h() {
    int X = 0;                          // 对普通查找来说，局部变量 X 挡住了命名空间 X
    using namespace X;                  // OK：只考虑命名空间名
    namespace A = X;                    // OK
    (void)X;
}
```

同一个 `X::Y`，在 `g` 的表达式里被成员类 `S::X` 挡住，在 `f` 的 using 指令和别名定义里却不会。

¶1 在 using 指令和命名空间别名定义（[[namespace.alias]]）中，查找命名空间名、以及它前面 `X::` 前缀里的名字时，只考虑命名空间名。

!!! std
    In a using-directive or namespace-alias-definition, during the lookup for a namespace-name or for a name in a nested-name-specifier only namespace names are considered.

这两个地方只能接受命名空间：using 指令提名一个命名空间，别名代表的也是命名空间（[[namespace.alias#4]]）。考虑别的东西没有意义，只会让无关的名字挡住命名空间。

普通的 `X::` 则不同。按 [[basic.lookup.qual#1]]，`X::m` 里的 `X` 还要考虑类型，因为 `m` 可能是类成员。而在 `using namespace X::Y;` 中，就算 `X` 是类，`X::Y` 也不可能是命名空间，所以连类型也可以跳过。

别名本身是命名空间名，所以可以出现在别的别名定义里：

```cpp run ok
namespace very_long_library_name { namespace detail { int k = 0; } }
namespace lib = very_long_library_name;
namespace det = lib::detail;           // lib 是别名，按命名空间名找到
int r = det::k;
```

## 相关规则

- 本节只管怎样找到被提名的命名空间。找到之后，using 指令如何影响后续查找，见 [[basic.lookup.unqual#1]]（无限定查找）和 [[namespace.qual]]（限定查找）。
- using 指令里的名字不能是依赖名（[[namespace.udir#1]]），using 指令也不能写在类作用域里（[[namespace.udir#2]]）。上例中的 using 指令写在成员函数体里，属于块作用域，所以合法。
- {{c++26}} using 指令和别名定义还可以用拼接：`using namespace [:r:];`、`namespace A = [:r:];`，`r` 必须代表全局命名空间以外的某个命名空间（[[namespace.udir#1]]、[[namespace.alias#2]]）。拼接不做名字查找，本节的规则不适用。

!!! impl "实现视角"
    Clang 解析 using 指令和命名空间别名时，用的是只匹配命名空间的专门查找（`LookupNamespaceName`）。所以名字只被其他实体占用时，它报告 expected namespace name，而不是二义或类型错误。

!!! history "历史与演进"
    这条规则从 C++98 起就有，文字几乎没变。C++23 的 [[P1787R6]] 保留了它；C++26 为 using 指令和别名定义增加了拼接形式。

## 思考题

!!! question "思考题"
    ```cpp
    namespace N { int x = 1; }
    namespace M { namespace N = ::N; }   // 别名
    void f() {
        struct N { };                    // 局部类 N
        using namespace M::N;            // (1)
        int y = x;                       // (2)
    }
    ```
    (1)、(2) 合法吗？`x` 是哪个？

<details markdown="1">
<summary>答案</summary>

(1) 合法。`M` 只按命名空间名查找，找到 `::M`；`N` 在 `M` 中查找，同样只考虑命名空间名，找到别名 `M::N`，也就是 `::N`。局部类 `N` 不在 `M::` 的查找范围内，与此无关。

(2) 合法。using 指令提名 `::N`。按 [[basic.lookup.unqual#2]]，`::N` 的成员在同时包含这条指令和 `::N` 的最近一层，也就是全局命名空间这一层参与查找，所以 `x` 是 `N::x`。本机 Clang 23 编译通过。
</details>
