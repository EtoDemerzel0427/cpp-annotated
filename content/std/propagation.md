---
title: 异常传播
summary: exception_ptr——在 handler 之外持有异常、跨线程传递、稍后重抛；current_exception 的复制与失败语义、rethrow_exception 的前置条件、make_exception_ptr、exception_ptr_cast；以及 nested_exception / throw_with_nested / rethrow_if_nested 组成的异常链
status: done
covers: except.nested
papers: N2179
related: support.exception, except.throw, except.handle, except.terminate, bad.exception, alloc.errors, intro.races, nullablepointer.requirements
tags: 标准库, exception_ptr, nested_exception, 异常, 多线程
updated: 2026-10-18
---

核心语言的异常机制有一个结构性限制：异常对象只能在 **handler 内部**通过 `catch` 参数或 `throw;` 访问，handler 一退出，异常对象就被销毁（[[except.throw]]）。但很多场景需要把异常"带出去"：

- **跨线程**：工作线程中抛出的异常，要交给等待结果的线程（`std::future`、`std::async`、线程池）。
- **延迟重抛**：先收集多个操作的错误，稍后统一处理。
- **跨越不支持异常的边界**：C 回调、事件循环。

C++11 的 `std::exception_ptr`（[[N2179]]）解决了这个问题。本节 [propagation] 定义它及其操作；[except.nested] 在其基础上提供"异常链"。

## `exception_ptr`：类型要求（¶1–¶8）

```cpp
using exception_ptr = unspecified;
```

- ¶1：`exception_ptr` 可用于**指代一个异常对象**。
- ¶2：满足 *Cpp17NullablePointer* 要求（[[nullablepointer.requirements]]）：可默认构造、可复制、可与 `nullptr` 比较、可在布尔语境中使用（显式转换为 `bool`）。
- ¶3：两个非空的 `exception_ptr` **等价且比较相等，当且仅当它们指代同一个异常**。
- ¶4：默认构造产生空值。
- ¶5：**不得**隐式转换为任何算术、枚举或指针类型。
- ¶6 注 1：实现可以使用**引用计数的智能指针**。（libc++/libstdc++ 都是：内部一个 `void*`，指向 Itanium ABI 的 `__cxa_exception` 头之后的异常对象，复制时原子地增加该头中的引用计数。）
- ¶8：所有成员函数都是 `constexpr` 的。

¶7 是一条**数据竞争**规定：

!!! std
    For purposes of determining the presence of a data race, operations on `exception_ptr` objects shall access and modify only the `exception_ptr` objects themselves and not the exceptions they refer to.

    为判定数据竞争，对 `exception_ptr` 对象的操作只能访问和修改 `exception_ptr` 对象本身，而不能访问它们所指代的异常。

也就是说，两个线程各自复制、销毁指向同一异常的 `exception_ptr`，不构成数据竞争（引用计数由实现同步）；对指代同一异常对象的 `exception_ptr` 使用 `rethrow_exception` 或 `exception_ptr_cast` 也不引入数据竞争。但注 2 警告：如果 `rethrow_exception` 重抛的是**同一个**异常对象（而非副本），两个线程并发访问这个被重抛的异常对象（例如都调用它的非 `const` 成员）**可能**构成数据竞争。

## `current_exception`（¶9）

```cpp
constexpr exception_ptr current-exception() noexcept;   // 仅用于说明
exception_ptr current_exception() noexcept;
```

¶9 *Returns*：一个 `exception_ptr`，指代**当前处理的异常**（[[g:currently-handled-exception]]）或其**副本**；若当前没有正在处理的异常，返回空 `exception_ptr`。附带四条规定：

1. 被指代的对象至少在还有 `exception_ptr` 指代它时保持有效——这就是"延长异常对象生命期"的机制，[[except.throw]] 中异常对象的销毁时机也考虑了 `exception_ptr` 的存在。
2. 如果函数需要分配内存而分配失败，返回一个指代 `bad_alloc` 实例的 `exception_ptr`（[[alloc.errors]]）——不抛出，因为函数是 `noexcept` 的。
3. 两次连续调用的返回值是否指代**同一个**异常对象是**未指明的**——注 3：即是否每次都创建新副本是未指明的。Itanium ABI 的实现不复制，直接增加引用计数。
4. 如果复制当前异常对象时抛出了异常，返回指代那个被抛出异常的 `exception_ptr`；如果做不到，返回指代 `bad_exception` 实例的（[[bad.exception]]）。注 4：被抛出异常的复制构造函数也可能失败，实现可以用 `bad_exception` 代替以避免无限递归。

"当前处理的异常"不仅限于 `catch` 块内：因抛出异常而进入 `std::terminate` 时，有一个隐式 handler 处于活动状态（[[except.handle]]），所以自定义 `terminate_handler` 中也能用 `current_exception()` 拿到那个未捕获的异常（见 [[support.exception]] 的例子）。

为什么要有一个"仅用于说明"的 `constexpr` 版本 *`current-exception`*？因为 `current_exception()` 本身不是 `constexpr` 的，而 `make_exception_ptr` 是 `constexpr` 的，其规格要用"如同 `try { throw e; } catch(...) { return current-exception(); }`"来描述——需要一个可以在常量求值中使用的版本。

## `rethrow_exception`（¶10–¶11）

```cpp
[[noreturn]] constexpr void rethrow_exception(exception_ptr p);
```

¶10 *Preconditions*：`p` **不是空指针**。传入空 `exception_ptr` 是未定义行为——这是最常见的误用，必须先检查 `if (p)`。

¶11 *Effects*：令 *u* 为 `p` 所指代的异常对象**或其副本**——是否复制是未指明的，副本的内存以未指明的方式分配。

- ¶11.1 若为形成 *u* 分配内存失败，抛出 `bad_alloc` 实例；
- ¶11.2 否则，若复制异常以形成 *u* 时抛出异常，抛出那个异常；
- ¶11.3 否则，抛出 *u*。

由于是否复制未指明，`catch (std::runtime_error& e)` 中对 `e` 的修改**可能**影响到其他线程中通过同一 `exception_ptr` 看到的对象——这就是 ¶7 注 2 所说的数据竞争风险。按 `const&` 捕获是好习惯。

## `make_exception_ptr`（¶12）

```cpp
template<class E> constexpr exception_ptr make_exception_ptr(E e) noexcept;
```

¶12 *Effects*：创建一个指代 `e` 的**副本**的 `exception_ptr`，**如同**：

```cpp
try { throw e; } catch (...) { return current-exception(); }
```

"如同"给了实现优化空间：真的执行 `throw` 意味着走一遍完整的异常抛出和 handler 搜索，代价很高。

!!! impl
    libc++ 在条件允许时（启用了异常和 RTTI，且运行时库提供 `__cxa_init_primary_exception`）**不真的抛出**：它直接调用 `__cxa_allocate_exception` 分配异常对象，用 placement new 复制构造 `e`，再用 `__cxa_init_primary_exception` 填好类型信息和析构函数，得到一个与真正 `throw` 产生的完全相同的异常对象。只有在 Objective-C++ 等特殊情形下才回退到 `try { throw e; } catch (...) {...}`。

注意 `E` 是**按值**接收的：`make_exception_ptr(derived_ref_as_base)` 会切片。传给它的应当是异常的**最终类型**。

## `exception_ptr_cast`（¶13–¶14）

```cpp
template<class E>
  constexpr optional<const E&> exception_ptr_cast(const exception_ptr& p) noexcept;
template<class E> void exception_ptr_cast(const exception_ptr&&) = delete;
```

这是较新的工作草案加入的函数（特性测试宏 `__cpp_lib_exception_ptr_cast` 值为 `202603L`）。它解决了一个长期的痛点：想**查看** `exception_ptr` 里装的是什么，以前只能 `rethrow_exception` 再 `catch`——一次完整的抛出，代价昂贵。

- ¶13 *Mandates*：`E` 是 cv 非限定的完整对象类型，不是数组类型，不是指针或成员指针类型。注 5：当 `E` 是指针或成员指针类型时，`const E&` 类型的 handler 可以在**不绑定到异常对象本身**的情况下匹配（[[except.handle]] 中指针的转换匹配会产生临时对象），因此无法返回指向异常对象的引用。
- ¶14 *Returns*：若 `p` 非空，且一个 `const E&` 类型的 handler **会匹配**该异常对象（[[except.handle]]），返回包含指向该异常对象的引用的 `optional`；否则返回 `nullopt`。

右值版本被 `= delete`，防止 `exception_ptr_cast<E>(std::make_exception_ptr(x))` 这种写法：临时 `exception_ptr` 是异常对象唯一的持有者，完整表达式结束后异常对象被销毁，返回的引用随即悬垂。

截至本文编写时，libc++ 尚未提供 `exception_ptr_cast`。

## 跨线程传递的完整例子

```cpp run title="exception-ptr.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <thread>

int main() {
    std::exception_ptr err;                      // ¶4：默认构造为空
    std::thread worker([&] {
        try {
            throw std::logic_error("from worker");
        } catch (...) {
            err = std::current_exception();      // 在 handler 内捕获异常
        }                                        // handler 退出，但异常对象被 err 保活
    });
    worker.join();                               // join 提供 happens-before，读 err 无数据竞争

    if (err) {                                   // ¶10：rethrow_exception 要求非空
        try {
            std::rethrow_exception(err);
        } catch (const std::logic_error& e) {
            std::printf("main got: %s\n", e.what());
        }
    }

    auto p = std::make_exception_ptr(std::out_of_range("oops"));
    auto q = p;
    std::printf("%d %d\n", p == q, std::current_exception() == nullptr);   // 1 1
}
```

## 嵌套异常（[except.nested]）

### `nested_exception`

```cpp
class nested_exception {
public:
  nested_exception() noexcept;
  nested_exception(const nested_exception&) noexcept = default;
  nested_exception& operator=(const nested_exception&) noexcept = default;
  virtual ~nested_exception() = default;
  [[noreturn]] void rethrow_nested() const;
  exception_ptr nested_ptr() const noexcept;
};
```

- ¶1：设计为通过**多重继承**使用的 mixin。它捕获**当前处理的异常**并保存起来，供以后使用。
- ¶2 注 1：它有虚析构函数，是**多态类**，因此可以用 `dynamic_cast` 检测一个异常对象是否带有 `nested_exception` 基类。
- ¶3：构造函数调用 `current_exception()` 并保存结果。——所以 `nested_exception` 对象必须在 handler **内部**构造，才能捕获到"内层"异常。
- ¶4 `rethrow_nested()`：若 `nested_ptr()` 返回空，调用 **`std::terminate`**；否则抛出保存的异常。
- ¶5 `nested_ptr()`：返回保存的 `exception_ptr`。

注意它**不**派生自 `std::exception`，没有 `what()`。

### `throw_with_nested`（¶6–¶8）

```cpp
template<class T> [[noreturn]] void throw_with_nested(T&& t);
```

令 `U` 为 `decay_t<T>`。

- ¶7 *Preconditions*：`U` 满足 *Cpp17CopyConstructible*。
- ¶8 *Throws*：若 `is_class_v<U> && !is_final_v<U> && !is_base_of_v<nested_exception, U>` 为真，抛出一个**未指明类型**的异常，它公开派生自 `U` **和** `nested_exception`，并由 `std::forward<T>(t)` 构造；否则直接抛出 `std::forward<T>(t)`。

也就是说，`throw_with_nested` 在能做 mixin 的时候（`U` 是非 final 的类且尚未带 `nested_exception`）合成一个"`U` + 内层异常"的类型抛出；否则（`int`、final 类、已经是嵌套异常）退化成普通的 `throw`，**内层异常就丢了**。

### `rethrow_if_nested`（¶9）

```cpp
template<class E> void rethrow_if_nested(const E& e);
```

¶9 *Effects*：若 `E` 不是多态类类型，或者 `nested_exception` 是 `E` 的不可访问或有歧义的基类，**无效果**。否则执行：

```cpp
if (auto p = dynamic_cast<const nested_exception*>(addressof(e)))
  p->rethrow_nested();
```

它是"如果有内层异常就把它抛出来"的工具。`dynamic_cast` 在这里做的是**交叉转换**（cross-cast）：从 `E` 转到它的兄弟基类 `nested_exception`，这正是 ¶2 要求 `nested_exception` 为多态类的原因。

```cpp run title="nested-exception.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>

void print_nested(const std::exception& e, int depth = 0) {
    std::printf("%*s%s\n", depth * 2, "", e.what());
    try {
        std::rethrow_if_nested(e);               // 有内层异常则抛出
    } catch (const std::exception& inner) {
        print_nested(inner, depth + 1);
    } catch (...) {}
}

void open_file(const std::string& name) {
    throw std::runtime_error("cannot open " + name);
}

void load_config() {
    try {
        open_file("app.toml");
    } catch (...) {
        // 抛出一个"runtime_error + nested_exception"的未指明类型，内层异常被保存
        std::throw_with_nested(std::runtime_error("load_config failed"));
    }
}

int main() {
    try {
        load_config();
    } catch (const std::exception& e) {
        print_nested(e);
    }
}
// 输出：
// load_config failed
//   cannot open app.toml
```

!!! pitfall "在 handler 之外调用 `throw_with_nested`"
    `throw_with_nested` 合成的异常类型的构造会构造 `nested_exception` 基类，而后者调用 `current_exception()`。如果不在 handler 中调用，保存的是空 `exception_ptr`；之后有人对它调用 `rethrow_if_nested`，就会走到 `rethrow_nested()` 的空指针分支——**调用 `std::terminate`**（¶4），而不是"没有内层异常就什么也不做"。

## 小结

!!! summary
    - `exception_ptr`：可空、可复制、可比较的"异常句柄"，相等当且仅当指代同一异常；实现通常是引用计数指针；复制/销毁不与所指异常构成数据竞争。
    - `current_exception()`：返回当前处理的异常或其副本；无异常时为空；内存不足返回 `bad_alloc`，复制失败返回复制抛出的异常或 `bad_exception`。
    - `rethrow_exception(p)`：`p` 为空是 UB；可能抛出原对象也可能抛出副本。
    - `make_exception_ptr(e)`：如同抛出再捕获；按值接收，注意切片。
    - `exception_ptr_cast<E>(p)`：不重抛即可查看异常；按 handler 匹配规则判断；右值版本被删除。
    - `throw_with_nested` 合成"外层 + 内层"的异常；`rethrow_if_nested` 用交叉 `dynamic_cast` 取出内层；空的 `nested_exception` 调用 `rethrow_nested` 会 `terminate`。
