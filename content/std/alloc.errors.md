---
title: 存储分配错误
summary: 分配失败时的两层机制：先调用程序安装的 new_handler 设法腾出内存，再抛出 bad_alloc；数组长度非法时 new 表达式抛出 bad_array_new_length（Clang 实际抛 bad_alloc）。
status: done
covers: *
related: new.delete, support.dynamic, expr.new, exception, support.exception, basic.stc.dynamic.allocation, except.terminate
tags: 标准库, bad_alloc, new_handler, 异常
updated: 2026-10-19
---

!!! tldr
    - 默认的 `operator new` 分配失败时，先调用当前的 new_handler；没有安装 new_handler 时抛出 `std::bad_alloc`。
    - new_handler 只能做三件事之一：腾出内存后返回、抛出 `bad_alloc` 族的异常、终止程序。
    - 初始的 new_handler 是空指针；`set_new_handler` 返回旧值，`get_new_handler` 读取当前值。
    - `new T[n]` 的 `n` 为负数或过大时，*new-expression* 本身抛出 `bad_array_new_length`，它派生自 `bad_alloc`。本机 Clang 实际抛的是 `bad_alloc`，可移植代码应当捕获基类。

## new_handler：失败时先求助 [new.handler]

```cpp run title="new-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

char* reserve = nullptr;   // 预留的应急内存

void on_oom() {
  if (reserve) {
    std::free(reserve);    // 腾出内存后返回：operator new 会重试
    reserve = nullptr;
    return;
  }
  throw std::bad_alloc();  // 没什么可释放了：抛出
}

int main() {
  reserve = static_cast<char*>(std::malloc(1 << 20));
  std::new_handler old = std::set_new_handler(on_oom);
  std::printf("%d %d\n", old == nullptr,
              std::get_new_handler() == on_oom);   // 1 1
  std::set_new_handler(old);
  std::free(reserve);
}
```

程序启动时预留一块内存，内存耗尽时把它释放掉，给程序一次自救的机会。这就是 new_handler 的典型用法。

¶1 `new_handler` 是 `void (*)()`，即**处理函数**（[[g:new-handler]]）的类型。`operator new` 和 `operator new[]` 无法满足分配请求时调用它。调用发生在默认 `operator new` 的循环里（[[new.delete.single#3]]）：分配失败，调用 handler，handler 返回后再试一次。

¶2 Required behavior：new_handler 必须做以下三件事之一。

- ¶2.1 腾出更多可分配的存储，然后返回；
- ¶2.2 抛出 `bad_alloc` 或其派生类的异常；
- ¶2.3 终止程序，不返回调用者，比如调用 `std::abort`。

这是对程序的要求。handler 返回了却没有腾出内存，`operator new` 会一直重试下去，程序卡死。handler 抛出 `bad_alloc` 族以外的异常则违反了 Required behavior，行为未定义（[[res.on.functions]]）。

## 安装与读取 [set.new.handler]、[get.new.handler]

```cpp
new_handler set_new_handler(new_handler new_p) noexcept;
new_handler get_new_handler() noexcept;
```

`set_new_handler` 把 `new_p` 设为当前 handler（¶1），返回之前的 handler（¶2）。第 3 段规定，初始的 handler 是空指针，所以默认情况下 `operator new` 失败时直接抛 `bad_alloc`。`get_new_handler` 返回当前 handler，注 1 提醒它可能是空指针。两者并发调用不会引入数据竞争（[[res.on.data.races]]）。

!!! pitfall "new_handler 只由 `operator new` 调用"
    `malloc` 失败不会调用它。替换了 `operator new` 的程序，如果替换版本自己不调用 `get_new_handler()`，安装的 handler 也永远不会被调用：标准只要求替换版本满足 Required behavior，没有要求它调用 handler（[[new.delete]]）。

!!! note "按类安装 handler"
    《Effective C++》介绍过一种写法：类的成员 `operator new` 先用 `set_new_handler` 换上本类专用的 handler，调用 `::operator new`，再用 RAII 恢复原来的 handler。它依赖 `set_new_handler` 返回旧值。new_handler 是全局状态，所以这种写法在多线程程序里不安全。

## `bad_alloc` [bad.alloc]

```cpp
class bad_alloc : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1 实现报告存储分配失败时，抛出的异常对象的类型是 `bad_alloc`。

¶2 `what()` 返回一个由实现定义的空终止字节串。默认构造、复制构造、复制赋值都不抛异常，复制后 `what()` 的内容相同，这些是所有标准异常类共同的约定（[[exception#2]]）。

会抛出 `bad_alloc` 的地方：

- 全局 `operator new` / `operator new[]` 分配失败（[[new.delete.single#2]]），替换版本也必须如此；
- 标准库容器通过 `std::allocator<T>::allocate` 分配失败；
- new_handler 主动抛出（¶2.2）；
- 数组长度非法时抛出它的派生类 `bad_array_new_length`（见下文）。

`what()` 在 C++26 成为 `constexpr`，配合常量求值中的异常。本机 Clang 23 还不支持在常量求值中抛异常，libc++ 的 `bad_alloc::what()` 也还不是 `constexpr`。

## `bad_array_new_length` [new.badlength]

```cpp run title="bad-array-new-length.cpp" impl
#include <cstdio>
#include <new>

int main(int argc, char**) {
  long n = argc - 2;              // 运行时为 -1
  try {
    int* p = new int[n];
    std::printf("%p\n", (void*)p);
    delete[] p;
  } catch (const std::bad_array_new_length&) {
    std::puts("bad_array_new_length");  // 标准要求
  } catch (const std::bad_alloc&) {
    std::puts("bad_alloc");             // 本机 Clang 的结果
  }
}
```

`n * sizeof(int)` 可能溢出 `size_t`。早期的实现会悄悄分配一块过小的内存，造成缓冲区溢出。C++11 起，*new-expression* 必须先检查数组长度（[[expr.new#8]]）。长度在以下情况下非法：转换前为负数；分配的总大小超过实现的上限；初始化器的个数超过数组元素个数。

长度非法时，分配函数不会被调用：

- 长度表达式是潜在求值的核心常量表达式，程序非良构。本机 Clang 对 `new int[-1]` 报 "array is too large"。
- 否则，如果将要调用的分配函数不抛异常（比如 `new (std::nothrow) int[n]`），*new-expression* 的值是空指针。
- 否则，*new-expression* 抛出能被 `std::bad_array_new_length` 的 handler 捕获的异常。

¶1 `bad_array_new_length` 派生自 `bad_alloc`，用来报告数组长度小于零或超过实现上限。`catch (const std::bad_alloc&)` 也能捕获它。

!!! impl "Clang 抛的是 `bad_alloc`"
    Clang 在运行时发现长度非法时，不抛 `bad_array_new_length`，而是把 `size_t(-1)` 作为大小传给 `operator new[]`，靠它分配失败抛出 `bad_alloc`。所以上面的程序在本机 `-O0` 和 `-O2` 下都打印 `bad_alloc`，这与标准不符。GCC 则调用运行时库的 `__cxa_throw_bad_array_new_length`。

    还有一个副作用：如果去掉例子里的 `printf`，`p` 没有被使用，`-O2` 会把整对 `new` / `delete` 删掉，连 `bad_alloc` 也不抛了。nothrow 形式不受影响，`new (std::nothrow) int[n]` 在本机返回空指针，符合标准。

## 思考题

!!! question "思考题"
    new_handler 里可以调用 `operator new` 吗？

<details markdown="1">
<summary>答案</summary>

标准没有禁止，但很危险。如果里面的 `operator new` 也失败，会再次调用同一个 handler，可能无限递归。handler 应当只释放内存；确实需要分配时，先 `set_new_handler(nullptr)` 卸载自己。
</details>
