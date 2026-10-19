---
title: const_cast
summary: const_cast 只改变 cv 限定，适用于相似的对象指针、数据成员指针和对应的引用；转换本身从不是未定义行为，修改一个 const 对象才是；本节还定义了去掉常量性这个术语，其他转换都受它约束。
status: done
related: expr.static.cast, expr.reinterpret.cast, expr.dynamic.cast, expr.cast, conv.qual, dcl.type.cv, basic.type.qualifier, topics/casts
tags: 类型转换, const, cv 限定, UB
updated: 2026-10-19
---

!!! tldr
    - `const_cast` 只改变 `const` 和 `volatile`，可以去掉也可以加上，可以作用于多级指针的任意一层，但不能改变类型本身。
    - 它适用于对象指针、数据成员指针和对象的引用，不适用于函数指针和成员函数指针。
    - 转换本身从不是未定义行为。未定义行为来自之后修改一个 const 对象，判断依据是对象本身是不是 const，而不是访问路径上有没有 `const`。
    - 去掉常量性不只是删掉某层 `const`，也包括 `int**` 到 `const int**` 这种在不安全位置加 `const` 的转换。
    - 只有 `const_cast` 和 C 风格转换能去掉常量性，`static_cast`、`reinterpret_cast`、`dynamic_cast` 都不能。

## 对象是不是 const

<div class="compare" markdown="1">

```cpp run ok
int main() {
  int x = 1;           // x 不是 const
  const int& cr = x;
  const_cast<int&>(cr) = 2;
  // OK：被修改的 x 不是 const 对象
  return x == 2 ? 0 : 1;
}
```

```cpp run ub
int main() {
  const int x = 1;     // x 是 const 对象
  const_cast<int&>(x) = 2;
  // UB: 修改 const 对象
  return x;
}
```

</div>

两边的 `const_cast` 写法一样，转换本身也都合法。区别在于被修改的对象：左边的 `x` 只是经由一个 `const int&` 被访问，对象本身不是 const；右边的 `x` 就是一个 const 对象，修改它是未定义行为（[[dcl.type.cv]]）。本机 Clang 编译右边的程序，退出码是 1：编译器认定 `x` 永远是 1，直接返回了常量。

## 能做哪些转换（¶1–¶4）

¶1 结果的类型是 `T`。`T` 是对象的左值引用时结果是左值，是对象的右值引用时结果是亡值，否则结果是 prvalue，这时先对操作数做左值到右值、数组到指针、函数到指针转换。除了第 4.3 项规定的情形，不对操作数做临时量实质化。只能做下文列出的转换。

¶1 只提到对象的引用，所以 `const_cast` 不能用于函数的引用。¶2 是一条注：在本节的限制下，表达式可以用 `const_cast` 转换为自身的类型。

### 指针（¶3）

¶3 设 `T1`、`T2` 是两个[[g:similar-types|相似]]的对象指针类型或数据成员指针类型。如果它们的**限定分解**（qualification-decomposition，[[conv.qual]]）中每一层的 `P` 都相同，`T1` 的 prvalue 就可以用 `const_cast` 转换为 `T2`。

限定分解把类型拆成 cv<sub>0</sub> P<sub>0</sub> cv<sub>1</sub> P<sub>1</sub> ⋯ cv<sub>n</sub> U 的形式，每个 P 是指针、成员指针或数组。例如 `const int* volatile*` 分解为 cv<sub>0</sub> 为空、P<sub>0</sub> 是指针、cv<sub>1</sub> 是 `volatile`、P<sub>1</sub> 是指针、cv<sub>2</sub> 是 `const`、U 是 `int`。每层 P 都相同，就是说指针的层数和种类不变，只有各层的 cv 不同。

空指针转换为空指针，空成员指针转换为空成员指针。否则结果指向与原指针相同的对象（或它的尾后位置），或者指向相同的成员。

```cpp title="const-cast-ptr.cpp" error
struct S { const int cm = 0; };
void fn();

void t(int** pp, const int* const* cpcp, int* ip, volatile int* vp) {
  int** a = const_cast<int**>(cpcp);           // OK：两层 const 都去掉
  const int** b = const_cast<const int**>(pp); // OK：也可以加 const
  int* c = const_cast<int*>(vp);               // OK：去掉 volatile
  int S::* m = const_cast<int S::*>(&S::cm);   // OK：数据成员指针
  long* d = const_cast<long*>(ip);             // error: 类型不相似
  void (*f)() = const_cast<void (*)()>(&fn);   // error: 函数指针
  int x = const_cast<int>(*ip);                // error: 不是指针或引用
  (void)a; (void)b; (void)c; (void)m; (void)d; (void)f; (void)x;
}
```

### 引用（¶4）

¶4 设 `T1`、`T2` 是对象类型。如果 `T1*` 能用 `const_cast` 转换为 `T2*`，那么也可以做下面三种转换：

- ¶4.1 `T1` 的左值转换为 `T2` 的左值：`const_cast<T2&>`；
- ¶4.2 `T1` 的 glvalue 转换为 `T2` 的亡值：`const_cast<T2&&>`；
- ¶4.3 `T1` 是类或数组类型时，`T1` 的 prvalue 转换为 `T2` 的亡值：`const_cast<T2&&>`，这时先对操作数做临时量实质化。

结果与（可能经过实质化的）操作数指代同一个对象。

```cpp run title="const-cast-ref.cpp" ok
int main() {
  const int ci = 1;
  const int& cr = ci;
  int& r = const_cast<int&>(cr);    // ¶4.1：转换合法，写入 r 才是 UB
  struct S { int v; };
  S&& s = const_cast<S&&>(S{1});    // ¶4.3：类 prvalue 先实质化
  (void)r;
  return s.v == 1 ? 0 : 1;
}
```

标准的例 1 演示的是数组 prvalue：

```cpp title="const-cast-array.cpp"
typedef int* A[3];                // 3 个 int* 的数组
typedef const int* const CA[3];   // 3 个 const int* const 的数组

auto&& r2 = const_cast<A&&>(CA{});  // OK：数组 prvalue 先实质化
```

按标准这一行是良构的。本机 Clang 23 拒绝它，报告 `const_cast from rvalue to reference type 'A &&'`，说明 Clang 还没有实现第 4.3 项中数组 prvalue 的情形，所以这个例子不标判定。

¶4.3 只针对类和数组，是因为其他类型的 prvalue 根本不带 cv 限定（[[expr.type]]），没有什么可以去掉。`const_cast<int&&>(5)` 是非良构的。

## 修改的后果（¶5）

¶5 是一条注：用去掉了 `const` 的 `const_cast` 结果去写，视对象的类型而定，可能产生未定义行为（[[dcl.type.cv]]）。脚注 50 补充，`const_cast` 并不只用来去掉 `const`。

[[dcl.type.cv]] 的规则是：修改一个 const 对象（`mutable` 成员除外）是未定义行为。按 [[basic.type.qualifier]]，**const 对象**是类型为 `const T` 的对象，以及这种对象的非 `mutable` 子对象；`new const T` 创建的对象也是。`const T&` 绑定到非 const 对象，或者 `const T*` 指向非 const 对象，都不会让对象变成 const 的。

把修改 const 对象定为未定义行为，给了实现两项自由：

1. 把 const 对象放进只读内存。常量初始化的静态 `const` 对象和字符串字面量通常在 `.rodata` 段里，写入会触发段错误。
2. 常量传播。编译器可以认定 `const int x = 1;` 的值永远是 1，把所有读取都换成常量，开头的例子就是这样。

常量求值中不允许未定义行为，所以编译期能准确地区分这两种情况：

```cpp title="const-cast-constexpr.cpp" error
constexpr int f() {
  const int x = 1;
  const_cast<int&>(x) = 2;    // 修改 const 对象
  return x;
}
static_assert(f() == 1);      // error: 不是常量表达式

constexpr int g() {
  int x = 1;
  const int& r = x;
  const_cast<int&>(r) = 2;    // OK：x 不是 const 对象
  return x;
}
static_assert(g() == 2);      // OK
```

本机 Clang 的说明是 `modification of object of const-qualified type 'const int' is not allowed in a constant expression`。

## 去掉常量性（¶6、¶7）

其他几种具名转换都规定不能**去掉常量性**（casts away constness，[[g:casts-away-constness]]），这个术语就定义在这里。

¶6 设 `T1` 与 `T2` 不同。取 `T1` 的一个 *n* 层限定分解，`T2` 的形式是 cv2<sub>0</sub> P2<sub>0</sub> ⋯ cv2<sub>n</sub> U2。把 `T2` 每层的 cv 套到 `T1` 的骨架上，得到 cv2<sub>0</sub> P1<sub>0</sub> ⋯ cv2<sub>n</sub> U1。如果 `T1` 不能通过限定转换变成这个类型，从 `T1` 到 `T2` 的转换就去掉了常量性。

**限定转换**（qualification conversion，[[conv.qual]]）是隐式的加 cv 转换。它只能加 cv，并且在某一层加 `const` 时，外面的各层也都必须是 `const`。所以去掉常量性有两种情况：

1. 真的去掉某一层的 cv，例如 `const int*` 到 `int*`；
2. 在不安全的位置加 `const`，例如 `int**` 到 `const int**`。

第 2 种看上去是在加 `const`，实际上和第 1 种一样危险：

```cpp run title="unsafe-add-const.cpp" ub
const int ci = 0;

int main() {
  int* p = nullptr;
  int** pp = &p;
  auto cpp = const_cast<const int**>(pp);  // 必须用 const_cast
  *cpp = &ci;   // 合法：把 const int* 存进 p
  *p = 1;       // UB: 通过 p 修改了 const 对象 ci
}
```

整个过程中没有一处明显去掉 `const` 的写法，最后却修改了 const 对象。本机运行时程序在 `*p = 1` 处崩溃，因为 `ci` 在只读段里。正因如此，`int**` 到 `const int**` 不是限定转换，不能隐式进行，`static_cast` 也不行，只能用 `const_cast`。安全的写法是同时给中间层加 `const`：`int**` 到 `const int* const*` 是合法的隐式转换。

¶7 把引用归结为指针：如果 `T1*` 到 `T2*` 的转换去掉了常量性，那么 `T1` 左值到 `T2` 左值的左值引用转换、`T1` 表达式到 `T2` 亡值的右值引用转换，也去掉了常量性。

各种转换与去掉常量性的关系：

| 转换 | 能否去掉常量性 | 出处 |
|---|---|---|
| `const_cast` | 能 | 本节 |
| `static_cast` | 不能 | [[expr.static.cast]] 各项都要求 cv 不减少 |
| `reinterpret_cast` | 不能 | [[expr.reinterpret.cast#2]] |
| `dynamic_cast` | 不能 | [[expr.dynamic.cast#1]] |
| C 风格转换 | 能，它会尝试 `static_cast` 或 `reinterpret_cast` 后接 `const_cast` | [[expr.cast#4]] |

把去掉 `const` 这件危险的事集中到一个显眼的关键字上，便于审查和搜索。

## 不在 const_cast 范围内的转换（¶8）

¶8 是一条注：有些只涉及 cv 变化的转换也不能用 `const_cast` 完成。

- 函数指针之间的转换不在范围内，因为这样得到的值一经使用就是未定义行为。
- 出于同样的原因，成员函数指针之间的转换也不在范围内，特别是从指向 `const` 成员函数的指针到指向非 `const` 成员函数的指针。`void (S::*)() const` 和 `void (S::*)()` 的函数类型不同，不是只差 cv 的相似类型。

```cpp title="const-cast-pmf.cpp" error
struct S { void f() const; };

void t() {
  void (S::*p)() const = &S::f;
  auto q = const_cast<void (S::*)()>(p);  // error: 成员函数指针
}
```

## 正当用途

第一种是调用 const 正确性不足的旧接口。C 库或老代码的参数本应是 `const char*`，却写成了 `char*`，而你确认它不会写入：

```cpp run title="legacy-api.cpp" ok
void legacy_api(char* s) { (void)s; }   // 实际上不修改 s

int main() {
  const char* msg = "hello";
  legacy_api(const_cast<char*>(msg));   // OK：legacy_api 不写入
}
```

第二种是用 const 版本实现非 const 版本，避免重复代码：

```cpp run title="const-overload.cpp" ok
#include <cstddef>

class Buffer {
  char data_[16]{};
public:
  const char& at(std::size_t i) const {
    // ……复杂的边界检查……
    return data_[i];
  }
  char& at(std::size_t i) {
    // 能调用到这个重载，说明 *this 不是 const 对象
    return const_cast<char&>(static_cast<const Buffer&>(*this).at(i));
  }
};

int main() {
  Buffer b;
  b.at(3) = 'x';
  return b.at(3) == 'x' ? 0 : 1;
}
```

C++23 的显式对象形参（`this auto& self`）提供了另一种去重的办法，不再需要 `const_cast`。

第三种是去掉 `volatile`，例如把 `volatile` 缓冲区交给不接受 `volatile` 的函数。同样，如果对象本身是 volatile 对象，通过非 volatile 的 glvalue 访问它是未定义行为（[[dcl.type.cv]]）。

## 常见误解

!!! pitfall "去掉 const 之后不写入就一定安全"
    就当前代码而言是这样，但不写入往往要靠被调用的函数保证。一旦那个函数改成写入，未定义行为就悄悄出现了。

!!! pitfall "字符串字面量"
    `char* p = const_cast<char*>("abc"); p[0] = 'x';` 是未定义行为：字符串字面量是 const 对象，通常在只读段里，运行时会直接崩溃。

!!! pitfall "int** 到 const int** 只是加了 const"
    见第 6 段的例子：这个转换能让你不写任何去掉 `const` 的代码就修改 const 对象，所以语言把它算作去掉常量性。

## 思考题

!!! question "思考题 1"
    `const int* const* p;` 下，`const_cast<int* const*>(p)` 和 `static_cast<const int* const* const>(p)` 是否合法？前者是否去掉了常量性？

<details markdown="1">
<summary>答案</summary>

`const_cast<int* const*>(p)` 合法：两个类型相似，每层的 P 相同，只改了最内层 `int` 的 `const`。它去掉了常量性，因为 `const int* const*` 不能通过限定转换变成 `int* const*`。

`static_cast<const int* const* const>(p)` 也合法。prvalue 的顶层 `const` 会被丢弃，实际上是转换到 `const int* const*`，也就是同类型转换，[[expr.static.cast#5]] 要求的隐式转换序列存在。
</details>

!!! question "思考题 2"
    `struct S { mutable int m; int n; }; const S s{};` 下，`const_cast<S&>(s).m = 1;` 和 `const_cast<S&>(s).n = 1;` 各怎样？

<details markdown="1">
<summary>答案</summary>

`s` 是 const 对象，`s.n` 是它的非 `mutable` 子对象，因而也是 const 对象，修改它是未定义行为。

`s.m` 是 `mutable` 成员，不是 const 对象（[[basic.type.qualifier]]），修改它是合法的。而且这里根本不需要 `const_cast`：按 [[expr.ref#8.2]]，`mutable` 成员不继承对象表达式的 `const`，`s.m = 1;` 直接就能编译。
</details>

## 小结

!!! summary
    - `const_cast` 只改 cv：用于相似的对象指针和数据成员指针（¶3），以及对应的左值、亡值引用（¶4）；类和数组的 prvalue 可以先实质化再转换为亡值（¶4.3）。
    - 不适用于类型不相似的指针、函数指针、成员函数指针，以及非指针非引用类型。
    - 转换本身从不是未定义行为；修改 const 对象才是（[[dcl.type.cv]]），要看对象本身是否为 const。
    - 去掉常量性（¶6、¶7）指把目标的 cv 套到源类型上后不构成限定转换，包括删掉某层 cv 和在不安全位置加 `const` 两种情况。
    - 只有 `const_cast` 和 C 风格转换能去掉常量性。
