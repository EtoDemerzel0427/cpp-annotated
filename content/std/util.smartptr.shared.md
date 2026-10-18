---
title: shared_ptr
summary: shared_ptr 的逐段契约——"兼容"的指针类型、构造时捕获删除器、"启用 shared_from_this"、别名构造、从 weak_ptr/unique_ptr 构造；赋值等价于"构造临时再 swap"；operator[] 的加固前置条件；make_shared 家族的初始化与销毁规则；四种指针转换为什么不能用 shared_ptr<T>(static_cast<T*>(r.get()))
status: done
covers: *
related: util.sharedptr, util.smartptr.weak, util.smartptr.enab, util.smartptr.ownerless, unique.ptr, allocator.traits, expr.delete, expr.static.cast, expr.dynamic.cast
tags: 标准库, 智能指针, shared_ptr, make_shared, 别名构造
papers: P0674R1, P1020R1, P3037R6
updated: 2026-10-18
---

本页逐段解读 [util.smartptr.shared] 的全部子条款。物理模型（控制块、单次分配、线程安全）见 [[util.sharedptr]]，下文直接使用"控制块"一词。

最新草案中 `shared_ptr` 几乎所有成员都是 `constexpr`（C++26，[[P3037R6]]），例外是 `owner_before`、`owner_hash` 以及 `reinterpret_pointer_cast`——前两者的结果依赖控制块地址的顺序或散列，常量求值中无法给出（[[LWG4557]] 还移除了 `owner_less`/`owner_before` 上原有的 `constexpr`）。本机 libc++ 尚未实现 `constexpr shared_ptr`：在 `static_assert` 中调用 `make_shared` 报 "non-constexpr function 'make_shared<int, int, 0>' cannot be used in a constant expression"。

## 概述（[util.smartptr.shared.general]）

- ¶1：`shared_ptr` 存储一个指针（通常来自 `new`），实现**共享所有权**语义：最后一个所有者负责销毁对象或释放相关资源。不拥有指针的 `shared_ptr` 称为**空**（[[g:empty-shared-ptr]]）的。注意"空"指的是**不拥有**，而不是 `get() == nullptr`——两者可以独立变化（见别名构造）。
- `element_type` 是 `remove_extent_t<T>`：`shared_ptr<int[]>` 的 `element_type` 是 `int`。
- ¶2：满足 *Cpp17CopyConstructible*、*Cpp17CopyAssignable*、*Cpp17LessThanComparable*，可按语境转换为 `bool`。
- ¶3：`T` 可以是不完整类型；注 1：`T` 甚至可以是函数类型（例如持有一个由 `dlopen` 得到的函数指针，删除器负责 `dlclose`）。
- ¶5：数据竞争规则，见 [[util.sharedptr]]。
- ¶6：**兼容**（[[g:compatible-pointer-type]]）的定义——`Y*` 与 `T*` 兼容，当 `Y*` 可转换为 `T*`，**或** `Y` 是 `U[N]` 而 `T` 是 cv `U[]`。后半句让 `shared_ptr<int[5]>` 可以转换为 `shared_ptr<int[]>`（`int(*)[5]` 本来不能转换为 `int(*)[]`）。复制、移动、从 `weak_ptr` 构造等都以"兼容"为约束。

## 构造函数（[util.smartptr.shared.const]）

### ¶1："启用 shared_from_this"

（[[g:enables-shared-from-this]]）

若 `Y` 有一个**无歧义且可访问**的基类是 `enable_shared_from_this` 的特化，"以 `p` 启用 shared_from_this"意味着构造函数执行：

```cpp
if (p != nullptr && p->weak-this.expired())
  p->weak-this = shared_ptr<remove_cv_t<Y>>(*this, const_cast<remove_cv_t<Y>*>(p));
```

两个细节：

- **`expired()` 检查**：只有第一个拥有该对象的 `shared_ptr` 会设置 `weak-this`。用同一个裸指针再构造第二个 `shared_ptr`（这本身就是 UB，见下）时不会覆盖。
- ¶1 末句：对 `weak-this` 的赋值**不是原子的**，与对同一对象的任何潜在并发访问冲突。在一个线程里构造 `shared_ptr<X>(p)` 的同时另一个线程对 `*p` 调用 `weak_from_this()` 是数据竞争。

基类必须**可访问**：`struct X : private enable_shared_from_this<X>` 时检测不到，`shared_from_this()` 永远抛 `bad_weak_ptr`。这是常见的坑——`class` 默认私有继承。

### 从裸指针构造（¶2–¶8）

- ¶2：默认构造：`use_count() == 0 && get() == nullptr`。
- `template<class Y> explicit shared_ptr(Y* p)`：
  - ¶3 *Constraints*：`T` 为数组时 `delete[] p` 良构且指针类型匹配；否则 `delete p` 良构且 `Y*` 可转换为 `T*`；
  - ¶4 *Mandates*：`Y` 是完整类型；
  - ¶5 *Preconditions*：相应的 `delete`/`delete[]` 有良定义行为且不抛出；
  - ¶6 效果：拥有 `p`（数组时配一个调用 `delete[] p` 的删除器）；非数组时启用 shared_from_this；**若抛出异常，调用 `delete p`**（或 `delete[] p`）；
  - ¶8 *Throws*：`bad_alloc`，或资源不足时的由实现定义的异常。

关键在于**模板参数 `Y`**：构造函数记住的是 `Y`，不是 `T`。控制块里存的删除器执行的是 `delete (Y*)p`。所以 `shared_ptr<Base> p(new Derived)` 即使 `Base` 析构函数非虚也能正确销毁——这与 `unique_ptr` 截然不同（[[unique.ptr]]）。

```cpp title="shared-ptr-type-erasure.cpp" ok
#include <memory>
#include <string>
#include <cassert>
struct Base { ~Base() {} };                      // 非虚析构函数
struct Derived : Base { std::string s = std::string(100, 'x'); };
int main() {
    std::shared_ptr<Base> p(new Derived);        // 删除器按 Derived* 捕获：delete (Derived*)p
    std::shared_ptr<void> v = std::make_shared<Derived>();   // 连 void 都可以
    std::shared_ptr<Base> q = std::make_shared<Derived>();
    std::shared_ptr<Derived> d = std::static_pointer_cast<Derived>(q);   // 共享所有权
    assert(q.use_count() == 2);
}                                                // 全部正确析构，ASan/LSan 无报告
```

但这只在**构造时就知道 `Derived`** 时成立。`Base* b = new Derived; shared_ptr<Base> p(b);` 捕获的是 `Base`，照样是 UB。

!!! ub "同一个裸指针交给两个 shared_ptr"
    每次从裸指针构造都会新建一个控制块。两个控制块各自以为自己是唯一所有者，最终 `delete` 两次：

    ```cpp title="double-control-block.cpp" ub
    #include <memory>
    int main() {
        int* raw = new int(42);
        std::shared_ptr<int> a(raw);
        std::shared_ptr<int> b(raw);   // 第二个控制块
    }                                  // UB：raw 被 delete 两次
    ```

    本机 ASan 报告 "attempting double-free"。形式上，违反的是 ¶5 的前置条件：第二个构造函数要求 `delete p` 有良定义行为——而 `p` 会被第一个所有组删除。`enable_shared_from_this` 的存在就是为了让对象能安全地"再要一个"共享同一控制块的 `shared_ptr`。

### 带删除器与分配器（¶9–¶13）

`shared_ptr(p, d)`、`shared_ptr(p, d, a)`、以及 `nullptr_t` 版本：

- ¶9 *Constraints*：`D` 可移动构造，`d(p)` 良构；
- ¶10 *Preconditions*：`d` 的构造与移动不抛出；`d(p)` 有良定义行为、不抛出；`A` 满足 *Cpp17Allocator*；
- ¶11：带分配器的版本用 `a` 的副本为内部使用（控制块）分配内存；**若抛出异常，调用 `d(p)`**；
- `nullptr_t` 版本拥有一个**空指针**和删除器：`use_count() == 1` 而 `get() == nullptr`——"非空但存储空指针"。删除器仍会在最后以 `nullptr` 被调用！这一点与 `unique_ptr` 不同（后者从不以空指针调用删除器），对 `fclose` 之类的删除器要小心。

注意 `nullptr_t` 版本和 `T` 为数组时都**不**启用 shared_from_this（¶11 只对前两个构造函数且 `T` 非数组时启用）。

### 别名构造（¶14–¶17）

```cpp
template<class Y> shared_ptr(const shared_ptr<Y>& r, element_type* p) noexcept;
template<class Y> shared_ptr(shared_ptr<Y>&& r, element_type* p) noexcept;   // C++20
```

¶14：构造一个**存储 `p`**、与 `r` 的初始值**共享所有权**的 `shared_ptr`。存储指针和被拥有的对象在这里彻底分离：

```cpp title="aliasing-ctor.cpp" ok
#include <memory>
#include <cassert>
#include <string>
struct Person { std::string name; int age; };
int main() {
    auto p = std::make_shared<Person>("Ada", 36);
    std::shared_ptr<int> age(p, &p->age);       // 别名构造：共享 p 的所有权，指向成员
    assert(p.use_count() == 2 && *age == 36);
    p.reset();                                   // Person 仍然活着：age 持有它
    assert(*age == 36 && age.use_count() == 1);
    std::shared_ptr<int> empty_but_nonnull(std::shared_ptr<int>(), age.get());
    assert(empty_but_nonnull.get() != nullptr && empty_but_nonnull.use_count() == 0);
}
```

典型用途：把指向成员（或数组元素、或某个由父对象管理的子对象）的指针暴露出去，同时保证父对象不会先死。`static_pointer_cast` 等转换函数也都是用别名构造实现的。

- ¶16 注 1：除非 `p` 至少在 `r` 的所有权组销毁之前一直有效，否则会产生悬空指针——别名构造**不检查** `p` 与 `r` 有什么关系。
- ¶17 注 2：它允许创建"空但存储指针非空"的 `shared_ptr`（`r` 为空时）。这样的对象 `operator bool` 为真、`use_count()` 为 0，不拥有任何东西，类似一个带了 `shared_ptr` 接口的裸指针。
- ¶15：右值版本把 `r` 置空，省去一次引用计数的增减。

### 复制、移动（¶18–¶23）

复制：`get() == r.get() && use_count() == r.use_count()`；移动：`*this` 获得 `r` 的旧值，`r` 变空且 `r.get() == nullptr`。约束都是 `Y*` 与 `T*` **兼容**。

### 从 `weak_ptr` 构造（¶24–¶27）

`explicit shared_ptr(const weak_ptr<Y>& r)`：共享 `r` 的所有权并复制其存储指针；**`r.expired()` 时抛 `bad_weak_ptr`**；抛出时无效果。与 `r.lock()` 的区别只在失败方式。它必须是原子的"检查并递增"——强计数一旦为 0 就不能"复活"对象，实现通常是对强计数的比较-交换循环。

### 从 `unique_ptr` 构造（¶28–¶29）

`r.get() == nullptr` 时等价于默认构造；否则 `D` 非引用时等价于 `shared_ptr(r.release(), std::move(r.get_deleter()))`，`D` 为引用时等价于 `shared_ptr(r.release(), ref(r.get_deleter()))`。抛出时无效果（`r` 仍然拥有对象）。有推导指引 `shared_ptr(unique_ptr<T, D>) -> shared_ptr<T>`，以及从 `weak_ptr` 的推导指引；**没有**从裸指针的推导指引（无法区分 `new T` 与 `new T[]`）。

## 析构与赋值（[util.smartptr.shared.dest]、[util.smartptr.shared.assign]）

析构（¶1）：空或 `use_count() > 1` 时无副作用；否则若拥有删除器 `d` 则调用 `d(p)`，否则 `delete p`。

赋值统一定义为"**构造临时对象再 swap**"：`operator=(r)` 等价于 `shared_ptr(r).swap(*this)`。这个写法自动处理了自赋值、异常安全（构造临时对象可能抛异常时 `*this` 不变），以及**旧对象的析构时机**：旧值在临时对象析构时（赋值语句末尾）才被释放。

¶3 注 1 明确允许实现**不**真的创建临时对象：引用计数的变化不是可观察副作用，`p = p;` 和 `q = p;`（`q` 已与 `p` 共享）都可以是空操作。

`reset()`、`reset(p)`、`reset(p, d)`、`reset(p, d, a)`（[util.smartptr.shared.mod]）同样定义为构造临时对象再 swap。所以 `sp.reset(sp.get())` 会创建第二个控制块——双重删除。

## 观察器（[util.smartptr.shared.obs]）

- `get()`：存储指针。
- `operator*`、`operator->`：*Preconditions* `get() != nullptr`；`T` 为数组或 cv `void` 时是否声明未指明（声明了也必须良构）——这让实现可以无条件声明它们，而 `shared_ptr<void>` 仍可实例化。
- `operator[](ptrdiff_t i)`（¶8–¶12）：仅数组 `T` 时有意义。*Preconditions* `get() != nullptr`；***Hardened preconditions***：`i >= 0`，若 `T` 是 `U[N]` 则 `i < N`。这是本章少数的 C++26 加固前置条件之一（来自 C++26 的标准库加固工作）：加固实现必须在执行前以终止语义检查它们。对 `T` 为 `U[]` 的情形，上界无从知道，只检查非负。
- `use_count()`（¶13–¶17）：*Synchronization*：无。空时返回 0。注 1：`get() == nullptr` 不意味着特定的 `use_count()` 值；注 2：`weak_ptr::lock()` 会影响它；注 3：多线程下只是近似值。
- `operator bool`：`get() != nullptr`——**不是**"是否拥有"。

### 基于所有权的比较（¶19–¶22）

- `owner_before(b)`（¶19）：返回一个未指明的值，构成严格弱序，并且 `!a.owner_before(b) && !b.owner_before(a)` 当且仅当 `a.owner_equal(b)`。实现上比较控制块地址。
- `owner_hash()`（¶20）{{c++26}}：与 `owner_equal` 一致的散列。
- `owner_equal(b)`（¶21–¶22）{{c++26}}：当且仅当二者共享所有权或都为空时为真；是等价关系。

这三者忽略存储指针：别名构造出的 `shared_ptr` 与原对象 `owner_equal`，但 `==` 不成立。它们是 `weak_ptr` 作为关联容器键的基础，详见 [[util.smartptr.ownerless]]。

## 创建（[util.smartptr.shared.create]）

### 公共规则（¶1–¶7）

适用于 `make_shared`、`allocate_shared`、`make_shared_for_overwrite`、`allocate_shared_for_overwrite` 的全部重载：

- ¶2 *Preconditions*：`A` 满足 *Cpp17Allocator*。
- ¶3：为 `T`（`T` 为 `U[]` 时为 `U[N]`）分配内存；`allocate_shared` 用 `a` 的**重绑定**副本（`value_type` 未指明——实际是控制块类型）。抛异常时无效果。
- ¶4：返回值 `r` 满足 `r.get() != nullptr && r.use_count() == 1`。
- ¶7 *Remarks*：
  - (7.1) 实现**应当**最多执行一次内存分配（见 [[util.sharedptr]]）。
  - (7.4)/(7.6) `make_shared` 用 `::new(pv) U(args...)` / `::new(pv) U()` 初始化——**圆括号**，不是花括号，所以 `make_shared<vector<int>>(3, 1)` 是三个 1；
  - (7.5)/(7.7) `allocate_shared` 用 `allocator_traits<A2>::construct(a2, pu, ...)`，其中 `a2` 是重绑定到 `remove_cv_t<U>` 的分配器副本——于是 `polymorphic_allocator` 的 uses-allocator 构造（[[allocator.uses]]）能作用到对象上。"先重绑定再 construct" 是 [[LWG3216]] 的修正；
  - (7.8) `*_for_overwrite` 用 `::new(pv) U`——默认初始化；
  - (7.9)/(7.10) 数组元素按地址**升序**初始化，**逆序**销毁；某个元素初始化抛异常时已初始化的元素逆序销毁；
  - (7.11) 由 `make_shared`、`make_shared_for_overwrite`、`allocate_shared_for_overwrite` 初始化的对象用 `pu->~U()` 销毁；(7.12) 由 `allocate_shared` 初始化的用 `allocator_traits<A2>::destroy(a2, pu)` 销毁（[[LWG4024]] 补上了 `_for_overwrite` 的情形）。

### 各重载

| 调用 | `T` 的形态 | 初始值 |
|---|---|---|
| `make_shared<T>(args...)`（¶8–¶11） | 非数组 | `T(std::forward<Args>(args)...)`，并启用 shared_from_this（¶10） |
| `make_shared<T>(N)`（¶12–¶14） | `U[]` | `N` 个元素，默认初始值（即值初始化） |
| `make_shared<T>()`（¶15–¶17） | `U[N]` | 默认初始值 |
| `make_shared<T>(N, u)`（¶18–¶20） | `U[]` | 每个元素为 `u` |
| `make_shared<T>(u)`（¶21–¶23） | `U[N]` | 每个元素为 `u` |
| `make_shared_for_overwrite<T>()`（¶24–¶26） | 非 `U[]`（含 `U[N]`） | 默认初始化 |
| `make_shared_for_overwrite<T>(N)`（¶27–¶29） | `U[]` | 默认初始化 |

数组支持来自 C++20 的 [[P0674R1]]，`_for_overwrite` 来自 [[P1020R1]]（原名 `make_shared_default_init`）。¶7.2 的"初始值为 `u` 的数组"按元素解释，所以 `make_shared<double[][2]>(6, {1.0, 0.0})` 让每个 `double[2]` 都是 `{1.0, 0.0}`。注意这里的"默认初始值"是标准的特别用语，对非数组 `U` 意味着 `::new(pv) U()`——**值**初始化，不要与"默认初始化"混淆。

## 比较（[util.smartptr.shared.cmp]）

- `a == b`：`a.get() == b.get()`；`a == nullptr`：`!a`。
- `<=>`：`compare_three_way()(a.get(), b.get())`，返回 `strong_ordering`。与裸指针的内建 `<` 不同，`compare_three_way` 对任意指针给出全序，所以 `shared_ptr` 可以直接做 `std::set` 的键（¶4 注）。
- 比较的是**存储指针**而非所有权。

## 类型转换（[util.smartptr.shared.cast]）

四个函数 `static_pointer_cast`、`dynamic_pointer_cast`、`const_pointer_cast`、`reinterpret_pointer_cast`，各有 `const&` 与 `&&`（C++20）版本，实现都是**别名构造**：

```cpp
shared_ptr<T>(R, static_cast<typename shared_ptr<T>::element_type*>(r.get()))
```

- *Mandates*：对应的 `static_cast<T*>((U*)nullptr)` 等良构。
- `dynamic_pointer_cast`：*Preconditions* `dynamic_cast` 本身有良定义行为（[[expr.dynamic.cast]] 在对象生命周期外等情形下是 UB）；`dynamic_cast` 返回空时返回**空** `shared_ptr`（不共享所有权）——对右值版本而言，`r` 此时**不被**移走。
- 每个函数的注都在警告：看似等价的 `shared_ptr<T>(static_cast<T*>(r.get()))` 会建立第二个控制块，导致**同一对象被删除两次**——就是上面"双重控制块"UB 的变体。

`reinterpret_pointer_cast` 不是 `constexpr`（`reinterpret_cast` 不能用于常量求值）。

## `get_deleter`（[util.smartptr.getdeleter]）

`get_deleter<D>(p)`：若 `p` 拥有 cv 无限定类型 `D` 的删除器，返回其地址，否则 `nullptr`。¶1 注：返回的指针在最后一个拥有 `d` 的 `shared_ptr` 销毁后是否仍有效**未指明**——实现可能等所有 `weak_ptr` 也销毁才销毁删除器。libc++ 用 `typeid` 比较实现（`__get_deleter(const type_info&)`），所以**禁用 RTTI 时 `get_deleter` 总是返回空指针**。

## I/O（[util.smartptr.shared.io]）

`os << p` 等价于 `os << p.get()`。

## 思考题

<details markdown="1">
<summary>1. `std::shared_ptr<FILE> f(std::fopen(name, "r"), std::fclose);` 在 `fopen` 失败时有什么问题？</summary>

这不是 `nullptr_t` 重载（`fopen` 返回 `FILE*`），而是 `shared_ptr(Y* p, D d)`，`p` 恰好是空指针。它创建了一个**拥有空指针**的 `shared_ptr`，`use_count() == 1`；析构时按 [util.smartptr.shared.dest] ¶1.2 调用 `d(p)`，即 `fclose(nullptr)`——C 标准下这是 UB。与 `unique_ptr`（析构时先判空）不同，`shared_ptr` 的删除器必须自己处理空指针。（另外，取 `std::fclose` 的地址本身也不受标准保证，见 [[namespace.std]]。）
</details>

<details markdown="1">
<summary>2. 为什么 `make_shared<T>(args...)` 启用 shared_from_this，而 `shared_ptr<T>(nullptr, d)` 不启用？</summary>

启用的动作是给 `p->weak-this` 赋值，需要一个真实的对象。`nullptr_t` 版本没有对象；数组版本的元素类型即使派生自 `enable_shared_from_this`，也无法用一个 `shared_ptr<U[]>` 合理地初始化每个元素的 `weak-this`（类型都不对），所以标准只在非数组、有对象指针时启用。
</details>

<details markdown="1">
<summary>3. `dynamic_pointer_cast<D>(std::move(r))` 转换失败时，`r` 还拥有对象吗？</summary>

拥有。¶6.2：`dynamic_cast` 返回空时结果是 `shared_ptr<T>()`，没有调用以 `std::move(r)` 为实参的别名构造，`r` 没有被移走。
</details>

## 小结

- 构造时按 `Y` 捕获删除器：`shared_ptr<Base>(new Derived)` 安全，`shared_ptr<void>` 也能正确析构。
- 每次从裸指针构造都新建控制块；同一裸指针交给两个 `shared_ptr` 是双重删除。
- 别名构造把"存储什么"和"拥有什么"分离；"空"指不拥有，`operator bool` 只看 `get()`。
- 赋值与 `reset` 都是"构造临时再 swap"。
- `nullptr` / 空指针 + 删除器的 `shared_ptr` 会以空指针调用删除器。
- `operator[]` 有 C++26 加固前置条件；其余解引用只是普通前置条件。
- `make_shared` 用圆括号初始化，数组升序构造、逆序销毁；`allocate_shared` 经重绑定的分配器 `construct`/`destroy`。
- 指针转换一律用 `*_pointer_cast`，它们是别名构造。
