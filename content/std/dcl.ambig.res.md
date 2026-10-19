---
title: 歧义消解
summary: 函数式转换和声明写法相同时怎样取舍：能读成声明的就是声明，能读成 type-id 的就是 type-id。包括最令人烦恼的解析、模板实参与 sizeof 中的歧义，以及形参里被括起来的类型名。
status: draft
related: stmt.ambig, dcl.decl, dcl.name, dcl.fct, expr.type.conv, expr.sizeof, expr.cast, temp.arg.general, dcl.init
tags: 歧义, most vexing parse, 文法, type-id
updated: 2026-10-19
---

!!! tldr
    - `T(x)` 既可以是把 `x` 转换成 `T` 的表达式，也可以是声明变量 `x`（名字外多了一对括号）。标准的规则是：能读成声明的，就是声明。
    - 所以 `S v(int(a));` 和 `Widget w();` 声明的都是函数。改用花括号、多加一层括号或者写 `=`，就能得到对象。
    - 在既能写类型又能写表达式的地方（模板实参、`typeid`），能读成 type-id 的就是 type-id，因此 `Y<int()>` 对非类型模板形参是错误的。
    - 当前草案中 `sizeof`、`alignof` 和 C 风格转换只接受不能表示函数类型的 *nofun-type-id*，`sizeof(int())` 因此变成了表达式。本机 Clang 23 仍按旧规则报错。
    - 形参列表里被括起来的类型名按类型处理：`void f(int(C));` 的形参是函数指针，不是名为 `C` 的 `int`。

## 歧义从哪里来

C++ 有函数式类型转换 `T(x)`（[[expr.type.conv]]），又继承了 C 的声明符文法，而声明符可以随意加括号（[[dcl.decl]]）：`int (a)` 就是 `int a`。于是同一串记号常有两种读法：

| 记号 | 表达式读法 | 声明读法 |
|---|---|---|
| `int(a)` | 把 `a` 转换成 `int` | 名为 `a` 的 `int`，名字外有冗余括号 |
| `int()` | 值初始化的 `int`，值为 0 | 无形参、返回 `int` 的函数类型 |

文法本身分不出来，标准只能给出偏好规则。整条语句是表达式语句还是声明语句的歧义在 [[stmt.ambig]] 处理；本节处理出现在声明内部的三种歧义，规则的思路都一样。

## 对象还是函数（¶1）

```cpp run ok
#include <type_traits>
struct S { S(int); };
typedef struct BB { int C[2]; } *B, C;

void foo(double a) {
  S v(int(a));      // 函数声明：S v(int a)
  S w(int());       // 函数声明：形参是返回 int 的函数，调整为 int(*)()
  S x((int(a)));    // 对象声明
  S y((int)a);      // 对象声明
  S z = int(a);     // 对象声明
  S b(auto()->C);   // 函数声明：形参是返回 C 的函数，调整为 C(*)()

  static_assert(std::is_same_v<decltype(v), S(int)>);
  static_assert(std::is_same_v<decltype(w), S(int (*)())>);
  static_assert(std::is_same_v<decltype(b), S(C (*)())>);
}
int main() { }
```

¶1 `S v(int(a));` 可以是用 `int(a)` 初始化的对象 `v`，也可以是一个函数 `v`，它的形参写成 `int(a)`，即 `int a` 加了冗余括号。和 [[stmt.ambig]] 一样，标准规定任何可能是声明的结构都当作声明，所以 `v` 是函数。

`S w(int())` 也是函数。`int()` 作为抽象声明符表示返回 `int` 的函数类型，用作形参类型时按 [[dcl.fct#5]] 调整为函数指针 `int(*)()`。

`x`、`y`、`z` 是对象，因为外层多一对括号的 `(int(a))`、C 风格转换 `(int)a` 都不可能是形参声明，复制初始化 `= int(a)` 也不会被读成声明。

### 尾置返回类型的形式要以 auto 开头

¶1 的最后一句处理一种特殊形式：如果一个结构在语法上可以是声明，并且最外层声明符可以匹配带尾置返回类型的声明符文法，那么只有以 `auto` 开头时它才是声明。

```cpp run error
struct S { S(int); };
typedef struct BB { int C[2]; } *B, C;
void foo() {
  S a(B()->C);   // 对象声明：B() 不以 auto 开头
}                // error: 但 S 不能用 int[2] 初始化
```

`B()->C` 在文法上可以读成形参类型 `B() -> C`，也就是返回 `C` 的函数。但尾置返回类型要求说明符是单独的 `auto`（[[dcl.fct#1]]），这种读法注定非良构。如果没有这一句，能读成声明就读成声明的规则会选中它，把一个可能合法的表达式变成错误。加上这一句后，`B()->C` 按表达式读：`B()` 是值初始化的空指针，`->C` 访问成员数组。这个例子最终仍然报错，但错误发生在语义上（`S` 没有接受 `int*` 的构造函数），不在解析上。`S b(auto()->C)` 以 `auto` 开头，所以仍是函数声明。

### 最令人烦恼的解析

这条规则最出名的后果叫[[g:most-vexing-parse|最令人烦恼的解析]]（most vexing parse）：本想构造对象，结果声明了函数。

```cpp run error
#include <iterator>
#include <sstream>
#include <vector>

struct Timer { };
struct TimeKeeper { TimeKeeper(Timer); int get(); };

int f() {
  TimeKeeper tk(Timer());   // 函数声明：形参类型是 Timer(*)()
  return tk.get();          // error: tk 是函数
}

void g(std::istringstream& in) {
  std::vector<int> v(std::istream_iterator<int>(in),
                     std::istream_iterator<int>());
  v.size();                 // error: v 是函数
}
```

第一个形参 `std::istream_iterator<int>(in)` 读成名为 `in` 的形参，第二个读成函数指针形参。Clang 对这两处都给出 `-Wvexing-parse` 警告（parentheses were disambiguated as a function declaration）；GCC 也有同名的警告。

注 1 给出了消歧的方法，概括起来就是写出一个不可能是声明的形式：

| 写法 | 结果 |
|---|---|
| `S x{int(a)};` | 对象：列表初始化，C++11 起的首选 |
| `S x((int(a)));` | 对象：多一层括号就不可能是形参 |
| `S x = int(a);` | 对象：复制初始化 |
| `S x((int)a);`、`S x(static_cast<int>(a));` | 对象：不是函数式转换 |
| `S x(int(a));` | 函数 |
| `S x();` | 函数（[[dcl.init#15]] 的注也专门指出了这一点） |

上面两个例子可以改成 `TimeKeeper tk{Timer{}};` 和 `std::vector<int> v{std::istream_iterator<int>(in), {}};`。

!!! pitfall "没有加锁的锁"
    语句层面（[[stmt.ambig]]）也有同类问题：
    ```cpp
    std::lock_guard<std::mutex>(m);   // 声明了一个名为 m 的 lock_guard 变量
    ```
    这条语句能读成声明，所以它声明了一个默认构造的局部变量 `m`，遮住了外层的互斥量。`lock_guard` 没有默认构造函数，所以这里碰巧报错；如果守卫类型可以默认构造，程序就会安静地编译通过，却根本没有加锁。应写成 `std::lock_guard g(m);` 或 `std::scoped_lock g{m};`。

## type-id 还是表达式（¶2）

### 模板实参与 typeid

¶2 第二种歧义出现在既能写 *type-id*（类型名，见 [[dcl.name]]）又能写表达式的地方，比如模板实参和 `typeid(…)`。规则是：在这个语法位置上可能是 type-id 的，就是 type-id。

这里的可能指语法上可能。`int(1)` 不可能是 type-id，因为 `1` 不能出现在声明符里，所以它一定是表达式。`int()` 可以是 type-id（函数类型），所以它就是 type-id，哪怕函数类型在这里没有意义：

```cpp run error
template <class T> struct X {};
template <int N> struct Y {};

X<int()> a;    // type-id：T = int()，OK
X<int(1)> b;   // 表达式：error，X 需要类型
Y<int()> c;    // type-id：error，Y 需要值
Y<int(1)> d;   // 表达式：N = 1，OK
```

`Y<int()>` 体现了这条规则的代价：作者显然想要 `Y<0>`，但解析时并不看模板形参是哪一种。Clang 的诊断是 template argument for non-type template parameter is treated as function type 'int ()'。

### sizeof、alignof 与 C 风格转换

注 2 指出，表达式与 [[g:nofun-type-id|nofun-type-id]] 之间不会产生这种歧义。nofun-type-id 是最外层不能是函数声明符的 type-id，这是 C++23 之后的新措辞。当前草案中 `sizeof`、`alignof`、C 风格转换 `(T)e` 和 `new (T)` 的类型操作数都是 nofun-type-id。`int()`、`int(unsigned(a))` 的最外层是函数声明符，不是 nofun-type-id，于是只能读成表达式。

```cpp
void foo(signed char a) {
  sizeof(int());              // 表达式：sizeof(int{})
  sizeof(int(a));             // 表达式
  sizeof(int(unsigned(a)));   // 表达式
  (int())+1;                  // 表达式：值为 1
  (int(a))+1;                 // 表达式
  (int(unsigned(a)))+1;       // 表达式
}
```

在 C++23 中，第 1、3、4、6 行能读成 type-id，于是被当作函数类型 `int()` 或 `int(unsigned)`，全部非良构。`int(unsigned(a))` 尤其反直觉：`unsigned(a)` 看起来是转换，却可以读成形参声明 `unsigned a`。

本机 Clang 23 仍按旧规则处理，这四行分别报 invalid application of 'sizeof' to a function type 和 C-style cast from 'int' to 'int ()' is not allowed，所以这段代码没有标判定。可移植的代码应该写 `sizeof(int{})` 或 `sizeof(int)`。

`alignof` 只接受 `alignof( nofun-type-id )`，没有表达式形式，所以当前草案下 `alignof(int())` 是语法错误。`typeid` 和模板实参仍然使用 type-id，上一小节的规则照常适用。

### 同样要以 auto 开头

¶2 也有和第 1 段对称的一句：如果一个结构在语法上可以是 type-id，并且最外层抽象声明符可以匹配带尾置返回类型的形式，那么只有以 `auto` 开头时它才是 type-id。

```cpp run error
typedef struct BB { int C[2]; } *B, C;
void g() {
  (void)sizeof(B()->C[1]);      // OK：sizeof(表达式)
  (void)sizeof(auto()->C[1]);   // error
}
```

第一行不以 `auto` 开头，是表达式，而且 `sizeof` 的操作数不求值，空指针不会被解引用。第二行按当前草案，`auto() -> C[1]` 的最外层是函数，不是 nofun-type-id，只能读成表达式，而 `auto()` 不是合法的表达式，所以非良构。Clang 按旧规则把它当作 type-id，报告函数不能返回数组，结论同样是非良构。

## 形参里被括起来的类型名（¶3）

```cpp run error
class C { };
void f(int(C)) { }   // 即 void f(int (*fp)(C))，不是 void f(int C)

int g(C);

void foo() {
  f(1);              // error: 1 不能转换为函数指针
  f(g);              // OK
}
```

¶3 在形参声明子句里，`int(C)` 可以是一个名为 `C` 的 `int` 形参（冗余括号），也可以是一个接受 `C`、返回 `int` 的函数类型形参，调整后成为函数指针。规则是：把括号里的类型名当作类型说明符，不当作形参名，所以取后一种读法。

```cpp run ok
#include <type_traits>
class C { };
void h(int *(C[10]));   // 形参：接受 C[10]（调整为 C*）、返回 int* 的函数
static_assert(std::is_same_v<decltype(h), void(int *(*)(C *))>);
int main() { }
```

这样选择的理由是，把一个类型名重新声明为形参名会遮住这个类型，几乎不会是作者的本意。这条规则只在 `C` 是类型名时生效；如果 `C` 不是类型名，`int(C)` 只能是名为 `C` 的 `int` 形参。

## 判定只看语法

三条规则都是纯语法的：只要语法上能读成声明（或 type-id），就采用这种读法，即使读出来的声明在语义上非良构，也不会退回去按表达式解析（[[stmt.ambig#3]]）。

如果消歧依赖语义，比如按声明解析出错就改成表达式，解析就得和重载决议、模板实例化交织在一起，结果可能取决于很远处的声明。纯语法的规则有时违反直觉，但它确定而且局部，只需要知道哪些名字是类型名。

!!! impl
    为了实现这些规则，GCC 和 Clang 都使用试探性解析：遇到可能是声明的结构，先试着按声明解析，能完整解析就采用，否则回溯按表达式解析。这需要任意长的前瞻，因为 `T(*g)(double(3))` 这样的语句要读到最后才能决定。

## 历史与演进

!!! history
    - 对象还是函数、type-id 还是表达式、括号中的类型名，这三条规则从 C++98 起就有。
    - C++11 的列表初始化提供了最直接的规避手段，因为花括号里不可能是形参列表。
    - 尾置返回类型带来了 `B()->C` 这种新歧义，后来的修订加入了以 `auto` 开头才算声明或 type-id 的限制。
    - C++23 之后的草案引入 *nofun-type-id*，`sizeof(int())`、`(int())+1` 不再有歧义。

## 思考题

!!! question "思考题 1"
    下面每一行声明了什么？
    ```cpp
    struct T { T(int); T(); };
    int n = 0;
    void f() {
      T a(T());
      T b(T(n));
      T c(T(1));
      T d((T(n)));
      T e(T(n), T());
    }
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：函数，形参类型 `T(*)()`，返回 `T`。
- `b`：函数，形参是 `T n`（冗余括号），返回 `T`。
- `c`：对象，用 `T(1)` 初始化。`1` 不能出现在声明符里，所以不可能是形参声明。
- `d`：对象，外层多出的括号使它不可能是形参声明子句。
- `e`：函数，两个形参：`T n` 和 `T(*)()`。

Clang 对 `a`、`b`、`e` 都给出 `-Wvexing-parse` 警告。
</details>

!!! question "思考题 2"
    `template<int N> struct Y {};` 中 `Y<int()>` 非良构，那 `Y<(int())>` 呢？

<details markdown="1">
<summary>答案</summary>

良构，等于 `Y<0>`。type-id 不能以 `(` 开头，所以 `(int())` 在模板实参位置只能是表达式。它是一个括号表达式，而括号表达式 `( expression )` 的内部只接受表达式，没有 type-id 的选项。能在括号里放类型的只有 C 风格转换 `( type ) cast-expression`，而这里 `)` 后面紧跟 `>`，构不成转换。所以 `int()` 是值为 0 的表达式。本机 Clang 23 接受这个写法。
</details>
