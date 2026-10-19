---
title: 友元
summary: 友元授予指名 private/protected 成员的权利但不使其成为成员；友元类的基类说明符与成员声明都享有该权利；友元类型声明（含 C++26 包展开）；在类中定义友元函数（隐藏友元，只能经 ADL 找到）；友元关系不继承、不传递；友元声明不绑定名字
status: draft
papers: P2893R3
related: dcl.friend, class.access, class.protected, temp.friend, basic.lookup.argdep, basic.scope.scope, dcl.meaning, dcl.inline, class.local
tags: 类, 友元, 访问控制, ADL, 隐藏友元
updated: 2026-10-17
---

**友元**（friend）相当于访问控制的白名单：一个类可以指定某些函数或类，允许它们指名自己的 private 和 protected 成员。友元是 C++ 封装模型中有意保留的出口。有些操作在逻辑上属于类的接口，却不适合（或不能）写成成员函数，例如对称的二元运算符、流输出运算符、需要访问两个类内部的函数，以及紧密协作的辅助类。

语法层面的细节（`friend` 说明符可以出现在哪里、能和哪些说明符组合、C++26 的包展开语法）见 [[dcl.friend]]；模板相关的友元规则见 [[temp.friend]]。本页讲语义：友元得到了什么、没有得到什么，以及友元声明对名字查找有什么影响。

## 友元是被授予访问权的非成员（¶1）

¶1：类的友元是获得授权、可以指名该类的 private 和 protected 成员的函数或类。类通过友元声明指定它的友元。友元声明给予特殊的访问权，但**不会使被指定者成为授权类的成员**。

```cpp run title="friend-vs-member.cpp" ok
class X {
    int a = 0;
    friend void friend_set(X*, int);     // 非成员，但可访问 a
public:
    void member_set(int);                // 成员
};

void friend_set(X* p, int i) { p->a = i; }   // 需要显式的对象参数
void X::member_set(int i) { a = i; }         // 隐式 this

int main() {
    X obj;
    friend_set(&obj, 10);
    obj.member_set(10);
}
```

不是成员，意味着：友元函数没有 `this`；不能用 `obj.friend_set(...)` 调用；不能是虚函数（但可以把另一个类的虚成员函数声明为友元）；不受访问说明符的影响（见 ¶8）。

## 友元类：基类说明符与成员声明都享有权利（¶2）

¶2：把一个类声明为友元，意味着在被授权类的 *base-specifier* 和成员声明中，可以指名授权类的 private 和 protected 成员。

```cpp run title="friend-class.cpp" ok
class A {
    class B { };
    enum { N = 4 };
    friend struct X;
};

struct X : A::B {           // OK: 基类说明符中可以指名 A::B
    A::B mx;                // OK: 成员声明中可以
    int arr[A::N];          // OK
    class Y {
        A::B my;            // OK: 友元类的嵌套类的成员同样可以（嵌套类是 X 的成员）
    };
};

int main() { X x; (void)x; }
```

这里的成员声明包括成员函数的定义（无论在类内还是类外）、嵌套类，以及嵌套类的成员，因为访问权沿嵌套传递（[[class.access#2|[class.access.general]/2]]）。但它不包括 `X` 的友元，因为友元关系不传递（¶9）。

```cpp title="friend-class-scope.cpp" error
class X {
    enum { a = 100 };
    friend class Y;
};
class Y { int v[X::a]; };    // OK: Y 是 X 的友元
class Z { int v[X::a]; };    // error: X::a 是 private 的
```

## 友元类型声明（¶3）

¶3：不声明函数的友元声明必须是 ***friend-type-declaration***。如果 *friend-type-specifier* 指代一个（可能 cv 限定的）类类型，该类就被声明为友元；否则这个说明符被忽略。

忽略的规定是为模板设计的：在 `template<class T> class R { friend T; };` 中，`T` 可能实例化为 `int`，这时 `friend int;` 不是错误，只是没有效果。

友元类型说明符的几种形式（[[dcl.friend]] 有更细的语法讨论）：

```cpp title="friend-type.cpp" error
class C;
typedef C Ct;

class X1 {
    friend C;                 // OK: C 是友元（C++11 起可以省略 class）
};
class X2 {
    friend Ct;                // OK: 经 typedef 也行，友元是 C
    friend D;                 // error: 找不到 D——不带 class-key 的形式不会引入新名字
    friend class D;           // OK: 详述类型说明符声明了一个新类 D
};
template<class T> class R1 { friend T; };
R1<int> ri;                   // OK: "friend int;" 被忽略
```

### 包展开 {{c++26}}

C++26 允许 *friend-type-specifier* 后跟 `...` 构成包展开（[[P2893R3]]，"variadic friends"），一个声明中也可以用逗号列出多个友元类型：

```cpp run title="variadic-friends.cpp" ok
template<class... Ts>
class Passkey {
    friend Ts...;                // C++26：所有 Ts 都是友元
    Passkey() = default;         // 只有友元能构造 Passkey
};

class Owner;
class Auditor;

class Resource {
public:
    void reset(Passkey<Owner, Auditor>) {}   // 只有 Owner 或 Auditor 能调用（它们能造出钥匙）
};

class Owner   { public: void go(Resource& r) { r.reset({}); } };
class Auditor { public: void go(Resource& r) { r.reset({}); } };

int main() {
    Resource r;
    Owner{}.go(r);
    Auditor{}.go(r);
    // r.reset({});              // error: Passkey 的默认构造函数是 private 的
}
```

在 C++23 及之前，这种通行证（passkey）惯用法只能针对每种固定的友元数目各写一个特化，或者借助宏。Clang 23 在 `-std=c++2c` 下支持这一特性（在较早的模式下作为扩展接受并给出警告）。

## 友元声明指代实体，不是名字（¶4）

¶4（注 2）：友元声明指代的是一个实体，而不是一个名字的所有重载。另一个类的成员函数可以是友元，构造函数和析构函数也可以：

```cpp
class Y {
    friend char* X::foo(int);    // 只有这一个重载是友元
    friend X::X(char);           // 构造函数可以是友元
    friend X::~X();              // 析构函数也可以
};
```

想把一组重载全部设为友元，需要逐个声明。

## 在友元声明中定义函数（¶5–¶7）

¶5：当且仅当类是非局部类（[[class.local]]）且函数名是非限定名时，才可以在友元声明中定义函数：

```cpp
class M {
    friend void f() { }          // 定义了全局函数 f（M 的友元），不是成员函数
};
```

- 为什么要求非限定名？带限定名的友元声明（`friend void N::g();`）指代一个已有的函数，定义它应该在其所属作用域中进行。
- 为什么排除局部类？友元函数属于外围的命名空间作用域，而在块作用域中的类里定义一个命名空间作用域的函数，在语法和链接上都无法安排（局部类连自己的成员函数都只能在类内定义）。

¶6：这样定义的函数如果附属于全局模块，就隐式为 `inline`（[[dcl.inline]]），因此在头文件的类定义里定义友元函数不会违反 ODR。在具名模块中定义的友元函数不是隐式 inline 的，这一点与模块中的成员函数相同（类内定义的成员函数在具名模块中也不再隐式 inline），这样模块接口中实现细节的变化不必导致导入者重新编译。注 3：在类外定义的友元函数不在类的作用域中。

¶7：友元声明的 *decl-specifier-seq* 中不能出现存储类说明符（`static`、`extern` 等）。

### 隐藏友元（hidden friend）

在类中首次声明（通常同时定义）的友元函数有一个独特的性质：普通的名字查找（无限定查找或限定查找）找不到它的名字，**只能通过实参依赖查找**（ADL，[[basic.lookup.argdep]]）在关联类中找到它。这是因为友元声明不绑定名字（¶10，[[basic.scope.scope]]/2.9）：它把函数声明在外围命名空间中，但在那里出现匹配的普通声明之前，这个名字在该命名空间中不可见。

```cpp title="hidden-friend.cpp" error
namespace N {
    struct V {
        int x;
        friend bool operator==(V a, V b) { return a.x == b.x; }   // 隐藏友元
        friend void touch(V) {}
        friend void nonadl() {}                                    // 没有 V 类型的形参
        operator int() const { return x; }
    };
    struct Conv {
        Conv(V) {}
        friend void sink(Conv) {}
    };
}

int main() {
    N::V a{1}, b{1};
    bool e = (a == b);       // OK: ADL 在关联类 N::V 中找到
    touch(a);                // OK: 同上
    N::touch(a);             // error: 限定查找找不到隐藏友元
    nonadl();                // error: 没有实参，ADL 无从关联；永远无法调用
    sink(a);                 // error: 实参类型是 V，关联类不包括 Conv——不会因为 V 可转换为 Conv 就去查找
    sink(N::Conv(a));        // OK
    return e;
}
```

为什么推荐把运算符写成隐藏友元？

1. **减少重载决议的负担**：命名空间作用域的 `operator==` 会参与该命名空间（以及 using 指令引入它的地方）中每一次 `==` 的重载决议；隐藏友元只在实参确实涉及该类时才成为候选。在大型代码库中，这对编译时间和诊断信息的长度都有可观的影响。
2. **防止意外的隐式转换**：`sink(a)` 的例子说明，只有实参本身的类型关联到该类时才会找到它，不会仅仅因为某个类型能隐式转换成该类就被选中，这消除了许多出人意料的重载匹配。
3. **对称性**：作为非成员，左右操作数都可以发生隐式转换（只要至少一个操作数关联到该类），而成员运算符的左操作数不能转换。
4. **能访问私有成员**，无需额外的 getter。

### 类模板中定义的友元函数

对于在类模板中定义的友元函数，每个特化都会定义一个不同的非模板函数（[[temp.friend]]）。如果它的签名不依赖模板参数，两个特化就会把同一个函数定义两次：

```cpp title="friend-in-template.cpp" error
template<class T> struct Y {
    friend void ff() {}          // 每个特化都定义 ::ff()
};
Y<int>  yi;
Y<char> yc;                      // error: ::ff() 被重定义
```

正确的写法是让签名依赖 `T`，例如 `friend Op operator+(Op, Op)`，这样每个特化各自定义一个不同的 `operator+`。

!!! pitfall "非模板友元与模板函数"
    ```cpp
    template<class T> class Box {
        friend void show(const Box&);              // 声明了一个**非模板**函数 show(const Box<T>&)
    };
    template<class T> void show(const Box<T>&) {}  // 这是另一个函数模板，与上面的友元无关！
    int main() { Box<int> b; show(b); }            // 重载决议偏好非模板 ⇒ 调用未定义的 show(const Box<int>&)
    ```
    本机 Clang 编译通过，但链接失败（找不到 `show(Box<int> const&)`），而且默认不给警告。要把函数模板的特化设为友元，需要先声明模板，再写 `friend void show<>(const Box&);`，或者直接在类内定义（隐藏友元）。

## 友元的访问前提与位置（¶8）

¶8 包含两句话：

1. 友元声明所指定的成员，必须在包含该友元声明的类中可访问。不能借友元声明访问别的类的私有成员函数。
2. 无论友元声明出现在类的 private、protected 还是 public 部分，含义都相同。

```cpp title="friend-member-access.cpp" error
class X {
    void priv();
public:
    void pub();
};
class Y {
    friend void X::pub();     // OK
    friend void X::priv();    // error: X::priv 在 Y 中不可访问
};
```

## 不继承、不传递（¶9）

¶9：友元关系**既不继承，也不传递**。

```cpp title="friend-not-inherited.cpp" error
class A {
    friend class B;
    int a;
};
class B {
    friend class C;
};
class C {
    void f(A* p) { p->a++; }     // error: C 是 A 的友元的友元，但不是 A 的友元
};
class D : public B {
    void f(A* p) { p->a++; }     // error: D 派生自 A 的友元，但不是 A 的友元
};
```

两个方向都不继承：

- 友元的派生类不是友元（上例中的 `D`）；
- 授权类的派生类也不会把基类的友元当作自己的友元：`B` 是 `A` 的友元，并不意味着 `B` 能访问 `class A2 : A` 新增的私有成员。不过 `B` 仍然可以经由 `A2` 对象访问继承自 `A` 的成员，因为这时的访问依据是 [[class.access.base]] 中关于指名类的递归规则（¶5.7）。

为什么这样设计？友元是授权类单方面、点对点的信任声明。如果友元关系可以继承，任何人都能通过从友元派生来获得访问权，封装就形同虚设；如果可以传递，信任的边界就不再由授权类控制。

## 友元声明不绑定名字（¶10）

¶10（注 4）：友元声明**从不绑定名字**（[[dcl.meaning]]、[[dcl.type.elab]]）。它指向（target）外围作用域中的一个实体，但不把名字引入任何作用域供普通查找使用。具体规则如下：

- 非限定名的友元函数声明，目标是最内层的外围命名空间（不考虑更外层的作用域）；
- 非限定名的友元类声明（`friend class Z;`）如果找不到已有的类，就在最内层的外围命名空间（对局部类而言是最内层的块作用域）中声明它；
- 在该命名空间中出现普通声明之前，普通查找找不到这个名字。

例 8 展示了这些规则：

```cpp title="friend-binding.cpp" error
void h(int);
template <class T> void f2(T);
namespace A {
    class X {
        friend void f(X);        // A::f(X) 是友元
        class Y {
            friend void g();     // A::g 是友元
            friend void h(int);  // A::h 是友元——不考虑 ::h
            friend void f2<>(int);   // ::f2<>(int) 是友元（模板特化：查找已有模板）
        };
    };
    // 此处 A::f、A::g、A::h 不可见
    X x;
    void g() { f(x); }           // A::g 的定义；f(x) 经 ADL 找到 A::f
    void f(X) { }                // A::f 的定义
    void h(int) { }              // A::h 的定义
    // 此处 A::f、A::g、A::h 可见，并且已知是友元
}

using A::x;

void h() {
    A::f(x);                     // OK: A::f 已在 A 中声明
    A::X::f(x);                  // error: f 不是 A::X 的成员
    A::X::Y::g();                // error: g 不是 A::X::Y 的成员
}
```

注意，`friend void h(int);` 声明的是 `A::h`，而不是全局的 `::h`，即使 `::h` 早已声明且签名完全一致。这是一个常见的陷阱：想把全局函数设为友元，必须写 `friend void ::h(int);`。

例 9 展示局部类中的友元：

```cpp title="friend-in-local-class.cpp" error
class X;
void a();
void f() {
    class Y;
    extern void b();
    class A {
        friend class X;   // OK: 但 X 是一个（新的）局部类，不是 ::X
        friend class Y;   // OK: 块作用域中的 Y
        friend class Z;   // OK: 在块作用域中引入局部类 Z
        friend void a();  // error: 不考虑 ::a
        friend void b();  // OK: 块作用域中的 extern 声明
        friend void c();  // error: 局部类中的友元函数必须已在块作用域中声明
    };
    X* px;                // OK: 但找到的是 ::X（友元声明没有绑定名字）
    Z* pz;                // error: 找不到 Z
}
```

局部类的友元函数声明只考虑最内层的块作用域，在那里找不到就是错误（不会去命名空间作用域中找，也不会像非局部类那样在命名空间中引入新函数）。

## 实现视角

!!! impl
    - 友元关系纯粹是编译期的访问控制，对 ABI 没有影响（MSVC 的修饰名会编码成员的访问权，但友元函数是非成员，不涉及）。
    - 隐藏友元只能经 ADL 找到，编译器通常这样实现：把函数声明放入命名空间的符号表，但带上不可见标记，普通查找跳过它，ADL 则在关联类的友元列表中查找。在 Clang 中，这对应声明的 IDNS（标识符命名空间）标志位。
    - 编译时间：库实现（如 libc++ 的迭代器、`std::chrono`）大量改用隐藏友元来缩小候选集，这是一项常被提及的编译性能优化。

## 历史与演进

!!! history
    - **C++98**：友元函数与友元类。在 ARM 时代，类中定义的友元函数的名字会注入外围作用域（friend name injection）；C++98 标准化时改为不可见、只能经 ADL 找到，隐藏友元的语义由此而来。
    - **C++11**：`friend T;` 形式（不带 *class-key*，可用于模板参数与 typedef 名），非类类型时被忽略。
    - **C++20**：引入模块后，具名模块中在类内定义的友元函数不再隐式 inline（即 ¶6 中附属于全局模块的限定）。
    - **C++26** {{c++26}}：[[P2893R3]] 可变参数友元：`friend Ts...;` 与一个声明中列出多个友元类型。

## 陷阱

!!! pitfall
    1. **`friend void h(int);` 不指向全局的 `::h`**：它声明（并授权）的是最内层命名空间中的 `h`。应写 `friend void ::h(int);`。
    2. **隐藏友元找不到**：没有关联到该类的实参时，隐藏友元无法调用。不要把无参数或参数与该类无关的函数定义成隐藏友元。
    3. **非模板友元与函数模板混淆**：类模板中的 `friend void f(Box&);` 声明的是非模板函数，需要为每个特化单独定义；想授权函数模板的特化，要写 `f<>`。
    4. **类内友元定义的签名不依赖模板参数**：多个特化会导致重定义。
    5. **以为派生类继承了友元**：并没有。基类的友元也不能访问派生类新增的私有成员。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct S {
        friend void f(S) {}
        friend void g(int) {}
    };
    void t() { f(S{}); g(1); }
    ```
    `t` 中哪个调用合法？如何让另一个也能被调用？

<details markdown="1">
<summary>答案</summary>

`f(S{})` 合法：ADL 在关联类 `S` 中找到隐藏友元 `f`。`g(1)` ill-formed：实参类型 `int` 没有关联类，ADL 不会查看 `S`，而普通查找找不到 `g`（友元声明不绑定名字）。要调用 `g`，可以在全局命名空间中再声明一次 `void g(int);`。这个普通声明与友元声明相对应（[[basic.scope.scope]]），使普通查找能找到这个名字，它指向的仍是在类中定义的那个函数。
</details>

!!! question "思考题 2"
    `class A { int x; friend class B; }; class B { public: struct N { int get(A& a) { return a.x; } }; };` 中 `B::N::get` 能访问 `A::x` 吗？如果把 `N` 改成 `B` 的友元类（而不是嵌套类）呢？

<details markdown="1">
<summary>答案</summary>

嵌套类可以。¶2 说，在友元类的成员声明中可以指名 `A` 的私有成员；嵌套类 `N` 是 `B` 的成员，`N` 的成员函数定义也属于 `B` 的成员声明范围（对嵌套类而言访问权可传递，见 [class.access.general]/2 及脚注）。如果 `N` 只是 `B` 的友元（`class N; class B { friend class N; };`），就不行：友元关系不传递（¶9），`N` 只是友元的友元。
</details>

## 小结

!!! summary
    | 规则 | 要点 |
    |---|---|
    | 本质 | 授权指名 private/protected 成员；不是成员，没有 `this` |
    | 友元类 | 其基类说明符、成员声明（含嵌套类）都获得授权 |
    | 友元类型 | 指代类类型才生效，否则忽略；C++26 支持包展开 |
    | 类内定义 | 仅非局部类、非限定名；全局模块中隐式 inline |
    | 隐藏友元 | 不绑定名字，只能经 ADL 找到；减少候选、防止意外转换 |
    | 前提 | 友元声明指定的成员须在声明类中可访问；所在访问区段无关 |
    | 不继承、不传递 | 友元的派生类、友元的友元都不是友元 |
    | 目标作用域 | 非限定友元函数指向最内层外围命名空间；局部类中只看最内层块作用域 |
