---
title: 显式特化
summary: 用 template<> 为某一组模板实参单独写一份定义：能特化什么，特化必须在哪里、什么时候声明，成员特化要写几层 template<>，以及为什么函数模板最好重载而不要特化。
status: done
covers: temp.expl.spec
papers: P0692R1
related: temp.spec, temp.inst, temp.explicit, temp.spec.partial, temp.deduct.decl, temp.over, temp.func.order, over.match.best, basic.def.odr
tags: 模板, 显式特化, 全特化, ODR, IFNDR
updated: 2026-10-19
---

!!! tldr
    - 显式特化 `template<> ...` 不是模板，而是一个具体的类、函数或变量，只是名字写作 `X<int>`。它的定义和主模板毫无关系。
    - 特化的声明必须出现在第一次会引起隐式实例化的使用之前，而且每个用到它的翻译单元都要看得见，否则程序非良构、不要求诊断。最稳妥的位置是紧跟在主模板后面。
    - 函数模板的显式特化不参与重载决议：编译器先在主模板之间选出一个，再看它有没有被特化。想为某个类型定制行为，应该写重载。
    - `inline`、`constexpr`、属性和契约都不从模板继承。写在头文件里的函数模板特化要自己加 `inline`。
    - 定义显式特化类的成员时不写 `template<>`；只有仍然是特化的那几层外围模板，才各需要一个 `template<>`。

## 一份替代的定义

```cpp run ok
#include <cstdio>
template<class T> struct Traits {           // 主模板
    static const char* name() { return "?"; }
};
template<> struct Traits<int> {             // 显式特化
    static const char* name() { return "int"; }
    static constexpr bool builtin = true;   // 主模板没有这个成员
};
int main() {
    std::printf("%s %s %d\n", Traits<double>::name(),
                Traits<int>::name(), Traits<int>::builtin);
}
```

程序输出 `? int 1`。`Traits<double>` 由编译器照着[[g:primary-template|主模板]]（primary template，也就是最初声明的那个模板）生成，这叫[[g:implicit-instantiation|隐式实例化]]（[[temp.inst]]）。`Traits<int>` 则用我们手写的定义，这份定义叫**显式特化**（explicit specialization），俗称全特化。

显式特化和部分特化（[[temp.spec.partial]]）不同。部分特化如 `Traits<T*>` 还有未确定的形参，仍然是模板；显式特化的所有实参都已确定，它是一个具体的实体。这一点决定了本节的大部分规则：

- 它的定义与主模板无关，成员可以完全不同，比如上面多出来的 `builtin`；
- 特化出来的函数是普通函数，不会自动 `inline`，要遵守 ODR；
- 它必须在编译器按主模板生成同一个特化之前声明，否则同一个实体就有了两份定义。

### 可以特化什么（¶1）

¶1 以下实体可以用 `template<>` 开头的声明显式特化：

| ¶ | 实体 | 例 |
|---|---|---|
| 1.1 | 函数模板 | `template<> void f<int>(int);` |
| 1.2 | 类模板 | `template<> struct X<int> { };` |
| 1.3 | 变量模板 | `template<> constexpr int v<int> = 1;` |
| 1.4 | 类模板的成员函数 | `template<> void X<int>::mf();` |
| 1.5 | 类模板的静态数据成员 | `template<> int X<int>::s = 0;` |
| 1.6 | 类模板的成员类 | `template<> struct X<int>::Inner { };` |
| 1.7 | 类模板的成员枚举 | `template<> enum X<int>::E : int { a };` |
| 1.8 | 类或类模板的成员类模板 | `template<> template<> struct X<int>::Y<char> { };` |
| 1.9 | 类或类模板的成员函数模板 | `template<> template<> void X<int>::g<char>(char);` |

```text
explicit-specialization:
    template < > declaration
```

函数模板的特化可以省略模板实参，由编译器从函数类型推导出来：

```cpp ok
template<class T> class Array { /* ... */ };
template<class T> void sort(Array<T>& v) { /* ... */ }

template<> void sort<int>(Array<int>&);     // 显式写出 T = int
template<> void sort(Array<char*>&);        // T = char* 从函数类型推导
```

推导的细节和有多个候选模板时怎么选，见 [[temp.deduct.decl]]。

## 声明必须先于使用（¶7–¶9）

<div class="compare" markdown="1">

```cpp error
template<class T> void sort(T*) { }
void f(int* p) { sort(p); }
// 使用之后才特化
template<> void sort(int*) { }  // error
```

```cpp ok
template<class T> void sort(T*) { }
template<> void sort(int*) { }
void f(int* p) { sort(p); }  // 调用特化
```

</div>

左边的 `sort(p)` 处，特化还没有声明，编译器只能决定用主模板生成 `sort<int>`。之后再出现手写的 `sort<int>`，同一个函数就有了两份不同的定义。本机 Clang 23 对左边报 `explicit specialization of 'sort<int>' after instantiation`。

¶7 规定：如果一个模板、成员模板或类模板的成员被显式特化，那么在每个翻译单元里，凡是会引起隐式实例化的使用处，都必须能看到这个特化的声明（标准的说法是声明从使用处**可达**，reachable）。违反这条不要求诊断，程序非良构，简称 IFNDR（ill-formed, no diagnostic required）：编译器可以不报错，生成的程序做什么都可以。

### 跨翻译单元时没有人能发现

同一个翻译单元里，编译器能看到冲突，所以 Clang 会报错。特化和使用分在两个翻译单元时就看不到了：

```cpp title="a.h"
template<class T> int size_of() { return sizeof(T); }
struct Foo { int a[4]; };
```

```cpp title="b.cpp"
#include "a.h"
int from_b() { return size_of<Foo>(); }   // 看不到特化
```

```cpp title="c.cpp" ifndr
#include "a.h"
#include <cstdio>
template<> int size_of<Foo>() { return -1; }
int from_b();
int main() { std::printf("%d %d\n", from_b(), size_of<Foo>()); }
```

本机 Clang 23 编译链接都没有任何提示。`-O0` 输出 `-1 -1`，`-O2` 输出 `16 -1`。

原因在符号层面。显式特化和隐式实例化的 mangled name 相同，链接时是同一个符号。`b.cpp` 里隐式实例化出来的 `size_of<Foo>` 是弱定义，`c.cpp` 里的显式特化是普通的强定义，链接器选了强定义。但 `-O2` 下 `b.cpp` 已经把调用内联成了 `sizeof(Foo)`，链接器再选什么都影响不到它。

!!! tip "特化放在哪里"
    显式特化要么和主模板放在同一个头文件，要么放在特化所涉及类型的头文件里，紧跟在类型定义之后。不要把特化藏在某个 `.cpp` 里，指望别的翻译单元也能用上。

会引起隐式实例化的使用不一定是一次显式调用。`sizeof(X<int>)`、把 `X<int>` 用作基类或数据成员类型、另一个模板实例化时间接用到，都算。所以特化离主模板越近越好。

### 声明了却没有定义

¶7 还有两句：

- 如果程序没有给某个显式特化提供定义，而它又被以会引起隐式实例化的方式使用，或者它是虚成员函数，程序 IFNDR。实际上这通常表现为链接错误。
- 已声明但未定义的显式特化，永远不会被隐式实例化。

¶9 注 2 由此推出：只声明不定义的类模板特化就是一个不完整类，可以像其他不完整类一样使用。

```cpp
template<class T> class X { };  // 主模板有定义
template<> class X<int>;        // 只声明特化

X<int>* p;                      // OK：指向不完整类的指针
X<int> x;                       // error: X<int> 是不完整类型
```

即使主模板有定义，`X<int>` 也不会从主模板生成。这可以用来禁止某个实参，不过 C++20 起用约束（[[temp.constr]]）表达通常更清楚。

!!! lawyer "成员枚举：特化来得及吗"
    标准例 4 的后半段：

    ```cpp
    template<class T> struct A {
        enum E : T;
        enum class S : T;
    };
    template<> enum A<int>::E : int { eint };           // OK
    template<> enum class A<int>::S : int { sint };     // OK
    template<class T> enum A<T>::E : T { eT };
    template<class T> enum class A<T>::S : T { sT };
    template<> enum A<char>::E : char { echar };        // error
    template<> enum class A<char>::S : char { schar };  // OK
    ```

    写出 `A<char>::E` 这个名字，就要先隐式实例化 `A<char>`，才能查到成员 `E`。类实例化时，无作用域枚举的定义随之实例化（[[temp.inst#3]]），此时类外定义 `{ eT }` 已经可见，再特化 `E` 就晚了。有作用域枚举 `S` 只实例化声明，还来得及。`A<int>` 的两个特化出现在 `{ eT }` 之前，那时 `E` 还没有可用的定义，所以不冲突。本机 Clang 23 对 `A<char>::E` 那一行报 `explicit specialization of 'E' after instantiation`。

¶8 列举了一长串实体（各种模板、各种成员），说明它们的显式特化和部分特化声明相对于实例化点的位置，会决定程序是否良构。这一段以一首押韵的五行打油诗结尾，大意是写特化时要小心它的位置，否则为了让它编译通过会吃尽苦头。它没有引入新规则，只是提醒 ¶7 和 [[temp.point]] 的后果。

## 函数模板的特化不参与重载（¶11）

<div class="compare" markdown="1">

```cpp run ok
#include <stdio.h>
template<class T> void f(T)  { puts("a"); }
template<> void f(int*)      { puts("c"); }
template<class T> void f(T*) { puts("b"); }
int main() { int* p{}; f(p); }  // 输出 b
```

```cpp run ok
#include <stdio.h>
template<class T> void f(T)  { puts("a"); }
template<class T> void f(T*) { puts("b"); }
template<> void f(int*)      { puts("c"); }
int main() { int* p{}; f(p); }  // 输出 c
```

</div>

两个程序只差特化 `c` 的位置，结果却不同。原因分两步。

1. 特化属于哪个模板，由它声明时可见的模板决定（[[temp.deduct.decl]]）。左边 `c` 声明时只有 `f(T)` 可见，于是它是 `f(T)` 的特化 `f<int*>`。右边两个模板都能匹配，`f(T*)` 更特殊，于是它是 `f(T*)` 的特化 `f<int>`。
2. 重载决议只在主模板之间进行（[[temp.over]]）。`f(p)` 的候选是 `f(T)` 推导出的 `f<int*>` 和 `f(T*)` 推导出的 `f<int>`，偏序选中 `f(T*)`。选定之后，才去看 `f(T*)` 的 `f<int>` 有没有被显式特化。左边没有，输出 `b`；右边有，输出 `c`。

所以显式特化的函数从不参与选择，它只是替换已经选中的那个特化的函数体。这让代码的行为依赖声明顺序，很难推理。

¶11 另外规定，一个与模板同名、类型又恰好等于某个模板特化的普通函数，不是显式特化，而是一个独立的非模板函数，与模板构成重载（[[temp.fct]]）：

```cpp run ok
#include <cstdio>
template<class T> void k(T) { std::puts("primary"); }
void k(int)                 { std::puts("plain overload"); }  // 普通函数
template<> void k(int)      { std::puts("specialization"); }  // k<int> 的特化

int main() {
    k(1);        // plain overload：同等匹配时非模板优先
    k<>(1);      // specialization：<> 只考虑模板
    k<int>(1);   // specialization
}
```

`k(1)` 选中普通函数，依据是 [[over.match.best]] ¶2.4：两个候选同样好时，非模板函数胜出。

由此得到两条实用建议：

- 想为某个类型定制函数模板的行为，写一个普通重载（非模板函数或另一个函数模板），不要显式特化。
- 确实需要特化语义时（例如函数模板是某个库的定制点），让函数模板转发给一个类模板的静态成员函数，再去特化或部分特化那个类模板。

## `inline`、`constexpr`、属性和契约不继承（¶12）

¶12 函数模板或变量模板的显式特化是否为 `inline`、`constexpr`、`constinit`、`consteval`，由特化自己的声明决定，与模板无关。模板声明上的属性和 C++26 的函数契约说明符（`pre`、`post`）对显式特化也没有效果。

```cpp
template<class T> void f(T) { /* ... */ }
template<class T> inline T g(T) { /* ... */ }

template<> inline void f<>(int) { /* ... */ }   // OK：inline
template<> int g<>(int) { /* ... */ }           // OK：不是 inline

template<typename> [[noreturn]] void h([[maybe_unused]] int i);
template<> void h<int>(int i) {
    // [[noreturn]] 不继承：实现不应警告函数会返回
    // [[maybe_unused]] 也不继承：实现可以警告 i 未使用
}
```

`constexpr` 不继承的后果：

```cpp error
template<class T> constexpr int k(T) { return 1; }
template<> int k(int) { return 2; }   // 不是 constexpr
static_assert(k('a') == 1);           // OK：k<char> 由主模板生成
static_assert(k(0) == 2);             // error: k<int> 不是 constexpr
```

这样规定是因为特化有自己的函数体。`constexpr` 是对函数体的承诺，主模板的函数体能常量求值，不代表特化的也能；`inline` 决定这份定义能否在多个翻译单元中重复出现，只有写定义的人知道它放在哪里。语言又没有取消这两个说明符的语法，所以只能规定不继承。

!!! pitfall "头文件里的函数模板特化"
    函数模板及其隐式实例化可以在多个翻译单元中重复定义（[[basic.def.odr]]），显式特化却是普通函数。把 `template<> void f(int) { ... }` 写在头文件里、被两个 `.cpp` 包含，就是同一个非内联函数定义了两次，链接时报重复符号。要写成 `template<> inline void f(int) { ... }`，或者头文件里只放声明、在一个 `.cpp` 里定义。变量模板的特化同理，用 `inline` 或 `constexpr`（`constexpr` 变量隐含 `inline`）。

## 特化类模板的成员（¶5–¶6、¶14–¶17）

### 只替换一个成员（¶5、¶14）

```cpp run ok
#include <cstdio>
template<class T> struct Printer {
    void print(T) { std::puts("generic"); }
    void hello()  { std::puts("hello"); }
};
template<> void Printer<bool>::print(bool v) {
    std::puts(v ? "true" : "false");
}

int main() {
    Printer<bool> p;
    p.print(true);    // true：显式特化的成员
    p.hello();        // hello：仍由模板生成
}
```

¶5 类模板的成员函数、成员函数模板、成员类、成员枚举、成员类模板、静态数据成员和静态数据成员模板，都可以针对一个隐式实例化的类特化单独做显式特化。这时类模板的定义必须可见。`Printer<bool>` 本身仍从模板生成，只有 `print` 换成了手写的版本。如果这样的特化指名一个隐式声明的特殊成员函数（例如没有声明过的默认构造函数），程序非良构。

¶14 即使成员在类模板定义里已经有了函数体，也照样可以特化。成员模板的特化可以只特化外层类，也可以连成员模板一起特化：

```cpp ok
template<class T> struct A {
    void f(T);
    template<class X1> void g1(T, X1);
    template<class X2> void g2(T, X2);
    void h(T) { }
};

template<> void A<int>::f(int);              // 特化成员函数

template<class T> template<class X1>
void A<T>::g1(T, X1) { }                     // 类外定义成员模板（不是特化）

template<> template<class X1>
void A<int>::g1(int, X1);                    // 只特化 A<int>，g1 仍是模板

template<> template<>
void A<int>::g1(int, char);                  // 都特化：X1 推导为 char
template<> template<>
void A<int>::g2<char>(int, char);            // X2 显式指定为 char

template<> void A<int>::h(int) { }           // 类内已有定义也可以特化
```

¶17 第三个声明说明了一点：未特化的类模板的成员模板，特化后如果还留着自己的形参，它本身仍是模板。

### 要写几个 `template<>`（¶6、¶15–¶16）

¶6 显式特化类的成员不会从类模板的成员声明生成，用到哪个成员，就必须自己定义哪个。特化类的定义与生成的特化无关，所以定义它的成员时就像定义普通类的成员一样，不写 `template<>`：

```cpp
template<class T> struct A {
    struct B { };
    template<class U> struct C { };
};

template<> struct A<int> {          // 显式特化的类
    void f(int);
};
void h() {
    A<int> a;
    a.f(16);                        // A<int>::f 必须在某处定义
}
void A<int>::f(int) { }             // 不写 template<>：A<int> 是普通类

template<> struct A<char>::B {      // 特化成员类，A<char> 由模板生成
    void f();
};
void A<char>::B::f() { }            // 也不写：A<char>::B 是普通类

template<> template<class U>
struct A<char>::C {                 // 成员类模板特化后仍是类模板
    void f();
};
template<>                          // 要写：外层 A<char> 是特化
template<class U> void A<char>::C<U>::f() { }

template<> struct A<short>::B { void f(); };
template<> void A<short>::B::f() { }             // error: 不能写 template<>

template<> template<class U> struct A<short>::C { void f(); };
template<class U> void A<short>::C<U>::f() { }   // error: 缺少 template<>
```

可以这样记：`A<int>` 特化之后就是一个普通类，`A<int>::f` 是普通成员函数，和定义 `struct Foo` 的成员一样，不写任何 `template`。`A<char>::C<U>` 仍是模板，定义它的成员时要同时写出外层的特化（`template<>`）和自己的形参（`template<class U>`）。

¶15 成员可以嵌套在多层类模板里。特化这样的成员时，每一层被显式特化的外围类模板都要有一个 `template<>`：

```cpp
template<class T1> class A {
    template<class T2> class B {
        void mf();
    };
};
template<> template<> class A<int>::B<double>;
template<> template<> void A<char>::B<char>::mf();
```

¶16 在命名空间作用域的声明里，可以只特化其中几层，其余层保持未特化，并用 `template<形参列表>` 代替那一层的 `template<>`，形参的种类要与主模板定义一致。但外围类模板没有特化时，不能特化其中的成员类模板：

```cpp
template<class T1> class A {
    template<class T2> class B {
        template<class T3> void mf1(T3);
        void mf2();
    };
};
template<> template<class X>
class A<int>::B {                       // 特化 A<int>，B 仍是模板
    template<class T> void mf1(T);
};
template<> template<> template<class T>
void A<int>::B<double>::mf1(T t) { }    // 特化 A<int> 和 B<double>，mf1 仍是模板
template<class Y> template<>
void A<Y>::B<double>::mf2() { }         // error: 特化了 B<double>，外围的 A 却没有
```

最后一行被禁止，是因为 `A<Y>` 的 `Y` 未知，某个 `A` 的显式特化可能把成员 `B` 改得面目全非甚至删掉，对所有 `Y` 特化 `A<Y>::B<double>` 没有意义。

## 静态数据成员：有初始化器才是定义（¶13）

¶13 模板的静态数据成员的显式特化，以及静态数据成员模板的显式特化，带初始化器时是定义，不带时只是声明：

```cpp
struct Q { Q() {} };
template<class T> struct X { static Q x; };

template<> Q X<int>::x;          // 声明，不是定义
template<> Q X<int>::x ();       // error: 这声明了一个函数
template<> Q X<int>::x = Q();    // 定义
template<> Q X<char>::x{};       // 定义：花括号初始化器
```

这与普通类的静态数据成员不同，`Q S::x;` 在类外就是定义。显式特化需要一种只声明特化存在的写法（放在头文件里），所以无初始化器的形式被规定为声明。要默认初始化时，注 4 建议用函数式转型 `= Q()`；C++11 起写 `{}` 也可以。

## 其他限制（¶2–¶4、¶10、¶18–¶19）

¶2 显式特化不能是 `export` 声明。在模块里，特化随主模板一起可达，不需要单独导出。显式特化也不能带 `thread_local` 以外的存储类说明符：`template<> static void f<int>(int);` 非良构，链接属性由主模板决定。本机 Clang 23 对这种写法只给一条警告（`-Wexplicit-specialization-storage-class`），这满足至少一条诊断的要求。

¶3 显式特化可以在主模板可以定义的任何作用域中声明（[[dcl.meaning]]、[[class.mem]]、[[temp.mem]]），包括类作用域：

```cpp ok
struct S {
    template<class T> int g(T) { return 0; }
    template<> int g(int) { return 1; }   // 在类内特化成员函数模板
};
```

早期标准要求显式特化只能出现在命名空间作用域，[[CWG727]] 把它放宽成了今天的规则。本机 Clang 23 接受上面的代码。

¶4 显式特化不引入新名字。被特化的模板至少要先声明（不必定义）；特化成员模板时，外围类或类模板的定义必须可见：

```cpp
template<> class X<int> { /* ... */ };     // error: X 还不是模板
template<class T> class X;
template<> class X<char*> { /* ... */ };   // OK
```

¶10 注 3 提醒，特化受约束的模板时，模板实参必须满足模板的关联约束（[[temp.constr.decl]]）。

¶18 显式特化声明不能是友元声明。`template<> friend struct S<int>;` 非良构。友元声明可以指名一个已有的函数模板特化，如 `friend void f<>(int);`，但那是在引用特化，不是在声明特化。

¶19 下面三种显式特化的声明和定义里不能写默认函数实参：函数模板的显式特化（¶19.1）、成员函数模板的显式特化（¶19.2），以及所属类特化是隐式实例化的类模板成员函数的显式特化（¶19.3）。

```cpp error
template<class T> void f(T) { }
template<> void f(char = 'a') { }   // error: 特化不能有默认实参
```

函数调用时，默认实参取自重载决议选中的那个模板的声明，而特化在选定模板之后才被考虑。如果特化可以有自己的默认实参，`f()` 这样的调用是否合法就会取决于特化是否可见。注 5 指出，显式特化的类的成员函数（如前面的 `A<int>::f`）可以有默认实参，因为它是普通类的普通成员函数。

显式特化声明中的模板实参和函数声明符里的名字不做访问检查，可以直接写类的私有成员类型（[[temp.spec#6]]，C++20 的 [[P0692R1]]）。

## 常见误解

!!! pitfall "特化 `std::swap`"
    在 `std` 中声明标准库函数模板的显式特化是未定义行为（[[namespace.std#1]]），只有标准库类模板（如 `std::hash`、`std::formatter`）允许在满足条件时特化（[[namespace.std#2]]）。所以 `template<> void std::swap(MyType&, MyType&)` 是错的，应该在 `MyType` 所在的命名空间写一个 `swap` 重载，由 ADL 找到它。

!!! pitfall "特化了函数模板，就能改变重载决议的结果"
    不能。特化只替换被选中的那个特化的函数体，不会让一个原本不被选中的模板胜出，见上面 ¶11 的对比。需要影响选择，就写重载。

## 思考题

!!! question "思考题"
    下面的程序输出什么？
    ```cpp
    #include <cstdio>
    template<class T> void f(T)  { std::puts("a"); }
    template<class T> void f(T*) { std::puts("b"); }
    template<> void f<int*>(int*) { std::puts("c"); }
    int main() { int x; f(&x); }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `b`。特化写明了 `f<int*>`，即 `T = int*`：代入 `f(T)` 得到 `f(int*)`，代入 `f(T*)` 得到 `f(int**)`，只有前者与声明的类型相符，所以它特化的是 `f(T)`。调用 `f(&x)` 时偏序选中更特殊的 `f(T*)`（`T = int`），而 `f(T*)` 的 `f<int>` 没有被特化，于是输出 `b`。把特化写成 `template<> void f<int>(int*)`，或者不写模板实参 `template<> void f(int*)`（两个模板都可见，偏序选 `f(T*)`），才会输出 `c`。本机 Clang 23 运行结果为 `b`。
</details>

## 历史与演进

!!! history
    - C++98 已有显式特化，¶8 的打油诗也从那时保留至今。
    - C++14 加入变量模板，也就有了变量模板的显式特化。
    - [[CWG727]] 允许在类作用域中显式特化。
    - C++20 的 [[P0692R1]] 让特化声明中的名字免于访问检查；`constinit`、`consteval` 也加入了不继承的列表。
    - C++26 规定函数契约说明符不从模板继承。
