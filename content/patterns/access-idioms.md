---
title: passkey 与 attorney-client
summary: 友元一次交出全部私有成员；passkey 把一个公有函数限定给指定的调用者，attorney-client 只转发选定的私有成员，以及 `{}` 聚合初始化、make_shared、显式实例化和静态反射在访问控制上留下的缺口。
status: draft
order: 90
since: c++11
papers: P1008R1, CWG1518, P2893R3, P0692R1, P3547R1
related: class.friend, class.access, class.access.base, dcl.init.aggr, over.match.ctor, temp.spec.general, util.smartptr.shared.create, meta.reflection.access.context, topics/name-lookup-and-customization, topics/ownership-and-smart-pointers, topics/special-members-and-elision, patterns/factory-and-registration
tags: 访问控制, 友元, passkey, attorney-client, make_shared, 惯用法
updated: 2026-10-19
---

!!! tldr
    - 友元一次交出类的全部私有和受保护成员，而且友元关系既不继承，也不传递。想只放行一个函数、只放行一个调用者，要另想办法。
    - passkey 让公有函数多接收一个按值传递的空类型 `Key`，`Key` 的构造函数是私有的，只有指定的调用者是它的友元。空的 `Key` 在本机 arm64 和 x86-64 上都不占用寄存器，生成的代码与没有它时相同。
    - C++17 及以前，私有的 `Key() = default;` 不妨碍 `Key` 是聚合，任何人都能写 `{}` 绕过它。C++20 起有用户声明的构造函数就不是聚合；写 `Key() {}` 或 `explicit Key() = default;` 在各版本都安全。
    - `make_shared` 在标准库内部调用构造函数，私有构造函数因此无法使用。把构造函数改为公有、要求一个私有嵌套的 `Key` 参数，就能既用 `make_shared` 又挡住外人。
    - attorney-client 用一个中间类只转发选定的私有成员。显式实例化不检查模板实参的访问权限，C++26 的 splice 表达式也不检查，这两条后门不该出现在产品代码里。

## 友元给得太多

```cpp title="engine.cpp" ok
class Engine {
  int rpm_ = 0;
  int fuel_ = 100;
  void set_rpm(int r) { rpm_ = r; }
  void drain_fuel() { fuel_ = 0; }
  friend class Mechanic;   // 本意：只让 Mechanic 调 set_rpm
};

class Mechanic {
public:
  void tune(Engine& e) { e.set_rpm(800); }
  void oops(Engine& e) { e.drain_fuel(); }   // 同样允许
};
```

**友元**（[[g:friend|friend]]）是一个类指定的函数或类，可以指名这个类的私有和受保护成员（[[class.friend#1]]）。这里的授权是整体的：`Mechanic` 只需要 `set_rpm`，却同时得到了 `rpm_`、`fuel_` 和 `drain_fuel`。`Engine` 的不变式此后不仅靠它自己的成员函数维护，也靠 `Mechanic` 的每一行代码维护。

可以只把一个成员函数声明为友元，例如 `friend void Mechanic::tune(Engine&);`。这收窄了调用者一侧，被访问的一侧仍然是全部成员。而且这句声明是限定名，要在 `Mechanic` 里找到 `tune`，所以 `Engine` 的头文件必须先看到 `Mechanic` 的完整定义。

¶9 还规定友元关系既不继承，也不传递：

```cpp title="friend-not-inherited.cpp" error
class Engine {
  void set_rpm(int) {}
  friend class Mechanic;
};

class Mechanic {
  friend class Helper;
public:
  void tune(Engine& e) { e.set_rpm(800); }   // OK
};

class Apprentice : public Mechanic {
public:
  void tune2(Engine& e) { e.set_rpm(900); }  // error: 友元关系不继承
};

class Helper {
public:
  void poke(Engine& e) { e.set_rpm(1); }     // error: 友元关系不传递
};
```

本机 Clang 23 对两处都报 `'set_rpm' is a private member of 'Engine'`。友元是一份写给具体类的授权，不随派生扩散，也不能转授。下面两种惯用法都建立在这两条规则上：在授权的一方和使用的一方之间放一个中间类型，由它决定放行什么。

| 方案 | 谁能访问 | 能访问什么 | 改动在哪里 |
|---|---|---|---|
| `friend class X` | X 的所有成员 | 全部私有和受保护成员 | 被访问的类 |
| `friend void X::f()` | 一个成员函数 | 全部私有和受保护成员 | 被访问的类，且依赖 X 的定义 |
| passkey | 能构造 `Key` 的类 | 带 `Key` 形参的那几个公有函数 | 函数签名多一个形参 |
| attorney-client | attorney 的友元 | attorney 转发的那几个私有成员 | 多一个中间类 |

## passkey：把访问权写进参数类型

```cpp run title="passkey.cpp" ok
#include <cstdio>

template <class T>
class Key {
  friend T;                // C++11：模板形参可以做友元
  Key() {}                 // 私有，用户提供
};

class Registry;

class Database {
public:
  void reset(Key<Registry>) { std::puts("reset"); }   // 只有 Registry 能调用
  void query() const { std::puts("query"); }           // 人人可调用
};

class Registry {
public:
  void shutdown(Database& db) { db.reset({}); }  // OK：Registry 是 Key<Registry> 的友元
};

int main() {
  Database db;
  Registry r;
  r.shutdown(db);
  db.query();
}
```

`reset` 是公有的，任何人都能指名它，但调用它需要先造出一个 `Key<Registry>`。实参 `{}` 对形参做复制列表初始化，空的花括号会值初始化 `Key`，也就是调用它的默认构造函数。访问检查发生在调用处：[[class.access.general#6]] 的注说明，对构造函数的隐式引用同样受访问控制。在 `Registry` 里调用时，`Registry` 是友元，检查通过；换一个地方就不行：

```cpp title="passkey-outsider.cpp" error
template <class T> class Key { friend T; Key() {} };
class Registry;
class Database { public: void reset(Key<Registry>) {} };

void outsider(Database& db) {
  db.reset({});   // error: calling a private constructor of class 'Key<Registry>'
}
```

这样，粒度变成了逐个函数：`Database` 可以只让 `Registry` 调 `reset`，再用 `Key<Auditor>` 把另一个函数交给 `Auditor`，其余成员依旧私有。C++26 允许 `friend Ts...;`，一个 `Key<Owner, Auditor>` 就能同时放行几个类，例子见 [[class.friend]] 的包展开一节（[[P2893R3]]）。

### 代价

`Key` 是空类，按值传递。把 `reset` 标成 `noinline` 后，在 `-O2` 下对比 `reset(Key<Registry>, int)` 和不带 `Key` 的 `reset_plain(int)`：本机 arm64 和 `--target=x86_64-linux-gnu` 生成的被调函数和调用处都逐条相同，`int` 都在第二个整数寄存器里（`w1`、`%esi`），`Key` 不占寄存器，也不占栈。

代价在名字上。`Key<Registry>` 是形参类型，会进入修饰名（`_ZN8Database5resetE3KeyI8RegistryEi`），给已发布的函数加上或去掉 passkey 都会改变 ABI。

### `= default` 留下的缺口

<div class="compare" markdown="1">

```cpp title="defaulted.cpp"
class Registry;
class Token {
  friend class Registry;
  Token() = default;   // 私有、预置
};
struct Database {
  void reset(Token) {}
};
void attacker(Database& db) {
  db.reset({});
  // C++11/14/17：OK，聚合初始化
  // C++20：error，私有构造函数
}
```

```cpp title="user-provided.cpp" error
class Registry;
class Token {
  friend class Registry;
  Token() {}           // 私有、用户提供
};
struct Database {
  void reset(Token) {}
};
void attacker(Database& db) {
  db.reset({});
  // error：任何版本都调用
  // 私有构造函数
}
```

</div>

左边的 `Token` 在第一次声明时就预置了构造函数，这样的构造函数是用户声明的，但不是用户提供的。C++11 到 C++17 的聚合定义只排除用户提供的构造函数（C++17 还排除 `explicit` 构造函数），所以左边的 `Token` 是聚合。**聚合**（[[g:aggregate]]）的 `{}` 是聚合初始化，逐个初始化元素，根本不调用构造函数，私有也就无从检查。

C++20 改为排除所有用户声明的构造函数（[[dcl.init.aggr#1]] ¶1.1，[[P1008R1]]），左边的 `Token` 不再是聚合，`{}` 要调用私有的默认构造函数，于是报错。本机 Clang 23 的结果：

| `-std=` | `Token() = default;` | `Token() {}` | `explicit Token() = default;` |
|---|---|---|---|
| c++11 / c++14 / c++17 | `{}` 和 `Token{}` 都通过 | error | `{}`、`Token{}` 都 error |
| c++20 / c++2c | error | error | `{}`、`Token{}` 都 error |

需要兼容 C++17 及以前的代码时，写用户提供的 `Key() {}`。另一种写法是 `explicit Key() = default;`：显式构造函数让类在 C++17 起不是聚合，而在复制列表初始化的语境里，值初始化选中显式的默认构造函数是非良构的（[[over.match.ctor#1]] 最后一句，[[CWG1518]]）。Clang 把这条作为缺陷修正，在 `-std=c++11` 下也报 `chosen constructor is explicit in copy-initialization`。代价是友元自己也不能写 `{}`，要写 `Key{}`。标准库的 `std::in_place_t`、`std::piecewise_construct_t` 用的就是 `explicit ... () = default;`，目的是不让 `{}` 隐式转换成这些标签类型（[[utility.syn]]）。

### 防误用，不防恶意

passkey 拦住的是不小心的调用，不是蓄意的绕过。

- `Key` 可以复制。被调函数拿到 `Key` 后，可以把它保存下来，或者转交给别人。要堵住这一点，可以把复制构造函数删掉：C++17 起 `Key{}` 是纯右值，直接初始化形参，不需要复制构造函数（见思考题 1）。
- `Key` 是可平凡复制的空类，`std::bit_cast<Key<Registry>>('x')` 能编译，也能运行，完全不经过构造函数。
- 显式实例化和 C++26 的 splice 表达式都能越过访问控制，见后文。

## 私有构造函数与 make_shared

passkey 最常见的用途不是限定调用者，而是配合 `std::make_shared`。一个只允许通过工厂函数创建的类，自然会把构造函数设为私有：

```cpp title="private-ctor.cpp" error
#include <memory>
class Session {
  explicit Session(int fd) : fd_(fd) {}
  int fd_;
public:
  static std::shared_ptr<Session> open(int fd) {
    return std::make_shared<Session>(fd);   // error
  }
  int fd() const { return fd_; }
};
```

`open` 是成员，有权调用私有构造函数，但真正调用构造函数的不是 `open`。标准规定 `make_shared` 用 `::new(pv) U(l...)` 初始化对象（[[util.smartptr.shared.create#7.4]]），这个表达式出现在标准库的某个内部函数里，那里没有访问权。本机 libc++ 的诊断出现在 `construct_at.h`，提示是 `calling a private constructor of class 'Session'`，前面还有五层实例化的 note。`make_unique` 同理（[[unique.ptr.create#2]]），本机的诊断出现在 `unique_ptr.h` 里。

把 `std::make_shared` 声明为友元并不可靠：标准只规定了构造用的表达式，没有规定它出现在哪个函数里。passkey 把访问检查挪回到 `open` 里：

```cpp run title="passkey-make-shared.cpp" ok
#include <cstdio>
#include <memory>

class Session {
  struct Key { explicit Key() = default; };   // 私有嵌套类型
  int fd_;
public:
  Session(Key, int fd) : fd_(fd) {}          // 公有，但需要 Key
  static std::shared_ptr<Session> open(int fd) {
    return std::make_shared<Session>(Key{}, fd);
  }
  int fd() const { return fd_; }
};

int main() {
  auto s = Session::open(3);
  std::printf("%d %zu\n", s->fd(), sizeof(Session));   // 3 4
}
```

构造函数现在是公有的，`make_shared` 内部的 `::new` 可以调用它。`Key{}` 写在成员函数 `open` 里，嵌套类型 `Session::Key` 是私有的，只有 `Session` 的成员和友元能指名它。`Key` 只出现在形参里，`sizeof(Session)` 仍然是 4。外人的三种尝试都失败：

```cpp title="passkey-make-shared-outsider.cpp" error
#include <memory>
class Session {
  struct Key { explicit Key() = default; };
public:
  Session(Key, int) {}
};

void outsider() {
  Session a({}, 3);              // error: Key 的构造函数是 explicit 的
  Session b(Session::Key{}, 3);  // error: 'Key' is a private member of 'Session'
  auto c = std::make_shared<Session>(Session::Key{}, 3);   // error: 同上
}
```

`explicit` 在这里不能省。访问控制管的是名字（[[class.access.general#6]]），`{}` 没有写出 `Key` 这个名字，如果 `Key` 是聚合，或者构造函数不是 `explicit`，第一行就能通过：

<div class="compare" markdown="1">

```cpp title="leaky-key.cpp" ok
class Session {
  struct Key {};      // 私有，但是聚合
public:
  Session(Key, int) {}
};
Session a({}, 3);     // OK：没有指名 Key
```

```cpp title="sealed-key.cpp" error
class Session {
  struct Key {
    explicit Key() = default;
  };
public:
  Session(Key, int) {}
};
Session a({}, 3);     // error
```

</div>

另一种常见的绕法是在 `open` 里定义一个派生自 `Session` 的局部类，给它公有构造函数，再 `make_shared` 这个派生类。它要求 `Session` 不是 `final`，而且对象的动态类型变成了另一个类。passkey 没有这些附带影响。工厂函数本身的设计见 [[patterns/factory-and-registration|工厂与自注册]]，`make_shared` 的单次分配见 [[topics/ownership-and-smart-pointers]]。

## attorney-client：只转发选定的私有成员

passkey 适合限定公有函数的调用者。另一种需求是让某个类使用几个私有成员，而不改动公有接口：

```cpp run title="attorney.cpp" ok
#include <cstdio>

class Buffer {
  int data_[4] = {1, 2, 3, 4};
  int size_ = 4;
  void reserve(int) { std::puts("reserve"); }
  void unsafe_resize(int n) { size_ = n; }   // 不想交给任何外人
  friend class BufferAttorney;
public:
  int size() const { return size_; }
};

class BufferAttorney {
  // 只转发 Serializer 需要的两个私有成员
  static int* raw(Buffer& b) { return b.data_; }
  static void reserve(Buffer& b, int n) { b.reserve(n); }
  friend class Serializer;
};

class Serializer {
public:
  static void load(Buffer& b) {
    BufferAttorney::reserve(b, 4);
    BufferAttorney::raw(b)[0] = 42;
  }
};

int main() {
  Buffer b;
  Serializer::load(b);
  std::printf("%d\n", b.size());
}
```

`Buffer`（client）把 `BufferAttorney` 声明为友元，`BufferAttorney`（attorney）的成员全部是私有的静态转发函数，它又只把 `Serializer` 声明为友元。友元关系不传递，所以 `Serializer` 不是 `Buffer` 的友元，只能通过 attorney 转发的两个函数接触 `Buffer`。第三方连 attorney 也用不了：

```cpp title="attorney-limits.cpp" error
class Buffer {
  void unsafe_resize(int) {}
  void reserve(int) {}
  friend class BufferAttorney;
};
class BufferAttorney {
  static void reserve(Buffer& b, int n) { b.reserve(n); }
  friend class Serializer;
};
class Serializer {
public:
  static void load(Buffer& b) { b.unsafe_resize(0); }  // error: 'unsafe_resize' is a private member of 'Buffer'
};
void outsider(Buffer& b) { BufferAttorney::reserve(b, 1); }  // error: 'reserve' is a private member of 'BufferAttorney'
```

转发函数定义在类内，隐式内联。本机 `-O2` 下，经 attorney 写 `data_[0]` 的函数和直接写的函数都编译成同样的两条指令。转发函数调用虚函数时仍然是动态分派，attorney 只决定能不能调用，不改变调用的语义。

代价在维护上。每一对 client 与使用者都要一个 attorney，client 的私有成员改名或改签名时，attorney 要跟着改。attorney 还必须和 client 一样被使用者看到，通常和 client 放在同一个头文件里。

| | passkey | attorney-client |
|---|---|---|
| 放行的对象 | client 的公有函数 | client 的私有成员 |
| client 要改什么 | 函数签名加一个 `Key` 形参 | 加一行 `friend class Attorney;` |
| 使用者怎样调用 | `obj.f({}, ...)` | `Attorney::f(obj, ...)` |
| 改变修饰名 | 是 | 否 |
| 运行时开销（本机 `-O2`） | 无 | 无 |

## 显式实例化：一条合法的后门

访问控制还有一个出自标准本身的缺口。显式实例化和显式特化的声明里，普通的访问检查规则不适用于其中的名字，函数体、默认实参、基类子句、成员说明等少数位置除外（[[temp.spec.general#6]]）。这条规则方便为私有嵌套类型显式实例化模板或特化 trait，但它也让任何人都能取得私有成员的成员指针：

```cpp run title="rob.cpp" ok
#include <cstdio>

class Vault {
  int secret_ = 42;
};

// 标签类型：声明一个只能经 ADL 找到的友元函数
struct VaultSecret {
  friend int Vault::* get(VaultSecret);
};

// 类模板里的友元定义把模板实参带出来
template <int Vault::* M>
struct Rob {
  friend int Vault::* get(VaultSecret) { return M; }
};

// 显式实例化：模板实参里的 &Vault::secret_ 不做访问检查
template struct Rob<&Vault::secret_>;

int main() {
  Vault v;
  std::printf("%d\n", v.*get(VaultSecret{}));   // 42
}
```

同样的模板实参换成隐式实例化，比如 `Rob<&Vault::secret_> r;`，Clang 就报 `'secret_' is a private member of 'Vault'`。`get` 是一个隐藏友元，只能经实参依赖查找在关联类 `VaultSecret` 里找到（见 [[topics/name-lookup-and-customization]] 的隐藏友元一节）；`v.*p` 用的是成员指针，没有指名 `secret_`。逐步的分析和取私有成员函数的版本见 [[class.access]] 的合法的后门一节。C++20 起偏特化的模板实参也不做这种检查（[[temp.spec.partial.general#10]]，[[P0692R1]]）。

!!! pitfall "不要在产品代码里用它"
    这段代码良构，ASan 和 UBSan 下运行也没有报告，但它绕过的是类作者唯一能用来维护不变式的工具，审查代码的人从 `Vault` 的定义里看不出有人在改它的成员。同一个显式实例化定义在整个程序中只能出现一次（[[temp.spec.general#5]] ¶5.1），两个翻译单元各写一遍就违反了这一条；本机把这样的两个文件链接在一起，没有任何诊断。需要从测试里访问私有成员时，passkey 或 attorney 是可以审查的替代。

## 静态反射与访问控制 {{c++26}}

C++26 的静态反射提供了另一条路。`std::meta::members_of`、`nonstatic_data_members_of` 等查询都必须带一个**访问语境**（[[g:access-context]]）参数：`access_context::current()` 只返回调用处能访问的成员，`access_context::unchecked()` 返回全部成员（[[meta.reflection.access.context]]，[[P3547R1]]）。拿到成员的反射之后，用 splice 表达式指名它，访问检查总是通过（[[class.access.base#5]] ¶5.3）：

```cpp
#include <meta>
class Vault { int secret_ = 42; };

consteval std::meta::info secret_member() {
  return std::meta::nonstatic_data_members_of(
      ^^Vault, std::meta::access_context::unchecked())[0];
}
int peek(Vault& v) { return v.[: secret_member() :]; }
```

本机 Clang 23 还不支持静态反射（没有 `<meta>`，`-freflection` 被忽略），这段代码没有经过编译验证，因此不标判定。与显式实例化相比，这里越过访问控制必须写出 `unchecked()` 这个词，在代码里看得见。查询函数的完整规则见 [[meta.reflection.queries]]。

## 怎么选

| 需求 | 做法 |
|---|---|
| 一个类需要另一个类的大部分内部状态，两者实际上是一个组件 | 直接 `friend class`；考虑合并或改为嵌套类 |
| 公有函数只该由一两个类调用 | passkey；C++17 及以前用 `Key() {}` |
| 私有构造函数，又要用 `make_shared` 或 `make_unique` | 私有嵌套的 `struct Key { explicit Key() = default; };` 加公有构造函数 |
| 某个类只需要几个私有成员，公有接口不想动 | attorney-client |
| 多个类各自需要不同的私有成员子集 | 每个使用者一个 attorney；数量多时先检查类的职责是不是太多 |
| 想限制派生类能调用什么 | 访问控制和友元都不合适，见 [[patterns/nvi|非虚接口与模板方法]] |
| 单元测试想读私有成员 | 优先通过公有接口测；实在需要时用 attorney，不要用显式实例化后门 |

## 思考题

!!! question "1"
    `Key` 的复制构造函数被删除，默认构造函数私有、`A` 是友元。`A` 里写 `f(Key{})`，其中 `f` 按值接收 `Key`。在 C++14 和 C++17 下分别能否编译？

<details markdown="1">
<summary>答案</summary>

C++14 不能，C++17 起可以。C++14 中 `Key{}` 先创建一个临时对象，再用它复制初始化形参，即使复制被省略，复制或移动构造函数也必须可用；删除的复制构造函数同时抑制了移动构造函数的隐式声明。本机 Clang 23 在 `-std=c++14` 下报 `call to deleted constructor of 'Key'`。C++17 起，用同类型的纯右值初始化对象时，直接由纯右值的初始化器初始化目标对象（[[dcl.init.general#15]] ¶15.6.1），不涉及复制构造函数。写成 `f({})` 时两个版本都能编译，因为形参直接由空花括号初始化，本来就没有临时对象。更多内容见 [[topics/special-members-and-elision]]。
</details>

!!! question "2"
    `Session::Key` 是私有嵌套的聚合 `struct Key {};`，构造函数 `Session(Key, int)` 是公有的。外人写 `Session a({}, 3);` 能通过，那么 `std::make_shared<Session>({}, 3)` 呢？

<details markdown="1">
<summary>答案</summary>

不能编译，但原因与访问控制无关。`make_shared` 的形参是转发引用包 `Args&&...`，花括号初始化列表作为实参时，对应的形参是不推导语境（[[temp.deduct.call#1]]），包无法推导。本机 Clang 23 的 note 是 `deduced incomplete pack <(no value), int>`。所以这个漏洞只出现在直接调用构造函数的地方，经过 `make_shared` 反而被挡住了。不能依赖这一点，`Key` 仍应写成 `explicit Key() = default;`。
</details>

!!! question "3"
    attorney 为什么用静态成员函数转发，而不是让 `Buffer` 写 `friend void Serializer::load(Buffer&);`？

<details markdown="1">
<summary>答案</summary>

后一种写法只收窄了调用者，`Serializer::load` 仍然能访问 `Buffer` 的全部私有成员（[[class.friend#1]]），`unsafe_resize` 也在其中。它还要求 `Buffer` 的头文件先看到 `Serializer` 的完整定义，因为 `Serializer::load` 是限定名，要在 `Serializer` 里查找，于是 client 依赖了使用者。attorney 方向相反：client 只知道 attorney 的名字，attorney 决定转发哪些成员，使用者依赖 attorney。
</details>
