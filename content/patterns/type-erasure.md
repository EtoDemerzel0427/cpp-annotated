---
title: 类型擦除
summary: 不要求共同基类、又保持值语义的运行期多态：从虚函数内部接口一步步手写一个 Drawable，加上复制、移动、小缓冲区优化和手写虚表，讲清 placement new、launder、生命周期与 noexcept 移动的规则，再看标准库里各种类型擦除类型擦掉了什么、各自要付出什么代价。
status: draft
order: 60
since: c++11
papers: P0288R9, P2548R6, P0792R14, P3019R14
related: func.wrap, func.wrap.func, func.wrap.move, func.wrap.copy, func.wrap.ref, any, polymorphic, mem.res.class, util.smartptr.shared.const, basic.life, ptr.launder, intro.object, basic.align, patterns/strategy, patterns/visitor, topics/ownership-and-smart-pointers, topics/allocators-and-pmr, toolchain/object-layout-and-vtables
tags: 类型擦除, 多态, 值语义, 小对象优化, std::function, std::any, 设计模式
updated: 2026-10-19
---

!!! tldr
    - 类型擦除让互不相关的类型只要有相同的操作（比如都有 `draw()`），就能装进同一个类型里，按值复制、移动、放进容器，用户的类型不需要继承任何基类。
    - 经典实现是一个私有的虚函数接口（concept）加一个类模板实现（model），外层类用指针持有 model；复制靠虚函数 `clone()`，构造函数模板必须排除外层类自身。
    - 小缓冲区优化把小对象直接构造在外层对象内部，省掉堆分配；它要求对齐正确、生命周期手工管理，并且只能用于移动构造不抛异常的类型，否则外层的 `noexcept` 移动无法成立。
    - 用函数指针结构体代替虚函数，可以把对象完整地放进缓冲区，每次调用少一次间接访问；代价是要用 `std::launder` 从缓冲区地址取回对象。
    - 标准库里的 `function`、`move_only_function`、`copyable_function`、`function_ref`、`any`、`shared_ptr` 的删除器、`pmr::memory_resource` 和 C++26 的 `polymorphic` 都是类型擦除，区别在于擦掉了什么、是否拥有对象、是否可复制、调用空对象时会怎样。

## 问题：没有共同基类的多态

一个绘图程序要把各种图元放进同一个容器，逐个调用 `draw()`。图元来自不同的库：`Circle` 是自己写的，`Text` 来自一个不能修改的第三方库。它们都有 `void draw() const`，但没有共同的基类。

<div class="compare" markdown="1">

```cpp
// 继承：每个类型都要派生自 Shape
struct Shape {
  virtual ~Shape() = default;
  virtual void draw() const = 0;
};
struct Circle : Shape {
  double r;
  void draw() const override;
};
// Text 改不了，只能再包一层
std::vector<std::unique_ptr<Shape>> v;
// v 不能复制，元素可以为空
```

```cpp
// 类型擦除：只要求有 draw()
struct Circle {
  double r;
  void draw() const;
};
struct Text {              // 第三方类型
  std::string s;
  void draw() const;
};
std::vector<Drawable> v{Circle{1},
                        Text{"hi"}};
auto w = v;                // 深复制
```

</div>

左边是经典的虚函数多态，它有三个限制。第一，类型必须事先继承 `Shape`，这叫**侵入式**（intrusive）设计，不能修改的类型只能再写适配类。第二，对象只能通过指针或引用使用，容器里装的是 `unique_ptr`，失去了值语义：不能直接复制，元素可能为空。第三，`Shape` 的接口固定在基类里，同一个类型想参与另一种接口就要再继承一次。

模板（或 concepts）是另一条路，`template <class T> void render(const T&)` 不要求继承，但每个类型生成一份代码，`vector` 也只能装一种类型。

**类型擦除**（[[g:type-erasure]]）取两者之长：`Drawable` 是一个普通的值类型，可以从任何有 `draw()` 的对象构造，构造时记住具体类型该如何调用、复制、销毁，之后具体类型就从静态类型里消失了。调用通过运行期分派完成，这一点和虚函数一样；但用户的类型不必继承任何东西，`Drawable` 本身也可以复制、移动、放进容器。

## 第一步：concept 与 model

```cpp run title="step1.cpp" ok
#include <cstdio>
#include <memory>
#include <string>
#include <utility>
#include <vector>

// 两个互不相关的类型，没有共同基类
struct Circle { double r; void draw() const { std::printf("circle %g\n", r); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };

class Drawable {
  struct Concept {                         // 内部接口
    virtual ~Concept() = default;
    virtual void draw() const = 0;
  };
  template <class T>
  struct Model final : Concept {           // 每个具体类型一个实现
    T obj;
    explicit Model(T x) : obj(std::move(x)) {}
    void draw() const override { obj.draw(); }
  };
  std::unique_ptr<Concept> self;

public:
  template <class T>
  Drawable(T x) : self(std::make_unique<Model<T>>(std::move(x))) {}
  void draw() const { self->draw(); }
};

int main() {
  std::vector<Drawable> v;
  v.emplace_back(Circle{1.5});
  v.emplace_back(Text{"hi"});
  for (const Drawable& d : v) d.draw();
}
```

结构分三层：

1. `Concept` 是一个只在 `Drawable` 内部可见的抽象基类，列出被擦除的类型需要支持的操作。习惯上叫它 concept，与 C++20 的 `concept` 关键字无关。
2. `Model<T>` 是类模板，派生自 `Concept`，持有一个 `T`，把每个虚函数转发给 `T` 的同名操作。每用一个新类型构造 `Drawable`，编译器就实例化一个新的 `Model<T>`，连同它的虚表。
3. `Drawable` 持有一个 `unique_ptr<Concept>`，对外提供非虚的 `draw()`，内部转发给 `self->draw()`。

继承仍然存在，只是从用户的类型挪到了库的内部：继承 `Concept` 的是 `Model<Circle>`，而不是 `Circle`。`Circle` 对 `Drawable` 一无所知，`Drawable` 对 `Circle` 的要求也只是表达式 `obj.draw()` 能编译。

这一版还缺两样东西：它不能复制（成员是 `unique_ptr`），构造函数模板也没有约束，任何类型都能尝试构造，错误要到实例化 `Model<T>::draw` 时才出现。

## 第二步：复制与移动

```cpp run title="step2.cpp" ok
#include <concepts>
#include <cstdio>
#include <memory>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

struct Circle { double r; void draw() const { std::printf("circle %g\n", r); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };

template <class T>
concept CanDraw = requires(const T& t) { t.draw(); };

class Drawable {
  struct Concept {
    virtual ~Concept() = default;
    virtual void draw() const = 0;
    virtual std::unique_ptr<Concept> clone() const = 0;
  };
  template <class T>
  struct Model final : Concept {
    T obj;
    template <class U>
    explicit Model(U&& u) : obj(std::forward<U>(u)) {}
    void draw() const override { obj.draw(); }
    std::unique_ptr<Concept> clone() const override {
      return std::make_unique<Model>(obj);
    }
  };
  std::unique_ptr<Concept> self;

public:
  template <class T>
    requires (!std::same_as<std::remove_cvref_t<T>, Drawable>)
             && CanDraw<std::remove_cvref_t<T>>
  Drawable(T&& x)
      : self(std::make_unique<Model<std::remove_cvref_t<T>>>(std::forward<T>(x))) {}

  Drawable(const Drawable& o) : self(o.self->clone()) {}
  Drawable(Drawable&&) noexcept = default;
  Drawable& operator=(const Drawable& o) { return *this = Drawable(o); }
  Drawable& operator=(Drawable&&) noexcept = default;

  void draw() const { self->draw(); }
};

int main() {
  std::vector<Drawable> v{Circle{1.5}, Text{"hi"}};
  std::vector<Drawable> w = v;         // 深复制：每个元素 clone 一次
  w[0] = Text{"replaced"};
  for (const Drawable& d : v) d.draw();
  for (const Drawable& d : w) d.draw();
}
```

本机输出 `circle 1.5`、`text hi`、`text replaced`、`text hi`：修改 `w` 不影响 `v`，这就是值语义。

先看复制。`Drawable` 的复制构造函数不知道 `self` 指向的具体类型，只有 `Model<T>` 知道，所以复制也要经过虚函数：`clone()` 在 `Model<T>` 里用 `T` 的复制构造函数造一个新的 `Model`。这和手写多态类层次时的虚 `clone()` 是同一个技巧，区别是它只写一次，所有 `T` 都由模板生成。

复制赋值先构造一个副本，再移动赋值过来。副本构造失败时 `*this` 不变，这是强异常保证，详见 [[topics/exception-safety]]。

移动直接沿用 `unique_ptr` 的移动：只交换指针，不碰被擦除的对象，因此可以是 `noexcept`。被移动后的 `Drawable` 的 `self` 为空，它只能被销毁或重新赋值，对它调用 `draw()` 会解引用空指针。这和标准库的约定一致：被移动的对象处于有效但未指明的状态（[[g:valid-but-unspecified-state]]），调用有前提条件的操作之前要先赋值。

构造函数模板有两个约束：`CanDraw` 让不能 `draw()` 的类型在重载决议阶段就被排除，错误信息指向调用处；`!same_as<..., Drawable>` 则防止它和复制构造函数竞争。第二条看起来多余，后文的陷阱一节会展示去掉它的后果。

`Model` 里存的是 `remove_cvref_t<T>`：从左值 `Circle&` 构造时也要复制一个 `Circle` 进去，而不是存一个引用。值语义的类型擦除总是拥有自己的对象。

## 第三步：小缓冲区优化

上面的 `Drawable` 每构造一次都要 `new` 一个 `Model`，哪怕被擦除的对象只有 8 字节。**小对象优化**（small-object optimization，SBO，[[g:small-object-optimization]]）在外层对象里预留一块缓冲区，放得下的对象直接构造在里面，放不下的才去堆上。

```cpp run title="sbo.cpp" ok
#include <concepts>
#include <cstddef>
#include <cstdio>
#include <new>
#include <string>
#include <type_traits>
#include <utility>

template <class T>
concept CanDraw = requires(const T& t) { t.draw(); };

class Drawable {
  static constexpr std::size_t Size = 3 * sizeof(void*);
  static constexpr std::size_t Align = alignof(void*);

  struct Concept {
    virtual void draw() const = 0;
    virtual Concept* copy_to(void* buf) const = 0;      // 返回新对象的地址
    virtual Concept* move_to(void* buf) noexcept = 0;   // 同上；*this 随后失效
    virtual void destroy() noexcept = 0;                // 析构，必要时释放
  protected:
    ~Concept() = default;                               // 只通过 destroy() 销毁
  };

  template <class T, bool Inline>
  struct Model final : Concept {
    T obj;
    template <class... A> explicit Model(A&&... a) : obj(std::forward<A>(a)...) {}
    void draw() const override { obj.draw(); }
    Concept* copy_to(void* buf) const override {
      if constexpr (Inline) return ::new (buf) Model(obj);
      else return new Model(obj);
    }
    Concept* move_to(void* buf) noexcept override {
      if constexpr (Inline) {
        Concept* p = ::new (buf) Model(std::move(obj));
        this->~Model();                                 // 旧缓冲区里的对象到此结束
        return p;
      } else {
        return this;                                    // 堆上的对象：只交出指针
      }
    }
    void destroy() noexcept override {
      if constexpr (Inline) this->~Model();
      else delete this;
    }
  };

  template <class T>
  static constexpr bool fits = sizeof(Model<T, true>) <= Size
                            && alignof(Model<T, true>) <= Align
                            && std::is_nothrow_move_constructible_v<T>;

  alignas(Align) std::byte buf[Size];
  Concept* self;                                        // 指向 buf 内或堆上

public:
  template <class T, class D = std::remove_cvref_t<T>>
    requires (!std::same_as<D, Drawable>) && CanDraw<D>
  Drawable(T&& x) {
    if constexpr (fits<D>) self = ::new (buf) Model<D, true>(std::forward<T>(x));
    else                   self = new Model<D, false>(std::forward<T>(x));
  }
  Drawable(const Drawable& o) : self(o.self->copy_to(buf)) {}
  Drawable(Drawable&& o) noexcept : self(o.self->move_to(buf)) { o.self = nullptr; }
  Drawable& operator=(Drawable o) noexcept {            // 复制并交换的变体
    if (self) self->destroy();
    self = o.self->move_to(buf);
    o.self = nullptr;
    return *this;
  }
  ~Drawable() { if (self) self->destroy(); }

  void draw() const { self->draw(); }
};

struct Circle { double r; void draw() const { std::printf("circle %g\n", r); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };

int main() {
  Drawable a = Circle{1.5};                     // 放进 buf
  Drawable b = Text{"a string that is long enough to allocate"};  // 堆上
  Drawable c = a, d = std::move(b);
  a = d;
  Drawable e = std::move(c);                   // buf 内的对象：逐个移动
  a.draw(); d.draw(); e.draw();
  std::printf("sizeof(Drawable)=%zu\n", sizeof(Drawable));
}
```

本机 ASan 和 UBSan 都没有报告，`sizeof(Drawable)` 是 32：24 字节缓冲区加一个指针。`Model` 多了一个模板参数 `Inline`，同一个 `T` 只会用到其中一种。`Concept` 不再有虚析构函数，销毁统一走 `destroy()`：缓冲区里的对象只调用析构函数，堆上的对象还要释放内存。

下面逐条看这段代码依赖的规则。

### 在字节数组里创建对象

`buf` 是 `std::byte` 数组。在 `unsigned char` 或 `std::byte` 数组的存储里用 `new` 创建一个完整对象时，只要新对象完全落在数组内，就说这个数组为它**提供存储**（[[g:provides-storage]]，[[intro.object#3]]）。数组本身的生命周期不受影响，`Drawable` 仍然是一个完整的、正常的对象。

`::new (buf) Model(...)` 是 **placement new 表达式**（[[g:placement-new-expression]]）：额外的实参 `buf` 传给不分配内存的 `operator new(size_t, void*)`，它原样返回这个地址，什么也不做（[[new.delete.placement#2]]）。随后对象在这块存储上初始化，初始化完成时它的生命周期开始（[[basic.life#2]]）。写成 `::new` 会跳过类专属的 `operator new`；`Model` 是自己的类型，这里只是习惯，到第四步直接构造用户类型 `T` 时才真正有意义。

### 对齐

[[basic.life#2.1]] 要求存储的大小和对齐都适合 `T`，在对齐不满足的存储上创建对象是 UB（[[basic.align#1]]）。`std::byte` 数组本身的对齐是 1，所以必须写 `alignas(Align)`，并且 `fits` 要检查 `alignof(Model<T, true>) <= Align`。只检查大小，`alignas(16)` 的类型就会被构造到 8 字节对齐的地址上。

### 生命周期由谁结束

放进 `buf` 的对象不会被 `Drawable` 的隐式析构函数销毁，编译器只知道这里有一个 `std::byte` 数组。在存储被重用或释放之前不调用析构函数，标准允许，但那个对象的析构函数就再也不会运行（[[basic.life#6]]），`std::string` 这样的成员会泄漏。所以 `~Drawable` 必须显式调用 `destroy()`，`move_to` 把对象搬走之后也要立即析构原来的那个。

`move_to` 在 `this->~Model()` 之后直接返回，不再访问任何成员。生命周期结束之后通过原来的指针访问成员或调用成员函数是 UB（[[basic.life#7.2]]），而返回一个早已算好的 `p` 不属于这种访问。

### 为什么保存 `self`，而不是每次从 `buf` 算出来

`self` 是 placement new 表达式的结果，它直接指向新创建的 `Model`，再转换为基类指针。如果改为每次用 `reinterpret_cast<Concept*>(buf)` 取对象，得到的指针并不指向 `Model`：

- `reinterpret_cast` 在对象指针之间的转换等价于先转成 `void*` 再 `static_cast`（[[expr.reinterpret.cast#7]]）。从 `void*` 转换时，只有当原来指向的对象与某个目标类型的对象**指针可互转**（[[g:pointer-interconvertible]]）时，结果才指向那个对象，否则指针值不变（[[expr.static.cast#12]]）。
- 数组元素 `buf[0]` 和放在那里的 `Model` 不是指针可互转的（[[basic.compound#7]]），所以转换后的指针仍然指向一个 `std::byte`，通过它调用 `draw()` 是 UB。
- `std::launder` 正是为此准备的：只要地址 A 上有一个生命周期内的、类型相似的对象，`std::launder(p)` 就返回指向它的指针（[[ptr.launder#2]]）。但 `Concept` 是 `Model` 的基类子对象，它是否位于 `buf` 的起始地址由实现决定，`std::launder(reinterpret_cast<Concept*>(buf))` 不一定满足前提条件。

保存 placement new 返回的指针，这些问题都不出现，代价是每个 `Drawable` 多 8 字节。下文的手写虚表版本走另一条路：只保存虚表指针，用 `launder` 从缓冲区取回对象。

### 为什么只放移动不抛异常的类型

`fits` 的第三个条件是 `is_nothrow_move_constructible_v<T>`。`Drawable` 的移动构造函数是 `noexcept` 的；对象在堆上时它只交出指针，对象在缓冲区里时它必须调用 `T` 的移动构造函数。如果 `T` 的移动可能抛出异常，异常会离开一个 `noexcept` 函数，程序调用 `std::terminate`（[[except.terminate#1.3]]）。

反过来，如果为了容纳这类 `T` 而去掉 `Drawable` 移动构造函数上的 `noexcept`，`std::vector<Drawable>` 扩容时就会改为逐个复制元素，每个元素一次 `clone()`。两种结果都不能接受，所以抛异常的类型只能放到堆上：堆上的对象移动时只交出指针，永远不会抛出。标准库对 `any`、`move_only_function`、`copyable_function` 的小对象优化提出的是同一个限制（[[any.class.general#3]]、[[func.wrap.move.class#2]]）。

### 外层类不能逐字节复制

`self` 指向 `Drawable` 自己的 `buf`。隐式的复制构造函数会把 `self` 原样复制过去，新对象的 `self` 指向旧对象的缓冲区，旧对象一销毁就成了悬垂指针。所以复制、移动和赋值都必须手写，让新对象把 `Model` 重新构造在自己的 `buf` 里。

### 本机测量

把第二步的版本和 SBO 版本放进同一个程序，替换全局 `operator new` 计数，`-O2` 下各构造 100 万个包着 `Circle{double}` 的 `Drawable`（`vector` 已预留空间），逐个调用 `draw()`，再复制整个 `vector`：

```text
heap  sizeof=8   build: allocs=1000000 12–14ms  copy: allocs=1000001
sbo   sizeof=32  build: allocs=0       1–5ms    copy: allocs=1
```

SBO 版本构造时一次分配也没有，复制 `vector` 也只有给新数组的那一次。代价是每个 `Drawable` 从 8 字节变成 32 字节，以及放不下的类型仍然要分配。时间是三次运行的范围，只说明量级。

`Text`（libc++ 的 `std::string` 24 字节）加上 `Model` 的虚表指针是 32 字节，放不进 24 字节的缓冲区。虚表指针占用了缓冲区，下一步正是要把它挪出去。

## 第四步：手写虚表

虚函数版本里，每个 `Model<T>` 对象内部都带一个虚表指针。可以把虚表拿到对象外面：为每个 `T` 生成一个函数指针结构体，`Drawable` 只保存指向它的指针，缓冲区全部留给 `T` 本身。

```cpp run title="vtable.cpp" ok
#include <concepts>
#include <cstddef>
#include <cstdio>
#include <new>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

template <class T>
concept CanDraw = requires(const T& t) { t.draw(); };

class Drawable {
  static constexpr std::size_t Size = 3 * sizeof(void*);
  static constexpr std::size_t Align = alignof(void*);

  struct VTable {                                   // 手写的虚表
    void (*draw)(const void* buf);
    void (*copy)(void* dst, const void* src);
    void (*move)(void* dst, void* src) noexcept;    // 之后 src 只需销毁
    void (*destroy)(void* buf) noexcept;
  };

  template <class T>
  static constexpr bool fits = sizeof(T) <= Size && alignof(T) <= Align
                            && std::is_nothrow_move_constructible_v<T>;

  // buf 里要么直接是 T，要么是一个 T*
  template <class T> static T* get(void* b) {
    if constexpr (fits<T>) return std::launder(static_cast<T*>(b));
    else return *std::launder(static_cast<T**>(b));
  }
  template <class T> static const T* get(const void* b) {
    return get<T>(const_cast<void*>(b));
  }

  template <class T>
  static constexpr VTable vtable_for = {
    [](const void* b) { get<T>(b)->draw(); },
    [](void* dst, const void* src) {
      if constexpr (fits<T>) ::new (dst) T(*get<T>(src));
      else ::new (dst) T*(new T(*get<T>(src)));
    },
    [](void* dst, void* src) noexcept {
      if constexpr (fits<T>) ::new (dst) T(std::move(*get<T>(src)));
      else ::new (dst) T*(std::exchange(*std::launder(static_cast<T**>(src)), nullptr));
    },
    [](void* b) noexcept {
      if constexpr (fits<T>) get<T>(b)->~T();
      else delete get<T>(b);
    },
  };

  alignas(Align) std::byte buf[Size];
  const VTable* vt;

public:
  template <class T, class D = std::remove_cvref_t<T>>
    requires (!std::same_as<D, Drawable>) && CanDraw<D>
  Drawable(T&& x) : vt(&vtable_for<D>) {
    if constexpr (fits<D>) ::new (buf) D(std::forward<T>(x));
    else ::new (buf) D*(new D(std::forward<T>(x)));
  }
  Drawable(const Drawable& o) : vt(o.vt) { vt->copy(buf, o.buf); }
  Drawable(Drawable&& o) noexcept : vt(o.vt) { vt->move(buf, o.buf); }
  Drawable& operator=(Drawable o) noexcept {
    vt->destroy(buf);
    vt = o.vt;
    vt->move(buf, o.buf);
    return *this;
  }
  ~Drawable() { vt->destroy(buf); }

  void draw() const { vt->draw(buf); }
};

struct Circle { double r[3]; void draw() const { std::printf("circle %g\n", r[0]); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };
struct Poly   { std::vector<double> xs; std::string name;
                void draw() const { std::printf("poly %s\n", name.c_str()); } };

int main() {
  Drawable a = Circle{{1.5}};   // 24 字节：放进 buf
  Drawable b = Text{"label"};   // libc++ 的 string 24 字节：也放进 buf
  Drawable p = Poly{{1, 2}, "a name long enough to allocate"};  // 48 字节：堆上
  Drawable c = a, d = std::move(b), e = p, f = std::move(p);
  a = d;
  a.draw(); c.draw(); e.draw(); f.draw();
  std::printf("sizeof(Drawable)=%zu\n", sizeof(Drawable));
}
```

`sizeof(Drawable)` 仍是 32，但现在 24 字节的 `Circle` 和 `Text` 都放得进缓冲区。`vtable_for<T>` 是一个 `constexpr` 变量模板，每个 `T` 一份，放在只读数据段里，所有包着同一种类型的 `Drawable` 共享它，这和编译器生成的虚表完全一样。无捕获的 lambda 可以隐式转换为函数指针，正好用来填表。

这个版本在两处不同于虚函数版本。

第一，取回对象需要 `launder`。对象只在 `buf` 里，没有单独保存的指针。`static_cast<T*>(b)` 的结果仍然指向 `buf` 的第一个字节（[[expr.static.cast#12]]），`std::launder` 才把它变成指向那里的 `T` 的指针（[[ptr.launder#3]]）。这次前提条件是满足的：`T` 是完整对象，就从 `buf` 的起始地址开始。放不下的类型在 `buf` 里存的是一个 `T*` 对象，取它的时候同样要 `launder`。

第二，被移动后的对象仍然有类型。`vt` 在移动之后保持不变，被移动的 `Drawable` 里还有一个被移动过的 `T`（或一个空的 `T*`），析构函数照常调用 `destroy`，不需要空状态检查。

### 每次调用的代价

本机 Clang 23 `-O2`（arm64）下，对 `void call_draw(const Drawable& d) { d.draw(); }` 三个版本生成的代码：

```text
// 第二步（堆上的 Model）        // SBO + 虚函数              // 手写虚表
ldr x0, [x0]       // self       ldr x0, [x0, #24]  // self    ldr x8, [x0, #24]  // vt
ldr x8, [x0]       // vptr       ldr x8, [x0]       // vptr    ldr x1, [x8]       // draw
ldr x1, [x8, #16]  // draw       ldr x1, [x8]       // draw    br  x1
br  x1                           br  x1
```

前两个版本都是三次相互依赖的读取：读 `self`，读对象里的虚表指针，读虚表里的函数指针。SBO 版本的第二次读取落在 `Drawable` 自己的缓冲区里，缓存局部性更好，但依赖链没有变短。手写虚表少一次读取，因为虚表指针直接存在 `Drawable` 里。第二步版本的 `draw` 在虚表偏移 16 处，是因为 Itanium C++ ABI 为虚析构函数占了两个槽位，见 [[toolchain/object-layout-and-vtables]]。

更进一步，可以把最常调用的函数指针直接存进 `Drawable`，调用时只读一次；每多存一个，对象就大 8 字节。`function_ref` 采用的就是这种布局：一个调用函数指针加一个指向对象的指针（[[func.wrap.ref.class#1]]）。

三个版本的共同代价是间接调用本身：编译器在调用处看不到目标函数，不能内联，除非优化器能证明 `vt` 或动态类型只有一种可能。每擦除一个新类型，还要实例化一套 `Model<T>` 或 `vtable_for<T>`，增加目标代码体积和编译时间。

## 标准库里的类型擦除

| 类型 | 擦除了什么 | 拥有对象 | 可复制 | 空状态 | 本机 libc++ `sizeof` |
|---|---|---|---|---|---|
| `function<R(A...)>` | 可调用对象的类型 | 是 | 是，要求目标可复制 | 有；调用抛 `bad_function_call` | 32 |
| `move_only_function<R(A...)>` {{c++23}} | 同上 | 是 | 否，只能移动 | 有；调用违反前置条件 | 未实现 |
| `copyable_function<R(A...)>` {{c++26}} | 同上 | 是 | 是 | 有；调用违反前置条件 | 未实现 |
| `function_ref<R(A...)>` {{c++26}} | 同上 | 否，只引用 | 平凡可复制 | 无 | 未实现 |
| `any` | 任意可复制类型 | 是 | 是 | 有；`any_cast` 抛 `bad_any_cast` | 32 |
| `shared_ptr<T>` | 删除器、分配器、实际指针类型 | 共享 | 是（共享所有权） | 有 | 16 |
| `pmr::polymorphic_allocator<T>` | 内存资源的类型 | 否 | 是 | 无 | 8 |
| `polymorphic<T>` {{c++26}} | `T` 的派生类类型 | 是 | 是，按动态类型复制 | 仅在被移动后 | 未实现 |

本机 libc++ 尚未实现 `move_only_function`、`copyable_function`、`function_ref` 和 `polymorphic`，对应的格子不给数值，下文涉及它们的代码也不加判定。

### 函数包装器

`std::function` 就是本页的 `Drawable`，只是被擦除的操作从 `draw()` 换成了 `operator()(A...)`。四个函数包装器的完整对照见 [[func.wrap]]，这里只看和类型擦除实现有关的几点。

- `function` 要求目标可复制，因为它自己可复制，复制要经过类似 `clone()` 的虚函数。只能移动的 lambda（比如捕获了 `unique_ptr`）装不进去，这就是 `move_only_function`（[[P0288R9]]）存在的理由。
- `function::operator()` 是 `const` 成员，却会以非 `const` 方式调用目标，`copyable_function`（[[P2548R6]]）让签名里的 `const` 真正约束调用方式。
- `function_ref`（[[P0792R14]]）不拥有对象，只保存一个指向对象的指针和一个调用函数指针，从不分配，适合作函数形参。

标准对 `function` 的小对象优化只给出推荐做法：保存一个对象指针加一个成员函数指针这样的小目标时，应当避免动态分配（[[func.wrap.func.con#15]]）。对 `move_only_function` 和 `copyable_function`，标准还在注释中指出小对象优化只能用于移动构造不抛异常的类型（[[func.wrap.move.class#2]]）。

### `any`

`any` 擦除的操作最少：复制、移动、销毁，以及通过 `type()` 和 `any_cast` 查询类型。它没有调用接口，取出值时必须写出确切的类型，所以它更像一个类型安全的 `void*`，而不是多态的替代品。它对存入类型的要求是可复制构造（[[any.cons#6]]），移动构造是 `noexcept` 的（[[any.cons#4]]），因此小对象优化同样只能用于移动不抛异常的类型（[[any.class.general#3]]）。实现细节见 [[any]]。

### 小缓冲区的门槛

```cpp run title="std-sbo.cpp" impl
#include <any>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

template <std::size_t N> struct Bytes { char c[N]; void operator()() const {} };
struct ThrowMove {                     // 1 字节，但复制和移动都可能抛出
  ThrowMove() = default;
  ThrowMove(const ThrowMove&) {}
  ThrowMove(ThrowMove&&) {}
  void operator()() const {}
};

template <class W, class F> int count(F f) {
  int before = allocs;
  W w(f);
  return allocs - before;
}

int main() {
  using F = std::function<void()>;
  std::printf("function: 16B=%d 24B=%d throw=%d\n",
              count<F>(Bytes<16>{}), count<F>(Bytes<24>{}), count<F>(ThrowMove{}));
  std::printf("any:      24B=%d 32B=%d throw=%d\n",
              count<std::any>(Bytes<24>{}), count<std::any>(Bytes<32>{}),
              count<std::any>(ThrowMove{}));
}
```

本机 libc++ 输出：

```text
function: 16B=0 24B=1 throw=1
any:      24B=0 32B=1 throw=1
```

两者都是 32 字节，门槛却不同：`any` 能就地存放 24 字节的对象，`function` 只能存放 16 字节。libc++ 的 `function` 在缓冲区里放的是一个带虚函数的包装对象，虚表指针占了 8 字节，和本页第三步的 `Model` 一样；`any` 把管理函数指针放在缓冲区之外，和第四步一样。1 字节的 `ThrowMove` 两者都只能放到堆上；本机 libc++ 的 `function` 检查的是复制构造不抛异常，`any` 检查的是移动构造不抛异常。这些阈值都是实现细节，libstdc++ 和 MSVC 各不相同，代码不应该依赖它们。

### `shared_ptr` 的删除器

`shared_ptr<T>` 的类型里没有删除器，构造时 `shared_ptr(p, d)` 把删除器连同 `p` 的实际类型一起存进控制块（[[util.smartptr.shared.const#11]]），销毁时通过控制块的虚函数调用。所以 `vector<shared_ptr<int>>` 能装着用不同方式释放的对象，`shared_ptr<Base>` 能在 `Base` 没有虚析构函数时正确销毁派生类对象。这一点和代价的测量见 [[topics/ownership-and-smart-pointers]]。对比 `unique_ptr<T, D>`：删除器是类型的一部分，没有擦除，也就没有间接调用。

### `pmr::memory_resource`：虚函数接口的那一种

`std::pmr::memory_resource` 是一个普通的抽象基类，具体的资源（`monotonic_buffer_resource`、`unsynchronized_pool_resource`、用户自己的资源）都要继承它（[[mem.res.class]]）。它本身是侵入式的经典多态，公开的非虚函数 `allocate` 转调私有虚函数 `do_allocate`，这是 [[patterns/nvi|非虚接口]] 的写法。

类型擦除发生在上一层：`polymorphic_allocator<T>` 只保存一个 `memory_resource*`，于是 `pmr::vector<int>` 无论用哪种资源都是同一个类型。普通的 `vector<int, MyAlloc>` 则把分配器写进了类型。本机 `pmr::vector<int>` 是 32 字节，比 `vector<int>` 多出的 8 字节就是这个指针。详见 [[topics/allocators-and-pmr]]。

这说明类型擦除和虚函数不是对立的：库的作者可以要求用户继承一个接口，再在使用处把具体类型藏到指针后面。区别只在于用户的类型是否需要知道这个接口。

### `polymorphic`：封闭层次的值语义 {{c++26}}

`std::polymorphic<T>`（[[P3019R14]]）解决的是另一半问题。它要求对象的类型派生自 `T`（[[polymorphic.ctor#12]]），所以不是非侵入式的；但它和本页的 `Drawable` 一样提供值语义：

```cpp
struct Shape {
  virtual ~Shape() = default;
  virtual void draw() const = 0;
};
struct Circle : Shape { double r = 1; void draw() const override; };

std::vector<std::polymorphic<Shape>> v;
v.emplace_back(std::in_place_type<Circle>);
auto w = v;          // 按动态类型复制每个元素，不需要虚 clone()
w[0]->draw();
```

本机 libc++ 尚未实现 `polymorphic`，这段代码没有经过编译。构造时 `polymorphic` 记住了实际类型 `Circle`，复制时调用 `Circle` 的复制构造函数（[[polymorphic.ctor#8]]），擦除的正是派生类的类型。它的移动构造函数允许移动构造一个新对象而不是接管指针（[[polymorphic.ctor#10]]），这是为小对象优化留出的余地。完整规则见 [[polymorphic]]。

已有一个类层次时，`polymorphic<Base>` 比手写类型擦除简单得多；类型来自各处、不能修改时，才需要 `Drawable` 这样的非侵入式设计。

## 陷阱

### 构造函数模板劫持复制

第二步里的 `!same_as<..., Drawable>` 约束如果去掉，问题出在 `Drawable` 本身也有 `draw()`，它满足 `CanDraw`：

```cpp run title="hijack.cpp"
#include <cstdio>
#include <memory>
#include <type_traits>
#include <utility>

struct Circle { void draw() const { std::puts("circle"); } };

class Drawable {
  struct Concept {
    virtual ~Concept() = default;
    virtual void draw() const = 0;
    virtual std::unique_ptr<Concept> clone() const = 0;
  };
  template <class T> struct Model final : Concept {
    T obj;
    template <class U> explicit Model(U&& u) : obj(std::forward<U>(u)) {}
    void draw() const override { obj.draw(); }
    std::unique_ptr<Concept> clone() const override { return std::make_unique<Model>(obj); }
  };
  std::unique_ptr<Concept> self;
public:
  template <class T>                         // 没有排除 Drawable 本身
    requires requires(const T& t) { t.draw(); }
  Drawable(T&& x)
      : self(std::make_unique<Model<std::remove_cvref_t<T>>>(std::forward<T>(x))) {}
  Drawable(const Drawable& o) : self(o.self->clone()) {}
  Drawable(Drawable&&) noexcept = default;
  void draw() const { self->draw(); }
};

int main() {
  Drawable a = Circle{};
  const Drawable& ca = a;
  Drawable b = ca;   // const 左值：选中复制构造函数
  Drawable c = a;    // 非 const 左值：选中模板，T = Drawable&
  c.draw();
}
```

`Drawable c = a;` 有两个候选：复制构造函数 `Drawable(const Drawable&)`，以及模板实例化出的 `Drawable(Drawable&)`。两者都是引用绑定，后者绑定到 cv 限定更少的类型，隐式转换序列更好（[[over.ics.rank#3.2.6]]）。只有两个候选同样好时，非模板优先的规则（[[over.match.best.general#2.4]]）才起作用，所以模板胜出。模板构造函数永远不会被当作复制构造函数（[[class.copy.ctor#1]]），但这不妨碍它在重载决议中击败复制构造函数。

模板于是构造一个 `Model<Drawable>`，它的成员 `obj` 用 `std::forward<U>(u)` 初始化，`u` 又是非 `const` 的 `Drawable&`，于是再次选中模板，再构造一个 `Model<Drawable>`……递归永不结束。本机运行时栈溢出，ASan 报告 `stack-overflow`，调用栈里是重复的 `make_unique<Drawable::Model<Drawable>, Drawable&>`。

所以转发引用构造函数模板总要排除外层类自身，标准库的 `function` 和 `any` 都有这一条约束（[[func.wrap.func.con#9]]、[[any.cons#6]]）。

### 小缓冲区里放了移动会抛出的类型

把 `sbo.cpp` 中 `fits` 的 `is_nothrow_move_constructible_v<T>` 条件删掉，再放进一个移动构造函数会抛出的类型：

```cpp
struct Flaky {
  Flaky() = default;
  Flaky(const Flaky&) = default;
  Flaky(Flaky&&) { throw 42; }      // 移动可能抛出（这里总是抛出）
  void draw() const {}
};

int main() {
  Flaky f;
  Drawable a = f;                   // 复制进 buf
  try { Drawable b = std::move(a); } catch (int) { std::puts("caught"); }
}
```

`catch` 永远不会执行。异常从 `noexcept` 的 `move_to` 里抛出，搜索处理器时离开了一个不抛出的函数，程序调用 `std::terminate`（[[except.terminate#1.3]]）。本机输出 `libc++abi: terminating due to uncaught exception of type int`。这是一个行为确定的程序，只是它的行为是终止。

### 调用空包装器

```cpp run title="empty.cpp" ok
#include <cstdio>
#include <functional>

int main() {
  std::function<void()> f;            // 空
  try {
    f();
  } catch (const std::bad_function_call& e) {
    std::puts("bad_function_call");
  }
}
```

空的 `std::function` 被调用时抛出 `bad_function_call`（[[func.wrap.func.inv#2]]），所以每次调用都隐含一次判空。`move_only_function` 和 `copyable_function` 改为把非空列为前置条件（[[func.wrap.move.inv#2]]、[[func.wrap.copy.inv#2]]），违反前置条件是 UB（[[structure.specifications#3.4]]）。这省掉了判空，也让 `noexcept` 签名可以成立，代价是空调用不再有任何保护。

自己写的 `Drawable` 也要决定这件事。第二、三步的版本被移动后 `self` 为空，调用 `draw()` 就是空指针解引用；可以在 `draw()` 里检查并抛异常，也可以像标准库后来的包装器一样把非空写成前置条件。重要的是写清楚。

### `function_ref` 悬垂

```cpp
#include <functional>

int main() {
  int base = 40;
  std::function_ref<int(int)> r = [base](int x) { return base + x; };
  return r(2);   // UB：lambda 临时对象在上一行末尾已经销毁
}
```

从可调用对象构造 `function_ref` 时，它保存的是 `addressof(f)`（[[func.wrap.ref.ctor#8]]），不复制对象。上面的 lambda 是一个临时对象，在声明 `r` 的完整表达式结束时销毁，`r` 里的指针随即悬垂。本机 libc++ 尚未实现 `function_ref`，这段代码没有经过编译，所以不加判定。

`function_ref` 和 `std::string_view` 一样是借用类型：作函数形参时安全，因为实参在整个调用期间都活着；作变量或成员时，必须保证被引用的对象活得更久。这类问题的全貌见 [[topics/dangling-references]]。

## 何时使用

| 需求 | 选择 |
|---|---|
| 类型集合封闭、事先全部已知 | `std::variant` + `std::visit`，见 [[patterns/visitor\|访问者]] |
| 自己设计的类层次，需要多态 | 虚函数；需要值语义时用 `polymorphic<Base>` |
| 编译期就知道具体类型，追求可内联 | 模板加 concepts，见 [[patterns/crtp\|CRTP]]、[[patterns/policy-based-design\|基于策略的设计]] |
| 类型开放、来自各处、不能修改，需要按值存储 | 类型擦除（标准库的或手写的） |
| 只是传一个回调，调用结束后不再使用 | `function_ref` 或模板形参，不要用 `const std::function&` |
| 保存一个回调供以后调用 | `move_only_function`（不需要复制时）、`copyable_function` 或 `function` |
| 存放任意值，取出时知道类型 | `any` |

手写类型擦除的成本不在于第一版，而在于把复制、移动、小缓冲区、异常安全都做对。被擦除的接口只有一个调用操作时，直接用标准库的函数包装器；接口有多个操作（如 `draw` 加 `bounds`）时才值得手写。策略对象用哪种形式传递的比较见 [[patterns/strategy|策略模式的几种写法]]。

## 思考题

!!! question "1"
    `sbo.cpp` 的 `Drawable` 如果不写复制构造函数，改为 `Drawable(const Drawable&) = default;`，用一个包着 `Circle` 的对象复制出另一个，会发生什么？

<details markdown="1">
<summary>答案</summary>

默认的复制构造函数逐个复制成员：`buf` 被逐字节复制（`std::byte` 数组的复制不会在新的 `buf` 里创建 `Model` 对象），`self` 被原样复制，仍然指向源对象的 `buf`。之后两个 `Drawable` 的析构函数都会对同一个 `Model` 调用 `destroy()`，第二次是在生命周期已经结束的对象上调用成员函数，UB（[[basic.life#7.2]]）。源对象先销毁时，副本的 `self` 立即悬垂。缓冲区里的对象只能通过它自己的复制构造函数在新地址上重新创建，所以带小缓冲区的类必须手写复制和移动。
</details>

!!! question "2"
    `any` 和本页 `sbo.cpp` 的 `Drawable` 都用 24 字节的缓冲区，为什么 libc++ 的 `any` 能就地存放 24 字节的对象，`sbo.cpp` 只能存放 16 字节的？

<details markdown="1">
<summary>答案</summary>

`sbo.cpp` 在缓冲区里构造的是 `Model<T, true>`，它有虚函数，对象里带一个 8 字节的虚表指针，留给 `T` 的只剩 16 字节。`any` 不在缓冲区里放带虚函数的对象，它把类型相关的操作放在对象之外的一个函数（指针）里，缓冲区全部给 `T`，这和第四步的手写虚表相同。libc++ 的 `function` 用的是前一种布局，所以本机测量中它只能就地存放 16 字节的目标。
</details>

!!! question "3"
    一个函数只在内部同步地调用传进来的回调，签名该写成 `void each(const std::function<void(int)>& f)`、`void each(std::function_ref<void(int)> f)`，还是 `template <class F> void each(F&& f)`？

<details markdown="1">
<summary>答案</summary>

`const std::function&` 最差：调用方传 lambda 时要先构造一个临时的 `function`，可能堆分配，调用时还要经过间接调用和判空。`function_ref` 不分配、平凡可复制，调用只多一次间接调用，`each` 可以放在 `.cpp` 里单独编译，适合不想把实现放进头文件的接口。模板形参没有任何间接调用，lambda 可以内联，但每种回调类型实例化一份 `each`，实现必须放在头文件里。回调不会被保存，所以不需要拥有它的 `function` 或 `move_only_function`。
</details>
