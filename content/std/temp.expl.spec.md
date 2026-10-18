---
title: 显式特化
summary: `template<>` 为某组模板实参提供完全替代的定义。可以特化什么、在哪里声明、何时必须可见（在首次会引起隐式实例化的使用之前，否则 IFNDR——标准为此写了一首打油诗）、成员特化的 template<> 层数、为什么函数模板的特化不参与重载、inline/constexpr/属性不从模板继承、默认实参的禁令。
status: done
covers: temp.expl.spec
papers: P0692R1
related: temp.spec, temp.inst, temp.explicit, temp.spec.partial, temp.deduct.decl, temp.over, temp.func.order, over.match.best, basic.def.odr
tags: 模板, 显式特化, 全特化, ODR, IFNDR
updated: 2026-10-18
---

[[g:explicit-specialization|**显式特化**]]（explicit specialization，俗称"全特化"）告诉编译器：对这组模板实参，**不要**用模板生成定义，用我写的这份。

```cpp
template<class T> struct is_pointer       { static constexpr bool value = false; };
template<class T> struct is_pointer<T*>   { static constexpr bool value = true;  };  // 部分特化
template<>        struct is_pointer<void> { static constexpr bool value = false; };  // 显式特化（多余，示意）
```

它和**部分特化**（[[temp.spec.partial]]）不同：部分特化仍是模板（还有未确定的形参），显式特化是一个**具体实体**——一个普通的类、函数或变量，只是名字恰好写作 `X<int>`。这一点决定了本节的很多规则：显式特化的函数是普通函数（不自动 inline），要遵守 ODR；它的定义与主模板毫无关系（成员可以完全不同）；它必须在"有人按主模板实例化它"之前被声明。

## 可以显式特化什么（¶1）

¶1 以下实体可以用 `template<>` 引入的声明显式特化：

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

```cpp ok
template<class T> class stream;
template<> class stream<char> { /* ... */ };       // #1

template<class T> class Array { /* ... */ };
template<class T> void sort(Array<T>& v) { /* ... */ }

template<> void sort<int>(Array<int>&);            // #2
template<> void sort(Array<char*>&);               // #3：模板实参从函数类型推导
```

#1 将作为 `stream<char>` 的定义；其他 `stream` 由模板实例化（在这个例子里主模板没有定义，所以其他 `stream<T>` 都是不完整类型）。#2、#3 分别用于 `Array<int>`、`Array<char*>`；其他 `Array` 类型用模板生成的函数。

## 声明的形式与位置（¶2–¶4）

¶2 显式特化中的 *declaration* 不能是 *export-declaration*（模块中，显式特化随主模板的可达性一起可用，不需要也不能单独 `export`）；不能使用 `thread_local` 以外的存储类说明符——所以不能写 `template<> static void f<int>(int);`，链接属性由主模板决定。

¶3 显式特化可以在**任何主模板可以被定义的作用域**中声明（[[dcl.meaning]]、[[class.mem]]、[[temp.mem]]）。

这意味着**类作用域**中的成员模板可以直接在类内特化：

```cpp ok
struct S {
    template<class T> int g(T) { return 0; }
    template<> int g(int) { return 1; }      // OK：在类作用域内显式特化成员函数模板
};
```

!!! history "类内显式特化"
    C++17 之前标准要求显式特化必须在命名空间作用域声明，类内特化是非良构的（MSVC 一直允许）。[[CWG727]] 放宽为"主模板可以被定义的任何作用域"，现在 GCC、Clang、MSVC 都接受。

¶4 显式特化**不引入名字**。被特化的函数模板、类模板或变量模板的**声明**（不必是定义，注 1）必须从显式特化处可达；对类或类模板的**成员模板**做显式特化时，类或类模板的**定义**必须可达。

```cpp
template<> class X<int> { /* ... */ };     // error: X 还不是模板（未声明）
template<class T> class X;
template<> class X<char*> { /* ... */ };   // OK：X 是已声明的类模板
```

## 成员的显式特化（¶5–¶6）

¶5 类模板的成员函数、成员函数模板、成员类、成员枚举、成员类模板、静态数据成员、静态数据成员模板，可以为一个**隐式实例化**的类特化而显式特化；此时类模板的**定义**必须从显式特化处可达。若这样的成员显式特化指名一个隐式声明的特殊成员函数（[[special]]），程序非良构。

也就是说，可以只"替换" `X<int>` 的一个成员，而 `X<int>` 的其余部分仍然从模板生成：

```cpp run ok title="member_spec.cpp"
#include <cstdio>
template<class T> struct Printer {
    void print(T v) { std::printf("generic\n"); (void)v; }
    void hello()    { std::printf("hello\n"); }
};
template<> void Printer<bool>::print(bool v) { std::printf(v ? "true\n" : "false\n"); }

int main() {
    Printer<bool> p;
    p.print(true);    // true（显式特化的成员）
    p.hello();        // hello（仍由模板生成）
}
```

¶6 反过来：**显式特化的类**，其成员**不**从类模板的成员声明隐式实例化；如果需要成员的定义，必须自己显式定义。显式特化类的定义必须从它的任何成员的定义处可达。显式特化类的定义与生成的特化**无关**——成员不必同名、同类型。显式特化类模板的成员**按普通类的方式定义，不写 `template<>`**；显式特化成员类的成员也如此。但定义一个"被特化为类模板"的显式特化成员类模板的成员时，**要**写 `template<>`。

这几句话规定了一个经常让人困惑的 `template<>` 层数问题：

```cpp
template<class T> struct A {
    struct B { };
    template<class U> struct C { };
};

template<> struct A<int> {          // 显式特化的类：成员与主模板无关
    void f(int);
};
void h() {
    A<int> a;
    a.f(16);                        // A<int>::f 必须在某处定义
}
void A<int>::f(int) { }             // 不写 template<>：A<int> 是普通类

template<> struct A<char>::B {      // 显式特化成员类（A<char> 是隐式实例化的）
    void f();
};
void A<char>::B::f() { }            // 也不写 template<>：A<char>::B 是普通类

template<> template<class U> struct A<char>::C {   // 成员类模板被特化"为类模板"
    void f();
};
template<>                          // 要写 template<>：外层 A<char> 是特化
template<class U> void A<char>::C<U>::f() { }

template<> struct A<short>::B { void f(); };
template<> void A<short>::B::f() { }                // error: 不允许 template<>

template<> template<class U> struct A<short>::C { void f(); };
template<class U> void A<short>::C<U>::f() { }      // error: 需要 template<>
```

记忆方法：**`template<>` 的个数 = 名字里"被特化的模板"层数，但只在声明"仍是特化/模板"的东西时出现**。`A<int>` 显式特化后它就是一个普通类，`A<int>::f` 是普通成员函数——就像定义 `struct Foo` 的成员一样，不写任何 `template`。而 `A<char>::C<U>` 仍是模板，定义它的成员要同时写出"外层的特化"（`template<>`）和"自己的形参"（`template<class U>`）。

## 声明必须先于使用（¶7）

¶7 是本节最重要、也最容易违反的规则：

!!! std
    If a template, a member template or a member of a class template is explicitly specialized, a declaration of that specialization shall be reachable from every use of that specialization that would cause an implicit instantiation to take place

    显式特化的声明必须从每一个"会导致隐式实例化的使用"处可达——在每个有这种使用的 TU 中。

违反它是 {{ifndr}}。此外：

- 若程序没有为某个显式特化提供定义，而该特化被以会导致隐式实例化的方式使用，或者该成员是虚成员函数——{{ifndr}}；
- 对**已声明但未定义**的显式特化，**永远不会**生成隐式实例化。

```cpp
class String { };
template<class T> class Array { /* ... */ };
template<class T> void sort(Array<T>& v) { /* ... */ }

void f(Array<String>& v) {
    sort(v);              // 使用主模板 sort(Array<T>&)，T 为 String
}

template<> void sort<String>(Array<String>& v);   // error: 在主模板的使用之后特化
template<> void sort<>(Array<char*>& v);          // OK：sort<char*> 尚未被使用
```

为什么不能"后来居上"？因为 `sort(v)` 那一刻编译器已经决定用主模板生成 `sort<String>`（至少已经有了一个隐式实例化的意图，实例化点可能在 TU 末尾）；之后又冒出一个 `sort<String>` 的手写定义，同一个实体就有了两个不同的定义。在同一 TU 中编译器能看到冲突，Clang 报 "explicit specialization of 'sort<String>' after instantiation"；跨 TU（一个 TU 用了主模板，另一个 TU 有特化）则看不到，这就是 IFNDR——实践中链接器随机选一个，程序行为取决于链接顺序。

!!! pitfall "特化必须和主模板放在一起"
    最稳妥的做法：显式特化要么和主模板放在同一个头文件，要么放在"使用该特化的类型"的头文件里，**紧跟**类型定义之后。永远不要把特化放在某个 `.cpp` 里，期待别的 TU 也能"用上"。

### 成员枚举的例子

标准例 4 后半段展示了 ¶3.2（无作用域枚举的定义随类实例化）与 ¶7 的交互：

```cpp
template<class T> struct A {
    enum E : T;
    enum class S : T;
};
template<> enum A<int>::E : int { eint };           // OK
template<> enum class A<int>::S : int { sint };     // OK
template<class T> enum A<T>::E : T { eT };
template<class T> enum class A<T>::S : T { sT };
template<> enum A<char>::E : char { echar };        // error: A<char>::E 在 A<char> 实例化时已被实例化
template<> enum class A<char>::S : char { schar };  // OK
```

关键在于：写出 `A<char>::E` 这个名字本身就要求 `A<char>` 被隐式实例化（¶5：成员特化针对的是"隐式实例化的类特化"，要查找成员 `E` 就得有类的成员列表）。`A<char>` 一实例化，无作用域枚举 `E` 的**定义**随之实例化（[[temp.inst#3]] ¶3.2，此时类外定义 `{ eT }` 已经可见），再特化就晚了；有作用域枚举 `S` 只实例化声明，还来得及。而 `A<int>` 的两个特化出现在类外定义 `{ eT }` **之前**，实例化 `A<int>` 时 `E` 还没有可用的定义，所以不冲突。Clang 对 `A<char>::E` 那一行报 "explicit specialization of 'E' after instantiation"。

## 标准里的打油诗（¶8）

¶8 列举了一长串"显式特化声明与部分特化声明的**位置**会影响程序是否良构"的实体——函数模板、类模板、变量模板、成员函数、静态数据成员、成员类、成员枚举、成员类模板、成员函数模板、成员模板的成员函数……"等等"——然后以一首押韵的五行打油诗（limerick）收尾：

!!! std
    When writing a specialization, be careful about its location; or to make it compile will be such a trial as to kindle its self-immolation.

    写特化时，小心它放在哪儿；否则想让它编译通过，会是一场足以让它自焚的磨难。

这是 ISO C++ 标准中唯一一段韵文，从 C++98 起一直保留至今。它没有规范效力（¶8 本身是在总结 ¶7 和 [[temp.point]] 的后果），但非常精确地概括了实践经验：显式特化与部分特化的错误几乎都是**位置**错误——在使用之后声明、在另一个 TU 中声明、在实例化点之后可见。

## 已声明未定义的类特化（¶9）

¶9（注 2）已声明但未定义的类模板显式特化，可以像其他不完整类一样使用：

```cpp
template<class T> class X;      // 类模板
template<> class X<int>;        // 声明显式特化，不定义

X<int>* p;                      // OK：指向已声明的类 X<int> 的指针
X<int> x;                       // error: 不完整类 X<int> 的对象
```

结合 ¶7 的"已声明未定义的显式特化永不隐式实例化"：即使主模板有定义，`X<int>` 也不会从主模板生成——它就是不完整的。这是一种"禁用某个实参"的技巧，不过 C++20 起用约束（`requires`）表达通常更清楚。

## 约束（¶10）

¶10（注 3）显式特化受约束的模板，需要满足其关联约束。全部模板实参都指定时在形成模板名时检查；函数模板有尾随实参省略时，在推导中检查（[[temp.deduct.decl]]）。

## 函数模板的特化不是重载（¶11）

¶11 与模板同名、且类型恰好与某个模板特化相同的函数，**不是**显式特化（[[temp.fct]]）——它是一个独立的非模板函数，与模板构成重载。

这条规则与"函数模板的显式特化不参与重载决议"一起，构成了 Herb Sutter 那篇著名文章 *Why Not Specialize Function Templates?*（以及 GotW #49）的核心论点。看这个例子（常被称为 Dimov/Abrahams 例子）：

```cpp run title="dimov_abrahams.cpp"
#include <cstdio>
template<class T> void f(T)    { std::puts("(a) f(T)"); }
template<>        void f(int*) { std::puts("(c) f<int*>(int*)"); }  // 特化的是 (a)！
template<class T> void f(T*)   { std::puts("(b) f(T*)"); }

int main() {
    int* p = nullptr;
    f(p);        // 输出 (b) f(T*)
}
```

把 (c) 移到 (b) 之后：

```cpp run title="dimov_abrahams2.cpp"
#include <cstdio>
template<class T> void f(T)    { std::puts("(a) f(T)"); }
template<class T> void f(T*)   { std::puts("(b) f(T*)"); }
template<>        void f(int*) { std::puts("(c) f<int>(int*)"); }   // 现在特化的是 (b)

int main() {
    int* p = nullptr;
    f(p);        // 输出 (c) f<int>(int*)
}
```

原因分两步：

1. **显式特化属于哪个模板**，由声明处可见的模板做推导（[[temp.deduct.decl]]）再偏序决定。第一个程序中 (c) 声明时只有 (a) 可见，于是它是 `f<int*>`（(a) 的特化）。第二个程序中 (a)、(b) 都能匹配，(b) 更特殊，于是 (c) 是 `f<int>`（(b) 的特化）。
2. **重载决议只看主模板**（[[temp.over]]）：对 `f(p)`，候选是 (a) 推导出的 `f<int*>` 和 (b) 推导出的 `f<int>`；偏序选 (b)。选定模板之后，才去看这个特化有没有被显式特化。第一个程序中 (b) 的 `f<int>` 没有被特化，输出 (b)；第二个程序中有，输出 (c)。

所以显式特化的函数**不参与**选择，它只是"替换已被选中的那个模板特化的函数体"。这让代码行为依赖于声明顺序，极难推理。Sutter 的建议是：

- 想为某个类型定制函数模板的行为，**写一个普通的重载**（非模板函数或另一个函数模板），不要显式特化；
- 如果确实需要特化的语义（例如函数模板是某个库的定制点），让函数模板转发给一个类模板的静态成员，然后特化/部分特化那个类模板。

```cpp run title="overload_vs_spec.cpp"
#include <cstdio>
template<class T> void f(T)    { std::puts("primary"); }
void f(int)                    { std::puts("plain overload"); }   // 非模板函数，¶11：不是特化
template<> void f(int)         { std::puts("specialization"); }  // f<int> 的显式特化

int main() {
    f(1);        // plain overload：同等匹配时非模板优先（[over.match.best] ¶2.4）
    f<>(1);      // specialization：<> 强制只考虑模板
    f<int>(1);   // specialization
}
```

## inline、constexpr、属性不从模板继承（¶12）

¶12 函数或变量模板的显式特化是否为 `inline`、`constexpr`、`constinit`、`consteval`，由**显式特化自己**决定，与模板的这些性质无关。同样，模板声明上的**属性**和**函数契约说明符**（{{c++26}}）对显式特化没有效果。

```cpp
template<class T> void f(T) { /* ... */ }
template<class T> inline T g(T) { /* ... */ }

template<> inline void f<>(int) { /* ... */ }   // OK：inline
template<> int g<>(int) { /* ... */ }           // OK：不是 inline

template<typename> [[noreturn]] void h([[maybe_unused]] int i);
template<> void h<int>(int i) {
    // 实现不应警告"函数返回了"（[[noreturn]] 不继承），
    // 但可以警告未使用的形参 i（[[maybe_unused]] 也不继承）
}
```

后果：

```cpp error
template<class T> constexpr int k(T) { return 1; }
template<> int k(int) { return 2; }   // 不是 constexpr！
static_assert(k('a') == 1);           // OK：主模板生成的 k<char> 是 constexpr
static_assert(k(0) == 2);             // error: k<int> 不是 constexpr 函数
```

!!! pitfall "头文件里的函数模板特化 = ODR 违规"
    函数模板本身可以放在头文件里，因为模板（及其隐式实例化）可以在多个 TU 中定义（[[basic.def.odr]]）。但**显式特化是普通函数**，`template<> void f(int) { ... }` 写在头文件里、被两个 `.cpp` 包含，就是同一个非内联函数的两次定义——链接时 "duplicate symbol"。必须写成 `template<> inline void f(int) { ... }`，或者只在头文件中声明、在一个 `.cpp` 中定义。变量模板的显式特化同理（用 `inline` 或 `constexpr`——后者对变量隐含 `inline`）。

!!! note "契约不继承 {{c++26}}"
    C++26 的函数契约说明符（`pre`、`post`）同样不从模板传给显式特化。为函数模板写了前置条件，并不意味着它的显式特化也会检查——特化必须自己重新写。

## 静态数据成员特化：声明还是定义（¶13）

¶13 模板的静态数据成员的显式特化、或静态数据成员模板的显式特化，**有初始化器才是定义**，否则只是声明。

```cpp
struct Q { Q() {} };
template<class T> struct X { static Q x; };

template<> Q X<int>::x;          // 声明（不是定义！）
template<> Q X<int>::x ();       // error: 声明了一个函数
template<> Q X<int>::x = Q();    // 定义
template<> Q X<char>::x{};       // 定义（花括号初始化器）
```

这与普通静态数据成员的类外定义（`Q S::x;` 就是定义）**不同**。原因：显式特化的声明语法 `template<> Q X<int>::x;` 需要一种方式只"声明"特化存在（例如在头文件中），于是标准规定无初始化器时为声明。需要默认初始化的定义时，注 4 建议用函数式转型 `= X()`；C++11 起用 `{}` 也行。

## 成员与成员模板的特化（¶14–¶17）

¶14 类模板的成员或成员模板可以为类模板的某个**隐式实例化**显式特化，即使成员或成员模板在类模板定义中已有定义。成员（模板）的显式特化用显式特化的语法写出。

```cpp ok
template<class T> struct A {
    void f(T);
    template<class X1> void g1(T, X1);
    template<class X2> void g2(T, X2);
    void h(T) { }
};

template<> void A<int>::f(int);                         // 成员函数特化

template<class T> template<class X1>
    void A<T>::g1(T, X1) { }                            // 类外定义成员模板（不是特化）

template<> template<class X1>
    void A<int>::g1(int, X1);                           // 成员模板特化：仍是模板（X1）

template<> template<>
    void A<int>::g1(int, char);                         // 成员模板的完全特化：X1 推导为 char
template<> template<>
    void A<int>::g2<char>(int, char);                   // X2 显式指定为 char

template<> void A<int>::h(int) { }                      // 类内已有定义的成员也可以特化
```

¶15 成员或成员模板可以嵌套在许多层外围类模板中。对这样的成员做显式特化时，**每一层被显式特化的外围类模板**都要有一个 `template<>`：

```cpp
template<class T1> class A {
    template<class T2> class B {
        void mf();
    };
};
template<> template<> class A<int>::B<double>;          // 两层都特化：两个 template<>
template<> template<> void A<char>::B<char>::mf();
```

¶16 在命名空间作用域中对类模板成员或成员模板的显式特化声明里，成员模板及其**一部分**外围类模板可以保持**未特化**——但**不能**在外围类模板未特化的情况下显式特化成员类模板。此时对未特化的层用 `template<形参列表>` 代替 `template<>`，形参类型必须与主模板定义中的一致。

```cpp
template<class T1> class A {
    template<class T2> class B {
        template<class T3> void mf1(T3);
        void mf2();
    };
};
template<> template<class X>
    class A<int>::B {                                   // 特化 A<int>，B 仍是模板
        template<class T> void mf1(T);
    };
template<> template<> template<class T>
    void A<int>::B<double>::mf1(T t) { }                // 特化 A<int> 和 B<double>，mf1 仍是模板
template<class Y> template<>
    void A<Y>::B<double>::mf2() { }                     // error: B<double> 被特化，但外围的 A 没有
```

最后一行的禁令：`A<Y>` 是未知的特化，它的成员 `B` 可能被某个 `A` 的显式特化改得面目全非（甚至不存在），"对所有 `Y` 特化 `A<Y>::B<double>`"是无意义的。

¶17 未特化的类模板的成员函数模板、成员类模板、静态数据成员模板的特化，**本身仍是模板**（上例中 `template<> template<class X1> void A<int>::g1(int, X1);` 就是一个模板）。

## 杂项禁令（¶18–¶19）

¶18 显式特化声明**不能是友元声明**：

```cpp error
template<class T> struct S { };
struct F { template<> friend struct S<int>; };   // error
```

（友元声明**可以指名**一个函数模板的特化，如 `friend void f<>(int);`，但那不是显式特化**声明**——它引用一个已存在的特化。）

¶19 以下显式特化的声明或定义中**不能指定默认函数实参**：

- ¶19.1 函数模板的显式特化；
- ¶19.2 成员函数模板的显式特化；
- ¶19.3 类模板成员函数的显式特化，若该成员函数特化所属的类模板特化是**隐式实例化**的。

```cpp error
template<class T> void f(T, int = 0) { }
template<> void f(char, int = 1) { }    // error: 不能有默认实参
```

原因：默认实参属于**模板**（调用时从模板的声明中取得），重载决议在选中模板之后才看特化——若允许特化提供不同的默认实参，同一个调用 `f(c)` 的含义就会取决于特化是否可见。注 5：**显式特化的类**的成员函数（如前面 `A<int>::f`）可以有默认实参——那是普通类的普通成员函数。

## 访问检查

[[temp.spec#6]]：显式特化**声明**中的名字（模板实参、函数声明符中的类型）不做访问检查（C++20 起，[[P0692R1]]），但类特化的成员规格与函数体照常检查。

## 实现视角

!!! impl "特化的符号与链接"
    - 函数模板显式特化的 mangled name 与对应隐式实例化**相同**（`f<int>` 就是 `_Z1fIiEvT_`），两者在链接时是"同一个符号"。这正是 ¶7 违规跨 TU 时不报错的原因：一个 TU 输出弱定义（隐式实例化），另一个 TU 输出强定义（显式特化）；链接器通常选强定义，但内联或常量折叠后的调用点可能早已用了主模板的版本，造成"同一函数两种行为"。
    - 显式特化的函数不是 inline 时输出强符号，多个 TU 定义 → 链接错误 "duplicate symbol"。

!!! history "历史与演进"
    | 版本 | 变化 |
    |---|---|
    | C++98 | 显式特化、¶8 的打油诗已存在 |
    | C++14 | 变量模板的显式特化 |
    | C++17 | [[CWG727]]：可以在类作用域内显式特化（主模板可定义的任何作用域） |
    | C++20 | [[P0692R1]]：特化声明中的私有名不做访问检查；`constinit`、`consteval` 也不从模板继承 |
    | C++26 | 函数契约说明符不从模板继承（¶12） |

## 陷阱

!!! pitfall "特化函数模板，而不是重载"
    见 ¶11 的 Dimov/Abrahams 例子。首选重载；需要"部分特化函数模板"时，转发给类模板。

!!! pitfall "`std` 命名空间中的函数模板特化"
    C++20 起，用户为标准库**函数模板**提供显式特化是未定义行为（[[namespace.std]]）；为标准库**类模板**（如 `std::hash`、`std::formatter`）特化仍然允许（满足条件时）。所以 `template<> void std::swap(MyType&, MyType&)` 是错的——写一个同命名空间的 `swap` 重载，靠 ADL 找到它。

!!! pitfall "特化之前的隐式使用可能很隐蔽"
    "使用"不一定是显式调用：`sizeof(X<int>)`、作为基类、作为数据成员类型、在另一个模板的实例化中间接用到……都会导致隐式实例化。把显式特化紧贴主模板放置，是避免此类问题的唯一可靠办法。

## 思考题

!!! question "思考题 1"
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

输出 `b`。显式写了 `f<int*>`：`T = int*`，在 (a) 中得到 `f(int*)`，在 (b) 中得到 `f(int**)`——只有 (a) 的类型匹配，所以 (c) 是 (a) 的特化。调用 `f(&x)` 时偏序选中更特殊的 (b)（`T = int`），(b) 的 `f<int>` 没有被特化，输出 `b`。把特化写成 `template<> void f<int>(int*)` 或 `template<> void f(int*)`（此时 (a)(b) 都可见，偏序选 (b)）才会输出 `c`。
</details>

!!! question "思考题 2"
    `a.h` 中定义了 `template<class T> int size_of() { return sizeof(T); }`。`b.cpp` 调用 `size_of<Foo>()`；`c.cpp` 中写了 `template<> int size_of<Foo>() { return -1; }` 并调用它。程序的行为是什么？

<details markdown="1">
<summary>答案</summary>

违反 ¶7：`b.cpp` 中对 `size_of<Foo>` 的使用会导致隐式实例化，但特化的声明在 `b.cpp` 中不可达——{{ifndr}}。实践中，`b.cpp` 输出的是 `size_of<Foo>` 的弱定义（或直接内联成 `sizeof(Foo)`），`c.cpp` 输出强定义。链接器会选强定义，但 `b.cpp` 中被内联的调用不受影响，于是不同优化级别下 `b.cpp` 看到的值可能不同。修正：把特化的声明（至少是声明）放进 `a.h` 或 `Foo` 的头文件。
</details>

!!! question "思考题 3"
    为什么 ¶12 规定 `constexpr` 不从模板继承，而不是"默认继承、可以显式去掉"？

<details markdown="1">
<summary>答案</summary>

显式特化是一个**独立的定义**，与主模板的函数体毫无关系（¶6 对类也是这么说的）。`constexpr` 是对**函数体**的承诺（能在常量求值中执行），主模板的函数体满足这个承诺，不代表特化的函数体也满足。如果自动继承，就会出现"声明为 constexpr 却根本不能常量求值的函数"，而且无法从特化本身的声明看出来。`inline` 同理：它影响 ODR，是一个关于**这份定义**如何在多个 TU 中出现的声明，必须由写定义的人决定。语言也没有"取消 constexpr/inline"的语法，所以只能"不继承"。
</details>

## 小结

| 规则 | 段落 | 后果 |
|---|---|---|
| 可特化：函数/类/变量模板，类模板的各类成员，成员模板 | ¶1 | — |
| 不能 export、不能带存储类（`thread_local` 除外） | ¶2 | {{ill-formed}} |
| 可在主模板可定义的任何作用域声明（含类作用域） | ¶3 | — |
| 主模板声明须可达；成员模板特化须类定义可达 | ¶4–¶5 | {{ill-formed}} |
| 显式特化类的成员不从模板生成，按普通类定义（不写 `template<>`） | ¶6 | — |
| 特化声明须在每个会引起隐式实例化的使用之前可达 | ¶7 | {{ifndr}} |
| 被使用（或为虚函数）的特化必须有定义 | ¶7 | {{ifndr}} |
| 位置很重要（打油诗） | ¶8 | 注释性 |
| 同类型的非模板函数不是特化 | ¶11 | 与模板构成重载 |
| inline/constexpr/constinit/consteval/属性/契约不继承 | ¶12 | 头文件中的特化需 `inline` |
| 静态数据成员特化：有初始化器才是定义 | ¶13 | — |
| 每层被特化的外围类模板一个 `template<>`；不能特化"未特化外围"中的成员类模板 | ¶15–¶16 | — |
| 不能是友元声明；不能有默认实参 | ¶18–¶19 | {{ill-formed}} |
