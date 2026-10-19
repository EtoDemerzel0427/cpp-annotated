---
title: unique_ptr
summary: 独占所有权指针 unique_ptr 的完整规则：删除器与 pointer 类型、不完整类型、构造和赋值的约束、reset 的操作顺序、数组版本的转换限制、make_unique 系列，以及按值传递它在 ABI 上的代价。
status: done
covers: *
related: smartptr, util.sharedptr, expr.delete, expr.new, basic.life, class.dtor, pointer.traits, smartptr.adapt, nullablepointer.requirements
tags: 标准库, 智能指针, unique_ptr, RAII, 删除器, ABI
papers: P2273R3, P1020R1, P3144R2
updated: 2026-10-19
---

!!! tldr
    - `unique_ptr<T, D>` 拥有一个对象，自身销毁时用删除器 `D` 处置它。默认删除器和无状态删除器不占空间，`unique_ptr` 和普通指针一样大；函数指针删除器会让它变成两倍大。
    - `T` 可以是不完整类型，但销毁 `unique_ptr` 的地方必须能看到完整的 `T`，否则编译报错。pimpl 惯用法要在 `.cpp` 文件里定义析构函数。
    - 删除器若定义了嵌套类型 `pointer`，`unique_ptr` 存储的就是这个类型，于是能管理文件描述符这类不是指针的句柄。
    - `reset` 先存入新指针再调用删除器；移动赋值是先 `reset(u.release())` 再赋值删除器，所以 `head = std::move(head->next)` 是未定义行为。
    - `unique_ptr<T[]>` 禁止从派生类数组转换；`make_unique<T[]>(n)` 把元素值初始化，`make_unique_for_overwrite` 不初始化。

## 独占所有权 [unique.ptr.general]

¶1–¶3 标准先定义**唯一指针**（[[g:unique-pointer]]）这个抽象：对象 *u* 存储一个指向另一个对象 *p* 的指针，并在 *u* 自己被销毁时处置 *p*，这时说 *u* 拥有 *p*。处置所用的机制叫做 *p* 的**删除器**（[[g:deleter]]），它是一个函数对象，正确地调用它会以适当的方式处置 *p*，通常就是删除。*u* 可以按要求重置它存储的指针和删除器，但必须先用旧删除器处置旧对象，替换才算完成。

¶4 `unique_ptr` 的每个特化都实现了这种严格的所有权语义：可以移动构造和移动赋值，但不能复制。模板参数 `T` 可以是不完整类型，条件见下文。¶5 的注说明了它的用途：为动态分配的内存提供异常安全，把所有权传进函数，从函数里返回所有权。

## 删除器与 `pointer` 类型 [unique.ptr.single.general]

### 删除器决定大小

```cpp run impl
#include <cstdio>
#include <cstdlib>
#include <memory>

struct FreeDeleter {
  void operator()(void* p) const noexcept { std::free(p); }
};

int main() {
  auto lam = [](int* p) { delete p; };
  using FP = void (*)(int*);
  std::printf("%zu\n", sizeof(std::unique_ptr<int>));                  // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FreeDeleter>));     // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, decltype(lam)>));   // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FP>));              // 16
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FreeDeleter&>));    // 16
}
```

注释里是本机 64 位 libc++ 的输出。空的删除器（默认删除器、空函数对象、无捕获 lambda）不占空间，靠的是空基类优化或 `[[no_unique_address]]`（[[intro.object]] 中的潜在重叠子对象）。标准没有要求这一点，但主流实现都做到了，所以判定是 {{impl}}。

函数指针删除器要存一个指针，`unique_ptr` 变成两倍大，而且通过函数指针调用不容易内联。所以删除器应该优先写成无状态的函数对象。

### 对 `T` 和 `D` 的要求（¶1–¶3）

¶1 如果 `T*` 不是合法的类型，实例化 `unique_ptr<T, D>` 的定义是非良构的。注 1 举的例子是 `unique_ptr<T&, D>` 和 `unique_ptr<int() const, D>`（[[LWG4144]]）。

¶2 `D` 必须是函数对象类型、函数的左值引用，或者函数对象类型的左值引用；对 `D` 的值 `d` 和 `pointer` 的值 `ptr`，`d(ptr)` 必须合法，并能恰当地处置这个指针。¶3 `D` 不是引用类型时，必须满足 *Cpp17Destructible*。

`D` 是引用类型时，`unique_ptr` 只存一个引用，删除器对象由外部拥有，必须比 `unique_ptr` 活得更久。

### `pointer` 不一定是 `T*`（¶4–¶5）

!!! std "[unique.ptr.single.general]/4"
    If the qualified-id `remove_reference_t<D>::pointer` is valid and denotes a type, then `unique_ptr<T, D>::pointer` shall be a synonym for `remove_reference_t<D>::pointer`. Otherwise `unique_ptr<T, D>::pointer` shall be a synonym for `element_type*`.

¶4 如果删除器有嵌套类型 `pointer`，`unique_ptr` 存储的就是这个类型，否则是 `T*`。`pointer` 必须满足 *Cpp17NullablePointer*（[[nullablepointer.requirements]]）：能和 `nullptr` 比较，值初始化得到空值，复制时不抛异常。

这样 `unique_ptr` 就能管理不是指针的句柄，比如 POSIX 文件描述符、Win32 `HANDLE`：把句柄包装成满足 *Cpp17NullablePointer* 的类型，在删除器里写 `using pointer = Handle;`。¶5 的例子说明，分配器的花式指针类型也可以用作 `pointer`。

## 默认删除器与不完整类型 [unique.ptr.dltr]

```cpp run error
#include <memory>
class Widget {
  struct Impl;                   // 不完整类型
  std::unique_ptr<Impl> impl;    // OK: T 可以不完整
public:
  Widget();
  // 没有声明析构函数：隐式析构函数在 Impl 仍不完整处定义
};
void use() { Widget w; }         // error: 实例化 default_delete<Impl>::operator()
```

[unique.ptr.dltr.general] ¶2 允许 `default_delete<T>` 的 `T` 不完整。但 [unique.ptr.dltr.dflt] ¶3 规定，`default_delete<T>::operator()` 要求 `T` 是完整类型（*Mandates*），¶4 它的效果是对指针执行 `delete`。

`Widget` 没有声明析构函数，隐式的析构函数在第一次使用它的地方定义，那里 `Impl` 还不完整。析构 `impl` 要实例化 `default_delete<Impl>::operator()`，于是编译失败。本机 libc++ 报告对不完整类型 `Widget::Impl` 使用了 `sizeof`。

正确的写法是在头文件里只声明 `~Widget();`，在 `Impl` 完整的 `.cpp` 文件里写 `Widget::~Widget() = default;`。移动赋值也可能销毁旧的 `Impl`，同样要在 `.cpp` 里定义。

这条 *Mandates* 把 pimpl 最常见的错误变成了编译错误。直接 `delete` 一个不完整类类型的指针，C++26 之前在该类有非平凡析构函数时是未定义行为，编译器最多给一条警告；C++26 起这是非良构的（[[expr.delete#4]]，[[P3144R2]]）。

`default_delete` 是一个空类，还有一个转换构造函数：¶1 只要 `U*` 能隐式转换为 `T*`，`default_delete<T>` 就能从 `default_delete<U>` 构造。`unique_ptr<Base>` 能从 `unique_ptr<Derived>` 构造，靠的就是它。

数组版本 `default_delete<T[]>`（[unique.ptr.dltr.dflt1]）调用 `delete[]`。它的 `operator()` 是一个模板，¶3 要求 `U(*)[]` 能转换为 `T(*)[]`。指向数组的指针之间只允许添加 cv 限定，所以只接受 `T*` 和 cv 限定更少的指针，拒绝派生类指针。

## 构造 [unique.ptr.single.ctor]

- 默认构造和 `nullptr_t` 构造（¶1–¶4）要求 `D` 不是指针类型，并且可以默认构造。`unique_ptr<int, void(*)(int*)> p;` 不能编译：值初始化的函数指针删除器是空指针，之后一旦调用就是未定义行为，所以干脆不允许这样构造。
- `explicit unique_ptr(type_identity_t<pointer> p)`（¶5–¶8）。`explicit` 防止一个 `T*` 悄悄变成所有权；`type_identity_t` 禁止类模板实参推导，所以 `std::unique_ptr p(new int);` 是 {{ill-formed}}，因为从 `int*` 无法区分 `new int` 和 `new int[n]`。
- `(p, d)` 两个构造函数（¶9–¶13）分别从 `const D&` 复制删除器、从 `D&&` 移动删除器，前置条件要求这次构造不抛异常。¶13 规定 `D` 是引用类型时，接受右值的那个构造函数定义为弃置。¶14 的例子中 `unique_ptr<int, const D&> p4(new int, D());` 是错的，它会把引用绑定到一个临时删除器上。
- 移动构造（¶15–¶18）：`D` 是引用时复制这个引用，否则移动删除器。
- 转换移动构造 `unique_ptr(unique_ptr<U, E>&&)`（¶19–¶22）要求：¶19.1 `unique_ptr<U, E>::pointer` 能隐式转换为 `pointer`；¶19.2 `U` 不是数组；¶19.3 `D` 是引用时 `E` 必须与 `D` 相同，否则 `E` 必须能隐式转换为 `D`。

## 析构 [unique.ptr.single.dtor]

¶1 析构函数等价于 `if (get()) get_deleter()(get());`，所以删除器不会以空指针被调用，`fclose(nullptr)` 这类问题不会出现。¶2 删除器抛出异常时，行为未定义。

转换构造只检查指针能否转换，不检查析构函数是否为虚：

```cpp run ub
#include <memory>
#include <string>
struct Base { ~Base() {} };   // 非虚析构函数
struct Derived : Base { std::string s = std::string(100, 'x'); };
int main() {
  std::unique_ptr<Base> p = std::make_unique<Derived>();   // 编译通过
}   // UB: 通过 Base* 删除动态类型为 Derived 的对象
```

`default_delete<Base>` 执行 `delete` 一个 `Base*`，而对象的动态类型是 `Derived`，`Base` 的析构函数又不是虚的，按 [[expr.delete]] 这是未定义行为。本机用 `-fsanitize=address` 编译，加上 `ASAN_OPTIONS=detect_leaks=1` 运行，LeakSanitizer 报告 `Derived::s` 的缓冲区泄漏了，这只是可能的后果之一。`shared_ptr` 没有这个问题，它在构造时按实际类型记录删除方式（[[util.smartptr.shared]]）。

## 赋值 [unique.ptr.single.asgn]

¶3 移动赋值的效果是：

```cpp
reset(u.release());
get_deleter() = std::forward<D>(u.get_deleter());
```

¶4 如果 `this != addressof(u)`，赋值后 `u.get() == nullptr`；否则 `u.get()` 不变。所以自我移动赋值是安全的：`release` 交出指针，`reset` 又接管同一个指针。

先 `reset` 再赋值删除器，这个顺序在链表里会出问题：

```cpp run ub
#include <memory>
#include <utility>

struct Node {
  std::unique_ptr<Node> next;
  int v;
};

constexpr int pop_bad() {
  auto head = std::make_unique<Node>(
      std::make_unique<Node>(nullptr, 2), 1);
  head = std::move(head->next);   // UB
  return head->v;
}

constexpr int pop_good() {
  auto head = std::make_unique<Node>(
      std::make_unique<Node>(nullptr, 2), 1);
  head = std::exchange(head->next, nullptr);   // OK
  return head->v;
}

static_assert(pop_good() == 2);
int main() { return pop_bad() == 2 ? 0 : 1; }   // 运行期看起来正常
```

`head = std::move(head->next)` 中，`u` 就是旧头节点的成员 `next`。`reset` 删除旧头节点时，`u` 也随之销毁，接下来的 `u.get_deleter()` 访问的是一个已经销毁的对象。删除器是空类时，这次访问通常不真正读内存，运行期看不出问题，AddressSanitizer 也查不到。

常量求值会检查这种错误。把 `pop_bad()` 放进 `static_assert`，Clang 23 报告在已删除的堆对象上调用了成员函数。`pop_good` 先用 `std::exchange` 把 `next` 移到一个临时对象里，再赋给 `head`，就没有这个问题。

¶6–¶10 转换移动赋值要求指针能隐式转换、`U` 不是数组、`is_assignable_v<D&, E&&>` 为真。¶11 `operator=(nullptr_t)` 等价于 `reset()`。

## 观察器 [unique.ptr.single.observers]

- `operator*`（¶1–¶4）：¶1 要求 `*declval<pointer>()` 合法，所以 `unique_ptr<void>` 的 `operator*` 不会在重载决议中造成硬错误（[[LWG4324]]）。¶2 如果 `pointer` 的 `operator*` 返回纯右值，`T&` 会绑定到一个临时对象而悬空，这种组合是非良构的（[[LWG4148]]）。¶3 前置条件是 `get() != nullptr`。它的 `noexcept` 跟随 `*declval<pointer>()`。
- `operator->`（¶5–¶7）：前置条件同样是 `get() != nullptr`。
- `get()` 返回存储的指针，`get_deleter()` 返回删除器的引用，`explicit operator bool()` 返回 `get() != nullptr`。

这两个前置条件都是普通前置条件，不是 C++26 的加固前置条件（hardened precondition），所以加固实现也不保证检查空 `unique_ptr` 的解引用。

## 修改器 [unique.ptr.single.modifiers]

¶1–¶2 `release()` 放弃所有权并返回指针，不调用删除器。不接住返回值就是内存泄漏。

¶3 `reset(p)` 的顺序是规定好的：

!!! std "[unique.ptr.single.modifiers]/3"
    Assigns p to the stored pointer, and then, with the old value of the stored pointer, old_p, evaluates `if (old_p) get_deleter()(old_p);`

先把 `p` 存进去，再用旧值 `old_p` 调用删除器。注 1 解释了原因：调用删除器可能销毁 `*this` 本身，比如 `*this` 是被删除对象的成员。先更新指针，删除器运行期间和之后 `*this` 都处于一致的状态，不会删除两次。注 2 补充，这种情况下后置条件 `get() == p` 不成立，因为 `this->get()` 已经不是合法的表达式。¶5 删除器抛出异常是未定义行为。

¶6–¶7 `swap` 交换指针和删除器，前置条件是删除器可交换，并且交换时不抛异常。

## 数组版本 `unique_ptr<T[], D>` [unique.ptr.runtime]

¶1 数组版本和主模板的区别：

- ¶1.1 指向数组的指针之间不允许的转换，在相应的 `unique_ptr<T[], D>` 之间同样不允许；数组版本和非数组版本之间也不能互相转换。这些转换使程序非良构。
- ¶1.2 构造函数和 `reset` 拒绝指向 `T` 的派生类的指针。
- ¶1.3–¶1.4 没有 `operator*` 和 `operator->`，有 `operator[]`。
- ¶1.5 默认删除器调用 `delete[]`。

¶3 `T` 必须是完整类型，这和单对象版本不同。

禁止派生类数组转换为基类数组，是因为下标运算按静态类型的大小移动指针：`Base* p = new Derived[3];` 之后，`p[1]` 访问的是错误的地址，`delete[] p` 更是未定义行为（[[expr.delete]]）。规则写成 `V(*)[]` 能否转换为 `element_type(*)[]`，指向数组的指针之间只允许 cv 限定转换（[[conv.qual]]），正好排除了派生类到基类的转换。

```cpp run ok
#include <memory>
#include <type_traits>
struct B {};
struct D : B {};
using std::unique_ptr;
// 加 const：OK
static_assert(std::is_convertible_v<unique_ptr<int[]>,
                                    unique_ptr<const int[]>>);
// 派生到基：拒绝
static_assert(!std::is_convertible_v<unique_ptr<D[]>, unique_ptr<B[]>>);
static_assert(!std::is_constructible_v<unique_ptr<B[]>, D*>);
// 数组与非数组之间：拒绝
static_assert(!std::is_convertible_v<unique_ptr<int[]>, unique_ptr<int>>);
static_assert(std::is_constructible_v<unique_ptr<const int[]>, int*>);
int main() {}
```

构造函数（[unique.ptr.runtime.ctor] ¶2、¶4、¶6）、转换赋值（[unique.ptr.runtime.asgn] ¶2）和 `reset`（[unique.ptr.runtime.modifiers] ¶3）的约束都是这条规则的变体。注意只有 `pointer` 就是 `element_type*` 时才允许这种 `V*` 转换；使用花式指针时，类型必须完全相同。

[unique.ptr.runtime.observers] ¶1 `operator[](i)` 的前置条件是 `i` 小于数组的元素个数。`unique_ptr<T[]>` 不知道数组有多长，标准层面无法检查。

!!! impl "libc++ 借助数组 cookie 做边界检查"
    Itanium C++ ABI 规定，`T` 有非平凡析构函数时，`new T[n]` 在数组前面存放元素个数，叫做数组 cookie，供 `delete[]` 使用。libc++ 在加固模式（`fast` 及以上）下，如果使用默认删除器并且存在 cookie，就读取它来检查 `operator[]` 的下标。本机验证：`make_unique<std::string[]>(3)` 之后访问下标 3，在 `fast` 模式下程序陷入并终止；`make_unique<int[]>(3)` 之后访问下标 3 则不会被发现，因为 `int` 的析构是平凡的，没有 cookie。libc++ 另有一个额外存储长度、改变布局的 ABI 配置 `_LIBCPP_ABI_BOUNDED_UNIQUE_PTR`，默认不启用。

## 创建函数 [unique.ptr.create]

| 调用 | 适用的 `T` | 返回 |
|---|---|---|
| ¶1–¶2 `make_unique<T>(args...)` | 不是数组 | `unique_ptr<T>(new T(std::forward<Args>(args)...))` |
| ¶3–¶4 `make_unique<T[]>(n)` | 未知边界数组 | `unique_ptr<T>(new remove_extent_t<T>[n]())`，值初始化 |
| ¶5 `make_unique<T[N]>(...)` | 已知边界数组 | 弃置 |
| ¶6–¶7 `make_unique_for_overwrite<T>()` | 不是数组 | `unique_ptr<T>(new T)`，默认初始化 |
| ¶8–¶9 `make_unique_for_overwrite<T[]>(n)` | 未知边界数组 | `unique_ptr<T>(new remove_extent_t<T>[n])` |
| ¶10 `make_unique_for_overwrite<T[N]>(...)` | 已知边界数组 | 弃置 |

`make_unique` 用圆括号 `new T(args...)`。C++20 起圆括号也能初始化聚合（[[dcl.init]]），但它不会选择 `initializer_list` 构造函数：`make_unique<vector<int>>(3, 1)` 得到三个 1，不是 `{3, 1}`。

`make_unique<T[]>(n)` 里的 `()` 表示值初始化，`make_unique<double[]>(1'000'000)` 会把一百万个 `double` 清零。如果马上就要覆盖它们，这一步是浪费，所以 C++20 加了 `make_unique_for_overwrite`（[[P1020R1]]）。它做默认初始化，平凡类型的元素具有不确定值。C++26 把未初始化的自动变量改成了错误值，但动态分配的对象仍然是不确定值（[[basic.indet]]）。

`make_unique` 没有接受自定义删除器或分配器的版本。

C++14 时，推荐 `make_unique` 的一个理由是异常安全：`f(unique_ptr<T>(new T), g())` 可能先执行 `new T`，再执行抛出异常的 `g()`，导致泄漏。C++17 规定各个形参的初始化之间不交错（[[expr.call]]），这种泄漏不会再发生。今天用 `make_unique` 是为了不写 `new`，也不重复写类型名。

C++23 起，`unique_ptr` 的几乎所有操作和 `make_unique` 都是 `constexpr` 的（[[P2273R3]]）：

```cpp run ok
#include <memory>
constexpr int f() {
  auto p = std::make_unique<int>(20);
  auto q = std::make_unique<int[]>(3);   // 值初始化：全是 0
  q[1] = 22;
  return *p + q[0] + q[1];
}
static_assert(f() == 42);
int main() {}
```

## 比较、散列与输出

[unique.ptr.special] ¶1–¶2 `swap(x, y)` 要求 `is_swappable_v<D>`，效果是 `x.swap(y)`。

¶3 `==` 比较 `get()`。¶4–¶7 `<` 用 `less<CT>` 比较，`CT` 是两种 `pointer` 的公共类型。普通指针的 `<` 比较不相关的对象时结果未指定，而 `std::less` 对指针总是给出一个实现定义的严格全序（[[comparisons.general]]），所以 `unique_ptr` 之间的比较总有全序。¶11 `<=>` 用 `compare_three_way`，同样是全序。¶12–¶18 定义了与 `nullptr` 的各种比较。

`hash<unique_ptr<T, D>>`（[[util.smartptr.hash#1]]）只在 `hash<pointer>` 启用时启用，值等于 `hash<pointer>()(p.get())`。

[unique.ptr.io] `os << p` 要求 `os << p.get()` 合法，效果就是输出 `p.get()`。

## ABI：按值传递 `unique_ptr` 不是免费的

`sizeof(unique_ptr<T>) == sizeof(T*)`，但在 Itanium C++ ABI（Linux、macOS）下，有非平凡析构函数或非平凡复制、移动构造函数的类型不能通过寄存器传递。调用方在栈上构造一个临时对象，把它的地址传过去；被调函数返回后，调用方还要析构这个已经被移空的临时对象。所以调用 `void sink(std::unique_ptr<T> p)` 比调用 `void sink(T* p)` 多一次内存写、一次内存读和一次析构检查。

libc++ 有一个 ABI 配置 `_LIBCPP_ABI_ENABLE_UNIQUE_PTR_TRIVIAL_ABI`，给 `unique_ptr` 加上 Clang 的 `[[clang::trivial_abi]]` 属性，让它可以通过寄存器传递。这个配置在 libc++ 的 ABI 版本 2 中默认开启，但主流平台为了二进制兼容使用的是 ABI 版本 1，没有开启。

## 思考题

!!! question "思考题 1"
    为什么 `unique_ptr<T>` 允许 `T` 不完整，而 `unique_ptr<T[]>` 要求 `T` 完整？

<details markdown="1">
<summary>答案</summary>

单对象版本的类定义不需要知道 `sizeof(T)`，它只存储一个 `T*`；需要完整类型的是析构，由 `default_delete::operator()` 的 *Mandates* 把关。数组版本的转换规则要判断 `V(*)[]` 能否转换为 `T(*)[]`，`operator[]` 也要做指针算术，这些都需要 `T` 完整，所以 [unique.ptr.runtime.general] ¶3 把它作为整体要求。
</details>

!!! question "思考题 2"
    `std::unique_ptr<FILE, int(*)(FILE*)> f(std::fopen("x", "r"), &std::fclose);` 有什么问题？

<details markdown="1">
<summary>答案</summary>

至少有三个。第一，`unique_ptr` 变成两个指针大，通过函数指针调用也不容易内联。第二，除了少数明确标为可取地址的函数，取标准库函数的地址，行为是未指定的，甚至可能非良构（[[namespace.std]]）。第三，`fclose` 的返回值被丢弃，写入缓冲区失败的错误就被吞掉了。`fopen` 失败返回空指针倒没有问题，析构函数不会以空指针调用删除器。更好的写法是一个无状态的函数对象：`struct fcloser { void operator()(FILE* f) const noexcept { std::fclose(f); } };`。
</details>

!!! question "思考题 3"
    `std::unique_ptr<int, void(*)(int*)> p;` 为什么不能编译？

<details markdown="1">
<summary>答案</summary>

[unique.ptr.single.ctor] ¶1 要求 `is_pointer_v<deleter_type>` 为假。函数指针删除器值初始化之后是空指针，之后如果 `reset(new int)` 再析构，就会调用空函数指针。标准选择在编译期排除这种构造。
</details>
