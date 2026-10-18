---
title: 函数模板 mem_fn
summary: mem_fn(pm) 把成员指针变成一个普通的函数对象（简单调用包装器），调用模式为 invoke(pmd, call_args...)，因此对象、指针、智能指针、reference_wrapper 都能作为第一个实参
status: done
related: func.require, func.bind.partial, func.not.fn, expr.mptr.oper, function.objects
tags: 标准库, functional, mem_fn, 成员指针
updated: 2026-10-18
---

成员指针是**可调用类型**，却不是**函数对象类型**（[[function.objects]]）：`pmf(obj)` 不是合法表达式。C++20 之前的大量算法（以及今天仍然很多的第三方代码）只接受“能写成 `f(x)` 的东西”，于是需要一个适配器把 `&Person::name` 变成 `f(person)` 形态——这就是 `mem_fn`。

```cpp
template<class R, class T> constexpr unspecified mem_fn(R T::* pm) noexcept;
```

形参类型 `R T::*` 同时匹配**数据成员指针**（`R` 为对象类型）和**成员函数指针**（`R` 为函数类型，如 `int() const`）。

!!! std
    Returns: A simple call wrapper fn with call pattern invoke(pmd, call_args...), where pmd is the target object of fn of type R T::\* direct-non-list-initialized with pm.

¶1 规定返回的是一个**简单调用包装器**（[[func.require]] ¶6）：

- 调用模式 `invoke(pmd, call_args...)`：第一个调用实参按 *INVOKE* 的分支处理，可以是对象、派生类对象、`reference_wrapper`、裸指针、智能指针……；数据成员指针只接受一个实参，且保留对象的值类别（右值对象得到 xvalue）。
- 简单调用包装器：可复制构造、可复制赋值，且复制/移动/赋值都是不抛异常的 `constexpr` 函数——它唯一的状态是一个成员指针。
- 函数本身 `noexcept`，C++20 起 `constexpr`。

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
  auto copy = adult;  copy = adult;                                   // 简单调用包装器：可复制、可赋值
  std::printf("%d\n", copy(std::ref(ps[0])));                         // reference_wrapper 也行
}
```

!!! note "今天还需要 `mem_fn` 吗？"
    在 Ranges 算法里通常不需要：投影和谓词本来就经 `std::invoke` 调用，`std::ranges::count_if(ps, &Person::adult)` 直接可用。`mem_fn` 仍有价值的场合是：接口只接受“函数对象”（如老式算法、`std::function` 以外的回调系统），或者需要一个**有名字的、可存储、可复制赋值**的对象。

!!! pitfall "重载成员函数"
    `std::mem_fn(&Widget::draw)` 在 `draw` 有重载时无法推导 `R`。要么显式写出类型 `std::mem_fn<void() const>(&Widget::draw)`，要么 `static_cast` 选定一个重载。另外，对标准库的非静态成员函数（如 `std::string::size`）形成成员指针，按 [[namespace.std#6]] 其行为是未指明的（可能非良构）{{unspec}}——`std::mem_fn(&std::string::size)` 不可移植，对标准库类型应当用 lambda。

`mem_fn` 在 libc++ 中位于 `__functional/mem_fn.h`：一个持有 `_Tp __f_` 的 `__mem_fn<_Tp>` 类，`operator()` 调用 `std::__invoke(__f_, args...)`。

!!! summary
    | 要点 | 内容 |
    |---|---|
    | 作用 | 把成员指针（数据或函数）变成函数对象 |
    | 包装器层级 | 简单调用包装器：可复制、可赋值，复制操作 `constexpr` 且不抛异常 |
    | 调用模式 | `invoke(pmd, call_args...)`，第一个实参可为对象、指针、智能指针、`reference_wrapper` |
    | 现代替代 | Ranges 算法直接接受成员指针；需要时用 lambda |
