---
title: 友元
summary: 友元声明让一个函数或类可以指名本类的 private 和 protected 成员，但不使它成为成员；在类内定义的友元函数只能经实参依赖查找找到；友元关系不继承、不传递；友元声明指向哪个实体、不把名字引入作用域。
status: done
papers: P2893R3
related: dcl.friend, class.access, class.protected, temp.friend, basic.lookup.argdep, basic.scope.scope, dcl.meaning, dcl.inline, class.local
tags: 类, 友元, 访问控制, ADL, 隐藏友元
updated: 2026-10-19
---

!!! tldr
    - 友元是被授权指名本类 private 和 protected 成员的函数或类。它不是成员：友元函数没有 `this`，也不受所在访问区段的影响。
    - 友元类的基类说明符、成员声明和嵌套类都享有授权；授权只覆盖被点名的那个实体，不继承、不传递。
    - 在类里首次声明的友元函数，普通名字查找找不到，只能经实参依赖查找（ADL）找到，这就是隐藏友元，适合用来写运算符。
    - 非限定的友元函数声明指向最内层的外围命名空间：`friend void h(int);` 声明的是那里的 `h`，而不是已有的全局 `::h`。
    - `friend T;` 在 `T` 不是类类型时被忽略；C++26 允许 `friend Ts...;` 一次把整个包设为友元。

```cpp run title="friend-vs-member.cpp" ok
class X {
    int a = 0;
    friend void friend_set(X*, int);   // 友元：非成员
public:
    void member_set(int);              // 成员
};
void friend_set(X* p, int i) { p->a = i; }  // 显式传入对象
void X::member_set(int i) { a = i; }        // 隐式的 this

int main() {
    X obj;
    friend_set(&obj, 10);
    obj.member_set(10);
}
```

有些操作逻辑上属于类的接口，却不适合写成成员函数：左右对称的二元运算符、流输出运算符、需要同时看到两个类内部的函数。**友元**（friend）为它们提供了访问私有成员的途径。`friend` 说明符的语法见 [[dcl.friend]]，模板相关的友元规则见 [[temp.friend]]。

## 友元得到什么（¶1–¶2）

¶1 类的友元是获得授权、可以指名该类 private 和 protected 成员的函数或类。类用友元声明指定自己的友元。友元声明给予特殊的访问权，但不会让被指定者成为这个类的成员。

不是成员，意味着友元函数没有 `this`，不能写成 `obj.friend_set(...)` 来调用，也不能是虚函数。另一个类的虚成员函数可以被声明为友元，因为友元关系只管访问权。

¶2 把一个类声明为友元，它的 *base-specifier* 和成员声明中就可以指名授权类的 private 和 protected 成员：

```cpp run title="friend-class.cpp" ok
class A {
    class B { };
    enum { N = 4 };
    friend struct X;
};
struct X : A::B {      // OK: 基类说明符
    A::B mx;           // OK: 成员声明
    int arr[A::N];     // OK
    class Y {
        A::B my;       // OK: 嵌套类也是 X 的成员
    };
};
int main() { X x; (void)x; }
```

成员声明包括成员函数的定义（无论写在类内还是类外）、嵌套类以及嵌套类的成员，因为访问权沿嵌套传递（[[class.access#2]]）。友元类的友元则不在其中，友元关系不传递（¶9）。

```cpp title="friend-class-scope.cpp" error
class X {
    enum { a = 100 };
    friend class Y;
};
class Y { int v[X::a]; };   // OK: Y 是 X 的友元
class Z { int v[X::a]; };   // error: X::a 是 private 的
```

## 友元声明的前提（¶4、¶7、¶8）

¶4 的注说明，友元声明指代一个实体，而不是一个名字下的全部重载。另一个类的成员函数可以是友元，构造函数和析构函数也可以：

```cpp
class Y {
    friend char* X::foo(int);   // 只有这一个重载是友元
    friend X::X(char);          // 构造函数
    friend X::~X();             // 析构函数
};
```

想把一组重载都设为友元，要逐个声明。

¶8 第一句要求：友元声明所指定的成员，在包含这个友元声明的类中必须可访问。不能借友元声明点名别的类的私有成员函数：

```cpp title="friend-member-access.cpp" error
class X {
    void priv();
public:
    void pub();
};
class Y {
    friend void X::pub();    // OK
    friend void X::priv();   // error: X::priv 在 Y 中不可访问
};
```

¶8 第二句说明，友元声明写在类的 private、protected 还是 public 部分，含义都一样。¶7 友元声明的 *decl-specifier-seq* 中不能出现存储类说明符，如 `static`、`extern`。

## 友元关系不继承、不传递（¶9）

```cpp title="friend-not-inherited.cpp" error
class A {
    friend class B;
    int a;
};
class B {
    friend class C;
};
class C {
    void f(A* p) { p->a++; }   // error: 友元的友元不是友元
};
class D : public B {
    void f(A* p) { p->a++; }   // error: 友元的派生类不是友元
};
```

¶9 友元关系既不继承，也不传递。

两个方向都不继承。友元的派生类不是友元，如上例的 `D`。授权类的派生类也不把基类的友元当作自己的友元：`B` 是 `A` 的友元，不意味着 `B` 能访问 `class A2 : public A` 新增的私有成员。不过 `B` 仍可以经由 `A2` 对象访问继承自 `A` 的成员，这时依据的是 [[class.access.base]] 中关于指名类的递归规则（¶5.7）。

友元是授权类单方面、点对点的信任声明。如果友元关系可以继承，任何人从友元派生一个类就能获得访问权；如果可以传递，信任的边界就不再由授权类控制。

## 友元类型声明（¶3）

¶3 不声明函数的友元声明必须是 ***friend-type-declaration***。如果其中的 *friend-type-specifier* 指代一个（可能带 cv 限定的）类类型，这个类就成为友元；否则这个说明符被忽略。

```cpp title="friend-type.cpp" error
class C;
typedef C Ct;
class X1 {
    friend C;          // OK: C 是友元
};
class X2 {
    friend Ct;         // OK: 经 typedef，友元是 C
    friend D;          // error: 找不到 D
    friend class D;    // OK: 声明了一个新类 D
};
template<class T> class R1 { friend T; };
R1<int> ri;            // OK: friend int; 被忽略
```

不带类关键字的 `friend D;` 只查找已有的名字，不会引入新类；`friend class D;` 是详述类型说明符，找不到时会声明一个新类。忽略非类类型的规定是为模板准备的：`friend T;` 中的 `T` 可能被实例化为 `int`，这时不报错，只是没有效果。

### 包展开 {{c++26}}

C++26 允许 *friend-type-specifier* 后跟 `...` 构成包展开，一个声明里也可以用逗号列出多个友元类型（[[P2893R3]]）：

```cpp run title="variadic-friends.cpp" ok
template<class... Ts>
class Passkey {
    friend Ts...;              // 所有 Ts 都是友元
    Passkey() = default;       // 只有友元能构造
};
class Owner;
class Auditor;
class Resource {
public:
    // 只有能造出 Passkey 的类才能调用
    void reset(Passkey<Owner, Auditor>) {}
};
class Owner {
public:
    void go(Resource& r) { r.reset({}); }
};
class Auditor {
public:
    void go(Resource& r) { r.reset({}); }
};
int main() {
    Resource r;
    Owner{}.go(r);
    Auditor{}.go(r);
    // r.reset({});            // error: Passkey() 是 private 的
}
```

C++23 及以前，这种通行证（passkey）写法要为每种友元个数各写一个版本。Clang 23 在 `-std=c++2c` 下支持这一特性，在更早的模式下作为扩展接受并给出 `-Wc++26-extensions` 警告。

## 在类内定义友元函数（¶5–¶6）

¶5 当且仅当类不是局部类（[[class.local]]）、且函数名是非限定名时，才可以在友元声明里定义函数：

```cpp
class M {
    friend void f() { }   // 定义了 M 外围命名空间中的 f，不是成员函数
};
```

要求非限定名，是因为 `friend void N::g();` 指代的是一个已有的函数，定义它应当在它所属的作用域里进行。排除局部类，是因为这样的函数属于外围命名空间，而在块作用域里的类中定义一个命名空间作用域的函数，无从安排。

¶6 这样定义的函数如果附属于全局模块，就隐式为 `inline`（[[dcl.inline]]），所以在头文件的类定义里定义友元函数不会违反 ODR。在具名模块中这样定义的函数不是隐式 inline 的，与具名模块中类内定义的成员函数一致，这样模块接口里的实现细节改变不必让所有导入者重新编译。注 3 补充，在类外定义的友元函数不在类的作用域中。

### 隐藏友元

```cpp title="hidden-friend.cpp" error
namespace N {
    struct V {
        int x;
        friend bool operator==(V a, V b) { return a.x == b.x; }
        friend void touch(V) {}
        friend void nonadl() {}   // 没有与 V 相关的形参
    };
    struct Conv {
        Conv(V) {}
        friend void sink(Conv) {}
    };
}
int main() {
    N::V a{1}, b{1};
    bool e = (a == b);   // OK: ADL 在关联类 N::V 中找到
    touch(a);            // OK: 同上
    N::touch(a);         // error: 限定查找找不到
    nonadl();            // error: 无从关联，永远无法调用
    sink(a);             // error: 关联类是 V，不包括 Conv
    sink(N::Conv(a));    // OK
    return e;
}
```

在类里首次声明（通常同时定义）的友元函数，普通的名字查找，无论限定还是非限定，都找不到它。它只能通过**实参依赖查找**（[[g:argument-dependent-lookup|ADL]]，[[basic.lookup.argdep]]）找到：调用的实参类型以这个类为关联类时，ADL 会查看这个类的友元。这样的函数叫做[[g:hidden-friend|隐藏友元]]（hidden friend）。

原因是友元声明不把名字绑定到任何作用域（¶10，[[basic.scope.scope#2.9]]）。函数属于外围命名空间，但在那里出现匹配的普通声明之前，普通查找看不到它。

运算符常写成隐藏友元，理由有四个：

1. 候选集更小。命名空间作用域的 `operator==` 会参与该命名空间里每一次 `==` 的重载决议；隐藏友元只在实参涉及这个类时才成为候选，编译时间和诊断信息的长度都会受益。
2. 不会因隐式转换被意外选中。上例的 `sink(a)` 说明，`V` 能转换成 `Conv` 并不会让 ADL 去查看 `Conv`。
3. 左右对称。作为非成员，左右两个操作数都可以发生隐式转换，只要至少有一个操作数关联到这个类；成员运算符的左操作数不能转换。
4. 能直接访问私有成员，不需要额外的 getter。

### 类模板中定义的友元函数

类模板中定义的友元函数，每个特化各定义一个不同的非模板函数（[[temp.friend]]）。如果它的签名不依赖模板参数，两个特化就会定义同一个函数两次：

```cpp title="friend-in-template.cpp" error
template<class T> struct Y {
    friend void ff() {}   // 每个特化都定义 ::ff()
};
Y<int>  yi;
Y<char> yc;               // error: ::ff() 重定义
```

让签名依赖 `T` 就没有问题，例如 `friend Y operator+(Y, Y)`，每个特化各自定义一个 `operator+`。

!!! pitfall "非模板友元与同名的函数模板"
    ```cpp
    template<class T> class Box {
        friend void show(const Box&);   // 非模板函数 show(const Box<T>&)
    };
    template<class T> void show(const Box<T>&) {}  // 另一个函数模板
    int main() { Box<int> b; show(b); }
    ```
    `Box<int>` 的友元声明声明了一个非模板函数 `show(const Box<int>&)`，它与后面的函数模板无关。重载决议在两者同样匹配时偏好非模板函数，于是调用了这个从未定义的函数。本机 Clang 编译通过、默认不给警告，链接时找不到 `show(Box<int> const&)`。要把函数模板的特化设为友元，先声明模板，再写 `friend void show<>(const Box&);`；或者直接在类内定义。

## 友元声明不绑定名字（¶10）

¶10 的注说明，友元声明从不绑定名字（[[dcl.meaning]]、[[dcl.type.elab]]）。它声明的实体属于某个外围作用域，但不把名字放进任何作用域供普通查找使用。具体来说：

- 非限定名的友元函数声明，指向最内层的外围命名空间里的函数，更外层的作用域不在考虑之列；
- 非限定名的友元类声明（`friend class Z;`）找不到已有的类时，在最内层的外围命名空间中声明它，局部类则是在最内层的块作用域中；
- 在那个作用域里出现普通声明之前，普通查找找不到这个名字。

```cpp title="friend-binding.cpp" error
void h(int);
template<class T> void f2(T);
namespace A {
    class X {
        friend void f(X);          // A::f(X) 是友元
        class Y {
            friend void g();       // A::g 是友元
            friend void h(int);    // A::h 是友元，不考虑 ::h
            friend void f2<>(int); // ::f2<>(int) 是友元
        };
    };
    // 这里看不到 A::f、A::g、A::h
    X x;
    void g() { f(x); }   // 定义 A::g；f(x) 经 ADL 找到 A::f
    void f(X) { }        // 定义 A::f
    void h(int) { }      // 定义 A::h
    // 这里 A::f、A::g、A::h 可见，并且已知是友元
}
using A::x;
void h() {
    A::f(x);             // OK
    A::X::f(x);          // error: f 不是 A::X 的成员
    A::X::Y::g();        // error: g 不是 A::X::Y 的成员
}
```

这是标准例 8。注意 `friend void h(int);` 声明的是 `A::h`，即使全局的 `::h` 早已声明、签名也完全相同。想把全局函数设为友元，要写 `friend void ::h(int);`。`f2<>` 带模板实参列表，是在点名一个已有模板的特化，所以会查找到全局的 `f2`。

局部类中的友元规则更严格：

```cpp title="friend-in-local-class.cpp" error
class X;
void a();
void f() {
    class Y;
    extern void b();
    class A {
        friend class X;   // OK: 但这是一个新的局部类 X，不是 ::X
        friend class Y;   // OK: 块作用域中的 Y
        friend class Z;   // OK: 在块作用域引入局部类 Z
        friend void a();  // error: 不考虑 ::a
        friend void b();  // OK: 块作用域中的 extern 声明
        friend void c();  // error
    };
    X* px;                // OK: 但找到的是 ::X
    Z* pz;                // error: 找不到 Z
}
```

这是标准例 9。局部类的友元函数声明只在最内层的块作用域里找已有的声明，找不到就是错误，不会像非局部类那样在命名空间中引入新函数。`friend class X;` 与 `friend class Z;` 声明的局部类也不绑定名字，所以后面的 `X*` 找到的是 `::X`，`Z*` 什么也找不到。

## 实现视角

!!! impl
    - 友元关系纯粹是编译期的访问控制，不影响 ABI。
    - 隐藏友元在编译器里通常这样实现：函数声明照常放进命名空间的符号表，但带上不可见的标记，普通查找跳过它，ADL 在关联类的友元列表里找到它。
    - 标准库实现大量使用隐藏友元来缩小重载候选集，例如迭代器的比较运算符，这是一项常见的编译性能优化。

## 历史与演进

!!! history
    - C++98 之前的 ARM 规则中，类内声明的友元函数名会注入外围作用域。C++98 标准化时取消了这种注入，改为普通查找不可见、只能经 ADL 找到，隐藏友元的行为由此而来。
    - C++11 加入不带类关键字的 `friend T;`，可用于模板参数和 typedef 名，非类类型时被忽略。
    - C++20 引入模块后，具名模块中在类内定义的友元函数不再隐式 inline，即 ¶6 中附属于全局模块的限定。
    - C++26 {{c++26}} 的 [[P2893R3]] 加入可变参数友元：`friend Ts...;`，以及在一个声明中列出多个友元类型。

## 常见误解

!!! pitfall "`friend void h(int);` 指向已有的全局 `::h`"
    它声明并授权的是最内层外围命名空间中的 `h`。要授权全局函数，写 `friend void ::h(int);`。

!!! pitfall "随便什么函数都能写成隐藏友元"
    没有实参关联到这个类时，隐藏友元无法调用。无参数或参数与该类无关的函数不要这样定义。

!!! pitfall "派生类继承基类的友元"
    友元关系不继承。基类的友元也不能访问派生类新增的私有成员。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct S {
        friend void f(S) {}
        friend void g(int) {}
    };
    void t() { f(S{}); g(1); }
    ```
    `t` 中哪个调用合法？怎样让另一个也能被调用？

<details markdown="1">
<summary>答案</summary>

`f(S{})` 合法：ADL 在关联类 `S` 中找到隐藏友元 `f`。`g(1)` 非良构：实参类型 `int` 没有关联类，ADL 不会查看 `S`，普通查找又找不到 `g`，因为友元声明不绑定名字。

在全局命名空间中再声明一次 `void g(int);` 即可。这个普通声明与友元声明对应（[[basic.scope.scope]]），让普通查找能找到这个名字，它指向的仍是类中定义的那个函数。
</details>

!!! question "思考题 2"
    `class A { int x; friend class B; }; class B { public: struct N { int get(A& a) { return a.x; } }; };` 中，`B::N::get` 能访问 `A::x` 吗？如果 `N` 不是 `B` 的嵌套类，而是 `B` 的友元类呢？

<details markdown="1">
<summary>答案</summary>

嵌套类可以。¶2 规定友元类的成员声明中可以指名 `A` 的私有成员；`N` 是 `B` 的成员，它的成员函数定义也在授权范围内，访问权沿嵌套传递（[[class.access#2]] 及脚注 89）。

如果 `N` 只是 `B` 的友元（`class N; class B { friend class N; };`），就不行。友元关系不传递（¶9），`N` 只是友元的友元。
</details>
