---
title: C++ 与 C 的差异
summary: 合法的 C 代码用 C++ 编译时会在哪里报错、哪里不报错却改变含义，以及每处差异背后的设计理由；附 Clang 23 分别按 C17 和 C++2c 编译的结果。
status: done
covers: *
related: diff, diff.library, diff.cpp03, lex.key, basic.def, basic.scope, basic.link, conv.ptr, expr.arith.conv, dcl.init.aggr, dcl.enum, class.name
tags: 附录, 兼容性, C, 迁移
updated: 2026-10-19
---

!!! tldr
    - 这一节列出合法的 C 代码在 C++ 中非良构、未定义或含义改变的 39 处，写 C/C++ 共用头文件、把 C 项目迁移到 C++ 时都会碰到。
    - 大多数差异来自 C++ 更严格的类型检查：`void*` 不能隐式转成其他对象指针，枚举不能和整数随意互换，字符串字面量是 `const` 的。
    - 另一类来自作用域规则：`struct` 在 C++ 中是一个作用域，类名和普通名字在同一个名字空间里，内层的 `struct x` 会隐藏外层的变量 `x`。
    - 编译器不报错、但含义改变的有 `sizeof('x')`、`sizeof(0, arr)`、内层类名隐藏外层对象、文件作用域 `const` 的内部链接；`&*p`、`&a[N]` 在 C 中良定义而在 C++ 中是 UB。
    - Clang 对其中几条只给警告（`char* p = "abc"`、类型声明上的 `static`、递归调用 `main`、C 风格的指派初始化），用 `-pedantic-errors` 才能把它们变成错误。

C 的各个版本都没有在附录中点名，条目针对的是 C 的现行规则。与其他小节相比，这一节的条目多两项：改写的难度和这种写法的使用频率。它们汇总在页尾的表格里。

下文的实测用 Clang 23.1.3 把同一份源文件分别按 `clang -x c -std=c17` 和 `clang++ -x c++ -std=c++2c` 编译。

## 词法 {#diff.lex}

### 新关键字

```cpp error
int class = 1, new = 2, this = 3;   // 合法的 C
```

¶1 C++ 增加了 `class`、`new`、`delete`、`this`、`template`、`namespace`、`private`、`virtual`、`operator`、`friend`、`try`、`catch`、`throw` 等关键字（[[lex.key]]）。用它们作标识符的 C 程序不是合法的 C++ 程序。C 代码里 `new`、`class`、`this` 作变量名或结构体成员名相当常见。

### 字符字面量的类型是 `char`

```cpp
int function(int i);
int function(char c);
int n = function('x');           // 调用 function(char)
int sz = sizeof('x');            // C：sizeof(int)；C++：1
```

¶2 C 中字符字面量 `'x'` 的类型是 `int`，C++ 中是 `char`（[[lex.ccon]]）。这是为了让重载决议更合理：`function('x')` 应当匹配 `function(char)`。代价是依赖 `sizeof('x') == sizeof(int)` 的 C 程序在 C++ 中结果不同，编译器不会提示。

### 拼接的字符串字面量不能有冲突的编码前缀

¶3 `L"a" U"b"` 这样两边编码前缀不同的相邻字符串字面量，在 C++ 中非良构（[[lex.string]]）。C 中是否支持由实现定义，这是一个不可移植的特性。另见 [[diff.cpp20]]。

### 字符串字面量是 `const` 的

```cpp error
char* p = "abc";          // 合法的 C；C++ 中非良构
void f(char*);
void g() {
  f((char*)"def");        // OK：附录给出的改法
}
```

¶4 C++ 中，普通字符串字面量的类型是 `const char` 的数组，而不是 C 中的 `char` 的数组。宽字符串、UTF-8、UTF-16、UTF-32 字符串字面量同理，分别是 `const wchar_t`、`const char8_t`、`const char16_t`、`const char32_t` 的数组（[[lex.string]]）。理由是避免调用一个可能修改实参的重载函数。C 中修改字符串字面量同样是 UB，只是类型系统不阻止。

Clang 在 C++ 模式下对第一行只给警告 `ISO C++11 does not allow conversion from string literal to 'char *'`，加 `-pedantic-errors` 才是错误。附录建议的改法是加强制转换；更好的做法是把指针改成 `const char*`。

## 基础 {#diff.basic}

### 没有暂定定义

```cpp error
int i;
int i;   // 合法的 C；C++ 中重复定义
```

¶1 C 允许文件作用域上不带初始化器、不带 `extern` 的对象声明在同一翻译单元里出现多次，最后合并成一个定义，这叫暂定定义（[[g:tentative-definition]]）。C++ 中每个这样的声明都是定义（[[basic.def]]），第二个就是重复定义。

一个后果是：只用 C 的初始化语法，在 C++ 中无法定义一组互相引用的文件局部静态对象。

```cpp error
struct X { int i; struct X* next; };
static struct X a;               // C：暂定定义；C++：定义
static struct X b = { 0, &a };
static struct X a = { 1, &b };   // C++：重复定义
```

理由是避免内置类型和用户定义类型使用不同的初始化规则。在 C++ 中，这组对象之一的初始化必须通过函数调用等其他方式完成。

### `struct` 是一个作用域

```cpp error
struct X {
  struct Y { int a; } b;
};
struct Y c;   // 合法的 C；C++ 中要写 X::Y c;
```

¶2 C++ 中 `struct` 就是类，而类作用域是 C++ 的核心（[[basic.scope]]）。在 C 中，嵌套定义的结构体标签属于外层作用域。C++ 中 `Y` 是 `X::Y`，最后一行的 `struct Y` 声明了一个新的、不完整的全局类型，Clang 报 `variable has incomplete type 'struct Y'`。只有在外层引用嵌套的结构体、枚举或枚举项名字时才会遇到这个差别，见下文类一节中的嵌套类名。

### 文件作用域的 `const` 对象有内部链接

```cpp title="a.c"
const int limit = 10;
```

```cpp title="b.c"
extern const int limit;
int main(void) { return limit; }
```

¶3 在文件作用域上显式声明为 `const`、没有显式声明为 `extern` 的名字，在 C++ 中有内部链接，在 C 中有外部链接（[[basic.link]]，另见 [[dcl.type]]）。上面两个文件按 C 编译链接，程序返回 10；按 C++ 编译，`a.c` 中的 `limit` 对其他翻译单元不可见，链接时报未定义符号。

C++ 这样规定是因为 `const` 对象可以在编译期当作值使用：程序员被鼓励为每个 `const` 对象写出初始化器，并把它放进被多个翻译单元包含的头文件。需要外部链接时，在定义处加 `extern`：`extern const int limit = 10;`。C++17 起，头文件里更好的写法是 `inline constexpr int limit = 10;`。

### `main` 不能递归调用，也不能取地址

¶4 C++ 中 `main` 可能需要特殊处理，例如实现在它开头插入初始化静态对象的代码，所以程序不能递归调用它，也不能取它的地址（[[basic.start.main]]）。改法很简单：引入一个中间函数，如 `mymain(argc, argv)`。Clang 默认不诊断，加 `-pedantic` 才对每一处使用给出 `referring to 'main' within an expression is a Clang extension` 警告。

### C 的兼容类型

¶5 C 在多处允许兼容类型（compatible types）之间混用，C++ 不允许（[[basic.types]]）。例如 C 中枚举类型与它的底层整数类型兼容，C++ 中枚举是与底层类型不同的独立类型。更严格的类型检查对 C++ 必不可少。附录指出，名字修饰中包含形参类型的类型安全链接能找出很多、但不是全部这类问题；有些情形在 C++ 中也被布局兼容的规则允许。

## 表达式 {#diff.expr}

### `void*` 不能隐式转换为对象指针

```cpp error
char a[10];
void* b = a;
void foo() {
  char* c = b;   // 合法的 C；C++ 中非良构
}
```

¶1 C++ 比 C 更努力地在编译期保证类型安全：`void*` 到对象指针的转换必须显式写出（[[conv.ptr]]）。编译器会诊断所有这类转换，改法是加强制转换 `char* c = (char*)b;`。最常见的场合是 `int* p = malloc(n * sizeof *p);`。

### 枚举不能和别的枚举或浮点数混合运算

```cpp error
enum E1 { e };
enum E2 { f };
int b = e <= 3.7;     // 合法的 C；C++ 中非良构
int k = f - e;        // 合法的 C；C++ 中非良构
int x = 1 ? e : f;    // 合法的 C；C++ 中非良构
```

¶2 一个操作数是枚举、另一个是不同的枚举或浮点类型时，常用算术转换在 C++ 中非良构（[[expr.arith.conv]]），以加强类型安全。C++20 起这些写法被弃用，C++26 才改为非良构（[[diff.cpp23]]）。用强制转换或一元 `+` 先做整数提升，就能恢复原来的行为：`(int)e <= 3.7`、`+f - e`。

### 枚举在常用算术转换中的处理不同

```cpp
typedef enum { E0 } E;   // C 中 E 的底层类型可以是 unsigned int
static_assert(((E)E0 - 1 < 0) == (E0 - 1 < 0), "Must pass for C++");
```

¶3 对没有固定底层类型的枚举，C 在常用算术转换中把它的值转换为枚举的底层类型，而底层类型由实现选择，可以是 `unsigned int`。C++ 改为按枚举的取值范围做整数提升（[[conv.prom]]、[[dcl.enum]]），通常得到 `int`。

上例中，`E0` 在 C 中的类型是 `int`，`(E)E0` 的类型是 `E`。底层类型是 `unsigned int` 时，`(E)E0 - 1` 是一个很大的无符号数，断言失败。C++ 中两边都提升为 `int`，断言总是成立。这正是 C++ 想避免的问题：把一个枚举常量换成转换为枚举类型的同一常量，表达式的结果不应改变。本机 Clang 按 C17 编译时这条断言确实失败，按 C++ 编译时通过。

### `bool` 不能自减

¶4 对 `bool` 左值使用 `--` 在 C++ 中非良构（[[expr.post.incr]]、[[expr.pre.incr]]），在 C 中通过 `<stdbool.h>` 的 `bool` 或 `_Bool` 是合法的。这种运算的语义令人意外。C++17 起 `++` 也不再允许（[[diff.cpp14]]）。

### `&*p` 和 `&a[N]`

```cpp ub
void f() {
  char* p = nullptr;
  char* p2 = &*p;     // C：良定义；C++：UB
  char* p3 = &p[0];   // C：良定义；C++：UB
  int a[5];
  int* q = &a[5];     // C：良定义；C++：UB
}
```

¶5 C 标准明文规定 `&*E` 等价于 `E`，`&E[i]` 等价于 `E + i`，其中的 `*` 和 `[]` 实际上不求值，所以对空指针或尾后指针这样写是良定义的。C++ 对左值的处理是一致的，没有这条特殊规则：`*p` 先形成一个左值，而 `p` 不指向对象时这一步就是 UB（[[expr.unary.op]]）。

改法是改写成指针算术，如 `a + 5`、`p + 0`，必要时加上空指针检查。`&a[N]` 作为尾后指针的写法在 C 风格代码中并不少见。

### 类型只能在声明中定义

```cpp error
void* p;
void f() { p = (void*)(struct x { int i; }*)0; }
```

¶6 C 允许在 `sizeof` 表达式或强制转换表达式中定义新类型，上例定义了 `struct x`。C++ 中类型只能在声明中定义（[[expr.sizeof]]、[[expr.cast]]），这样定义在源代码中的位置更清楚。Clang 报 `'x' cannot be defined in a type specifier`。

### 数组之间不能直接比较

<div class="compare" markdown="1">

```cpp error
int arr1[5];
int arr2[5];
int same = arr1 == arr2;
// 合法的 C；C++ 中非良构
```

```cpp ok
int arr1[5];
int arr2[5];
int idem = arr1 == +arr2;
// C++ 中合法；C 中违反约束
```

</div>

¶7 C 允许直接比较两个数组，比较的是退化后的地址而不是内容，这很容易误解。C++26 起这样的比较非良构（[[expr.rel]]、[[expr.eq]]，另见 [[diff.cpp23]]）。按 C17 编译时 Clang 只警告比较结果总是 `false`；按 C++2c 编译时报 `comparison between two arrays is ill-formed in C++26`。

附录建议用一元 `+` 把任一数组转换成指针。但 C 的一元 `+` 不接受指针，C/C++ 共用的代码应写 `&arr1[0] == &arr2[0]`。

### 条件、赋值、逗号表达式的结果可以是左值

```cpp ok
char arr[100];
int s = sizeof(0, arr);   // C++：100；C：sizeof(char*)
```

¶8 C++ 中条件表达式、赋值表达式和逗号表达式的结果可以是左值，C 中它们总是右值（[[expr.cond]]、[[expr.assign]]、[[expr.comma]]）。C++ 更强调左值，比如函数调用也可以产生左值。上例在 C++ 中逗号表达式的结果是数组左值本身，`sizeof` 得到 100；在 C 中结果经过了数组到指针的转换。Clang 按 C 编译时有 `-Wsizeof-array-decay` 警告，按 C++ 编译时没有诊断。依赖这一点的 C 代码要显式转换为相应的右值。

## 语句 {#diff.stat}

### 不能跳过带初始化的声明

```cpp error
void f(int n) {
  goto L;
  int x = n;   // 合法的 C；C++ 中跳过了初始化
L:
  (void)x;
}
```

¶1 C++ 中，跳过一个带显式或隐式初始化的声明是非良构的，除非跳过的是整个没有进入的块（[[stmt.switch]]、[[stmt.goto]]）。初始化器中的构造函数可能分配资源，离开块时要释放；允许跳过初始化就需要复杂的运行期判断，而且对未初始化对象的很多操作都是 UB。有了这条编译期规则，一个已初始化的变量只要在作用域内，就一定被初始化过。

Clang 报 `cannot jump from this goto statement to its label`。`switch` 的 `case` 标签跳过初始化同理，用一对花括号把那个 `case` 中的声明包起来即可。

### 声明了返回类型的函数必须返回值

¶2 从声明了返回类型的函数中不带值地返回，在 C++ 中无效（[[stmt.return]]）。调用者和被调用者可能对类对象的返回采用复杂的机制，有些路径不带值返回会让实现复杂得多。而且承诺返回值却不返回一直被认为是有问题的做法，只是因为很早的 C 不区分 `void` 和 `int` 返回类型才被容忍。

这里要分两种情况。显式的 `return;` 在 C++ 中非良构，必须诊断；Clang 在 C17 下也把它当作错误（`-Wreturn-mismatch`）。从非 `void` 函数的末尾流出则是运行期 UB（[[stmt.return#4]]），编译器通常只给 `-Wreturn-type` 警告。改法是补上合适的返回值。

## 声明 {#diff.dcl}

### 变量不能声明为 `void` 类型

¶1 C++ 中任何变量声明都不能是 cv `void` 类型。C 允许，只要它不是定义，例如 `extern void x;`（[[dcl.pre]]）。这是更严格的类型检查。

### 存储类说明符只能用于对象和函数

```cpp error
static struct S {   // 合法的 C；C++ 中非良构
  int i;
};
```

¶2 C++ 中 `static` 和 `extern` 只能用于对象和函数的名字（[[dcl.stc]]）；C 中它们用在类型声明上时被忽略。存储类说明符与类型放在一起没有意义，而 C++ 的类成员可以声明为 `static`，在类型声明上写它容易引起混淆。Clang 在 C++ 中只给警告 `'static' is not permitted on a declaration of a type`，并没有拒绝。

### `register` 不是存储类说明符

¶3 `register` 在 C++ 中没有任何效果，C++17 起不再是存储类说明符（[[dcl.stc]]，另见 [[diff.cpp14]]）。老的 C 代码里很常见，删掉即可。Clang 在 C++17 及以后的模式下报 `ISO C++17 does not allow 'register' storage class specifier`。

### typedef 名不能与同一作用域的类名相同

```cpp error
typedef struct name1 { int a; } name1;   // C 和 C++ 都合法
struct name { int a; };
typedef int name;                        // 合法的 C；C++ 中非良构
```

¶4 C 中 typedef 名和结构体标签在不同的名字空间里，可以同名。C++ 中，typedef 名必须与同一作用域中的类名不同，除非它就是这个类的同义词（[[dcl.typedef]]）。原因是 C++ 在声明对象或类型转换时不要求写 `class`、`struct` 或 `union` 前缀：有了 `class name {…};`，就可以直接写 `name i;`。两个类型之一要改名。

### `const` 对象必须初始化

¶5 `const int ci;` 在 C 中合法，在 C++ 中非良构（[[dcl.type]]，另见 [[basic.link]]）。`const` 对象不能被赋值，不初始化就不可能持有有用的值。Clang 报 `default initialization of an object of const type 'const int'`。

### `auto` 不能用作存储类说明符

¶6 C 的 `auto int x;` 在 C++ 中非良构（[[dcl.spec.auto]]）。C++ 用 `auto` 从初始化器推导变量类型，如果同时允许它作存储类说明符，某些语境中会出现不想要的解释。Clang 对此只给警告 `-Wauto-storage-class`。

### 空形参表表示不接受实参

```cpp
int f();   // C++：等价于 int f(void)
           // C17 及以前：实参的个数和类型未知
```

¶7 C++ 中空形参表表示函数不接受实参（[[dcl.fct]]），这样可以避免用错误的实参个数或类型调用函数。C 早已把无原型的声明标为过时，C23 也改成了与 C++ 相同的含义。转换时要把 C 的不完整声明补全为原型；如果对同一个无原型函数的不同调用传了不同个数或类型的实参，程序还需要进一步修改。

### 返回类型和形参类型中不能定义类型

```cpp error
void f( struct S { int a; } arg ) {}   // 合法的 C；C++ 中非良构
enum E { A, B, C } g() {}              // 合法的 C；C++ 中非良构
```

¶8 C++ 中不能在返回类型或形参类型中定义类型（[[dcl.fct]]，另见 [[expr.sizeof]]）。比较不同翻译单元中的类型时，C++ 依靠名字等价，C 依靠结构等价。至于形参类型：定义在形参列表中的类型属于函数的作用域，在 C++ 中唯一合法的调用只能来自函数自身。类型定义要移到文件作用域或头文件中。

### 没有旧式函数定义

```cpp error
int f2(a, b) int a; int b; { return a + b; }   // K&R 风格
```

¶9 C++ 的函数定义语法不包括 C 的旧式（K&R 风格）定义（[[dcl.fct.def]]），因为原型对类型安全必不可少。C 中这种写法早已过时：Clang 在 C17 下警告它不被 C23 支持，在 C++ 下报一串语法错误。

### 指派初始化受到限制

```cpp
struct A { int x, y; };
struct B { struct A a; };
struct A a = {.y = 1, .x = 2};  // 合法的 C；C++ 中非良构：乱序
int arr[3] = {[1] = 5};         // 合法的 C；C++ 中非良构：数组指派符
struct B b = {.a.x = 0};        // 合法的 C；C++ 中非良构：嵌套指派符
struct A c = {.x = 1, 2};       // 合法的 C；C++ 中非良构：混用
```

¶10 C++ 的指派初始化比 C 受限（[[dcl.init.aggr]]）：非静态数据成员的指派符必须按声明顺序出现；不支持数组元素指派符和嵌套指派符；同一个初始化列表中不能混用指派与非指派的初始化器。

各有理由。C++ 中成员按构造的逆序销毁，初始化列表中的元素按书写顺序求值，所以成员初始化器必须按顺序给出。数组指派符 `[1]` 与 lambda 表达式的语法冲突。嵌套指派符很少使用。

Clang 在 C++ 中把这四种写法都作为扩展接受，分别给出 `-Wreorder-init-list` 和三条 `-Wc99-designator` 警告。GCC 对乱序的指派会直接报错。可移植的共用代码要按声明顺序写。

### 用字符串初始化字符数组时要容得下 `'\0'`

```cpp error
char array[4] = "abcd";   // 合法的 C（不存结尾的 '\0'）；C++ 中非良构
```

¶11 C++ 中，用字符串初始化字符数组时，字符串的字符数（包括结尾的 `'\0'`）不能超过数组的元素数（[[dcl.init.string]]）。C 允许数组恰好放不下结尾的 `'\0'`，而没有结尾零的数组交给标准字符串函数处理可能酿成严重后果。数组要多声明一个元素；确实需要不带结尾零的字节数组时，写成 `{'a', 'b', 'c', 'd'}`。

### 枚举对象只能被赋予同一枚举类型的值

```cpp error
enum color { red, blue, green };
enum color c = 1;   // 合法的 C；C++ 中非良构
```

¶12 C 中枚举类型的对象可以被赋予任何整数类型的值；C++ 中只能被赋予同一枚举类型的值（[[dcl.enum]]），这是 C++ 类型安全的体现。加显式转换就能修正，这种写法在 C 代码中很常见。

### 枚举项的类型是它的枚举

```cpp error
enum e { A };
void f() {
  auto x = A;
  int* p = &x;   // 合法的 C23；C++ 中 x 的类型是 enum e
}
```

¶13 C++ 中枚举项的类型是它的枚举类型，C 中是某种整数类型（[[dcl.enum]]）。C++ 中枚举是一个独立的类型。上例按 C23 编译时 `x` 的类型是 `int`，按 C++ 编译时报 `cannot initialize a variable of type 'int *' with an rvalue of type 'e *'`。

### 对齐说明符是属性说明符

```cpp
#include <stdalign.h>
unsigned alignas(8) int x;   // 合法的 C；C++ 中非良构
unsigned int y alignas(8);   // 合法的 C++；C 中非良构
```

¶14 C++ 中的对齐说明符属于属性说明符，位置受属性语法约束；C 中它是声明说明符，可以和其他说明符混在一起（[[dcl.align]]）。C++ 要求对齐说明符的位置没有歧义。C/C++ 共用的写法是放在声明最前面：`alignas(8) unsigned int x;`。

## 类 {#diff.class}

### 内层的类名隐藏外层的对象

```cpp run title="hide.c" ok
#include <stdio.h>
int x[99];
int main(void) {
  struct x { int a; };
  printf("%zu\n", sizeof(x));   // C：数组的大小；C++：结构体的大小
}
```

¶1 C++ 中，类声明把类名引入所在的作用域，并隐藏外层作用域中同名的对象、函数或其他声明（[[class.name]]，另见 [[dcl.typedef]]）。C 中内层作用域的结构体标签从不隐藏外层的对象或函数名。同一份文件按 C 编译输出 `396`，按 C++ 编译输出 `4`，没有任何诊断。

这是 C++ 名字空间规则带来的少数几处不兼容之一。C++ 中一个名字可以在同一作用域里既声明为类型又声明为非类型，此时非类型名隐藏类型名，要引用类型就得加 `class`、`struct`、`union` 或 `enum`。这套规则让用户定义类型用起来尽量像基本类型，委员会认为它的好处远超这处不兼容。如果被隐藏的名字在全局作用域，可以用 `::x` 访问；如果在块作用域，类型或对象之一要改名。

### 隐式复制操作不能复制 `volatile` 左值

```cpp error
struct X { int i; };
volatile struct X x1 = {0};
void f() {
  struct X x2 = x1;   // 合法的 C；C++ 中非良构
  struct X x3;
  x3 = x1;            // 同样非良构
}
```

¶2 隐式声明的复制构造函数和复制赋值运算符的形参是 `const X&`，不能绑定到 `volatile X` 左值（[[class.copy.ctor]]）。委员会讨论过别的方案：把形参改成 `const volatile X&` 会让类对象难以生成高效的代码；为隐式操作提供两套签名，又可能引起歧义，并让根据基类和成员决定这些操作形式的规则变复杂。

Clang 报 `no matching constructor for initialization of 'struct X'` 和 `no viable overloaded '='`。需要 `volatile` 语义的复制时，自己声明构造函数或赋值运算符；不需要时，可以用 `const_cast` 去掉 `volatile`。

### 普通 `int` 位域是有符号的

¶3 C 中 `int b : 3;` 是有符号还是无符号由实现定义；C++ 中它是有符号的（[[class.bit]]）。同一个模板的不同特化之间符号性必须一致，为了一致，非依赖类型也取消了这个实现自由。

### 嵌套类的名字局限于外围类

```cpp error
struct X {
  struct Y { int a; } y;
};
struct Y yy;   // 合法的 C；C++ 中非良构
```

¶4 C++ 中嵌套类的名字属于外围类；C 中它与最外层的外围结构体属于同一个作用域（[[class.nest]]）。C++ 的类有成员函数，需要类建立作用域。按 C 的规则，类只能是一个不完整的作用域机制，程序员无法保持类内的局部性；以 C 规则为基础的一套 C++ 作用域规则会非常复杂，涉及嵌套类或局部函数的例子将难以预测。

附录建议在外围结构体之前先声明 `struct Y;`。这在 C 中可行，但在 C++ 中 `X` 内部带类体的 `struct Y { … }` 仍然定义了新的成员类 `X::Y`，不会补全外面的 `::Y`，Clang 照样报 `variable has incomplete type 'struct Y'`。在两种语言中都可行的改法是把 `Y` 的定义移到 `X` 外面，`X` 里只写 `struct Y y;`。

### typedef 名在类中被使用后不能重新声明

```cpp ifndr
typedef int I;
struct S {
  I i;
  int I;   // 合法的 C；C++ 中 IFNDR
};
```

¶5 C++ 中，一个 typedef 名在类定义中被使用之后，不能在同一个类里重新声明（[[class.member.lookup]]）。类变复杂时，允许这样的重新定义会让人搞不清 `I` 到底指什么。按当前草案 [[class.member.lookup#6]]，在类中查找 `I` 的结果若与在完整类语境中查找的结果不同，程序非良构，不要求诊断。Clang 对这段代码没有诊断。

## 预处理 {#diff.cpp}

¶1 `__STDC__` 是否预定义、值是什么，在 C++ 中由实现定义（[[cpp.predefined]]）。C++ 不等于 C，强制定义 `__STDC__` 等于要求编译器作出不真实的声明。用 `#ifdef __STDC__` 判断是否为标准 C 的头文件，在 C++ 中可能走另一个分支。Clang 在 C++ 模式下仍然把 `__STDC__` 定义为 1，判断 C++ 应该用 `__cplusplus`。

## 小结

下表按附录的原话汇总每条的改写难度和使用频率。可以自动完成的改动，编译器都会指出位置；语义变换需要理解代码后手工改写。

| 条目 | 改写难度 | 使用频率 |
|---|---|---|
| [lex] 新关键字 | 语法变换；改一大批相关程序更费工夫 | 常见 |
| [lex] `sizeof('x')` | 简单 | 依赖它的程序大概罕见 |
| [lex] 编码前缀冲突 | 语法变换 | 很少 |
| [lex] 字符串字面量 `const` | 语法变换（加强制转换） | 有正当理由修改字面量的程序大概罕见 |
| [basic] 暂定定义 | 语义变换 | 很少 |
| [basic] `struct` 作用域 | 语义变换 | 只有在外面引用嵌套名字时才察觉，大概罕见 |
| [basic] `const` 的内部链接 | 语义变换 | 很少 |
| [basic] 递归调用 `main` | 很简单 | 很少 |
| [basic] 兼容类型 | 语义变换 | 常见 |
| [expr] `void*` 转换 | 可自动完成 | 常见 |
| [expr] 枚举混合运算 | 编译器会诊断 | 不常见 |
| [expr] 枚举的算术转换 | 加显式转换 | 罕见 |
| [expr] `bool` 自减 | 附录未给出 | 附录未给出 |
| [expr] `&*p`、`&a[N]` | 语法变换 | 偶尔 |
| [expr] 表达式中定义类型 | 语法变换 | 很少 |
| [expr] 数组比较 | 编译器会诊断 | 罕见 |
| [expr] 左值结果 | 加显式转换 | 罕见 |
| [stmt] 跳过初始化 | 语义变换 | 很少 |
| [stmt] 不返回值 | 语义变换 | 很少 |
| [dcl] `void` 变量 | 语法变换 | 很少 |
| [dcl] 类型声明上的 `static` | 语法变换 | 很少 |
| [dcl] `register` | 语法变换 | 常见 |
| [dcl] typedef 与类同名 | 语义变换 | 很少 |
| [dcl] `const` 未初始化 | 语义变换 | 很少 |
| [dcl] `auto` 存储类 | 语法变换 | 罕见 |
| [dcl] 空形参表 | 语法变换 | 常见 |
| [dcl] 形参或返回类型中定义类型 | 语义变换 | 很少 |
| [dcl] K&R 函数定义 | 语法变换 | 旧程序中常见 |
| [dcl] 指派初始化 | 语法变换 | 乱序常见，其余很少 |
| [dcl] 字符数组放不下 `'\0'` | 语义变换 | 很少 |
| [dcl] 整数赋给枚举 | 语法变换 | 常见 |
| [dcl] 枚举项的类型 | 语义变换 | 很少 |
| [dcl] 对齐说明符的位置 | 语法变换 | 很少 |
| [class] 类名隐藏对象 | 语义变换 | 很少 |
| [class] 复制 `volatile` 对象 | 语义变换 | 很少 |
| [class] `int` 位域的符号 | 语法变换 | 很少 |
| [class] 嵌套类名 | 语义变换 | 很少 |
| [class] typedef 重新声明 | 语义变换 | 很少 |
| [cpp] `__STDC__` | 语义变换 | 相当常见 |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 [diff.iso.general] 说明这一节按本文档的章节列出 C++ 与 C 的差异，并且是在前面各节所列差异之外的部分。

</details>
