---
title: type_index
summary: std::type_index 把不可复制的 type_info 包装成可复制、可比较、可哈希的值，用作 map 或 unordered_map 的键；相等比较转发给 type_info::operator==，排序用 before，哈希等于 hash_code()。
status: done
covers: type.index.synopsis
papers: P1614R2
related: support.rtti, expr.typeid, type.info, unord.hash, associative, unord
tags: 标准库, RTTI, typeid, type_index
updated: 2026-10-19
---

!!! tldr
    - `type_info` 不可复制，没有 `<`，也没有 `std::hash` 特化，不能直接做容器的键；`std::type_index` 内部存一个 `const type_info*`，补上了这些操作。
    - 构造函数是隐式的，`m[typeid(T)]` 可以直接写。
    - `==` 比较的是 `type_info`，不是指针；`<` 等用 `type_info::before` 实现，顺序未指定，`std::map<type_index, T>` 的遍历顺序不可移植。
    - `std::hash<type_index>` 的结果等于 `hash_code()`，不同类型可能冲突。

## 用类型做键

```cpp run title="type-index.cpp" ok
#include <cassert>
#include <map>
#include <string>
#include <typeindex>
#include <unordered_map>

struct Base { virtual ~Base() = default; };
struct Derived : Base {};

int main() {
  std::unordered_map<std::type_index, std::string> names{
    {typeid(int), "int"},          // type_info 隐式转换为 type_index
    {typeid(Derived), "Derived"},
  };
  Derived d;
  Base& b = d;
  assert(names.at(typeid(b)) == "Derived");   // 多态 glvalue：动态类型
  assert(std::type_index(typeid(const int)) == typeid(int));

  std::map<std::type_index, int> ordered;     // 用 before() 排序
  ordered[typeid(double)] = 1;
  ordered[typeid(char)] = 2;

  std::type_index ti = typeid(int);
  assert(std::hash<std::type_index>{}(ti) == ti.hash_code());
  assert((ti <=> std::type_index(typeid(int))) == 0);
}
```

按类型分派的注册表、事件总线、每个类型一个实例的服务定位器，都需要以类型为键查表。`typeid` 给出的是 `const std::type_info&`，而 `type_info` 不可复制、不可赋值（[[type.info]]），放不进容器。`std::type_index`（C++11，头文件 `<typeindex>`）就是为此准备的包装。

`typeid` 的规则照常适用：顶层 cv 限定和引用被忽略；作用于多态类型的 glvalue 时，得到的是动态类型。

## 定义 [type.index.synopsis]、[type.index]

`<typeindex>` 包含 `<compare>` 和 `<typeinfo>`，声明 `type_index`、`hash` 主模板和 `hash<type_index>` 特化。

`type_index` 的说明用成员只有一个 `const type_info* target;`。概要里的注释解释了为什么用指针而不用引用：有引用成员的类，隐式的复制赋值运算符被定义为弃置的（[[class.copy.assign]]），用指针才能让默认的复制和移动操作正常工作。

¶1 `type_index` 是 `type_info` 的简单包装，可以用作关联容器（[[associative]]）和无序关联容器（[[unord]]）的索引类型。

| 成员 | 效果 | 段落 |
|---|---|---|
| `type_index(const type_info& rhs) noexcept` | `target = &rhs`，隐式转换 | ¶2 |
| `==` | `*target == *rhs.target` | ¶3 |
| `<`、`>`、`<=`、`>=` | 都用 `type_info::before` 表达，如 `<` 是 `target->before(*rhs.target)` | ¶4–¶7 |
| `<=>` | 相等返回 `equal`，`before` 为真返回 `less`，否则 `greater`；类型是 `strong_ordering` | ¶8 |
| `hash_code()` | `target->hash_code()` | ¶9 |
| `name()` | `target->name()` | ¶10 |
| `hash<type_index>` | 对任何 `index`，结果与 `index.hash_code()` 相同 | ¶11 |

¶3 比较的是两个 `type_info`，不是两个指针。标准不保证同一类型的每次 `typeid` 都得到同一个对象，跨共享库时往往不是同一个，所以比较指针会出错。`type_info` 的 `==` 在各平台上怎样实现，见 [[support.rtti]] 的实现说明。

`before` 的顺序是未指定的，可能随程序而变（[type.info] 第 1 段），它与类型名的字典序、声明顺序都无关。`hash_code()` 只保证同一次执行中同一类型得到相同的值。

`!=` 由 `==` 重写得到，`<=>` 是 C++20 由 [[P1614R2]] 加入的。`type_index` 的成员都不是 `constexpr` 的，尽管 `type_info::operator==` 从 C++23 起已经是 `constexpr`。

!!! pitfall "以为 `name()` 可读或可移植"
    `name()` 返回由实现定义的字符串。GCC 和 Clang 返回修饰名（`int` 是 `"i"`），MSVC 返回可读的名字。不要拿它做序列化的键，也不要跨进程比较。
