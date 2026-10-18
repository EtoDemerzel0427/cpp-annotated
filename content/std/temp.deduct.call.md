---
title: 从函数调用推导模板实参
summary: 最常见的推导语境：每个函数形参类型 P 与对应实参类型 A 比较。P 非引用时 A 发生数组/函数退化并去掉顶层 cv；P 是引用时用被引用类型；转发引用 T&& 遇到左值时把 A 换成 A&；初始化列表只对 initializer_list<P'> 与 P'[N] 可推导；允许的三种"差异"（更多 cv、限定转换、派生到基类）；重载集实参。
status: done
covers: temp.deduct.call
papers: N4164
related: temp.deduct, temp.deduct.type, temp.arg.explicit, temp.over, dcl.init.list, dcl.spec.auto, over.match.class.deduct, topics/type-deduction, topics/value-categories
tags: 模板, 模板实参推导, 转发引用, initializer_list
updated: 2026-10-18
---

[[temp.deduct.call]] 处理的是最常见的推导：`f(x)` 中，从实参 `x` 推出 `f` 的模板实参。它的工作是把每对"形参类型 `P` / 实参类型 `A`"**调整**成适合比较的形式，然后交给 [[temp.deduct.type]] 做真正的结构匹配。

这一节同时是 `auto` 推导的基础：`auto x = expr;` 就是按本节规则，把 `auto` 换成一个虚构模板形参 `U`、把 `expr` 当作实参推导出来的（[[dcl.type.auto.deduct]]）。所以本节的每一条规则，都同时决定了 `auto` 的行为（`initializer_list` 是唯一的特例）。两者的并列对比见 [[topics/type-deduction]]。

## P 与 A；初始化列表；形参包（¶1）

¶1 对每个**含有参与推导的模板形参**的函数形参类型（记作 `P`），与调用中对应实参的类型（记作 `A`）比较。不含参与推导的模板形参的形参（例如 `int`，或所有模板形参都已显式指定的）不参与推导，只在重载决议中检查转换（[[temp.arg.explicit#7]]）。

### 初始化列表实参

实参是**花括号初始化列表**时，它没有类型，不能直接作为 `A`。¶1 规定：

- 若从 `P` 去掉引用和 cv 后得到 `std::initializer_list<P'>` 或 `P'[N]`，且实参是**非空**初始化列表，则把列表的**每个元素**当作类型为 `P'` 的单独形参的实参分别推导。`P'[N]` 情形中若 `N` 是常量模板形参，`N` 从列表长度推导。
- 否则，初始化列表实参使该形参成为**非推导语境**（[[temp.deduct.type#5]] ¶5.9）。

```cpp ok title="init_list_deduce.cpp"
#include <initializer_list>
template<class T> void f(std::initializer_list<T>) { }
template<class T, int N> void h(T const(&)[N]) { static_assert(N == 3); }
template<class T> void j(T const(&)[3]) { }
struct Aggr { int i; int j; };
template<int N> void k(Aggr const(&)[N]) { static_assert(N == 3); }
template<int M, int N> void m(int const(&)[M][N]) { static_assert(M == 2 && N == 2); }

void t() {
    f({1, 2, 3});            // T = int
    h({1, 2, 3});            // T = int，N = 3
    j({42});                 // T = int；界 3 不参与（只有一个元素也行）
    k({{1}, {2}, {3}});      // N = 3：每个元素 {1} 初始化一个 Aggr
    m({{1, 2}, {3, 4}});     // M = 2，N = 2：嵌套列表
}
```

```cpp error
#include <initializer_list>
template<class T> void f(std::initializer_list<T>);
template<class T> void g(T);
struct Aggr { int i; int j; };
template<int N> void k(Aggr const(&)[N]);

void t() {
    f({1, "asdf"});   // error: T 被推导为 int 和 const char*
    g({1, 2, 3});     // error: T 无法推导（非推导语境）
    k({1, 2, 3});     // error: 推导失败——int 无法"成为" Aggr
}
```

几点值得注意：

- `g({1,2,3})` 失败，而 `auto x = {1,2,3};` 推导为 `initializer_list<int>`——这是 `auto` 与模板推导**唯一**的规则差异（[[dcl.type.auto.deduct]] 把 `auto` 换成 `initializer_list<U>` 再推导）。
- `k({1,2,3})` 失败：每个元素 `1` 要与 `P' = Aggr` 推导，`Aggr` 不含模板形参，于是检查 `int` 能否隐式转换为 `Aggr`——不能（聚合初始化不是隐式转换）。`k({{1},{2},{3}})` 中每个元素 `{1}` 本身是初始化列表，对不含模板形参的 `P'` 不做推导，只要求能初始化。
- `j({42})`：`P' = T`、界是固定的 3，界不参与推导，一个元素就够了（剩下的值初始化）。

标准例 1 还展示了元素是重载集的情形：

```cpp
template<typename T, int N> void o(T (* const (&)[N])(T)) { }
int f1(int);
int f4(int);
char f4(char);
o({ &f1, &f4 });                                // OK：T 从第一个元素推导为 int，
                                                // 第二个元素（重载集）不推导任何东西；N = 2
o({ &f1, static_cast<char(*)(char)>(&f4) });    // error: T 推导冲突
```

### 尾随函数形参包

对出现在形参列表**末尾**的函数形参包，用包的 *declarator-id* 的类型作为 `P`，与**每个剩余实参**推导。每次推导确定包所展开的模板形参包的下一个位置。函数形参包出现在**非推导语境**中（例如不在末尾）时，其类型永远不被推导。

```cpp
template<class... Types> void f(Types&...);
template<class T1, class... Types> void g(T1, Types...);
template<class T1, class... Types> void g1(Types..., T1);

void h(int x, float& y) {
    const int z = x;
    f(x, y, z);                   // Types = int, float, const int
    g(x, y, z);                   // T1 = int；Types = float, int
    g1(x, y, z);                  // error: Types 不在末尾，不推导
    g1<int, int, int>(x, y, z);   // OK：不推导（Types = int, int，T1 = int）
}
```

`f(x, y, z)` 中 `z` 推导出 `const int`：`P = Types&` 是引用，cv 保留（¶3）。`g(x, y, z)` 中 `z` 推导出 `int`：`P = Types` 是值，顶层 cv 被去掉（¶2.3）。

## P 不是引用时：A 的退化（¶2）

¶2 若 `P` **不是引用类型**：

- ¶2.1 `A` 是数组类型 → 用数组到指针转换得到的指针类型代替；否则
- ¶2.2 `A` 是函数类型 → 用函数到指针转换得到的指针类型代替；否则
- ¶2.3 `A` 有顶层 cv → 忽略。

这模拟的是**按值传参**时实际发生的事：数组和函数不能按值传递，会退化；按值拷贝出来的形参与实参的 const 无关。

## P 本身的 cv 与引用（¶3）

¶3 若 `P` 有顶层 cv，推导时忽略。若 `P` 是引用类型，用 `P` **所引用的类型**推导。

```cpp
template<class T> int f(const T&);
int n1 = f(5);          // f<int>(const int&)
const int i = 0;
int n2 = f(i);          // f<int>(const int&)：P' = const T，A = const int → T = int
template<class T> int g(volatile T&);
int n3 = g(i);          // g<const int>(const volatile int&)
```

`g(i)`：`P` 引用 `volatile T`，`A = const int`；匹配 `volatile T` 与 `const int`，`T` 吸收了 `const`，并允许"更多 cv"（¶4.1）——结果 `T = const int`。

### 按值、按引用、按转发引用：一张表

| 实参 | `template<class T> void f(T)` | `f(T&)` | `f(T&&)` |
|---|---|---|---|
| `int i`（左值） | `T = int` | `T = int` | `T = int&` |
| `const int ci`（左值） | `T = int` | `T = const int` | `T = const int&` |
| `42`（纯右值） | `T = int` | 推导出 `int`，但不能绑定：失败 | `T = int` |
| `std::move(i)`（亡值） | `T = int` | 同上，失败 | `T = int` |
| `int arr[3]` | `T = int*` | `T = int[3]` | `T = int(&)[3]` |
| `const int carr[2]` | `T = const int*` | `T = const int[2]` | `T = const int(&)[2]` |
| `"hi"`（`const char[3]` 左值） | `T = const char*` | `T = const char[3]` | `T = const char(&)[3]` |
| `void fn(int)` | `T = void(*)(int)` | `T = void(int)` | `T = void(&)(int)` |

（以上每一格都在 Clang 23 上用 `static_assert(std::is_same_v<...>)` 验证过。）

注意 `const int carr[2]` 按值时得到 `const int*`：数组退化后指针**指向** `const int`，那个 `const` 不是顶层的，保留。

## 转发引用（¶3 后半）

!!! std
    A *forwarding reference* is an rvalue reference to a cv-unqualified template parameter that does not represent a template parameter of a class template (during class template argument deduction).

    转发引用：对 cv 未限定的模板形参的右值引用，且（在类模板实参推导中）该形参不代表类模板的模板形参。

规则：**若 `P` 是转发引用且实参是左值，用"对 `A` 的左值引用"代替 `A` 推导。**

```cpp
template <class T> int f(T&& heisenreference);
template <class T> int g(const T&&);
int i;
int n1 = f(i);   // f<int&>(int&)：A 换成 int&，T = int&，T&& 折叠为 int&
int n2 = f(0);   // f<int>(int&&)
int n3 = g(i);   // error: g<int>(const int&&) 会把右值引用绑定到左值
```

（标准给形参起名 `heisenreference`——"海森堡引用"：观测之前不知道它是左值引用还是右值引用。）

拆开 `f(i)`：

1. `P = T&&`，是转发引用；实参 `i` 是左值，`A = int` 换成 `int&`。
2. `P` 是引用，用被引用类型 `T` 推导（¶3）：`T` 对 `int&`，得 `T = int&`。
3. 代入：`T&&` = `int& &&`，按**引用折叠**（[[dcl.ref#7]]）得 `int&`。

`f(0)`：`0` 是右值，不替换，`T = int`，形参 `int&&`。

于是 `T` 的推导结果**编码了实参的值类别**：左值 → `T` 是左值引用类型；右值 → `T` 是非引用类型。`std::forward<T>(x)` 正是利用 `T` 恢复原来的值类别：

```cpp run ok title="perfect_forward.cpp"
#include <cstdio>
#include <utility>
void sink(int&)  { std::puts("lvalue"); }
void sink(int&&) { std::puts("rvalue"); }

template<class T> void relay(T&& x) {
    sink(x);                       // 总是 lvalue：具名的 x 是左值
    sink(std::forward<T>(x));      // T = int& → 左值；T = int → 右值
}

int main() {
    int i = 0;
    relay(i);        // lvalue lvalue
    relay(42);       // lvalue rvalue
}
```

**不是**转发引用的情形：

| 写法 | 是否转发引用 | 原因 |
|---|---|---|
| `template<class T> void f(T&&)` | 是 | — |
| `template<class T> void f(const T&&)` | 否 | cv 限定 |
| `template<class T> void f(std::vector<T>&&)` | 否 | 不是"对模板形参的"右值引用 |
| `template<class T> struct S { void f(T&&); }` | 否 | `T` 在调用 `f` 时不被推导（成员函数不是模板） |
| `template<class T> struct S { template<class U> void f(U&&); }` | 是（`U&&`） | — |
| `auto&& x = expr;` | 是（同样规则） | [[dcl.type.auto.deduct]] |
| CTAD 中构造函数的 `T&&`（`T` 是类模板形参） | 否 | 定义中明确排除 |
| 推导指引中的 `T&&` | 是 | 推导指引的形参是它自己的 |

最后两行对应标准例 4 的后半：

```cpp
template <class T> struct A {
    template <class U>
        A(T&&, U&&, int*);   // #1：T&& 不是转发引用；U&& 是
    A(T&&, int*);            // #2
};
template <class T> A(T&&, int*) -> A<T>;   // #3：T&& 是转发引用

int i; int *ip;
A a{i, 0, ip};    // error: 无法从 #1 推导（T&& 不能绑定左值 i）
A a0{0, 0, ip};   // 用 #1 推导出 A<int>，用 #1 初始化
A a2{i, ip};      // 用 #3 推导出 A<int&>，用 #2 初始化
```

CTAD（[[over.match.class.deduct]]）把构造函数变成虚构的函数模板，类模板形参 `T` 成了虚构模板的形参——如果 `T&&` 也算转发引用，`A a{i, 0, ip}` 就会推出 `A<int&>`，这通常不是类作者的意图（`std::vector<T>` 有 `vector(T&&)` 风格的构造函数，你不会想要 `vector<int&>`）。所以定义特意排除。推导指引是用户显式写的，用户可以要求转发引用语义。

!!! history "“万能引用”与“转发引用”"
    Scott Meyers 最早称之为 universal reference（万能引用），这个说法流传甚广。标准术语 forwarding reference 来自 [[N4164]]（Sutter、Stroustrup、Dos Reis），在 C++17 的标准文本中正式使用。两者指同一件事。

## 允许的三种差异（¶4–¶5）

¶4 一般而言，推导要找到模板实参，使推导出的 `A`（`P` 代入后的结果）与（调整后的）`A` **完全相同**。但有三种情况允许不同：

- ¶4.1 原 `P` 是引用类型时，推导出的 `A`（被引用类型）可以比调整后的 `A` **更 cv 限定**。（`const T&` 绑定 `int` 左值：推导出 `const int`，比 `int` 多 `const`。）
- ¶4.2 调整后的 `A` 可以是另一个指针或成员指针类型，能通过**函数指针转换**和/或**限定转换**转为推导出的 `A`。（`const T*` 接受 `int*`；`void(*)()` 接受 `void(*)() noexcept`。）
- ¶4.3 `P` 是 *simple-template-id* 形式的类（如 `B<T>`）时，调整后的 `A` 可以是推导出的 `A` 的**派生类** `D`。`P` 是指向这种类的指针时同理。但如果有一个类 `C`，它是 `D` 的（直接或间接）基类、又派生自 `B`，且 `C` 也是合法的推导结果，则推导结果不能是 `B`。

¶4.3 的最后一句是 C++ 后来补充的"最派生优先"：

```cpp ok title="most_derived_base.cpp"
template <typename... T> struct X;
template <> struct X<> { };
template <typename T, typename... Ts>
struct X<T, Ts...> : X<Ts...> { };      // X<int> 派生自 X<>

struct D : X<int> { };
struct E : X<>, X<int> { };             // E 同时直接派生自 X<> 和 X<int>

template <typename... T> constexpr int f(const X<T...>&) { return sizeof...(T); }

static_assert(f(D()) == 1);   // f<int>，不是 f<>：B = X<>，C = X<int>
static_assert(f(E()) == 1);   // f<int>，不是 f<>
```

`D` 的基类中有 `X<int>` 和 `X<>`，两者都能匹配 `X<T...>`。没有这条规则就会二义而推导失败；有了它，`X<int>`（更靠近 `D` 的那个，并且它本身派生自 `X<>`）胜出。这个规则对 `std::tuple` 风格的递归继承实现很重要。

¶5 这些例外**只在推导本来会失败时**才考虑。若产生多个可能的推导结果，推导失败。

注 1（¶5）：如果某个模板形参不出现在任何函数形参中、或只出现在非推导语境中，它的模板实参无法从调用推导，必须显式指定（如 `convert<int>(d)`）。

!!! pitfall "推导不考虑用户定义转换"
    ¶4 的三种差异就是推导所能容忍的全部。**隐式转换**——整型提升、算术转换、转换构造函数、转换运算符——统统不考虑：

    ```cpp
    template<class T> struct Wrapper { Wrapper(T) { } };
    template<class T> void take(Wrapper<T>);
    take(42);    // error: int 不是 Wrapper<T>，推导不会去找 Wrapper<int>(int)
    ```

    同理，`template<class T> bool eq(const std::basic_string<T>&, const std::basic_string<T>&)` 不接受 `eq(s, "abc")`：`const char[4]` 不是 `basic_string<T>`，推导不会去找转换构造函数。修正：显式指定实参，或把形参放进非推导语境（`std::type_identity_t<Wrapper<T>>`），或为非模板类型写非模板的友元函数（"hidden friend"，类内定义的友元在 `T` 已知时是普通函数）。

```cpp ok title="allowed_diffs.cpp"
template<class T> void f(const T*) { }
template<class T> struct B { };
template<class T> struct D : B<T> { };
template<class T> void g(B<T>*) { }

void t() {
    int* p = nullptr;
    f(p);         // ¶4.2：int* → const int*（限定转换），T = int
    D<int> d;
    g(&d);        // ¶4.3：D<int>* → B<int>*，T = int
}
```

## 实参是重载集（¶6–¶10）

¶6 当 `P` 是函数类型、函数指针类型或成员函数指针类型时：

- ¶6.1 实参是含有**一个或多个函数模板**的重载集 → 该形参视为**非推导语境**；
- ¶6.2 实参是重载集（不含函数模板）→ 用集合中**约束满足**的每个成员**试推导**。若所有成功的试推导产生**相同**的 `A`，那就是推导结果；否则该形参视为非推导语境。

```cpp ok
// 例 6：只有一个成员匹配，是推导语境
template <class T> int f(T (*p)(T));
int g(int);
int g(char);
int i = f(g);       // g(int) 能匹配 T(*)(T)（T = int）；g(char) 返回 int、形参 char，不匹配
```

```cpp ok
// 例 7：多个成员都能匹配且结果不同 → 非推导语境，T 从别处推导
template <class T> int f(T, T (*p)(T));
int g(int);
char g(char);
int i = f(1, g);    // 第二个形参非推导；T 从第一个实参推导为 int，再选 g(int)
```

```cpp ok
// 例 8：重载集中有模板 → 非推导语境
template <class T> int f(T, T (*p)(T));
char g(char);
template <class T> T g(T);
int i = f(1, g);    // 第二个形参非推导；T = int，选 g<int>
```

```cpp ok
// 例 9：约束不满足的成员不参与；两个都给出相同类型时也 OK
template<bool B> struct X {
    static void f(short) requires B;   // #1
    static void f(short);              // #2
};
void test() {
    auto x = &X<true>::f;    // OK：推导出 void(*)(short)，选 #1（更受约束）
    auto y = &X<false>::f;   // OK：推导出 void(*)(short)，选 #2
    (void)x; (void)y;
}
```

例 9 中 `auto` 推导走的就是本节规则（[[dcl.type.auto.deduct]]）。`X<true>::f` 的两个成员类型相同，¶6.2 说"所有成功的试推导产生相同的 `A`"即可，于是推导为 `void(*)(short)`；然后 [[over.over]] 用约束选出 #1。

¶6.2 的设计意图：推导**只关心类型**；具体选哪个函数，在推导成功之后由 [[over.over]] 决定（[[temp.deduct.type#5]] 注 2）。所以只要类型无歧义，就不需要在推导阶段就选出唯一的函数。

## 陷阱

!!! pitfall "`T&&` 不总是右值引用"
    在 `template<class T> void f(T&&)` 中，`T&&` 能绑定左值。在函数体里重载 `f(T&&)` 与 `f(const T&)` 时，非 const 左值实参会选 `T&&` 版本（`T = U&`，精确匹配），而不是 `const T&`——这是"转发引用贪婪"问题，常让人以为调用了拷贝版本却调用了转发版本。完美转发构造函数会劫持拷贝构造就是这个原因。

!!! pitfall "按值形参丢掉 const 和数组长度"
    `template<class T> void f(T)` 永远推不出 `const`、引用或数组类型。想保留数组长度用 `T(&)[N]` 或 `const T(&)[N]`；想保留一切用 `T&&`。

!!! pitfall "`{...}` 只对 `initializer_list<T>` 与 `T[N]` 可推导"
    `template<class T> void f(std::vector<T>)` 不能接受 `f({1, 2, 3})`：`vector<T>` 不是那两种形式，初始化列表让形参成为非推导语境，`T` 推不出来。需要写 `f<int>({1,2,3})` 或 `f(std::vector{1,2,3})`。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> void f(T&&, T&&);
    int i = 0;
    f(i, 0);
    ```
    能编译吗？

<details markdown="1">
<summary>答案</summary>

不能。第一对：`i` 是左值，`A` 换成 `int&`，推导 `T = int&`。第二对：`0` 是右值，推导 `T = int`。两对推导出不同的 `T`，推导失败（[[temp.deduct.type#2]]）。这说明转发引用把值类别编码进 `T`，多个转发引用形参共用一个 `T` 时，实参的值类别也必须一致。通常应该写 `template<class T, class U> void f(T&&, U&&)`。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> void f(const T& a, const T& b);
    f("ab", "abc");
    ```
    能编译吗？如果把形参改成按值 `f(T a, T b)` 呢？

<details markdown="1">
<summary>答案</summary>

按引用：`P` 是引用，数组**不退化**（¶2 只对非引用 `P` 退化）。第一对推导 `T = char[3]`（`const T` 对 `const char[3]`），第二对推导 `T = char[4]`，冲突，推导失败。

按值：¶2.1 数组退化为 `const char*`，两对都推导 `T = const char*`，成功。这就是为什么 `std::max("ab", "abc")` 编译失败（`max` 按 `const T&` 接收），而按值的版本却能"工作"（比较的是指针，结果几乎肯定不是你想要的）。
</details>

## 小结

| 情形 | 调整 | 段落 |
|---|---|---|
| 实参是初始化列表 | 仅 `initializer_list<P'>`/`P'[N]` 逐元素推导，否则非推导 | ¶1 |
| 尾随函数形参包 | 逐个剩余实参推导；非尾随则不推导 | ¶1 |
| `P` 非引用 | `A`：数组→指针、函数→指针、去顶层 cv | ¶2 |
| `P` 有顶层 cv / 是引用 | 去 cv / 用被引用类型 | ¶3 |
| 转发引用 + 左值实参 | `A` 换成 `A&` | ¶3 |
| 允许的差异 | 更多 cv（引用）、限定/函数指针转换、派生到基类（最派生优先） | ¶4 |
| 差异仅在本会失败时考虑；多解则失败 | — | ¶5 |
| 实参是重载集 | 含模板 → 非推导；否则试推导，结果唯一才算 | ¶6 |
