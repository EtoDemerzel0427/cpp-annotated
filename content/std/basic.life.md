---
title: 对象生命周期
summary: 对象的生命周期从初始化完成开始，到析构开始或存储被复用时结束；生命周期之外的指针和引用只能有限使用；在原地换上新对象后旧名字还能不能用（透明可替换、std::launder）；作用域退出和 const 对象的两条额外限制。
status: done
papers: P0137R1, P0593R6
related: intro.object, basic.stc, class.cdtor, class.union, expr.new, ptr.launder, basic.indet
tags: 对象模型, 生命周期, UB, launder
updated: 2026-10-19
---

!!! tldr
    - 对象的生命周期在存储就绪、初始化完成时开始；类对象在析构函数开始执行时结束，非类对象在被销毁时结束；存储被释放或被别的对象复用时也会结束。
    - 生命周期之外，指向对象的指针只能当 `void*` 用；成员访问、`delete`、转换到虚基类、`dynamic_cast` 都是 UB。引用和名字同理，不能读写对象的值。
    - 在原地创建一个同类型的新对象后，旧的指针、引用和名字能否自动指向新对象，取决于是否**透明可替换**：完整对象要求非 `const`、恰好覆盖、类型相同。
    - 不满足透明可替换时，用 placement new 的返回值，或者对旧地址调用 `std::launder`。
    - 有非平凡析构函数的局部、静态、线程对象，作用域结束时原位置上必须有原类型的对象；`const` 的这类对象的存储上不得创建新对象。

## 生命周期从哪里开始（¶2）

```cpp run title="lifetime-begin.cpp" ok
#include <string>

void f() {
    int x;                      // 生命周期在此开始（值是错误值，见 [basic.indet]）
    std::string s("abc");       // 构造函数返回时开始
    struct P { int a, b; } p;   // 平凡默认构造：在此开始
    (void)x; (void)p;
}

int main() { f(); }
```

对象的**生命周期**（lifetime）是一个运行期属性。只有在生命周期之内，才能按对象的类型正常读写它、调用它的成员函数。按 ¶2，类型为 `T` 的对象的生命周期在两件事都完成时开始：

- ¶2.1 取得了大小和对齐都适合 `T` 的存储；
- ¶2.2 它的初始化（如果有）已经完成。

`int x;` 这样的声明什么也不做，也算初始化完成。标准把这种情况叫做**空初始化**（vacuous initialization）：变量被默认初始化，没有做其他初始化，并且如果是类类型（或其数组），默认初始化选中的是平凡构造函数。

对类类型，初始化完成就是构造函数执行完毕。构造函数体执行期间，对象处于构造期间（period of construction）：既不是完全不可用，也还不在生命周期之内。这段时间的规则在 [[class.cdtor]]，例如虚函数按正在构造的那个类分派。

### 联合体成员

如果对象是联合体成员或其子对象，只有当这个成员是联合体里被初始化的那个时，它的生命周期才开始。此外还有几种途径：给成员赋值会切换活跃成员（[[class.union]]），平凡复制联合体会复制活跃成员（[[class.copy.ctor]]、[[class.copy.assign]]），`std::start_lifetime_as` 也能开始生命周期（[[obj.lifetime]]）。

```cpp run title="union-lifetime.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};     // u.i 的生命周期开始；u.f 不在生命周期内
    u.f = 2.0f;      // 赋值切换活跃成员：u.f 开始，u.i 结束
    return u.f == 2.0f ? 0 : 1;   // OK
    // 此时再读 u.i 是 UB：u.i 不在生命周期内
}
```

另一个例外在 [[allocator.members]]：`std::allocator<T>::allocate` 创建了数组对象，但不开始其元素的生命周期，见后文 `vector` 风格存储的例子。

## 生命周期在哪里结束（¶2）

类型为 `T` 的对象 *o* 的生命周期在下列任一情况发生时结束：

- ¶2.3 `T` 是非类类型，对象被销毁，例如 `std::destroy_at(&x)`、伪析构函数调用 `p->~int()`，或者存储期结束；
- ¶2.4 `T` 是类类型，析构函数调用开始；
- ¶2.5 对象占据的存储被释放，或者被一个不嵌套于 *o* 的对象复用（[[intro.object]]）。

¶2.4 说的是析构函数开始，而不是结束。析构函数体执行期间，对象已经不在生命周期内，而是处于析构期间，同样由 [[class.cdtor]] 管辖。

¶2.5 里的不嵌套于 *o* 是为 `unsigned char` 缓冲区留的口子。在 `unsigned char` 数组里 placement new 一个对象时，数组为新对象**提供存储**（[[intro.object#3]]），新对象嵌套于数组之内，数组的生命周期不会因此结束。

### new-expression 中的复用发生在初始化之前

¶2 的最后一句规定：求值 *new-expression* 时，分配函数一返回，存储就算被复用了，这发生在求值 *new-initializer*（括号或花括号里的初始化器）之前。所以初始化器里不能再读旧对象：

<div class="compare" markdown="1">

```cpp run ub
#include <new>
struct S { int m; };

int main() {
  S x{1};
  ::new (&x) S(x.m);  // UB
  return x.m;
}
```

```cpp run ok
#include <new>
struct S { int m; };

int main() {
  S x{1};
  int v = x.m;        // 先读出来
  ::new (&x) S(v);    // OK
  return x.m;
}
```

</div>

左边求值 `x.m` 时，`x` 的存储已经被视为复用，旧 `x` 的生命周期已经结束。这也说明了为什么 `this->~T(); new (this) T(other);` 这种赋值写法在 `other` 就是 `*this` 时是错的：析构之后，`other` 已经不在生命周期内。

## 生命周期之外还能做什么（¶5、¶7、¶8）

¶5 规定，标准在任何地方归属于对象或引用的属性，只在它的生命周期内成立。生命周期之外能做什么，必须由 ¶7、¶8 和 [[class.cdtor]] 另行允许。

这里说的生命周期之外，指两段时间：存储已经分配、生命周期还没开始；或者生命周期已经结束、存储还没被复用或释放。正在构造或析构的对象另见 [[class.cdtor]]。

### 指针（¶7）

¶7 允许以有限的方式使用指向这块存储的指针。把它当作 `void*` 使用是良定义的，也可以对它解引用，但得到的左值只能按 ¶8 有限使用。下列用法是 UB：

| 列表项 | 用法 | 为什么不行 |
|---|---|---|
| ¶7.1 | 作为 *delete-expression* 的操作数 | `delete` 要调用析构函数 |
| ¶7.2 | 访问非静态数据成员，或调用非静态成员函数 | 需要对象存在 |
| ¶7.3 | 转换为指向虚基类（或其基类）的指针 | 虚基类的偏移要通过对象的 vptr 查表 |
| ¶7.4 | 作为 `dynamic_cast` 的操作数 | 要读 vptr 得到动态类型 |

清单之外的用法都允许：复制、比较指针，转换为 `void*`，转换为非虚基类的指针（偏移在编译期已知，不必读取对象）。

下面改编自标准的例 2：

```cpp run title="mutate.cpp" ub
#include <cstdlib>
#include <new>

struct B {
    virtual void f() {}
    void mutate();
    virtual ~B() {}
};
struct D1 : B { void f() override {} };
struct D2 : B { void f() override {} };

void B::mutate() {
    ::new (this) D2;   // 复用存储，结束 *this 的生命周期
    f();               // UB：¶7.2，this->f()
    void* p = this;    // OK：当作 void* 使用
    (void)p;
}

int main() {
    void* p = std::malloc(sizeof(D1) + sizeof(D2));
    B* pb = ::new (p) D1;
    pb->mutate();
    void* q = pb;      // OK
    (void)q;
    pb->f();           // UB：*pb 的生命周期已结束
    std::free(p);
}
```

`pb->f()` 为什么不能调用到 `D2::f`？编译器知道 `pb` 指向一个 `D1`，可以把 `pb->f()` 直接改成调用 `D1::f`。中间那次 `mutate()` 不影响这个推断：它不能悄悄把 `D1` 变成 `D2`，因为那会结束对象的生命周期，之后再通过 `pb` 访问就是 UB。要使用新对象，应当用 placement new 的返回值：`B* pb2 = ::new (p) D2; pb2->f();`。

### 引用和名字（¶8）

¶8 是同一规则的 glvalue 版本（glvalue 是指代一个对象的表达式，例如变量名、`*p`）。在同样的时间段内，可以使用不依赖对象值的属性，比如取地址、绑定到同类型的引用。下列用法是 UB：

| 列表项 | 用法 |
|---|---|
| ¶8.1 | 访问对象，即读或写它的值 |
| ¶8.2 | 调用非静态成员函数 |
| ¶8.3 | 绑定到虚基类的引用 |
| ¶8.4 | 作为 `dynamic_cast` 或 `typeid` 的操作数 |

```cpp run title="glvalue-outside.cpp" ub
#include <memory>

int main() {
    int x = 1;
    std::destroy_at(&x);   // 结束 x 的生命周期
    int* p = &x;           // OK：取地址不依赖值
    int& r = x;            // OK：绑定到同类型的引用
    (void)p;
    return r;              // UB：¶8.1，读取生命周期之外的对象
}
```

### 多线程（¶1）

¶1 规定，[basic.life] 里说的之前和之后都按 [[g:happens-before]] 关系理解，而不是单线程里的先后。所以注 5 指出：一个线程正在构造的对象，另一个线程在没有适当同步的情况下引用它，就是 UB。没有同步，就谈不上在构造完成之后。错误的双检锁（double-checked locking）写法错就错在这里。

## 原地换上新对象：透明可替换（¶9–¶10）

旧对象的生命周期结束后，在同一位置创建了一个新对象。原来指向旧对象的指针、引用和名字，能不能直接拿来用新对象？

```cpp run title="transparent-replace.cpp" ok
#include <new>

struct C {
    int i;
    void f() {}
    C(int i) : i(i) {}
    C(const C&) = default;
    const C& operator=(const C& other);
};

const C& C::operator=(const C& other) {
    if (this != &other) {
        this->~C();              // *this 的生命周期结束
        ::new (this) C(other);   // 同一位置创建同类型的新对象
        f();                     // OK：this 指向新对象
    }
    return *this;
}

int main() {
    C c1{1}, c2{2};
    c1 = c2;                     // OK
    c1.f();                      // OK：名字 c1 指向新对象
    return c1.i == 2 ? 0 : 1;
}
```

¶10 回答：如果旧对象 *o1* **透明可替换**（transparently replaceable）为新对象 *o2*，那么指向 *o1* 的指针、引用 *o1* 的引用、*o1* 的名字都会自动指向 *o2*，在 *o2* 的生命周期开始后可以用来操作它。上例就是这样。

¶9 给出定义。*o1* 透明可替换为 *o2*，要么属于情形一，要么属于情形二。

情形一（¶9.1）：两者都是完整对象（不是任何对象的子对象），并且

- ¶9.1.1 *o1* 不是 `const` 的；
- ¶9.1.2 *o2* 占据的存储恰好覆盖 *o1* 原来占据的存储；
- ¶9.1.3 两者类型相同，忽略顶层 cv 限定。

情形二（¶9.2）：两者是**对应的直接子对象**（corresponding direct subobjects），并且 *o1* 的完整对象不是 `const` 的（¶9.2.1），或者 *o1* 是 `mutable` 成员子对象或其子对象（¶9.2.2）。

对应的直接子对象由 [[intro.object#2]] 定义：在某个子对象 *e* 的存储上创建新对象时，如果 *e* 所在的对象在生命周期内、新对象恰好覆盖 *e*、*e* 不是潜在重叠子对象、类型相同，新对象就成为同一个外层对象的子对象，与 *e* 是对应的直接子对象。潜在重叠子对象指基类子对象和标了 `[[no_unique_address]]` 的成员，它们的存储可能与别的子对象共用，所以被排除。

### 每个条件保护一种优化

| 条件 | 保护的优化 |
|---|---|
| 旧对象不是 `const` 完整对象 | 编译器可以假设 `const` 对象的值不变，做常量传播 |
| 恰好覆盖 | 指针运算、子对象偏移在新旧对象之间保持一致 |
| 类型相同 | 动态类型（vptr）不变，可以去虚化 |
| 不能是基类子对象 | 基类子对象的动态类型是派生类，换成基类类型的完整对象会改变它；存储也可能与其他成员共用 |

### `const` 成员和引用成员不再妨碍替换 {{c++20}}

C++17 的 ¶9 还多一条要求：类类型不能含有 `const` 限定或引用类型的非静态数据成员。下面这种很自然的代码因此是 UB，必须写 `std::launder`。C++20 删除了这条限制，现在它是良构的：

```cpp run title="const-member.cpp" ok
#include <new>

struct X { const int n; int& r; };

int main() {
    int a = 1, b = 2;
    X x{1, a};
    x.~X();
    ::new (&x) X{2, b};   // C++17：x 不能再用来访问新对象
    return x.n + x.r;     // C++20 起 OK
}
```

删除的动机之一是标准库：`std::optional<X>`、`std::vector<X>` 的元素含有 `const` 成员时，严格遵守 C++17 的实现得在每次访问时 `launder`，既笨拙又妨碍优化。

现在剩下的是完整对象本身不能是 `const`。下面是 [[ptr.launder]] 里的例子：

```cpp run title="const-complete.cpp" ok
#include <new>

struct X { int n; };

int main() {
    const X* p = new const X{3};
    const int a = p->n;
    ::new (const_cast<X*>(p)) const X{5};   // p 不指向新对象：原对象是 const 完整对象
    // const int b = p->n;                  // UB：p 仍指向已结束生命周期的旧对象
    const int c = std::launder(p)->n;       // OK
    delete std::launder(p);
    return a + c == 8 ? 0 : 1;
}
```

这是动态存储期的 `const` 对象，所以不受 ¶12 约束。如果是局部或静态的 `const` 完整对象，连创建新对象本身都是 UB，见下文。

### 不能透明替换时：`std::launder`

¶10 的注 6 说，条件不满足时，可以对表示该存储地址的指针调用 `std::launder`（[[ptr.launder]]），得到指向新对象的指针。`launder` 本身有前置条件：那个地址上必须有一个类型相似、处于生命周期内的对象。

需要 `launder` 的典型情形有三种：原对象是 `const` 完整对象（上例）；手里的指针原本指向另一个类型的对象，例如 `unsigned char` 缓冲区；被替换的是基类子对象。下面是一个最小的 `optional`：

```cpp run title="optional-like.cpp" ok
#include <new>
#include <string>
#include <utility>

template<class T>
class Opt {
    alignas(T) unsigned char buf_[sizeof(T)];   // buf_ 为 T 提供存储
    bool has_ = false;

    // 没有 launder 时，reinterpret_cast 的结果仍指向 buf_[0]，访问是 UB
    T* ptr() { return std::launder(reinterpret_cast<T*>(buf_)); }

public:
    Opt() = default;
    ~Opt() { reset(); }
    template<class... A>
    T& emplace(A&&... a) {
        reset();
        T* p = ::new (buf_) T(std::forward<A>(a)...);
        has_ = true;
        return *p;           // placement new 的返回值本来就指向新对象
    }
    void reset() { if (has_) { ptr()->~T(); has_ = false; } }
    T& operator*() { return *ptr(); }
};

int main() {
    Opt<std::string> o;
    o.emplace("hello");
    o.emplace("world");      // 先析构旧 string，再在同一 buf_ 中构造新的
    return (*o).size() == 5 ? 0 : 1;
}
```

另一种做法是把 placement new 的返回值存成成员 `T* p_`，之后一律通过它访问，代价是多存一个指针。标准库实现通常用联合体成员 `union { T val_; };` 作为存储：在 `val_` 的位置上构造的新对象与 `val_` 是对应的直接子对象，透明可替换，通过成员名访问就不需要 `launder`。

### `vector` 风格的存储

```cpp run title="vector-like.cpp" ok
#include <memory>
#include <string>

int main() {
    std::allocator<std::string> a;
    std::string* p = a.allocate(3);   // 创建 string[3] 数组对象，元素生命周期未开始
    for (int i = 0; i < 3; ++i)
        std::construct_at(p + i, 3, char('a' + i));   // p + i 合法：p 指向数组元素
    std::string s = p[0] + p[2];      // OK：元素在生命周期内
    std::destroy(p, p + 3);
    a.deallocate(p, 3);
    return s == "aaaccc" ? 0 : 1;
}
```

指针运算只在数组对象内部有定义。如果 `allocate` 返回的存储里没有数组对象，`p + i` 就是 UB，`std::vector` 也就无法用标准 C++ 实现。[[P0593R6]] 修好了这个问题：[[allocator.members]] 规定 `allocate` 创建一个 `T[n]` 数组对象，但不开始元素的生命周期，元素在 `construct_at` 之后才开始。

## 不调用析构函数也能结束生命周期（¶6）

¶6 允许程序不调用析构函数，而是通过复用或释放存储来结束类对象的生命周期。这时析构函数不会被隐式调用。注 4 提醒，程序的正确性往往依赖于析构函数被调用，例如释放资源；但跳过析构本身不是 UB。

```cpp run title="skip-dtor.cpp" ok
#include <new>
#include <string>

int main() {
    alignas(std::string) unsigned char buf[sizeof(std::string)];
    auto* s = ::new (buf) std::string(100, 'x');   // 在堆上分配了 100 字节
    ::new (buf) int(0);   // 复用存储：*s 的生命周期结束，析构函数没有调用
    (void)s;              // 内存泄漏，但不是 UB
}
```

本机用 AddressSanitizer 并开启泄漏检测（`ASAN_OPTIONS=detect_leaks=1`）运行，会报告这处泄漏，但没有任何 UB 报告。

## 作用域退出时要放回原类型（¶11）

编译器会在作用域结束处无条件地插入析构函数调用，它不知道你中途换过对象。所以 ¶11 规定：如果程序结束了一个静态、线程或自动存储期的 `T` 类型对象的生命周期，而 `T` 有非平凡析构函数，那么在隐式析构调用发生时，原位置上必须有一个原类型的对象，否则行为未定义。因异常而退出块时也一样。

<div class="compare" markdown="1">

```cpp run ub
#include <new>
class T {};
struct B { ~B() {} };

void h() {
  B b;
  ::new (&b) T;  // 结束 b 的生命周期
}  // UB：此时没有 B 对象

int main() { h(); }
```

```cpp run ok
#include <new>
struct T {};
struct B { ~B() {} };

void h() {
  B b;
  b.~B();
  T* t = ::new (&b) T;
  t->~T();
  ::new (&b) B;  // 放回一个 B
}  // OK

int main() { h(); }
```

</div>

右边的写法要求 `B` 的构造不会抛出异常。如果 `::new (&b) B` 抛出，退出作用域时那里没有 `B`，同样是 UB。

## `const` 对象的存储不能复用（¶12）

在静态、线程或自动存储期的 `const` 完整对象占据的存储里创建新对象是 UB，在它生命周期结束后的那块存储里也一样。

```cpp run title="const-static.cpp" ub
#include <new>

struct B { B() {} ~B() {} };

const B b;

void h() {
    b.~B();
    ::new (const_cast<B*>(&b)) const B;   // UB：¶12
}

int main() { h(); }
```

这类对象可能放在只读内存（`.rodata` 段）里，写入会触发硬件异常；即使不在只读内存里，编译器也可能已经把它的值传播到了所有使用处。`new const X` 得到的动态存储期 `const` 对象不受这条约束。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶3 引用的生命周期在其初始化完成时开始，结束的方式如同它是一个需要存储的标量对象。引用没有析构函数，它在存储期结束或所在对象的存储被复用时结束。

¶4 是一条注，指向 [[class.base.init]] 对基类和成员子对象生命周期的描述。

</details>

## 实现视角

!!! impl "编译器怎样利用这些规则"
    - 去虚化：对 `B* p = new D; p->f();`，编译器知道 `*p` 的动态类型是 `D`，可以直接调用 `D::f`。Clang 的 `-fstrict-vtable-pointers` 更激进地假设 vptr 在对象生命周期内不变，并把 `std::launder` 当作这类假设的屏障。
    - `const` 传播：编译器假定 `const` 完整对象的值在生命周期内不变，可以提前读进寄存器或折叠成常量。¶9.1.1 和 ¶12 保护的就是这一点。
    - `std::launder` 在 GCC 和 Clang 上实现为 `__builtin_launder`，不生成任何指令，只是让优化器放弃对这个指针所指对象的旧假设。
    - 编译器在作用域出口和异常路径的 landing pad 里直接生成析构调用，这是 ¶11 的来由。

## 历史与演进

!!! history
    - C++98 已经有生命周期的概念、¶7 和 ¶8 那样的清单，以及透明替换的雏形。当时的条件还包括类不含 `const` 或引用成员。
    - C++17：[[P0137R1]] 随对象模型的重写引入了 `std::launder`，不满足透明替换时如何拿到新对象的指针从此有了依据。
    - C++20：删除了类不得含 `const` 或引用成员的限制。生命周期结束的条件从类类型且有非平凡析构函数时析构开始，改为所有类类型析构开始即结束（[[CWG2256]]）；伪析构函数调用也会结束非类对象的生命周期。[[P0593R6]] 引入隐式对象创建，并规定 `std::allocator::allocate` 创建数组对象。
    - C++23 之后的新措辞：子对象的透明替换改用对应的直接子对象来表述，明确排除潜在重叠子对象；¶2 明确了 *new-expression* 在初始化器求值之前就复用存储（例 1）。

## 常见误解

!!! pitfall "placement new 之后旧指针一定能用"
    只有透明可替换时才能用。常见的反例是：被替换的是基类子对象，新旧类型不同，原对象是 `const` 完整对象。不确定时，就用 placement new 的返回值。

!!! pitfall "`std::launder` 能解决一切问题"
    `launder` 只是给出指向一个已经存在、处于生命周期内的对象的指针。如果那个地址上根本没有该类型的对象，例如把 `malloc` 来的内存直接当作 `std::string` 而没有 placement new，前置条件不满足，调用本身就是 UB。

!!! pitfall "析构之后读成员做调试输出"
    `obj.~T(); log(obj.x);` 是 UB（¶8.1），即使析构函数什么也没做。C++20 起，显式调用平凡析构函数同样结束生命周期。

## 思考题

!!! question "思考题 1"
    下面的程序有 UB 吗？

    ```cpp
    struct Base { virtual int id() { return 1; } virtual ~Base() = default; };
    struct Der : Base { int id() override { return 2; } };
    int main() {
        Der d;
        Base* pb = &d;
        pb->~Base();
        ::new (pb) Base;
        int r = pb->id();
        ::new (&d) Der;
        return r;
    }
    ```

<details markdown="1">
<summary>答案</summary>

有。`pb->~Base()` 是虚析构调用，实际执行 `Der::~Der()`，结束了 `d` 的生命周期。`::new (pb) Base` 在这块存储上创建了一个 `Base` 完整对象，这里只把 `pb` 当作地址使用，没有问题。

但旧对象是 `Der` 的基类子对象：它不是完整对象，¶9.1 不适用；基类子对象是潜在重叠子对象，`d` 的生命周期也已结束，新 `Base` 不会成为与它对应的直接子对象，¶9.2 也不适用。替换不透明，`pb->id()` 是 ¶7.2 的 UB。应当用 placement new 的返回值，或者写 `std::launder(pb)->id()`。程序最后放回了一个 `Der`，所以作用域退出时满足 ¶11。
</details>

!!! question "思考题 2"
    `struct S { const int c; }; S s{1}; s.~S(); new (&s) S{2}; int v = s.c;` 在 C++17 和 C++20 中分别如何？如果改成 `const S s{1};`（自动存储期）呢？

<details markdown="1">
<summary>答案</summary>

C++17 中 `S` 含 `const` 成员，不能透明替换，`s.c` 是 UB，需要写 `std::launder(&s)->c`。C++20 起 `s` 不是 `const` 完整对象，类型相同、恰好覆盖，可以透明替换，没有问题。

改成 `const S s{1};` 后，在自动存储期的 `const` 完整对象的存储上创建新对象，按 ¶12 直接是 UB，`launder` 也补救不了。
</details>

!!! question "思考题 3"
    为什么 ¶7 允许把生命周期之外的 `D*` 转换为非虚基类的指针，却禁止转换为虚基类的指针？

<details markdown="1">
<summary>答案</summary>

非虚基类子对象相对派生类对象的偏移是编译期常量，转换只是给地址加一个固定值，不需要读取对象。虚基类子对象的偏移取决于最派生类型，通常要通过对象的 vptr 到虚表里查（Itanium ABI 的 vbase offset），也就要读取对象。对象不在生命周期内时，vptr 可能还没设置，或者已在析构过程中被改写。
</details>

## 小结

| 情形 | 规则 |
|---|---|
| 生命周期开始 | 存储就绪且初始化完成（包括空初始化）；联合体成员须成为活跃成员 |
| 生命周期结束 | 非类：被销毁；类：析构开始；或存储被释放、被非嵌套对象复用 |
| *new-expression* | 分配函数返回后、初始化器求值前，存储即被视为复用 |
| 生命周期之外的指针 | 当 `void*` 用可以；`delete`、成员访问、转虚基类、`dynamic_cast` 是 UB |
| 生命周期之外的 glvalue | 不依赖值的属性可以用；读写、调成员函数、绑虚基类引用、`dynamic_cast`、`typeid` 是 UB |
| 透明替换 | 完整对象：非 `const`、恰好覆盖、同类型；子对象：对应的直接子对象，且完整对象非 `const` 或成员是 `mutable` |
| 不能透明替换时 | 用 placement new 的返回值，或 `std::launder` |
| 作用域退出 | 非平凡析构的静态、线程、自动对象，原位置上必须有原类型对象 |
| `const` 对象 | 静态、线程、自动存储期的 `const` 完整对象，存储上不得创建新对象 |
