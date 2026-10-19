---
title: 异常传播
summary: 用 exception_ptr 在 handler 之外持有异常、跨线程传递、稍后重抛：current_exception、rethrow_exception、make_exception_ptr、exception_ptr_cast 的契约；以及 nested_exception、throw_with_nested、rethrow_if_nested 组成的异常链。
status: done
covers: except.nested
papers: N2179
related: support.exception, except.throw, except.handle, except.terminate, bad.exception, alloc.errors, intro.races, nullablepointer.requirements
tags: 标准库, exception_ptr, nested_exception, 异常, 多线程
updated: 2026-10-19
---

!!! tldr
    - 异常对象在 handler 退出时销毁。在 handler 里调用 `std::current_exception()` 得到一个 `exception_ptr`，就能让异常对象活下去，交给别的线程或稍后重抛。
    - `exception_ptr` 像一个引用计数的智能指针：可以为空，可以复制，指向同一个异常时比较相等。
    - `rethrow_exception(p)` 要求 `p` 非空；它抛出的可能是原对象，也可能是副本。
    - `make_exception_ptr(e)` 相当于抛出 `e` 再捕获；新加入的 `exception_ptr_cast<E>(p)` 不用重抛就能查看异常。
    - `throw_with_nested` 把当前异常包进新异常里，`rethrow_if_nested` 把内层异常取出来；它们只能在 handler 里使用。

## 把异常带出 handler [propagation]

```cpp run title="exception-ptr.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <thread>

int main() {
  std::exception_ptr err;               // 默认构造：空
  std::thread worker([&] {
    try {
      throw std::logic_error("from worker");
    } catch (...) {
      err = std::current_exception();   // 在 handler 内取得异常
    }                                   // 异常对象由 err 保活
  });
  worker.join();                        // join 之后读 err 没有数据竞争

  if (err) {                            // rethrow_exception 要求非空
    try {
      std::rethrow_exception(err);
    } catch (const std::logic_error& e) {
      std::printf("main got: %s\n", e.what());
    }
  }
}
```

在语言层面，只有 handler 内部能通过 `catch` 的参数或 `throw;` 接触异常对象，handler 一退出它就被销毁（[[except.throw]]）。但工作线程里的异常要交给等待结果的线程，`std::future`、`std::async`、线程池都需要这样做；有时还要先收集错误、稍后统一处理，或者让异常穿过不支持异常的 C 回调。C++11 的 `std::exception_ptr`（[[N2179]]）解决了这个问题。

### `exception_ptr` 的性质（¶1–¶8）

```cpp
using exception_ptr = unspecified;
```

- ¶1 `exception_ptr` 可以用来指代一个异常对象。
- ¶2 它满足 *Cpp17NullablePointer*（[[nullablepointer.requirements]]）：可以默认构造、复制，可以与 `nullptr` 比较，可以在条件里检查真假。
- ¶3 两个非空的 `exception_ptr` 当且仅当指代同一个异常时比较相等。
- ¶4 默认构造得到空值。
- ¶5 它不能隐式转换为任何算术、枚举或指针类型。
- ¶6 注 1 说明实现可以用引用计数的智能指针。libc++ 和 libstdc++ 都是这样：内部一个指向异常对象的指针，复制时原子地增加 Itanium ABI 异常头里的引用计数。
- ¶8 它的所有成员函数都是 `constexpr` 的。

¶7 规定了数据竞争：对 `exception_ptr` 的操作只访问和修改 `exception_ptr` 对象本身，不访问它指代的异常。所以两个线程各自复制、销毁指向同一异常的 `exception_ptr`，不构成数据竞争；对它们调用 `rethrow_exception` 或 `exception_ptr_cast` 也不会。注 2 提醒，如果 `rethrow_exception` 抛出的是同一个异常对象而不是副本，两个线程并发访问那个被重抛的对象仍然可能构成数据竞争。

### `current_exception`（¶9）

```cpp
constexpr exception_ptr current-exception() noexcept;   // 仅用于说明
exception_ptr current_exception() noexcept;
```

¶9 返回指代**当前处理的异常**（[[g:currently-handled-exception]]）或其副本的 `exception_ptr`；没有正在处理的异常时返回空值。具体规定有四条：

1. 被指代的对象至少在还有 `exception_ptr` 指代它时保持有效。这就是上例中异常对象能活过 handler 的原因。
2. 需要分配内存而分配失败时，返回指代一个 `bad_alloc` 对象的 `exception_ptr`。函数是 `noexcept` 的，不能抛出。
3. 两次调用的结果是否指代同一个对象是未指定的，即是否每次都复制是未指定的（注 3）。本机两次调用的结果比较相等，Itanium ABI 的实现只增加引用计数，不复制。
4. 复制当前异常时如果抛出了异常，返回指代那个新异常的 `exception_ptr`；做不到时，指代一个 `bad_exception` 对象（[[bad.exception]]）。注 4 解释，新异常的复制也可能失败，用 `bad_exception` 代替可以避免无限递归。

当前处理的异常不限于 `catch` 块内。因未捕获的异常进入 `std::terminate` 时，有一个隐式 handler 处于活动状态（[[except.handle]]），自定义的 terminate_handler 也能用 `current_exception()` 拿到那个异常（例子见 [[support.exception]]）。

仅用于说明的 *`current-exception`* 是 `constexpr` 的，而公开的 `current_exception()` 不是。下文 `make_exception_ptr` 是 `constexpr` 的，它的规格写作抛出再捕获，需要一个能在常量求值中使用的版本来描述。

### `rethrow_exception`（¶10–¶11）

```cpp
[[noreturn]] constexpr void rethrow_exception(exception_ptr p);
```

¶10 前置条件：`p` 不是空指针。传入空的 `exception_ptr` 是未定义行为，这是最常见的误用，调用前要先检查 `if (p)`。

¶11 令 *u* 为 `p` 指代的异常对象或它的副本。是否复制是未指定的，副本的内存以未指定的方式分配。

- ¶11.1 为 *u* 分配内存失败时，抛出 `bad_alloc`；
- ¶11.2 否则，复制时抛出了异常，就抛出那个异常；
- ¶11.3 否则，抛出 *u*。

既然可能不复制，在 `catch (std::runtime_error& e)` 里修改 `e`，别的线程通过同一个 `exception_ptr` 也可能看到这次修改，这正是第 7 段注 2 说的数据竞争。按 `const&` 捕获可以避免。

### `make_exception_ptr`（¶12）

```cpp
template<class E> constexpr exception_ptr make_exception_ptr(E e) noexcept;
```

¶12 创建一个指代 `e` 的副本的 `exception_ptr`，效果如同：

```cpp
try { throw e; } catch (...) { return current-exception(); }
```

真的抛出一次要走完整的异常抛出和 handler 搜索，代价很高。"如同"给实现留出了直接构造异常对象的空间。

`e` 是按值传入的，传一个绑定到派生类对象的基类引用会发生切片。应当传入异常的最终类型。

!!! impl "libc++ 不真的抛出"
    条件允许时（启用了异常和 RTTI，运行时库提供 `__cxa_init_primary_exception`），libc++ 用 `__cxa_allocate_exception` 分配异常对象，在其中复制构造 `e`，再用 `__cxa_init_primary_exception` 填好类型信息和析构函数，得到的异常对象与真正 `throw` 产生的一样。只在 Objective-C++ 等特殊情形下才退回到 `try { throw e; } catch (...)`。

### `exception_ptr_cast`（¶13–¶14）

```cpp
template<class E>
  constexpr optional<const E&> exception_ptr_cast(const exception_ptr& p) noexcept;
template<class E> void exception_ptr_cast(const exception_ptr&&) = delete;
```

以前想知道 `exception_ptr` 里装的是什么，只能 `rethrow_exception` 再 `catch`，代价是一次完整的抛出。`exception_ptr_cast` 是较新的工作草案加入的函数，不用重抛就能查看（特性测试宏 `__cpp_lib_exception_ptr_cast` 的值为 `202603L`）。截至写作时，本机 libc++ 还没有提供它。

¶14 如果 `p` 非空，并且一个 `const E&` 类型的 handler 能匹配这个异常对象（[[except.handle]]），返回装着指向该异常对象的引用的 `optional`；否则返回 `nullopt`。

¶13 Mandates：`E` 是没有 cv 限定的完整对象类型，不是数组，不是指针或成员指针。注 5 解释了最后一项：`E` 是指针时，`const E&` 的 handler 可以通过转换匹配，这时绑定的是一个临时对象而不是异常对象本身，无法返回指向异常对象的引用。

右值版本被删除，是为了拒绝 `exception_ptr_cast<E>(std::make_exception_ptr(x))`：临时的 `exception_ptr` 是异常对象唯一的持有者，完整表达式结束时异常对象就被销毁，返回的引用会悬空。

## 异常链 [except.nested]

```cpp run title="nested-exception.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>

void print(const std::exception& e, int depth = 0) {
  std::printf("%*s%s\n", depth * 2, "", e.what());
  try {
    std::rethrow_if_nested(e);       // 有内层异常就抛出来
  } catch (const std::exception& inner) {
    print(inner, depth + 1);
  } catch (...) {}
}

void open_file(const std::string& name) {
  throw std::runtime_error("cannot open " + name);
}

void load_config() {
  try {
    open_file("app.toml");
  } catch (...) {
    std::throw_with_nested(std::runtime_error("load_config failed"));
  }
}

int main() {
  try {
    load_config();
  } catch (const std::exception& e) {
    print(e);
  }
}
```

程序打印：

```text
load_config failed
  cannot open app.toml
```

高层代码捕获底层异常后，常常想抛出一个带有更多上下文的新异常，同时不丢掉原来的异常。异常链就是为此设计的。

### `nested_exception`（¶1–¶5）

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

¶1 `nested_exception` 设计成通过多重继承使用的混入类（mixin），它捕获当前处理的异常并保存下来。

¶3 它的构造函数调用 `current_exception()` 并保存结果，所以只有在 handler 里构造，才能捕获到内层异常。

¶2 注 1 说明它有虚析构函数，是多态类，因此可以用 `dynamic_cast` 检测一个异常对象是否带有 `nested_exception` 基类。它不派生自 `std::exception`，没有 `what()`。

¶4 `rethrow_nested()`：保存的 `exception_ptr` 为空时调用 `std::terminate`，否则抛出保存的异常。`nested_ptr()` 返回保存的 `exception_ptr`（¶5）。

### `throw_with_nested`（¶6–¶8）

```cpp
template<class T> [[noreturn]] void throw_with_nested(T&& t);
```

¶6–¶7 令 `U` 为 `decay_t<T>`，前置条件是 `U` 满足 *Cpp17CopyConstructible*。

¶8 如果 `U` 是类、不是 final、也还没有 `nested_exception` 基类，抛出一个未指定类型的异常，它同时公开派生自 `U` 和 `nested_exception`，由 `std::forward<T>(t)` 构造。否则直接抛出 `std::forward<T>(t)`。也就是说，对 `int`、final 类、已经带有 `nested_exception` 的类型，`throw_with_nested` 退化成普通的 `throw`，内层异常不会被保存。

### `rethrow_if_nested`（¶9）

```cpp
template<class E> void rethrow_if_nested(const E& e);
```

¶9 如果 `E` 不是多态类类型，或者 `nested_exception` 是 `E` 的不可访问或有歧义的基类，什么也不做。否则执行：

```cpp
if (auto p = dynamic_cast<const nested_exception*>(addressof(e)))
  p->rethrow_nested();
```

这里的 `dynamic_cast` 是一次交叉转换（cross-cast）：从 `E` 转到它的兄弟基类 `nested_exception`。交叉转换要求类是多态的，这就是第 2 段让 `nested_exception` 带虚析构函数的原因。

!!! pitfall "在 handler 之外调用 `throw_with_nested`"
    ```cpp run title="nested-outside.cpp"
    #include <cstdio>
    #include <exception>
    #include <stdexcept>

    int main() {
      try {
        std::throw_with_nested(std::runtime_error("outside"));  // 不在 handler 中
      } catch (const std::exception& e) {
        std::puts(e.what());
        std::rethrow_if_nested(e);   // nested_ptr() 为空：调用 std::terminate
      }
    }
    ```
    合成类型的 `nested_exception` 基类在构造时调用 `current_exception()`，不在 handler 里就保存了一个空指针。之后 `rethrow_if_nested` 会走到 `rethrow_nested()` 的空指针分支，调用 `std::terminate`（¶4），而不是因为没有内层异常就什么也不做。本机这个程序打印 `outside` 之后被终止。
