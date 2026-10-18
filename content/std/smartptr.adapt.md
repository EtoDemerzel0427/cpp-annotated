---
title: out_ptr 与 inout_ptr
summary: 把智能指针接到 C 风格"T** 输出形参"上的适配器——临时对象在完整表达式结束时才把结果 reset 回智能指针；shared_ptr 必须带删除器、不能用于 inout_ptr；void** 转换；同一完整表达式中读取智能指针的陷阱
status: done
covers: *
related: smartptr, unique.ptr, util.smartptr.shared, memory, class.temporary, intro.races
tags: 标准库, 智能指针, out_ptr, C 互操作
papers: P1132R8
updated: 2026-10-18
---

大量 C API 用"输出指针形参"返回新分配的资源：

```c
int sqlite3_open(const char* filename, sqlite3** ppDb);
HRESULT CoCreateInstance(..., void** ppv);
int av_dict_set(AVDictionary** pm, const char* key, const char* value, int flags);   // 可能先释放 *pm
```

在 C++ 里把结果交给 `unique_ptr`，传统写法要一个中间裸指针：

```cpp
sqlite3* raw = nullptr;
int rc = sqlite3_open(name, &raw);
std::unique_ptr<sqlite3, closer> db(raw);   // 若中间抛异常或提前 return，raw 就泄漏了
```

C++23 的 `out_ptr`/`inout_ptr`（[[P1132R8]]）把这三步压成一个表达式：`sqlite3_open(name, std::out_ptr(db))`。

## 工作原理

`std::out_ptr(s, args...)` 返回一个 `out_ptr_t<Smart, Pointer, Args...>` **临时对象**，其中保存：

- `Smart& s`：目标智能指针的引用；
- `tuple<Args...> a`：额外实参（通常是删除器）；
- `Pointer p`：一个值初始化的裸指针。

C 函数拿到的是 `&p`（经由 `operator Pointer*()`），把结果写进 `p`。**临时对象在完整表达式结束时析构**（[[class.temporary]]），析构函数把 `p` 交给智能指针：`s.reset(static_cast<SP>(p), args...)`。

## `out_ptr_t`（[out.ptr.t]）

### ¶3：约束

- `Pointer` 须满足 *Cpp17NullablePointer*。
- **若 `Smart` 是 `shared_ptr` 的特化且 `sizeof...(Args) == 0`，程序 {{ill-formed}}。** 注 1 解释：`shared_ptr::reset(p)` 会用 `default_delete` 替换原来的删除器，而从 C API 得到的资源几乎从不应该用 `delete` 释放——不给删除器多半是用户错误。

¶4：依赖程序定义类型的程序定义特化不必满足主模板的要求——允许为自定义智能指针（例如 COM 的 `CComPtr`）定制。

### ¶5：转换函数之间可能冲突

对同一 `out_ptr_t` 对象求值转换函数可能冲突（[[intro.races]]）。实际意义是：同一个临时对象只能被转换**一次**——¶10 与 ¶14 分别要求 `operator Pointer*()` 与 `operator void**()` 不曾在 `*this` 上调用过对方。

### 构造函数（¶6–¶7）

保存引用与实参、值初始化 `p`，然后**清空目标**：若 `s.reset()` 良构就调用它，否则若 `Smart` 可默认构造就 `s = Smart()`，否则 {{ill-formed}}。

这一步意味着：智能指针原有的资源**在调用 C 函数之前就被释放了**。对"输出"语义这是对的——旧值反正要被覆盖。若 C 函数需要**读**旧值，要用 `inout_ptr`。

¶7 注 2：构造函数故意不是 `noexcept`，以允许实现在构造时就为 `shared_ptr` 预先分配控制块（从而析构函数中不必再分配、不会抛异常）。

### 析构函数（¶8–¶9）

令 `SP` 为 *POINTER_OF_OR*(Smart, Pointer)（[[memory]]）。**若 `p` 非空**，用 `apply` 展开保存的实参，调用 `s.reset(static_cast<SP>(p), args...)`；若该表达式不良构，则 `s = Smart(static_cast<SP>(p), args...)`；都不行则 {{ill-formed}}。`p` 为空（C 函数失败、没写）时什么也不做，`s` 保持构造函数里清空后的状态。

### 转换函数（¶10–¶17）

- `operator Pointer*()`：返回 `addressof(const_cast<Pointer&>(p))`。
- `operator void**()`：*Constraints* `Pointer` 不是 `void*`；*Mandates* `Pointer` 是指针类型。返回一个 `void**` 值 `v`，使得 `*v` 初始为 `static_cast<void*>(p)`，且对 `*v` 的修改会在析构时反映到 `p` 上。¶16：在 `*this` 生命周期之外访问 `*v` 是 UB。¶17 注 3：`reinterpret_cast<void**>(static_cast<Pointer*>(*this))` 对某些实现是可行的策略——但对另一些实现（例如 `T*` 与 `void*` 表示不同的平台），实现需要在对象里另存一个 `void*`，析构时再转换回去。这就是标准把它写成"返回某个值 `v` 使得……"而不是直接规定 `reinterpret_cast` 的原因：`T**` 与 `void**` 之间的 `reinterpret_cast` 再解引用，按 [[basic.lval]] 是类型别名违规。

## `out_ptr`（[out.ptr]）

```cpp
template<class Pointer = void, class Smart, class... Args>
  constexpr auto out_ptr(Smart& s, Args&&... args);
```

¶1：`P` 是 `Pointer`（若显式给出且非 `void`），否则 *POINTER_OF*(Smart)。¶2：返回 `out_ptr_t<Smart, P, Args&&...>(s, std::forward<Args>(args)...)`。注意保存的是 `Args&&`——**引用**，所以传入临时删除器也没问题：它活到完整表达式结束，与 `out_ptr_t` 一样长。

## `inout_ptr_t` 与 `inout_ptr`（[inout.ptr.t]、[inout.ptr]）

用于 C 函数**先读取（并可能释放）旧值、再写入新值**的情形（例如 `realloc` 风格的 API）。

- ¶3：`Pointer` 须满足 *Cpp17NullablePointer*；**若 `Smart` 是 `shared_ptr` 的特化，程序 {{ill-formed}}**（不论有没有删除器）。注 1：无法从共享所有权模型中正确地取得资源的独占所有权——`shared_ptr` 没有 `release()`，C 函数释放旧资源时，其他 `shared_ptr` 副本会悬空。
- ¶6：构造时 `p` 初始化为 `smart.get()`（若 `Smart` 本身是裸指针类型，则为 `smart`）——C 函数看到的是旧值。
- ¶7：实现**可以**在构造函数里调用 `s.release()`。
- ¶10–¶11：析构时，若构造函数没有 `release()`，先执行 `s.release()`（*release-statement*）——放弃旧值的所有权，因为 C 函数已经负责处理它；然后若 `p` 非空，`s.reset(static_cast<SP>(p), args...)`（或 `s = Smart(...)`）。`Smart` 是裸指针时直接赋值。

`release()` 而不是 `reset()`：旧资源已经由 C 函数释放（或复用），智能指针绝不能再删一次。若 C 函数把指针置空，`release()` 照样执行而不再 `reset`，`s` 最终为空。`Smart` 本身是裸指针时，(11.1) **无条件**赋值 `s = Smart(static_cast<SP>(p), ...)`——这是 [[LWG3897]] 的修正：此前裸指针版本也带着 `if (p)` 判断，C 函数把指针置空后，用户的裸指针仍保留着已被释放的旧值。

## 示例

```cpp title="out-ptr.cpp" ok
#include <memory>
#include <cstdio>
#include <cstdlib>

// 模拟 C API
struct widget { int id; };
extern "C" int widget_create(widget** out, int id) {
    if (id < 0) return -1;                       // 失败时不写 *out
    *out = static_cast<widget*>(std::malloc(sizeof(widget)));
    (*out)->id = id;
    return 0;
}
extern "C" int widget_recreate(widget** inout, int id) {   // 先释放旧的，再写入新的
    std::free(*inout);
    *inout = nullptr;
    return widget_create(inout, id);
}
extern "C" int any_create(void** out) { *out = std::malloc(4); return 0; }
struct free_deleter { void operator()(void* p) const noexcept { std::free(p); } };

int main() {
    std::unique_ptr<widget, free_deleter> w;
    if (widget_create(std::out_ptr(w), 7) == 0) std::printf("created %d\n", w->id);
    widget_recreate(std::inout_ptr(w), 8);                 // 旧对象由 C 函数释放，unique_ptr 不再重复释放
    std::printf("recreated %d\n", w->id);

    std::shared_ptr<widget> s;
    widget_create(std::out_ptr(s, free_deleter{}), 9);     // shared_ptr 必须显式给删除器
    std::printf("shared %d\n", s->id);

    std::unique_ptr<int, free_deleter> raw;
    any_create(std::out_ptr(raw));                          // Pointer = int*，经 operator void**() 传给 void** 形参
    std::printf("void** ok: %d\n", raw != nullptr);
}
```

ASan/LSan 下运行无报告。`shared_ptr` 不给删除器则被拒绝：

```cpp title="out-ptr-shared-no-deleter.cpp" error
#include <memory>
struct widget;
extern "C" int widget_create(widget** out, int id);
void f() {
    std::shared_ptr<widget> s;
    widget_create(std::out_ptr(s), 1);    // error: shared_ptr 且没有删除器实参（[out.ptr.t]/3）
}
```

libc++ 的诊断："Using std::shared_ptr<> without a deleter in std::out_ptr is not supported."

!!! pitfall "同一完整表达式里智能指针还没更新"
    结果是在临时对象**析构**时才写回的，即完整表达式结束时。在同一个表达式里读取智能指针，看到的是构造函数清空后的值：

    ```cpp title="out-ptr-same-expr.cpp" ok
    #include <memory>
    #include <cstdio>
    #include <cstdlib>
    struct widget { int id; };
    extern "C" int widget_create(widget** out, int id) {
        *out = static_cast<widget*>(std::malloc(sizeof(widget))); (*out)->id = id; return 0;
    }
    struct free_deleter { void operator()(void* p) const noexcept { std::free(p); } };
    int main() {
        std::unique_ptr<widget, free_deleter> w;
        bool ok = widget_create(std::out_ptr(w), 7) == 0 && w != nullptr;   // 同一完整表达式：w 尚未更新
        std::printf("same full-expression: %d; afterwards: %d\n", ok, w != nullptr);   // 0; 1
    }
    ```

    `if (create(std::out_ptr(p)) == 0 && p->ready())` 这样的写法甚至会解引用空指针。把调用与使用分成两条语句。

## 小结

- `out_ptr`：构造时清空目标，C 函数写入临时裸指针，完整表达式结束时 `reset` 回去（`p` 为空则不 reset）。
- `inout_ptr`：C 函数看到旧值并负责处置；析构时 `release()` 旧值再 `reset` 新值。
- `shared_ptr`：`out_ptr` 必须带删除器；`inout_ptr` 完全禁止。
- 可以传给 `void**` 形参，但同一临时对象只能转换一次，结果在完整表达式结束前不可见。
