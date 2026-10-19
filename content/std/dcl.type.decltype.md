---
title: decltype 说明符
summary: decltype(e) 得到什么类型：不加括号的名字和成员访问取声明类型，其他表达式按值类别得到 T&&、T& 或 T；prvalue 操作数不创建临时对象，所以允许不完整类型和被弃置的析构函数。
status: done
since: c++11
papers: N3276
related: basic.lval, expr.prim.id.unqual, expr.context, conv.rval, dcl.spec.auto, dcl.struct.bind, temp.deduct
tags: 声明, 类型推导, decltype, 值类别
updated: 2026-10-19
---

!!! tldr
    - `decltype(x)` 是变量 `x` 声明时的类型；`decltype((x))` 把 `(x)` 当作表达式，左值得到 `T&`。一对括号就能改变结果。
    - 对一般的表达式，`decltype` 把值类别编码进引用：xvalue 得到 `T&&`，lvalue 得到 `T&`，prvalue 得到 `T`。
    - 结构化绑定、常量模板参数、拼接表达式不加括号时也取声明类型，各有专门的规则。
    - `decltype` 的操作数不求值。操作数是 prvalue 时不创建临时对象，所以类型可以不完整，析构函数可以被弃置，但这只对最外层的那个 prvalue 成立。
    - `decltype(auto)` 照搬这套规则，所以 `return (v);` 会让它推导出引用。

## 一对括号的差别 ¶1

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;

int i;
struct A { double x; };
const A* a = new A();

static_assert(same<decltype(i), int>);                 // 变量 i 的声明类型
static_assert(same<decltype((i)), int&>);              // 表达式 (i) 是左值
static_assert(same<decltype(a->x), double>);           // 成员 A::x 的声明类型
static_assert(same<decltype((a->x)), const double&>);  // a 指向 const，表达式是 const 左值
int main() {}
```

`decltype` 其实把两种查询放进了一个关键字。操作数是不加括号的名字或成员访问时，它查的是这个名字所指实体的**声明类型**：`A::x` 声明为 `double`，`a` 指向 const 也不影响。操作数是其他任何表达式时（加一对括号就算），它查的是表达式的类型和**值类别**（value category）。值类别是表达式的一种分类（[[basic.lval]]）：lvalue 指代一个有身份的对象或函数，xvalue 指代一个可以被移走资源的对象（如 `std::move(x)` 的结果），prvalue 是用来初始化对象的纯值（如 `42`、`f()` 返回的非引用值）。

两种需求都真实存在。声明一个和 `x` 同类型的变量（`decltype(x) y;`）时，要的是声明类型，不能凭空多出 `&`；写 `auto f(T t) -> decltype(t.get())` 时，要的是表达式的类型和值类别，才能准确保留返回的是引用还是值。用括号区分两者是一种折中：不加括号的单个名字当作实体，其余一律当作表达式。

¶1 对表达式 E，`decltype(E)` 按顺序取第一条适用的规则：

| ¶ | E 的形式 | `decltype(E)` |
|---|---|---|
| 1.1 | 不加括号的名字，指名结构化绑定 | 结构化绑定声明中规定的被引用类型 |
| 1.2 | 不加括号的名字，指名常量模板参数 | 模板参数的类型（完成 `auto` 或 CTAD 推导之后） |
| 1.3 | 不加括号的名字，或不加括号的类成员访问 | 所指实体的类型；没有这样的实体时非良构 |
| 1.4 | 不加括号的拼接表达式 {{c++26}} | 拼接所指的实体、对象或值的类型 |
| 1.5 | xvalue | `T&&`，T 是 E 的类型 |
| 1.6 | lvalue | `T&` |
| 1.7 | 其他（prvalue） | `T` |

`decltype` 的操作数是**不求值操作数**（unevaluated operand，[[expr.context]]）：它只用来确定类型，不会执行，也不算对其中的变量和函数的 odr-use（[[basic.def.odr]]）。

### 表达式：值类别变成引用（¶1.5–¶1.7）

```cpp run ok
#include <type_traits>
#include <utility>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i;
int arr[3];
int f();
int&& rr();
struct S { int m; };
enum E { e1 };

static_assert(same<decltype(i++), int>);           // 后缀 ++ 是 prvalue
static_assert(same<decltype(++i), int&>);          // 前缀 ++ 是 lvalue
static_assert(same<decltype(i = 1), int&>);        // 赋值是 lvalue
static_assert(same<decltype(std::move(i)), int&&>);
static_assert(same<decltype(rr()), int&&>);        // 返回右值引用的调用是 xvalue
static_assert(same<decltype(f()), int>);
static_assert(same<decltype("abc"), const char(&)[4]>);  // 字符串字面量是 lvalue
static_assert(same<decltype(arr), int[3]>);        // 1.3：不退化成指针
static_assert(same<decltype(arr[0]), int&>);
static_assert(same<decltype(f), int()>);           // 1.3：函数类型
static_assert(same<decltype((f)), int(&)()>);
static_assert(same<decltype(true ? i : 1), int>);  // 一侧是 prvalue，结果是 prvalue
static_assert(same<decltype(true ? i : i), int&>);
static_assert(same<decltype((S{}.m)), int&&>);     // 临时对象的成员是 xvalue
static_assert(same<decltype((e1)), E>);            // 枚举项是 prvalue
int main() {}
```

`decltype(i++)` 这类写法，Clang 会给出 `-Wunevaluated-expression` 警告，提醒其中的副作用不会发生。

### 名字与成员访问（¶1.3）

在成员函数里，成员名 `m` 会被隐式改写成 `this->m`（[[class.mfct.non.static]]），但它在源码里仍然是不加括号的名字，所以取声明类型。lambda 中复制捕获的变量也类似：不加括号时 `decltype` 取原变量的声明类型；加了括号，就当作访问闭包对象的成员，而默认的 `operator()` 是 const 的（[[expr.prim.id.unqual]]）。

```cpp run ok
#include <type_traits>
struct W {
    int m;
    void cf() const {
        static_assert(std::is_same_v<decltype(m), int>);
        static_assert(std::is_same_v<decltype((m)), const int&>);  // this 是 const W*
    }
};
int main() {
    W{1}.cf();
    int loc = 0;
    auto l = [loc] {
        static_assert(std::is_same_v<decltype(loc), int>);
        static_assert(std::is_same_v<decltype((loc)), const int&>);
        return loc;
    };
    return l();
}
```

¶1.3 的后半句规定，名字没有指名一个实体时非良构。典型情形是重载集：`ov` 指名两个函数，没有唯一的类型。

```cpp error
void ov(int);
void ov(double);
using T = decltype(ov);   // error: 重载函数名
```

### 结构化绑定（¶1.1）

结构化绑定不是变量，而是某个隐藏对象（或它的成员）的别名。¶1.1 让 `decltype` 返回 [[dcl.struct.bind]] 规定的被引用类型：绑定到类成员时是成员的声明类型（带上隐藏对象的 cv），tuple 式绑定时是 `std::tuple_element<i, E>::type`。

```cpp run ok
#include <type_traits>
#include <tuple>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int g = 0;
int main() {
    std::tuple<int, int&> tp{1, g};
    auto [p, q] = tp;
    static_assert(same<decltype(p), int>);     // tuple_element<0>::type
    static_assert(same<decltype(q), int&>);    // tuple_element<1>::type 本身是引用
    static_assert(same<decltype((p)), int&>);  // 加括号：普通左值

    struct S { int x; const int y; } s{1, 2};
    auto& [sx, sy] = s;
    static_assert(same<decltype(sx), int>);        // 不是 int&
    static_assert(same<decltype(sy), const int>);
    return p - 1;
}
```

`auto& [sx, sy] = s;` 中的 `&` 修饰的是隐藏对象 `e`（类型 `S&`），`sx` 只是 `e.x` 的名字，被引用类型是 `int`。

### 常量模板参数（¶1.2）

```cpp run ok
#include <type_traits>
struct C { int v; };
template<auto N> void t() {
    static_assert(std::is_same_v<decltype(N), int>);    // 推导出的类型
    static_assert(std::is_same_v<decltype((N)), int>);  // 标量参数是 prvalue
}
template<C c> void u() {
    static_assert(std::is_same_v<decltype(c), C>);
    static_assert(std::is_same_v<decltype((c)), const C&>);  // 类类型参数是 const 左值
}
int main() { t<1>(); u<C{1}>(); }
```

常量模板参数不是变量。标量类型的参数在表达式里是 prvalue；类类型的参数指代一个**模板参数对象**（[[temp.param]]），是 const 左值。¶1.2 统一给出推导之后的声明类型，加括号时再按值类别处理。

### 包索引与拼接（¶1.3、¶1.4）

不加括号的包索引表达式 `pack...[0]`（[[expr.prim.pack.index]]）算作名字，取第 0 个形参的声明类型：

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

¶1.4 对 C++26 的拼接表达式 `[: r :]` 做同样的处理。标准的例子里 `x1` 是 `const int&&` 类型的变量，`decltype([:^^x1:])` 是 `const int&&`，`decltype(([:^^x1:]))` 是 `const int&`。本机 Clang 23 尚未实现反射，这一点没有验证。

## prvalue 操作数不创建临时对象（¶2）

```cpp run ok
struct Incomplete;
Incomplete make();
using T1 = decltype(make());     // OK: 不完整类型

struct Abstract { virtual void f() = 0; };
Abstract mk_abs();
using T2 = decltype(mk_abs());   // OK: 抽象类

struct NoDtor { ~NoDtor() = delete; };
NoDtor mk();
using T3 = decltype(mk());       // OK: 析构函数被弃置
using T4 = decltype((mk()));     // OK: 括号不影响
using T5 = decltype(0, mk());    // OK: 结果仍是这个 prvalue
int main() {}
```

¶2 如果 `decltype` 的操作数是 prvalue，就不对它做**临时量实质化**（temporary materialization，把 prvalue 变成一个临时对象的转换，[[conv.rval]]），也不为它提供结果对象。所以这个 prvalue 的类型可以不完整，也可以是抽象类。条文把（可能加括号的）立即调用排除在外；立即调用是对 `consteval` 函数的一类调用，精确定义见 [[expr.const.imm]]。

注 2 解释了后果：既然没有为 prvalue 分配存储，也就不需要销毁它，所以不必实例化返回的类模板，也不必检查析构函数能否调用。注 3 指出，与 ¶1 不同，这里括号没有特殊含义。

保护只对最外层的 prvalue 成立。prvalue 一旦被拿去初始化另一个对象，或者作为弃值表达式出现，就会被实质化：

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor mk();
void take(NoDtor);
using T6 = decltype(take(mk()));   // error: 形参对象需要析构
using T7 = decltype(mk(), 0);      // error: 逗号左边是弃值表达式，被实质化
```

`take(mk())` 中 `mk()` 直接初始化形参，不产生额外的临时对象，但形参对象要由调用方销毁（[[expr.call]]），析构函数仍然被使用。

### 这条规则为什么重要

标准的例 2 展示了它对重载决议的影响：

```cpp
template<class T> struct A { ~A() = delete; };
template<class T> auto h() -> A<T>;
template<class T> auto i(T) -> T;                      // 恒等函数
template<class T> auto f(T) -> decltype(i(h<T>()));   // #1
template<class T> auto f(T) -> void;                   // #2
auto g() -> void {
    f(42);    // OK: 调用 #2
}
template<class T> auto q(T) -> decltype((h<T>()));
void r() {
    q(42);    // error
}
```

`#1` 的返回类型里，`h<T>()` 是 `i` 的实参，要实质化成对象去初始化 `i` 的形参，这要求 `A<int>` 完整，并且使用了被弃置的析构函数。于是替换失败（SFINAE，[[temp.deduct]]），`#1` 被排除，选中 `#2`。`i(...)` 的结果本身是 `decltype` 的直接操作数，不会再引入临时对象。

`q` 的返回类型 `decltype((h<T>()))` 不要求 `A<T>` 完整，推导成功，选中 `q<int>`。但调用 `q(42)` 本身会产生一个 `A<int>` 临时对象，要使用它的析构函数，所以 `r` 非良构。

这条规则由 [[N3276]] 在 C++11 定稿前加入。它针对的是 `auto f(...) -> decltype(g(...))` 这类层层嵌套的返回类型：如果每一层都要求返回类型完整，就会触发大量不必要的类模板实例化，在表达式模板这样的递归结构中甚至会无限递归。

## decltype(auto)

注 1 指出，`decltype(auto)` 的规则在 [[dcl.type.auto.deduct#4]]：它把初始化器当作 `decltype` 的操作数来推导，所以括号的影响原样保留。

```cpp run ok
#include <type_traits>
int x = 0;
decltype(auto) a = x;     // int
decltype(auto) b = (x);   // int&
static_assert(std::is_same_v<decltype(a), int>);
static_assert(std::is_same_v<decltype(b), int&>);

decltype(auto) get_ref() { static int v = 0; return (v); }   // int&
static_assert(std::is_same_v<decltype(get_ref()), int&>);
int main() {}
```

!!! pitfall "返回局部变量时加了括号"
    `decltype(auto) danger() { int v = 0; return (v); }` 的返回类型，C++20 中是 `int&`；C++23 起 return 语句中指名局部变量的表达式是 xvalue（[[expr.prim.id.unqual]]），返回类型变成 `int&&`。两种情况返回的都是悬垂引用。

## 实现视角

!!! impl "decltype 与名字修饰"
    `decltype` 出现在函数模板签名里（尾置返回类型、模板参数的默认值）时，表达式会编码进修饰后的名字。Itanium ABI 有两种编码：`Dt <expression> E` 用于不加括号的名字或成员访问，`DT <expression> E` 用于其他表达式，正好对应 ¶1 的两种模式。所以 `decltype(x)` 和 `decltype((x))` 在签名中是可以区分的两种写法。

## 历史与演进

!!! history
    - C++11 引入 `decltype`；[[N3276]] 加入 prvalue 操作数不实质化的规则。
    - C++14 加入 `decltype(auto)`。
    - C++17 加入结构化绑定（¶1.1）和 `auto` 常量模板参数；C++20 加入类类型的常量模板参数，它们的类型都需要推导，由 ¶1.2 处理。
    - C++23 让 return 语句中的局部变量成为 xvalue，影响 `decltype(auto)` 的推导结果。
    - C++26 加入包索引和拼接表达式（¶1.4）。

## 思考题

!!! question "思考题 1"
    设 `struct S { int m; }; const S cs{}; S&& rs();`。写出 `decltype(cs.m)`、`decltype((cs.m))`、`decltype(rs().m)`、`decltype((rs().m))`。

<details markdown="1">
<summary>答案</summary>

- `decltype(cs.m)`：不加括号的成员访问，取成员的声明类型 `int`。
- `decltype((cs.m))`：`cs.m` 是 `const int` 左值，得到 `const int&`。
- `decltype(rs().m)`：仍是不加括号的成员访问，得到 `int`。
- `decltype((rs().m))`：`rs()` 是 xvalue，它的成员也是 xvalue（[[expr.ref]]），得到 `int&&`。
</details>

!!! question "思考题 2"
    SFINAE 检测里常写 `template<class T> auto f(T t) -> decltype(t.size(), void())`。右操作数为什么写 `void()`？换成 `decltype(void(t.size()))` 有什么不同？

<details markdown="1">
<summary>答案</summary>

`t.size()` 不合法时替换失败，`f` 被排除；合法时整个 `decltype` 的结果是右操作数的类型 `void`。

右操作数写成 `void()`，是为了防止调用到用户重载的逗号运算符：如果 `t.size()` 的返回类型重载了 `operator,`，而右操作数的类型是 `void`，那么任何用户定义的 `operator,` 都无法接受它，只能使用内建的逗号运算符（[[over.match.oper]]）。

`decltype(void(t.size()))` 把 `t.size()` 转换为 `void`，没有逗号运算符的问题，效果相同。两种写法里 `t.size()` 都是弃值表达式，所以如果它返回类类型的 prvalue，都会被实质化，要求这个类型完整、析构函数可用；¶2 的保护不覆盖它。
</details>
