---
title: shared_ptr
summary: shared_ptr 的完整契约：从裸指针、删除器、别名、weak_ptr 和 unique_ptr 构造；赋值与 reset 的统一定义；观察器；make_shared 家族的初始化与销毁；比较与四个指针转换函数。
status: done
covers: *
related: util.sharedptr, util.smartptr.weak, util.smartptr.enab, util.smartptr.ownerless, unique.ptr, allocator.traits, expr.delete, expr.static.cast, expr.dynamic.cast
tags: 标准库, 智能指针, shared_ptr, make_shared, 别名构造
papers: P0674R1, P1020R1, P3037R6
updated: 2026-10-19
---

!!! tldr
    - `shared_ptr` 存一个存储指针，同时拥有一个对象；两者可以不同（别名构造）。不拥有任何东西的 `shared_ptr` 叫空的，与 `get() == nullptr` 是两回事。
    - 从裸指针构造时，删除器按实参的静态类型记住，所以 `shared_ptr<Base>(new Derived)` 即使析构函数不是虚的也能正确销毁。
    - 每次从裸指针构造都会新建一个所有权组。同一个裸指针交给两个 `shared_ptr`，或者写 `shared_ptr<T>(static_cast<T*>(r.get()))`，都会删除两次。
    - 赋值和 `reset` 都定义为构造一个临时对象再 `swap`。
    - `make_shared` 用圆括号初始化对象，只分配一次内存；数组元素按地址升序构造、逆序销毁。

一个 `shared_ptr` 在实现上是两个指针：一个指向对象，一个指向堆上的控制块（存放引用计数、删除器和分配器）。这个物理模型和线程安全规则见 [[util.sharedptr]]。最新草案中 `shared_ptr` 的绝大多数成员都是 `constexpr`（C++26，[[P3037R6]]），本机 libc++ 尚未实现这一点。

## 存储指针与所有权 [util.smartptr.shared.general]

¶1 `shared_ptr` 存储一个指针，通常来自 `new`，并实现共享所有权：一组 `shared_ptr` 共同拥有一个对象，最后一个所有者负责销毁对象或释放相关资源。不拥有任何指针的 `shared_ptr` 叫做**空的**（empty，[[g:empty-shared-ptr]]）。

存储指针（`get()` 的返回值）和被拥有的指针通常相同，但标准允许两者分离，下文的别名构造就是例子。所以空不等于 `get() == nullptr`：空的 `shared_ptr` 可以存一个非空指针，非空的 `shared_ptr` 也可以拥有一个空指针。

成员类型 `element_type` 是 `remove_extent_t<T>`，例如 `shared_ptr<int[]>` 的 `element_type` 是 `int`。

¶2 `shared_ptr` 满足 *Cpp17CopyConstructible*、*Cpp17CopyAssignable* 和 *Cpp17LessThanComparable*，可以放进标准容器，也可以按语境转换为 `bool`。¶3 `T` 可以是不完整类型，注 1 指出甚至可以是函数类型。

¶5 判断数据竞争时，成员函数只访问 `shared_ptr` 和 `weak_ptr` 对象本身，不访问它们指向的对象，详见 [[util.sharedptr]]。

¶6 本节多处约束用到**兼容**（compatible，[[g:compatible-pointer-type]]）：如果 `Y*` 可以转换为 `T*`，或者 `Y` 是 `U[N]` 而 `T` 是 cv `U[]`，就说 `Y*` 与 `T*` 兼容。后半句让 `shared_ptr<int[5]>` 可以转换为 `shared_ptr<int[]>`，尽管 `int(*)[5]` 不能隐式转换为 `int(*)[]`。

## 从裸指针构造 [util.smartptr.shared.const]

### 删除器按 Y 记住（¶2–¶8）

```cpp run title="type-erasure.cpp" ok
#include <memory>
#include <string>
#include <cassert>
struct Base { ~Base() {} };                      // 析构函数不是虚的
struct Derived : Base { std::string s = std::string(100, 'x'); };
int main() {
    std::shared_ptr<Base> p(new Derived);        // 删除器执行 delete (Derived*)
    std::shared_ptr<void> v = std::make_shared<Derived>();
    std::shared_ptr<Base> q = std::make_shared<Derived>();
    std::shared_ptr<Derived> d = std::static_pointer_cast<Derived>(q);
    assert(q.use_count() == 2);
}                                                // 全部正确析构
```

本机用 ASan 运行没有任何报告。`Base` 的析构函数不是虚的，`p` 却正确销毁了 `Derived` 及其中的字符串。

原因在构造函数的签名：`template<class Y> explicit shared_ptr(Y* p)`。构造函数记住的是实参的类型 `Y`，而不是 `T`，控制块里的删除器执行的是 `delete p`，其中 `p` 的类型是 `Y*`。这一点与 `unique_ptr<Base>` 不同，后者总是 `delete` 一个 `Base*`（[[unique.ptr]]）。前提是构造时就知道 `Derived`：`Base* b = new Derived; shared_ptr<Base> p(b);` 记住的是 `Base`，照样是 UB。

¶2 默认构造得到空的 `shared_ptr`，`use_count() == 0 && get() == nullptr`。从 `Y* p` 构造时：

- ¶3 *Constraints*：`T` 不是数组时，`delete p` 良构且 `Y*` 可转换为 `T*`；`T` 是数组时，`delete[] p` 良构且数组指针类型匹配。
- ¶4 *Mandates*：`Y` 是完整类型。
- ¶5 *Preconditions*：相应的 `delete` 或 `delete[]` 有良定义的行为，且不抛出异常。
- ¶6 效果：拥有 `p`；`T` 是数组时配一个执行 `delete[] p` 的删除器。如果构造中抛出异常（例如分配控制块失败），会先 `delete p` 再传播异常，所以 `shared_ptr<X>(new X)` 不会泄漏。
- ¶7 后置条件 `use_count() == 1 && get() == p`；¶8 可能抛出 `bad_alloc`。

!!! ub "同一个裸指针交给两个 shared_ptr"
    ```cpp run title="double-owner.cpp" ub
    #include <memory>
    int main() {
        int* raw = new int(42);
        std::shared_ptr<int> a(raw);
        std::shared_ptr<int> b(raw);   // 第二个所有权组
    }                                  // UB：raw 被 delete 两次
    ```

    每次从裸指针构造都会新建一个控制块。`a` 和 `b` 各自以为自己是唯一所有者，最终各 `delete` 一次。本机 ASan 报告 `attempting double-free`。形式上违反的是 ¶5：第二次构造时，`delete raw` 并没有良定义的行为，因为 `raw` 会被另一组删除。对象需要从内部再取得一个 `shared_ptr` 时，应使用 [[util.smartptr.enab]]。

### 带删除器和分配器（¶9–¶13）

```cpp
shared_ptr(Y* p, D d);           shared_ptr(Y* p, D d, A a);
shared_ptr(nullptr_t p, D d);    shared_ptr(nullptr_t p, D d, A a);
```

¶9 要求 `D` 可移动构造，且 `d(p)` 良构。¶10 要求复制或移动 `d` 不抛出，`d(p)` 有良定义的行为且不抛出，`A` 满足 *Cpp17Allocator*。¶11 带分配器的版本用 `a` 的副本给控制块分配内存；构造中抛出异常时会调用 `d(p)`。

删除器会对存储的指针调用，即使这个指针是空的：

```cpp run title="null-with-deleter.cpp" ok
#include <memory>
#include <cstdio>
int main() {
    std::shared_ptr<int> p(nullptr, [](int* q) {
        std::printf("deleter(%p)\n", (void*)q);
    });
    std::printf("use_count=%ld bool=%d\n", p.use_count(), bool(p));
}
```

本机输出 `use_count=1 bool=0`，随后打印 `deleter(0x0)`。`p` 拥有一个空指针和一个删除器，所以不是空的，析构时按 [util.smartptr.shared.dest] ¶1.2 调用删除器。`unique_ptr` 则只在指针非空时调用删除器。所以给 `shared_ptr` 写删除器时要自己处理空指针，比如 `fclose(nullptr)` 在 C 中是 UB。

### 别名构造（¶14–¶17）

```cpp run title="aliasing.cpp" ok
#include <memory>
#include <cassert>
#include <string>
struct Person { std::string name; int age; };
int main() {
    auto p = std::make_shared<Person>("Ada", 36);
    std::shared_ptr<int> age(p, &p->age);   // 拥有 Person，指向成员
    assert(p.use_count() == 2 && *age == 36);
    p.reset();
    assert(*age == 36 && age.use_count() == 1);   // Person 仍然存活
    std::shared_ptr<int> e(std::shared_ptr<int>(), age.get());
    assert(e && e.use_count() == 0);         // 空，但存储指针非空
}
```

¶14 `shared_ptr(const shared_ptr<Y>& r, element_type* p)` 构造一个存储 `p`、与 `r` 共享所有权的 `shared_ptr`。¶15 C++20 增加的右值版本会把 `r` 置空，省去一次引用计数的增减。

典型用途是把指向成员、数组元素或其他子对象的指针交出去，同时保证外层对象不会先被销毁。下文的四个指针转换函数也都是用别名构造实现的。

¶16 注 1 提醒，别名构造不检查 `p` 与 `r` 的关系，如果 `p` 比 `r` 的所有权组活得短，就会产生悬空指针。¶17 注 2 指出，`r` 为空时得到的是一个空的、但存储指针非空的 `shared_ptr`，如上例中的 `e`：它不拥有任何东西，`operator bool` 却为真。

### 复制、移动和其他来源（¶18–¶29）

¶18–¶20 复制构造之后 `get() == r.get()`，`use_count() == r.use_count()`；¶21–¶23 移动构造之后 `*this` 得到 `r` 原来的值，`r` 变空且 `r.get() == nullptr`。模板版本都要求 `Y*` 与 `T*` 兼容。

¶24–¶27 `explicit shared_ptr(const weak_ptr<Y>& r)` 与 `r` 共享所有权并复制它的存储指针。`r.expired()` 时抛出 `bad_weak_ptr`，与 `r.lock()` 的区别只在于失败的方式（[[util.smartptr.weak]]）。

¶28–¶29 `shared_ptr(unique_ptr<Y, D>&& r)`：`r.get()` 为空时等价于默认构造；否则等价于 `shared_ptr(r.release(), std::move(r.get_deleter()))`，`D` 是引用类型时改用 `ref(r.get_deleter())`。抛出异常时没有效果，`r` 仍然拥有对象。

类模板实参推导只能从 `weak_ptr` 和 `unique_ptr` 推导，没有从裸指针推导的推导指引，因为 `shared_ptr p(new int[3])` 无法区分 `new T` 和 `new T[]`。

### 启用 shared_from_this（¶1）

¶1 定义了**以 `p` 启用 shared_from_this**（[[g:enables-shared-from-this]]）：如果 `Y` 有一个无歧义且可访问的基类是 `enable_shared_from_this` 的特化，构造函数就执行

```cpp
if (p != nullptr && p->weak-this.expired())
  p->weak-this = shared_ptr<remove_cv_t<Y>>(*this, const_cast<remove_cv_t<Y>*>(p));
```

其中 *weak-this* 是基类里一个说明用的 `weak_ptr` 成员。只有从 `Y*` 构造（含带删除器的两个版本，`T` 不是数组时）和 `make_shared`/`allocate_shared` 会做这一步；别名构造、复制和从 `weak_ptr` 构造不会，因为它们没有创建新的所有权组。¶1 最后一句指出，这次赋值不是原子的。细节和陷阱见 [[util.smartptr.enab]]。

## 析构、赋值与 reset [util.smartptr.shared.dest] [util.smartptr.shared.assign] [util.smartptr.shared.mod]

析构函数（[util.smartptr.shared.dest] ¶1）在 `*this` 为空或 `use_count() > 1` 时没有副作用；否则，有删除器 `d` 就调用 `d(p)`，没有就 `delete p`。

所有赋值运算符都定义为构造一个临时对象再交换：`operator=(r)` 等价于 `shared_ptr(r).swap(*this)`。`reset()`、`reset(p)`、`reset(p, d)`、`reset(p, d, a)` 也一样。这个定义同时说明了三件事：

- 自赋值是安全的；
- 构造临时对象时抛出异常，`*this` 不变；
- 旧对象在临时对象析构时才被释放，也就是这条语句结束时。

[util.smartptr.shared.assign] ¶3 注 1 补充，临时对象引起的计数变化不是可观察副作用，实现不必真的创建临时对象，`p = p;` 这类赋值可以什么都不做。

同样的定义也说明 `sp.reset(sp.get())` 是错的：`shared_ptr(sp.get())` 新建了第二个所有权组，结果是双重删除。

## 观察器 [util.smartptr.shared.obs]

- ¶1 `get()` 返回存储指针。¶18 `operator bool` 返回 `get() != nullptr`，它不表示是否拥有对象。
- ¶2–¶7 `operator*` 和 `operator->` 的前置条件是 `get() != nullptr`。`T` 是数组或 cv `void` 时，是否声明它们是未指定的，但如果声明了，声明本身必须良构。这让实现可以无条件地声明它们，`shared_ptr<void>` 仍然可以实例化。
- ¶8–¶12 `operator[](ptrdiff_t i)` 只对数组 `T` 有意义，前置条件是 `get() != nullptr`。¶9 还有两条加固前置条件（hardened precondition）：`i >= 0`；`T` 是 `U[N]` 时 `i < N`。在加固实现中违反它们会以终止型语义报告契约违反（[[intro.compliance]]）。`T` 是 `U[]` 时上界未知，只能检查非负。本机 libc++ 即使开启 `_LIBCPP_HARDENING_MODE_DEBUG` 也还没有检查这两条。
- ¶13–¶17 `use_count()` 返回共享所有权的 `shared_ptr` 个数，为空时返回 0，没有同步语义。注 3 指出，多线程下这只是一个近似值，`use_count() == 1` 并不意味着别的线程对对象的访问已经结束。

¶19–¶22 `owner_before`、`owner_hash`、`owner_equal` 按所有权而不是存储指针比较：别名构造出的 `shared_ptr` 与原对象 `owner_equal`，但 `==` 不成立。它们是 `weak_ptr` 能做容器键的基础，见 [[util.smartptr.ownerless]]。其中 `owner_before` 和 `owner_hash` 不是 `constexpr`，它们依赖控制块地址的数值。

## make_shared 家族 [util.smartptr.shared.create]

```cpp run title="make-shared.cpp" ok
#include <memory>
#include <vector>
#include <cassert>
int main() {
    auto v = std::make_shared<std::vector<int>>(3, 1);
    assert(v->size() == 3);                  // 圆括号：三个 1
    auto a = std::make_shared<double[][2]>(6, {1.0, 0.0});
    assert(a[5][0] == 1.0);                  // 每个 double[2] 都是 {1, 0}
    auto b = std::make_shared<int[]>(4);
    assert(b[3] == 0);                       // 值初始化
}
```

`make_shared`、`allocate_shared`、`make_shared_for_overwrite`、`allocate_shared_for_overwrite` 共用 ¶1–¶7 的规则：

- ¶3 为对象分配内存（`T` 是 `U[]` 时为 `U[N]`）。带分配器的版本用 `a` 的副本，并重绑定到一个未指定的 `value_type`，实际上就是控制块的类型。抛出异常时没有效果。
- ¶4 返回值 `r` 满足 `r.get() != nullptr && r.use_count() == 1`。
- ¶7.1 实现应当只分配一次内存，把对象和控制块放在一起（代价见 [[util.sharedptr]]）。
- ¶7.4 `make_shared` 用 `::new(pv) U(args...)` 初始化，是圆括号而不是花括号，所以 `make_shared<vector<int>>(3, 1)` 得到三个 1。
- ¶7.5 `allocate_shared` 用 `allocator_traits<A2>::construct(a2, pu, args...)`，其中 `a2` 是重绑定到 `remove_cv_t<U>` 的分配器副本（[[LWG3216]]）。所以 `polymorphic_allocator` 的 uses-allocator 构造能作用到对象上（[[allocator.uses]]）。
- ¶7.8 `_for_overwrite` 版本用 `::new(pv) U`，即默认初始化，适合随后就要整体覆盖的大缓冲区。
- ¶7.9、¶7.10 数组元素按地址升序初始化，逆序销毁；某个元素初始化时抛出异常，已经构造的元素逆序销毁。
- ¶7.11、¶7.12 销毁方式与构造方式对应：`allocate_shared` 构造的对象用 `allocator_traits<A2>::destroy` 销毁，其他用 `pu->~U()`（[[LWG4024]]）。

标准把未给初值的情形说成对象具有默认初值（default initial value），¶7.6 规定它的含义是 `::new(pv) U()`，也就是值初始化。不要与 `_for_overwrite` 的默认初始化混淆。

| 调用 | `T` 的形式 | 初值 |
|---|---|---|
| `make_shared<T>(args...)`（¶8–¶11） | 非数组 | `T(std::forward<Args>(args)...)`，并启用 shared_from_this |
| `make_shared<T>(N)`（¶12–¶14） | `U[]` | `N` 个元素，值初始化 |
| `make_shared<T>()`（¶15–¶17） | `U[N]` | 值初始化 |
| `make_shared<T>(N, u)`（¶18–¶20） | `U[]` | 每个元素都是 `u` |
| `make_shared<T>(u)`（¶21–¶23） | `U[N]` | 每个元素都是 `u` |
| `make_shared_for_overwrite<T>()`（¶24–¶26） | 非数组或 `U[N]` | 默认初始化 |
| `make_shared_for_overwrite<T>(N)`（¶27–¶29） | `U[]` | 默认初始化 |

每一行都有对应的 `allocate_shared` 重载。¶7.2 规定，数组类型的初值 `u` 按元素对应解释，所以 `make_shared<double[][2]>(6, {1.0, 0.0})` 中每个 `double[2]` 都是 `{1.0, 0.0}`。数组形式来自 C++20 的 [[P0674R1]]，`_for_overwrite` 来自 [[P1020R1]]。

## 比较 [util.smartptr.shared.cmp]

¶1 `a == b` 比较 `a.get() == b.get()`，¶2 `a == nullptr` 等价于 `!a`。¶3 `a <=> b` 返回 `compare_three_way()(a.get(), b.get())`，类型是 `strong_ordering`。`compare_three_way` 对任意指针给出全序，即使两个指针指向不相关的对象，所以 `shared_ptr` 可以直接做 `std::set` 的键（¶4 注 1）。

比较的都是存储指针，不是所有权。要按所有权比较，用上文的 `owner_*`。

## 指针转换 [util.smartptr.shared.cast]

<div class="compare" markdown="1">

```cpp run ok
#include <memory>
struct B { virtual ~B() = default; };
struct D : B {};
int main() {
  std::shared_ptr<B> b(new D);
  auto d = std::static_pointer_cast<D>(b);
  // d 与 b 共享所有权
}
```

```cpp run ub
#include <memory>
struct B { virtual ~B() = default; };
struct D : B {};
int main() {
  std::shared_ptr<B> b(new D);
  std::shared_ptr<D> d(
      static_cast<D*>(b.get()));
  // UB: 第二个所有权组
}
```

</div>

右边的程序在本机 ASan 下报告 `heap-use-after-free`：`d` 析构时删除了对象，`b` 析构时又删除一次。

`static_pointer_cast`、`dynamic_pointer_cast`、`const_pointer_cast`、`reinterpret_pointer_cast` 都有 `const&` 和 `&&`（C++20）两个版本，返回值都是别名构造：

```cpp
shared_ptr<T>(R, static_cast<typename shared_ptr<T>::element_type*>(r.get()))
```

其中 `R` 是 `r` 或 `std::move(r)`。每个函数的 *Mandates* 是对应的内建转换良构（¶1、¶4、¶8、¶11）。每个函数后面的注都警告，看似等价的 `shared_ptr<T>(static_cast<T*>(r.get()))` 会让同一个对象被删除两次。

¶5–¶6 `dynamic_pointer_cast` 要求那次 `dynamic_cast` 本身有良定义的行为（[[expr.dynamic.cast]]）。`dynamic_cast` 返回空指针时，结果是默认构造的空 `shared_ptr`，此时右值版本不会移走 `r`。

`reinterpret_pointer_cast` 不是 `constexpr`，因为 `reinterpret_cast` 不能出现在常量求值中。

## get_deleter [util.smartptr.getdeleter]

¶1 `get_deleter<D>(p)`：如果 `p` 拥有一个 cv 无限定类型为 `D` 的删除器，返回它的地址，否则返回空指针。返回的指针至少在还有 `shared_ptr` 拥有这个删除器时有效；注 1 说明它是否更久有效是未指定的，因为实现可能等所有 `weak_ptr` 都销毁之后才销毁删除器。

libc++ 用 `typeid` 比较删除器的类型。本机用 `-fno-rtti` 编译时，libc++ 根本不声明 `std::get_deleter`，调用它会得到 `no member named 'get_deleter'` 错误。

<details class="fine" markdown="1"><summary>其余条文</summary>

[util.smartptr.shared.general] ¶4 例 1 演示在 `if` 条件中声明 `shared_ptr` 并用 `dynamic_pointer_cast` 初始化。

[util.smartptr.shared.dest] ¶2 注 1：一个 `shared_ptr` 析构之后，与它共享所有权的其他 `shared_ptr` 的 `use_count()` 都减一。

[util.smartptr.shared.mod] ¶1 与 [util.smartptr.shared.spec] ¶1：成员 `swap` 交换两个对象的内容，非成员 `swap(a, b)` 等价于 `a.swap(b)`。

[util.smartptr.shared.cmp] ¶5：`a <=> nullptr` 把 `a.get()` 与一个 `element_type*` 类型的空指针做三路比较。

[util.smartptr.shared.io] ¶1–¶2：`os << p` 等价于 `os << p.get()`，返回 `os`。

</details>

## 常见误解

!!! pitfall "`if (sp)` 判断的是是否拥有对象"
    `operator bool` 只看 `get()`。别名构造可以得到一个为真却不拥有任何东西的 `shared_ptr`，带删除器的空指针构造可以得到一个为假却拥有资源的 `shared_ptr`。判断是否拥有要用 `use_count() != 0`。

!!! pitfall "删除器只在指针非空时调用"
    这是 `unique_ptr` 的规则。`shared_ptr` 拥有的指针即使为空，析构时也会调用删除器。

## 思考题

!!! question "思考题 1"
    `std::shared_ptr<FILE> f(std::fopen(name, "r"), std::fclose);` 在 `fopen` 失败时有什么问题？

<details markdown="1">
<summary>答案</summary>

`fopen` 返回 `FILE*`，所以选中的是 `shared_ptr(Y* p, D d)`，不是 `nullptr_t` 版本。`p` 恰好是空指针，得到的 `shared_ptr` 拥有一个空指针，`use_count() == 1`。析构时按 [util.smartptr.shared.dest] ¶1.2 调用 `fclose(nullptr)`，这在 C 中是 UB。删除器应写成 `[](FILE* f) { if (f) std::fclose(f); }`。另外，取标准库函数 `std::fclose` 的地址本身也不受标准保证（[[namespace.std]]）。
</details>

!!! question "思考题 2"
    `dynamic_pointer_cast<D>(std::move(r))` 转换失败时，`r` 还拥有对象吗？

<details markdown="1">
<summary>答案</summary>

还拥有。按 ¶6.2，`dynamic_cast` 返回空指针时结果是 `shared_ptr<T>()`，根本没有执行以 `std::move(r)` 为实参的别名构造，`r` 没有被移走。本机验证 `assert(!e && r)` 成立。
</details>

## 小结

| 操作 | 要点 |
|---|---|
| `shared_ptr<T>(new Y)` | 删除器按 `Y` 记住；新建所有权组 |
| `shared_ptr<T>(p, d)` | 即使 `p` 为空，析构时也调用 `d(p)` |
| 别名构造 | 存储什么与拥有什么分离；可能空而非空指针 |
| 赋值、`reset` | 构造临时对象再 `swap` |
| `make_shared` | 一次分配；圆括号初始化；数组升序构造、逆序销毁 |
| `==`、`<=>` | 比较存储指针 |
| `*_pointer_cast` | 别名构造，与原对象共享所有权 |
