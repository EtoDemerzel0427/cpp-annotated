---
title: using 指令与命名空间别名中的查找
summary: 在 using namespace … 与 namespace A = … 中，查找命名空间名及其嵌套名说明符里的名字时只考虑命名空间名，同名的变量、类型一律忽略。
status: done
related: basic.lookup, namespace.udir, namespace.alias, basic.lookup.qual, basic.lookup.unqual, basic.namespace
tags: 名字查找, 命名空间, using 指令
updated: 2026-10-17
---

这是第 6.5 节最短的一条，只有一段：

!!! std
    In a using-directive or namespace-alias-definition, during the lookup for a namespace-name or for a name in a nested-name-specifier only namespace names are considered.

    在 *using-directive* 或 *namespace-alias-definition* 中，查找 *namespace-name* 以及 *nested-name-specifier* 中的名字时，只考虑命名空间名。

## 释义（¶1）

¶1 涉及以下两种声明：

```cpp ok
#include <chrono>
#include <filesystem>
using namespace std::chrono;            // using-directive（[namespace.udir]）
namespace fs = std::filesystem;         // namespace-alias-definition（[namespace.alias]）
```

在这两种语境中，无论 `std`、`chrono`、`filesystem` 是最终的 *namespace-name*，还是前面 *nested-name-specifier* 里的组件，查找时都**只考虑命名空间名**（包括命名空间别名，它也是 *namespace-name*）。变量、函数、类型、模板即使同名并且在更内层，也当作不存在。

### 原因

这两种语境在文法上只能接受命名空间：using 指令提名命名空间，别名的底层实体是命名空间（[[namespace.alias#4]]）。所以查找时考虑别的东西没有意义，只会造成被无关名字挡住的错误。

这与一般的 *nested-name-specifier* 查找形成对比。按 [[basic.lookup.qual#1]]，对普通的 `X::` 中的 X，查找考虑命名空间与类型，因为普通的 `X::m` 可以是类成员。而在 `using namespace X::Y;` 中，即使 X 是一个类，`X::Y` 也不可能是命名空间（类里不能声明命名空间），所以连类型也可以排除。

```cpp run error
namespace X { namespace Y { int v = 1; } }

struct S {
    struct X { struct Y {}; };          // 类作用域里的同名类 X
    int f() {
        using namespace X::Y;           // OK：X 只考虑命名空间 → ::X，忽略 S::X
        namespace Z = X::Y;             // OK：同上
        return v + Z::v;                // ::X::Y::v
    }
    int g() {
        return X::Y::v;                 // error: 普通 nns 查找找到类 S::X，S::X::Y 是类，没有 v
    }
};

void h() {
    int X = 0;                          // 局部变量隐藏了命名空间 X（对普通查找而言）
    using namespace X;                  // OK：只考虑命名空间名
    namespace A = X;                    // OK
    (void)X;
}
```

对比 `g` 与 `f`：同一个 `X::Y`，在普通表达式里会被成员类 `S::X` 挡住，在 using 指令与别名定义中则不会。

## 与其他条款的关系

- 本节只规定怎样找到被提名的命名空间；找到之后，using 指令怎样影响后续查找，见 [[basic.lookup.unqual#1]]（活跃的 using 指令、无限定搜索）与 [[namespace.qual]]（限定查找中的传递）。
- [[namespace.udir#1]] 规定，using 指令的 *nested-name-specifier* 与 *namespace-name* 不得是依赖的；using 指令也不得出现在类作用域中（[[namespace.udir#2]]）。上例中的 using 指令写在成员函数体（块作用域）里，因此合法。
- 从 C++26 起 {{c++26}}，using 指令与别名定义还可以使用 *splice-specifier*：`using namespace [:r:];`、`namespace A = [:r:];`，其中 `r` 必须是指代非全局命名空间的反射（[[namespace.udir#1]]、[[namespace.alias#2]]）。splice 不涉及名字查找，本节的规则不适用于它。

## 命名空间别名

在别名定义 `namespace A = X::Y;` 中，`X` 与 `Y` 都按本节只考虑命名空间名。别名本身是 *namespace-name*，所以也可以给别名再起别名：

```cpp run ok
namespace very_long_library_name { namespace detail { int k = 0; } }
namespace lib = very_long_library_name;
namespace det = lib::detail;           // lib 是别名，也是命名空间名，被考虑
int r = det::k;
```

!!! impl "实现视角"
    Clang 在解析 using 指令与命名空间别名时使用专门的查找种类（只匹配命名空间的 `LookupNamespaceName`），因此诊断也不同：若名字只被其他实体占用，它报告"期望命名空间名"，而不是二义或类型错误。

!!! history "历史与演进"
    本规则从 C++98 起就存在（早期标准中位于 [basic.lookup.udir]，文字几乎未变）。C++23 的 P1787R6 保留了它；C++26 为 using 指令与别名增加了 *splice-specifier* 形式。

## 思考题

!!! question "思考题"
    ```cpp
    namespace N { int x = 1; }
    struct N2 { };
    namespace M { namespace N = ::N; }   // 别名
    void f() {
        struct N { };                    // 局部类 N
        using namespace M::N;            // (1)
        int y = x;                       // (2)
    }
    ```
    (1)(2) 合法吗？`x` 是哪个？

<details markdown="1">
<summary>答案</summary>

(1) 合法：`M` 只考虑命名空间，找到 `::M`；`N` 在 M 中查找（同样只考虑命名空间名），找到别名 `M::N`，即 `::N`。局部类 `N` 与此无关（它甚至不在 `M::` 的查找范围内）。

(2) 合法：using 指令提名 `::N`；按 [[basic.lookup.unqual#2]]，`::N` 在同时包含指令与 `::N` 的最近作用域，即全局这一层并入，`x` 沿作用域链在全局层找到 `N::x`。
</details>

## 小结

- 在 `using namespace …;` 与 `namespace A = …;` 中，查找只看命名空间名（含别名）。
- 与普通的 *nested-name-specifier* 不同，这里连类型也被忽略，因为那里不可能出现类。
- 被局部变量、成员类等隐藏的命名空间名，在这两种语境中依然可以使用。
