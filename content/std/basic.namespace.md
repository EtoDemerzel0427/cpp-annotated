---
title: 命名空间
summary: 命名空间可以分多处定义；内联命名空间与库版本化/ABI；嵌套命名空间定义 a::inline b::c；无名命名空间等价于唯一名字加 using 指令，并带来内部链接；命名空间别名；using 指令的传递性，以及名字如同在最近公共外层命名空间中声明的查找规则
status: done
covers: basic.namespace.general, namespace.def, namespace.def.general, namespace.unnamed, namespace.alias, namespace.udir
papers: N2535, N4230, P1094R2, N4266
related: basic.scope.namespace, basic.lookup.unqual, basic.lookup.qual, basic.lookup.udir, basic.lookup.argdep, basic.link, namespace.udecl, module.interface, temp.expl.spec
tags: 命名空间, 名字查找, 链接, ABI
updated: 2026-10-17
---

命名空间（namespace）解决的是大型程序中的名字冲突：两个库都想定义 `log`、`vector`、`detail::impl`，命名空间让它们各自处在不同的作用域里。和类不同，命名空间是**开放**的，同一个命名空间可以在许多文件、许多位置反复打开并追加成员。

本页覆盖 [basic.namespace] 整节：命名空间的一般性质（[basic.namespace.general]）、命名空间定义与内联命名空间（[namespace.def]）、无名命名空间（[namespace.unnamed]）、命名空间别名（[namespace.alias]）和 using 指令（[namespace.udir]）。与之密切相关的有：命名空间作用域（[[basic.scope.namespace]]）、限定名查找（[[basic.lookup.qual]]，尤其是 [[namespace.qual]]）、无限定名查找中 using 指令的作用（[[basic.lookup.unqual]]）、查找 using 指令和别名中的命名空间名（[[basic.lookup.udir]]）。using 声明是另一回事，见 [[namespace.udecl]]。

## 命名空间是什么（[basic.namespace.general]）

¶1 规定，命名空间是一个可选具名的实体，其作用域可以包含任何种类实体的声明。通过命名空间的名字可以访问属于它的实体，即命名空间的成员。与其他实体不同，命名空间的定义**可以拆分**到一个或多个翻译单元、模块中的多个部分。

¶2（注）说明了命名空间与模块的关系：

- 一个 *namespace-definition* 只要包含任何 *export-declaration*，它就是导出的；
- 命名空间**永远不附属于具名模块**，名字也永远没有模块链接。

```cpp title="namespace-module.cpp"
export module M;
namespace N1 {}                  // N1 未导出
export namespace N2 {}           // N2 导出
namespace N3 { export int n; }   // N3 也导出（因为含导出声明）
```

为什么命名空间不附属于模块？因为不同模块完全可能往同一个命名空间（比如 `std` 或公司的顶层命名空间）里添加成员；如果命名空间属于第一个声明它的模块，第二个模块就无法再打开它。

¶3 规定，存在一个[[g:global-namespace|全局命名空间]]（global namespace），它没有声明（[[basic.scope.namespace]]），属于全局作用域；它不是无名命名空间。注 2 指出，既然没有声明，名字查找就找不到它，`::x` 中的 `::` 是语法，不是查找。所以 [[namespace.alias#2]] 和 [[namespace.udir#1]] 都要求 *splice-specifier* 不得指代全局命名空间（反射可以得到 `^^::`，但不能用它来声明别名或 using 指令）。

## 命名空间定义（[namespace.def.general]）

```text
named-namespace-definition:
    inline(opt) namespace attribute-specifier-seq(opt) identifier { namespace-body }
unnamed-namespace-definition:
    inline(opt) namespace attribute-specifier-seq(opt) { namespace-body }
nested-namespace-definition:
    namespace enclosing-namespace-specifier :: inline(opt) identifier { namespace-body }
enclosing-namespace-specifier:
    identifier | enclosing-namespace-specifier :: inline(opt) identifier
```

### 只能在命名空间作用域中（¶1）

¶1 规定，每个 *namespace-definition* 必须位于命名空间作用域（[[basic.scope.namespace]]）。函数体内、类内都不能定义命名空间。

### 定义还是扩展？（¶2）

¶2 规定，对具名命名空间定义 D，在 D 所在的命名空间 A 及 A 的内联命名空间集合中搜索其标识符：

- 找到某个命名空间 N 的 *namespace-definition*：D **扩展**（extends）N，D 的目标作用域是 N 所属的作用域；
- 什么都没找到：把这个标识符作为 *namespace-name* 引入 A。

两个细节值得注意：

1. 搜索范围包括 A 的内联命名空间集合。所以 `namespace std { inline namespace __1 { namespace ranges {} } }` 之后，在 `std` 中再写 `namespace ranges { ... }` 扩展的是 `std::__1::ranges`，而不是新建 `std::ranges`。内联命名空间能够透明地工作，这是关键之一。
2. 找到的必须是命名空间定义。如果找到的是同名的变量、类或命名空间别名，就不是扩展，而这个新的命名空间名会与已有声明冲突，非良构。

```cpp title="namespace-extend.cpp" error
namespace lib { inline namespace v2 { namespace detail { int a; } } }
namespace lib { namespace detail { int b; } }   // 扩展 lib::v2::detail
int x = lib::v2::detail::b;                       // OK

namespace Alias = lib;
namespace Alias { }                               // error: Alias 是别名，不能被"扩展"
int Thing;
namespace Thing { }                               // error: 与变量 Thing 冲突
```

### 嵌套（¶3）

¶3 指出，命名空间定义本身是一个声明，可以出现在命名空间体中，所以可以嵌套。名字查找由内向外进行：

```cpp title="namespace-nested.cpp" ok
namespace Outer {
    int i;
    namespace Inner {
        void f() { i++; }    // Outer::i（Inner::i 还没声明）
        int i;
        void g() { i++; }    // Inner::i
    }
}

int main() {}
```

`f` 中的 `i` 找到的是 `Outer::i`，因为在 `f` 的位置，`Inner::i` 还没有声明，而无限定名查找只看之前的声明（[[basic.lookup.unqual]]）。

### 属性（¶5）

¶5 规定，*named-namespace-definition* 中的属性属于所定义或扩展的命名空间。实际有用的主要是 `[[deprecated]]`（C++17，[[N4266]]）：

```cpp title="namespace-deprecated.cpp" ok
namespace [[deprecated("use v2")]] v1 { inline void f() {} }
namespace v2 { inline void f() {} }

int main() {
    v2::f();
    // v1::f();   // 会产生弃用警告
}
```

## 内联命名空间（¶4、¶6–¶7）

¶4 规定，命名空间定义前带 `inline` 时，该命名空间声明为[[g:inline-namespace|内联命名空间]]（inline namespace）。扩展时也可以写 `inline`，但前提是最初声明这个命名空间名的定义写了 `inline`。

```cpp title="inline-reopen.cpp" error
namespace N {}
inline namespace N {}      // error: 原来不是内联的
inline namespace M {}
namespace M {}             // OK: 扩展时可以省略 inline（Clang 会警告）
```

¶6 列出了内联命名空间成员如同外层命名空间成员的四个具体方面：

1. **ADL**：内联命名空间与其外层命名空间，只要其中一个加入关联命名空间集合，另一个也会加入（[[basic.lookup.argdep]]）；
2. **无限定查找**：在外层命名空间中隐式插入一条指向内联命名空间的 using 指令，与无名命名空间的做法相同；
3. **模板**：内联命名空间中的模板可以如同外层命名空间的成员一样部分特化、显式实例化、显式特化，在外层命名空间里写特化即可；
4. **限定查找**：在外层命名空间中做限定查找时，即使外层命名空间中已有同名声明，也会包含内联命名空间的成员（[[namespace.qual]]）。

**第 4 点与普通 using 指令的行为不同**：对 `using namespace X;`，限定查找 `N::name` 只有在 N 自身找不到 `name` 时才会去看 X；对内联命名空间，两者同时考虑。

```cpp title="inline-namespace-lookup.cpp" error
namespace N {
    inline namespace V { int x; }
    int x;
}
int a = N::x;              // error: 有歧义——N::x 与 N::V::x 同时被找到（¶6 第 4 点）

namespace L {
    inline namespace v1 { struct S {}; }
    void f(S);
}
void t() {
    L::S s;                // OK: 限定查找穿透内联命名空间
    f(s);                  // OK: S 的关联命名空间 L::v1，连带 L，找到 L::f
}
```

¶7 规定，这些性质是传递的：N 含内联命名空间 M，M 又含内联命名空间 O，那么 O 的成员可以如同 M 或 N 的成员一样使用。N 的[[g:inline-namespace-set|内联命名空间集合]]（inline namespace set）是 N 中所有内联命名空间的传递闭包。

### 为什么需要内联命名空间：库版本化

内联命名空间（C++11，[[N2535]]）是为库的版本演进设计的。设想库的第一版是这样的：

```cpp
namespace lib { struct Widget { int a; }; void use(Widget); }
```

第二版需要改变 `Widget` 的布局。如果直接改，老代码编译出的目标文件与新库链接时，ABI 会悄无声息地不匹配。用内联命名空间可以这样写：

```cpp run title="versioning.cpp" ok
namespace lib {
    namespace v1 {
        struct Widget { int a; };
        inline int use(Widget w) { return w.a; }
    }
    inline namespace v2 {               // 当前默认版本
        struct Widget { int a; long b; };
        inline int use(Widget w) { return w.a + static_cast<int>(w.b); }
        template<class T> struct Box { T t; };
    }
}

template<> struct lib::Box<int> { int special; };   // 如同 lib 的成员一样特化（¶6 第 3 点）

int main() {
    lib::Widget w{1, 2};       // 实际上是 lib::v2::Widget
    lib::v1::Widget old{3};    // 旧版本仍然可以显式使用
    lib::Box<int> b{4};
    return lib::use(w) + lib::v1::use(old) + b.special;
}
```

用户源代码写 `lib::Widget`，不需要知道版本号；但修饰名中包含 `v2`（`lib::v2::Widget` 编码为 `N3lib2v26WidgetE`），所以链接老版本的目标文件时会得到**链接错误**，而不是没有任何提示的运行时崩溃。

!!! impl "标准库实现中的内联命名空间"
    - **libc++** 把几乎所有内容放在 `std::__1`（`_LIBCPP_ABI_NAMESPACE`，可配置）中。所以在 macOS 上 `std::string` 的修饰名中能看到 `NSt3__1...`。这让同一个进程里可以并存不同 ABI 版本的 libc++。
    - **libstdc++** 在 GCC 5 的双 ABI 迁移中用内联命名空间 `std::__cxx11` 放置新的 `std::string`、`std::list` 等（C++11 要求 `std::string` 不能写时复制、`list::size()` 为 O(1)，必须改布局）。它还额外加了 GCC 的 `abi_tag` 属性，让返回这些类型的函数的修饰名也随之改变。
    - 内联命名空间对 ADL 和特化透明，这正是标准库能用它而不破坏用户代码（例如用户对 `std::hash` 的特化）的原因。

## 嵌套命名空间定义（¶8）

¶8 规定，*nested-namespace-definition* `namespace E::I { B }` 等价于 `namespace E { inline(opt) namespace I { B } }`，当且仅当 `I` 前写了 `inline` 时才带 `inline`。由于 *enclosing-namespace-specifier* 本身也可以带 `inline`，递归展开即可。

```cpp title="nested-namespace-def.cpp" error
namespace A::inline B::C {     // C++20
    int i;
}
// 等价于：namespace A { inline namespace B { namespace C { int i; } } }
int j = A::C::i + A::B::C::i;  // OK: 两种写法都行

namespace X::Y { }             // OK (C++17)
inline namespace Z::W { }      // error: 嵌套命名空间定义的开头不能写 inline
```

C++17 引入 `namespace a::b::c`（[[N4230]]），但不允许其中任何一段是内联的；C++20（[[P1094R2]]）允许在除第一段以外的任何位置写 `inline`。第一段不能是内联的，因为在语法上，`inline namespace A::B` 中的 `inline` 修饰的是哪一段会有歧义；要让第一段内联，仍然得用传统写法。

## 无名命名空间（[namespace.unnamed]）

¶1 规定，*unnamed-namespace-definition* 的行为如同将它替换为：

```text
inline(opt) namespace unique { /* 空 */ }
using namespace unique;
namespace unique { namespace-body }
```

其中 `inline` 当且仅当原定义写了 `inline` 时出现；一个翻译单元中所有的 *unique* 都替换为同一个标识符，而这个标识符与程序中所有其他标识符都不同。属性属于 *unique*。

这三行等价代码精确地定义了无名命名空间的全部行为：

1. 第一行先声明命名空间，让第二行的 using 指令有可指代的对象；
2. 第二行的 using 指令让成员在外层作用域可以无限定使用；
3. 第三行放入实际内容；
4. 同一 TU 中所有无名命名空间是同一个命名空间（可以反复打开）；不同 TU 中则各不相同。

```cpp title="unnamed-namespace.cpp" error
namespace { int i; }             // unique::i
void f() { i++; }                // unique::i++

namespace A {
    namespace {
        int i;                   // A::unique::i
        int j;                   // A::unique::j
    }
    void g() { i++; }            // A::unique::i++
}

using namespace A;
void h() {
    i++;                         // error: unique::i 还是 A::unique::i？
    A::i++;                      // OK: A::unique::i
    j++;                         // OK: A::unique::j
}
```

`h` 中的 `i++` 有歧义：`::unique::i` 和 `A::unique::i` 都经由 using 指令出现在全局命名空间中（见下文 ¶3 的规则），两者都不是函数，因而冲突。

### 无名命名空间与内部链接

[namespace.unnamed] 本身没有提到链接，但 [[basic.link#4]] 规定：**无名命名空间或其中（直接或间接）声明的命名空间具有内部链接**，其中声明的名字（变量、函数、类、枚举、模板等）随之具有内部链接。所以无名命名空间是表达本 TU 私有的标准写法，比 `static` 更通用，因为 `static` 不能用于类型。

```cpp run title="unnamed-internal.cpp" ok
namespace {
    struct Helper { int v = 42; };      // 类型也是 TU 局部的
    int compute() { return Helper{}.v; }
}

int main() { return compute() - 42; }
```

!!! impl "修饰名"
    Itanium ABI 中无名命名空间编码为 `_GLOBAL__N_1` 这样的名字（GCC 和 Clang 都是）：例如上面的 `compute` 在 Clang 下修饰为 `_ZN12_GLOBAL__N_17computeEv`，并且是局部符号（`nm` 中显示为小写 `t`），不会参与跨 TU 的链接。内部链接还带来优化好处：编译器知道所有调用点，可以自由内联、删除未用函数、修改调用约定。

!!! history "C++03 中的无名命名空间"
    C++03 中无名命名空间的成员具有外部链接，只是名字唯一，其他翻译单元无法写出它。这导致一个奇怪的限制：模板实参必须具有外部链接，而 `static` 函数不行，无名命名空间中的函数却可以。C++03 还弃用了命名空间作用域对象上的 `static`，推荐用无名命名空间代替；C++11 把无名命名空间的成员改为内部链接，同时取消了对 `static` 的弃用。

!!! pitfall "头文件中的无名命名空间"
    在头文件中定义无名命名空间，每个包含它的 TU 都会得到一份独立的实体。对变量来说，这意味着每个 TU 有各自的副本；对头文件中的 `inline` 函数或模板来说，如果它们引用了无名命名空间中的实体，不同 TU 中的定义就引用了不同的实体，违反 ODR（[[basic.def.odr]]），属于 IFNDR。

## 命名空间别名（[namespace.alias]）

```text
namespace-alias-definition:
    namespace identifier = qualified-namespace-specifier ;
    namespace identifier = splice-specifier ;
```

- ¶2：*splice-specifier*（C++26 反射）必须指代一个不是全局命名空间的命名空间；
- ¶3：标识符成为一个[[g:namespace-alias|命名空间别名]]（namespace alias）；
- ¶4：别名的底层实体（underlying entity，[[basic.pre]]）是所指的命名空间。注 1 指出，查找 *namespace-name* 时只考虑命名空间名（[[basic.lookup.udir]]）。

```cpp title="namespace-alias.cpp" ok
namespace very::long_::library_name::v3 { int x = 1; }
namespace lib = very::long_::library_name::v3;

int f() { return lib::x; }

int g() {
    namespace fs_alias = lib;     // 块作用域中也可以
    return fs_alias::x;
}

int main() { return f() + g() - 2; }
```

别名只是一个同义词，不是新的命名空间：不能用别名扩展命名空间（见上文 ¶2 的例子），也不能用别名再次定义别名为别的命名空间（同一作用域中别名的重声明必须指代同一个命名空间）。

## using 指令（[namespace.udir]）

```text
using-directive:
    attribute-specifier-seq(opt) using namespace nested-name-specifier(opt) namespace-name ;
    attribute-specifier-seq(opt) using namespace splice-specifier ;
```

### 约束（¶1–¶2）

- ¶1：*splice-specifier* 不得指代全局命名空间；*nested-name-specifier*、*namespace-name*、*splice-specifier* 不得是待决的，因为 using 指令影响名字查找，必须在模板定义时就确定；
- ¶2：using 指令**不能出现在类作用域**，可以出现在命名空间作用域或块作用域。查找其中的 *namespace-name* 只考虑命名空间名。

```cpp title="udir-class.cpp" error
namespace M { int i; }
struct K {
    using namespace M;     // error: 类作用域中不允许 using 指令
};
```

为什么类里不行？类作用域的查找规则（[[class.member.lookup]]）基于在类及其基类中搜索声明，using 指令会让类的成员这一概念变得模糊：`K::i` 应该找到 `M::i` 吗？那 `M::i` 算不算 `K` 的成员？标准选择直接禁止。

### 名字如同在最近公共外层命名空间中声明（¶3–¶4）

¶3（注）中的这一句是 using 指令最核心、也最反直觉的规则：

!!! std
    During unqualified name lookup, the names appear as if they were declared in the nearest enclosing namespace which contains both the *using-directive* and the designated namespace.

    在无限定名查找中，这些名字如同声明在同时包含该 using 指令和被指定命名空间的最近外层命名空间中。

规范性的规则在 [[basic.lookup.unqual]]（活跃的 using 指令如何影响查找），这里只是总结。¶4（注）指出，**using 指令不引入任何名字**，它只改变查找的路径。

为什么是最近公共外层命名空间，而不是 using 指令所在的作用域？考虑下面的例子：

```cpp title="udir-nearest.cpp" error
namespace A {
    int i;
    namespace B {
        namespace C { int i; }
        using namespace A::B::C;
        void f1() { i = 5; }        // OK: C::i "如同在 B 中声明"，在查找到 A::i 之前找到
    }
    namespace D {
        using namespace B;
        using namespace C;
        void f2() { i = 5; }        // error: 歧义——B::C::i 还是 A::i？
    }
    void f3() { i = 5; }            // OK: A::i
}
void f4() { i = 5; }                // error: 哪个 i 都不可见
```

逐个分析如下。

- `f1`：using 指令在 B 中，指向 `A::B::C`。同时包含 B 和 C 的最近命名空间是 B，所以 `C::i` 如同声明在 B 中。查找从 `f1` 的块作用域向外进行，在 B 中（包括如同声明在 B 中的 `C::i`）找到之后就停止，不会看到 `A::i`。
- `f2`：D 中有两条 using 指令。对 `using namespace B;`，同时包含 D 和 B 的最近命名空间是 A，B 的成员如同在 A 中；而 B 中还有 `using namespace C;`（传递，¶5），C 的成员也如同在 A 中。对 D 中的 `using namespace C;`，同时包含 D 和 C 的最近命名空间也是 A。于是 A 中同时有 `A::i` 和 `C::i`，两者都不是函数，因此有歧义。
- `f4`：全局命名空间中没有 `i`，也没有任何 using 指令。

这样设计，是为了让 using 指令的效果与被指定命名空间的成员在名字层级上的位置一致：它们不应比所在的命名空间本身离使用点更近。如果 `using namespace std;` 让 `std` 的成员如同在当前函数中声明，当前命名空间中的同名实体就会被遮蔽，这对写 `using namespace` 的人来说更加危险。

### 传递性（¶5）

¶5（注）指出，using 指令是**传递**的：如果一个作用域含有指向某命名空间的 using 指令，而那个命名空间自己又含有 using 指令，后者指向的命名空间也会纳入考虑。

```cpp title="udir-transitive.cpp" error
namespace M { int i; }
namespace N {
    int i;
    using namespace M;
}
void f() {
    using namespace N;
    i = 7;                 // error: M::i 与 N::i 都可见
}
```

注意这里并没有 `N::i` 遮蔽 `M::i` 的效果：N 中的 using 指令让 `M::i` 如同在全局命名空间中声明（同时包含 N 和 M 的最近命名空间）；`f` 中的 using 指令让 `N::i` 也如同在全局命名空间中声明。两者处于同一层，因此有歧义。如果直接在 N 中查找（`N::i` 的限定查找），则 N 自己的声明优先，using 指令的目标只在 N 本身找不到时才纳入考虑（[[namespace.qual]]）。

### 之后添加的声明（¶6）

¶6（注）指出，在 using 指令之后加入被指定命名空间的声明，在它们出现之后也能通过该 using 指令找到。using 声明正好相反，它只引入声明时可见的那些声明（[[namespace.udecl#9]]）。

```cpp title="udir-later.cpp" ok
namespace A { void f(int) {} }
using namespace A;
namespace A { void f(char) {} }

void g() { f('a'); }        // 调用 A::f(char)：using 指令能看到后来的声明

int main() { g(); }
```

### 冲突与重载（¶7–¶8）

¶7（注）指出，如果名字查找在两个不同的命名空间中找到某个名字的声明，而它们不声明同一个实体，又不全是函数或函数模板，使用这个名字就非良构（[[basic.lookup]]）。特别地，在不同命名空间中声明的变量、函数或枚举量的名字不会隐藏类或枚举的名字（同一作用域内同名变量隐藏类名的规则不跨命名空间生效）。

```cpp title="udir-conflict.cpp" error
namespace A {
    class X { };
    extern "C"   int g();
    extern "C++" int h();
}
namespace B {
    void X(int);
    extern "C"   int g();
    extern "C++" int h(int);
}
using namespace A;
using namespace B;

void f() {
    X(1);          // error: X 在两个命名空间中被找到
    g();           // OK: A::g 和 B::g 是同一个 extern "C" 函数（[dcl.link]/7）
    h();           // OK: 都是函数，重载决议选 A::h
}
```

`g()` 合法这一点值得留意：两个命名空间中的 `extern "C" int g()` 声明的是同一个实体（C 语言链接的函数没有命名空间概念，见 [[dcl.link#7]]），所以不冲突。

¶8（注）指出，命名空间的考虑顺序以及 using 指令之间的关系**不影响重载决议**；即使两个签名相同的函数中，一个所在的命名空间经由 using 指令可以到达另一个所在的命名空间，也不会因此排除其中某一个。脚注 76 对比了类层次中的查找：类成员查找可以依据沿某条路径一个成员隐藏另一个来消解歧义（[[class.member.lookup]]），而 using 指令没有这种机制。

```cpp title="udir-overload.cpp" error
namespace D {
    int d1;
    void f(char);
}
using namespace D;

int d1;              // OK: 与 D::d1 不冲突（声明本身没问题）

namespace E {
    int e;
    void f(int);
}

namespace D {        // 扩展 D
    int d2;
    using namespace E;
    void f(int);
}

void f() {
    d1++;            // error: ::d1 还是 D::d1？
    ::d1++;          // OK
    D::d1++;         // OK
    d2++;            // OK: D::d2
    e++;             // OK: E::e
    f(1);            // error: D::f(int) 与 E::f(int) 有歧义
    f('a');          // OK: D::f(char)
}
```

`f(1)` 有歧义：`D::f(int)` 和 `E::f(int)` 签名相同，标准不会因为 D 经由 using 指令能到达 E 就让 D 的版本优先。两者都进入候选集，重载决议无法区分。

## 实现视角

!!! impl "命名空间在目标代码中"
    - 命名空间只存在于修饰名中：`a::b::f()` 在 Itanium ABI 中编码为 `_ZN1a1b1fEv`。内联命名空间也照常编码（这正是它用于 ABI 版本化的原理）；无名命名空间编码为 `_GLOBAL__N_1`；命名空间别名完全不出现在修饰名中。
    - 对于 using 指令的名字如同在最近公共外层命名空间中声明这条规则，实现通常这样处理：在查找到达每一层命名空间作用域时，额外检查在这一层生效的那些 using 指令的目标命名空间。Clang 的无限定查找实现就是按这个思路组织的：先收集所有活跃的 using 指令，为每条算出公共祖先命名空间，再在查找走到那一层时把目标命名空间一并搜索。
    - `using namespace std;` 在头文件中的危害是确定的：它让所有包含该头文件的 TU 都在全局命名空间看到 `std` 的全部名字（包括未来版本新增的名字），新标准增加一个名字就可能让原本无歧义的代码变得歧义。

## 历史与演进

!!! history "C++98 → C++26"
    - **C++98**：命名空间、无名命名空间（成员仍是外部链接）、命名空间别名、using 指令；弃用命名空间作用域对象上的 `static`。
    - **C++11**：内联命名空间（[[N2535]]）；无名命名空间成员改为内部链接，`static` 的弃用被撤销。
    - **C++17**：嵌套命名空间定义 `namespace a::b::c`（[[N4230]]）；命名空间和枚举量可以带属性（[[N4266]]）。
    - **C++20**：嵌套命名空间定义中可以写 `inline`（[[P1094R2]]）；引入模块，命名空间不附属于模块，含导出声明的命名空间定义视为导出。
    - **C++26**：静态反射加入 `namespace X = [: r :];` 与 `using namespace [: r :];`，*splice-specifier* 不得指代全局命名空间。

## 陷阱

!!! pitfall "using 指令不会让名字离使用点更近"
    在函数里写 `using namespace N;`，`N` 的成员并不如同在函数中声明，而是如同在 `N` 和当前位置的最近公共外层命名空间（通常是全局命名空间）中声明。因此当前命名空间中的同名实体会隐藏它们，局部变量当然也会。

!!! pitfall "内联命名空间中的同名声明不会被外层声明隐藏"
    `namespace N { inline namespace V { int x; } int x; }` 中 `N::x` 是歧义的，而对普通 using 指令则是 `N::x` 优先。

!!! pitfall "无名命名空间放在头文件里"
    每个 TU 得到独立的实体；如果 `inline` 函数或模板引用了这些实体，就违反 ODR。

## 思考题

!!! question "思考题 1"
    下面的代码中，`int l = k;` 为什么有歧义，而 `int m = i;` 没有？

    ```cpp
    namespace A { int i; }
    namespace B {
        int i;
        int j;
        namespace C {
            namespace D {
                using namespace A;
                int j;
                int k;
                int a = i;
            }
            using namespace D;
            int k = 89;
            int l = k;
            int m = i;
            int n = j;
        }
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `int a = i;`（在 D 中）：`using namespace A;` 让 `A::i` 如同在全局命名空间中声明（同时包含 D 和 A 的最近命名空间）。从 D 向外依次查找 D、C、B，在 B 中找到 `B::i` 后停止。所以结果是 `B::i`，`A::i` 实际上被隐藏了。
- `int l = k;`（在 C 中）：`using namespace D;` 让 D 的成员如同在 C 中声明（C 同时包含该指令和 D）。C 自己也有 `k`，于是 C 中同时有 `C::k` 和 `D::k`，两者都是变量，因此有歧义。
- `int m = i;`：D 的成员如同在 C 中，但 D 里没有 `i`；D 中的 `using namespace A;` 经传递性生效，`A::i` 如同在全局命名空间中。查找 C → B，在 B 中找到 `B::i`，停止。
- `int n = j;`：`D::j` 如同在 C 中，先于 B 被找到，所以是 `D::j`。
</details>

!!! question "思考题 2"
    为什么标准库实现可以把 `std::vector` 实际放在 `std::__1` 中，而用户写的 `template<> struct std::hash<MyType>` 仍然有效？如果把 `__1` 换成普通命名空间加 `using namespace __1;`，会出什么问题？

<details markdown="1">
<summary>答案</summary>

按 ¶6 第 3 点，内联命名空间的成员可以如同外层命名空间的成员一样显式特化，所以用户惯常的写法 `namespace std { template<> struct hash<MyType> { ... }; }` 会当作 `std::__1::hash` 的特化。

如果换成普通命名空间加 using 指令，在 C++11 的规则下这种写法是非良构的：当时 [temp.expl.spec] 要求不带限定的显式特化必须声明在模板最近的外层命名空间中；如果那个命名空间是内联的，则可以是它的外层命名空间集合中的任一个。对普通的 `std::__1`，只有在 `namespace std::__1 { ... }` 里面写才行，而用户代码不可能知道 `__1` 这个名字。这正是发明内联命名空间时要解决的问题之一（GCC 早先用非标准的 strong using 扩展做同样的事）。

现行草案已经放宽了这条规则（[[temp.expl.spec#3]]：显式特化可以在主模板可以定义的任何作用域中声明，包括外层命名空间），所以单就特化而言差别变小了，Clang 23 也接受两种写法。但其他差别仍然存在：ADL 时 `std::__1` 中类型的关联命名空间只有 `std::__1`，不会连带 `std`；限定查找 `std::name` 时，若 `std` 自己有同名声明，就不再考虑 using 指令的目标。内联命名空间让这些方面都如同成员在外层命名空间中一样。
</details>

## 小结

!!! summary "要点"
    - 命名空间是开放的，可以跨 TU、跨模块多次扩展；命名空间不附属于模块。
    - 内联命名空间：在 ADL、无限定查找、限定查找、模板特化中，其成员都如同外层命名空间的成员；用于 ABI 版本化（libc++ `std::__1`、libstdc++ `std::__cxx11`）。
    - `namespace a::inline b::c`（C++20）；第一段不能 `inline`。
    - 无名命名空间 = 唯一名字 + using 指令；其成员具有内部链接（[[basic.link]]）。
    - using 指令：不引入名字；名字如同在最近公共外层命名空间中声明；传递；能看到后来添加的声明；不能出现在类中；不改变重载决议。

| 机制 | 引入名字？ | 看到后来的声明？ | 能在类中？ | 典型用途 |
|---|---|---|---|---|
| using 指令 | 否 | 是 | 否 | 局部便利 |
| using 声明（[[namespace.udecl]]） | 是 | 否 | 是（基类成员） | 精确引入、修改访问 |
| 内联命名空间 | 隐式 using 指令 + 更多 | 是 | — | 版本化 |
| 命名空间别名 | 是（别名本身） | — | 否 | 缩短长名字 |
