---
title: 全局模块片段
summary: 模块单元在 module; 与模块声明之间包含传统头文件的地方；其中模块没有用到的声明会被丢弃，decl-reachable 关系精确规定了什么算用到。
status: done
since: c++20
papers: P1103R3
related: module.unit, module.import, module.reach, module.context, basic.lookup.argdep, cpp.pre, basic.def.odr, temp.dep
tags: 模块, 全局模块片段, 可达性
updated: 2026-10-19
---

!!! tldr
    - 模块单元要用传统头文件时，把 `#include` 写在 `module;` 和 `export module M;` 之间。这段叫全局模块片段，其中的声明附属于全局模块，与别处 `#include` 得到的是同一实体。
    - 全局模块片段里只能写预处理指令，声明只能通过 `#include` 引入。
    - 全局模块片段中的声明不会被导出，导入者看不到它们的名字。
    - 模块正文没有用到的声明会被丢弃，对模块单元之外既不可见也不可达；什么算用到，由 decl-reachable 关系规定。
    - 模板中依赖调用要找的函数如果只在全局模块片段里，可能已被丢弃，导入者实例化时就会失败。

## 模块里怎样使用传统头文件

<div class="compare" markdown="1">

```cpp title="wrong.cppm"
export module M;
#include "legacy.h"
// int parse(const char*);
// 这个 parse 附属于 M
export int use() {
  return parse("1");
}
```

```cpp title="right.cppm" ok
module;
#include "legacy.h"
// 全局模块片段：附属于全局模块
export module M;
export int use() {
  return parse("1");
}
```

</div>

绝大多数库仍以头文件发布，模块单元又必须以模块声明开头。如果像左边那样在 `export module M;` 之后 `#include`，头文件里的声明都在 M 的管辖范围中，按 [[module.unit#7]] 附属于 M。左边的 `parse` 因此是模块 M 自己的一个新函数，与库里定义的 `::parse` 不是同一个实体（[[basic.link#8]]）。本机 Clang 23 编译左边的文件，目标文件引用的符号是 `__ZW1M5parsePKc`（`parse@M`），而库提供的是 `__Z5parsePKc`，链接时找不到定义。对 `#include <...>` 形式，Clang 还会给出 `-Winclude-angled-in-module-purview` 警告。

¶1 右边的写法把 `#include` 放在模块声明之前。`module;` 到模块声明之间的部分是这个模块单元的**全局模块片段**（[[g:global-module-fragment|global module fragment]]）。它属于全局模块（[[module.unit#6]]），其中的声明附属于全局模块，在本模块单元中照常可用。它不在 M 的管辖范围中，所以不能在这里写 `export`（[[module.interface#1]]）。

```text
global-module-fragment:
    module-keyword ; declaration-seq(opt)
```

### 只能写预处理指令

[[cpp.pre#5]] 规定，在翻译阶段 4 开始时，全局模块片段中既不能有普通文本行，也不能有 `import` 指令。所以这里只能写 `#include`、`#define`、`#if` 之类的预处理指令，声明只能通过 `#include` 引入。

<div class="compare" markdown="1">

```cpp title="ok.cppm" ok
module;
#define _GNU_SOURCE
#include <cstdio>
export module M;
```

```cpp title="bad.cppm" error
module;
void f();
// error: 全局模块片段中
// 出现文本行
export module M;
```

</div>

全局模块片段只是兼容层，为 `#include` 服务。在模块中声明全局模块的实体，正规的写法是 `extern "C++"`（[[module.unit#7]]）；导入则应当写在模块管辖范围中（[[module.import#1]]）。

!!! impl "Clang 不诊断文本行"
    本机 Clang 23 对右边的 `bad.cppm` 不给任何诊断，即使开启 `-Wall -Wextra -pedantic`。[[cpp.pre#5]] 是可诊断规则，这是 Clang 不符合标准之处。写可移植的代码时，全局模块片段中只放预处理指令。

## 全局模块片段中的声明不会被导出

全局模块片段里的声明不在任何 *export-declaration* 中，所以不是被导出的。导入者的名字查找找不到它们：

```cpp title="lib.h"
#pragma once
namespace lib {
  struct Used { int v = 1; };
  inline int helper(Used u) { return u.v; }
}
```

```cpp title="L.cppm"
module;
#include "lib.h"
export module L;
export lib::Used make() { return {}; }
```

```cpp title="user.cpp" error
import L;
int main() {
  auto u = make();       // OK
  int a = u.v;           // OK：lib::Used 的定义可达，成员查找只需要定义可达
  return helper(u) + a;  // error: lib::helper 不可见
}
```

`helper(u)` 的实参依赖查找（ADL，按实参类型所在的命名空间查找函数）会进入 `lib`，但 `lib::helper` 附属于全局模块、没有导出，对 `user.cpp` 不可见。Clang 23 报 "use of undeclared identifier 'helper'"。

导入者想用 `lib::helper`，可以让模块 L 写 `export using lib::helper;`（[[module.interface#5]]），也可以自己 `#include "lib.h"`。

## 没有用到的声明会被丢弃

一个模块的全局模块片段可能包含了几十万行系统头文件，模块真正用到的只是一小部分。¶3 规定，全局模块片段中的声明 D，如果模块正文中没有任何声明用到它，D 就被**丢弃**（[[g:discarded-declaration|discarded]]）。用到的精确含义是下一节的 decl-reachable。

注 2 说明了丢弃的效果：被丢弃的声明在该模块单元之外既不可达也不可见。如果模板的实例化点（[[temp.point]]）在该模块单元之外，即使实例化语境（[[module.context]]）包含该模块单元，被丢弃的声明在实例化中也不可达、不可见。

丢弃有两个目的：

- 编译器不必把被丢弃的声明写进 BMI（二进制模块接口，编译器为导入者缓存的接口信息），接口文件更小。
- 导入者不会无意中依赖模块碰巧包含的头文件，例如通过 ADL 找到某个函数，或者让某个类型变得完整。否则模块作者删掉一个 `#include`，导入者就可能编译失败。

标准的例 2 展示了丢弃的效果：

```cpp title="foo.h"
namespace N {
  struct X {};
  int d();
  int e();
  inline int f(X, int = d()) { return e(); }
  int g(X);
  int h(X);
}
```

```cpp title="M.cppm（模块 M 的接口单元）"
module;
#include "foo.h"
export module M;
template<typename T> int use_f() {
  N::X x;                       // N::X、N 和 :: 从 use_f decl-reachable
  return f(x, 123);             // N::f 从 use_f decl-reachable；
                                // N::e、N::d 从 N::f decl-reachable，所以也从 use_f
                                // decl-reachable，即使这次调用没有用默认实参
}
template<typename T> int use_g() {
  N::X x;                       // N::X、N 和 :: 从 use_g decl-reachable
  return g((T(), x));           // N::g 不从 use_g decl-reachable
}
template<typename T> int use_h() {
  N::X x;                       // N::X、N 和 :: 从 use_h decl-reachable
  return h((T(), x));           // N::h 不从 use_h decl-reachable，但……
}
int k = use_h<int>();           // use_h<int> 从 k decl-reachable，
                                // N::h 从 use_h<int> decl-reachable，所以 N::h 没有被丢弃
```

```cpp title="M-impl.cpp（模块 M 的实现单元）" error
module M;
int a = use_f<int>();           // OK
int b = use_g<int>();           // error: 找不到 g，它已被丢弃
int c = use_h<int>();           // OK
```

`use_g<int>` 的实例化点在实现单元中，`g((T(), x))` 是依赖调用，要靠 ADL 在 `N` 中找 `g`。接口单元中没有任何声明用到 `N::g`，它已被丢弃，在实现单元里不可见。`N::h` 则因为接口中的 `int k = use_h<int>();` 实例化时用到了它而保留下来。

这也说明丢弃是脆弱的：删掉接口中看似无关的 `int k = use_h<int>();`，实现单元中的 `use_h<int>()` 就会编译失败。模块作者应当保证模板需要的东西被显式用到，或者干脆导出它们。

!!! impl "Clang 的两种 BMI"
    本机 Clang 23 上，这个例子的结果取决于 BMI 的生成方式：

    - 用 `--precompile` 生成的完整 BMI（约 30 KB）不实施丢弃，`use_g<int>()` 被接受。
    - 用 `-c M.cppm -fmodule-output=M.pcm` 一步生成目标文件和 BMI 时，默认产出 reduced BMI（约 24 KB；加 `-fno-modules-reduced-bmi` 则产出完整 BMI）。它实施丢弃，`use_g<int>()` 报 "use of undeclared identifier 'g'"，与标准一致。

    CMake 驱动 Clang 时使用的是 `-fmodule-output` 方式（见 [[toolchain/modules-in-practice]]）。同一份代码在不同构建方式下表现不同，这是不要依赖未被显式使用的全局模块片段声明的又一个理由。

## 什么算用到：decl-reachable（¶2）

丢弃要求编译器在模块定义时就判断一个声明是否被用到。难点在模板：依赖调用 `g(x)` 在定义时还不知道会调用谁。¶2 给出的是一个保守的、在定义时就能静态计算的关系。

### 直接用到（¶2.1–¶2.4）

¶2 在同一 TU 中，下面任一条成立时，声明 D 从声明 S [[g:decl-reachable|decl-reachable]]：

- ¶2.1 D 不声明函数或函数模板，而 S 中有指名 D 的 *id-expression*、*namespace-name*、*type-name*、*template-name* 或 *concept-name*。
- ¶2.2 D 声明函数或函数模板，而 S 中的某个表达式命名了它（[[basic.def.odr]] 意义上的命名，即被重载决议选中）。
- ¶2.3 S 含有依赖调用 E（[[temp.dep]]），把 E 中每个类型依赖的实参或操作数换成一个没有关联命名空间和关联实体的占位类型的值，对这个合成表达式所做的任何名字查找能找到 D。注 1 补充，这包括改写比较运算符时对 `operator==`、`operator<=>`、`operator!=` 的查找。
- ¶2.4 S 中有一个对含有 D 的重载集取地址的表达式（[[over.over]]），而目标类型是依赖的，例如 `static_cast<T>(&f)`。

函数和其他东西区别对待。写出函数名 `f` 时，名字查找可能找到一整个重载集，只有被选中的那个才算用到，这样可以丢弃更多无用的重载。

依赖调用在定义时无法做重载决议，所以 ¶2.3 只做名字查找，找到的全算。占位类型没有关联命名空间，所以合成表达式的 ADL 只考虑非依赖实参带来的命名空间。例 2 中：

- `f(x, 123)` 的 `x` 类型不依赖于 `T`，ADL 进入 `N`，找到 `N::f`。
- `g((T(), x))` 中，逗号表达式 `(T(), x)` 是类型依赖的（`T` 可能重载了逗号运算符），整个被换成占位值，ADL 不进入 `N`，找不到 `N::g`。

### 连带保留（¶2.5）

一个声明被用到，与它密不可分的声明也必须保留，否则它在导入者那里是残缺的。¶2.5 如果存在一个不是命名空间定义的声明 M，M 从 S decl-reachable，并且满足下面任一条，D 也从 S decl-reachable：

| 条款 | D 与 M 的关系 | 例子 |
|---|---|---|
| ¶2.5.1 | D 从 M decl-reachable（传递） | `N::f` 用到的 `N::e` |
| ¶2.5.2 | D 与 M 声明同一实体，且 D 不是友元声明、不栖居于块作用域 | 函数的前置声明与定义 |
| ¶2.5.3 | D 声明命名空间 N，M 是 N 的成员 | 外围的 `N` 和 `::` |
| ¶2.5.4 | 一个声明类 C，另一个声明 C 的成员或友元 | 类与成员，双向 |
| ¶2.5.5 | 一个声明枚举 E，另一个声明 E 的枚举项 | 枚举与枚举项，双向 |
| ¶2.5.6 | D 声明函数或变量，M 在 D 之中声明 | 函数体内的局部类，变量初始化器中 lambda 里的声明 |
| ¶2.5.7 | 一个声明模板，另一个声明它的偏特化、显式特化或实例化 | 例 2 中的 `use_h<int>` |
| ¶2.5.8 | M 声明类模板，D 是它的推导指引 | |
| ¶2.5.9 | 一个声明类或枚举类型，另一个为它引入用于链接的 typedef 名 | `typedef struct { ... } P;` |

¶2.5 要求 M 不是命名空间定义。`namespace std { ... }` 这样的定义包含了其中所有成员的声明；如果允许 M 是命名空间定义，只要一个成员被用到，经过外围命名空间就会把整个命名空间的内容拉进来，丢弃就失效了。所以从成员只能单向走到外围命名空间（¶2.5.3），不能再从命名空间扩散出去。

### 由实现决定的部分（¶2.6–¶2.10）

做上述判定时，下面这些替换是否先行发生是未指明的：

- ¶2.6 对别名声明、typedef、using 声明、命名空间别名的引用，是否先替换为它们指名的声明；
- ¶2.7 不表示依赖类型的别名模板特化，是否先替换为它表示的类型；
- ¶2.8 不表示依赖类型的 `decltype`，是否先替换为它表示的类型；
- ¶2.9 非值依赖的常量表达式，是否先替换为求值结果；
- ¶2.10 非依赖语境中的拼接（splice，[[basic.splice]]），是否先替换为它指代的构造。

编译器构建语法树时，常常已经把别名、`decltype`、常量表达式替换成了它们表示的东西。例如 `int a[size];` 的类型可能直接记为 `int[2]`，要追溯到对 `size` 的引用就得额外保留信息。标准不强迫实现保留这些信息，代价是依赖这些引用的判定在不同实现上可能不同。标准的例 1：

```cpp
const int size = 2;
int ary1[size];                 // 未指明 size 是否从 ary1 decl-reachable（¶2.9）
constexpr int identity(int x) { return x; }
int ary2[identity(2)];          // 未指明 identity 是否从 ary2 decl-reachable

template<typename> struct S;
template<typename, int> struct S2;
constexpr int g(int);

template<typename T, int N>
S<S2<T, g(N)>> f();             // S、S2、g 和 :: 都从 f decl-reachable
                                // g(N) 是值依赖的，不会被替换

template<int N>
void h() noexcept(g(N) == N);   // g 和 :: 从 h decl-reachable
```

### 从哪里出发（¶3）

¶3 判断是否丢弃时，出发点是 TU 的 *declaration-seq* 中的声明。按 *translation-unit* 的文法，这是模块声明之后、私有模块片段之前的部分。

- 全局模块片段内部的声明互相引用不算。
- 只被私有模块片段用到的声明会被丢弃。这没有问题，私有模块片段本来就对其他 TU 不可达，被丢弃的声明在本模块单元内照常可用。
- 只有模块单元的全局模块片段会丢弃声明，普通 TU 不丢弃任何东西。

[[basic.lookup.argdep#4]] 与此配合：依赖名的 ADL 会从实例化语境中的每个点查找，但忽略那些出现在其他 TU、附属于全局模块、并且已被丢弃或具有内部链接的声明。

## 实现视角

!!! impl "全局模块片段与 ODR"
    全局模块片段中通过 `#include` 引入的 inline 函数、类定义等，与其他 TU 通过 `#include` 得到的是同一个实体，必须遵守 ODR 对多处定义一致的要求（[[basic.def.odr]]）。模块的全局模块片段在定义了 `NDEBUG` 时包含某个头文件，另一个 TU 不定义 `NDEBUG` 就包含它，于是得到两份不同的 inline 函数定义，这和使用传统头文件时一样是 IFNDR（违反了不要求诊断的规则，程序没有任何保证）。

    编译器导入多个 BMI 时要合并其中同一个全局模块实体的定义，这时有机会发现只用头文件时发现不了的违规。本机实验：模块 A 的全局模块片段在 `#define BIG` 后包含 `cfg.h`（得到 `struct Cfg { long v; }`），模块 B 不定义 `BIG` 就包含它（得到 `struct Cfg { int v; }`）。在同时导入 A 和 B 的 TU 中访问 `a().v`，Clang 23 报 "reference to 'v' is ambiguous"，并把两个 `Cfg::v` 都列为候选。按标准这是 IFNDR，这样的诊断只是额外的好处。

## 历史与演进

!!! history
    - 全局模块片段来自 Modules TS，C++20 的 [[P1103R3]] 要求它以 `module;` 开头，这样不用解析就能从第一行认出一个文件是模块单元。设计背景见 [[history/modules]]。
    - decl-reachable 与丢弃规则也来自 C++20 的合并方案，之后经过多次修正，例如注 1 中改写比较运算符时的查找，以及随 C++26 反射加入的 ¶2.10。

## 常见误解

!!! pitfall "导入者能用模块全局模块片段里的名字"
    不能，它们没有导出。导入者需要什么，应当自己 `#include` 或 `import`。

!!! pitfall "导出的模板做依赖调用，目标函数只在全局模块片段里"
    就是例 2 中的 `use_g`：模块正文从未以非依赖的方式用到 `N::g`，它被丢弃，在模块外实例化时找不到。解决办法是在模块中让它被用到（例如 `using N::g;`），或者改成非依赖地调用它。

## 思考题

!!! question "思考题 1"
    全局模块片段包含了 `struct P { int x; }; struct Q { P p; };`，模块正文只有 `export Q make();`。`P` 会被丢弃吗？

<details markdown="1">
<summary>答案</summary>

不会。`Q` 从 `make` decl-reachable（¶2.1，*type-name* 指名了 `Q`）。由 ¶2.5.4，成员 `p` 的声明也 decl-reachable；`p` 的声明中有 *type-name* `P`，再由 ¶2.1 和 ¶2.5.1，`P` 也 decl-reachable。直观上也必须如此：导入者使用 `Q` 需要知道它的布局，进而需要 `P` 是完整类型。
</details>

!!! question "思考题 2"
    为什么 ¶2.2 只把被选中的函数算作用到，而 ¶2.3 对依赖调用却把名字查找找到的所有声明都算上？

<details markdown="1">
<summary>答案</summary>

非依赖调用在定义处就完成了重载决议，被选中的函数是确定的，其他重载在任何情况下都不会被这次调用用到，可以安全丢弃。依赖调用的重载决议推迟到实例化时，那时可能选中名字查找找到的任何一个候选，定义时无法排除，只能全部保留。但只有依赖实参才能经 ADL 找到的候选不在其中，因为占位类型没有关联命名空间；这部分是有意排除的，由模块作者负责让它们被用到。
</details>
