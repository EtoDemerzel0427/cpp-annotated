---
title: 实例化语境
summary: 模板在一个模块里定义、在另一个翻译单元里实例化时，依赖名的 ADL 和声明的可达性要从哪些程序点去看；默认函数、嵌套实例化、常量求值各有规则。
status: done
since: c++20
papers: P1103R3
related: module.reach, module.global.frag, temp.point, temp.dep, basic.lookup.argdep, expr.const.reflect, class.compare.default
tags: 模块, 模板, 实例化, 可达性
updated: 2026-10-19
---

!!! tldr
    - 实例化语境是一组程序点。依赖名的 ADL 从其中每一点各查一遍，声明从其中任一点可达就算可达，所以点越多，能用的东西越多。
    - 普通代码的语境只有它自己这一点；直接实例化一个模板，语境是它的实例化点，通常在使用者那里。
    - 嵌套实例化另外加上模板所在模块主接口单元的末尾，所以模板内部调用的辅助模板能用到模块接口里可达的一切。
    - 只通过别的模块间接接触到的头文件单元，从实例化语境看是否可达是未指明的：需要什么就直接 `import` 什么。

## 模板在哪里看

没有模块时，模板实例化看到什么由**实例化点**（[[g:point-of-instantiation|point of instantiation]]，[[temp.point]]）决定，大致是使用模板的那条声明之后，本翻译单元在它之前声明的东西都能用。头文件被粘贴进每个翻译单元，模板定义处看得到的，实例化处一般也看得到。

模块打破了这个假设。模板在模块 M 的接口单元里定义，实例化却发生在导入者那里，两处看到的东西可能完全不同：定义处能看到 M 自己导入的模块、全局模块片段里的头文件、M 没导出的实体；实例化处只能看到导入者自己导入的东西。实例化时，依赖名（[[temp.dep]]，含义取决于模板实参的名字）的查找和类型完整性应该以哪边为准？标准的回答是给出一组点，两边的一部分都算。

## 定义（¶1）

¶1 **实例化语境**（[[g:instantiation-context|instantiation context]]）是程序中的一组点，它决定在某个声明或某次模板实例化的语境中，实参依赖查找（ADL，[[basic.lookup.argdep]]）能找到哪些声明，以及哪些声明可达（[[module.reach]]）。两处使用分别是：

- 依赖名的 ADL 除了在通常的位置查找，还要从实例化语境中的每一点各查一遍（[[basic.lookup.argdep#4]]）；
- 一个声明从实例化语境中任何一点可达，它就是可达的（[[module.reach#4]]）。

两者都是取并集，所以点越多，能找到、能用的东西越多。下面各段规定在各种情形下语境里有哪些点。

## 各种情形

### 普通代码和直接实例化（¶7、¶5）

¶7 不属于下面任何情形时，程序中某一点的实例化语境只包含这一点本身。普通的非模板代码就是这样。

¶5 实例化其他模板特化时，实例化语境包含该模板的实例化点。导入者在普通函数里写 `f<int>()`，`f<int>` 的实例化点在导入者的翻译单元里，语境就只有那里。

### 嵌套实例化（¶3）

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
  return outer(p);   // inner<Detail*> 是嵌套实例化（¶3）
}
```

```cpp title="use-direct.cpp" unspecified
import M;
int main() {
  auto p = make();
  return direct(p);  // direct<Detail*> 是直接实例化（¶5）
}
```

`Detail` 定义在实现分区 `M:Impl` 里。实现分区不是模块接口单元，从导入者看不是必然可达的；但 `M.cppm` 直接导入了它，所以从 M 主接口的末尾看是必然可达的（[[module.reach#1]]）。

¶3 一个模板在另一个模板特化里以依赖于模板形参的方式被引用时，它的实例化点规定为外围特化的实例化点（[[temp.point#1]]）。这种嵌套实例化的语境包含：

- 外围特化的实例化语境中的每一点；以及
- 如果这个模板定义在模块 M 的某个接口单元里，而实例化点不在 M 的接口单元里，还包含 M 的主模块接口单元的 *declaration-seq* 末尾这一点（有私有模块片段时，在片段之前）。

`inner<Detail*>` 在 `outer<Detail*>` 里被依赖地引用，属于这种情形，语境里有 M 主接口的末尾，那里 `Detail` 完整，所以 `use-outer.cpp` 良构。`direct<Detail*>` 是直接实例化，语境只有 `use-direct.cpp` 里的实例化点，`M:Impl` 从那里不是必然可达的，是否合法未指明（[[module.reach#2]]）。

选主接口末尾，是因为到了那里模块 M 的接口已经完整建立：所有接口分区都已导入，M 自己的 `import` 都已生效。模板作者可以期望，M 的接口能看到的东西，模板内部都能用。直接实例化不需要这条：导入者对 M 的接口单元有接口依赖，M 的接口单元本身必然可达。嵌套实例化的实例化点继承自外围特化，可能离 M 很远，所以要把 M 主接口的末尾显式加进来。

!!! impl "Clang 23 没有按 ¶3 处理"
    本机 Clang 23 对两个使用者都报 `definition of 'Detail' must be imported from module 'M' before it is required`。对 `use-direct.cpp` 这是允许的选择；对 `use-outer.cpp`，Clang 看来没有实现 ¶3 加入主接口末尾的规则，至少对实现分区如此。编译 `M.cppm` 时 Clang 还警告 `importing an implementation partition unit in a module interface is not recommended. Names from M:Impl may not be reachable`，说明它有意不把接口中导入的实现分区当作对外可达。

    可移植的写法是：导出模板需要其定义的类型，放进接口分区并由主接口 `export import`，或者直接放进主接口。

### 默认函数（¶2、¶4）

¶2 隐式定义一个**默认函数**（defaulted function，`= default` 的或隐式声明的特殊成员函数和比较运算符，[[special]]、[[class.compare.default]]）时，实例化语境包含两部分：类定义处的实例化语境中的每一点，以及导致这次隐式定义的那个构造的实例化语境中的每一点。

例如模块 M 里有 `export struct S { T t; bool operator==(const S&) const = default; };`，导入者写 `s1 == s2`，触发 `operator==` 的隐式定义。比较 `t` 时查找 `T` 的 `operator==`，既能用 M 里类定义处可达的东西，也能用导入者使用处可达的东西。

¶4 默认函数的隐式定义里引用了模板、因而隐式实例化它时，实例化语境包含该默认函数的实例化语境中的每一点。比如默认的 `operator==` 比较一个 `std::vector<T>` 成员，触发 `vector` 的 `operator==` 的实例化。

### 常量求值引起的实例化（¶6）{{c++26}}

¶6 作为核心常量表达式求值的表达式导致某个构造被隐式实例化时，实例化语境包含**求值语境**（[[expr.const.reflect]]）中的每一点。

注 1 说明，这种隐式实例化可能来自对库函数的调用，比如反射元函数 `std::meta::substitute`（[[meta.reflection]]）。求值语境可以包含与 `std::meta::define_aggregate` 产生的注入声明关联的合成点。也就是说，常量求值过程中补全的类，对求值中触发的实例化也是可见的。

### 只有这些点（¶8）

¶8 实例化语境只包含以上各段规定的点，实现不能自行添加点，让更多声明可达或能被 ADL 找到。实现可以自由决定的是另一件事：[[module.reach#2]] 允许它把额外的翻译单元视为可达。

## 标准例子（¶9）

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
  g(0);       // 是否合法未指明
}
```

`foo<int, X>` 要复制 `X`，需要 `X` 的定义。它的实例化语境包含 TU #1 的末尾（¶9.1）、TU #2 的末尾（¶9.2）和调用 `f(0)` 的位置（¶9.3）。在 TU #2 末尾，`defn.h` 已被直接导入，`X` 的定义可达，所以 `f(0)` 合法。

`bar<int, X*>` 的 `auto v = *u;` 同样要复制 `X`。它的语境包含 TU #1 的末尾（¶9.4）、TU #3 的末尾（¶9.5，那里只导入了 `decl.h`，`X` 不完整）和调用 `g(0)` 的位置（¶9.6）。`test.cpp` 经由 M1 对 `defn.h` 的头文件单元有接口依赖，但它既不是模块接口单元，也没有被 `test.cpp` 直接导入，所以不是必然可达的。实现可以把它视为可达，也可以不这样做，于是 `g(0)` 是否合法未指明。

!!! impl "本机验证"
    用 Clang 23 的头文件单元（`-fmodule-header=user`）构建 `defn.h`、`decl.h`，再依次构建 stuff、M1、M2，编译 `test.cpp`：`f(0)` 通过；`g(0)` 报 `definition of 'X' must be imported from module './defn.h' before it is required`，附注 `definition here is not reachable`。Clang 选择不把额外的翻译单元视为可达，这是标准允许的。

!!! lawyer "¶9.2 从哪里来"
    按字面推导，¶9.2 并不显然。`f<int>` 由 `test.cpp` 的非模板代码直接引用，属于 ¶5，语境只有它在 TU #4 的实例化点。¶3 为 `foo<int, X>` 加入的是 `foo` 所在模块 stuff 的主接口末尾，也就是 TU #1，而不是 TU #2。

    例子的意图是：模板 `f` 定义处（M1 接口末尾）可达的东西，应当可供 `f` 内部引发的嵌套实例化使用，这也是 ¶3 的设计目的。但要从规范性文字中读出这一点，需要把 ¶3 理解为沿外围特化链累积每一层模板所在模块的主接口末尾。这是措辞上值得留意的一处缺口；Clang 接受 `f(0)`，与例子的结论一致。

## 与 ADL 的关系

[[basic.lookup.argdep#5]] 的标准例子展示了实例化语境在 ADL 中的作用。模块 N 的导出模板 `apply(t, u)` 里有依赖调用 `f(t, u)` 和 `g(t)`。实例化时，ADL 从语境中的每一点查找，包括 N 的接口末尾和调用处，所以在 N 的接口里可见的 `S::f` 也能被考虑。而 N 里的 `static int R::g(X)` 虽然在 N 的接口末尾可见，却有内部链接，不能在 N 的接口单元之外使用，所以那次调用非良构。

## 历史与演进

!!! history
    - 实例化语境随模块合并提案 [[P1103R3]] 进入 C++20，取代了 Modules TS 中关于实例化时哪些声明可见的较为模糊的规则。
    - C++26 加入 ¶6，把常量求值的求值语境（静态反射引入的合成点和注入声明）纳入实例化语境。

## 常见误解

!!! pitfall "模板在模块里测试通过，导入者实例化却失败"
    模板依赖某个类型的完整性或某个 ADL 候选，而它们只在模块内部的实现分区，或全局模块片段里（且被丢弃）。模块作者在模块内测试时，实例化点就在模块内，一切正常；导入者实例化时，语境不包含那些点。测试模块时，要从模块外部实例化导出的模板。

!!! pitfall "依赖头文件单元的传递可达"
    像 ¶9 的 `g(0)` 那样，只通过别的模块间接接触到某个头文件单元时，其中的定义是否可达是未指明的。需要什么就直接 `import` 什么。

## 思考题

!!! question "思考题"
    在 ¶9 中，如果 TU #4 在 `import M2;` 之后再加一行 `import "defn.h";`，`g(0)` 是否就确定合法了？

<details markdown="1">
<summary>答案</summary>

是。`bar<int, X*>` 的实例化语境包含调用 `g(0)` 的点（¶9.6），这一点在 `import "defn.h";` 之后。`defn.h` 头文件单元由 TU #4 直接导入，必然可达（[[module.reach#1]]），所以 `X` 的定义可达。`defn.h` 与 `decl.h` 中的 `X` 都附属于全局模块并有外部链接，是同一个实体，所以这个定义就是 `X*` 里那个 `X` 的定义。本机 Clang 23 也接受这样修改后的 `test.cpp`。
</details>
