---
title: 范围 for 语句
summary: 范围 for 的精确改写；begin/end 的查找规则（数组、成员、仅 ADL）；C++17 起 begin 与 end 可以是不同类型；初始化器中临时对象的生命周期（C++23 修复）；C++20 的 init-statement；结构化绑定。
status: draft
since: c++11
papers: P0184R0, P0962R1, P0614R1, P2718R0
related: stmt.for, stmt.iter, class.temporary, basic.lookup.argdep, dcl.struct.bind, stmt.expand
tags: 语句, 循环, 临时对象, 生命周期
updated: 2026-10-17
---

范围 for（range-based for）是 C++11 最常用的特性之一，但标准没有给它单独的语义：[[stmt.ranged]] 只有一段，整段都在说**它等价于下面这个经典 for 循环**。因此，循环变量绑定到什么、迭代器从哪来、临时对象活多久，这些问题的答案都在这个改写和它引用的条款里：[[class.temporary]]（临时对象）、[[basic.lookup.argdep]]（ADL）、[[class.member.lookup]]（成员查找）。

## 改写（¶1）

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

其中 *range*、*begin*、*end* 是仅供说明的变量（exposition only，¶1.2），程序不能用名字引用它们。实现里它们通常叫 `__range1`、`__begin1` 之类，Clang 的诊断中会出现这些名字。

逐行解读这个改写：

| 行 | 含义 | 后果 |
|---|---|---|
| `auto&& range = init;` | 用转发引用绑定初始化器的结果 | 左值 → 左值引用，不拷贝；右值（prvalue）→ 物化为临时对象，生命周期延长到整个循环 |
| `auto begin = begin-expr;` | 迭代器按值保存 | 对 `begin-expr` 的结果做一次拷贝/移动（通常会被消除） |
| `auto end = end-expr;` | 单独一条声明 | C++17 起 `begin` 与 `end` 可以是不同类型（见下文） |
| `begin != end` | 用 `!=` 比较 | 只需要 `!=`，不需要 `<` |
| `++begin` | 前置递增 | 不要求后置 `++` |
| `decl = *begin;` | 每轮在循环体块内重新声明循环变量 | 每轮一个新变量；`auto x` 拷贝，`auto& x` 绑定 |

### 初始化器加括号（¶1.1）

¶1.1 如果 *for-range-initializer* 是表达式，就当作它外面套了一层括号，这样逗号运算符不会被误解为分隔两个 *init-declarator*。也就是说，`for (int x : a, b)` 迭代的是 `(a, b)`，即 `b`。

### 花括号初始化器

*for-range-initializer* 可以是花括号列表。此时 `auto&& range = {1, 2, 3};` 推导出 `std::initializer_list<int>`（[[dcl.type.auto.deduct]]），所以需要 `<initializer_list>`，不过它通常已经由其他头文件间接包含：

```cpp run ok
#include <initializer_list>
int main() {
    int s = 0;
    for (int x : {1, 2, 3}) s += x;
    return s == 6 ? 0 : 1;
}
```

## begin-expr 与 end-expr 的确定（¶1.3）

三种情况按顺序检查：

### 1. 数组（¶1.3.1）

如果 *range* 的类型是数组 `R` 的引用，*begin-expr* 就是 `range`（退化为指针），*end-expr* 是 `range + N`，N 是数组长度。如果数组边界未知或元素类型不完整，程序非良构，因为无法计算 `end`。

```cpp error
extern int arr[];          // 未知边界
int h() {
    int s = 0;
    for (int x : arr) s += x;   // error: 无法确定 end
    return s;
}
```

数组不走成员查找或 ADL，所以即使在全局命名空间定义了 `begin(int(&)[3])`，它也不会被使用。

### 2. 类类型且同时找到成员 begin 和 end（¶1.3.2）

如果 *range* 的类型是类 `C` 的引用，并且在 `C` 的作用域中对 `begin` 和 `end` 两个名字的查找**都至少找到一个声明**，就使用 `range.begin()` 和 `range.end()`。

这里有几处需要精确理解：

- 判断依据是名字查找，而不是能否调用。只要找到名为 `begin` 和 `end` 的任意声明（数据成员、类型、枚举项都算），就走成员路线；如果之后 `range.begin()` 调用不了，就是编译错误，不会退回到 ADL。
- 两个名字都必须找到。C++11/14/17 的规则是只要找到其中一个就用成员，这会误伤一些类型。例如派生自 `std::ios_base` 的类，由于 `std::ios_base::end` 是一个 `seekdir` 枚举项，它会被认为有成员 `end`，即使提供了 ADL 版本的 `begin`/`end` 也无法用于范围 for。C++20 通过 [[P0962R1]] 改为要求两者都找到。

```cpp run ok
namespace N {
    struct R { int a[3]; int end; };      // 只有名为 end 的成员（还不是函数）
    int* begin(R& r) { return r.a; }
    int* end(R& r) { return r.a + 3; }
}
int main() {
    N::R r{{1, 2, 3}, 0};
    int s = 0;
    for (int x : r) s += x;   // C++20 起：没找到成员 begin，于是走 ADL，使用 N::begin/N::end
    return s == 6 ? 0 : 1;
}
```

### 3. 否则：只用 ADL（¶1.3.3）

否则，*begin-expr* 和 *end-expr* 是 `begin(range)` 和 `end(range)`，其中 `begin`/`end` **只做实参依赖查找**（ADL，[[basic.lookup.argdep]]）。注 1 特别指出，这里不做普通的无限定查找（[[basic.lookup.unqual]]）。

这样规定的原因是：如果做普通查找，范围 for 的含义就会随所在位置的 `using` 声明和外层命名空间里的函数而变化。只用 ADL，一个类型能否被范围 for 迭代就成了这个类型自身（及其关联命名空间）的属性。

因此，在不相关的命名空间（比如全局命名空间）里为第三方类型补一对 `begin`/`end` 是没有用的：

```cpp error
namespace M { struct Q { int a[2]; }; }
int* begin(M::Q& q) { return q.a; }        // 位于全局命名空间，不是 M::Q 的关联命名空间
int* end(M::Q& q) { return q.a + 2; }
int g(M::Q& q) {
    int s = 0;
    for (int x : q) s += x;                 // error: ADL 只看 M，找不到 begin/end
    return s;
}
```

标准库类型的关联命名空间是 `std`，所以 ADL 能找到 `std::begin`/`std::end`；不过 `std::vector` 等容器实际走的是成员路线。

### begin 与 end 可以是不同类型 {{c++17}}

C++11/14 的改写是 `auto __begin = begin-expr, __end = end-expr;`。同一个声明中的 `auto` 必须推导出同一类型，所以 `begin` 和 `end` 必须同类型。C++17（[[P0184R0]]）把它拆成两条声明，于是只要 `begin != end` 能比较，`end` 就可以是一个**哨兵**（sentinel）类型。C++20 Ranges 库（`std::ranges::subrange`、`std::default_sentinel_t`、`std::unreachable_sentinel_t` 等）能直接用于范围 for，语言上的前提就是这一改动。

```cpp run ok
struct ZStr {                                  // 以 '\0' 结尾的字符串，end 是哨兵
    const char* p;
    struct Sentinel {};
    const char* begin() const { return p; }
    Sentinel end() const { return {}; }
};
bool operator!=(const char* it, ZStr::Sentinel) { return *it != '\0'; }
int main() {
    int n = 0;
    for (char c : ZStr{"hello"}) { (void)c; ++n; }   // 不必预先计算长度
    return n == 5 ? 0 : 1;
}
```

## 循环变量的声明方式

*for-range-declaration* 可以是普通声明或结构化绑定声明（[[stmt.pre]]）。它每轮在循环体的块中重新声明一次，初始化器是 `*begin`。

| 写法 | 效果 | 适用 |
|---|---|---|
| `for (auto x : r)` | 每个元素拷贝一份 | 小的值类型 |
| `for (auto& x : r)` | 左值引用；不能绑定到 prvalue | 需要修改元素 |
| `for (const auto& x : r)` | const 引用；可绑定 prvalue（延长到本轮结束） | 只读、避免拷贝 |
| `for (auto&& x : r)` | 转发引用，绑定一切 | 泛型代码、代理迭代器（如 `std::vector<bool>`） |
| `for (auto& [k, v] : m)` | 结构化绑定 | 遍历 `map` 等 |

```cpp error
#include <vector>
void f(std::vector<bool>& v) {
    for (auto& b : v) b = true;    // error: *begin 返回代理 prvalue，非 const 左值引用无法绑定
}
```

```cpp ok
#include <vector>
void f(std::vector<bool>& v) {
    for (auto&& b : v) b = true;   // OK: b 绑定到代理对象，赋值通过代理写回
}
```

```cpp run ok
#include <map>
#include <string>
int main() {
    std::map<std::string, int> m{{"a", 1}, {"b", 2}};
    int s = 0;
    for (const auto& [k, v] : m) s += v;   // 结构化绑定作为 for-range-declaration
    return s == 3 ? 0 : 1;
}
```

在改写中，循环变量与循环体位于同一个块，所以在循环体的最外层重新声明同名变量是非良构的：

```cpp error
void k(int (&v)[3]) {
    for (int x : v) {
        int x = 1;     // error: x 重复声明
        (void)x;
    }
}
```

!!! pitfall "`const auto&` 遍历 map 时的类型陷阱"
    `std::map<K, V>` 的元素类型是 `std::pair<const K, V>`。如果写成 `for (const std::pair<K, V>& p : m)`（漏了 `const K`），类型不匹配，每个元素都会隐式转换出一个临时 pair，引用绑定到这个临时对象上。结果是每轮一次拷贝，而且取地址得到的也不是容器中元素的地址。用 `const auto&` 或结构化绑定可以避免这个问题。

## 范围初始化器中的临时对象 {{c++23}}

### 问题

`auto&& range = for-range-initializer;` 只会延长直接绑定到 `range` 的那个临时对象的生命周期。如果初始化器在一个临时对象上调用成员函数，并返回指向其内部的引用，那么：

- 绑定到 `range` 的是返回的引用，它指向临时对象内部；
- 临时对象本身在初始化 `range` 的完整表达式结束时就销毁了；
- 循环中使用 `range` 就是在访问已销毁的对象，行为未定义。

这是 C++11 至 C++20 中最常见的悬空引用来源之一：

```cpp
for (int x : get().value()) { }        // get() 返回 optional<vector<int>> 的 prvalue
for (char c : make_person().name()) { } // name() 返回 const std::string&
for (auto& e : std::vector{...}[0]) { }  // operator[] 返回元素引用
```

### 修复

注 2 指向 [[class.temporary#7]]：C++23 起（[[P2718R0]]），在 *for-range-initializer* 中创建的临时对象，如果原本会在该完整表达式结束时销毁，现在会**一直存活到 `range` 引用的生命周期结束**，即整个循环结束。这一修复涵盖初始化器中创建的所有临时对象，而不只是直接绑定到引用的那一个。

下面的程序在 `-std=c++20` 下用 AddressSanitizer 运行会报告 stack-use-after-scope，在 `-std=c++23` 及以后则正常（Clang 23 实测）：

```cpp run ok
#include <optional>
#include <vector>
std::optional<std::vector<int>> get() { return std::vector<int>{1, 2, 3}; }
int main() {
    int s = 0;
    for (int x : get().value()) s += x;   // C++23 起 OK：get() 返回的临时 optional 活到循环结束
    return s == 6 ? 0 : 1;
}
```

### 修复不到的地方

标准例 2 精确地划出了边界：

```cpp ub
#include <list>
using T = std::list<int>;
const T& f1(const T& t) { return t; }
const T& f2(T t)        { return t; }
T g();

void foo() {
    for (auto e : f1(g())) {}     // OK: g() 返回的临时对象生命周期被延长
    for (auto e : f2(g())) {}     // UB
}
```

`f2` 不行，是因为 `f2` 返回的是对形参 `t` 的引用。形参不是临时对象，[[class.temporary#7]] 不适用于它。形参的生命周期在函数返回时或在包含调用的完整表达式结束时结束（具体是哪个由实现定义，见 [[expr.call]]），无论哪种都早于循环体执行。Clang 会在 `f2` 的定义处给出 `-Wreturn-stack-address` 警告（返回了对形参的引用）。`g()` 产生的临时对象确实被延长了，但它只是用来初始化 `t` 的源对象，与返回的引用无关。

同理，修复只覆盖 *for-range-initializer* 中创建的临时对象。在循环体里创建的临时对象，以及初始化器中所调用函数内部创建的临时对象，都不受影响。

!!! history "为什么花了十二年？"
    这个问题自 C++11 起就广为人知。反对统一延长的主要理由是，它让范围 for 的初始化器与普通的 `auto&& r = ...;` 声明语义不同，并且可能让某些临时对象（例如持有锁的对象）意外地活得更久。C++23 最终接受了这个特例，因为范围 for 中悬空引用的危害远大于延长生命周期的代价。在 C++23 之前，惯用的规避办法是用 C++20 的 *init-statement* 显式持有对象（见下文）。

## init-statement {{c++20}}

C++20（[[P0614R1]]）允许范围 for 带 *init-statement*，它在改写中位于 `auto&& range` 之前、同一个外层块中。两个典型用途：

```cpp run ok
#include <optional>
#include <vector>
std::optional<std::vector<int>> get() { return std::vector<int>{1, 2, 3}; }
int main() {
    int s = 0;
    for (auto opt = get(); int x : opt.value())      // C++20 中规避悬空：显式持有临时对象
        s += x;
    for (std::size_t i = 0; int x : *get()) {        // 带索引的遍历
        s += static_cast<int>(i) * x;
        ++i;
    }
    return s == 6 + (0 * 1 + 1 * 2 + 2 * 3) ? 0 : 1;
}
```

（第二个循环在 C++23 起才是安全的：`*get()` 返回对临时 optional 内部的引用，依赖 [[class.temporary#7]] 的延长。）

## 循环体中修改范围

改写中的 `begin` 和 `end` 在循环开始前只计算一次。如果循环体修改了容器，使迭代器失效（例如对 `std::vector` 执行 `push_back`），后续的 `++begin`、`begin != end`、`*begin` 都是在操作失效的迭代器，行为未定义。

```cpp ub
#include <vector>
int main() {
    std::vector<int> v{1, 2, 3};
    for (int x : v)
        if (x == 1) v.push_back(4);   // UB: 可能重新分配，begin/end 失效
}
```

## 实现视角

!!! impl "仅供说明的变量在诊断中可见"
    Clang 的诊断会直接提到 `__range1`、`__begin1`、`__end1` 这些名字，constexpr 求值失败时的提示就是一例。看到这些名字时，对照 ¶1 的改写就能定位问题。

!!! impl "范围 for 与优化"
    因为 `end` 只计算一次，范围 for 天然避免了经典写法 `for (i = 0; i < v.size(); ++i)` 中每轮重新调用 `size()` 的开销（尽管优化器通常能消除它）。对数组和 `std::vector`，三大编译器生成的代码与指针循环基本一致。

## 历史与演进

!!! history
    - C++11：引入范围 for。改写为 `auto __begin = begin-expr, __end = end-expr;`；成员查找规则是找到 begin 或 end 之一即用成员。
    - C++17：`begin` 与 `end` 可以是不同类型（[[P0184R0]]）。
    - C++20：可以带 *init-statement*（[[P0614R1]]）；成员查找改为必须同时找到 begin 和 end（[[P0962R1]]）。
    - C++23：*for-range-initializer* 中所有临时对象的生命周期延长到循环结束（[[P2718R0]]）。
    - C++26：展开语句 `template for`（[[stmt.expand]]）复用了本节对 *begin-expr*/*end-expr* 的定义。

## 陷阱

!!! pitfall "`for (auto x : v)` 是拷贝"
    对 `std::vector<std::string>` 写 `for (auto s : v)` 会每轮拷贝一个字符串。只读时用 `const auto&`。

!!! pitfall "范围 for 无法反向迭代"
    改写固定使用 `begin`/`end` 和 `++`。要反向遍历，可以用 `std::views::reverse`，或自己写一个返回 `rbegin`/`rend` 的适配器。注意，如果适配器持有对临时对象的引用，在 C++23 之前同样存在悬空问题。

## 思考题

!!! question "1. 下面的循环迭代几次？"
    ```cpp
    int a[] = {1, 2, 3}, b[] = {4, 5};
    for (int x : a, b) { }
    ```

<details markdown="1">
<summary>答案</summary>

2 次。¶1.1 规定表达式形式的初始化器视为加了括号，即 `(a, b)`。逗号运算符的结果是右操作数 `b`（左值，类型 `int[2]`），于是 `range` 是 `int(&)[2]`。（编译器可能会警告左操作数没有副作用。）
</details>

!!! question "2. 某类型有成员函数 `begin()`，但没有任何名为 `end` 的成员；同时其关联命名空间中有自由函数 `begin` 和 `end`。范围 for 用哪一对？"

<details markdown="1">
<summary>答案</summary>

C++20 起，成员查找没有同时找到 `begin` 和 `end`，所以不走 ¶1.3.2，而是走 ¶1.3.3，两个都用 ADL 找到的自由函数（自由 `begin` 与成员 `begin` 是否一致，由该类型的作者负责）。C++17 及之前，找到了成员 `begin` 就走成员路线，而 `range.end()` 不存在，程序非良构。
</details>

!!! question "3. C++23 下，`for (auto x : std::string("abc").substr(1))` 和 `for (char c : std::string_view(std::string("abc")))` 安全吗？"

<details markdown="1">
<summary>答案</summary>

都安全。第一个循环中，`substr` 返回一个 prvalue `std::string`，它直接绑定到 `range`，即使在 C++11 中生命周期也会延长。第二个循环中，`std::string("abc")` 是 *for-range-initializer* 中创建的临时对象，C++23 起其生命周期延长到循环结束，`string_view` 指向的缓冲区在循环中有效；在 C++20 及之前，这里是悬空的。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 改写 | `auto&& range = init; auto begin = ...; auto end = ...; for (; begin != end; ++begin) { decl = *begin; body }` |
| 数组 | `range` 和 `range + N`；未知边界或不完整元素类型非良构 |
| 类 | 成员查找同时找到 `begin` 和 `end`（C++20）→ 成员函数；否则 → 仅 ADL 的 `begin(range)`/`end(range)` |
| 不做 | 普通无限定查找 |
| begin/end 类型 | C++17 起可以不同（哨兵） |
| 临时对象 | C++23 起初始化器中所有临时对象活到循环结束；但对形参的引用、函数内部的临时对象不在此列 |
| init-statement | C++20 起允许，位于 `range` 之前 |
| 循环变量 | 每轮在循环体块内重新声明；可以是结构化绑定 |
