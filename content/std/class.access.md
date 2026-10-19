---
title: 成员访问控制
summary: 访问控制管的是名字能否被指名，而不是实体能否被使用；在名字查找与重载决议之后检查；访问说明符；public/protected/private 继承与可访问基类；指名类与可访问性算法；虚函数按静态类型检查访问；多条路径取最宽；嵌套类；显式实例化中不检查访问的后门；C++26 splice 绕过访问
status: draft
covers: class.access.general, class.access.spec, class.access.base, class.access.virt, class.paths, class.access.nest
related: class.friend, class.protected, class.member.lookup, conv.ptr, namespace.udecl, temp.spec.general, temp.deduct.general, expr.ref, class.local
tags: 类, 访问控制, 继承, 友元
updated: 2026-10-17
---

访问控制（`public`/`protected`/`private`）是 C++ 封装的语言基础，但它的精确语义与大多数程序员的直觉不同。本页覆盖第 11.8 节中除友元（[[class.friend]]）与受保护访问附加规则（[[class.protected]]）以外的全部子条款。

先记住三条贯穿全节的原则：

1. **访问控制针对的是名字，不是实体**。它判断的是在这个位置能否指名（name）这个成员，而不是这个对象或函数能不能被使用。借助 public 的别名、指针、引用或模板实参，完全可以使用私有实体。
2. **访问控制在最后检查**。名字查找、重载决议、隐式转换的选择都不考虑访问权：先确定这段代码是什么意思，再检查它是否用到了不可访问的东西。访问控制不会改变程序的含义，只会让它 ill-formed。
3. **访问检查的语境是声明**。一个名字能否被指名，取决于这个名字出现在哪个实体的声明里（成员函数、友元……），而不是运行时谁在调用。

## 三种访问权（[class.access.general] ¶1）

¶1：类的成员可以是

- ¶1.1 **private**：只能由声明它的类的成员和友元指名；
- ¶1.2 **protected**：只能由声明它的类的成员和友元、派生自该类的类及其友元指名（附加限制见 [[class.protected]]）；
- ¶1.3 **public**：可以在任何地方指名。

注 1：构造函数和析构函数没有名字，但表达式可以指名它们（[[basic.def.odr]]），所以它们同样受访问控制。私有构造函数能阻止外部创建对象，原因就在这里。

注意原文的措辞是 "can be named"，这是理解本节的关键：

```cpp run title="names-not-entities.cpp" ok
class Vault {
    int secret = 42;
public:
    int& door() { return secret; }          // 通过 public 接口泄露引用
    static constexpr auto ptr = &Vault::secret;   // 在类内部可以指名 secret
};

int main() {
    Vault v;
    int& r = v.door();                      // OK: 没有在外部指名 secret
    r = 7;                                  // OK: 访问的是实体，与访问控制无关
    return v.*Vault::ptr == 7 ? 0 : 1;      // OK: 指名的是 public 的 ptr
}
```

访问控制不是安全机制：它防止的是无意中写出依赖实现细节的代码，并不防止有意绕过（本页末尾还会介绍合法的绕过方法）。

## 访问权的传递（¶2）

¶2：类的成员可以访问该类有权访问的所有成员。成员函数中的局部类可以访问该成员函数本身能访问的成员（[[class.local]]）。脚注 89 总结说，对嵌套类和局部类而言，访问权是可传递、可累积的。

```cpp run title="nested-access.cpp" ok
class Outer {
    int x = 1;
    class Inner {                       // 嵌套类是成员，拥有成员的访问权
        int peek(Outer& o) { return o.x; }
        struct Deeper {                 // 嵌套类的嵌套类：同样可以
            int peek(Outer& o) { return o.x; }
        };
    };
public:
    int f() {
        struct Local {                  // 成员函数中的局部类：继承 f 的访问权
            static int get(Outer& o) { return o.x; }
        };
        return Local::get(*this);
    }
};

int main() { Outer o; return o.f() == 1 ? 0 : 1; }
```

## 默认访问权（¶3）

¶3：用 `class` 定义的类，成员默认是 private 的；用 `struct` 或 `union` 定义的，默认是 public 的。`class` 与 `struct` 在语言上只有两处差别，这是其中之一（另一处是默认继承方式，见 [class.access.base]/2）。

## 访问控制统一适用，且在重载决议之后（¶4–¶5）

¶4：访问控制统一适用于声明和表达式。注 2：访问控制也适用于友元声明所指名的成员（[[class.friend#8|[class.friend]/8]]）和 using 声明（[[namespace.udecl]]）。指名一个 *using-declarator* 时，访问控制施加于 using 声明本身，而不是它所引入的声明。

!!! std
    For an overload set, access control is applied only to the function selected by overload resolution.

    对于重载集，访问控制只施加于重载决议所选中的那个函数。

```cpp title="access-after-overload.cpp" error
struct S {
    void f(int);
private:
    void f(double);
};

void g(S* sp) {
    sp->f(2);        // OK: 选中 f(int)，它是 public 的
    sp->f(2.0);      // error: 选中 f(double)，它是 private 的——不会"退而求其次"去选 f(int)
}
```

第二个调用是理解 ¶5 的关键：**私有的 `f(double)` 并没有从候选中消失**。重载决议选中了它（精确匹配），随后访问检查失败，程序 ill-formed。访问控制不参与选择哪个函数，只负责判断选中的函数能不能用。

¶5 正式表述了这一原则：

!!! std
    The interpretation of a given construct is established without regard to access control. If the interpretation established makes use of inaccessible members or base classes, the construct is ill-formed.

    一个构造的解释在不考虑访问控制的情况下确定。若所确定的解释用到了不可访问的成员或基类，该构造 ill-formed。

注 4：访问控制不会阻止成员被名字查找找到，也不会阻止对基类的隐式转换被考虑。

为什么这样设计？如果访问控制参与重载决议，同一段代码在类内和类外就会选中不同的函数：在类外选 `f(int)`，在成员函数里选 `f(double)`。这样一来，把一段代码从成员函数挪到自由函数里会悄悄改变语义，把一个成员从 public 改成 private 也会无声地改变别处的重载选择。C++ 的选择是让含义保持稳定，出错就报错。

### 类型别名：只看别名本身

注 3：访问控制施加于被指名的声明，因此对类型别名只检查别名声明本身的访问权，不检查底层实体：

```cpp title="typedef-access.cpp" error
class A {
    class B { };
public:
    typedef B BB;
};

void f() {
    A::BB x;          // OK: typedef A::BB 是 public 的
    auto y = A::BB{}; // OK
    decltype(y) z;    // OK: 根本没有指名 A::B
    A::B w;           // error: A::B 是 private 的
}
```

这再次说明访问控制管的是拼写；在类外，完全可以通过 `auto`、`decltype`、模板实参推导来使用私有类型。

### SFINAE 与访问控制

从 C++11 起，访问检查是模板实参替换的一部分（[[temp.deduct.general#8]] 注 5）：在替换中指名不可访问的成员属于替换失败，而不是硬错误。因此可以用 trait 检测可访问的成员：

```cpp run title="sfinae-access.cpp" ok
#include <type_traits>
#include <utility>

template<class T, class = void> struct has_v : std::false_type {};
template<class T> struct has_v<T, std::void_t<decltype(std::declval<T&>().v)>> : std::true_type {};

class Hidden { int v; };
struct Open  { int v; };

static_assert(!has_v<Hidden>::value);   // 不可访问 ⇒ 替换失败 ⇒ 选主模板
static_assert(has_v<Open>::value);

int main() { }
```

## 访问检查的语境（¶6–¶7）

¶6：所有访问控制影响的，都是从某个特定实体的声明中指名类成员的能力，这包括该声明中出现在被声明实体名字之前的部分；如果实体是类，还包括在类的 *member-specification* 之外出现的该类成员的定义。注 5：这种访问也适用于对构造函数、转换函数和析构函数的隐式引用。

这句话解决了一个语法上的难题。考虑类外定义成员函数：

```cpp
A::I A::f() { return 0; }
```

返回类型 `A::I` 出现在 `A::f` 之前，解析到 `A::I` 时，编译器还不知道这是 `A` 的成员函数的定义。¶6 规定访问检查以整个声明为语境，所以 `A::I` 也按 `A::f` 的权限检查。¶7 的例子列出了各种情况：

```cpp title="access-context.cpp" ok
class A {
    typedef int I;                   // private
    I f();
    friend I g(I);
    static I x;
    template<int> struct Q;
    template<int> friend struct R;
protected:
    struct B { };
};

A::I A::f() { return 0; }            // OK: 返回类型在 A::f 的声明中，A::f 是成员
A::I g(A::I p = A::x);               // OK: g 是 A 的友元（包括默认实参中的 A::x）
A::I g(A::I p) { return 0; }
A::I A::x = 0;                       // OK: 静态成员的定义
template<A::I> struct A::Q { };      // OK: 成员模板的定义
template<A::I> struct R { };         // OK: R 是友元
struct D : A::B, A { };              // OK: D 派生自 A，可以访问 protected 的 A::B
```

最后一行最微妙：解析 `A::B` 时还没看到后面的 `, A`，不知道 `D` 派生自 `A`。标准要求实现推迟对 *base-specifier* 的访问检查，直到看完整个 *base-specifier-list*。

!!! impl "编译器偏差"
    截至写作时，Clang 23 以 "`B` 是 `A` 的 protected 成员" 为由拒绝最后一行，因为它没有把 *base-specifier* 中的访问检查推迟到整个列表结束。其余各行 Clang 都接受。按标准，整个例子是良构的。

## 默认实参与默认模板实参（¶8–¶9）

¶8：默认实参的访问在声明处检查，而不是在使用处。函数模板与类模板成员函数的默认实参按 [[temp.inst]] 的规则（实例化时在声明的语境中）检查。

```cpp run title="default-arg-access.cpp" ok
class C {
    static int k;                       // private
public:
    static void h(int = k) {}           // OK: 在 C 的成员声明中指名 k
};
int C::k = 0;

int main() { C::h(); }                  // OK: 调用处不重新检查默认实参的访问
```

这很合理：默认实参是声明的一部分，由声明者负责；调用者只是接受默认值，不应该因为默认值的写法而出错。

¶9：默认模板实参的访问在它出现的语境中检查，而不是在使用处：

```cpp title="default-template-arg-access.cpp" error
class B { };
template <class T> class C {
protected:
    typedef T TT;
};

template <class U, class V = typename U::TT>   // 在命名空间作用域中检查 U::TT
class D : public U { };

D<C<B>>* d;    // error: C<B>::TT 是 protected 的；尽管 D 派生自 C<B>，默认实参不在 D 的作用域内
```

---

## 访问说明符（[class.access.spec]）

¶1–¶2：成员声明可以用 *access-specifier*（`public:` 等）标记，它对其后的成员生效，直到类结束或遇到另一个访问说明符。访问说明符可以出现任意多次、任意顺序。

¶3：在类内重声明一个成员时，访问权必须与首次声明相同：

```cpp title="redeclare-access.cpp" error
struct S {
    class A;
    enum E : int;
private:
    class A { };                  // error: 不能改变访问权
    enum E : int { e0 };          // error: 不能改变访问权
};
```

¶4（注 1）是一个经典陷阱：在派生类中查找基类的名字时，找到的是注入类名（injected-class-name，[[class.pre]]）。它作为基类的成员继承下来，可访问性随继承方式变化，可能比原作用域中的类名更难访问：

```cpp title="injected-class-name-access.cpp" error
class A { };
class B : private A { };
class C : public B {
    A* p;              // error: 找到的是注入类名 B::A（经 private 继承而来，在 C 中不可访问）
    ::A* q;            // OK: 全局作用域中的 A
};
```

## 基类的可访问性（[class.access.base]）

### 继承方式（¶1–¶2）

¶1：继承方式决定基类成员在派生类中具有什么访问权：

| 基类中的 ↓ ／ 继承方式 → | `public` | `protected` | `private` |
|---|---|---|---|
| public 成员 | public | protected | private |
| protected 成员 | protected | protected | private |
| private 成员 | （不可访问） | （不可访问） | （不可访问） |

脚注 90：基类的 private 成员对派生类始终不可访问，除非基类用友元声明显式授权。

¶2：没有写访问说明符时，用 `struct` 定义的派生类默认 `public` 继承，用 `class` 定义的默认 `private` 继承。这由派生类的 *class-key* 决定，与基类用什么关键字定义无关。

### 直接指名 vs 作为继承成员指名（¶3）

¶3（注 1）：私有基类的成员作为继承成员可能不可访问，直接指名却可以访问。指针的隐式转换可能因基类不可访问而 ill-formed，显式转换（C 风格转换）却是良构的。

```cpp title="private-base-note.cpp" error
class B {
public:
    int mi;
    static int si;
};
class D : private B { };
class DD : public D {
    void f();
};

void DD::f() {
    mi = 3;                       // error: mi 在 D 中是 private 的（经 DD → D → B 路径指名）
    si = 3;                       // error: 同上，静态成员也一样
    ::B  b;
    b.mi = 3;                     // OK: 直接通过 ::B 指名，与继承无关
    b.si = 3;                     // OK
    ::B::si = 3;                  // OK
    ::B* bp1 = this;              // error: B 是 D 的私有基类，DD 中不可访问
    ::B* bp2 = (::B*)this;        // OK: C 风格转换可以忽略基类的可访问性
    bp2->mi = 3;                  // OK: 通过 B* 访问
}
```

C 风格转换可以无视私有继承（[[expr.cast]]），这是 C 风格转换能做而 `static_cast` 做不到的少数几件事之一。

### 可访问基类的定义（¶4）

¶4 定义了基类 `B` 何时在程序点 *R* 处是 `N` 的**可访问基类**：假想 `B` 有一个 public 成员 m，满足下列条件之一即可：

- ¶4.1 m 会是 `N` 的 public 成员（即 `B` 是 `N` 沿全 public 路径的基类）；
- ¶4.2 *R* 出现在 `N` 的直接成员或友元中，且 m 会是 `N` 的 private 或 protected 成员；
- ¶4.3 *R* 出现在派生自 `N` 的类 `P` 的直接成员或友元中，且 m 会是 `P` 的 private 或 protected 成员；
- ¶4.4 存在类 `S`：`B` 是 `S` 的在 *R* 处可访问的基类，且 `S` 是 `N` 的在 *R* 处可访问的基类（传递性）。

```cpp run title="accessible-base-transitive.cpp" ok
class B { public: int m; };
class S : private B { friend class N; };
class N : private S {
public:
    void f() {
        B* p = this;    // OK: 由 ¶4.4——在 N::f 中，S 是 N 的可访问基类（¶4.2），
                        //     B 是 S 的可访问基类（¶4.2 的友元情形：N 是 S 的友元）
        (void)p;
    }
};

int main() { N n; n.f(); }
```

### 隐式转换与指名类（¶5）

¶5：如果基类可访问，就可以把派生类指针隐式转换为该基类指针（[[conv.ptr]]、[[conv.mem]]）。注 2：因此类 `X` 的成员和友元可以把 `X*` 隐式转换为指向其 private/protected 直接基类的指针。

¶5 接着引入**指名类**（designating class），它是访问检查的参照系。指名成员 m 的表达式 E 的指名类是：

- ¶5.1 如果 E 是 *splice-expression*，是 m 直接所属的最内层类 {{c++26}}；
- ¶5.2 否则，是名字查找在其作用域中执行搜索并找到 m 的那个类。

注 3：指名类可以是显式的（`T::m` 中的 `T`），也可以是隐式的（`p->m` 中 `*p` 的类型，包括隐式的 `this->`）。`p->T::m` 中指名类是 `T`。

成员 m 作为 `N` 的成员被指名时，满足下列条件之一，它在程序点 *R* 处就是可访问的：

- ¶5.3 m 由 *splice-expression* 指名 {{c++26}}（无条件可访问，见下文）；或
- ¶5.4 m 作为 `N` 的成员是 public 的；或
- ¶5.5 m 作为 `N` 的成员是 private 的，且 *R* 出现在 `N` 的直接成员或友元中；或
- ¶5.6 m 作为 `N` 的成员是 protected 的，且 *R* 出现在 `N` 的直接成员或友元中，或者出现在派生自 `N` 的类 `P` 的成员中、且 m 作为 `P` 的成员是 public、private 或 protected 的（再附加 [[class.protected]] 的检查）；或
- ¶5.7 存在 `N` 的一个基类 `B`，它在 *R* 处可访问，且 m 作为 `B` 的成员被指名时在 *R* 处可访问。

¶5.7 是一条递归规则，它使友元关系可以沿着可访问的基类转换向上传递，见例 4：

```cpp run title="designating-class.cpp" ok
class B;
class A {
private:
    int i;
    friend void f(B*);
};
class B : public A { };

void f(B* p) {
    p->i = 1;       // OK: 指名类是 B；i 作为 B 的成员不可访问（它是 A 的 private 成员），
                    //     但由 ¶5.7：A 是 B 的可访问基类，且 i 作为 A 的成员在 f 中可访问（f 是 A 的友元）
}

int main() { B b; f(&b); }
```

### 对象表达式必须能转换到指名类（¶6）

¶6：用类成员访问运算符（含隐式的 `this->`）访问非静态数据成员或非静态成员函数时，左操作数（`.` 的情形视为取地址后的指针）必须能隐式转换为指向指名类的指针，否则 ill-formed。注 4：这是在成员作为指名类的成员可访问之外的额外要求。

为什么需要这条规则？访问非静态成员时，实际上要找到对象中的那个子对象，这隐含了一次派生类到基类的转换，而这次转换本身也必须合法。静态成员不需要子对象，所以不受此限：

```cpp title="object-expression-conversion.cpp" error
class A { public: int x; static int s; };
class B : private A { friend void g(); };
int A::s = 0;

void h() {
    B b;
    b.::A::x = 1;      // error: 指名类是 ::A，x 是 public 的（¶5.4 满足），
                       //        但 B* → A* 在 h 中不可访问（¶6 不满足）
    b.::A::s = 1;      // OK: 静态成员，¶6 不适用
}
void g() {
    B b;
    b.::A::x = 1;      // OK: g 是 B 的友元，B* → A* 可访问
}
```

---

## 虚函数的访问（[class.access.virt]）

¶1：虚函数的访问规则由它自己的声明决定，不受后来覆盖它的函数的访问规则影响。¶2：访问在调用点检查，依据的是用来指代对象的表达式的类型（即静态类型）；函数实际所在的类中的访问权一般是未知的。

```cpp title="virtual-access.cpp" error
class B {
public:
    virtual int f();
};
class D : public B {
private:
    int f() override;
};

void f() {
    D d;
    B* pb = &d;
    D* pd = &d;
    pb->f();          // OK: B::f 是 public 的；运行时调用 D::f（尽管它是 private 的）
    pd->f();          // error: D::f 是 private 的
}
```

这与访问控制针对名字的原则一脉相承：`pb->f()` 指名的是 `B::f`，访问检查到此为止，动态分派到哪里与访问无关（[[class.virtual]] 脚注 87 也说明，判断覆盖时不考虑访问）。

**非虚接口**（Non-Virtual Interface，NVI）惯用法正是建立在这条规则上的：public 的非虚函数调用 private 的虚函数，派生类覆盖这个 private 虚函数来定制行为，而外部只能通过基类的 public 接口进入：

```cpp run title="nvi.cpp" ok
#include <cstdio>

class Widget {
public:
    void draw() { prepare(); do_draw(); }       // 非虚的公共接口：可以统一加前置/后置逻辑
    virtual ~Widget() = default;
private:
    void prepare() { std::puts("prepare"); }
    virtual void do_draw() { std::puts("Widget"); }   // private 虚函数：定制点
};

class Button : public Widget {
    void do_draw() override { std::puts("Button"); } // 覆盖 private 虚函数：完全合法
};

int main() {
    Button b;
    Widget& w = b;
    w.draw();       // prepare / Button
}
```

## 多条路径：取最宽（[class.paths]）

¶1：如果一个声明可以通过多重继承图中的多条路径到达，访问权取给出最多访问权的那条路径。

```cpp run title="multiple-paths.cpp" ok
class W { public: void f() {} };
class A : private virtual W { };
class B : public virtual W { };
class C : public A, public B {
public:
    void g() { W::f(); }     // OK: 经 B 的 public 路径可以访问
};

int main() { C c; c.g(); c.f(); }   // c.f() 在外部同样 OK
```

只有虚继承才会出现同一个子对象有多条路径的情况（非虚继承下每条路径对应不同的子对象，那是二义性问题，不是访问问题）。

## 嵌套类（[class.access.nest]）

¶1：嵌套类是成员，因而与其他成员拥有相同的访问权（从 C++11 起可以访问外围类的 private 成员；C++98 中嵌套类没有这种特权）。反过来，外围类的成员对嵌套类的成员没有特殊访问权，必须遵守普通的访问规则：

```cpp title="nested-class-access.cpp" error
class E {
    int x;
    class B { };

    class I {
        B b;                        // OK: E::I 可以访问 E::B
        int y;
        void f(E* p, int i) {
            p->x = i;               // OK: E::I 可以访问 E::x
        }
    };

    int g(I* p) {
        return p->y;                // error: I::y 是 I 的 private 成员
    }
};
```

之所以不对称，是因为嵌套类是外围类的成员，属于外围类实现的一部分；而外围类只是嵌套类的使用者之一，嵌套类有它自己的封装。需要反向访问时，在嵌套类中把外围类声明为友元。

---

## 合法的后门

### 显式实例化不检查访问

[[temp.spec.general#6]]：在显式实例化或显式特化的声明中，常规的访问检查规则不适用于其中的名字（函数体、默认实参、*base-clause*、*member-specification*、枚举列表、静态数据成员或变量模板的初始化器中的名字除外）。注 1 明确指出，模板实参和函数声明符中使用的名字可以是通常不可访问的私有类型或对象。

为什么要有这条规则？显式实例化/特化常常需要以私有类型为模板实参，例如为类的私有嵌套类型特化一个 trait，或者在库实现中显式实例化以私有类型参数化的模板。如果在这里检查访问，这些声明就都得是友元，非常不便。

但它带来一个著名的副作用：可以合法地取得任何私有成员的成员指针，并通过友元函数把它带到类外：

```cpp run title="private-access-via-explicit-instantiation.cpp" ok
#include <cstdio>

class Safe {
    int secret = 42;
    void hidden() const { std::puts("hidden called"); }
};

// 用标签类型区分要偷的成员；get 只在类内定义，靠 ADL 找到
struct SecretTag { friend constexpr auto get(SecretTag); };
struct HiddenTag { friend constexpr auto get(HiddenTag); };

template<class Tag, auto M>
struct Thief {
    friend constexpr auto get(Tag) { return M; }   // 定义上面声明的友元函数，返回成员指针
};

// 显式实例化：模板实参 &Safe::secret 中的名字不做访问检查
template struct Thief<SecretTag, &Safe::secret>;
template struct Thief<HiddenTag, &Safe::hidden>;

int main() {
    Safe s;
    std::printf("%d\n", s.*get(SecretTag{}));   // 42
    (s.*get(HiddenTag{}))();                     // hidden called
}
```

拆解它的合法性：

1. `template struct Thief<SecretTag, &Safe::secret>;` 是显式实例化定义，其模板实参中的 `&Safe::secret` 不受访问检查（[temp.spec.general]/6）；
2. 实例化 `Thief<SecretTag, &Safe::secret>` 时，其中的友元函数 `get(SecretTag)` 随之得到定义，这是一个返回成员指针值的普通非模板函数；
3. `main` 中调用 `get(SecretTag{})`，ADL 在关联类 `SecretTag` 中找到它（[[basic.lookup.argdep]]）；
4. 使用成员指针 `s.*p` 不涉及指名 `secret`，而访问控制只管名字。

每一步都是良构的。这是规则上的一个奇特之处，而不是工程实践：它依赖于友元函数只能定义一次（每个标签只能实例化一次 `Thief`），并且严重破坏封装。单元测试和调试工具偶尔会用到它。

### C++26：splice 表达式不受访问控制 {{c++26}}

有了静态反射，这件事就直截了当了：[class.access.base]/5.3 规定，由 *splice-expression* 指名的成员总是可访问的。配合 `std::meta::access_context::unchecked()` 列出全部成员（[[meta.reflection.access.context]]），可以直接写 `obj.[: member :]`。

```cpp
#include <meta>

class Safe { int secret = 42; };

consteval std::meta::info secret_member() {
    return std::meta::nonstatic_data_members_of(
        ^^Safe, std::meta::access_context::unchecked())[0];
}

int peek(Safe& s) { return s.[: secret_member() :]; }   // OK: splice 指名不做访问检查
```

（本机 Clang 23 尚不支持静态反射，上例未经编译验证。）设计上的考虑是：反射查询本身已经带有访问语境参数（`access_context::current()` 只返回当前语境可访问的成员），是否尊重访问控制的决定前移到了查询阶段，由程序员显式选择；splice 只是使用已经拿到的反射，不再重复检查。

## 实现视角

!!! impl
    - 访问控制几乎完全是编译期的概念，但会间接影响布局：Itanium ABI 依据 C++03 意义上的 POD（"POD for the purpose of layout"）判断派生类能否复用基类的尾部填充，而 C++03 的 POD 要求没有 private/protected 的非静态数据成员。因此把一个数据成员从 public 改成 private，可能改变派生类的布局与大小。
    - MSVC 把成员的访问权编码进修饰名（mangled name），所以在 MSVC 上把 `private` 改成 `public` 会导致链接时找不到符号，`#define private public` 这种技巧在 MSVC 上会造成链接错误。Itanium ABI 的修饰名不含访问权。
    - 编译器实现重载决议之后再检查访问的方式是：查找时记录每个找到的声明所经由的路径与访问权，选定之后再检查；对模板中依赖的访问检查，Clang 会推迟到实例化时进行。

## 历史与演进

!!! history
    - **C++98**：嵌套类没有访问外围类私有成员的特权（需要友元）；后经核心问题修订，C++11 起嵌套类作为成员拥有成员的访问权。
    - **C++11**：访问检查成为 SFINAE 的一部分；using 声明的访问规则澄清。
    - **C++23**：名字查找章节（[[basic.lookup]]）重写后，指名类定义为在其作用域中执行搜索并找到该成员的类。
    - **C++26** {{c++26}}：*splice-expression* 的指名类定义为成员直接所属的类，且 splice 指名的成员无条件可访问；反射查询以 `access_context` 显式控制可访问性。

## 陷阱

!!! pitfall
    1. **以为重载决议会跳过私有成员**：不会。私有重载被选中后才报错，`sp->f(2.0)` 是错误，而不是改为调用 `f(int)`。
    2. **以为 private 能保护数据**：它只保护名字。引用、指针、`auto`、模板、显式实例化、C++26 splice 都能触及实体。
    3. **注入类名在私有继承下不可访问**：在 `class C : public B` 中（`B : private A`）写 `A` 会失败，应写 `::A`。
    4. **以为覆盖时把虚函数改成 private 就能隐藏它**：通过基类指针照样能调用。
    5. **默认继承方式**：`class D : B` 是 private 继承；从 `struct` 改成 `class` 会悄悄改变继承方式和成员默认访问权。
    6. **C 风格转换绕过私有继承**：即使 `B` 是私有基类，`(B*)pd` 仍能编译通过（而且做的是正确的指针调整），`static_cast` 则会报错。

## 思考题

!!! question "思考题 1"
    下面的调用选中哪个函数？程序是否良构？
    ```cpp
    class X {
    public:
        void f(long);
    private:
        void f(int);
        friend void call(X&);
    };
    void call(X& x) { x.f(1); }
    void other(X& x) { x.f(1); }
    ```

<details markdown="1">
<summary>答案</summary>

两处调用都选中 `f(int)`（精确匹配）。在 `call` 中，`call` 是 `X` 的友元，可以访问 `f(int)`，良构。在 `other` 中，重载决议同样选中 `f(int)`，随后访问检查失败，`other` ill-formed。编译器不会因为 `f(int)` 不可访问就改选 `f(long)`（¶4、¶5）。
</details>

!!! question "思考题 2"
    `struct B { int m; }; struct D : private B { using B::m; }; struct E : D {};` 中，`E e; e.m = 1;` 良构吗？`B* p = &e;` 呢？

<details markdown="1">
<summary>答案</summary>

`e.m = 1;` 良构：名字查找在 `E` 中找到的是经 `D` 继承来的 using 声明 `D::m`（作为 `D` 的 public 成员，因为 using 声明位于 `struct D` 的默认 public 区），访问检查施加于 using 声明本身（[class.access.general]/4）。¶6 还要求 `E*` 能转换为指向指名类的指针；指名类是 `E`（查找在 `E` 的作用域中进行），这个转换显然成立。`B* p = &e;` ill-formed：`B` 是 `D` 的私有基类，在外部不是 `E` 的可访问基类（[class.access.base]/4）。using 声明只改变了名字 `m` 的访问权，不改变基类的可访问性。
</details>

!!! question "思考题 3"
    默认实参的访问在声明处检查（¶8），默认模板实参的访问在它出现的语境中检查（¶9）。这两条规则是不是同一个原则？

<details markdown="1">
<summary>答案</summary>

是同一个原则：**谁写下了这个名字，就按谁的权限检查**。默认实参写在函数声明里，按该声明（如成员函数、友元）的权限检查；默认模板实参写在模板声明里，按模板声明所在的语境检查。在 [class.access.general] 的例 5 中，`D` 的模板形参列表位于命名空间作用域，不在 `D` 的类作用域中，所以即使 `D` 最终派生自 `C<B>`，默认实参 `typename U::TT` 也享受不到派生类对 protected 成员的访问权。两者都不在使用处检查，因为使用者并没有写下这个名字。
</details>

## 小结

!!! summary
    | 规则 | 要点 |
    |---|---|
    | 本质 | 控制名字能否被指名；不控制实体能否被使用 |
    | 时机 | 名字查找、重载决议之后；不改变程序含义，只导致 ill-formed |
    | 语境 | 按名字所在声明的实体（成员、友元）判断；类外成员定义的返回类型也算在内 |
    | 默认实参 | 在声明处检查；默认模板实参在出现的语境检查 |
    | 继承方式 | 决定基类成员在派生类中的访问权上限；`class` 默认 private，`struct` 默认 public |
    | 可访问基类 | 决定派生到基类的隐式转换能否进行；可传递 |
    | 指名类 | 访问检查的参照系；非静态成员还要求对象表达式能转换到指名类 |
    | 虚函数 | 按静态类型中的声明检查访问；覆盖者的访问权无关 |
    | 多条路径 | 取最宽的 |
    | 嵌套类 | 是成员，可访问外围类；反之不行 |
    | 后门 | 显式实例化/特化中不检查访问；C++26 splice 不检查访问 |
