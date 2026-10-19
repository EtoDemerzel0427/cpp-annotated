---
title: 引用
summary: 引用声明符 `&` 和 `&&` 的含义：引用不是对象，所以没有引用的引用、引用数组和指向引用的指针；引用不能带 cv；哪些引用可以不初始化；哪些绑定是未定义行为；以及引用折叠与转发引用。
status: draft
related: dcl.decl, dcl.ptr, dcl.init.ref, basic.lval, class.temporary, temp.deduct.call, expr.prim.id, expr.unary.op, topics/value-categories
tags: 引用, 引用折叠, 转发引用, UB
updated: 2026-10-19
---

!!! tldr
    - 引用可以看作对象或函数的另一个名字。它不是对象，是否占存储未指定，所以不能有引用的引用、引用数组和指向引用的指针。
    - 直接写 `int& const` 非良构；cv 经由别名或 `decltype` 加到引用上时被忽略，所以 `typedef int& A; const A` 仍是 `int&`。
    - 引用必须初始化，只有 `extern` 声明、类成员声明、形参和返回类型例外。
    - 把引用绑定到空指针解引用的结果、绑定到类型不符的对象，或者在引用初始化之前使用它，都是未定义行为。
    - 经由别名、模板形参或 `decltype` 形成的引用的引用会折叠：只要有一个 `&`，结果就是左值引用。转发引用 `T&&` 正是靠这条规则工作的。

引用怎样绑定到初始化器（直接绑定、临时量物化、生命期延长）见 [[dcl.init.ref]]；与引用相关的值类别见 [[basic.lval]] 和 [[topics/value-categories]]。

## 引用声明符（¶1–3）

```cpp run ok
struct link { link* next; };
link* first;

void h(link*& p) {     // p 是对指针的引用
  p->next = first;
  first = p;
  p = nullptr;         // 修改的是调用者的指针
}

int v[20];
int& g(int i) { return v[i]; }

int main() {
  link* q = new link;
  h(q);                // 之后 q 为空，first 指向原来的节点
  g(3) = 7;            // 给 v[3] 赋值
  bool ok = q == nullptr && v[3] == 7;
  delete first;
  return ok ? 0 : 1;
}
```

¶3 的例子展示了引用的三种典型用法：作形参让函数修改实参，作返回值让 `g(3) = 7` 赋值给数组元素，以及对指针的引用 `link*&` 让函数修改调用者的指针。

¶1 如果声明 `T D` 中的 `D` 形如 `& D1` 或 `&& D1`，名字的类型就是"`T` 的引用"，前面再加上内层声明符积累的修饰（见 [[dcl.decl]]）。`&` 后面可以有属性，属性属于引用类型。注 1 给出了理解引用的方式：引用可以看作对象的一个名字。

¶2 用 `&` 声明的是**左值引用**（[[g:lvalue-reference|lvalue reference]]），用 `&&` 声明的是**右值引用**（[[g:rvalue-reference|rvalue reference]]）。它们是不同的类型；除非另有说明，二者语义相同，统称引用。另有说明的地方就是 C++11 移动语义所依赖的规则：

| 差异 | 条款 |
|---|---|
| 右值引用只能绑定右值（和函数左值）；非 const 的左值引用只能绑定左值 | [[dcl.init.ref]] |
| 重载决议中，右值实参优先绑定到右值引用 | [[over.ics.rank]] |
| 返回右值引用的函数调用、转换为右值引用的表达式是 xvalue | [[basic.lval]] |
| 具名的右值引用变量本身是左值 | [[expr.prim.id.unqual]] |

!!! pitfall "具名的右值引用是左值"
    在 `void f(std::string&& s) { g(s); }` 中，`g(s)` 调用的是接受左值的重载，不是 `g(std::string&&)`。要继续移动，写 `g(std::move(s))`。

## 引用不能带 cv（¶1）

¶1 的文法里 `&` 后面不能写 cv 限定符，这一点和指针不同。

!!! std
    Cv-qualified references are ill-formed except when the cv-qualifiers are introduced through the use of a *typedef-name* or *decltype-specifier*, in which case the cv-qualifiers are ignored.

```cpp run error
int i;
int& const cr = i;   // error: 不能直接给引用加 cv

typedef int& A;
const A ar = i;      // OK：const 被忽略，ar 的类型是 int&
const A aref = 3;    // error: aref 是 int&，不能绑定右值
```

最后一行是标准例 1。常有人以为 `const A` 是 `const int&`，但 `const` 修饰的是 `A` 这个引用类型本身，而引用不能有 cv，所以 `const` 被丢弃。Clang 对此给出 `-Wignored-reference-qualifiers` 警告。

为什么经由别名时不报错？在模板里，`const T` 的 `T` 可能被替换成引用类型。如果这时报错，大量泛型代码都要对引用做特殊处理。引用本来就不能重新绑定，忽略 cv 与它的语义并不矛盾。直接写出 `int& const` 则几乎一定出于误解，报错可以及时纠正。

¶1 的最后一句规定，形成"cv `void` 的引用"非良构：

```cpp run error
template<class T> T& deref(T* p) { return *p; }
void g(void* p) { deref(p); }   // error: T 推导为 void，void& 无效，没有可行函数
```

¶8 是一条注：带 cv 或引用限定的函数类型（如 `void() const`）也不能形成引用，见 [[dcl.fct#11]]。

## 引用不是对象（¶4–5）

¶4 引用是否需要存储是未指定的。局部的 `int& r = x;` 通常被优化成 `x` 的别名，不占任何空间；引用类型的数据成员、按引用捕获的 lambda 成员、没有被内联的引用形参，在实践中都实现为指针。

```cpp run ok
struct R { int& r; };
static_assert(sizeof(R) == sizeof(void*));   // 主流实现上成立，标准不保证
int main() { }
```

既然引用不一定有存储，也不是对象，很多东西就无从谈起。

¶5 规定：

!!! std
    There shall be no references to references, no arrays of references, and no pointers to references.

```cpp run error
int x;
int& && rr = x;   // error: 引用的引用（直接写出时；经由别名会折叠，见下文）
int& arr[2];      // error: 引用数组
int&* pr;         // error: 指向引用的指针
int& noinit;      // error: 引用必须初始化
```

需要可以重新绑定的引用或者引用的数组时，用指针或 `std::reference_wrapper<T>`。后者是一个对象，内部存一个指针。

### 必须初始化，以及三个例外（¶5）

¶5 的后半规定，引用的声明必须带初始化器（[[dcl.init.ref]]），以下三种情况除外，它们都是在别处初始化：

```cpp run ok
extern int& ext;                         // 1. 显式 extern：在别处定义
struct M {
  int& m;                                // 2. 类定义中的成员：由构造函数初始化
  M(int& x) : m(x) { }
};
int& pick(int& a, int&) { return a; }    // 3. 形参和返回类型：由调用初始化
int g = 0;
int& ext = g;
int main() { M m(g); return pick(m.m, ext); }
```

## 绑定时的未定义行为（¶6）

¶6 一共有三条未定义行为。标准例 3 把它们放在一起：

```cpp
int &f(int&);
int &g();
extern int &ir3;
int *ip = 0;
int &ir1 = *ip;     // UB: 空指针
int &ir2 = f(ir3);  // UB: ir3 尚未初始化
int &ir3 = g();
int &ir4 = f(ir4);  // UB: ir4 在自己的初始化器中被使用

char x alignas(int);
int &ir5 = *reinterpret_cast<int *>(&x);   // UB: 初始化器指代的是 char 对象
```

### 绑定到类型不符的对象或函数

第一条：把引用绑定到函数时，如果初始化器（经过转换后）是一个 glvalue，它的类型与函数定义的类型不是调用兼容的（[[expr.call]]），行为未定义。典型做法是先 `reinterpret_cast` 成错误的函数类型：

```cpp run ub
void f(int) { }
using F = void(long);
int main() {
  F& r = reinterpret_cast<F&>(f);   // UB: void(int) 与 void(long) 不调用兼容
  (void)r;
}
```

第二条：把引用绑定到对象时，如果对象不能经由初始化器这个 glvalue 的类型访问（type-accessible，即严格别名规则，见 [[basic.lval]]），行为未定义。上面的 `ir5` 就是这种情况：`x` 是 `char` 对象，不能经由 `int` 类型的 glvalue 访问。注意，未定义行为发生在绑定的时候，不必等到读写。

### 没有空引用

注 2 说明，glvalue 指代的对象可以在生命期之外（[[basic.life]] 允许在一些情况下这样绑定，例如构造期间）。但空指针值和尾后指针根本不指向对象，所以在行为良好的程序里，引用不可能指向它们。

这就是没有空引用的依据。如果 `p` 为空，`*p` 本身已经是未定义行为（[[expr.unary.op]]），得到的根本不是一个对象。UBSan 可以在运行时抓到这种绑定：

```cpp run ub
#include <cstdio>
int* ip = nullptr;
int main() {
  int& r = *ip;                     // UB: 绑定到空指针解引用的结果
  std::printf("%p\n", (void*)&r);
}
```

用 `-fsanitize=undefined` 编译运行，报告 reference binding to null pointer of type 'int'。

因为这是未定义行为，编译器可以假设引用永远不为空。`if (&r == nullptr)` 可以直接优化为 `false`，Clang 对此给出 `-Wtautological-undefined-compare` 警告。注 2 还提到，引用不能直接绑定到位域（[[class.bit]]）；`const int&` 绑定位域时，绑定的是物化出来的临时量。

### 在初始化之前使用引用

第三条：如果对引用的求值不发生在它的初始化之后（happens after，[[intro.races]]），行为未定义。

例子里的 `ir4` 在自己的初始化器里使用了自己，Clang 给出 `-Wuninitialized` 警告（reference 'ir4' is not yet bound to a value when used within its own initialization）。`ir2` 是静态初始化顺序问题（[[basic.start]]）在引用上的体现：`ir3` 要用 `g()` 动态初始化，在那之前它没有绑定任何东西，这时使用它得到的不是零，而是未定义行为。

## 引用折叠（¶7）

直接写 `int& &` 非良构，但经由类型别名、模板类型形参或 `decltype` 间接形成的引用的引用是允许的，按**引用折叠**（[[g:reference-collapsing|reference collapsing]]）的规则得到一个引用：

```cpp run ok
#include <type_traits>
int i;
typedef int&  LRI;
typedef int&& RRI;

LRI& r1 = i;            // int&
const LRI& r2 = i;      // int&（const 被忽略）
const LRI&& r3 = i;     // int&
RRI& r4 = i;            // int&
RRI&& r5 = 5;           // int&&
decltype(r2)& r6 = i;   // int&
decltype(r2)&& r7 = i;  // int&

static_assert(std::is_same_v<decltype(r3), int&>);
static_assert(std::is_same_v<decltype(r5), int&&>);
static_assert(std::is_same_v<decltype(r7), int&>);
int main() { (void)r1; (void)r4; (void)r6; }
```

¶7 设别名或 `decltype` 表示的类型 `TR` 是 `T` 的引用（`T&` 或 `T&&`）。试图形成"cv `TR` 的左值引用"时，得到 `T&`；试图形成"cv `TR` 的右值引用"时，得到 `TR` 本身。两种情况下 cv 都被忽略。

| 别名 `TR` | 再加 `&` | 再加 `&&` |
|---|---|---|
| `T&` | `T&` | `T&` |
| `T&&` | `T&` | `T&&` |

可以这样记：只要有一个 `&`，结果就是 `&`；只有两个都是 `&&` 时才得到 `&&`。

### 转发引用

引用折叠的主要用途是完美转发。[[temp.deduct.call#3]] 定义了**转发引用**（[[g:forwarding-reference|forwarding reference]]）：函数模板形参中，指向无 cv 的模板类型形参的右值引用 `T&&`。类模板实参推导时，如果 `T` 是类模板自己的形参，`T&&` 不算转发引用。`auto&&` 也是转发引用。

推导时，如果实参是左值，`T` 推导为左值引用类型 `U&`，于是形参类型 `T&&` 就是 `U& &&`，折叠为 `U&`。实参是右值时，`T` 推导为 `U`，形参类型是 `U&&`。

```cpp run ok
#include <type_traits>

template<class T> void f(T&& t) {       // 转发引用
  if constexpr (std::is_lvalue_reference_v<T>)
    static_assert(std::is_lvalue_reference_v<decltype(t)>);
  else
    static_assert(std::is_rvalue_reference_v<decltype(t)>);
}
template<class T> void g(const T&&);    // 不是转发引用：有 const
template<class T> struct W {
  void m(T&&);                          // 不是转发引用：T 不在这里推导
};

int main() {
  int i = 0;
  const int ci = 0;
  f(i);       // T = int&，形参 int&
  f(ci);      // T = const int&，形参 const int&
  f(1);       // T = int，形参 int&&

  auto&& a = i;   // int&
  auto&& b = 1;   // int&&
  static_assert(std::is_same_v<decltype(a), int&>);
  static_assert(std::is_same_v<decltype(b), int&&>);
}
```

`std::forward<T>(t)` 的实现就是 `static_cast<T&&>(t)`。`T = U&` 时折叠为 `U&`，结果是左值；`T = U` 时是 `U&&`，结果是 xvalue。这样就还原了原始实参的值类别。range-for 常写的 `for (auto&& e : r)` 也利用了这一点，迭代器返回引用或返回值都能处理。

!!! pitfall "`const T&` 中的 `T` 是引用"
    对 `template<class T> void f(const T& x)`，如果显式指定 `T` 为 `int&`，形参类型是 `int&`，不是 `const int&`：`const` 加在引用上被忽略，然后发生折叠。本不该被修改的实参就变得可以修改了。

## 实现视角

!!! impl
    - Itanium C++ ABI 中，引用形参和指针形参的传递方式相同，都是传地址；引用类型的数据成员布局也与指针相同。名字修饰区分二者：左值引用记作 `R`，右值引用记作 `O`，例如 `_Z1hRi` 是 `h(int&)`，`_Z1hOi` 是 `h(int&&)`。
    - 编译器把引用当作非空、已对齐、可以解引用的指针。Clang 在 LLVM IR 中给引用形参加上 `nonnull`、`dereferenceable(N)`、`align` 属性，这正是第 6 段的未定义行为留出的优化空间。

## 历史与演进

!!! history
    - C++98 只有左值引用。引用的引用在任何情况下都非良构，模板里的 `T&` 遇到 `T = int&` 就出错，`std::bind1st` 这类适配器因此无法处理接受引用形参的函数对象。
    - C++11 加入了右值引用和移动语义（[[N2118]] 等提案）、完整的引用折叠规则，以及后来称为转发引用的推导规则。
    - C++23 之后的措辞用调用兼容和类型可访问精确描述第 6 段的未定义行为，取代了以前"引用必须绑定到有效的对象或函数"这种笼统的说法。
    - C++26 起，`return` 语句中把返回的引用绑定到临时量是非良构的（[[stmt.return]]）。

## 思考题

!!! question "思考题 1"
    设 `template<class T> using Ref = T&;`，下面各变量的类型是什么？
    ```cpp
    int i;
    Ref<int&&> a = i;
    Ref<const int>&& b = i;
    const Ref<int> c = i;
    decltype((i))&& d = i;
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：`Ref<int&&>` 是"`int&&` 的左值引用"，折叠为 `int&`。
- `b`：`Ref<const int>` 是 `const int&`，再加 `&&` 折叠为 `const int&`。
- `c`：`Ref<int>` 是 `int&`，`const` 经由别名加在引用上，被忽略，类型是 `int&`。
- `d`：带括号的名字 `(i)` 是左值，`decltype((i))` 是 `int&`，加 `&&` 折叠为 `int&`。
</details>

!!! question "思考题 2"
    `int* p = nullptr; int& r = *p;` 是未定义行为。那么 `sizeof(*p)` 和 `decltype(*p)` 呢？

<details markdown="1">
<summary>答案</summary>

两者都没有问题。`sizeof(*p)` 和 `decltype(*p)` 中的 `*p` 都是不求值操作数（[[expr.sizeof]]、[[dcl.type.decltype]]），不会真的解引用。前者的结果是 `sizeof(int)`，后者是类型 `int&`。
</details>
