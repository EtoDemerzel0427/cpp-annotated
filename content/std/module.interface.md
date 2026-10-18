---
title: 导出声明
summary: export 能出现在哪里、能修饰什么；什么样的声明算"被导出"；导出与链接的关系（不能导出内部链接名字、导出的名字不会有模块链接）；导出的 using 声明与重声明规则；导出命名空间与 export 块。
status: done
since: c++20
papers: P1103R3, P2615R1
related: module.unit, module.import, module.reach, basic.link, basic.lookup, namespace.udecl, dcl.spec.auto
tags: 模块, 导出, 链接
updated: 2026-10-17
---

`export` 是模块对外的"开关"：模块接口单元中被导出的命名空间作用域声明，可以被导入者的名字查找找到；没有导出的，导入者写不出它的名字。本节规定 `export` 的语法位置、它能修饰哪些声明，以及它与**链接**的耦合——导出的名字必须能被其他 TU 指代，所以不能是内部链接的。

阅读前需要：[[module.unit]]（接口单元、管辖范围、附属）、[[basic.link]]（四种链接）。导出只管**可见性**，至于导出声明所提供的定义在哪里"生效"，是可达性（[[module.reach]]）的问题。

## 语法

```text
export-declaration:
    export name-declaration
    export { declaration-seq(opt) }
    export-keyword module-import-declaration
```

三种形式：

1. **单个声明**：`export int f();`、`export struct S { ... };`、`export namespace N { ... }`、`export template<class T> ...`。
2. **export 块**：`export { int f(); struct S; }`，相当于对块中每个声明分别加 `export`。
3. **再导出**：`export import M;`，其中 `export-keyword` 是预处理器识别出导入指令后替换出的特殊记号（[[cpp.import#3]]），语义见 [[module.import#7]]。

第一种形式只接受 *name-declaration*（[[dcl.pre]]），不接受 *special-declaration*——即显式实例化、显式特化以及另一个 *export-declaration*。所以 `export template<> void f<int>(int);`、`export template void f<long>(long);` 从语法上就是非良构的。

!!! impl "Clang 的偏差"
    本机 Clang 23 接受 `export template<> void f<int>(int) {}` 和 `export template void f<long>(long);`，没有任何诊断。按当前草案的文法，这两者都不是合法的 *export-declaration*。

## 出现位置与基本约束（¶1）

¶1 对 *export-declaration* 的约束：

- 必须**栖居于命名空间作用域**（全局命名空间或具名命名空间内），并出现在**模块接口单元的管辖范围**中。所以：
    - 普通实现单元、实现分区、非模块 TU、全局模块片段中都不能出现 `export`；
    - 类作用域、块作用域中不能出现 `export`。
- 不得**直接或间接**出现在**无名命名空间**或**私有模块片段**之中。
- *export-declaration* 具有其 *name-declaration*、*declaration-seq* 或 *module-import-declaration* 的声明效果——`export` 本身不改变被修饰声明"声明了什么"。
- *name-declaration* 不得声明**偏特化**（[[temp.decls.general]]）。
- export 块的 *declaration-seq* 中不得含有 *export-declaration* 或 *module-import-declaration*（不能嵌套 `export`，也不能在块里写 `import`）。

Note 1：*export-declaration* **不建立作用域**。`export { int a; }` 中的 `a` 就在外围命名空间里，和写成 `export int a;` 完全一样。

为什么有这些限制？

- **只在接口单元**：`export` 的意义是"把名字提供给导入者"，而只有接口单元能被导入（实现分区也可被导入，但只在模块内部，没有"对外"一说）。
- **不在无名命名空间**：无名命名空间中的一切都是内部链接，不能被别的 TU 指代，导出它们毫无意义（¶3 的特例）。
- **不在私有模块片段**：私有片段的全部意义就是"不影响导入者"（[[module.private.frag]]）。
- **不导出偏特化**：偏特化不引入名字，它是主模板的一部分；只要主模板可达，偏特化在匹配时就会被考虑（只要它也可达）。允许 `export` 修饰它会让人误以为"不导出偏特化就能对导入者隐藏它"。这条限制来自 [[P2615R1]]（作为缺陷报告应用于 C++20）。

```cpp title="M.cppm" error
export module M;
template<class T> struct V {};
export template<class T> struct V<T*> {};   // error: 不能导出偏特化（¶1）
export { export int q; }                     // error: export 块中嵌套 export（¶1）
module :private;
export int z;                                // error: 私有模块片段中不能 export（¶1）
```

```cpp title="impl.cpp" error
module M;
export int g();     // error: 不在模块接口单元中（¶1）
```

!!! impl "本机诊断"
    Clang 23 对嵌套 `export` 报 "export declaration appears within another export declaration"，对私有片段报 "export declaration cannot be used in a private module fragment"，对非接口单元报 "export declaration can only be used within a module interface"。但它**不**诊断导出偏特化——又一处偏差。

## 什么是"被导出"（¶2）

¶2 一个声明[[g:exported-declaration|被导出]]（exported），当且仅当它：

- 在 *export-declaration* 之中**并且**栖居于命名空间作用域；或
- **¶2.1** 是**含有被导出声明的命名空间定义**；或
- **¶2.2** 是**头文件单元**中至少引入一个名字的声明。

逐条理解：

- **"栖居于命名空间作用域"**：`export struct X { void f(); struct Y {}; };` 中被导出的只有 `X`。`X::f`、`X::Y` 栖居于类作用域，**不是**"被导出的声明"。但这不妨碍导入者使用它们——类成员通过类成员查找找到，前提是类定义**可达**（¶7 Note 3）。
- **¶2.1 命名空间自动导出**：`namespace N { export int x; }` 让 `N` 也成为被导出的（否则导入者连 `N::` 都写不出来）。注意这里是"这一个命名空间定义"被导出，同一模块中其他 `namespace N { ... }` 的定义不受影响——它们中的未导出成员仍然不可见。
- **¶2.2 头文件单元**：头文件单元中的一切都隐式导出（[[module.import#5]] Note 2），因为头文件本来就没有"导出"的概念，`import "x.h";` 必须与 `#include "x.h"` 提供相同的名字。

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
export enum E { e1 };     // E 与枚举项 e1（栖居于命名空间作用域）都被导出
export struct S {         // S 被导出；S::m 不是"被导出的声明"，但 S 的定义可达，导入者能用 S::m
  int m;
};
```

## 不能导出内部链接的名字（¶3–¶4）

¶3 不在头文件单元中的被导出声明，不得声明具有**内部链接**的名字。

理由很直接：导出就是承诺"别的 TU 可以通过这个名字指代这个实体"，内部链接却说"只有本 TU 能指代它"。两者矛盾。

头文件单元是例外（[[module.import#6]]）：头文件里有大量 `static` 函数和 `const` 变量（内部链接），`import "x.h";` 必须能像 `#include` 一样提供它们。

¶4 Example 1（加注）：

```cpp title="a.h"
export int x;
```

```cpp title="TU #1" error
module;
#include "a.h"                  // error: x 的声明不在模块接口单元的管辖范围中
                                //  （全局模块片段不属于管辖范围）
export module M;
export namespace {}             // error: 无名命名空间有内部链接
namespace {
  export int a2;                // error: 导出内部链接名字（且位于无名命名空间中，¶1）
}
export static int b;            // error: b 被显式声明为 static
export int f();                 // OK
export namespace N { }          // OK
export using namespace N;       // OK：using 指令不声明名字，导出它没有效果但合法
```

最后一行值得一说：`using namespace N;` 是 *using-directive*，属于 *name-declaration*，所以语法上可以导出。但它不引入名字，按 ¶2 它不是"被导出的声明"（不引入名字），导入者**不会**因此获得 `using namespace N` 的效果——using 指令的作用只在本 TU 内（[[basic.lookup.udir]]）。

还有一个隐蔽的情况：**模块接口中的 `const` 变量不再默认内部链接**（[[basic.link#3]] 的 ¶3.2.1），所以 `export const int n = 5;` 是合法的——它是外部链接（¶7 Example 5）。在普通头文件里，`const int n = 5;` 是内部链接；正因如此，模块接口单元必须改变这条默认规则，否则常量没法导出。

## 导出 using 声明（¶5）

¶5 若被导出的声明是 *using-declaration*（[[namespace.udecl]]）且不在头文件单元中，则它的每个 *using-declarator* 所指名的实体，要么是**类型别名**，要么是以**外部链接名字**引入的。

using 声明本身不声明实体，它只是把别处声明的实体"带到"当前作用域。导出 using 声明，就是让导入者能通过新名字找到那个实体——因此那个实体必须是导入者有权指代的，即外部链接。模块链接的实体不行（导入者不在同一模块），内部链接的更不行。

这条规则的典型用途是**把全局模块片段中的声明重新导出**：传统头文件中的函数 `#include` 到全局模块片段后不会被导出，`export using ::f;` 把它导出。这也是标准库模块 `std` 的常见实现方式（libc++ 的 `std.cppm` 大量使用 `export namespace std { using std::vector; ... }`）。

¶5 Example 2（加注）：

```cpp title="b.h"
int f();
```

```cpp title="c.h（可导入头文件）"
int g();
```

```cpp title="TU #1：X.cppm"
export module X;
export int h();
```

```cpp title="TU #2：M.cppm" error
module;
#include "b.h"
export module M;
import "c.h";
import X;
export using ::f, ::g, ::h;     // OK：f、g 附属于全局模块，h 附属于 X，都是外部链接
struct S;
export using ::S;               // error: S 有模块链接
namespace N {
  export int h();
  static int h(int);            // #1
}
export using N::h;              // error: #1 有内部链接
```

最后一行展示了 using 声明与重载集的交互：`using N::h` 带入了 `N::h` 的**所有**重载，只要其中一个是内部链接，就违反 ¶5。

Note 2：被导出的**类型别名**的底层实体不必有外部链接名字：

```cpp title="M.cppm" ok
export module M;
struct S;
export using T = S;             // OK：导出名字 T，它表示类型 S（S 本身是模块链接）
```

这是"可见"与"可达"分离的经典用法：导入者可以写 `T`，但写不出 `S`。至于能否用 `T` 定义对象，取决于 `S` 的定义是否**可达**（[[module.reach#6]]）。

!!! impl "本机诊断"
    Clang 23 对 ¶5 的两个错误分别报 "using declaration referring to 'S' with module linkage cannot be exported" 和 "using declaration referring to 'h' with internal linkage cannot be exported"，并附上 "target of using declaration" 注释。

## 导出的重声明（¶6）

¶6 实体 X 的重声明：

- 若 X 是由**被导出的声明引入**的，则重声明**隐式导出**；
- 否则，重声明**不得**被导出，除非它是类型别名、命名空间或命名空间别名。

换句话说，**导出状态由首次声明决定**，之后只能"维持"不能"升级"：

- `export struct S; struct S { ... };` ——合法，定义隐式导出。这是常见写法：先在接口顶部导出声明，后面再定义。
- `struct S { ... }; export struct S;` ——非良构：S 首次声明时是模块链接，后来想改成外部链接。链接必须在首次声明时就确定，否则在两者之间编译的代码会以为 S 是模块链接的。

例外中的三者都不是"有链接的实体"的首次声明问题：类型别名可以随时重新声明并导出（指向同一类型即可）；命名空间是开放的，任何一次定义都可以选择导出（配合 ¶2.1）；命名空间别名同理。

¶6 Example 4（加注）：

```cpp title="M.cppm" error
export module M;
struct S { int n; };
typedef S S;
export typedef S S;             // OK：类型别名，可以导出
export struct S;                // error: 被导出的声明跟在未导出的声明之后
namespace N {                   // 外部链接，附属于全局模块，未导出
  void f();
}
namespace N {                   // OK：导出的命名空间重声明了未导出的命名空间
  export void g();
}
```

```cpp title="M2.cppm" ok
export module M2;
export struct X;
struct X { int a; };            // OK：隐式导出（¶6）
export int v();
int v() { return 1; }           // OK：隐式导出
```

!!! impl "本机诊断"
    Clang 23 对 `export struct S;` 报 "cannot export redeclaration 'S' here since the previous declaration has module linkage"。

## 导出与链接、名字查找（¶7）

¶7 Note 3（非规范）总结了几条后果：

- 被导出的声明引入的名字**永远不具有模块链接**。它们具有外部链接、无链接，或（在头文件单元中）内部链接。这直接来自 [[basic.link#4]] 的 ¶4.10："附属于具名模块**且未导出**"才是模块链接。
- 模块导出的命名空间作用域声明，可以被导入该模块的任何 TU 中的名字查找找到（[[basic.lookup]]）。
- 类和枚举的**成员名**，在该类型的定义**可达**的任何语境中都能被找到——成员不需要单独导出。

¶7 Example 5（加注）：

```cpp title="M.cppm（M 的接口单元）"
export module M;
export struct X {
  static void f();
  struct Y { };
};

namespace {
  struct S { };
}
export void f(S);               // 标准例子标为 OK——但见下方讨论
struct T { };
export T id(T);                 // OK：T 有模块链接，不是 TU-local

export struct A;                // A 以不完整类型导出

export auto rootFinder(double a) {
  return [=](double x) { return (x + a/x)/2; };
}

export const int n = 5;         // OK：n 有外部链接（模块接口中 const 不再隐含内部链接）
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
  X::f();                       // OK：X 被导出，且 X 的定义可达
  X::Y y;                       // OK：X::Y 作为完整类型随 X 导出
  auto f = rootFinder(2);       // OK
  return A{45}.value;           // error: A 不完整
}
```

逐行分析：

- `X::f()`、`X::Y`：成员不需要单独导出，X 的定义（在接口单元中）可达即可。
- `id(T)`：`T` 未导出，导入者写不出 `T`，但可以 `auto t = id({});` 调用它——返回值的类型是 `T`，`T` 的定义可达，一切正常。
- `rootFinder`：返回类型是 lambda 的闭包类型，没有名字，导入者用 `auto` 接住。注意 [[dcl.spec.auto#12]]：返回类型含占位符的导出函数，必须在导出声明所在 TU 中、私有模块片段之外定义——否则导入者无法推导返回类型。
- `A{45}.value`：`A` 被导出了（导入者能写出 `A`），但它的定义在**实现单元**中。实现单元不能被导入，也不在导入者的可达 TU 集合中，所以导入者看到的 `A` 永远是不完整的。这是"导出 ≠ 可用"的最好示例：导出控制名字，可达控制语义属性。

!!! lawyer "`export void f(S);` 真的 OK 吗？"
    这一行与 [[basic.link#17]] 存在张力。`S` 在无名命名空间中，具有内部链接，是 **TU-local** 类型（[[basic.link#15]]）。`export void f(S);` 是 `f`（一个非 TU-local 的外部链接函数）的声明，它的形参类型**命名**了 `S`（[[basic.link#13]]），按 [[basic.link#14]] 这是一个**暴露**（exposure）——非 inline 函数可以忽略的只是函数体，不包括声明符中的形参类型。而 [[basic.link#17]] 规定模块接口单元中非 TU-local 实体的声明是暴露时，程序**非良构**。

    所以按规范性文字，这一行应当是非良构的；例子中的 "OK" 注释（例子是非规范性的）很可能是 TU-local 规则（[[P1815R2]]）加入之前遗留下来的。本机 Clang 23 对这一行给出警告 `TU local entity 'S' is exposed [-WTU-local-entity-exposure]`，与规范性文字的方向一致（尽管只是警告）。

    这类"例子与规范冲突"的情况，language lawyer 的原则是：**以规范性文字为准**，例子只是辅助理解。

## 导出命名空间与语言链接规范（¶8）

¶8 Note 4：被导出的 *namespace-definition* 或被导出的 *linkage-specification* 中的声明**都是被导出的**，受被导出声明的所有规则约束。

`export namespace N { ... }` 等价于对其中每个声明加 `export`（因为 `export` 修饰的是整个命名空间定义，其中的声明都"在 *export-declaration* 之中"且栖居于命名空间作用域）。这很方便，但也意味着：里面不能有内部链接的东西，不能有对模块链接实体的 using 声明：

```cpp title="M.cppm" error
export module M;
int g;
export namespace N {
  int x;                        // OK
  using ::g;                    // error: ::g 有模块链接（¶5）
}
```

`export extern "C++" { ... }` 与 `extern "C++" { export ... }` 都能把声明既附属于全局模块又导出，常用于渐进迁移：

```cpp title="legacy.cppm" ok
export module legacy;
export extern "C++" {
  int parse(const char*);       // 附属于全局模块（[module.unit]/7.2.4），被导出
}                               // 修饰名与头文件时代相同：不含模块名
```

## 什么可以导出：速查

| 声明 | 能否 `export` | 依据 |
|---|---|---|
| 外部链接的函数、变量、类、枚举、模板、概念 | 能 | — |
| 模块接口中的 `const`/`constexpr` 变量 | 能（此处它们默认不是内部链接） | [[basic.link#3]] ¶3.2.1 |
| `static` 函数/变量，无名命名空间中的任何东西 | 不能 | ¶1、¶3 |
| 偏特化 | 不能 | ¶1 |
| 显式特化、显式实例化 | 不能（文法上 `export` 后只能接 *name-declaration*）；可以在 export 块中出现 | 文法 |
| 类型别名（`using T = ...;`、`typedef`） | 能，底层类型无需外部链接 | ¶5 Note 2 |
| using 声明 | 能，若指名的实体都是外部链接（或是类型别名） | ¶5 |
| using 指令 | 文法上能，但无效果 | ¶4 Example 1 |
| `static_assert` | 文法上能，但不引入名字 | 文法 |
| 命名空间 | 能；含被导出声明的命名空间定义自动被导出 | ¶2.1 |
| 类成员（单独） | 不能（不在命名空间作用域）；随类可达 | ¶1、¶7 |
| 首次声明未导出的实体的重声明 | 不能（除类型别名、命名空间、命名空间别名） | ¶6 |
| 导入声明 | `export import`：再导出 | [[module.import#7]] |

## 历史与演进

!!! history "C++20 → C++23"
    - C++20 [[P1103R3]] 确立了 `export` 的三种形式和"不能导出内部链接名字"的规则。Modules TS 中曾有 `export module` 之外的更多 `export` 用法限制，合并后统一为现在的形式。
    - C++23 周期中，[[P2615R1]]（"Meaningful exports"）作为对 C++20 的缺陷报告收紧了 `export` 能修饰的声明，例如禁止导出偏特化这类不引入新名字的声明。
    - 模块接口单元中 `const` 变量不再默认内部链接，是 C++20 随模块一起引入的链接规则变化（见 [[basic.link]]）。

## 陷阱

!!! pitfall "导出了名字，却用不了"
    `export struct A;` + 实现单元中定义 `A`：导入者只得到一个不完整类型。若希望导入者能创建 `A`，定义必须放在接口单元（或被导出的接口分区）中。这正是 PIMPL 式封装的模块版本——有时是刻意为之。

!!! pitfall "以为导出了类，成员函数就会 inline"
    `export struct S { int get() { return v; } int v; };` 在具名模块中，`get` **不是** inline 的（[[class.mfct#1]]）。导入者调用 `s.get()` 是一次跨 TU 的函数调用，除非开启 LTO 或编译器另有跨模块内联机制。需要 inline 就显式写 `inline`。

!!! pitfall "`export using namespace std;` 不会传给导入者"
    using 指令只影响本 TU 的名字查找。导出它是合法的空操作。

!!! pitfall "导出 inline 函数中调用未导出的函数"
    `void helper(); export inline void api() { helper(); }`——合法：`helper` 是模块链接，不是 TU-local。但若 `helper` 是 `static` 的，`api` 的定义就是一个暴露（[[basic.link#14]]），在模块接口中非良构。

## 思考题

!!! question "思考题 1"
    下面哪些行是非良构的？

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

- (1) OK：导出类型别名，底层实体无需外部链接（¶5 Note 2）。
- (2) 非良构：A 首次声明未导出，重声明不得导出（¶6）。
- (3)(4) OK：(4) 隐式导出（¶6）。
- (5) 非良构：无名命名空间具有内部链接，导出它违反 ¶3（标准 ¶4 Example 1 中的同一行被标为 error）。
</details>

!!! question "思考题 2"
    为什么 ¶6 允许 `namespace N { void f(); }` 之后再写 `export namespace N { void g(); }`，却不允许 `struct S {}; export struct S;`？

<details markdown="1">
<summary>答案</summary>

命名空间本身附属于全局模块、总是外部链接（[[module.unit#7]] ¶7.2.1），"导出"一个命名空间定义不改变命名空间的链接，只是让导入者能写出 `N::` 并找到其中被导出的成员——命名空间的每次定义可以独立选择。而 `S` 首次声明时获得的是**模块链接**；导出它的重声明意味着把它变成外部链接，链接在实体的生命中途改变，前后编译的代码会对同一实体的链接产生不同的认识。所以标准要求导出状态由首次声明决定。
</details>

## 小结

| 规则 | 段落 |
|---|---|
| `export` 只能在模块接口单元管辖范围的命名空间作用域中；不得在无名命名空间、私有模块片段中 | ¶1 |
| 不得导出偏特化；export 块不得嵌套 `export` 或含 `import`；`export` 不建立作用域 | ¶1 |
| 被导出 = 在 export 声明中且栖居于命名空间作用域；含被导出声明的命名空间定义；头文件单元中的声明 | ¶2 |
| 不得导出内部链接名字（头文件单元除外） | ¶3 |
| 导出的 using 声明只能指名外部链接实体或类型别名 | ¶5 |
| 导出状态由首次声明决定；类型别名/命名空间/命名空间别名例外 | ¶6 |
| 导出名字不会是模块链接；类成员随类定义的可达性被找到 | ¶7 |
| 导出的命名空间定义或语言链接规范中的声明都被导出 | ¶8 |
