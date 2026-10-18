---
title: delete 表达式
summary: delete 与 delete[] 的操作数要求与配对规则、通过基类指针删除需要虚析构函数、不完整类型的删除（C++26 起非良构）、析构与释放的次序、释放函数的查找与选择（销毁型 operator delete、对齐、sized deallocation）以及传给释放函数的实参
status: draft
papers: N3778, P0035R4, P0722R3, P3144R2
related: expr.new, basic.stc.dynamic.deallocation, class.free, class.dtor, basic.life, new.delete, conv.qual
tags: delete, operator delete, 析构函数, 虚析构, sized deallocation, 销毁型 delete
updated: 2026-10-17
---

*delete-expression* 是 [[expr.new]] 的逆操作：它销毁由 *new-expression* 创建的最派生对象或数组，然后（通常）调用**释放函数**归还存储。和 `new` 一样，`delete p` 也是两件事的组合：

1. 调用析构函数（如果有），对数组则按逆序析构每个元素；
2. 调用名为 `operator delete` 或 `operator delete[]` 的释放函数（[[basic.stc.dynamic.deallocation]]）。

本节的大部分篇幅在回答两个问题：哪些指针可以 delete（否则是 UB），以及调用哪个释放函数、传什么实参。后一个问题在 C++14（sized deallocation）、C++17（对齐）、C++20（销毁型 delete）中不断加入新的维度，最终形成了 ¶9 那个分步骤的选择流程。

预备知识：分配/释放函数的一般约束见 [[basic.stc.dynamic]]（普通释放函数与销毁型 operator delete 的定义见 [[basic.stc.dynamic.deallocation]]）；类专属版本见 [[class.free]]；析构函数见 [[class.dtor]]；对象生命周期见 [[basic.life]]。

## 文法与操作数（¶1）

¶1 有两种形式：

- `::opt delete cast-expression`，即**单对象 delete 表达式**（[[g:single-object-delete-expression]]）；
- `::opt delete [ ] cast-expression`，即**数组 delete 表达式**（[[g:array-delete-expression]]）。

`delete` 后紧跟空方括号 `[]` 时，总是解释为第二种形式。脚注 55：因此 `delete [] { return new int; }()` 并不是 delete 一个立即调用的 lambda 的结果，要这样写，必须给 lambda 加括号。

操作数的要求如下：

- 如果是类类型，它会按语境隐式转换（[[conv]]）为指向对象类型的指针，之后用转换结果代替原操作数。这要求类恰好有一个可用的、到对象指针类型的非 explicit 转换函数；
- 否则必须是指向对象类型的指针的 prvalue。`void*` 不行，因为 `void` 不是对象类型；函数指针也不行。

*delete-expression* 的类型是 `void`。

```cpp title="delete-operand.cpp" run ok
struct Handle { int* p; operator int*() const { return p; } };

int main() {
    const int* c = new const int(1);
    delete c;                                  // OK：指向 const 的指针也能 delete（注 2）
    int* n = nullptr;
    delete n;                                  // OK：空指针
    Handle h{new int(2)};
    delete h;                                  // OK：按语境隐式转换为 int*
    delete ([] { return new int(3); })();      // OK：lambda 加了括号
}
```

```cpp title="delete-operand-error.cpp" error
void f(void* vp, void (*fp)()) {
    delete vp;                         // error: void* 不是指向对象类型的指针
    delete fp;                         // error: 函数指针
    delete [] { return new int; }();   // error: [] 被解释为 delete[]
}
```

（对于 `delete vp`，Clang 23 在 `-std=c++2c` 下报告 “cannot delete pointer to incomplete type 'void'”；在 `-std=c++23` 下只给出 `-Wdelete-incomplete` 警告，并作为扩展接受。按 ¶1，它一直是非良构的，警告已满足诊断要求。）

## 可以 delete 什么（¶2）

¶2 规定了操作数的值的合法范围，**违反即为 UB**：

| 形式 | 操作数可以是 |
|---|---|
| 单对象 `delete p` | 空指针值；先前一次**非数组** *new-expression* 的结果；或指向这样创建的对象的基类子对象的指针 |
| 数组 `delete[] p` | 空指针值；先前一次**数组** *new-expression* 的结果，且其分配函数不是不分配形式（不是 `new (buf) T[n]` 那种） |

注 1 强调，delete 的形式必须与 new 所分配对象的类型相匹配，而不是与 *new-expression* 的语法相匹配：`using A = int[4]; int* p = new A;` 必须用 `delete[] p`。

注 2：指向 `const` 的指针可以直接 `delete`，不需要先 `const_cast`。这看起来奇怪，仿佛是通过 `const T*` 修改了对象，其实是合理的：析构不算修改，`const` 对象也有生命周期的终点，局部的 `const` 对象在作用域结束时同样会被析构。

脚注 56：对于非零长度的数组，数组 *new-expression* 的结果就是指向首元素的指针；零长度数组没有首元素，但其 `new` 的结果仍然可以（也必须）用 `delete[]` 释放。

```cpp title="delete-mismatch.cpp" run ub
int main() {
    int* p = new int[4];
    delete p;           // UB: 数组 new 必须用 delete[]（¶2）
}
```

对这种明显的不匹配，Clang 会给出 `-Wmismatched-new-delete` 警告；运行期，在设置 `ASAN_OPTIONS=alloc_dealloc_mismatch=1` 时（macOS 上默认关闭），AddressSanitizer 会报告 “alloc-dealloc-mismatch (operator new [] vs operator delete)”。

其他常见的 UB：

- `delete` 一个栈上对象或静态对象的地址；
- `delete` 一个不是由 new 返回的指针，如数组中间元素的地址、成员子对象的地址；
- 重复 delete：第一次 delete 之后，指针值成为无效指针值（[[basic.stc.dynamic.deallocation]]），再次 delete 是 UB；
- 对用标准库 placement 形式 `new (buf) T[n]` 创建的数组使用 `delete[]`，因为那块存储不是由 `operator new[]` 分配的。要销毁这种数组，应逐个调用析构函数（或用 `std::destroy_n`）。

## 静态类型与动态类型（¶3）

¶3 是“基类需要虚析构函数”这条著名规则的出处：

- 单对象 delete：如果被删除对象的静态类型与动态类型**不相似**（[[conv.qual]]），且选中的释放函数不是销毁型 operator delete，那么静态类型必须是动态类型的基类，并且**静态类型必须有虚析构函数**，否则是 UB。
- 数组 delete：如果动态类型与静态类型不相似，就是 UB，**没有**虚析构函数这一例外。

```cpp title="no-virtual-dtor.cpp" run ub
struct B { ~B() {} };                        // 非虚析构函数
struct D : B {
    int* buf = new int[4];
    ~D() { delete[] buf; }
};
int main() {
    B* p = new D;
    delete p;    // UB: 静态类型 B ≠ 动态类型 D，且 B 没有虚析构函数（¶3）
}
```

实践中最常见的后果是只调用了 `~B()`，`~D()` 被跳过，于是 `buf` 泄漏（本地用 `ASAN_OPTIONS=detect_leaks=1` 可以看到 LeakSanitizer 报告 16 字节泄漏）；同时，传给 sized `operator delete` 的大小是 `sizeof(B)` 而不是 `sizeof(D)`。但标准说的是 UB，而不仅仅是泄漏：在多重继承下，`B*` 甚至可能不等于对象的起始地址，传给释放函数的就是一个错误的指针。

为什么数组没有虚析构函数的豁免？因为 `delete[]` 要按元素大小遍历数组，`D[]` 的元素步长是 `sizeof(D)`，而通过 `B*` 只能知道 `sizeof(B)`，虚析构函数解决不了步长问题。这也是“不要多态地使用数组”这条建议在标准中的依据：

```cpp title="polymorphic-array.cpp" ub
struct B { virtual ~B() = default; };
struct D : B { int extra; };
int main() {
    B* a = new D[2];
    delete[] a;    // UB: 数组 delete 的静态类型 B 与动态类型 D 不相似（¶3）
}
```

相似（similar）允许 cv 限定上的差异：`const D*` 指向的 `D` 对象可以通过 `const D*` 删除，`D**` 与 `const D* const*` 等多级指针的 cv 差异同理。

## 不完整类型（¶4）{{c++26}}

¶4 如果被删除对象在 delete 处具有不完整类类型，**程序非良构**。

这是 C++26 的修改（[[P3144R2]]）。在 C++23 及之前，规则是：如果对象具有不完整类类型，而完整类型有非平凡析构函数或释放函数，则行为未定义。编译器在 delete 处看不到析构函数，只能不调用它，然后调用全局 `operator delete`。这是静默错误的典型：程序能编译通过，析构函数却从未被调用。C++26 直接把它定为非良构。

```cpp title="delete-incomplete.cpp" error
struct Inc;
void f(Inc* p) {
    delete p;    // error (C++26): 删除指向不完整类型的指针
}
```

Clang 23 在 `-std=c++2c` 下报告 “cannot delete pointer to incomplete type 'Inc'”；在 `-std=c++23` 下只给出 `-Wdelete-incomplete` 警告，指出它与 C++2c 不兼容，并且可能导致 UB。

`std::unique_ptr<T>` 的默认删除器 `std::default_delete<T>` 的 `operator()` 一直带有 *Mandates*：“`T` 是完整类型”（[[unique.ptr.dltr.dflt#3]]），实现通常用 `static_assert(sizeof(T) > 0)` 之类的手段来诊断。这就是 pimpl 惯用法要求在 `.cpp` 文件中定义析构函数的原因。

## 析构（¶5）

¶5 如果操作数不是空指针，且选中的释放函数不是销毁型 operator delete，求值 *delete-expression* 时就会调用被删除对象（或数组各元素）的析构函数（如果有）。析构函数必须在 delete 处可访问。数组元素**按地址递减的顺序析构**，即构造完成顺序的逆序（[[class.base.init]]）。

```cpp title="delete-private-dtor.cpp" error
struct Priv {
private:
    ~Priv();
};
void f(Priv* p) {
    delete p;    // error: 析构函数不可访问（¶5）
}
```

因此，把析构函数设为私有或受保护，是一种强制对象只能通过特定接口销毁的手段（例如引用计数类的 `release()`）。

## 何时调用释放函数（¶6）

¶6 如果操作数不是空指针：

- ¶6.1 如果对应 *new-expression* 的分配调用没有被省略，分配也没有被扩展（[[expr.new#14]]），*delete-expression* 必须调用释放函数，第一个实参是分配调用的返回值；
- ¶6.2 否则，如果分配被扩展（或者存储是通过扩展另一个 *new-expression* 的分配提供的），并且共享这块扩展存储的其他所有指针都已经被 delete，就调用释放函数，实参是那次被扩展的分配调用的返回值；
- ¶6.3 否则不调用释放函数。

注 3：**无论析构函数是否抛出异常，释放函数都会被调用**。（不过析构函数默认是 `noexcept` 的，除非显式声明为 `noexcept(false)`，否则从中抛出异常会导致 `std::terminate`。）

如果操作数是空指针，是否调用释放函数是**未指明**的。所以 `delete nullptr` 不做任何事：析构函数一定不会被调用；释放函数即使被调用，收到的也是空指针，而标准库的释放函数对空指针什么也不做（[[new.delete.single]]）。自定义的 `operator delete` 必须能正确处理空指针。

```cpp title="delete-null.cpp" ok
struct S { ~S(); };
void f() {
    S* p = nullptr;
    delete p;          // OK：不调用 ~S()；可能调用、也可能不调用 operator delete
    delete[] p;        // OK：同上
    if (p) delete p;   // 多余的检查
}
```

## 释放函数的名字与查找（¶7–¶8）

¶7 单对象 delete 调用 `operator delete`，数组 delete 调用 `operator delete[]`。注 4：实现提供全局的默认版本，程序可以替换它们（[[replacement.functions]]），也可以提供类专属版本（[[class.free]]）。

¶8 查找规则如下。如果 `delete` 前没有 `::`，且操作数类型是指向（可能 cv 限定的）类类型 `T` 或其（可能多维的）数组的指针：

- ¶8.1 单对象 delete，且 `T` 有虚析构函数：释放函数是**在动态类型的虚析构函数的定义处**选出的那个（[[class.dtor]]）；
- ¶8.2 否则在 `T` 的作用域中查找释放函数名。

其他情况（有 `::`、非类类型、或类作用域中没有找到）在全局作用域查找。无论哪种情况，都只保留**普通释放函数**（usual deallocation functions，[[basic.stc.dynamic.deallocation]]）的声明，其余的丢弃。

注 5：如果类中只找到 placement 形式的释放函数，丢弃之后查找集合为空，程序非良构。而且这时不会回退到全局作用域，因为查找本身已经找到了声明。

### 为什么 ¶8.1 很重要

¶8.1 使得 `delete pb`（`pb` 是 `Base*`，指向 `Derived`）调用的是 `Derived` 作用域中的 `operator delete`，而不是 `Base` 的。在实现上，编译器生成 `Derived` 的删除析构函数（deleting destructor，见下文实现视角）时就确定了释放函数，`delete pb` 通过虚调用进入它。虚析构函数与类专属 `operator delete` 能够正确配合，原因就在这里：

```cpp title="virtual-dtor-dealloc.cpp" run ok
#include <cstdio>
#include <new>

struct Base {
    virtual ~Base() = default;
};
struct Derived : Base {
    double payload[4];
    static void operator delete(void* p, std::size_t n) {   // 类专属 sized delete
        std::printf("Derived::operator delete(p, %zu)\n", n);
        ::operator delete(p);
    }
};

int main() {
    Base* b = new Derived;
    delete b;   // ¶8.1：在 Derived 的虚析构函数定义处选出 Derived::operator delete，大小为 sizeof(Derived)
}
```

在 64 位平台上，程序输出 `Derived::operator delete(p, 40)`：既选对了函数，传入的也是动态类型的大小（¶10）。

```cpp title="only-placement-delete.cpp" error
#include <cstddef>
struct OnlyPlacement {
    static void* operator new(std::size_t, int);
    static void operator delete(void*, int);   // 只有 placement 形式
};
void g(OnlyPlacement* p) {
    delete p;    // error: 类作用域查找只找到非普通释放函数，丢弃后为空（注 5）
}
```

## 选择哪一个释放函数（¶9）

¶9 查找得到一组普通释放函数后，按以下步骤依次筛选：

| 步骤 | 规则 |
|---|---|
| ¶9.1 | 若其中有**销毁型 operator delete**，淘汰所有非销毁型的 |
| ¶9.2 | 若类型有 new-extended 对齐，优先带 `std::align_val_t` 形参的；否则优先不带的。有优先者则淘汰非优先者 |
| ¶9.3 | 若只剩一个，选中它，结束 |
| ¶9.4 | 若释放函数属于类作用域，选**不带** `std::size_t` 形参的 |
| ¶9.5 | 若类型完整，且（仅对数组 delete）操作数是指向具有非平凡析构函数的类类型（或其多维数组）的指针，选**带** `std::size_t` 形参的 |
| ¶9.6 | 否则，是否选带 `std::size_t` 的版本**未指明** |

最后，除非释放函数是在动态类型虚析构函数的定义处选出的（¶8.1），选中的释放函数必须在 delete 处可访问。

由此可以得出几个值得注意的推论：

- 类作用域中同时有 sized 和 unsized 版本时，选 unsized（¶9.4）。这是 C++14 之前的历史行为，为了兼容而保留下来。
- 在全局作用域查找、类型完整的单对象 delete，选 sized（¶9.5）。这样分配器在释放时不必再去查找块的大小（例如 tcmalloc、jemalloc 可以直接按大小类别归还）。
- 数组 delete 只有在元素类型有非平凡析构函数时才要求选 sized 版本，因为只有这时才有记录元素个数的 cookie，才能算出总大小。
- `-fno-sized-deallocation` 这类编译选项让编译器总是选 unsized，严格来说不符合标准（违反 ¶9.5），但在需要兼容没有提供 sized 版本的旧替换分配器时很有用。

```cpp title="sized-dealloc-selection.cpp" run ok
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new(std::size_t n) { return std::malloc(n ? n : 1); }
void operator delete(void* p) noexcept { std::puts("global unsized"); std::free(p); }
void operator delete(void* p, std::size_t n) noexcept { std::printf("global sized %zu\n", n); std::free(p); }

struct Both {
    static void operator delete(void* p) { std::puts("Both: unsized"); ::operator delete(p); }
    static void operator delete(void* p, std::size_t) { std::puts("Both: sized"); ::operator delete(p); }
};

int main() {
    delete new int;    // 全局、完整类型 → ¶9.5：sized
    delete new Both;   // 类作用域中两者都有 → ¶9.4：unsized（随后 ::operator delete(p) 打印 global unsized）
}
```

在 Clang 23 上，输出是 `global sized 4`、`Both: unsized`、`global unsized`。用 `-fno-sized-deallocation` 编译时，第一行变成 `global unsized`。

## 删除的是哪个对象、传什么实参（¶10）

¶10 定义了**被删除对象**（[[g:deleted-object]]）：

- 单对象 delete：如果操作数所指对象 *A* 的静态类型没有虚析构函数，被删除对象就是 *A*；否则是 *A* 的最派生对象。注 6：如果释放函数不是销毁型的，而被删除对象不是最派生对象（即前一种情况），行为未定义（也就是 ¶3 的规定）。
- 数组 delete：被删除对象是数组对象。

释放函数的实参：

| 形参 | 实参 |
|---|---|
| 第一个（`void*` 或销毁型的 `T*`） | 单对象：被删除对象的地址；数组：被删除对象的地址按数组分配开销调整后的值（即回退到 cookie 之前） |
| `std::destroying_delete_t` | 一个未指明的值 |
| `std::align_val_t` | 被删除对象类型的对齐 |
| `std::size_t` | 单对象：被删除对象的大小；数组：数组大小**加上**分配开销 |

注 7：形成第一个实参时，忽略被删除对象类型中的 cv 限定。

注 8：如果由此调用的是一个可替换的释放函数，而第一个实参不是先前某次可替换分配函数调用的结果，或者第二、第三个实参与那次调用的对应实参不一致，行为未定义（[[new.delete.single]]、[[new.delete.array]]）。换句话说，**sized delete 收到的大小必须与当初请求的大小一致**。这也是通过没有虚析构函数的基类指针删除对象在实践中会破坏分配器的原因：传入的大小是错的。

## 销毁型 operator delete {{c++20}}

**销毁型 operator delete**（destroying operator delete，[[basic.stc.dynamic.deallocation]]，[[P0722R3]]）是一种类专属的 `operator delete`，其第二个形参的类型为 `std::destroying_delete_t`，第一个形参是 `C*` 而不是 `void*`：

```cpp
struct C {
    void operator delete(C* p, std::destroying_delete_t);
};
```

它被选中时（¶9.1 使它优先于所有非销毁型版本）：

- delete 表达式不调用析构函数（¶5），析构由 `operator delete` 自己负责；
- ¶3 中静态类型必须有虚析构函数的要求不适用，由 `operator delete` 自己负责找出动态类型；
- 第一个实参是指向被删除对象的、带类型的指针。

它的用途有：

1. 不依赖虚函数表的多态删除：用一个类型标签字段来分派析构与释放，省去虚函数表的开销；
2. 可变大小的对象：对象尾部带有变长数据（如 `std::string` 的某些实现、LLVM 的 `User` 类），释放时需要先读取对象里的长度字段才能算出分配大小，而普通 `operator delete` 被调用时对象已经析构，读不到这个字段了；
3. 在对象析构之前，做一些必须在对象仍然存活时进行的清理。

```cpp title="destroying-delete.cpp" run ok
#include <cstdio>
#include <new>

struct Shape {
    enum Kind { circle, square } kind;
    explicit Shape(Kind k) : kind(k) {}
    void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape { double r; Circle() : Shape(circle), r(1) {} ~Circle() { std::puts("~Circle"); } };
struct Square : Shape { double a; Square() : Shape(square), a(2) {} ~Square() { std::puts("~Square"); } };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
    switch (p->kind) {        // 对象还活着：可以读 kind
    case circle: { auto* c = static_cast<Circle*>(p); c->~Circle(); ::operator delete(c, sizeof(Circle)); break; }
    case square: { auto* s = static_cast<Square*>(p); s->~Square(); ::operator delete(s, sizeof(Square)); break; }
    }
}

int main() {
    Shape* a = new Circle;
    Shape* b = new Square;
    delete a;   // OK：没有虚析构函数，但选中的是销毁型 delete（¶3 的例外）
    delete b;
}
```

## delete this

标准中没有任何一条规则禁止 `delete this`。按 ¶2，只要 `*this` 是由非数组 *new-expression* 创建的（最派生）对象，`delete this` 就是良定义的。之后的约束来自 [[basic.life]] 和 [[basic.stc.dynamic.deallocation]]：

- `delete this` 之后，不得再访问任何非静态成员，也不得调用非静态成员函数，因为对象已经不在生命周期内；
- `this` 的值本身成为无效指针值，即使只是复制它，也是实现定义的行为；
- 对象必须确实是动态分配的，对栈上或静态对象调用一个会 `delete this` 的成员函数是 UB。

```cpp title="delete-this.cpp" run ok
#include <cstdio>
struct Node {
    int refs = 1;
    void release() {
        if (--refs == 0) delete this;   // OK：对象由非数组 new 创建；此后不再访问成员
    }
    ~Node() { std::puts("~Node"); }
};
int main() {
    Node* n = new Node;
    n->release();    // 之后 n 是无效指针值，不得再使用
}
```

## 实现视角

!!! impl "删除析构函数（deleting destructor）"
    - Itanium C++ ABI 为有虚析构函数的类在虚表中放两个析构函数条目：*complete object destructor*（D1，只析构）和 *deleting destructor*（D0，析构后调用合适的 `operator delete`）。`delete pb` 编译为对 D0 的虚调用；¶8.1 中在动态类型虚析构函数的定义处选出的释放函数，就是 D0 里调用的那一个，传入的 sized 大小 `sizeof(Derived)` 也是在那里确定的。（此外还有 D2，即 base object destructor，用于基类子对象。）
    - MSVC 使用标量删除析构函数（scalar deleting destructor），它带一个标志参数，决定析构后是否释放；数组另有 vector deleting destructor。
    - 非虚析构函数加基类指针删除：编译器直接调用 `B::~B()`，然后以 `B*` 的值和 `sizeof(B)` 调用 `operator delete`。在单继承下，指针值通常恰好正确（基类子对象在偏移 0 处），所以看起来能运行；在多重继承下，指针值是错的，会直接破坏堆。
    - sized deallocation 的默认设置：Clang 从 19 版起默认开启 sized deallocation（本地验证 Clang 23 中 `delete new int` 调用的是 sized 版本）；GCC 在 C++14 及以上模式中默认开启；MSVC 也默认开启。
    - `delete nullptr`：GCC 和 Clang 在单对象 delete 之前都会生成一次空指针检查，指针为空时既不调用析构函数，也不调用 `operator delete`（¶6 允许不调用）。

## 历史与演进

!!! history "C++98 → 当前草案"
    - **C++98**：`delete`/`delete[]` 的配对规则、通过基类指针删除需要虚析构函数、删除不完整类型（析构非平凡时为 UB），这些规则都已存在。
    - **C++14**：[[N3778]] 引入 sized deallocation，全局 `operator delete(void*, std::size_t)` 加入标准库，¶9 中 sized/unsized 的选择规则随之形成。
    - **C++17**：[[P0035R4]] 引入对齐的释放函数 `operator delete(void*, std::align_val_t)`（¶9.2）。
    - **C++20**：[[P0722R3]] 引入销毁型 operator delete（¶9.1，以及 ¶3、¶5 中的例外）。
    - **C++26**：[[P3144R2]] 使删除指向不完整类类型的指针成为非良构（¶4）{{c++26}}。
    - **当前草案（C++26 之后）**：释放函数如果具有潜在抛出的异常规约，程序非良构（[[diff.cpp26]]，[[basic.stc.dynamic.deallocation]]）{{c++29}}。此前，没有显式 *noexcept-specifier* 的释放函数已经隐式为 `noexcept`（[[except.spec#10]]），但显式写 `noexcept(false)` 是允许的。

## 陷阱

!!! pitfall "基类没有虚析构函数"
    只要有可能通过基类指针 `delete` 派生类对象，基类就必须有虚析构函数（或者改用销毁型 delete）。常见的折中做法是：多态基类的析构函数要么是 `public virtual`，要么是 `protected` 非虚。后者让通过基类指针 delete 的代码在编译期就被拒绝。

!!! pitfall "多态数组"
    `B* a = new D[n]; delete[] a;` 即使 `B` 有虚析构函数也是 UB（¶3），而且 `a[1]` 本身就已经是错误的指针运算。多态对象的集合应使用 `std::vector<std::unique_ptr<B>>`。

!!! pitfall "以为 `delete p; p = nullptr;` 能防止所有重复释放"
    它只能保护这一个变量。指向同一对象的其他指针（包括 `this`）仍然是无效指针值。

!!! pitfall "自定义 operator delete 不处理空指针"
    见 ¶6 末尾：对空指针是否调用释放函数是未指明的。实现可以用空指针调用你的类专属 `operator delete`，所以它必须能容忍空指针。

!!! pitfall "pimpl 中的不完整类型"
    在 C++23 中，如果头文件里内联生成的析构函数 `delete` 了一个不完整的 `Impl*`，可能会静默地跳过 `Impl` 的析构函数（UB）。C++26 把它变成了编译错误（¶4）；`std::unique_ptr<Impl>` 的默认删除器则一直会拒绝这种情况。两种情况的解决办法都是把析构函数的定义放到 `Impl` 已完整的 `.cpp` 文件中。

## 思考题

!!! question "思考题 1"
    `struct B { virtual ~B(); static void operator delete(void*); }; struct D : B { static void operator delete(void*, std::size_t); };`。`B* p = new D; delete p;` 调用哪个释放函数？传入什么实参？

<details markdown="1">
<summary>答案</summary>

按 ¶8.1，`B` 有虚析构函数，释放函数在动态类型 `D` 的（隐式定义的）虚析构函数的定义处选出：在 `D` 的作用域中查找 `operator delete`，找到 `D::operator delete(void*, size_t)`，它隐藏了 `B` 的版本。只有一个候选，按 ¶9.3 选中它。实参是 `D` 对象的地址和 `sizeof(D)`（¶10，被删除对象是最派生对象）。由于它是在虚析构函数的定义处选出的，即使 `D::operator delete` 是私有的，也不影响 `delete p` 处的可访问性检查（¶9 末句）。
</details>

!!! question "思考题 2"
    为什么 ¶9.4 在类作用域中优先选择不带 `size_t` 的版本，而 ¶9.5 在全局作用域中优先选择带 `size_t` 的版本？

<details markdown="1">
<summary>答案</summary>

这是出于历史兼容。从 C++98 起，类专属的 `operator delete(void*, size_t)` 就是合法的普通释放函数；类同时声明了两种版本时，旧规则规定使用单参数版本，C++14 不能改变已有程序的行为。而全局的 sized `operator delete` 是 C++14 才加入标准库的新函数，可以从一开始就规定能传大小就传大小，以获得性能上的收益。
</details>

!!! question "思考题 3"
    `struct S { int x; }; const S* p = new const S{1}; delete p;` 中，¶10 的注 7 说要忽略 cv 限定，这指的是什么？如果改为 `delete[]` 一个 `new const S[2]{{1}, {2}}` 的结果呢？

<details markdown="1">
<summary>答案</summary>

释放函数的第一个形参是 `void*`，而被删除对象的地址是 `const S*`；`const S*` 不能隐式转换为 `void*`，因为那会丢掉 `const`。注 7 说明，形成实参时忽略 cv 限定，即实现直接传递地址值，既不需要也不进行 cv 检查。数组情形同理：`new const S[2]{{1}, {2}}` 是合法的（[[expr.new#1]] 注 2；注意不带初始化器的 `new const S[2]` 是非良构的，因为 `const` 对象的默认初始化要求类型可以 const 默认构造），对 `const S*` 使用 `delete[]` 也合法，传给 `operator delete[]` 的是按数组开销调整后的地址（`S` 的析构是平凡的，通常没有 cookie，调整量为 0）。
</details>

## 小结

| 问题 | 段落 | 答案 |
|---|---|---|
| 操作数 | ¶1 | 对象指针 prvalue，或可按语境转换为对象指针的类类型；`delete []` 总是数组形式 |
| 合法的值 | ¶2 | 空指针，或对应形式 new 的结果（单对象还可以是基类子对象指针）；否则 UB |
| 静态/动态类型 | ¶3 | 单对象：不相似时需虚析构函数（销毁型 delete 例外）；数组：不相似即 UB |
| 不完整类型 | ¶4 | 非良构（C++26；此前可能是 UB） |
| 析构 | ¶5 | 非空且非销毁型 delete 时调用析构函数，须可访问；数组逆序 |
| 是否释放 | ¶6 | 非空时按分配是否被省略/扩展决定；空指针时未指明 |
| 查找 | ¶8 | 虚析构 → 在动态类型析构函数定义处选；否则类作用域，再全局；只保留普通释放函数 |
| 选择 | ¶9 | 销毁型 > 对齐匹配 > 唯一者 > 类作用域取 unsized > 完整类型取 sized > 未指明 |
| 实参 | ¶10 | 被删除对象（或数组调整后）的地址、对齐、大小（含数组开销） |
