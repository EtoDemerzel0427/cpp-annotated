---
title: 实例化语境
summary: 模板在一个模块中定义、在另一个 TU 中实例化时，应当从哪些程序点去看；实例化语境决定依赖名的 ADL 能找到什么、哪些声明可达；默认函数、嵌套实例化、常量求值各有规则。
status: done
since: c++20
papers: P1103R3
related: module.reach, module.global.frag, temp.point, temp.dep, basic.lookup.argdep, expr.const.reflect, class.compare.default
tags: 模块, 模板, 实例化, 可达性
updated: 2026-10-18
---

没有模块时，模板实例化从哪里看，由**实例化点**（point of instantiation，[[temp.point]]）决定：本 TU 中在实例化点之前声明的东西都可以用。头文件被粘贴进每个 TU，模板定义处能看到的东西，实例化处一般也能看到。

模块打破了这个假设。模板在模块 M 的接口单元中定义，实例化却发生在导入者的 TU 中，两处可见、可达的东西完全不同：

- 模板定义处（M 的接口单元）能看到 M 自己的 `import`、全局模块片段中的头文件、M 的非导出实体；
- 实例化处（导入者）能看到导入者自己 `import` 的东西。

模板实例化时，依赖名的查找和类型完整性应该以哪边为准？答案是两边都算。更精确地说，标准规定了一组程序点，称为**实例化语境**（instantiation context）。

阅读前需要：[[temp.point]]（实例化点）、[[temp.dep]]（依赖名）、[[module.reach]]（可达）、[[basic.lookup.argdep]]（ADL）。

## 定义（¶1）

¶1 [[g:instantiation-context|实例化语境]]是程序中的一组点，它决定了在某个特定声明或模板实例化的语境中：

- 实参依赖查找（[[basic.lookup.argdep]]）能找到哪些声明；
- 哪些声明是可达的（[[module.reach]]）。

这两处分别这样使用它：

- [[basic.lookup.argdep#4]]：若 N 是依赖名，ADL 还要从实例化语境中的每个点做一遍查找（同时忽略其他 TU 中附属于全局模块、且被丢弃或具有内部链接的声明）。
- [[module.reach#4]]：一个声明可达，当且仅当它从实例化语境中的任意一个点可达。

所以实例化语境的效果是取并集：点越多，能找到、能用的东西越多。

## 各种情形（¶2–¶8）

### 默认函数的隐式定义（¶2）

¶2 在隐式定义一个默认函数（defaulted function，如 `= default` 的特殊成员函数、默认比较运算符，[[special]]、[[class.compare.default]]）期间，实例化语境包含：

- 类定义处的实例化语境中的每个点，以及
- 导致该默认函数被隐式定义的那个程序构造的实例化语境中的每个点。

例如模块 M 中有 `export struct S { T t; bool operator==(const S&) const = default; };`，导入者写 `s1 == s2` 会触发 `operator==` 的隐式定义。这个定义需要比较 `t`，查找 `T` 的 `operator==` 时，既能用 M 中（类定义处）可达的东西，也能用导入者（使用处）可达的东西。

### 嵌套实例化（¶3）

¶3 如果一个模板的隐式实例化，其实例化点规定为外围特化的实例化点（[[temp.point#1]]：在另一个模板特化中以依赖于模板形参的方式被引用），则实例化语境包含：

- 外围特化的实例化语境中的每个点；并且，
- 若该模板定义在模块 M 的模块接口单元中，而实例化点不在 M 的模块接口单元中，则还包含 **M 的主模块接口单元的 *declaration-seq* 末尾**这个点（如果有私有模块片段，则在它之前）。

第二部分是本节最关键的规则。它的意思是：模块 M 的模板在别处被嵌套实例化时，在 M 的主接口末尾处可达的一切也算可达。为什么选主接口末尾？因为到了那里，模块 M 的接口已经完整建立：M 的所有接口分区都已直接或间接导入，M 自己的 `import` 都已生效。模板作者在 M 中写模板时，可以合理地期望 M 的接口能看到的东西，模板都能用。

为什么只针对嵌套实例化（¶3），而不是所有实例化（¶5）？对于顶层实例化（导入者直接写 `f<int>()`），实例化点就在导入者中，导入者对 M 的接口单元有接口依赖，M 的接口单元本身必然可达。嵌套实例化的实例化点继承自外围特化，可能离 M 很远，所以需要把 M 主接口的末尾显式加进来。

### 从默认函数中引用的模板（¶4）

¶4 因在默认函数的隐式定义中被引用而被隐式实例化的模板，其实例化语境包含该默认函数的实例化语境中的每个点。（比如默认 `operator==` 比较一个 `std::vector<T>` 成员，触发 `operator==<T>` 的实例化。）

### 其他模板特化（¶5）

¶5 在实例化任何其他模板特化期间，实例化语境包含该模板的实例化点。

### 常量求值引起的实例化（¶6）{{c++26}}

¶6 当作为核心常量表达式求值的表达式导致某个构造被隐式实例化时，在实例化期间，实例化语境包含**求值语境**（evaluation context，[[expr.const.reflect]]）中的每个点。

Note 1：隐式实例化可能来自对库函数的调用（[[meta.reflection]]，如反射元函数 `substitute`）。求值语境可以包含与 `std::meta::define_aggregate` 产生的注入声明相关联的合成点。

这条随 C++26 静态反射加入：常量求值过程中可以注入新的声明（例如用 `define_aggregate` 补全一个不完整类），对于求值过程中触发的实例化，这些声明对应的合成点也应当可见。

### 其他情形（¶7–¶8）

¶7 其他任何情况下，程序中某点的实例化语境只包含该点本身。

¶8 实例化语境只包含上述各段所规定的点。

¶8 是一个封闭性声明：实现不能自行添加点，让更多东西可达或能被 ADL 找到。（但注意 [[module.reach#2]] 允许实现把额外的 TU 视为可达，这是另一方面的自由。）

## 标准例子（¶9）

¶9 Example 1（加注）：

```cpp title="TU #1：stuff.cppm"
export module stuff;
export template<typename T, typename U> void foo(T, U u) { auto v = u; }
export template<typename T, typename U> void bar(T, U u) { auto v = *u; }
```

```cpp title="TU #2：M1.cppm"
export module M1;
import "defn.h";        // 提供 struct X {};
import stuff;
export template<typename T> void f(T t) {
  X x;
  foo(t, x);
}
```

```cpp title="TU #3：M2.cppm"
export module M2;
import "decl.h";        // 提供 struct X;（不是定义）
import stuff;
export template<typename T> void g(T t) {
  X *x;
  bar(t, x);
}
```

```cpp title="TU #4：test.cpp" unspecified
import M1;
import M2;
void test() {
  f(0);       // OK
  g(0);       // 未指明是否合法
}
```

`f(0)` 合法。`foo<int, X>` 的实例化语境包含：

- **¶9.1** TU #1 的末尾（`foo<int, X>` 在 `f<int>` 中被依赖地引用，实例化点继承自 `f<int>`；`foo` 定义在 stuff 的接口中而实例化点不在其中，于是按 ¶3 加入 stuff 主接口的末尾）；
- **¶9.2** TU #2 的末尾（M1 主接口的末尾，`f` 定义在那里）；
- **¶9.3** 调用 `f(0)` 的位置。

!!! lawyer "¶9.2 从哪里来？"
    按字面推导，¶9.2 并不显然。`f<int>` 是 test.cpp 中的非模板代码直接引用的，属于 ¶5（语境只含其实例化点，在 TU #4 中）；¶3 加入的是被实例化的那个模板（`foo`）所在模块的主接口末尾，即 TU #1，而不是 TU #2。例子的意图显然是：模板 `f` 定义处（M1 接口末尾）能看到的东西，应当可供 `f` 内部引发的嵌套实例化使用，这也正是 ¶3 的设计初衷。但要从规范性文字中读出这一点，需要把 ¶3 理解为沿着外围特化链，累积每一层模板定义所在模块的主接口末尾。这是措辞上值得留意的一处漏洞；本页不对此下结论，以标准例子的结论为准（Clang 也接受 `f(0)`）。

在 TU #2 末尾，`defn.h` 的头文件单元已被导入，`X` 的定义从那里可达。所以 `auto v = u;`（需要 `X` 完整以拷贝）合法。

`g(0)` 是否合法未指明。`bar<int, X*>` 的实例化语境包含：

- **¶9.4** TU #1 的末尾；
- **¶9.5** TU #3 的末尾，那里只导入了 `decl.h`，`X` 不完整；
- **¶9.6** 调用 `g(0)` 的位置，test.cpp 导入了 M1 和 M2。

`*u` 需要 `X` 完整吗？对 `X*` 解引用得到 `X` 的左值，`auto v = *u;` 需要拷贝 `X`，所以需要 `X` 的定义。那么从这三个点出发，`defn.h` 头文件单元是否可达？test.cpp 对 M1 有接口依赖，M1 导入了 `defn.h`，所以 test.cpp 对 `defn.h` 的头文件单元有接口依赖；但它不是模块接口单元，也没有被 test.cpp 直接导入，因此**不是必然可达的**（[[module.reach#1]]）。[[module.reach#2]] 允许实现把它视为可达，也允许不这样做，于是 `g(0)` 的合法性是未指明的。

!!! impl "本机验证"
    用 Clang 23 的头文件单元（`-fmodule-header=user`）构建 `defn.h`、`decl.h`，再依次构建 stuff、M1、M2，编译 test.cpp：`f(0)` 通过；`g(0)` 报错 "definition of 'X' must be imported from module './defn.h' before it is required"，附注 "definition here is not reachable"。也就是说，Clang 选择不把额外的 TU 视为可达，这是标准允许的选择之一。

## 一个检验 ¶3 的例子

下面的例子中，模块 M 的接口导入了一个实现分区。实现分区不是模块接口单元，所以从导入者看它不是必然可达的；但从 M 主接口的末尾看，它是直接导入的，因而必然可达。

```cpp title="M-Impl.cppm"
module M:Impl;
struct Detail { int v = 5; };
```

```cpp title="M.cppm"
export module M;
import :Impl;
export Detail* make() { return new Detail; }
template<class P> int inner(P p) { return p->v; }
export template<class P> int outer(P p) { return inner(p); }
export template<class P> int direct(P p) { return p->v; }
```

```cpp title="use-outer.cpp" ok
import M;
int main() {
  auto p = make();
  return outer(p);   // inner<Detail*> 是嵌套实例化（¶3）：
                     //   实例化语境含 M 主接口末尾，那里 M:Impl 必然可达 → Detail 完整
}
```

```cpp title="use-direct.cpp" unspecified
import M;
int main() {
  auto p = make();
  return direct(p);  // direct<Detail*> 是顶层实例化（¶5）：实例化语境只有这里
                     //   M:Impl 对此处不是必然可达的 → 是否合法未指明
}
```

!!! impl "Clang 与 ¶3 的偏差"
    按以上分析，`use-outer.cpp` 应当是良构的。本机 Clang 23 却对两个文件都报 "definition of 'Detail' must be imported from module 'M' before it is required"。对 `use-direct.cpp` 来说这是允许的选择；对 `use-outer.cpp`，Clang 看起来没有实现 ¶3 中加入主接口末尾的规则（至少对实现分区如此）。Clang 在编译 M.cppm 时也给出警告 "importing an implementation partition unit in a module interface is not recommended. Names from M:Impl may not be reachable"，说明 Clang 有意不把接口中导入的实现分区当作对外可达。

    可移植的写法是：凡是导出模板需要其定义的类型，都放进接口分区并由主接口 `export import`，或者至少放进主接口本身。

## 与 ADL 的关系

[[basic.lookup.argdep#5]] 的标准例子展示了实例化语境在 ADL 中的效果：模块 N 的导出模板 `apply(t, u)` 中有依赖调用 `f(t, u)`，实例化时从实例化语境中的每个点（包括 N 的接口末尾、调用处）做 ADL，所以能找到在调用处可见或在 N 接口中可达的 `f`；而 N 中 `static` 的 `R::g` 虽然在 N 的接口末尾可见，却因为其他 TU 中具有内部链接的声明会被忽略而找不到。

## 历史与演进

!!! history "C++20 → C++26"
    - 实例化语境随 [[P1103R3]] 进入 C++20，取代了 Modules TS 中关于实例化时哪些声明可见的较为模糊的规则。
    - C++26 加入 ¶6，把常量求值中的求值语境（静态反射引入的合成点、注入声明）纳入实例化语境。

## 陷阱

!!! pitfall "模板在模块内能编译，导入者实例化却失败"
    模板依赖某个类型的完整性或某个 ADL 候选，而它们只存在于模块内部的实现分区或全局模块片段中（且被丢弃）。模块作者自测时实例化点在模块内，一切正常；导入者实例化时，实例化语境并不包含那些点。测试模块时，务必从模块外部实例化导出的模板。

!!! pitfall "依赖头文件单元的传递可达"
    如 ¶9 的 `g(0)`：一个 TU 只通过别的模块间接接触到某个头文件单元时，其中的定义是否可达是未指明的。需要什么就直接 `import` 什么。

## 思考题

!!! question "思考题"
    在 ¶9 中，如果把 TU #4 改为在 `import M2;` 之后再加一行 `import "defn.h";`，`g(0)` 是否变为确定合法？

<details markdown="1">
<summary>答案</summary>

是。`bar<int, X*>` 的实例化语境包含调用 `g(0)` 的点（¶9.6），该点在 `import "defn.h";` 之后；`defn.h` 头文件单元由 TU #4 直接导入，必然可达（[[module.reach#1]]），于是 `X` 的定义可达。（`defn.h` 与 `decl.h` 中的 `X` 都附属于全局模块且外部链接，是同一实体，所以定义适用于 `X*` 中的那个 `X`。）
</details>

## 小结

| 情形 | 实例化语境包含 | 段落 |
|---|---|---|
| 默认函数的隐式定义 | 类定义处的语境 ∪ 触发定义处的语境 | ¶2 |
| 嵌套实例化（实例化点继承外围特化） | 外围特化的语境 ∪（模板定义在 M 的接口中且实例化点不在其中时）M 主接口末尾 | ¶3 |
| 默认函数中引用的模板 | 默认函数的语境 | ¶4 |
| 其他模板特化 | 实例化点 | ¶5 |
| 常量求值引起的实例化 | 求值语境中的每个点 | ¶6 |
| 其他 | 该点本身 | ¶7 |
| 用途 | 依赖名的 ADL；可达性 | ¶1 |
