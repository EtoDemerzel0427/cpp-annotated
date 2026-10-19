---
title: 成员访问控制
summary: public、protected、private 控制的是在哪里可以指名一个成员；访问检查在名字查找和重载决议之后进行；继承方式、可访问基类和指名类怎样决定一次访问是否合法；虚函数、多重路径和嵌套类的访问规则。
status: done
covers: class.access.general, class.access.spec, class.access.base, class.access.virt, class.paths, class.access.nest
related: class.friend, class.protected, class.member.lookup, conv.ptr, namespace.udecl, temp.spec.general, temp.deduct.general, expr.ref, class.local
tags: 类, 访问控制, 继承, 友元
updated: 2026-10-19
---

!!! tldr
    - 访问控制管的是在某个位置能不能写出（指名）一个成员的名字，不管实体本身能不能被使用；通过引用、指针、`auto`、模板都能用到私有实体。
    - 编译器先不考虑访问权完成名字查找和重载决议，再检查选中的东西是否可访问；不可访问就报错，不会改选另一个重载。
    - 继承方式给基类成员在派生类中的访问权设了上限，也决定派生类指针能否隐式转换为基类指针。
    - 虚函数按调用表达式的静态类型检查访问：覆盖函数是 private 的，照样能经由基类调用，非虚接口惯用法就建立在这一点上。
    - 显式实例化中的名字不做访问检查，C++26 中由 splice 指名的成员也不检查，这是两条合法的后门。

```cpp run title="names-not-entities.cpp" ok
class Vault {
    int secret = 42;
public:
    int& door() { return secret; }   // 交出一个引用
};
int main() {
    Vault v;
    int& r = v.door();   // OK: 没有在类外写出 secret 这个名字
    r = 7;               // OK: 修改的是实体，访问控制不管
    // v.secret = 7;     // error: secret 是 private 的
}
```

`secret` 是私有成员，但 `main` 照样改了它的值。访问控制检查的是名字：它规定在程序的哪些位置可以**指名**（name）一个成员，也就是写出一个指代它的名字或表达式。拿到引用之后再使用实体，与访问控制无关。

所以访问控制不是安全机制。它防止的是无意中依赖实现细节的代码，而不是有意的绕过。本页覆盖第 11.8 节中除友元（[[class.friend]]）和 protected 附加规则（[[class.protected]]）以外的全部内容。

## 三种访问权（[class.access.general] ¶1–¶3）

¶1 类的成员可以是：

- ¶1.1 **private**：只有声明它的类的成员和友元能指名它；
- ¶1.2 **protected**：除了上面两者，派生自该类的类及其友元也能指名它，附加限制见 [[class.protected]]；
- ¶1.3 **public**：任何地方都能指名它。

注 1 说明，构造函数和析构函数虽然没有名字，表达式仍然可以指名它们（[[basic.def.odr]]），所以它们同样受访问控制。私有构造函数能阻止外部创建对象，靠的就是这一点。

¶2 类的成员可以访问该类有权访问的一切成员。成员函数里的局部类，可以访问该成员函数本身能访问的成员。脚注 89 总结说，访问权对嵌套类和局部类是可传递、可累积的：

```cpp run title="nested-access.cpp" ok
class Outer {
    int x = 1;
    class Inner {               // 嵌套类是成员，有成员的访问权
        int peek(Outer& o) { return o.x; }
        struct Deeper {         // 再嵌套一层也一样
            int peek(Outer& o) { return o.x; }
        };
    };
public:
    int f() {
        struct Local {          // 局部类：得到 f 的访问权
            static int get(Outer& o) { return o.x; }
        };
        return Local::get(*this);
    }
};
int main() { Outer o; return o.f() == 1 ? 0 : 1; }
```

¶3 用 `class` 定义的类，成员默认是 private 的；用 `struct` 或 `union` 定义的，默认是 public 的。`class` 和 `struct` 在语言上只有这一处和默认继承方式（见下文）两处差别。

## 访问说明符（[class.access.spec]）

¶1–¶2 访问说明符 `public:`、`protected:`、`private:` 对其后的成员生效，直到类结束或遇到下一个访问说明符。它们可以出现任意多次，顺序不限。

¶3 在类内重声明一个成员时，访问权必须与首次声明相同：

```cpp title="redeclare-access.cpp" error
struct S {
    class A;
    enum E : int;
private:
    class A { };            // error: 不能改变访问权
    enum E : int { e0 };    // error: 不能改变访问权
};
```

¶4 的注提醒一个容易踩的坑。在派生类里查找基类的名字，找到的是基类的[[g:injected-class-name|注入类名]]，即类名在类自身作用域里的那份绑定。它作为基类的成员被继承下来，访问权随继承方式变化，可能比全局作用域里的类名更难访问：

```cpp title="injected-class-name-access.cpp" error
class A { };
class B : private A { };
class C : public B {
    A* p;      // error: 找到的是经 private 继承而来的注入类名
    ::A* q;    // OK: 全局作用域中的 A
};
```

## 先确定含义，再检查访问（¶4–¶5）

```cpp title="access-after-overload.cpp" error
struct S {
    void f(int);
private:
    void f(double);
};
void g(S* sp) {
    sp->f(2);      // OK: 选中 public 的 f(int)
    sp->f(2.0);    // error: 选中 private 的 f(double)
}
```

第二个调用里，私有的 `f(double)` 没有从候选中消失。重载决议选中了它（精确匹配），随后访问检查失败，程序非良构。编译器不会退而选 `f(int)`。

!!! std
    The interpretation of a given construct is established without regard to access control. If the interpretation established makes use of inaccessible members or base classes, the construct is ill-formed.

¶5 一个构造的含义在不考虑访问控制的情况下确定；如果确定下来的含义用到了不可访问的成员或基类，这个构造非良构。注 4 说得更具体：访问控制不会阻止名字查找找到成员，也不会阻止编译器考虑到基类的隐式转换。¶4 对重载集单独说了一句：访问控制只施加于重载决议选中的那个函数。

为什么这样设计？如果访问权参与重载决议，同一个调用在类内和类外会选中不同的函数。把一段代码从成员函数挪到自由函数里，或者把一个成员从 public 改成 private，都会悄悄改变别处的重载选择。C++ 的选择是让含义保持稳定，出错就报错。

### 检查的是被指名的那个声明

¶4 访问控制统一适用于声明和表达式。注 2 指出，它也适用于友元声明（[[class.friend#8]]）和 using 声明（[[namespace.udecl]]）所指名的成员。指名一个 using 声明引入的名字时，检查的是 using 声明本身的访问权，而不是它所引入的那个声明。

注 3 把同一原则用在类型别名上：只检查别名声明本身，不检查底层实体。

```cpp title="typedef-access.cpp" error
class A {
    class B { };
public:
    typedef B BB;
};
void f() {
    A::BB x;           // OK: A::BB 是 public 的
    auto y = A::BB{};  // OK
    decltype(y) z;     // OK: 根本没有写出 A::B
    A::B w;            // error: A::B 是 private 的
}
```

### 访问检查与 SFINAE

模板实参替换时，访问检查是替换的一部分（[[temp.deduct.general#8]] 的注 5）。在替换中指名不可访问的成员只是替换失败，不是硬错误，所以可以写 trait 检测某个成员能否访问：

```cpp run title="sfinae-access.cpp" ok
#include <type_traits>
#include <utility>
template<class T, class = void>
struct has_v : std::false_type {};
template<class T>
struct has_v<T, std::void_t<decltype(std::declval<T&>().v)>>
    : std::true_type {};

class Hidden { int v; };
struct Open  { int v; };
static_assert(!has_v<Hidden>::value);   // 不可访问：替换失败
static_assert(has_v<Open>::value);
int main() {}
```

## 在谁的声明里指名（¶6–¶9）

¶6 访问控制管的是从某个实体的声明中指名类成员的能力。这个声明包括出现在被声明实体名字之前的部分；实体是类时，还包括写在类外的该类成员的定义。注 5 补充，对构造函数、转换函数、析构函数的隐式引用也按这个语境检查。

这解决了一个解析顺序的问题：

```cpp title="access-context.cpp" ok
class A {
    typedef int I;          // private
    I f();
    friend I g(I);
    static I x;
    template<int> struct Q;
    template<int> friend struct R;
protected:
    struct B { };
};
A::I A::f() { return 0; }   // OK: 返回类型属于成员 A::f 的声明
A::I g(A::I p = A::x);      // OK: g 是友元，默认实参也算
A::I g(A::I) { return 0; }
A::I A::x = 0;              // OK: 静态成员的定义
template<A::I> struct A::Q { };
template<A::I> struct R { };  // OK: R 是友元
struct D : A::B, A { };     // OK: D 派生自 A（Clang 误报）
```

¶7 的例 4 与此相同（当前草案的版本还给 `f` 和 `g` 加了契约断言，这里省去）。解析 `A::I A::f()` 中的 `A::I` 时，编译器还不知道后面跟的是 `A` 的成员函数，所以对第一个 `A::I` 的访问检查必须推迟。最后一行同理：解析 `A::B` 时还没看到 `, A`，不知道 `D` 派生自 `A`，对 *base-specifier* 的检查要推迟到看完整个基类列表。

!!! impl "Clang 的偏差"
    截至写作时，Clang 23 以 `'B' is a protected member of 'A'` 拒绝最后一行，它没有把 *base-specifier* 中的访问检查推迟到列表结束。其余各行 Clang 都接受。按标准，整个例子是良构的。

¶8 默认实参的访问在声明处检查，不在使用处检查。默认实参是声明的一部分，由写声明的人负责；调用者只是接受默认值。函数模板和类模板成员函数的默认实参按 [[temp.inst]] 的规则检查。

```cpp run title="default-arg-access.cpp" ok
class C {
    static int k;              // private
public:
    static void h(int = k) {}  // OK: 在 C 的成员声明里指名 k
};
int C::k = 0;
int main() { C::h(); }         // OK: 调用处不重新检查
```

¶9 默认模板实参的访问在它出现的语境中检查，不在使用处检查：

```cpp title="default-template-arg-access.cpp" error
class B { };
template<class T> class C {
protected:
    typedef T TT;
};
template<class U, class V = typename U::TT>  // 在命名空间作用域检查
class D : public U { };

D<C<B>>* d;   // error: C<B>::TT 是 protected 的
```

`D` 最终派生自 `C<B>`，但默认实参写在 `D` 的模板形参列表里，那里是命名空间作用域，不在 `D` 的类作用域内，享受不到派生类对 protected 成员的访问权。¶8 和 ¶9 是同一个原则：谁写下了这个名字，就按谁的权限检查。

## 继承与基类的可访问性（[class.access.base]）

### 继承方式（¶1–¶2）

¶1 继承方式决定基类成员在派生类中具有什么访问权：

| 基类中的成员 | `public` 继承 | `protected` 继承 | `private` 继承 |
|---|---|---|---|
| public | public | protected | private |
| protected | protected | protected | private |
| private | 不可访问 | 不可访问 | 不可访问 |

脚注 90 强调，基类的 private 成员对派生类始终不可访问，除非基类用友元声明明确授权。

¶2 没有写访问说明符时，用 `struct` 定义的派生类默认 public 继承，用 `class` 定义的默认 private 继承。这由派生类的类关键字决定，与基类用哪个关键字定义无关。

### 作为继承成员不可访问，直接指名却可以（¶3）

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
    mi = 3;                  // error: mi 在 D 中是 private 的
    si = 3;                  // error: 静态成员也一样
    ::B b;
    b.mi = 3;                // OK: 直接经 ::B 指名
    b.si = 3;                // OK
    ::B::si = 3;             // OK
    ::B* bp1 = this;         // error: B 是私有基类
    ::B* bp2 = (::B*)this;   // OK: C 风格转换
    bp2->mi = 3;             // OK: 经 B* 访问
}
```

这是 ¶3 注中的例子。`mi` 经 `DD → D → B` 的路径指名时不可访问，因为它在 `D` 里是 private 的；但直接通过一个 `::B` 对象指名就没问题。

同一个注还指出，到不可访问基类的指针转换，隐式进行是非良构的，用显式转换却可以。C 风格转换可以无视基类的可访问性（[[expr.cast]]），而且做的是正确的指针调整。这是它能做而 `static_cast` 做不到的少数几件事之一。

### 可访问基类（¶4–¶5）

¶4 定义了基类 `B` 在程序点 *R* 处是 `N` 的**可访问基类**（accessible base class）的条件。假想 `B` 有一个 public 成员 m，满足下列任一条即可：

- ¶4.1 m 会是 `N` 的 public 成员，即从 `N` 到 `B` 一路都是 public 继承；
- ¶4.2 *R* 位于 `N` 的直接成员或友元中，且 m 会是 `N` 的 private 或 protected 成员；
- ¶4.3 *R* 位于派生自 `N` 的类 `P` 的直接成员或友元中，且 m 会是 `P` 的 private 或 protected 成员；
- ¶4.4 有一个类 `S`，`B` 是 `S` 在 *R* 处的可访问基类，`S` 又是 `N` 在 *R* 处的可访问基类。

```cpp run title="accessible-base-transitive.cpp" ok
class B { public: int m; };
class S : private B { friend class N; };
class N : private S {
public:
    void f() {
        B* p = this;   // OK: 由 ¶4.4
        (void)p;
    }
};
int main() { N n; n.f(); }
```

在 `N::f` 中，`S` 是 `N` 的可访问基类（¶4.2，`f` 是 `N` 的成员）；`B` 是 `S` 的可访问基类（¶4.2，`N` 是 `S` 的友元）。按 ¶4.4 传递，`B` 是 `N` 的可访问基类。

¶5 第一句说明这个定义的用途：基类可访问时，派生类指针可以隐式转换为该基类的指针（[[conv.ptr]]、[[conv.mem]]）。所以类 `X` 的成员和友元可以把 `X*` 隐式转换为指向它的 private 或 protected 直接基类的指针。

### 指名类（¶5）

一个成员是否可访问，要看它是作为哪个类的成员被指名的。¶5 把这个类叫做**指名类**（[[g:designating-class|designating class]]）。表达式 E 指名成员 m 时，它的指名类是：

- ¶5.1 如果 E 是 *splice-expression* {{c++26}}，是 m 直接所属的最内层的类；
- ¶5.2 否则，是名字查找在其作用域中执行搜索并找到 m 的那个类。

注 3 举例：`T::m` 中指名类是 `T`；`p->m` 中是 `*p` 的类，隐式的 `this->m` 也一样；`p->T::m` 中是 `T`。

成员 m 作为类 `N` 的成员被指名时，在 *R* 处可访问的条件是下列之一：

- ¶5.3 m 由 *splice-expression* 指名 {{c++26}}；
- ¶5.4 m 作为 `N` 的成员是 public 的；
- ¶5.5 m 作为 `N` 的成员是 private 的，且 *R* 位于 `N` 的直接成员或友元中；
- ¶5.6 m 作为 `N` 的成员是 protected 的，且 *R* 位于 `N` 的直接成员或友元中，或者位于派生自 `N` 的类 `P` 的成员中、而 m 作为 `P` 的成员可访问（还要通过 [[class.protected]] 的附加检查）；
- ¶5.7 `N` 有一个在 *R* 处可访问的基类 `B`，且 m 作为 `B` 的成员被指名时在 *R* 处可访问。

¶5.7 是递归的，它让对基类成员的授权能经由可访问的派生到基类转换生效：

```cpp run title="designating-class.cpp" ok
class B;
class A {
private:
    int i;
    friend void f(B*);
};
class B : public A { };
void f(B* p) {
    p->i = 1;   // OK
}
int main() { B b; f(&b); }
```

`p->i` 的指名类是 `B`。`i` 作为 `B` 的成员不可访问，因为它是 `A` 的私有成员，而 `f` 不是 `B` 的友元。但 `A` 是 `B` 的可访问基类，`i` 作为 `A` 的成员在 `f` 中可访问（`f` 是 `A` 的友元），所以按 ¶5.7 成立。

### 对象表达式要能转换到指名类（¶6）

¶6 用成员访问运算符（包括隐式的 `this->`）访问非静态数据成员或非静态成员函数时，左操作数（`.` 的情形看作取地址后的指针）必须能隐式转换为指向指名类的指针。注 4 强调，这是在成员本身可访问之外的又一个要求。

访问非静态成员要先在对象里找到那个子对象，这隐含一次派生到基类的转换，这次转换本身也必须合法。静态成员不属于任何子对象，所以不受这条限制：

```cpp title="object-expression-conversion.cpp" error
class A { public: int x; static int s; };
class B : private A { friend void g(); };
int A::s = 0;
void h() {
    B b;
    b.::A::x = 1;   // error: x 可访问，但 B* → A* 不可访问
    b.::A::s = 1;   // OK: 静态成员
}
void g() {
    B b;
    b.::A::x = 1;   // OK: g 是 B 的友元
}
```

## 虚函数的访问（[class.access.virt]）

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
    pb->f();   // OK: B::f 是 public 的，运行时调用 D::f
    pd->f();   // error: D::f 是 private 的
}
```

¶1 虚函数的访问规则由它自己的声明决定，不受后来覆盖它的函数影响。¶2 访问在调用点检查，依据的是指代对象的那个表达式的类型，即静态类型。函数实际定义在哪个类、在那里是什么访问权，一般是不知道的。

这与访问控制只管名字的原则一致：`pb->f()` 指名的是 `B::f`，检查到此为止，运行时分派到哪里与访问无关。判断覆盖时也不考虑访问权（[[class.virtual]] 脚注 87）。

**非虚接口**（Non-Virtual Interface，NVI）惯用法就建立在这条规则上：public 的非虚函数调用 private 的虚函数，派生类覆盖这个 private 虚函数来定制行为，外部只能从基类的 public 接口进入。

```cpp run title="nvi.cpp" ok
#include <cstdio>
class Widget {
public:
    void draw() { prepare(); do_draw(); }   // 统一的前置逻辑
    virtual ~Widget() = default;
private:
    void prepare() { std::puts("prepare"); }
    virtual void do_draw() { std::puts("Widget"); }
};
class Button : public Widget {
    void do_draw() override { std::puts("Button"); }
};
int main() {
    Button b;
    Widget& w = b;
    w.draw();   // prepare / Button
}
```

## 多条路径取最宽（[class.paths]）

```cpp run title="multiple-paths.cpp" ok
class W { public: void f() {} };
class A : private virtual W { };
class B : public virtual W { };
class C : public A, public B {
public:
    void g() { W::f(); }   // OK: 经 B 的 public 路径
};
int main() { C c; c.g(); c.f(); }
```

¶1 如果一个声明可以经由继承图中的多条路径到达，访问权取给出最多访问权的那条路径。

只有虚继承才会让同一个子对象有多条路径。非虚继承下每条路径对应不同的子对象，那是二义性问题，不是访问问题。

## 嵌套类（[class.access.nest]）

```cpp title="nested-class-access.cpp" error
class E {
    int x;
    class B { };
    class I {
        B b;                  // OK: E::I 可以访问 E::B
        int y;
        void f(E* p, int i) {
            p->x = i;         // OK: E::I 可以访问 E::x
        }
    };
    int g(I* p) {
        return p->y;          // error: I::y 是 I 的私有成员
    }
};
```

¶1 嵌套类是成员，因而和其他成员有相同的访问权。反过来，外围类的成员对嵌套类的成员没有特殊访问权，要遵守普通的访问规则。

不对称的原因是：嵌套类是外围类实现的一部分，而外围类只是嵌套类的一个使用者，嵌套类有自己的封装。需要反向访问时，在嵌套类里把外围类声明为友元。

## 合法的后门

### 显式实例化不检查访问

[[temp.spec.general#6]] 规定，显式实例化和显式特化的声明中，普通的访问检查规则不适用于其中的名字；函数体、默认实参、*base-clause*、成员说明、枚举符列表、静态数据成员或变量模板的初始化器中的名字除外。它的注说明，模板实参和函数声明符里可以用平常不可访问的私有类型或对象。

这条规则的本意是方便：为类的私有嵌套类型特化一个 trait，或者在库实现里显式实例化以私有类型为参数的模板，都不必再声明友元。但它有一个著名的副作用，可以合法地取得任何私有成员的成员指针：

```cpp run title="private-access-via-explicit-instantiation.cpp" ok
#include <cstdio>
class Safe {
    int secret = 42;
    void hidden() const { std::puts("hidden called"); }
};
// 每个标签对应一个要取的成员；get 只能经 ADL 找到
struct SecretTag { friend constexpr auto get(SecretTag); };
struct HiddenTag { friend constexpr auto get(HiddenTag); };

template<class Tag, auto M>
struct Thief {
    friend constexpr auto get(Tag) { return M; }
};
// 显式实例化：模板实参中的 &Safe::secret 不做访问检查
template struct Thief<SecretTag, &Safe::secret>;
template struct Thief<HiddenTag, &Safe::hidden>;

int main() {
    Safe s;
    std::printf("%d\n", s.*get(SecretTag{}));  // 42
    (s.*get(HiddenTag{}))();                    // hidden called
}
```

每一步都是良构的：

1. 显式实例化定义的模板实参 `&Safe::secret` 不受访问检查。
2. 实例化 `Thief<SecretTag, &Safe::secret>` 时，友元函数 `get(SecretTag)` 随之得到定义，它返回那个成员指针。
3. `main` 中的 `get(SecretTag{})` 经实参依赖查找（[[basic.lookup.argdep]]）在关联类 `SecretTag` 中找到它。
4. `s.*p` 使用的是成员指针，没有指名 `secret`。

这是规则上的一个怪现象，不是工程实践。单元测试和调试工具偶尔会用到它。

### splice 表达式不检查访问 {{c++26}}

¶5.3 规定，由 *splice-expression* 指名的成员总是可访问的。配合 `std::meta::access_context::unchecked()` 列出全部成员（[[meta.reflection.access.context]]），就可以直接写 `obj.[: member :]`：

```cpp
#include <meta>
class Safe { int secret = 42; };

consteval std::meta::info secret_member() {
    return std::meta::nonstatic_data_members_of(
        ^^Safe, std::meta::access_context::unchecked())[0];
}
int peek(Safe& s) { return s.[: secret_member() :]; }  // OK
```

本机 Clang 23 还不支持静态反射，这段代码没有经过编译验证。设计上的考虑是：反射查询本身带有访问语境参数，`access_context::current()` 只返回当前语境能访问的成员。是否尊重访问控制，在查询时就由程序员明确选择；splice 只是使用已经拿到的反射，不再重复检查。

## 实现视角

!!! impl
    - 访问控制基本是编译期的概念，但会间接影响布局。Itanium ABI 依据 C++03 意义上的 POD（POD for the purpose of layout）判断派生类能否复用基类尾部的填充，而 C++03 的 POD 要求没有 private 或 protected 的非静态数据成员。所以把一个数据成员从 public 改成 private，可能改变派生类的布局和大小。
    - MSVC 把成员的访问权编进修饰名，Itanium ABI 的修饰名则不含访问权。所以在 MSVC 上，用 `#define private public` 之类的手法编译一部分代码，会导致链接时找不到符号。

## 历史与演进

!!! history
    - C++98 中嵌套类没有访问外围类私有成员的特权，要靠友元。[[CWG45]] 修正了这一点，C++11 起嵌套类作为成员拥有成员的访问权。
    - C++11 规定访问检查是模板实参替换的一部分，不可访问成员导致替换失败而不是硬错误（[[CWG1170]]）。
    - C++26 {{c++26}} 为 *splice-expression* 规定了指名类，并规定由它指名的成员无条件可访问；反射查询用 `access_context` 明确控制可访问性。

## 常见误解

!!! pitfall "重载决议会跳过私有的重载"
    不会。私有重载被选中之后才报错，`sp->f(2.0)` 是错误，而不是改为调用 `f(int)`。

!!! pitfall "private 能保护数据"
    它只限制名字。引用、指针、`auto`、`decltype`、模板、显式实例化、C++26 的 splice 都能触及私有实体。

!!! pitfall "覆盖时把虚函数改成 private 就能藏起来"
    通过基类的指针或引用照样能调用，访问检查看的是基类中的声明。

!!! pitfall "把 struct 改成 class 只影响成员的默认访问权"
    默认继承方式也会从 public 变成 private：`class D : B` 是 private 继承。

## 思考题

!!! question "思考题 1"
    下面两处调用分别选中哪个函数？程序是否良构？
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

两处都选中 `f(int)`（精确匹配）。`call` 是 `X` 的友元，可以访问 `f(int)`，良构。`other` 中重载决议同样选中 `f(int)`，随后访问检查失败，`other` 非良构。编译器不会因为 `f(int)` 不可访问就改选 `f(long)`（[class.access.general] ¶4、¶5）。
</details>

!!! question "思考题 2"
    `struct B { int m; }; struct D : private B { using B::m; }; struct E : D {};` 中，`E e; e.m = 1;` 良构吗？`B* p = &e;` 呢？

<details markdown="1">
<summary>答案</summary>

`e.m = 1;` 良构。查找在 `E` 中找到经 `D` 继承来的 using 声明，它位于 `struct D` 默认的 public 区域，在 `E` 中仍是 public 的；访问检查施加于 using 声明本身（[class.access.general] ¶4）。指名类是 `E`，¶6 要求的 `E*` 到 `E*` 的转换显然成立。

`B* p = &e;` 非良构：`B` 是 `D` 的私有基类，在类外不是 `E` 的可访问基类（[class.access.base] ¶4）。using 声明只改变了名字 `m` 的访问权，不改变基类的可访问性。Clang 报告 `cannot cast 'E' to its private base class 'B'`。
</details>
