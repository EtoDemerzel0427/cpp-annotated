---
title: inline 说明符
summary: inline 在标准中的真正含义是允许在多个翻译单元中定义，但仍是同一个实体、同一个地址，内联替换只是一个不具约束力的提示；inline 变量（C++17）；哪些函数和变量隐式 inline；链接器层面的 COMDAT / vague linkage
status: done
since: c++98
papers: P0386R2
related: basic.def.odr, basic.link, dcl.constexpr, class.mfct, class.friend, class.static.data, module.unit
tags: 声明, ODR, inline, 链接
updated: 2026-10-17
---

几乎每个 C++ 程序员都学过这样一句话：`inline` 建议编译器把函数内联展开。这句话在 1990 年代大致正确，但在今天的标准里，它只对应一个不具约束力的段落（¶3）。`inline` 在标准中真正有约束力的含义与 ODR 有关：

> inline 函数或变量可以在多个翻译单元中各有一个定义（只要这些定义相同），而它们仍然是**同一个实体**、具有**同一个地址**。

把函数定义写在头文件里，需要的正是这种语义。C++17 把它扩展到变量（[[P0386R2]]），于是把 `inline` 看作优化提示的说法就站不住了：内联展开一个变量是什么意思呢？

阅读本节之前，需要了解 ODR 中关于可以有多个定义的实体的规则（[[basic.def.odr]]），以及链接（[[basic.link]]）。

## 适用范围（¶1）

¶1 规定 `inline` 只能用于函数或变量的声明，不能出现在块作用域的声明上，也不能用于函数参数。如果用于友元函数声明，该声明必须是定义，或者该函数之前已经声明为 inline。

```cpp error
inline struct T { };         // error: inline 不能用于类（没有声明变量或函数）
void g() {
    inline int x = 0;        // error: 块作用域声明
}
void h(inline int);          // error: 参数
```

```cpp run ok
inline struct S { int v; } s;    // OK: inline 修饰的是变量 s，不是类 S
int main() { return s.v; }
```

为什么块作用域不能用 `inline`？块作用域的变量没有链接，不可能在多个 TU 中定义，ODR 豁免对它没有意义；块作用域的函数声明则总是指向外部的某个函数，`inline` 应当写在那个函数自己的声明上。

友元的那条限制针对的是 `struct S { friend inline void f(); };` 这类写法。这个友元声明可能是 `f` 的首次声明，如果它只是声明却又标了 inline，那么每个使用 `f` 的 TU 中都必须有 `f` 的定义（见 ¶4）。这个声明藏在类里，这项义务很容易被忽略。

## inline 函数与 inline 变量（¶2）

¶2 规定，带 `inline` 的函数声明声明一个 **inline 函数**（[[g:inline-function]]），带 `inline` 的变量声明声明一个 **inline 变量**（[[g:inline-variable]]）。

理解 inline 的关键在 Note 1：

!!! std
    An inline function or variable with external or module linkage can be defined in multiple translation units, but is one entity with one address.

    具有外部或模块链接的 inline 函数或变量可以在多个 TU 中定义，但它是**一个**实体，只有**一个**地址。

由此可以推出，在这样的函数体内定义的类型和静态局部变量也是唯一的。头文件中 inline 函数里的 `static` 局部变量在整个程序中只有一份，Meyers 单例写在头文件里也能正确工作，原因就在这里。

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
    assert(next_id() == 2);              // 两个 TU 共享同一个静态局部变量
}
```

Note 2 指出，`inline` 不影响函数的链接。`inline void f();` 仍然具有外部链接；`static inline void f();` 具有内部链接，此时 ODR 豁免无关紧要，每个 TU 都有自己的 `f`。在某些情况下，inline 函数不能使用具有内部链接的名字（[[basic.link]]）：模块接口中不能暴露 TU 局部实体；在头文件中，如果 inline 函数引用了 `static` 变量，不同 TU 中的定义引用的就是不同的实体，违反了 [[basic.def.odr]] 要求各定义相同的规定。

```cpp
// header.h —— 一个典型的 ODR 违规
static int helper_state = 0;                       // 每个 TU 一份
inline int bump() { return ++helper_state; }       // 每个 TU 中的 bump 引用不同的 helper_state
                                                   // → 多个定义不"相同"：IFNDR
```

## 内联替换只是提示（¶3）

¶3 规定，`inline` 向实现表明，在调用点做内联替换优于通常的函数调用机制。实现不必这样做；即使不做内联替换，本节关于 inline 函数的其他规则也仍须遵守。

这一段在今天几乎没有实际作用：

- 优化器会内联它认为合适的任何函数（包括非 inline 函数），也会拒绝内联它认为不合适的任何 inline 函数。GCC 和 Clang 在决策时会把 `inline` 关键字当作一个微弱的启发式信号，但影响有限。
- 真正需要强制内联或禁止内联时，实现提供了扩展：`[[gnu::always_inline]]`、`__forceinline`（MSVC）、`[[gnu::noinline]]`。

所以应当把 `inline` 理解为链接层面的工具，它的作用是允许在多处定义，而不是优化层面的工具。

## 声明顺序与跨 TU 一致性（¶4）

¶4 包含两条规则：

1. 如果在函数或变量首次声明为 inline 的位置，它的定义已经可达，程序非良构。也就是说，不能先定义一个非 inline 的函数，再补一个 inline 声明。
2. 如果一个具有外部或模块链接的函数或变量在某个**定义域**（definition domain，[[basic.def.odr#13]]：一个私有模块片段，或一个 TU 中除私有模块片段外的部分）中声明为 inline，那么在声明它的每个定义域的末尾，都必须有一个 inline 声明可达；不要求诊断 {{ifndr}}。

```cpp error
void f() { }
inline void f();       // error: f 的定义在此已可达，不能事后声明为 inline
int v = 1;
inline int v;          // error: 同理（这里还是 v 的重定义）
```

```cpp run ok
inline void f();       // 先声明为 inline
void f() { }           // OK: 定义不必重复 inline，f 已是 inline 函数
void g();
inline void g() { }    // OK: 首次的 inline 声明就是定义本身，此前没有可达的定义
int main() { f(); g(); }
```

为什么禁止先定义、后 inline？编译器看到非 inline 定义时，可能已经把它当作只此一份的强符号处理，发射了一个普通的外部定义；之后的 inline 声明会改变这个决定，而这时已经无法撤回。规则 2 针对的是多个 TU 的情形：如果 TU A 认为 `f` 是 inline 的（生成弱符号），TU B 却认为它不是（生成强符号），链接结果就取决于具体实现。这种情况无法在单个 TU 中诊断，所以是 IFNDR。

Note 3 指出，在一个 TU 中，可以在 inline 函数的定义可达之前就调用它，inline 变量也可以在定义可达之前使用，只要定义最终在该定义域末尾可达即可（[[basic.def.odr#13]] 要求：对于被 odr-use 的 inline 函数或变量，从每个使用它的定义域末尾都必须能到达其定义）。

```cpp run ok
inline int twice(int);
int use() { return twice(21); }     // OK: 定义在后面
inline int twice(int x) { return 2 * x; }
int main() { return use() - 42; }
```

## 模块中的 inline（¶5）

¶5 规定，如果一个附属于具名模块的 inline 函数或变量在某个定义域中声明，它就必须在该定义域中定义。

Note 4 说明了两条与模块相关的隐式 inline 规则：

- constexpr 函数隐式 inline（[[dcl.constexpr#1]]）；
- 只有在全局模块中，在类定义内定义的函数才隐式 inline（[[class.mfct#1]]、[[class.friend#6]]）。

第二条是 C++20 的一个重要变化：在具名模块的接口单元中，`export struct S { void f() { … } };` 中的 `f` 不是 inline 的。为什么？模块接口编译后生成 BMI（二进制模块接口），模块的实现可以只在模块自己的目标文件中编译一次。如果类内定义的函数自动 inline，修改函数体就会改变所有导入者需要看到的内容，违背了模块分离接口与实现的 ABI 目标。需要 inline 时，应显式写出 `inline`。

## 哪些东西隐式 inline

本节本身只提到其中一部分。下表汇总了散布在标准各处的规则：

| 实体 | 隐式 inline？ | 依据 |
|---|---|---|
| 类定义内定义的成员函数（全局模块） | 是 | [[class.mfct#1]] |
| 类定义内定义的友元函数（全局模块） | 是 | [[class.friend#6]] |
| 具名模块中，类定义内定义的成员/友元函数 | **否** | 同上（条件不满足） |
| `constexpr` / `consteval` 函数 | 是 | [[dcl.constexpr#1]] |
| 首次声明带 `constexpr` 的静态数据成员 | 是 | [[dcl.constexpr#1]] |
| 命名空间作用域的 `constexpr` 变量 | **否**（但 const 默认内部链接） | [[basic.link#3]] |
| `static const int` 等非 constexpr 静态数据成员 | **否** | [[class.static.data]] |
| 被弃置的函数（`= delete`） | 是 | [[dcl.fct.def.delete#4]] |
| 在首次声明上显式预置的函数（`= default`） | 是 | [[dcl.fct.def.default#3]] |
| 隐式声明的特殊成员函数 | 是（"inline public member"） | [[class.ctor.general]]、[[class.dtor]] 等 |
| 非泛型 lambda 的函数调用运算符 | 是 | [[expr.prim.lambda.closure#5]] |
| 函数模板、变量模板 | **否**（但有自己的 ODR 豁免） | [[basic.def.odr]] |

最后一行常被误解。函数模板不是 inline 函数，它能写在头文件里，是因为 ODR 对模板另有豁免。区别体现在显式特化上：`template<> void f<int>() { }` 是一个普通函数，不再享有模板的豁免，如果写在头文件里被多个 TU 包含，就需要显式加上 `inline`。

```cpp title="spec.h"
template<class T> void describe() { }            // 模板：可在多个 TU 中定义
template<> inline void describe<int>() { }       // 显式特化：必须写 inline 才能放在头文件中
```

## 实现视角：COMDAT 与模糊链接

!!! impl "inline 在目标文件里长什么样"
    对每个被 odr-use 的 inline 函数或变量，编译器在每个 TU 的目标文件中都发射一份定义，并把它标记为可合并，由链接器保留其中一份。具体机制如下：

    - ELF（Linux）：每个 inline 实体放在一个 **COMDAT 组**中，符号为 `WEAK`；对同名的 COMDAT 组，链接器只保留一个（见下方输出）。
    - Mach-O（macOS）：`nm -m` 显示为 `weak external`。
    - LLVM IR：链接类型为 `linkonce_odr`。`linkonce` 表示未被引用时可以丢弃，`odr` 表示编译器可以假设所有定义等价（因此可以内联其中任意一份定义的函数体，也可以做跨定义的优化）。
    - COFF（Windows）：`IMAGE_COMDAT_SELECT_ANY` 的 COMDAT 节。

    GCC 文档把这种可能出现在多个目标文件中、由链接器去重的链接方式称为 **vague linkage**（模糊链接），适用对象包括 inline 函数、模板实例化、vtable、type_info 对象等。

    下面是 `inline int counter`、`inline int next()` 及其静态局部变量在 x86-64 ELF 目标文件中的 COMDAT 组（`llvm-readelf -g` 输出节选）：

    ```text
    COMDAT group section [    4] `.group' [_Z4nextv] contains 2 sections:
       [    5]   .text._Z4nextv
    COMDAT group section [    7] `.group' [_ZZ4nextvE1n] contains 1 sections:
       [    8]   .bss._ZZ4nextvE1n
    COMDAT group section [    9] `.group' [counter] contains 1 sections:
       [   10]   .bss.counter
    ```

    有动态初始化的 inline 变量还会配一个同样是 `linkonce_odr` 的守卫变量（Itanium ABI 中 mangled 名以 `_ZGV` 开头）。即使多个 TU 都包含了初始化代码，守卫变量也能确保变量只初始化一次。

!!! warning "ODR 违规时链接器不会报错"
    如果两个 TU 中 inline 函数的定义不同（例如受不同的宏影响），程序非良构，但不要求诊断（[[basic.def.odr]]）。链接器只是按名字挑一份保留，通常是第一个遇到的，不会比较内容。结果可能是某个 TU 中内联展开的是版本 A，另一个 TU 通过调用得到的却是版本 B。这类问题极难调试。使用 `-flto` 时，GCC 的 `-Wodr` 和一些链接器选项可以发现其中一部分。

!!! warning "动态库"
    一个实体、一个地址，这是标准在单个程序内给出的保证，而标准并不知道动态库的存在。在 Windows 上，每个 DLL 默认各有一份 inline 变量和静态局部变量；在 ELF 上，如果使用了 `-fvisibility=hidden` 或 `-Bsymbolic` 等选项，也可能出现多份。跨动态库共享状态时，不要依赖 inline 变量的唯一性。

## 历史与演进

!!! history "历史与演进"
    - C++98：`inline` 是函数说明符（与 `virtual`、`explicit` 并列），规则主要围绕每个使用它的 TU 都必须有定义这一点。
    - C++11：`constexpr` 函数隐式 inline。
    - C++17：inline 变量（[[P0386R2]]）。`inline` 从 *function-specifier* 中移出，成为独立的 *decl-specifier*。`static constexpr` 数据成员隐式 inline，解决了类内初始化的 static const 成员在 odr-use 时还需要类外定义的老问题。
    - C++20：模块；具名模块中类内定义的函数不再隐式 inline；引入定义域与可达的措辞，取代原来出现在每个 TU 中的说法。

!!! pitfall "常见误解"
    - 误以为 inline 让函数被内联。这既不保证，也不是它的主要语义。
    - 误以为 inline 函数有内部链接。没有，inline 不影响链接。
    - 误以为 static inline 和 inline 一样。不一样，`static inline` 是内部链接，每个 TU 有一个独立的函数，各有自己的静态局部变量和地址。
    - 误以为函数模板隐式 inline。它不是，但它享有模板自己的 ODR 豁免；显式特化需要显式写 `inline`。
    - 误以为命名空间作用域的 constexpr 变量是 inline 的。它不是，只有静态数据成员才是。

!!! summary "小结"
    - `inline` 的规范性含义是：可以在多个 TU 中（以相同的方式）定义，但仍是一个实体、一个地址；内联替换只是提示。
    - 不能用于块作用域和参数；不能先定义后 inline。
    - 每个 odr-use 它的定义域都必须能到达其定义；各 TU 中的 inline 性必须一致（否则 IFNDR）。
    - 具名模块中类内定义的函数不再隐式 inline。
    - 在链接器层面体现为 COMDAT / weak / `linkonce_odr`，按名字去重，不比较内容。

!!! question "思考题 1"
    头文件中写 `const std::string kName = "x";`（命名空间作用域），被 100 个 TU 包含。会发生什么？`inline const std::string kName = "x";` 呢？

<details markdown="1">
<summary>答案</summary>

`const` 变量默认具有内部链接（[[basic.link#3]]），所以每个 TU 都有一个独立的 `kName` 对象，各自在启动时动态初始化（构造 `std::string`）。结果是 100 个对象、100 次构造和析构，地址各不相同。加上 `inline` 后，它具有外部链接，整个程序只有一个对象，只初始化一次（由守卫变量保证），所有 TU 看到的是同一个地址。
</details>

!!! question "思考题 2"
    为什么 `struct S { static const int N = 10; }; const int& r = S::N;` 在 C++14 中可能链接失败，而在 C++17 中把 `const` 换成 `constexpr` 就没问题？

<details markdown="1">
<summary>答案</summary>

`static const int N = 10;` 是类内的声明，不是定义（[[basic.def#2]] ¶2.3：非 inline 静态数据成员）。绑定引用 `r` 是对 `S::N` 的 odr-use，需要有一个定义；如果程序中没有 `const int S::N;`，链接时就找不到符号。C++17 起，`static constexpr int N = 10;` 隐式 inline（[[dcl.constexpr#1]]），类内声明即定义，链接器能找到（COMDAT 中的）定义。注意，C++17 中 `static const int N = 10;` 仍然不是 inline 的，问题依旧存在。
</details>
