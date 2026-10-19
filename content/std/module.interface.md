---
title: 导出声明
summary: export 能写在哪里、能修饰什么，什么样的声明算被导出，以及导出与链接的关系。
status: done
since: c++20
papers: P1103R3, P2615R1
related: module.unit, module.import, module.reach, basic.link, basic.lookup, namespace.udecl, dcl.spec.auto
tags: 模块, 导出, 链接
updated: 2026-10-19
---

!!! tldr
    - `export` 只能写在模块接口单元管辖范围内的命名空间作用域中，不能写在实现单元、无名命名空间或私有模块片段里。
    - 导出决定导入者能写出哪些名字。类成员不需要单独导出，只要类的定义对导入者可达，成员就能用。
    - 被导出的名字不能具有内部链接；导出的 `using` 声明只能指向具有外部链接的实体或类型别名。
    - 一个实体是否导出由它的第一次声明决定：先导出、后定义可以，先不导出、后补 `export` 不行。
    - 导出名字不等于导入者能完整使用它：`export struct A;` 的定义如果在实现单元里，导入者看到的永远是不完整类型。

## export 的三种写法

```cpp title="M.cppm" ok
export module M;
import Q;
export import R;               // 再导出：导入 M 的人也导入 R
export int f();                // 导出单个声明
export {                       // export 块：块内每个声明都被导出
  struct S { int v; };
  int g(S);
}
export namespace N {           // 导出整个命名空间定义
  int h();
}
```

文法上，*export-declaration* 有三种形式：

```text
export-declaration:
    export name-declaration
    export { declaration-seq(opt) }
    export-keyword module-import-declaration
```

第三种是再导出（`export import`），它的含义在 [[module.import#7]] 中规定。第一种只接受 *name-declaration*（[[dcl.pre]]），不接受显式特化、显式实例化和另一个 *export-declaration*，所以 `export template<> void f<int>(int) {}` 和 `export template void f<long>(long);` 按文法就不成立。

!!! impl "Clang 的偏差"
    本机 Clang 23 接受 `export template<> void f<int>(int) {}`、`export template void f<long>(long);`，也接受导出偏特化（见下一节），都不给诊断。按当前草案，这三者都是非良构的。

## export 能写在哪里（¶1）

¶1 *export-declaration* 必须栖居于命名空间作用域（全局命名空间或具名命名空间），并且出现在模块接口单元的管辖范围（[[module.unit#5]]，模块声明到 TU 末尾）中。它不能直接或间接地出现在无名命名空间或私有模块片段里。

<div class="compare" markdown="1">

```cpp title="M.cppm" error
export module M;
export { export int q; }
// error: export 块中嵌套 export
module :private;
export int z;
// error: 私有模块片段中不能 export
```

```cpp title="impl.cpp" error
module M;
export int g();
// error: 不在模块接口单元中
```

</div>

这些位置限制都有直接的理由：

- 导出的作用是把名字提供给模块外的导入者，而只有接口单元能被模块外导入。所以实现单元、实现分区、全局模块片段、非模块 TU 中都不能写 `export`。
- 无名命名空间中的一切都具有内部链接，别的 TU 无法指代它们（这是 ¶3 的特例）。
- 私有模块片段存在的目的就是不影响导入者（[[module.private.frag]]）。
- 类成员、局部声明不在命名空间作用域，不能单独导出。

¶1 还有三条规定：

- `export` 不改变声明本身的效果：*export-declaration* 具有它所包含的声明的效果。注 1 补充，它不建立作用域，`export { int a; }` 中的 `a` 就在外围命名空间里，和 `export int a;` 一样。
- 不能导出偏特化（[[temp.decls.general]]）。偏特化不引入名字，只要主模板和偏特化本身对导入者可达，匹配时就会用到它。允许导出偏特化，会让人误以为不导出就能对导入者隐藏它。这条限制来自 [[P2615R1]]，作为缺陷报告也适用于 C++20。
- export 块中不能再有 `export` 或导入声明。

Clang 23 对左边两处分别报 "export declaration appears within another export declaration" 和 "export declaration cannot be used in a private module fragment"，对右边报 "export declaration can only be used within a module interface"。

## 什么算被导出（¶2）

¶2 一个声明是**被导出的**（[[g:exported-declaration|exported]]），如果它位于 *export-declaration* 之中并且栖居于命名空间作用域，或者属于下面两种情况：

- ¶2.1 它是一个含有被导出声明的命名空间定义；
- ¶2.2 它在头文件单元中，并且至少引入一个名字。

```cpp title="M.cppm" ok
export module M;
export {
  int a;                  // 被导出
  namespace N { int b; }  // N 的这个定义和 N::b 都被导出
}
namespace P {
  export int c;           // P 的这个定义因 ¶2.1 被导出
  int d;                  // 未导出：模块链接
}
export enum E { e1 };     // E 和 e1 都栖居于命名空间作用域，都被导出
export struct S {         // S 被导出，S::m 不是被导出的声明
  int m;
};
```

`S::m` 栖居于类作用域，不是被导出的声明，但导入者照样能写 `s.m`。类成员通过类成员查找找到，只需要 `S` 的定义对导入者可达（¶7）。

¶2.1 让导入者能写出 `P::c`：如果包含 `c` 的命名空间定义不算被导出，导入者连 `P::` 都写不出来。被导出的只是这一个命名空间定义，同一模块中其他 `namespace P { ... }` 里未导出的成员仍然不可见。

¶2.2 让头文件单元（`import "x.h";`，见 [[module.import#5]]）中的一切都隐式导出。头文件本来没有导出的概念，而 `import "x.h";` 应当提供与 `#include "x.h"` 相同的名字。

## 不能导出内部链接的名字（¶3–¶4）

¶3 不在头文件单元中的被导出声明，不得声明具有内部链接的名字。导出意味着别的 TU 可以通过这个名字指代这个实体，内部链接却意味着只有本 TU 能指代它，两者矛盾。

头文件单元是例外：头文件里有大量 `static` 函数和 `const` 变量，`import "x.h";` 必须能像 `#include` 一样提供它们（[[module.import#6]]）。

¶4 标准的例 1：

```cpp title="M.cppm" error
module;
#include "a.h"                  // a.h 的内容是 export int x;
                                // error: 全局模块片段不在接口单元的管辖范围中
export module M;
export namespace {}             // error: 无名命名空间具有内部链接
namespace {
  export int a2;                // error: 在无名命名空间中导出
}
export static int b;            // error: b 显式声明为 static
export int f();                 // OK
export namespace N { }          // OK
export using namespace N;       // OK，但没有效果
```

Clang 23 对四处错误依次报 "export declaration can only be used within a module interface"、"anonymous namespaces cannot be exported"、"export declaration appears within anonymous namespace"、"declaration of 'b' with internal linkage cannot be exported"。

最后一行是 using 指令（*using-directive*）。它属于 *name-declaration*，所以文法上可以导出；但它不引入名字，按 ¶2 不算被导出的声明。using 指令只影响本 TU 的名字查找（[[basic.lookup.udir]]），导入者不会因此获得 `using namespace N` 的效果。

在普通头文件里，`const int n = 5;` 具有内部链接，按 ¶3 本该无法导出。为此，模块接口单元管辖范围中的 `const` 变量不再默认具有内部链接（[[basic.link#3]] 的 ¶3.2.1），`export const int n = 5;` 合法，`n` 具有外部链接。

## 导出 using 声明（¶5）

using 声明（*using-declaration*，[[namespace.udecl]]）不声明新实体，只是让别处声明的实体可以在这里用某个名字找到。导出它，就是让导入者通过这个名字找到那个实体。

¶5 所以，不在头文件单元中的被导出 using 声明，其中每个 *using-declarator* 指名的实体，要么是类型别名，要么是以具有外部链接的名字引入的。模块链接的实体不行，导入者不在同一个模块；内部链接的更不行。标准的例 2：

```cpp title="b.h"
int f();
```

```cpp title="c.h（可导入头文件）"
int g();
```

```cpp title="X.cppm"
export module X;
export int h();
```

```cpp title="M.cppm" error
module;
#include "b.h"
export module M;
import "c.h";
import X;
export using ::f, ::g, ::h;     // OK：f、g 附属于全局模块，h 附属于 X，都是外部链接
struct S;
export using ::S;               // error: S 具有模块链接
namespace N {
  export int h();
  static int h(int);            // #1
}
export using N::h;              // error: #1 具有内部链接
```

最后一行说明，using 声明带入的是整个重载集：`N::h` 的重载中只要有一个具有内部链接，就违反 ¶5。Clang 23 对两处错误分别报 "using declaration referring to 'S' with module linkage cannot be exported" 和 "... 'h' with internal linkage cannot be exported"。

这条规则最常见的用途，是把全局模块片段（[[module.global.frag]]）中通过 `#include` 得到的声明重新导出。头文件中的函数包含进全局模块片段后并不被导出，`export using ::f;` 把它导出。libc++ 的 `std.cppm` 就是这样实现 `import std;` 的：先在全局模块片段里包含全部头文件，再写 `export namespace std { using std::vector; ... }`。

注 2 补充，被导出的类型别名，其底层实体不必具有外部链接：

```cpp title="M.cppm" ok
export module M;
struct S;
export using T = S;             // OK：导出名字 T，它表示类型 S
```

导入者可以写 `T`，但写不出 `S`。能不能用 `T` 定义对象，取决于 `S` 的定义是否可达（[[module.reach#6]]）。

## 导出状态由第一次声明决定（¶6）

<div class="compare" markdown="1">

```cpp title="M2.cppm" ok
export module M2;
export struct X;
struct X { int a; };
// OK：隐式导出
export int v();
int v() { return 1; }
// OK：隐式导出
```

```cpp title="M.cppm" error
export module M;
struct S { int n; };
export struct S;
// error: 导出的声明
// 跟在未导出的声明之后
```

</div>

¶6 实体 X 的重声明，如果 X 由被导出的声明引入，就隐式导出；否则重声明不得被导出，除非它是类型别名、命名空间或命名空间别名。

左边是常见写法：在接口顶部导出声明，后面再定义。右边的 `S` 第一次声明时具有模块链接，再导出就等于把它改成外部链接。链接在中途改变，前后两段代码对同一实体的链接就有了不同的认识，所以标准要求链接在第一次声明时确定。Clang 23 对右边报 "cannot export redeclaration 'S' here since the previous declaration has module linkage"。

三种例外不存在这个问题。类型别名可以随时重新声明并导出；命名空间附属于全局模块，总是具有外部链接（[[module.unit#7]]），每一次定义都可以独立选择是否导出；命名空间别名同理。标准的例 4：

```cpp title="M.cppm" error
export module M;
struct S { int n; };
typedef S S;
export typedef S S;             // OK：类型别名
export struct S;                // error: 导出的声明跟在未导出的声明之后
namespace N {                   // 外部链接，附属于全局模块，未导出
  void f();
}
namespace N {                   // OK：导出的命名空间重声明未导出的命名空间
  export void g();
}
```

## 导入者怎样使用导出的名字（¶7）

¶7 注 3 总结了导出的几条后果：

- 被导出的声明引入的名字永远不具有模块链接，它们具有外部链接、无链接，或者（在头文件单元中）内部链接。这直接来自 [[basic.link#4]]：只有附属于具名模块且未导出的名字才具有模块链接。
- 模块导出的命名空间作用域声明，在导入该模块的任何 TU 中都能被名字查找找到（[[basic.lookup]]）。
- 类和枚举的成员名，在该类型的定义可达的任何地方都能被找到。

可见与可达是两件事：导出让导入者能写出名字，**可达性**（[[module.reach]]）决定导入者能否看到定义、默认实参等语义信息。标准的例 5 把两者放在一起：

```cpp title="M.cppm（M 的接口单元）"
export module M;
export struct X {
  static void f();
  struct Y { };
};

namespace {
  struct S { };
}
export void f(S);               // 标准例子标为 OK，见下方讨论
struct T { };
export T id(T);                 // OK：T 具有模块链接，不是 TU-local

export struct A;                // A 以不完整类型导出

export auto rootFinder(double a) {
  return [=](double x) { return (x + a/x)/2; };
}

export const int n = 5;         // OK：n 具有外部链接
```

```cpp title="M-impl.cpp（M 的实现单元）"
module M;
struct A {
  int value;
};
```

```cpp title="main.cpp" error
import M;
int main() {
  X::f();                       // OK：X 被导出，X 的定义可达
  X::Y y;                       // OK：X::Y 随 X 的定义可用
  auto f = rootFinder(2);       // OK
  return A{45}.value;           // error: A 是不完整类型
}
```

- `X::f`、`X::Y` 没有单独导出，`X` 的定义在接口单元中，可达，成员就能用。
- `T` 没有导出，导入者写不出 `T`，但可以写 `auto t = id({});`。`T` 的定义可达，所以返回值可以正常使用。
- `rootFinder` 返回 lambda 的闭包类型，导入者用 `auto` 接收。返回类型含占位符的导出函数，必须在导出声明所在的 TU 中、私有模块片段之外定义（[[dcl.spec.auto#12]]），否则导入者无法推导返回类型。
- `A` 被导出了，导入者能写出 `A`，但它的定义在实现单元中。实现单元不能被导入，对导入者不可达，所以导入者看到的 `A` 永远是不完整的。Clang 23 对最后一行报 "invalid use of incomplete type 'A'"。

!!! lawyer "`export void f(S);` 真的 OK 吗？"
    `S` 在无名命名空间中，具有内部链接，是 **TU-local** 实体（只能在本 TU 中使用的实体，见 [[basic.link#15]]）。`export void f(S);` 声明的 `f` 具有外部链接，不是 TU-local；它的形参类型指名了 `S`（[[basic.link#13]]），按 [[basic.link#14]] 这个声明是一个**暴露**（exposure）：非 inline 函数可以忽略的只是函数体，不包括形参类型。[[basic.link#17]] 规定，模块接口单元中非 TU-local 实体的声明如果是暴露，程序非良构。

    所以按规范性文字，这一行非良构；例子不具规范效力，其中的 OK 注释很可能是 TU-local 规则（[[P1815R2]]）加入之前留下的。本机 Clang 23 对这一行给出警告 `TU local entity 'S' is exposed [-WTU-local-entity-exposure]`，方向与规范性文字一致。例子与规范性文字冲突时，以规范性文字为准。

## 导出命名空间与语言链接块（¶8）

¶8 注 4 指出，被导出的命名空间定义或被导出的语言链接规范（[[dcl.link]]）中的声明都是被导出的，受上面所有规则约束。所以 `export namespace N { ... }` 里不能有内部链接的东西，也不能有指向模块链接实体的 using 声明（标准的例 6）：

```cpp title="M.cppm" error
export module M;
int g;
export namespace N {
  int x;                        // OK
  using ::g;                    // error: ::g 具有模块链接
}
```

`export extern "C++" { ... }` 中的声明既附属于全局模块（[[module.unit#7]]），又被导出，符号名与头文件时代相同，适合把已有的库逐步迁移到模块：

```cpp title="legacy.cppm" ok
export module legacy;
export extern "C++" {
  int parse(const char*);       // 附属于全局模块，被导出
}
```

## 速查：什么可以导出

| 声明 | 能否 `export` | 依据 |
|---|---|---|
| 外部链接的函数、变量、类、枚举、模板、概念 | 能 | |
| 模块接口中的 `const`、`constexpr` 变量 | 能，这里它们默认不是内部链接 | [[basic.link#3]] |
| `static` 函数和变量，无名命名空间中的任何东西 | 不能 | ¶1、¶3 |
| 偏特化 | 不能 | ¶1 |
| 显式特化、显式实例化 | 不能直接加 `export`（文法）；可以出现在 export 块中 | 文法 |
| 类型别名 | 能，底层类型不必有外部链接 | ¶5 注 2 |
| using 声明 | 能，前提是指向的实体都是外部链接或类型别名 | ¶5 |
| using 指令、`static_assert` | 文法上能，但不引入名字，没有效果 | ¶2 |
| 命名空间 | 能；含被导出声明的命名空间定义自动被导出 | ¶2.1 |
| 类成员 | 不能单独导出，随类的定义可达 | ¶1、¶7 |
| 第一次声明未导出的实体的重声明 | 不能（类型别名、命名空间、命名空间别名除外） | ¶6 |
| 导入声明 | `export import` 即再导出 | [[module.import#7]] |

## 历史与演进

!!! history
    - `export` 的三种形式和不能导出内部链接名字的规则来自 C++20 的 [[P1103R3]]。模块接口中 `const` 变量不再默认内部链接，也随模块一起进入 C++20。
    - [[P2615R1]]（*Meaningful exports*）作为对 C++20 的缺陷报告收紧了 `export` 能修饰的声明，例如禁止导出偏特化这种不引入名字的声明。

## 常见误解

!!! pitfall "导出了类，类内定义的成员函数就是 inline 的"
    在具名模块中，`export struct S { int get() { return v; } int v; };` 的 `get` 不是 inline 的（[[class.mfct#1]]）。导入者调用 `s.get()` 是一次普通的外部调用，除非开启 LTO 之类的跨 TU 优化。需要 inline 就显式写 `inline`。

!!! pitfall "`export using namespace std;` 会传给导入者"
    不会。using 指令只影响本 TU 的名字查找，导出它是合法的空操作。

!!! pitfall "导出的 inline 函数可以随意调用模块里的函数"
    `void helper(); export inline void api() { helper(); }` 合法：`helper` 具有模块链接，不是 TU-local。但如果 `helper` 是 `static` 的，`api` 的定义就是一个暴露（[[basic.link#14]]），在模块接口中非良构。本机 Clang 23 对此只给出 `-WTU-local-entity-exposure` 警告。

## 思考题

!!! question "思考题 1"
    下面哪些行非良构？

    ```cpp
    export module M;
    struct A {};
    export using B = A;            // (1)
    export struct A;               // (2)
    export struct C;               // (3)
    struct C { int x; };           // (4)
    export namespace { }           // (5)
    ```

<details markdown="1">
<summary>答案</summary>

- (1) 合法：导出类型别名，底层实体不必有外部链接（¶5 注 2）。
- (2) 非良构：`A` 第一次声明时没有导出，重声明不得导出（¶6）。
- (3)、(4) 合法：(4) 隐式导出（¶6）。
- (5) 非良构：无名命名空间具有内部链接，违反 ¶3，标准例 1 中同样的一行标为 error。
</details>

!!! question "思考题 2"
    接口单元只写了 `export struct Handle; export Handle* make();`，`Handle` 的定义放在实现单元里。导入者能做哪些事？

<details markdown="1">
<summary>答案</summary>

导入者能写出 `Handle`，能声明 `Handle*` 变量并调用 `make()`，但 `Handle` 的定义对它不可达，所以 `Handle` 是不完整类型：不能创建 `Handle` 对象、不能访问成员、不能 `sizeof(Handle)`、也不能 `delete` 这个指针（C++26 起，`delete` 不完整类型的对象是非良构的，见 [[expr.delete#4]]）。这是模块版本的不透明句柄，销毁也要由模块提供的函数完成。
</details>
