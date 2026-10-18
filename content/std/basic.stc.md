---
title: 存储期
summary: 四种存储期（静态、线程、自动、动态）由创建对象的构造决定；动态存储由全局分配/释放函数管理，本节规定这些函数的签名与语义约束
status: done
covers: *
papers: N3778, P0035R4, P0722R3, N3664
related: basic.life, intro.object, expr.new, expr.delete, new.delete, basic.start.static, basic.start.term, stmt.dcl
tags: 存储期, operator new, operator delete, 动态内存
updated: 2026-10-17
---

**存储期**（storage duration）是对象的一个属性，规定了**包含该对象的存储至少能存在多久**。注意措辞："存储"的"最短潜在生命期"（minimum potential lifetime of the storage）。它描述的是**存储**，不是对象：对象的生命周期（[[basic.life]]）总是落在其存储期之内，但可以短得多（例如 placement new 到一块静态存储里的对象，可以在程序中途就结束生命周期）。

本节分为五部分：总则（[[basic.stc.general]]）、静态（[[basic.stc.static]]）、线程（[[basic.stc.thread]]）、自动（[[basic.stc.auto]]）、动态（[[basic.stc.dynamic]]，含分配函数 [[basic.stc.dynamic.allocation]] 与释放函数 [[basic.stc.dynamic.deallocation]]）。前四部分很短，第五部分是重头戏：它定义了 `operator new`/`operator delete` 必须遵守的契约，是自定义内存分配的法律基础。

## 总则 [basic.stc.general]

### 四种存储期（¶1–¶2）

| 存储期 | 由什么构造产生 | 存储持续到 |
|---|---|---|
| **静态**（static） | 命名空间作用域变量；首次用 `static`/`extern` 声明的变量；静态数据成员 | 程序结束 |
| **线程**（thread） | `thread_local` 变量 | 线程结束 |
| **自动**（automatic） | 块作用域变量（未声明 `static`/`thread_local`/`extern`）；函数参数 | 所在块退出（参数：其销毁之后） |
| **动态**（dynamic） | *new-expression*；隐式创建的对象（[[intro.object#13]]） | 被释放为止 |

¶2：静态、线程、自动存储期与**声明引入的对象**（[[basic.def]]）和**临时对象**（[[class.temporary]]）相关联；动态存储期与 *new-expression* 创建的对象，以及**隐式创建的对象**相关联。

!!! note "隐式创建的对象一律是“动态”存储期？"
    ¶2 说动态存储期与"隐式创建的对象"相关联。但隐式创建可以发生在一个自动存储期的 `unsigned char` 数组里（[[intro.object#16]]）——那里的对象是什么存储期？按 ¶2 的字面表述是动态；而按 ¶4"子对象的存储期是其完整对象的存储期"无法推出，因为被提供存储的对象不是子对象。这是条文中一个不太清晰的角落；实践上它没有可观察的后果（存储期主要决定存储何时结束，而被嵌套对象的存储随外层数组结束）。

注 1：一段存储的存储期结束后，指向它的指针变成**无效指针值**，使用受限（[[basic.compound]]）：解引用是 UB；拷贝、比较等是实现定义的。

### 引用与子对象（¶3–¶4）

- ¶3：存储期的分类同样适用于**引用**——`static const int& r = 42;` 中的 `r` 具有静态存储期（它可能需要存储来保存地址）。
- ¶4：**子对象和引用成员的存储期是其完整对象的存储期**。`new S` 的成员也是动态存储期；局部 `S s;` 的成员是自动存储期。

## 静态存储期 [basic.stc.static]

¶1：所有满足以下条件的变量具有**静态存储期**：

- ¶1.1 没有线程存储期，并且
- ¶1.2 属于命名空间作用域（[[basic.scope.namespace]]），或者首次声明时带 `static` 或 `extern` 关键字（[[dcl.stc]]）。

其存储持续整个程序运行期间（初始化见 [[basic.start.static]]，销毁见 [[basic.start.term]]）。

```cpp run title="static-sd.cpp" ok
int a;                    // 命名空间作用域：静态存储期
static int b;             // 静态存储期（内部链接）

struct S { static int m; };
int S::m = 0;             // 静态数据成员：静态存储期

int f() {
    static int calls = 0; // 块作用域 static：静态存储期，首次经过声明时初始化（[stmt.dcl]）
    extern int a;         // 块作用域 extern：指向命名空间的 a，静态存储期
    return ++calls + a + b + S::m;
}

int main() { f(); return f() == 2 ? 0 : 1; }
```

¶2：如果静态存储期变量的**初始化或析构有副作用**，即使看起来没被使用也**不得被消除**，唯一例外是 [[class.copy.elision]] 允许的复制消除。这保证了"注册器"惯用法有效：

```cpp run title="registrar.cpp" ok
#include <cstdio>

struct Registrar {
    Registrar() { std::puts("registered"); }   // 有副作用的初始化
};

static Registrar reg;     // 从未被使用，但不得被消除：程序启动时一定打印 "registered"

int main() {}
```

!!! warning "链接器不受此约束"
    ¶2 约束的是"实现"对**已经成为程序一部分**的变量的处理。如果 `reg` 位于静态库（`.a`）中一个没有被任何符号引用的目标文件里，链接器根本不会把这个目标文件拉进程序——这不违反 ¶2，因为那个变量从未成为程序的一部分。这是插件注册模式在静态库中"失灵"的常见原因。

¶3 是注：块作用域的 `static` 变量见 [[stmt.dcl]]；类中的 `static` 数据成员见 [[class.static.data]]。

## 线程存储期 [basic.stc.thread]

¶1：所有用 `thread_local` 声明的变量具有**线程存储期**。存储持续到创建它的线程结束。**每个线程有一个独立的对象或引用**，使用声明的名字指向与**当前线程**关联的那一个。

¶2 是注：初始化见 [[basic.start.static]]、[[basic.start.dynamic]]、[[stmt.dcl]]；若被构造了，则在线程退出时销毁（[[basic.start.term]]）。

```cpp run title="thread-local.cpp" ok
#include <thread>
#include <cassert>

thread_local int counter = 0;   // 每个线程一份

void work() {
    for (int i = 0; i < 1000; ++i) ++counter;   // 无数据竞争：各自的对象
    assert(counter == 1000);
}

int main() {
    std::thread t1(work), t2(work);
    t1.join(); t2.join();
    return counter;            // 主线程自己的 counter：0
}
```

!!! note "thread_local 隐含 static"
    块作用域中 `thread_local int x;` 隐含 `static`（[[dcl.stc]]）——它不会每次进入块时重新创建，而是每个线程一个、首次经过时初始化。

## 自动存储期 [basic.stc.auto]

¶1：属于**块作用域**且没有显式声明为 `static`、`thread_local` 或 `extern` 的变量具有**自动存储期**，存储持续到创建它们的块退出为止。属于**参数作用域**的变量（函数参数）也具有自动存储期，其存储持续到**其销毁之后立即结束**（[[expr.call]]）。

参数那句话很精细：参数的销毁时机是实现定义的——在函数返回时，还是在包含调用的完整表达式结束时（[[expr.call]]）。存储跟随销毁结束，而不是跟随函数返回。

¶2：如果自动存储期变量的初始化或析构有副作用，实现不得在块结束前销毁它，也不得作为优化消除它，即使看起来未被使用（复制消除除外）。这保证了 RAII 守卫有效：

```cpp run title="raii-guard.cpp" ok
#include <mutex>

std::mutex m;
int shared = 0;

void f() {
    std::lock_guard<std::mutex> g(m);   // g 从未被"使用"，但不得被提前销毁或消除
    ++shared;
}   // 锁在这里释放，而不是在上一行之后

int main() { f(); return shared == 1 ? 0 : 1; }
```

!!! pitfall "临时对象不是变量"
    `std::lock_guard<std::mutex>{m};`（没有名字）创建的是一个**临时对象**，在该完整表达式结束时就被销毁（[[class.temporary]]），根本保护不了下一行。¶2 只保护**变量**。

## 动态存储期 [basic.stc.dynamic]

### 总则 [basic.stc.dynamic.general]

¶1：对象可以在运行时由 *new-expression*（[[expr.new]]）动态创建，由 *delete-expression*（[[expr.delete]]）销毁。实现通过**全局分配函数** `operator new`、`operator new[]` 和**全局释放函数** `operator delete`、`operator delete[]` 提供对动态存储的访问与管理。注 1：[[new.delete.placement]] 中的非分配形式（`operator new(size_t, void*)` 等）不分配也不释放。

¶2：库为全局分配/释放函数提供默认定义，其中一些是**可替换的**（replaceable，[[dcl.fct.def.replace]]）。以下函数在**每个翻译单元的全局作用域中隐式声明**：

```cpp
void* operator new(std::size_t);
void* operator new(std::size_t, std::align_val_t);
void  operator delete(void*) noexcept;
void  operator delete(void*, std::size_t) noexcept;
void  operator delete(void*, std::align_val_t) noexcept;
void  operator delete(void*, std::size_t, std::align_val_t) noexcept;
// 以及对应的 operator new[] / operator delete[] 共 6 个
```

隐式声明只引入函数名，不引入 `std`、`std::size_t`、`std::align_val_t` 等名字（注 2）。所以：

```cpp run title="no-include-new.cpp" ok
int main() {
    int* p = new int(1);          // OK: 不需要 #include <new>
    void* q = operator new(16);   // OK: 直接调用分配函数也行
    operator delete(q);
    delete p;
    // std::size_t n = 0;         // error: 没有包含声明 std::size_t 的头文件
}
```

`nothrow` 版本（`operator new(std::size_t, const std::nothrow_t&)`）和 placement 版本**不是**隐式声明的，需要 `<new>`。

类也可以声明自己的分配/释放函数（[[class.free]]），*new-expression* 会先在类作用域中查找。

¶3：如果分配或释放函数的行为不满足下面两小节规定的语义约束，行为未定义。这是对**用户替换版本**的约束：你替换了全局 `operator new`，就必须遵守契约。

### 分配函数 [basic.stc.dynamic.allocation]

#### 签名要求（¶1）

- 非类成员的分配函数必须属于**全局作用域**，且不能具有内部链接（不能是 `static` 函数，不能在命名空间里）。
- 返回类型必须是 `void*`。
- 第一个参数类型必须是 `std::size_t`，且**不能有默认实参**。它被解释为请求的字节数。
- 可以是函数模板，但返回类型和第一个参数不能依赖模板参数，且模板必须有**至少两个参数**（防止模板版本劫持普通的 `new T`）。

```cpp run title="alloc-sig.cpp" error
#include <cstddef>

namespace N { void* operator new(std::size_t); }        // error: 不在全局作用域
static void* operator new(std::size_t, int);            // error: 内部链接
void* operator new(std::size_t = 0, double);            // error: 第一个参数有默认实参（且默认实参后跟无默认实参的参数）
template<class T> void* operator new(T);                // error: 第一个参数依赖模板参数 / 只有一个参数
```

#### 语义（¶2）

- 成功时返回一块**至少**请求大小的存储的起始地址。连续多次分配之间的次序、连续性、初始值都是**未指定**的。
- 即使请求 0 字节也可能失败。
- **可替换分配函数**成功时返回**非空**指针 `p0`，且与之前返回的任何值 `p1` 都不同——除非 `p1` 之后被传给了可替换的释放函数。也就是说 `new char[0]` 两次得到不同的非空指针（脚注 18：这与 C 的 `malloc(0)` 可返回空指针不同）。
- 对库提供的 [[new.delete.single]]、[[new.delete.array]] 中的版本，返回的存储与调用者可访问的其他任何对象的存储不相交。
- **通过零字节请求返回的指针间接访问，行为未定义。**

```cpp run title="zero-size.cpp" ok
int main() {
    char* a = new char[0];   // 合法：返回非空、唯一的指针
    char* b = new char[0];
    bool distinct = a != b;  // 必为 true
    // *a = 'x';             // UB: 通过零大小分配返回的指针间接访问
    delete[] a;
    delete[] b;
    return distinct ? 0 : 1;
}
```

#### 对齐（¶3）

除保留的 placement 分配函数外，成功返回的存储必须如下对齐：

- ¶3.1 若分配函数有 `std::align_val_t` 参数：按该参数指定的对齐；
- ¶3.2 否则若是 `operator new[]`：对任何**不具有 new-extended 对齐**（[[basic.align#3]]）且**不大于请求大小**的对象类型都对齐；
- ¶3.3 否则：对任何不具有 new-extended 对齐、且大小**等于**请求大小的对象类型都对齐。

¶3.2/¶3.3 的区别在于数组版本可能被用来放置多个较小的对象（例如 `new char[64]` 用作缓冲区），所以要对"所有不大于请求大小"的类型都对齐；单对象版本只需对"恰好该大小"的类型对齐——请求 2 字节时，实现可以只给 2 字节对齐，不必给 16 字节对齐（但主流实现都直接给 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`）。

#### 失败（¶4）

- 分配失败时**可以**调用当前安装的 new-handler（[[new.handler]]），程序提供的分配函数可用 `std::get_new_handler` 获取它。
- 具有**不抛出**异常规格（`noexcept`）的分配函数通过**返回空指针**表示失败。
- 其他分配函数**永不返回空指针**，只能通过抛出能被 `std::bad_alloc` 处理器匹配的异常表示失败。

这条规则让编译器可以省略 `new T` 之后的空指针检查——这在 [[expr.new]] 中有体现：只有当分配函数是不抛出的，*new-expression* 才需要检查返回值是否为空再决定是否初始化。

#### 何时调用全局分配函数（¶5）

全局分配函数**只**在以下情况被调用：作为 *new-expression* 的结果；以函数调用语法直接调用；为**协程状态**分配存储（[[dcl.fct.def.coroutine]]）；通过标准库函数间接调用。

注 2 列举了**不**用全局分配函数的情形：静态存储期对象、线程存储期对象或引用、`std::type_info` 对象、契约违反时的 `std::contracts::contract_violation` 对象 {{c++26}}、**异常对象**（[[except.throw]]，实现另有专门的分配机制，如 Itanium ABI 的 `__cxa_allocate_exception`）。

!!! note "分配消除（[expr.new]/14）"
    [[expr.new#14]] 允许实现**省略**对可替换全局分配函数的调用，改由实现自己提供存储（例如放在栈上），或者合并多个 *new-expression* 的分配。所以即使你替换了全局 `operator new` 来计数，计数结果也不一定等于源码中 `new` 的次数：

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
        std::printf("v=%d count=%d\n", v, count);   // 本机 Clang 23：-O0 输出 count=1，-O2 输出 count=0
    }
    ```

    这条许可自 C++14 起存在（[[N3664]]）。注意它只针对 *new-expression* 引起的调用；直接写 `::operator new(n)` 的函数调用不在许可之内（Clang 提供 `__builtin_operator_new` 内建，让 `std::allocator` 等库代码也能享受这一优化，但那是实现扩展）。常量求值中，对可替换分配函数的调用**总是**被省略（[[expr.new#15]]），这是 `constexpr` 动态分配能工作的基础。

### 释放函数 [basic.stc.dynamic.deallocation]

#### 签名（¶1–¶3）

- ¶1：非类成员的释放函数必须属于全局作用域，不能具有内部链接。
- ¶2：**销毁型 operator delete**（destroying operator delete）{{c++20}}：至少两个参数且第二个参数类型为 `std::destroying_delete_t` 的释放函数。它必须是名为 `operator delete` 的**类成员函数**。注 1：数组删除不能使用销毁型 delete。
- ¶3：
    - 返回类型必须是 `void`；不得有潜在抛出的异常规格（隐式就是 `noexcept`）；
    - 销毁型 delete 的第一个参数类型是"指向 `C` 的指针"（`C` 是声明它的类），其他释放函数的第一个参数是 `void*`；
    - **常规释放函数**（usual deallocation function）：第一个参数之后的参数依次是——可选的 `std::destroying_delete_t`，然后可选的 `std::size_t`，然后可选的 `std::align_val_t`。销毁型 delete 必须是常规释放函数。
    - 可以是函数模板（第一个参数和返回类型不得依赖模板参数，至少两个参数），但模板实例**永远不是**常规释放函数。

"常规"的意义在于 *delete-expression* 只会调用常规释放函数（[[expr.delete]]）；非常规的（placement 形式的）`operator delete` 只在 placement new 的构造函数抛异常时被匹配调用。

##### 销毁型 delete

普通的 `delete p` 先调用析构函数，再调用 `operator delete` 释放存储。销毁型 delete 把**这两步都交给你**：编译器**不**调用析构函数，直接把（具有静态类型 `C*` 的）指针交给你的 `operator delete`，由你自己决定如何析构和释放。

```cpp run title="destroying-delete.cpp" ok
#include <new>
#include <cstdio>

struct Shape {
    enum Kind { Circle, Square } kind;
    void operator delete(Shape* p, std::destroying_delete_t);   // 销毁型 delete
};
struct Circle : Shape { double r; };
struct Square : Shape { double side; };

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
    // 根据 kind 手动分派正确的析构与释放——无需虚析构函数和 vptr
    if (p->kind == Circle) { auto* c = static_cast<struct Circle*>(p); c->~Circle(); ::operator delete(c, sizeof(struct Circle)); }
    else                   { auto* s = static_cast<struct Square*>(p); s->~Square(); ::operator delete(s, sizeof(struct Square)); }
    std::puts("destroyed");
}

int main() {
    Shape* s = new Circle{{Shape::Circle}, 1.0};
    delete s;    // 不调用 ~Shape()，直接调用 Shape::operator delete(s, destroying_delete)
}
```

典型用途：不使用虚析构函数的"手工多态"（如 LLVM 的 `User`/`Value` 层次）、对象与其他数据一起分配的变长对象（析构时需要知道真实大小）。由 [[P0722R3]] 引入。

##### 尺寸释放与对齐释放

- **尺寸释放**（sized deallocation）{{c++14}}：`operator delete(void*, std::size_t)`。*delete-expression* 在知道对象大小时把大小传过去，分配器就不用自己记录或查找块大小（[[N3778]]）。脚注 19：全局 `operator delete(void*, std::size_t)` 的存在使得 `void* operator new(std::size_t, std::size_t)` 不能再被当作 placement 分配函数使用——它对应的"placement delete"会与尺寸释放函数撞签名。这是 C++14 的一个不兼容变更（[[diff.cpp11.basic]]）。
- **对齐释放** {{c++17}}：带 `std::align_val_t` 的版本，与 over-aligned 分配配对（[[P0035R4]]）。

#### 语义（¶4–¶5）

- ¶4：传给释放函数的第一个实参可以是空指针；对标准库提供的释放函数，这时调用无效果（所以 `delete nullptr` 安全）。
- ¶5：对标准库的释放函数，若实参不是空指针，则释放该指针所指的存储，**结束该存储区域的存储期**。之后所有指向它的指针都变成无效指针值（[[basic.compound]]）。

## 替换全局分配函数

[[dcl.fct.def.replace]] 和 [[new.delete]] 规定：程序可以在**某个**翻译单元中定义可替换的全局分配/释放函数，以取代库版本。替换版本不得声明为 `inline`，且必须遵守本节的契约（¶3 的 UB 条款）：

```cpp run title="replace-new.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

static std::size_t live = 0;

void* operator new(std::size_t n) {
    if (n == 0) n = 1;                       // 零大小也必须返回唯一的非空指针
    for (;;) {
        if (void* p = std::malloc(n)) { ++live; return p; }
        std::new_handler h = std::get_new_handler();
        if (!h) throw std::bad_alloc();      // 失败只能抛 bad_alloc，不能返回空
        h();                                 // 让 new-handler 尝试腾出内存
    }
}
void operator delete(void* p) noexcept {
    if (p) { --live; std::free(p); }
}
void operator delete(void* p, std::size_t) noexcept { operator delete(p); }

int main() {
    auto* v = new int[4];   // operator new[] 的默认实现调用 operator new
    delete[] v;
    std::printf("live=%zu\n", live);
}
```

!!! tip "只替换 `operator new(size_t)` 通常就够了"
    库的默认 `operator new[]`、`nothrow` 版本都被规定为（直接或间接）调用 `operator new(std::size_t)`；默认的 `operator delete[]`、尺寸版本 `operator delete` 也调用 `operator delete(void*)`。所以替换这两个基本函数通常就能截获所有非对齐的全局分配。对齐版本是独立的一组，需要单独替换。

## 实现视角

!!! impl "实现视角"
    - **libstdc++/libc++** 的默认 `operator new` 就是 "`malloc` + 循环调用 new-handler + 抛 `bad_alloc`"，与脚注 18 的意图一致；对齐版本调用 `aligned_alloc`/`posix_memalign`（Windows 上 `_aligned_malloc`）。
    - **尺寸释放**：GCC 在 C++14 起默认开启；Clang 在较长时间内需要 `-fsized-deallocation` 才开启（因为依赖运行时库提供对应符号），后来才改为默认开启。尺寸信息对 tcmalloc/jemalloc 这类分配器有明显的性能收益。
    - **分配消除**：Clang 很积极地消除 `new`/`delete` 配对（本机 `-O2` 下上面的计数例子输出 0）；GCC 在较新版本中也会做类似优化。
    - **线程存储期**：ELF 平台通过 TLS 段（`.tdata`/`.tbss`）和 `__tls_get_addr` 实现；有非平凡构造/析构的 `thread_local` 需要"首次使用时初始化"的包装函数（Itanium ABI 中的 TLS wrapper）与线程退出时的析构注册（`__cxa_thread_atexit`）。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：静态、自动、动态三种存储期；全局 `operator new/delete` 及其数组、nothrow、placement 形式。
    - **C++11**：新增**线程存储期**和 `thread_local`。
    - **C++14**：尺寸释放（[[N3778]]）；允许省略/合并分配（[[N3664]]）。
    - **C++17**：对齐分配/释放、`std::align_val_t`、`__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[P0035R4]]）。
    - **C++20**：销毁型 `operator delete`（[[P0722R3]]）；`constexpr` 中可以使用 `new`/`delete`（依赖于常量求值中省略分配函数调用）；隐式创建的对象纳入动态存储期。
    - **C++26**：随契约（contracts）加入，注 2 中增加契约违反对象 `std::contracts::contract_violation`。

## 陷阱

!!! pitfall "混用分配与释放"
    `new` 配 `delete`、`new[]` 配 `delete[]`、`malloc` 配 `free`。混用不在本节的契约之内——[[expr.delete]] 规定为 UB。

!!! pitfall "替换的 operator new 返回空指针"
    非 `noexcept` 的分配函数返回空指针违反 ¶4，属于 ¶3 的 UB。编译器会假设 `new` 的结果非空并据此优化（例如删除你后面写的 `if (!p)` 检查）。

!!! pitfall "以为 `static` 局部变量的存储在首次调用时才分配"
    存储期是**整个程序**；"首次经过声明时"发生的只是**初始化**。存储本身通常在 `.bss`/`.data` 段里，程序加载时就存在。

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

(a) 作为声明合法，但脚注 19 指出：由于全局 `operator delete(void*, std::size_t)` 是常规（尺寸）释放函数，`new (n) T` 这种 placement 形式在构造函数抛异常时会去匹配同签名的释放函数，从而选中尺寸释放函数——[[expr.new]] 规定这种情况下程序非良构。所以它实际上不能用作 placement 分配函数。

(b) 合法：模板有两个参数，返回类型和第一个参数都不依赖模板参数。

(c) 合法：只有**第一个**参数不能有默认实参，后面的参数可以。
</details>

!!! question "思考题 2"
    函数参数是自动存储期，它的存储什么时候结束？为什么不简单地说"函数返回时"？

<details markdown="1">
<summary>答案</summary>

¶1 说参数的存储持续到"其销毁之后立即结束"。参数何时销毁由 [[expr.call]] 规定：是在函数返回时，还是在包含调用的完整表达式结束时，由实现定义（这与调用约定有关：有的 ABI 由被调用者析构参数，有的由调用者析构）。如果写成"函数返回时"，那么在调用者负责析构的 ABI 上，析构时参数的存储已经不存在了，自相矛盾。所以存储的结束点跟着销毁走。
</details>

## 小结

| 存储期 | 来源 | 结束 | 初值 |
|---|---|---|---|
| 静态 | 命名空间变量、`static`/`extern` 变量、静态成员 | 程序结束 | 先零初始化 |
| 线程 | `thread_local` | 线程结束 | 先零初始化 |
| 自动 | 块变量、参数、（多数）临时对象 | 块退出 / 参数销毁后 | 错误值（[[basic.indet]]） |
| 动态 | *new-expression*、隐式创建 | 释放 | 不确定值 |

| 分配函数契约 | 释放函数契约 |
|---|---|
| 全局作用域、非内部链接 | 全局作用域、非内部链接 |
| 返回 `void*`，首参 `std::size_t` 无默认实参 | 返回 `void`，不得抛出 |
| 成功：非空、唯一、对齐 | 空指针实参：库版本无效果 |
| 失败：抛 `bad_alloc`（或 `noexcept` 版本返回空） | 非空：结束存储期 |
| 零大小请求合法，但不能解引用结果 | 常规释放函数：`[destroying_delete_t] [size_t] [align_val_t]` |
