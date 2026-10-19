---
title: 受保护成员访问
summary: protected 非静态成员的附加检查：经由派生类 C 的成员或友元访问时，对象表达式的类必须是 C 或其派生类；形成成员指针时嵌套名说明符必须指名 C 或其派生类；静态成员与 splice 不受此限；经典谜题与成员指针后门
status: draft
related: class.access, class.access.base, class.friend, expr.ref, expr.unary.op, expr.mptr.oper
tags: 类, 访问控制, protected
updated: 2026-10-17
---

关于 `protected`，最常见的说法是"派生类可以访问基类的 protected 成员"，但这只说对了一半。准确地说，**派生类只能访问它自己那一份基类子对象中的 protected 成员**，也就是通过自己（或自己的派生类）类型的对象访问，而不能通过任意的基类对象访问。本节的附加检查就是把这一限制写成了规则。

前置阅读：[[class.access]]，特别是 [[class.access.base]] 中指名类（designating class）的概念和 ¶5.6（protected 成员何时可访问）。

## 规则（¶1）

¶1：如果一个非静态数据成员或非静态成员函数是其指名类的 protected 成员，且不是由 *splice-expression* 指名的，那么在 [[class.access]] 已有的检查之外，还要施加一项**附加检查**：

如前所述，对 protected 成员的访问之所以获准，是因为引用出现在某个类 C 的友元或直接成员中。于是：

- 如果访问是为了形成成员指针（`&X::m`，[[expr.unary.op]]），*nested-name-specifier* 必须指名 C 或 C 的派生类；
- 否则，如果访问涉及一个（可能隐式的）对象表达式（[[expr.prim.id.general]]、[[expr.ref]]），对象表达式的类必须是 C 或 C 的派生类。

脚注 91：这一附加检查不适用于其他成员，例如静态数据成员或枚举成员常量。

!!! std
    Otherwise, if the access involves a (possibly implicit) object expression, the class of the object expression shall be C or a class derived from C.

    否则，若访问涉及一个（可能隐式的）对象表达式，该对象表达式的类应为 C 或派生自 C 的类。

### 为什么需要这条规则

设想没有这条规则：

```cpp
class Account {
protected:
    int balance = 0;
};
class Savings : public Account { };
class Attacker : public Account {
public:
    static void steal(Account& victim) { victim.balance = 0; }   // 假如合法……
};
```

那么任何人只要从 `Account` 派生一个类，就能修改所有 `Account` 对象（包括 `Savings` 对象）的 protected 状态，protected 就退化成了多写一行就能访问的 public。附加检查把权限限制在派生类自己（及其后代）的对象上：`Attacker` 只能改动 `Attacker` 对象的 `balance`。

`Savings` 的不变式应该由 `Account` 和 `Savings` 共同维护，旁系的 `Attacker` 无权插手。这正是 protected 的设计意图：**它是基类与其派生类之间的接口**，而不是所有派生类共享的后门。

## 标准例子逐行解读

```cpp title="protected-std-example.cpp" error
class B {
protected:
    int i;
    static int j;
};

class D1 : public B { };

class D2 : public B {
    friend void fr(B*, D1*, D2*);
    void mem(B*, D1*);
};

void fr(B* pb, D1* p1, D2* p2) {
    pb->i = 1;                    // error: 对象表达式的类是 B，不是 D2 或其派生类
    p1->i = 2;                    // error: D1 是 D2 的兄弟，不是 D2 的派生类
    p2->i = 3;                    // OK: 经由 D2 访问
    p2->B::i = 4;                 // OK: 经由 D2 访问——指名类是 B，但对象表达式的类是 D2
    int B::* pmi_B = &B::i;       // error: 成员指针的嵌套名说明符必须指名 D2 或其派生类
    int B::* pmi_B2 = &D2::i;     // OK: &D2::i 的类型是 int B::*
    B::j = 5;                     // error: fr 不是指名类 B 的友元（static 成员不受附加检查，
                                  //        但 j 作为 B 的 protected 成员本身就不可访问）
    D2::j = 6;                    // OK: 指名类是 D2，fr 是 D2 的友元；static 成员不做附加检查
}

void D2::mem(B* pb, D1* p1) {
    pb->i = 1;                    // error
    p1->i = 2;                    // error
    i = 3;                        // OK: 隐式 this->i，this 的类型是 D2*
    B::i = 4;                     // OK: 隐式 (*this).B::i，对象仍是 D2
    int B::* pmi_B = &B::i;       // error
    int B::* pmi_B2 = &D2::i;     // OK
    j = 5;                        // OK: 静态成员
    B::j = 6;                     // OK: 在 D2 的成员中，B::j 作为 B 的 protected 成员可访问（[class.access.base]/5.6），
                                  //     且静态成员不做附加检查
}

void g(B* pb, D1* p1, D2* p2) {
    pb->i = 1;                    // error: g 既不是成员也不是友元
    p1->i = 2;                    // error
    p2->i = 3;                    // error
}
```

几个要点：

- **`p2->B::i`**：指名类是 `B`（由限定名决定），但附加检查看的是对象表达式的类（`D2`），所以合法。附加检查与指名类是两回事。
- **`B::j` 在 `fr` 中报错，在 `D2::mem` 中不报错**：区别不在附加检查（static 成员不受附加检查），而在基本的可访问性。[class.access.base]/5.6 允许的是引用出现在 N 的派生类 P 的成员中，而 `fr` 是 `D2` 的友元而非成员，指名类又是 `B`，所以不满足条件。改写成 `D2::j` 后，指名类变成 `D2`，`j` 作为 `D2` 的成员是 protected 的，`fr` 又是 `D2` 的友元，满足 ¶5.6 的第一种情形。
- **`&B::i` 与 `&D2::i`**：二者的类型都是 `int B::*`（[[expr.unary.op]]：成员指针的类型由成员所属的类决定），但只有后者能通过附加检查。

## 经典谜题

### 谜题 1：访问另一个同类对象

```cpp title="puzzle-same-class.cpp" error
class Base {
protected:
    int v = 0;
};
class Derived : public Base {
public:
    void copy_from(const Derived& other) { v = other.v; }   // OK: other 是 Derived
    void copy_from(const Base& other)    { v = other.v; }   // error: other 的类是 Base
};
```

很多人在实现从基类拷贝时遇到这个错误。通常的解决方法是在 `Base` 中提供一个 protected 的辅助函数（如 protected 的复制构造函数或 `assign_from(const Base&)`），由 `Base` 自己读取 `other.v`。

### 谜题 2：转换成基类就不行了

```cpp title="puzzle-cast.cpp" error
class B { protected: int i = 0; };
class D : public B {
    void f() {
        i = 1;                              // OK: this->i
        this->B::i = 2;                     // OK: 对象表达式的类是 D
        static_cast<B&>(*this).i = 3;       // error: 对象表达式的类变成了 B
        B* pb = this;
        pb->i = 4;                          // error: 同上——即使 pb 实际指向 *this
    }
};
```

附加检查是静态的：它看的是对象表达式的静态类型，不关心运行时它是否恰好指向自己。

### 谜题 3：受保护的构造函数与析构函数

```cpp title="puzzle-protected-ctor.cpp" error
class B {
protected:
    B() = default;
    ~B() = default;
};
class D : public B {
    void f() {
        D d;          // OK: 构造 D 时调用 B()：这是在 D 的构造函数中对基类子对象的初始化
        B b;          // error: 在 D 的成员中创建一个独立的 B 对象
        B* p = new B; // error
    }
};
```

把构造函数设为 `protected`，惯用的含义是这个类只能作为基类使用（类似抽象类，但无需纯虚函数）；把非虚析构函数设为 `protected`，含义是不能通过基类指针 `delete`。主流编译器都拒绝 `B b;`（本机 Clang 已验证）。

!!! lawyer "构造函数与附加检查"
    构造函数是非静态成员函数，但 `B b;` 中并没有字面意义上的对象表达式，所以 ¶1 的附加检查如何适用于构造函数调用，措辞并不完全明确。各实现的共识是：在 `D` 中创建独立的 `B` 对象，相当于经由一个 `B` 类型的对象访问 protected 成员，因此拒绝；而构造 `D` 时初始化其 `B` 基类子对象是允许的。析构函数同理（`B b;` 在作用域结束时要隐式调用 `~B()`）。

## 成员指针：附加检查的漏洞

¶1 要求形成成员指针时写 `&D2::i` 而不是 `&B::i`，但得到的成员指针类型是 `int B::*`，可以作用于任何 `B` 对象：

```cpp run title="pmf-loophole.cpp" ok
#include <cstdio>

class B {
protected:
    int i = 1;
};
class D1 : public B { };          // 兄弟类
class D2 : public B {
public:
    static int peek(B& any) {
        // return any.i;           // error: 对象表达式的类是 B
        int B::* p = &D2::i;       // OK: 嵌套名说明符指名 D2
        return any.*p;             // OK: .* 不涉及对 i 的指名，不做访问检查
    }
};

int main() {
    D1 sibling;
    std::printf("%d\n", D2::peek(sibling));   // 读到了兄弟类对象的 protected 成员
}
```

这是规则的一个已知后果，不是编译器漏洞：`.*`/`->*`（[[expr.mptr.oper]]）不指名成员，访问控制只在形成成员指针时检查一次。标准接受这一点，因为附加检查的目的是防止无意的误用，而不是对抗有意的绕过。

## 不受附加检查的情形

| 情形 | 原因 |
|---|---|
| 静态数据成员、静态成员函数 | 不属于任何对象（脚注 91） |
| 枚举成员、嵌套类型、类型别名 | 同上 |
| 由 *splice-expression* 指名的成员 {{c++26}} | ¶1 明确排除；splice 指名的成员总是可访问（[class.access.base]/5.3） |
| 指名类中 public 的成员（即使它在更派生类中变成 protected） | 附加检查只针对作为指名类的 protected 成员 |

最后一行的例子：`struct B { int x; }; class D : protected B {};` 中，在 `D` 的派生类 `E` 的成员里写 `b.x`（`b` 是 `B&`），指名类是 `B`，`x` 作为 `B` 的成员是 public 的，可以直接访问，不涉及 protected 的附加检查。

## 实现视角

!!! impl
    - 附加检查完全在编译期进行，依据表达式的静态类型。实现时需要记录访问是凭借哪个类 C 的成员资格获准的，然后检查对象表达式的类是否为 C 的（非严格）派生类。Clang 在 `Sema` 的访问检查中专门为 protected 成员处理这种实例上下文（instance context）。
    - 诊断质量：主流编译器通常只报告 "`i` 是 `B` 的 protected 成员"，而不解释原因在于对象表达式的类不是当前类的派生类，容易让人误以为派生类根本不能访问 protected 成员。

## 历史与演进

!!! history
    - 这条规则自 C++98 起就存在，实质内容一直稳定；措辞随着指名类、对象表达式等概念的重新整理而多次改写。
    - **C++26** {{c++26}}：明确排除由 *splice-expression* 指名的成员。

## 陷阱

!!! pitfall
    1. **以为派生类可以随意访问基类的 protected 成员**：只能经由派生类自身（或其后代）类型的对象访问。
    2. **转换为 `Base&` 后访问**：静态类型变成了 `Base`，附加检查不通过。
    3. **兄弟类之间不能互相访问 protected 成员**，即使它们派生自同一个基类。
    4. **友元函数也受附加检查**：`D2` 的友元只能经由 `D2`（及其派生类）对象访问 `B` 的 protected 非静态成员。
    5. **成员指针后门**：`&D::m` 得到的是 `T B::*`，可以作用于任何 `B`。在需要真正保护的场合，protected 不是可靠的边界。

## 思考题

!!! question "思考题 1"
    ```cpp
    class B { protected: void f(); };
    class D : public B { };
    class E : public D {
        void g(D& d, E& e) { d.f(); e.f(); }
    };
    ```
    哪个调用合法？

<details markdown="1">
<summary>答案</summary>

`e.f()` 合法：访问因 `E` 的成员资格获准（C = `E`），对象表达式的类是 `E`。`d.f()` ill-formed：对象表达式的类是 `D`，它是 `E` 的基类，而不是 `E` 或其派生类，尽管 `D` 也派生自 `B`，`E` 也派生自 `D`。在 `E` 的成员中，只有经由 `E`（或 `E` 的派生类）对象才能访问 `B` 的 protected 非静态成员。
</details>

!!! question "思考题 2"
    为什么附加检查不适用于静态成员？如果适用，会产生什么问题？

<details markdown="1">
<summary>答案</summary>

静态成员不属于任何对象，不存在别人的那一份。附加检查要保护的是其他继承分支上对象的状态，而静态成员只有一份，由整个类层次共享，按 [class.access.base]/5.6 判断是否可访问就足够了。如果对静态成员也施加附加检查，`B::j` 这种没有对象表达式的写法就没有可检查的对象类型；而 `pb->j`（静态成员也可以用成员访问语法）会因为 `pb` 的类型不同而时而可以、时而不行，访问的却是同一个实体，这样的规则毫无意义。
</details>

## 小结

!!! summary
    - 附加检查适用于：非静态数据成员与成员函数、作为指名类的 protected 成员、不是由 splice 指名。
    - 访问因类 C 的成员/友元身份获准时：
        - 对象表达式的类必须是 C 或 C 的派生类；
        - 形成成员指针时，嵌套名说明符必须指名 C 或 C 的派生类。
    - 检查依据静态类型；兄弟类、转换为基类后都不行。
    - 成员指针一旦形成，`.*` 可以作用于任何基类对象，这是规则的已知后果。
