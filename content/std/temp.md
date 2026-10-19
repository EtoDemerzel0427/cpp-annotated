---
title: 模板
summary: 第 13 章导读：模板怎样声明、怎样给出实参、怎样约束，模板里的名字怎样查找，特化何时生成，函数模板的实参怎样推导，以及各部分在哪一页。
status: draft
related: temp.pre, temp.param, temp.names, temp.arg, temp.constr, temp.res, temp.spec, temp.deduct, topics/concepts, topics/two-phase-lookup
tags: 模板, 泛型编程, 导读
updated: 2026-10-19
---

!!! tldr
    - 模板是生成一族实体的规则，它的特化才是具体的类、函数或变量：`std::vector<int>` 是类，`std::vector` 不是。
    - 模板里的构造分为待决的（依赖模板形参）和非待决的。非待决的部分在定义处检查，待决的部分推迟到实例化，这就是两阶段查找，也是要写 `typename` 和 `template` 的原因。
    - 本章有大量 IFNDR 规则，因为同一个模板会在多个翻译单元、多个实例化点展开，编译器无法互相比对。
    - 建议的顺序：[[temp.pre]] → [[temp.param]] → [[temp.names]] → [[temp.arg]]，再按需要读约束、名字决议、实例化和推导。

```cpp run ok
#include <concepts>
template<std::integral T>          // 模板形参和约束（13.2、13.5）
T twice(T x) { return x + x; }     // 函数模板（13.1、13.7）

template<class T>
struct Box {
  T v;
  typename T::size_type n() const  // 待决名要写 typename（13.8）
  { return v.size(); }
};

int main() {
  auto a = twice(21);              // 推导出 T = int（13.10），隐式实例化 twice<int>（13.9）
  // twice(1.5);                   // error: double 不满足 std::integral
  return a - 42;
}
```

这段代码几乎用到了第 13 章的每个部分：声明模板，给出模板实参，检查约束，查找模板里的名字，实例化特化，推导模板实参。这一章回答的就是这些步骤各自怎样进行。它大量借用名字查找（[[basic.lookup]]）、ODR（[[basic.def.odr]]）、常量表达式（[[expr.const]]）和重载决议（[[over.match]]），并在它们之上再区分待决与非待决。

## 本章结构

| 小节 | 内容 | 本站页面 |
|---|---|---|
| 13.1 | 模板声明的组成，templated 实体，*requires-clause*，定义的可达性 | [[temp.pre]] |
| 13.2 | 模板形参：类型形参、常量形参、模板模板形参；默认实参；形参包 | [[temp.param]] |
| 13.3 | *template-id*：`<` 何时是模板实参的开始，`template` 关键字，`>>` | [[temp.names]] |
| 13.4 | 各种模板实参怎样与形参匹配 | [[temp.arg]] |
| 13.5 | 约束：形式、满足、规范化、按约束排序 | [[temp.constr]]、[[temp.constr.order]] |
| 13.6 | 两个 *template-id* 何时是同一个类型 | [[temp.type]] |
| 13.7 | 类模板及其成员、变参模板、友元、部分特化、函数模板的重载与偏序、别名模板、概念 | [[temp.decls]]、[[temp.class]]、[[temp.spec.partial]]、[[temp.fct]]、[[temp.alias]]、[[temp.concept]] 等 |
| 13.8 | 名字决议：待决名、待决类型和表达式、两阶段查找、实例化点 | [[temp.res]]、[[temp.dep]]、[[temp.dep.res]] |
| 13.9 | 隐式实例化、显式实例化、显式特化 | [[temp.spec]]、[[temp.inst]]、[[temp.explicit]]、[[temp.expl.spec]] |
| 13.10 | 显式模板实参、模板实参推导（SFINAE 的出处）、重载决议中的模板 | [[temp.fct.spec]]、[[temp.deduct]]、[[temp.over]] |

概念相关的规则分散在 [[temp.constr]]、[[temp.concept]]、[[expr.prim.req]]、[[over.match.best]] 中，专题 [[topics/concepts]] 把它们串在一起。两阶段查找见专题 [[topics/two-phase-lookup]]。

## 贯穿全章的几组概念

### 模板与特化

按 [[temp.pre#1]]，模板定义的是一族类、函数或变量，一族类型的别名，或者一个概念。特化可以由实例化隐式生成，也可以由程序员显式提供（[[temp.spec]]）。不同模板的特化永远是不同的实体（[[temp.pre#6]]）。概念是例外：它从不实例化，`C<int>` 这样的 concept-id 只是一个 `bool` 纯右值（[[temp.concept#5]]、[[temp.names#15]]）。

### 模板与 templated 实体

类模板的成员函数、函数模板里的局部类、lambda 的闭包类型，本身都不是模板，但处在模板之中。[[temp.pre#8]] 称它们为 **templated 实体**。很多规则对 templated 实体都适用，例如只有 templated 函数能有尾随 *requires-clause*，`if constexpr` 舍弃的分支只在 templated 实体里不实例化。

### 待决与非待决

模板定义里的每个构造，要么依赖模板形参，只能等到实例化时才能确定，叫**待决**（dependent）；要么在定义处就能确定，叫非待决。非待决的部分在定义处查找和检查，待决的部分推迟到实例化（[[temp.res]]）。所以待决的限定名是类型时要写 `typename`，后面跟模板实参列表时要写 `template`（[[temp.names#11]]）。

### 等价与功能等价

两个涉及模板形参的表达式何时算相同？[[temp.over.link]] 按记号比较来定义**等价**，而不是按含义。两个构造含义相同但写法不同（功能等价而不等价），而程序的含义又取决于它们是否相同时，程序是 IFNDR。函数模板的重声明、原子约束的比较（[[temp.constr.atomic]]）都受此影响，约束之间的包含关系也因此要求使用同一个具名概念（[[temp.constr.order]]）。

### IFNDR 特别多

模板分散在不同翻译单元中编译，实例化点可能有多个，编译器不可能跨翻译单元、跨实例化点比较一切，所以这一章有很多规则违反后是 IFNDR（非良构，不要求诊断）。例如：隐式实例化处看不到函数模板的定义，又没有显式实例化（[[temp.pre#10]]）；同一个原子约束在程序不同位置的满足结果不同（[[temp.constr.atomic]]）；模板不可能有任何合法的特化（[[temp.res]]）。

## C++26 的变化

{{c++26}} 本章在 C++26 中变化较多，后面各页会反复遇到：

- 术语：原来的非类型模板形参（non-type template parameter）改称**常量模板形参**（constant template parameter），对应的实参改称常量模板实参。本站统一使用新术语。
- 模板模板形参不再只能接受类模板和别名模板，也可以接受概念和变量模板（[[temp.param]]）。
- 折叠展开约束（[[temp.constr.fold]]）让 `(C<Ts> && ...)` 这样的约束之间也能比较包含关系。
- 包索引 `Ts...[N]`（[[temp.names]]）。
- 静态反射：拼接说明符可以出现在模板实参列表之前（[[temp.names#7]]），`std::meta::info` 可以作为常量模板实参（[[temp.type]]）。
