---
title: unique_ptr
summary: 独占所有权指针的完整契约——删除器的三种形态与空基优化、pointer 类型的推导、不完整类型何时可以何时不行、unique_ptr<T[]> 的转换限制、reset 的操作顺序、make_unique 与 make_unique_for_overwrite，以及 ABI 层面"按值传递 unique_ptr 并不免费"
status: done
covers: *
related: smartptr, util.sharedptr, expr.delete, expr.new, basic.life, class.dtor, pointer.traits, smartptr.adapt, nullablepointer.requirements
tags: 标准库, 智能指针, unique_ptr, RAII, 删除器, ABI
papers: P2273R3, P1020R1
updated: 2026-10-18
---

`unique_ptr` 是 C++ 资源管理的基石：它把"谁负责释放"这个问题编码进类型系统。它的设计目标是**零开销**——对默认删除器，`unique_ptr<T>` 与 `T*` 一样大，生成的代码与手写 `delete` 相同。为了达到这一点，同时又支持任意的释放策略（`fclose`、`free`、自定义池、`CloseHandle`……），标准给它配了一套相当精巧的删除器与 `pointer` 类型规则。

本页覆盖 [unique.ptr] 的全部子条款。

## 独占所有权的定义（[unique.ptr.general]）

¶1–¶3 用一个抽象模型定义"唯一指针"（[[g:unique-pointer]]）：对象 *u* 存储指向另一对象 *p* 的指针，并在 *u* 自身被销毁时**处置** *p*；此时称 *u* **拥有** *p*。处置的机制称为 *p* 的关联**删除器**（[[g:deleter]]）——一个函数对象，正确调用它会导致 *p* 被适当处置（通常是删除）。记 *u.p* 为存储的指针、*u.d* 为删除器。*u* 可以按请求**重置**二者，但在替换被视为完成之前，必须先经由旧删除器处置旧对象。

¶4：`unique_ptr` 的每个特化都满足 *Cpp17MoveConstructible* 与 *Cpp17MoveAssignable*，但**不**满足可复制的要求——"严格所有权语义"在类型层面的体现。**`T` 可以是不完整类型**——这是 pimpl 惯用法的基础，但有条件，见下文。

## 默认删除器（[unique.ptr.dltr]）

`default_delete<T>` 是一个空类：

- `operator()(T* ptr)`：*Mandates* `T` 是完整类型（[unique.ptr.dltr.dflt] ¶3）；效果是对 `ptr` 调用 `delete`（¶4）。
- 转换构造函数 `default_delete(const default_delete<U>&)`：*Constraints* `U*` 可隐式转换为 `T*`（¶1）。这是 `unique_ptr<Base>` 能从 `unique_ptr<Derived>` 构造的原因之一。

`default_delete<T[]>`（[unique.ptr.dltr.dflt1]）调用 `delete[]`，其 `operator()` 本身是模板 `template<class U> operator()(U* ptr)`，*Constraints* 为 `U(*)[]` 可转换为 `T(*)[]`——只允许**添加 cv 限定**，不允许派生类到基类。

### "完整类型"的 *Mandates* 为何重要

C++98 的 `delete p` 对不完整类型只是 {{ub}}（若该类型有非平凡析构函数或类特有的 `operator delete`，[[expr.delete]]），编译器最多给个警告。`default_delete` 把它提升为 *Mandates*：库实现用 `static_assert(sizeof(T) > 0)` 一类手段**强制诊断**。这把 pimpl 中最常见的错误从运行期泄漏变成了编译错误：

```cpp title="pimpl-incomplete.cpp" error
#include <memory>
class Widget {
    struct Impl;                      // 不完整类型
    std::unique_ptr<Impl> impl;       // OK：unique_ptr<T> 允许 T 不完整
public:
    Widget();
    // 没有声明析构函数：隐式析构函数在被 odr-use 处定义，此时 Impl 仍不完整
};
void use() { Widget w; }              // error：实例化 ~unique_ptr → default_delete<Impl>::operator()
```

libc++ 的诊断是"invalid application of 'sizeof' to an incomplete type 'Widget::Impl'"。正确做法是在头文件中**声明** `~Widget();`，在 `Impl` 完整的 .cpp 文件里定义 `Widget::~Widget() = default;`。移动构造和移动赋值同理（它们也可能销毁旧的 `Impl`）。

## 单对象 `unique_ptr`（[unique.ptr.single]）

### 类型要求（[unique.ptr.single.general]）

¶1：若 `T*` 是无效类型，实例化 `unique_ptr<T, D>` 的定义是 {{ill-formed}}。注 1 举例：`unique_ptr<T&, D>`、`unique_ptr<int() const, D>`。这条由 [[LWG4144]] 加入——此前 `unique_ptr<int&>` 的行为没有明确规定。

¶2：`D` 必须是函数对象类型、函数的左值引用，或函数对象类型的左值引用，且对 `D` 的值 `d` 和 `pointer` 的值 `ptr`，`d(ptr)` 有效并恰当地处置该指针。¶3：`D` 若不是引用类型，须满足 *Cpp17Destructible*。

¶4 是 `pointer` 的推导规则：

!!! std "[unique.ptr.single.general]/4"
    If the qualified-id `remove_reference_t<D>::pointer` is valid and denotes a type, then `unique_ptr<T, D>::pointer` shall be a synonym for `remove_reference_t<D>::pointer`. Otherwise `unique_ptr<T, D>::pointer` shall be a synonym for `element_type*`.

    若删除器类型有嵌套的 `pointer` 类型，`unique_ptr` 的 `pointer` 就是它；否则是 `T*`。

`pointer` 须满足 *Cpp17NullablePointer*（[[nullablepointer.requirements]]）：可与 `nullptr` 比较、值初始化得到空值、可复制且不抛出。这让 `unique_ptr` 可以管理**不是指针的句柄**——POSIX 文件描述符、Win32 `HANDLE`、OpenGL 对象名——只要把它包成满足 *Cpp17NullablePointer* 的类型，并在删除器里声明 `using pointer = Handle;`。¶5 的例子说明分配器的花式指针类型也可以用作 `pointer`。

### 删除器的三种形态与空基优化

| `D` 的形态 | 存储 | `sizeof(unique_ptr<int, D>)`（本机 libc++，64 位） |
|---|---|---|
| `default_delete<int>` | 空类，零开销 | 8 |
| 空函数对象 / 无捕获 lambda | 空类，零开销 | 8 |
| 函数指针 `void(*)(int*)` | 一个指针 | 16 |
| 函数对象的引用 `D&` | 一个引用 | 16 |
| 有状态函数对象 | 其状态 | `8 + sizeof(D)`（含填充） |

空删除器不占空间是靠**空基类优化**或 `[[no_unique_address]]`（[[intro.object]] 中"潜在重叠子对象"一节）实现的。标准没有要求这一点，但所有主流实现都做到了，因为这是 `unique_ptr` 零开销承诺的核心。所以：**优先用无状态函数对象，而不是函数指针作删除器**——后者不仅让 `unique_ptr` 变大一倍，还阻碍内联。

```cpp title="deleter-size.cpp" impl
#include <memory>
#include <cstdio>
#include <cstdlib>

struct FreeDeleter { void operator()(void* p) const noexcept { std::free(p); } };

int main() {
    auto lam = [](int* p) { delete p; };
    std::printf("default_delete : %zu\n", sizeof(std::unique_ptr<int>));                  // 8
    std::printf("empty functor  : %zu\n", sizeof(std::unique_ptr<int, FreeDeleter>));     // 8
    std::printf("stateless λ    : %zu\n", sizeof(std::unique_ptr<int, decltype(lam)>));   // 8
    std::printf("function ptr   : %zu\n", sizeof(std::unique_ptr<int, void(*)(int*)>));   // 16
    std::printf("deleter ref    : %zu\n", sizeof(std::unique_ptr<int, FreeDeleter&>));    // 16
}
```

**引用删除器** `unique_ptr<T, D&>`：`unique_ptr` 只存一个引用，删除器对象由外部拥有、必须活得比 `unique_ptr` 长。构造时只接受左值删除器——[unique.ptr.single.ctor] ¶13 规定 `D` 为引用类型时，接受 `remove_reference_t<D>&&` 的构造函数被**定义为弃置**，¶14 的例子 `unique_ptr<int, const D&> p4(new int, D());` 是错误的，因为它会把引用绑定到一个临时删除器上。

### 构造函数（[unique.ptr.single.ctor]）

- 默认构造与 `nullptr_t` 构造（¶1–¶4）：*Constraints* `D` 不是指针类型且可默认构造。**不是指针类型**这一条很关键：`unique_ptr<int, void(*)(int*)> p;` 不可行——一个值初始化的函数指针删除器是空指针，之后调用它就是 UB，所以干脆不让构造。
- `explicit unique_ptr(type_identity_t<pointer> p)`（¶5–¶8）：`explicit` 防止 `T*` 静默变成所有权；`type_identity_t` 阻止类模板实参推导——`unique_ptr p(new int);` 是 {{ill-formed}}，因为无法区分 `new int` 和 `new int[n]`。
- `(p, d)` 两个构造函数（¶9–¶13）：分别从 `const D&` 复制、从 `D&&` 移动删除器；前置条件要求这次构造不抛异常。
- 移动构造（¶15–¶18）：`D` 是引用时**复制**引用，否则移动删除器。
- 转换移动构造 `unique_ptr(unique_ptr<U, E>&&)`（¶19–¶22）：*Constraints* 为 (19.1) `unique_ptr<U, E>::pointer` 可隐式转换为 `pointer`；(19.2) `U` 不是数组；(19.3) `D` 为引用时 `E` 必须与 `D` 相同，否则 `E` 可隐式转换为 `D`。

### 析构（[unique.ptr.single.dtor]）

¶1：等价于 `if (get()) get_deleter()(get());`。所以删除器**不会**被以空指针调用——`fclose(nullptr)` 之类的问题不存在。¶2：若删除器抛出异常，行为未定义。

**多态删除的陷阱。** 转换构造只检查指针可转换，**不检查**析构函数是否为虚。`unique_ptr<Base>` 持有 `Derived` 对象而 `Base` 析构函数非虚时，`default_delete<Base>` 执行 `delete (Base*)p`，按 [[expr.delete]] 是 {{ub}}：

```cpp title="nonvirtual-dtor.cpp" ub
#include <memory>
#include <string>
struct Base { ~Base() {} };                     // 非虚析构函数
struct Derived : Base { std::string s = std::string(100, 'x'); };
int main() {
    std::unique_ptr<Base> p = std::make_unique<Derived>();   // 编译通过：Derived* → Base* 可隐式转换
}                                                            // UB: delete 一个 Base*，其动态类型是 Derived
```

本机 ASan/LSan 报告 "detected memory leaks"（`Derived::s` 的缓冲区从未释放）——这只是众多可能后果之一。`shared_ptr` 没有这个问题，因为它的删除器在**构造时**按实际类型捕获（见 [[util.smartptr.shared]]）。

### 赋值（[unique.ptr.single.asgn]）

移动赋值的效果（¶3）是：

```cpp
reset(u.release());
get_deleter() = std::forward<D>(u.get_deleter());
```

¶4 后置条件：若 `this != addressof(u)`，`u.get() == nullptr`；否则 `u.get()` 不变——自移动赋值是安全的空操作（`reset(release())` 释放后又接管同一指针）。

!!! ub "链表中的 `head = std::move(head->next)`"
    这条"先 reset、后赋删除器"的顺序藏着一个陷阱。在单链表 `struct Node { unique_ptr<Node> next; }` 里写 `head = std::move(head->next);`：`reset` 删除旧头节点，而 `u` 正是**旧头节点的 `next` 成员**——它随之被销毁；紧接着 `u.get_deleter()` 访问的是已销毁的对象。按标准措辞这是 {{ub}}。对空删除器，运行期通常没有可观察的后果（没有真正读内存），ASan 也查不出来；但常量求值器会直接指出：

    ```cpp title="list-pop.cpp" ub
    #include <memory>
    #include <utility>

    struct Node {
        std::unique_ptr<Node> next;
        int v;
    };

    constexpr int pop_bad() {
        auto head = std::make_unique<Node>(std::make_unique<Node>(nullptr, 2), 1);
        head = std::move(head->next);   // reset 销毁旧头 → u 随之销毁 → 再访问 u.get_deleter()
        return head->v;
    }

    constexpr int pop_good() {
        auto head = std::make_unique<Node>(std::make_unique<Node>(nullptr, 2), 1);
        head = std::exchange(head->next, nullptr);   // 先把 next 移到临时对象里，再赋值
        return head->v;
    }

    static_assert(pop_good() == 2);
    int main() { return pop_bad() == 2 ? 0 : 1; }   // 运行期"看起来正常"
    ```

    在 `static_assert(pop_bad() == 2)` 中，Clang 23 报告 "member call on heap allocated object that has been deleted"。用 `std::exchange` 或先移到局部变量即可避免。

转换移动赋值（¶6–¶10）的 *Constraints*：指针可隐式转换、`U` 不是数组、`is_assignable_v<D&, E&&>`。`operator=(nullptr_t)` 等价于 `reset()`。

### 观察器（[unique.ptr.single.observers]）

- `operator*`（¶1–¶4）：*Constraints* `*declval<pointer>()` 良构（[[LWG4324]] 使其对 `unique_ptr<void>` SFINAE 友好）；*Mandates* `reference_converts_from_temporary_v<add_lvalue_reference_t<T>, decltype(*declval<pointer>())>` 为假——若花式 `pointer` 的 `operator*` 返回**纯右值**，`T&` 会绑定到临时对象而悬空，这种组合直接 {{ill-formed}}（[[LWG4148]]）；*Preconditions* `get() != nullptr`。`noexcept` 规格跟随 `*declval<pointer>()`。
- `operator->`（¶5–¶7）：*Preconditions* `get() != nullptr`。注意这两个前置条件都是**普通**前置条件，不是 C++26 的 *Hardened preconditions*——加固实现不保证检查空 `unique_ptr` 解引用。
- `get()`、`get_deleter()`、`explicit operator bool()`（返回 `get() != nullptr`）。

### 修改器（[unique.ptr.single.modifiers]）

`release()` 放弃所有权并返回指针，**不**调用删除器——忘记接住返回值就是泄漏。

`reset(p)` 的顺序是 ¶3 精心规定的：

!!! std "[unique.ptr.single.modifiers]/3"
    Assigns p to the stored pointer, and then, with the old value of the stored pointer, old_p, evaluates `if (old_p) get_deleter()(old_p);`

    先把 `p` 赋给存储的指针，然后才用旧值 `old_p` 调用删除器。

注 1 解释了原因：删除器的调用**可能销毁 `*this` 本身**（例如 `*this` 是被删除对象的成员，或删除器的副作用间接销毁了拥有者）。先更新指针，保证在删除器运行期间以及之后，`*this` 处于一致状态、不会二次删除。注 2 补充：这种情况下后置条件 `get() == p` 不成立，因为 `this->get()` 已不是有效表达式。¶5：删除器抛异常是 UB。

`swap`（¶6–¶7）交换指针与删除器；前置条件是删除器可交换且不抛出。

## 数组版本 `unique_ptr<T[], D>`（[unique.ptr.runtime]）

¶1 列出与主模板的差异：

- (1.1) 会被相应指针到数组类型禁止的 `unique_ptr<T[]>` 之间的转换，以及与非数组 `unique_ptr` 之间的互相转换，都**使程序非良构**；
- (1.2) 构造函数和 `reset` 拒绝指向 `T` 的**派生类**的指针；
- (1.3) 不提供 `operator*`、`operator->`；(1.4) 提供 `operator[]`；(1.5) 默认删除器调用 `delete[]`。

¶3：`T` 必须是**完整**类型（与单对象版本不同）。

为什么禁止 `Derived[]` → `Base[]`？因为数组下标运算按**静态**类型的大小步进：`Base* p = new Derived[3]; p[1]` 访问的是错误的地址，`delete[] p` 更是 UB（[[expr.delete]]）。规则的实现手段是把"可转换"检查统一表述为 `V(*)[]` 可转换为 `element_type(*)[]`——指向数组的指针之间只允许 cv 限定转换（[[conv.qual]]），恰好排除了派生到基的转换。

```cpp title="array-conversions.cpp" ok
#include <memory>
#include <type_traits>
struct B {}; struct D : B {};
static_assert( std::is_convertible_v<std::unique_ptr<int[]>, std::unique_ptr<const int[]>>);  // 加 const：OK
static_assert(!std::is_convertible_v<std::unique_ptr<D[]>,   std::unique_ptr<B[]>>);          // 派生到基：拒绝
static_assert(!std::is_constructible_v<std::unique_ptr<B[]>, D*>);                             // 构造函数也拒绝
static_assert(!std::is_convertible_v<std::unique_ptr<int[]>, std::unique_ptr<int>>);           // 数组 ↔ 非数组：拒绝
static_assert( std::is_constructible_v<std::unique_ptr<const int[]>, int*>);
int main() {}
```

构造函数（[unique.ptr.runtime.ctor] ¶2、¶4）、转换构造（¶6）、转换赋值（[unique.ptr.runtime.asgn] ¶2）与 `reset`（[unique.ptr.runtime.modifiers] ¶3）的 *Constraints* 都是这一规则的变体；注意它们只在 `pointer` 就是 `element_type*` 时才允许"`V*` 转换"，花式指针必须类型完全相同。

`operator[](size_t i)`（[unique.ptr.runtime.observers]）：*Preconditions* `i` 小于数组元素个数。`unique_ptr<T[]>` **不知道**数组长度，标准层面无法检查。

!!! impl "libc++ 的数组 cookie 边界检查"
    libc++ 在加固模式（`fast` 及以上）下会对 `unique_ptr<T[]>::operator[]` 做边界检查——但只在它能"免费"得到长度时：Itanium C++ ABI 要求 `new T[n]` 在 `T` 有非平凡析构函数时在数组前面存放元素个数（**数组 cookie**），供 `delete[]` 使用。libc++ 在使用默认删除器且存在 cookie 时读取它。本机实测：`make_unique<std::string[]>(3)` 后访问 `[3]` 在 `fast` 模式下被捕获终止；`make_unique<int[]>(3)` 后访问 `[3]` 则不被捕获（`int` 平凡可析构，没有 cookie）。libc++ 还提供一个改变布局、额外存储长度的 ABI 配置（`_LIBCPP_ABI_BOUNDED_UNIQUE_PTR`），默认不启用。

## 创建函数（[unique.ptr.create]）

| 调用 | 约束 | 等价于 |
|---|---|---|
| `make_unique<T>(args...)` | `T` 不是数组 | `unique_ptr<T>(new T(std::forward<Args>(args)...))` |
| `make_unique<T[]>(n)` | 未知边界数组 | `unique_ptr<T>(new remove_extent_t<T>[n]())`——**值初始化** |
| `make_unique<T[N]>(...)` | 已知边界数组 | 弃置 |
| `make_unique_for_overwrite<T>()` | `T` 不是数组 | `unique_ptr<T>(new T)`——**默认初始化** |
| `make_unique_for_overwrite<T[]>(n)` | 未知边界数组 | `unique_ptr<T>(new remove_extent_t<T>[n])` |
| `make_unique_for_overwrite<T[N]>(...)` | 已知边界数组 | 弃置 |

几点说明：

- `make_unique` 用的是 `new T(args...)`（圆括号），C++20 起对聚合也适用（圆括号聚合初始化，[[dcl.init]]），但**不会**选择 `initializer_list` 构造函数：`make_unique<vector<int>>(3, 1)` 是三个 1，不是 `{3, 1}`。
- `make_unique<T[]>(n)` 的 `()` 意味着值初始化：`make_unique<double[]>(1'000'000)` 会把一百万个 `double` 清零。若马上要覆盖它们，这是纯浪费——这正是 C++20 `make_unique_for_overwrite`（[[P1020R1]]）存在的理由：默认初始化，平凡类型的元素具有不确定值（C++26 起，对自动变量是错误值；对动态分配对象仍是不确定值，见 [[basic.indet]]）。
- `make_unique` 没有自定义删除器的版本，也没有分配器版本。
- **C++17 之后，`make_unique` 已不再是异常安全的必需品。** C++14 时代的经典论证是 `f(unique_ptr<T>(new T), g())` 可能先执行 `new T`、再执行抛异常的 `g()`、导致泄漏；C++17 规定函数实参的初始化彼此**不交错**（[[expr.call]]），这个泄漏不再可能。`make_unique` 今天的价值在于不写 `new`、不重复类型名。

C++23 起，`unique_ptr` 的绝大部分操作以及 `make_unique` 都是 `constexpr` 的（[[P2273R3]]）：

```cpp title="constexpr-unique-ptr.cpp" ok
#include <memory>
constexpr int f() {
    auto p = std::make_unique<int>(20);
    auto q = std::make_unique<int[]>(3);   // 值初始化：全 0
    q[1] = 22;
    return *p + q[0] + q[1];
}
static_assert(f() == 42);
int main() {}
```

## 特化算法与比较（[unique.ptr.special]）

- `swap(x, y)`：*Constraints* `is_swappable_v<D>`。
- `==` 比较 `get()`；`<` 用 `less<CT>`（`CT` 是两种 `pointer` 的公共类型），这保证即使比较**不相关**的指针也有全序（裸指针的 `<` 对不相关对象是未指明的，而 `std::less` 对指针总给出实现定义的全序，[[comparisons.general]]）。`<=>` 用 `compare_three_way`，同样提供全序。
- 与 `nullptr` 的比较（¶12–¶18）一应俱全。

## 散列与 I/O

- `hash<unique_ptr<T, D>>`（[[util.smartptr.hash]] ¶1）：当且仅当 `hash<pointer>` 启用时启用，值等于 `hash<pointer>()(p.get())`；成员函数不保证 `noexcept`（花式指针的散列可能抛出）。
- `operator<<`（[unique.ptr.io]）：*Constraints* `os << p.get()` 有效，等价于输出 `p.get()`。

## ABI 视角：按值传递 `unique_ptr` 并不免费

`sizeof(unique_ptr<T>) == sizeof(T*)`，但在 Itanium C++ ABI（Linux、macOS）下，**有非平凡析构函数或复制/移动构造函数的类型不能通过寄存器传递**：调用者在栈上构造临时对象，传它的地址；被调用者返回后，调用者还要检查并析构这个（已被移空的）临时对象。所以 `void sink(std::unique_ptr<T> p)` 的调用比 `void sink(T* p)` 多一次内存写、一次内存读和一次析构检查。

libc++ 有一个 ABI 配置 `_LIBCPP_ABI_ENABLE_UNIQUE_PTR_TRIVIAL_ABI`，给 `unique_ptr` 加上 Clang 的 `[[clang::trivial_abi]]` 属性，使其能通过寄存器传递。它在 libc++ 的 ABI v2 中默认开启，但主流平台使用的 ABI v1 为了二进制兼容没有开启。这是"标准库的 ABI 稳定性"代价的一个经典例子。

## 思考题

<details markdown="1">
<summary>1. 为什么 `unique_ptr<T>` 允许 `T` 不完整，而 `unique_ptr<T[]>` 要求 `T` 完整？</summary>

单对象版本的类定义本身不需要知道 `sizeof(T)`：存储的只是 `T*`，析构才需要完整类型（由 `default_delete::operator()` 的 *Mandates* 把关）。数组版本的转换规则要求判断 `V(*)[]` 是否可转换为 `T(*)[]`，以及 `operator[]` 的指针算术，都需要 `T` 完整；[unique.ptr.runtime.general] ¶3 因此把它作为整体要求。
</details>

<details markdown="1">
<summary>2. 下面的删除器有什么问题？`std::unique_ptr<FILE, int(*)(FILE*)> f(std::fopen("x", "r"), &std::fclose);`</summary>

至少三个问题。其一，`unique_ptr` 变成两个指针大小，且通过函数指针调用不易内联。其二，取标准库函数的地址是未指明行为甚至可能非良构——标准库函数（除少数被明确标为 *addressable* 的以外）都不保证能取地址（[[namespace.std]]）。其三，`fopen` 失败返回空指针时没问题（析构不会以空指针调用删除器），但 `fclose` 的返回值被丢弃，写缓冲失败的错误被吞掉。更好的写法是自定义一个无状态函数对象 `struct fcloser { void operator()(FILE* f) const noexcept { std::fclose(f); } };`。
</details>

<details markdown="1">
<summary>3. `unique_ptr<int, void(*)(int*)> p;` 为什么不能编译？</summary>

默认构造函数的 *Constraints* 要求 `is_pointer_v<deleter_type>` 为假（¶1）。函数指针删除器被值初始化为空指针，一旦之后 `reset(new int)` 再析构就会调用空函数指针。标准选择在编译期就排除这种构造。
</details>

## 小结

- `pointer` = `D::pointer`（若有）否则 `T*`；须满足 *Cpp17NullablePointer*，因此可管理非指针句柄。
- 空删除器经空基优化不占空间；函数指针删除器使大小翻倍。
- `T` 可不完整，但析构点必须看到完整类型（*Mandates*，强制诊断）。
- 析构与 `reset` 不以空指针调用删除器；`reset` 先改指针再调删除器；删除器抛异常是 UB。
- 移动赋值是"先 `reset(u.release())` 再赋删除器"，`p = std::move(p->next)` 因此是陷阱。
- 数组版本禁止派生到基的转换、禁止数组与非数组互转，`operator[]` 无标准边界检查。
- `make_unique<T[]>` 值初始化，`make_unique_for_overwrite` 默认初始化；C++23 起 `constexpr`。
- ABI：主流平台上 `unique_ptr` 不能经寄存器传递。
