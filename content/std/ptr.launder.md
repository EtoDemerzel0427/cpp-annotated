---
title: 指针优化屏障 std::launder
summary: std::launder 的完整契约——Mandates 排除函数与 void、Preconditions 要求地址处有生命周期内的相似类型对象且可达字节不扩大、Returns 指向该对象、constexpr 条件；它不创建对象，只修正"指针指向哪个对象"
status: done
papers: P0137R1
related: basic.life, basic.compound, intro.object, conv.qual, expr.new, support.dynamic, expr.const
tags: 标准库, launder, 对象模型, 生命周期, UB
updated: 2026-10-18
---

C++17 的对象模型里，**指针值不只是地址**：一个指针值"指向某个对象"（[[basic.compound]]），同一地址上先后存在的不同对象，对应的指针值是不同的。大多数情况下，在旧对象的存储上创建新对象后，旧指针会**自动**指向新对象——这叫**透明替换**（[[g:transparently-replaceable]]，[[basic.life]] ¶9–¶10）。但透明替换有条件，不满足时旧指针仍然"指向"已死去的旧对象，通过它访问新对象是 UB。

`std::launder` 就是为这种情况准备的：给它一个**地址正确但"指向的对象不对"**的指针，它返回一个指向该地址处**当前那个对象**的指针。它的动机、透明替换的条件和典型用法已在 [[basic.life]] 中详细讨论，本页聚焦于库条款给出的**精确契约**。

```cpp
template<class T> constexpr T* launder(T* p) noexcept;
```

## Mandates：不能洗函数指针和 `void*`（¶1）

*Mandates*：`!is_function_v<T> && !is_void_v<T>` 为 `true`。

"Mandates" 在库条款中意味着：条件不满足时**程序非良构**（[[structure.specifications]]），必须给出诊断。这和"Constraints"（不满足则不参与重载决议）、"Preconditions"（不满足则 UB）是三个不同的法律层级。

```cpp title="launder-mandates.cpp" error
#include <new>

void f();
auto p = std::launder(&f);                      // error: T 是函数类型
auto q = std::launder(static_cast<void*>(nullptr));  // error: T 是 void
```

为什么排除？函数不是对象，不存在"在函数的存储上创建新函数"这回事；`void*` 不指向特定类型的对象，`launder` 无法确定要找哪个对象。

## Preconditions：三项要求（¶2）

!!! std
    `p` represents the address *A* of a byte in memory. An object *X* whose type is similar to `T` is located at the address *A*, and is either within its lifetime or is an array element subobject whose containing array object is within its lifetime. All bytes of storage that would be reachable through the result are reachable through `p`.

    `p` 表示内存中某个字节的地址 *A*。有一个类型与 `T` 相似的对象 *X* 位于地址 *A*，并且它处于生命周期内，或者是一个所在数组对象处于生命周期内的数组元素子对象。经由结果可达的所有存储字节，都可以经由 `p` 到达。

这是一个 *Preconditions*：违反任何一项，行为未定义。逐项拆解：

1. **`p` 表示一个字节的地址**。空指针、无效指针值（[[g:invalid-pointer-value]]）都不满足。所以 `std::launder(nullptr)` 是 UB（尽管实现上它什么也不做）。
2. **地址 *A* 处有一个类型与 `T` 相似（[[conv.qual]]）的对象 *X*，且处于生命周期内**。"相似"意味着 cv 限定可以不同：`launder` 一个 `const X*` 可以得到指向非 `const` 对象 `X` 的指针（类型仍是 `const X*`）。"或者是生命周期内数组的元素"这个补充是为了覆盖元素本身生命周期未开始（例如 `std::allocator<T>::allocate` 得到的数组，[[basic.life]]）但仍需对其形成指针的情形。**`launder` 不创建对象**：如果地址处根本没有 `T` 类型的对象（比如只是一个 `unsigned char` 缓冲区），前置条件不满足——这时应该用隐式对象创建或 `std::start_lifetime_as`（[[obj.lifetime]]）。
3. **可达性不扩大**：通过结果能到达的字节，都必须能通过 `p` 到达。可达性定义在 [[basic.compound]]：经由指向对象 *x* 的指针值可达的字节，是与 *x* 指针可互相转换的某个对象 *y* 所占据的存储——若 *y* 是数组元素，则是其**直接外围数组**所占据的存储。这一条防止用 `launder` 绕过 [[expr.add]] 的指针算术边界。

```cpp run title="launder-reachability.cpp" ub
#include <new>

int arr[2][3];

int main() {
    int* p = &arr[0][0];                 // 经由 p 可达：arr[0] 这个 int[3] 的 12 字节
    auto q = std::launder(reinterpret_cast<int(*)[3]>(p));
    // q 将指向 arr[0]（类型为 int[3]，位于同一地址，生命周期内）；
    // 但 arr[0] 是 arr 的元素，经由 q 可达的是整个 arr（24 字节），
    // 超出了经由 p 可达的范围 —— 违反 ¶2 的最后一项：UB
    return q[1][0];
}
```

可达性规则的工程意义是：编译器可以假设"通过 `p` 只能碰到这 12 个字节"（例如做别名分析），`launder` 不能被用来打破这一假设。

## Returns 与 constexpr（¶3–¶4）

¶3 *Returns*：一个类型为 `T*`、**指向 *X*** 的值。

¶4 *Remarks*：对这个函数的调用可以出现在**核心常量表达式**中，当且仅当其实参的（转换后）值可以用来代替这次函数调用。换言之，在常量求值中 `launder` 只能是"恒等变换"——实参本身已经指向正确的对象时才能用。常量求值器跟踪每个指针所指的对象，没有"指针指向旧对象"需要修正的空间；如果实参指向的对象不是 *X*，调用就不是常量表达式。

## 什么时候需要它（¶5 注 1）

注 1 用一句话概括了需要 `launder` 的场合：

!!! std
    If a new object is created in storage occupied by an existing object of the same type, a pointer to the original object can be used to refer to the new object unless its complete object is a const object or it is a base class subobject; in the latter cases, this function can be used to obtain a usable pointer to the new object.

    若在一个已有对象占据的存储中创建同类型的新对象，指向原对象的指针可用于指代新对象，除非其完整对象是 const 对象或它是基类子对象；在后两种情况下，可以用本函数获得可用的指向新对象的指针。

在 C++20 删除了 [[basic.life]] 中"不能有 const 或引用成员"的条件之后，需要 `launder` 的场合大幅缩小，主要剩下：

| 场景 | 为什么不能透明替换 |
|---|---|
| 替换 `const` 完整对象（动态存储期） | [[basic.life]] ¶9：o1 不能是 const 完整对象 |
| 替换基类子对象 | 基类子对象是潜在重叠子对象，透明替换要求两者都不是 |
| 从字节缓冲区 `reinterpret_cast` 得到对象指针 | 转型结果仍指向缓冲区（`unsigned char`），不指向在其中创建的对象（[[intro.object]] "提供存储"） |
| 替换后类型不同 | 透明替换要求同类型（忽略顶层 cv） |

¶6 例 1 是第一种情况的标准例子：

```cpp run title="launder-const.cpp" ok
#include <new>

struct X { int n; };

int main() {
    const X* p = new const X{3};
    const int a = p->n;
    new (const_cast<X*>(p)) const X{5};  // p 不指向新对象：其完整对象是 const
    // const int b = p->n;               // UB
    const int c = std::launder(p)->n;    // OK
    delete std::launder(p);
    return a + c == 8 ? 0 : 1;
}
```

第三种情况是最常见的实际用途——手写的 `optional`/`variant`/小缓冲区优化：

```cpp run title="launder-buffer.cpp" ok
#include <new>
#include <string>

template<class T>
class Slot {
    alignas(T) unsigned char buf_[sizeof(T)];
public:
    template<class... A> void emplace(A&&... a) { ::new (buf_) T(static_cast<A&&>(a)...); }
    T& get() { return *std::launder(reinterpret_cast<T*>(buf_)); }   // 必须 launder
    void reset() { get().~T(); }
};

int main() {
    Slot<std::string> s;
    s.emplace("hello");
    bool ok = s.get() == "hello";
    s.reset();
    return ok ? 0 : 1;
}
```

## 实现：零指令，只对优化器生效

!!! impl
    libc++ 的实现就是 `return __builtin_launder(__p);`（`<__new/launder.h>`），并注明"编译器会诊断 `__builtin_launder` 的误用，因此不需要额外的 `static_assert`"——¶1 的 Mandates 正是由内建函数实现的：Clang 对函数指针和 `void*` 报 "function pointer argument to '__builtin_launder' is not allowed" 等错误。

    `__builtin_launder` 在通常情况下**不产生任何机器指令**。它的作用是在中间表示中切断指针的"来历"：优化器不能再把通过结果指针的读取与通过原指针观察到的值联系起来（例如把 `const` 成员的旧值传播过来）。在开启 `-fstrict-vtable-pointers` 时，Clang 还把它作为 vptr 不变性假设的屏障。

!!! pitfall "`launder` 不是万能的\"让 UB 消失\"按钮"
    - 它不创建对象，不开始生命周期——地址处必须**已经**有那个对象。
    - 它不能扩大可达范围——不能拿元素指针换整个数组的指针。
    - 它不能修复类型不对的访问——`launder(reinterpret_cast<float*>(&i))` 在 `&i` 处没有 `float` 对象，前置条件不满足。

## 小结

!!! summary
    - Mandates：`T` 不能是函数类型或 `void`——违反则非良构。
    - Preconditions：`p` 是有效地址；该地址处有生命周期内的、类型与 `T` 相似的对象；结果的可达字节不超出 `p` 的可达字节——违反则 UB。
    - Returns：指向该对象的 `T*`；常量求值中只能作为恒等变换使用。
    - 典型场合：替换 const 完整对象、替换基类子对象、从字节缓冲区取出对象指针。
    - 零运行时开销，只约束优化器。
