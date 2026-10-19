---
title: 类型识别
summary: typeid 的结果类型 std::type_info：== 比较的是类型而不是对象地址，before、hash_code、name 的结果都未指定或由实现定义；以及 dynamic_cast 和 typeid 失败时抛出的 bad_cast、bad_typeid。
status: done
covers: support.rtti.general, typeinfo.syn, type.info, bad.cast, bad.typeid
related: type.index, expr.typeid, expr.dynamic.cast, class.virtual, exception, support.exception, cmp.categories, unord.hash
tags: 标准库, RTTI, typeid, type_info, type_index
updated: 2026-10-19
---

!!! tldr
    - `std::type_info` 只能由 `typeid` 产生，不可复制，只能通过引用或指针使用；用之前必须包含 `<typeinfo>`。
    - 判断两个类型是否相同要用 `==`，不要比较 `&typeid(T)` 的地址。C++23 起 `==` 是 `constexpr` 的。
    - `before` 的顺序、`hash_code` 的值、`name` 的内容都未指定或由实现定义，可能因程序而异，不能持久化或跨进程比较。`hash_code` 允许冲突。
    - 到引用类型的 `dynamic_cast` 失败时抛 `std::bad_cast`；`typeid(*p)` 中 `p` 为空且类型是多态的，抛 `std::bad_typeid`。
    - 想把类型当作容器的键，用 [[type.index|std::type_index]]。

## `typeid` 的结果

```cpp run title="type-info-eq.cpp" ok
#include <typeinfo>

static_assert(typeid(int) == typeid(const int));  // 顶层 cv 被忽略
static_assert(typeid(int&) == typeid(int));       // 引用也被忽略
static_assert(typeid(int) != typeid(long));

int main() {}
```

**运行时类型识别**（RTTI）在语言里有两个入口：`typeid`（[[expr.typeid]]）和 `dynamic_cast`（[[expr.dynamic.cast]]）。`typeid` 得到一个 `const std::type_info` 左值，描述一个类型；作用于多态类型的对象时，描述的是对象的动态类型。本节定义 `type_info` 和两个报告失败的异常类。

¶1 [support.rtti.general] 说明，`<typeinfo>` 定义与实现生成的类型信息相关的类型，以及两个报告类型识别错误的类型；`<typeindex>` 定义一个可以用作关联容器键的包装类型。`<typeinfo>` 整个是 freestanding 的。

`std::type_info` 不是预定义的。如果 `typeid` 表达式之前没有标准库对 `std::type_info` 的声明（包含 `<typeinfo>` 或 `import std;`），程序非良构（[[expr.typeid#8]]）。本机 Clang 的诊断是 `you need to include <typeinfo> or import std before using the 'typeid' operator`。

## `type_info` [type.info]

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

这个类没有公开的构造函数，也不可复制。`typeid` 返回的对象一直存在到程序结束（[[expr.typeid#1]]），所以保存 `const type_info&` 或 `const type_info*` 是安全的。

析构函数是虚的，因为实现会从 `type_info` 派生出内部类，存放 `dynamic_cast` 需要的继承关系。Itanium ABI 里有 `__class_type_info`、`__si_class_type_info`（单继承）、`__vmi_class_type_info`（多重或虚继承）等，`typeid` 返回的对象的动态类型可以是其中之一。`!=` 由 `==` 重写得到（[[over.match.oper]]）。

!!! std
    The names, encoding rule, and collating sequence for types are all unspecified and may differ between programs.

¶1 `type_info` 的对象实际上保存着指向类型名字的指针，以及一个用来比较相等和排序的编码值。名字、编码规则、排序顺序都是未指定的，不同程序之间可以不同。所以 `name()`、`hash_code()`、`before()` 的结果都不该写进文件或发给另一个进程。

### `operator==`（¶2–¶3）

¶3 两个 `type_info` 描述同一类型时返回 `true`。标准只保证描述同一类型的 `type_info` 比较相等，没有保证同一类型的所有 `typeid` 都得到同一个对象。实际上，同一类型的类型信息可能在多个共享库里各有一份，所以比较 `&typeid(T)` 是不可靠的。

!!! impl "libc++ 怎样比较两个 `type_info`"
    libc++ 的 `<typeinfo>` 按平台选择三种策略之一（宏 `_LIBCPP_TYPEINFO_COMPARISON_IMPLEMENTATION`）：

    1. Unique（多数 ELF 平台）：假设链接器把每个类型的类型信息合并成唯一一份，只比较类型名字符串的地址；
    2. NonUnique（Windows、AIX）：地址相等或字符串内容相等即为相等；
    3. NonUniqueARMRTTIBit（Apple arm64，本机）：编译器在名字指针的最高位标记这份类型信息是否可能不唯一，两边都唯一时比较地址，否则比较字符串。

    在 Unique 策略下，如果两个共享库都用 `-fvisibility=hidden` 编译、各自带有某个类型的类型信息，跨库比较会得到两个不同的类型，跨库的 `dynamic_cast` 和 `catch` 随之失败。这是部署时的常见问题。标准本身不涉及共享库，所以这算不上违反标准，而是实现在 ABI 层面的取舍。

### `before`、`hash_code`、`name`（¶4–¶9）

¶5 `before` 在 `*this` 按实现的排序顺序位于 `rhs` 之前时返回 `true`。这个顺序与继承关系、声明顺序、名字的字典序都无关，存在的意义只是让类型能放进有序容器，`type_index::operator<` 就用它实现。

¶6 `hash_code` 返回未指定的值，只保证在程序的一次执行中，比较相等的两个 `type_info` 返回相同的值。

¶7 实现应当为不相等的 `type_info` 返回不同的值，但这只是建议，哈希冲突是允许的。所以 `hash_code()` 不能当作类型的唯一标识。

¶8 `name` 返回一个由实现定义的空终止字节串，第 9 段补充它可以是适合转换为 `wstring` 显示的多字节字符串。标准对内容没有任何其他要求，连不同类型的名字不同都不要求。

```cpp run title="type-name.cpp" impl
#include <cstdio>
#include <typeinfo>

struct Derived {};

int main() {
  std::printf("%s %s\n", typeid(int).name(), typeid(Derived).name());
}
```

GCC 和 Clang 遵循 Itanium ABI，返回修饰名（mangled name）中表示类型的部分，本机打印 `i 7Derived`；可以用 `<cxxabi.h>` 里的 `abi::__cxa_demangle` 还原成可读形式。MSVC 返回可读的名字，比如 `class Derived`。需要稳定、可移植的类型名时，C++26 的静态反射提供了 `std::meta::identifier_of`、`std::meta::display_string_of`（[[expr.reflect]]）。

## `bad_cast` 与 `bad_typeid` [bad.cast]、[bad.typeid]

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
    (void)typeid(*np);              // 空指针：抛 bad_typeid
  } catch (const std::bad_typeid&) {
    std::puts("bad_typeid");
  }
  try {
    (void)dynamic_cast<Other&>(*b); // 到引用的转换失败：抛 bad_cast
  } catch (const std::bad_cast&) {
    std::puts("bad_cast");
  }
  delete b;
}
```

两者都派生自 `std::exception`，`what()` 返回由实现定义的字符串，特殊成员函数的约定见 [[exception]]。

`bad_cast` 报告一次无效的 `dynamic_cast`（[bad.cast]）。到指针类型的 `dynamic_cast` 失败时得到空指针，只有到引用类型的失败才抛异常。标准库在别处也用它，比如 `std::use_facet` 找不到 facet 时抛 `bad_cast`，`std::any_cast` 抛的 `bad_any_cast` 派生自它。

`bad_typeid` 报告 `typeid` 表达式中的空指针（[bad.typeid]）。

!!! lawyer "`typeid(*np)` 为什么不是未定义行为"
    对空指针解引用一般是未定义行为，但 [[expr.typeid#3]] 专门规定：`typeid` 的操作数如果是（可以带括号的）`*p` 形式，且 `p` 是空指针，`typeid` 抛出 `bad_typeid`。条件很窄。写成 `typeid(f(*p))` 就不受保护；而 `*p` 的类型不是多态类时，操作数根本不求值（[[expr.typeid#5]]），不会解引用，也不会抛异常，结果是静态类型的 `type_info`。

## 思考题

!!! question "思考题"
    `std::map<std::type_index, int>` 按什么顺序遍历？这个顺序在两次运行之间一定相同吗？

<details markdown="1">
<summary>答案</summary>

按 `type_info::before` 的顺序（[[type.index#4]]）。这个顺序是未指定的（[type.info] 第 1 段），可能依赖类型信息的地址，所以可能随链接顺序甚至地址空间随机化而变。需要稳定的顺序时，应当自己维护类型到编号的映射。
</details>
