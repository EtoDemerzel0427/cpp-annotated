---
title: 指针优化屏障 std::launder
summary: std::launder 的契约：给它一个地址正确、但指向旧对象（或指向存储而非对象）的指针，它返回指向该地址上现存对象的指针；它不创建对象，也不能扩大指针可访问的范围。
status: done
papers: P0137R1
related: basic.life, basic.compound, intro.object, conv.qual, expr.new, support.dynamic, expr.const
tags: 标准库, launder, 对象模型, 生命周期, UB
updated: 2026-10-19
---

!!! tldr
    - 指针不只是地址，它指向某个特定的对象。在旧对象的位置上创建新对象后，旧指针通常自动指向新对象，但有例外；`std::launder` 处理这些例外。
    - 需要它的典型场合：替换 const 完整对象、替换基类子对象、从 `unsigned char` 缓冲区 `reinterpret_cast` 出对象指针。
    - 前置条件：地址上必须已经有一个类型相似、处于生命周期内的对象，结果能访问的字节不能多于原指针。违反就是未定义行为。
    - `T` 是函数类型或 `void` 时程序非良构。`launder` 不产生机器指令，只约束优化器。

## 为什么需要它

```cpp run title="launder-const.cpp" ok
#include <new>

struct X { int n; };

int main() {
  const X* p = new const X{3};
  const int a = p->n;
  new (const_cast<X*>(p)) const X{5};  // 完整对象是 const：p 不指向新对象
  // const int b = p->n;               // UB
  const int c = std::launder(p)->n;    // OK，c == 5
  delete std::launder(p);
  return a + c == 8 ? 0 : 1;
}
```

这是标准第 6 段的例子（加上了 `delete`）。C++ 的指针值指向一个具体的对象，而不只是一个地址（[[basic.compound]]）。同一地址上先后存在的两个对象，指向它们的指针值是不同的。

多数情况下，在旧对象的存储上创建同类型的新对象后，旧指针会自动指向新对象，这称为**透明替换**（[[g:transparently-replaceable]]，[[basic.life#9]]）。但旧对象是 const 完整对象时，透明替换不成立：`p` 仍然指向已经结束生命周期的旧对象，通过它读 `n` 是未定义行为。编译器可以据此假设 `p->n` 还是 3。

`std::launder(p)` 返回一个指向该地址上当前对象（新的 `X{5}`）的指针。透明替换的完整条件和更多例子见 [[basic.life]]。

¶5 注 1 概括了需要 `launder` 的场合：在已有对象的存储里创建同类型的新对象时，指向原对象的指针可以用来访问新对象，除非原对象的完整对象是 const，或者原对象是基类子对象；这两种情况下要用 `launder`。

| 场景 | 为什么旧指针不能用 |
|---|---|
| 替换 const 完整对象 | 透明替换要求旧对象不是 const 完整对象（[[basic.life#9]]） |
| 替换基类子对象 | 基类子对象可能与其他对象重叠，不参与透明替换（[[intro.object#2]]） |
| 从字节缓冲区 `reinterpret_cast` 出对象指针 | 转型的结果仍指向缓冲区数组，不指向在其中创建的对象（[[intro.object]] 中的提供存储） |
| 新对象类型不同 | 透明替换要求类型相同（忽略顶层 cv） |

第三种是实际代码里最常见的，手写的 `optional`、`variant`、小缓冲区优化都会遇到：

```cpp run title="launder-buffer.cpp" ok
#include <new>
#include <string>

template<class T>
class Slot {
  alignas(T) unsigned char buf_[sizeof(T)];
public:
  template<class... A> void emplace(A&&... a) {
    ::new (buf_) T(static_cast<A&&>(a)...);
  }
  T& get() {   // 必须 launder：转型结果仍指向 buf_
    return *std::launder(reinterpret_cast<T*>(buf_));
  }
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

另一种写法是在 `emplace` 里保存 placement new 返回的指针，以后都用它，就不需要 `launder`，代价是多存一个指针。

## 签名与 Mandates（¶1）

```cpp
template<class T> constexpr T* launder(T* p) noexcept;
```

¶1 Mandates：`!is_function_v<T> && !is_void_v<T>` 为 `true`。库条款里的 Mandates 指条件不满足时程序非良构，编译器必须诊断（[[structure.specifications]]）。

```cpp title="launder-mandates.cpp" error
#include <new>

void f();
auto p = std::launder(&f);   // error: T 是函数类型
auto q = std::launder(static_cast<void*>(nullptr));  // error: T 是 void
```

函数不是对象，不存在在函数的存储上创建新函数的情形；`void*` 不指向特定类型的对象，`launder` 无从知道要找哪个对象。本机 Clang 对两行分别报 "function pointer argument to '__builtin_launder' is not allowed" 和 "void pointer argument ..."。

## 前置条件（¶2）

¶2 的 Preconditions 有三项，违反任何一项都是未定义行为：

1. `p` 表示内存中某个字节的地址 *A*。空指针和无效指针值不满足，所以 `std::launder(nullptr)` 是未定义行为，尽管实际上它什么也不做。
2. 地址 *A* 上有一个对象 *X*，它的类型与 `T` 相似（只差 cv 限定，见 [[conv.qual]]），并且 *X* 处于生命周期内，或者是一个处于生命周期内的数组的元素。后半句覆盖的是 `std::allocator<T>::allocate` 这类情形：数组已经存在，元素的生命周期还没开始，但仍然需要指向元素的指针。
3. 通过结果能访问到的每个字节，通过 `p` 也都能访问到。

第 2 项意味着 `launder` 不创建对象，也不开始任何对象的生命周期。地址上只有一个 `unsigned char` 缓冲区、没有 `T` 对象时，应当先创建对象：隐式对象创建或 `std::start_lifetime_as`（[[obj.lifetime]]）。

第 3 项里的能访问到，标准称为**可达**（reachable，[[basic.compound]]）。指向对象 *x* 的指针可达的字节，是 *x* 所占的存储；如果 *x* 是数组元素，则是整个数组所占的存储（严格的定义还要考虑与 *x* 指针可互相转换的对象）。这一项防止用 `launder` 绕过指针算术的边界：

```cpp run title="launder-reachability.cpp" ub
#include <new>

int arr[2][3];

int main() {
  int* p = &arr[0][0];   // 经由 p 可达：arr[0] 的 12 字节
  auto q = std::launder(reinterpret_cast<int(*)[3]>(p));
  // q 会指向 arr[0]；经由它可达的是整个 arr（24 字节）
  return q[1][0];        // UB：违反 ¶2 的可达性要求
}
```

`arr[0]` 本身是数组 `arr` 的元素，所以指向它的指针可以走到 `arr[1]`；而 `p` 指向的 `arr[0][0]` 只能在 `arr[0]` 之内移动。编译器可以假设通过 `p` 只会访问这 12 个字节，`launder` 不能打破这一假设。这个例子在本机运行时没有任何症状，sanitizer 也不报告。

## 返回值与常量求值（¶3–¶4）

¶3 Returns：一个指向 *X* 的 `T*`。

¶4 在常量表达式中，只有当实参本身就可以代替这次调用时，`launder` 的调用才算核心常量表达式。也就是说，常量求值中的 `launder` 只能是恒等变换。常量求值器知道每个指针指向哪个对象，不会出现需要修正的旧指针；实参指向的不是 *X*，调用就不是常量表达式。

## 实现

!!! impl "libc++：一个内建函数"
    libc++ 的 `std::launder` 就是 `return __builtin_launder(__p);`，第 1 段的 Mandates 由这个内建函数检查。

    `__builtin_launder` 一般不生成任何指令。它在中间表示中切断结果指针与原指针的联系，优化器不能再把通过原指针得知的值（例如 const 成员的旧值）用在通过结果指针的读取上。开启 `-fstrict-vtable-pointers` 时，Clang 还把它当作虚表指针不变假设的屏障。

!!! pitfall "`launder` 修不了的错误"
    - 地址上没有对象时，它不会创建对象。
    - 它不能扩大可达范围，不能把元素指针变成整个数组的指针。
    - 它不能修复类型错误：`std::launder(reinterpret_cast<float*>(&i))` 在 `&i` 处没有 `float` 对象，前置条件不满足。
