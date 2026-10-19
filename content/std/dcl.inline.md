---
title: inline 说明符
summary: inline 在标准里的约束性含义是允许在多个翻译单元中各有一份相同的定义，而它们仍是同一个实体、同一个地址；内联展开只是不具约束力的提示。本页还讲 inline 变量、哪些东西隐式 inline，以及链接器怎样处理这些定义。
status: done
since: c++98
papers: P0386R2
related: basic.def.odr, basic.link, dcl.constexpr, class.mfct, class.friend, class.static.data, module.unit
tags: 声明, ODR, inline, 链接
updated: 2026-10-19
---

!!! tldr
    - inline 函数和 inline 变量可以在多个翻译单元中各有一份定义（必须相同），整个程序里它们仍是一个实体、一个地址，里面的静态局部变量也只有一份。
    - `inline` 不改变链接；要求编译器内联展开的那一段只是提示，实现可以不理会。
    - 不能先给出非 inline 的定义，再补一个 inline 声明；一个翻译单元认为是 inline、另一个认为不是，属于不要求诊断的错误。
    - 类内定义的成员函数、constexpr 函数、`static constexpr` 数据成员都隐式 inline；函数模板不是 inline 的，它的显式特化放进头文件时要自己写 `inline`。
    - 链接器按名字保留其中一份定义，不比较内容，所以各份定义不一致时不会报错。

## inline 的真正含义

```cpp title="counter.h"
inline int next_id() {
    static int n = 0;          // 整个程序只有一个 n
    return ++n;
}
inline int global_config = 42; // C++17：整个程序只有一个 global_config
```

```cpp title="a.cpp"
#include "counter.h"
int* addr_a() { return &global_config; }
int call_a() { return next_id(); }
```

```cpp title="b.cpp"
#include "counter.h"
#include <cassert>
int* addr_a();
int call_a();
int main() {
    assert(addr_a() == &global_config);  // 同一个地址
    call_a();
    assert(next_id() == 2);              // 两个 TU 共用同一个静态局部变量
}
```

`counter.h` 被两个翻译单元（TU，单独编译的源文件及其包含的头文件）包含，`next_id` 和 `global_config` 在两边各有一份定义。去掉 `inline`，链接时会报重复定义；加上 `inline`，程序正常运行，两个断言都成立。本机 Clang 23 编译运行验证过。

¶2 带 `inline` 的函数声明声明一个 **inline 函数**（[[g:inline-function]]），带 `inline` 的变量声明声明一个 **inline 变量**（[[g:inline-variable]]）。它们的关键性质写在注 1 里：

!!! std
    An inline function or variable with external or module linkage can be defined in multiple translation units, but is one entity with one address.

有外部链接或模块链接的 inline 函数或变量，可以在多个 TU 中定义（[[basic.def.odr]] 要求这些定义相同），但它仍然只是一个实体，只有一个地址。注 1 接着推出：在这种函数体内定义的类型和静态变量也只有一份。头文件里写 Meyers 单例（函数内的 `static` 局部对象）能正确工作，靠的就是这一点。

把函数定义写进头文件，需要的正是这种语义。C++17 把它推广到变量（[[P0386R2]]），也说明 `inline` 早已不是优化提示：内联展开一个变量没有意义。

### inline 不改变链接（¶2 注 2）

`inline void f();` 仍然有外部链接；`static inline void f();` 有内部链接，每个 TU 有自己的 `f`，多份定义的问题也就不存在。

注 2 还提醒，inline 函数有时不能使用内部链接的名字（[[basic.link]]）。模块接口里不能暴露只属于本 TU 的实体；头文件里的 inline 函数如果引用了 `static` 变量，每个 TU 中的定义引用的是不同的对象，这些定义就不相同了：

```cpp ifndr
// header.h
static int helper_state = 0;                    // 每个 TU 一份
inline int bump() { return ++helper_state; }    // 每个 TU 里引用的对象不同：违反 ODR
```

这种违反 ODR 的程序是**非良构、不要求诊断**（IFNDR）的：编译器和链接器可以不给任何提示，程序没有任何保证。

### 内联展开只是提示（¶3）

¶3 规定，`inline` 向实现表示在调用处展开函数体优于普通调用。实现不必展开；即使不展开，其余关于 inline 函数的规则仍然适用。

实际的优化器会内联它认为合适的任何函数，包括非 inline 函数，也会拒绝内联它认为不合适的 inline 函数。GCC 和 Clang 只把 `inline` 当作一个很弱的启发信号。需要强制内联或禁止内联时，用实现的扩展：`[[gnu::always_inline]]`、`[[gnu::noinline]]`、MSVC 的 `__forceinline`。

## 能写在哪里（¶1）

```cpp error
inline struct T { };         // error: 没有声明变量或函数
void g() {
    inline int x = 0;        // error: 块作用域
}
void h(inline int);          // error: 形参
```

¶1 `inline` 只能用于函数或变量的声明，不能出现在块作用域的声明上，也不能用于形参。`inline struct S { int v; } s;` 是合法的，因为 `inline` 修饰的是变量 `s`。

块作用域里的变量，要么是只在这里定义一次的局部变量，谈不上多个 TU 的多份定义；要么是 `extern` 声明，指向外面的某个变量。块作用域的函数声明也总是指向外面的函数。在后两种情况里，`inline` 应该写在那个实体自己的声明上。

¶1 最后一句规定，友元函数声明带 `inline` 时，它必须是定义，或者这个函数之前已经声明为 inline。`struct S { friend inline void f(); };` 可能是 `f` 的第一次声明；它把 `f` 变成 inline 函数，于是每个使用 `f` 的 TU 都必须有 `f` 的定义（见下一节），而这个义务藏在类里，很容易被忽略。本机 Clang 23 不检查这一条（见 [[dcl.friend]]）。

## 先 inline，后定义（¶4）

<div class="compare" markdown="1">

```cpp run ok
inline void f();   // 先声明为 inline
void f() { }       // OK: 定义不必再写
void g();
inline void g() { }
// OK: 第一次 inline 声明就是定义
int main() { f(); g(); }
```

```cpp error
void f() { }
inline void f();
// error: 定义已经可达
int v = 1;
inline int v;
// error: 同理（也是重定义）
```

</div>

¶4 第一条：在函数或变量第一次声明为 inline 的位置，如果它的定义已经可达，程序非良构。编译器看到非 inline 的定义时，可能已经把它当作只有一份的普通外部定义输出了，事后的 inline 声明没法撤回这个决定。

第二条针对多个 TU。先要一个词：**定义域**（definition domain）指一个 TU 中私有模块片段以外的部分，或者私有模块片段本身（[[basic.def.odr#13]]）；不用模块时，一个 TU 就是一个定义域。如果一个有外部或模块链接的函数或变量在某个定义域里声明为 inline，那么在每个声明了它的定义域的末尾，都必须能看到一个 inline 声明。违反这一条不要求诊断 {{ifndr}}：TU A 认为 `f` 是 inline 的，TU B 认为不是，单独编译哪个 TU 都看不出问题。

注 3 指出，在一个 TU 里，可以在 inline 函数的定义出现之前就调用它，只要定义域末尾能看到定义（[[basic.def.odr#13]]）：

```cpp run ok
inline int twice(int);
int use() { return twice(21); }     // OK: 定义在后面
inline int twice(int x) { return 2 * x; }
int main() { return use() - 42; }
```

## 模块中的 inline（¶5）

¶5 附属于具名模块的 inline 函数或变量，在哪个定义域里声明，就必须在那个定义域里定义。

注 4 提醒了两条隐式 inline 的规则：constexpr 函数隐式 inline（[[dcl.constexpr#1]]）；在类定义内定义的函数，只有在全局模块中（即不属于任何具名模块时）才隐式 inline（[[class.mfct#1]]、[[class.friend#6]]）。

所以 C++20 起，具名模块接口里的 `export struct S { void f() { … } };` 中，`f` 不是 inline 的。模块接口可以只在模块自己的目标文件里编译一次函数体；如果类内定义的函数自动 inline，导入者就得看到并内联函数体，修改函数体会影响所有导入者，违背模块分离接口与实现的目标。需要 inline 时，在模块里显式写出来。

## 哪些东西隐式 inline

| 实体 | 是否 inline | 依据 |
|---|---|---|
| 类定义内定义的成员函数（全局模块） | 是 | [[class.mfct#1]] |
| 类定义内定义的友元函数（全局模块） | 是 | [[class.friend#6]] |
| 具名模块中，类定义内定义的成员函数、友元函数 | 否 | 同上 |
| `constexpr`、`consteval` 函数 | 是 | [[dcl.constexpr#1]] |
| 首次声明带 `constexpr` 的静态数据成员 | 是 | [[dcl.constexpr#1]] |
| 命名空间作用域的 `constexpr` 变量 | 否（但 const 变量默认内部链接） | [[basic.link#3]] |
| `static const int` 这类非 constexpr 静态数据成员 | 否 | [[class.static.data]] |
| 弃置函数（`= delete`） | 是 | [[dcl.fct.def.delete#4]] |
| 在首次声明上显式预置的函数（`= default`） | 是 | [[dcl.fct.def.default#3]] |
| 隐式声明的特殊成员函数 | 是 | [[class.default.ctor]]、[[class.copy.ctor]]、[[class.dtor]] 等 |
| 非泛型 lambda 的函数调用运算符 | 是 | [[expr.prim.lambda.closure#5]] |
| 函数模板、变量模板 | 否（ODR 对模板另有豁免） | [[basic.def.odr]] |

最后一行常被误解。函数模板能写在头文件里，是因为 ODR 允许模板在多个 TU 中定义，而不是因为它是 inline 的。显式特化 `template<> void f<int>() { }` 是一个普通函数，不再享有模板的豁免，放在头文件里被多个 TU 包含时，就需要写 `inline`：

```cpp title="spec.h"
template<class T> void describe() { }            // 模板：可以在多个 TU 中定义
template<> inline void describe<int>() { }       // 显式特化：要写 inline 才能放进头文件
```

## 链接器怎样处理多份定义

!!! impl "COMDAT 与模糊链接"
    对每个被使用的 inline 函数或变量，编译器在每个 TU 的目标文件里都输出一份定义，并标记为可合并，由链接器保留其中一份：

    - ELF（Linux）：每个 inline 实体放进一个 COMDAT 组，符号为 `WEAK`，同名的组只保留一个。
    - Mach-O（macOS）：`nm -m` 显示为 `weak external`。
    - LLVM IR：链接类型为 `linkonce_odr`。`linkonce` 表示没被引用时可以丢弃，`odr` 表示编译器可以假设各份定义等价，于是可以内联其中任意一份的函数体。
    - COFF（Windows）：选择方式为 `IMAGE_COMDAT_SELECT_ANY` 的 COMDAT 节。

    GCC 文档把这种可能出现在多个目标文件里、由链接器去重的方式叫做 vague linkage（模糊链接），inline 函数、模板实例、虚表、`type_info` 对象都这样处理。

    下面是 `inline int counter`、`inline int next()` 及其静态局部变量在 x86-64 ELF 目标文件中的 COMDAT 组（本机 Clang 23 `--target=x86_64-linux-gnu` 编译，`llvm-readelf -g` 输出节选）：

    ```text
    COMDAT group section [    4] `.group' [_Z4nextv] contains 2 sections:
       [    5]   .text._Z4nextv
    COMDAT group section [    7] `.group' [_ZZ4nextvE1n] contains 1 sections:
       [    8]   .bss._ZZ4nextvE1n
    COMDAT group section [    9] `.group' [counter] contains 1 sections:
       [   10]   .bss.counter
    ```

    有动态初始化的 inline 变量还会配一个同样可合并的守卫变量（Itanium ABI 中修饰名以 `_ZGV` 开头），保证即使多个 TU 都带着初始化代码，变量也只初始化一次。

!!! warning "定义不一致时链接器不会报错"
    如果两个 TU 中 inline 函数的定义不同（例如受不同的宏影响），程序是 IFNDR。链接器只按名字挑一份保留，通常是第一个遇到的，不比较内容。结果可能是某个 TU 里内联展开的是版本 A，另一个 TU 通过调用得到的是版本 B，极难调试。使用 `-flto` 时，GCC 的 `-Wodr` 能发现其中一部分。

!!! warning "动态库"
    一个实体、一个地址是标准对单个程序的保证，而标准不知道动态库的存在。在 Windows 上，每个 DLL 默认各有一份 inline 变量和静态局部变量；在 ELF 上，用了 `-fvisibility=hidden` 或 `-Bsymbolic` 等选项也可能出现多份。跨动态库共享状态时，不要依赖 inline 变量的唯一性。

!!! history "历史与演进"
    - C++98：`inline` 是函数说明符，与 `virtual`、`explicit` 并列；主要规则是每个使用 inline 函数的 TU 都必须有它的定义。
    - C++11：constexpr 函数隐式 inline。
    - C++17：inline 变量（[[P0386R2]]），`inline` 不再是函数说明符；`static constexpr` 数据成员隐式 inline，解决了类内初始化的 `static const` 成员被 odr-use 时还要类外定义的老问题。
    - C++20：模块；具名模块中类内定义的函数不再隐式 inline；原来按 TU 表述的规则改用定义域和可达来表述。

!!! pitfall "常见误解"
    - inline 让函数被内联：既不保证，也不是它的主要含义。
    - inline 函数有内部链接：没有，`inline` 不影响链接。
    - `static inline` 和 `inline` 一样：不一样，`static inline` 函数每个 TU 一份，各有自己的地址和静态局部变量。
    - 函数模板隐式 inline：不是，它享有模板自己的 ODR 豁免；显式特化要自己写 `inline`。
    - 命名空间作用域的 constexpr 变量是 inline 的：不是，只有静态数据成员是。

!!! question "思考题 1"
    头文件里在命名空间作用域写 `const std::string kName = "x";`，被 100 个 TU 包含，会发生什么？写成 `inline const std::string kName = "x";` 呢？

<details markdown="1">
<summary>答案</summary>

const 变量默认有内部链接（[[basic.link#3]]），所以每个 TU 都有自己的 `kName`，各自在启动时动态初始化。结果是 100 个对象、100 次构造和析构，地址各不相同。加上 `inline` 后它有外部链接，整个程序只有一个对象，由守卫变量保证只初始化一次，所有 TU 看到同一个地址。
</details>

!!! question "思考题 2"
    为什么 `struct S { static const int N = 10; }; const int& r = S::N;` 在 C++14 中可能链接失败，而在 C++17 中把 `const` 换成 `constexpr` 就没问题？

<details markdown="1">
<summary>答案</summary>

非 inline 静态数据成员在类内的声明不是定义（[[basic.def#2]] 的第 2.3 项）。把引用 `r` 绑定到 `S::N` 是对它的 odr-use，需要一个定义；程序中没有 `const int S::N;` 时，链接器找不到符号。C++17 起 `static constexpr int N = 10;` 隐式 inline（[[dcl.constexpr#1]]），类内声明就是定义，每个 TU 都输出一份可合并的定义。C++17 中 `static const int N = 10;` 仍然不是 inline 的，问题依旧。
</details>
