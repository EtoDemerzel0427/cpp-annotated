---
title: 范围 for 语句
summary: 范围 for 被定义为一个普通 for 循环的改写；这个改写决定了 begin/end 怎么找、循环变量绑定到什么、初始化器里的临时对象活多久。
status: done
since: c++11
papers: P0184R0, P0962R1, P0614R1, P2718R0
related: stmt.for, stmt.iter, class.temporary, basic.lookup.argdep, dcl.struct.bind, stmt.expand
tags: 语句, 循环, 临时对象, 生命周期
updated: 2026-10-21
---

!!! tldr
    - 范围 for 没有独立的语义，它等价于一段用 `auto&& range`、`begin`、`end` 写成的普通 `for` 循环。
    - 数组直接用指针；类类型只有在成员里同时找到 `begin` 和 `end` 时才调用成员函数，否则只用 ADL 找自由函数 `begin`/`end`，不做普通查找。
    - C++17 起 `begin` 和 `end` 可以是不同类型，`end` 可以是一个哨兵。
    - C++23 起，初始化器里创建的所有临时对象都活到循环结束，`for (int x : get().value())` 不再悬空；但返回形参引用的函数仍然会悬空。
    - `begin` 和 `end` 只在循环开始前计算一次，循环体里让迭代器失效（如对 `vector` 做 `push_back`）是未定义行为。

## 改写

¶1 范围 for 语句

```text
for ( init-statement(opt) for-range-declaration : for-range-initializer ) statement
```

等价于

```text
{
    init-statement(opt)
    auto && range = for-range-initializer ;
    auto begin = begin-expr ;
    auto end = end-expr ;
    for ( ; begin != end; ++begin ) {
        for-range-declaration = * begin ;
        statement
    }
}
```

¶1.2 *range*、*begin*、*end* 是仅供说明的变量，程序不能用名字引用它们。这段改写的每一行都有后果：

| 行 | 后果 |
|---|---|
| `auto&& range = init;` | 左值直接绑定，不拷贝；prvalue 物化为临时对象，生命周期延长到整个循环 |
| `auto begin = ...; auto end = ...;` | 两条独立的声明，所以两者可以是不同类型；都只计算一次 |
| `begin != end`、`++begin` | 迭代器只需要支持 `!=` 和前置 `++` |
| `decl = *begin;` | 循环变量每轮在循环体的块里重新声明一次 |

¶1.1 如果初始化器是表达式，就当作它外面套了一层括号，这样逗号不会被误读成分隔两个声明符。所以 `for (int x : a, b)` 迭代的是逗号表达式 `(a, b)` 的结果，也就是 `b`。

初始化器也可以是花括号列表。这时 `auto&& range = {1, 2, 3};` 推导出 `std::initializer_list<int>`（[[dcl.type.auto.deduct]]），需要包含 `<initializer_list>`：

```cpp run ok
#include <initializer_list>
int main() {
    int s = 0;
    for (int x : {1, 2, 3}) s += x;
    return s == 6 ? 0 : 1;
}
```

## begin 和 end 从哪里来

¶1.3 按顺序检查三种情况。

### 数组

¶1.3.1 如果 *range* 是数组的引用，*begin-expr* 就是 `range`（退化为指针），*end-expr* 是 `range + N`，N 是数组长度。数组边界未知或元素类型不完整时程序非良构，因为算不出 `end`：

```cpp error
extern int arr[];               // 未知边界
int h() {
    int s = 0;
    for (int x : arr) s += x;   // error
    return s;
}
```

### 类类型：成员

¶1.3.2 如果 *range* 是类 `C` 的引用，并且在 `C` 的作用域里查找 `begin` 和 `end` 这两个名字都至少找到一个声明，就用 `range.begin()` 和 `range.end()`。

判断依据是名字查找，不是能否调用。名为 `begin` 和 `end` 的任何成员都算，包括数据成员、类型、枚举项。一旦走了这条路，`range.begin()` 调不通就是编译错误，不会退回去找自由函数。

两个名字都要找到，这是 C++20 的 [[P0962R1]] 改的。此前只要找到其中一个就走成员路线，这误伤了派生自 `std::ios_base` 的类：`std::ios_base::end` 是一个枚举项，于是这些类被认为有成员 `end`，为它们写的自由 `begin`/`end` 永远用不上。

```cpp run ok
namespace N {
    struct R { int a[3]; int end; };   // 有名为 end 的成员，但没有 begin
    int* begin(R& r) { return r.a; }
    int* end(R& r) { return r.a + 3; }
}
int main() {
    N::R r{{1, 2, 3}, 0};
    int s = 0;
    for (int x : r) s += x;   // 走 ADL，用 N::begin、N::end
    return s == 6 ? 0 : 1;
}
```

### 其他：只用 ADL

¶1.3.3 否则，*begin-expr* 和 *end-expr* 是 `begin(range)` 和 `end(range)`，这里的 `begin`、`end` 只做实参依赖查找（ADL，在实参类型所在的命名空间里查找函数，见 [[basic.lookup.argdep]]），不做普通的无限定查找（注 1）。

这样一来，一个类型能不能用于范围 for，只取决于这个类型和它所在的命名空间，与循环写在哪里、周围有哪些 `using` 无关。代价是，在别的命名空间里为第三方类型补一对 `begin`/`end` 没有用：

```cpp error
namespace M { struct Q { int a[2]; }; }
int* begin(M::Q& q) { return q.a; }   // 在全局命名空间，ADL 看不到
int* end(M::Q& q) { return q.a + 2; }
int g(M::Q& q) {
    int s = 0;
    for (int x : q) s += x;   // error: 找不到 begin
    return s;
}
```

### begin 和 end 可以是不同类型 {{c++17}}

C++11 的改写是 `auto __begin = begin-expr, __end = end-expr;`。同一条声明里的 `auto` 必须推导出同一类型，所以两者必须同类型。C++17 的 [[P0184R0]] 把它拆成两条声明，于是 `end` 可以是一个**哨兵**（sentinel）：一个只用来和迭代器比较、判断是否到头的对象。C++20 Ranges 库里的 `std::default_sentinel_t`、`std::unreachable_sentinel_t` 能直接用于范围 for，靠的就是这一改动。

```cpp run ok
struct ZStr {                       // 以 '\0' 结尾的字符串
    const char* p;
    struct Sentinel {};
    const char* begin() const { return p; }
    Sentinel end() const { return {}; }
};
bool operator!=(const char* it, ZStr::Sentinel) { return *it != '\0'; }
int main() {
    int n = 0;
    for (char c : ZStr{"hello"}) { (void)c; ++n; }   // 不必先算长度
    return n == 5 ? 0 : 1;
}
```

## 循环变量

*for-range-declaration* 可以是普通声明，也可以是结构化绑定声明。它每轮以 `*begin` 为初始化器重新声明一次。

| 写法 | 效果 |
|---|---|
| `for (auto x : r)` | 每个元素拷贝一份 |
| `for (auto& x : r)` | 左值引用，可以修改元素；不能绑定到 prvalue |
| `for (const auto& x : r)` | 只读，不拷贝 |
| `for (auto&& x : r)` | 什么都能绑定，适合泛型代码和返回代理对象的迭代器 |
| `for (const auto& [k, v] : m)` | 结构化绑定 |

`std::vector<bool>` 的迭代器解引用得到一个代理对象（prvalue），非 const 左值引用绑定不上：

<div class="compare" markdown="1">

```cpp error
#include <vector>
void f(std::vector<bool>& v) {
    for (auto& b : v)   // error
        b = true;
}
```

```cpp ok
#include <vector>
void f(std::vector<bool>& v) {
    for (auto&& b : v)  // OK
        b = true;       // 经代理写回
}
```

</div>

循环变量和循环体在同一个块里，所以不能在循环体的最外层再声明同名变量：

```cpp error
void k(int (&v)[3]) {
    for (int x : v) {
        int x = 1;   // error: x 重复声明
        (void)x;
    }
}
```

!!! pitfall "遍历 map 时写错元素类型"
    `std::map<K, V>` 的元素类型是 `std::pair<const K, V>`。写成 `for (const std::pair<K, V>& p : m)` 时类型不匹配，每个元素都会转换出一个临时 `pair`，引用绑定到这个临时对象上：每轮一次拷贝，取到的地址也不是容器里元素的地址。用 `const auto&` 或结构化绑定可以避免。

## 初始化器里的临时对象 {{c++23}}

### 问题

`auto&& range = ...;` 只延长直接绑定到 `range` 的那个临时对象。如果初始化器在一个临时对象上调用成员函数，返回指向它内部的引用，那么临时对象在这条声明结束时就销毁了，`range` 成了悬空引用：

```cpp run ok
#include <optional>
#include <vector>
std::optional<std::vector<int>> get() {
    return std::vector<int>{1, 2, 3};
}
int main() {
    int s = 0;
    for (int x : get().value()) s += x;
    return s == 6 ? 0 : 1;
}
```

`value()` 返回 `optional` 内部 `vector` 的引用，而 `get()` 返回的 `optional` 是个临时对象。本机 Clang 23 加 `-fsanitize=address` 运行：`-std=c++20` 下报告 `stack-use-after-scope`，`-std=c++23` 下正常。

### 修复

注 2 指向 [[class.temporary#7]]：C++23 起（[[P2718R0]]），初始化器里创建的临时对象，凡是原本会在这条完整表达式结束时销毁的，都延长到整个循环结束。延长的是初始化器中的所有临时对象，不只是直接绑定到 `range` 的那一个。

这样做的代价是范围 for 的初始化器与一条普通的 `auto&& r = ...;` 声明行为不再一致，某些临时对象（比如持有锁的对象）也会活得比预期久。C++23 接受了这个代价，因为悬空的危害大得多。

### 修复不到的地方

标准例 2 划出了边界：

```cpp ub
#include <list>
using T = std::list<int>;
const T& f1(const T& t) { return t; }
const T& f2(T t)        { return t; }
T g();

void foo() {
    for (auto e : f1(g())) {}   // OK: g() 的临时对象被延长
    for (auto e : f2(g())) {}   // UB
}
```

`f2` 返回的是对自己形参 `t` 的引用。形参不是临时对象，不受延长；它在函数返回时或在调用所在的完整表达式结束时销毁（具体哪一个由实现定义，见 [[expr.call]]），都早于循环体执行。这里也没有别的临时对象可以延长：`g()` 是纯右值，直接初始化形参 `t`（[[dcl.init.general#15.6.1]]），不经过临时对象。Clang 在 `f2` 的定义处给出 `-Wreturn-stack-address` 警告。

同理，在循环体里创建的临时对象，以及初始化器调用的函数内部创建的临时对象，都不在延长之列。

## init-statement {{c++20}}

C++20 的 [[P0614R1]] 允许范围 for 带 *init-statement*，它在改写中位于 `auto&& range` 之前。常见用途有两个：在 C++23 之前显式持有临时对象以避免悬空，以及给遍历加一个计数器。

```cpp run ok
#include <cstddef>
#include <optional>
#include <vector>
std::optional<std::vector<int>> get() {
    return std::vector<int>{1, 2, 3};
}
int main() {
    int s = 0;
    for (auto opt = get(); int x : opt.value())  // 显式持有
        s += x;
    std::vector<int> v{10, 20, 30};
    for (std::size_t i = 0; int x : v) {         // 带计数器
        s += static_cast<int>(i) * x;
        ++i;
    }
    return s == 6 + 20 + 60 ? 0 : 1;
}
```

## 循环体里修改容器

`begin` 和 `end` 在循环开始前只计算一次。循环体如果让它们失效，后面的 `++begin`、`begin != end`、`*begin` 都在用失效的迭代器，行为未定义：

```cpp ub
#include <vector>
int main() {
    std::vector<int> v{1, 2, 3};
    for (int x : v)
        if (x == 1) v.push_back(4);   // 可能重新分配，begin/end 失效
}
```

## 历史

!!! history
    - C++11 引入范围 for。当时 `begin` 和 `end` 写在同一条声明里，成员查找只要找到二者之一就用成员。
    - C++17：`begin` 和 `end` 可以是不同类型（[[P0184R0]]）。
    - C++20：可以带 *init-statement*（[[P0614R1]]）；成员查找要同时找到 `begin` 和 `end`（[[P0962R1]]）。
    - C++23：初始化器中的临时对象活到循环结束（[[P2718R0]]）。
    - C++26 的展开语句 `template for`（[[stmt.expand]]）沿用了本节对 *begin-expr*、*end-expr* 的定义。

## 思考题

!!! question "1. 下面的循环迭代几次？"
    ```cpp
    int a[] = {1, 2, 3}, b[] = {4, 5};
    for (int x : a, b) { }
    ```

<details markdown="1">
<summary>答案</summary>

2 次。按 ¶1.1，初始化器视为 `(a, b)`，逗号表达式的结果是右操作数 `b`，类型 `int[2]` 的左值。Clang 会警告逗号左边的操作数没有作用。
</details>

!!! question "2. 某个类有成员函数 `begin()`，没有任何名为 `end` 的成员，它的命名空间里有自由函数 `begin` 和 `end`。范围 for 用哪一对？"

<details markdown="1">
<summary>答案</summary>

C++20 起，成员查找没有同时找到两个名字，所以走 ¶1.3.3，两个都用 ADL 找到的自由函数。C++17 及之前，找到成员 `begin` 就走成员路线，而 `range.end()` 不存在，程序非良构。
</details>

!!! question "3. C++23 下，`for (char c : std::string("abc").substr(1))` 和 `for (char c : std::string_view(std::string("abc")))` 安全吗？"

<details markdown="1">
<summary>答案</summary>

都安全。第一个里 `substr` 返回 prvalue `std::string`，直接绑定到 `range`，C++11 起就会延长。第二个里 `std::string("abc")` 是初始化器中创建的临时对象，C++23 起活到循环结束，`string_view` 指向的缓冲区一直有效；C++20 及之前这里会悬空。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 改写 | `auto&& range = init; auto begin = ...; auto end = ...; for (; begin != end; ++begin) { decl = *begin; body }` |
| 数组 | `range` 和 `range + N`；边界未知或元素类型不完整则非良构 |
| 类 | 成员里同时找到 `begin` 和 `end` 则用成员函数，否则用只经 ADL 查找的 `begin(range)`、`end(range)` |
| `begin`/`end` 类型 | C++17 起可以不同 |
| 临时对象 | C++23 起初始化器中的临时对象活到循环结束；形参和被调函数内部的对象不在此列 |
| init-statement | C++20 起允许，位于 `range` 之前 |
