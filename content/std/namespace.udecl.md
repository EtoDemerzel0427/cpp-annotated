---
title: using 声明
summary: using 声明把一次限定查找的结果绑定到当前作用域的一个名字上，用来引入命名空间成员、把基类成员带进派生类并修改访问级别、继承构造函数。
status: done
papers: P0136R1, P0195R2, P1099R5, P2169R4
related: basic.namespace, basic.lookup, basic.lookup.qual, class.member.lookup, class.inhctor.init, over.match.funcs, basic.scope.scope, class.access, enum, temp.res
tags: 声明, 名字查找, 继承, 构造函数, 访问控制
updated: 2026-10-19
---

!!! tldr
    - `using N::f;` 让当前作用域里的 `f` 指代此刻在 `N` 中查找 `f` 得到的那组声明。之后再加入 `N` 的重载看不到。
    - 在类里，using 声明只能命名基类成员或枚举量。它把基类的整个重载集并入派生类，而派生类自己声明的同签名函数会隐藏或覆盖其中对应的那个。
    - using 声明所在的访问区段决定新名字的访问级别，这就是 `public: using Base::g;` 能把 protected 成员公开的原因。被命名的每个声明都必须可访问。
    - `using Base::Base;` 继承构造函数：基类的构造函数参与派生类的构造，派生类自己的其他成员按默认方式初始化。
    - 类成员（枚举量除外）不能在类外用 using 声明引入，静态成员也不行。

## 它做了什么

```cpp run title="udecl-snapshot.cpp" ok
#include <cstdio>

namespace A {
    void f(int) { std::puts("f(int)"); }
}

using A::f;              // f 是 A::f(int) 的同义词

namespace A {
    void f(char) { std::puts("f(char)"); }
}

void foo() {
    f('a');              // f(int)：using 声明时 f(char) 还不存在
}
void bar() {
    using A::f;          // 此时 A::f(int) 和 A::f(char) 都已声明
    f('a');              // f(char)
}
int main() { foo(); bar(); }
```

**[[g:using-declaration|using 声明]]**（using-declaration）`using A::f;` 在当前作用域里引入名字 `f`。以后查找 `f` 找到这条 using 声明时，它就换成它所命名的那组声明（第 2 段注 1）。

¶9 那组声明在 using 声明出现时就确定了。`foo` 里的 `f` 只能找到 `A::f(int)`，尽管调用时 `A::f(char)` 已经存在。默认实参、默认模板实参和模板特化是例外，之后添加的也会被考虑，因为它们不是新的声明，而是附在已有实体上的。

这正是它与 using 指令 `using namespace A;` 的区别：using 指令不引入名字，只改变查找路径，所以总能看到后来的声明（[[namespace.udir]]）。两者的对比表见 [[basic.namespace]]。

using 声明主要有三种用途：

1. 引入命名空间成员，例如 `using std::swap;`；
2. 把基类成员带进派生类，以解除名字隐藏或修改访问级别；
3. 继承构造函数，`using Base::Base;`。

此外它也能引入枚举量，`using enum`（[[enum]]）就建立在这个机制上。

## 语法与命名的声明（¶1）

```text
using-declaration:      using using-declarator-list ;
using-declarator-list:  using-declarator ...(opt)
                      | using-declarator-list , using-declarator ...(opt)
using-declarator:       typename(opt) nested-name-specifier unqualified-id
```

*nested-name-specifier* 不是可选的，using 声明一定带限定，引入全局名字时写 `using ::x;`。C++17 起一条 using 声明可以有多个声明符，`using A::x, B::y;` 等价于逐个写（脚注 77），声明符后面还可以跟 `...` 做包展开（[[P0195R2]]）。

¶1 每个声明符命名的，就是对它做限定名查找（[[basic.lookup.qual]]）得到的那组声明，只有三处调整：

- 同一作用域里，变量或函数会隐藏同名的类或枚举，普通查找会丢掉被隐藏的那个类。using 声明不丢，它只在检查歧义时忽略它，所以被隐藏的类名会一起带过来（见下文冲突一节的 `struct g`）。
- 返回类型待决的转换函数模板被忽略。
- 派生类里对应的函数会隐藏基类函数，见第 11 段。

在模板里引入待决的类型名，要在声明符前写 `typename`（[[temp.res]]）：

```cpp title="udecl-typename.cpp" ok
template<class T>
struct Derived : T {
    using typename T::value_type;   // 待决的类型名
    using T::get;                   // 待决的非类型成员
    value_type v{};
};

struct Base { using value_type = int; int get() const { return 1; } };

int main() { Derived<Base> d; return d.get() - 1 + d.v; }
```

## 同一作用域里的冲突（¶10）

¶10 有两条规则，都以[[basic.scope.scope|潜在冲突]]为基础。直观地说，两个声明在同一作用域里引入同一个名字，又不是同一个实体的重复声明，也不是可以共存的重载，它们就潜在冲突。

第一条：using 声明命名的某个声明，与它所在作用域里的另一个声明 B 潜在冲突，并且其中一个对另一个可达，程序就非良构。唯一的例外是 C++26 的名字无关声明 `_`（[[P2169R4]]）：B 是名字无关声明，而且 using 声明写在 B 之前。

```cpp title="udecl-name-independent.cpp" error
int _;
void f() {
    int _;          // B：名字无关声明
    _ = 0;
    using ::_;      // error: using 声明不在 B 之前
}
void g() {
    using ::_;      // OK：先于 B
    int _;          // OK：名字无关声明可以与它共存
}
```

第二条：同一作用域里两条 using 声明所命名的声明潜在冲突、互相可达，而且不全是函数或函数模板，程序就非良构。如果都是函数，using 声明本身没有问题，只是重载决议可能区分不了它们（注 5）。

标准例 8 把这些情况都放在了一起：

```cpp title="udecl-conflicts.cpp" error
namespace A {
    int x;
    int f(int);
    int g;
    void h();
}
namespace B {
    int i;
    struct g { };
    struct x { };
    void f(int);
    void f(double);
    void g(char);                     // OK：隐藏 struct g
}

void func() {
    int i;
    using B::i;                       // error: 与局部变量 i 冲突
    void f(char);
    using B::f;                       // OK：都是函数
    using A::f;                       // OK，但与 B::f(int) 签名相同
    f(1);                             // error: 歧义
    static_cast<int(*)(int)>(f)(1);   // OK：调用 A::f
    f(3.5);                           // OK：B::f(double)
    using B::g;
    g('a');                           // OK：B::g(char)
    struct g g1;                      // OK：g1 的类型是 B::g
    using A::g;                       // error: 与 B::g 冲突
    void h();
    using A::h;                       // error: 与局部声明的 h 冲突
    using B::x;
    using A::x;                       // OK：变量 A::x 隐藏 struct B::x
    using A::x;                       // OK：重复命名同一个声明
    x = 99;                           // 给 A::x 赋值
    struct x x1;                      // x1 的类型是 B::x
}
```

- `using B::g;` 同时带来了函数 `B::g(char)` 和被它隐藏的类 `B::g`。之后 `g('a')` 找到函数，`struct g` 找到类。
- `void h();` 声明的是全局的 `::h`，`using A::h;` 命名的是 `A::h`。两者签名相同，却是不同的实体，所以冲突。
- 块作用域和命名空间作用域里可以重复写同一条 using 声明，比如这里的两次 `using A::x;`。类作用域里不行，见下文第 8 段。

## 在类里使用

### 只能命名基类成员或枚举量（¶3）

```cpp title="udecl-member.cpp" error
enum class button { up, down };

struct B {
    void f(char);
    enum E { e };
    union { int x; };
};
struct C { int f(); };

struct S {
    using button::up;         // OK（C++20）：枚举量不需要来自基类
    button b = up;
};

struct D : B {
    using B::f;               // OK：B 是 D 的基类
    using B::e;               // OK：基类 B 的枚举量
    using B::x;               // OK：基类 B 的匿名联合成员
    using C::f;               // error: C 不是 D 的基类
    void f(int) { f('c'); }   // 调用 B::f(char)
    void g(int) { g('c'); }   // 递归调用 D::g(int)
};

template<typename... bases>
struct X : bases... {
    using bases::f...;        // C++17：包展开
};
X<B, C> xx;                   // OK：命名 B::f 和 C::f
```

¶3 作为类成员的 using 声明，每个声明符要么命名枚举量，要么它的 *nested-name-specifier* 命名当前类的一个基类。命名构造函数时必须是直接基类。在类模板里，类必须派生自所指定的基类，或者至少有一个待决基类，这时检查推迟到实例化。

`D::f(int)` 里的 `f('c')` 调用的是 `B::f(char)`。没有 `using B::f;` 的话，`D::f` 会隐藏基类所有名为 `f` 的函数（[[class.member.lookup]]），`f('c')` 只能把 `'c'` 转换成 `int` 去调用 `D::f(int)`。`g` 就是这种情况。

### 类成员只能在类里引入（¶7）

¶7 命名类成员（枚举量除外）的 using 声明必须是成员声明。在块作用域或命名空间作用域里写 `using X::s;`，即使 `s` 是静态成员，也是非良构的：

```cpp title="udecl-class-member-outside.cpp" error
struct X {
    int i;
    static int s;
    enum { e };
};

void f() {
    using X::i;    // error: 类成员，而这里不是成员声明
    using X::s;    // error: 静态成员也不行
    using X::e;    // OK：枚举量例外
}
```

需要短名字时，可以改用引用，例如 `auto& s = X::s;`。

### 其他限制（¶4–¶6、¶8）

¶5 using 声明不能命名 *template-id*。它引入的是名字，引入模板时它的所有特化都随之而来：

```cpp title="udecl-template-id.cpp" error
struct A {
    template<class T> void f(T);
    template<class T> struct X { };
};
struct B : A {
    using A::f<double>;   // error
    using A::X<int>;      // error
    using A::f;           // OK：引入整个函数模板
};
```

¶6 using 声明不能命名命名空间，那是命名空间别名和 using 指令的事（[[basic.namespace]]）。第 4 段注 2 指出，析构函数没有名字，所以 using 声明也无法引用基类的析构函数。

¶8 同一个声明被同一个类作用域里的两个声明符命名，程序非良构：

```cpp title="udecl-duplicate.cpp" error
struct C { int i; };
struct D1 : C { };
struct D2 : C { };

struct D3 : D1, D2 {
    using D1::i;     // OK：等价于 using C::i
    using D1::i;     // error: 重复
    using D2::i;     // error: 重复，它命名的也是 C::i
};
```

!!! impl "Clang 的偏差"
    本机 Clang 23 只诊断第二行 `using D1::i;`，接受了第三行 `using D2::i;`。按第 8 段，`D2::i` 找到的同样是 `C::i` 这个声明，应当非良构。

¶4 注 3：命名基类成员函数的 using 声明不会阻止派生类隐式声明特殊成员函数，即使签名相同。写了 `using Base::operator=;` 之后，派生类仍然有自己的复制赋值运算符：

```cpp run title="udecl-special-members.cpp" ok
#include <cstdio>

struct Base {
    Base& operator=(const Base&) { std::puts("Base::operator=(const Base&)"); return *this; }
    Base& operator=(int) { std::puts("Base::operator=(int)"); return *this; }
};
struct Derived : Base {
    using Base::operator=;    // 两个 Base::operator= 都被引入
};

int main() {
    Derived d1, d2;
    d1 = 5;                   // Base::operator=(int)
    d1 = d2;                  // Derived 隐式的复制赋值，它再调用 Base::operator=
}
```

`d1 = d2` 的候选里有 `Derived::operator=(const Derived&)` 和引入的 `Base::operator=(const Base&)`。前者是精确匹配，后者要做派生类到基类的转换，所以选前者。程序两次输出的分别来自 `operator=(int)` 和隐式复制赋值内部对基类的调用。

## 派生类的声明优先（¶11、¶12）

```cpp run title="udecl-hide-override.cpp" ok
#include <cstdio>

struct B {
    virtual void f(int)  { std::puts("B::f(int)"); }
    virtual void f(char) { std::puts("B::f(char)"); }
    void g(int)  { std::puts("B::g(int)"); }
    void h(int)  { std::puts("B::h(int)"); }
    void i()     { std::puts("B::i()"); }
    void j()     { std::puts("B::j()"); }
};

struct D : B {
    using B::f;
    void f(int) override { std::puts("D::f(int)"); }   // 覆盖 B::f(int)
    using B::g;
    void g(char) { std::puts("D::g(char)"); }          // 新的重载
    using B::h;
    void h(int) { std::puts("D::h(int)"); }            // 隐藏 B::h(int)
    using B::i;
    void i(this B&) { std::puts("D::i(this B&)"); }    // 不对应 B::i
    using B::j;
    void j(this D&) { std::puts("D::j(this D&)"); }    // 对应 B::j，隐藏它
};

int main() {
    D d; D* p = &d;
    p->f(1);     // D::f(int)
    p->f('a');   // B::f(char)
    p->g(1);     // B::g(int)
    p->g('a');   // D::g(char)
    p->i();      // 标准：B::i()；Clang 23 实际调用 D::i
    p->j();      // D::j(this D&)
}
```

¶11 派生类 C 里的 using 声明所命名的集合，不包括这样的基类成员函数：把它当作 C 的成员看时，它与 C 自己声明的某个函数**对应**（correspond，[[basic.scope.scope]]），即同名、同参数类型列表、同样的 cv 和引用限定。所以派生类的同签名函数会隐藏基类的版本（是虚函数时就是覆盖），两者不冲突。

¶12 注 6：构建重载候选集时，using 声明引入的函数被当作派生类的直接成员，它的隐式对象参数被视为派生类的引用，而不是基类的引用（[[over.match.funcs]]）。函数的类型不变，在其他方面它仍是基类的成员，例如 `&D::g` 的类型是 `void (B::*)(int)`。

如果隐式对象参数仍然是 `B&`，派生类自己的成员在对象参数上总是更好的匹配，引入的函数就永远处于劣势，并入同一个重载集也就没有意义了。

`i` 和 `j` 两行展示了这两段与 C++23 显式对象参数（[[dcl.fct]]）的交互。`B::j` 当作 D 的成员时，对象参数是 `D&`，与 `j(this D&)` 对应，所以被隐藏。`B::i` 与 `i(this B&)` 不对应，两者都是候选。按第 12 段，`B::i` 的对象参数视为 `D&`，对 `D` 左值是恒等转换；`D::i` 要做派生类到基类的转换，所以标准例 9 说调用的是 `B::i`。

!!! impl "Clang 与标准例子不一致"
    本机 Clang 23 运行上面的程序时，`p->i()` 打印的是 `D::i(this B&)`，与标准例 9 不符。

## 访问控制（¶14、¶16）

```cpp title="udecl-access.cpp" error
class A {
private:
    void f(char);
public:
    void f(int);
protected:
    void g();
};

class B : public A {
    using A::f;       // error: A::f(char) 不可访问
public:
    using A::g;       // OK：B::g 是 A::g 的 public 同义词
};
```

¶14 不命名构造函数时，声明符命名的每个声明都必须可访问。`using A::f;` 命名的是整个重载集 `{f(char), f(int)}`，其中 `f(char)` 是 private 的，而 using 声明没法只挑其中一个。

¶16 using 声明和其他成员声明一样，具有它所在区段的访问级别。这是用它修改访问级别的依据：把 protected 成员公开（上面的 `g`），或者在私有继承时有选择地公开一部分接口：

```cpp run title="udecl-private-inherit.cpp" ok
#include <vector>

class Stack : private std::vector<int> {
public:
    using vector::push_back;     // 只公开需要的接口
    using vector::back;
    using vector::pop_back;
    using vector::empty;
    using vector::size;
};

int main() {
    Stack s;
    s.push_back(1);
    s.push_back(2);
    s.pop_back();
    return s.back() == 1 ? 0 : 1;
    // s.begin();   // error: begin 仍是私有继承来的
}
```

## 不能消解继承歧义（¶15）

¶15 注 8：声明符指代的是基类的成员，而不是某个基类子对象的成员，所以 using 声明不能用来消解重复继承造成的歧义：

```cpp title="udecl-ambiguous-base.cpp" error
struct A { int x(); };
struct B : A { };
struct C : A {
    using A::x;
    int x(int);
};

struct D : B, C {
    using C::x;
    int x(double);
};

int f(D* d) {
    return d->x();   // error: 重载决议选中 A::x，但 A 是 D 的有歧义的基类
}
```

`using C::x;` 把 `A::x()` 和 `C::x(int)` 带进 D，重载决议选中 `A::x()`。调用它要把 `D*` 转换成 `A*`，而 D 里有两个 A 子对象，一个经由 B，一个经由 C，转换有歧义（[[conv.ptr]]）。using 声明里没有经由 C 的那个 A 这种说法。

## 继承构造函数（¶2、¶13、¶1）

```cpp run title="inherit-ctor.cpp" ok
#include <string>
#include <cstdio>

struct Base {
    Base(int n) : s(std::to_string(n)) {}
    Base(const char* p) : s(p) {}
    std::string s;
};

struct Derived : Base {
    using Base::Base;      // 继承 Base(int) 和 Base(const char*)
    int extra = 42;        // 由默认成员初始化器初始化
};

int main() {
    Derived a(7), b("hi");
    std::printf("%s %s %d\n", a.s.c_str(), b.s.c_str(), a.extra);   // 7 hi 42
}
```

¶2 声明符命名构造函数时，这条 using 声明表示当前类**继承**（inherit）基类的那组构造函数。第 13 段规定，查找派生类的构造函数（[[class.qual]]）或构建构造用的候选集（[[over.match.ctor]] 等）时，这些构造函数被当作派生类的构造函数。

选中一个继承来的构造函数后，来源基类用它初始化，其他基类和成员都按默认方式隐式初始化（[[class.inhctor.init]]）。其他子对象无法默认初始化时，这个构造函数就是被删除的：

```cpp title="inherit-ctor-deleted.cpp" error
struct P { P(int) {} };
struct Q { Q(const char*) {} };

template<class... Bs>
struct M : Bs... {
    using Bs::Bs...;       // C++17：继承所有基类的构造函数
};

M<P, Q> m(1);              // error: 选中 P(int)，但 Q 无法默认初始化，构造函数被删除
```

派生类自己声明了同签名的构造函数时，它按第 11 段隐藏继承来的版本。两个基类提供同签名的构造函数时，直接使用会有歧义：

```cpp title="udecl-ctor-ambiguity.cpp" error
struct B1 { B1(int); };
struct B2 { B2(int); };

struct D1 : B1, B2 {
    using B1::B1;
    using B2::B2;
};
D1 d1(0);           // error: 歧义，B1(int) 还是 B2(int)

struct D2 : B1, B2 {
    using B1::B1;
    using B2::B2;
    D2(int);        // OK：隐藏 B1(int) 和 B2(int)
};
D2 d2(0);           // OK：调用 D2::D2(int)
```

访问控制对构造函数另有规定。第 14 段规定，命名构造函数时不做访问检查，否则基类只要有一个 private 构造函数，整组就都无法继承。第 16 段规定，继承来的构造函数的可访问性，与用它构造基类对象时相同，using 声明所在的区段被忽略：

```cpp title="inherit-ctor-access.cpp" error
class Base3 { protected: Base3(int) {} };
struct Der3 : Base3 {
    using Base3::Base3;   // 写在 public 区段也不会公开它
};
Der3 d3(1);               // error: 在这里用 Base3(int) 构造基类不可访问
```

¶1 后半段处理模板里的情形。声明符的终止名（最后一个组成名字）待决时，编译器在模板定义时无法知道它是否命名构造函数。规则是：当且仅当 *nested-name-specifier* 的终止名与 *unqualified-id* 相同，也就是 `using T::T;`、`using Base<U>::Base;` 这种形式，才视为命名构造函数。实例化后发现判断错了，程序非良构：

```cpp title="udecl-dependent-ctor.cpp" error
struct Base { Base(int) {} Base() {} };

template<class T> struct X : T { using T::T; };      // 视为命名构造函数
X<Base> x(1);                                         // OK

template<class T> struct W : T { using T::Base; };   // T 与 Base 不同：不视为构造函数
W<Base> w;    // error: 实例化后 Base::Base 命名的是构造函数
```

本机 Clang 23 同样拒绝 `W<Base>`，只是诊断的角度不同：它报告待决的 using 声明解析成了类型（`Base` 的注入类名）却没有写 `typename`。

## 历史与演进

!!! history
    - C++98 已有 using 声明，包括在类里引入基类成员和修改访问级别。
    - C++11 加入继承构造函数。最初的语义是在派生类里隐式声明一组对应的构造函数，在默认实参、可变参数构造函数等方面有不少问题。
    - C++17 重新定义了继承构造函数（[[P0136R1]]）：不再生成派生类的构造函数声明，而是让基类的构造函数在查找和重载决议中当作派生类的构造函数。同年加入了多个声明符和包展开（[[P0195R2]]）。
    - C++20 允许 using 声明命名不属于基类的枚举量，并加入 `using enum`（[[P1099R5]]）。
    - C++26 加入名字无关声明 `_`（[[P2169R4]]），第 10 段的例外即源于此。

## 常见误解

!!! pitfall "using 声明会随着重载的增加自动更新"
    不会。`using A::f;` 之后加入 `A` 的 `f` 对它不可见（第 9 段）。如果头文件里先写了 using 声明，再包含另一个扩展 `A::f` 的头文件，能不能调用到新重载就取决于包含顺序。

!!! pitfall "可以只公开基类的某一个重载"
    做不到。using 声明总是引入整个重载集，而且其中每个都必须可访问（第 14 段）。只想公开一个，就写一个转发函数。

!!! pitfall "继承构造函数会初始化派生类自己的成员"
    除来源基类外，其他子对象都按默认方式初始化（[[class.inhctor.init]]）。派生类新增的 `int` 成员如果没有默认成员初始化器，读到的是不确定值，C++26 起是错误值。

## 思考题

!!! question "思考题 1"
    下面哪些行是良构的？`f(1.5)` 调用的是哪个函数？

    ```cpp
    namespace N { void f(int); }
    using N::f;
    namespace N { void f(double); }
    void g() { f(1.5); }

    struct S { static int s; };
    using S::s;
    ```

<details markdown="1">
<summary>答案</summary>

- `f(1.5)` 良构，但调用的是 `N::f(int)`，`1.5` 被转换成 `int`。using 声明只命名了它出现时已有的 `f(int)`（第 9 段）。
- `using S::s;` 非良构。命名类成员（枚举量除外）的 using 声明必须是成员声明（第 7 段），静态成员也不例外。
</details>

!!! question "思考题 2"
    `struct B { void f(); }; struct D : B { using B::f; void f(); };` 中，D 的 `f` 与 `B::f` 是什么关系？把 D 里的声明改成 `void f() const;` 呢？

<details markdown="1">
<summary>答案</summary>

第一种：`B::f` 当作 D 的成员时与 `D::f()` 对应，按第 11 段它不在 using 声明命名的集合里，也就是被 `D::f` 隐藏了。两者既不冲突，也不是同一个函数的重复声明。

第二种：`f() const` 与 `B::f()` 的 cv 限定不同，不对应，两者都在重载集里。对非 const 的 `D` 对象调用 `f()` 选中 `B::f`，因为它的对象参数视为 `D&`（第 12 段），比 `const D&` 更好；对 const 对象调用则选中 `D::f() const`。
</details>
