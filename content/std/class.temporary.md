---
title: 临时对象
summary: 临时对象什么时候产生（C++17 起只在 prvalue 需要变成对象时才物化）、默认什么时候销毁（完整表达式结束时），以及引用绑定、范围 for 等七种语境下的例外；悬垂引用的规则大多在这里。
status: done
papers: P0135R1, P2718R0, P2748R5
related: conv.rval, basic.lval, dcl.init.ref, class.copy.elision, stmt.ranged, stmt.return, class.base.init, intro.object
tags: 临时对象, 生命周期延长, 悬垂引用, 复制消除
updated: 2026-10-19
---

!!! tldr
    - C++17 起，prvalue 不是对象，只是初始化对象的方式。只有在必须有一个对象时，例如把引用绑定到它，才**物化**出临时对象。用 prvalue 初始化同类型对象时没有临时对象，也不需要复制或移动构造函数。
    - 临时对象默认在包含它的完整表达式（大致就是一条语句）结束时销毁，所以 `const char* p = name().c_str();` 中的 `p` 一出语句就悬垂。
    - 引用直接绑定到临时对象（或其成员）时，临时对象活到引用的生命周期结束。经过函数调用返回的引用不算，这是悬垂引用最常见的来源。
    - 不延长的情形：绑定到函数的引用形参、圆括号聚合初始化、*new-initializer*。在 mem-initializer 和 C++26 的 return 语句里绑定临时对象，现在直接非良构。
    - C++23 起，范围 `for` 初始化器里的临时对象都活到循环结束。

## 什么时候产生临时对象（¶1–¶2）

```cpp run title="guaranteed-elision.cpp" ok
struct NonMovable {
    NonMovable(int) {}
    NonMovable(const NonMovable&) = delete;
    NonMovable(NonMovable&&) = delete;
};

NonMovable make() { return NonMovable(42); }   // OK：prvalue 直接初始化返回对象

int main() {
    NonMovable a = make();                       // OK：没有临时对象
    NonMovable b = NonMovable(NonMovable(1));    // OK：最终只初始化 b 一个对象
    (void)a; (void)b;
}   // C++14 中三处都是错误：需要可访问的复制或移动构造函数
```

表达式按值类别分为 glvalue 和 prvalue（[[basic.lval]]）。glvalue 指代一个已有的对象；**prvalue** 则相当于一份初始化对象的配方，例如 `NonMovable(42)`、`make()`、`1 + 2`。C++17 起，prvalue 本身不是对象，它初始化的那个对象叫它的**结果对象**（result object）。上例中 `make()` 的结果对象就是 `a`，中间没有任何复制。

¶1 规定，**临时对象**（temporary object）只在两种情况下创建：

- ¶1.1 prvalue 被转换为 xvalue 时，即**临时物化转换**（temporary materialization conversion，[[conv.rval]]）；
- ¶1.2 实现为了传递或返回某些类型的对象而需要时，见下一节。

C++17 之前，每个类类型的 prvalue 都是一个临时对象，再复制到目标，复制消除只是允许的优化。[[P0135R1]] 改成了现在的规则，这就是保证复制消除。

### 物化尽可能推迟（¶2）

¶2 规定物化通常尽可能推迟，以免创建不必要的临时对象。注 2 汇总了会发生物化的场合：

| 列表项 | 场合 | 例子 |
|---|---|---|
| ¶2.1 | 引用绑定到 prvalue | `const T& r = T{};` |
| ¶2.2 | 对类 prvalue 做成员访问 | `T{}.member` |
| ¶2.3 | 对类 prvalue 调用隐式对象成员函数 | `T{}.f()` |
| ¶2.4 | 对数组 prvalue 做数组到指针转换或下标 | `id<int[3]>{1, 2, 3}[i]` |
| ¶2.5 | 用花括号列表初始化 `std::initializer_list<T>` | `std::initializer_list<int> il = {1, 2, 3};` |
| ¶2.6 | 某些不求值操作数 | `sizeof(T{})`、`typeid(T{})` |
| ¶2.7 | 非 `void` 的 prvalue 作为弃值表达式 | 表达式语句 `T{};` |

用 prvalue 初始化同类型对象时不物化，例如 `T x = T{};`、`return T{};`，以及用 `f(T{})` 初始化值形参。下面是标准的例 1：

```cpp run title="materialize.cpp" ok
class X {
public:
    X(int) {}
    X(const X&) {}
    X& operator=(const X&) { return *this; }
    ~X() {}
};

X f(X x) { return x; }

int main() {
    X a(1);
    X b = f(X(2));   // X(2) 直接构造在 f 的形参里；f 的结果直接构造在 b 里
    a = f(a);        // f(a) 的结果要物化成临时对象，才能绑定到 operator= 的 const X& 形参
}
```

### 不求值也要检查（¶1）

¶1 第二句规定，即使临时对象的创建不被求值（例如在 `sizeof` 里），也要像真的创建并销毁了它一样遵守所有语义限制。注 1 说明这包括所选构造函数和析构函数是否可访问、是否被删除。唯一的例外是 `decltype` 的操作数：那里的 prvalue 不引入临时对象（[[dcl.type.decltype]]）。

```cpp run title="unevaluated-temp.cpp" error
struct P { private: ~P(); };
P make();

using A = decltype(make());   // OK：decltype 里不引入临时对象
auto n = sizeof(P{});         // error：析构函数不可访问，即使不求值
```

## 为在寄存器里传递而复制（¶3）

把类型 `X` 的对象传给函数或从函数返回时，如果 `X` 是

- ¶3.1 标量类型，或
- ¶3.2 类类型，至少有一个合格的复制或移动构造函数，所有这样的构造函数都是平凡的，并且析构函数是平凡的或被删除的，

实现就可以创建临时对象来保存形参或返回对象（¶3.3–¶3.5 规定了这些临时对象之间依次怎样初始化）。注 3 说明了动机：让对象可以放在寄存器里传递。寄存器没有地址，对象放进寄存器再写回内存，就成了另一个对象。对这样的类型，复制过程中不运行任何用户代码，所以标准干脆允许它。

可观察的后果是，对象的地址在调用前后可能不同：

```cpp run title="register-pass.cpp" unspecified
#include <cstdio>

struct Small { int a, b; };   // 平凡复制、平凡析构

const void* seen;

Small make() {
    Small s{1, 2};
    seen = &s;
    return s;                  // 可能经由寄存器返回
}

int main() {
    Small r = make();
    std::printf("%d\n", seen == &r);   // 未指定；本机 AArch64 上为 0
}
```

!!! impl "ABI 中的对调用而言非平凡"
    Itanium C++ ABI 把不满足 ¶3.2 的类称为对调用而言非平凡（non-trivial for the purposes of calls）。这类对象不能放在寄存器里，由调用者在内存中创建，再传递它的地址。典型的例子是 `std::unique_ptr<T>`：它只有一个指针大小，却因为析构函数非平凡，必须经内存传递，比裸指针多一次内存往返。Clang 的 `[[clang::trivial_abi]]` 可以让类在 ABI 上按平凡类处理。MSVC x64 的规则不同，主要按大小（1、2、4、8 字节）等条件决定。

## 默认活到完整表达式结束（¶4）

¶4 规定，临时对象在词法上包含其创建点的**完整表达式**（full-expression）求值的最后一步销毁，求值以抛出异常结束时也一样。完整表达式大致是不属于其他表达式的表达式（[[intro.execution]]），例如一条表达式语句、一个变量的初始化器、`if` 的条件。所以临时对象活到分号是一个很好的近似：

```cpp run title="end-of-full-expr.cpp" ok
#include <cstdio>
#include <string>

std::string name() { return "temporary"; }

int main() {
    std::printf("%s\n", name().c_str());   // OK：临时 string 活到这条语句结束

    const char* p = name().c_str();         // 临时 string 在这个分号处销毁，p 悬垂
    (void)p;                                // 只要不解引用 p 就没有 UB
}
```

本机 Clang 23 对第二处给出 `-Wdangling-gsl` 警告。

## 引用绑定延长生命周期（¶6）

### 哪些绑定会延长

```cpp run title="extension-yes.cpp" ok
#include <string>

template<class T> using id = T;
struct S { int m; std::string s; };

int main(int argc, char**) {
    int i = 1;
    const std::string& a = std::string("abc");    // ¶6.1
    int&& b = id<int[3]>{1, 2, 3}[i];             // ¶6.3：整个临时数组被延长
    std::string&& c = S{1, "x"}.s;                // ¶6.4：整个 S 被延长
    const int& d = static_cast<const int&>(0);    // ¶6.6
    int&& e = argc > 1 ? id<int[3]>{1, 2, 3}[i]
                       : static_cast<int&&>(0);   // ¶6.8：只延长实际求值的那个
    const int& f = (const int&)1;                 // 注 4：C 风格转换按 static_cast 处理
    return a.size() + b + c.size() + d + e + f > 0 ? 0 : 1;   // 全部 OK
}
```

¶6 规定，引用绑定到临时对象时，如果引用所绑定的 glvalue 是经由下列途径之一得到的，那么这个临时对象（或者引用绑定的子对象所在的那个完整临时对象）活到引用的生命周期结束。这就是**生命周期延长**（lifetime extension）。

| 列表项 | 途径 | 例子 |
|---|---|---|
| ¶6.1 | 临时物化转换 | `const T& r = T{};` |
| ¶6.2 | 括号 `( e )` | `const T& r = (T{});` |
| ¶6.3 | 对数组操作数取下标 | `int&& r = id<int[3]>{1, 2, 3}[i];` |
| ¶6.4 | 用 `.` 访问非引用类型的非静态数据成员，或转到直接基类 | `int&& r = S{}.m;` |
| ¶6.5 | 用 `.*` 访问非引用类型的数据成员指针 | `int&& r = S{}.*pm;` |
| ¶6.6 | 不经用户定义转换、结果仍指向同一对象（或其完整对象、子对象）的四种具名转换 | `static_cast<const int&>(0)` |
| ¶6.7 | 到引用类型、初始化器为花括号列表的函数式转换 | `using R = const T&; R{T{}}` |
| ¶6.8 | 是 glvalue 的条件表达式，第二或第三操作数是上述表达式之一 | `c ? T{1} : T{2}` |
| ¶6.9 | 是 glvalue 的逗号表达式，右操作数是上述表达式之一 | `(f(), T{})` |

除 ¶6.1 外，每一项都要求操作数本身也是这些表达式之一，所以清单是递归的。它刻画的是一类能在编译期看出结果就是某个临时对象（或其子对象）的表达式，[[stmt.return]] 和 [[class.base.init]] 把它们称为**临时表达式**（temporary expression）。

注 5 补充，如果临时对象的引用成员是由另一个临时对象初始化的，延长会递归地作用到那个成员上：

```cpp run title="extension-recursive.cpp" ok
struct S { const int& m; };

int main() {
    const S& s = S{1};   // S 临时对象和 int 临时对象都活到 s 结束
    return s.m;          // OK：1
}
```

### 经过函数调用就不延长

函数（包括成员函数和重载运算符）返回的引用不在 ¶6 的清单里。编译器在调用点看不出返回的引用指向哪里，所以什么也不延长：

```cpp run title="dangling-call.cpp" ub
#include <algorithm>
#include <string>

struct Holder {
    std::string s{"hello"};
    const std::string& get() const { return s; }
};

int main() {
    const int& m = std::max(1, 2);           // 临时 int 绑定到 max 的引用形参，活到分号
    const std::string& g = Holder{}.get();   // 成员函数调用，不是 ¶6.4 的成员访问
    return m + static_cast<int>(g.size());   // UB：两个引用都已悬垂
}
```

`Holder{}.s` 是成员访问，会延长整个 `Holder`；`Holder{}.get()` 是函数调用，不会。把公有成员改成 getter 之后就悬垂了。本机 Clang 23 对 `std::max` 那一行给出 `-Wdangling` 警告，对 `get()` 那一行没有警告；AddressSanitizer 在运行时报告了 stack-use-after-scope。

### 三种不延长的绑定（¶6.10–¶6.12）

即使引用直接绑定到临时对象，下面三种情形也不延长到引用的生命周期：

- ¶6.10 函数调用中绑定到引用形参的临时对象，活到包含该调用的完整表达式结束。形参本来就比这个完整表达式活得短，延长没有意义。
- ¶6.11 用圆括号表达式列表初始化类类型聚合体时，绑定到引用成员的临时对象，活到包含该列表的完整表达式结束 {{c++20}}。
- ¶6.12 *new-initializer* 中绑定到引用的临时对象，活到包含它的完整表达式结束。注 6 指出这可能造成悬垂引用。

<div class="compare" markdown="1">

```cpp run ub
struct A { const int& r; };

int main() {
  A b{42};  // 花括号：延长到 b 结束
  A a(42);  // 圆括号：¶6.11，分号处销毁
  return a.r + b.r;  // UB：读 a.r
}
```

```cpp run ub
#include <utility>
struct S {
  int mi;
  const std::pair<int, int>& mp;
};

int main() {
  S a{1, {2, 3}};           // OK：延长
  S* p = new S{1, {2, 3}};  // ¶6.12
  int r = a.mp.first
        + p->mp.first;      // UB：读 p->mp
  delete p;
  return r;
}
```

</div>

C++20 的圆括号聚合初始化有意模仿构造函数调用。如果 `A` 有一个构造函数 `A(const int&)`，`A a(42)` 中的临时对象属于 ¶6.10，不会延长；¶6.11 让聚合体的行为与之保持一致。

### 已改为非良构的两种绑定

¶6 的例外清单过去还有两项，现在都已改为非良构，编译器必须报告：

1. 在构造函数的 mem-initializer 中把引用成员绑定到临时对象（[[class.base.init#8]]）。原来的规则是临时对象活到构造函数退出，结果必然悬垂。在默认成员初始化器里这样做同样非良构（[[class.base.init#13]]），但只在它实际被用于初始化时才算。
2. return 语句把返回的引用绑定到临时对象（[[stmt.return#6]]）{{c++26}}。C++23 中这样写合法，但必然返回悬垂引用。这一改动来自 [[P2748R5]]。

```cpp run title="now-ill-formed.cpp" error
struct A {
    A() : v(42) {}            // error：mem-initializer 中引用成员绑定到临时对象
    const int& v;
};

const int& f() { return 42; }        // error（C++26）：返回的引用绑定到临时对象
auto&& g() { return 42; }            // error（C++26）
const double& h() {
    static int x = 42;
    return x;                        // error（C++26）：int 转 double 产生临时对象
}
```

本机 Clang 23 在 `-std=c++2c` 下对 `f`、`g`、`h` 都报错（returning reference to local temporary object），在 `-std=c++23` 及更早的模式下只给出警告。

!!! lawyer "return 的新规则也只认临时表达式"
    [[stmt.return]] 的例子里还有这样一段：

    ```cpp
    auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
    auto&& f3() { return id(42); }   // OK，但几乎肯定是 bug
    ```

    `id(42)` 是函数调用，不是临时表达式，新规则管不到，道理与 ¶6 不延长函数调用的结果相同。基于 `[[clang::lifetimebound]]` 等注解的 `-Wdangling` 类警告在这方面走得更远。

## 其他例外语境（¶5、¶7–¶10）

标准一共列了七种临时对象不在完整表达式结束时销毁的语境，引用绑定是第三种。其余六种如下。

### 数组元素的默认实参（¶5）

第一、二种语境：用默认构造函数初始化没有对应初始化器的数组元素时；复制整个数组（例如 lambda 按值捕获数组、隐式复制构造函数复制数组成员）而逐个复制元素时。在这两种情况下，如果构造函数有默认实参，默认实参里创建的临时对象在构造下一个元素之前就销毁。否则一个 1000 个元素的数组会在一个完整表达式里累积 1000 个临时对象。

```cpp run title="array-default-arg.cpp" ok
#include <cstdio>

struct Tmp { Tmp() { std::puts("Tmp()"); } ~Tmp() { std::puts("~Tmp()"); } };
struct E { E(const Tmp& = Tmp()) { std::puts("E()"); } };

int main() {
    E arr[2];   // 输出：Tmp() E() ~Tmp() Tmp() E() ~Tmp()
}
```

### 范围 `for` 的初始化器（¶7）{{c++23}}

第四种语境：在范围 `for` 的 *for-range-initializer*（冒号右边的表达式）中创建的临时对象，如果原本会在它结束时销毁，现在活到由它初始化的那个引用的生命周期结束，也就是整个循环结束。

范围 `for` 的定义里有一句 `auto&& __range = for-range-initializer;`（[[stmt.ranged]]）。按 ¶6，只有初始化器本身是临时表达式时临时对象才会延长，中间只要经过一次函数调用就会悬垂：

```cpp run title="range-for.cpp" ok
#include <cstdio>
#include <vector>

struct T {
    std::vector<int> v{1, 2, 3};
    ~T() { std::puts("~T"); }
    const std::vector<int>& items() const { return v; }
};
T make() { return {}; }

int main() {
    for (int x : make().items())   // C++20：临时 T 在循环开始前销毁，UB
        std::printf("%d\n", x);    // C++23：临时 T 活到循环结束，OK
    std::puts("end");
}
```

本机 Clang 23 在 `-std=c++20` 下先输出 `~T` 再进入循环，读到的是已销毁的数据；在 `-std=c++23` 下先输出 1 2 3 再输出 `~T`。这一改动来自 [[P2718R0]]，只在 C++23 及以后的模式下生效。

### 展开语句（¶8–¶9）{{c++26}}

第五、六种语境针对 C++26 的展开语句 `template for`（[[stmt.expand]]）：

- ¶8 枚举形式 `template for (auto x : {a, b, c})` 中，在列表的某个元素 E 里创建的临时对象，如果原本会在 E 的完整表达式结束时销毁，现在活到由 E 初始化的那个循环变量的生命周期结束。
- ¶9 迭代形式和解构形式中，在初始化器里创建的临时对象，如果原本会在初始化器结束时销毁，现在活到由它初始化的引用（如果有）的生命周期结束。

!!! warning "实现状态"
    本机 Clang 23 支持 `template for`，但这两条还没有正确实现。`template for (int y : tup(T{5}))`（`tup` 以 `const T&` 接收参数，返回 `std::tuple`）中，`T{5}` 在循环体执行之前就销毁了，与 ¶9 不符；枚举形式里写 `{T{7}.v, 8}` 则直接让编译器崩溃。目前不要依赖这里的延长行为。

### 结构化绑定（¶10）{{c++26}}

第七种语境：在结构化绑定声明（[[dcl.struct.bind]]）中，为那些具有唯一名字的隐藏变量的初始化器引入的临时对象，在整个结构化绑定声明结束时才销毁。这些隐藏变量就是元组式绑定中保存 `get<i>(e)` 结果的引用。这样，几次 `get<i>` 调用之间可以安全地共享临时对象，销毁时点也明确。

## 销毁顺序（¶11–¶12）

¶11 规定了三层顺序：

1. 设 x、y 是两个未被延长的临时对象或函数形参。如果它们在同一个完整表达式结束时销毁，且 x 先于 y 初始化，那么 y 先于 x 销毁。
2. 两个以上被延长、在同一时点结束的临时对象，按构造完成的逆序销毁。
3. 被延长的临时对象还要和同存储期的其他对象一起排序：在它之前创建的同存储期对象后于它销毁，在它之后创建的先于它销毁。换句话说，被延长的临时对象就像一个在其创建点定义的同存储期变量。

¶12 的例 6 演示了这一点：

```cpp run title="destruction-order.cpp" ok
#include <cstdio>

struct S {
    int id;
    S(int i = 0) : id(i) { std::printf("S(%d)\n", id); }
    friend S operator+(const S& a, const S& b) { return S(a.id + b.id); }
    ~S() { std::printf("~S(%d)\n", id); }
};

S obj1(1);
const S& cr = S(16) + S(23);   // S(16)、S(23) 绑定到引用形参，分号处逆序销毁
                               // 结果 S(39) 绑定到 cr，活到程序结束
S obj2(2);

int main() {}
// 程序结束时：~S(2) → ~S(39) → ~S(1)
```

`S(16)` 和 `S(23)` 谁先创建是未指定的（[[expr.call]]），但先创建的那个后销毁。本机 Clang 23 先创建 `S(16)`，输出的销毁顺序是 `~S(23)`、`~S(16)`。

## 实现视角

!!! impl "编译器怎样实现生命周期延长"
    - 被延长的临时对象就是一个隐藏的局部变量，绑定到静态引用时是隐藏的静态变量：`const T& r = T{};` 大致等价于 `T __tmp{}; const T& r = __tmp;`。Itanium ABI 还为静态引用绑定的临时对象规定了修饰名，前缀是 `_ZGR`（reference temporary）。
    - 延长在编译期按语法结构决定，所以不可能穿过函数调用：编译器在调用点看不到返回的引用指向哪个对象。这是 ¶6 的清单只包含内置运算的根本原因。
    - Clang 的 `-Wdangling`、`-Wdangling-gsl`、`-Wreturn-stack-address` 和 `[[clang::lifetimebound]]` 注解，GCC 的 `-Wdangling-reference`，都是在标准规则之外用启发式方法捕获悬垂引用的工具。

## 历史与演进

!!! history
    - C++98：类类型右值的很多场合都会产生临时对象。引用延长规则已经存在，例外包括构造函数初始化列表中的引用成员（活到构造函数退出）、函数调用的引用形参、return 语句（活到函数退出）。
    - C++11：引入右值引用和 xvalue，延长规则同样适用于右值引用。
    - C++17：[[P0135R1]] 保证复制消除，prvalue 不再是临时对象，引入临时物化转换。同一时期，在 mem-initializer 中把引用成员绑定到临时对象改为非良构（[[CWG1696]]）。
    - C++20：圆括号聚合初始化带来 ¶6.11 的例外。
    - C++23：[[P2718R0]] 让范围 `for` 初始化器中的临时对象活到循环结束。
    - C++26：[[P2748R5]] 让 return 语句中引用绑定到临时对象变为非良构；展开语句和结构化绑定各自有了临时对象的销毁规则。

## 常见误解

!!! pitfall "`std::string_view` 也能延长临时对象"
    `std::string_view sv = std::string("abc");` 中的 `sv` 是对象，不是引用，¶6 不适用。临时 `string` 在分号处销毁，`sv` 悬垂。生命周期延长只对引用有效。

!!! pitfall "`auto&&` 能接住任何东西"
    `auto&& x = make().value();` 经过了成员函数调用（`std::optional<T>::value()` 返回 `T&&`），不延长，`x` 悬垂。改为按值接收：`auto x = make().value();`。

!!! pitfall "`const T&` 成员能保存临时对象"
    `struct W { const std::string& s; W(const std::string& s) : s(s) {} };  W w(std::string("x"));` 中，临时 `string` 绑定到构造函数的引用形参（¶6.10），在分号处销毁，`w.s` 悬垂。`s(s)` 绑定的是形参，一个左值，不是临时表达式，所以编译器不会按 [[class.base.init#8]] 报错。

## 思考题

!!! question "思考题 1"
    以下哪些引用悬垂？

    ```cpp
    struct P { int x; int& rx() { return x; } };
    P make();
    const int& a = make().x;                     // (a)
    const int& b = make().rx();                  // (b)
    const int& c = static_cast<P&&>(make()).x;   // (c)
    const int& d = true ? make().x : 0;          // (d)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 不悬垂：¶6.4 的成员访问，整个 `P` 临时对象被延长。

(b) 悬垂：成员函数调用的结果不在 ¶6 的清单中。

(c) 不悬垂：`make()` 被物化（¶6.1），`static_cast<P&&>` 不经用户定义转换、结果指向同一对象（¶6.6），再做成员访问（¶6.4）。

(d) 不悬垂，但理由不同。第二操作数 `make().x` 是 xvalue，第三操作数 `0` 是 prvalue，值类别不同，条件表达式的结果是 prvalue（[[expr.cond]]）。于是 `d` 绑定到由这个结果物化出的新临时 `int`（¶6.1），被延长的是这个新对象；`make()` 返回的 `P` 在分号处销毁，但 `d` 并不引用它。
</details>

!!! question "思考题 2"
    为什么 C++17 起 `NonMovable x = NonMovable(1);` 合法，而 `NonMovable x = std::move(NonMovable(1));` 不合法？

<details markdown="1">
<summary>答案</summary>

前者的初始化器是同类型的 prvalue，直接以 `x` 为结果对象，不涉及复制或移动。后者中，`std::move` 的形参是引用，实参 `NonMovable(1)` 必须先物化成临时对象（¶2.1）才能绑定；`std::move` 返回 xvalue，用 xvalue 初始化 `x` 要调用移动构造函数，而它被删除了。即使类型可以移动，这样写也会多一次移动。
</details>

!!! question "思考题 3"
    `for (auto& x : std::vector<std::string>{"a", "b"})` 在 C++20 中会悬垂吗？`for (char c : std::string("ab").substr(0))` 呢？

<details markdown="1">
<summary>答案</summary>

第一个不会：`__range` 直接绑定到由 prvalue 物化的临时 `vector`（¶6.1），在任何标准下都会延长。

第二个也不会：`.substr(0)` 按值返回一个新的 `string`，`__range` 绑定到它，它被延长。原来的 `string("ab")` 在 C++20 中于初始化器结束时销毁，但循环只用到 `substr` 的结果。真正会悬垂的是返回引用的情形，例如 `for (char c : make().name())`（`name()` 返回 `const std::string&`），它在 C++20 中是 UB，在 C++23 中没有问题。
</details>

## 小结

| 问题 | 规则 |
|---|---|
| 何时创建 | 物化时；或为了在寄存器中传参、返回（平凡复制的类型） |
| 何时不创建 | 用 prvalue 初始化同类型对象（C++17 起保证） |
| 默认何时销毁 | 完整表达式求值的最后一步，后构造的先销毁 |
| 延长 | 引用经 ¶6.1–¶6.9 的内置运算直接绑定到临时对象或其子对象 |
| 不延长 | 经函数调用；绑定到函数的引用形参（¶6.10）；圆括号聚合初始化（¶6.11）；*new-initializer*（¶6.12） |
| 非良构 | mem-initializer 或默认成员初始化器绑定临时对象；return 绑定临时对象（C++26） |
| 其他语境 | 数组元素的默认实参（¶5）；范围 `for`（C++23）；展开语句、结构化绑定（C++26） |
