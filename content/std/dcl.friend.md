---
title: friend 说明符
summary: 这一节只有一句话，友元的规则都在 [class.friend]；本页整理 friend 声明的写法：友元函数与友元类型、friend class X 与 friend X 的区别、模板形参作友元、C++26 的友元包展开，以及 friend 能与哪些说明符组合。
status: done
papers: P2893R3
related: class.friend, dcl.pre, dcl.type.elab, temp.friend, basic.lookup.argdep, dcl.inline
tags: 声明, 说明符, 友元, 访问控制
updated: 2026-10-19
---

!!! tldr
    - [dcl.friend] 只说 `friend` 用于授予访问权，规则都在 [[class.friend]]。
    - `friend class X;` 在找不到 `X` 时会声明一个新类；`friend X;` 要求 `X` 已经声明，`X` 不是类类型时整条声明被忽略。
    - 模板形参只能写成 `friend T;`，不能写 `friend class T;`。
    - C++26 起一条友元声明可以列出多个类型，并且可以展开包：`friend Ts...;`。
    - `friend` 不能与存储类说明符或 `virtual` 组合；类内定义的友元函数只能通过实参依赖查找找到。

¶1 这一节只有一句话：

!!! std
    The `friend` specifier is used to specify access to class members; see [class.friend].

友元能访问什么、友元关系为什么不传递也不继承，这些都在 [[class.friend]] 和 [[class.access]]。下面整理的是 `friend` 在语法上的几种写法，相关规则散在 [[dcl.pre]]、[[dcl.spec.general]]、[[dcl.type.elab]] 等处。

## 友元函数与友元类型

| 形式 | 写法 | 例子 |
|---|---|---|
| 友元函数 | 普通的函数声明或定义，说明符里有 `friend` | `friend void f(X&);`、`friend bool operator==(const X&, const X&) = default;` |
| 友元类型 | *friend-type-declaration*：`friend` 加一个或多个类型 | `friend class Y;`、`friend Y;`、`friend Ts...;` |

不声明函数的友元声明必须是 *friend-type-declaration*（[[class.friend#3]]）。只要一条声明符合 *friend-type-declaration* 的语法，就按它处理（[[dcl.pre#3]]），所以 `friend C;` 不会被当成一条只有说明符、缺了声明符的普通声明。

### friend class X 与 friend X

```cpp run ok
class C;
typedef C Ct;
class X {
    friend C;          // C 必须已声明（C++11 起）
    friend Ct;         // typedef 名也可以，友元是 C
    friend class D;    // 找不到 D 时，在外围命名空间声明一个新类 D
    friend int;        // 不是类类型，忽略（C++11 起合法）
};
int main() { }
```

两种写法的区别在于找不到名字时怎么办：

- `friend class D;` 用的是详述类型说明符（`class`、`struct` 加名字）。如果在最内层外围命名空间里找不到 `D`，它就声明一个新类 `D`，属于那个命名空间。但这条声明不让普通名字查找找到 `D`，要使用它还得在命名空间里另外声明（[[dcl.type.elab#4]]）。
- `friend D;` 中的 `D` 是普通的类型名，必须能查到，找不到就报错，不会引入新类。

<div class="compare" markdown="1">

```cpp run ok
struct S { friend class Later; };
// 详述类型说明符可以引用它
class Later* p = nullptr;
int main() { }
```

```cpp error
struct S { friend class Undeclared; };
Undeclared* p;   // error: 查不到
struct T { friend Unknown; };
                 // error: Unknown 未声明
```

</div>

### 模板形参作友元

```cpp run ok
template<class T> class Box {
    int secret = 42;
    friend T;      // T 是类时成为友元，否则忽略
};
struct Inspector { int peek(Box<Inspector>& b) { return b.secret - 42; } };
Box<int> bi;       // OK: friend int; 被忽略
int main() { Box<Inspector> b; return Inspector{}.peek(b); }
```

C++11 起可以写 `friend T;`。如果 `T` 实例化为 `int` 这样的非类类型，这条声明被忽略，不会报错。`friend class T;` 则非良构，因为详述类型说明符里的名字不能是 typedef 名或模板类型形参（[[dcl.type.elab#6]]）：

```cpp error
template<class T> class Box2 {
    friend class T;   // error: T 是模板形参
};
```

## 友元列表与包展开 {{c++26}}

```cpp run ok
template<class... Ts>
class Registry {
    int count = 0;
    friend Ts...;          // 包中每个类都是友元
};
struct A; struct B;
struct A { int get(Registry<A, B>& r) { return r.count; } };
struct B { void inc(Registry<A, B>& r) { ++r.count; } };

struct P; struct Q;
class Multi { friend P, Q; };   // 一条声明列出多个友元

int main() {
    Registry<A, B> r;
    B{}.inc(r);
    return A{}.get(r) - 1;      // 0
}
```

C++26 起，*friend-type-declaration* 可以用逗号列出多个类型，每个后面都可以跟 `...` 展开包（[[P2893R3]]）。C++23 及以前，一条友元声明只能有一个类型，要让一个包里的所有类型都成为友元，只能绕道，例如 passkey 惯用法。[[class.friend#3]] 的例子里还有混合写法 `friend Ts::Nested..., Us...;`。本机 Clang 23 在 `-std=c++23` 下也接受这种写法，只给一条 C++26 扩展的警告。

## friend 能和哪些说明符组合

- 至多一个 `friend`（[[dcl.spec.general#2]]）。
- 不能有存储类说明符：`friend static void f();` 非良构（[[class.friend#7]]）。
- 不能有 `virtual`：友元函数不是这个类的成员，而 `virtual` 只能用于本类的非静态成员函数（[[dcl.fct.spec#2]]）。
- 可以有 `inline`、`constexpr`、`consteval`。带 `inline` 的友元声明必须是定义，或者这个函数之前已经声明为 inline（[[dcl.inline#1]]）。
- 类内定义的友元函数（`friend void f() { }`），如果类附属于全局模块（即不在具名模块里），隐式是 inline 的（[[class.friend#6]]）。

```cpp error
struct S {
    friend static void f();      // error: 存储类说明符
    friend virtual void g();     // error: virtual
};
```

!!! impl "Clang 不检查 friend inline 的非定义声明"
    按 [[dcl.inline#1]]，`struct S { friend inline void f(); };` 非良构：`f` 之前没有声明为 inline，这里也不是定义。本机 Clang 23 接受这段代码，不给诊断。

## 只能靠 ADL 找到的友元函数

```cpp run ok
struct Money {
    long cents;
    friend Money operator+(Money a, Money b) { return {a.cents + b.cents}; }
};
int main() {
    Money m = Money{100} + Money{50};   // OK: 通过实参类型 Money 找到 operator+
    return int(m.cents) - 150;
}
```

如果一个友元函数第一次声明就在类里，它属于外围命名空间，但普通的非限定查找和限定查找都找不到它，只有**实参依赖查找**（ADL，按实参的类型去相关的类和命名空间里找函数，[[basic.lookup.argdep]]）能找到。上面的 `operator+` 就是这样，这种写法叫隐藏友元（hidden friend）：它不会出现在无关的重载决议里。没有类类型实参时，就找不到它：

```cpp error
struct S { friend void f() { } };
void g() { f(); }    // error: f 只能经 ADL 找到，这里没有实参
```

友元声明的名字落在哪个作用域，见 [[dcl.meaning.general]] 和 [[class.friend]]。

!!! history "历史与演进"
    - C++98：友元类型只能写成 `friend class X;`，不能用 typedef 名或模板形参。
    - C++11：允许 `friend X;`、`friend T;` 和 typedef 名，非类类型被忽略。
    - C++20：具名模块中，类内定义的友元函数不再隐式 inline。
    - C++26：友元列表与包展开（[[P2893R3]]）。

!!! question "思考题"
    `template<class T> class W { friend T; };` 中，`T` 是 `const Foo` 时，`Foo` 是 `W<T>` 的友元吗？`T` 是 `Foo&` 呢？

<details markdown="1">
<summary>答案</summary>

[[class.friend#3]] 规定，友元类型说明符指代一个（可能带 cv 限定的）类类型时，那个类成为友元，否则这个说明符被忽略。所以 `T` 为 `const Foo` 时 `Foo` 是友元；`Foo&` 是引用类型，不是类类型，`friend T;` 被忽略。本机 Clang 23 中，`Foo` 的成员函数访问 `W<Foo&>` 的私有成员会报 "is a private member" 错误。
</details>
