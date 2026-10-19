---
title: 受保护成员访问
summary: 派生类只能经由自己（或自己的派生类）类型的对象访问基类的 protected 非静态成员，形成成员指针时也必须写自己的类名。
status: done
related: class.access, class.access.base, class.friend, expr.ref, expr.unary.op, expr.mptr.oper
tags: 类, 访问控制, protected
updated: 2026-10-19
---

!!! tldr
    - 派生类 `D` 的成员和友元访问基类的 protected 非静态成员时，对象表达式的静态类型必须是 `D` 或 `D` 的派生类。经由 `B&`、兄弟类对象访问都不行。
    - 形成成员指针时要写 `&D::m`，不能写 `&B::m`；但得到的类型仍是 `T B::*`。
    - 静态成员、枚举成员、嵌套类型和由 splice 指名的成员不受这项检查。
    - 成员指针一旦形成，可以通过 `.*` 作用于任何 `B` 对象，所以 protected 防的是误用，不是有意的绕过。

## 派生类只能动自己那一份

```cpp error
class Account {
protected:
    int balance = 0;
};
class Savings : public Account {};
class Attacker : public Account {
public:
    static void reset(Savings& s) {
        s.balance = 0;   // error: s 不是 Attacker
    }
    void reset_self() {
        balance = 0;     // OK：this 是 Attacker*
    }
};
```

`Attacker` 是 `Account` 的派生类，可以访问 `Account` 的 protected 成员，但只能经由 `Attacker` 对象访问。如果没有这条限制，任何人只要从 `Account` 派生一个类，就能改写所有 `Account` 对象（包括 `Savings` 对象）的内部状态，protected 就和 public 差不多了。

所以 protected 的含义是：基类和它的每一个派生类之间的接口。`Savings` 的不变式由 `Account` 和 `Savings` 共同维护，旁系的 `Attacker` 无权插手。

## 规则（¶1）

先回顾 [[class.access.base]] 的两个概念。**指名类**（[[g:designating-class]]）是查找成员名时所在的类：`p->m` 中是 `p` 指向的类，`p->B::m` 中是 `B`。protected 成员在某处可访问，是因为这个引用出现在某个类 C 的成员或友元中，而 C 是该成员所在类的派生类（[[class.access.base#5]]）。

¶1 在此之上，对 protected 的非静态数据成员和非静态成员函数再加一项检查（成员由 *splice-expression* 指名时除外）。设访问因 C 的成员或友元身份而获准：

- 如果访问是为了形成成员指针（[[expr.unary.op]]），*nested-name-specifier* 必须指名 C 或 C 的派生类；
- 否则，如果访问涉及一个对象表达式（可以是隐式的 `*this`，[[expr.prim.id.general]]、[[expr.ref]]），对象表达式的类必须是 C 或 C 的派生类。

!!! std
    Otherwise, if the access involves a (possibly implicit) object expression, the class of the object expression shall be C or a class derived from C.

脚注 91 补充，这项检查不适用于其他成员，例如静态数据成员和枚举成员。

## 标准例逐行看

```cpp title="protected-std-example.cpp" error
class B {
protected:
    int i;
    static int j;
};
class D1 : public B {};
class D2 : public B {
    friend void fr(B*, D1*, D2*);
    void mem(B*, D1*);
};

void fr(B* pb, D1* p1, D2* p2) {
    pb->i = 1;                 // error: 对象表达式的类是 B
    p1->i = 2;                 // error: D1 是 D2 的兄弟
    p2->i = 3;                 // OK
    p2->B::i = 4;              // OK: 指名类是 B，但对象是 D2
    int B::* pmi_B = &B::i;    // error: 必须写 &D2::i
    int B::* pmi_B2 = &D2::i;  // OK: 类型仍是 int B::*
    B::j = 5;                  // error: fr 不是 B 的友元
    D2::j = 6;                 // OK: 静态成员，指名类 D2
}

void D2::mem(B* pb, D1* p1) {
    pb->i = 1;                 // error
    p1->i = 2;                 // error
    i = 3;                     // OK: 隐式 this->i
    B::i = 4;                  // OK: 隐式 (*this).B::i
    int B::* pmi_B = &B::i;    // error
    int B::* pmi_B2 = &D2::i;  // OK
    j = 5;                     // OK: 静态成员
    B::j = 6;                  // OK: 静态成员
}

void g(B* pb, D1* p1, D2* p2) {
    pb->i = 1;                 // error: g 既非成员也非友元
    p1->i = 2;                 // error
    p2->i = 3;                 // error
}
```

`p2->B::i` 说明附加检查和指名类是两回事：限定名把指名类定为 `B`，但附加检查看的是对象表达式的类 `D2`，所以合法。

`B::j` 在 `fr` 里报错、在 `D2::mem` 里不报错，原因不在附加检查（静态成员不受它约束），而在基本的可访问性。[[class.access.base#5]] 第 5.6 项允许的是出现在派生类成员中的引用，`fr` 只是 `D2` 的友元；指名类又是 `B`，`fr` 不是 `B` 的友元。改写成 `D2::j` 后，指名类变成 `D2`，`j` 作为 `D2` 的成员是 protected 的，`fr` 是 `D2` 的友元，于是可访问。

`&B::i` 和 `&D2::i` 的类型都是 `int B::*`，因为成员指针的类型由成员实际所在的类决定（[[expr.unary.op]]）。区别只在于后者能通过附加检查。

## 常见的几种碰壁

### 转换成基类就不行了

```cpp error
class B { protected: int i = 0; };
class D : public B {
    void f() {
        i = 1;                         // OK: this->i
        this->B::i = 2;                // OK: 对象的类是 D
        static_cast<B&>(*this).i = 3;  // error: 对象的类变成了 B
        B* pb = this;
        pb->i = 4;                     // error: 即使 pb 指向 *this
    }
};
```

附加检查只看对象表达式的静态类型，不关心它运行时是否恰好指向自己。

### 从基类对象拷贝

```cpp error
class Base { protected: int v = 0; };
class Derived : public Base {
public:
    void copy_from(const Derived& o) { v = o.v; }  // OK
    void copy_from(const Base& o)    { v = o.v; }  // error
};
```

常见的做法是在 `Base` 里提供一个 protected 的辅助函数，例如 `assign_from(const Base&)`，由 `Base` 自己读取 `o.v`。

### 隔代访问

```cpp error
class B { protected: void f(); };
class D : public B {};
class E : public D {
    void g(D& d, E& e) {
        d.f();   // error: D 是 E 的基类，不是 E 的派生类
        e.f();   // OK
    }
};
```

在 `E` 的成员中，访问因 `E` 的成员身份获准，C 就是 `E`。`D` 虽然也派生自 `B`，但它不是 `E` 或 `E` 的派生类。

### protected 的构造函数和析构函数

```cpp error
class B {
protected:
    B() = default;
    ~B() = default;
};
class D : public B {
    void f() {
        D d;           // OK: 初始化 D 的基类子对象
        B b;           // error: 构造独立的 B 对象
        B* p = new B;  // error
    }
};
```

把构造函数设为 protected，惯用的含义是这个类只能作为基类使用；把非虚析构函数设为 protected，含义是不能经由基类指针 `delete`。本机 Clang 23 拒绝 `B b;`（同时报告构造函数和析构函数不可访问）和 `new B`。

!!! lawyer "构造函数调用里的对象表达式"
    `B b;` 里没有字面上的对象表达式，¶1 如何作用于构造函数调用，措辞并不完全明确。各实现的共同理解是：在 `D` 的成员里创建独立的 `B` 对象，相当于经由一个 `B` 对象访问 protected 成员，因此拒绝；初始化 `D` 自己的 `B` 基类子对象则允许。

## 成员指针绕过检查

¶1 要求写 `&D2::i`，但得到的 `int B::*` 可以作用于任何 `B` 对象：

```cpp run title="pmf-loophole.cpp" ok
#include <cstdio>

class B {
protected:
    int i = 1;
};
class D1 : public B {};
class D2 : public B {
public:
    static int peek(B& any) {
        // return any.i;          // error
        int B::* p = &D2::i;      // OK
        return any.*p;            // OK: .* 不指名成员
    }
};

int main() {
    D1 sibling;
    std::printf("%d\n", D2::peek(sibling));  // 1
}
```

`.*` 和 `->*`（[[expr.mptr.oper]]）不指名成员，访问控制只在形成成员指针时检查一次。这是规则的已知后果，不是编译器缺陷。访问控制针对的是无意的误用，不是有意的绕过。

## 不受附加检查的情形

| 情形 | 原因 |
|---|---|
| 静态数据成员、静态成员函数 | 不属于某个对象（脚注 91） |
| 枚举成员、嵌套类型、类型别名 | 同上 |
| 由 *splice-expression* 指名的成员 {{c++26}} | ¶1 明确排除；这类成员总是可访问（[[class.access.base#5]] 第 5.3 项） |
| 在指名类中是 public 的成员 | 附加检查只针对在指名类中是 protected 的成员 |

最后一行的例子：`struct S { int x; }; class T : protected S {}; class U : public T {};`。在 `U` 的成员里通过 `S& s` 写 `s.x`，指名类是 `S`，`x` 在 `S` 中是 public 的，可以直接访问，不涉及附加检查。

静态成员只有一份，由整个类层次共享，不存在别人的那一份需要保护。如果对它也做附加检查，`B::j` 这种没有对象表达式的写法就无从检查；而 `pb->j` 会因为 `pb` 的类型不同时而合法、时而非法，访问的却是同一个实体。

!!! note "诊断"
    Clang 对附加检查失败的报告和普通的不可访问一样，只说 `'i' is a protected member of 'B'`，不提对象表达式的类型，容易让人误以为派生类根本不能访问 protected 成员。

## 思考题

!!! question "思考题"
    `D2` 的友元函数 `fr(D1& x)` 能否通过 `static_cast<B&>(x).i` 访问 `x` 的 `i`？能否通过 `x.*(&D2::i)` 访问？

<details markdown="1">
<summary>答案</summary>

第一种不能：对象表达式的类是 `B`，不是 `D2` 或其派生类。第二种可以：`&D2::i` 满足成员指针的要求，类型是 `int B::*`；`D1&` 可以隐式转换为 `B&`，`.*` 不做访问检查。友元和成员在这里受同样的约束，也享有同样的漏洞。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

这条规则自 C++98 起就有，实质内容一直没变，措辞随着指名类、对象表达式等概念的整理而改写过多次。C++26 引入静态反射后，加上了排除 *splice-expression* 的条件。

</details>
