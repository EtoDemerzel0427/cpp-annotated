---
title: 类模板
summary: 类模板定义一族互不相关的类类型；怎样在类外定义它的成员函数、成员类、成员枚举和静态数据成员；推导指引怎样写、怎样被找到。
status: done
covers: temp.class.general, temp.mem.func, temp.deduct.guide, temp.mem.class, temp.static, temp.mem.enum
since: c++98
papers: P0091R3
related: temp.decls, temp.mem, temp.local, temp.inst, over.match.class.deduct, dcl.type.class.deduct, temp.over.link, temp.spec.partial
tags: 模板, 类模板, 推导指引, CTAD, 类外定义
updated: 2026-10-19
---

!!! tldr
    - `Array<int>` 和 `Array<long>` 是两个毫无关系的类：没有转换，静态成员各有一份，私有成员互不可见。
    - 在类外定义成员时，*template-head* 要与类模板的等价，模板名后按原顺序写出形参（包写成 `Ts...`）；形参名可以换。约束写法不同但效果相同时，程序是 IFNDR。
    - 类模板的普通成员函数不是函数模板：它的模板实参来自对象的类型，调用时不做推导，实参可以隐式转换。
    - 推导指引告诉 CTAD 某种构造实参该推出哪个特化。它不经名字查找，必须写在类模板所在的作用域；`explicit` 指引只参与直接初始化。
    - 静态数据成员的类外定义本身是模板定义，可以放进头文件；未知界数组成员的显式特化可以换一个界。

## 类模板定义一族类型 [temp.class.general]

```cpp run ok
template<class T> class Array {
    T* v;
    int sz;
public:
    explicit Array(int n) : v(new T[n]{}), sz(n) { }
    ~Array() { delete[] v; }
    Array(const Array&) = delete;      // Array 即 Array<T>
    T& operator[](int i) { return v[i]; }
    T& elem(int i) { return v[i]; }
};

int main() {
    Array<int> a(3);
    a[1] = 7;
    return a.elem(1) - 7;
}
```

¶1 **类模板**（class template）为一个无界的、彼此相关的类型集合规定布局和操作。¶2 的例子就是这个 `Array`：前缀 `template<class T>` 表示正在声明一个模板，声明里可以把 `T` 当作类型名使用。换句话说，`Array` 是以 `T` 为参数的参数化类型。

`Array` 本身不是类型，`Array<int>` 才是。`Array<int>` 叫做类模板的一个**特化**（specialization）。在类模板外需要类型的地方只写 `Array`，要么触发类模板实参推导（CTAD，见下文的推导指引），要么非良构。

在类模板内部，单独出现的 `Array` 是**注入类名**（injected-class-name），指当前特化 `Array<T>`（[[temp.local]]）。所以上面的拷贝构造函数可以写成 `Array(const Array&)`，不必重复 `<T>`。

每个特化都是独立的类。`Array<int>` 与 `Array<long>` 之间没有继承或转换关系，静态成员各有一份，一个特化也不能访问另一个特化的私有成员，除非声明为友元（[[temp.friend]]）。

## 在类外定义成员（¶3）

<div class="compare" markdown="1">

```cpp ok
template<class T1, class T2>
struct A { void f1(); };

// 形参改名：OK
template<class X, class Y>
void A<X, Y>::f1() { }

template<class... Types>
struct B { void f3(); };

template<class... Ts>
void B<Ts...>::f3() { }
```

```cpp error
template<class T1, class T2>
struct A { void f2(); };

// 顺序与 template-head 不一致
template<class T2, class T1>
void A<T1, T2>::f2() { }  // error

template<class... Types>
struct B { void f4(); };

template<class... Types>
void B<Types>::f4() { }   // error: 包未展开
```

</div>

¶3 是一条注，把分散在 [[temp.mem.func]]、[[temp.over.link]] 里的规范规则归纳成三点：

1. 类外的成员定义本身是一个模板定义，它的 *template-head*（`template<...>` 这一部分）必须与类模板的**等价**（[[temp.over.link#6]]）。
2. 形参的名字可以与类模板定义里的不同。
3. 类模板名后面跟的是这个 *template-head* 的模板实参列表（[[temp.arg]]），也就是按原顺序依次写出各个形参，形参包写成 `Ts...`。

右边的 `A<T1, T2>` 为什么错？`template<class T2, class T1>` 的实参列表是 `<T2, T1>`，起作用的是形参的位置，名字只是记号。写成 `A<T1, T2>` 等于指名了一个交换了两个实参的特化，它不是主模板，类模板里找不到与之对应的成员声明。

### 约束也要等价

如果类模板带约束，类外定义的 *template-head* 里的约束必须写得和原来一样：

```cpp error
template<typename T> concept C = true;
template<typename T> concept D = true;

template<C T> struct S {
    void f();
    void g();
    template<D U> struct Inner;
};

template<C A> void S<A>::f() { }        // OK：template-head 等价
template<typename T> void S<T>::g() { } // error: 少了约束，找不到匹配的声明
template<C X> template<D Y>
struct S<X>::Inner { };                 // OK：两层 template-head 都等价
```

标准的例子里还有一种写法：

```cpp ifndr
template<typename T> concept C = true;
template<C T> struct S { void h(); };

template<typename T> requires C<T>   // IFNDR
void S<T>::h() { }
```

`template<C T>` 与 `template<typename T> requires C<T>` 接受同样的模板实参，二者**功能等价**（functionally equivalent），但写法不同，所以不**等价**（equivalent）。按 [[temp.over.link#7]]，这样的程序非良构，不要求诊断（IFNDR）：标准对它没有任何要求，编译器可以报错，也可以默默接受。

规则这样定，是因为判断两段任意的约束在语义上是否相同一般做不到。标准只要求编译器按书写结构比较，结构不同而语义相同的情形交给 IFNDR。Clang 23 对这一行直接报错（type constraint differs in template redeclaration），这是允许的。

### class-key 要一致（¶4）

¶4 类模板的部分特化、显式特化和显式实例化所用的 *class-key*，必须与原模板声明属于同一种（[[dcl.type.elab]]）。`class` 和 `struct` 算同一种，`union` 只能对应 `union`。

```cpp error
template<class T> struct S { };
template<class T> class S<T*> { };      // OK：class 与 struct 同种
template<> union S<int> { };            // error: union 与 struct 不同种
```

## 成员函数 [temp.mem.func]

### 类外定义（¶1）

¶1 类模板的成员函数可以在类模板定义之外定义：

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

template<class T> Array<T>::Array(int n) : v(new T[n]{}), sz(n) { }
template<class T> Array<T>::~Array() { delete[] v; }
template<class T> T& Array<T>::operator[](int i) {
    if (i < 0 || sz <= i) { std::puts("Array: range error"); std::abort(); }
    return v[i];
}

int main() { Array<double> a(2); a[0] = 1.5; return int(a[0]) - 1; }
```

限定部分必须写成 `Array<T>::`。在类外 `Array` 不是注入类名，`template<class T> void Array::f()` 是错的。进入 `Array<T>::` 之后，参数列表和函数体都在类作用域内，可以只写 `Array`，所以构造函数写作 `Array<T>::Array`。

写在声明符前面的返回类型还不在类作用域内，要写全；尾置返回类型已经在类作用域内：

```cpp run ok
template<class T> struct Node {
    Node* next();
    Node* prev();
};
template<class T> Node<T>* Node<T>::next() { return this; }
template<class T> auto Node<T>::prev() -> Node* { return this; }
int main() { Node<int> n; return n.next() == n.prev() ? 0 : 1; }
```

带约束的成员函数，类外定义要重复同样的 *requires-clause*。判断类外定义对应哪个类内声明时，尾随的 *requires-clause* 也算在内（[[basic.scope.scope]]）：

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

### 模板实参来自对象（¶2）

¶2 类模板成员函数的模板实参，由调用它的那个对象的类型决定。`v1` 是 `Array<int>`，`v1[3]` 调用的就是 `Array<int>::operator[]`。

由此可知，类模板的普通成员函数不是函数模板。类的特化一旦确定，它就是一个普通函数，参数类型已经固定，调用时不做模板实参推导，实参可以做任何隐式转换：

```cpp run ok
template<class T> struct Wrap {
    void set(T) { }                     // 参数类型在 Wrap<T> 确定时就固定了
};
template<class T> void free_set(Wrap<T>&, T) { }   // 函数模板：T 从两个实参分别推导

int main() {
    Wrap<long> w;
    w.set(1);                           // OK：int 隐式转换为 long
    // free_set(w, 1);                  // error: T 推导冲突（long 与 int）
    free_set<long>(w, 1);               // OK：显式指定
}
```

类模板隐式实例化时，只实例化成员函数的声明；某个成员函数的定义要到需要它时才实例化（[[temp.inst]]）。所以 `std::vector<std::unique_ptr<int>>` 能用：它的拷贝构造函数一旦实例化就会出错，但只要不拷贝，它就不会被实例化。

## 成员类 [temp.mem.class]

¶1 类模板的成员类可以在类模板定义之外定义。注 1 提醒，定义必须出现在第一次需要实例化它的使用之前。只用到指针或引用时，成员类不必完整：

<div class="compare" markdown="1">

```cpp ok
template<class T>
struct A { class B; };

A<int>::B* b1;  // OK：只需 A<int>
template<class T>
class A<T>::B { };
A<int>::B b2;   // OK：定义已出现
```

```cpp error
template<class T>
struct A { class B; };

A<int>::B b0;   // error: B 尚未定义
template<class T>
class A<T>::B { };
```

</div>

## 成员枚举 [temp.mem.enum]

¶1 类模板的成员枚举也可以在类外定义。前提是枚举在类内能先声明而不定义，也就是有固定底层类型或者是有作用域的枚举（[[dcl.enum]]）：

```cpp run ok
template<class T> struct A {
    enum E : T;                         // 底层类型依赖于 T
};
template<class T> enum A<T>::E : T { e1, e2 };
A<int>::E e = A<int>::e1;
int main() { return e; }
```

## 静态数据成员 [temp.static]

¶1 静态数据成员和静态数据成员模板的定义，可以写在包含该类模板定义的命名空间作用域中：

```cpp run ok
template<class T> class X {
public:
    static T s;
};
template<class T> T X<T>::s = 0;        // 本身是一个模板定义

struct limits {
    template<class T>
    static const T min;                 // 静态数据成员模板：声明
};
template<class T>
const T limits::min = { };              // 定义

int main() { return X<int>::s + limits::min<int>; }
```

`template<class T> T X<T>::s = 0;` 是模板定义，可以放在头文件里被多个翻译单元包含，不违反 ODR（[[basic.def.odr]]）。普通类的静态数据成员定义如果放进头文件，就会导致多重定义。

C++17 起更常见的写法是在类内用 `inline` 或 `constexpr`（隐式 inline）定义，不再需要类外定义：

```cpp run ok
template<class T> struct Counter {
    static inline int count = 0;
    static constexpr T zero{};
};
int main() {
    ++Counter<int>::count;
    ++Counter<long>::count;
    return Counter<int>::count - 1 + int(Counter<long>::zero);
}
```

`Counter<int>::count` 和 `Counter<long>::count` 是两个对象。想让所有特化共享一个计数器，要把静态成员放进一个非模板的基类。

!!! warning "初始化顺序"
    隐式实例化的类模板静态数据成员，初始化是无序的（[[basic.start.dynamic]]）：如果它需要动态初始化，就与其他任何动态初始化都没有先后保证，即使在同一个翻译单元里。用 `constexpr` 或 `constinit` 做常量初始化可以避开这个问题。

### 未知界数组（¶2）

¶2 如果静态数据成员声明为未知界数组，它的显式特化可以用与一般定义不同的界：

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

`A<int>::i` 的显式特化不是从 `A<T>::i[4]` 实例化来的，它直接给出 `A<int>` 的成员 `i` 的定义，所以可以补成另一个界。

## 推导指引 [temp.deduct.guide]

```cpp run ok
#include <string>
#include <type_traits>
template<class T> struct S {
    T data;
    S(T t) : data(t) { }
};
S(const char*) -> S<std::string>;       // 推导指引

S a(42);                                // S<int>：从构造函数推出
S b("hello");                           // S<std::string>：由推导指引决定
static_assert(std::is_same_v<decltype(a), S<int>>);
static_assert(std::is_same_v<decltype(b), S<std::string>>);
int main() { }
```

C++17 起，可以只写类模板名来声明变量，由初始化器推出模板实参，这叫**类模板实参推导**（class template argument deduction，CTAD，[[dcl.type.class.deduct]]）。编译器根据类模板的构造函数生成一组隐式的推导规则，没有这条推导指引时，`S b("hello")` 会推出 `S<const char*>`。

**推导指引**（deduction guide）是用户补充的推导规则：看到这样的构造实参，就推出这样的特化。完整的推导算法在 [[over.match.class.deduct]]，本节只管推导指引怎样声明。

```text
deduction-guide:
    explicit-specifier(opt) simple-template-name ( parameter-declaration-clause ) -> simple-template-id requires-clause(opt) ;
```

它的写法像一个带尾置返回类型的构造函数声明，但没有函数体，箭头后是一个特化。推导指引前面可以加 *template-head* 成为模板，也可以不加。

### 怎样被找到（¶1）

¶1 当类模板名（或者 C++26 中指称类模板的 *splice-type-specifier*）用作推导类类型的说明符时，就使用推导指引。

!!! std
    Deduction guides are not found by name lookup. Instead, when performing class template argument deduction, all reachable deduction guides declared for the class template are considered.

推导指引不是函数，不能调用，也没有可以引用的名字。using 声明、using 指令、ADL 都与它无关。做 CTAD 时，凡是在此处可达的（reachable，[[module.reach]]）、为这个类模板声明的推导指引都参与。在单个翻译单元里，可达大致就是出现在使用之前。

¶2 的例子是一个模板推导指引：

```cpp run ok
#include <type_traits>
template<class T, class D = int>
struct S { T data; };

template<class U>
S(U) -> S<typename U::type>;

struct A {
    using type = short;
    operator type() { return 0; }
};
S x{A()};
static_assert(std::is_same_v<decltype(x), S<short, int>>);
int main() { }
```

推导指引给出 `S<short>`，默认模板实参把它补成 `S<short, int>`。之后用 `A()` 初始化 `short data`，用到的是 `A` 的转换函数。

推导指引只决定推出哪个特化。推导完成后，初始化按普通规则对那个特化进行：第一个例子里 `S b("hello")` 调用的是 `S<std::string>` 的构造函数，把 `const char*` 转换成 `std::string`。如果那个特化没有合适的构造函数，推导成功，初始化仍然失败。

### 五条限制（¶3）

¶3 对推导指引的声明有五条要求：

1. 形参列表的限制与函数声明相同（[[dcl.fct]]），但不能出现 `auto` 形参。想要模板，就显式写 *template-head*。
2. 箭头后的 *simple-template-id* 必须指名一个类模板特化。
3. 箭头前的名字必须与箭头后的模板名是同一个标识符，`X(...) -> Y<...>` 非良构。
4. 推导指引必须位于类模板所属的作用域；对成员类模板，访问权限也要与它相同。
5. 同一个类模板的两个推导指引如果形参列表等价，且其中一个从另一个可达，程序非良构。推导指引不能重复声明。

```cpp error
#include <string>
template<class T> struct Z { Z(T) { } };
Z(int) -> Z<int>;
Z(int) -> Z<int>;                       // error: 重复声明

template<class T> struct Q { Q(T) { } };
Q(int) -> Z<int>;                       // error: 模板名不同

class O {
    template<class T> struct In { In(T) { } };   // private
public:
    In(const char*) -> In<std::string>;          // error: 访问权限与 In 不同
};
```

```cpp
template<class T> struct W { W(T) { } };
W(auto) -> W<int>;                      // 按 ¶3 非良构：不能有 auto 形参
```

!!! warning "Clang 的偏差"
    本机 Clang 23 接受 `W(auto) -> W<int>;`，把它当作模板推导指引使用，不给任何诊断。这与标准不符，所以上面这段没有标判定。

第 4 条意味着，命名空间作用域的类模板，推导指引要写在同一个命名空间里，不能在自己的命名空间里给 `std::vector` 添加推导指引。成员类模板的推导指引写在外围类中：

```cpp run ok
#include <string>
#include <type_traits>
struct Outer {
    template<class T> struct In { In(T) { } };
    In(const char*) -> In<std::string>;   // 与 In 同为 public
};
Outer::In i("x");
static_assert(std::is_same_v<decltype(i), Outer::In<std::string>>);
int main() { }
```

### explicit 推导指引

`explicit` 推导指引和 explicit 构造函数一样，在复制初始化中不参与；在复制列表初始化中被选中则非良构（[[over.match.class.deduct]]）。于是同一个初始化器，用 `=` 和用 `()` 可能推出不同的类型：

```cpp run ok
#include <string>
#include <type_traits>
template<class T> struct S {
    T data;
    S(T t) : data(t) { }
};
explicit S(const char*) -> S<std::string>;

S a("hi");             // 直接初始化：explicit 指引参与
S b = "hi";            // 复制初始化：只剩构造函数生成的规则
static_assert(std::is_same_v<decltype(a), S<std::string>>);
static_assert(std::is_same_v<decltype(b), S<const char*>>);
int main() { }
```

### 带约束的推导指引

推导指引可以带 *requires-clause* 或受约束的模板形参。几个指引都匹配时，约束参与比较（[[over.match.best]]、[[temp.func.order]]）：

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

!!! history "演进"
    CTAD 和推导指引由 C++17 的 [[P0091R3]] 引入。C++20 加入了聚合类和别名模板的 CTAD（[[over.match.class.deduct]]）。C++26 的静态反射允许用 *splice-type-specifier* 指称类模板来做 CTAD，¶1 的措辞随之扩展。

!!! impl "实现视角"
    每个用到的成员函数会在每个使用它的翻译单元里实例化，输出为 COMDAT（弱）符号，由链接器去重；没用到的不生成代码。`X<int>::s` 这样的模板静态成员同样以弱符号输出，如果需要动态初始化，会有一个 guard 变量保证只初始化一次。推导指引只在编译期参与 CTAD，不产生任何符号。

## 思考题

!!! question "思考题 1"
    `x` 和 `y` 的类型是什么？如果把推导指引改为 `explicit` 呢？

    ```cpp
    template<class T> struct Box { Box(T) {} };
    Box(int) -> Box<long>;
    Box x(1);
    Box y = 1;
    ```

<details markdown="1">
<summary>答案</summary>

候选有两个：从构造函数生成的 `template<class T> Box(T) -> Box<T>`，和用户写的 `Box(int) -> Box<long>`。对实参 `1`，两者都是精确匹配；按 [[over.match.best]]，非模板优于模板，选用户指引，`x`、`y` 都是 `Box<long>`。

改成 `explicit` 后，`x` 是直接初始化，结果不变，仍为 `Box<long>`。`y` 是复制初始化，explicit 指引不参与，只剩构造函数生成的规则，`y` 是 `Box<int>`。
</details>

!!! question "思考题 2"
    为什么 #1 对、#2 错？

    ```cpp
    template<class T, class U> struct M { void f(); };
    template<class U, class T> void M<U, T>::f() { }   // #1
    template<class T, class U> void M<U, T>::f() { }   // #2
    ```

<details markdown="1">
<summary>答案</summary>

#1 的 *template-head* 是 `template<class U, class T>`，实参列表是 `<U, T>`，与 `M<U, T>` 一致；第一个形参叫 `U` 并无妨碍。#2 的实参列表是 `<T, U>`，却写成了 `M<U, T>`，即交换了两个实参的特化。它不是主模板，找不到对应的成员声明。
</details>
