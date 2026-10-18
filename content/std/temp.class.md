---
title: 类模板
summary: 类模板定义一族类型；成员（函数、成员类、静态数据成员、枚举）的类外定义必须带等价的 template-head 并按原顺序写出模板实参列表；成员函数的模板实参由对象类型决定；推导指引的语法、查找方式与限制；类模板静态成员的定义与未知界数组
status: done
covers: temp.class.general, temp.mem.func, temp.deduct.guide, temp.mem.class, temp.static, temp.mem.enum
since: c++98
papers: P0091R3
related: temp.decls, temp.mem, temp.local, temp.inst, over.match.class.deduct, dcl.type.class.deduct, temp.over.link, temp.spec.partial
tags: 模板, 类模板, 推导指引, CTAD, 类外定义
updated: 2026-10-17
---

**类模板**（class template）为一个**无界的**相关类型集合规定布局与操作：`std::vector<int>`、`std::vector<std::string>`……每个特化都是一个独立的类类型，但它们共享同一份"蓝图"。

13.7.2 [temp.class] 分为六个小节，本页全部覆盖：

| 小节 | 规定什么 |
|---|---|
| 13.7.2.1 [temp.class.general] | 类模板是什么；类外定义成员时 *template-head* 与实参列表的写法；*class-key* 一致性 |
| 13.7.2.2 [temp.mem.func] | 类外定义成员函数；成员函数的模板实参从哪里来 |
| 13.7.2.3 [temp.deduct.guide] | **推导指引**（CTAD 的用户可定制部分） |
| 13.7.2.4 [temp.mem.class] | 类外定义成员类 |
| 13.7.2.5 [temp.static] | 静态数据成员的定义 |
| 13.7.2.6 [temp.mem.enum] | 类外定义成员枚举 |

前置知识：模板声明的一般形式 [[temp.pre]]，注入类名 [[temp.local]]，隐式实例化 [[temp.inst]]。

---

## 13.7.2.1 类模板概述

### 类模板定义一族类型（¶1–2）

¶1 类模板为无界的相关类型集合定义布局和操作。¶2 是一个例子（`Array<T>`）：前缀 `template<class T>` 说明正在声明一个模板，并且 *type-name* `T` 可以在声明中使用——换句话说，`Array` 是以 `T` 为参数的**参数化类型**。

```cpp run ok
template<class T> class Array {
    T* v;
    int sz;
public:
    explicit Array(int n) : v(new T[n]{}), sz(n) { }
    ~Array() { delete[] v; }
    Array(const Array&) = delete;
    T& operator[](int i) { return v[i]; }
    T& elem(int i) { return v[i]; }       // 类内定义：隐式 inline
    Array* self() { return this; }        // 注入类名：Array 在这里就是 Array<T>
};

int main() {
    Array<int> a(3);
    a[1] = 7;
    return a.elem(1) - 7;
}
```

在类模板的作用域内，模板名 `Array` 单独出现时是**注入类名**（injected-class-name），指称当前特化 `Array<T>`（[[temp.local]]）。所以成员里可以直接写 `Array*`、`Array(const Array&)`，不必重复 `<T>`。

!!! note "类模板不是类型"
    `Array` 本身不是类型，`Array<int>` 才是。在需要类型的地方写 `Array`（在类模板作用域外），要么是 CTAD（[[dcl.type.class.deduct]]），要么非良构。每个特化是**完全无关**的类：`Array<int>` 与 `Array<long>` 之间没有任何继承或转换关系，静态成员各有一份，`Array<int>` 的私有成员对 `Array<long>` 不可访问（除非用友元打通，[[temp.friend]]）。

### 类外定义成员：template-head 与实参列表（¶3）

¶3 是一个注（不具规范效力，规范规则散在 [[temp.mem.func]]、[[temp.over.link]]、[[dcl.meaning]] 中），但它把类外定义的三条要点说得最清楚：

1. 类外的成员定义本身是一个**模板定义**，它的 *template-head* 必须与类模板的**等价**（[[temp.over.link#6]]）；
2. 模板形参的**名字**可以不同（`T` 可以写成 `U`）；
3. 类模板名后面跟的是 *template-head* 的**模板实参列表**（[[temp.arg#2]]）——即**按原顺序**列出形参，形参包写成 `Ts...`。

```cpp run ok
template<class T1, class T2> struct A {
    void f1();
};
template<class X, class Y> void A<X, Y>::f1() { }    // OK: 名字可以换，顺序不能换

template<class... Types> struct B {
    void f3();
};
template<class... Ts> void B<Ts...>::f3() { }        // OK: 包必须写成展开

int main() { A<int, char>{}.f1(); B<int>{}.f3(); }
```

```cpp error
template<class T1, class T2> struct A { void f2(); };
template<class T2, class T1> void A<T1, T2>::f2() { }   // error: 实参顺序与 template-head 不一致

template<class... Types> struct B { void f4(); };
template<class... Types> void B<Types>::f4() { }        // error: 包未展开
```

为什么 `A<T1, T2>` 不行？因为 `template<class T2, class T1>` 的模板实参列表是 `<T2, T1>`——形参的**位置**才有意义，名字只是记号。写 `A<T1, T2>` 相当于指名了 `A` 的一个"交换了实参的"特化，它不是主模板本身，而是一个形如部分特化的东西——但它又不是部分特化的声明，于是找不到匹配的成员声明。

带约束的类模板，*template-head* 中的约束也要**等价**（不仅仅是"功能上等价"）：

```cpp error
template<typename T> concept C = true;
template<typename T> concept D = true;

template<C T> struct S {
    void f();
    void g();
    template<D U> struct Inner;
};

template<C A> void S<A>::f() { }        // OK: template-head 等价
template<typename T> void S<T>::g() { } // error: 没有约束，template-head 不等价
template<C X> template<D Y>
struct S<X>::Inner { };                 // OK: 两层 template-head 都等价
```

!!! lawyer "功能等价但不等价（IFNDR）"
    标准例子中还有一行：

    ```cpp
    template<typename T> requires C<T>    // IFNDR
    void S<T>::h() { }
    ```

    `template<C T>` 与 `template<typename T> requires C<T>` 接受且满足的模板实参集合完全相同——它们**功能等价**（functionally equivalent）但**不等价**（equivalent），按 [[temp.over.link#7]]，程序非良构、不要求诊断。为什么不直接要求诊断？因为判断"功能等价"一般是不可判定的（想想任意的常量表达式），标准只要求编译器按**字面结构**比较（"等价"），而把"结构不同但语义相同"的情形定为 IFNDR，免得编译器做"英雄式的努力"。实践中 Clang 23 对这一行直接报错（诊断为 template-head 中的类型约束与之前的声明不同），这是 IFNDR 允许的。

### class-key 必须一致（¶4）

¶4 类模板的部分特化、显式特化、显式实例化中的 *class-key* 必须与原模板声明在**种类**上一致（[[dcl.type.elab]]）：`class` 与 `struct` 可以互换，但 `union` 只能与 `union` 对应。

```cpp error
template<class T> struct S { };
template<class T> class S<T*> { };      // OK: class 与 struct 是同一种类
template<> union S<int> { };            // error: union 与 struct 不同种类
```

---

## 13.7.2.2 类模板的成员函数

### 类外定义（¶1）

¶1 类模板的成员函数可以在类模板定义之外定义。这时要写出完整的 *template-head*，并用 `ClassName<形参...>::` 限定：

```cpp run ok
#include <cstdio>
#include <cstdlib>
template<class T> class Array {
    T* v;
    int sz;
public:
    explicit Array(int);
    ~Array();
    T& operator[](int);
};

template<class T> Array<T>::Array(int n) : v(new T[n]{}), sz(n) { }   // 构造函数：Array<T>::Array
template<class T> Array<T>::~Array() { delete[] v; }
template<class T> T& Array<T>::operator[](int i) {
    if (i < 0 || sz <= i) { std::puts("Array: range error"); std::abort(); }
    return v[i];
}

int main() { Array<double> a(2); a[0] = 1.5; return int(a[0]) - 1; }
```

注意 `Array<T>::Array(int)`：限定名部分要写实参列表，但构造函数名本身是注入类名 `Array`。进入 `Array<T>::` 之后（在声明符之后的参数列表和函数体里），可以直接用注入类名 `Array`；但在声明符**之前**的返回类型里还没进入类作用域，必须写全（或者使用尾置返回类型）：

```cpp run ok
template<class T> struct Node {
    Node* next();
    Node* prev();
};
template<class T> Node<T>* Node<T>::next() { return this; }        // 返回类型在类作用域外：要写 Node<T>
template<class T> auto Node<T>::prev() -> Node* { return this; }   // 尾置返回类型在类作用域内
int main() { Node<int> n; return n.next() == n.prev() ? 0 : 1; }
```

**带约束的成员函数**：类外定义必须重复同样的 *requires-clause*，否则它与类内声明不对应（[[basic.scope.scope]] 中"对应"的判定包括尾随 *requires-clause*）：

```cpp error
template<typename T> concept C = requires { typename T::type; };

template<typename T> struct S {
    void f() requires C<T>;
    void g() requires C<T>;
};

template<typename T>
void S<T>::f() requires C<T> { }      // OK
template<typename T>
void S<T>::g() { }                    // error: S<T> 中没有无约束的 g
```

### 模板实参由对象决定（¶2）

¶2 类模板成员函数的模板实参由**调用该成员函数的对象的类型**的模板实参决定。`v1[3]` 中 `v1` 是 `Array<int>`，所以调用的是 `Array<int>::operator[]`。这句话的意义在于：普通成员函数（非成员模板）**不做模板实参推导**——它不是函数模板，而是"类模板特化的成员函数"，一旦类特化确定，它就是一个普通函数，参数可以进行任意隐式转换：

```cpp run ok
template<class T> struct Wrap {
    void set(T) { }                     // 不是函数模板：参数类型在 Wrap<T> 确定时就固定了
};
template<class T> void free_set(Wrap<T>&, T) { }   // 函数模板：T 从两个实参分别推导

int main() {
    Wrap<long> w;
    w.set(1);                           // OK: int → long 隐式转换
    // free_set(w, 1);                  // error: T 推导冲突（long 与 int）
    free_set<long>(w, 1);               // OK: 显式指定
}
```

!!! note "按需实例化"
    类模板被隐式实例化时，只实例化成员函数的**声明**；成员函数的**定义**只在被 odr-use（或需要其定义）时才实例化（[[temp.inst]]）。所以 `std::vector<std::unique_ptr<int>>` 可以使用，尽管它的拷贝构造函数（若被实例化）会因 `unique_ptr` 不可拷贝而失败——只要不调用它。

---

## 13.7.2.3 推导指引

**推导指引**（deduction guide）是 C++17 类模板实参推导（CTAD）中由用户提供的部分：它告诉编译器"见到这样的构造实参时，推导出这样的特化"。完整的推导算法在 [[over.match.class.deduct]]，占位符本身在 [[dcl.type.class.deduct]]，本小节只管推导指引的**声明**。

### 何时使用、怎样被找到（¶1）

¶1 当 *template-name*（或指称类模板的 *splice-type-specifier*，{{c++26}}）作为**推导类类型**的类型说明符出现时，使用推导指引。

!!! std
    Deduction guides are not found by name lookup. Instead, when performing class template argument deduction, all reachable deduction guides declared for the class template are considered.

推导指引**不通过名字查找**被找到：做 CTAD 时，考虑为该类模板声明的**所有可达的**（reachable，[[module.reach]]）推导指引。这意味着：

- 推导指引不是函数，不能被调用，也没有名字可以被引用；
- 不受 using-declaration、using-directive 的影响，也不受 ADL 影响；
- 只要在 CTAD 发生处**可达**（在同一 TU 中，就是"出现在使用之前"），就会被考虑。

```text
deduction-guide:
    explicit-specifier(opt) simple-template-name ( parameter-declaration-clause ) -> simple-template-id requires-clause(opt) ;
```

语法上它像一个带尾置返回类型的构造函数声明，但：没有函数体、没有返回类型前缀、名字是模板名、"返回类型"是一个 *simple-template-id*。推导指引可以是模板（前面加 *template-head*），也可以不是：

```cpp run ok
#include <string>
#include <type_traits>
template<class T> struct S {
    T data;
    S(T t) : data(t) { }
};
S(const char*) -> S<std::string>;                 // 非模板推导指引

template<class T, class D = int> struct P { T data; };
template<class U> P(U) -> P<typename U::type>;    // 模板推导指引（标准 ¶2 的例子）

struct A {
    using type = short;
    operator type() { return 0; }
};

S s("hello");
P x{A()};
static_assert(std::is_same_v<decltype(s), S<std::string>>);
static_assert(std::is_same_v<decltype(x), P<short, int>>);   // D 用默认实参
int main() { }
```

¶2 的例子值得细看：`P x{A()};` 中，聚合推导与 `P(U)` 指引都参与（[[over.match.class.deduct]]），推导指引给出 `P<short>`，默认模板实参补全为 `P<short, int>`。随后用 `A()` 初始化 `short data`——借助 `A` 的转换函数。

### 限制（¶3）

¶3 推导指引的声明有五条限制：

1. *parameter-declaration-clause* 的限制与函数声明相同（[[dcl.fct]]），**但不能**出现泛型参数类型占位符（`auto` 形参）——推导指引不能是"简写函数模板"。想要模板就显式写 *template-head*。
2. 箭头后的 *simple-template-id* 必须指名一个**类模板特化**。
3. 箭头前的 *simple-template-name* 必须与 *simple-template-id* 的模板名是**同一个标识符**——`X(...) -> Y<...>` 非良构。
4. 推导指引必须**居于**（inhabit）类模板所属的作用域；如果是成员类模板，还要有**相同的访问权限**。
5. 同一类模板的两个推导指引若有**等价的** *parameter-declaration-clause*，且其中一个对另一个可达，则非良构——推导指引不能"重声明"。

```cpp error
#include <string>
template<class T> struct Z { Z(T) { } };
Z(int) -> Z<int>;
Z(int) -> Z<int>;                       // error: 等价的推导指引重复声明

template<class T> struct Q { Q(T) { } };
Q(int) -> Z<int>;                       // error: 模板名必须相同

class O {
    template<class T> struct In { In(T) { } };   // private
public:
    In(const char*) -> In<std::string>;          // error: 访问权限与 In 不同
};
```

```cpp
template<class T> struct W { W(T) { } };
W(auto) -> W<int>;                      // ill-formed: 推导指引中不能出现 auto 形参
```

!!! warning "编译器现状"
    按 ¶3，`W(auto) -> W<int>;` 非良构。截至写作时，本机 Clang 23 **接受**这条声明并把它当作模板推导指引使用，没有给出诊断。这是编译器与标准的偏差。

"居于类模板所属的作用域"意味着：命名空间作用域的类模板，推导指引要写在**同一个命名空间**中（不能在别的命名空间里"为 `std::vector` 添加推导指引"）；成员类模板的推导指引写在外围类里：

```cpp run ok
#include <string>
#include <type_traits>
struct Outer {
    template<class T> struct In { In(T) { } };
    In(const char*) -> In<std::string>;       // 成员推导指引：在类中，访问权限相同（public）
};
Outer::In i("x");
static_assert(std::is_same_v<decltype(i), Outer::In<std::string>>);
int main() { }
```

### explicit 推导指引

`explicit` 推导指引在**复制初始化**语境中不被考虑（与 explicit 构造函数相同的规则，见 [[over.match.class.deduct]] 中"概念上的构造函数继承 *explicit-specifier*"）；若在**复制列表初始化**中被选中则非良构。这给出一个常见的"惊喜"：同一个初始化器，`=` 与 `()` 推导出不同的类型。

```cpp run ok
#include <string>
#include <type_traits>
template<class T> struct S {
    T data;
    S(T t) : data(t) { }
};
explicit S(const char*) -> S<std::string>;

S a("hi");             // 直接初始化：explicit 指引参与 → S<std::string>
S b = "hi";            // 复制初始化：explicit 指引不参与 → 由构造函数生成的隐式指引 → S<const char*>
static_assert(std::is_same_v<decltype(a), S<std::string>>);
static_assert(std::is_same_v<decltype(b), S<const char*>>);
int main() { }
```

### 带约束的推导指引

推导指引可以带尾随 *requires-clause*，也可以有受约束的模板形参。约束参与推导指引之间的重载决议（最终按 [[over.match.best]] 与 [[temp.func.order]] 比较）：

```cpp run ok
#include <concepts>
#include <type_traits>
template<class T> struct Num { T v; };
template<std::integral I>       Num(I) -> Num<long long>;
template<std::floating_point F> Num(F) -> Num<double>;

Num a{1};
Num b{1.0f};
static_assert(std::is_same_v<decltype(a), Num<long long>>);
static_assert(std::is_same_v<decltype(b), Num<double>>);
int main() { }
```

!!! pitfall "推导指引不影响初始化本身"
    推导指引只决定"推导出哪个特化"。推导完成后，初始化按普通规则对**那个特化**进行：`S(const char*) -> S<std::string>` 之后，真正调用的是 `S<std::string>` 的构造函数，并把 `const char*` 转换为 `std::string`。如果目标特化里没有合适的构造函数，推导成功但初始化失败。

!!! history "历史与演进"
    - **C++17**：CTAD 与推导指引由 [[P0091R3]] 引入。
    - **C++20**：聚合的 CTAD、别名模板的 CTAD（见 [[over.match.class.deduct]]）。
    - **C++26**：推导类类型可以由指称类模板的 *splice-type-specifier* 给出（静态反射），¶1 措辞相应扩展。

---

## 13.7.2.4 类模板的成员类

¶1 类模板的成员类可以在类模板定义之外定义。注释提醒：成员类必须在**首次需要实例化它的使用**之前定义——只用到指针或引用不需要成员类完整：

```cpp run ok
template<class T> struct A {
    class B;
};
A<int>::B* b1;                          // OK: 需要 A<int> 完整，不需要 A<int>::B
template<class T> class A<T>::B { };
A<int>::B b2;                           // OK: 需要 A<int>::B 的定义——此时已经有了
int main() { }
```

```cpp error
template<class T> struct A { class B; };
A<int>::B b0;                           // error: A<int>::B 是不完整类型（定义还未出现）
template<class T> class A<T>::B { };
```

成员类本身是"类模板的成员"，不是独立的模板，但它是模板化实体（templated entity，[[temp.pre]]），按 [[temp.inst]] 按需实例化：实例化 `A<int>` 只会实例化 `A<int>::B` 的声明。

---

## 13.7.2.5 类模板的静态数据成员

### 类外定义（¶1）

¶1 静态数据成员（或静态数据成员模板）的定义可以在**外围命名空间作用域**中提供：

```cpp run ok
template<class T> class X {
public:
    static T s;
};
template<class T> T X<T>::s = 0;        // 静态数据成员的定义：本身是一个模板定义

struct limits {
    template<class T>
    static const T min;                 // 静态数据成员模板：声明
};
template<class T>
const T limits::min = { };              // 定义

int main() { return X<int>::s + limits::min<int>; }
```

`template<class T> T X<T>::s = 0;` 是一个**模板化的变量定义**，可以（也通常）放在头文件中，在多个 TU 中出现不违反 ODR——每个特化 `X<int>::s` 按模板实体的 ODR 规则（[[basic.def.odr]]）只对应一个对象。这与非模板类的静态数据成员不同：非模板类的静态成员定义放在头文件会导致多重定义。

C++17 起更常见的写法是 `inline` 静态成员，或 `constexpr` 静态成员（隐式 inline），不需要类外定义：

```cpp run ok
template<class T> struct Counter {
    static inline int count = 0;               // C++17：类内定义
    static constexpr T zero{};                 // constexpr 静态成员隐式 inline
};
int main() { ++Counter<int>::count; ++Counter<long>::count; return Counter<int>::count - 1 + int(Counter<long>::zero); }
```

!!! note "每个特化一份"
    `Counter<int>::count` 和 `Counter<long>::count` 是两个不同的对象。这是"每个特化是独立的类"的直接推论，也是"在类模板中用静态成员实现全局计数器"之所以失败的原因——需要真正共享时，把静态成员放到非模板基类里。

!!! warning "静态成员的初始化顺序"
    隐式实例化的类模板静态数据成员具有**无序初始化**（unordered initialization，[[basic.start.dynamic]]）：若它的初始化是动态的，它与其他任何动态初始化之间都没有顺序保证（即使在同一个 TU 中）。用常量初始化（`constexpr`/`constinit`）避开这个问题。

### 未知界数组的显式特化（¶2）

¶2 若静态数据成员被声明为**未知界数组**，它的显式特化可以有与（主模板的）定义**不同的**界：

```cpp run ok
template<class T> struct A {
    static int i[];
};
template<class T> int A<T>::i[4];       // 一般定义：4 个元素
template<> int A<int>::i[] = { 1 };     // 显式特化：1 个元素
static_assert(sizeof(A<char>::i) == 4 * sizeof(int));
static_assert(sizeof(A<int>::i) == sizeof(int));
int main() { }
```

为什么需要专门写这一条？因为一般而言，同一实体的各个声明必须有一致的类型（[[basic.link]]），而 `int[4]` 与 `int[1]` 是不同的类型。显式特化 `A<int>::i` 是 `A<int>` 的成员 `i`（类型 `int[]`）的定义，它不是从 `A<T>::i[4]` 实例化来的；¶2 明确允许这种"补全成不同界"的情形。

---

## 13.7.2.6 类模板的枚举成员

¶1 类模板的枚举成员可以在类模板定义之外定义（需要是可以前置声明的枚举：有固定底层类型的枚举，或有作用域的枚举，[[dcl.enum]]）：

```cpp run ok
template<class T> struct A {
    enum E : T;                          // 不透明枚举声明，底层类型依赖于 T
};
template<class T> enum A<T>::E : T { e1, e2 };
A<int>::E e = A<int>::e1;
int main() { return e; }
```

---

## 实现视角

!!! impl "实现视角"
    - **按需实例化与代码体积**：每个被使用的成员函数在每个用到它的 TU 中都会被实例化并生成为 COMDAT（弱）符号，链接器去重。未被使用的成员函数不生成代码，这正是"类模板成员函数只在被使用时实例化"在目标文件层面的体现。
    - **静态数据成员**：`X<int>::s` 这样的模板静态成员也以 COMDAT/弱符号形式输出，链接器保证只保留一份；动态初始化会被一个 guard 变量保护（与函数局部静态类似），因为多个 TU 可能都含有它的初始化代码。
    - **推导指引不进入目标文件**：推导指引只在编译期参与 CTAD，不生成任何符号。

## 陷阱

!!! pitfall "常见误解"
    - "类外定义时写 `template<class T> void A::f()` 就行"——必须写 `A<T>::f`。在类外，`A` 不是注入类名。
    - "类外定义的约束可以换一种写法"——必须**等价**；换写法（如 `template<C T>` ↔ `requires C<T>`）是 IFNDR。
    - "推导指引像函数一样可以放在任何命名空间、可以被 using 引入"——推导指引必须居于类模板所在的作用域，且不经名字查找。
    - "`S s = x;` 与 `S s(x);` 推导结果一定相同"——explicit 推导指引只参与直接初始化。
    - "类模板静态成员在所有特化之间共享"——每个特化一份。

## 思考题

!!! question "思考题 1"
    下面的代码中 `x` 的类型是什么？如果把推导指引改为 `explicit`，`x` 和 `y` 的类型分别是什么？

    ```cpp
    template<class T> struct Box { Box(T) {} };
    Box(int) -> Box<long>;
    Box x(1);
    Box y = 1;
    ```

<details markdown="1">
<summary>答案</summary>

不加 `explicit`：CTAD 的候选是从构造函数生成的隐式指引 `template<class T> Box(T) -> Box<T>` 与用户指引 `Box(int) -> Box<long>`。对实参 `1`，二者的转换序列都是精确匹配；按 [[over.match.best]]，非模板优于模板，选用户指引，`x`、`y` 都是 `Box<long>`。

加 `explicit`：`x` 是直接初始化，explicit 指引参与，仍为 `Box<long>`；`y` 是复制初始化，explicit 指引不是候选，只剩隐式指引，`y` 是 `Box<int>`。
</details>

!!! question "思考题 2"
    为什么下面第二个定义是错的，而第一个是对的？

    ```cpp
    template<class T, class U> struct M { void f(); };
    template<class U, class T> void M<U, T>::f() { }   // #1
    template<class T, class U> void M<U, T>::f() { }   // #2
    ```

<details markdown="1">
<summary>答案</summary>

#1 的 *template-head* 是 `template<class U, class T>`，它的模板实参列表是 `<U, T>`，与 `M<U, T>` 一致——形参名只是记号，第一个形参叫 `U` 也无妨。#2 的 *template-head* 的实参列表是 `<T, U>`，而它写成了 `M<U, T>`，即"把第一、二个实参交换"的特化，这不是主模板的实参列表，因此找不到对应的成员声明——它试图定义一个并不存在的「部分特化」`M<U, T>` 的成员。
</details>

!!! summary "小结"
    - 类模板 = 一族互不相关的类类型；模板内部模板名是注入类名。
    - 类外定义成员：*template-head* 等价（约束也要等价，否则 IFNDR 或不匹配）、形参名可换、实参列表按原顺序写（包写成展开）。
    - 成员函数不是函数模板：模板实参由对象类型决定，参数可隐式转换；按需实例化。
    - 推导指引：不经名字查找，所有可达指引都参与；不能用 `auto` 形参；模板名要相同；居于类模板的作用域并（成员类模板）同访问权限；不可重复声明；`explicit` 指引只参与直接初始化。
    - 静态数据成员：类外定义本身是模板定义，可放头文件；每个特化一份；未知界数组的显式特化可以换界。
    - 成员类、成员枚举可以类外定义；成员类须在需要完整类型的使用前定义。
