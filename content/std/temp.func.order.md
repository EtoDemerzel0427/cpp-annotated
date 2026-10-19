---
title: 函数模板的偏序
summary: 多个函数模板都能为一次调用生成可行特化、转换序列又分不出高下时，编译器怎样判断哪个模板更特化，以及约束在什么条件下参与这一比较。
status: done
covers: temp.func.order
since: c++98
related: temp.deduct.partial, temp.deduct.type, over.match.best, temp.constr.order, temp.spec.partial, temp.over.link, over.match.oper, temp.fct, temp.variadic
tags: 模板, 偏序, 重载决议, 约束
updated: 2026-10-19
---

!!! tldr
    - 偏序判断两个函数模板谁更特化：把一个模板的形参换成合成的唯一类型，看另一个能否从中推导；只有一个方向成功，被推导出的一方更特化。
    - 偏序比较的是模板本身，不是实参。调用语境中只比较有实参对应的参数，带默认实参的参数、函数形参包和省略号不参与。
    - `f(T)` 与 `f(T&)` 永远歧义；对左值，`f(T&)` 比 `f(T&&)` 更特化；`f(const T&)` 比 `f(T&)` 更特化。
    - 约束只在双向推导都成功，并且两个模板除约束外完全对应时才参与比较，更受约束者更特化。
    - 在重载决议中，偏序排在比较转换序列和非模板优先之后，是靠后的平局裁决。

## 问题

```cpp run ok
template<class T> int f(T)  { return 1; }   // #1
template<class T> int f(T*) { return 2; }   // #2
int main() {
  int* p = nullptr;
  return f(p) - 2;   // 调用 #2
}
```

`#1` 推导出 `f<int*>(int*)`，`#2` 推导出 `f<int>(int*)`。两个特化的参数类型都是 `int*`，都是精确匹配，比较转换序列分不出高下。直觉上 `#2` 只接受指针，`#1` 什么都接受，`#2` 更具体，应当选它。[[g:partial-ordering|**偏序**]]（partial ordering）把这个直觉变成了一套算法。

叫偏序是因为它不是全序：两个模板可能互不更特化，例如 `f(T, int)` 与 `f(int, T)`，这时调用就是歧义的。

## 什么时候用偏序（¶1）

¶1 一个名字对应多个函数模板时，模板实参推导（[[temp.deduct]]）可能为不止一个模板找到特化。下面四种场合用偏序决定指的是哪个模板：

- ¶1.1 调用函数模板特化时的重载决议（[[over.match.best]]）；
- ¶1.2 取函数模板特化的地址（[[over.over]]）；
- ¶1.3 为 placement new 选择匹配的 placement 释放函数，而它是函数模板特化时（[[basic.stc.dynamic.deallocation]]、[[expr.new]]）；
- ¶1.4 友元声明、显式实例化或显式特化指向一个函数模板特化时。

在重载决议中，偏序排得很靠后：先比较隐式转换序列，再看是否非模板优于模板，最后才是偏序（[[over.match.best]]）。

¶1.4 容易被忽略。不写模板实参的显式特化，要靠推导加偏序决定它特化的是哪个模板：

```cpp run ok
template<class T> int f(T)  { return 1; }   // #1
template<class T> int f(T*) { return 2; }   // #2
template<> int f(int*) { return 5; }        // #1（T = int*）和 #2（T = int）都匹配，偏序选 #2
int main() { int x; return f(&x) - 5; }     // 调用 #2 的显式特化
```

## 算法

### 变换与双向推导（¶2–¶4）

¶2 偏序依次变换两个模板，并用函数类型做模板实参推导，以此判断谁更特化。如果双向推导都成功，再按约束选出更受约束的模板（见 ¶8）。

¶3 变换的做法是：对每个类型、常量、类型模板、变量模板或概念模板形参（包括形参包），分别合成一个唯一的类型、值、类模板、变量模板或概念，替换函数类型中这个形参的每一次出现。为常量形参合成的值，如果其类型里有占位符（如 `auto`），占位符也换成一个合成的唯一类型。¶4 合成的模板与对应的模板模板形参有相同的 *template-head*。

合成类型是唯一的，意思是它不等于任何其他类型。`T` 变换成 `U` 之后，用 `P = int` 去推导 `A = U` 就会失败，因为 `U` 不是 `int`。

比较模板 F 和 G 的步骤如下：

1. 变换 F，得到它的参数类型，作为实参 A。
2. 拿 G 原来的参数类型作为形参 P，从 A 推导 P（[[temp.deduct.partial]]）。成功就说 F **至少与 G 一样特化**。
3. 反过来，用变换后的 G 对 F 推导。
4. F 至少与 G 一样特化，而 G 不是至少与 F 一样特化，F 就**更特化**。
5. 双向都成功时，转到 ¶8 比较约束；双向都失败，或约束也分不出，两者互不更特化。

变换后的 F 可以看作 F 能接受的最一般的实参。G 能接受它，说明 G 的接受范围包含 F 的；反过来不成立，F 的接受范围就严格更小。

推导阶段不检查约束：合成类型 `U` 是否满足 `std::integral` 根本不会被问到。约束只在 ¶8 里单独比较，比的是约束之间的包含关系（[[temp.constr.order]]）。

### 推导的细节（¶6，[temp.deduct.partial]）

¶6 拿变换后的函数类型对另一个模板推导，细节在 [[temp.deduct.partial]]：

- **比较哪些类型**（[[temp.deduct.partial#3]]）：调用语境只用调用中有对应实参的那些参数（默认实参不算实参）；调用转换函数时用返回类型；其他语境，如取地址或显式特化，用整个函数类型。
- **预处理**（第 5–7 段）：P、A 是引用的，换成所引用的类型；如果两者原本都是引用，记下哪一边 cv 限定更多；然后去掉顶层 cv 限定。
- **推导**（第 8 段）：A 来自函数形参包而 P 不是包，推导失败。否则按 [[temp.deduct.type]] 推导，这里没有调用推导中允许的那些宽松处理。P 是函数形参包时，A 中剩下的每个参数类型都和包的元素类型比较。
- **引用的平局规则**（第 9 段）：某一对类型推导后相同，而 P、A 原本都是引用时：实参模板一侧是左值引用、形参模板一侧不是，就认定形参一侧不至少与实参一侧一样特化；否则，实参一侧 cv 限定更多时同样这样认定。
- **汇总**（第 10 段）：F 的每个类型都至少与 G 的对应类型一样特化，F 就至少与 G 一样特化。
- **尾随包**（第 11 段）：F、G 互相至少一样特化时，如果 G 有一个尾随函数形参包，F 在那个位置没有参数，F 本身也没有尾随包，F 更特化。
- **用不上的模板形参**（第 12 段）：模板形参没有推导出值也没关系，只要它没有出现在参与比较的类型中。

### 成员函数（¶5）

¶5 成员函数模板 M 被看作在参数列表最前面多了一个参数，类型记作 X(M)。设 M 是类 A 的成员，cv 限定为 cv：

- ¶5.1 如果 M 的引用限定符是 `&&`，或者 M 没有引用限定符而另一个变换后模板中对应位置的参数是右值引用，X(M) 是 cv A 的右值引用（如果这一判断递归地依赖 X(M) 本身，就不算右值引用）；
- ¶5.2 否则，X(M) 是 cv A 的左值引用。

注 1 说明，这样成员函数就能和非成员函数一起排序，结果与两个等价的非成员函数相同。另外，如果恰好一个模板是作为参数顺序反转的重写候选被考虑的（[[over.match.oper]]，例如 C++20 把 `a == b` 也当作 `b == a` 考虑），它变换后的参数顺序也要反过来。

```cpp run ok
struct A { };
template<class T> struct B {
  template<class R> int operator*(R&) { return 1; }           // #1
};
template<class T, class R> int operator*(T&, R&) { return 2; }  // #2

// 偏序时 #1 被看作 template<class R> int operator*(B<A>&, R&);   // #1a

int main() {
  A a;
  B<A> b;
  return (b * a) - 1;   // 调用 #1
}
```

| 方向 | 变换后作实参 | 对另一方推导 | 结果 |
|---|---|---|---|
| #1a 对 #2 | `(B<A>&, U&)` | `T&` 得 `T = B<A>`，`R&` 得 `R = U` | 成功 |
| #2 对 #1a | `(U1&, U2&)` | `B<A>&` 对 `U1&`：`U1` 不是 `B<A>` | 失败 |

#1 更特化。`B<A>` 中的 `A` 不是模板形参，所以不会被换成合成类型。

## 推演实例

### T、T*、const T*（¶6 例 2）

```cpp run ok
template<class T> int f(T)        { return 1; }
template<class T> int f(T*)       { return 2; }
template<class T> int f(const T*) { return 3; }
int main() {
  const int* p = nullptr;
  return f(p) - 3;   // 调用 f(const T*)
}
```

三个候选分别推导出 `T = const int*`、`T = const int`、`T = int`，参数类型都是 `const int*`，进入偏序：

| 变换后作实参 | 形参 | 推导 | 结论 |
|---|---|---|---|
| `T*` 变换成 `U*` | `T` | `T = U*` | `T*` 至少与 `T` 一样特化 |
| `T` 变换成 `U` | `T*` | `U` 不是指针 | 反之不成立 |
| `const T*` 变换成 `const U*` | `T*` | `T = const U` | `const T*` 至少与 `T*` 一样特化 |
| `T*` 变换成 `U*` | `const T*` | `U` 没有 const | 反之不成立 |

`f(T*)` 比 `f(T)` 更特化，`f(const T*)` 比两者都更特化。第四行说明偏序的推导是严格匹配：调用推导允许给实参加 const（[[temp.deduct.call]]），偏序不允许。

### T 与 T&：永远歧义

```cpp error
template<class T> void g(T);
template<class T> void g(T&);
void m() {
  float x;
  g(x);   // error: 歧义
}
```

`g(T&)` 变换成 `U&`，去掉引用后是 `U`，对 `g(T)` 的 `T` 推导成功。`g(T)` 变换成 `U`，对 `g(T&)` 去掉引用后的 `T` 推导也成功。双向成功，而引用的平局规则要求两边原本都是引用，这里只有一边是，不适用。没有约束可比，于是歧义。按值和按引用重载同一个函数模板总是这样。

### T& 与 const T&，T& 与 T&&

```cpp run ok
template<class T> int a(T&)       { return 1; }
template<class T> int a(const T&) { return 2; }
template<class T> int b(T&)       { return 1; }
template<class T> int b(T&&)      { return 2; }
int main() {
  const int ci = 0;
  int i = 0;
  return (a(ci) - 2) + (b(i) - 1);   // a(ci) 调用 a(const T&)，b(i) 调用 b(T&)
}
```

`a(ci)`：`a(T&)` 推导出 `T = const int`，`a(const T&)` 推导出 `T = int`，两者绑定的都是 `const int&`。偏序时去掉引用和顶层 cv 后，两个方向的推导都成功。但两边原本都是引用，平局规则生效：以 `const T&` 一侧为实参推导时，实参一侧 cv 限定更多，于是认定 `T&` 不至少与 `const T&` 一样特化。结果 `a(const T&)` 更特化。直观地看，`T&` 中的 `T` 可以吸收 const，模式更宽；`const T&` 把 const 写死在模式里，更具体。

`b(i)`：`b(T&)` 推导出 `T = int`，`b(T&&)` 是转发引用，推导出 `T = int&`，参数类型都是 `int&`。偏序时，以 `b(T&)` 一侧为实参推导，实参一侧是左值引用、形参一侧不是，于是认定 `T&&` 不至少与 `T&` 一样特化。所以 `b(T&)` 更特化。这条规则让转发引用重载和左值引用重载可以共存。

### 只比较有实参的参数（¶7）

¶7 是一条注：调用语境中只考虑有实参对应的参数，所以函数形参包、带默认实参的参数和省略号参数会被忽略。

```cpp run ok
template<class T> int f(T)           { return 1; }   // #1
template<class T> int f(T*, int = 1) { return 2; }   // #2
template<class T> int g(T)           { return 3; }   // #3
template<class T> int g(T*, ...)     { return 4; }   // #4

int main() {
  int* ip = nullptr;
  return (f(ip) - 2) + (g(ip) - 4);   // 调用 #2 和 #4
}
```

`f(ip)` 只有一个实参，偏序只比较第一个参数：`T*` 对 `T`，#2 更特化。带默认实参的第二个参数不参与。`g` 同理，省略号不参与。

忽略参数也可能导致歧义（例 4）：

```cpp error
template<class T, class U> struct A { };

template<class T, class U> void f(U, A<U, T>* p = 0);   // #1
template<         class U> void f(U, A<U, U>* p = 0);   // #2
template<class T         > void g(T, T = T());          // #3
template<class T, class... U> void g(T, U...);          // #4

void h() {
  f<int>(42, (A<int, int>*)0);   // OK: 调用 #2
  f<int>(42);                    // error: 歧义
  g(42);                         // error: 歧义
}
```

- `f<int>(42, (A<int, int>*)0)` 有两个实参，两个参数都参与比较。#2 变换成 `(U, A<U, U>*)`，对 #1 推导得 `U = U`、`T = U`，成功；#1 变换成 `(U2, A<U2, U1>*)`，对 #2 推导要求 `U` 既是 `U2` 又是 `U1`，失败。#2 更特化。
- `f<int>(42)` 只有一个实参，只比较第一个参数，两边都是 `U`，双向成功。#1 的 `T` 只出现在没有实参的参数里，可以没有值。转到 ¶8：两个模板的模板形参个数不同（2 对 1），按 ¶8.1 互不更特化，歧义。
- `g(42)` 中，#3 的第二个参数有默认实参，被忽略；#4 的包推导为空，也没有实参。双向成功。尾随包的平局规则要求 F 在 G 的尾随包处没有参数，而 #3 在那里有一个带默认实参的参数，不满足，歧义。

包的例子（例 5）：

```cpp run ok
template<class T, class... U> int f(T, U...)  { return 1; }   // #1
template<class T>             int f(T)        { return 2; }   // #2
template<class T, class... U> int g(T*, U...) { return 3; }   // #3
template<class T>             int g(T)        { return 4; }   // #4

int main() {
  int i;
  return (f(&i) - 2) + (g(&i) - 3);   // 调用 #2 和 #3
}
```

`f(&i)` 只比较第一个参数，`T` 对 `T`，双向成功。#1 有尾随包，#2 在那里没有参数，自己也没有包，所以 #2 更特化。`g(&i)` 中 `T*` 比 `T` 更特化，推导这一步就分出了胜负，包不影响结果。

### 变参模板之间

[[temp.deduct.partial#8]] 的例子：

```cpp run ok
template<class... Args>           int f(Args...)     { return 1; }   // #1
template<class T1, class... Args> int f(T1, Args...) { return 2; }   // #2
template<class T1, class T2>      int f(T1, T2)      { return 3; }   // #3

int main() {
  return (f() - 1) + (f(1, 2, 3) - 2) + (f(1, 2) - 3);
}
```

- `f()` 只有 #1 可行。
- `f(1, 2, 3)` 中 #1、#2 可行。#2 变换成 `(U1, Us...)`，对 #1 的 `Args...` 逐个比较，成功。#1 变换成 `(Us...)`，对 #2 的 `T1` 推导时，A 来自形参包而 P 不是包，失败。#2 更特化。
- `f(1, 2)` 中三个都可行。#3 对另外两个推导都成功，另外两个的变换中含有包，对 #3 的非包参数推导失败。#3 最特化。

一般结论：非变参的比变参的更特化，有固定前缀参数的变参模板比纯变参模板更特化。

### 只出现在返回类型里的形参

```cpp run ok
template<class T> T c(int) { return 1; }            // #1
template<class T, class U> T c(U) { return 2; }     // #2
int main() { return c<int>(1) - 1; }                // 调用 #1
```

调用语境只比较参数类型：#1 的 `int` 对 #2 的 `U`。#1 对 #2 推导得 `U = int`，成功；#2 的 `T` 只出现在返回类型中，没有值也无妨（[[temp.deduct.partial#12]]）。#2 变换后的 `U2` 对 #1 的 `int` 推导失败。#1 更特化。

## 约束作为平局裁决（¶8）{{c++20}}

```cpp run ok
#include <concepts>
template<class T>         int d(T) { return 1; }   // #1
template<std::integral T> int d(T) { return 2; }   // #2

int main() { return (d(1) - 2) + (d(1.0) - 1); }   // d(1) 选 #2；d(1.0) 只有 #1 可行
```

`d(1)` 时两个模板双向推导都成功，形参列表也一样，于是比较约束，更受约束的 #2 胜出。

¶8 规定了约束在什么条件下参与：

- ¶8.1 两个模板的模板形参列表（包括简写函数模板中发明的形参）或函数参数列表长度不同，互不更特化。
- ¶8.2.1 恰好一个模板是参数反转的重写候选时：如果任一模板有形参不能从函数参数推导，互不更特化；如果找不到、或者能找到不止一种模板形参的重排方式，使对应的模板形参等价、位置对应的函数参数类型相同，也互不更特化。
- ¶8.2.2 其他情况下，对应的模板形参不等价（[[temp.over.link]]），或位置对应的函数参数类型不同，互不更特化。
- ¶8.3 偏序发生在调用转换函数的语境中，而两个模板的返回类型不同，互不更特化。
- ¶8.4 否则，如果一个模板比另一个更受约束（[[temp.constr.order]]），它更特化。
- ¶8.5 否则，互不更特化。

总的意思是：只有两个模板除约束外完全对应时，才用约束裁决。原因在于约束的包含关系只有在两边的模板形参指同一个东西时才有意义。`template<std::integral T> void f(T)` 和 `template<class U> void f(U*)` 的 `T`、`U` 根本不对应，说前者更受约束没有意义。

¶8.1 的例子：

```cpp error
#include <concepts>
template<std::integral T> void r(T);
template<class T, class U = void> void r(T);   // 多了一个模板形参
void t() { r(1); }                             // error: 歧义，不比较约束
```

双向推导都成功（`U` 不在比较的类型中），但模板形参个数不同，¶8.1 直接判定互不更特化，尽管第一个看起来更受约束。

### 简写写法与普通写法可以对应（例 6 前半）

```cpp run ok
template<typename> constexpr bool True = true;
template<typename T> concept C = True<T>;

void f(C auto&, auto&) = delete;    // #1：相当于 template<C T1, class T2> void f(T1&, T2&)
template<C Q> void f(Q&, C auto&);  // #2：相当于 template<C Q, C T2> void f(Q&, T2&)

void g(struct A* ap, struct B* bp) {
  f(*ap, *bp);   // OK: 选 #2
}
int main() {}
```

两个模板都有两个模板形参、两个函数参数，位置一一对应，忽略约束后形参等价，于是比较约束。#2 的约束 `C<Q> ∧ C<T2>` 包含 #1 的 `C<T1>`，#2 更受约束，调用的是 #2 而不是被删除的 #1。一个用简写语法、一个写 *template-head*，并不妨碍它们对应。

### 反转候选的重排（例 6 后半）

```cpp
template<typename> constexpr bool True = true;
template<typename T> concept C = True<T>;
template<typename T, typename U> struct X { };

template<typename T, C U, typename V> bool operator==(X<T, U>, V) = delete;   // #1
template<C T, C U, C V>               bool operator==(T, X<U, V>);            // #2

void h() {
  X<void*, int>{} == 0;   // 标准：OK，选 #2
}
```

#1 正常匹配，`T = void*, U = int, V = int`。#2 只能以反转的形式 `0 == X<...>` 匹配，`T = int, U = void*, V = int`。反转后 #2 的参数是 `(X<U, V>, T)`，与 #1 的 `(X<T, U>, V)` 按位置对应，要求 #1 的 `[T, U, V]` 对上 #2 的 `[U, V, T]`。这样的重排恰好一种，忽略约束后形参等价，于是比较约束：#2 约束了全部三个形参，#1 只约束了 `U`，#2 更受约束。

!!! warning "编译器现状"
    本机 Clang 23 对这个例子报告重载决议选中了被删除的 `operator==`，也就是选了 #1，没有实现 ¶8.2.1 的重排对应规则。按标准应选 #2。

### 转换函数（¶8.3）

对转换函数调用做偏序时，比较的是返回类型（[[temp.deduct.partial#3]]）。¶8.3 进一步规定，两个转换函数模板的返回类型不同时，不用约束裁决：转换函数的目标类型不同，它们就不是同一个函数的不同约束版本。

## 部分特化复用这套规则

类模板和变量模板的部分特化比较谁更特化时（[[temp.spec.partial.order]]），把每个部分特化改写成只有一个参数的函数模板，然后原样使用本页的算法，比较的是整个函数类型。所以本页的推演方法同样适用于部分特化。

## 实现视角

!!! impl
    - 编译器实现偏序时，用一组不透明的特殊类型替换模板形参，然后复用推导引擎。不匹配任何具体类型，正是不透明类型的性质。
    - Clang 的歧义诊断会列出每个候选和它的推导结果（`candidate function [with T = ...]`），但不解释偏序为什么失败。要知道原因，需要按本页的表格自己推演。

## 历史与演进

!!! history
    - C++98 的偏序规则已经基本成型：变换、双向推导、引用和 cv 的处理。
    - C++11 的变参模板带来了函数形参包的规则（[[temp.deduct.partial]] 第 8、11 段）；右值引用带来了左值引用优先的平局规则；成员函数的 X(M) 开始考虑引用限定符。
    - C++20 让约束在双向推导都成功时参与裁决，并要求两个模板除约束外对应；`operator==` 的反转候选带来了 ¶5 的参数反转和 ¶8.2.1 的重排规则。
    - C++26 增加了变量模板模板形参和概念模板形参，¶3 相应地为它们合成唯一的变量模板和概念。

## 常见误解

!!! pitfall "偏序比较的是哪个特化更匹配实参"
    不是。偏序比较的是模板本身，与实际实参无关，实参只决定哪些参数参与比较。

!!! pitfall "`f(T&&)` 是右值引用，所以比 `f(T&)` 更特化"
    相反。对左值实参，`f(T&)` 更特化（[[temp.deduct.partial#9]]）。

!!! pitfall "带约束的版本总会胜出"
    只有两个模板除约束外完全对应时才比较约束。模板形参个数不同、参数类型不同，约束都不起作用（¶8.1、¶8.2.2）。

!!! pitfall "默认实参能让模板更特化"
    调用语境中，没有实参对应的参数，包括带默认实参的参数，根本不参与偏序。

## 思考题

!!! question "思考题 1"
    下面的调用选哪个？

    ```cpp
    template<class T> void p(T, int);    // #1
    template<class T> void p(int, T);    // #2
    p(1, 1);
    ```

<details markdown="1">
<summary>答案</summary>

歧义。两个模板都可行（`T = int`），参数类型都是 `(int, int)`。#1 变换成 `(U, int)`，对 #2 的 `(int, T)` 推导，第一位 `int` 对 `U` 失败。#2 变换成 `(int, U)`，对 #1 的 `(T, int)` 推导，第二位失败。双向都失败，互不更特化。每个模板都在一个位置上比另一个具体，没有一个全面胜出。本机 Clang 23 报告调用歧义。
</details>

!!! question "思考题 2"
    `template<class T> void f(T*)` 与 `template<class T> void f(const T*)`，为什么 `int* p; f(p);` 选前者，`const int* q; f(q);` 选后者？

<details markdown="1">
<summary>答案</summary>

`f(p)`：`f(T*)` 的参数是 `int*`，恒等转换；`f(const T*)` 的参数是 `const int*`，需要一次限定转换。按 [[over.ics.rank]]，恒等转换序列优于它，比较转换序列这一步就选出了 `f(T*)`，偏序没有出场。

`f(q)`：两者的参数类型都是 `const int*`，转换序列相同，进入偏序，`f(const T*)` 更特化。很多看似由偏序决定的选择，其实在比较转换序列时就已经定了。
</details>

!!! question "思考题 3"
    `template<class T> int f(T, T*)` 与 `template<class T, class U> int f(T, U*)`，`int i; f(i, &i)` 选哪个？如果把第二个换成 `template<class T, class U> requires std::same_as<T, U> int f(T, U*)` 呢？

<details markdown="1">
<summary>答案</summary>

第一种情况选第一个。第一个变换成 `(V, V*)`，对第二个推导得 `T = V, U = V`，成功；第二个变换成 `(V1, V2*)`，对第一个推导要求 `T` 既是 `V1` 又是 `V2`，失败。

第二种情况仍然选第一个。推导这一步不看约束，结果和之前一样，只有一个方向成功，约束没有机会参与；即使双向成功，两个模板的形参个数也不同，¶8.1 同样会让约束失效。约束不能把形状上更一般的模板变成更特化的。本机 Clang 23 的结果与此一致。
</details>
