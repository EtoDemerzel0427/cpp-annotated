---
title: 联合体
summary: 联合体在任一时刻至多有一个活跃成员；对成员赋值何时会切换活跃成员，带 std::string 这类成员时怎样手动管理生命周期；公共初始序列特例、匿名联合体和变体成员。
status: done
covers: class.union.general, class.union.anon
papers: P0137R1, P1330R0, P3074R7
related: basic.life, intro.object, class.mem, class.default.ctor, class.dtor, class.copy.ctor, dcl.init.aggr, expr.const.core, obj.lifetime
tags: 联合体, 对象模型, 生命周期, UB, constexpr
updated: 2026-10-19
---

!!! tldr
    - 联合体的成员共用同一块存储，任一时刻至多一个成员处于生命周期内，这个成员叫活跃成员。读取非活跃成员是未定义行为，写 `float` 读 `uint32_t` 的类型双关在 C++ 中不成立，应改用 `std::bit_cast`。
    - 用内置赋值给 `int` 这类简单成员赋值，会先让它成为活跃成员再赋值。成员是 `std::string` 这类带非平凡构造函数的类型时，只能先手动析构旧成员，再用 placement new 或 `std::construct_at` 构造新成员。
    - 成员有非平凡的复制、移动操作时，联合体的相应函数被删除。C++26 起，联合体的默认构造函数和析构函数不再因为成员非平凡而被删除，但截至 Clang 23 还没有实现。
    - 标准布局联合体中，几个结构体成员开头相同的那几个成员（公共初始序列）可以通过任一个结构体读取。
    - 匿名联合体的成员名字直接属于外层作用域；联合体和匿名联合体的成员统称变体成员，至多一个可以有默认成员初始化器。

## 活跃成员（¶1–¶2）

```cpp run title="inactive-read.cpp" ub
union U { int i; float f; };

int main() {
    U u{.i = 1};     // 活跃成员：i
    float x = u.f;   // UB: u.f 不在生命周期内
    return x > 0;
}
```

¶1 联合体（union）就是用 `union` 关键字定义的类。它可以有成员函数、构造函数、析构函数和访问说明符，在重载决议、模板推导中也和 `struct` 一样处理，只是成员默认是 public。本页讲的是它与普通类不同的地方。

¶2 联合体的非静态数据成员共用同一块存储。如果一个成员的名字指代的对象正处在生命周期内（[[basic.life]]），就说这个成员是**活跃的**（active）。同一时刻至多一个成员是活跃的，也就是说联合体里至多存着一个成员的值。也可能一个都没有，例如 `U u;` 没有初始化任何成员时。

!!! std
    In a union, a non-static data member is *active* if its name refers to an object whose lifetime has begun and has not ended.

活跃与否不是联合体里某个隐藏的标志，它完全由生命周期决定。切换活跃成员，就是结束旧成员的生命周期、开始新成员的生命周期。读取非活跃成员，就是对一个不在生命周期内的对象做左值到右值转换，[[basic.life#8]] 规定这是未定义行为。

### 类型双关在 C++ 中不成立

C 语言允许写一个成员、读另一个成员，效果是把同样的字节按新类型重新解释。C++ 没有采纳这条规则：每个成员都是一个独立的对象，读取一个不在生命周期内的对象没有确定的含义；何况成员可能是带不变式的类类型，把字节按它重新解释并不安全。

```cpp run title="type-punning.cpp" ub
#include <cstdint>

union Pun { float f; std::uint32_t u; };

std::uint32_t bits_bad(float x) {
    Pun p;
    p.f = x;
    return p.u;      // UB: 活跃成员是 f
}

int main() { return bits_bad(1.0f) == 0x3f800000 ? 0 : 1; }
```

GCC 明确把这种写法作为扩展来支持，Clang 的行为与之一致，所以它在实践中能运行；但在常量求值中两者都会拒绝，而且它不是可移植的 C++。可移植的写法是 C++20 的 `std::bit_cast` 或 `std::memcpy`：

```cpp run title="bit-cast.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t bits(float x) {
    return std::bit_cast<std::uint32_t>(x);
}
static_assert(bits(1.0f) == 0x3f800000);   // 编译期也可以用

int main() { }
```

## 用赋值切换活跃成员（¶5）

给 `union U { int i; float f; } u{.i = 1};` 写 `u.f = 2.0f;` 合法吗？按 [[basic.life]]，`u.f` 此时不在生命周期内，对它赋值就是在生命周期外修改对象，本应是 UB。但 C 和 C++ 代码一直都这样写。¶5 为这种写法提供了依据：在满足条件时，赋值会先在那块存储里创建一个 `f`，再给它赋值。

```cpp run title="assign-switch.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};
    u.f = static_cast<float>(u.i);   // 先读 i，再创建 f，再赋值
    return u.f == 1.0f ? 0 : 1;      // OK: f 是活跃成员
}
```

### 规则

¶5 对使用内置赋值运算符或平凡赋值运算符的赋值 `E1 = E2`，标准从左操作数 `E1` 中挑出一组联合体成员访问，记作 S(E1)。对其中每个元素 X，如果按 [[basic.life]] 修改 X 是 UB（X 不在生命周期内），就：

- 在 X 指名的存储中隐式创建一个 X 类型的对象；
- 不进行任何初始化；
- 让它的生命周期在左右两个操作数求值之后、赋值之前开始。

注 4 补充，这会结束联合体先前活跃成员的生命周期。规则还覆盖了以 S(E1) 中的元素为直接子对象（逐层向外）的匿名联合体成员。

S(E) 递归地定义如下：

- ¶5.1 `E` 形如 `A.B`：S(E) 包含 S(A) 的全部元素。此外，如果 `B` 是一个联合体成员，类型是非类非数组类型、带平凡且未删除的默认构造函数的类类型，或者这些类型的数组，`A.B` 本身也加入。
- ¶5.2 `E` 形如 `A[B]`，且是内置下标：如果 `A` 是数组，S(E) = S(A)；如果 `B` 是数组（`i[arr]` 写法），S(E) = S(B)；否则为空。`A` 是指针时链条在这里中断。
- ¶5.3 其他形式：S(E) 为空。

这几个条件各有道理：

1. 只接受平凡且未删除的默认构造函数，因为新对象不经初始化就开始了生命周期。只有当什么都不做本来就是这个类型的合法默认初始化时，这样凭空出现的对象才不会破坏类型的不变式。`std::string` 这样的类型不能无中生有。
2. 只接受内置赋值或平凡赋值。用户定义的 `operator=` 是一次普通的成员函数调用，它的 `this` 必须指向生命周期内的对象；平凡赋值只是复制字节，在未初始化的新对象上执行没有问题。
3. 新对象的生命周期在右操作数求值之后才开始，所以 `u.f = u.i;` 这种读旧成员、写新成员的写法是合法的：读 `u.i` 时它仍然活跃。

### 嵌套和数组

标准例 2 展示了 S(E) 怎样沿着成员访问一路向外：

```cpp run title="nested-union-assign.cpp" ok
union A { int x; int y[4]; };
struct B { A a; };
union C { B b; int k; };

constexpr int f() {
    C c;                  // 没有任何成员的生命周期开始
    c.b.a.y[3] = 4;       // OK: 创建 c.b 和 c.b.a.y
    return c.b.a.y[3];    // OK
}
static_assert(f() == 4);  // 常量求值中同样成立

int main() { return f() == 4 ? 0 : 1; }
```

逐层计算 S(`c.b.a.y[3]`)：

1. 这是 `A[B]` 形式，`c.b.a.y` 是数组，所以结果等于 S(`c.b.a.y`)。
2. `c.b.a.y` 是 `A.B` 形式，`y` 是联合体 `A` 的成员，类型是 `int` 数组，加入。
3. `c.b.a` 中的 `a` 是结构体 `B` 的成员，不是联合体成员，不加入。
4. `c.b` 中的 `b` 是联合体 `C` 的成员，`B` 有平凡的默认构造函数，加入。

结果是 {`c.b`, `c.b.a.y`}，这两个对象都被隐式创建，分别成为各自联合体的活跃成员。

### 规则不适用的情况

例 2 的后半部分：

```cpp run title="const-member-no-switch.cpp" ub
struct X { const int a; int b; };
union Y { X x; int k; };

int main() {
    Y y = { { 1, 2 } };   // OK: y.x 是活跃成员
    int n = y.x.a;
    y.k = 4;              // OK: 结束 y.x，y.k 成为活跃成员
    y.x.b = n;            // UB: y.x 不会被重新创建
    return y.x.b;
}
```

`X` 有一个没有初始化器的 `const` 成员，所以它的默认构造函数被删除（[[class.default.ctor#2]]），`y.x` 不满足 ¶5.1；`b` 是结构体成员而不是联合体成员。于是 S(`y.x.b`) 为空，没有对象被创建，`y.x.b = n` 修改的是生命周期外的对象。

!!! impl "Clang 在常量求值中漏掉了这个 UB"
    把上面的代码改写成 `constexpr` 函数并在 `static_assert` 中调用，Clang 23 不报错，直接接受。按标准这是 UB，常量求值必须拒绝（[[expr.const.core]]）。对于默认构造函数非平凡的成员，Clang 则会正确报告"对非活跃成员赋值"。

用户定义的赋值运算符同样不会触发切换：

```cpp run title="user-assign-no-switch.cpp" ub
struct P {
    int v;
    P& operator=(int x) { v = x; return *this; }   // 不是平凡赋值
};
union U { int i; P p; };

int main() {
    U u{.i = 0};
    u.p = 5;     // UB: 调用 P::operator= 时 u.p 不在生命周期内
    return u.p.v;
}
```

另外，[[obj.lifetime]] 中的 `std::start_lifetime(r)` 可以显式开始一个联合体成员的生命周期，使它成为活跃成员，不初始化任何东西。它要求成员类型是隐式生命周期的聚合类型。

## 带非平凡成员的联合体（¶4 注 3、¶6）

C++11 起，联合体的成员可以是 `std::string` 这样带非平凡特殊成员函数的类型。联合体不知道哪个成员是活跃的，所以编译器无法替它生成正确的复制、移动和析构。¶4 注 3 说明了标准的处理：如果某个成员的复制构造、移动构造、复制赋值或移动赋值是非平凡的，联合体的相应函数必须由用户提供，否则被定义为删除的（[[class.copy.ctor]]、[[class.copy.assign]]）。

¶6 注 5 指出，¶5 不适用时，只能用 placement new（或等价的 `std::construct_at`）切换活跃成员。例 3 给出的做法是先析构旧成员，再构造新成员：

```cpp
u.m.~M();
new (&u.n) N;
```

下面是一个完整的带标签联合体，相当于一个简化的 `std::variant`：

```cpp run title="tagged-union.cpp" ok
#include <memory>
#include <string>
#include <utility>

class IntOrString {
    enum class Kind { Int, Str } kind_ = Kind::Int;
    union { int i_ = 0; std::string s_; };   // i_ 默认活跃

    void destroy() {
        if (kind_ == Kind::Str) std::destroy_at(&s_);
    }

public:
    IntOrString() {}                // 必须由用户提供
    ~IntOrString() { destroy(); }   // 只析构活跃成员
    IntOrString(const IntOrString&) = delete;
    IntOrString& operator=(const IntOrString&) = delete;

    void set(int v) {
        destroy();
        i_ = v;                     // ¶5：int 可以直接赋值
        kind_ = Kind::Int;
    }
    void set(std::string v) {
        if (kind_ == Kind::Str) {   // 已经是 string：普通赋值
            s_ = std::move(v);
            return;
        }
        std::construct_at(&s_, std::move(v));   // ¶6：只能这样
        kind_ = Kind::Str;
    }
    const std::string* str() const {
        return kind_ == Kind::Str ? &s_ : nullptr;
    }
};

int main() {
    IntOrString x;
    x.set("hello, union");
    x.set(42);
    x.set("again");
    return x.str() ? 0 : 1;
}
```

几个要点：

- `s_ = std::move(v)` 只能在 `s_` 已经活跃时使用。`std::string::operator=` 是用户提供的，不会触发 ¶5。
- 析构函数靠 `kind_` 知道该析构哪个成员，联合体自己不记录这件事。
- `kind_` 在 `construct_at` 成功之后才改。如果构造抛出异常，`kind_` 仍是 `Int`，析构函数不会去析构一个不存在的 `s_`；不过此时联合体里实际上没有活跃成员。`std::variant` 的 `valueless_by_exception` 状态就是为这种情况设的。

### C++26 的平凡联合体 {{c++26}}

注 3 的例子是 `union U { int i; float f; std::string s; };`。它的复制、移动操作都被删除；但按当前草案，它的默认构造函数和析构函数都是平凡的，尽管 `std::string` 的相应函数非平凡。

C++23 及以前不是这样：`U` 的默认构造函数和析构函数也被删除，`U u;` 直接非良构，必须手写 `U() {}` 和 `~U() {}`。[[P3074R7]] 改了两处：

- [[class.default.ctor#3]]：判断默认构造函数是否平凡时，联合体不再考察成员的类型（¶3.4）。联合体的默认构造函数本来就不构造任何成员。
- [[class.dtor#7]]：联合体的默认析构函数只在两种情况下被删除。一是默认初始化选中的构造函数被删除或非平凡（¶7.2.1）；二是某个带默认成员初始化器的变体成员有非平凡析构函数（¶7.2.2）。如果默认构造会让某个成员活跃，什么都不做的析构函数就可能漏掉它，所以要删除；默认构造什么都不做时，析构什么都不做也就是一致的。

改动的动机是 `std::inplace_vector<T, N>` 这类先有存储、后构造元素的类型。过去要写 `union { T storage[N]; }` 并手写空的构造函数和析构函数，而用户提供的构造、析构函数会让整个类型不再平凡，在常量求值中也更难用。

```cpp run title="trivial-union.cpp"
#include <memory>
#include <string>
#include <type_traits>

union U { int i; std::string s; };

// C++26：默认构造与析构都是平凡的
static_assert(std::is_trivially_default_constructible_v<U>);
static_assert(std::is_trivially_destructible_v<U>);
static_assert(!std::is_copy_constructible_v<U>);   // 复制仍被删除

int main() {
    U u;                               // 没有活跃成员
    std::construct_at(&u.s, "hello");  // s 成为活跃成员
    std::destroy_at(&u.s);             // 必须手动结束，否则泄漏
}
```

按 C++26 这段代码是良构的。本机 Clang 23 还没有实现 [[P3074R7]]，前两个 `static_assert` 失败，`U u;` 被报告为调用了被删除的默认构造函数，所以这里没有标注判定。在编译器支持之前，可移植的写法是像上面的 `IntOrString` 那样手写构造函数和析构函数。

!!! lawyer "带默认成员初始化器的平凡成员"
    按 [[class.default.ctor#3]] ¶3.2，有成员带默认成员初始化器时，默认构造函数不是平凡的；而 ¶7.2.1 说默认初始化选中非平凡构造函数时，联合体的析构函数被删除。逐字读下来，`union X { int i = 0; float f; };` 的析构函数也会被删除，尽管所有成员都是平凡的。这会让大量既有代码失效，多半不是本意，读这一段时要留意草案的后续修订。

## 公共初始序列（¶2 注 1）

¶2 注 1 提到一条为方便使用联合体而设的保证，正式规则在 [[class.mem.general#30]]：

```cpp run title="common-initial-sequence.cpp" ok
struct T1 { int a, b; };
struct T2 { int c; double d; };
union U { T1 t1; T2 t2; };

int f() {
    U u = { { 1, 2 } };   // 活跃成员是 t1
    return u.t2.c;        // OK: 如同读 u.t1.a
    // return (int)u.t2.d; // UB: d 不在公共初始序列中
}

int main() { return f() == 1 ? 0 : 1; }
```

两个标准布局结构体的**公共初始序列**（common initial sequence）是从第一个成员开始、对应成员类型布局兼容的最长前缀（精确条件见 [[class.mem.general#27]]，还要求对齐、位域宽度相同等）。在标准布局联合体中，如果活跃成员是结构体 `T1`，就可以通过另一个结构体成员 `T2` 读取公共初始序列里的成员，效果如同读取 `T1` 中对应的成员。

这条规则保留了 C 语言中带标签联合体的常见写法：每个成员结构体都以同一个标签字段开头，不管当前活跃的是哪个，都可以先读标签。

```cpp run title="tagged-cis.cpp" ok
enum Kind { K_INT, K_STR };
struct Any  { Kind kind; };
struct IntV { Kind kind; int value; };
struct StrV { Kind kind; const char* value; };
union Value { Any any; IntV i; StrV s; };

int get(const Value& v) {
    switch (v.any.kind) {     // 不论活跃的是 i 还是 s 都合法
    case K_INT: return v.i.value;
    case K_STR: return v.s.value[0];
    }
    return -1;
}

int main() {
    Value v{.i = {K_INT, 42}};
    return get(v) == 42 ? 0 : 1;
}
```

这条特例只允许读，不允许写；只适用于结构体成员。`union { int i; float f; }` 里的 `int` 和 `float` 不是结构体，谈不上公共初始序列。

!!! impl "Clang 在常量求值中不支持这条特例"
    把上面的 `f` 改成 `constexpr` 并在常量表达式中调用，Clang 23 报告读取了非活跃成员 `t2`。按标准，这次读取如同指名了 `t1` 的对应成员，不属于 [[expr.const.core]] 禁止的读取非活跃成员。这是实现的限制。

## 布局与限制（¶3–¶4）

¶3 联合体的大小足以容纳最大的成员，每个成员都像是某个非联合体类的唯一成员那样分配。注 2 指出，联合体对象和它的每个成员都是**指针可互转换**的（pointer-interconvertible，[[basic.compound]]）：指向其中一个的指针可以用 `reinterpret_cast` 或 `static_cast` 经 `void*` 直接得到指向另一个的指针。所以所有成员的地址都相同，都等于联合体的地址。

```cpp run title="union-address.cpp" ok
#include <cassert>

union U { char c; int i; double d; };
static_assert(sizeof(U) >= sizeof(double));
static_assert(alignof(U) >= alignof(double));

int main() {
    U u{.i = 7};
    assert((void*)&u.c == (void*)&u.d);
    int* p = reinterpret_cast<int*>(&u);   // 指向活跃成员 u.i
    assert(*p == 7);
}
```

标准没有规定 `sizeof(U)` 恰好等于最大成员的大小，末尾可以有填充。主流 ABI 中它等于最大成员的大小向上取整到最严格的对齐。

¶4 联合体可以有成员函数，包括构造函数和析构函数，但有四条限制：

| 规则 | 原因 |
|---|---|
| 不能有虚函数 | 联合体不能被派生，虚函数没有用处；虚表指针还会和成员抢首地址 |
| 不能有基类 | 基类子对象一直存在，与至多一个成员活跃的模型冲突 |
| 不能作为基类 | 同上 |
| 不能有引用类型的成员 | 引用不是对象，没有可以切换的存储 |

```cpp title="union-restrictions.cpp" error
struct B {};
union U1 : B { int i; };          // error: 联合体不能有基类
union U2 { int i; };
struct D : U2 {};                 // error: 联合体不能作为基类
union U3 { virtual void f(); };   // error: 联合体不能有虚函数
union U4 { int& r; };             // error: 引用类型成员
```

## 常量求值与复制

联合体在常量求值中的规则在 [[expr.const.core]] 中：

- 读取非活跃成员（对它做左值到右值转换）不是核心常量表达式（¶2.11），所以常量求值必须发现这种 UB。
- C++20 起（[[P1330R0]]），常量求值中可以通过 ¶5 的赋值切换活跃成员。
- 平凡地复制或移动联合体时，常量求值把它看作复制活跃成员（¶7）。

```cpp run title="constexpr-union.cpp" ok
constexpr int ok() {
    union W { int a; float b; };
    W w{.a = 1};
    w.b = 2.0f;          // C++20 起常量求值中允许
    return (int)w.b;
}
static_assert(ok() == 2);

constexpr int bad() {
    union W { int a; float b; };
    W w{.a = 1};
    return (int)w.b;     // 读非活跃成员
}
// static_assert(bad() == 0);   // error: 不是常量表达式

int main() { }
```

`std::optional`、`std::variant` 能在 `constexpr` 中使用，靠的就是这些规则。

运行时复制联合体时，隐式定义的复制、移动构造函数（存在且未被删除时）复制对象表示，并为源对象中的每个对象在目标中创建对应的对象（[[class.copy.ctor#16]]）。所以 `U v = u;` 之后，`v` 的活跃成员与 `u` 相同。

## 匿名联合体 [class.union.anon]

```cpp run title="anon-union.cpp" ok
#include <cstring>

int main() {
    union { int a; const char* p; };   // 匿名联合体
    a = 1;                             // 像普通变量一样使用
    p = "Jennifer";                    // p 成为活跃成员
    return std::strlen(p) == 8 ? 0 : 1;
}
```

¶1 形如 `union { 成员 } ;` 的声明是**匿名联合体**（anonymous union）。它定义了一个无名类型和这个类型的一个无名对象：对象是非静态数据成员时叫匿名联合体成员，否则叫匿名联合体变量。这个类型不能有别的对象。匿名联合体的成员名字绑定在联合体声明所在的作用域，所以像普通变量（或外层类的成员）一样直接使用，只是彼此共享地址。

匿名联合体中的声明只能是 public 非静态数据成员、空声明或 `static_assert`。它不能声明函数，也不能声明嵌套类型，包括 lambda 的闭包类型和嵌套的匿名联合体。原因是匿名联合体没有名字，外面没法写 `Anon::f`；它只是一组共享存储的变量。

```cpp title="anon-union-restrictions.cpp" error
struct S {
    union { int a; float b; };              // OK
    union { int c; private: int d; };       // error: 必须是 public
    union { int e; void f(); };             // error: 不能声明函数
    union { int g; struct N {} n; };        // error: 不能声明嵌套类型
    union { int h; static_assert(true); };  // OK
};
```

¶2 存储类说明符的规则：

| 位置 | 规则 |
|---|---|
| 具有外部链接的命名空间（包括全局命名空间） | 必须带 `static` |
| 块作用域 | 只能用块变量允许的说明符，如 `static`、`thread_local` |
| 类作用域 | 不能有存储类说明符 |

全局的匿名联合体变量没有名字，别的翻译单元不可能引用它。要求 `static` 使它具有内部链接，各翻译单元之间就不需要对应了。无名命名空间本身没有外部链接，其中的匿名联合体不必带 `static`。

```cpp title="anon-union-storage.cpp" error
union { int ga; };                  // error: 必须是 static
static union { int sa; };           // OK
namespace { union { int na; }; }    // OK: 无名命名空间

void f() {
    static union { int s1; };       // OK
    thread_local union { int s2; }; // OK
}

struct C {
    static union { int x; };        // error: 类作用域不能有
};
```

¶3 注 1 指出，在 `union { … }` 后面声明了对象、指针或引用时，它就不是匿名联合体，成员只能通过对象访问：

```cpp title="not-anonymous.cpp" error
void f() {
    union { int aa; char* p; } obj, *ptr = &obj;
    aa = 1;           // error: aa 不在这个作用域中
    ptr->aa = 1;      // OK
}
```

注 2 指向 [[dcl.init.aggr]]：没有用户声明构造函数的联合体是聚合，花括号初始化默认初始化第一个成员，也可以用指派初始化器 `{.f = 1.0f}` 选择别的成员。

## 类联合类与变体成员（¶4）

```cpp
struct Tagged {
    int tag;                      // 普通成员
    union { int i; double d; };   // i、d 是 Tagged 的变体成员
};                                // Tagged 是类联合类
```

¶4 **类联合类**（union-like class）是联合体，或者以匿名联合体为直接成员的类。它的**变体成员**（variant member）包括：联合体自己的非静态数据成员（匿名联合体除外），以及作为它的成员的匿名联合体里的非静态数据成员。上例中 `i` 和 `d` 是变体成员，`tag` 不是。

许多规则需要区分一定存在的成员和可能不活跃的成员，这时就用到这个概念。例如判断默认构造函数和析构函数是否被删除时，变体成员另行处理（[[class.default.ctor#2]]、[[class.dtor#7]]）；类的析构函数不会析构变体成员，因为它们可能根本不活跃（[[class.dtor]]）；构造函数的 *mem-initializer* 对一个联合体至多初始化一个变体成员（[[class.base.init]]）。

¶4 最后一句规定，一个联合体中至多一个变体成员可以有默认成员初始化器，因为默认构造只能让一个成员活跃。匿名联合体的成员也计入外层联合体：

```cpp title="one-dmi.cpp" error
union U {
    int x = 0;
    union {
        int k;
    };
    union {
        int z;
        int y = 1;      // error: U 的第二个带初始化器的变体成员
    };
};
```

对 `Tagged` 这样不是联合体的类联合类，每个匿名联合体是一个独立的联合体，各自至多一个初始化器。

## 实现视角

!!! impl
    - 在 Itanium C++ ABI 下，联合体按值传参的方式取决于它对调用而言是否平凡（复制构造函数和析构函数平凡且未删除）。
    - GCC 文档明确允许直接通过联合体类型读取非活跃成员来重新解释字节，经指针间接访问时不保证。这是实现的保证，不是 C++ 的保证。
    - `std::variant` 在 libstdc++、libc++ 和 MSVC STL 中都实现为递归的联合体：每层包含一个备选类型和由其余类型组成的联合体，外面再加一个索引。`valueless_by_exception` 对应没有活跃成员的状态。

## 历史与演进

!!! history
    - C++98/03：联合体成员不能有非平凡的构造函数、析构函数或复制赋值，放不进 `std::string`。
    - C++11：无限制联合体，允许非平凡成员，相应的特殊成员函数被删除，由程序员手写；同时引入默认成员初始化器。
    - C++17：对象模型以生命周期重新表述，¶5 的赋值切换规则随 [[P0137R1]] 加入，为长期存在的写法提供了依据。
    - C++20：常量求值中可以切换活跃成员（[[P1330R0]]）；指派初始化器使 `U{.f = 1}` 成为选择成员的标准写法。
    - C++26：平凡联合体（[[P3074R7]]），联合体的默认构造函数和析构函数不再因成员非平凡而被删除。

## 常见误解

!!! pitfall "写 A 读 B 就是按新类型重新解释字节"
    在 C++ 中这是 UB，只是 GCC 和 Clang 作为扩展支持。应当用 `std::bit_cast`。

!!! pitfall "对成员赋值总能切换活跃成员"
    只有内置或平凡赋值、目标类型有平凡且未删除的默认构造函数时才行。`s` 不活跃时，`u.s = "x"`（`std::string`）是 UB。经过指针时链条也会中断：`p` 指向的对象本身不在生命周期内时，`p->m = 1` 不会创建它。

!!! pitfall "联合体会析构它的活跃成员"
    联合体不知道哪个成员活跃，所以不会析构任何成员。带非平凡成员的联合体必须由外层代码显式析构；反过来，析构一个非活跃成员（`u.s.~basic_string()`）也是 UB（[[basic.life#7]]）。

## 思考题

!!! question "思考题 1"
    给定 `struct S { int a, b; }; union U { int i; S s; } u{.i = 1};`，执行 `u.s.b = 2;` 之后，哪个成员是活跃的？读 `u.s.b` 可以吗？可以指望 `u.s.a == 1` 吗？

<details markdown="1">
<summary>答案</summary>

`b` 是结构体成员，不加入 S；`s` 是联合体成员，`S` 有平凡的默认构造函数，加入。所以 `u.s` 被隐式创建并成为活跃成员，`u.i` 的生命周期结束。读 `u.s.b` 得到 2。

`u.s.a` 处在生命周期内，但新对象 `u.s` 没有经过任何初始化。标准没有规定它的值等于原来 `u.i` 的值，即使它们占用同一块字节，也不应依赖 `u.s.a == 1`。
</details>

!!! question "思考题 2"
    为什么 ¶5 只接受有平凡默认构造函数的成员，而不是对任何可默认构造的类型隐式调用默认构造函数？

<details markdown="1">
<summary>答案</summary>

一个看起来只是赋值的表达式，不应该暗中执行用户代码。如果允许调用非平凡的默认构造函数，`u.s = x;` 会在赋值前运行构造函数，可能分配内存，也可能抛出异常，求值顺序和异常安全都会变得难以描述。平凡的默认构造什么也不做，凭空创建对象和正常的默认初始化没有区别，所以可以隐式完成。
</details>

!!! question "思考题 3"
    `union U { std::string s; int i; };` 在 C++26 中，`U u; u.i = 1;` 合法吗？之后 `u` 离开作用域会怎样？

<details markdown="1">
<summary>答案</summary>

合法。`U` 的默认构造函数是平凡的（[[class.default.ctor#3]] ¶3.4 对联合体不考察成员），`U u;` 之后没有活跃成员；`u.i = 1` 按 ¶5 创建一个 `int`。`U` 的析构函数也是平凡的：默认初始化选中的构造函数平凡，也没有带初始化器的非平凡变体成员。离开作用域时什么也不做，活跃的是 `int`，没有泄漏。如果活跃的是 `s`，就必须在离开作用域前调用 `std::destroy_at(&u.s)`。在 C++23 中，`U u;` 本身就是非良构的。
</details>
