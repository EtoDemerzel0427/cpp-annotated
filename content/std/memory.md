---
title: 内存（<memory> 总览）
summary: <memory> 概要中值得注意的部分（freestanding 的划分、POINTER_OF）、特化内存算法与 placement new 的关系、addressof 为什么存在，以及 C 的 malloc 族在 C++ 对象模型中的规则：隐式创建对象，realloc(p, 0) 是错误行为。
status: done
covers: memory.general, memory.syn, specialized.addressof, c.malloc
related: mem, intro.object, basic.life, expr.new, specialized.algorithms, pointer.traits, allocator.traits, support.types
tags: 标准库, memory, addressof, malloc, freestanding
papers: P0593R6
updated: 2026-10-19
---

!!! tldr
    - `construct_at` 就是一次 placement new，`destroy_at` 就是一次析构函数调用；它们可以在常量求值中使用。
    - `std::addressof` 返回对象的真实地址，不受重载的一元 `operator&` 影响，泛型代码取地址应当用它。
    - `malloc`、`calloc`、`realloc` 不调用 `operator new`，但会在返回的存储里隐式创建对象，所以 `malloc` 一块内存后直接当 `int` 数组用是良定义的。
    - `realloc(p, 0)` 在 C++ 中是错误行为，效果由实现定义；C23 则把它定为未定义行为。
    - `unique_ptr`、`allocator_traits`、`addressof` 是 freestanding 的，`std::allocator`、`shared_ptr` 不是。

[memory] 是第 20 章的第一个子条款。¶1（[memory.general]）说它描述 `<memory>` 的内容和 `<cstdlib>` 的一部分内容，后者就是本页最后一节的 `malloc` 族。

它下面的小节本站按主题分页：

| 子条款 | 本站笔记 |
|---|---|
| [pointer.traits]、[pointer.conversion] | [[pointer.traits]]：`pointer_traits`、`to_address` |
| [ptr.align] | [[ptr.align]]：`align`、`assume_aligned`、`is_sufficiently_aligned` |
| [obj.lifetime] | [[obj.lifetime]]：`start_lifetime_as` 等 |
| [allocator.tag]、[allocator.uses] | [[allocator.uses]]：`allocator_arg`、`uses_allocator`、uses-allocator 构造 |
| [allocator.traits] | [[allocator.traits]] |
| [default.allocator] | [[default.allocator]]：`std::allocator` |
| [specialized.addressof]、[c.malloc] | 本页 |

## 特化内存算法：库版的 placement new

```cpp run title="construct-at.cpp" ok
#include <memory>
#include <new>

struct S { int v; };

constexpr int f() {
    std::allocator<S> a;
    S* p = a.allocate(2);                       // 只有数组对象的生命周期开始，元素没有
    std::construct_at(p, 1);                    // C++20 起可在常量求值中使用
    ::new (static_cast<void*>(p + 1)) S{2};     // C++26 起 placement new 也可以
    int r = p[0].v + p[1].v;
    std::destroy(p, p + 2);
    a.deallocate(p, 2);
    return r;
}
static_assert(f() == 3);

int main() {}
```

`uninitialized_copy`、`uninitialized_fill`、`construct_at`、`destroy_at`、`destroy` 等声明在 `<memory>`，规范在 [[specialized.algorithms]]。

`construct_at(p, args...)` 的效果是 `::new (voidify(*p)) T(std::forward<Args>(args)...)`（[[specialized.construct]]），`voidify(obj)` 就是把 `addressof(obj)` 转成 `void*`。所以它就是一次 placement new（[[expr.new]]），只是有三点不同：

- 用 `::new`，跳过类自己的 `operator new` 重载；
- 用 `addressof` 而不是 `&`，不受重载的 `operator&` 干扰；
- 它是 `constexpr` 的。C++26 之前常量求值里不能直接写 placement new，`construct_at` 是唯一的办法。本机 Clang 23 在 `-std=c++23` 下拒绝上例的 placement new 那一行，在 `-std=c++2c` 下通过。

`destroy_at(p)` 对非数组类型就是 `p->~T()`，对数组则逐个销毁元素。

这些算法在存储上创建新对象时，原来占用这块存储的对象生命周期结束，这条规则来自 [[basic.life]]。如果构造中途抛出异常，已经构造好的对象以未指定的顺序销毁，然后异常继续传播（[[specialized.algorithms.general]]）。

## `addressof` [specialized.addressof]

一元 `&` 作用于类类型的操作数时会参与重载决议（[[over.match.oper]]），类可以让 `&x` 返回任何东西，甚至把它定义为弃置的：

```cpp run title="addressof.cpp" ok
#include <memory>

struct Evil {
    int x;
    void operator&() const = delete;   // 禁止取地址
};

constexpr int g() {
    Evil e{5};
    // &e;                               // error: 调用弃置的 operator&
    return std::addressof(e)->x;         // OK：真实地址，也能用在常量求值中
}
static_assert(g() == 5);

int main() {}
```

¶1 `addressof(r)` 返回 `r` 所引用的对象或函数的真实地址，即使存在重载的 `operator&`。¶2 如果 `E` 是左值常量子表达式，`addressof(E)` 也是常量子表达式。

容器、`optional`、`construct_at` 这些泛型代码必须拿到真实地址，所以标准库内部一律用 `addressof`。

概要里还有一个弃置的重载 `const T* addressof(const T&&) = delete;`，拒绝右值实参：`std::addressof(Evil{})` 是 {{ill-formed}}，因为临时对象的地址几乎必然会悬空。

!!! impl "实现"
    纯 C++ 写不出能用于常量求值的 `addressof`，因为 `reinterpret_cast` 不能出现在常量表达式里。libc++、libstdc++、MSVC STL 都用编译器内建函数 `__builtin_addressof` 实现它。

## C 库内存分配 [c.malloc]

这些函数声明在 `<cstdlib>`（¶1 的注）。¶2 和 ¶8 规定它们的语义照搬 C 标准（当前引用 C23，ISO/IEC 9899:2024 的 7.24.4），此外 C++ 补充了三条规则。

### 隐式创建对象（¶4、¶7）

```cpp run title="malloc-objects.cpp" ok
#include <cstdio>
#include <cstdlib>

struct Point { int x, y; };

int main() {
    int* p = static_cast<int*>(std::calloc(4, sizeof(int)));
    auto* q = static_cast<Point*>(std::malloc(sizeof(Point)));
    q->x = 1; q->y = 2;                      // 不需要 placement new
    std::printf("%d %d\n", p[3], q->x + q->y);   // 0 3
    std::free(q);
    std::free(p);
}
```

!!! std
    These functions implicitly create objects ([intro.object]) in the returned region of storage and return a pointer to a suitable created object.

¶4 这些函数在返回的存储中**隐式创建对象**，并返回指向一个合适的已创建对象的指针。上例因此是良定义的：`Point` 是隐式生存期类型（例如聚合体或标量类型），`malloc` 返回的存储里已经有一个 `Point` 对象，可以直接给成员赋值。机制见 [[intro.object]] 中隐式创建对象的部分，这条规则由 C++20 的 [[P0593R6]] 加入。

¶4、¶7 还规定了两个顺序：

- `calloc` 先创建对象，再把存储清零。所以清零后的字节就是这些对象的值，上例的 `p[3]` 读到 0。
- `realloc` 返回非空指针时，先创建对象，再拷贝旧内容。旧内容被拷贝进已经存在的新对象，`realloc` 一个 `int` 数组之后读元素是良定义的。

### 不经过 `operator new`（¶3、¶7、¶9）

`malloc`、`calloc`、`aligned_alloc`、`realloc` 不调用 `::operator new()`，`free` 也不调用 `::operator delete()`。所以替换全局 `operator new`（[[new.delete]]）不影响 `malloc`；用 `free` 释放 `new` 得到的内存，或者用 `delete` 释放 `malloc` 得到的内存，都是 {{ub}}（[[basic.stc.dynamic.deallocation]]）。

### `realloc(p, 0)` 是错误行为（¶5–¶6）

¶5 的前置条件是 `free(ptr)` 有良定义的行为，即 `ptr` 为空，或者来自 `malloc` 族且尚未释放。

!!! std
    If ptr is not null and size is zero, the behavior is erroneous and the effects are implementation-defined.

¶6 `ptr` 非空而 `size` 为零时，行为是错误行为（erroneous behavior，[[g:erroneous-behavior]]），效果由实现定义。

C 实现对 `realloc(p, 0)` 的处理长期不一致：有的释放 `p` 并返回空指针，有的返回一个最小的块。C23 把它改成了未定义行为。C++ 没有跟随，而是归为 {{erroneous}}：实现必须给出确定的效果，同时这种写法被认定为错误，实现可以诊断或终止程序。可移植的代码应当单独处理 `size == 0`。

!!! pitfall "malloc 只保证基本对齐"
    `malloc` 只保证适合基本对齐（[[g:fundamental-alignment]]，即 `alignof(max_align_t)`）。类型有扩展对齐（如 `alignas(64)`）时，要用 `aligned_alloc`，并且按 C 标准，`size` 应当是 `alignment` 的整数倍；或者直接用 `new`，C++17 起 `new` 会为过对齐类型调用带 `align_val_t` 的分配函数。

## 概要里值得注意的部分 [memory.syn]

¶1 列出 `<memory>` 的几类内容：描述指针和类指针类型性质的工具、为容器管理内存、销毁对象、在未初始化的内存中构造对象；`pointer_tag_pair`（[[ptrtag]]），它选用指针的哪些位由实现定义，包装后的大小与原指针相同；以及智能指针和 `out_ptr_t` / `inout_ptr_t`（[[smartptr]]）。概要本身有八百多行，绝大部分是声明，值得注意的有下面几处。

### freestanding 标注

概要里大多数声明都带有 `// freestanding` 注释，表示独立实现（[[g:freestanding-implementation]]）也必须提供它。划分的依据是是否需要堆：

- `pointer_traits`、`allocator_traits`、`uses_allocator`、`addressof`、`construct_at`、`unique_ptr`、`default_delete`、`out_ptr`、`pointer_tag_pair` 是 freestanding 的。`unique_ptr` 配一个自定义删除器，在内核里也能用。
- `std::allocator`、`make_unique`、`shared_ptr`、`weak_ptr`、`indirect`、`polymorphic` 不是。它们要么直接调用 `::operator new`，要么像 `shared_ptr` 那样需要分配控制块。
- 带执行策略的并行算法重载标为 `// freestanding-deleted`：独立实现里这些重载存在，但定义为弃置的（[[freestanding.item]]）。

### `POINTER_OF`（¶2–¶3）

¶2 定义了说明专用的类型函数 *POINTER_OF*(T)：如果 `T::pointer` 是有效的类型，就是它（¶2.1）；否则如果 `T::element_type` 有效，就是 `T::element_type*`（¶2.2）；否则是 `pointer_traits<T>::element_type*`（¶2.3）。

¶3 的 *POINTER_OF_OR*(T, U) 在 *POINTER_OF*(T) 有效时就是它，否则是 `U`。[[smartptr.adapt]] 的 `out_ptr` / `inout_ptr` 用它们从任意智能指针类推出对应的裸指针类型。

概要末尾还在 `std::pmr` 里声明了 `pmr::indirect<T>` 与 `pmr::polymorphic<T>`，即使用 `polymorphic_allocator<T>` 的版本（[[indirect]]、[[polymorphic]]）。

## 思考题

!!! question "思考题 1"
    `std::addressof(f)` 中 `f` 是一个函数，结果是什么？`addressof` 能用于位域吗？

<details markdown="1">
<summary>答案</summary>

¶1 说 `addressof` 返回对象或函数的真实地址，所以 `std::addressof(f)` 返回函数指针，`T` 被推导为函数类型。

位域要分两种情况。对非 const 的位域 `b.a`，`T` 推导为 `int`，`int&` 不能绑定到位域（[[dcl.init.ref]]），调用非良构，Clang 报 non-const reference cannot bind to bit-field。对 const 的位域 `b.c`，`T` 推导为 `const int`，`const int&` 会绑定到一个临时对象，于是 `addressof` 返回临时对象的地址，表达式结束后就悬空了。弃置的 `addressof(const T&&)` 拦不住它，因为实参是左值。本机 Clang 23 对此不给任何诊断。
</details>

!!! question "思考题 2"
    下面的代码在 C++20 中是良定义的吗？`int* p = (int*)std::calloc(4, sizeof(int)); return p[3];`

<details markdown="1">
<summary>答案</summary>

良定义，返回 0。`calloc` 隐式创建了合适的对象（这里是 `int` 数组或若干 `int`，由之后的使用方式决定），而且对象在清零之前创建（[[c.malloc#4]]），所以它们的值是 0。C++17 及以前，严格按标准这块存储里没有任何 `int` 对象，读取是未定义行为，[[P0593R6]] 修补了这个问题。
</details>
