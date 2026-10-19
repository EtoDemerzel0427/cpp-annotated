---
title: 隐式实例化
summary: 编译器何时自动从模板生成定义：类模板特化在需要完整类型时实例化，且只生成成员的声明；成员函数、静态数据成员、默认实参、noexcept 说明符各自按需实例化；常量求值或确定类型需要时也算需要；实现不得多实例化，无限递归实例化是未定义行为。
status: done
covers: temp.inst
papers: P0859R0, P0692R1
related: temp.spec, temp.explicit, temp.expl.spec, temp.point, temp.res, temp.decls, basic.def.odr, expr.const, stmt.if, topics/compile-time-programming
tags: 模板, 实例化, 惰性实例化, 完整类型, constexpr
updated: 2026-10-19
---

!!! tldr
    - 类模板特化只在需要完整类型时才实例化。指针、引用、类型别名、非定义的声明都不触发。
    - 类实例化时只生成成员的声明。成员函数体、静态数据成员的初始化器等到真正用到时才生成，所以类模板可以有只对部分实参合法的成员。
    - 静态数据成员没有被使用，它的初始化和副作用就不会发生，模板里的自动注册因此常常失效。
    - 常量求值或确定表达式类型需要某个函数或变量的定义时，即使它没有被 odr-use，也会实例化。
    - 虚函数是否被实例化是未指定的，实践中几乎总会实例化。无限递归实例化是未定义行为。

## 只生成用到的部分

```cpp run ok
template<class T>
struct C {
  void f() { T x; }   // T 是 void 时这行非良构
  void g() { }
};

C<void> c;            // OK
int main() { c.g(); }
```

`C<void>::f` 的函数体里有 `void x;`，但只要没有人调用 `f`，程序就是良构的。编译器实例化 `C<void>` 时只生成 `f` 的声明，函数体留到需要时再生成。这就是**隐式实例化**（implicit instantiation，[[g:implicit-instantiation]]）的惰性：编译器在用到一个特化时自动生成它的定义，而且只生成用到的部分。

`std::vector<T>::resize(n)` 要求 `T` 可默认构造，不可默认构造的 `T` 照样能使用 `vector<T>` 的其余成员，依据就在这里。实例化在源代码的哪个位置发生，由 [[temp.point]] 规定；本节规定是否发生。

本节的规则大多以"除非它是已声明的特化"开头。**已声明的特化**（declared specialization，[[g:declared-specialization]]）指定义另有来源的特化，比如程序员写了显式特化，或者用 `template class X<int>;` 指定在别处生成（[[temp.spec]]）。这时编译器不应该自己再生成一份。¶1 的精确定义见本页末尾一节。

## 类模板特化何时实例化（¶2）

¶2 类模板特化在两种情况下隐式实例化：被引用于需要完整定义的对象类型的语境；或者类类型是否完整会影响程序的语义。

第一种很直观：定义变量、`sizeof`、访问成员、`new`、作为基类、指针算术，都需要完整类型。第二种更隐蔽，注 2 举了两个例子：`delete p` 的语义取决于类有没有声明析构函数，`D*` 到 `B*` 的转换取决于继承关系。

```cpp run ok title="needs_complete.cpp"
template<class T> class B { };
template<class T> class D : public B<T> { };

void f(void*);
void f(B<int>*);

void g(D<int>* p, D<char>* pp, D<double>* ppp) {
  f(p);              // 实例化 D<int>，才知道能转为 B<int>*
  B<char>* q = pp;   // 实例化 D<char>，才知道是派生到基类的转换
  delete ppp;        // 实例化 D<double>
  (void)q;
}
```

下面这些用法都不需要完整类型，不会实例化：

<div class="compare" markdown="1">

```cpp run ok
template<class T> struct Bad {
  static_assert(sizeof(T) == 0);
};
Bad<int>* p = nullptr;
void take(Bad<int>&);
using U = Bad<int>;
extern Bad<int> obj;
int main() {}
```

```cpp run error
template<class T> struct Bad {
  static_assert(sizeof(T) == 0);
};
Bad<int>* p = nullptr;
auto n = sizeof(*p);
// error: 实例化 Bad<int>，
// static_assert 失败
int main() {}
```

</div>

¶2 最后规定：如果为这个特化选中的模板（主模板或某个部分特化，[[temp.spec.partial.match]]）在实例化点只有声明、没有定义，实例化的结果是不完整类型。

```cpp error
template<class T> class X;
X<char> ch;   // error: X<char> 是不完整类型
```

`std::tuple_size` 这类 trait 正是利用这一点：主模板不定义，未特化的实参得到不完整类型，可以被 SFINAE 检测到。

## 类实例化时生成什么（¶3）

¶3 类模板特化的隐式实例化：

- ¶3.1 对非删除的成员函数、成员类、有作用域的成员枚举、静态数据成员、成员模板和友元，只实例化声明，不实例化定义；
- ¶3.2 对删除的成员函数、无作用域的成员枚举和成员匿名联合，实例化定义。

第二类的定义无法推迟：删除函数的定义就是 `= delete`；无作用域枚举的枚举项和匿名联合的成员都会成为外围类的成员，不实例化定义，就不知道类里有哪些名字。

所以下面的显式特化是重定义：

```cpp error
template<class T>
struct C {
  void g() = delete;
};
C<int> c;                        // g 的定义 = delete 随类实例化
template<> void C<int>::g() { }  // error: 重定义 C<int>::g
```

!!! impl "Clang 的偏差"
    本机 Clang 23 接受这段代码，没有报重定义。按 ¶3.2 它是非良构的。

### 对应定义的声明视同定义

¶3 后半规定，在按 [[basic.def.odr]] 和 [[class.mem]] 判断重声明是否合法时，实例化出的声明如果对应模板中的一个定义，就视同定义。惰性只是推迟生成函数体，不等于没有定义。

最常见的后果出现在类模板里定义的友元函数上：

```cpp error
template<typename T> struct Friendly {
  template<typename U> friend int f(U) { return sizeof(T); }
};
Friendly<char> fc;
Friendly<float> ff;   // error: f(U) 的第二个定义
```

每个 `Friendly<X>` 都在外围命名空间声明同一个函数模板 `f`，每次都视同定义，两次实例化就是两次定义。让友元的签名依赖于 `T`，例如 `friend int f(Friendly<T>)`，每个特化定义的就是不同的函数。

例 4 的前半段把同一原理用在成员类模板的部分特化上：

```cpp error
template<class T, class U>
struct Outer {
  template<class X, class Y> struct Inner;
  template<class Y> struct Inner<T, Y>;       // #1a
  template<class Y> struct Inner<T, Y> { };   // #1b：#1a 的合法重声明
  template<class Y> struct Inner<U, Y> { };   // #2
};
Outer<int, int> outer;   // error at #2
```

`T`、`U` 都是 `int` 时，#2 与 #1b 成了同一个部分特化 `Inner<int, Y>` 的两个定义。

## 成员、函数、变量何时实例化（¶4–¶7）

¶4 模板化类的成员，在被引用于需要成员定义存在的语境，或者定义的存在会影响程序语义时，才隐式实例化。特别地，静态数据成员的初始化（及其副作用）不会发生，除非这个静态数据成员本身以需要其定义的方式被使用。

模板里的自动注册失效，原因就是这一句：

```cpp run ok title="autoreg.cpp"
#include <cstdio>
int reg(const char* n) { std::printf("registered %s\n", n); return 0; }

template<class T> struct AutoReg {
  static inline int token = reg(T::name);
};

struct Foo : AutoReg<Foo> {
  static constexpr const char* name = "Foo";
};
struct Bar : AutoReg<Bar> {
  static constexpr const char* name = "Bar";
  static constexpr auto* force = &token;   // 使用 token
};

int main() { std::puts("main"); }
// 输出：
// registered Bar
// main
```

`AutoReg<Foo>` 作为基类被实例化了，但那只生成了 `token` 的声明。没有人使用 `token`，它的定义和初始化器就不会实例化，`reg` 不会被调用。`Bar` 取了 `&token`，强制了实例化。换成非模板类，`static inline int token = reg(...)` 一定会初始化；把非模板版本改写成 CRTP 版本后注册失效，就是这个原因。

¶5 函数模板特化同理：在需要函数定义存在、或定义的存在影响语义时实例化。从类内友元函数定义实例化出声明的函数也一样。需要函数定义存在，基本就是 **odr-use**（[[basic.def.odr]]：调用、取地址等需要实体有定义的使用）。只出现在 `sizeof`、`decltype` 这类不求值操作数里时，通常只需要声明。

¶6 的例 5 把这些规则放在一起：

```cpp ok
template<class T> struct Z {
  void f();
  void g();
};

void h() {
  Z<int> a;      // 实例化类 Z<int>
  Z<char>* p;    // 不实例化 Z<char>
  Z<double>* q;  // 不实例化 Z<double>

  a.f();         // 实例化 Z<int>::f()
  p->g();        // 实例化类 Z<char> 和 Z<char>::g()
}
```

`Z<double>`、`Z<int>::g()`、`Z<char>::f()` 都没有被实例化。（`f`、`g` 没有定义，链接会失败，但这与实例化无关。）

¶7 变量模板特化的规则与函数相同。变量模板的默认模板实参，只在需要它的值时才实例化。

## 常量求值和类型推导也需要定义（¶8–¶9）

### 为常量求值所需（¶8）

```cpp error title="needed_for_ce.cpp"
template<typename T> constexpr int f() { return T::value; }

template<bool B, typename T> void g(decltype(B ? f<T>() : 0));
template<bool B, typename T> void g(...);
template<bool B, typename T> void h(decltype(int{B ? f<T>() : 0}));
template<bool B, typename T> void h(...);

void x() {
  g<false, int>(0);   // OK
  h<false, int>(0);   // error: 实例化了 f<int>，int::value 非良构
}
```

¶8 一个变量或函数如果被某个表达式**为常量求值所需**（needed for constant evaluation，[[expr.const.defns]]），就认为它的定义的存在影响程序语义。即使这个表达式并不要求常量求值，或者常量求值实际上用不到这个定义，也是如此。

`h` 的形参类型里有列表初始化 `int{…}`。判断它是否窄化（[[dcl.init.list]]）要看源表达式是不是常量表达式、值是多少，于是 `B ? f<T>() : 0` 成了潜在常量求值的表达式，`f<int>` 必须实例化。即使 `B` 是 `false`，即使 `int` 到 `int` 根本不可能窄化，也一样。`f<int>` 函数体里的错误不在推导的直接语境中（[[temp.deduct]]），所以是硬错误，不会让这个重载被 SFINAE 丢弃。

`g` 里的 `decltype` 只关心类型，`f<T>()` 的类型从声明就知道是 `int`，不需要实例化定义。

C++17 及以前，constexpr 函数何时被实例化没有明确规定，编译器行为不一。C++20 的 [[P0859R0]] 引入潜在常量求值和为常量求值所需这两个概念，形成了 ¶8。

### 为确定类型所需（¶9）

```cpp
template<typename T> struct X {
  static inline int arr[] = {1, 2, T::error};
};
decltype(+X<int>::arr) r;    // error: 为补全 arr 的类型实例化了定义

template<typename T> struct X2 {
  static inline int arr[3] = {1, 2, T::error};
};
decltype(+X2<int>::arr) r2;  // OK：类型已完整，arr 没有被 odr-use
```

¶9 如果确定程序中某个表达式的类型需要实例化，定义的存在也影响语义，即使变量或函数没有被 odr-use。`X<int>::arr` 声明的类型是 `int[]`，元素个数要从初始化器得出；`X2<int>::arr` 的类型已经完整。返回类型为 `auto` 的函数也一样：要知道 `decltype(f<int>())`，必须实例化 `f<int>` 的函数体。

!!! impl "Clang 的偏差"
    本机 Clang 23 接受 `decltype(+X<int>::arr) r;`，没有实例化 `arr` 的初始化器。按 ¶9 这是非良构的。

## 可以不实例化的情形（¶10–¶11）

```cpp ok
template <class T> struct S {
  operator int();
};

void f(int);
void f(S<int>&);
void f(S<float>);

void g(S<int>& sr) {
  f(sr);   // 允许但不要求实例化 S<int> 和 S<float>
}
```

¶10 如果不实例化某个类模板定义也能确定重载决议选中哪个函数，是否实际实例化是{{unspec}}的。`f(S<int>&)` 是精确匹配，引用绑定不需要看 `S<int>` 的内部；`f(S<float>)` 要实例化 `S<float>` 才知道有没有转换。编译器可以跳过，也可以照常实例化。所以如果 `S<float>` 的实例化本身会出错，这段代码在一些实现上能编译，在另一些上不能。

¶11 函数模板特化以涉及重载决议的方式被使用时，它的声明被隐式实例化（[[temp.over]]）。函数体此时不实例化，除非它最终被选中并被 odr-use。

## 实现不得多实例化（¶12）

¶12 实现不得隐式实例化函数模板、变量模板、成员模板、非虚成员函数、模板化类的成员类或静态数据成员，也不得实例化 constexpr if 语句未选中的子语句（[[stmt.if]]），除非确有需要。注 4 补充，泛型 lambda 所在的函数被实例化时，只要它的调用运算符模板没有被实例化，其中 constexpr if 的子语句也不会实例化。

这是给程序员的保证：类模板里可以写只对某些 `T` 合法的非虚成员，不用担心编译器把它们都生成出来。

虚函数是例外，是否实例化一个本来不会被实例化的虚成员函数，是未指定的。实现需要把虚函数的地址填进虚表，所以通常在类实例化时就实例化所有虚函数：

<div class="compare" markdown="1">

```cpp run ok
template<class T> struct W {
  void nv() { T::nope(); }
};
W<int> w;   // OK：nv 从不实例化
int main() {}
```

```cpp unspecified
template<class T> struct W {
  virtual void v() { T::nope(); }
};
W<int> w;
// 未指定；本机 Clang 23 实例化 v
// 并报错
```

</div>

¶12 还规定了默认实参和默认成员初始化器：在其中使用模板特化，不会仅因此实例化模板，除非为了判断它们本身是否正确必须实例化；只有在函数调用中真正用到默认实参，或者构造函数定义、聚合初始化中真正用到默认成员初始化器时，其中的特化才会实例化。

```cpp
template<class T> struct S {
  int m = T::value;     // 默认成员初始化器
  S(int) : m(0) {}      // 不用它
  S() {}                // 用它
};
S<int> a(1);   // OK：初始化器从未实例化
S<int> b;      // error: S() 用到了 m 的默认成员初始化器
```

## 默认实参和其他单独实例化的构造（¶13–¶16）

函数模板的默认实参、noexcept 说明符、函数契约说明符和函数体一样，是**单独实例化的构造**（[[temp.decls.general]]）：各自在需要时才实例化。

### 默认实参（¶14–¶15）

```cpp error
template<class T> void f(T x, T y = ydef(T()), T z = zdef(T()));

class A { };
A zdef(A);

void g(A a, A b, A c) {
  f(a, b, c);   // 不实例化任何默认实参
  f(a, b);      // 实例化 z 的默认实参：OK
  f(a);         // error: 实例化 y 的默认实参，ydef 未声明
}
```

¶14 调用模板化函数时用到了默认实参，编译器就实例化这个默认实参：查找其中的依赖名、检查语义约束、实例化其中用到的模板，如同它是同一作用域、同样模板形参、同样访问权限下的一个初始化器。这个过程叫**默认实参实例化**（default argument instantiation，[[g:default-argument-instantiation]]）。唯一的区别是，其中 lambda 的闭包类型声明在哪个作用域（因而关联命名空间是什么），仍由默认实参定义处决定。

¶15 每个默认实参独立实例化（注 6）。`ydef` 从未声明，但只要没有人用到 `y` 的默认实参，程序就是良构的。`ydef(T())` 是依赖调用，实例化时还会做 ADL（[[temp.dep.res]]）：如果在调用之前声明了 `A ydef(A)`，`f(a)` 就合法。

### noexcept 和契约说明符（¶16）

¶16 其余单独实例化的构造也只在需要时实例化，典型的是 noexcept 说明符（[[except.spec]]）和 {{c++26}} 函数契约说明符（[[dcl.contract.func]]）。实例化时的查找和检查，如同在那一点实例化特化的声明。

延迟实例化 noexcept 说明符很有用。类模板成员函数上的 `noexcept(noexcept(T(std::declval<T&&>())))` 如果随类一起实例化，会在 `T` 还不完整时过早出错。等到真的要知道它是否 noexcept 时（被调用、被 `noexcept` 运算符查询、检查虚函数覆盖）再实例化，就能支持 `std::vector<Incomplete>` 这样的用法。

### 局部类和非泛型 lambda 随外围函数实例化（¶13）

¶13 模板化函数 `F` 如果是局部类的成员（¶13.1），或者非泛型 lambda 的函数调用运算符（¶13.2），它的单独实例化构造在 `F` 的声明实例化时就跟着实例化。换句话说，外围函数模板的特化一实例化，局部类的成员函数体、非泛型 lambda 的函数体也就实例化了，即使从未被调用：

<div class="compare" markdown="1">

```cpp error
template<class T> void outer() {
  struct Local {
    void f() { T::nope(); }
  };
}
template void outer<int>();
// error
```

```cpp error
template<class T> void outer() {
  auto l = [] { T::nope(); };
  (void)l;
}
template void outer<int>();
// error：l 从未被调用
```

</div>

局部类和 lambda 无法在外围函数之外被引用，此时不实例化，就再也没有模板实参来触发它。注 5 说明，就实例化而言它们仍是与外围函数分开的构造，只是时机绑定在一起。泛型 lambda 的调用运算符是成员模板，函数体依赖自己的模板形参，仍然等到被调用时再实例化。

## 递归实例化（¶18）

```cpp error
template<class T> class X {
  X<T>* p;    // OK：指针不需要完整类型
  X<T*> a;    // X<T> 需要 X<T*>，X<T*> 又需要 X<T**>，……
};
X<int> x;
```

¶18 递归实例化的总深度有一个实现定义的上限，递归可以涉及多个模板。无限递归实例化是{{ub}}。附录 [[implimits]] 建议的上限至少是 1024。

本机 Clang 23 报 recursive template instantiation exceeded maximum depth of 1024，上限可以用 `-ftemplate-depth=N` 调整，GCC 有同名选项。标准把它定为 UB 而不是非良构，因为一般无法判定递归是否终止。实践中编译器都会在达到上限时报错。

深递归常见于递归实现的 tuple 或类型列表、每层一个特化的 constexpr 递归函数，以及终止条件写错的部分特化。C++17 的折叠表达式、C++26 的包索引 `Ts...[I]` 和展开语句，往往能把这类递归消掉。

## 约束不随特化实例化（¶19）

¶19 模板特化或成员函数的 *type-constraint* 和 *requires-clause* 不随特化或函数本身一起实例化，局部类的成员函数也是如此。判断约束是否满足、比较两个声明时，才按 [[temp.constr.decl]] 和 [[temp.constr.atomic]] 代入原子约束。注 8 指出，约束是否满足在模板实参推导和重载决议时判断。

```cpp error
template<typename T> concept C = sizeof(T) > 2;
template<typename T> concept D = C<T> && sizeof(T) > 4;

template<typename T> struct S {
  S() requires C<T> { }   // #1
  S() requires D<T> { }   // #2
};

S<char[8]> s2;   // OK：两个都满足，#2 约束更强
S<char> s1;      // error: 没有匹配的构造函数
```

`S<char>` 实例化时两个构造函数都是它的成员，只是约束不满足。它们仍然抑制了隐式默认构造函数的声明（[[class.default.ctor]]），所以 `s1` 没有可行的构造函数。

例 12 是约束上的 IFNDR（非良构、不要求诊断）：`requires false` 的成员类模板没有任何合法的特化，按 [[temp.res.general#6]] 程序 IFNDR。

## 已声明的特化（¶1）

¶1 特化 `E` 是已声明的特化，如果存在可达的、针对 `E` 的显式实例化定义或显式特化声明；或者存在可达的显式实例化声明（`extern template`），且 `E` 不是以下几种：

| 例外 | 为什么仍需隐式实例化 |
|---|---|
| ¶1.1 内联函数 | 为了内联展开（¶5 注 3） |
| ¶1.2 类型从初始化器或返回值推导的实体（`auto`） | 不实例化就不知道类型 |
| ¶1.3 潜在常量变量（[[expr.const.init]]） | 常量表达式要用它的值 |
| ¶1.4 模板化类的特化 | 类必须完整才能使用；`extern template` 只阻止生成成员的定义 |

¶5 的注 3 解释了第一项：对内联函数写 `extern template`，它仍然在 odr-use 时隐式实例化，函数体可以被内联，只是本翻译单元不输出它的外部副本。效果见 [[temp.explicit]] 的多翻译单元例子。

注 1 提醒：导入模块的翻译单元里发生的隐式实例化，不能使用被导入翻译单元中具有内部链接的名字（[[basic.link]]）。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶17 是一条注，指出实例化点由 [[temp.point]] 规定。

</details>

## 常见误解

!!! pitfall "能编译就说明所有成员都合法"
    成员函数只在被使用时才实例化。测试只用到 `push_back`，`resize` 里的错误就不会被发现。写库时可以在测试里用显式实例化定义 `template class MyVec<SomeType>;`，强制实例化所有已定义的成员（[[temp.explicit#9]]）。

!!! pitfall "`decltype` 和 `sizeof` 从不实例化"
    不求值操作数里的函数调用通常不实例化函数体。但返回类型是 `auto` 时，要实例化函数体才知道类型；表达式是潜在常量求值的，也要实例化（¶8）。这时函数体里的错误是硬错误。

## 思考题

!!! question "思考题 1"
    以下哪几行会让 `Big<int>` 隐式实例化？
    ```cpp
    template<class T> struct Big { T data[1000]; };
    Big<int>* a;                         // (1)
    Big<int>& f();                       // (2)
    auto g() -> Big<int>;                // (3)
    void h(Big<int>* p) { p = p + 1; }   // (4)
    bool b = std::is_class_v<Big<int>>;  // (5)
    ```

<details markdown="1">
<summary>答案</summary>

只有 (4)。(1)(2) 是指针和引用；(3) 是函数声明，返回类型只在函数定义和调用处才需要完整。(4) 指针算术要求指向完整的对象类型（[[expr.add]]）。(5) `std::is_class` 不要求完整类型，库通常用编译器内建实现，本机 Clang 23 + libc++ 不会实例化。在 `Big` 里放一个 `static_assert(sizeof(T) == 0)` 可以验证，只有 (4) 触发。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> struct A {
      static constexpr int v = T::value;
      int arr[2];
    };
    int n = sizeof(A<int>);
    ```
    这段代码良构吗？

<details markdown="1">
<summary>答案</summary>

良构。`sizeof(A<int>)` 实例化类 `A<int>`，按 ¶3.1 只生成静态数据成员 `v` 的声明，类内初始化器属于它的定义，不会代入 `T::value`。本机 Clang 23 接受。如果之后用到 `A<int>::v` 的值，初始化器就会实例化并报错。
</details>

!!! question "思考题 3"
    为什么非泛型 lambda 的函数体随外围函数实例化（¶13），泛型 lambda 却不是？

<details markdown="1">
<summary>答案</summary>

非泛型 lambda 的调用运算符是普通成员函数。外围函数特化实例化之后，它已经是具体的函数，以后再也没有模板实参来触发实例化，只能现在实例化。泛型 lambda 的调用运算符是成员模板，函数体依赖自己的 `auto` 形参，可以等到被调用时再实例化，适用 ¶12。不过，函数体里只依赖外围 `T` 的部分，代入 `T` 后已经是非依赖的，实现可以按 [[temp.res.general#6]] 提前诊断。
</details>
