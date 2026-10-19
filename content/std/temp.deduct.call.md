---
title: 从函数调用推导模板实参
summary: 调用函数模板时，每个形参类型 P 与对应实参类型 A 怎样比较：按值形参让数组和函数退化并去掉顶层 const，引用形参用被引用的类型，转发引用遇到左值时把 A 换成左值引用；推导容许的三种差异；花括号列表、形参包和重载集作实参时的规则。
status: done
covers: temp.deduct.call
papers: N4164
related: temp.deduct, temp.deduct.type, temp.arg.explicit, temp.over, dcl.init.list, dcl.spec.auto, over.match.class.deduct, topics/type-deduction, topics/value-categories
tags: 模板, 模板实参推导, 转发引用, initializer_list
updated: 2026-10-19
---

!!! tldr
    - 推导把每个形参类型 `P` 和对应实参的类型 `A` 配成一对来比较。比较之前，按值形参会让数组、函数实参退化成指针，并去掉实参的顶层 `const`；引用形参则用它引用的类型比较。
    - `T&&` 形式的转发引用遇到左值实参时，`A` 换成左值引用，于是 `T` 推导为 `X&`。`T` 由此记下了实参是左值还是右值，`std::forward<T>` 靠它恢复。
    - 推导不考虑隐式转换。实参和形参之间只容许三种差异：多出的 cv、指针的限定转换和函数指针转换、派生类到基类模板。
    - 花括号列表作实参时，只有 `std::initializer_list<T>` 和 `T[N]` 形参能逐元素推导，其他形参推不出来。这是 `auto` 推导与模板推导唯一的不同。
    - 实参是重载函数名时：集合里有函数模板就不推导；否则逐个试，结果唯一才算推导成功。

## 三种形参写法，三种结果

```cpp
template<class T> void byval(T);
template<class T> void byref(T&);
template<class T> void fwd(T&&);

const int ci = 0;
byval(ci);   // T = int
byref(ci);   // T = const int
fwd(ci);     // T = const int&
```

同一个实参，三种形参写法推出三个不同的 `T`。原因在于比较之前，形参类型和实参类型都要先调整。

¶1 函数调用中，每个含有参与推导的模板形参的函数形参类型（记作 `P`），与调用中对应实参的类型（记作 `A`）比较。调整之后的 `P` 和 `A` 交给 [[temp.deduct.type]] 做结构匹配。不含参与推导的模板形参的形参（比如 `int`，或模板实参已经显式写出的形参）不参与推导，只在重载决议时检查转换（[[temp.arg.explicit#7]]）。

`auto` 的推导用的也是这一节的规则：`auto x = expr;` 相当于把 `auto` 换成一个虚构的模板形参，把 `expr` 当作实参来推导（[[dcl.type.auto.deduct]]）。两者的对照见 [[topics/type-deduction]]。

### 按值形参：实参退化（¶2）

¶2 如果 `P` 不是引用类型：

- ¶2.1 `A` 是数组类型时，换成数组到指针转换得到的指针类型；否则
- ¶2.2 `A` 是函数类型时，换成函数到指针转换得到的指针类型；否则
- ¶2.3 `A` 有顶层 cv 时，忽略它。

这模拟的是按值传参时实际发生的事：数组和函数不能按值传递，会退化成指针；拷贝出来的形参也与实参是否 `const` 无关。所以 `byval(ci)` 推导出 `T = int`。

### 形参的 cv 与引用（¶3）

¶3 如果 `P` 有顶层 cv，推导时忽略。如果 `P` 是引用类型，用它引用的类型推导。

```cpp
template<class T> int f(const T&);
int n1 = f(5);          // f<int>(const int&)
const int i = 0;
int n2 = f(i);          // f<int>(const int&)：const T 对 const int，T = int
template<class T> int g(volatile T&);
int n3 = g(i);          // g<const int>(const volatile int&)
```

`byref(ci)` 中，`T&` 引用的是 `T`，拿 `T` 去对 `const int`，得到 `T = const int`，`const` 被保留了下来。`g(i)` 中，`volatile T` 对 `const int`，`T` 吸收了 `const`，得到 `T = const int`；推导出的 `const volatile int` 比实参多了 `volatile`，这是 ¶4.1 容许的差异。

下表列出常见实参在三种形参下推导出的 `T`。每一格都在本机 Clang 23 上用 `static_assert` 核对过。

| 实参 | `f(T)` | `f(T&)` | `f(T&&)` |
|---|---|---|---|
| `int i`（左值） | `int` | `int` | `int&` |
| `const int ci`（左值） | `int` | `const int` | `const int&` |
| `42`（纯右值） | `int` | 推导出 `int`，但无法绑定，失败 | `int` |
| `std::move(i)`（亡值） | `int` | 同上，失败 | `int` |
| `int arr[3]` | `int*` | `int[3]` | `int(&)[3]` |
| `const int carr[2]` | `const int*` | `const int[2]` | `const int(&)[2]` |
| `"hi"`（`const char[3]` 左值） | `const char*` | `const char[3]` | `const char(&)[3]` |
| `void fn(int)` | `void(*)(int)` | `void(int)` | `void(&)(int)` |

`const int carr[2]` 按值时得到 `const int*`：数组退化后，`const` 修饰的是指针指向的 `int`，不是顶层，所以保留。

## 转发引用（¶3）

!!! std
    A *forwarding reference* is an rvalue reference to a cv-unqualified template parameter that does not represent a template parameter of a class template (during class template argument deduction).

[[g:forwarding-reference|**转发引用**]]（forwarding reference）是对一个没有 cv 限定的模板形参的右值引用，也就是 `T&&`。类模板实参推导时，代表类模板形参的 `T&&` 不算（见下文）。¶3 规定：如果 `P` 是转发引用而实参是左值，就用 `A` 的左值引用类型代替 `A` 来推导。

```cpp
template <class T> int f(T&& heisenreference);
template <class T> int g(const T&&);
int i;
int n1 = f(i);   // f<int&>(int&)
int n2 = f(0);   // f<int>(int&&)
int n3 = g(i);   // error: g<int>(const int&&) 会把右值引用绑定到左值
```

标准给形参起名 heisenreference，取自海森堡：观测之前不知道它是左值引用还是右值引用。`f(i)` 的推导过程是：

1. `P = T&&` 是转发引用，实参 `i` 是左值，`A` 从 `int` 换成 `int&`；
2. `P` 是引用，用它引用的 `T` 去对 `int&`，得到 `T = int&`；
3. 代入后 `T&&` 是 `int& &&`，按引用折叠（[[dcl.ref#7]]）成为 `int&`。

`f(0)` 的实参是右值，`A` 不变，`T = int`，形参是 `int&&`。`g` 的形参带了 `const`，不是转发引用，`T` 推导为 `int`，`const int&&` 不能绑定左值。

于是 `T` 的推导结果记下了实参的值类别：实参是左值时 `T` 是左值引用，是右值时 `T` 不是引用。`std::forward<T>(x)` 用 `T` 恢复原来的值类别：

```cpp run ok
#include <cstdio>
#include <utility>
void sink(int&)  { std::puts("lvalue"); }
void sink(int&&) { std::puts("rvalue"); }

template<class T> void relay(T&& x) {
    sink(x);                       // 总是 lvalue：有名字的 x 是左值
    sink(std::forward<T>(x));      // T = int& 时是左值，T = int 时是右值
}

int main() {
    int i = 0;
    relay(i);        // lvalue lvalue
    relay(42);       // lvalue rvalue
}
```

哪些写法是转发引用：

| 写法 | 是否转发引用 | 原因 |
|---|---|---|
| `template<class T> void f(T&&)` | 是 | |
| `template<class T> void f(const T&&)` | 否 | 有 cv 限定 |
| `template<class T> void f(std::vector<T>&&)` | 否 | 不是对模板形参本身的引用 |
| `template<class T> struct S { void f(T&&); }` | 否 | 调用 `f` 时 `T` 已经确定，不推导 |
| `template<class T> struct S { template<class U> void f(U&&); }` | 是（`U&&`） | |
| `auto&& x = expr;` | 是 | [[dcl.type.auto.deduct]] |
| 类模板实参推导中构造函数的 `T&&`（`T` 是类模板形参） | 否 | 定义明确排除 |
| 推导指引中的 `T&&` | 是 | 推导指引的形参属于它自己 |

最后两行对应标准例 4 的后半：

```cpp
template <class T> struct A {
    template <class U>
        A(T&&, U&&, int*);   // #1：T&& 不是转发引用，U&& 是
    A(T&&, int*);            // #2
};
template <class T> A(T&&, int*) -> A<T>;   // #3：T&& 是转发引用

int i; int *ip;
A a{i, 0, ip};    // error: 无法从 #1 推导（T&& 不能绑定左值 i）
A a0{0, 0, ip};   // 用 #1 推导出 A<int>，用 #1 初始化
A a2{i, ip};      // 用 #3 推导出 A<int&>，用 #2 初始化
```

类模板实参推导（[[over.match.class.deduct]]）把构造函数当成虚构的函数模板，类模板形参 `T` 成了这个虚构模板的形参。如果 `A(T&&, ...)` 中的 `T&&` 也算转发引用，左值实参就会推出 `A<int&>`，这通常不是类作者的本意，所以定义把它排除了。推导指引是作者专门写的，可以要求转发引用的语义。

这个术语由 [[N4164]] 引入标准。在此之前，它常被称为 universal reference（万能引用），两者指同一件事。

## 推导容许的三种差异（¶4–¶5）

¶4 一般来说，推导要找到一组模板实参，使代入后的 `P`（推导出的 `A`）与调整后的 `A` 完全相同。但有三种情况允许两者不同：

- ¶4.1 原来的 `P` 是引用类型时，推导出的 `A` 可以比 `A` 多 cv 限定。例如 `const T&` 接受 `int` 左值。
- ¶4.2 `A` 可以是另一个指针或成员指针类型，只要能通过函数指针转换和限定转换变成推导出的 `A`。例如 `const T*` 接受 `int*`，`void(*)()` 接受 `void(*)() noexcept`。
- ¶4.3 `P` 是 *simple-template-id* 形式的类类型（如 `B<T>`）时，`A` 可以是推导出的 `A` 的派生类；`P` 是指向这种类的指针时，`A` 可以是指向派生类的指针。

```cpp ok
template<class T> void f(const T*) { }
template<class T> struct B { };
template<class T> struct D : B<T> { };
template<class T> void g(B<T>*) { }

void t() {
    int* p = nullptr;
    f(p);         // ¶4.2：int* 经限定转换成为 const int*，T = int
    D<int> d;
    g(&d);        // ¶4.3：D<int>* 转换成 B<int>*，T = int
}
```

¶4.3 最后一句规定了派生类有多个基类都能匹配时选哪一个：如果某个基类 `C` 本身派生自 `B`，而 `C` 也能作为推导结果，就不能推导为 `B`。也就是离派生类更近的基类优先：

```cpp ok
template <typename... T> struct X;
template <> struct X<> { };
template <typename T, typename... Ts>
struct X<T, Ts...> : X<Ts...> { };      // X<int> 派生自 X<>

struct D : X<int> { };
struct E : X<>, X<int> { };             // E 直接派生自 X<> 和 X<int>

template <typename... T> constexpr int f(const X<T...>&) { return sizeof...(T); }

static_assert(f(D()) == 1);   // f<int>，不是 f<>：B 是 X<>，C 是 X<int>
static_assert(f(E()) == 1);   // f<int>，不是 f<>
```

`D` 的基类 `X<int>` 和 `X<>` 都能匹配 `X<T...>`。没有这条规则，推导就有两个结果而失败；有了它，派生自 `X<>` 的 `X<int>` 胜出。`std::tuple` 风格的递归继承实现依赖这一点。

¶5 这三种例外只在推导本来会失败时才考虑。考虑之后如果得到不止一个可能的结果，推导失败。

注 1 提醒，一个模板形参如果不出现在任何函数形参里，或者只出现在[[g:non-deduced-context|非推导语境]]中，就无法从调用推导，必须显式指定，例如 `convert<int>(d)`。

!!! pitfall "推导不考虑隐式转换"
    除了上面三种差异，整型提升、算术转换、转换构造函数、转换运算符一概不考虑：

    ```cpp
    template<class T> struct Wrapper { Wrapper(T) { } };
    template<class T> void take(Wrapper<T>);
    void t() { take(42); }   // error: int 不是 Wrapper<T>，推导不会去找 Wrapper<int>(int)
    ```

    同理，`template<class C> bool eq(const std::basic_string<C>&, const std::basic_string<C>&)` 不接受 `eq(s, "abc")`。修正方法有三种：显式指定实参；把形参放进非推导语境（`std::type_identity_t<Wrapper<T>>`）；或者在类里定义非模板的友元函数（hidden friend），类模板实例化之后它就是普通函数，可以做转换。

## 花括号列表作实参（¶1）

花括号初始化列表没有类型，不能直接作为 `A`。¶1 规定：

- 从 `P` 去掉引用和 cv 后，如果得到 `std::initializer_list<P'>` 或 `P'[N]`，而实参是非空的初始化列表，就把列表的每个元素当作一个类型为 `P'` 的独立形参的实参，分别推导。`P'[N]` 中如果 `N` 是常量模板形参，`N` 从列表长度推导。
- 否则，初始化列表实参让这个形参成为非推导语境（[[temp.deduct.type#5]] ¶5.9）。

```cpp ok
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
    j({42});                 // T = int；数组界 3 不参与推导
    k({{1}, {2}, {3}});      // N = 3：每个 {1} 初始化一个 Aggr
    m({{1, 2}, {3, 4}});     // M = 2，N = 2
}
```

```cpp error
#include <initializer_list>
template<class T> void f(std::initializer_list<T>);
template<class T> void g(T);
struct Aggr { int i; int j; };
template<int N> void k(Aggr const(&)[N]);

void t() {
    f({1, "asdf"});   // error: T 推导为 int 和 const char*，冲突
    g({1, 2, 3});     // error: 非推导语境，T 推不出来
    k({1, 2, 3});     // error: int 不能转换为 Aggr
}
```

- `g({1, 2, 3})` 失败，而 `auto x = {1, 2, 3};` 推导为 `std::initializer_list<int>`。这是 `auto` 与模板推导唯一的规则差异：[[dcl.type.auto.deduct]] 对 `auto` 专门把它换成 `initializer_list<U>` 再推导。
- `k({1, 2, 3})` 失败：每个元素 `1` 对应 `P' = Aggr`，`Aggr` 不含模板形参，于是检查 `int` 能否隐式转换为 `Aggr`，不能。`k({{1}, {2}, {3}})` 中每个元素 `{1}` 本身是列表，只要求它能初始化 `Aggr`。
- `j({42})` 中数组界是固定的 3，不参与推导，一个元素也可以，其余元素值初始化。

元素也可以是重载函数名。下面的例子中，`T` 从第一个元素推导为 `int`，第二个元素 `&f4` 是重载集，不推导任何东西（见下文 ¶6），`N = 2`：

```cpp
template<typename T, int N> void o(T (* const (&)[N])(T)) { }
int f1(int);
int f4(int);
char f4(char);
o({ &f1, &f4 });                                // OK
o({ &f1, static_cast<char(*)(char)>(&f4) });    // error: T 推导为 int 和 char，冲突
```

## 函数形参包（¶1）

对出现在形参列表末尾的函数形参包，用包的声明符的类型作为 `P`，与剩下的每个实参分别推导，每次推导确定包里下一个位置的模板实参。如果函数形参包出现在非推导语境中，它的类型永远不会被推导，例如包不在末尾时：

```cpp
template<class... Types> void f(Types&...);
template<class T1, class... Types> void g(T1, Types...);
template<class T1, class... Types> void g1(Types..., T1);

void h(int x, float& y) {
    const int z = x;
    f(x, y, z);                   // Types = int, float, const int
    g(x, y, z);                   // T1 = int；Types = float, int
    g1(x, y, z);                  // error: Types 不在末尾，不推导
    g1<int, int, int>(x, y, z);   // OK：不推导，Types = int, int，T1 = int
}
```

`f(x, y, z)` 中 `z` 推导出 `const int`，因为 `P = Types&` 是引用，cv 保留（¶3）。`g(x, y, z)` 中 `z` 推导出 `int`，因为 `P = Types` 按值，顶层 cv 被去掉（¶2.3）。

## 实参是重载函数名（¶6–¶10）

¶6 `P` 是函数类型、函数指针类型或成员函数指针类型时，如果实参是一个重载集：

- ¶6.1 集合里有一个或多个函数模板，这个形参就作为非推导语境；
- ¶6.2 集合里没有函数模板，就用其中约束得到满足的每个成员试着推导。所有成功的试推导得到同一个 `A` 时，这就是推导结果；否则这个形参作为非推导语境。

```cpp ok
// 例 6：只有一个成员能匹配，可以推导
template <class T> int f(T (*p)(T));
int g(int);
int g(char);
int i = f(g);       // 只有 g(int) 符合 T(*)(T)，T = int
```

```cpp ok
// 例 7：两个成员都能匹配且结果不同，不推导；T 从别的实参得到
template <class T> int f(T, T (*p)(T));
int g(int);
char g(char);
int i = f(1, g);    // T 从 1 推导为 int，再选 g(int)
```

```cpp ok
// 例 8：重载集里有模板，不推导
template <class T> int f(T, T (*p)(T));
char g(char);
template <class T> T g(T);
int i = f(1, g);    // T = int，选 g<int>
```

```cpp ok
// 例 9：几个成员给出相同的类型，也算推导成功
template<bool B> struct X {
    static void f(short) requires B;   // #1
    static void f(short);              // #2
};
void test() {
    auto x = &X<true>::f;    // OK：推导出 void(*)(short)，选 #1
    auto y = &X<false>::f;   // OK：推导出 void(*)(short)，选 #2
    (void)x; (void)y;
}
```

例 9 中，`X<true>::f` 的两个成员类型相同，¶6.2 只要求所有成功的试推导得到同一个 `A`，所以推导为 `void(*)(short)`。具体选哪个函数由 [[over.over]] 在推导之后决定，它按约束选出了 #1。推导只负责确定类型，类型没有歧义就够了。

## 常见误解

!!! pitfall "`T&&` 一定是右值引用"
    在 `template<class T> void f(T&&)` 中，`T&&` 能绑定左值。和 `f(const T&)` 重载时，非 const 左值实参会选中 `T&&` 版本：`T` 推导为 `U&`，形参是 `U&`。两者都是引用绑定，但 `const U&` 引用的类型 cv 限定更多，按 [[over.ics.rank]] 排名更低。完美转发的构造函数会抢走拷贝构造，也是这个原因。

!!! pitfall "按值形参能推出 `const` 或数组类型"
    `template<class T> void f(T)` 永远推不出 `const`、引用或数组类型。要保留数组长度就写 `T(&)[N]` 或 `const T(&)[N]`；要保留一切就写 `T&&`。

!!! pitfall "`f({1, 2, 3})` 能推导出 `vector<int>`"
    `template<class T> void f(std::vector<T>)` 不接受 `f({1, 2, 3})`。`vector<T>` 不是 `initializer_list<T>` 或 `T[N]`，花括号列表让这个形参成为非推导语境，`T` 推不出来。应该写 `f<int>({1, 2, 3})` 或 `f(std::vector{1, 2, 3})`。

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

不能。第一对中 `i` 是左值，`A` 换成 `int&`，推导出 `T = int&`；第二对中 `0` 是右值，推导出 `T = int`。两对结果不同，推导失败（[[temp.deduct.type#2]]）。转发引用把值类别记在 `T` 里，几个转发引用形参共用一个 `T` 时，实参的值类别也必须一致。通常应该写成 `template<class T, class U> void f(T&&, U&&)`。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> void f(const T& a, const T& b);
    f("ab", "abc");
    ```
    能编译吗？把形参改成按值 `f(T a, T b)` 呢？

<details markdown="1">
<summary>答案</summary>

按引用时不能。`P` 是引用，数组不退化（¶2 只适用于非引用的 `P`）。第一对推导出 `T = char[3]`，第二对推导出 `T = char[4]`，冲突。

按值时可以。按 ¶2.1 数组退化为 `const char*`，两对都推导出 `T = const char*`。所以 `std::max("ab", "abc")` 编译失败（`max` 的形参是 `const T&`），而按值的版本能编译，只不过比较的是两个指针，结果几乎肯定不是想要的。本机 Clang 23 的结果与此一致。
</details>
