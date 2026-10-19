---
title: 显式实例化
summary: `template class X<int>;` 在这里生成特化的定义，`extern template class X<int>;` 让本翻译单元不生成、改用别处的定义；用来缩短编译时间、把模板实现藏进 .cpp、强制检查所有成员。
status: done
covers: temp.explicit
related: temp.spec, temp.inst, temp.expl.spec, temp.deduct.decl, basic.def.odr, dcl.inline
tags: 模板, 显式实例化, extern template, 编译时间
updated: 2026-10-19
---

!!! tldr
    - `template class X<int>;` 是显式实例化定义，在这里按模板生成 `X<int>`；`extern template class X<int>;` 是显式实例化声明，告诉编译器本翻译单元不必生成，别处会有。
    - `template` 后面没有 `<>`。带 `<>` 的 `template<>` 是显式特化，含义完全不同。
    - 显式实例化一个类模板特化，会实例化它所有已定义、约束满足的直接非模板成员，可以用来强制检查每个成员。
    - 用了 `extern template` 又在本翻译单元用到这个实体，程序中就必须有一份显式实例化定义，否则非良构、不要求诊断，实践中表现为链接错误。
    - 对内联函数，`extern template` 不阻止为内联而实例化，只是不输出外部副本。

## 两种形式（¶1–¶2）

隐式实例化（[[temp.inst]]）由编译器决定在哪里生成特化的定义，通常是每个用到它的翻译单元各生成一份，再由链接器去重。**显式实例化**（explicit instantiation，[[g:explicit-instantiation]]）把这个决定交给程序员：

```cpp
template class std::vector<int>;          // 显式实例化定义：在这里生成
extern template class std::vector<int>;   // 显式实例化声明：本翻译单元不生成
```

¶1 可以显式实例化的有类模板、函数模板、变量模板和成员模板的特化，以及类模板的成员函数、成员类、静态数据成员。

¶2 语法是 `extern`(可选) `template` *declaration*。带 `extern` 的是**显式实例化声明**（[[g:explicit-instantiation-declaration]]），不带的是**显式实例化定义**。

| 写法 | 含义 |
|---|---|
| `template struct X<int>;` | 显式实例化定义：按模板生成 `X<int>` |
| `extern template struct X<int>;` | 显式实例化声明：本翻译单元不生成 |
| `template<> struct X<int> { … };` | 显式特化：不用模板，用这份定义（[[temp.expl.spec]]） |

它有三种用途：

1. 缩短编译时间。重量级的特化在每个翻译单元都实例化一次代价很高。头文件里写 `extern template`，某一个 `.cpp` 里写一次显式实例化定义，其他翻译单元就只生成调用。libstdc++ 和 libc++ 对 `basic_string<char>`、`basic_ostream<char>` 等都这样做。
2. 把模板实现藏进 `.cpp`。模板只对少数几种实参有意义时，头文件只放声明，`.cpp` 里放定义，并显式实例化这几种。
3. 测试。显式实例化定义会实例化类的所有成员，能提前暴露只有调用某个成员时才出现的错误（¶9）。

## 写法上的限制（¶3–¶4）

¶3 显式实例化不能带 `thread_local` 以外的存储类说明符；函数模板、类模板成员函数、变量模板的显式实例化不能带 `inline`、`constexpr`、`consteval`；也不能带属性。这些性质属于实体本身，由模板决定，显式实例化只负责在这里生成实体。

```cpp error
template<class T> inline void f(T) {}
template inline void f(int);          // error: 不能是 inline
template static void f(char);         // error: 不能有存储类
template [[nodiscard]] void f(long);  // error: 不能带属性
```

¶4 实例化类时，*declaration* 必须用带尖括号的 *simple-template-id* 写出类名；其他情况下，*declaration* 必须是只有一个声明符、没有初始化器的简单声明。变量模板特化的名字同样要写成 *simple-template-id*。

```cpp run ok title="explicit_forms.cpp"
template<class T> class Array { void mf(); };
template<class T> void Array<T>::mf() { }

template class Array<char>;            // 整个类
template void Array<int>::mf();        // 只实例化一个成员函数

template<class T> void sort(Array<T>&) { }
template void sort(Array<char>&);      // T 从函数类型推导

namespace N {
  template<class T> void f(T&) { }
}
template void N::f<int>(int&);         // 限定名，显式模板实参

int main() { }
```

函数模板的显式实例化可以省略模板实参，由 [[temp.deduct.decl]] 从声明的函数类型推导。

## 显式实例化与原模板的关系（¶5–¶8）

¶5 显式实例化不引入新的名字。函数模板、变量模板、类模板的成员函数或静态数据成员的声明，必须在显式实例化处可达；类模板和成员类的定义也必须可达，除非已有同实参的显式特化可达。

¶5 还规定，显式实例化不能指名隐式声明的特殊成员函数（[[special]]）。这类函数只在需要时隐式定义，不是从模板的成员定义实例化来的，没有东西可以显式实例化。

```cpp error
template<class T> struct S { };
template S<int>::S();   // error: S<int>::S() 是隐式声明的
```

¶6 显式实例化里的声明，和代入模板得到的声明，是同一实体的两个声明。注 1 指出，两者的类型必须按 [[basic.link]] 匹配：

```cpp
template<typename T> T var = {};
template float var<float>;      // OK：实例化出的变量类型是 float
template int var<int[16]>[];    // OK：可以省略数组的第一维
template int *var<int>;         // error: 实例化出的变量类型是 int

template<typename T> auto av = T();
template int av<int>;           // OK：auto 变量可以用 int 重声明

template<typename T> auto f() {}
template void f<int>();         // error: 推导返回类型的函数必须用占位类型重声明
```

最后一行要写成 `template auto f<int>();`（[[dcl.spec.auto]]）。¶6 最后一句说明，变量的显式实例化在语法上像定义，本身却不是定义，不与显式实例化定义生成的那个定义冲突。

!!! impl "Clang 的偏差"
    本机 Clang 23 拒绝 `template int var<int[16]>[];`，报 type 'int[]' of explicit instantiation of 'var' does not match expected type 'int[16]'。标准例子明确说它是合法的。

¶7 如果对同一组实参，显式实例化出现在显式特化的声明之后，显式实例化没有效果（本机 Clang 23 给出 `-Winstantiation-after-specialization` 警告）。顺序反过来是非良构的，见 [[temp.spec#5]]。除此之外，显式实例化定义所在的每个翻译单元里，都必须有对应的函数模板、变量模板、成员函数或静态数据成员的定义：没有模板定义就无从生成。

¶8 是一条注：显式实例化受约束的模板，必须满足它的关联约束（[[temp.constr.decl]]）。

## 实例化类就是实例化它的成员（¶9–¶11）

```cpp error
template<class T> struct Box {
  T v;
  void ok() { }
  void bad() { v.nope(); }   // 只对有 nope() 的 T 合法
};
Box<int> b;                  // OK：隐式实例化不生成 bad 的定义
template struct Box<int>;    // error: 显式实例化定义生成了 bad
```

¶9 显式实例化一个类模板特化，同时也是对它每个**直接非模板成员**的同种（声明或定义）显式实例化。跳过两类成员：本翻译单元中已经显式特化过的，以及关联约束不被这组实参满足的。注 3 补充，通常还会实例化与类相关的实现数据，比如虚表。

¶10 显式实例化定义只对实例化点之前已经定义的成员是显式实例化定义。

```cpp run ok
template<class T> struct Box {
  T v;
  void bad() requires requires (T t) { t.nope(); }
  { v.nope(); }              // 约束不满足：跳过（¶9）
  void later();              // 没有定义：跳过（¶10）
};
template struct Box<int>;    // OK
int main() {}
```

约束的例外随 C++20 的概念一起加入。没有它，带 `requires` 子句、只对部分 `T` 存在的成员，会让整个类的显式实例化失败。

¶9 说的是直接非模板成员。成员函数模板、成员类模板还缺模板实参，不会被实例化。嵌套类是非模板成员，会被实例化，并递归地实例化它的成员。

¶11 显式实例化一个预期析构函数（prospective destructor，C++20 起类可以声明多个带不同约束的析构函数，见 [[class.dtor]]）时，必须对应类中最终被选中的那一个。

## extern template 的规则（¶12）

¶12 同一翻译单元里，同一实体既有显式实例化声明又有显式实例化定义时，定义必须在声明之后：

<div class="compare" markdown="1">

```cpp run ok
template<class T> void f(T) {}
extern template void f(int);
template void f(int);   // OK
int main() {}
```

```cpp error
template<class T> void f(T) {}
template void f(int);
extern template void f(int);
// error: 声明在定义之后
```

</div>

一个实体如果有显式实例化声明，又在本翻译单元里以本会引起隐式实例化的方式被使用，程序中某处必须有它的显式实例化定义，否则 {{ifndr}}（非良构、不要求诊断：标准对这样的程序没有任何要求）。实践中这表现为链接错误。

注 4 说明这条也适用于内联函数，尽管对内联函数写显式实例化声明没有别的规范效果。原因是：如果某个翻译单元取了内联函数的地址，而实现在这里选择不输出函数体，就必须有另一个翻译单元提供它。

显式实例化声明不能指名具有内部链接的模板的特化，因为别的翻译单元不可能提供它的定义：

```cpp error
namespace { template<class T> void f(T) {} }
extern template void f(int);   // error: 具有内部链接
```

### 一个多翻译单元的例子

```cpp title="big.h"
#pragma once
#include <cstdio>
template<class T> struct Big {
  T v{};
  void work() { std::printf("work %d\n", (int)v); }   // 类内定义：隐式 inline
};
extern template struct Big<int>;   // 包含者不要实例化 Big<int> 的成员
```

```cpp title="big.cpp"
#include "big.h"
template struct Big<int>;          // 唯一的显式实例化定义
```

```cpp title="main.cpp"
#include "big.h"
int main() { Big<int> b; b.work(); }
```

在本机用 Clang 23 编译 `main.cpp`，再用 `nm` 查看符号：

- `-O0`：`Big<int>::work()` 是未定义符号，留给链接器到 `big.o` 里找。只链接 `main.o` 会得到 `Undefined symbols … Big<int>::work()`，这就是 ¶12 的 IFNDR 在实践中的样子。
- `-O2`：`work` 被内联了，`main.o` 里完全没有对它的引用，单独链接也能成功。

`-O2` 的结果正是 [[temp.inst#1]] 第 1.1 项的效果：内联函数即使有 `extern template`，仍然可以为了内联而实例化，只是不输出外部副本。所以对类内定义的成员函数，`extern template` 省下的主要是输出代码和链接器去重的开销，前端仍要实例化函数体；对类外定义、不带 `inline` 的成员函数，它才真正省掉本翻译单元的实例化。

!!! pitfall "只有调试构建链接失败"
    头文件里有 `extern template class X<int>;`，却没有任何 `.cpp` 写 `template class X<int>;`。`-O0` 下链接失败，`-O2` 下可能因为全部内联而链接成功，这类问题很难查。

!!! tip "什么时候用 extern template"
    少数几个特化被大量翻译单元使用、而且实例化代价高时才值得用，并且应当先测量。预编译头和模块通常收益更大。模块导出的模板仍在导入方实例化，所以 `extern template` 在模块里依然有意义。

## 不实例化默认实参（¶13）

```cpp run ok
char* p = 0;
template<class T> T g(T x = &p) { return x; }
template int g<int>(int);   // OK：尽管 &p 不能转为 int
int main() {}
```

¶13 显式实例化不算使用默认实参，所以不做默认实参实例化（[[temp.inst#14]]）。默认实参 `&p` 的类型是 `char**`，对 `T = int` 非良构，但只要没有调用省略了这个实参，它就不会被实例化。

## 实现视角

!!! impl "ABI 与目标文件"
    - 在 Itanium C++ ABI（Linux、macOS）上，隐式实例化和显式实例化定义生成的符号都可以在多个目标文件里重复出现，链接器合并。所以跨翻译单元重复的显式实例化定义（违反 [[temp.spec#5]] 第 5.1 项）实践中不会被发现。
    - MSVC 上，`extern template` 配合 `__declspec(dllexport)` / `__declspec(dllimport)` 是从 DLL 导出模板特化的常用做法。
    - 显式实例化类模板会生成虚表（¶9 注 3 所说的实现数据），可以把虚表固定在一个翻译单元里。

!!! history "历史与演进"
    | 版本 | 变化 |
    |---|---|
    | C++98 | 显式实例化定义 `template class X<int>;` |
    | C++11 | 显式实例化声明 `extern template`，此前是编译器扩展 |
    | C++14 | 变量模板的显式实例化 |
    | C++20 | 约束不满足的成员被跳过（¶9）；预期析构函数（¶11） |

## 常见误解

!!! pitfall "`template` 与 `template<>` 差不多"
    `template void f<int>(int);` 是实例化，用模板的定义；`template<> void f<int>(int);` 是显式特化的声明，承诺另外提供定义。后者不提供定义会链接失败；如果在特化声明之前已经用过 `f<int>`，程序非良构（[[temp.expl.spec#7]]）。

!!! pitfall "显式实例化标准库容器总能成功"
    `template class std::vector<NonCopyable>;` 会实例化 `vector` 所有已定义、约束满足的非模板成员。某个没有用 `requires` 约束的成员（比如拷贝构造函数）对该类型非良构，即使从不调用，也会报错。标准不保证标准库容器能对任意元素类型显式实例化。

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

会，错在 `Inner`。按 ¶9，显式实例化 `S<int>` 也显式实例化它的每个直接非模板成员。`f` 已定义，实例化没有问题；`g` 是成员模板，不实例化；`Inner` 是非模板成员类，被显式实例化定义，又实例化了它的成员 `h`，`int::nope()` 出错。本机 Clang 23 在 `h` 的函数体处报错。
</details>

!!! question "思考题 2"
    模板定义放在 `.cpp` 里，头文件只有声明，`.cpp` 末尾写 `template class Matrix<float>; template class Matrix<double>;`。用户使用 `Matrix<int>::foo()` 会怎样？

<details markdown="1">
<summary>答案</summary>

用户的翻译单元里只有 `foo` 的声明，没有模板成员的定义，编译器只能生成一个对外部符号的调用。程序中没有任何翻译单元提供 `Matrix<int>::foo` 的定义，违反了 odr-use 的非内联函数必须恰好定义一次的要求（[[basic.def.odr]]）。这是 {{ifndr}}，实践中表现为链接错误。
</details>
