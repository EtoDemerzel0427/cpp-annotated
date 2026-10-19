---
title: delete 表达式
summary: delete 和 delete[] 先析构对象再调用释放函数；本页讲哪些指针可以删除、为什么基类需要虚析构函数、调用哪一个 operator delete 以及传给它什么实参。
status: done
papers: N3778, P0035R4, P0722R3, P3144R2
related: expr.new, basic.stc.dynamic.deallocation, class.free, class.dtor, basic.life, new.delete, conv.qual
tags: delete, operator delete, 析构函数, 虚析构, sized deallocation, 销毁型 delete
updated: 2026-10-19
---

!!! tldr
    - `delete p` 做两件事：调用析构函数，再调用释放函数 `operator delete` 归还存储。`delete[]` 对数组做同样的事，元素按构造的逆序析构。
    - `delete` 只能用于非数组 `new` 的结果，`delete[]` 只能用于数组 `new` 的结果，空指针两者都可以；用错就是未定义行为。
    - 经基类指针 `delete` 派生类对象时，基类必须有虚析构函数，否则是 UB。`delete[]` 经基类指针删除派生类数组，有虚析构函数也是 UB。
    - C++26 起，`delete` 一个指向不完整类的指针是非良构的，此前可能静默跳过析构函数。
    - 释放函数的选择有固定顺序：销毁型优先，然后按对齐筛选，类作用域里优先不带大小的版本，全局作用域里类型完整时优先带大小的版本。

## delete 做了什么（¶1）

¶1 *delete-expression* 销毁一个由 *new-expression* 创建的最终派生对象或数组。它与 `new`（[[expr.new]]）对称，也分两步：

1. 调用析构函数（如果有）；
2. 调用**释放函数**（deallocation function）`operator delete` 或 `operator delete[]`，归还存储（[[basic.stc.dynamic.deallocation]]）。

`delete cast-expression` 是**单对象 delete 表达式**（[[g:single-object-delete-expression]]），`delete [] cast-expression` 是**数组 delete 表达式**（[[g:array-delete-expression]]），两者前面都可以加 `::`。表达式的类型是 `void`。

```cpp title="delete-operand.cpp" run ok
struct Handle { int* p; operator int*() const { return p; } };

int main() {
    const int* c = new const int(1);
    delete c;                                  // OK：指向 const 的指针也能 delete
    int* n = nullptr;
    delete n;                                  // OK：空指针
    Handle h{new int(2)};
    delete h;                                  // OK：按语境隐式转换为 int*
    delete ([] { return new int(3); })();      // OK：lambda 加了括号
}
```

操作数是类类型时，它按语境隐式转换（[[conv]]）为对象指针，这要求类恰好有一个这样的非 explicit 转换函数。否则操作数必须是对象指针类型的纯右值，`void*` 和函数指针都不行：

```cpp title="delete-operand-error.cpp" error
void f(void* vp, void (*fp)()) {
    delete vp;                         // error: void 不是对象类型
    delete fp;                         // error: 函数指针
    delete [] { return new int; }();   // error: [] 被解释为 delete[]
}
```

`delete` 后紧跟空方括号时总是解释成数组形式，所以以 `[]` 开头的 lambda 必须加括号（脚注 55）。`delete vp` 在 C++23 模式下，本机 Clang 23 只给一条 `-Wdelete-incomplete` 警告就接受；它一直是非良构的，警告已经满足诊断要求。

`delete` 指向 `const` 的指针不需要先 `const_cast`（注 2）。析构不算修改，局部的 `const` 对象离开作用域时同样会被析构。

## 哪些指针可以删除（¶2）

```cpp title="delete-mismatch.cpp" run ub
int main() {
    int* p = new int[4];
    delete p;           // UB: 数组 new 必须用 delete[]
}
```

¶2 规定了操作数的值可以是什么，其他情况都是 UB：

| 形式 | 操作数可以是 |
|---|---|
| `delete p` | 空指针；非数组 *new-expression* 的结果；或者指向这样创建的对象的基类子对象的指针 |
| `delete[] p` | 空指针；数组 *new-expression* 的结果，而且它用的不是不分配存储的放置形式 `new (buf) T[n]` |

注 1 指出，选哪种形式取决于分配出来的对象类型，而不是 `new` 的写法：`using A = int[4]; int* p = new A;` 必须用 `delete[] p`。脚注 56 补充，长度为零的数组没有首元素，但它的 `new` 结果仍然要用 `delete[]` 释放。

上面的例子，Clang 在编译期给出 `-Wmismatched-new-delete` 警告；运行期，设置 `ASAN_OPTIONS=alloc_dealloc_mismatch=1` 后（macOS 上默认关闭），AddressSanitizer 报告 `alloc-dealloc-mismatch (operator new [] vs operator delete)`。

常见的违规还有：

- 删除栈上或静态对象的地址；
- 删除数组中间元素或成员子对象的地址；
- 重复删除：第一次 `delete` 后，指向该对象的所有指针都成为无效指针值（[[basic.stc.dynamic.deallocation]]）；
- 对 `new (buf) T[n]` 创建的数组用 `delete[]`。这块存储不是 `operator new[]` 分配的，应逐个析构元素，例如用 `std::destroy_n`。

## 基类指针与虚析构函数（¶3）

```cpp title="no-virtual-dtor.cpp" run ub
struct B { ~B() {} };                        // 非虚析构函数
struct D : B {
    int* buf = new int[4];
    ~D() { delete[] buf; }
};
int main() {
    B* p = new D;
    delete p;    // UB: 静态类型 B 与动态类型 D 不同，而 B 没有虚析构函数
}
```

¶3 对单对象 `delete`：如果被删除对象的静态类型（指针声明的类型）与动态类型（实际创建的类型）不相似（[[conv.qual]]，即除了各层 cv 限定之外不同），而选中的释放函数又不是后文的销毁型 operator delete，那么静态类型必须是动态类型的基类，并且必须有虚析构函数，否则是 UB。

本机上这个程序只调用了 `~B()`，`~D()` 被跳过，`buf` 泄漏，LeakSanitizer 报告 16 字节泄漏。但后果不止泄漏：传给 sized `operator delete` 的大小是 `sizeof(B)`；多重继承时 `B*` 甚至不等于对象的起始地址，释放函数收到的是错误的指针。

对数组 `delete[]`，静态类型与动态类型不相似就是 UB，没有虚析构函数这个例外：

```cpp title="polymorphic-array.cpp" ub
struct B { virtual ~B() = default; };
struct D : B { int extra; };
int main() {
    B* a = new D[2];
    delete[] a;    // UB: 数组的静态类型 B 与动态类型 D 不相似
}
```

`delete[]` 要按元素大小遍历数组，元素步长是 `sizeof(D)`，而经 `B*` 只知道 `sizeof(B)`，虚析构函数解决不了步长问题。

## 不完整类型（¶4）{{c++26}}

```cpp title="delete-incomplete.cpp" error
struct Inc;
void f(Inc* p) {
    delete p;    // error: 删除指向不完整类型的指针（C++26）
}
```

¶4 被删除对象在 `delete` 处是不完整类类型时，程序非良构。

这是 C++26 的修改（[[P3144R2]]）。此前的规则是：如果完整类型有非平凡析构函数或类专属释放函数，行为未定义。编译器在 `delete` 处看不到析构函数，只能不调用它，再调用全局 `operator delete`，程序编译通过，析构函数却从未执行。本机 Clang 23 在 `-std=c++2c` 下报错 `cannot delete pointer to incomplete type 'Inc'`，在 `-std=c++23` 下只给 `-Wdelete-incomplete` 警告。

`std::unique_ptr<T>` 的默认删除器一直要求 `T` 是完整类型（[[unique.ptr.dltr.dflt#3]]），所以 pimpl 惯用法要把析构函数定义在 `Impl` 已经完整的 `.cpp` 文件里。

## 析构（¶5）

¶5 操作数不是空指针、而且选中的不是销毁型 operator delete 时，`delete` 调用对象或各数组元素的析构函数（如果有）。析构函数必须在 `delete` 处可访问。数组元素按地址递减的顺序析构，也就是构造完成顺序的逆序。

```cpp title="delete-private-dtor.cpp" error
struct Priv {
private:
    ~Priv();
};
void f(Priv* p) {
    delete p;    // error: 析构函数不可访问
}
```

把析构函数设为私有或受保护，可以强制对象只能经特定接口销毁，例如引用计数类的 `release()`。

## 空指针与释放函数的调用（¶6）

¶6 操作数不是空指针时，`delete` 调用释放函数，第一个实参是当初分配函数返回的值。注 3 补充，即使析构函数抛出异常，释放函数也照样调用。

操作数是空指针时，是否调用释放函数是未指定的。析构函数一定不会被调用；释放函数即使被调用，收到的也是空指针，标准库的版本对空指针什么都不做（[[new.delete.single]]）。所以 `if (p) delete p;` 中的检查是多余的，而自定义的 `operator delete` 必须能处理空指针。

```cpp title="delete-null.cpp" ok
struct S { ~S() {} };
void f() {
    S* p = nullptr;
    delete p;          // OK：不调用 ~S()；operator delete 可能调用，也可能不调用
    delete[] p;        // OK：同上
}
```

¶6.2 和 ¶6.3 处理另一种情况：实现可以省略 `new` 的分配调用，或者把几次 `new` 的分配合并成一次（[[expr.new#14]]）。这时只有共享那块存储的所有对象都删除了，才调用一次释放函数；分配被省略的则不调用。

## 找到哪些释放函数（¶7–¶8）

¶7 单对象 `delete` 调用 `operator delete`，数组 `delete` 调用 `operator delete[]`。标准库提供全局版本，程序可以替换它们（[[replacement.functions]]），也可以为类提供类专属版本（[[class.free]]）。

¶8 如果 `delete` 前没有 `::`，而操作数指向类类型 `T` 或 `T` 的数组：

- ¶8.1 单对象 `delete`，且 `T` 有虚析构函数：用在动态类型的虚析构函数定义处选出的那个释放函数（[[class.dtor]]）；
- ¶8.2 否则在 `T` 的作用域中查找。

其他情况，包括写了 `::`、不是类类型、类作用域中没找到，都在全局作用域查找。找到的声明只保留**普通释放函数**（usual deallocation function，[[basic.stc.dynamic.deallocation]]），也就是参数形如 `(void*)`、`(void*, std::size_t)`、`(void*, std::align_val_t)` 等的版本，放置形式的都丢弃。

注 5：如果类里只有放置形式的释放函数，丢弃后集合为空，程序非良构，而且不会退回全局作用域，因为查找已经在类中找到了声明。

```cpp title="only-placement-delete.cpp" error
#include <cstddef>
struct OnlyPlacement {
    static void* operator new(std::size_t, int);
    static void operator delete(void*, int);   // 只有放置形式
};
void g(OnlyPlacement* p) {
    delete p;    // error: 类中找到的声明全部被丢弃
}
```

¶8.1 让虚析构函数和类专属 `operator delete` 能正确配合：经 `Base*` 删除 `Derived` 对象时，用的是 `Derived` 作用域里的释放函数，传入的也是 `Derived` 的大小。

```cpp title="virtual-dtor-dealloc.cpp" run ok
#include <cstdio>
#include <new>

struct Base {
    virtual ~Base() = default;
};
struct Derived : Base {
    double payload[4];
    static void operator delete(void* p, std::size_t n) {   // 类专属，带大小
        std::printf("Derived::operator delete(p, %zu)\n", n);
        ::operator delete(p);
    }
};

int main() {
    Base* b = new Derived;
    delete b;   // 选出 Derived::operator delete，大小为 sizeof(Derived)
}
```

64 位平台上输出 `Derived::operator delete(p, 40)`。

## 选择哪一个释放函数（¶9）

¶9 查找得到一组普通释放函数后，依次筛选：

| 步骤 | 规则 |
|---|---|
| ¶9.1 | 有销毁型 operator delete 时，淘汰所有非销毁型的 |
| ¶9.2 | 类型有超出默认的对齐要求（new-extended alignment）时，优先带 `std::align_val_t` 形参的，否则优先不带的；有优先者就淘汰其余 |
| ¶9.3 | 只剩一个时选中它 |
| ¶9.4 | 释放函数属于类作用域时，选不带 `std::size_t` 形参的 |
| ¶9.5 | 类型完整时选带 `std::size_t` 形参的；对数组 `delete` 还要求元素是有非平凡析构函数的类 |
| ¶9.6 | 否则，是否选带 `std::size_t` 的版本未指定 |

除非释放函数是在动态类型的虚析构函数定义处选出的（¶8.1），它必须在 `delete` 处可访问。

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
    delete new int;    // 全局、类型完整：¶9.5，带大小
    delete new Both;   // 类中两种都有：¶9.4，不带大小
}
```

本机 Clang 23 输出 `global sized 4`、`Both: unsized`、`global unsized`。用 `-fno-sized-deallocation` 编译时，第一行变成 `global unsized`。

两条规则方向相反，是出于兼容。类专属的 `operator delete(void*, std::size_t)` 从 C++98 起就合法，类同时声明两种版本时一直用单参数的那个，C++14 不能改变已有程序的行为。全局的带大小版本是 C++14 新加的（[[N3778]]），可以直接规定能传大小就传大小，这样 tcmalloc、jemalloc 这类分配器释放时不必再查块的大小。

数组只在元素有非平凡析构函数时才要求带大小，因为只有这时 `new[]` 才会记录元素个数（数组 cookie），`delete[]` 才算得出总大小。`-fno-sized-deallocation` 违反了 ¶9.5，但在兼容不提供带大小版本的旧分配器时有用。

## 传给释放函数的实参（¶10）

¶10 先定义**被删除对象**（[[g:deleted-object]]）：单对象 `delete` 中，如果操作数所指对象 *A* 的静态类型没有虚析构函数，被删除对象就是 *A*，否则是 *A* 的最终派生对象；数组 `delete` 中是整个数组对象。

| 形参 | 实参 |
|---|---|
| 第一个（`void*`，或销毁型的 `T*`） | 被删除对象的地址；数组要按分配开销调整，即退回到 cookie 之前 |
| `std::destroying_delete_t` | 一个未指定的值 |
| `std::align_val_t` | 被删除对象类型的对齐 |
| `std::size_t` | 被删除对象的大小；数组是数组大小加上分配开销 |

注 7：形成第一个实参时忽略 cv 限定，所以 `const S*` 的值可以直接传给 `void*` 形参。

注 8：如果调用的是可替换的标准释放函数，传入的指针、大小、对齐必须与当初分配时一致，否则是 UB（[[new.delete.single]]）。经没有虚析构函数的基类指针删除对象，实践中会破坏分配器，原因之一就是大小传错了。

## 销毁型 operator delete {{c++20}}

**销毁型 operator delete**（destroying operator delete，[[P0722R3]]）是一种类专属的 `operator delete`，第一个形参是 `C*` 而不是 `void*`，第二个形参的类型是 `std::destroying_delete_t`（[[basic.stc.dynamic.deallocation]]）。选中它时：

- `delete` 不调用析构函数（¶5），析构由它自己负责；
- ¶3 要求的虚析构函数不再需要，由它自己找出动态类型；
- 它收到的是带类型的对象指针，对象此时仍然活着。

下面的例子不用虚函数表，而是用一个类型标签实现多态删除：

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
    switch (p->kind) {        // 对象还活着，可以读 kind
    case circle: { auto* c = static_cast<Circle*>(p); c->~Circle(); ::operator delete(c, sizeof(Circle)); break; }
    case square: { auto* s = static_cast<Square*>(p); s->~Square(); ::operator delete(s, sizeof(Square)); break; }
    }
}

int main() {
    Shape* a = new Circle;
    Shape* b = new Square;
    delete a;   // OK：没有虚析构函数，但选中的是销毁型 delete
    delete b;
}
```

另一个用途是尾部带变长数据的对象：分配大小记录在对象自己的字段里。普通 `operator delete` 被调用时对象已经析构，读不到这个字段；销毁型版本可以先读出大小，再析构、释放。

## delete this

标准没有禁止 `delete this`。按 ¶2，只要 `*this` 是非数组 `new` 创建的最终派生对象，`delete this` 就有定义。之后的限制来自 [[basic.life]] 和 [[basic.stc.dynamic.deallocation]]：

- 不能再访问任何非静态成员，也不能调用非静态成员函数，对象已经不在生命周期内；
- `this` 的值成为无效指针值，连复制它都是实现定义的行为；
- 对栈上或静态对象调用会 `delete this` 的成员函数是 UB。

```cpp title="delete-this.cpp" run ok
#include <cstdio>
struct Node {
    int refs = 1;
    void release() {
        if (--refs == 0) delete this;   // OK：对象由非数组 new 创建，之后不再访问成员
    }
    ~Node() { std::puts("~Node"); }
};
int main() {
    Node* n = new Node;
    n->release();    // 之后 n 是无效指针值
}
```

!!! impl "实现视角"
    - Itanium C++ ABI 为有虚析构函数的类在虚表里放两个析构函数：完整对象析构函数 D1 只析构；删除析构函数（deleting destructor）D0 析构之后调用 `operator delete`。`delete pb` 编译为对 D0 的虚调用，¶8.1 所说的在动态类型析构函数定义处选出的释放函数，就是 D0 里调用的那个，`sizeof(Derived)` 也在那里确定。
    - MSVC 用 scalar deleting destructor，带一个标志参数决定析构后是否释放；数组另有 vector deleting destructor。
    - 基类没有虚析构函数时，编译器直接调用 `B::~B()`，再用 `B*` 的值和 `sizeof(B)` 调用 `operator delete`。单继承下基类子对象通常在偏移 0，看起来能运行；多重继承下指针值是错的，会破坏堆。
    - 带大小的释放：Clang 从 19 版起默认开启，GCC 在 C++14 及以上模式默认开启，MSVC 也默认开启。
    - GCC 和 Clang 对单对象 `delete` 都先检查空指针，为空时既不析构也不调用 `operator delete`，¶6 允许这样做。

## 历史与演进

!!! history
    - C++98 已有 `delete`/`delete[]` 的配对规则、基类需要虚析构函数、删除不完整类型（析构非平凡时为 UB）。
    - C++14 引入带大小的释放（[[N3778]]），形成 ¶9 中 sized 与 unsized 的选择规则。
    - C++17 引入带对齐的释放函数（[[P0035R4]]，¶9.2）。
    - C++20 引入销毁型 operator delete（[[P0722R3]]）。
    - C++26 把删除不完整类型改为非良构（[[P3144R2]]）。
    - C++26 之后的草案规定，释放函数带有可能抛出的异常规约时程序非良构（[[diff.cpp26]]）{{c++29}}。此前没写 *noexcept-specifier* 的释放函数已隐式为 `noexcept`，但显式写 `noexcept(false)` 是允许的。

## 常见误解

!!! pitfall "多态基类的析构函数可以不是虚的"
    只要可能经基类指针 `delete` 派生类对象，基类就需要虚析构函数，或者改用销毁型 delete。常见做法是：多态基类的析构函数要么是 `public virtual`，要么是 `protected` 非虚，后者让经基类指针 `delete` 的代码在编译期就被拒绝。

!!! pitfall "`delete p; p = nullptr;` 能防止所有重复释放"
    它只保护这一个变量。指向同一对象的其他指针，包括 `this`，仍然是无效指针值。

!!! pitfall "自定义 `operator delete` 不必处理空指针"
    对空指针是否调用释放函数是未指定的（¶6），实现可以用空指针调用你的类专属版本。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct B { virtual ~B(); static void operator delete(void*); };
    struct D : B { static void operator delete(void*, std::size_t); };
    B* p = new D;
    delete p;
    ```
    调用哪个释放函数？传入什么实参？

<details markdown="1">
<summary>答案</summary>

`B` 有虚析构函数，按 ¶8.1，释放函数在 `D` 的隐式虚析构函数定义处选出：在 `D` 的作用域查找，找到 `D::operator delete(void*, std::size_t)`，它隐藏了 `B` 的版本。只有一个候选，按 ¶9.3 选中。

被删除对象是最终派生对象，所以实参是 `D` 对象的地址和 `sizeof(D)`（¶10）。因为它是在虚析构函数定义处选出的，¶9 末句的可访问性要求不在 `delete p` 处检查。
</details>

!!! question "思考题 2"
    `struct T { int x; }; const T* q = new const T[2]{{1}, {2}}; delete[] q;` 合法吗？传给 `operator delete[]` 的是什么？

<details markdown="1">
<summary>答案</summary>

合法。注 2 允许删除指向 `const` 的指针，注 7 说明形成实参时忽略 cv 限定。`T` 的析构函数是平凡的，实现通常不放数组 cookie，所以按开销调整后的地址就是 `q` 本身；如果调用的是带大小的版本，大小是 `2 * sizeof(T)` 加上开销。

注意不带初始化器的 `new const T[2]` 是非良构的：`const` 对象默认初始化要求类型可以 const 默认构造，而 `T` 的 `x` 没有默认成员初始化器。
</details>

## 小结

| 问题 | 段落 | 答案 |
|---|---|---|
| 操作数 | ¶1 | 对象指针纯右值，或能按语境转换成对象指针的类；`delete []` 总是数组形式 |
| 合法的值 | ¶2 | 空指针，或对应形式 `new` 的结果（单对象还可以是基类子对象指针）；否则 UB |
| 静态与动态类型 | ¶3 | 单对象：不相似时需要虚析构函数，销毁型 delete 例外；数组：不相似即 UB |
| 不完整类型 | ¶4 | 非良构（C++26） |
| 析构 | ¶5 | 非空且不是销毁型 delete 时调用，须可访问；数组逆序 |
| 释放 | ¶6 | 非空时调用；空指针时未指定 |
| 查找 | ¶8 | 有虚析构函数时用动态类型析构函数处选出的；否则类作用域，再全局；只留普通释放函数 |
| 选择 | ¶9 | 销毁型 > 对齐匹配 > 唯一者 > 类作用域取不带大小 > 完整类型取带大小 > 未指定 |
| 实参 | ¶10 | 被删除对象的地址（数组要调整）、对齐、大小（数组含开销） |
