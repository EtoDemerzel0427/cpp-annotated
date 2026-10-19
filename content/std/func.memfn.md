---
title: 函数模板 mem_fn
summary: mem_fn(pm) 把成员指针包装成能用 f(obj, args...) 调用的函数对象；它是简单调用包装器，调用模式为 invoke(pmd, call_args...)，所以对象、指针、智能指针、reference_wrapper 都能作为第一个实参。
status: done
related: func.require, func.bind.partial, func.not.fn, expr.mptr.oper, function.objects
tags: 标准库, functional, mem_fn, 成员指针
updated: 2026-10-19
---

!!! tldr
    - 成员指针不能写成 `pm(obj)` 来调用；`std::mem_fn(pm)` 返回一个可以这样调用的函数对象。
    - 调用经过 *INVOKE*，第一个实参可以是对象、派生类对象、裸指针、智能指针或 `reference_wrapper`。
    - 结果是简单调用包装器：可以复制和赋值，这些操作都是不抛异常的 `constexpr` 函数。
    - Ranges 算法本来就经 `std::invoke` 调用谓词和投影，可以直接传成员指针，不需要 `mem_fn`。

## 把成员指针变成函数对象

```cpp run title="mem_fn.cpp" ok
#include <functional>
#include <algorithm>
#include <memory>
#include <string>
#include <vector>
#include <cstdio>
struct Person {
  std::string name; int age;
  bool adult() const { return age >= 18; }
};
int main() {
  std::vector<Person> ps{{"a", 20}, {"b", 10}};
  auto adult = std::mem_fn(&Person::adult);
  auto age = std::mem_fn(&Person::age);
  std::printf("%td\n", std::count_if(ps.begin(), ps.end(), adult));   // 1
  auto up = std::make_unique<Person>(Person{"c", 30});
  std::printf("%d %d %d\n", age(ps[1]), age(&ps[0]), age(up));       // 对象、指针、智能指针
  auto copy = adult;  copy = adult;                                   // 可复制、可赋值
  std::printf("%d\n", copy(std::ref(ps[0])));                         // reference_wrapper 也行
}
```

成员指针是可调用类型，但不是函数对象类型（[[function.objects]]）：`pmf(obj)` 不是合法表达式。经典算法如 `std::count_if` 用 `pred(*it)` 调用谓词，只接受能写成 `f(x)` 的东西。`mem_fn` 就是把 `&Person::adult` 变成这种形态的适配器。

## 规格 [func.memfn]

```cpp
template<class R, class T> constexpr unspecified mem_fn(R T::* pm) noexcept;
```

形参类型 `R T::*` 同时匹配数据成员指针（`R` 是对象类型，如 `int`）和成员函数指针（`R` 是函数类型，如 `bool() const`）。

¶1 `mem_fn` 返回一个简单调用包装器（[[g:simple-call-wrapper]]）`fn`。它的目标对象 `pmd` 类型为 `R T::*`，用 `pm` 直接非列表初始化；调用模式是 `invoke(pmd, call_args...)`。由此可知：

- 第一个调用实参按 *INVOKE* 的分支处理（[[func.require]]），可以是对象、派生类对象、`reference_wrapper`、裸指针、智能指针。包装数据成员指针时只接受一个实参，并保留对象的值类别：右值对象得到 xvalue。
- 简单调用包装器要求可复制构造、可复制赋值，复制、移动和赋值都是不抛异常的 `constexpr` 函数。`mem_fn` 唯一的状态是一个成员指针，自然满足。
- `mem_fn` 本身是 `noexcept` 的，C++20 起是 `constexpr`。

## 今天还需要 `mem_fn` 吗

Ranges 算法的谓词和投影本来就经 `std::invoke` 调用，`std::ranges::count_if(ps, &Person::adult)` 直接可用。`mem_fn` 仍然有用的场合是：接口只接受能写成 `f(x)` 的函数对象，例如经典算法或第三方回调系统；或者需要一个有名字、可保存、可复制赋值的对象。

!!! pitfall "重载的成员函数"
    `Widget::draw` 有重载时，`std::mem_fn(&Widget::draw)` 推导不出 `R`。可以显式写出 `R`：`std::mem_fn<void() const>(&Widget::draw)`，或者先用 `static_cast` 选定一个重载。

!!! pitfall "标准库类型的成员函数"
    对标准库类的非静态成员函数（如 `std::string::size`）取成员指针，行为是未指明的，可能是非良构的（[[namespace.std#6]]）{{unspec}}。所以 `std::mem_fn(&std::string::size)` 不可移植，对标准库类型应当用 lambda。
