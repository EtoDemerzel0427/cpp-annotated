---
title: 命名空间
summary: 命名空间怎样定义和反复扩展；using 指令让名字在哪一层可见；无名命名空间、内联命名空间和命名空间别名分别解决什么问题。
status: done
covers: basic.namespace.general, namespace.def, namespace.def.general, namespace.unnamed, namespace.alias, namespace.udir
papers: N2535, N4230, P1094R2, N4266
related: basic.scope.namespace, basic.lookup.unqual, basic.lookup.qual, basic.lookup.udir, basic.lookup.argdep, basic.link, namespace.udecl, module.interface, temp.expl.spec
tags: 命名空间, 名字查找, 链接, ABI
updated: 2026-10-19
---

!!! tldr
    - 命名空间是开放的：同一个命名空间可以在许多文件里反复打开、追加成员。别名不能用来扩展命名空间。
    - `using namespace N;` 不引入任何名字。在无限定查找中，`N` 的成员如同声明在同时包含这条指令和 `N` 的最近外层命名空间里，通常就是全局命名空间。
    - 无名命名空间等价于一个本翻译单元独有的名字加一条 using 指令，其中的一切都具有内部链接，类型也不例外。
    - 内联命名空间的成员在查找、ADL 和模板特化上都如同外层命名空间的成员。标准库靠它做 ABI 版本化，例如 libc++ 的 `std::__1`。
    - `namespace A::inline B::C { }` 是嵌套命名空间定义的简写（C++20），第一段不能写 `inline`。

## 命名空间是开放的 [basic.namespace.general]

两个库都想定义 `log`、`vector`、`detail::impl` 时，命名空间让它们各自处在不同的作用域里。和类不同，命名空间的定义可以分成许多段：

```cpp run title="namespace-open.cpp" ok
namespace lib { int a = 1; }
namespace lib { int b = 2; }        // 扩展 lib，追加成员

int main() { return lib::a + lib::b - 3; }
```

¶1 命名空间是一个可以没有名字的实体，它的作用域里可以声明任何种类的实体。属于命名空间的实体叫做它的**成员**（member），通过命名空间的名字访问。命名空间的定义可以分散在多个翻译单元和多个模块里，这是其他实体都没有的性质。

¶3 程序里还有一个**[[g:global-namespace|全局命名空间]]**（global namespace），所有不在任何命名空间里的声明都属于它（[[basic.scope.namespace]]）。它没有声明，因此名字查找找不到它：`::x` 中的 `::` 是语法的一部分，不是对某个名字的查找。全局命名空间也不是无名命名空间。

¶2 命名空间不附属于任何具名模块，其中的名字也不会具有模块链接。只要命名空间定义里含有导出声明，这个定义就算导出的（[[module.interface]]）：

```cpp title="namespace-module.cpp"
export module M;
namespace N1 {}                  // N1 未导出
export namespace N2 {}           // N2 导出
namespace N3 { export int n; }   // N3 也导出，因为含导出声明
```

不同的模块常常要往同一个命名空间（`std`、公司的顶层命名空间）里添加成员。如果命名空间属于第一个声明它的模块，别的模块就不能再打开它了。

## 定义与扩展 [namespace.def.general]

```text
named-namespace-definition:
    inline(opt) namespace attribute-specifier-seq(opt) identifier { namespace-body }
unnamed-namespace-definition:
    inline(opt) namespace attribute-specifier-seq(opt) { namespace-body }
nested-namespace-definition:
    namespace enclosing-namespace-specifier :: inline(opt) identifier { namespace-body }
```

¶1 命名空间定义只能出现在命名空间作用域里，函数体内和类内都不行。

¶2 编译器遇到 `namespace X { ... }` 时，先在当前所在的命名空间（连同它的内联命名空间，见下文）里找名字 `X`。找到的是某个命名空间 N 的定义，这次定义就**扩展**（extend）N；什么都没找到，就引入一个新的命名空间名。找到的如果是别的东西，比如变量或命名空间别名，新名字就与它冲突：

```cpp title="namespace-extend.cpp" error
namespace lib { int a; }
namespace lib { int b; }       // OK：扩展 lib

namespace Alias = lib;
namespace Alias { }            // error: Alias 是别名，不能扩展
int Thing;
namespace Thing { }            // error: 与变量 Thing 冲突
```

¶3 命名空间定义本身也是声明，所以可以嵌套。查找照常由内向外进行，并且只看已经出现的声明：

```cpp title="namespace-nested.cpp" ok
namespace Outer {
    int i;
    namespace Inner {
        void f() { i++; }    // Outer::i：Inner::i 还没有声明
        int i;
        void g() { i++; }    // Inner::i
    }
}
int main() {}
```

¶5 命名空间定义里的属性属于被定义或被扩展的命名空间。实际有用的主要是 C++17 起允许的 `[[deprecated]]`（[[N4266]]），使用其中的成员时会得到弃用警告：

```cpp title="namespace-deprecated.cpp" ok
namespace [[deprecated("use v2")]] v1 { inline void f() {} }
namespace v2 { inline void f() {} }

int main() { v2::f(); }    // 写 v1::f() 会有弃用警告
```

## 命名空间别名 [namespace.alias]

```cpp run title="namespace-alias.cpp" ok
namespace very::long_::library_name::v3 { int x = 1; }
namespace lib = very::long_::library_name::v3;

int f() { return lib::x; }
int g() {
    namespace L = lib;            // 块作用域里也可以
    return L::x;
}
int main() { return f() + g() - 2; }
```

¶3 `namespace lib = ...;` 声明一个**[[g:namespace-alias|命名空间别名]]**（namespace alias）。

¶4 别名只是同义词，它指向的命名空间叫做它的底层实体（[[basic.pre]]）。所以不能用别名扩展命名空间（上一节的例子），同一作用域里重复声明同一个别名时也必须指向同一个命名空间。查找 `=` 右边的名字时只考虑命名空间名（[[basic.lookup.udir]]）。

¶2 C++26 反射允许写 `namespace X = [: r :];`，这时 *splice-specifier* 必须指代一个命名空间，而且不能是全局命名空间。

## using 指令 [namespace.udir]

```text
using-directive:
    attribute-specifier-seq(opt) using namespace nested-name-specifier(opt) namespace-name ;
    attribute-specifier-seq(opt) using namespace splice-specifier ;
```

¶4 **[[g:using-directive|using 指令]]**（using-directive）`using namespace N;` 不引入任何名字。它只改变后续无限定查找和限定查找的路径，让 `N` 的成员可以不带限定地使用。要把一个具体的名字引入当前作用域，用的是 using 声明 `using N::f;`（[[namespace.udecl]]）：

| | using 指令 `using namespace N;` | using 声明 `using N::f;` |
|---|---|---|
| 是否引入名字 | 否，只改变查找路径 | 是，`f` 成为当前作用域里的名字 |
| 之后加入 `N` 的声明 | 能看到（第 6 段） | 看不到（[[namespace.udecl#9]]） |
| 能否写在类里 | 否（第 2 段） | 能，用于基类成员 |
| 与本作用域的同名声明 | 不冲突，使用时才可能有歧义 | 可能冲突 |

### 名字出现在哪一层（¶3）

using 指令的效果取决于一条位置规则：

!!! std
    During unqualified name lookup, the names appear as if they were declared in the nearest enclosing namespace which contains both the *using-directive* and the designated namespace.

    在无限定查找中，这些名字如同声明在同时包含这条 using 指令和被指定命名空间的最近外层命名空间里。

¶3 是注，规范性的规则在 [[basic.lookup.unqual]]。函数里写 `using namespace std;` 时，同时包含这个函数和 `std` 的最近命名空间是全局命名空间，于是 `std` 的名字如同声明在全局命名空间里。它们不会比当前命名空间离使用点更近，当前命名空间里的同名实体照样能隐藏它们，局部变量更是如此。

标准的例子把几种情况放在了一起：

```cpp title="udir-nearest.cpp" error
namespace A {
    int i;
    namespace B {
        namespace C { int i; }
        using namespace A::B::C;
        void f1() { i = 5; }        // OK：C::i 如同在 B 中，先于 A::i 被找到
    }
    namespace D {
        using namespace B;
        using namespace C;
        void f2() { i = 5; }        // error: 歧义，B::C::i 还是 A::i？
    }
    void f3() { i = 5; }            // OK：A::i
}
void f4() { i = 5; }                // error: 两个 i 都不可见
```

- `f1`：指令在 B 里，指向 `A::B::C`。同时包含 B 和 C 的最近命名空间是 B，所以 `C::i` 如同在 B 里。查找从 `f1` 向外走到 B 就找到了它，不会再看到 `A::i`。
- `f2`：D 里的两条指令，`using namespace B;` 和 `using namespace C;`，公共外层命名空间都是 A。B 里那条指向 C 的指令也会传递过来（见下一小节）。于是 `C::i` 如同在 A 里，与 `A::i` 同层，两者都是变量，因此有歧义。
- `f4`：全局命名空间里既没有 `i`，也没有 using 指令。

### 传递性与之后的声明（¶5、¶6）

¶5 using 指令是传递的。被指定的命名空间里如果还有 using 指令，那些指令指向的命名空间也会纳入查找：

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

这里 `N::i` 不会隐藏 `M::i`。N 里的指令让 `M::i` 如同在全局命名空间里，`f` 里的指令让 `N::i` 也如同在全局命名空间里，两者同层，所以有歧义。改成限定查找 `N::i` 就没有问题：限定查找先看 N 自己的声明，只有找不到时才去看 N 里 using 指令的目标（[[namespace.qual]]）。

¶6 using 指令之后才加入被指定命名空间的声明，在它们出现之后同样能通过这条指令找到：

```cpp title="udir-later.cpp" ok
namespace A { void f(int) {} }
using namespace A;
namespace A { void f(char) {} }

void g() { f('a'); }        // 调用 A::f(char)
int main() { g(); }
```

### 不能写在类里（¶1、¶2）

¶2 using 指令可以出现在命名空间作用域和块作用域，但不能出现在类作用域：

```cpp title="udir-class.cpp" error
namespace M { int i; }
struct K {
    using namespace M;     // error: 类作用域里不允许 using 指令
};
```

类作用域的查找规则是在类和它的基类里搜索成员（[[class.member.lookup]]）。如果允许 using 指令，`K::i` 是否应该找到 `M::i`、`M::i` 算不算 `K` 的成员，都说不清楚，所以标准直接禁止。

¶1 指令里的命名空间名不能是待决的，也就是不能依赖模板参数，因为它要在模板定义时就确定查找路径。用 C++26 反射写 `using namespace [: r :];` 时，`r` 也不能指代全局命名空间。

### 冲突与重载（¶7、¶8）

¶7 无限定查找经由 using 指令在两个不同的命名空间里找到同一个名字时，如果两个声明不是同一个实体，又不全是函数，使用这个名字就是非良构的（[[basic.lookup]]）。在同一个作用域里，变量或函数的名字会隐藏同名的类；这条隐藏规则不跨命名空间生效。

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
    X(1);          // error: 在两个命名空间里都找到了 X
    g();           // OK：A::g 和 B::g 是同一个函数
    h();           // OK：都是函数，重载决议选 A::h
}
```

`g()` 没有歧义，是因为 C 语言链接的函数不分命名空间，两处 `extern "C" int g()` 声明的是同一个函数（[[dcl.link#7]]）。

¶8 命名空间被查找的先后、using 指令之间的关系都不影响重载决议。两个签名相同的函数分别在 D 和 E 里，即使 D 经由 using 指令能到达 E，D 的版本也不会因此优先：

```cpp title="udir-overload.cpp" error
namespace D {
    int d1;
    void f(char);
}
using namespace D;

int d1;              // OK：声明本身不与 D::d1 冲突

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
    d2++;            // OK：D::d2
    e++;             // OK：E::e
    f(1);            // error: D::f(int) 与 E::f(int) 有歧义
    f('a');          // OK：D::f(char)
}
```

脚注 76 对比了类层次里的查找：在那里，沿某条继承路径一个成员隐藏另一个，可以消解歧义；经由 using 指令找到的名字没有这种机制。

## 无名命名空间 [namespace.unnamed]

```cpp run title="unnamed-internal.cpp" ok
namespace {
    struct Helper { int v = 42; };      // 类型也只属于本翻译单元
    int compute() { return Helper{}.v; }
}
int main() { return compute() - 42; }
```

¶1 **[[g:unnamed-namespace|无名命名空间]]**（unnamed namespace）`namespace { body }` 的行为如同被替换成下面三行：

```text
inline(opt) namespace unique { /* 空 */ }
using namespace unique;
namespace unique { body }
```

`unique` 是编译器选的一个标识符：同一个翻译单元里的所有无名命名空间用同一个，它与程序里其他任何标识符都不同。`inline` 当且仅当原定义写了 `inline` 时出现，属性属于 `unique`。

这三行决定了无名命名空间的全部行为。第一行先声明命名空间，让第二行的 using 指令有对象可指；第二行让成员可以在外层不带限定地使用；第三行放入内容。同一个翻译单元里的无名命名空间是同一个，可以反复打开；不同翻译单元里的各不相同。

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
    A::i++;                      // OK：A::unique::i
    j++;                         // OK：A::unique::j
}
```

`h` 里的 `i++` 有歧义：按 using 指令的位置规则，`::unique::i` 和 `A::unique::i` 都如同声明在全局命名空间里。

### 内部链接

本节没有提到链接，规则在 [[basic.link#4]]：无名命名空间，以及直接或间接声明在其中的命名空间，具有内部链接，其中声明的变量、函数、类、模板也随之具有内部链接。内部链接的名字只在本翻译单元里可见，别的翻译单元里的同名声明是另一个实体。

所以无名命名空间是表达本文件私有的标准写法。它比 `static` 更通用，因为 `static` 不能用在类型上。

!!! impl "修饰名"
    Itanium ABI（GCC、Clang 在 Linux 和 macOS 上使用的 C++ ABI）把无名命名空间编码为 `_GLOBAL__N_1`。上面的 `compute` 在本机 Clang 23 下的符号是 `_ZN12_GLOBAL__N_17computeEv`，`nm` 显示为小写 `t`，即局部符号，不参与跨翻译单元的链接。内部链接也方便优化：编译器知道所有调用点，可以放心地内联、删除没用到的函数。

!!! pitfall "头文件里的无名命名空间"
    每个包含该头文件的翻译单元都会得到一份独立的实体。如果头文件里的 `inline` 函数或模板用到了这些实体，各翻译单元里的定义引用的就是不同的实体，违反 ODR（[[basic.def.odr]]）。这种违规属于非良构、不要求诊断：编译器和链接器都可能不报告，运行结果没有保证。

## 内联命名空间

¶4 定义前带 `inline` 的命名空间是**[[g:inline-namespace|内联命名空间]]**（inline namespace）。扩展时可以写也可以省略 `inline`，但只有最初声明这个名字的定义写了 `inline`，后面才能写：

```cpp title="inline-reopen.cpp" error
namespace N {}
inline namespace N {}      // error: N 原来不是内联的
inline namespace M {}
namespace M {}             // OK：扩展时可以省略 inline（Clang 会警告）
```

### 成员如同属于外层命名空间（¶6、¶7）

¶6 内联命名空间的成员在大多数方面都可以当作外层命名空间的成员使用。具体有四点：

1. ADL：内联命名空间和它的外层命名空间，只要一个加入了关联命名空间集合，另一个也随之加入（[[basic.lookup.argdep]]）。
2. 无限定查找：外层命名空间里隐式插入一条指向它的 using 指令，与无名命名空间的做法相同。
3. 模板：其中的模板可以在外层命名空间里部分特化、显式实例化和显式特化，就像它是外层命名空间的成员。
4. 限定查找：查找 `外层::name` 时，即使外层命名空间自己就有 `name`，内联命名空间的成员也一并考虑（[[namespace.qual]]）。

第 4 点与普通 using 指令不同。对普通 using 指令，`N::x` 先看 N 自己，N 里有 `x` 就停止；对内联命名空间，两者同时考虑：

<div class="compare" markdown="1">

```cpp error
namespace N {
  inline namespace V { int x; }
  int x;
}
int a = N::x;  // error: 歧义
```

```cpp ok
namespace N {
  namespace V { int x; }
  using namespace V;
  int x;
}
int a = N::x;  // OK：N 自己的 x
```

</div>

¶7 这些性质是传递的：N 含内联命名空间 M，M 又含内联命名空间 O，O 的成员就可以当作 M 或 N 的成员使用。N 里所有内联命名空间的传递闭包叫做 N 的**[[g:inline-namespace-set|内联命名空间集合]]**（inline namespace set）。

上一节讲扩展时，编译器搜索的范围也包括这个集合。所以 `namespace std { inline namespace __1 { namespace ranges {} } }` 之后，在 `std` 里写 `namespace ranges { ... }` 扩展的是 `std::__1::ranges`，而不是新建一个 `std::ranges`。

### 用途：库的版本化

内联命名空间是 C++11 为库的版本演进加入的（[[N2535]]）。设想库的第二版要改变 `Widget` 的布局。如果直接修改，用旧头文件编译的目标文件和新库链接时，两边对 `Widget` 的理解不一样，却不会有任何提示。用内联命名空间可以这样写：

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

// 在 lib 里特化 v2 的模板（第 3 点）
template<> struct lib::Box<int> { int special; };

int main() {
    lib::Widget w{1, 2};       // 实际上是 lib::v2::Widget
    lib::v1::Widget old{3};    // 旧版本仍可显式使用
    lib::Box<int> b{4};
    return lib::use(w) + lib::v1::use(old) + b.special - 10;
}
```

源代码里写 `lib::Widget`，不需要知道版本号；但修饰名里含有 `v2`（`lib::v2::Widget` 编码为 `N3lib2v26WidgetE`）。所以新旧目标文件混用时，得到的是链接错误，而不是运行时的布局错乱。

!!! impl "标准库里的内联命名空间"
    - libc++ 把几乎所有内容放在 `std::__1` 里（名字可通过 `_LIBCPP_ABI_NAMESPACE` 配置），所以 macOS 上 `std::string` 的修饰名里有 `NSt3__1`。
    - libstdc++ 在 GCC 5 改变 `std::string`、`std::list` 布局时（C++11 禁止 `string` 写时复制，要求 `list::size()` 为常数时间），把新版本放进内联命名空间 `std::__cxx11`，并配合 GCC 的 `abi_tag` 属性，让返回这些类型的函数的修饰名也随之改变。
    - 由于内联命名空间对 ADL 和模板特化透明，用户为 `std::hash` 写的特化不会因此失效。

## 嵌套命名空间定义（¶8）

¶8 `namespace E::I { B }` 等价于 `namespace E { namespace I { B } }`；如果 `I` 前写了 `inline`，里层就是内联命名空间。*enclosing-namespace-specifier* 里的各段也可以带 `inline`，递归展开即可：

```cpp title="nested-namespace-def.cpp" error
namespace A::inline B::C {     // C++20
    int i;
}
// 等价于 namespace A { inline namespace B { namespace C { int i; } } }
int j = A::C::i + A::B::C::i;  // OK：两种写法都行

namespace X::Y { }             // OK（C++17）
inline namespace Z::W { }      // error: 开头不能写 inline
```

C++17 引入 `namespace a::b::c`（[[N4230]]），不允许任何一段是内联的。C++20 的 [[P1094R2]] 允许除第一段以外的任何一段写 `inline`。第一段仍然不行，因为 `inline namespace A::B` 里的 `inline` 修饰哪一段会有歧义；要让第一段内联，只能用传统写法。

## 历史与演进

!!! history
    - C++98 已有命名空间、无名命名空间、命名空间别名和 using 指令。当时无名命名空间的成员具有外部链接，只是名字别人写不出来。C++98 还弃用了命名空间作用域对象上的 `static`，推荐改用无名命名空间。
    - C++11 加入内联命名空间（[[N2535]]）；无名命名空间的成员改为内部链接，`static` 的弃用随之撤销。
    - C++17 加入 `namespace a::b::c`（[[N4230]]），命名空间可以带属性（[[N4266]]）。
    - C++20 允许嵌套命名空间定义里写 `inline`（[[P1094R2]]）；模块加入后，命名空间被规定为不附属于模块。
    - C++26 静态反射加入 `namespace X = [: r :];` 和 `using namespace [: r :];`。

## 常见误解

!!! pitfall "函数里的 using 指令让名字离使用点最近"
    `N` 的成员如同声明在 `N` 和当前位置的最近公共外层命名空间里，通常是全局命名空间。当前命名空间和局部作用域里的同名实体都会隐藏它们。

!!! pitfall "外层的同名声明会隐藏内联命名空间的成员"
    不会。`namespace N { inline namespace V { int x; } int x; }` 中 `N::x` 有歧义；换成普通 using 指令时，`N::x` 才是 N 自己的 `x`。

!!! pitfall "头文件里写 `using namespace std;` 只是风格问题"
    它让所有包含该头文件的翻译单元在全局命名空间看到 `std` 的全部名字，包括以后标准新增的名字。标准库每加一个名字，都可能让原本没有歧义的代码变得有歧义。

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

- `int a = i;`（在 D 里）：`using namespace A;` 让 `A::i` 如同在全局命名空间里，因为同时包含 D 和 A 的最近命名空间是全局命名空间。查找依次走过 D、C、B，在 B 里找到 `B::i` 就停止，`A::i` 被隐藏。
- `int l = k;`（在 C 里）：`using namespace D;` 让 D 的成员如同在 C 里。C 自己也有 `k`，于是 C 这一层同时有 `C::k` 和 `D::k`，两者都是变量，有歧义。
- `int m = i;`：D 里没有 `i`；D 里的 `using namespace A;` 经传递生效，`A::i` 仍如同在全局命名空间里。查找 C、B，在 B 里找到 `B::i`。
- `int n = j;`：`D::j` 如同在 C 里，先于 `B::j` 被找到。
</details>

!!! question "思考题 2"
    libc++ 把 `std::vector` 放在内联命名空间 `std::__1` 里。如果换成普通命名空间 `__1` 再在 `std` 里写 `using namespace __1;`，会出什么问题？

<details markdown="1">
<summary>答案</summary>

至少有两处不同。第一，ADL：`std::__1::vector<int>` 的关联命名空间只有 `std::__1`，不再连带 `std`，直接声明在 `std` 里的函数就不会被 ADL 找到。第二，限定查找：`std::name` 时如果 `std` 自己有同名声明，就不会再看 using 指令的目标。

用户在 `namespace std { ... }` 里写的特化原本也是问题：C++11 要求显式特化声明在模板所在的命名空间里，内联命名空间的外层也算，普通的 `__1` 的外层则不算。现行草案已放宽为在主模板可以定义的任何作用域里都能显式特化（[[temp.expl.spec#3]]），本机 Clang 23 对两种写法都接受，所以这一点的差别已经不大。
</details>
