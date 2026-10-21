---
title: 第四卷 · 模板、推导与约束
summary: 25 道题，考查两阶段查找与待决名、IFNDR 的几种来源、模板实参推导与 SFINAE、偏序与特化、CTAD、概念的满足与包含、NTTP、折叠表达式和 if constexpr 的丢弃语句。
status: done
order: 4
related: temp.res, temp.dep, temp.point, temp.deduct, temp.func.order, temp.spec.partial, temp.expl.spec, over.match.class.deduct, temp.constr, temp.param, temp.variadic, stmt.if, topics/two-phase-lookup, topics/type-deduction, topics/concepts
tags: 考卷, 模板, 两阶段查找, 模板实参推导, SFINAE, CTAD, 概念, IFNDR
updated: 2026-10-20
---

!!! tldr
    - 范围：[[temp.res]]、[[temp.dep]]、[[temp.point]]、[[temp.deduct]]、[[temp.func.order]]、[[temp.spec.partial]]、[[temp.expl.spec]]、[[over.match.class.deduct]]、[[temp.alias]]、[[temp.constr]]、[[temp.param]]、[[temp.variadic]]、[[stmt.if]]。
    - 共 25 题：判定题 15 道、选择题 7 道、简答题 3 道，难度大致递增。非模板的查找与重载、初始化、常量求值以及 C++26 的包索引和反射各有单独的考卷。
    - 判定题按整个程序里最重的一项作答；IFNDR 的题目都能对应到一条写明"no diagnostic required"的段落。
    - 建议用时 75 分钟。先只凭代码和条文作答，再用编译器验证；IFNDR 的题目上，编译器报错与否都不能当作判定依据。

## 一、待决名、消歧义与无合法特化的模板

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

程序输出什么？

```cpp run
#include <cstdio>
int x = 42;
template<class T> struct B { int x = 0; };
template<class T> struct D : B<T> {
  int f() { return x; }
};
int main() { D<int> d; std::printf("%d\n", d.f()); }
```

- A. `0`
- B. `42`
- C. 程序非良构：`x` 有歧义
- D. 程序 IFNDR，输出不确定

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B，输出 `42`。**

1. `return x;` 里的 `x` 是无限定名，不在依赖调用里，也不是当前实例化的成员，所以它不是待决名。非待决名在模板定义处查找一次并就此绑定（[[temp.res.general#1]]）。
2. 定义处的类作用域查找只搜索非依赖基类（[[class.member.lookup#4]]）。`B<T>` 依赖于 `T`，是**依赖基类**（[[temp.dep.type#3]]），它的成员在定义处不可见。
3. 查找继续向外，找到全局的 `::x`。实例化 `D<int>` 时 `x` 不会重新查找，`B<int>::x` 没有机会参与，所以没有歧义，也没有 IFNDR。

选 A 的人默认实例化时会重新查找 `x`，但只有待决名才会这样。要访问基类成员，写 `this->x` 或 `B<T>::x`：这两种写法的查找上下文依赖于 `T`，名字因此成为待决名（[[temp.dep.type#5]] 第 5.2、5.4 项）。

```cpp run ok
#include <cstdio>
int x = 42;
template<class T> struct B { int x = 0; };
template<class T> struct D : B<T> {
  int f() { return this->x; }
};
int main() { D<int> d; std::printf("%d\n", d.f()); }   // 输出 0
```

详见 [[topics/two-phase-lookup]]。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

C++20 起，下列四处 `T::R`、`T::P`、`T::Ptr` 都没有写 `typename`。哪一处的 `T::R` 不会被当作类型？

```cpp
template<class T> struct S {
  T::R f(T::P p);              // (A) 类模板的成员声明
  using Ptr = T::Ptr;          // (D) 别名声明
};
template<class T> T::R g();    // (B) 命名空间作用域，返回类型
template<class T> void h(T::R);// (C) 命名空间作用域，形参类型
```

- A. (A)
- B. (B)
- C. (C)
- D. (D)

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

[[P0634R3]] 引入了**仅类型语境**（type-only context）：依赖的限定名出现在这些位置时，直接当作类型（[[temp.res.general#5]]）。逐项对照 [[temp.res.general#4]]：

- (A) 返回类型是成员声明的 *decl-specifier*（第 4.4.2 项），形参是成员声明里的 *parameter-declaration*（第 4.4.3 项）。
- (B) 是命名空间作用域里 *simple-declaration* 的 *decl-specifier*（第 4.4.1 项）。
- (D) 是 *defining-type-id*（第 4.3.2 项）。
- (C) 的形参不在列表里。第 4.4.4 项只覆盖 *declarator-id* 是限定名的函数声明，`h` 不是。

所以 (C) 按默认规则解析：`T::R` 是一个表达式，整句声明的是 `void` 类型的变量模板 `h`，用 `(T::R)` 初始化。`void` 变量不可能合法，这个变量模板没有任何合法特化，程序 IFNDR（[[temp.res.general#6]] 第 6.1 项）。[[temp.res.general#4]] 的例 5 就是这一行。Clang 在定义处直接报错 `variable has incomplete type 'void'`，IFNDR 允许这样做。

写成 `void h(typename T::R)`，或者在类外定义成员 `template<class T> void S<T>::h(T::R)`（*declarator-id* 是限定名），都能正确解释成函数模板。块作用域里的 `T::R x;` 也不在列表里，同样必须写 `typename`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。`f` 从未被调用。

```cpp run
template<class T> void f(T) {
  static_assert(false, "f must not be instantiated");
}
int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。**

1. [[dcl.pre#13]] 规定：如果 *static_assert-declaration* 的表达式是在模板定义的语境中求值的，这条声明不起作用。只有实例化时才会真正检查。
2. [[temp.res.general#6]] 第 6.1 项判断"有没有合法特化"时明确排除失败的 *static_assert-declaration*，所以不能说 `f` 没有合法特化。
3. `f` 没有被实例化，`static_assert` 从未失败，程序良构。

这条规则来自 [[P2593R1]]。在它之前，`static_assert(false)` 不依赖模板形参，任何特化都会失败，程序 IFNDR，这就是干扰项 `ifndr` 的来源。以前的变通写法是 `static_assert(sizeof(T) == 0)` 之类的依赖表达式。严格说这种写法同样没有任何有效特化，在旧规则下也是 IFNDR，只是编译器检查不出来。

一旦调用 `f(1)`，实例化时 `static_assert` 失败，程序非良构（[[dcl.pre#13]] 第 13.1 项）。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

判定整个程序。`f` 从未被调用。

```cpp run
template<class T> void f(T) {
  int a[-static_cast<int>(sizeof(T) / sizeof(T))];
  (void)a;
}
int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：IFNDR。**

1. 数组界必须是 `std::size_t` 类型的转换常量表达式，值大于零（[[dcl.array#1]]）。对任何能让 `sizeof(T)` 成立的 `T`，`sizeof(T) / sizeof(T)` 都是 1，界是 `-1`，转换成 `size_t` 是窄化转换，不是转换常量表达式；`sizeof(T)` 本身不成立时更是错误。
2. 所以这个函数模板没有任何合法特化，而且它从未被实例化。[[temp.res.general#6]] 第 6.1 项：程序非良构，不要求诊断。

Clang 不报任何诊断，这是 IFNDR 允许的。选 `ok` 的理由是"没有实例化就不检查"，但标准并没有这样承诺：没有合法特化的模板，即使从不实例化，程序也已经出错，只是编译器可以不说。

和上一题对比：那里唯一的问题是失败的 `static_assert`，被第 6.1 项明确排除；这里的问题是数组界，不在排除之列。

界写成 `-static_cast<int>(sizeof(T))` 就不一定了：`sizeof(T)` 超过 `INT_MAX` 时，转换成 `int` 会回绕（`int` 为 32 位时按模 2<sup>32</sup>）。在 64 位平台上取 `T = char[3000000000]`，界是正数 1294967296，Clang 实测接受 `f<char[3000000000]>(nullptr)`，模板于是有了合法特化。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

判定整个程序。

```cpp run
#include <cstdio>
namespace N {
  struct A {};
  int h(A, long) { return 1; }
}
template<class T> int g(T t) { return h(t, 0); }
int x = g(N::A{});
namespace N {
  int h(A, int) { return 2; }
}
int main() { std::printf("%d\n", x); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：IFNDR。**

1. `h(t, 0)` 的实参 `t` 是类型依赖的，所以这是依赖调用（[[temp.dep.general#2]] 第 2.2 项）。定义处的普通无限定查找找不到任何 `h`；实例化时在实例化语境里做 ADL，关联命名空间是 `N`（[[basic.lookup.argdep#4]]）。
2. `g<N::A>` 的**实例化点**（point of instantiation）有两个：紧跟在 `int x = g(N::A{});` 这条命名空间作用域声明之后（[[temp.point#1]]），以及翻译单元末尾（[[temp.point#7]] 第 7.1 项）。
3. 在第一个点，ADL 只能找到 `h(A, long)`，调用的是它；在 TU 末尾，`h(A, int)` 也可见，而且对 `0` 是精确匹配，会选中它。
4. 两个实例化点给出的含义不同，[[temp.point#7]]：程序非良构，不要求诊断。

实测 Clang 输出 `2`，因为 Clang 把函数模板的实例化推迟到 TU 末尾。别的实现可能输出 `1`，两种都不能当作标准保证的结果。把 `h(A, int)` 挪到模板定义之前，两个实例化点看到的就一样了，程序良构，输出 `2`。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

`B<T>` 是 `D<T>` 的依赖基类，`B<T>` 里有成员函数 `g`。在 `D<T>` 的成员函数里，下面四种写法分别会怎样查找 `g`？哪一种会抑制虚调用？哪一种在不实现两阶段查找的老编译器上能编译，在 Clang 上却不能？

```cpp
template<class T> struct D : B<T> {
  int a() { return g(); }          // (1)
  int b() { return this->g(); }    // (2)
  int c() { return B<T>::g(); }    // (3)
  using B<T>::g;                   // (4) 之后在成员函数里写 g()
};
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**参考答案：**

(1) `g()` 没有实参，不是依赖调用（[[temp.dep.general#2]]），所以 `g` 是非待决名，在定义处查找一次。依赖基类不被搜索（[[class.member.lookup#4]]），如果外层没有别的 `g`，查找失败，程序非良构；如果外层有 `::g`，就悄悄绑定到它（参见第 1 题）。不实现两阶段查找的老编译器会在实例化时再查，于是"能编译"，Clang 报 `use of undeclared identifier 'g'`。

(2) `this->g` 是类成员访问，查找上下文是当前实例化，它有依赖基类而定义处查不到 `g`，所以名字是待决的（[[temp.dep.type#5]] 第 5.4 项），实例化时在 `B<int>` 里找到。调用方式和普通成员调用一样，`g` 是虚函数时照常动态派发。

(3) `B<T>::g` 的查找上下文是依赖类型，名字是待决的（[[temp.dep.type#5]] 第 5.2 项），实例化时找到。但它是限定名调用，限定名调用不做虚派发（[[class.virtual#16]]），即使派生类覆盖了 `g`，调用的也是 `B<T>::g`。

(4) *using-declarator* 的 *nested-name-specifier* 依赖于 `T`，声明把 `B<T>::g` 引入 `D<T>` 的作用域。之后无限定的 `g()` 在定义处就能找到这个 using 声明，实例化时替换为 `B<int>` 里的声明（[[temp.res.general#1]] 注 1）。虚派发不受影响。

```cpp run ok
#include <cstdio>
template<class T> struct B {
  virtual int g() { return 1; }
  virtual ~B() = default;
};
template<class T> struct D : B<T> {
  int call_this() { return this->g(); }
  int call_qual() { return B<T>::g(); }
};
struct E : D<int> { int g() override { return 2; } };
int main() {
  E e;
  std::printf("%d %d\n", e.call_this(), e.call_qual());   // 输出 2 1
}
```

</details>
</div>

## 二、实参推导、SFINAE 与偏序

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。

```cpp run
template<class T> void f(T, T) {}
void g() {}
int main() { f(g, &g); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。**

1. 两个形参的类型 `T` 都不是引用。[[temp.deduct.call#2]] 第 2.2 项：实参 `A` 是函数类型时，推导用函数到指针转换之后的类型。
2. 第一个实参 `g` 的类型是 `void()`，推导时换成 `void(*)()`；第二个实参 `&g` 本来就是 `void(*)()`。两处都推出 `T = void(*)()`，没有冲突。

改成引用形参就不同了：形参是引用时不做退化，`T` 分别推成 `void()` 和 `void(*)()`，推导失败。

```cpp run error
template<class T> void f(const T&, const T&) {}
void g() {}
int main() { f(g, &g); }   // error: T 推出 void() 和 void(*)()
```

数组同理：`f(T, T)` 接受 `f("abc", "ab")`（都退化成 `const char*`），`f(const T&, const T&)` 则会推出 `char[4]` 和 `char[3]`，推导失败。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

下面五个调用里，哪些能推导成功？

```cpp
#include <cstddef>
#include <initializer_list>
#include <vector>
template<class T> void a(T);
template<class T> void b(std::initializer_list<T>);
template<class T, std::size_t N> void c(T (&&)[N]);
template<class T> void d(std::vector<T>);

void test() {
  a({1, 2});      // (1)
  b({1, 2});      // (2)
  b({});          // (3)
  c({1, 2, 3});   // (4)
  d({1, 2});      // (5)
}
```

- A. (2)(4)
- B. (2)(3)(4)
- C. (2)(4)(5)
- D. (1)(2)(4)(5)

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：A。**

[[temp.deduct.call#1]] 只为两种形参规定了从花括号列表推导：去掉引用和 cv 之后是 `std::initializer_list<P′>` 或 `P′[N]`，而且实参是**非空**列表。这时把每个元素当作一个单独的实参，推导 `P′`；`N` 是常量模板形参时由元素个数推出。其他情况下，花括号列表让该形参成为非推导语境（[[temp.deduct.type#5]] 第 5.9 项）。

- (1) 形参是 `T`，不是上述两种形式，`T` 推不出来，失败。
- (2) `T = int`，成功。
- (3) 列表是空的，第 1 段的特殊规则不适用，形参成为非推导语境，`T` 推不出来，失败。
- (4) `T (&&)[N]` 去掉引用后是 `T[N]`，推出 `T = int`、`N = 3`，成功。
- (5) `std::vector<T>` 虽然有初始化列表构造函数，但它不是 `initializer_list<P′>`，推导规则不看构造函数，失败。

选 C 的人以为 `vector<T>` 能"透过"它的构造函数推导。推导只做类型匹配，不做重载决议；要让 (5) 成立，得写 `d<int>({1, 2})`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
template<class T> struct W { using type = typename T::type; };
template<class T> int f(typename W<T>::type*) { return 1; }
template<class T> int f(...) { return 2; }
int main() { return f<int>(nullptr); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 对第一个 `f`，把显式实参 `T = int` 代入函数类型，要求 `W<int>::type`。查找类成员需要完整的类，于是 `W<int>` 被隐式实例化（[[temp.inst#2]]）。
2. 实例化 `W<int>` 时，成员别名 `typename int::type` 非良构。这个错误发生在类模板特化的实例化里，而不是 `f` 的函数类型本身。
3. [[temp.deduct.general#8]]：无效的类型和表达式只有出现在推导替换位置的**直接语境**（immediate context）里，才算推导失败；单独实例化的构造不属于直接语境，注 7 也说明实例化模板特化之类的副作用可能让程序非良构。所以这里不是 SFINAE，而是硬错误，第二个 `f` 没有机会被选中。

去掉 `W`，直接写 `typename T::type*`，`int::type` 就出现在 `f` 的函数类型里，属于直接语境，推导失败，调用落到 `f(...)`，返回 2：

```cpp run ok
template<class T> int f(typename T::type*) { return 1; }
template<class T> int f(...) { return 2; }
int main() { return f<int>(nullptr); }   // 返回 2
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

程序输出什么？

```cpp run
#include <cstdio>
template<class T> int f(T)        { return 1; }
template<class T> int f(T*)       { return 2; }
template<class T> int f(const T*) { return 3; }
int main() {
  int i = 0;
  const int* p = &i;
  std::printf("%d%d\n", f(p), f(&i));
}
```

- A. `33`
- B. `32`
- C. `22`
- D. 程序非良构：`f(&i)` 有歧义

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B，输出 `32`。**

`f(p)`，实参类型 `const int*`：三个模板分别推出 `T = const int*`、`T = const int`、`T = int`，全是精确匹配，交给偏序。用 #3 的变换类型 `const U*` 去推 #2 的 `T*`，得到 `T = const U`，成功；反过来用 `U*` 去推 `const T*` 失败。所以 #3 比 #2 更特化，#2 又比 #1 更特化（[[temp.deduct.partial#10]]、[[temp.func.order#2]]），选 #3。

`f(&i)`，实参类型 `int*`：#1 推出 `T = int*`、#2 推出 `T = int`，都是恒等转换；#3 推出 `T = int`，形参 `const int*` 需要限定转换。先比较转换序列：恒等转换是任何非恒等序列的真子序列，所以 #1、#2 都比 #3 好（[[over.ics.rank#3]] 第 3.2.1 项）。偏序只在转换序列分不出高下时才用（[[over.match.best.general#2]] 第 2.5 项），#3 在这一步之前就已经出局。剩下 #1 和 #2，#2 更特化，结果是 2。

选 A 的人把偏序放到了转换序列之前。偏序是平局决胜规则，不能推翻转换序列的比较结果。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
template<class T, class U> struct S { static constexpr int v = 0; };
template<class T>          struct S<T, T*>  { static constexpr int v = 1; };
template<class T, class U> struct S<T*, U*> { static constexpr int v = 2; };
int main() { return S<int*, int**>::v; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 匹配（[[temp.spec.partial.match#2]]）：第一个偏特化推出 `T = int*`，第二个推出 `T = int`、`U = int*`。两个都匹配。
2. 偏序（[[temp.spec.partial.order#1]]）：把两个偏特化改写成函数模板 `f(X<T, T*>)` 和 `f(X<T*, U*>)` 再比较。
   - 用 `X<A, A*>`（`A` 是合成的唯一类型）去推 `X<T*, U*>`：`T*` 对 `A` 推不出，失败。
   - 用 `X<B*, C*>` 去推 `X<T, T*>`：第一个位置得到 `T = B*`，第二个位置得到 `T = C`，冲突，失败。
3. 两个方向都失败，谁也不比谁更特化。[[temp.spec.partial.match#1]] 第 1.2 项：这时使用该模板有歧义，程序非良构。Clang 报 `ambiguous partial specializations`。

直观地说，`S<T, T*>` 要求第二个实参正好比第一个多一层指针，`S<T*, U*>` 要求两个实参都是指针，两个条件互不包含，所以没有更特化的一方。再加一个 `template<class T> struct S<T*, T**>`，它比两者都更特化，程序就良构了。

</details>
</div>

## 三、特化、别名模板与 CTAD

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。

```cpp run
#include <cstdio>
template<class T> using Ptr = T*;
template<class T> int f(Ptr<T>);
template<class T> int f(T*) { return 2; }
int main() { int i = 0; std::printf("%d\n", f(&i)); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，输出 `2`。**

1. 别名模板的特化等价于把实参代入后的类型（[[temp.alias#2]]），`Ptr<T>` 就是 `T*`。
2. 于是两条声明的形参类型、模板头都相同，它们对应（[[basic.scope.scope#4]] 第 4.5 项），声明的是同一个函数模板。第一条是声明，第二条是它的定义。
3. 调用时只有一个候选，`T = int`，输出 `2`。

把第一条也写成定义，就成了同一个函数模板定义两次，违反 [[basic.def.odr#2]]：

```cpp error
template<class T> using Ptr = T*;
template<class T> int f(Ptr<T>) { return 1; }
template<class T> int f(T*) { return 2; }   // error: redefinition of 'f'
```

干扰项是"两个重载、调用有歧义"。别名模板不产生新类型，也不产生新模板，它在声明匹配时完全透明。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

判定整个程序。

```cpp run
template<class T> int f(T) { return 0; }
int a = f(1);
template<> int f(int) { return 1; }
int main() { return a; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：IFNDR。**

1. `int a = f(1);` odr-use 了 `f<int>`，需要它的定义，于是隐式实例化（[[temp.inst#5]]）。
2. [[temp.expl.spec#7]]：如果一个模板被显式特化，那么在每个会引起隐式实例化的使用处，这个特化的声明都必须可达；违反时不要求诊断。这里显式特化写在使用之后，程序 IFNDR。

Clang 在同一个 TU 里能看出问题，报 `explicit specialization of 'f<int>' after instantiation`，IFNDR 允许诊断。使用和显式特化分在两个 TU 时，编译器通常无从发现，见第 25 题。

不是每一次提及都会引起实例化。如果之前只出现在 `decltype` 里，而返回类型是写明的，就不需要函数定义，后面再显式特化是合法的：

```cpp run ok
template<class T> int f(T) { return 0; }
using R = decltype(f(1));            // 不需要 f<int> 的定义
template<> int f(int) { return 1; }
int main() { return f(1); }
```

把返回类型改成 `auto`，`decltype(f(1))` 就需要推导返回类型，必须实例化定义（[[dcl.spec.auto.general#15]]），又回到 IFNDR。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
template<class T> struct Box { Box(T&&) {} };
int main() { int i = 0; Box b(i); (void)b; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 构造函数 `Box(T&&)` 生成隐式推导指引 `template<class T> Box(T&&) -> Box<T>`（[[over.match.class.deduct#1]] 第 1.1 项）。另有复制推导候选 `Box(Box<T>)`，实参 `int` 与它不匹配。
2. [[temp.deduct.call#3]] 对**转发引用**（forwarding reference）的定义排除了一种情况：在类模板实参推导中，代表类模板形参的 `T&&` 不是转发引用。所以左值实参不会让 `T` 推成 `int&`。
3. 按普通规则，`T` 推成 `int`，指引的形参是 `int&&`，不能绑定左值 `i`，指引不可行。没有可行的指引，推导失败。Clang 报 `no viable constructor or deduction guide`。

`T` 是构造函数所属类模板的形参，类型在实例化 `Box<int>` 时就固定了，`Box<int>::Box(int&&)` 只接受右值，CTAD 不该推出别的结果。写一条用户推导指引，指引自己的 `T` 就是转发引用：

```cpp run ok
template<class T> struct Box { Box(T&&) {} };
template<class T> Box(T&&) -> Box<T>;
int main() { int i = 0; Box b(i); (void)b; }   // Box<int&>，构造函数折叠为 Box(int&)
```

[[temp.deduct.call#3]] 的例 4 用 `A a{i, 0, ip};` 和 `A a2{i, ip};` 演示了同一件事。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

`v2`、`v3`、`v4` 的类型分别是什么？

```cpp run
#include <vector>
std::vector v1{1, 2};
std::vector v2{v1};
std::vector v3{v1, v1};
std::vector v4{v1.begin(), v1.end()};
int main() {}
```

- A. `vector<int>`、`vector<vector<int>>`、`vector<int>`
- B. `vector<int>`、`vector<vector<int>>`、`vector<vector<int>::iterator>`
- C. `vector<vector<int>>`、`vector<vector<int>>`、`vector<int>`
- D. `vector<vector<int>>`、`vector<vector<int>>`、`vector<vector<int>::iterator>`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

CTAD 把推导指引当作一个假想类的构造函数，按初始化的形式做重载决议（[[over.match.class.deduct#6]]）。花括号初始化走 [[over.match.list]] 的两阶段：先只看初始化列表构造函数，再看全部构造函数。

- `v2{v1}`：[[over.match.class.deduct#6]] 第 6.1 项规定，列表只有一个元素，且其类型是该类模板的特化（或派生自它）时，跳过第一阶段。第二阶段里，复制推导候选 `vector(vector<T, A>)`（第 1.3 项）推出 `vector<int>`，`initializer_list<T>` 形参对实参 `v1` 推导失败。结果是复制，不是包一层。
- `v3{v1, v1}`：两个元素，第 6.1 项不适用。第一阶段 `vector(initializer_list<T>, ...)` 推出 `T = vector<int>`，结果是 `vector<vector<int>>`。
- `v4{v1.begin(), v1.end()}`：同样两个元素，第一阶段里 `initializer_list<T>` 推出 `T = vector<int>::iterator`，可行，于是不进入第二阶段，迭代器对构造函数和标准库的迭代器推导指引都没有机会。

要得到 `vector<int>`，改用圆括号 `std::vector v4(v1.begin(), v1.end());`，这时只有第二阶段，选中迭代器区间的推导指引。

</details>
</div>

## 四、概念与约束

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

关于 `f(1)` 和 `g(1)`，下列说法哪个正确？

```cpp run
#include <concepts>
template<class T> concept Small = sizeof(T) <= 4;
template<class T> concept A = Small<T> && std::integral<T>;
template<class T> concept B = sizeof(T) <= 4 && std::integral<T>;
int f(Small auto) { return 1; }
int f(A auto)     { return 2; }
int g(Small auto) { return 1; }
int g(B auto)     { return 3; }
int main() { return f(1) + g(1); }
```

- A. `f(1)` 返回 2，`g(1)` 返回 3
- B. `f(1)` 返回 2，`g(1)` 有歧义，程序非良构
- C. `f(1)` 和 `g(1)` 都有歧义
- D. `f(1)` 和 `g(1)` 都返回 1

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

两个候选的转换序列相同，偏序推导两个方向都成功，模板形参列表等价（类型约束不计入形参的等价性，[[temp.over.link#6]]），于是按约束决胜：更受约束的模板更特化（[[temp.func.order#8]] 第 8.4 项）。关键是**包含**（subsumption）怎么判断。

1. 关联约束先**规范化**（[[temp.constr.decl#3]]）。规范化会展开概念：`Small<T>` 的范式就是 `Small` 定义里的那个原子约束 `sizeof(T) <= 4`（[[temp.constr.normal#1]] 第 1.4 项）。
2. 两个原子约束**相同**（identical），要求它们来自源码里**同一处**表达式，并且形参映射相同（[[temp.constr.atomic#2]]）。包含关系只比较相同的原子约束（[[temp.constr.order#1]] 第 1.2 项）。
3. `A<T>` 的范式是 `sizeof(T) <= 4`（来自 `Small` 的定义）∧ `std::integral` 的原子约束。它包含 `Small<T>` 的范式，`f(A auto)` 更受约束，`f(1)` 返回 2。
4. `B` 里的 `sizeof(T) <= 4` 是另一处源码，即使字面上一样，也和 `Small` 里的那一个不相同。`B` 和 `Small` 互不包含，`g(1)` 两个候选不分高下，调用非良构（[[over.match.best.general#3]]）。

Clang 在歧义错误之后给出提示：`similar constraint expressions not considered equivalent`。只按来源判断相同，是为了让编译器不必比较任意表达式是否等价。要复用一个条件并参与包含，就把它写成概念，再通过概念名引用。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
#include <concepts>
template<class T> concept Big = sizeof(T) > 4;
template<class T> int f(T) requires (!Big<T>) { return 1; }
template<class T> int f(T) requires (!Big<T>) && std::integral<T> { return 2; }
int main() { return f(1); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 规范化只拆开 `&&`、`||`、括号、概念名，以及 `&&`、`||` 的折叠表达式（[[temp.constr.normal#1]]）。`!Big<T>` 是一个逻辑非表达式，不属于这几种，按第 1.6 项整体成为一个原子约束，`Big` 不会被展开到它里面。
2. 两个声明里的 `!Big<T>` 是源码里的两处表达式，按 [[temp.constr.atomic#2]] 不是相同的原子约束。第二个 `f` 的约束 `(!Big<T>)₂ ∧ integral` 不包含第一个的 `(!Big<T>)₁`（[[temp.constr.order#1]]）。
3. 两个 `f` 都可行，谁也不比谁更受约束，偏序分不出（[[temp.func.order#8]] 第 8.5 项），调用有歧义，程序非良构（[[over.match.best.general#3]]）。

干扰项是"第二个多了一个条件，当然更受约束"。如果把否定包进一个概念，两处引用的就是概念定义里同一个原子约束：

```cpp run ok
#include <concepts>
template<class T> concept Big = sizeof(T) > 4;
template<class T> concept NotBig = !Big<T>;
template<class T> int f(T) requires NotBig<T> { return 1; }
template<class T> int f(T) requires NotBig<T> && std::integral<T> { return 2; }
int main() { return f(1); }   // 返回 2
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
struct S { void bar(); };
template<class T> concept HasFoo = requires(T t) { t.foo(); };
static_assert(!HasFoo<S>);
static_assert(!requires(S s) { s.foo(); });
int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 第一个 `static_assert`：`HasFoo<S>` 的原子约束是那个 *requires-expression*，检查满足时把 `S` 代入（[[temp.constr.atomic#3]]）。代入后 `t.foo()` 无效，按 [[expr.prim.req.general#5]]，*requires-expression* 的值为 `false`，不会让程序非良构。这一行成立。
2. 第二个 `static_assert`：*requires-expression* 不在任何模板化实体里，没有模板实参可以代入。"值为 false"这条规则只针对代入模板实参产生的无效表达式，这里的 `s.foo()` 就是一个普通的表达式，`S` 没有成员 `foo`，按普通规则非良构。[[expr.prim.req.general#5]] 的注 1 明确写了这一点。Clang 报 `no member named 'foo' in 'S'`。

*requires-expression* 只在代入模板实参时才把无效表达式变成 `false`。要在非模板代码里探测一个具体类型，得像第一行那样经过一个概念或模板。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
template<class T> requires (sizeof(T)) void f(T) {}
void f(int) {}
int main() { f(0); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 调用 `f(0)` 时，函数模板推出 `T = int`，随后检查关联约束是否满足（[[temp.deduct.general#5]]）。
2. 原子约束 `sizeof(T)` 代入后没有出现无效的类型或表达式，所以不是"不满足"。[[temp.constr.atomic#3]] 接着要求 E 是 **bool 类型**的常量表达式，这里没有上下文转换，`std::size_t` 不行，程序非良构。
3. 非模板的 `f(int)` 也是精确匹配，按 [[over.match.best.general#2]] 第 2.4 项本该胜出，但错误发生在为模板构造候选的过程中，轮不到比较。[[temp.constr.atomic#3]] 的例 3 是同一个情形。

Clang 在模板定义处就报 `atomic constraint must be of type 'bool'`，即使没有调用也一样。没有调用时，这个原子约束不可能有良构的满足检查，而且从未检查，程序按 [[temp.res.general#6]] 第 6.5 项 IFNDR，提前诊断是允许的。

和"代入失败"对比：`requires (T::value)` 对 `T = int` 代入时 `int::value` 无效，约束只是不满足，模板被排除，调用回落到其他重载。

```cpp run ok
template<class T> requires (T::value) void g(T) {}
void g(...) {}
int main() { g(0); }   // 调用 g(...)
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

`f(0)` 有歧义。解释原因，并在不改变 `IncDec` 含义的前提下改写它，使 `f(0)` 选中第二个重载。

```cpp run
template<class T> concept Inc    = requires(T t) { ++t; };
template<class T> concept IncDec = requires(T t) { ++t; --t; };
int f(Inc auto)    { return 1; }
int f(IncDec auto) { return 2; }
int main() { return f(0); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**参考答案：** 一个 *requires-expression* 整体是一个原子约束，规范化不会把它拆成一条条要求（[[temp.constr.normal#1]] 第 1.6 项，[[temp.constr.normal#3]] 的例 2 列出了 `requires (T x) { ++x; }` 作为原子约束的情形）。`Inc` 和 `IncDec` 各自只有一个原子约束，来自两处不同的表达式，不相同（[[temp.constr.atomic#2]]），所以互不包含。`int` 两个都满足，偏序分不出（[[temp.func.order#8]] 第 8.5 项），调用有歧义。

编译器不会去比较两个 *requires-expression* 的内容，看出 `{ ++t; }` 是 `{ ++t; --t; }` 的子集。改写的办法是让 `IncDec` 通过概念名复用 `Inc`：

```cpp run ok
template<class T> concept Inc    = requires(T t) { ++t; };
template<class T> concept IncDec = Inc<T> && requires(T t) { --t; };
int f(Inc auto)    { return 1; }
int f(IncDec auto) { return 2; }
int main() { return f(0); }   // 返回 2
```

现在 `IncDec<T>` 的范式是 `Inc` 里的那个原子约束 ∧ 新的 *requires-expression*，包含 `Inc<T>`（[[temp.constr.order#1]]）。满足 `IncDec` 的类型集合没有变。标准库的概念层级（如 `std::bidirectional_iterator` 用 `std::forward_iterator<I> && ...` 定义）就是这样写的。详见 [[topics/concepts]]。

</details>
</div>

## 五、NTTP、变参与 if constexpr

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
struct P { int x; mutable int y; };
template<P p> struct B {};
B<P{1, 2}> b;
int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 常量模板形参的类型必须是**结构类型**（structural type），或者含占位符（[[temp.param#11]]）。
2. 类类型要成为结构类型，所有基类和非静态数据成员都必须是 public 且非 mutable（[[temp.param#12]] 第 12.3.1 项）。`P::y` 是 mutable，`P` 不是结构类型，声明 `template<P p>` 本身就非良构。Clang 在这一行报 `type 'P' of non-type template parameter is not a structural type`。

模板形参对象是 const 的，并且按值区分特化（[[temp.param#13]]）。mutable 成员能在 const 对象上被修改，会破坏"同值即同一特化"的前提，所以被排除。

去掉 `mutable` 程序就良构。以下几种常被误判为非法，其实都可以：`template<double D>`（浮点是标量类型，第 12.1 项）、`template<auto V>` 配 `'x'`、`template<const int& R>` 配命名空间作用域的 `constexpr int k`。真正被禁止的是让引用或指针指向临时对象、字符串字面量这类对象（[[temp.arg.nontype#6]]）。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

下面四个函数模板分别按 `main` 里的方式调用。哪些会导致程序非良构？

```cpp
template<class... T> auto a(T... t) { return (t + ...); }
template<class... T> auto b(T... t) { return (t && ...); }
template<class... T> auto c(T... t) { return (..., t); }
template<class... T> auto d(T... t) { return (0 + ... + t * 2); }
int main() {
  a();
  b();
  c();
  d(1, 2);
}
```

- A. 只有 `a()`
- B. `a()` 和 `d`
- C. `a()`、`c()` 和 `d`
- D. 只有 `d`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

- `a()`：一元折叠的包为空时，只有 `&&`、`||`、`,` 有规定的值（[[temp.variadic#15]] 的表 20），其他运算符的实例化非良构。`+` 不在表里。
- `b()`：空的 `&&` 折叠得到 `true`。
- `c()`：空的 `,` 折叠得到 `void()`。`auto` 从 `return void();` 推出 `void`，而返回 `void` 的函数可以返回 `void` 类型的操作数（[[stmt.return#2]]），所以合法。
- `d`：折叠表达式两侧的操作数必须是 *cast-expression*（[[expr.prim.fold#1]] 的文法）。`t * 2` 是乘法表达式，不是 *cast-expression*，这是语法错误，和调用的实参无关。要写成 `(0 + ... + (t * 2))`。

选 C 的人以为空包的逗号折叠无效，或者以为 `auto` 推不出 `void`。选 A 的人把 `t * 2` 当成了普通表达式，但折叠表达式的文法刻意不让 `+` 和 `*` 混在操作数里，以免优先级产生歧义。Clang 对 `d` 报 `expression not permitted as operand of fold expression`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
#include <type_traits>
int main() {
  int i = 0;
  if constexpr (std::is_pointer_v<decltype(i)>) {
    return *i;
  }
  return i;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. 条件为 `false`，第一个子语句是**丢弃语句**（discarded statement）（[[stmt.if#2]]）。
2. 但 [[stmt.if#2]] 只说在实例化外围的模板化实体时，丢弃语句不被实例化。`main` 不是模板，没有实例化这一步，丢弃语句照常进行语义检查。丢弃在非模板代码里的效果是：其中的 odr-use 不要求实体有定义（注 1），其中的 `return` 不参与返回类型推导（[[dcl.spec.auto.general#4]]）。
3. `*i` 的操作数必须是指针（[[expr.unary.op#1]]），`int` 不行，程序非良构。

`if constexpr` 不是 `#if`。放进一个模板里，让条件依赖模板形参，丢弃分支才不会被实例化：

```cpp run ok
#include <type_traits>
int main() {
  auto get = [](auto v) {
    if constexpr (std::is_pointer_v<decltype(v)>) return *v;
    else return v;
  };
  int i = 0;
  return get(i) + get(&i);
}
```

泛型 lambda 的函数调用运算符是模板，`get(i)` 实例化时 `return *v;` 被丢弃，不被实例化。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。

```cpp run
auto f() {
  if constexpr (true) return 1;
  else return 2.0;
}
int main() { return f() - 1; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，`f` 的返回类型是 `int`。**

1. 丢弃语句的定义（[[stmt.if#2]]）不限于模板：条件为 `true` 时，`else` 分支就是丢弃语句，在非模板函数里也一样。
2. 返回类型从**非丢弃**的 `return` 语句推导（[[dcl.spec.auto.general#4]]）；要求各次推导一致的规则也只针对非丢弃的 `return` 语句（[[dcl.spec.auto.general#10]]）。只有 `return 1;` 参与推导，返回类型是 `int`。
3. `return 2.0;` 虽然被丢弃，仍然要通过语义检查（参见上一题）。它本身没有错误：`2.0` 是合法表达式，不参与推导，也就不和 `int` 冲突。

这一题和上一题是一对：丢弃语句在非模板代码里仍然要检查，但其中的 `return` 不参与推导。换成普通 `if`，两条 `return` 都参与推导，分别推出 `int` 和 `double`，程序非良构：

```cpp error
auto f() {
  if (true) return 1;
  else return 2.0;   // error: 'auto' 推出 double，之前推出 int
}
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

两个翻译单元都包含 `f.h`。判定这个程序，说明依据，并预测在常见的 Itanium ABI 实现（Clang、GCC）上分别用 `-O0` 和 `-O2` 编译链接时可能看到什么输出，为什么会不同。

```cpp title="f.h"
template<class T> int f(T) { return 1; }
```

```cpp title="tu1.cpp"
#include <cstdio>
#include "f.h"
int via_tu2();
int main() { std::printf("%d %d\n", f(0), via_tu2()); }
```

```cpp title="tu2.cpp"
#include "f.h"
template<> int f<int>(int) { return 2; }
int via_tu2() { return f(0); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**参考答案：IFNDR。**

`tu1.cpp` 调用 `f(0)`，引起 `f<int>` 的隐式实例化，但在这个 TU 里 `f<int>` 的显式特化声明不可达。[[temp.expl.spec#7]] 要求显式特化的声明在每个 TU 里、每个会引起隐式实例化的使用处都可达，否则不要求诊断。两个 TU 各自都没有可诊断的错误，所以编译器和链接器通常都不会报告。

实现上，`tu1.o` 里隐式实例化出的 `f<int>` 是弱符号（Mach-O 上的 `weak external`，ELF 上的 COMDAT/weak），`tu2.o` 里的显式特化是普通的强符号，两者的修饰名相同（`_Z1fIiEiT_`）。链接器遇到强符号和弱符号同名，选强符号，不报错。

- `-O0`：`tu1` 里的 `f(0)` 是一次真正的调用，链接后跳到 `tu2` 的显式特化，输出 `2 2`。
- `-O2`：`tu1` 里的 `f<int>` 被内联成常量 1，根本不再调用符号，输出 `1 2`。

本机 Clang 23 的实测结果正是如此：同一份源码，优化级别不同，输出就不同。这是 IFNDR 在实际中最常见的样子：没有诊断，结果取决于内联决策。修正方法是把显式特化的声明 `template<> int f<int>(int);` 放进 `f.h`，让每个使用处都看得到它。

</details>
</div>

## 题目与条款对照

| 题号 | 考查点 | 条款 |
|---|---|---|
| 1 | 依赖基类的成员不参与定义处的查找 | [[temp.res.general#1]]、[[class.member.lookup#4]]、[[temp.dep.type#3]] |
| 2 | 仅类型语境与可以省略 `typename` 的位置 | [[temp.res.general#4]]、[[temp.res.general#5]] |
| 3 | `static_assert(false)` 与 P2593 | [[dcl.pre#13]]、[[temp.res.general#6]] |
| 4 | 没有合法特化的模板 | [[temp.res.general#6]]、[[dcl.array#1]] |
| 5 | 多个实例化点含义不同 | [[temp.point#1]]、[[temp.point#7]]、[[temp.dep.general#2]] |
| 6 | 调用依赖基类成员的几种写法 | [[temp.dep.type#5]]、[[class.member.lookup#4]] |
| 7 | 推导时函数到指针的退化 | [[temp.deduct.call#2]] |
| 8 | 从花括号列表推导 | [[temp.deduct.call#1]]、[[temp.deduct.type#5]] |
| 9 | SFINAE 的直接语境 | [[temp.deduct.general#8]]、[[temp.inst#2]] |
| 10 | 函数模板偏序与转换序列的先后 | [[temp.deduct.partial#10]]、[[over.ics.rank#3]]、[[over.match.best.general#2]] |
| 11 | 类模板偏特化的歧义 | [[temp.spec.partial.match#1]]、[[temp.spec.partial.order#1]] |
| 12 | 别名模板在声明匹配中透明 | [[temp.alias#2]]、[[basic.scope.scope#4]]、[[basic.def.odr#2]] |
| 13 | 显式特化必须在使用前声明 | [[temp.expl.spec#7]]、[[temp.inst#5]] |
| 14 | CTAD 中 `T&&` 不是转发引用 | [[temp.deduct.call#3]]、[[over.match.class.deduct#1]] |
| 15 | CTAD 的复制推导与初始化列表 | [[over.match.class.deduct#6]]、[[over.match.list]] |
| 16 | 原子约束的相同性与包含 | [[temp.constr.normal#1]]、[[temp.constr.atomic#2]]、[[temp.constr.order#1]] |
| 17 | 否定是原子约束 | [[temp.constr.normal#1]]、[[temp.func.order#8]] |
| 18 | 模板外的 *requires-expression* | [[expr.prim.req.general#5]]、[[temp.constr.atomic#3]] |
| 19 | 原子约束必须是 bool | [[temp.constr.atomic#3]]、[[temp.deduct.general#5]] |
| 20 | *requires-expression* 整体是一个原子约束 | [[temp.constr.normal#1]]、[[temp.constr.order#1]] |
| 21 | 结构类型 | [[temp.param#11]]、[[temp.param#12]] |
| 22 | 空包折叠与折叠表达式的文法 | [[temp.variadic#15]]、[[expr.prim.fold#1]] |
| 23 | 非模板中的丢弃语句仍被检查 | [[stmt.if#2]]、[[expr.unary.op#1]] |
| 24 | 丢弃语句中的 `return` 不参与推导 | [[dcl.spec.auto.general#4]]、[[dcl.spec.auto.general#10]] |
| 25 | 跨 TU 的显式特化 | [[temp.expl.spec#7]] |
