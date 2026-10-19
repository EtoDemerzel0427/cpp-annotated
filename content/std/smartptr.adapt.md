---
title: out_ptr 与 inout_ptr
summary: C++23 的两个适配器，把智能指针直接传给 C 风格的 T** 输出形参：临时对象在完整表达式结束时才把结果交回智能指针；shared_ptr 用 out_ptr 必须带删除器，不能用 inout_ptr。
status: done
covers: *
related: smartptr, unique.ptr, util.smartptr.shared, memory, class.temporary, intro.races
tags: 标准库, 智能指针, out_ptr, C 互操作
papers: P1132R8
updated: 2026-10-19
---

!!! tldr
    - `f(std::out_ptr(sp))` 生成一个临时对象，C 函数把结果写进它内部的裸指针，临时对象在完整表达式结束时析构，再把结果 `reset` 进 `sp`。
    - `out_ptr` 在调用 C 函数之前就清空 `sp`；C 函数需要读取并处置旧值时，用 `inout_ptr`，它在最后 `release()` 旧值而不是删除它。
    - 在同一个完整表达式里读取 `sp`，看到的还是清空后的值。
    - `shared_ptr` 配 `out_ptr` 时必须给出删除器，否则非良构；`shared_ptr` 配 `inout_ptr` 一律非良构。
    - 可以传给 `void**` 形参，但同一个临时对象只能转换一次。

## 为什么需要它

很多 C API 通过输出指针形参返回新分配的资源，例如 `int sqlite3_open(const char*, sqlite3**)`。把结果交给 `unique_ptr`，传统的写法需要一个中间裸指针：

```cpp
sqlite3* raw = nullptr;
int rc = sqlite3_open(name, &raw);
std::unique_ptr<sqlite3, closer> db(raw);   // 中间抛出异常或提前返回，raw 就泄漏了
```

C++23 的 `out_ptr` 和 `inout_ptr`（[[P1132R8]]）把这三步合成一个表达式：

```cpp run title="out-ptr.cpp" ok
#include <memory>
#include <cstdio>
#include <cstdlib>

// 模拟 C API
struct widget { int id; };
extern "C" int widget_create(widget** out, int id) {
  if (id < 0) return -1;                     // 失败时不写 *out
  *out = static_cast<widget*>(std::malloc(sizeof(widget)));
  (*out)->id = id;
  return 0;
}
extern "C" int widget_recreate(widget** inout, int id) {
  std::free(*inout);                         // 先释放旧对象
  *inout = nullptr;
  return widget_create(inout, id);
}
extern "C" int any_create(void** out) {
  *out = std::malloc(4);
  return 0;
}
struct free_deleter {
  void operator()(void* p) const noexcept { std::free(p); }
};

int main() {
  std::unique_ptr<widget, free_deleter> w;
  if (widget_create(std::out_ptr(w), 7) == 0)
    std::printf("created %d\n", w->id);
  widget_recreate(std::inout_ptr(w), 8);
  std::printf("recreated %d\n", w->id);

  std::shared_ptr<widget> s;
  widget_create(std::out_ptr(s, free_deleter{}), 9);
  std::printf("shared %d\n", s->id);

  std::unique_ptr<int, free_deleter> raw;
  any_create(std::out_ptr(raw));             // int* 经 operator void**() 传给 void**
  std::printf("void** ok: %d\n", raw != nullptr);
}
```

本机输出 `created 7`、`recreated 8`、`shared 9`、`void** ok: 1`，ASan 和 UBSan 都没有报告。`widget_recreate` 自己释放了旧对象，`inout_ptr` 不会让 `unique_ptr` 再释放一次。

## out_ptr_t 的工作方式 [out.ptr.t]

`std::out_ptr(s, args...)` 返回一个 `out_ptr_t<Smart, Pointer, Args...>` 临时对象。它有三个说明用的成员：对目标智能指针的引用 `s`，保存额外实参（通常是删除器）的 `tuple<Args...> a`，以及一个裸指针 `p`。C 函数通过转换函数拿到 `&p`，把结果写进 `p`。临时对象在完整表达式结束时析构（[[class.temporary]]），析构函数再把 `p` 交给 `s`。

### 构造：先清空目标（¶6–¶7）

¶6 构造函数保存引用和实参，值初始化 `p`，然后清空目标：`s.reset()` 良构就调用它，否则 `Smart` 可默认构造就执行 `s = Smart()`，两者都不行则非良构。

所以智能指针原来持有的资源在调用 C 函数之前就释放了。对纯输出形参这是对的，旧值反正要被覆盖。如果 C 函数需要读取旧值，要用 `inout_ptr`。

¶7 注 2 说明构造函数故意不是 `noexcept`：实现可以在构造时就为 `shared_ptr` 预先分配控制块，这样析构函数里就不必再分配，也就不会抛出异常。

### 析构：交回结果（¶8–¶9）

¶8 令 `SP` 为 *POINTER_OF_OR*(Smart, Pointer)，即智能指针自己的 `pointer` 类型（[[memory]]）。¶9 如果 `p` 非空，就展开保存的实参调用 `s.reset(static_cast<SP>(p), args...)`；这个表达式不良构时改用 `s = Smart(static_cast<SP>(p), args...)`；都不行则非良构。`p` 为空（C 函数失败，没有写入）时什么也不做，`s` 保持构造时清空后的状态。

### 转换函数（¶10–¶17）

`operator Pointer*()` 返回 `p` 的地址。`operator void**()` 用于形参是 `void**` 的 API：¶12 要求 `Pointer` 不是 `void*`，¶13 要求 `Pointer` 是指针类型；¶15 它返回某个 `void**` 值 `v`，`*v` 的初值等于 `static_cast<void*>(p)`，之后对 `*v` 的修改会在析构时反映到 `p` 上。¶16 在临时对象的生命周期之外访问 `*v` 是 UB。

标准没有直接规定 `operator void**()` 返回 `reinterpret_cast<void**>(&p)`。把 `int**` 重新解释为 `void**` 再通过它写入，是用 `void*` 类型去访问一个 `int*` 对象，违反类型别名规则（[[basic.lval]]）；在 `T*` 和 `void*` 表示不同的平台上更是错的。所以实现可以在对象里另存一个 `void*`，析构时再转换回来。¶17 注 3 指出，`reinterpret_cast` 对某些实现是可行的策略。

¶5 对同一个对象求值两个转换函数可能冲突（[[intro.races]]）。¶10 和 ¶14 的前置条件进一步要求：调用了其中一个，就不能再调用另一个。实际意义是同一个临时对象只能转换一次。

### shared_ptr 必须带删除器（¶3）

```cpp title="out-ptr-shared.cpp" error
#include <memory>
struct widget;
extern "C" int widget_create(widget** out, int id);
void f() {
    std::shared_ptr<widget> s;
    widget_create(std::out_ptr(s), 1);   // error: 没有删除器
}
```

¶3 规定，如果 `Smart` 是 `shared_ptr` 的特化且没有额外实参，程序非良构。注 1 解释了原因：`shared_ptr::reset(p)` 会改用 `delete` 作删除器，而从 C API 得到的资源几乎从不该用 `delete` 释放，不给删除器多半是写错了。本机 libc++ 以一条 `static_assert` 拒绝，消息是 `Using std::shared_ptr<> without a deleter in std::out_ptr is not supported.`

¶3 还要求 `Pointer` 满足 *Cpp17NullablePointer*。¶4 允许程序为依赖于自定义类型的 `out_ptr_t` 写特化，不必满足主模板的要求，这样可以适配 COM 的 `CComPtr` 之类的自定义智能指针。

## out_ptr [out.ptr]

```cpp
template<class Pointer = void, class Smart, class... Args>
  constexpr auto out_ptr(Smart& s, Args&&... args);
```

¶1 如果显式给出了非 `void` 的 `Pointer`，C 函数看到的指针类型就是它，否则是智能指针的 `pointer` 类型。显式给出在 C 函数的形参类型与智能指针不一致时有用，标准的例子是 `std::out_ptr<std::FILE*>(file_ptr)`。¶2 返回 `out_ptr_t<Smart, P, Args&&...>(s, std::forward<Args>(args)...)`。保存的是 `Args&&`，也就是引用，所以传入临时的删除器也没问题：它和 `out_ptr_t` 一样活到完整表达式结束。

## inout_ptr [inout.ptr.t] [inout.ptr]

¶1 `inout_ptr_t` 用于这样的 C 函数：它先读取并可能释放旧值，再写入新值。标准的例子中，`star_fish_populate(std::inout_ptr(peach), ...)` 由 C 函数负责处置 `peach` 原来的对象。

¶6 构造时 `p` 初始化为 `smart.get()`，`Smart` 本身是裸指针类型时为 `smart`，所以 C 函数看到的是旧值。¶7 实现可以在构造函数里就调用 `s.release()`。

¶10–¶11 析构时，如果构造函数没有 `release()`，先执行 `s.release()`，放弃旧值的所有权，因为 C 函数已经负责处置它；然后如果 `p` 非空，就像 `out_ptr_t` 一样 `s.reset(static_cast<SP>(p), args...)`。这里用 `release()` 而不是 `reset()`，是因为旧资源已经由 C 函数释放或复用，智能指针不能再删一次。C 函数把指针置空时，`release()` 照样执行而不再 `reset`，`s` 最终为空。

¶11.1 `Smart` 是裸指针时，无条件地赋值 `s = Smart(static_cast<SP>(p), ...)`，没有 `if (p)`。[[LWG3897]] 之前的措辞带着这个判断，C 函数把指针置空后，用户的裸指针会保留已经释放的旧值。本机 libc++ 已按新措辞实现：C 函数释放并置空后，原来的裸指针变成了空指针。

¶3 规定，`Smart` 是 `shared_ptr` 的特化时程序非良构，不论有没有删除器。注 1 解释，在共享所有权模型下无法正确地取得资源的独占所有权：`shared_ptr` 没有 `release()`，C 函数释放旧资源后，其他 `shared_ptr` 副本就悬空了。

`inout_ptr_t` 的转换函数（¶12–¶19）与 `out_ptr_t` 相同。

## 常见误解

!!! pitfall "同一个完整表达式里智能指针已经更新"
    ```cpp run title="same-expr.cpp" ok
    #include <memory>
    #include <cstdio>
    #include <cstdlib>
    struct widget { int id; };
    extern "C" int widget_create(widget** out, int id) {
      *out = static_cast<widget*>(std::malloc(sizeof(widget)));
      (*out)->id = id;
      return 0;
    }
    struct free_deleter {
      void operator()(void* p) const noexcept { std::free(p); }
    };
    int main() {
      std::unique_ptr<widget, free_deleter> w;
      bool ok = widget_create(std::out_ptr(w), 7) == 0
                && w != nullptr;                 // w 尚未更新
      std::printf("%d %d\n", ok, w != nullptr);  // 0 1
    }
    ```
    结果在临时对象析构时才写回，也就是完整表达式结束时。同一个表达式里读取 `w`，看到的是构造函数清空后的空指针。`if (create(std::out_ptr(p)) == 0 && p->ready())` 这样的写法会解引用空指针。把调用和使用分成两条语句。

## 小结

| | `out_ptr` | `inout_ptr` |
|---|---|---|
| 构造时 | 清空目标 | `p` 取旧值 |
| C 函数 | 写入新值 | 处置旧值，写入新值 |
| 析构时 | `p` 非空则 `reset(p)` | `release()` 旧值，`p` 非空则 `reset(p)` |
| `shared_ptr` | 必须带删除器 | 非良构 |
