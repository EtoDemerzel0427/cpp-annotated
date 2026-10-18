---
title: 内存（<memory> 总览）
summary: <memory> 头文件概要的读法：POINTER_OF 说明用工具、freestanding 标注、特化内存算法与 placement new 的关系；addressof 为什么存在；C 的 malloc 族在 C++ 对象模型里隐式创建对象，realloc(p, 0) 是错误行为
status: done
covers: memory.general, memory.syn, specialized.addressof, c.malloc
related: mem, intro.object, basic.life, expr.new, specialized.algorithms, pointer.traits, allocator.traits, support.types
tags: 标准库, memory, addressof, malloc, freestanding
papers: P2590R2
updated: 2026-10-18
---

[memory] 是第 20 章的第一个大子条款，¶1 说它描述 `<memory>` 的内容和 `<cstdlib>` 的**一部分**内容（即 C 的 `malloc` 族，见本页最后一节）。它下面挂了十几个小节，本站按主题拆成几页：

| 子条款 | 本站笔记 |
|---|---|
| [pointer.traits]、[pointer.conversion] | [[pointer.traits]]：`pointer_traits`、`to_address` |
| [ptr.align] | [[ptr.align]]：`align`、`assume_aligned`、`is_sufficiently_aligned` |
| [obj.lifetime] | [[obj.lifetime]]：`start_lifetime`、`start_lifetime_as(_array)` |
| [allocator.tag]、[allocator.uses] | [[allocator.uses]]：`allocator_arg`、`uses_allocator`、uses-allocator 构造 |
| [allocator.traits] | [[allocator.traits]] |
| [default.allocator] | [[default.allocator]]：`std::allocator` |
| [specialized.addressof]、[c.malloc] | 本页 |

## 头文件概要（[memory.syn]）

### ¶1：`<memory>` 管哪几类东西

¶1 把 `<memory>` 的内容分成几类：描述指针与类指针类型性质的类型和函数模板、为容器等模板管理内存、销毁对象、在**未初始化内存**中构造对象（[pointer.traits] 到 [specialized.addressof]，以及 [[specialized.algorithms]]）；`pointer_tag_pair`（[[ptrtag]]，其位选择由实现定义，包装后对象的大小与原指针相同）；以及智能指针与 `out_ptr_t`/`inout_ptr_t`（[[smartptr]]）。

概要本身有八百多行，绝大部分是声明。读它时值得注意的只有几件事。

### freestanding 标注

概要里几乎每一行都带 `// freestanding` 注释，意思是**独立实现**（[[g:freestanding-implementation]]）也必须提供这个声明。一个有趣的划分是：

- `pointer_traits`、`allocator_traits`、`uses_allocator`、`addressof`、`construct_at`、`unique_ptr`、`default_delete`、`out_ptr`、`pointer_tag_pair`：**freestanding**。这些东西不依赖堆——`unique_ptr` 配一个自定义删除器，在内核里也能用。
- `std::allocator`、`shared_ptr`、`weak_ptr`、`make_unique`、`indirect`、`polymorphic`：**不是** freestanding。它们要么直接调用 `::operator new`，要么（`shared_ptr`）需要分配控制块。
- 带执行策略的并行算法重载标为 `// freestanding-deleted`：在独立实现里这些重载存在但被定义为弃置（见 [[freestanding.item]]）。

### ¶2–¶3：`POINTER_OF` 与 `POINTER_OF_OR`

¶2 定义了一个说明用（exposition-only）的类型函数 *POINTER_OF*(T)：

1. 若 `T::pointer` 有效且是类型，就是它（¶2.1）；
2. 否则若 `T::element_type` 有效，就是 `T::element_type*`（¶2.2）；
3. 否则是 `pointer_traits<T>::element_type*`（¶2.3）。

¶3 的 *POINTER_OF_OR*(T, U) 是"若 *POINTER_OF*(T) 有效就用它，否则用 `U`"。这两个工具只被 [[smartptr.adapt]] 的 `out_ptr`/`inout_ptr` 使用：它们需要从任意"智能指针类"推出"裸指针类型应该是什么"。

### 两个 `pmr` 别名

概要末尾在 `std::pmr` 里声明了 `pmr::indirect<T>` 与 `pmr::polymorphic<T>`，即使用 `polymorphic_allocator<T>` 的版本（[[indirect]]、[[polymorphic]]、[[mem.poly.allocator.class]]）。

## 特化内存算法：库版的 placement new

`uninitialized_copy`、`uninitialized_fill`、`construct_at`、`destroy_at`、`destroy` 等声明在 `<memory>`，规范在 [[specialized.algorithms]]。它们和核心语言的关系非常直接：

- `construct_at(p, args...)` 的效果就是 `::new (voidify(*p)) T(std::forward<Args>(args)...)`（[[specialized.construct]]），其中 `voidify(obj)` 是 `addressof(obj)` 转成 `void*`。也就是说它**就是**一次 placement new（[[expr.new]]），只不过：
  - 用 `::new` 跳过类特有的 `operator new` 重载；
  - 用 `addressof` 而不是 `&`，不受重载 `operator&` 干扰；
  - 它是 `constexpr` 的（C++20 起）。C++26 之前常量求值里**不能**直接写 placement new，`construct_at` 是唯一途径；C++26 起 placement new 本身也可用于常量求值。
- `destroy_at(p)` 对非数组 `T` 就是 `p->~T()`，对数组则逐元素销毁。
- 这些算法创建新对象时，复用存储上原有对象的生命周期结束（[[specialized.algorithms.general]] ¶3 的注，规则本身来自 [[basic.life]]）。若构造中途抛异常，已构造的对象以**未指明的顺序**销毁后再传播异常（同条 ¶2）。

```cpp title="construct-at.cpp" ok
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

本机 Clang 23 在 `-std=c++23` 下对第二种写法报"this placement new expression is not supported in constant expressions before C++2c"，`-std=c++2c` 下通过。

## `addressof`（[specialized.addressof]）

¶1：`addressof(r)` 返回 `r` 所引用对象或函数的**真实地址**，即使类型重载了 `operator&`。¶2：若 `E` 是左值常量子表达式，`addressof(E)` 也是常量子表达式——因此它可用于常量求值。

为什么需要它？一元 `&` 对类类型操作数会参与重载决议（[[over.match.oper]]），用户可以让 `&x` 返回任何东西，甚至把它定义为弃置。泛型代码（容器、`optional`、`construct_at`）必须拿到真实地址，所以标准库内部一律用 `addressof`。

```cpp title="addressof.cpp" ok
#include <memory>

struct Evil {
    int x;
    void operator&() const = delete;   // 禁止取地址
};

constexpr int g() {
    Evil e{5};
    // &e;                               // error: 调用弃置函数
    return std::addressof(e)->x;         // OK：真实地址，且可用于常量求值
}
static_assert(g() == 5);

int main() {}
```

概要里还有一个弃置重载 `const T* addressof(const T&&) = delete;`，用来拒绝对右值取地址（`std::addressof(Evil{})` 是 {{ill-formed}}）——临时对象的地址几乎必然悬空。

!!! impl "实现"
    `addressof` 无法用纯 C++ 在常量求值中实现（`reinterpret_cast` 不是常量表达式），libc++、libstdc++、MSVC STL 都用编译器内建函数 `__builtin_addressof`。这是标准库依赖编译器"魔法"的典型例子。

## C 库内存分配（[c.malloc]）

这一节虽然在 `<memory>` 的子条款下，声明却在 `<cstdlib>`（¶1 的注）。它对 C 函数的语义"照搬 C 标准"（¶2、¶8，当前引用 C23，即 ISO/IEC 9899:2024 7.24.4），但补充了三条 C++ 独有的规则。

### 不经过 `operator new`（¶3、¶7、¶9）

`malloc`、`calloc`、`aligned_alloc`、`realloc` 不会调用 `::operator new()`，`free` 也不会调用 `::operator delete()`。所以**替换全局 `operator new`**（[[new.delete]]）不会影响 `malloc`；反之，用 `free` 释放 `new` 得到的内存、或用 `delete` 释放 `malloc` 的内存，都是 {{ub}}（[[basic.stc.dynamic.deallocation]]）。

### 隐式创建对象（¶4、¶7）

这是 C++20 的关键修补（[[P0593R6]]）：

!!! std "[c.malloc]/4"
    These functions implicitly create objects ([intro.object]) in the returned region of storage and return a pointer to a suitable created object.

    这些函数在返回的存储区域中**隐式创建对象**，并返回指向一个"合适的"已创建对象的指针。

所以 `auto* p = static_cast<Point*>(std::malloc(sizeof(Point))); p->x = 1;` 在 C++20 起对隐式生存期类型是良定义的——不需要 placement new。机制细节见 [[intro.object]] 的"隐式对象创建"一节。两个顺序细节：

- `calloc`：对象**在清零之前**创建。因此清零的字节成为这些对象的值（对 `int` 就是 0）。
- `realloc`：返回非空指针时，对象**在拷贝之前**创建。于是旧内容被拷贝进"已经存在的"新对象，`realloc` 一个 `int` 数组后读元素是良定义的。

### `realloc(p, 0)`：错误行为（¶5–¶6）

¶5 的前置条件是 `free(ptr)` 有良定义行为（`ptr` 是空指针，或来自 `malloc` 族且尚未释放）。¶6 有一条 C++ 特有的规定：

!!! std "[c.malloc]/6"
    If ptr is not null and size is zero, the behavior is erroneous and the effects are implementation-defined.

    若 `ptr` 非空而 `size` 为零，行为是**错误行为**（erroneous behavior），其效果由实现定义。

背景：C 语言对 `realloc(p, 0)` 的语义长期分裂（有的实现释放 `p` 并返回空指针，有的返回一个最小块），C23 干脆把它改成了未定义行为。C++ 没有跟着变成 UB，而是归为 {{erroneous}}：实现必须给出确定的（由实现定义的）效果，但这种写法被标记为"错误"，实现可以诊断或终止（[[g:erroneous-behavior]]）。可移植代码应当把 `size == 0` 单独处理。

!!! pitfall "malloc 的对齐保证"
    `malloc` 只保证对**基本对齐**（[[g:fundamental-alignment]]，即 `alignof(max_align_t)`）合适。若类型有扩展对齐（`alignas(64)`），要用 `aligned_alloc`，并且 `size` 应是 `alignment` 的整数倍（C 标准的要求）；或者直接用 `new`——C++17 起 `new` 会对过对齐类型自动调用带 `align_val_t` 的分配函数。

## 思考题

<details markdown="1">
<summary>1. `std::addressof(f)` 中 `f` 是一个函数，返回什么？`addressof` 能否用于位域？</summary>

¶1 明确说 `addressof` 返回"对象**或函数**"的真实地址，所以 `std::addressof(f)` 返回函数指针（`T` 被推导为函数类型，返回 `T*`）。

位域则要分情况。对非 const 位域 `b.a`，`T` 推导为 `int`，`int&` 不能绑定到位域（[[dcl.init.ref]] ¶5.1.1 排除了位域），调用 {{ill-formed}}——Clang 报"non-const reference cannot bind to bit-field"。但对 **const** 位域 `b.c`，`T` 推导为 `const int`，`const int&` 走 ¶5.4 的路径绑定到一个**临时对象**；`addressof` 于是"成功"返回临时对象的地址，表达式结束后即悬空。弃置的 `addressof(const T&&)` 重载拦不住它，因为实参是左值。本机 Clang 23 对此静默接受。
</details>

<details markdown="1">
<summary>2. 下面代码在 C++20 中是否良定义？`int* p = (int*)std::calloc(4, sizeof(int)); return p[3];`</summary>

良定义，返回 0。`calloc` 隐式创建一个 `int[4]`（或 4 个 `int`——"合适的"对象集合由使用方式决定），而且对象在清零**之前**创建（¶4），所以清零后它们的值是 0。C++17 及以前，严格按标准这里没有任何 `int` 对象存在，读取是 UB——这正是 [[P0593R6]] 修补的问题。
</details>

## 小结

- `<memory>` 概要的要点：freestanding 划分（`unique_ptr` 是，`shared_ptr`/`allocator` 不是）、*POINTER_OF* 工具、`pmr::indirect`/`pmr::polymorphic` 别名。
- `construct_at`/`destroy_at` 是 placement new 与伪析构调用的库包装：用 `::new`、`addressof`，并且 `constexpr`。
- `addressof` 绕过重载的 `operator&`；拒绝右值实参。
- `malloc` 族不经过 `operator new`，但会**隐式创建对象**；`calloc` 先建对象后清零，`realloc` 先建对象后拷贝；`realloc(p, 0)` 在 C++ 中是错误行为。
