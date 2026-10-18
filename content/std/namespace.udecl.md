---
title: using 声明
summary: using 声明把查找到的一组声明绑定到一个名字上：引入命名空间成员、把基类成员带入派生类（并可修改访问）、继承构造函数、引入枚举量；只包含声明时可见的重载；冲突、重复、隐藏与覆盖规则；C++17 的包展开
status: done
papers: P0136R1, P0195R2, P1099R5, P2169R4
related: basic.lookup, basic.lookup.qual, class.member.lookup, class.inhctor.init, over.match.funcs, basic.scope.scope, class.access, basic.namespace, enum, temp.res
tags: 声明, 名字查找, 继承, 构造函数, 访问控制
updated: 2026-10-17
---

[[g:using-declaration|using 声明]]（using-declaration）`using N::name;` 做一件精确的事：**在当前作用域中让名字 `name` 指代"在 `N` 中查找 `name` 得到的那组声明"**。它与 using **指令**（`using namespace N;`，[[namespace.udir]]）的区别是根本性的：

| | using 声明 `using N::f;` | using 指令 `using namespace N;` |
|---|---|---|
| 是否引入名字 | **是**：`f` 被绑定到当前作用域 | 否：只改变查找路径 |
| 看到之后添加的重载？ | **否**（¶9） | 是 |
| 能出现在类中？ | 是（命名基类成员或枚举量） | 否 |
| 与本作用域同名声明 | 可能冲突（¶10） | 不冲突，只可能在使用时歧义 |

using 声明的用途有四种，本节的规则基本可以按用途分组：

1. **引入命名空间成员**：`using std::swap;`
2. **把基类成员带进派生类**：解除名字隐藏、修改访问级别（¶3、¶11、¶16）；
3. **继承构造函数**：`using Base::Base;`（¶2、¶13，细节在 [[class.inhctor.init]]）；
4. **引入枚举量**：`using Color::red;`，以及 `using enum`（[[enum]]）的底层机制。

## 语法与"命名的声明集合"（¶1）

```text
using-declaration:      using using-declarator-list ;
using-declarator-list:  using-declarator ...(opt)
                      | using-declarator-list , using-declarator ...(opt)
using-declarator:       typename(opt) nested-name-specifier unqualified-id
```

注意 *nested-name-specifier* **不是**可选的——using 声明必须带限定（`using ::x;` 也可以）。脚注 77：一个带多个 *using-declarator* 的 using 声明（C++17）等价于一串各带一个的 using 声明。

¶1：*using-declarator* 的**组成名字**是其 *nested-name-specifier* 和 *unqualified-id* 的组成名字。每个 *using-declarator* **命名**通过限定名查找（[[basic.lookup.qual]]）找到的声明集合，有三个例外：

- 查找时本应被**丢弃**的类和枚举声明（"类名被同名的变量/函数隐藏"规则，[[basic.lookup]]）只是在检查歧义时被**忽略**——换句话说，using 声明同时"带上"被隐藏的类名；
- **返回类型待决的转换函数模板**被忽略；
- 某些函数被**隐藏**（见 ¶11）。

¶1 后半段处理**待决**的情形：*using-declarator* 的终止名是待决的（[[temp.dep.type]]）时，编译器在模板定义时不知道它是否命名构造函数。规则：**当且仅当** *nested-name-specifier* 的终止名与 *unqualified-id* 相同时，视为命名构造函数（即 `using T::T;`、`using Base<U>::Base;` 这种形式）。如果实例化后发现判断错了——被视为非构造函数的结果命名了构造函数，或者反过来——程序非良构。

```cpp title="udecl-dependent-ctor.cpp" error
struct Base { Base(int) {} Base() {} };

template<class T> struct X : T { using T::T; };      // 视为命名构造函数
X<Base> x(1);                                         // OK

template<class T> struct W : T { using T::Base; };   // 终止名 T ≠ Base：不视为构造函数
W<Base> w;    // error: 实例化后 Base::Base 命名的是构造函数（Clang 的诊断说法不同，但同样拒绝）
```

## 继承构造函数（¶2）

¶2：*using-declarator* 命名构造函数时，它声明当前类**继承**（inherits）所指基类的那组构造函数声明。注 1：否则，*unqualified-id* 被**绑定**到 *using-declarator* 上，名字查找遇到它时会被**替换**为它所命名的那些声明（[[basic.lookup]]）。如果命名的是一个枚举，其枚举量的名字**不会**随之被绑定（要那样做请用 `using enum`）。

继承构造函数的语义（C++17 起，[[P0136R1]]）：基类构造函数**不会**在派生类中被"复制"成新的构造函数声明；它们只是在查找派生类构造函数、构建重载候选集时**被视为**派生类的构造函数（¶13）。选中后，派生类中**其他**子对象按默认方式初始化（[[class.inhctor.init]]）。

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
    int extra = 42;        // 用默认成员初始化器初始化
};

int main() {
    Derived a(7), b("hi");
    std::printf("%s %s %d\n", a.s.c_str(), b.s.c_str(), a.extra);   // 7 hi 42
}
```

```cpp title="inherit-ctor-deleted.cpp" error
struct P { P(int) {} };
struct Q { Q(const char*) {} };

template<class... Bs>
struct M : Bs... {
    using Bs::Bs...;       // C++17: 包展开，继承所有基类的构造函数
};

M<P, Q> m(1);              // error: 选中 P(int)，但 Q 子对象无法默认初始化 ⇒ 被删除
```

## 类成员中的 using 声明（¶3–¶8）

### 必须命名基类成员或枚举量（¶3）

¶3：作为 *member-declaration* 的 using 声明，每个 *using-declarator* 要么**命名一个枚举量**，要么其 *nested-name-specifier* 命名**当前类的一个基类**。命名构造函数时，必须是**直接**基类。若所在类是类模板，则它必须派生自指定的基类，或者**至少有一个待决基类**（这时只能等实例化再检查）。

```cpp title="udecl-member.cpp" error
enum class button { up, down };

struct B {
    void f(char);
    enum E { e };
    union { int x; };
};

struct C { int f(); };

struct S {
    using button::up;         // OK (C++20): 命名枚举量，不需要是基类
    button b = up;
};

struct D : B {
    using B::f;               // OK: B 是 D 的基类
    using B::e;               // OK: e 是基类 B 的枚举量
    using B::x;               // OK: x 是基类 B 的匿名联合成员
    using C::f;               // error: C 不是 D 的基类
    void f(int) { f('c'); }   // 调用 B::f(char)
    void g(int) { g('c'); }   // 递归调用 D::g(int)
};

template<typename... bases>
struct X : bases... {
    using bases::f...;        // C++17: 包展开
};
X<B, C> xx;                   // OK: 命名 B::f 和 C::f
```

`D::f(int)` 中的 `f('c')` 调用 `B::f(char)`：没有 `using B::f;` 时，`D::f` 会**隐藏**基类的所有 `f`（[[class.member.lookup]]），`f('c')` 只能调用 `D::f(int)`（`'c'` 转换为 `int`）。`using B::f;` 把基类重载"拉进"同一个重载集。而 `g` 没有对应的 using 声明，`g('c')` 就只能找到 `D::g`。

### 注 2、注 3（¶4）

- 析构函数**没有名字**，所以 using 声明无法引用基类析构函数；
- 命名基类成员函数的 using 声明**不会抑制**派生类中特殊成员函数的隐式声明，即使签名相同。例如 `using Base::operator=;` 之后，派生类仍然有自己隐式声明的复制赋值运算符，它会**隐藏**（¶11）基类同签名的那个。

```cpp run title="udecl-special-members.cpp" ok
#include <cstdio>

struct Base {
    Base& operator=(const Base&) { std::puts("Base::operator="); return *this; }
    Base& operator=(int) { std::puts("Base::operator=(int)"); return *this; }
};
struct Derived : Base {
    using Base::operator=;    // 引入 operator=(int)；operator=(const Base&) 也被引入
};

int main() {
    Derived d1, d2;
    d1 = 5;                   // Base::operator=(int)
    d1 = d2;                  // Derived 的隐式复制赋值（它又调用 Base::operator=）
}
```

### 不能命名 *template-id*、命名空间（¶5–¶6）

¶5：using 声明不能命名 *template-id*——它引入的是**名字**，所以引入模板本身就会带上它的所有特化：

```cpp title="udecl-template-id.cpp" error
struct A {
    template<class T> void f(T);
    template<class T> struct X { };
};
struct B : A {
    using A::f<double>;   // error
    using A::X<int>;      // error
    using A::f;           // OK: 引入整个函数模板
};
```

¶6：using 声明不能命名命名空间（那是命名空间别名或 using 指令的工作）。

### 类成员只能在类中引入（¶7）

¶7：命名**类成员**（枚举量除外）的 using 声明必须是 *member-declaration*。所以在块作用域或命名空间作用域写 `using X::s;`，即使 `s` 是静态成员，也非良构：

```cpp title="udecl-class-member-outside.cpp" error
struct X {
    int i;
    static int s;
    enum { e };
};

void f() {
    using X::i;    // error: 类成员，且这里不是成员声明
    using X::s;    // error: 静态成员也不行
    using X::e;    // OK: 枚举量例外
}
```

为什么静态成员也不行？因为允许它会模糊"类成员"与"命名空间成员"的界限，并引发访问控制上的问题（在类外用一个名字访问私有静态成员？）。需要短名字时，可以用引用或别名代替。

### 同一个类中重复命名（¶8）

¶8：同一个声明被两个位于**同一类作用域**的 *using-declarator* 命名，程序非良构。

```cpp title="udecl-duplicate.cpp" error
struct C { int i; };
struct D1 : C { };
struct D2 : C { };

struct D3 : D1, D2 {
    using D1::i;     // OK: 等价于 using C::i
    using D1::i;     // error: 重复
    using D2::i;     // error: 重复——它也命名 C::i
};
```

!!! impl "Clang 的偏差"
    Clang 23 能诊断第二行 `using D1::i;`（报告重复声明），但**接受**第三行 `using D2::i;`。按 ¶8，`D2::i` 找到的同样是 `C::i` 这个声明，应当非良构。

在块作用域和命名空间作用域中，同一个 using 声明重复出现是允许的（¶10 例 8 中的 `using A::x;` 写了两次），只有类作用域禁止——与类中不能重复声明成员的规则一致。

## 只命名"此刻可见"的声明（¶9）

¶9（注）：*nested-name-specifier* 命名命名空间时，using 声明**不会**命名在它之后才加入该命名空间的声明。所以之后添加的重载被忽略；但**默认实参**、**默认模板实参**和模板**特化**（部分特化、显式特化）会被考虑——它们不是新的声明，而是对已有实体的补充。

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
    using A::f;          // 此时 A::f(int) 和 A::f(char) 都可见
    f('a');              // f(char)
}

int main() { foo(); bar(); }
```

这条规则让 using 声明的含义**在声明点就固定**，与之后的代码顺序无关，是 using 声明比 using 指令"更可预测"的根源。

## 冲突规则（¶10）

¶10 有两部分。

**第一部分**：using 声明命名的某个声明，与同一目标作用域中的另一个声明 B **潜在冲突**（[[basic.scope.scope]]），且两者有一个对另一个可达，程序非良构——**除非** B 是**名字无关声明**（name-independent，C++26 的 `_`，[[P2169R4]]）**并且** using 声明在 B 之前。

```cpp title="udecl-name-independent.cpp" error
int _;
void f() {
    int _;          // B：名字无关声明
    _ = 0;
    using ::_;      // error: using 声明没有出现在 B 之前
}
void g() {
    using ::_;      // OK: 先于 B
    int _;          // OK: 名字无关声明可以与之共存
}
```

**第二部分**：两个位于同一作用域的 using 声明命名的声明潜在冲突、互相可达，且**不全是**函数或函数模板，程序非良构。注 5：如果都是函数，using 声明本身没问题，但重载决议可能无法区分它们。

标准例 8 是一张冲突规则的速查表：

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
    void g(char);                     // OK: 隐藏 struct g
}

void func() {
    int i;
    using B::i;                       // error: 与局部变量 i 冲突
    void f(char);
    using B::f;                       // OK: 都是函数
    using A::f;                       // OK，但与 B::f(int) 签名相同
    f(1);                             // error: 歧义
    static_cast<int(*)(int)>(f)(1);   // OK: 调用 A::f
    f(3.5);                           // OK: B::f(double)
    using B::g;
    g('a');                           // OK: B::g(char)
    struct g g1;                      // OK: g1 的类型是 B::g（类名被一起带入）
    using A::g;                       // error: 与 B::g 冲突
    void h();
    using A::h;                       // error: 与局部函数声明 h() 冲突（签名相同、不是同一实体）
    using B::x;
    using A::x;                       // OK: 隐藏 struct B::x
    using A::x;                       // OK: 与上一个 using A::x 不冲突
    x = 99;                           // 给 A::x 赋值
    struct x x1;                      // x1 的类型是 B::x
}
```

几个值得细品的点：

- `using B::g;` 同时带上了函数 `B::g(char)` **和**被它隐藏的类 `B::g`（¶1 第一个例外）。之后 `g('a')` 找到函数，`struct g` 找到类。
- `using A::h;` 与局部声明 `void h();` 冲突：两者签名相同但声明不同的实体（一个是 `A::h`，另一个是全局 `::h`），这正是"潜在冲突"——它们对应（correspond）却不是同一实体的重声明。
- `using A::x;` 两次：同一个声明被重复命名，在块作用域中不是冲突。变量 `A::x` 隐藏类 `B::x`，与同一作用域中"变量隐藏同名类"的普通规则一致。

## 隐藏与覆盖：派生类声明优先（¶11）

¶11：类 C 中的 *using-declarator* 所命名的集合**不包括**这样的基类成员函数（模板）：把它们**视为 C 的成员**时，它们与 C 中某个函数（模板）声明**对应**（[[basic.scope.scope]]，即同名、同参数类型列表、同 cv/引用限定等）。换句话说：**派生类自己声明的同签名函数会隐藏（或覆盖）using 声明引入的那个**，而不会冲突。

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
    void j(this D&) { std::puts("D::j(this D&)"); }    // 对应 B::j（视为 D 的成员时），隐藏它
};

int main() {
    D d; D* p = &d;
    p->f(1);     // D::f(int)
    p->f('a');   // B::f(char)
    p->g(1);     // B::g(int)
    p->g('a');   // D::g(char)
    p->i();      // 标准：B::i()——作为 D 的成员，其隐式对象参数是 D&，比 B& 更好（Clang 23 实际调用 D::i）
    p->j();      // D::j(this D&)
}
```

`i` 与 `j` 两行展示了 C++23 显式对象参数（[[dcl.fct]]）与 using 声明的交互：判断"对应"时，基类成员函数被**视为 C 的成员**，它的隐式对象参数类型是 `D&`。`j(this D&)` 的显式对象参数也是 `D&`，两者对应，于是 `B::j` 被隐藏；`i(this B&)` 的对象参数是 `B&`，不对应，两者并存，重载决议中 `B::i`（对象参数视为 `D&`，见 ¶12）是更好的匹配。

!!! impl "Clang 与标准例子不一致"
    截至 Clang 23，运行上面的程序时 `p->i()` 打印的是 `D::i(this B&)`，与标准例 9（明确写着调用 `B::i`）不一致。按 ¶12，`B::i` 的对象参数视为 `D&`，实参 `*p` 是 `D` 左值，恒等转换；而 `D::i` 需要派生类到基类的转换，应当落败。

¶11 的例子后半段讲继承构造函数的冲突：

```cpp title="udecl-ctor-ambiguity.cpp" error
struct B1 { B1(int); };
struct B2 { B2(int); };

struct D1 : B1, B2 {
    using B1::B1;
    using B2::B2;
};
D1 d1(0);           // error: 歧义——B1(int) 与 B2(int)

struct D2 : B1, B2 {
    using B1::B1;
    using B2::B2;
    D2(int);        // OK: 隐藏 B1(int) 和 B2(int)
};
D2 d2(0);           // OK: 调用 D2::D2(int)
```

## 重载决议中的待遇（¶12–¶13）

¶12（注）：为构建重载候选集，派生类中 using 声明命名的函数被**视为派生类的直接成员**——特别是，**隐式对象参数**被视为派生类的引用，而不是基类的引用（[[over.match.funcs]]）。这不影响函数的类型；在其他方面它仍然是基类的成员（例如取地址 `&D::g` 得到的是 `void (B::*)(int)`）。

为什么要这样？如果隐式对象参数仍是 `B&`，那么派生类自己的成员（对象参数 `D&`）在对象参数上永远是更好的匹配，using 声明引入的函数将在重载中处于系统性劣势——这违背"把它们拉进同一重载集平等竞争"的初衷。

¶13：using 声明命名的构造函数在查找派生类构造函数（[[class.qual]]）或构建候选集（[[over.match.ctor]]、[[over.match.copy]]、[[over.match.list]]）时被视为派生类的构造函数。注 7：选中后，除了来源基类之外的所有子对象都被隐式初始化（[[class.inhctor.init]]）；在两者本来会有歧义时，派生类构造函数有时会被优先（[[over.match.best]] 的一条决胜规则）。

## 访问控制（¶14、¶16）

¶14：不命名构造函数的 *using-declarator* 所命名的**每一个**声明都必须**可访问**；命名构造函数时**不做**访问检查。

¶16：using 声明具有 *member-declaration* 通常的可访问性——这就是"用 using 声明**修改访问级别**"的依据。而通过 using 声明被考虑的基类构造函数，其可访问性等同于"用它构造基类对象时"的可访问性；using 声明本身的访问级别**被忽略**。

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
    using A::f;       // error: A::f(char) 不可访问（重载集中的每一个都必须可访问）
public:
    using A::g;       // OK: B::g 是 A::g 的 public 同义词
};

class Base3 { protected: Base3(int); };
struct Der3 : Base3 {
    using Base3::Base3;   // 继承的构造函数保持 protected 的可访问性
};
Der3 d3(1);               // error: 在此处构造 Base3 不可访问
```

`using A::f;` 失败的原因很微妙：它命名的是**整个重载集** `{f(char), f(int)}`，其中 `f(char)` 是 private 的。using 声明无法"只挑一个"引入。

修改访问是 using 声明最常见的用途之一：把 protected 成员提升为 public（如上 `g`），或者在私有继承中有选择地把某些基类成员重新公开：

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
    // s.begin();   // error: begin 仍然是 private 继承来的
}
```

## using 声明不能消解继承歧义（¶15）

¶15（注）：*using-declarator* 指代的是**基类成员**（而不是某个基类**子对象**的成员），所以不能用它来解决因重复继承产生的歧义：

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

`using C::x;` 把 `A::x()` 和 `C::x(int)` 带进 D。名字查找毫无问题，重载决议选中 `A::x()`；但调用它需要把 `D*` 转换为 `A*`，而 D 有两个 A 子对象（经由 B 和经由 C）——转换有歧义（[[class.member.lookup]]、[[conv.ptr]]）。using 声明没有"经由 C 的那个 A"这样的概念。

## `typename` 与待决名

*using-declarator* 前的 `typename` 用于在模板中引入待决的**类型**名（[[temp.res]]）：

```cpp title="udecl-typename.cpp" ok
template<class T>
struct Derived : T {
    using typename T::value_type;   // 引入待决类型名
    using T::get;                   // 引入待决成员（非类型）
    value_type v{};
};

struct Base { using value_type = int; int get() const { return 1; } };

int main() { Derived<Base> d; return d.get() - 1 + d.v; }
```

## 实现视角

!!! impl "编译器如何表示 using 声明"
    - Clang 中 using 声明表示为 `UsingDecl`，它为每个被命名的声明创建一个 `UsingShadowDecl`（"影子声明"）放在当前作用域中；名字查找找到影子声明后再解引用到目标。继承构造函数则用 `ConstructorUsingShadowDecl`，并在被选中时**按需**合成一个隐式的派生类构造函数（"inheriting constructor"）。GCC 的实现思路类似。
    - 继承构造函数在 Itanium ABI 中有专门的修饰：继承的构造函数编码为 `CI1` / `CI2` 加上基类类型，而不是普通的 `C1` / `C2`。
    - ¶9 的"快照"语义在实现上自然得到：`UsingDecl` 在声明时就固定了影子声明的列表；而默认实参、特化是挂在原实体上的，所以会被看到。

## 历史与演进

!!! history "C++98 → C++26"
    - **C++98**：using 声明，包括在类中引入基类成员和修改访问。
    - **C++11**：继承构造函数 `using Base::Base;`（最初的语义是在派生类中**隐式声明**一组对应的构造函数，有许多边缘问题）。
    - **C++17**：重新定义继承构造函数的语义（[[P0136R1]]）：不再生成派生类构造函数声明，而是让基类构造函数在查找时可见、在重载决议中被视为派生类的；修正了默认实参、可变参数构造函数、模板构造函数等问题。using 声明中的包展开与多个声明符（[[P0195R2]]）。
    - **C++20**：using 声明可以命名枚举量（包括在类中命名非基类的枚举量）、`using enum`（[[P1099R5]]）。
    - **C++26**：名字无关声明 `_`（[[P2169R4]]）与 using 声明的交互（¶10 第一部分的例外）。

## 陷阱

!!! pitfall "“using 声明会跟着重载一起更新”"
    不会。`using A::f;` 之后再往 `A` 中添加的 `f` 重载对它不可见（¶9）。头文件中先 `using` 再包含另一个扩展 `A::f` 的头文件，就会得到"有时能调用，有时不能"的效果。

!!! pitfall "想用 using 声明公开基类的某一个重载"
    不行，它总是引入整个重载集；并且集合中每一个都必须可访问（¶14）。只想公开一个，就写转发函数。

!!! pitfall "继承构造函数不会初始化派生类自己的成员"
    除来源基类外的子对象都是**默认初始化**的（[[class.inhctor.init]]）。派生类新增的 `int` 成员如果没有默认成员初始化器，值就是不确定的（C++26 中是错误值）。

!!! pitfall "`using Base::operator=;` 不会替代派生类的复制赋值"
    派生类仍有隐式声明的复制/移动赋值，它们隐藏基类同签名的版本（¶4 注 3、¶11）。

## 思考题

!!! question "思考题 1"
    下面哪些行是良构的？

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

- `f(1.5)`：良构，但调用的是 `N::f(int)`（`1.5` 转换为 `int`）：using 声明只命名了声明时可见的 `f(int)`（¶9）。开 `-Wconversion` 可能会给警告。
- `using S::s;`：非良构。命名类成员（枚举量除外）的 using 声明必须是成员声明（¶7），静态成员也不例外。
</details>

!!! question "思考题 2"
    为什么 ¶14 规定"命名构造函数时不做访问检查"，而 ¶16 又说继承构造函数的可访问性与基类中一致？两条规则合起来想达到什么效果？

<details markdown="1">
<summary>答案</summary>

`using Base::Base;` 命名的是基类的**全部**构造函数，其中通常有 private 的（例如私有的辅助构造函数）。如果像普通成员那样要求每个都可访问，几乎所有类都无法被继承构造。因此 ¶14 对构造函数放弃了"整个集合可访问"的检查；¶16 则保证可访问性不被"提升"或"降低"：基类中 private 的构造函数在派生类中也不能被外部调用，protected 的仍然只能在能构造基类的地方使用——using 声明的位置（在 public 还是 private 部分）被忽略。效果是：继承构造函数的可访问性"原样继承"。
</details>

!!! question "思考题 3"
    `struct B { void f(); }; struct D : B { using B::f; void f(); };` 中 D 的 `f` 是重声明、冲突还是隐藏？如果把 D 中的声明改成 `void f() const;` 呢？

<details markdown="1">
<summary>答案</summary>

第一种：`B::f` 视为 D 的成员时与 `D::f()` **对应**（同名、同参数、同 cv），按 ¶11 它被从 using 声明命名的集合中排除，即被 `D::f` **隐藏**——既不冲突也不是重声明。第二种：`void f() const` 与 `B::f()` 的 cv 限定不同，不对应，两者**并存**于重载集中；对非 const 的 `D` 对象调用 `f()` 选中 `B::f`（对象参数视为 `D&`，¶12，比 `const D&` 更好），对 const 对象调用选中 `D::f() const`。
</details>

## 小结

!!! summary "要点"
    - using 声明在声明点对限定名查找的结果拍一张"快照"，绑定到一个名字；之后添加的重载不会进入（默认实参和特化会）。
    - 类中：只能命名基类成员或枚举量；命名构造函数时必须是直接基类，表示**继承构造函数**。
    - 派生类自己声明的对应函数会隐藏/覆盖 using 声明带进来的基类函数（¶11），不冲突。
    - 重载决议中，using 声明引入的成员函数的隐式对象参数视为派生类引用（¶12）。
    - 访问：普通成员要求整个集合可访问，using 声明本身的访问级别决定新名字的访问级别；构造函数不检查、可访问性与基类一致。
    - 不能命名 *template-id*、命名空间、析构函数；类成员（除枚举量）不能在类外 using。
