---
title: 类型识别（typeid）
summary: typeid 得到一个描述类型的 std::type_info 对象：多态对象给出运行期的实际类型并且会求值操作数，其他表达式给出静态类型而不求值；对空指针写 typeid(*p) 抛出 std::bad_typeid；顶层 cv 和引用被忽略；使用前必须先声明 std::type_info。
status: done
papers: P1327R1
related: expr.dynamic.cast, type.info, bad.typeid, class.cdtor, class.virtual, expr.context, class.temporary, basic.def.odr, std.modules
tags: RTTI, 多态, 未求值操作数
updated: 2026-10-19
---

!!! tldr
    - `typeid(e)` 和 `typeid(T)` 得到一个 `const std::type_info` 左值，它引用的对象一直活到程序结束，可以放心保存它的引用或指针。
    - 操作数是多态类类型的 glvalue 时，`typeid` 求值操作数，给出对象的实际类型；其他情况下操作数不求值，给出表达式的静态类型。
    - 对空指针写 `typeid(*p)` 不是未定义行为，而是抛出 `std::bad_typeid`。这个例外只看语法形式，只对最外层的那个 `*` 生效。
    - 顶层的 `const`、`volatile` 和引用都被忽略：`typeid(const D&) == typeid(D)`。
    - 使用 `typeid` 之前必须包含 `<typeinfo>` 或 `import std;`，否则程序非良构。

## 静态类型还是实际类型

<div class="compare" markdown="1">

```cpp run ok
#include <typeinfo>
struct B {};         // 没有虚函数
struct D : B {};

int main() {
  D d;
  B* p = &d;
  return typeid(*p) == typeid(B)
    ? 0 : 1;         // 得到 B
}
```

```cpp run ok
#include <typeinfo>
struct B { virtual ~B() = default; };
struct D : B {};

int main() {
  D d;
  B* p = &d;
  return typeid(*p) == typeid(D)
    ? 0 : 1;         // 得到 D
}
```

</div>

两段代码只差一个虚析构函数。左边的 `B` 不是多态类，`typeid(*p)` 只看表达式的静态类型 `B`，在编译期就确定了。右边的 `B` 是**多态类**（polymorphic class，至少有一个虚函数的类，[[class.virtual]]），对象里带有指向类型信息的指针，`typeid` 在运行期读出对象实际的类型 `D`。

`typeid` 是运行期类型识别（RTTI）的一半，另一半是 [[expr.dynamic.cast]]。它的结果可以用 `==` 比较，可以取一个实现定义的名字，也可以包装成 `std::type_index` 放进关联容器。

## 结果（¶1）

¶1 `typeid` 表达式的结果是一个左值，静态类型是 `const std::type_info`（[[type.info]]）。动态类型可以是 `const std::type_info`，也可以是实现定义的、公有派生自 `std::type_info` 的某个类。脚注 46 建议把这个类命名为 `extended_type_info`。

结果引用的对象一直活到程序结束，程序结束时是否调用它的析构函数是未指定的。由此可以得出三点：

- 保存 `const std::type_info&` 或 `const std::type_info*` 是安全的，它们不会悬垂。
- `std::type_info` 的复制操作是删除的，只能持有引用或指针，或者包装成 `std::type_index`。
- 同一个类型的两次 `typeid` 不一定得到同一个对象。标准只保证 `==` 比较相等，不保证 `&typeid(T) == &typeid(T)`。

## 多态 glvalue：求值，取实际类型（¶4）

¶4 `typeid` 作用于多态类类型的 glvalue 时，结果代表这个 glvalue 所指的**最派生对象**（most derived object，不是其他对象子对象的那个完整对象，[[intro.object]]）的类型，也就是它的**动态类型**。

要知道动态类型就得在运行期读这个对象，所以这时的操作数是会被求值的。[[expr.context]] 和 [[basic.def.odr]] 在定义未求值操作数时都把这种情形排除在外。

## 其他操作数：不求值，取静态类型（¶5）

¶5 操作数是多态类 glvalue 以外的表达式时，结果代表表达式的静态类型，而且：

- 不做左值到右值、数组到指针、函数到指针转换，所以 `typeid` 能区分出数组类型和函数类型；
- 表达式是 prvalue 时，做临时量实质化转换（[[conv.rval]]）；
- 表达式是**未求值操作数**（unevaluated operand，不会在运行期执行的操作数，[[expr.context]]）。

```cpp run title="typeid-eval.cpp" ok
#include <typeinfo>

struct P { virtual ~P() = default; };
struct Q : P {};
struct N {};

int calls = 0;
P& get_poly() { ++calls; static Q q; return q; }
N& get_plain() { ++calls; static N n; return n; }

int main() {
  auto& a = typeid(get_poly());   // 多态 glvalue：get_poly() 被调用
  auto& b = typeid(get_plain());  // 非多态：get_plain() 不被调用
  int arr[3];
  bool c = typeid(arr) == typeid(int[3]);  // 没有退化成指针
  return calls == 1 && a == typeid(Q) && b == typeid(N) && c ? 0 : 1;
}
```

本机 Clang 对 `typeid(get_poly())` 给出 `-Wpotentially-evaluated-expression` 警告：带副作用的表达式虽然用作 `typeid` 的操作数，仍然会被求值。很多人以为 `typeid` 的操作数从不求值，这条警告正是为此而设。

!!! lawyer "prvalue 实质化与被删除的析构函数"
    第 5 段对 prvalue 做临时量实质化。[[class.temporary#1]] 规定，即使临时对象的创建是未求值的，也要满足如同创建并销毁了它的全部语义限制，包括析构函数可访问、未被删除，唯一的例外是 `decltype` 的操作数。所以对析构函数被删除的类 `S`，`typeid(S())` 按标准是非良构的。本机 Clang 23 接受了它，与标准不一致。

## 对空指针的 `*p`（¶3）

¶3 如果操作数是一个一元 `*` 表达式（外面可以有括号），而 `*` 的操作数求值为空指针，`typeid` 表达式抛出一个能被 `std::bad_typeid`（[[bad.typeid]]）处理器捕获的异常。注 1 提醒，在其他场合对空指针做 `*` 是未定义行为（[[expr.unary.op]]）。

```cpp run title="bad-typeid.cpp" ok
#include <typeinfo>

struct P { virtual ~P() = default; };

int main() {
  P* p = nullptr;
  try {
    (void)typeid(*p);     // 抛出 std::bad_typeid
    return 1;
  } catch (const std::bad_typeid&) {}
  try {
    (void)typeid((*p));   // 带括号也一样
    return 1;
  } catch (const std::bad_typeid&) {}
  return 0;
}
```

对多态 glvalue，`typeid` 要读对象里的虚表指针，对空指针读必然出错。标准在语法上认出最常见的写法 `typeid(*p)`，让实现在读之前先检查一次空指针。这个例外只看语法形式，范围很窄：

```cpp title="bad-typeid-narrow.cpp" ub
#include <typeinfo>

struct P {
  virtual ~P() = default;
  P& self() { return *this; }
};

int main() {
  P* p = nullptr;
  (void)typeid(p->self());  // UB: 不是 * 表达式，先对空指针调用了成员函数
  (void)typeid(*&*p);       // UB: 内层的 *p 是普通的解引用
}
```

第二行最外层确实是 `*`，但它的操作数 `&*p` 在求值时已经对空指针做了一次普通的 `*`，那一次不受第 3 段保护。

对非多态类型，`typeid(*p)` 的操作数不求值，`*p` 根本不会执行，所以既不抛异常也不是未定义行为，结果就是静态类型。

## 类型操作数与 cv 限定（¶6、¶7）

¶6 `typeid(type-id)` 的结果代表这个类型。类型是引用时，结果代表被引用的类型，去掉 cv 限定。注 2 提醒，*type-id* 不能是带 cv 限定或引用限定的函数类型，所以 `typeid(void() const)` 是非良构的。

¶7 表达式或 *type-id* 的类型带 cv 限定时，结果代表去掉 cv 之后的类型。标准的例 1 中四个比较全部为 `true`：

```cpp run title="typeid-cv.cpp" ok
#include <typeinfo>

class D {};
D d1;
const D d2;

int main() {
  bool ok = typeid(d1) == typeid(d2)
         && typeid(D) == typeid(const D)
         && typeid(D) == typeid(d2)
         && typeid(D) == typeid(const D&);
  // 只去掉顶层 cv：所指类型的 const 是类型的一部分
  bool diff = typeid(int*) != typeid(const int*);
  static_assert(typeid(int) == typeid(const volatile int&));
  return ok && diff ? 0 : 1;
}
```

`typeid` 回答的是对象是什么类型。对象是否 `const`、是直接访问还是通过引用访问，都不改变对象的类型，所以都被忽略。这和模板按值推导时去掉 cv 与引用的做法相似，但 `typeid` 不让数组和函数退化成指针。

`static_assert` 那一行能在编译期判定，是因为 C++23 起 `type_info::operator==` 是 `constexpr` 的。

## 使用前提（¶2、¶8）

¶2 操作数的类型是类类型或类类型的引用（可以带 cv）时，这个类必须是完整的。指向不完整类的指针没有问题，因为这时识别的是指针类型。

```cpp title="typeid-incomplete.cpp" error
#include <typeinfo>

struct I;

void f(I* p) {
  (void)typeid(I*);   // OK：指针类型
  (void)typeid(p);    // OK：表达式类型是 I*
  (void)typeid(I);    // error: I 不完整
  (void)typeid(*p);   // error: 表达式类型 I 不完整
}
```

¶8 `std::type_info` 不是语言预先声明的。在 `typeid` 表达式之前，必须能找到标准库对它的声明，来自 `<typeinfo>` 或标准库模块 `std`（[[std.modules]]），否则程序非良构。

```cpp title="typeid-no-header.cpp" error
int main() {
  return typeid(int) == typeid(int);   // error: 没有 <typeinfo>
}
```

本机 Clang 的诊断是 `you need to include <typeinfo> or import std before using the 'typeid' operator`。语言依赖库声明的地方不多，类似的还有 `std::initializer_list`、`<=>` 需要的 `<compare>`、协程需要的 `<coroutine>`。

## 构造与析构期间（¶9）

¶9 是一条注，指向 [[class.cdtor#5]]：在构造函数或析构函数里（包括它们直接或间接调用的函数），如果操作数指向正在构造或析构的对象，结果是当前构造函数或析构函数所属的类。

```cpp run title="typeid-ctor.cpp" ok
#include <typeinfo>

struct B {
  virtual ~B() = default;
  B() { in_ctor = &typeid(*this); }
  const std::type_info* in_ctor;
};
struct D : B {};

int main() {
  D d;
  return *d.in_ctor == typeid(B) && typeid(d) == typeid(D) ? 0 : 1;
}
```

构造 `B` 的时候 `D` 的部分还不存在，所以对象被当作 `B`，与构造期间虚函数按当前类分派是同一个道理。[[class.cdtor#5]] 还规定，操作数指向正在构造的对象、而静态类型既不是当前类也不是它的基类时，行为未定义。

## 常量求值

C++20 起（[[P1327R1]]），多态 `typeid` 可以出现在常量表达式中，前提是常量求值时知道对象的动态类型。动态类型在编译期未知时，例如引用形参所指的对象，就不是常量表达式（[[expr.const.core#2.30]]）。

## 实现视角

!!! impl
    - Itanium C++ ABI（GCC、Clang 在 Linux、macOS 上使用）中，多态类的虚表在虚表指针所指位置的前一个字存放指向 `type_info` 对象的指针。`typeid(*p)` 编译成三步：检查空指针，读虚表指针，读它前面那个字。非多态的情形和 `typeid(T)` 则直接引用编译期确定的 `_ZTI...` 符号。
    - `type_info::name()` 的结果由实现定义。GCC、Clang 返回 Itanium 修饰名（如 `1D`、`PKi`），可以用 `abi::__cxa_demangle` 还原；MSVC 返回可读的名字（如 `class D`）。它既不保证唯一，也不保证可读，不要用它做逻辑判断。
    - 在 `type_info` 对象全局唯一的平台上，相等比较只需比较地址；某些平台（尤其涉及动态库和符号可见性时）要比较名字字符串。
    - GCC、Clang 用 `-fno-rtti` 关闭 RTTI 后拒绝 `typeid`，MSVC 的 `/GR-` 类似。

## 历史与演进

!!! history
    - C++98：`typeid` 与 `std::type_info` 一同标准化。
    - C++11：增加 `type_info::hash_code()` 和 `std::type_index`，便于放进无序容器；`type_info` 的复制操作改为删除的。
    - C++20：多态 `typeid` 可以用在常量表达式中（[[P1327R1]]）。
    - C++23：`type_info::operator==` 成为 `constexpr`；引入标准库模块 `std`，它也能提供第 8 段要求的声明。

## 常见误解

!!! pitfall "typeid 的操作数从不求值"
    `typeid(*make_shape())` 中，如果 `make_shape()` 返回指向多态类的指针，函数会被调用；返回非多态类型就不会。给类加上一个虚函数，同一行代码的行为就变了。

!!! pitfall "typeid(*base_ptr) 总能给出实际类型"
    基类没有虚函数时，`typeid(*p)` 总是基类类型，与对象实际是什么无关。要得到动态类型，基类至少需要一个虚函数，通常是虚析构函数。

!!! pitfall "比较 name() 或 &typeid(T)"
    用 `strcmp(a.name(), b.name())` 或比较 `type_info` 的地址来判断类型是否相同，都不可移植。应当用 `==` 或 `std::type_index`。

## 思考题

!!! question "思考题 1"
    `struct P { virtual ~P(); }; P* f();` 下，`sizeof(typeid(*f()))` 会调用 `f` 吗？`noexcept(typeid(*f()))` 的值是什么？

<details markdown="1">
<summary>答案</summary>

不会。`sizeof` 的操作数是未求值操作数，它的子表达式都不求值。`typeid` 求值多态操作数，只在 `typeid` 表达式本身被求值时才发生。

`noexcept(typeid(*f()))` 是 `false`。表达式里有一个可能抛出异常的 `typeid`（对多态类的 `*p` 形式可能抛出 `std::bad_typeid`，见 [[except.spec]]），还有一次对没有声明 `noexcept` 的 `f` 的调用。
</details>

!!! question "思考题 2"
    `int a[3];` 下，`typeid(a) == typeid(int*)` 和 `typeid(+a) == typeid(int*)` 分别是什么？

<details markdown="1">
<summary>答案</summary>

第一个是 `false`：第 5 段规定不做数组到指针转换，`a` 的类型是 `int[3]`。

第二个是 `true`：一元 `+` 要求算术或指针操作数，`a` 先退化成 `int*`，`+a` 是 `int*` 类型的 prvalue。
</details>

## 小结

!!! summary
    | 操作数 | 是否求值 | 结果代表 |
    |---|---|---|
    | 多态类类型的 glvalue | 求值 | 动态类型 |
    | `*p` 形式，`p` 为空，类型是多态类 | 求值 | 抛出 `std::bad_typeid` |
    | 其他表达式 | 不求值；不退化；prvalue 实质化 | 静态类型 |
    | *type-id* | 不适用 | 该类型，去掉引用和顶层 cv |
    | 正在构造或析构的对象 | 求值 | 当前构造、析构函数所属的类 |
