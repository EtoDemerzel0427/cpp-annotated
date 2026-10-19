---
title: 存储分配错误
summary: bad_alloc 与 bad_array_new_length 两个异常类，以及 new_handler 机制：处理函数必须做的三件事之一、set_new_handler/get_new_handler 的契约，和 Clang 在数组长度非法时的偏离
status: done
covers: *
related: new.delete, support.dynamic, expr.new, exception, support.exception, basic.stc.dynamic.allocation, except.terminate
tags: 标准库, bad_alloc, new_handler, 异常
updated: 2026-10-18
---

当 `operator new` 拿不到内存时，C++ 提供了两层应对机制：

1. 先求助：调用程序安装的 **new_handler**，让它想办法腾出内存（或者决定放弃）；
2. 再报告：抛出 `std::bad_alloc`（或其派生类）。

本节定义这两层机制用到的类型和函数。它们与 [[new.delete]] 中 `operator new` 的默认行为（¶3 的循环）紧密配合。

## `bad_alloc`（[bad.alloc]）

```cpp
class bad_alloc : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1：实现为报告存储分配失败而抛出的异常对象，其类型就是 `bad_alloc`。¶2：`what()` 返回一个由实现定义的 NTBS（空终止字节串）。特殊成员函数的规格见 [[exception#2]]：默认构造、复制构造、复制赋值都具有非抛出的异常说明，复制后两者 `what()` 返回的字符串内容相同（`strcmp` 为 0）。

!!! note "`constexpr` 的 `what()` {{c++26}}"
    C++26 允许在常量求值中抛出和捕获异常，标准库的异常类型因此获得了 `constexpr` 成员，`bad_alloc::what()` 也在其中（对应特性测试宏 `__cpp_lib_constexpr_exceptions`，见 [[version.syn]]）。截至本文编写时，libc++ 的 `bad_alloc::what()` 仍是非 `constexpr` 的、定义在动态库里的函数。

什么时候会抛出 `bad_alloc`？

- 可替换的全局 `operator new`/`operator new[]` 失败时（[[new.delete.single#2]]）。这是要求的行为，替换版本也必须遵守；
- 标准库容器和分配器在 `allocator<T>::allocate` 失败时（通过 `operator new`）；
- [[expr.new]] 中的数组长度检查失败时——抛的是派生类 `bad_array_new_length`；
- new_handler 主动抛出时（见下文 ¶2.2）。

## `bad_array_new_length`（[new.badlength]）

```cpp
class bad_array_new_length : public bad_alloc {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1：用于报告试图分配一个大小小于零或大于由实现定义的上限的数组。它派生自 `bad_alloc`，所以 `catch (const std::bad_alloc&)` 也能接住它。

这个异常由 *new-expression* 本身抛出，而不是由 `operator new[]` 抛出。[[expr.new#8]] 规定：若数组的第一维表达式（转换后）的值小于零、或使得分配的总大小超过实现上限、或者小于初始化器给出的元素个数，则不调用分配函数，而是抛出一个能被 `std::bad_array_new_length` 类型的 handler 匹配的异常（如果分配函数是非抛出的，则 *new-expression* 返回空指针）。这样规定的原因是，`new int[n]` 中 `n * sizeof(int)` 可能溢出 `size_t`，早期的实现会悄悄分配一块过小的内存，造成缓冲区溢出；C++11 起实现必须检测出这种情况。

!!! impl "Clang 的偏离：抛 `bad_alloc` 而非 `bad_array_new_length`"
    Clang 在运行时检测到数组大小为负或溢出时，并不直接抛 `bad_array_new_length`，而是把 `size_t(-1)` 作为大小传给 `operator new[]`，依赖它分配失败抛出 `bad_alloc`。本机 Clang `-O1` 生成的 IR 中可以看到这种 `select i1 %overflow, i64 -1, i64 %size` 的模式。结果是异常类型为 `std::bad_alloc` 而不是 `std::bad_array_new_length`，`catch (const std::bad_array_new_length&)` 接不住它。这是一个已知的不符合之处；GCC 则调用运行时库的 `__cxa_throw_bad_array_new_length`。可移植代码应当捕获 `std::bad_alloc`。

```cpp run title="bad-array-new-length.cpp" impl
#include <cstdio>
#include <new>
#include <typeinfo>

int main(int argc, char**) {
    long n = argc - 2;                  // 运行时为 -1，阻止编译期诊断
    try {
        int* p = new int[n];
        delete[] p;
    } catch (const std::bad_array_new_length&) {
        std::puts("bad_array_new_length（标准要求）");
    } catch (const std::bad_alloc& e) {
        std::printf("bad_alloc: %s（Clang 的实际行为）\n", typeid(e).name());
    }
}
```

如果数组大小是潜在求值的核心常量表达式且非法，则程序是非良构的（[[expr.new#8]] ¶8.5），编译器直接报错，例如 Clang 的 "array is too large"。

## `new_handler`（[new.handler]）

```cpp
using new_handler = void (*)();
```

¶1：**处理函数**（handler function，[[g:new-handler]]）的类型，当 `operator new()` 或 `operator new[]()` 无法满足额外存储的请求时，调用的就是这种函数。

¶2 *Required behavior*：new_handler 必须做以下三件事之一。

- ¶2.1 腾出更多可供分配的存储，然后返回；`operator new` 会重新尝试分配（[[new.delete.single#3]] 的循环）；
- ¶2.2 抛出 `bad_alloc` 或其派生类的异常；
- ¶2.3 终止程序，不返回调用者（例如调用 `std::abort` 或 `std::exit`）。

这是对程序的要求。如果 handler 返回了但没有腾出任何内存，`operator new` 的循环会无限重复；这不是 UB，但程序会卡死。如果 handler 抛出了 `bad_alloc` 族以外的异常，就违反了 *Required behavior*，后果是未定义行为（[[res.on.functions]]），而且 `operator new` 的调用者只预期 `bad_alloc`。

## `set_new_handler` 与 `get_new_handler`（[set.new.handler]、[get.new.handler]）

```cpp
new_handler set_new_handler(new_handler new_p) noexcept;
new_handler get_new_handler() noexcept;
```

- `set_new_handler`：把 `new_p` 设为当前 new_handler（¶1），返回之前的 new_handler（¶2）。¶3：初始的 new_handler 是空指针。
- `get_new_handler`（C++11）：返回当前的 new_handler；注 1：可能是空指针。

由于初始值为空，默认的 `operator new` 失败时直接抛 `bad_alloc`（[[new.delete.single#3]] 的 ¶3.2）。按 [[res.on.data.races]] 的一般要求，并发调用这两个函数不得引入数据竞争。

```cpp run title="new-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

// 预留一块"应急内存"，内存不足时释放它，给程序一次自救的机会
static char* emergency = nullptr;

void on_oom() {
    if (emergency) {
        std::free(emergency);           // ¶2.1：腾出内存后返回，operator new 将重试
        emergency = nullptr;
        std::puts("released emergency reserve");
        return;
    }
    std::set_new_handler(nullptr);      // 没有更多可以释放的：卸载自己，
    throw std::bad_alloc();             // ¶2.2：并抛出 bad_alloc
}

int main() {
    emergency = static_cast<char*>(std::malloc(1 << 20));
    std::new_handler old = std::set_new_handler(on_oom);
    std::printf("old handler is null: %d\n", old == nullptr);       // ¶3：初始为空
    std::printf("current is on_oom: %d\n", std::get_new_handler() == on_oom);
    std::set_new_handler(old);
    std::free(emergency);
}
```

!!! pitfall "new_handler 不是 C 的 `malloc` 失败回调"
    只有 `operator new` 的默认实现（以及遵循同一约定的替换版本）才调用 new_handler。`malloc` 失败时不会调用它；替换了 `operator new` 的程序如果自己不循环调用 `get_new_handler()`，安装的 handler 也不会被调用，因为标准只要求替换版本满足 *Required behavior*（非空或抛 `bad_alloc`），并不要求它调用 handler。

!!! note "类专属的 new_handler 惯用法"
    这是《Effective C++》中的经典技巧：在类的成员 `operator new` 中，先用 `std::set_new_handler` 换上类专属的 handler，调用 `::operator new`，再（通过 RAII）恢复原 handler。这依赖于 `set_new_handler` 返回旧值的契约（¶2）。由于 new_handler 是全局状态，这个技巧在多线程环境中并不安全。

## 思考题

!!! question "思考题"
    1. new_handler 中可以调用 `operator new` 吗？
    2. `new (std::nothrow) int[n]` 在 `n` 为负时会怎样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 可以，标准并未禁止，但很危险：如果内部的 `operator new` 也失败，会再次调用同一个 handler，可能形成无限递归。实践中 handler 应当只释放内存，或者先 `set_new_handler(nullptr)` 再做可能分配的操作。
2. 按 [[expr.new#8]]：分配函数 `operator new[](size_t, const nothrow_t&)` 有非抛出的异常说明，因此 *new-expression* 的值是空指针，不抛出异常，也不调用分配函数。
</details>

## 小结

!!! summary
    - `bad_alloc`：分配失败的标准异常；`bad_array_new_length` 派生自它，用于数组长度为负、溢出或超过上限。
    - `bad_array_new_length` 由 *new-expression* 抛出，不由 `operator new[]` 抛出；Clang 实际抛 `bad_alloc`，可移植代码应捕获基类。
    - new_handler 必须三选一：腾出内存后返回、抛 `bad_alloc` 族异常、终止程序。
    - 初始 new_handler 为空；`set_new_handler` 返回旧值；`get_new_handler` 可能返回空。
