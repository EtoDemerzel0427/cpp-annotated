---
title: 类型识别
summary: typeid 产生的 std::type_info——operator==、before、hash_code、name 各自保证了什么、没保证什么；bad_cast 与 bad_typeid 由哪些核心语言表达式抛出；type_index 如何把 type_info 变成容器的键
status: done
covers: support.rtti.general, typeinfo.syn, type.info, bad.cast, bad.typeid
related: type.index, expr.typeid, expr.dynamic.cast, class.virtual, exception, support.exception, cmp.categories, unord.hash
tags: 标准库, RTTI, typeid, type_info, type_index
updated: 2026-10-18
---

C++ 的**运行时类型识别**（RTTI）有两个核心语言入口：`typeid`（[[expr.typeid]]）和 `dynamic_cast`（[[expr.dynamic.cast]]）。它们的结果和错误报告用到的类型，由本节定义：

| 头文件 | 内容 | 与核心语言的关系 |
|---|---|---|
| `<typeinfo>` | `type_info` | `typeid` 表达式的结果类型 |
| | `bad_cast` | 到引用类型的 `dynamic_cast` 失败时抛出 |
| | `bad_typeid` | `typeid` 作用于空指针解引用时抛出 |
| `<typeindex>` | `type_index` | 可复制、可比较、可哈希的 `type_info` 包装 |

¶1（[support.rtti.general]）说明 `<typeinfo>` 定义了与实现生成的类型信息相关的类型，以及两个报告动态类型识别错误的类型；`<typeindex>` 定义了一个用作（无序）关联容器索引类型的包装类型。`<typeinfo>` 全部是 freestanding 的（[typeinfo.syn]）。

[[expr.typeid#8]] 有一条规定和本节直接相关：`std::type_info` **不是预定义的**——如果 `typeid` 表达式之前没有标准库对 `std::type_info` 的声明（包含 `<typeinfo>`，或者 `import std;`），程序非良构。

## `type_info`（[type.info]）

```cpp
class type_info {
public:
  virtual ~type_info();
  constexpr bool operator==(const type_info& rhs) const noexcept;
  bool before(const type_info& rhs) const noexcept;
  size_t hash_code() const noexcept;
  const char* name() const noexcept;
  type_info(const type_info&) = delete;
  type_info& operator=(const type_info&) = delete;
};
```

几个结构性特点：

- **不可复制、不可赋值，没有公开构造函数**。用户无法自己创建 `type_info` 对象；唯一的来源是 `typeid` 表达式，它返回一个**静态存储期**的 `const std::type_info` 左值（[[expr.typeid]]）。所以只能保存 `const type_info&` 或 `const type_info*`。
- **虚析构函数**。实现会从 `type_info` 派生出内部类，存放继承关系等 `dynamic_cast` 需要的信息——Itanium ABI 中是 `__fundamental_type_info`、`__class_type_info`、`__si_class_type_info`（单继承）、`__vmi_class_type_info`（多重/虚继承）等。`typeid` 返回的对象的动态类型可能是这些派生类之一（[[expr.typeid]] 允许"`std::type_info` 或其派生类"）。
- 没有 `operator!=`：C++20 起由 `==` 重写得到（[[over.match.oper]]）。

¶1 是对整个类的定性描述：

!!! std
    Objects of this class effectively store a pointer to a name for the type, and an encoded value suitable for comparing two types for equality or collating order. The names, encoding rule, and collating sequence for types are all unspecified and may differ between programs.

    该类的对象实际上存储了指向类型名字的指针，以及一个适合用于比较两个类型是否相等或排序的编码值。类型的名字、编码规则和排序顺序**都是未指明的**，并且**在不同程序之间可以不同**。

"在不同程序之间可以不同"意味着：**不要把 `name()`、`hash_code()` 或 `before()` 的结果持久化或跨进程传递**。

### `operator==`（¶2–¶3）

返回两个 `type_info` 是否描述**同一类型**。注意是"同一类型"而不是"同一对象"：标准只保证描述同一类型的 `type_info` 比较相等，**并没有**保证同一类型的所有 `typeid` 表达式都指代同一个对象（实践中，同一类型的 RTTI 可能在多个共享库中各有一份），因此**比较 `&typeid(T)` 的地址是不可靠的**，必须用 `==`。

C++23 起 `operator==` 是 `constexpr` 的，可以在编译期比较类型：

```cpp run title="type-info-eq.cpp" ok
#include <typeinfo>

static_assert(typeid(int) == typeid(const int));     // typeid 忽略顶层 cv（[expr.typeid]）
static_assert(typeid(int) != typeid(long));
static_assert(typeid(int&) == typeid(int));          // 也忽略引用

int main() {}
```

!!! impl "libc++ 的三种比较策略"
    `type_info` 的相等比较看似简单，实际上是一个 ABI 难题：同一个类型的 RTTI 可能在多个共享库中各有一份。libc++ 的 `<typeinfo>` 根据平台选择三种实现之一：

    1. **Unique**（大多数 Itanium ABI 平台）：假设链接器/动态链接器把每个类型的 RTTI 合并为唯一一份，于是只需比较类型名字符串的**地址**；
    2. **NonUnique**（Windows COFF、AIX XCOFF）：先比地址，不等再做 `strcmp` 深比较；
    3. **NonUniqueARMRTTIBit**（Apple arm64，即本机）：编译器在名字指针的最高位打一个"非唯一"标记；两边都唯一则比地址，都非唯一则比字符串，一个唯一一个非唯一则必然不等。

    在常量求值中，libc++ 直接比较两个 `type_info` 对象的地址——编译期不存在"来自不同共享库"的问题。

    在 Unique 策略下，用 `-fvisibility=hidden` 编译的库中的类型各自有一份 RTTI，跨库比较会得到"不同类型"，导致跨库 `dynamic_cast` 和 `catch` 失败——这是一个经典的部署事故。

### `before`（¶4–¶5）

若 `*this` 在实现的排序顺序中位于 `rhs` 之前，返回 `true`。它提供一个**全序**，但这个顺序是未指明的，与继承关系、声明顺序都无关；`before` 的存在只是为了能把类型放进有序容器（这正是 `type_index::operator<` 的实现）。

### `hash_code`（¶6–¶7）

¶6：返回未指明的值，但**在程序的单次执行中**，比较相等的两个 `type_info` 必须返回相同的值。¶7 *Remarks*：实现**应当**（should）为不相等的两个 `type_info` 返回不同的值——这是建议，**不是保证**，哈希冲突是允许的。所以 `hash_code()` 不能用作类型的唯一标识；需要唯一标识时用 `type_index` 本身（它的 `==` 是精确的）。

### `name`（¶8–¶9）

¶8：返回一个**由实现定义的** NTBS。¶9：可以是适合转换为 `wstring` 显示的空终止多字节字符串。

标准对 `name()` 的内容**没有任何要求**——甚至不要求不同类型的名字不同。实践中：

- GCC/Clang（Itanium ABI）返回**修饰名**（mangled name）中的类型部分：`int` 是 `"i"`，`Derived` 是 `"7Derived"`，`std::string` 在 libc++ 上是 `"NSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEE"`。可以用 `abi::__cxa_demangle`（`<cxxabi.h>`）还原成可读形式。
- MSVC 返回可读名，例如 `"class Derived"`。

!!! tip "需要可移植的类型名？"
    `name()` 的输出不可移植，也不适合做序列化的键。C++26 的静态反射提供了 `std::meta::identifier_of`、`std::meta::display_string_of` 等工具（[[expr.reflect]]），可以在编译期得到类型的名字。

## `bad_cast` 与 `bad_typeid`（[bad.cast]、[bad.typeid]）

两者都派生自 `std::exception`，只有一个 `constexpr` 的 `what()`（返回由实现定义的 NTBS），特殊成员函数的规格见 [[exception]]。

| 异常 | 由谁抛出 | 核心语言出处 |
|---|---|---|
| `bad_cast` | 到**引用**类型的 `dynamic_cast` 失败（到指针类型的失败返回空指针） | [[expr.dynamic.cast]] |
| `bad_typeid` | `typeid` 的操作数是对**空指针**解引用得到的多态类型左值，如 `typeid(*p)` 且 `p` 为空 | [[expr.typeid]] |

`bad_cast` 还会被标准库在别处使用，例如 `std::use_facet` 找不到 facet 时，以及 `std::any_cast` 抛出的 `bad_any_cast` 就派生自 `bad_cast`。

```cpp run title="rtti-errors.cpp" ok
#include <cstdio>
#include <typeinfo>

struct Base { virtual ~Base() = default; };
struct Derived : Base {};
struct Other : Base {};

int main() {
    Base* b = new Derived;
    Base* np = nullptr;
    try {
        (void)typeid(*np);                   // 多态类型 glvalue，由解引用空指针得到 → 抛 bad_typeid
    } catch (const std::bad_typeid& e) {
        std::printf("bad_typeid: %s\n", e.what());
    }
    try {
        (void)dynamic_cast<Other&>(*b);      // 到引用的 dynamic_cast 失败 → 抛 bad_cast
    } catch (const std::bad_cast& e) {
        std::printf("bad_cast: %s\n", e.what());
    }
    delete b;
}
```

!!! lawyer "`typeid(*np)` 为什么不是 UB"
    解引用空指针通常是 UB，但 [[expr.typeid]] 为这一种情形做了专门规定：当 `typeid` 的操作数是对一个指针应用一元 `*` 得到的多态类类型 glvalue、且该指针为空指针值时，`typeid` 抛出 `bad_typeid`。这个"空指针检查"是 `typeid` 求值的一部分，发生在任何实际的内存访问之前。条件很窄（[[expr.typeid#3]]）：操作数必须**直接**是 `*p` 的形式（可以带括号）；写成 `typeid(f(*p))` 就不受此保护。另一方面，若 `*p` 的类型不是多态类，操作数是不求值操作数（[[expr.typeid#5]]），根本不会发生解引用，也就不抛异常，结果只是静态类型的 `type_info`。

## `type_index`（[type.index.synopsis]、[type.index]）

`type_info` 不可复制，不能直接作为 `std::map`/`std::unordered_map` 的键。`<typeindex>` 中的 `std::type_index` 是它的薄包装：内部只存一个 `const type_info*`，可复制、可赋值，`==` 转发给 `type_info::operator==`，`<` 等用 `before` 实现，`<=>` 返回 `strong_ordering`，`hash<type_index>` 与 `hash_code()` 一致。详见 [[type.index]]。

```cpp run title="type-index.cpp" ok
#include <cstdio>
#include <string>
#include <typeindex>
#include <unordered_map>

struct Base { virtual ~Base() = default; };
struct Circle : Base {};
struct Square : Base {};

int main() {
    std::unordered_map<std::type_index, std::string> names{
        {typeid(Circle), "circle"},          // type_info → type_index：隐式转换
        {typeid(Square), "square"},
    };
    Base* shapes[] = {new Circle, new Square};
    for (Base* s : shapes) {
        std::printf("%s\n", names.at(typeid(*s)).c_str());   // 按动态类型查找
        delete s;
    }
}
```

## 小结

!!! summary
    - `type_info` 只能由 `typeid` 产生，不可复制；比较类型用 `==`，不要比较地址。
    - `before` 给出未指明的全序；`hash_code` 在单次执行中对相等类型一致，但可能冲突；`name` 的内容由实现定义（GCC/Clang 返回修饰名）。
    - 所有编码、名字、顺序都可能随程序乃至执行而变，不要持久化。
    - `bad_cast`：到引用的 `dynamic_cast` 失败；`bad_typeid`：`typeid(*p)` 中 `p` 为空且类型多态。
    - `type_index`：可复制的 `type_info*` 包装，用作容器的键（详见 [[type.index]]）。
