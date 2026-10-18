---
title: friend 说明符
summary: friend 说明符只有一句话：它用于指定对类成员的访问权，语义全部在 [class.friend]。本页整理 friend 声明的几种语法形式、与其他说明符的组合，以及 C++26 的可变参数友元
status: done
papers: P2893R3
related: class.friend, dcl.pre, dcl.type.elab, temp.friend, basic.lookup.argdep, dcl.inline
tags: 声明, 说明符, 友元, 访问控制
updated: 2026-10-17
---

[dcl.friend] 是整本标准中最短的条款之一，只有一句话：

!!! std
    The `friend` specifier is used to specify access to class members; see [class.friend].

    friend 说明符用于指定对类成员的访问权；见 [class.friend]。

语义（友元能访问什么、友元关系不传递不继承、友元函数的名字在哪里可见）都在 [[class.friend]] 和 [[class.access]] 中。本页作为"说明符视角"的索引，整理 `friend` 在**语法**上的几种出现形式和组合规则——这些规则分散在 [[dcl.pre]]、[[dcl.spec.general]]、[[dcl.type.elab]]、[[class.mem.general]] 等多处。

## 两种友元声明

`friend` 出现在类的成员声明中，有两种完全不同的语法路径：

| 形式 | 语法 | 例子 |
|---|---|---|
| **友元函数** | 普通的 *member-declaration* / *function-definition*，说明符序列中含 `friend` | `friend void f(X&);`、`friend bool operator==(const X&, const X&) = default;` |
| **友元类型** | *friend-type-declaration*：`friend` *friend-type-specifier-list* `;` | `friend class Y;`、`friend Y;`、`friend Ts...;` |

[[class.friend#3]] 规定：不声明函数的友元声明必须是 *friend-type-declaration*。[[dcl.pre#3]] 则规定：当一个声明同时匹配 *friend-type-declaration* 的语法时，就按它处理——所以 `friend C;` 不会被当成"说明符 `friend` + 类型 `C`、没有声明符"的 *simple-declaration*。

### 友元类型说明符的三种写法

*friend-type-specifier* 可以是 *simple-type-specifier*、*elaborated-type-specifier* 或 *typename-specifier*：

```cpp run ok
class C;
typedef C Ct;
class X {
    friend C;                  // simple-type-specifier：C 必须已声明（C++11 起）
    friend Ct;                 // typedef 名也可以：友元是 C
    friend class D;            // elaborated-type-specifier：若找不到 D，就在最近的外围命名空间引入类 D
    friend int;                // 不是类类型：被忽略（C++11 起合法）
};
int main() { }
```

两种写法的关键区别：

- `friend class D;` 若在最内层外围命名空间（或块）中找不到 `D`，就**声明**一个新类 `D`（它是该命名空间的成员），但**不绑定名字**——在命名空间中仍需另行声明才能按普通查找找到（[[dcl.type.elab#4]]）。
- `friend D;` 是 *simple-type-specifier*，`D` 必须能被查找到；找不到就是错误，不会引入新类。

```cpp error
struct S { friend class Undeclared; };
Undeclared* p;               // error: friend 声明没有把 Undeclared 绑定到命名空间作用域
struct T { friend Unknown; };   // error: Unknown 没有声明
```

```cpp run ok
struct S { friend class Later; };
class Later* p = nullptr;    // OK: 详述类型说明符可以引用（或声明）它
int main() { }
```

### 模板参数作友元

C++11 起可以写 `friend T;`（*simple-type-specifier*）；但 `friend class T;` 是非良构的——详述类型说明符中的名字不能解析为 typedef 名或模板类型参数（[[dcl.type.elab#6]] 的 Note 3）。若 `T` 被实例化为非类类型（如 `int`），`friend T;` 被**忽略**，不是错误：

```cpp run ok
template<class T> class Box {
    int secret = 42;
    friend T;                 // OK: T 是类时它成为友元；T 是 int 时被忽略
};
struct Inspector { int peek(Box<Inspector>& b) { return b.secret - 42; } };
Box<int> bi;                  // OK: friend int; 被忽略
int main() { Box<Inspector> b; return Inspector{}.peek(b); }
```

```cpp error
template<class T> class Box2 {
    friend class T;           // error: T 是模板参数，不能出现在 class-key 后
};
```

## 可变参数友元 {{c++26}}

C++26 的 *friend-type-specifier-list* 允许**逗号分隔多个**友元类型，每个后面都可以跟 `...` 进行包展开（[[P2893R3]]）：

```cpp run ok
template<class... Ts>
class Registry {
    int count = 0;
    friend Ts...;                       // C++26: 包中每个类都是友元
};
struct A; struct B;
struct A { int get(Registry<A, B>& r) { return r.count; } };
struct B { void inc(Registry<A, B>& r) { ++r.count; } };
int main() {
    Registry<A, B> r;
    B{}.inc(r);
    return A{}.get(r) - 1;              // 0
}
```

```cpp run ok
struct P; struct Q;
class Multi {
    friend P, Q;                        // C++26: 一条声明列出多个友元
};
int main() { }
```

在 C++23 及之前，一条友元声明只能有一个类型，而且不能展开包。想让"模板参数包中的每个类型"成为友元，只能借助 passkey 惯用法或递归继承之类的绕路方案。标准中 [[class.friend#3]] 的例子还展示了偏特化中混合展开：`friend Ts::Nested..., Us...;`。

## friend 与其他说明符的组合

- **不能重复**：至多一个 `friend`（[[dcl.spec.general#2]]）。
- **不能与存储类说明符组合**：`friend static void f();` 非良构——[[class.friend#7]] 规定友元声明中不能出现存储类说明符。
- **不能与 `virtual` 组合**：友元函数不是本类的成员，`virtual` 只能用于本类的非静态成员函数（[[dcl.fct.spec#2]]）。
- **可以与 `inline`、`constexpr`、`consteval` 组合**；但若友元声明带 `inline`，它必须是定义，或者该函数之前已被声明为 inline（[[dcl.inline#1]]）。
- 在类内**定义**的友元函数（`friend void f() { }`）：若类附属于全局模块，它隐式是 inline 的（[[class.friend#6]]、[[dcl.inline#5]] Note 4）。

```cpp error
struct S {
    friend static void f();      // error: 友元声明不能有存储类说明符
    friend virtual void g();     // error: virtual 不能用于友元
};
```

!!! impl "Clang 不检查 `friend inline` 的非定义声明"
    按 [[dcl.inline#1]]，`struct S { friend inline void f(); };`（`f` 之前未声明为 inline，且这里不是定义）是非良构的。截至写作时 Clang 接受这段代码且不给诊断。

## 友元函数名字的可见性（概要）

在类内**首次声明**的友元函数（之前在外围命名空间中没有声明）属于外围命名空间，但它的名字**不会**被普通的非限定查找或限定查找找到，只能通过**实参依赖查找**（ADL，[[basic.lookup.argdep]]）找到。这就是"隐藏友元"（hidden friend）惯用法的基础：

```cpp run ok
struct Money {
    long cents;
    friend Money operator+(Money a, Money b) { return {a.cents + b.cents}; }  // hidden friend
};
int main() {
    Money m = Money{100} + Money{50};   // OK: ADL 通过 Money 找到 operator+
    // operator+(1, 2);                 // 找不到：普通查找看不见隐藏友元
    return int(m.cents) - 150;
}
```

```cpp error
struct S { friend void f() { } };
void g() { f(); }    // error: f 只能通过 ADL 找到，而这里没有类类型实参
```

详细规则见 [[class.friend]]、[[dcl.meaning.general]]（友元声明的目标作用域）与 [[basic.lookup.argdep]]。

!!! history "历史与演进"
    - C++98：友元类必须写成 `friend class X;`，不能用 typedef 名或模板参数。
    - C++11："扩展的 friend 声明"：允许 `friend X;`、`friend T;`、`friend typedef名;`，非类类型被忽略。
    - C++20：模块中，类内定义的友元函数不再自动 inline（只有附属于全局模块的才是）。
    - C++26：可变参数友元与友元列表（[[P2893R3]]）。

!!! summary "小结"
    - [dcl.friend] 只是一个指针，真正的规则在 [[class.friend]]。
    - 友元类型有两种写法：`friend class X;`（可引入新类，不绑定名字）和 `friend X;`（X 必须已声明，非类类型被忽略）。
    - `friend` 不能与存储类说明符、`virtual` 组合；可与 `inline`、`constexpr` 组合。
    - C++26：`friend Ts...;`、`friend A, B;`。

!!! question "思考题"
    `template<class T> struct W { friend T; };` 中，若 `T` 是 `const Foo`，`Foo` 会成为友元吗？若 `T` 是 `Foo&` 呢？

<details markdown="1">
<summary>答案</summary>

[[class.friend#3]]："若 *friend-type-specifier* 指代一个（可能 cv 限定的）类类型，该类被声明为友元；否则该说明符被忽略。"所以 `const Foo` 时 `Foo` 是友元（cv 被允许）；`Foo&` 是引用类型，不是类类型，`friend T;` 被忽略，`Foo` 不是友元。
</details>
