---
title: decltype 说明符
summary: decltype(E) 的七条规则：不加括号的名字/成员访问取实体的声明类型，其他表达式按值类别得到 T&& / T& / T；结构化绑定与模板参数的特例；prvalue 操作数不做临时量实质化，因而允许不完整类型、抽象类和被弃置的析构函数
status: done
since: c++11
papers: N3276
related: basic.lval, expr.prim.id.unqual, expr.context, conv.rval, dcl.spec.auto, dcl.struct.bind, temp.deduct
tags: 声明, 类型推导, decltype, 值类别
updated: 2026-10-17
---

`decltype(E)` 给出表达式 E 的声明类型。它是 C++11 为泛型编程引入的工具，用来在模板中写出 `a + b` 的类型、`f(args...)` 的返回类型之类的东西；在 C++03 中，这些只能依靠 `typeof` 扩展或复杂的 traits 来实现。

`decltype` 的规则只有寥寥几条，但有一个著名的特点：**加不加括号，结果不同**。`decltype(x)` 是 `x` 被声明的类型，`decltype((x))` 却是 `x` 作为表达式的类型再加上值类别（通常是左值引用）。理解这一点的关键在于，`decltype` 实际上是把两个操作合在了一个关键字里：

1. 查询实体的声明类型，用于不加括号的名字或不加括号的成员访问；
2. 查询表达式的类型和值类别，用于其他所有表达式，并把值类别编码进引用：xvalue 对应 `T&&`，lvalue 对应 `T&`，prvalue 对应 `T`。

阅读本节之前，需要了解值类别（[[basic.lval]]）、名字表达式的类型（[[expr.prim.id.unqual]]）、不求值操作数（[[expr.context]]）和临时量实质化（[[conv.rval]]）。

## 七条规则（¶1）

¶1 规定，对表达式 E，`decltype(E)` 按顺序取第一条适用的规则：

| ¶ | 条件 | `decltype(E)` |
|---|---|---|
| 1.1 | E 是不加括号的 *id-expression*，指名一个结构化绑定 | 结构化绑定声明中规定的被引用类型（referenced type） |
| 1.2 | E 是不加括号的 *id-expression*，指名一个常量模板参数 | 该模板参数的类型（经过必要的 `auto` / CTAD 推导之后） |
| 1.3 | E 是不加括号的 *id-expression* 或不加括号的类成员访问 | E 所指名实体的类型；若没有这样的实体，非良构 |
| 1.4 | E 是不加括号的 *splice-expression* {{c++26}} | 拼接所指代的实体、对象或值的类型 |
| 1.5 | E 是 xvalue | `T&&`（T 是 E 的类型） |
| 1.6 | E 是 lvalue | `T&` |
| 1.7 | 否则（prvalue） | `T` |

`decltype` 的操作数是不求值操作数，不会产生副作用，也不 odr-use 其中的实体（[[basic.def.odr]]）。

### 名字与成员访问（¶1.3）

```cpp run ok
#include <type_traits>
#include <utility>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;

const int&& foo();
int i;
struct A { double x; };
const A* a = new A();

static_assert(same<decltype(foo()), const int&&>);  // 1.5: 调用返回右值引用 → xvalue
static_assert(same<decltype(i), int>);              // 1.3: 实体 i 的声明类型
static_assert(same<decltype((i)), int&>);           // 1.6: (i) 是左值表达式
static_assert(same<decltype(a->x), double>);        // 1.3: 成员 x 的声明类型（不管 a 指向 const）
static_assert(same<decltype((a->x)), const double&>);  // 1.6: 表达式 a->x 是 const double 左值
int main() { }
```

最后两行最能说明两种模式的差别。把 `a->x` 当作实体，它是 `A::x`，声明为 `double`；把它当作表达式，由于 `a` 是 `const A*`，`a->x` 的类型是 `const double`，值类别是左值，于是 `decltype((a->x))` 是 `const double&`。

为什么要这样设计？在 [[N3276]] 之前关于 decltype 提案的讨论中，人们发现两种需求都存在：

- 写转发包装，或者声明一个与某个变量同类型的变量时，需要的是声明类型（`decltype(x) y;`）。这时引用性和 const 性应当和声明完全一致，不应凭空多出 `&`；
- 写 `auto f(T t) -> decltype(t.get())` 这类返回类型时，需要的是表达式类型加值类别，以便准确保留返回的是引用还是值。

用括号区分两者是一种折中：不加括号的单个名字视为实体，其余一切视为表达式。

### 更多例子：表达式模式

```cpp run ok
#include <type_traits>
#include <utility>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i;
int arr[3];
int f();
int&& rr();
struct S { int m; int bf : 3; };
enum E { e1 };

static_assert(same<decltype(i++), int>);             // 后缀 ++ 结果是 prvalue
static_assert(same<decltype(++i), int&>);            // 前缀 ++ 结果是 lvalue
static_assert(same<decltype(i = 1), int&>);          // 赋值结果是 lvalue
static_assert(same<decltype(std::move(i)), int&&>);  // xvalue
static_assert(same<decltype(42), int>);              // 字面量是 prvalue
static_assert(same<decltype("abc"), const char(&)[4]>);   // 字符串字面量是 lvalue！
static_assert(same<decltype(arr), int[3]>);          // 1.3：不退化
static_assert(same<decltype(arr[0]), int&>);         // 下标是 lvalue
static_assert(same<decltype(f), int()>);             // 1.3：函数类型
static_assert(same<decltype((f)), int(&)()>);        // 函数左值
static_assert(same<decltype(f()), int>);
static_assert(same<decltype(rr()), int&&>);
static_assert(same<decltype(true ? i : 1), int>);    // 条件表达式：一侧是 prvalue → prvalue
static_assert(same<decltype(true ? i : i), int&>);   // 两侧都是 int 左值 → lvalue
static_assert(same<decltype(S{}.m), int>);           // 1.3：成员访问，实体的声明类型
static_assert(same<decltype((S{}.m)), int&&>);       // 临时对象的成员是 xvalue
static_assert(same<decltype(S{}.bf), int>);          // 位域：声明类型
static_assert(same<decltype(e1), E>);                // 枚举项是实体，类型为 E
static_assert(same<decltype((e1)), E>);              // 枚举项表达式是 prvalue → E
int main() { }
```

（对于 `decltype(i++)` 之类的写法，Clang 会给出 `-Wunevaluated-expression` 警告，提醒其中的副作用不会发生。）

### 类成员访问与 this

在成员函数中，名字 `m` 会隐式转换为 `this->m`（[[class.mfct.non.static]]）。它仍然是不加括号的 *id-expression*，所以适用 1.3：

```cpp run ok
#include <type_traits>
struct W {
    int m;
    void cf() const {
        static_assert(std::is_same_v<decltype(m), int>);            // 实体 W::m 的声明类型
        static_assert(std::is_same_v<decltype((m)), const int&>);   // this 是 const W*，(m) 是 const 左值
        static_assert(std::is_same_v<decltype(this), const W*>);    // this 是 prvalue
    }
};
int main() { W{1}.cf(); }
```

### lambda 中的捕获

在 lambda 体中，被复制捕获的变量名有特殊处理（[[expr.prim.id.unqual]]）。作为 *id-expression*，它仍然指名原来的变量，1.3 给出原变量的声明类型；加上括号后，表达式被当作对闭包对象成员的访问，而默认的 `operator()` 是 const 的：

```cpp run ok
#include <type_traits>
int main() {
    int loc = 0;
    auto l = [loc] {
        static_assert(std::is_same_v<decltype(loc), int>);            // 原变量的声明类型
        static_assert(std::is_same_v<decltype((loc)), const int&>);   // 像是访问 const 闭包的成员
        return loc;
    };
    return l();
}
```

### 结构化绑定（¶1.1）

结构化绑定不是变量，而是某个隐藏对象（或其子对象）的名字。¶1.1 让 `decltype` 返回 [[dcl.struct.bind]] 中规定的被引用类型：对于绑定到类成员的情形，就是成员的声明类型（带上 cv）；对于 tuple-like 绑定，是 `std::tuple_element<i, E>::type`：

```cpp run ok
#include <type_traits>
#include <tuple>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int g = 0;
int main() {
    std::tuple<int, int&> tp{1, g};
    auto [p, q] = tp;
    static_assert(same<decltype(p), int>);      // tuple_element<0>::type
    static_assert(same<decltype(q), int&>);     // tuple_element<1>::type 本身是引用
    static_assert(same<decltype((p)), int&>);   // 加括号：普通的左值表达式

    struct S { int x; const int y; } s{1, 2};
    auto& [sx, sy] = s;
    static_assert(same<decltype(sx), int>);         // 即使用 auto& 绑定，也不是 int&
    static_assert(same<decltype(sy), const int>);   // 成员的声明类型（含 const）
    return p - 1;
}
```

注意在 `auto& [sx, sy] = s;` 中，`decltype(sx)` 是 `int` 而不是 `int&`。`&` 作用于隐藏的对象 `e`（`e` 的类型是 `S&`），而 `sx` 本身只是 `e.x` 的名字，其被引用类型就是 `int`。

### 常量模板参数（¶1.2）

```cpp run ok
#include <type_traits>
struct C { int v; };
template<auto N> void t() {
    static_assert(std::is_same_v<decltype(N), int>);     // 1.2：推导出的参数类型
    static_assert(std::is_same_v<decltype((N)), int>);   // 标量 NTTP 是 prvalue
}
template<C c> void u() {
    static_assert(std::is_same_v<decltype(c), C>);           // 1.2
    static_assert(std::is_same_v<decltype((c)), const C&>);  // 类类型 NTTP 是 const 左值（模板参数对象）
}
int main() { t<1>(); u<C{1}>(); }
```

¶1.2 之所以单列，是因为常量模板参数不是实体意义上的变量：标量类型的常量模板参数在表达式中是 prvalue，类类型的常量模板参数则是指向模板参数对象的 const 左值（[[temp.param]]）。1.2 统一给出（推导之后的）声明类型，加括号时则按值类别规则处理。

### 没有实体时（¶1.3 后半）

1.3 的后半句规定，如果没有这样的实体，程序非良构。最典型的情形是重载集：`decltype(ov)` 中的 `ov` 指名多个函数，没有唯一的实体。

```cpp error
void ov(int);
void ov(double);
using T = decltype(ov);     // error: 重载函数名无法确定为一个实体
```

### 拼接表达式（¶1.4）{{c++26}}

在标准例子中，x1 是 `const int&&` 类型的变量，`decltype([:^^x1:])` 是 `const int&&`，而 `decltype(([:^^x1:]))` 是 `const int&`。不加括号的拼接表达式与不加括号的名字一样，取实体的声明类型。（本机 Clang 尚未实现反射，未验证。）

### 包索引表达式

标准例子中还有 `decltype(pack...[0])`。包索引表达式（[[expr.prim.pack.index]]）在不加括号时被视为 *id-expression*，于是取实体（第 0 个参数）的声明类型 `int`；加括号则得到 `int&`。

```cpp run ok
#include <type_traits>
void f() {
    [](auto... pack) {
        static_assert(std::is_same_v<decltype(pack...[0]), int>);
        static_assert(std::is_same_v<decltype((pack...[0])), int&>);
    }(0);
}
int main() { f(); }
```

## prvalue 操作数：不做临时量实质化（¶2）

¶2 规定，如果 `decltype` 的操作数是 prvalue，且不是（可能加括号的）立即调用，就不应用临时量实质化转换（[[conv.rval]]），也不为这个 prvalue 提供结果对象。此时 prvalue 的类型可以是不完整类型或抽象类类型。

Note 2 解释了其后果：既然没有为 prvalue 分配存储，也就不需要销毁它。因此，函数调用的返回类型不会因为出现在这里而被实例化，也不需要检查析构函数是否可访问、是否被弃置。`decltype` 在这里的作用就像一个 typedef 名，写这个表达式只是为了得到它的类型。

Note 3 指出，与 ¶1 不同，**括号在这里没有特殊意义**：`decltype((f()))` 同样不做实质化。

```cpp run ok
struct Incomplete;
Incomplete make();
using T1 = decltype(make());          // OK: 不完整类型
T1* p = nullptr;

struct Abstract { virtual void f() = 0; };
Abstract mk_abs();                    // 声明返回抽象类的函数本身就不常见，但……
using T2 = decltype(mk_abs());        // OK: 抽象类类型的 prvalue

struct NoDtor { ~NoDtor() = delete; };
NoDtor mk();
using T3 = decltype(mk());            // OK: 析构函数被弃置也无所谓
using T4 = decltype((mk()));          // OK: 括号无影响
using T5 = decltype(0, mk());         // OK: 整个逗号表达式的结果仍是这个 prvalue
int main() { }
```

但是，只要 prvalue 被用作另一个操作的操作数、需要一个对象，就会发生实质化，这条规则也就不再起保护作用：

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor mk();
void take(NoDtor);
using T6 = decltype(take(mk()));      // error: mk() 初始化形参对象，形参的析构函数被使用
using T7 = decltype(mk(), 0);         // error: 逗号左操作数是弃值表达式，prvalue 被实质化
```

`take(mk())` 的情形值得细说。C++17 起，`mk()` 直接初始化形参，不产生临时对象，但形参对象的析构由调用方负责（[[expr.call]]），所以析构函数仍然被使用。

### 为什么需要这条规则：标准例子

```cpp
template<class T> struct A { ~A() = delete; };
template<class T> auto h() -> A<T>;
template<class T> auto i(T) -> T;          // 恒等函数
template<class T> auto f(T) -> decltype(i(h<T>()));   // #1
template<class T> auto f(T) -> void;                  // #2
auto g() -> void {
    f(42);    // OK: 调用 #2
}
```

在 `#1` 的返回类型中，`h<T>()` 是 `i` 的实参，它会被实质化为临时对象来初始化 `i` 的参数，这就要求 `A<T>` 完整，并且要使用被弃置的 `A<T>::~A()`。于是替换失败（SFINAE，[[temp.deduct]]），`#1` 不可行，选中 `#2`。但 `i(h<T>())` 本身作为 `decltype` 的直接操作数，不会再引入临时量。

```cpp
template<class T> auto q(T) -> decltype((h<T>()));   // 不要求 A<T> 完整，也不使用析构函数
void r() {
    q(42);    // error: 推导成功，选中 q<int>，其返回类型是 A<int>；
              // 调用表达式产生了临时对象，析构函数被使用 → 非良构
}
```

这条规则（[[N3276]]，在 C++11 定稿前加入）最初的动机是表达式模板与递归的返回类型推导。在 `auto f(...) -> decltype(g(...))` 这种链式写法中，如果每一层 `decltype` 都要求返回类型完整，就会触发大量不必要的类模板实例化，甚至无限递归。

!!! lawyer "立即调用例外的适用范围"
    ¶2 把（可能加括号的）立即调用排除在外，对这种 prvalue 仍然要做临时量实质化。但按当前 [[expr.const.imm#1]] 的定义，立即调用必须是潜在求值的调用，而 `decltype` 的操作数是不求值操作数，所以从字面上看，`decltype` 的操作数本身似乎永远不会是立即调用。这一例外实际适用于什么情形，值得进一步核对；可能涉及 `decltype` 位于其他求值上下文中的嵌套情形，也可能是历史措辞的遗留。

## decltype 与 decltype(auto)

Note 1 指出，`decltype(auto)` 的规则在 [[dcl.spec.auto]]（[[dcl.type.auto.deduct#4]]）中：它把初始化器当作 `decltype` 的操作数来推导类型。所以上面所有规则，包括括号的影响，都原样适用于 `decltype(auto)`：

```cpp run ok
#include <type_traits>
int x = 0;
decltype(auto) a = x;      // int
decltype(auto) b = (x);    // int&  —— 一对括号的差别
static_assert(std::is_same_v<decltype(a), int> && std::is_same_v<decltype(b), int&>);
int main() { }
```

!!! pitfall "decltype(auto) 返回类型中的括号"
    ```cpp
    decltype(auto) get() { static int v = 0; return v; }     // 返回 int
    decltype(auto) get_ref() { static int v = 0; return (v); }   // 返回 int&
    decltype(auto) danger() { int v = 0; return (v); }       // 返回 int&&（C++23 起，见下）——悬垂引用
    ```

    再看第三个函数。C++23 起（隐式移动规则简化之后），如果 `return (v);` 中的 `(v)` 指名局部变量，它就被视为 xvalue，于是 `decltype(auto)` 推导为 `int&&`；在 C++20 中则推导为 `int&`。无论哪种情况，返回的都是悬垂引用。参见 [[dcl.type.auto.deduct#4]] 中的 `f2` 例子。

## 实现视角

!!! impl "实现视角"
    - `decltype` 出现在函数模板的签名中时（尾置返回类型、模板参数默认值），其中的表达式会编码进 mangled 名。Itanium ABI 有两种编码：`Dt <expression> E` 对应不加括号的 id-expression 或成员访问，`DT <expression> E` 对应其他表达式，正好与 ¶1 的两种模式对应。因此 `decltype(x)` 与 `decltype((x))` 不仅类型可能不同，在签名中也是可以区分的两种写法。
    - GCC 在 C++11 之前提供 `typeof`/`__typeof__` 扩展，其行为大致相当于取表达式类型并去掉引用，与 `decltype` 不同。

!!! history "历史与演进"
    - C++11：引入 `decltype`；[[N3276]] 加入 prvalue 不实质化的规则。
    - C++14：`decltype(auto)`。
    - C++17：结构化绑定，加入 ¶1.1。
    - C++17/20：`auto` 常量模板参数（C++17）、类类型常量模板参数与 CTAD 占位符形式的模板参数（C++20）。它们的声明类型需要推导，¶1.2 专门处理这种情形。
    - C++23：`return (x);` 中的局部变量是 xvalue（隐式移动规则简化），这影响 `decltype(auto)` 的推导结果。
    - C++26：包索引（`pack...[I]`）、拼接表达式（¶1.4）。

!!! summary "小结"
    - 不加括号的名字、成员访问、结构化绑定、NTTP、拼接表达式，得到的是声明类型。
    - 其他表达式：xvalue 得到 `T&&`，lvalue 得到 `T&`，prvalue 得到 `T`。
    - 操作数不求值；prvalue 操作数不做实质化，因此允许不完整类型、抽象类、被弃置的析构函数，但这只限于 `decltype` 的直接操作数。
    - `decltype(auto)` 继承所有这些规则，包括括号的影响。

!!! question "思考题 1"
    设 `struct S { int m; }; const S cs{}; S&& rs();`。写出 `decltype(cs.m)`、`decltype((cs.m))`、`decltype(rs().m)`、`decltype((rs().m))`。

<details markdown="1">
<summary>答案</summary>

- `decltype(cs.m)`：不加括号的成员访问，取成员的声明类型 `int`。
- `decltype((cs.m))`：`cs.m` 是 `const int` 左值，得到 `const int&`。
- `decltype(rs().m)`：不加括号的成员访问，得到 `int`。
- `decltype((rs().m))`：`rs()` 是 xvalue，对它的成员访问也是 xvalue（[[expr.ref]]），得到 `int&&`。
</details>

!!! question "思考题 2"
    为什么 `template<class T> auto f(T t) -> decltype(t.size(), void())` 是常见的 SFINAE 写法？`decltype(void(t.size()))` 有什么不同？

<details markdown="1">
<summary>答案</summary>

逗号表达式让 `t.size()` 参与替换（不合法则 SFINAE），而整个 `decltype` 的结果是右操作数 `void()` 的类型 `void`。注意，`t.size()` 作为逗号的左操作数是弃值表达式，如果它返回一个类类型的 prvalue，就会被实质化，从而要求该类型完整且可析构（本节 ¶2 不保护它）。另一个潜在问题是，如果 `t.size()` 的类型重载了逗号运算符，`, void()` 就可能调用到它；用 `void()` 作右操作数正是为了避免这一点，因为 `void` 类型的操作数不能传给用户定义的逗号运算符。`decltype(void(t.size()))` 把 `t.size()` 转换为 `void`，同样是弃值表达式，效果基本相同，而且不用顾虑逗号运算符重载。
</details>
