---
title: type_index
summary: std::type_index——把不可复制的 type_info 包装成可复制、可比较、可散列的值类型，从而能作为 map/unordered_map 的键；比较基于 type_info::before 与 operator==，散列等于 hash_code()；以及跨动态库时 type_info 唯一性的实现细节
status: draft
covers: type.index.synopsis
papers: P1614R2
related: support.rtti, expr.typeid, type.info, unord.hash, associative, unord
tags: 标准库, RTTI, typeid, type_index
updated: 2026-10-18
---

`typeid` 表达式（[[expr.typeid]]）给你一个 `const std::type_info&`。但 `type_info` 本身**不可复制、不可赋值**（[[type.info]]），也没有 `operator<` 和 `std::hash` 特化——所以你不能把它直接放进 `std::map` 或 `std::unordered_map` 当键。`std::type_index`（C++11，`<typeindex>`）就是为这一件事存在的：一个持有 `const type_info*` 的轻量值类型。

典型用途：按类型分派的注册表、类型擦除容器、事件总线、“每个类型一个单例”的服务定位器。

## 头文件概要（[type.index.synopsis]）

`<typeindex>` 包含 `<compare>` 与 `<typeinfo>`，声明 `class type_index`、`hash` 主模板，以及 `hash<type_index>` 特化。

## `type_index`（[type.index]）

说明用的唯一成员是 `const type_info* target;`。概要中的注释点明了用指针而不是引用的理由：这样隐式的复制/移动构造和赋值才能正常工作（引用成员会使复制赋值被定义为弃置，见 [[class.copy.assign]]）。

¶1：`type_index` 是 `type_info` 的简单包装，可用作关联容器（[[associative]]）和无序关联容器（[[unord]]）的索引类型。

| 成员 | 语义 | 段落 |
|---|---|---|
| `type_index(const type_info& rhs) noexcept` | `target = &rhs`；**隐式**转换构造函数 | ¶2 |
| `==` | `*target == *rhs.target` | ¶3 |
| `<` `>` `<=` `>=` | 全部用 `type_info::before` 表达 | ¶4–¶7 |
| `<=>` {{c++20}} | 相等 → `equal`；`before` → `less`；否则 `greater`；返回 `strong_ordering` | ¶8 |
| `hash_code()` | `target->hash_code()` | ¶9 |
| `name()` | `target->name()`（实现定义的 NTBS） | ¶10 |
| `hash<type_index>` | 对任何 `index`，结果与 `index.hash_code()` 相同 | ¶11 |

几个法律细节：

- **相等比较的是 `type_info`，不是指针**。[[expr.typeid]] 只规定 `typeid` 的结果指向一个表示该类型的 `type_info` 对象，并没有要求同一类型的所有 `typeid` 求值引用**同一个**对象（跨动态库时实际上经常不是），所以 ¶3 用 `*target == *rhs.target` 而不是比较指针。
- **排序是实现定义的**。`type_info::before` 给出一个实现定义的全序（collation order），与名字的字典序、声明顺序都无关，并且**不保证跨程序运行稳定**。`std::map<type_index, T>` 的遍历顺序因此不可移植。
- `hash_code()` 只保证“相同类型 → 相同值”；不同类型可以碰撞，同一程序的不同运行也可以不同。
- `!=` 由 `==` 重写得到（C++20），`<=>` 由 [[P1614R2]] 加入。
- 所有成员都不是 `constexpr` 的——尽管 `type_info::operator==` 自 C++23 起是 `constexpr` 的。

由于构造函数是隐式的，可以直接写 `m[typeid(int)]`，`typeid` 的结果隐式转换为 `type_index`。`typeid` 的那些规则照样适用：顶层 cv 限定被忽略，作用于多态类型的 glvalue 时得到**动态类型**。

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
        {typeid(int), "int"},
        {typeid(Derived), "Derived"},
    };
    Derived d;
    Base& b = d;
    assert(names.at(typeid(b)) == "Derived");                       // 多态 glvalue：动态类型
    assert(std::type_index(typeid(const int)) == typeid(int));      // 顶层 cv 被忽略

    std::map<std::type_index, int> ordered;                         // 用 before() 排序
    ordered[typeid(double)] = 1;
    ordered[typeid(char)] = 2;
    assert(ordered.size() == 2);                                    // 但遍历顺序由实现定义

    std::type_index ti = typeid(int);
    assert(std::hash<std::type_index>{}(ti) == ti.hash_code());
    assert((ti <=> std::type_index(typeid(int))) == 0);
}
```

!!! impl "libc++：`type_info` 比较与动态库"
    libc++ 的 `type_index`（`<typeindex>`）就是标准说明的直译：一个 `const type_info* __t_`。真正有意思的是 `type_info` 的比较（`<typeinfo>`），它由 `_LIBCPP_TYPEINFO_COMPARISON_IMPLEMENTATION` 选择三种策略之一：

    - **Unique**（1，ELF 平台默认）：遵循 Itanium ABI，假设每个类型在程序中只有一份 RTTI，比较类型名字符串的**地址**即可；
    - **NonUnique**（2，Windows COFF、AIX 默认）：地址相等或类型名字符串内容相等即视为相等；
    - **NonUniqueARMRTTIBit**（3，Apple arm64 默认）：编译器在类型名指针的最高位标记“这份 RTTI 是否可能不唯一”，两边都唯一时比较地址，否则退回字符串比较。

    这关系到 `type_index` 在跨动态库（`dlopen`、`-Bsymbolic`、隐藏可见性）场景下的可靠性：在 Unique 策略下，若链接器没能合并两份 RTTI，同一类型的两个 `type_index` 会**比较不等**、散列也不同——注册表查找失败。这不是标准层面的问题（标准只规定同一类型的 `type_info` 比较相等），而是实现在 ABI 层面对“程序”范围的假设。

## 常见误区

!!! pitfall "以为 `name()` 可读或可移植"
    `name()` 返回实现定义的字符串：GCC/Clang 返回 Itanium 修饰名（`int` 是 `"i"`），MSVC 返回可读名。不要用它做序列化键或跨进程比较。

!!! pitfall "以为 `map<type_index, T>` 的顺序是确定的"
    `before` 的顺序是实现定义的，可能依赖地址，因而可能随链接顺序、ASLR 变化。需要稳定顺序时，请自己维护类型 → 编号的映射。

## 小结

| 问题 | 答案 |
|---|---|
| 为什么需要它 | `type_info` 不可复制、无 `<`、无 `hash` |
| 存的是什么 | `const type_info*`，不拥有 |
| 相等 | 比较 `type_info`，不比较指针 |
| 排序 | `type_info::before`，实现定义 |
| 散列 | `hash<type_index>` 等于 `hash_code()` |
| 跨动态库 | 取决于实现的 RTTI 唯一性策略 |
