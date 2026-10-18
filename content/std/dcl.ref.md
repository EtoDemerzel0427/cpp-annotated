---
title: 引用
summary: 引用声明符 `&` / `&&`：引用不是对象（不能有引用的引用、引用数组、指向引用的指针）、引用没有 cv、必须初始化的例外、绑定到空指针或错误类型对象的 UB、引用折叠与转发引用
status: draft
related: dcl.decl, dcl.ptr, dcl.init.ref, basic.lval, class.temporary, temp.deduct.call, expr.prim.id, expr.unary.op, topics/value-categories
tags: 引用, 引用折叠, 转发引用, UB
updated: 2026-10-17
---

引用是 C++ 相对 C 最早、也最基础的扩展之一。本节（[dcl.ref]）只规定引用**声明符**的含义和几条全局约束；引用如何**绑定**（直接绑定、临时量物化、生命周期延长）在 [[dcl.init.ref]]，引用相关的值类别在 [[basic.lval]] 与 [[topics/value-categories]]。

本节要回答的核心问题是："引用是什么？"标准的回答是一个**否定式**的定义：引用不是对象（[[intro.object]] 中对象的列表里没有它），它没有 cv、不一定占存储、不能取地址（`&r` 取的是被引用对象的地址）。注 1 说得最直白：引用可以被看作对象的一个**名字**。由此推出 ¶5 的一系列"不能"。

## 引用声明符（¶1）

¶1 在声明 `T D` 中，若 `D` 形如 `& attr(opt) D1` 或 `&& attr(opt) D1`，且 `T D1` 中 *declarator-id* 的类型是"*list* `T`"，则 `D` 中 *declarator-id* 的类型是"*list* 指向 `T` 的引用"。属性属于引用类型。

与指针声明符（[[dcl.ptr]]）不同，文法中 `&` 后面**不能跟 cv 限定符**。

!!! std
    Cv-qualified references are ill-formed except when the cv-qualifiers are introduced through the use of a *typedef-name* or *decltype-specifier*, in which case the cv-qualifiers are ignored.

    带 cv 的引用非良构，除非 cv 是通过类型别名或 `decltype` 引入的——那时 cv 被**忽略**。

```cpp title="ref-cv.cpp" error
int i;
int& const cr = i;      // error: 不能直接写带 cv 的引用

typedef int& A;
const A ar = i;         // OK：const 通过 typedef 作用在引用上，被忽略；ar 的类型是 int&
const A aref = 3;       // error: aref 的类型是 int&（不是 const int&），不能绑定到右值
```

最后一行是标准例 1：初学者常以为 `const A` 是 `const int&`，但 `const` 修饰的是 `A` 这个**引用类型**本身，而引用本身没有 cv，所以 `const` 被丢弃。为什么不直接报错？因为在模板中 `const T` 中的 `T` 可能被替换为引用类型，若报错，许多泛型代码都要特判引用。Clang 对此给出警告 `-Wignored-reference-qualifiers`。

¶1 最后一句：形成"指向 cv `void` 的引用"非良构。`void` 不是对象类型，没有可以"命名"的对象。

```cpp title="ref-void.cpp" error
extern void& vr;                            // error: 不能形成 void&
template<class T> T& deref(T* p) { return *p; }
void g(void* p) { deref(p); }               // error: 推导出 T = void，返回类型 void& 无效 ⇒ 替换失败，没有可行函数
```

## 左值引用与右值引用（¶2–3）

¶2 用 `&` 声明的是**左值引用**（lvalue reference），用 `&&` 声明的是**右值引用**（rvalue reference）。它们是**不同的类型**；除非另有说明，二者语义相同，统称"引用"。

"另有说明"的地方正是 C++11 移动语义的全部机关：

| 差异 | 条款 |
|---|---|
| 右值引用只能绑定到右值（以及函数左值）；非 const 左值引用只能绑定到左值 | [[dcl.init.ref]] |
| 重载决议中，右值实参优先绑定右值引用 | [[over.ics.rank]] |
| 返回右值引用的函数调用、转换为右值引用的表达式是 xvalue | [[basic.lval]] |
| 命名的右值引用变量本身是**左值** | [[expr.prim.id.unqual]] |

¶3（例）引用作为形参（按引用传递，修改实参）、作为返回值（`g(3) = 7` 赋值给数组元素）、引用到指针（`link*& p`，修改调用者的指针）。

```cpp title="ref-examples.cpp" ok
struct link { link* next; };
link* first;

void h(link*& p) {      // p 是"指向 link 的指针"的引用
    p->next = first;
    first = p;
    p = nullptr;        // 修改的是调用者的指针
}

int v[20];
int& g(int i) { return v[i]; }

int main() {
    link* q = new link;
    h(q);               // 之后 q == nullptr，first 指向原来的节点
    g(3) = 7;           // 给 v[3] 赋值
    bool ok = q == nullptr && v[3] == 7;
    delete first;
    return ok ? 0 : 1;
}
```

## 引用是否占存储：未指定（¶4）

¶4 引用是否需要存储是**未指定的**（unspecified）。

- 局部引用 `int& r = x;` 通常被优化成 `x` 的别名，不占任何存储；
- 引用类型的非静态数据成员、按引用捕获的 lambda 成员、无法内联的引用形参，在实践中都被实现为指针，占一个指针的大小。

```cpp title="ref-size.cpp" ok
struct R { int& r; };
static_assert(sizeof(R) == sizeof(void*));   // 主流实现上成立，但标准不保证
int main() { }
```

这条规则也是 ¶5 中"不能有指向引用的指针"的根源：如果引用不一定有存储，就没有可以指向的东西。

## 不能有的东西与必须初始化（¶5）

!!! std
    There shall be no references to references, no arrays of references, and no pointers to references.

    不能有引用的引用、引用的数组、指向引用的指针。

```cpp title="ref-no.cpp" error
int x;
int& && rr = x;     // error: 引用的引用（直接写出时；通过别名形成时会折叠，见 ¶7）
int& arr[2];        // error: 引用数组
int&* pr;           // error: 指向引用的指针
int& noinit;        // error: 引用必须初始化
```

想要"可重新绑定的引用"或"引用数组"，用指针或 `std::reference_wrapper<T>`（它是一个对象，内部存一个指针）。

¶5 后半：引用的声明**必须有初始化器**（[[dcl.init.ref]]），以下情形除外：

1. 带显式 `extern` 的声明（初始化在别处）；
2. 类定义内的类成员声明（由构造函数的成员初始化器或默认成员初始化器初始化）；
3. 形参或返回类型的声明（由调用初始化）。

```cpp title="ref-noinit-ok.cpp" ok
extern int& ext;                 // 1. extern：在别处定义
struct M {
    int& m;                      // 2. 类成员：由构造函数初始化
    M(int& x) : m(x) { }
};
int& pick(int& a, int&) { return a; }   // 3. 形参与返回类型
int g = 0;
int& ext = g;
int main() { M m(g); return pick(m.m, ext); }
```

## 未定义行为（¶6）

¶6 有三条 UB 规则。

**(a) 绑定到函数时类型不兼容。** 若转换后的初始化器是一个 glvalue，其类型与函数**定义**的类型不是"调用兼容"的（[[expr.call]]），则绑定是 UB。这通常是 `reinterpret_cast` 到错误的函数类型之后再绑定引用：

```cpp title="ref-fn-ub.cpp" ub
void f(int) { }
using F = void(long);
int main() {
    F& r = reinterpret_cast<F&>(f);   // UB: f 的类型 void(int) 与 void(long) 不调用兼容
    (void)r;
}
```

**(b) 绑定到对象时类型不可访问。** 若初始化器是一个 glvalue，而被绑定的对象**不能通过该 glvalue 的类型被访问**（type-accessible，[[basic.lval]] 的严格别名规则），则绑定本身就是 UB——不需要等到读写。

```cpp title="ref-alias-ub.cpp" ub
int main() {
    alignas(int) char x[sizeof(int)] = {};
    int& r = *reinterpret_cast<int*>(&x);   // UB: x 是 char 数组，不能通过 int 类型的 glvalue 访问
    (void)r;
}
```

注 2 说明：glvalue 指代的对象**可以**在其生命周期之外（[[basic.life]] 允许在有限的情况下绑定到生命周期外的对象，例如构造期间的成员）；但**空指针值或尾后指针不指向对象**，所以良定义的程序中引用不可能指向它们。这就是"**空引用**"不存在的规范依据：`*p` 中 `p` 为空时，解引用本身已经是 UB（[[expr.unary.op]]），得到的根本不是一个对象。

另外，引用不能直接绑定到**位域**（[[class.bit]]）：`const int&` 绑定到位域时，会物化一个临时量。

**(c) 在初始化之前求值引用。** 对引用的求值（[[expr.prim.id]]、[[expr.ref]]）若不发生在（happens after，[[intro.races]]）引用的初始化之后，行为未定义。

标准例 3 把三类都放在了一起：

```cpp title="ref-ub-std.cpp" ub
int &f(int&);
int &g();
extern int &ir3;
int *ip = 0;
int &ir1 = *ip;                 // UB: 空指针
int &ir2 = f(ir3);              // UB: ir3 尚未初始化（静态初始化顺序）
int &ir3 = g();
int &ir4 = f(ir4);              // UB: ir4 在自己的初始化器中被使用

char x alignas(int);
int &ir5 = *reinterpret_cast<int *>(&x);    // UB: 初始化器指代 char 对象
```

`ir2` 是"静态初始化顺序灾难"（[[basic.start]]）在引用上的体现：引用变量不能常量初始化时（`g()` 不是常量表达式），在动态初始化之前，它没有绑定任何东西——这时读它不会得到"零"，而是 UB。

UBSan 能抓到空引用绑定：

```cpp run title="null-ref.cpp" ub
#include <cstdio>
int* ip = nullptr;
int main() {
    int& r = *ip;                       // UB: -fsanitize=undefined 报告
    std::printf("%p\n", (void*)&r);     // "reference binding to null pointer of type 'int'"
}
```

!!! note "为什么不让编译器检查"
    `int& r = *p;` 的合法性取决于运行期的 `p`，编译器无法静态判断。把它定为 UB，意味着编译器可以**假设引用永不为空**：`if (&r == nullptr)` 可以被直接优化为 `false`（Clang 对此会给出 `-Wtautological-undefined-compare` 警告）。

## 引用折叠（¶7）

¶7 直接写 `int& &` 非良构，但通过 *typedef-name*、模板类型形参或 *decltype-specifier* 间接形成"引用的引用"是允许的，并按以下规则**折叠**（reference collapsing）：

设 `TR` 是指向 `T` 的引用（`T&` 或 `T&&`）：

| 试图形成 | 结果 |
|---|---|
| 左值引用 → cv `TR` | `T&` |
| 右值引用 → cv `TR` | `TR`（保持不变） |

记忆法：**只要有一个 `&`，结果就是 `&`；只有 `&& &&` 才得到 `&&`**。cv 在这里被忽略（¶1）。

```cpp title="collapse.cpp" ok
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

static_assert(std::is_same_v<decltype(r1), int&>);
static_assert(std::is_same_v<decltype(r3), int&>);
static_assert(std::is_same_v<decltype(r4), int&>);
static_assert(std::is_same_v<decltype(r5), int&&>);
static_assert(std::is_same_v<decltype(r7), int&>);
int main() { }
```

### 转发引用

引用折叠存在的主要理由是**完美转发**。[[temp.deduct.call#3]] 定义了**转发引用**（forwarding reference）：函数模板中"指向**无 cv** 的模板类型形参的右值引用"（`T&&`，且 `T` 不是类模板的形参——CTAD 中除外）。对它做模板实参推导时，若实参是左值，`T` 被推导为**左值引用类型** `U&`；然后形参类型 `T&&` = `U& &&` 按本节折叠为 `U&`。

```cpp title="forwarding.cpp" ok
#include <type_traits>
#include <utility>
#include <vector>

template<class T> void f(T&& t) {             // 转发引用
    if constexpr (std::is_lvalue_reference_v<T>)
        static_assert(std::is_lvalue_reference_v<decltype(t)>);   // 左值实参：T = U&，形参 U&
    else
        static_assert(std::is_rvalue_reference_v<decltype(t)>);   // 右值实参：T = U，形参 U&&
}
template<class T> void g(const T&&) { }        // 不是转发引用：有 const
template<class T> void h(std::vector<T>&&) { } // 不是转发引用：不是 T&&
template<class T> struct W { void m(T&&) { } };// 不是转发引用：T 在调用时已确定，不推导

int main() {
    int i = 0;
    const int ci = 0;
    f(i);       // T = int&,       形参 int&
    f(ci);      // T = const int&, 形参 const int&
    f(1);       // T = int,        形参 int&&

    auto&& a = i;   // auto&& 同样是转发引用：int&
    auto&& b = 1;   // int&&
    static_assert(std::is_same_v<decltype(a), int&>);
    static_assert(std::is_same_v<decltype(b), int&&>);
    // g(i); h(v); W<int>{}.m(i);  都非良构：右值引用不能绑定左值
}
```

`std::forward<T>(t)` 的实现就是 `static_cast<T&&>(t)`：`T = U&` 时折叠为 `U&`（左值），`T = U` 时为 `U&&`（xvalue）——于是原始实参的值类别被"完美"地恢复。

¶8（注）形成指向"带 cv 或 ref 限定的函数类型"的引用非良构，见 [[dcl.fct#11]]。

## 实现视角

!!! impl
    - **ABI**：在 Itanium C++ ABI 中，引用形参与指针形参传递方式相同（传地址）；引用类型的数据成员布局与指针相同。名字修饰区分二者：`R` 表示左值引用，`O` 表示右值引用（如 `_Z1fRi` 是 `f(int&)`，`_Z1fOi` 是 `f(int&&)`）。
    - **优化**：编译器把引用视为"非空、已对齐、指向可解引用对象"的指针。Clang 在 LLVM IR 中给引用形参加上 `nonnull`、`dereferenceable(N)`、`align` 属性——这正是 ¶6 中 UB 规则带来的优化自由。
    - **诊断**：Clang 对 `int& r = f(r);` 给出 `-Wuninitialized` 警告（"reference 'r' is not yet bound to a value when used within its own initialization"）；`-fsanitize=null` 在运行时检查空引用绑定。

## 历史与演进

!!! history
    - **C++98**：只有左值引用；`const T&` 可以绑定临时量（[[dcl.init.ref]]）。引用的引用在任何情况下都非良构，模板中 `T&` 遇到 `T = int&` 就直接出错，这让 `std::bind1st` 等适配器无法处理接受引用形参的函数对象。
    - **C++11**：右值引用 `&&` 与移动语义（[[N2118]] 等系列提案）；完整的引用折叠规则；转发引用（当时称为"universal reference"，标准术语"forwarding reference"在 C++17 时正式采用）。
    - **C++23 之后的新措辞**：¶6 用"调用兼容"（call-compatible）和"类型可访问"（type-accessible）精确描述绑定时的 UB，取代了以前"引用必须绑定到有效的对象或函数"这种模糊的表述。

## 陷阱

!!! pitfall "`const T&` 中 T 为引用"
    `template<class T> void f(const T& x)`，若 `T` 被显式指定为 `int&`，形参类型是 `int&`——不是 `const int&`。`const` 加在引用上被忽略，然后折叠。这在 `std::function<void(const T&)>` 一类代码中会导致意外的可修改性。

!!! pitfall "命名的右值引用是左值"
    `void f(std::string&& s) { g(s); }` 调用的是 `g(const std::string&)` 或 `g(std::string&)`，不是 `g(std::string&&)`。要继续转移，写 `g(std::move(s))`。

!!! pitfall "返回局部变量的引用"
    `int& f() { int x; return x; }` 良构（编译器会警告），调用者拿到的引用立即悬垂，任何使用都是 UB（[[basic.life]]）。C++26 起，返回绑定到临时量的引用是非良构的（[[stmt.return]]）。

!!! pitfall "`auto&&` 不是右值引用"
    `auto&& x = expr;` 是转发引用，`x` 的类型取决于 `expr` 的值类别。range-for 的 `for (auto&& e : r)` 正是利用这一点同时处理返回引用和返回值的迭代器。

## 思考题

!!! question "思考题 1"
    设 `template<class T> using Ref = T&;`，下面各声明中变量的类型是什么？
    ```cpp
    int i;
    Ref<int&&> a = i;
    Ref<const int>&& b = i;
    const Ref<int> c = i;
    decltype((i))&& d = i;
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：`Ref<int&&>` 是"左值引用 → `int&&`"，折叠为 `int&`。
- `b`：`Ref<const int>` 是 `const int&`，再加 `&&` 折叠为 `const int&`。
- `c`：`Ref<int>` 是 `int&`；`const` 通过别名加在引用上，被忽略，类型 `int&`。
- `d`：`decltype((i))` 是 `int&`（带括号的 id 表达式是左值），加 `&&` 折叠为 `int&`。
</details>

!!! question "思考题 2"
    `int* p = nullptr; int& r = *p;` 是 UB。那么 `sizeof(*p)` 和 `decltype(*p) x = r;` 呢？

<details markdown="1">
<summary>答案</summary>

`sizeof(*p)` 中 `*p` 是未求值操作数（[[expr.sizeof]]），不进行解引用，良定义，结果是 `sizeof(int)`。`decltype(*p)` 也是未求值操作数，得到 `int&`，良定义；`decltype(*p) x = r;` 是否 UB 取决于 `r`——若 `r` 就是上面那个 `int& r = *p;`，UB 早在 `r` 初始化时就已发生。
</details>

!!! question "思考题 3"
    为什么标准允许通过 typedef 形成的 `const` 引用（忽略 cv），却不允许直接写 `int& const`？

<details markdown="1">
<summary>答案</summary>

直接写 `int& const` 时，程序员明确在给引用加 cv，这必然是误解（以为引用可以"重新绑定"，或想要 `const int&`），报错能及时纠正。而通过 typedef、模板形参或 `decltype` 引入时，cv 和引用往往来自代码的不同部分（泛型代码写 `const T`，使用者传入 `int&`），若报错，所有泛型代码都要对引用类型特殊处理。忽略 cv 让 `const T` 在 `T` 为引用时退化为 `T`，与"引用本身不可重新绑定，天然就是 const 的"这一语义一致。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 本质 | 引用不是对象，是对象/函数的别名；是否占存储未指定 |
    | 两种引用 | `&` 左值引用、`&&` 右值引用，是不同类型；差异体现在绑定、重载、值类别 |
    | cv | 直接写非良构；通过别名/`decltype` 引入则忽略 |
    | 不能有 | 引用的引用（直接写）、引用数组、指向引用的指针、`void&` |
    | 必须初始化 | 除 `extern`、类成员、形参/返回类型 |
    | UB | 函数类型不调用兼容、对象类型不可访问、空指针/尾后指针、在初始化前求值 |
    | 引用折叠 | 有 `&` 则 `&`，`&& &&` 才 `&&`；只在别名/模板/`decltype` 中发生 |
    | 转发引用 | 函数模板的 `T&&`（`T` 无 cv、被推导）与 `auto&&`；左值实参推导出 `T = U&` |
