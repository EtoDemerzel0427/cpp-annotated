---
title: C++ 与 C 的差异
summary: Annex C.8：合法的 C 代码在 C++ 中失效或改变含义的 39 处——新关键字、字符字面量类型、字符串字面量 const、暂定定义、struct 作用域、const 的内部链接、void* 隐式转换、枚举的类型安全、取 *p 的地址、跳过初始化、空形参表、指派初始化的限制、类名隐藏、volatile 复制等。每条附带附录给出的改写难度与使用频率，以及 Clang 23 用 C17 与 C++2c 分别编译的实测。
status: draft
covers: *
related: diff, diff.library, diff.cpp03, lex.key, basic.def, basic.scope, basic.link, conv.ptr, expr.arith.conv, dcl.init.aggr, dcl.enum, class.name
tags: 附录, 兼容性, C, 迁移
updated: 2026-10-18
---

[diff.iso] 比较的是 C++ 与 **C**。它回答的问题是：一段合法的 C 代码，用 C++ 编译器编译，会在哪里报错，又会在哪里**不报错但含义改变**？写 C/C++ 共用的头文件、把 C 项目迁移到 C++、或者在 C++ 中 `#include` C 库的头文件，都会碰到这些差别。

这一节的条目比其他小节多两个字段：**Difficulty of converting**（改写难度）和 **How widely used**（使用频率），是附录从 C++98 一路保留下来的格式。下文每条都译出这两项。附录没有点名比较哪个版本的 C，条目里的描述对 C17/C23 基本都成立。

几个大方向：

- **类型更严格**：`void*` 不能隐式转成其他指针，枚举不能和整数随意互换，字符串字面量是 `const`。
- **作用域不同**：C++ 的 `struct` 是作用域，类名和 typedef 名在同一个名字空间里。
- **声明即定义**：C++ 没有"暂定定义"，`int i; int i;` 是重复定义。
- **一些 C 的写法在 C++ 里静默改变含义**：`sizeof('x')`、`sizeof(0, arr)`、内层 `struct x` 隐藏外层的 `x`。

实测环境：Clang 23.1.3，同一份源文件分别用 `clang -x c -std=c17` 和 `clang++ -x c++ -std=c++2c` 编译。

¶1 [diff.iso.general]：本小节按章节列出 C++ 与 C 的差异，是在前面各小节所列差异**之外**的部分。

## Clause [lex]：词法约定 {#diff.lex}

### ¶1 新关键字

**受影响小节**：[[lex.key]]

**改动**：C++ 增加了 `class`、`new`、`delete`、`this`、`template`、`namespace`、`private`、`virtual`、`operator`、`friend`、`try`、`catch`、`throw` 等关键字。

**影响**：用这些词作标识符的 C 程序不是合法的 C++ 程序。

```cpp error
int class = 1, new = 2, this = 3;   // 合法的 C，非良构的 C++
```

**改写难度**：语法变换。改一个程序容易；改一大批相关程序要花更多工夫。

**使用频率**：常见。C 代码里 `new`、`class`、`this`、`template` 作变量名或结构体成员名都很常见（Linux 内核头文件就是一例）。

### ¶2 字符字面量的类型从 `int` 改为 `char`

**受影响小节**：[[lex.ccon]]

**理由**：改进重载函数的实参匹配。`function('x')` 应当匹配 `function(char)` 而不是 `function(int)`。

**影响**：静默改变。

```cpp
int sz = sizeof('x');   // C：sizeof(int)，通常为 4；C++：1
```

**改写难度**：简单。

**使用频率**：依赖 `sizeof('x')` 的程序大概很少。

### ¶3 拼接的字符串字面量不能有冲突的编码前缀

**受影响小节**：[[lex.string]]

**改动**：`L"a" U"b"` 这样两边编码前缀不同的拼接在 C++ 中非良构（C 中由实现定义是否支持）。另见 [[diff.cpp20]] [lex] ¶2。

**改写难度**：语法变换。**使用频率**：很少。

### ¶4 字符串字面量是 `const` 的

**受影响小节**：[[lex.string]]

**改动**：普通字符串字面量的类型从"`char` 的数组"改为"`const char` 的数组"；`u8` 字面量从"`char` 的数组"改为"`const char8_t` 的数组"；`u`、`U` 字面量从"某种整数类型的数组"改为"`const char16_t` / `const char32_t` 的数组"；宽字符串字面量从"`wchar_t` 的数组"改为"`const wchar_t` 的数组"。

**理由**：避免调用一个可能会修改实参的重载函数。（C 中修改字符串字面量也是 UB，只是类型系统不拦着。）

```cpp error
char* p = "abc";   // 合法的 C；C++ 中非良构
```

**Clang 23 实测**：C++ 下 Clang 默认只给警告：`ISO C++11 does not allow conversion from string literal to 'char *' [-Wwritable-strings]`。这是一个可以降级的"错误"，加 `-pedantic-errors` 才是硬错误。

**改写难度**：语法变换。附录建议的改法是加强制转换 `(char*)"abc"`；更好的做法是把指针改成 `const char*`。

**使用频率**：有正当理由把字符串字面量当作可修改内存的程序大概很少。

## Clause [basic]：基础 {#diff.basic}

### ¶1 C++ 没有"暂定定义"

**受影响小节**：[[basic.def]]

**改动**：C 的**暂定定义**（[[g:tentative-definition]]）：文件作用域上没有初始化器、没有 `extern` 的对象声明，在同一 TU 里可以出现多次，最后合并成一个定义。C++ 中每个这样的声明都是定义。

```cpp error
int i;
int i;   // 合法的 C；C++ 中重复定义
```

这也使得在 C++ 中，**只用 C 的初始化语法**无法定义互相引用的文件局部静态对象：

```cpp error
struct X { int i; struct X* next; };

static struct X a;                // C：暂定定义；C++：定义
static struct X b = { 0, &a };
static struct X a = { 1, &b };    // C++：重复定义
```

**理由**：避免内置类型和用户定义类型使用不同的初始化规则。

**Clang 23 实测**：C17 无诊断；C++ 报 `redefinition of 'i'` 和 `redefinition of 'a'`。

**改写难度**：语义变换。在 C++ 中，互相引用的一组静态对象，其中一个的初始化必须通过函数调用完成（或者用 `extern` 声明 + 无名命名空间等手段）。

**使用频率**：很少。

### ¶2 `struct` 在 C++ 中是作用域

**受影响小节**：[[basic.scope]]

```cpp error
struct X {
  struct Y { int a; } b;
};
struct Y c;   // 合法的 C；C++ 中要写 X::Y c;
```

**理由**：类作用域对 C++ 至关重要，而 `struct` 就是类。

**Clang 23 实测**：C++ 报 `variable has incomplete type 'struct Y'`（`struct Y` 被当作一个新的、不完整的全局类型）。

**改写难度**：语义变换。

**使用频率**：C 程序极其频繁地使用 `struct`，但只有在 `struct`、枚举或枚举项的名字在外层被引用时才会察觉到差别，后者大概很少。

### ¶3 文件作用域的 `const` 名字有内部链接

**受影响小节**：[[basic.link]]（另见 [[dcl.type]]）

**改动**：文件作用域上显式声明为 `const`、但没有显式声明为 `extern` 的名字，在 C++ 中有**内部链接**；在 C 中是外部链接。

**理由**：C++ 中 `const` 对象可以在翻译期作为值使用，这一规则促使程序员为每个 `const` 对象提供显式初始化器，也允许把 `const` 对象放进被多个 TU 包含的头文件里。

```cpp
// a.c / a.cpp
const int limit = 10;
// b.c / b.cpp
extern const int limit;   // C：链接到 a 中的 limit；C++：未定义符号（a 中的 limit 是内部链接）
```

**改写难度**：语义变换。在定义处加 `extern`：`extern const int limit = 10;`。C++17 起头文件里更好的写法是 `inline constexpr int limit = 10;`。

**使用频率**：很少。

### ¶4 `main` 不能被递归调用，也不能取地址

**受影响小节**：[[basic.start.main]]

**理由**：`main` 可能需要特殊处理（例如编译器在 `main` 开头插入静态初始化代码）。

**Clang 23 实测**：C++ 默认不诊断；加 `-pedantic` 后对每一处使用给出 `referring to 'main' within an expression is a Clang extension [-Wmain]`。

**改写难度**：简单：引入一个中间函数，如 `mymain(argc, argv)`。

**使用频率**：很少。

### ¶5 C 允许"兼容类型"之间混用

**受影响小节**：[[basic.types]]

**改动**：C 在多处允许"兼容类型"（compatible types）之间混用，C++ 不允许。例如在 C 中，枚举类型与其底层整数类型是兼容的；在 C++ 中，枚举是与底层类型不同的独立类型。

**理由**：更严格的类型检查对 C++ 必不可少。

**改写难度**：语义变换。"类型安全链接"（名字修饰包含形参类型）能找出很多、但不是全部这类问题。有些情况在 C++ 中也被"布局兼容"规则允许。

**使用频率**：常见。

## Clause [expr]：表达式 {#diff.expr}

### ¶1 `void*` 转换为对象指针需要强制转换

**受影响小节**：[[conv.ptr]]

```cpp error
char a[10];
void* b = a;
void foo() {
  char* c = b;   // 合法的 C；C++ 中非良构
}
```

**理由**：C++ 比 C 更努力地在编译期保证类型安全。

**Clang 23 实测**：C++ 报 `cannot initialize a variable of type 'char *' with an lvalue of type 'void *'`。

**改写难度**：可以自动化。C++ 编译器会诊断所有违规，加强制转换即可：`char* c = (char*)b;`。最常见的场合是 `int* p = malloc(n * sizeof *p);`。

**使用频率**：常见。

### ¶2 枚举与另一种枚举或浮点类型混合运算无效

**受影响小节**：[[expr.arith.conv]]

```cpp error
enum E1 { e };
enum E2 { f };
int b = e <= 3.7;     // 合法的 C；C++ 中非良构
int k = f - e;        // 合法的 C；C++ 中非良构
int x = 1 ? e : f;    // 合法的 C；C++ 中非良构
```

**理由**：加强 C++ 的类型安全。这是 C++26 才从"弃用"升级为"非良构"的规则，见 [[diff.cpp23]] [expr] ¶1。

**Clang 23 实测**：C17 无诊断；C++2c 报 `invalid comparison of enumeration type 'E1' with floating-point type 'double'` 等三个错误。

**改写难度**：C++ 编译器会诊断。用强制转换或整数提升恢复原行为：`(int)e <= 3.7`、`+f - e`。

**使用频率**：不常见。

### ¶3 没有固定底层类型的枚举在常用算术转换中的处理不同

**受影响小节**：[[expr.arith.conv]]

**改动**：C 中，枚举值在常用算术转换中被转换为枚举的底层类型（由实现选择，可以是 `unsigned int`）；C++ 中，对没有固定底层类型的枚举施加**整数提升**（[[conv.prom]]），提升目标由枚举的**值**决定（[[dcl.enum]]），通常是 `int`。

**理由**：避免 C 中"把枚举常量换成同一常量转换为枚举类型"时可能产生的差异；让 C++ 能在赋予枚举项其枚举类型的同时，使它的行为像 `int`。

```cpp
typedef enum { E0 } E;   // 在 C 中，E 的底层类型可以是 unsigned int
static_assert(((E)E0 - 1 < 0) == (E0 - 1 < 0), "Must pass for C++");
```

C 中枚举常量 `E0` 的类型是 `int`，而 `(E)E0` 的类型是 `E`，若 `E` 的底层类型是 `unsigned int`，`(E)E0 - 1` 就是一个很大的无符号数，断言失败。C++ 中两边都提升为 `int`，断言必定成立。

**改写难度**：程序必须显式转换为底层类型。

**使用频率**：罕见。

### ¶4 `bool` 不能自减

**受影响小节**：[[expr.post.incr]] 与 [[expr.pre.incr]]

**改动**：对 `bool` 左值使用 `--` 在 C++ 中非良构（C 中通过 `<stdbool.h>` 的 `bool` 宏或 `_Bool` 是合法的）。C++17 起 `++` 也不允许，见 [[diff.cpp14]]。

**理由**：语义令人意外。

### ¶5 对空指针或尾后指针解引用再取地址

**受影响小节**：[[expr.unary.op]]

**改动**：某些上下文中，在 C 里对解引用的空指针或尾后指针取地址是良定义的（结果就是原指针），在 C++ 中是 UB。

```cpp ub
void f() {
  char* p = nullptr;
  char* p2 = &*p;    // C：良定义；C++：UB
  char* p3 = &p[0];  // C：良定义；C++：UB
  int a[5];
  int* q = &a[5];    // C：良定义；C++：UB
}
```

C 标准明文规定 `&*E` 等价于 `E`、`&E[i]` 等价于 `E + i`，`*` 和 `[]` 实际上不求值。C++ 没有这条特殊规则：`*p` 先形成一个左值，而形成一个不指向对象的左值本身就是 UB（参见 [[ub.expr]]）。

**理由**：C++ 中对左值的处理保持一致。

**改写难度**：语法变换，改成指针算术（`a + 5`、`p + 0`），必要时加上空指针检查。

**使用频率**：偶尔。`&a[N]` 作为尾后指针的写法在 C 风格代码中并不少见。

### ¶6 C++ 中类型只能在声明中定义，不能在表达式中定义

**受影响小节**：[[expr.sizeof]] 与 [[expr.cast]]

**改动**：C 中 `sizeof` 表达式或强制转换表达式可以定义一个新类型。

```cpp error
void* p;
void f() { p = (void*)(struct x { int i; }*)0; }   // C：定义了 struct x；C++：非良构
```

**理由**：这个禁令有助于明确定义在源代码中的位置。

**Clang 23 实测**：C++ 报 `'x' cannot be defined in a type specifier`。

**改写难度**：语法变换。**使用频率**：很少。

### ¶7 数组之间不能直接比较

**受影响小节**：[[expr.rel]] 与 [[expr.eq]]

**改动**：C 允许直接比较两个数组对象（比较的是退化后的地址），C++ 不允许。

```cpp
int arr1[5];
int arr2[5];
int same = arr1 == arr2;    // 合法的 C；C++ 中非良构
int idem = arr1 == +arr2;   // 合法的 C++；C 中违反约束（C 的一元 + 不接受指针）
```

**理由**：比较的是地址而不是内容，容易误解。C++26 的改动见 [[diff.cpp23]] [expr] ¶2。

**Clang 23 实测**：C17 只有 `array comparison always evaluates to false [-Wtautological-compare]` 警告；C++2c 报 `comparison between two arrays is ill-formed in C++26`。

**改写难度**：C++ 编译器会诊断。显式把任一数组转换为指针即可复现原行为，例如用一元 `+`——但如上所示，这种写法反过来在 C 中不合法；C/C++ 共用的代码应写 `&arr1[0] == &arr2[0]`。

**使用频率**：罕见。

### ¶8 条件、赋值、逗号表达式的结果可以是左值

**受影响小节**：[[expr.cond]]、[[expr.assign]]、[[expr.comma]]

**改动**：C++ 中这三种表达式的结果可以是左值；C 中它们总是右值。

**理由**：C++ 更强调左值，例如函数调用也可以产生左值。

**影响**：静默改变。

```cpp
char arr[100];
int s = sizeof(0, arr);   // C++：100（结果是数组左值）；C：sizeof(char*)（结果是退化后的指针）
```

**Clang 23 实测**：C17 给出 `sizeof on pointer operation will return size of 'char *' instead of 'char[100]' [-Wsizeof-array-decay]`；C++ 下无诊断，结果是 100。

**改写难度**：程序要显式转换为相应的右值。**使用频率**：罕见。

## Clause [stmt]：语句 {#diff.stat}

### ¶1 不能跳过带初始化的声明

**受影响小节**：[[stmt.switch]] 与 [[stmt.goto]]

**改动**：跳过一个带显式或隐式初始化器的声明（除非跳过的是整个没有进入的块）在 C++ 中无效。

**理由**：初始化器中的构造函数可能分配资源，离开块时需要释放；允许跳过初始化就需要复杂的运行期判断。而且对未初始化对象的很多操作都是 UB。有了这条简单的编译期规则，C++ 保证"一个已初始化的变量只要在作用域内，就确实被初始化过"。

```cpp error
void f(int n) {
  goto L;
  int x = n;   // 合法的 C；C++ 中跳过了初始化
L:
  (void)x;
}
```

**Clang 23 实测**：C++ 报 `cannot jump from this goto statement to its label`。`switch` 的 `case` 标签跳过初始化同理，加一对花括号把那个 `case` 的声明包起来即可。

**改写难度**：语义变换。**使用频率**：很少。

### ¶2 声明了返回值的函数必须返回值

**受影响小节**：[[stmt.return]]

**改动**：从声明了返回类型的函数中不带值地返回（显式的 `return;`，或者流出函数末尾）在 C++ 中无效。

**理由**：调用者和被调用者可能对类对象的返回采用相当复杂的机制；如果某些控制流路径不带值返回，实现会复杂得多。况且，承诺返回某类型的值却不返回，一直被认为是有问题的做法，只是因为很早的 C 不区分 `void` 和 `int` 返回类型才被容忍。

**补充**：需要区分两种情况。`return;`（不带值）在 C++ 中非良构，必须诊断；**流出**非 `void` 函数的末尾，在 C++ 中是运行期 UB（见 [[ub.stmt]]），编译器通常只警告。

**Clang 23 实测**：`int g(void) { return; }` 在 C17 和 C++ 下都报 `non-void function 'g' should return a value [-Wreturn-mismatch]`（Clang 在 C 中也把它当作错误）；`int h(void) { }` 两者都只有警告 `non-void function does not return a value [-Wreturn-type]`。

**改写难度**：语义变换，补上合适的返回值（如 0）。

**使用频率**：很少。多年来许多 C 实现已经对此给出警告。

## Clause [dcl]：声明 {#diff.dcl}

### ¶1 变量声明不能是 cv `void` 类型

**受影响小节**：[[dcl.pre]]

```cpp error
extern void x;   // 合法的 C（只要不是定义）；C++ 中非良构
```

**改写难度**：语法变换。**使用频率**：很少。

### ¶2 `static` / `extern` 只能用于对象和函数

**受影响小节**：[[dcl.stc]]

**改动**：C++ 中，存储类说明符不能用于类型声明；C 中它们被忽略。

```cpp
static struct S {   // 合法的 C；C++ 中非良构
  int i;
};
```

**理由**：存储类说明符与类型放在一起没有意义；C++ 中类成员可以用 `static` 声明，类型声明上的存储类说明符容易引起混淆。

**Clang 23 实测**：C17 给出 `'static' ignored on this declaration`；C++ 也只给警告 `'static' is not permitted on a declaration of a type [-Wmissing-declarations]`。

**改写难度**：语法变换。**使用频率**：很少。

### ¶3 `register` 不是存储类说明符

**受影响小节**：[[dcl.stc]]

C++17 起 `register` 不再是存储类说明符（见 [[diff.cpp14]]）。

**理由**：它在 C++ 中没有任何效果。

**改写难度**：语法变换，删掉即可。**使用频率**：常见（老 C 代码里到处都是）。

### ¶4 typedef 名不能与同一作用域的类名相同

**受影响小节**：[[dcl.typedef]]

**改动**：C++ 中，*typedef-name* 必须与同一作用域中声明的任何类类型名不同（除非 typedef 就是该类名的同义词）。C 中 typedef 名和结构体标签在不同的"名字空间"里，可以同名。

```cpp
typedef struct name1 { /* ... */ } name1;   // C 和 C++ 都合法
struct name { /* ... */ };
typedef int name;                           // 合法的 C；C++ 中非良构
```

**理由**：为了使用方便，C++ 不要求在对象声明或类型转换中给类型名加 `class`、`struct`、`union` 前缀：`class name {…}; name i;`。

**Clang 23 实测**：C++ 报 `typedef redefinition with different types ('int' vs 'name')`。

**改写难度**：语义变换，两个类型之一要改名。**使用频率**：很少。

### ¶5 `const` 对象必须初始化

**受影响小节**：[[dcl.type]]（另见 [[basic.link]]）

```cpp error
const int ci;   // 合法的 C；C++ 中非良构
```

**理由**：`const` 对象不能被赋值，必须初始化才能持有有用的值。

**Clang 23 实测**：C++ 报 `default initialization of an object of const type 'const int'`。

**改写难度**：语义变换。**使用频率**：很少。

### ¶6 `auto` 不能用作存储类说明符

**受影响小节**：[[dcl.spec.auto]]

```cpp error
void f() {
  auto int x;   // 合法的 C；C++ 中非良构
}
```

**理由**：`auto` 被用来从初始化器推导类型，如果同时允许它作存储类说明符，某些上下文中会出现不想要的解释。

**改写难度**：语法变换。**使用频率**：罕见。

### ¶7 空形参表表示不接受实参

**受影响小节**：[[dcl.fct]]

**改动**：C++ 中 `int f();` 表示 `int f(void)`；在 C17 及以前，它表示"实参的个数和类型未知"（C23 已经改成与 C++ 相同）。

**理由**：避免用错误的实参个数或类型调用函数。

**影响**：语义改变。这种写法在 C 中早已被标为"过时"（obsolescent）。

**改写难度**：语法变换。使用 C 不完整声明风格的函数声明必须补全为完整的原型。如果对同一个（无原型的）函数的不同调用传入了不同个数或类型的实参，程序可能还需要进一步修改。

**使用频率**：常见。

### ¶8 返回类型或形参类型中不能定义类型

**受影响小节**：[[dcl.fct]]（另见 [[expr.sizeof]]）

```cpp error
void f( struct S { int a; } arg ) {}   // 合法的 C；C++ 中非良构
enum E { A, B, C } f() {}              // 合法的 C；C++ 中非良构
```

**理由**：比较不同 TU 中的类型时，C++ 依赖名字等价，而 C 依赖结构等价。至于形参类型：在形参列表中定义的类型属于函数的作用域，C++ 中唯一合法的调用只能来自函数自身。

**Clang 23 实测**：C17 给出 `declaration of 'struct T' will not be visible outside of this function [-Wvisibility]`；C++ 报 `'T' cannot be defined in a parameter type`。

**改写难度**：语义变换，把类型定义移到文件作用域或头文件中。

**使用频率**：很少。这种风格被视为不好的编码风格。

### ¶9 没有"旧式"C 函数定义

**受影响小节**：[[dcl.fct.def]]

```cpp error
int f2(a, b) int a; int b; { return a + b; }   // K&R 风格：C17 中合法但已过时；C++ 中非良构
```

**理由**：原型对类型安全至关重要。

**Clang 23 实测**：C17 给出 `a function definition without a prototype is deprecated in all versions of C and is not supported in C23 [-Wdeprecated-non-prototype]`；C++ 报一串语法错误。

**改写难度**：语法变换。**使用频率**：在旧程序中常见，但早已被视为过时。

### ¶10 指派初始化的限制

**受影响小节**：[[dcl.init.aggr]]

**改动**：C++ 的指派初始化比 C 的受限：非静态数据成员的指派符必须按声明顺序出现；不支持数组元素指派符和嵌套指派符；同一初始化列表中不能混用指派与非指派初始化器。

```cpp
struct A { int x, y; };
struct B { struct A a; };
struct A a = {.y = 1, .x = 2};   // 合法的 C；C++ 中非良构（乱序）
int arr[3] = {[1] = 5};          // 合法的 C；C++ 中非良构（数组指派符）
struct B b = {.a.x = 0};         // 合法的 C；C++ 中非良构（嵌套指派符）
struct A c = {.x = 1, 2};        // 合法的 C；C++ 中非良构（混用）
```

**理由**：C++ 中成员按构造的逆序销毁，初始化列表中的元素按词法顺序求值，所以成员初始化器必须按顺序给出。数组指派符与 lambda 表达式的语法冲突（`[1]` 像一个捕获列表）。嵌套指派符很少使用。

**Clang 23 实测**：Clang 在 C++ 中把这四种写法都作为扩展接受，只给警告：

```text
warning: ISO C++ requires field designators to be specified in declaration order; field 'y' will be initialized after field 'x' [-Wreorder-init-list]
warning: array designators are a C99 extension [-Wc99-designator]
warning: nested designators are a C99 extension [-Wc99-designator]
warning: mixture of designated and non-designated initializers in the same initializer list is a C99 extension [-Wc99-designator]
```

GCC 对乱序指派会直接报错，可移植的 C/C++ 共用代码要按声明顺序写。

**改写难度**：语法变换。**使用频率**：乱序初始化器很常见，其他几种很少用。

### ¶11 用字符串初始化字符数组时，数组必须容得下结尾的 `'\0'`

**受影响小节**：[[dcl.init.string]]

```cpp error
char array[4] = "abcd";   // 合法的 C（不存 '\0'）；C++ 中非良构
```

**理由**：这种没有结尾零的数组被标准字符串函数处理时，有造成严重灾难的可能。

**Clang 23 实测**：C++ 报 `initializer-string for char array is too long, array size is 4 but initializer has size 5 (including the null terminating character)`。

**改写难度**：语义变换，数组要多声明一个元素。若确实需要不带结尾零的字节数组，改成 `{'a', 'b', 'c', 'd'}`。

**使用频率**：很少。这种写法被视为不好的编码风格（但在嵌入式代码的固定长度标识符里偶尔能见到）。

### ¶12 枚举对象只能被赋予同一枚举类型的值

**受影响小节**：[[dcl.enum]]

```cpp error
enum color { red, blue, green };
enum color c = 1;   // 合法的 C；C++ 中非良构
```

**理由**：C++ 的类型安全。

**Clang 23 实测**：C++ 报 `cannot initialize a variable of type 'enum color' with an rvalue of type 'int'`。

**改写难度**：语法变换（显式转换即可自动修正这类类型错误）。**使用频率**：常见。

### ¶13 枚举项的类型是其枚举

**受影响小节**：[[dcl.enum]]

**改动**：C++ 中枚举项的类型是它的枚举类型；C 中枚举项的类型是 `int`（C23 有所变化）。

```cpp error
enum e { A };
void f() {
  auto x = A;
  int* p = &x;   // 合法的 C（C23）；C++ 中非良构：x 的类型是 enum e
}
```

**理由**：C++ 中枚举是一个独立的类型。

**改写难度**：语义变换。**使用频率**：很少。

### ¶14 对齐说明符是属性说明符

**受影响小节**：[[dcl.align]]

**改动**：C++ 中 *alignment-specifier* 是一种 *attribute-specifier*，位置受属性语法约束；C 中它是 *declaration-specifier*，可以和其他说明符混在一起。

```cpp
#include <stdalign.h>
unsigned alignas(8) int x;   // 合法的 C；C++ 中非良构
unsigned int y alignas(8);   // 合法的 C++；C 中非良构
```

**理由**：C++ 要求对齐说明符的位置无歧义。

**改写难度**：语法变换。C/C++ 共用的写法是放在声明最前面：`alignas(8) unsigned int x;`。

**使用频率**：很少。

## Clause [class]：类 {#diff.class}

### ¶1 内层作用域的类声明隐藏外层同名的对象或函数

**受影响小节**：[[class.name]]（另见 [[dcl.typedef]]）

**改动**：C++ 中类声明把类名引入它所在的作用域，并隐藏外层作用域中同名的对象、函数或其他声明。C 中内层作用域的结构体标签从不隐藏外层的对象或函数名。

```cpp run title="hide.c" ok
#include <stdio.h>
int x[99];
int main(void) {
  struct x { int a; };
  printf("%zu\n", sizeof(x));   // C：数组的大小；C++：结构体的大小
}
```

**Clang 23 实测**：同一份文件，C17 输出 `396`，C++ 输出 `4`。静默改变。

**理由**：这是可以归因于 C++ 新的名字空间定义的少数不兼容之一：一个名字可以在同一作用域中既声明为类型又声明为非类型，此时非类型名字隐藏类型名字，要引用类型名就必须加 `class`、`struct`、`union` 或 `enum`。这种名字空间定义为 C++ 程序员提供了重要的书写便利，并让用户定义类型的使用尽量接近基本类型。委员会判断它的好处远远超过上述与 C 的不兼容。

**改写难度**：语义变换。如果需要访问的被隐藏名字在全局作用域，可以用 `::x`；如果在块作用域，类型或结构体标签之一要改名。

**使用频率**：很少。

### ¶2 隐式的复制构造函数和复制赋值不能复制 `volatile` 左值

**受影响小节**：[[class.copy.ctor]]

```cpp error
struct X { int i; };
volatile struct X x1 = {0};
struct X x2 = x1;   // 合法的 C；C++ 中非良构
struct X x3;
x3 = x1;            // 同样非良构
```

隐式复制构造函数的形参是 `const X&`，不能绑定到 `volatile X` 左值。

**理由**：委员会讨论过多种方案。把形参改成 `volatile const X&` 会让为类对象生成高效代码变得非常复杂；为隐式定义的操作提供两套签名，又有可能引起歧义，并让"根据基类和成员决定这些操作的形式"的规则变得复杂，相关疑虑一直没有解决。

**Clang 23 实测**：C++ 报 `no matching constructor for initialization of 'struct X'` 和 `no viable overloaded '='`。

**改写难度**：语义变换。需要 `volatile` 语义的复制，就提供用户声明的构造函数或赋值运算符；不需要的话，可以用显式的 `const_cast`。

**使用频率**：很少。

### ¶3 普通 `int` 类型的位域是有符号的

**受影响小节**：[[class.bit]]

**改动**：C 中 `int b : 3;` 是有符号还是无符号由实现定义；C++ 中是有符号的。

**理由**：模板特化之间的符号性需要一致。为了一致，对非依赖类型也取消了这个实现自由。

**改写难度**：语法变换。**使用频率**：很少。

### ¶4 嵌套类的名字局限于外围类

**受影响小节**：[[class.nest]]

```cpp error
struct X {
  struct Y { /* ... */ } y;
};
struct Y yy;   // 合法的 C；C++ 中非良构
```

**理由**：C++ 的类有成员函数，需要类建立作用域。C 的规则会让类成为一种不完整的作用域机制，使 C++ 程序员无法保持类内的局部性。基于 C 规则的一套 C++ 作用域规则会非常复杂，程序员也无法可靠地预测涉及嵌套或局部函数的非平凡例子的含义。

**改写难度**：语义变换。要让结构体类型名在外围结构体的作用域中可见，可以在定义外围结构体之前，先在外围作用域中声明这个结构体标签：

```cpp
struct Y;   // struct Y 与 struct X 在同一作用域
struct X {
  struct Y { /* ... */ } y;   // C++ 中：这里定义的是 X::Y，不是 ::Y！
};
```

（注意：按 C++ 的规则，`X` 内部带类体的 `struct Y { … }` 定义的是新的成员类 `X::Y`，并不会补全外层的 `::Y`。Clang 23 实测：在上面的代码之后写 `struct Y yy;`，C17 通过，C++ 报 `variable has incomplete type 'struct Y'`。所以真正可行的改法是把内层结构体的定义整个移到 `X` 外面，`X` 里只写 `struct Y y;`。）附录的意思是：凡是定义在其他结构体内部、又在外面被引用的 C 结构体类型，都应当提升到外围结构体所在的作用域。这是作用域规则差异的直接后果，见上文 [diff.basic] ¶2。

**使用频率**：很少。

### ¶5 typedef 名在类定义中被使用后不能再被重新声明

**受影响小节**：[[class.member.lookup]]

```cpp
typedef int I;
struct S {
  I i;
  int I;   // 合法的 C；C++ 中非良构，不要求诊断
};
```

**理由**：类变复杂时，允许在类型已被使用之后再重新定义它，会让 C++ 程序员搞不清 `I` 到底是什么。

**说明**：按当前草案 [[class.member.lookup#6]]，在类中查找 `I` 的结果若与在完整类上下文中的查找结果不同，程序是 **IFNDR**。

**Clang 23 实测**：C++ 下没有诊断。

**改写难度**：语义变换，类型或结构体成员之一要改名。**使用频率**：很少。

## Clause [cpp]：预处理指令 {#diff.cpp}

### ¶1 `__STDC__` 是否定义、定义成什么，由实现定义

**受影响小节**：[[cpp.predefined]]

**理由**：C++ 不等于 C。强制定义 `__STDC__` 就是要求编译器作出不真实的声明。

**影响**：语义改变。用 `#ifdef __STDC__` 判断"是否标准 C"的头文件，在 C++ 中可能走另一个分支。Clang 23 在 C++ 模式下仍然定义 `__STDC__` 为 1；判断 C++ 应该用 `__cplusplus`。

**改写难度**：语义变换。

**使用频率**：引用 `__STDC__` 的程序和头文件相当常见。

## 小结

| 类别 | 编译器会报错的 | 静默改变的 |
|---|---|---|
| 词法 | 新关键字、`char*` 指向字面量（Clang 只警告） | `sizeof('x')` |
| 基础 | 暂定定义、`struct` 作用域、`main` 递归（Clang 默认不报） | `const` 的内部链接（链接期才发现） |
| 表达式 | `void*` 转换、枚举混合运算、类型定义在表达式中、数组比较 | `sizeof(0, arr)`、`&*p`（UB） |
| 语句 | 跳过初始化、`return;` | 流出非 `void` 函数末尾（UB） |
| 声明 | `extern void`、typedef 同名、`const` 未初始化、K&R 定义、字符数组溢出、枚举赋值 | `int f();` 的含义 |
| 类 | `volatile` 复制、嵌套类名 | 内层 `struct x` 隐藏外层 `x`、typedef 重声明（IFNDR） |
| 预处理 | — | `__STDC__` |
