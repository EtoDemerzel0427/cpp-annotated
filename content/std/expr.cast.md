---
title: 显式类型转换（强制转换写法）
summary: C 风格转换 (T)e 按固定顺序把自己解释成某个具名转换或它们的组合；它可以无视基类的访问控制，在类不完整时可能不调整指针，所以 C++ 代码应改用具名转换。
status: done
related: expr.type.conv, expr.static.cast, expr.reinterpret.cast, expr.const.cast, expr.dynamic.cast, class.access.base, dcl.name, topics/casts
tags: 类型转换, C 兼容, 访问控制
updated: 2026-10-19
---

!!! tldr
    - `(T)e` 依次尝试 `const_cast`、`static_cast`、`static_cast` 加 `const_cast`、`reinterpret_cast`、`reinterpret_cast` 加 `const_cast`，采用第一个能匹配的解释，即使这个解释是非良构的。
    - 它从不做 `dynamic_cast`，所以 `(Derived*)p` 不做任何运行期检查。
    - 作为 `static_cast` 时，它可以无视 `private`/`protected` 继承，并正确调整指针。
    - 两个类中有一个不完整时，未指定它按 `static_cast` 还是 `reinterpret_cast` 解释，结果指针可能没有调整。
    - 单实参的函数式转换 `T(e)` 与 `(T)e` 完全等价，问题也一样。

## 写法与结果（¶1–¶3）

`(T)e` 是从 C 继承来的强制转换写法，C++ 另有四个具名转换：`static_cast`、`const_cast`、`reinterpret_cast`、`dynamic_cast`。¶2 列出这三种写法，并给出文法：

```text
cast-expression:
    unary-expression
    ( nofun-type-id ) cast-expression
```

文法是右递归的，所以 `(T)a.b` 是 `(T)(a.b)`，`(T)*p` 是 `(T)(*p)`，`(T)a + b` 是 `((T)a) + b`。括号中的 *nofun-type-id*（[[dcl.name]]）是不能写成函数类型的类型名：函数类型没有值，转换到它没有意义。

¶1 结果的类型是 `T`。`T` 是左值引用或函数的右值引用时，结果是左值；是对象的右值引用时，结果是亡值（xvalue）；否则是纯右值（prvalue）。注 1 补充，非类类型的 prvalue 会丢掉 cv 限定，所以 `(const int)3` 的类型是 `int`（[[expr.prop]]）。

¶3 除了下面 ¶4 列出的转换，以及用户通过构造函数或转换函数定义的转换（[[class.conv]]），其他转换都非良构。

单实参的函数式转换 `T(e)` 按 [[expr.type.conv#1]] 与 `(T)e` 等价，本页的一切都适用于它。

## 尝试顺序（¶4）

```cpp title="c-cast-order.cpp" error
struct A { };
struct I1 : A { };
struct I2 : A { };
struct D : I1, I2 { };
A* foo(D* p) {
    return (A*)(p);             // error: 选中 static_cast 解释，而 A 是二义基类
}

int*** ptr = 0;
auto t = (int const* const* const*)ptr;   // OK：const_cast 解释

struct S {
    operator const int*();
    operator volatile int*();
};
int* p = (int*)S();             // error: static_cast + const_cast 有两种解释
```

¶4 强制转换写法可以完成以下五种转换，每种都适用对应具名转换的限制和行为：

| 顺序 | 解释 |
|---|---|
| ¶4.1 | `const_cast` |
| ¶4.2 | `static_cast` |
| ¶4.3 | `static_cast` 后接 `const_cast` |
| ¶4.4 | `reinterpret_cast` |
| ¶4.5 | `reinterpret_cast` 后接 `const_cast` |

一个转换能有多种解释时，采用表中最靠前的那种，即使它导致转换非良构。编译器不是挨个尝试、哪个能编译就用哪个，而是在形式上能匹配就选定。

第一个函数里，`D*` 到 `A*` 在形式上是派生类到基类的 `static_cast`，于是选定它；`A` 是二义基类，转换因此非良构。如果允许退到 `reinterpret_cast`，这里就会默默得到一个没有调整过的错误指针。

`int***` 到 `int const* const* const*` 只添加了 cv 限定，`const_cast` 能完成，它排在最前。

`S` 可以先 `static_cast` 到 `const int*` 或 `volatile int*`，再 `const_cast` 到 `int*`。¶4 规定，`static_cast` 加 `const_cast` 有多种解释时转换非良构。

### 常见写法的实际含义

| `(T)e` | 实际解释 |
|---|---|
| `(int)3.7`、`(double)n`、`(Enum)i` | `static_cast` |
| `(Derived*)base_ptr` | `static_cast`，不检查 |
| `(int*)const_int_ptr` | `const_cast` |
| `(char*)"literal"` | `const_cast` |
| `(long*)int_ptr`、`(std::uintptr_t)ptr` | `reinterpret_cast` |
| `(char*)const_int_ptr` | `reinterpret_cast` 加 `const_cast` |
| `(void)expr` | `static_cast`（[[expr.static.cast#4]]） |

`dynamic_cast` 不在清单里，所以 C 风格转换从不做运行期检查。

## 无视基类的访问控制（¶4.6–¶4.8）

```cpp run title="c-cast-private-base.cpp" ok
struct X { int x = 2; };
struct B { int b = 1; };
struct D : X, private B { int d = 3; };   // B 是私有基类，且不是第一个基类

int main() {
    D d;
    B* pb = (B*)&d;                  // OK：¶4.6，调整到 B 子对象
    D* back = (D*)pb;                // OK：¶4.8，向下转换
    int D::* pm = (int D::*)&B::b;   // OK：¶4.8，基类成员指针到派生类成员指针
    // static_cast<B*>(&d);          // error: B 是不可访问的基类
    return (pb->b == 1 && back == &d && d.*pm == 1) ? 0 : 1;
}
```

¶4 规定，强制转换写法在下列情形中执行 `static_cast` 时，即使基类不可访问，转换也有效：

- ¶4.6 派生类对象的指针或左值、右值，转换到无二义基类的指针或引用；
- ¶4.7 派生类的成员指针，转换到无二义非虚基类的成员指针；
- ¶4.8 无二义非虚基类的对象指针、glvalue 或成员指针，转换到派生类的指针、引用或成员指针。

具名转换做不到这一点：`static_cast` 会因基类不可访问而报错，`reinterpret_cast` 不做地址调整。C 风格转换是语言里唯一能合法穿过私有继承的手段，[[expr.dynamic.cast]] 的例 2 就用它取得了私有基类的指针。访问控制表达的是类作者的设计，这种转换能不留痕迹地绕开它。

## 不完整类（¶5）

```cpp run title="c-cast-incomplete.cpp" unspecified
struct P;
struct Q;
Q* f(P* p) { return (Q*)p; }   // P、Q 此处不完整：解释方式未指定

struct X { int x; };
struct P { int a; };
struct Q : X, P {};            // P 是 Q 的第二个基类，两种解释的结果不同

int main() {
    Q q;
    P* pp = &q;
    return f(pp) == &q ? 0 : 1;   // static_cast 解释得 0；reinterpret_cast 解释得 1
}
```

¶5 操作数和目标类型都可以是指向不完整类的指针。如果两边指向的都是类类型，而其中至少一个不完整，那么未指定采用 `static_cast` 解释还是 `reinterpret_cast` 解释，即使这两个类之间确实有继承关系。

注 2 解释了为什么不要求某一种：类可能在同一翻译单元的后面才定义，多遍扫描的编译器可以按类完整时的样子来解释。GCC、Clang、MSVC 都是在转换处就做决定，看不到继承关系，于是按 `reinterpret_cast` 处理，地址不调整。本机 Clang 23 上这个程序退出码为 1。

具名转换没有这个问题：`static_cast<Q*>(p)` 在类不完整时直接非良构，`reinterpret_cast` 则明确不调整。

## 为什么应改用具名转换

- 意图不可见。从 `(Foo*)p` 看不出它是向下转换、去掉 const 还是重新解释。具名转换各自表达一种意图，也方便搜索。
- 语义随上下文改变，而且没有诊断。`(Derived*)base` 在公有继承时是 `static_cast`；改成私有继承，它照样编译（¶4.6）；去掉头文件让类不完整，它变成 `reinterpret_cast`（¶5）；把基类换成无关的类，它还是能编译。
- 一次能做两件危险的事，比如同时去掉 const 并重新解释类型（¶4.5）。
- `T(e)` 有同样的问题，外表却像一次构造函数调用。

!!! tip "工具"
    GCC 和 Clang 的 `-Wold-style-cast` 对每个 C 风格转换发出警告，但不管函数式写法。Clang-Tidy 的 `cppcoreguidelines-pro-type-cstyle-cast` 和 `google-readability-casting` 能建议对应的具名转换。C++ Core Guidelines 的 ES.48、ES.49 建议避免转换，必须转换时用具名转换。

!!! history
    C 只有 `(T)e` 一种显式转换。C++98 引入四个具名转换，并把 C 风格转换定义为它们的组合，访问控制的例外和不完整类的未指定行为从那时起就存在。C++11 加入了右值引用目标类型，结果是亡值。

## 常见误解

!!! pitfall "`(Derived*)p` 会检查类型"
    它是 `static_cast`，不是 `dynamic_cast`。向下转换到错误的类型是没有任何提示的 UB。

!!! pitfall "`(int)x` 和 `int(x)` 不一样"
    两者完全相同。要禁止窄化，写 `int{x}`；要表明意图，写 `static_cast<int>(x)`。

## 思考题

!!! question "思考题 1"
    `const char* s = "abc"; auto p = (unsigned char*)s;` 被解释成什么？

<details markdown="1">
<summary>答案</summary>

按顺序检查：`const_cast` 不行，`const char*` 和 `unsigned char*` 不是相似类型；`static_cast` 不行，无关对象指针之间不能 `static_cast`；`static_cast` 到 `const unsigned char*` 再 `const_cast` 也不行；单独的 `reinterpret_cast` 不能去掉常量性。最后，`reinterpret_cast` 到 `const unsigned char*` 再 `const_cast` 到 `unsigned char*` 可以，这就是 ¶4.5。

经 `p` 读取是合法的，`unsigned char` 可以访问任何对象；经 `p` 写入则修改了字符串字面量，是 UB。
</details>

!!! question "思考题 2"
    `struct X { int x; }; struct B { int b; }; struct D : X, private B {}; D d;` 在 `D` 的成员和友元之外，`((B&)d).b` 与 `reinterpret_cast<B&>(d).b` 有什么不同？

<details markdown="1">
<summary>答案</summary>

`(B&)d` 按 ¶4.6 是无视访问的 `static_cast`，结果指代 `d` 的 `B` 基类子对象，读 `.b` 没有问题。

`reinterpret_cast<B&>(d)` 不调整地址。`B` 不是第一个基类，`d` 与它的 `B` 子对象不是指针可互转的，所以结果仍然指代 `d` 本身。`D` 与 `B` 不相似，经它访问 `.b` 按 [[expr.ref#10]] 是 UB。
</details>
