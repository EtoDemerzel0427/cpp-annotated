---
title: 工厂与自注册
summary: 按名字或 ID 创建对象而调用方不必知道具体类型：返回 unique_ptr 的工厂函数、clone 与协变返回类型、名字到创建函数的注册表，各翻译单元用静态对象自注册的写法，以及它在静态库、延迟初始化、初始化顺序和多线程下为什么会失效，编译期注册表和抽象工厂。
status: draft
order: 70
since: c++98
papers: P0386R2, P2996R13
related: class.virtual, basic.start.dynamic, basic.start.static, basic.stc.static, stmt.dcl, dcl.inline, basic.link, temp.inst, lex.phases, unique.ptr, topics/ownership-and-smart-pointers, toolchain/linking-and-symbols, patterns/singleton, patterns/crtp, patterns/type-erasure
tags: 设计模式, 工厂, 注册表, 静态初始化, 静态库, 链接
updated: 2026-10-19
---

!!! tldr
    - 工厂函数返回 `std::unique_ptr<Base>`：所有权交给调用方，调用方需要共享时可以直接转成 `shared_ptr`。协变返回类型只对指针和引用成立，`unique_ptr<Derived>` 不能覆盖返回 `unique_ptr<Base>` 的虚函数。
    - 注册表是名字到创建函数的映射。自注册把注册写进每个具体类型所在 `.cpp` 的一个全局变量初始化里，新增类型不必修改任何中心文件。
    - 自注册依赖三件标准和链接器都不保证的事：目标文件被链接进来（静态库里没人引用的成员会被丢掉）、动态初始化在 `main` 之前发生（标准允许推迟）、注册表在注册之前已经构造（不同翻译单元间的初始化顺序未规定）。
    - 注册表放在函数局部静态变量里能解决第三条；前两条要靠链接选项（`-force_load`、`--whole-archive`）或让主程序显式引用每个模块。
    - 类型集合在编译期已知时，用类型列表在编译期生成工厂更简单：没有静态初始化，没有链接问题，重复的名字能用 `static_assert` 挡住。

## 按名字创建对象

配置文件里写着 `circle`、`square`，程序要据此创建对应的对象。最直接的写法是一个大 `if` 链：

```cpp run title="switch-factory.cpp" ok
#include <cstdio>
#include <memory>
#include <string_view>

struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Circle : Shape { double area() const override { return 3.14159; } };
struct Square : Shape { double area() const override { return 1.0; } };

std::unique_ptr<Shape> make_shape(std::string_view name) {
  if (name == "circle") return std::make_unique<Circle>();
  if (name == "square") return std::make_unique<Square>();
  return nullptr;                        // 未知名字
}

int main() {
  for (auto n : {"circle", "square", "hexagon"}) {
    auto s = make_shape(n);
    std::printf("%s: %s\n", n, s ? "ok" : "unknown");
  }
}
```

调用方只认识 `Shape` 和一个字符串，不需要包含 `Circle` 的头文件，这是**工厂**（factory）的全部意义：把创建哪个具体类型的决定，从调用方挪到一个地方。

问题在于这个地方本身。`make_shape` 必须看到所有具体类型的定义，每加一个类型都要改它、重新编译它。类型来自不同团队、不同库，甚至运行时才加载的插件时，这个中心文件就成了瓶颈。

## 工厂函数返回 `unique_ptr<Base>`

工厂创建的对象要交给调用方，返回类型应该表达这次所有权转移。三种常见选择的含义不同：

| 返回类型 | 含义 | 问题 |
|---|---|---|
| `Shape*` | 看不出调用方要不要 `delete` | 忘记释放就泄漏；表达式中途抛异常也泄漏 |
| `std::unique_ptr<Shape>` | 调用方成为唯一所有者 | 无 |
| `std::shared_ptr<Shape>` | 调用方与工厂共享 | 强迫每个调用方付控制块的代价 |

`unique_ptr<Shape>` 是默认选择。它和裸指针一样大，调用方想共享时可以直接用它初始化 `shared_ptr<Shape>`，反过来则做不到。为什么 `Shape` 必须有虚析构函数、`unique_ptr` 的大小和生成代码，见 [[topics/ownership-and-smart-pointers]]。

工厂失败的方式也要选。上面返回空指针表示名字未知，调用方必须检查；也可以抛异常或返回 `std::expected<std::unique_ptr<Shape>, Error>`。名字来自外部输入时，未知名字是正常情况，空指针或 `expected` 比异常更合适。

## 虚构造函数：clone

构造函数不能是虚函数：调用构造函数之前必须已经知道要构造什么类型。可是复制一个只知道基类引用的对象时，恰好需要按动态类型来构造。惯用的办法是一个虚函数 `clone`，每个派生类在里面复制自己，这个惯用法常被称作**虚构造函数**（virtual constructor）。

### 协变返回类型只适用于指针和引用

覆盖函数的返回类型一般必须和被覆盖的函数相同。¶8 允许一个例外：两者都是类的指针（或都是类的引用），而且派生类版本返回的类以基类版本返回的类为可访问、无歧义的基类，这叫**协变返回类型**（[[g:covariant-return-type]]，[[class.virtual#8]]）。

<div class="compare" markdown="1">

```cpp title="raw.cpp" ok
struct Shape {
  virtual ~Shape() = default;
  virtual Shape* clone() const = 0;
};
struct Circle : Shape {
  Circle* clone() const override {
    return new Circle(*this);  // OK：协变
  }
};
```

```cpp title="smart.cpp" error
#include <memory>
struct Shape {
  virtual ~Shape() = default;
  virtual std::unique_ptr<Shape>
  clone() const = 0;
};
struct Circle : Shape {
  std::unique_ptr<Circle>
  clone() const override;  // error
};
```

</div>

右边被拒绝，因为 `unique_ptr<Circle>` 是一个类类型，不是指向类的指针。`unique_ptr<Circle>` 能隐式转换成 `unique_ptr<Shape>`，但这两个模板特化之间没有继承关系，¶8 的条件一条也不满足。本机 Clang 报告 `virtual function 'clone' has a different return type ('unique_ptr<Circle>') than the function it overrides`。

协变的指针为什么可行？通过 `Shape&` 调用时，实际运行的是 `Circle::clone`，返回的 `Circle*` 会被转换成静态选中的那个函数的返回类型 `Shape*`（[[class.virtual#9]]）。对指针做这个派生到基类的转换只是调整地址，编译器可以在覆盖函数的入口或调用点插入。对任意类类型做转换要调用转换构造函数，标准不允许虚函数机制做这种事。

### 非虚的 `clone` 包一层

想要两全，就把返回智能指针的公开接口和做实际工作的虚函数分开：

```cpp run title="clone.cpp" ok
#include <cstdio>
#include <memory>

class Shape {
public:
  virtual ~Shape() = default;
  std::unique_ptr<Shape> clone() const {
    return std::unique_ptr<Shape>(clone_impl());
  }
  virtual double area() const = 0;
private:
  virtual Shape* clone_impl() const = 0;
};

class Circle : public Shape {
public:
  explicit Circle(double r) : r_(r) {}
  std::unique_ptr<Circle> clone() const {  // 隐藏 Shape::clone
    return std::unique_ptr<Circle>(clone_impl());
  }
  double area() const override { return 3.14159 * r_ * r_; }
private:
  Circle* clone_impl() const override {    // 协变：裸指针可以
    return new Circle(*this);
  }
  double r_;
};

int main() {
  Circle c(2);
  std::unique_ptr<Circle> c2 = c.clone();  // 静态类型是 Circle
  const Shape& s = c;
  std::unique_ptr<Shape> s2 = s.clone();   // 动态分派到 Circle
  std::printf("%.2f %.2f\n", c2->area(), s2->area());
}
```

裸指针只在 `clone_impl` 和包装函数之间存在一瞬间，立刻交给 `unique_ptr`。`Circle::clone` 不是覆盖，而是隐藏了 `Shape::clone`：通过 `Circle` 调用得到 `unique_ptr<Circle>`，通过 `Shape` 调用得到 `unique_ptr<Shape>`，两者都走 `clone_impl` 的动态分派。公开函数非虚、私有函数虚，正是 [[patterns/nvi|非虚接口]] 的结构；每个派生类重复的那两个函数，可以用 [[patterns/crtp|CRTP]] 基类生成。

C++26 的 `std::polymorphic<T>`（[[polymorphic]]）把这件事做成了库：它持有一个动态类型可能是 `T` 派生类的对象，复制时按动态类型深复制，不要求类层次提供 `clone`。截至写作时本机 libc++ 尚未提供它。

## 注册表：从名字到创建函数

去掉中心 `if` 链的第一步，是把它换成数据：一个从名字到**创建函数**（creator）的映射。下面的 `shape.h` 只含开头那个 `Shape` 接口。

```cpp title="registry.h"
#pragma once
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include "shape.h"

class ShapeRegistry {
public:
  using Creator = std::unique_ptr<Shape> (*)();
  bool add(std::string name, Creator c) {
    return creators_.emplace(std::move(name), c).second;
  }
  std::unique_ptr<Shape> create(std::string_view name) const {
    auto it = creators_.find(name);
    return it == creators_.end() ? nullptr : it->second();
  }
  std::size_t size() const { return creators_.size(); }
private:
  std::map<std::string, Creator, std::less<>> creators_;
};

ShapeRegistry& shape_registry();
```

```cpp title="registry.cpp"
#include "registry.h"
ShapeRegistry& shape_registry() {
  static ShapeRegistry r;   // 首次调用时构造
  return r;
}
```

几个细节：

- `std::less<>` 是透明比较器，`find` 可以直接拿 `string_view` 查找，不必先构造一个 `std::string`。
- 创建函数用普通函数指针。不捕获的 lambda 能隐式转换成函数指针，所以注册时照样可以写 lambda。只有创建函数需要携带状态（比如一个配置对象）时才需要 `std::function`，本机 libc++ 上它占 32 字节，函数指针占 8 字节。
- `add` 返回 `false` 表示名字重复。是覆盖、忽略还是报错，是注册表的策略，要在一处定下来。
- 注册表放在函数里的局部静态变量中，而不是命名空间作用域的全局变量。原因在下文初始化顺序一节。

## 自注册

有了注册表，还需要有人调用 `add`。如果还是由一个中心函数依次注册每个类型，问题只是换了个地方。**自注册**（self-registration）的做法是让每个具体类型在自己的 `.cpp` 里注册自己：

```cpp title="circle.cpp"
#include "registry.h"
namespace {
struct Circle : Shape {
  double area() const override { return 3.14159; }
};
const bool registered = shape_registry().add(
    "circle", [] () -> std::unique_ptr<Shape> {
      return std::make_unique<Circle>();
    });
}
```

`square.cpp` 写法相同。主程序只依赖注册表：

```cpp title="main.cpp"
#include <cstdio>
#include "registry.h"
int main(int argc, char** argv) {
  std::printf("%zu shapes registered\n", shape_registry().size());
  for (int i = 1; i < argc; ++i) {
    if (auto s = shape_registry().create(argv[i]))
      std::printf("%s: %.2f\n", argv[i], s->area());
    else
      std::printf("%s: unknown\n", argv[i]);
  }
}
```

`registered` 是一个命名空间作用域的变量，具有**静态存储期**（[[g:static-storage-duration]]，[[basic.stc.static#1]]）。它的初始值要调用函数才能算出来，所以不是常量初始化，而是**动态初始化**（[[g:dynamic-initialization]]，[[basic.start.static#2]]）。`add` 就在这次动态初始化中被调用。`registered` 本身从没被读过，但它的初始化有副作用，实现不能把它当成无用变量删掉（[[basic.stc.static#2]]）。

`Circle` 在匿名命名空间里，别的翻译单元根本看不见它。新增一个形状只需要新增一个 `.cpp` 并加进构建，`main.cpp` 和注册表都不用改。Google Test 的 `TEST` 宏就是这样工作的：每个测试展开成一个类和一个静态成员，静态成员的初始化把测试注册到全局列表里。

把四个目标文件直接链接在一起，一切正常：

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o circle.o square.o -o direct
$ ./direct circle square
2 shapes registered
circle: 3.14
square: 1.00
```

这里和下文的链接实验都在本机 arm64 macOS 上完成，编译器是 Homebrew Clang 23，链接器是系统的 `/usr/bin/ld`（`ld-1266.8`）。

## 自注册为什么会失效

自注册把类型是否存在交给了一个副作用：某个全局变量的初始化在 `main` 查询注册表之前运行过。这件事在三个地方可能不成立。

### 静态库：没人引用的成员不会被链接

把 `circle.o` 和 `square.o` 打包成静态库，其他什么都不变：

```text
$ llvm-ar rcs libshapes.a circle.o square.o
$ clang++ --ld-path=/usr/bin/ld main.o registry.o libshapes.a -o fromlib
$ ./fromlib circle square
0 shapes registered
circle: unknown
square: unknown
```

没有任何错误或警告，两个形状都消失了。链接器处理命令行上的 `.o` 文件时全部链接进来；处理静态库时，只提取能解决某个当前未定义符号的成员（详见 [[toolchain/linking-and-symbols]]）。`main.o` 和 `registry.o` 没有引用 `circle.o` 里的任何东西，而且也引用不了：

```text
$ llvm-nm -m --defined-only circle.o | grep ' external' | grep -vc weak
0
```

`circle.o` 不定义任何非弱的外部符号。`Circle`、`registered`、创建函数都在匿名命名空间里，具有内部链接；剩下的外部符号都是 `std::map`、`std::string` 等内联函数的弱定义，`registry.o` 里已经有了。这正是自注册想要的效果，没有人依赖具体类型。在链接器看来，没有人依赖的成员就不需要链接，它的全局变量初始化也就不存在。

标准对此没有说什么。翻译阶段 8 只说要链接库组件，以满足对当前翻译中没有定义的实体的引用（[[lex.phases#1]]）；没有被引用的组件属于程序吗，标准不回答。这是链接器的约定，不是语言规则。

解决办法是让链接器把整个库都链接进来，或者让主程序显式引用每个模块：

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o -Wl,-force_load,libshapes.a -o force
$ ./force circle
2 shapes registered
circle: 3.14
$ clang++ --ld-path=/usr/bin/ld main.o registry.o libshapes.a -Wl,-all_load -o allload
$ ./allload circle square
2 shapes registered
circle: 3.14
square: 1.00
```

| 方法 | 做法 | 代价 |
|---|---|---|
| Apple ld `-force_load,<lib>` | 无条件提取这一个库的全部成员 | 库里无关的成员也进来了 |
| Apple ld `-all_load` | 对所有静态库都这样做 | 同上，范围更大 |
| GNU ld、lld `--whole-archive <lib> --no-whole-archive`（据文档） | 包围的库全部提取 | 忘了关掉会把系统库也整个链接进来 |
| MSVC `link /WHOLEARCHIVE:<lib>`（据文档） | 同上 | 同上 |
| 不打静态库，直接链接目标文件（如 CMake 的 OBJECT 库） | 每个 `.o` 都在命令行上 | 构建脚本要改 |
| 锚点函数：`circle.cpp` 定义 `void link_circle() {}`，主程序调用它 | 让主程序引用每个模块 | 又回到了中心列表 |

`-Wl,-why_load` 能让 Apple ld 打印每个成员被提取的原因，排查时很有用：

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o libshapes.a -Wl,-all_load -Wl,-why_load -o x
-force_load caused load of .../libshapes.a[3](square.o)
-force_load caused load of .../libshapes.a[2](circle.o)
```

锚点函数的做法本机也验证过：`circle.cpp` 末尾加一行 `void link_circle() {}`，`main` 调用它，`circle.o` 就从库里被提取出来，注册数变成 1（`square.o` 仍然没有）。

!!! note "死代码剥离不受影响"
    已经链接进来的目标文件，自注册不会被 `-Wl,-dead_strip` 删掉。本机用 `-dead_strip` 链接四个 `.o`，仍然注册了两个形状。全局变量的初始化函数登记在 Mach-O 的 `__mod_init_func` 段（ELF 上是 `.init_array`）里，链接器把它当作根，从它可达的代码都会保留。这和 [[basic.stc.static#2]] 的要求一致。

### 动态初始化可以推迟

即使目标文件链接进来了，标准也不保证 `registered` 在 `main` 之前初始化。非块、非 inline 的静态存储期变量，动态初始化在 `main` 的第一条语句之前完成还是推迟进行，由实现定义（[[basic.start.dynamic#5]]）{{impl}}。

如果推迟，标准只要求它先于对同一翻译单元中任何非 inline 函数或变量的**非初始化 odr 使用**（[[g:non-initialization-odr-use]]，即不是由某个静态变量的初始化直接或间接引起的 [[g:odr-use|odr 使用]]，[[basic.start.dynamic#4]]）。脚注补充说，到了那个时刻，同一翻译单元里初始化有副作用的变量都要初始化，即使它们本身没有被 odr 使用。

把这条规则套在 `circle.cpp` 上：自注册的目的就是没有人使用这个翻译单元里的任何东西。查找注册表时通过函数指针调用创建函数，并没有以名字引用 `circle.cpp` 里的函数，不构成 odr 使用。如果实现选择推迟，就没有任何事件迫使 `registered` 初始化，标准允许 `circle` 永远不出现在注册表里。

主流实现不推迟普通全局变量的初始化（[[basic.start]] 的实现说明），所以这条规则在静态链接的程序里主要是理论上的。允许推迟的现实原因是动态库：用 `dlopen` 加载的共享库，它的全局变量只能在加载时初始化。本机把 `square.cpp` 编成 `libsquare.dylib`，注册表放在主程序和插件共用的 `libreg.dylib` 里：

```text
$ ./m
before dlopen: 1
after dlopen: 2
```

插件的自注册在 `dlopen` 返回之前运行。这正是插件系统想要的行为，但它意味着注册可能发生在 `main` 开始之后、其他线程正在查询注册表的时候，见下文线程安全一节。

### 注册表自己的初始化顺序

假设把注册表写成一个普通的全局变量，并且它的构造函数做了点事，比如预先注册一个内置类型（`registry.h` 里相应地加上构造函数的声明）：

```cpp title="registry.cpp（有问题的版本）" ub
#include "registry.h"
namespace {
struct Empty : Shape { double area() const override { return 0; } };
}
ShapeRegistry::ShapeRegistry() {
  add("empty", [] () -> std::unique_ptr<Shape> {
    return std::make_unique<Empty>();
  });
}
ShapeRegistry g_registry;                     // 命名空间作用域
ShapeRegistry& shape_registry() { return g_registry; }
```

`circle.cpp` 的 `registered` 和 `registry.cpp` 的 `g_registry` 在不同的翻译单元里。两者都是有序初始化的变量，但只有同一翻译单元里的有序变量才按定义的先后排序（[[basic.start.dynamic#3]]），跨翻译单元的先后没有规定。`registered` 先初始化时，`add` 访问的是一个还没构造的 `std::map`。这就是**静态初始化顺序灾难**（[[g:static-initialization-order-fiasco]]），UB。

本机的结果取决于链接顺序：

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o circle.o square.o -o g1 && ./g1 circle empty
3 shapes registered
circle: 3.14
empty: 0.00
$ clang++ --ld-path=/usr/bin/ld main.o circle.o square.o registry.o -o g2 && ./g2 circle empty
Segmentation fault: 11
```

加上 `-fsanitize=address,undefined` 后，UBSan 先报告 libc++ `__tree` 里 `member access within null pointer`，ASan 随后报告 SEGV，栈底是 `circle.cpp:6` 的 `__cxx_global_var_init`。本机的 dyld 按目标文件在命令行上的顺序运行各翻译单元的初始化函数，这是观察结果，不是任何规范的保证。

!!! impl "没有构造函数时为什么没出事"
    把上面的构造函数去掉，只留一个 `std::map` 成员，本机两种链接顺序都能正常工作。原因是 Clang 把 `g_registry` 的构造做成了静态初始化：生成的初始化函数只向 `__cxa_atexit` 登记析构函数，`map` 的内容直接由零初始化和常量数据得到。[[basic.start.static#3]] 允许实现这样做，即使标准没有要求（`constinit ShapeRegistry r;` 会被拒绝，说明它不是常量初始化）。代码碰巧没有崩溃，不等于它正确。

修复是前面 `registry.cpp` 已经采用的写法：把注册表放进函数的局部静态变量。块作用域的静态变量在控制第一次经过它的声明时初始化（[[stmt.dcl#3]]），所以无论哪个翻译单元先调用 `shape_registry()`，拿到的都是已经构造好的对象。本机用这个版本以两种链接顺序运行，结果相同。这个写法以及它的析构顺序问题，在 [[patterns/singleton|单例与静态初始化顺序]] 中详细讨论。

## 在头文件里注册：inline 变量

有时希望注册写在头文件里，比如只有头文件的库，或者想让注册跟着类型定义走。头文件会被多个翻译单元包含，变量的链接决定了注册发生几次：

```cpp title="triangle.h"
#pragma once
#include <cstdio>
#include "registry.h"
struct Triangle : Shape {
  double area() const override { return 0.5; }
};
inline const bool triangle_registered = [] {  // 去掉 inline 会怎样？
  bool ok = shape_registry().add("triangle", [] () -> std::unique_ptr<Shape> {
    return std::make_unique<Triangle>();
  });
  std::printf("add(\"triangle\") -> %s\n", ok ? "true" : "false");
  return ok;
}();
```

两个 `.cpp` 都包含这个头文件。本机运行：

| 声明 | 输出 |
|---|---|
| `inline const bool` | `add("triangle") -> true`，只调用一次 |
| `const bool` 或 `static const bool` | 一次 `true`，一次 `false`，每个翻译单元各注册一次 |

命名空间作用域的 `const` 变量，只要不是 `inline` 也没有声明 `extern`，就具有内部链接（[[basic.link#3.2]]），每个包含头文件的翻译单元都有自己的一份，初始化也各做一次。`inline` 变量（{{c++17}}，[[P0386R2]]）则可以在多个翻译单元里定义，但只是一个实体、一个地址（[[dcl.inline#2]]），实现用一个守卫变量保证它只初始化一次。

inline 变量的初始化是**部分有序**的（[[basic.start.dynamic#1]]），推迟时只需先于对它自己的非初始化 odr 使用（[[basic.start.dynamic#6]]）。它没有解决静态库的问题：只有包含了 `triangle.h` 的某个目标文件被链接进来，注册才会发生。

### 用类模板的静态成员自动注册

更常见的写法是让具体类型继承一个模板基类，由基类的静态数据成员完成注册，具体类型不必写任何注册代码：

```cpp title="autoreg.h"
#pragma once
#include "registry.h"

template <class D>
struct AutoRegister {
  static std::unique_ptr<Shape> create() { return std::make_unique<D>(); }
  static inline const bool registered =
      shape_registry().add(D::name, &create);
};
```

```cpp title="circle.h"
#pragma once
#include "autoreg.h"
struct Circle : Shape, AutoRegister<Circle> {
  static constexpr const char* name = "circle";
  double area() const override { return 3.14159; }
};
```

本机把 `circle.h` 包含进两个翻译单元，运行结果是 `0 shapes registered`。

原因在 [[temp.inst#4]]：类模板特化被隐式实例化时，静态数据成员只实例化声明；只有当这个成员以需要其定义存在的方式被使用时，它的定义才被实例化，初始化及其副作用才会发生。`AutoRegister<Circle>` 被实例化了（它是 `Circle` 的基类），但没有人使用 `registered`，所以它的初始化根本不存在。[[temp.inst#12]] 还明确禁止实现在不需要时实例化静态数据成员。

修复是在每个具体类型里放一处 odr 使用，迫使它实例化：

```cpp
struct Square : Shape, AutoRegister<Square> {
  static constexpr const char* name = "square";
  static constexpr const bool& anchor = registered;  // odr 使用
  double area() const override { return 1.0; }
};
```

绑定引用使用了 `registered` 的地址而不读它的值，这是一次 odr 使用，`registered` 的定义随之实例化。本机加上这一行后 `square` 出现在注册表里，并且两个翻译单元都包含 `square.h` 也只注册一次。类模板静态数据成员的初始化是**无序**的（[[basic.start.dynamic#1]]），它和其他翻译单元里任何变量的先后都没有规定，所以注册表仍然必须是函数局部静态变量。

!!! pitfall "用虚函数触发实例化不可移植"
    另一种流传的写法是在 `AutoRegister` 里放一个使用 `registered` 的虚函数，指望虚函数随类的 vtable 一起被实例化。[[temp.inst#12]] 规定，一个本来不会被实例化的虚成员函数是否被隐式实例化，是未指明的 {{unspec}}。这个技巧在某个编译器上能用，换一个编译器就可能静默失效。

## 线程安全

注册表可能在三个时刻被访问，安全性要求不同：

1. `main` 之前的静态初始化期间。如果此时程序没有启动其他线程，同一翻译单元里有序变量的初始化按定义顺序排序，其余的至多是不确定顺序的（[[basic.start.dynamic#3]]），不会同时运行。一旦某个初始化启动了线程，各初始化在哪个线程运行就是未指明的，可能并发。
2. `main` 之后只读。多个线程同时调用 `std::map` 的 `const` 成员函数不构成数据竞争（[[res.on.data.races]]），不需要锁。
3. 运行中加载插件。`dlopen` 在某个线程里触发注册（写），其他线程同时在查找（读），这是**数据竞争**（[[g:data-race]]），UB（[[intro.races]]）。

函数局部静态变量的初始化本身是线程安全的：多个线程同时第一次进入声明时，其余线程等待初始化完成（[[stmt.dcl#3]]）。但这只保护构造，不保护之后的 `add` 和 `create`。需要第 3 种情况时，用读写锁：

```cpp run title="locked-registry.cpp" ok
#include <cstdio>
#include <map>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <string_view>
#include <thread>

struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Circle : Shape { double area() const override { return 3.14; } };

class ShapeRegistry {
public:
  using Creator = std::unique_ptr<Shape> (*)();
  bool add(std::string name, Creator c) {
    std::unique_lock lock(m_);                 // 写：独占
    return creators_.emplace(std::move(name), c).second;
  }
  std::unique_ptr<Shape> create(std::string_view name) const {
    Creator c = nullptr;
    {
      std::shared_lock lock(m_);               // 读：共享
      auto it = creators_.find(name);
      if (it == creators_.end()) return nullptr;
      c = it->second;
    }
    return c();                                // 在锁外构造对象
  }
private:
  mutable std::shared_mutex m_;
  std::map<std::string, Creator, std::less<>> creators_;
};

ShapeRegistry& shape_registry() {
  static ShapeRegistry r;                      // 初始化是线程安全的
  return r;
}

int main() {
  auto make = [] () -> std::unique_ptr<Shape> { return std::make_unique<Circle>(); };
  shape_registry().add("circle", make);
  std::jthread plugin([&] {                    // 模拟运行中加载插件
    for (int i = 0; i < 1000; ++i) shape_registry().add("p" + std::to_string(i), make);
  });
  int found = 0;
  for (int i = 0; i < 1000; ++i) found += shape_registry().create("circle") != nullptr;
  std::printf("%d\n", found);
}
```

本机加 `-fsanitize=thread` 运行没有报告。删掉两行加锁语句后，TSan 报告 `data race`，位置在 libc++ 的 `__tree_balance_after_insert`。创建函数在锁外调用，这样一个形状的构造函数即使反过来查询注册表，也不会在同一把锁上死锁。

不需要运行时注册的程序可以更简单：约定所有注册在 `main` 之前完成，之后注册表只读，不加锁。可以在 `main` 开头调用一个 `freeze()`，之后的 `add` 一律报错，把约定变成检查。

## 编译期注册表

自注册的所有麻烦都来自一个前提：类型集合直到链接时甚至运行时才确定。如果类型集合在编译时就已知，同一个工厂可以完全在编译期生成：

```cpp run title="type-list-factory.cpp" ok
#include <array>
#include <cstdio>
#include <memory>
#include <string_view>

struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Circle : Shape {
  static constexpr std::string_view name = "circle";
  double area() const override { return 3.14159; }
};
struct Square : Shape {
  static constexpr std::string_view name = "square";
  double area() const override { return 1.0; }
};

template <class... Ts> struct type_list {};
using all_shapes = type_list<Circle, Square>;  // 唯一需要维护的列表

template <class... Ts>
consteval bool unique_names(type_list<Ts...>) {
  std::array<std::string_view, sizeof...(Ts)> n{Ts::name...};
  for (std::size_t i = 0; i < n.size(); ++i)
    for (std::size_t j = i + 1; j < n.size(); ++j)
      if (n[i] == n[j]) return false;
  return true;
}
static_assert(unique_names(all_shapes{}), "duplicate shape name");

template <class... Ts>
std::unique_ptr<Shape> make_shape(std::string_view name, type_list<Ts...>) {
  std::unique_ptr<Shape> r;
  (void)((name == Ts::name && (r = std::make_unique<Ts>(), true)) || ...);
  return r;
}

int main(int argc, char** argv) {
  for (int i = 1; i < argc; ++i) {
    auto s = make_shape(argv[i], all_shapes{});
    std::printf("%s: %s\n", argv[i], s ? "ok" : "unknown");
  }
}
```

`make_shape` 里的折叠表达式按 `||` 展开，每一项比较一个名字，匹配时创建对象并短路。本机 `-O2` 下整个 `make_shape` 内联进 `main`：先调用 `strlen`，长度不是 6 就直接返回空；否则用两条整数比较检查 6 个字节。没有 `std::map`，没有堆上的节点，程序也不需要任何动态初始化。名字重复在编译时就被 `static_assert` 拒绝，自注册版本只能在运行时从 `add` 的返回值发现。

代价是 `all_shapes` 又是一个中心列表，所在的翻译单元必须看到每个类型的完整定义。这与开头的 `if` 链是同一种依赖，只是写法更紧凑、能做编译期检查。类型集合由一个团队控制时，这通常是最好的选择；集合需要由互不知情的模块扩展时，还是要回到运行时注册。类型列表、折叠表达式等技巧见 [[topics/compile-time-programming]]。

### C++26 静态反射

C++26 的静态反射（[[meta.reflection]]，[[P2996R13]]）提供了另一种生成类型列表的方式：`std::meta::members_of` 可以列出一个命名空间中在当前位置之前声明的成员（[[meta.reflection.member.queries]]），再用 `is_base_of_type` 筛出 `Shape` 的派生类，这样就不必手写 `all_shapes`。下面是按当前草案写的示意，本机 Clang 23 不提供 `<meta>`，没有验证过，所以不标判定：

```cpp
#include <meta>
namespace shapes { /* 所有具体形状都定义在这里 */ }

consteval auto shape_types() {
  std::vector<std::meta::info> v;
  for (auto r : members_of(^^shapes, std::meta::access_context::unprivileged()))
    if (is_type(r) && is_class_type(r) && is_complete_type(r) &&
        is_base_of_type(^^Shape, r))
      v.push_back(r);
  return std::define_static_array(v);
}
```

它仍然只能看到当前翻译单元里已经声明的类型，所以仍然需要一个包含所有形状头文件的翻译单元；它省掉的是手写列表，没有改变编译期注册表的依赖结构。

## 抽象工厂

前面的工厂一次创建一个对象。有时要创建一族相互配套的对象，比如同一套界面主题下的按钮和复选框，混用两套主题的部件是错误的。**抽象工厂**（abstract factory）把一族创建函数放进一个接口：

```cpp run title="abstract-factory.cpp" ok
#include <cstdio>
#include <memory>

struct Button   { virtual ~Button() = default;   virtual void draw() const = 0; };
struct Checkbox { virtual ~Checkbox() = default; virtual void draw() const = 0; };

struct WidgetFactory {
  virtual ~WidgetFactory() = default;
  virtual std::unique_ptr<Button>   button() const = 0;
  virtual std::unique_ptr<Checkbox> checkbox() const = 0;
};

struct DarkButton : Button { void draw() const override { std::puts("dark button"); } };
struct DarkCheckbox : Checkbox { void draw() const override { std::puts("dark checkbox"); } };
struct DarkFactory : WidgetFactory {
  std::unique_ptr<Button> button() const override { return std::make_unique<DarkButton>(); }
  std::unique_ptr<Checkbox> checkbox() const override { return std::make_unique<DarkCheckbox>(); }
};

void build_dialog(const WidgetFactory& f) {  // 不知道是哪套主题
  f.button()->draw();
  f.checkbox()->draw();
}

int main() { build_dialog(DarkFactory{}); }
```

`build_dialog` 拿到的部件一定出自同一个工厂。具体工厂本身可以通过上面的注册表按名字创建，两个模式经常一起出现。主题在编译期就确定时，可以把工厂换成模板参数，见 [[patterns/policy-based-design|基于策略的设计]]，这样省掉虚调用，也能让编译器内联。

## 代价

下面的数字来自本机 arm64 macOS、Clang 23 `-O2`、libc++，注册表有 32 个条目，循环一千万次取平均。

| 项目 | 观察结果 |
|---|---|
| 直接 `make_unique` 创建并销毁一个对象 | 约 25 ns，主要是一次 `new` 和 `delete` |
| 经注册表按名字创建并销毁 | 约 36 ns |
| 其中 `std::map` 按 `string_view` 查找 | 约 12 ns |
| 创建函数：函数指针 / `std::function` | 8 / 32 字节 |
| 每个自注册的类型 | 一次 `main` 之前的函数调用、一个 `map` 节点、一个字符串 |
| 类型列表工厂 | 内联成长度比较和整数比较，无动态初始化 |

按名字查找的开销与一次堆分配同一量级。工厂通常用在读配置、反序列化这类本来就要解析字符串的地方，这点开销很少成为问题；在热循环里按名字创建对象则是设计问题，应该把查找结果（创建函数指针）缓存起来。

更大的代价不在运行时，而在可理解性上：自注册程序里有哪些类型，读源码看不出来，要看构建系统和链接选项。

## 常见陷阱

!!! pitfall "静态库里的自注册静默消失"
    没有链接错误，没有警告，只是注册表里少了东西。单元测试直接链接 `.o` 能通过，换成静态库发布后失效，是这个模式最典型的故障。发现注册数不对时，先用 `-Wl,-why_load`（Apple ld）或检查链接映射文件，确认目标文件是否被提取。

!!! pitfall "在头文件里写 `const bool registered`"
    命名空间作用域的 `const` 变量默认是内部链接，每个包含该头文件的翻译单元都注册一次。要用 `inline`。

!!! pitfall "在静态初始化期间使用注册表"
    另一个全局变量的初始化里调用 `shape_registry().create(...)`，能不能找到某个类型，取决于那个类型的自注册是否已经运行，而跨翻译单元的顺序没有规定。函数局部静态变量只保证注册表本身已经构造，不保证内容齐全。

!!! pitfall "注册表比使用者先销毁"
    函数局部静态变量在 `exit` 时按构造完成的逆序销毁（[[basic.start.term#4]]）。如果某个静态对象在注册表构造之前就构造完成，又在析构函数里访问注册表，访问的就是已经销毁的对象。常见的规避办法是让注册表永不销毁：`static auto* r = new ShapeRegistry; return *r;`，代价是泄漏检测工具会报告它。

## 什么时候用

| 情形 | 建议 |
|---|---|
| 类型集合小、由一个团队维护 | 编译期类型列表，或者直接写 `if` 链 |
| 需要按名字创建，类型集合在构建时确定，但希望新增类型不改中心文件 | 自注册，注册表放在函数局部静态变量里；构建时直接链接目标文件，或对静态库用整库链接选项 |
| 插件在运行时加载 | 显式的注册入口（插件导出一个 `register_plugin(Registry&)` 函数，由加载器调用），注册表加锁 |
| 需要复制一个只知道基类的对象 | 非虚 `clone` 包装私有的虚 `clone_impl`；C++26 可考虑 `std::polymorphic` |
| 需要一族配套的对象 | 抽象工厂；主题在编译期确定时用模板参数 |
| 只是想隐藏构造细节 | 一个普通的工厂函数就够了，不需要注册表 |

插件一行推荐显式入口而不是自注册：`dlopen` 之后用 `dlsym` 找到入口函数调用它，注册时机和线程都由加载器决定，不依赖全局变量的初始化，也能在出错时报告是哪个插件的问题。

## 思考题

!!! question "1"
    `circle.cpp` 的 `registered` 从未被读取，`Circle` 也没有被任何其他翻译单元引用。直接链接 `circle.o` 并加上 `-Wl,-dead_strip` 时，为什么注册仍然生效？而把 `circle.o` 放进静态库就失效了，这两种情况有什么区别？

<details markdown="1">
<summary>答案</summary>

`-dead_strip` 从根出发标记可达的代码和数据，各翻译单元的初始化函数登记在 `__mod_init_func` 段中，属于根；初始化函数调用 `add`，引用了创建函数，所以它们都被保留。这和 [[basic.stc.static#2]] 一致：有副作用的初始化不能删掉。

静态库的问题发生在更早的阶段：链接器根本没有把 `circle.o` 当作程序的一部分。[[lex.phases#1]] 的阶段 8 只说库组件被链接进来以满足对外部实体的引用，没有被引用的库成员不属于程序，[[basic.stc.static#2]] 这类规则也就无从适用。前者是对程序的优化，受语言规则约束；后者决定的是程序由什么组成，标准不管。
</details>

!!! question "2"
    `AutoRegister<D>` 的 `registered` 是 `static inline const bool`。如果把它改成非模板的普通类的 `static inline` 成员，还需要 `anchor` 吗？

<details markdown="1">
<summary>答案</summary>

不需要。[[temp.inst#4]] 的规则只针对模板化实体的成员：类模板特化被实例化时，静态数据成员的定义不随之实例化。普通类的 inline 静态数据成员在类定义里就是一个定义，每个包含它的翻译单元都有这个定义，它的动态初始化像其他 inline 变量一样，是部分有序的（[[basic.start.dynamic#1]]），在主流实现上于 `main` 之前运行。

代价是失去了自动化：每个类都要自己写一次注册语句。`anchor` 的那一行，本质上是为模板版本补上普通类本来就有的那个定义。
</details>

!!! question "3"
    一个自注册的形状模块定义了一个静态对象 `Unregistrar`，它的析构函数调用 `shape_registry().remove("circle")`。这在程序退出时安全吗？

<details markdown="1">
<summary>答案</summary>

如果 `Unregistrar` 在构造过程中调用过 `shape_registry()`（比如它的构造函数负责注册），那么是安全的。注册表的构造在 `Unregistrar` 的构造完成之前就已经完成，[[basic.start.term#4]] 规定，构造先完成的对象后销毁，所以 `Unregistrar` 析构时注册表还在。

如果 `Unregistrar` 的构造函数没有调用 `shape_registry()`，而注册表是之后才由别人第一次调用而构造的，那么注册表的构造后完成、先销毁，`Unregistrar` 的析构函数访问的是已经销毁的对象，这是 UB。安全与否取决于构造时有没有先碰一下注册表，这正是让注册表永不销毁的写法流行的原因。
</details>

## 小结

| 问题 | 结论 | 出处 |
|---|---|---|
| `unique_ptr<Derived>` 能否作协变返回类型 | 不能，协变只适用于类的指针和引用 | [[class.virtual#8]] |
| 协变覆盖函数的结果 | 转换成静态选中的函数的返回类型 | [[class.virtual#9]] |
| 自注册变量没人读，会被删掉吗 | 不会，有副作用的初始化不能删 | [[basic.stc.static#2]] |
| 全局变量一定在 `main` 之前初始化吗 | 由实现定义，可以推迟 | [[basic.start.dynamic#5]] |
| 跨翻译单元的初始化顺序 | 没有规定 | [[basic.start.dynamic#3]] |
| 函数局部静态变量何时初始化、是否线程安全 | 第一次经过声明时；并发进入的线程等待 | [[stmt.dcl#3]] |
| 头文件里的 `const` 变量 | 内部链接，每个翻译单元一份 | [[basic.link#3.2]] |
| inline 变量 | 多处定义，同一个实体 | [[dcl.inline#2]] |
| 类模板的静态数据成员何时初始化 | 只有被需要定义的方式使用时才实例化和初始化 | [[temp.inst#4]] |
| 静态库成员是否链接 | 标准不规定；链接器只提取被引用的成员 | [[lex.phases#1]] |
