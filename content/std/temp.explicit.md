---
title: 显式实例化
summary: `template class X<int>;` 与 `extern template class X<int>;`：程序员指定特化在哪里实例化。显式实例化定义会实例化类的全部（已定义的）成员；显式实例化声明压制本 TU 的实例化，用来缩短编译时间、控制目标文件内容；它们与重声明、内联、访问检查、默认实参之间的规则。
status: done
covers: temp.explicit
related: temp.spec, temp.inst, temp.expl.spec, temp.deduct.decl, basic.def.odr, dcl.inline
tags: 模板, 显式实例化, extern template, 编译时间
updated: 2026-10-18
---

隐式实例化（[[temp.inst]]）由编译器决定何时、在哪个翻译单元里生成特化的定义，通常是每个用到它的 TU 各生成一份，再由链接器去重。**显式实例化**（explicit instantiation）把这个决定交给程序员，有两种形式：

```cpp
template class std::vector<int>;          // 显式实例化定义：在这里生成 vector<int> 的全部定义
extern template class std::vector<int>;   // 显式实例化声明：别在本 TU 生成，别处会有
```

它们有三种用途。

1. 缩短编译时间、减小目标文件。一个重量级模板特化（如 `std::basic_string<char>`、大型表达式模板）在每个 TU 都实例化一次很昂贵。头文件中写 `extern template`，某个 `.cpp` 中写一次显式实例化定义，其他 TU 只生成调用。标准库实现大量使用这一手法（libstdc++、libc++ 对 `basic_string<char>`、`basic_ostream<char>` 等都有 `extern template`）。
2. 把模板定义藏在 `.cpp` 里。模板只对有限的几种实参有意义时，可以只在头文件中声明，在 `.cpp` 中定义并显式实例化这几种。这样用户看不到实现，改实现也不必重新编译用户代码。
3. 测试。显式实例化定义会实例化类模板的所有（已定义的、约束满足的）成员，能把那些只在某个成员被调用时才会出现的错误提前暴露出来（¶9）。

## 语法与两种形式（¶1–¶2）

¶1 类、函数、变量或成员模板的特化可以从其模板显式实例化；类模板的成员函数、成员类、静态数据成员可以从其成员定义显式实例化。

¶2 语法：

```text
explicit-instantiation:
    extern(opt) template declaration
```

带 `extern` 的是[[g:explicit-instantiation-declaration|**显式实例化声明**]]，不带的是**显式实例化定义**。注意 `template` 后面没有 `<>`；带 `<>` 的是显式特化（[[temp.expl.spec]]），两者含义截然不同：

| 写法 | 含义 |
|---|---|
| `template struct X<int>;` | 显式实例化定义：按模板生成 `X<int>` |
| `extern template struct X<int>;` | 显式实例化声明：本 TU 不生成 |
| `template<> struct X<int> { ... };` | 显式特化：不用模板，用这份定义 |

## 语法限制（¶3–¶4）

¶3 显式实例化不能使用 `thread_local` 以外的存储类说明符；对函数模板、类模板成员函数、变量模板的显式实例化不能用 `inline`、`constexpr`、`consteval`；不能有属性。

```cpp error
template<class T> inline void f(T) {}
template inline void f(int);        // error: explicit instantiation cannot be 'inline'
template static void f(char);       // error: 不能有存储类
template [[nodiscard]] void f(long);// error: 不能带属性
```

这些性质属于实体本身，由模板决定。显式实例化只负责在这里生成实体，无权改动它们。

¶4 对类或成员类的显式实例化，*declaration* 中的详述类型说明符必须含 *simple-template-id*；其他情况下 *declaration* 必须是一个只有单个声明符、没有初始化器的简单声明。对变量模板特化，声明符中的 *unqualified-id* 必须是 *simple-template-id*。

```cpp run ok title="explicit_forms.cpp"
template<class T> class Array { void mf(); };
template<class T> void Array<T>::mf() { }

template class Array<char>;              // 类模板
template void Array<int>::mf();          // 只实例化一个成员函数

template<class T> void sort(Array<T>&) { }
template void sort(Array<char>&);        // 模板实参从函数类型推导（[temp.deduct.decl]）

namespace N {
    template<class T> void f(T&) { }
}
template void N::f<int>(int&);           // 限定名 + 显式模板实参

int main() { }
```

函数模板的显式实例化可以省略模板实参，由 [[temp.deduct.decl]] 从声明的函数类型推导，配合偏序（[[temp.func.order]]）选出唯一的模板。

## 名字、可达性与同一实体的两个声明（¶5–¶6）

¶5 显式实例化不引入名字（[[basic.scope.scope]]）。

- 函数模板、变量模板、类模板的成员函数或静态数据成员、成员函数模板的声明必须从显式实例化处可达；
- 类模板、成员类、成员类模板的定义必须可达，除非有可达的同实参显式特化；
- 如果显式实例化的声明指名一个隐式声明的特殊成员函数，程序非良构。

```cpp error
template<class T> struct S { };
template S<int>::S();     // error: S<int>::S() 是隐式声明的，不能显式实例化
```

原因在于，隐式声明的特殊成员函数（[[special]]）在需要时才得到定义（隐式定义），并不是从模板的成员定义实例化出来的，因此没有模板定义可供实例化。要实例化它们，只能实例化整个类，它们会在使用时被隐式定义。

¶6 显式实例化中的 *declaration* 与对模板做相应替换得到的声明，是同一实体的两个声明。注 1：它们的类型必须按 [[basic.link]] 匹配（[[except.spec]] 另有规定的除外）。

```cpp
template<typename T> T var = {};
template float var<float>;      // OK：实例化出的变量类型是 float
template int var<int[16]>[];    // OK：允许省略数组的主界
template int *var<int>;         // error: 实例化出的变量类型是 int，不是 int*

template<typename T> auto av = T();
template int av<int>;           // OK：auto 变量可以用 int 重声明

template<typename T> auto f() {}
template void f<int>();         // error: 推导返回类型的函数不能用非推导返回类型重声明
```

最后一行的规则来自 [[dcl.spec.auto]]：返回类型推导的函数，其所有重声明都必须使用占位类型。写成 `template auto f<int>();` 才对。

!!! impl "Clang 的偏差"
    截至写作时，Clang 23 拒绝 `template int var<int[16]>[];`（报类型不匹配），标准例子明确说它是 OK 的。

¶6 末尾还规定，变量的显式实例化中的 *declaration* 尽管语法上像定义，本身却不是定义，也不与显式实例化定义所实例化出的定义冲突。

## 已显式特化时无效果；定义必须存在（¶7）

¶7 对一组给定实参，若显式实例化出现在显式特化的声明之后，显式实例化**无效果**（Clang 给出 `-Winstantiation-after-specialization` 警告）。反过来的顺序是非良构的，见 [[temp.spec#5]]。

在其他情况下，对于显式实例化定义，函数模板、变量模板、成员函数模板、类模板的成员函数或静态数据成员的定义必须出现在每个对它做显式实例化的翻译单元中。道理很简单：显式实例化定义的工作就是在这里生成定义，没有模板定义就无从生成。

## 约束（¶8）

¶8（注 2）显式实例化受约束模板，需要满足模板的关联约束（[[temp.constr.decl]]）。全部模板实参都给出时，在形成模板名时检查；函数模板有尾随实参省略时，在推导中（[[temp.deduct.decl]]）检查。

## 实例化类 = 实例化它的成员（¶9–¶11）

¶9 指名类模板特化的显式实例化，同时也是对其每个**直接非模板成员**的同种（声明或定义）显式实例化，前提是该成员在本 TU 中未被显式特化过，且其关联约束（若有）被实参满足。注 3：通常还会顺带实例化实现相关的类数据（如虚函数表）。

¶10 指名类模板特化的显式实例化定义，实例化该类本身，并且只对那些在实例化点已定义的成员是显式实例化定义。

这两条合起来，就是用显式实例化强制检查所有成员的依据：

```cpp error
template<class T> struct Box {
    T v;
    void ok() { }
    void bad() { v.nope(); }   // 只对有 nope() 的 T 合法
};
Box<int> b;                    // OK：隐式实例化不生成 bad 的定义
template struct Box<int>;      // error：显式实例化定义实例化所有已定义的成员，bad 出错
```

但有两类成员被跳过：

```cpp ok
template<class T> struct Box {
    T v;
    void bad() requires requires (T t) { t.nope(); } { v.nope(); }  // 约束不满足：跳过（¶9）
    void later();                                                   // 未定义：跳过（¶10）
};
template struct Box<int>;      // OK
```

¶9 的约束例外是 C++20 引入概念时加入的。有了它，条件成员函数（受 `requires` 子句约束的成员）不会破坏显式实例化；否则 `template class std::optional<int>;` 之类就会因为那些只对某些 `T` 存在的成员而失败。

注意 ¶9 说的是直接非模板成员。成员模板（成员函数模板、成员类模板）还缺模板实参，因此不会被实例化。嵌套类会被实例化（它是非模板成员），并递归地实例化它的成员。

¶11 对**预期析构函数**（prospective destructor，[[class.dtor]]）的显式实例化必须对应类中被选中的那个析构函数。（C++20 起类可以有多个带不同约束的预期析构函数。）

## extern template：规则与陷阱（¶12）

¶12 同一 TU 中，若一个实体既是显式实例化声明的对象，又是显式实例化定义的对象，那么定义必须在声明之后。

```cpp ok
template<class T> void f(T) {}
extern template void f(int);
template void f(int);           // OK：定义在声明之后
```

```cpp error
template<class T> void f(T) {}
template void f(int);
extern template void f(int);    // error: 显式实例化声明跟在定义之后
```

接下来一条最常用到：如果一个实体是显式实例化声明的对象，并且在本 TU 中以本来会导致隐式实例化的方式被使用，**那么程序中某处必须有它的显式实例化定义**，否则 {{ifndr}}。实践中这表现为链接错误。

注 4：这条规则也适用于内联函数，尽管对内联函数的显式实例化声明没有其他规范性效果。之所以需要它：如果某个 TU 取了内联函数的地址，而实现选择在该 TU 中压制外部副本，就必须有另一个 TU 提供函数体。

最后，显式实例化声明不能指名具有内部链接的模板的特化，因为内部链接的实体不可能在别的 TU 中定义。

```cpp error
namespace { template<class T> void f(T) {} }
extern template void f(int);    // error: 具有内部链接
```

### 一个完整的多 TU 例子

```cpp title="big.h"
#pragma once
#include <cstdio>
template<class T> struct Big {
    T v{};
    void work() { std::printf("work %d\n", (int)v); }   // 类内定义：隐式 inline
};
extern template struct Big<int>;     // 包含者：不要实例化 Big<int> 的成员
```

```cpp title="big.cpp"
#include "big.h"
template struct Big<int>;            // 唯一的显式实例化定义
```

```cpp title="main.cpp"
#include "big.h"
int main() { Big<int> b; b.work(); }
```

在 macOS 上用 Clang 23 编译（`llvm-nm -C` 查看符号）：

- `-O0` 编译 `main.cpp`：`Big<int>::work()` 是一个未定义符号（`U`）。本 TU 没有生成它，留给链接器去 `big.o` 里找。只链接 `main.o` 会得到 `Undefined symbols ... Big<int>::work()`，这正是 ¶12 的 IFNDR 在实践中的样子。
- `-O2` 编译 `main.cpp`：`work` 被内联了，`main.o` 里完全没有对它的引用。这正是 [[temp.inst#1]] 的 ¶1.1 与 [[temp.inst#5]] 注 3 所说的：内联函数即使有 `extern template`，也不算已声明的特化，仍然可以为了内联而隐式实例化，只是不输出外部副本。

所以对内联成员函数（类内定义的成员函数都是内联的），`extern template` 主要节省的是输出代码和链接器去重的成本，前端仍然要解析并实例化函数体以便内联；对非内联的成员函数（类外定义、不加 `inline`），它能真正省掉本 TU 的实例化工作。

!!! tip "什么时候用 extern template"
    - 少数几个特化被大量 TU 使用、且实例化代价高（大型类、深层表达式模板）。
    - 测量后再用：在现代编译器上，预编译头、模块（C++20 modules）通常能带来更大的收益。模块中导出的模板依然在导入方实例化，`extern template` 在模块世界里依然有意义。
    - 务必保证某个 TU 里有对应的显式实例化定义，否则就是链接错误。

## 显式实例化不使用默认实参（¶13）

¶13 显式实例化不构成对默认实参的使用，所以不会实例化默认实参。

```cpp ok
char* p = 0;
template<class T> T g(T x = &p) { return x; }
template int g<int>(int);       // OK：尽管 &p 不能转为 int
```

默认实参是单独的构造，要等到在调用处用上时才实例化（[[temp.inst#14]]）。显式实例化定义只生成函数本体。默认实参 `&p`（`char**`）对 `T = int` 是非良构的，但只要没有人在调用 `g<int>()` 时省略实参，它就永远不会被实例化。

## 访问检查豁免

[[temp.spec#6]] 规定显式实例化声明中的名字（模板实参、声明符中的类型）不做访问检查，这让 `template struct Thief<&Bank::balance>;` 之类的写法成为可能（详见 [[temp.spec]] 中的例子）。

## 实现视角

!!! impl "ABI 与目标文件"
    - 在 Itanium C++ ABI（Linux、macOS）上，隐式实例化与显式实例化定义生成的符号都允许在多个目标文件中重复出现（弱定义/COMDAT），链接器合并。所以跨 TU 重复的显式实例化定义（违反 [[temp.spec#5]] ¶5.1）实践中不会被发现。
    - MSVC 上 `extern template` 与 `__declspec(dllexport/dllimport)` 结合，是从 DLL 导出模板特化的标准做法：DLL 中 `template class __declspec(dllexport) X<int>;`，使用方头文件中 `extern template class __declspec(dllimport) X<int>;`。
    - 显式实例化类模板会实例化虚函数表（即 ¶9 注 3 所说的实现相关数据）。对于没有关键函数（key function）的类模板，这可以把虚函数表固定在一个 TU 中。

!!! history "历史与演进"
    | 版本 | 变化 |
    |---|---|
    | C++98 | 显式实例化定义 `template class X<int>;` |
    | C++11 | 显式实例化声明 `extern template`（此前是 GCC 等的扩展）；`thread_local` 可用于显式实例化 |
    | C++14 | 变量模板的显式实例化 |
    | C++20 | 约束不满足的成员被显式实例化跳过（¶9）；预期析构函数（¶11） |

## 陷阱

!!! pitfall "`template` 与 `template<>` 一字之差"
    `template void f<int>(int);` 是实例化（用模板的定义），`template<> void f<int>(int);` 是特化声明（承诺另外提供定义）。后者若不提供定义，链接失败；若有用户在特化声明之前使用了 `f<int>`，则是 IFNDR（[[temp.expl.spec#7]]）。

!!! pitfall "忘了显式实例化定义"
    头文件里有 `extern template class X<int>;`，却没有任何 `.cpp` 写 `template class X<int>;`。这样在 `-O0` 下链接失败，在 `-O2` 下却可能因为全部内联而链接成功。这种只在调试构建中出错的问题很难查。

!!! pitfall "显式实例化定义要求所有成员都合法"
    `template class std::vector<NonCopyable>;` 会尝试实例化 `vector` 的所有非模板、已定义且约束满足的成员。若某个成员（例如没有用 `requires` 约束的拷贝构造函数）对该类型非良构，即使你从不调用它，也会报错。标准库容器并不保证显式实例化对所有元素类型都可行。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> struct S {
        void f();
        template<class U> void g(U) { T::nope(); }
        struct Inner { void h() { T::nope(); } };
    };
    template<class T> void S<T>::f() { }
    template struct S<int>;
    ```
    这个显式实例化会报错吗？

<details markdown="1">
<summary>答案</summary>

会，因为 `Inner`。¶9：显式实例化类模板特化，同时显式实例化其每个直接非模板成员。`f` 已定义，实例化后没有问题。`g` 是成员模板，不会被实例化。`Inner` 是非模板成员类，被显式实例化定义；对成员类的显式实例化定义又实例化它的成员 `h`，`int::nope()` 出错。
</details>

!!! question "思考题 2"
    把模板定义放在 `.cpp` 文件里，头文件只放声明，`.cpp` 末尾写 `template class Matrix<float>; template class Matrix<double>;`。用户若使用 `Matrix<int>`，会发生什么？是编译错误、链接错误还是 UB？

<details markdown="1">
<summary>答案</summary>

用户 TU 中 `Matrix<int>` 的类定义可见（在头文件中），成员函数只有声明。调用 `Matrix<int>::foo()` 时需要隐式实例化其定义，但本 TU 中没有模板成员的定义，此时在实例化点只合法地产生一个对外部符号的引用（[[temp.over#5]] 也描述了同样的情形）。程序中没有任何 TU 提供 `Matrix<int>::foo` 的定义，违反了 ODR 中 odr-use 的非内联函数必须在程序中恰好定义一次的要求（[[basic.def.odr]]）。这是 {{ifndr}}，实践中表现为链接错误。
</details>

## 小结

| 规则 | 段落 | 要点 |
|---|---|---|
| 两种形式：定义 / `extern` 声明 | ¶2 | 无 `<>`；有 `<>` 是显式特化 |
| 不能带存储类（`thread_local` 除外）、`inline`/`constexpr`/`consteval`、属性 | ¶3 | — |
| 不引入名字；不能指名隐式声明的特殊成员 | ¶5 | {{ill-formed}} |
| 与模板替换得到的声明是同一实体的两个声明 | ¶6 | 类型必须匹配 |
| 在显式特化之后则无效果；定义必须在本 TU | ¶7 | — |
| 实例化类 → 实例化所有直接非模板、已定义、约束满足的成员 | ¶9–¶10 | 可用于强制检查 |
| 声明须在定义之前；有 `extern` 声明并使用 → 须有定义 | ¶12 | 否则 {{ifndr}}（链接错误） |
| 内部链接的模板不能 `extern template` | ¶12 | {{ill-formed}} |
| 不实例化默认实参 | ¶13 | — |
