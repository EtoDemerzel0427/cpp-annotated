---
title: 待决名决议
summary: 模板里的依赖调用在哪里查找函数：普通查找只看模板定义处，ADL 还要看实例化点；实例化点怎样确定，多个实例化点含义不同、或换一组头文件就会选出更好的重载时，程序非良构而不要求诊断。
status: done
covers: temp.dep.res, temp.point, temp.dep.candidate
papers: P1787R6
related: temp.res, temp.dep, temp.inst, basic.lookup.argdep, module.context, module.reach, temp.expl.spec, basic.def.odr, topics/two-phase-lookup
tags: 模板, 两阶段查找, 实例化点, ADL, 模块, IFNDR
updated: 2026-10-19
---

!!! tldr
    - 依赖调用 `f(t)` 的候选函数来自两处：模板定义处的普通无限定查找，加上定义处和实例化点的 ADL。模板定义之后才声明的函数，只能经由 ADL 找到。
    - 依赖基类的成员在模板定义处不可见，要写 `this->g()` 或 `Base<T>::g()`；后者会关闭虚调用。
    - 函数模板特化的实例化点紧跟在引用它的命名空间作用域声明之后，类模板特化的实例化点紧挨在它之前。
    - 函数模板特化在翻译单元末尾还有一个实例化点。几个实例化点给出不同含义时，程序非良构，不要求诊断。
    - 如果把所有翻译单元的声明都考虑进来，依赖调用会出错或选到更好的重载，程序同样非良构，不要求诊断。

## 模板定义之后声明的函数能不能被调用

```cpp run ok title="where_lookup_happens.cpp"
#include <cstdio>
void f(int) { std::puts("f(int)"); }

template<class T> void g(T t) { f(t); }

void f(double) { std::puts("f(double)"); } // 定义之后声明
namespace N {
  struct S { operator int() const { return 0; } };
  void f(S) { std::puts("N::f(S)"); }      // 定义之后声明
}

int main() {
  g(1.0);      // 输出 f(int)
  g(N::S{});   // 输出 N::f(S)
}
```

`g` 里的 `f(t)` 是一个**依赖调用**（dependent call）：实参 `t` 的类型取决于模板形参，所以在模板定义处还无法决定调用哪个 `f`（[[temp.dep]]）。`g(1.0)` 实例化时，`f(double)` 早已声明而且是精确匹配，最后调用的却是 `f(int)`。`g(N::S{})` 则找到了同样在定义之后才声明的 `N::f(S)`。

两者的区别在于查找方式。普通的无限定查找只在模板定义处做一次，那时只有 `f(int)`。**实参依赖查找**（ADL，[[g:argument-dependent-lookup]]）会到实参类型的关联命名空间里找函数，对依赖调用它还要在实例化时再做一次。`N::S` 的关联命名空间是 `N`，所以找到了 `N::f(S)`；`double` 是基本类型，没有关联命名空间，ADL 什么也找不到。

### 两阶段查找的完整规则

这套规则通常叫**两阶段查找**（two-phase lookup，[[g:two-phase-lookup]]）。这不是标准术语，而是几条分散规则的合称：

| 名字的种类 | 在哪里查找 | 出处 |
|---|---|---|
| 非依赖名（限定或不限定） | 只在模板定义处查一次，结果固定 | [[temp.res.general#1]] |
| 依赖调用 `f(args)` 的普通无限定查找 | 只从模板定义处出发 | [[temp.res.general#1]] |
| 依赖调用 `f(args)` 的 ADL | 从模板定义处，以及实例化语境中的每一点出发 | [[basic.lookup.argdep#4]] |
| 依赖的限定名 `T::x`、`Base<T>::x`、`t.x` | 实例化时在确定的类里做限定名查找 | [[temp.dep.type#5]] |

!!! std
    If N is a dependent name, the above lookup is also performed from each point in the instantiation context of the lookup, ...

[[basic.lookup.argdep#4]] 的这句话是第三行的依据：对依赖名，ADL 还要从**实例化语境**（instantiation context，[[g:instantiation-context]]）的每一点出发再做一次。不使用模块的程序里，实例化语境只有一个点，就是下文讲的实例化点（[[module.context#5]]）。

## 依赖基类与 `this->`

```cpp error
template<class T> struct Base { void g() { } };
template<class T> struct D : Base<T> {
  void f() { g(); }    // error: 找不到 g
};
```

`g()` 没有实参，不可能是依赖调用，`g` 是非依赖名，只在定义处查找。`D` 自己没有 `g`；`Base<T>` 是**依赖基类**（[[g:dependent-base-class]]），即依赖于模板形参的基类，在定义处不被搜索（[[temp.dep.type#3]]）；全局也没有 `g`。于是查找失败。

依赖基类不被搜索，是因为 `Base<T>` 可以被显式特化成任何样子。下面的程序在全局恰好有一个 `g`：

```cpp run ok title="silent_rebinding.cpp"
#include <cstdio>
void g() { std::puts("::g"); }

template<class T> struct Base {
  void g() { std::puts("Base<T>::g"); }
};
template<class T> struct D : Base<T> {
  void f() {
    g();          // 定义处绑定到 ::g
    this->g();    // 依赖名，实例化时查找
  }
};
template<> struct Base<int> { };   // 没有 g

int main() { D<double>{}.f(); }    // ::g，然后 Base<T>::g
```

无限定的 `g()` 静默地绑定到了 `::g`，没有任何诊断。如果规则允许在定义处看主模板 `Base<T>` 的成员，那么 `D<int>` 遇到没有 `g` 的 `Base<int>` 时含义又会改变。标准选择了一致的规则：在模板定义处，依赖基类视同不存在。

要使用依赖基类的成员，有下面几种写法：

```cpp run ok
template<class T> struct Base { void g() { } };
template<class T> struct D : Base<T> {
  void f() {
    this->g();      // this 的类型依赖，成员访问随之依赖
    D::g();         // 在当前类里查不到、又有依赖基类：依赖
    Base<T>::g();   // 查找的类依赖于 T：依赖
  }
};
template<class T> struct D2 : Base<T> {
  using Base<T>::g; // 把名字引入 D2
  void f() { g(); }
};
int main() { D<int>{}.f(); D2<int>{}.f(); }
```

`D::g()` 和 `Base<T>::g()` 依赖的依据分别是 [[temp.dep.type#5]] 的第 5.4 项和第 5.2 项。

!!! pitfall "`Base<T>::f()` 会关闭虚调用"
    限定名调用虚函数不做动态派发（[[class.virtual]]）。如果 `hook` 是虚函数，`Base<T>::hook()` 总是调用基类版本，`this->hook()` 才是虚调用：

    ```cpp run ok
    #include <cstdio>
    template<class T> struct Base {
      virtual void hook() { std::puts("Base::hook"); }
    };
    template<class T> struct D : Base<T> {
      void hook() override { std::puts("D::hook"); }
      void call() { this->hook(); Base<T>::hook(); }
    };
    int main() { D<int> d; d.call(); }   // D::hook，然后 Base::hook
    ```

    所以一般推荐写 `this->`。

!!! impl "MSVC 的旧行为"
    MSVC 长期不实现两阶段查找：它把模板体存成记号流，实例化时才解析和查找。于是依赖基类的成员可以无限定使用，缺少 `typename` 的代码照样编译，定义之后声明的普通函数也能被找到，从未实例化的模板里的错误不报。这些代码换到 GCC、Clang 上无法编译，`silent_rebinding.cpp` 在旧 MSVC 上还会调用 `Base<T>::g`。

    VS 2017 起，MSVC 在 `/permissive-` 模式下实现两阶段查找，`/Zc:twoPhase-` 可以关闭它。Clang 的 `-fdelayed-template-parsing` 模仿旧 MSVC，把函数模板体推迟到翻译单元末尾解析；用它编译上面找不到 `g()` 的例子不再报错。这是不符合标准的行为，Clang 也会提示该选项在 C++20 之后已弃用。

## 实例化点 [temp.point]

实例化语境里的点从哪里来？最基本的是**实例化点**（point of instantiation，POI，[[g:point-of-instantiation]]）：源代码中的一个位置，编译器视同在这里生成特化的定义。依赖调用的 ADL 从这里出发，看得到这里之前的声明。

### 函数紧随其后（¶1）

```cpp
namespace N { struct S { }; }
template<class T> void call(T t) { touch(t); }

void use() {
  call(N::S{});
}
// ← call<N::S> 的实例化点
namespace N { void touch(S) { } }
// ← 翻译单元末尾：也是实例化点（¶7）
```

¶1 对函数模板特化、成员函数模板特化、类模板的成员函数或静态数据成员的特化，实例化点紧随引用它的那个命名空间作用域声明或定义之后。`call(N::S{})` 写在 `use` 的函数体里，实例化点却不在调用处，而在整个 `use` 定义之后。

例外是嵌套的情形。如果这个特化是因为另一个模板特化引用它而隐式实例化的（¶1.1），并且引用它的语境依赖于模板形参（¶1.2），它的实例化点就是外围特化的实例化点。比如 `call<N::S>` 里再调用 `helper(t)`，`helper<N::S>` 的实例化点就是 `call<N::S>` 的实例化点。模板定义内部没有命名空间作用域的声明可以作为参照，只能沿用外围的。

¶2 调用用到了默认实参时，默认实参的实例化点就是这个函数特化的实例化点。

¶3 *noexcept-specifier* 的规则与 ¶1 相同：被另一个模板特化需要、需要它的语境又依赖于模板形参时，沿用那个特化的实例化点（¶3.1、¶3.2）；否则紧随需要它的命名空间作用域声明之后。默认实参和 noexcept 说明符各自按需单独实例化（[[temp.inst]]），所以需要自己的实例化点。

### 类紧挨其前（¶4）

```cpp error
namespace N { struct A { }; }
template<class T> struct H {
  char buf[probe(T{})];      // probe(T{}) 是依赖调用
};

int x = sizeof(H<N::A>);     // H<N::A> 的实例化点在这一行之前

namespace N { constexpr int probe(A) { return 4; } }
```

¶4 对类模板特化、类成员模板特化、类模板的成员类的特化，实例化点紧挨在引用它的命名空间作用域声明或定义之前。上例中实例化发生在 `x` 的声明之前，那时 `N::probe` 还没有声明，程序非良构。把 `N::probe` 移到 `x` 之前就正常了。

类放在前面，是因为引用它的声明往往要用它的完整定义：解析 `int x = sizeof(H<N::A>);` 时就必须知道 `H<N::A>` 的大小。函数只需要声明就能被引用，定义可以以后再生成。

嵌套的情形也与函数对应：被另一个模板特化引用（¶4.1）、引用语境依赖于模板形参（¶4.2）、而且之前尚未实例化（¶4.3）时，实例化点紧挨在外围模板的实例化点之前。

### 虚函数、显式实例化与展开语句（¶5、¶6、¶8）

¶5 隐式实例化的虚函数，实例化点紧随外围类模板特化的实例化点之后。虚函数要填进虚表，而虚表在类实例化时就需要。

¶6 显式实例化定义（`template void f<int>(int);`，见 [[temp.explicit]]）也是它所指定的特化的一个实例化点。

¶8 {{c++26}} 展开语句（[[stmt.expand]]）的循环体，实例化点是外围模板化实体的实例化点；不在模板里时，紧随包含它的命名空间作用域声明之后。展开语句在非模板函数里也要实例化循环体，所以单独规定。

### 翻译单元末尾也是实例化点（¶7）

¶7 第 1 段所说的那类函数特化，在一个翻译单元里可以有多个实例化点。除了前面描述的位置，翻译单元的声明序列末尾也是它的实例化点（¶7.1）；如果实例化点在私有模块片段里，翻译单元末尾也是（¶7.2）。类模板特化在一个翻译单元里至多有一个实例化点。任何特化都可以在多个翻译单元里各有实例化点。

!!! std
    If two different points of instantiation give a template specialization different meanings according to the one-definition rule, the program is ill-formed, no diagnostic required.

几个实例化点按 ODR（单一定义规则，[[basic.def.odr]]）给出不同含义时，程序是**非良构、不要求诊断**的（IFNDR）：标准对这个程序没有任何要求，编译器不必报错，生成的程序做什么都可以（[[intro.compliance]]）。

把翻译单元末尾也算作实例化点，是为了允许编译器把函数模板的实例化集中推迟到最后处理。Clang 和 GCC 都这样做。标准承认两个位置都合法，并要求它们含义一致。

```cpp ifndr title="two_pois.cpp"
#include <cstdio>
namespace N { struct S { }; }
template<class T> int g(T t) { return h(t); }

int a = g(N::S{});   // 点 1：紧随此声明之后，N::h 尚未声明
                     // 点 2：翻译单元末尾，N::h 已声明

namespace N { int h(S) { return 42; } }
int main() { std::printf("%d\n", a); }
```

按点 1，ADL 找不到 `h`，程序非良构；按点 2，调用 `N::h`。两个点含义不同，IFNDR。本机 Clang 23 在翻译单元末尾实例化 `g<N::S>`，接受这个程序并输出 `42`。

把 `g` 改成 `constexpr`，Clang 就会在用到时立即实例化（常量求值需要它的定义），报 `h` 未声明。两种结果都符合标准，因为程序本来就是 IFNDR。

晚声明一个重载，同样可能让不同实现得出不同结论：

```cpp ifndr
namespace N { struct S { }; }
template<class T> void call(T t) { touch(t); }
namespace N { void touch(S) { } }
void use() { call(N::S{}); }   // 点 1：只有 touch(S)
namespace N { void touch(const S&) { } }
// 点 2：两个 touch，调用二义
```

本机 Clang 23 在翻译单元末尾实例化，报告 `touch` 的调用有二义。

跨翻译单元也是一样：两个翻译单元里的 `g<N::S>` 看到的 `h` 不同，就是 IFNDR。每个翻译单元各自实例化，生成可合并的弱符号，链接器任选一份保留，不会发现不一致。

!!! lawyer "显式特化晚于使用"
    另一条相关规则在 [[temp.expl.spec#7]]：显式特化必须在每个会引起隐式实例化的使用之前声明。

    ```cpp error
    template<class T> void show(T) { }
    void use() { show(1); }               // 隐式实例化 show<int>
    template<> void show<int>(int) { }    // error: 太晚了
    ```

    同一个翻译单元里 Clang 能诊断（explicit specialization after instantiation）；分在不同翻译单元时基本无法诊断。

## 候选函数 [temp.dep.candidate]

### 结果不能取决于看到了哪些头文件（¶1）

```cpp title="h.h"
namespace N { struct S { }; void g(S, long); }
template<class T> void call(T t) { g(t, 0); }
```

```cpp title="a.cpp"
#include "h.h"
void use() { call(N::S{}); }   // 只看得到 g(S, long)
```

```cpp ifndr title="b.cpp"
#include "h.h"
namespace N { void g(S, int) { } }   // 对 g(t, 0) 是更好的匹配
```

`a.cpp` 里的 `call<N::S>` 选中 `g(S, long)`。可是 `b.cpp` 在同一个命名空间 `N` 里声明了 `g(S, int)`，对实参 `0` 是精确匹配。

¶1 对一个依赖调用，假设查找不只看模板定义语境和实例化语境，而是看所有翻译单元中在关联命名空间里声明的、具有外部链接的函数。如果这样会让调用非良构，或者找到更好的匹配，程序 {{ifndr}}。上面的程序正是这种情况。

编译器和链接器都不可能可靠地发现这类错误。避免它的办法是约定：一个类型的所有重载，和类型本身一起声明在同一个头文件或同一个模块接口里。

!!! history "从 UB 到 IFNDR"
    早期标准把 ¶1 的情形定为未定义行为，现在的措辞是非良构、不要求诊断。

### 模块中的依赖调用（¶2–¶5）

¶2–¶5 都是例子，展示模块怎样影响实例化语境中的 ADL。需要两条背景：

- 模块单元开头 `module;` 之后的部分叫**全局模块片段**（[[g:global-module-fragment]]），用来 `#include` 传统头文件。其中没有被模块单元用到的声明会被丢弃（[[module.global.frag]]），对导入者不可见。
- 实例化语境不只是实例化点。嵌套实例化时，它还包括外围特化的实例化语境；模板定义在模块 M 的接口单元里、而实例化点不在 M 的接口单元时，还包括 M 的主模块接口单元末尾（[[module.context#3]]）。在实例化语境中做 ADL 时，忽略来自其他翻译单元、属于全局模块、且被丢弃或具有内部链接的声明（[[basic.lookup.argdep#4]]）。

例 2（¶3）展示了定制点在模块中照常工作：

```cpp title="Std 的模块接口单元"
export module Std;
export template<typename Iter>
void indirect_swap(Iter lhs, Iter rhs) {
  swap(*lhs, *rhs);   // 无限定查找找不到 swap，只能靠 ADL
}
```

```cpp ok title="M 的模块接口单元"
export module M;
import Std;

struct S { /* ... */ };
void swap(S&, S&);        // #1，没有导出

void f(S* p, S* q) {
  indirect_swap(p, q);    // 经由实例化语境中的 ADL 找到 #1
}
```

`Std` 看不见 `M`，`#1` 也没有导出，但 `indirect_swap<S*>` 的实例化点在 `M` 里，ADL 从那里出发找到了 `swap(S&, S&)`。本机 Clang 23 编译并运行了这个例子的可执行版本，结果符合预期。

其余三个例子的要点：

- 例 1（¶2）：模块 `M1` 的全局模块片段里有 `Q::g_impl`，模板 `g` 的定义中用非依赖实参 `Q::X{}` 调用了它，定义处的 ADL 就找到了它。这算是用到，所以 `g_impl` 不会被丢弃，其他模块实例化 `g` 时可以调用它。
- 例 3（¶4）：模板里的 `t + t` 也按依赖调用处理，`operator+` 在实例化语境中可见即可。
- 例 4（¶5）：模块 `C1` 在全局模块片段里 `#include "foo.h"`，其中的 `dog(foo, foo)` 没有被 `C1` 用到，被丢弃，于是别处经由 `C1` 实例化的模板里 `dog(t, t)` 找不到它，非良构。同一个头文件里的 `cat` 是 `foo` 的隐藏友元，按第 4.2 项（关联类的定义可达时，找得到它的友元）仍能找到。如果改为导入头文件单元，`dog` 不会被丢弃，在 `C2` 接口单元末尾可见，调用合法。

!!! impl "Clang 没有实现丢弃规则"
    本机 Clang 23 对例 4 的错误情形不报错：它没有完整实现全局模块片段中声明的丢弃规则。按标准这里非良构，依赖这种宽松行为的代码不可移植。

## 常见误解

!!! pitfall "实例化时会重新查找所有名字"
    实例化时只追加 ADL。普通无限定查找停留在模板定义处，所以定义之后才声明、只接受 `int`、`double`、普通指针这类基本类型的重载，永远不会被依赖调用找到。

!!! pitfall "头文件顺序不影响结果"
    定制函数在使用模板之后才声明的代码，在 Clang、GCC 上往往因为翻译单元末尾实例化而碰巧能工作。换一个实现，或者把函数改成 `constexpr`，就可能失败。在第一次使用模板之前声明所有重载和特化。

## 思考题

!!! question "思考题 1"
    ```cpp
    #include <vector>
    template<class T> void print_all(const std::vector<T>& v) {
      for (auto& x : v) print(x);
    }
    struct Point { int x, y; };
    void print(const Point&);
    int main() { print_all(std::vector<Point>{}); }
    ```
    `print(x)` 能找到 `::print(const Point&)` 吗？把 `Point` 换成 `int`、`print` 换成 `void print(int);` 呢？

<details markdown="1">
<summary>答案</summary>

能。`Point` 的关联命名空间是全局命名空间，实例化语境中的 ADL 在那里找到 `print(const Point&)`，它在实例化点之前已经声明。

换成 `int` 后找不到。`int` 没有关联命名空间，ADL 什么也不找；普通无限定查找只在模板定义处进行，那时 `print(int)` 还没有声明。`std::vector<int>` 的关联命名空间 `std` 与此无关，`print` 的实参是 `int`。本机 Clang 23 报错：call to function 'print' that is neither visible in the template definition nor found by argument-dependent lookup。
</details>

!!! question "思考题 2"
    为什么类模板特化在一个翻译单元里至多有一个实例化点，函数模板特化却可以有多个？

<details markdown="1">
<summary>答案</summary>

类模板特化一旦实例化就是完整类型，之后的代码依赖它的大小、成员和基类。允许它在翻译单元末尾再实例化一次，之前基于第一次实例化做出的判断都可能失效。函数模板特化的定义只影响生成的代码，不影响之前声明的类型检查，所以可以推迟到末尾。标准因此把末尾也算作函数特化的实例化点，并要求两处含义一致（¶7）。
</details>

!!! question "思考题 3"
    `template<class T> struct D : Base<T> { void f() { g(*this); } };` 中，如果 `Base<T>` 有成员函数 `g`，实例化时会调用它吗？

<details markdown="1">
<summary>答案</summary>

不会。`*this` 的类型是 `D<T>`，所以 `g(*this)` 是依赖调用。但它的候选只来自定义处的无限定查找和 ADL：定义处不搜索依赖基类；ADL 只找命名空间作用域的函数和关联类的友元，不找成员函数。结果要么找到某个命名空间里的 `g`，要么非良构。要调用成员，写 `this->g(*this)`。
</details>
