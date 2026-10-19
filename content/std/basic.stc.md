---
title: 存储期
summary: 对象的存储能存在多久：静态、线程、自动、动态四种存储期分别由什么声明产生；动态存储由全局 operator new / operator delete 管理，它们的签名和必须遵守的约定也在这里规定。
status: done
covers: *
papers: N3778, P0035R4, P0722R3, N3664
related: basic.life, intro.object, expr.new, expr.delete, new.delete, basic.start.static, basic.start.term, stmt.dcl
tags: 存储期, operator new, operator delete, 动态内存
updated: 2026-10-19
---

!!! tldr
    - 存储期描述的是存储能存在多久，不是对象：对象的生命周期总落在存储期之内，但可以短得多。
    - 命名空间变量和 `static` 变量是静态存储期，`thread_local` 是线程存储期，普通局部变量和参数是自动存储期，`new` 出来的是动态存储期。
    - 有副作用的静态变量和局部变量，即使看起来没被使用，编译器也不能把它们删掉，RAII 守卫和注册器因此可靠。
    - 可替换的 `operator new` 失败时只能抛 `std::bad_alloc`，不能返回空指针；请求 0 字节也必须返回唯一的非空指针。违反这些约定的替换版本导致 UB。
    - 释放函数分为常规的和 placement 形式的；*delete-expression* 只调用常规释放函数。C++20 还有销毁型 `operator delete`，它连析构也一并接管。

## 四种存储期 [basic.stc.general]

```cpp run title="four-durations.cpp" ok
int a;                       // 静态：命名空间作用域
thread_local int t;          // 线程：每个线程一份

int f(int param) {           // param：自动
    int local = param;       // 自动：块作用域
    static int calls = 0;    // 静态：块作用域的 static
    int* p = new int(local); // *p：动态
    delete p;
    return ++calls;
}

int main() { return f(a + t) == 1 ? 0 : 1; }
```

¶1 **存储期**（storage duration）是对象的一个属性，规定了容纳对象的存储至少能存在多久。它由创建对象的那个构造决定，共四种：

| 存储期 | 由什么产生 | 存储持续到 |
|---|---|---|
| 静态 | 命名空间作用域变量；首次声明带 `static` 或 `extern` 的变量；静态数据成员 | 程序结束 |
| 线程 | `thread_local` 变量 | 线程结束 |
| 自动 | 块作用域变量（没有 `static`、`thread_local`、`extern`）；函数参数 | 所在块退出；参数在销毁之后 |
| 动态 | *new-expression*；隐式创建的对象（[[intro.object]]） | 被释放 |

存储期管的是存储，生命周期（[[basic.life]]）管的是对象。对象的生命周期总落在存储期之内，但可以短得多。例如用 placement new 放进静态缓冲区的对象，可以在程序中途结束生命周期，而那块存储一直都在。

¶2 静态、线程、自动存储期属于声明引入的对象和临时对象（[[class.temporary]]）；动态存储期属于 *new-expression* 创建的对象和隐式创建的对象。¶3 引用也按同样的方式分类。¶4 子对象和引用成员的存储期就是其完整对象的存储期：`new S` 的成员是动态存储期，局部变量 `S s;` 的成员是自动存储期。

注 1 提醒，一块存储的存储期结束后，指向它的指针变成**无效指针值**（invalid pointer value，[[basic.compound]]）。解引用它是 UB，连复制、比较它的效果都由实现定义。

## 静态存储期 [basic.stc.static]

¶1 没有线程存储期、并且属于命名空间作用域或首次声明带 `static` 或 `extern` 的变量，具有**静态存储期**。存储持续整个程序运行期间，初始化见 [[basic.start.static]]，销毁见 [[basic.start.term]]。

块作用域的 `static` 变量也是静态存储期。它的存储在程序加载时就已存在，通常在 `.bss` 或 `.data` 段里；首次经过声明时发生的只是初始化（[[stmt.dcl]]）。

¶2 如果静态存储期变量的初始化或析构函数有副作用，即使看起来没被使用，实现也不得消除它。唯一的例外是 [[class.copy.elision]] 允许的复制消除。注册器惯用法依赖的就是这一条：

```cpp run title="registrar.cpp" ok
#include <cstdio>

struct Registrar {
    Registrar() { std::puts("registered"); }   // 有副作用的初始化
};

static Registrar reg;   // 从未被使用，但不得消除：启动时一定打印

int main() {}
```

!!! warning "链接器不受这条约束"
    ¶2 约束的是已经成为程序一部分的变量。如果 `reg` 在静态库（`.a`）里一个没有任何符号被引用的目标文件中，链接器根本不会把这个目标文件拉进程序，这并不违反 ¶2。插件注册代码放进静态库后不起作用，常见原因就在这里。

## 线程存储期 [basic.stc.thread]

¶1 用 `thread_local` 声明的变量具有**线程存储期**，存储持续到创建它的线程结束。每个线程有一个独立的对象，使用这个名字时，指的是当前线程的那一个。¶2 是一条注：线程存储期变量如果被构造了，会在线程退出时销毁（[[basic.start.term]]）。

```cpp run title="thread-local.cpp" ok
#include <cassert>
#include <thread>

thread_local int counter = 0;   // 每个线程一份

void work() {
    for (int i = 0; i < 1000; ++i) ++counter;   // 没有数据竞争：各用各的
    assert(counter == 1000);
}

int main() {
    std::thread t1(work), t2(work);
    t1.join(); t2.join();
    return counter;   // 主线程自己的 counter：0
}
```

块作用域里的 `thread_local int x;` 隐含 `static`（[[dcl.stc]]），不会在每次进入块时重新创建。

## 自动存储期 [basic.stc.auto]

¶1 属于块作用域、没有显式声明为 `static`、`thread_local` 或 `extern` 的变量具有**自动存储期**，存储持续到创建它的块退出。函数参数也是自动存储期，它的存储在参数销毁之后立即结束。

参数这句话写得很仔细。参数在函数返回时销毁，还是在包含调用的完整表达式结束时销毁，由实现定义（[[expr.call]]），所以存储的结束点只能跟着销毁走，而不是跟着函数返回走。

¶2 如果自动存储期变量的初始化或析构函数有副作用，即使看起来没被使用，实现也不得在块结束前销毁它，也不得把它优化掉（复制消除除外）。RAII 守卫因此可靠：

```cpp run title="raii-guard.cpp" ok
#include <mutex>

std::mutex m;
int shared = 0;

void f() {
    std::lock_guard<std::mutex> g(m);   // g 从未被使用，但不得提前销毁
    ++shared;
}   // 锁在这里释放

int main() { f(); return shared == 1 ? 0 : 1; }
```

!!! pitfall "临时对象不是变量"
    `std::lock_guard<std::mutex>{m};` 没有名字，创建的是临时对象，在这条语句结束时就销毁了（[[class.temporary]]），保护不了下一行。¶2 只保护变量。

## 动态存储期 [basic.stc.dynamic]

### 分配函数和释放函数 [basic.stc.dynamic.general]

¶1 对象可以在运行时用 *new-expression* 创建（[[expr.new]]），用 *delete-expression* 销毁（[[expr.delete]]）。实现通过全局**分配函数**（allocation function）`operator new`、`operator new[]` 和全局**释放函数**（deallocation function）`operator delete`、`operator delete[]` 管理动态存储。注 1 指出，`operator new(std::size_t, void*)` 这类非分配形式（[[new.delete.placement]]）既不分配也不释放。

¶2 标准库为这些函数提供默认定义，其中一部分是**可替换的**（replaceable，[[dcl.fct.def.replace]]）：程序自己定义一个同签名的函数，就能取代库版本。下面这些函数在每个翻译单元的全局作用域里隐式声明：

```cpp
void* operator new(std::size_t);
void* operator new(std::size_t, std::align_val_t);
void  operator delete(void*) noexcept;
void  operator delete(void*, std::size_t) noexcept;
void  operator delete(void*, std::align_val_t) noexcept;
void  operator delete(void*, std::size_t, std::align_val_t) noexcept;
// 以及对应的 operator new[]、operator delete[]
```

隐式声明只引入这四个函数名，不引入 `std`、`std::size_t`、`std::align_val_t`（注 2）。所以不包含任何头文件也能用 `new` 和 `delete`：

```cpp run title="no-include-new.cpp" ok
int main() {
    int* p = new int(1);          // OK：不需要 #include <new>
    void* q = operator new(16);   // OK：直接调用分配函数
    operator delete(q);
    delete p;
    // std::size_t n = 0;         // error：没有声明 std::size_t
}
```

`nothrow` 版本和 placement 版本不是隐式声明的，要包含 `<new>`。类也可以声明自己的分配和释放函数（[[class.free]]），*new-expression* 会先在类里查找。

¶3 如果分配或释放函数的行为不满足下面两节规定的语义约束，行为未定义。这是对替换版本的要求：替换了全局 `operator new`，就要遵守同样的约定。

### 分配函数 [basic.stc.dynamic.allocation]

#### 签名（¶1）

不是类成员的分配函数必须在全局作用域，不能有内部链接。返回类型必须是 `void*`；第一个参数必须是 `std::size_t`，表示请求的字节数，而且不能有默认实参。分配函数可以是模板，但返回类型和第一个参数不能用模板参数，模板至少要有两个参数，以免截走普通的 `new T`。

```cpp run title="alloc-sig.cpp" error
#include <cstddef>

namespace N { void* operator new(std::size_t); }   // error：不在全局作用域
static void* operator new(std::size_t, int);       // error：内部链接
void* operator new(std::size_t = 0, double);       // error：第一个参数有默认实参
template<class T> void* operator new(T);           // error：只有一个参数
```

#### 成功时（¶2）

成功时返回一块存储的起始地址，大小至少是请求的字节数。相继分配的存储之间的次序、是否连续、初值都是未指定的。

可替换的分配函数成功时返回非空指针，并且与之前返回过的任何值都不同，除非那个值已经交给可替换的释放函数释放了。请求 0 字节也一样，两次 `new char[0]` 得到两个不同的非空指针。脚注 18 说明，这些规则有意与 `malloc` 保持一致，好让 `operator new` 能直接用 `malloc` 实现；区别只在 C 的 `malloc(0)` 可以返回空指针。通过零字节请求返回的指针做间接访问是 UB。

```cpp run title="zero-size.cpp" ok
int main() {
    char* a = new char[0];   // 非空、唯一
    char* b = new char[0];
    bool distinct = a != b;  // 必为 true
    // *a = 'x';             // UB：通过零大小分配的指针访问
    delete[] a;
    delete[] b;
    return distinct ? 0 : 1;
}
```

对标准库自己的版本（[[new.delete.single]]、[[new.delete.array]]），返回的存储还保证与调用者能访问到的任何其他对象都不重叠。

#### 对齐（¶3）

除保留的 placement 分配函数外，返回的存储必须按下面的方式对齐：

- ¶3.1 有 `std::align_val_t` 参数时，按该参数指定的对齐；
- ¶3.2 否则，如果是 `operator new[]`，对任何不大于请求大小、对齐不超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的对象类型都对齐；
- ¶3.3 否则，对大小正好等于请求大小、对齐不超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的对象类型对齐。

超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的对齐叫 new-extended 对齐（[[basic.align]]），要用带 `align_val_t` 的版本。数组版本的要求更宽，因为 `new char[64]` 常被当作缓冲区放好几个较小的对象。按 ¶3.3，请求 2 字节时只需 2 字节对齐，不过主流实现都直接给出 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`。

#### 失败时（¶4）

分配失败时，分配函数可以调用当前安装的 new-handler（[[new.handler]]），程序提供的版本可以用 `std::get_new_handler` 取得它。不抛出异常的分配函数（例如 `nothrow` 版本）通过返回空指针表示失败；其他分配函数**永不返回空指针**，只能抛出能被 `std::bad_alloc` 处理器捕获的异常。

所以普通的 `new T` 之后不必检查空指针，编译器也会据此删掉这样的检查。[[expr.new]] 只在分配函数不抛出异常时，才要求先检查返回值再初始化对象。

#### 何时调用（¶5）

全局分配函数只在这几种情况下被调用：*new-expression*；用函数调用语法直接调用；为协程状态分配存储（[[dcl.fct.def.coroutine]]）；通过标准库函数间接调用。

注 2 列出了不用全局分配函数的对象：静态存储期对象，线程存储期的对象和引用，`std::type_info` 对象，契约违反时的 `std::contracts::contract_violation` 对象 {{c++26}}，以及异常对象（[[except.throw]]）。异常对象由实现另行分配，例如 Itanium ABI 的 `__cxa_allocate_exception`。

!!! note "分配可以被省略"
    [[expr.new]] 允许实现省略 *new-expression* 对可替换全局分配函数的调用，改用自己提供的存储（例如栈上），或者把几次分配合并成一次。所以替换 `operator new` 来计数，结果不一定等于源码里 `new` 出现的次数：

    ```cpp run title="alloc-elision.cpp" unspecified
    #include <cstdio>
    #include <cstdlib>
    #include <new>

    int count = 0;
    void* operator new(std::size_t n) {
        ++count;
        if (void* p = std::malloc(n ? n : 1)) return p;
        throw std::bad_alloc();
    }
    void operator delete(void* p) noexcept { std::free(p); }
    void operator delete(void* p, std::size_t) noexcept { std::free(p); }

    int main() {
        int* p = new int(42);
        int v = *p;
        delete p;
        std::printf("v=%d count=%d\n", v, count);   // 本机 Clang 23：-O0 为 1，-O2 为 0
    }
    ```

    这条许可只针对 *new-expression*，直接写 `::operator new(n)` 的调用不能省略。Clang 提供 `__builtin_operator_new`，让 `std::allocator` 这类库代码也能得到这项优化，那是实现扩展。常量求值中对可替换分配函数的调用总是被省略，`constexpr` 里能用 `new` 靠的就是这一点。

### 释放函数 [basic.stc.dynamic.deallocation]

#### 签名（¶1–¶3）

¶1 不是类成员的释放函数必须在全局作用域，不能有内部链接。¶3 规定，释放函数的返回类型必须是 `void`，不能有潜在抛出的异常规格（不写时隐式就是 `noexcept`）；第一个参数是 `void*`，销毁型 delete（见下）除外。

¶3 还定义了**常规释放函数**（usual deallocation function）：第一个参数之后，依次只有可选的 `std::destroying_delete_t`、可选的 `std::size_t`、可选的 `std::align_val_t`。释放函数可以是模板，规则与分配函数相同，但模板的实例永远不是常规释放函数。

区分常规与否，是因为 *delete-expression* 只调用常规释放函数（[[expr.delete]]）。其他形式的 `operator delete` 只有一个用途：placement new 里的构造函数抛出异常时，与那个 placement `operator new` 配对，释放刚分配的存储。

#### 尺寸释放和对齐释放

`operator delete(void*, std::size_t)` 是**尺寸释放**（sized deallocation）{{c++14}}。*delete-expression* 知道对象大小时把它传过去，分配器就不必自己记录或查找块大小（[[N3778]]）。

脚注 19 指出了一个副作用：有了全局的 `operator delete(void*, std::size_t)`，`void* operator new(std::size_t, std::size_t)` 就不能再当 placement 分配函数用了，因为与它配对的 placement delete 和尺寸释放函数签名相同。这是 C++14 的一处不兼容变更（[[diff.cpp11.basic]]）。

带 `std::align_val_t` 的版本是**对齐释放** {{c++17}}，与 new-extended 对齐的分配配对（[[P0035R4]]）。

#### 销毁型 delete {{c++20}}

¶2 第二个参数类型为 `std::destroying_delete_t` 的释放函数是**销毁型 operator delete**（destroying operator delete）。它必须是类的成员函数，第一个参数是指向该类的指针；它必须是常规释放函数；注 1 说明，数组删除不能使用它。

普通的 `delete p` 先调用析构函数，再调用 `operator delete` 释放存储。销毁型 delete 把两步都交给你：编译器不调用析构函数，直接把指针交给它。

```cpp run title="destroying-delete.cpp" ok
#include <cstdio>
#include <new>

struct Shape {
    enum Kind { kCircle, kSquare } kind;
    void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape { double r; };
struct Square : Shape { double side; };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
    // 按 kind 手动分派析构与释放，不需要虚析构函数
    if (p->kind == kCircle) {
        auto* c = static_cast<Circle*>(p);
        c->~Circle();
        ::operator delete(c, sizeof(Circle));
    } else {
        auto* s = static_cast<Square*>(p);
        s->~Square();
        ::operator delete(s, sizeof(Square));
    }
    std::puts("destroyed");
}

int main() {
    Shape* s = new Circle{{Shape::kCircle}, 1.0};
    delete s;   // 不调用 ~Shape()，直接调用 Shape::operator delete
}
```

它适合两类代码：不用虚析构函数的手工多态，例如 LLVM 的 `Value` 层次；以及和尾部数据一起分配的变长对象，释放时需要知道真实大小。销毁型 delete 由 [[P0722R3]] 引入。

#### 语义（¶4–¶5）

¶4 传给释放函数的第一个实参可以是空指针，对标准库提供的释放函数，这样的调用没有效果，所以 `delete nullptr` 是安全的。¶5 实参非空时，标准库的释放函数释放它所指的存储，这块存储的存储期随之结束，所有指向它的指针都变成无效指针值。

## 替换全局分配函数

[[dcl.fct.def.replace]] 和 [[new.delete]] 规定，程序可以在某一个翻译单元里定义可替换的全局分配或释放函数。替换版本不能声明为 `inline`，并且必须遵守上面的约定：

```cpp run title="replace-new.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

static std::size_t live = 0;

void* operator new(std::size_t n) {
    if (n == 0) n = 1;                    // 0 字节也要返回唯一的非空指针
    for (;;) {
        if (void* p = std::malloc(n)) { ++live; return p; }
        std::new_handler h = std::get_new_handler();
        if (!h) throw std::bad_alloc();   // 失败只能抛异常，不能返回空
        h();                              // 让 new-handler 设法腾出内存
    }
}
void operator delete(void* p) noexcept {
    if (p) { --live; std::free(p); }
}
void operator delete(void* p, std::size_t) noexcept { operator delete(p); }

int main() {
    auto* v = new int[4];   // 默认的 operator new[] 调用 operator new
    delete[] v;
    std::printf("live=%zu\n", live);
}
```

库的默认 `operator new[]` 和 `nothrow` 版本都会（直接或间接）调用 `operator new(std::size_t)`，默认的 `operator delete[]` 和尺寸版本也会调用 `operator delete(void*)`（[[new.delete]]）。所以替换这两个基本函数，通常就能截获所有非对齐的全局分配。对齐版本是独立的一组，要单独替换。

## 实现视角

!!! impl
    - libstdc++ 和 libc++ 的默认 `operator new` 就是 `malloc`，加上循环调用 new-handler 和抛 `bad_alloc`，与脚注 18 的意图一致。对齐版本调用 `aligned_alloc` 或 `posix_memalign`，Windows 上是 `_aligned_malloc`。
    - 尺寸释放：GCC 在 C++14 起默认开启；Clang 很长时间里需要 `-fsized-deallocation`，因为它依赖运行时库提供对应的符号，后来才改为默认开启。tcmalloc、jemalloc 这类分配器能从尺寸信息中明显获益。
    - 分配省略：Clang 会积极地消除配对的 `new`/`delete`，上面计数的例子在 `-O2` 下输出 `count=0`。
    - 线程存储期：ELF 平台用 TLS 段（`.tdata`、`.tbss`）和 `__tls_get_addr` 实现。有非平凡构造或析构的 `thread_local` 需要一个首次使用时完成初始化的包装函数（Itanium ABI 的 TLS wrapper），以及在线程退出时执行析构的注册机制（`__cxa_thread_atexit`）。

## 历史与演进

!!! history
    - C++98：静态、自动、动态三种存储期；全局 `operator new`/`delete` 及其数组、`nothrow`、placement 形式。
    - C++11：新增线程存储期和 `thread_local`。
    - C++14：尺寸释放（[[N3778]]）；允许省略和合并分配（[[N3664]]）。
    - C++17：对齐分配和释放、`std::align_val_t`、`__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[P0035R4]]）。
    - C++20：销毁型 `operator delete`（[[P0722R3]]）；`constexpr` 中可以使用 `new`/`delete`；隐式创建的对象归入动态存储期。
    - C++26：随契约加入，注 2 增加了 `std::contracts::contract_violation`。

## 常见误解

!!! pitfall "分配和释放可以混用"
    `new` 配 `delete`，`new[]` 配 `delete[]`，`malloc` 配 `free`。混用不在上述约定之内，[[expr.delete]] 规定它是 UB。

!!! pitfall "替换的 `operator new` 可以返回空指针"
    非 `noexcept` 的分配函数返回空指针违反 ¶4，按 ¶3 是 UB。编译器假设 `new` 的结果非空，可能把你随后写的 `if (!p)` 检查删掉。

!!! pitfall "局部 `static` 变量的存储在首次调用时才分配"
    存储期覆盖整个程序运行期间。首次经过声明时发生的只是初始化，存储在程序加载时就已存在。

## 思考题

!!! question "思考题 1"
    下面的分配函数声明哪些合法？

    ```cpp
    void* operator new(std::size_t, std::size_t);            // (a)
    template<class T> void* operator new(std::size_t, T);    // (b)
    void* operator new(std::size_t, int = 0);                // (c)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 声明本身合法，但不能当 placement 分配函数用。`new (n) T` 的构造函数抛出异常时，要找签名匹配的释放函数，会找到全局的尺寸释放函数 `operator delete(void*, std::size_t)`；它是常规释放函数，[[expr.new]] 规定这种情况下程序非良构（脚注 19）。

(b) 合法：模板有两个参数，返回类型和第一个参数都不依赖模板参数。

(c) 合法：只有第一个参数不能有默认实参。
</details>

!!! question "思考题 2"
    函数参数的存储在什么时候结束？为什么标准不直接说在函数返回时结束？

<details markdown="1">
<summary>答案</summary>

按 [basic.stc.auto] ¶1，参数的存储在参数销毁之后立即结束。参数何时销毁由 [[expr.call]] 规定，在函数返回时还是在包含调用的完整表达式结束时，由实现定义。这与调用约定有关：有的 ABI 由被调用者析构参数，有的由调用者析构。如果写成函数返回时结束，在由调用者析构参数的 ABI 上，析构时存储已经不存在了。所以存储的结束点跟着销毁走。
</details>

## 小结

| 存储期 | 来源 | 结束 | 未初始化时的初值 |
|---|---|---|---|
| 静态 | 命名空间变量、`static`/`extern` 变量、静态数据成员 | 程序结束 | 先零初始化 |
| 线程 | `thread_local` | 线程结束 | 先零初始化 |
| 自动 | 块变量、参数、多数临时对象 | 块退出；参数在销毁之后 | 错误值（[[basic.indet]]） |
| 动态 | *new-expression*、隐式创建 | 被释放 | 不确定值 |

| 分配函数的约定 | 释放函数的约定 |
|---|---|
| 全局作用域，非内部链接 | 全局作用域，非内部链接 |
| 返回 `void*`，第一个参数 `std::size_t` 且无默认实参 | 返回 `void`，不得抛出 |
| 成功：非空、唯一、对齐 | 空指针实参：库版本没有效果 |
| 失败：抛 `bad_alloc`，`noexcept` 版本返回空 | 非空实参：结束存储期 |
| 0 字节请求合法，但不能通过结果访问 | 常规释放函数：`[destroying_delete_t] [size_t] [align_val_t]` |
