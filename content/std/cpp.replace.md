---
title: 宏替换
summary: 对象式宏与函数式宏的定义、重定义与调用；实参如何划分、何时先展开；__VA_ARGS__ 与 C++20 的 __VA_OPT__；# 字符串化与 ## 拼接的精确规则（含 placemarker）；宏定义的作用域与 #undef。重新扫描与"涂蓝"规则见 cpp.rescan。
status: draft
covers: cpp.replace.general, cpp.subst, cpp.stringize, cpp.concat, cpp.scope
related: cpp.rescan, cpp.pre, cpp.cond, cpp.import, cpp.predefined, lex.pptoken, lex.phases
tags: 预处理, 宏, 可变参数宏
updated: 2026-10-18
---

宏替换是预处理器的核心，也是 C++ 中**最不像 C++** 的部分：它不懂作用域、不懂类型、不懂表达式，只在**预处理记号**的层面做"查找—替换"。但它的规则比"文本替换"精确得多，而且有几处非常反直觉的地方：为什么要写 `xstr(s) str(s)` 两层？`glue(HIGH, LOW)` 为什么不展开 `LOW`？`F(,)` 有几个实参？`__VA_OPT__` 到底解决了什么？

本页覆盖 [[cpp.replace]] 的五个小节：概述（定义与调用）、实参替换、`#`、`##`、作用域。最后一步——**重新扫描与递归抑制**——单独成页：[[cpp.rescan]]。

前置知识：预处理记号（[[lex.pptoken]]），翻译阶段（[[lex.phases]]），什么是指令（[[cpp.pre]]）。

## 全景：一次函数式宏调用经历了什么

先给出完整的流水线，后文逐步展开：

```text
  F(arg1, arg2)
     │
     ├─① 识别调用、划分实参                      [cpp.replace.general] ¶13–¶16
     │
     ├─② 实参替换：对替换列表中的每个形参        [cpp.subst]
     │     · 是 # 的操作数        → 用实参原始记号（不展开），交给 #
     │     · 紧邻 ##               → 用实参原始记号（不展开），空实参变 placemarker
     │     · 其他                  → 用实参【完全宏展开】后的记号
     │     · __VA_OPT__(...)       → 视 __VA_ARGS__ 是否为空决定
     │
     ├─③ 执行 # （字符串化）                       [cpp.stringize]
     ├─④ 执行 ##（拼接）                           [cpp.concat]
     ├─⑤ 删除所有 placemarker                      [cpp.rescan] ¶1
     │
     └─⑥ 结果连同源文件后续记号一起重新扫描，      [cpp.rescan] ¶1–¶3
           正在被替换的宏名"涂蓝"、不再展开
```

对象式宏只经历 ④⑤⑥（它没有形参，但替换列表中可以有 `##`）。

## 宏的定义（cpp.replace.general）

### 重定义：必须"一模一样"（¶1–¶3）

¶1：两个替换列表**相同**当且仅当其中的预处理记号在**数量、顺序、拼写和空白分隔**上都相同，而所有空白分隔被视为相同——即"有没有空白"要一致，"有多少空白、是什么空白"无所谓。

¶2：已被定义为对象式宏的标识符可以被另一个 `#define` 重定义，前提是新定义也是对象式宏，且替换列表相同；否则非良构。函数式宏同理，另外要求形参的**个数和拼写**都相同。

¶3 的例子：

```cpp run title="redefine-ok.cpp" ok
#define OBJ_LIKE      (1-1)
#define OBJ_LIKE      /* whitespace */ (1-1) /* other */
#define FUNC_LIKE(a)   ( a )
#define FUNC_LIKE( a )(     /* note the whitespace */ \
                a /* other stuff on this line
                  */ )
int main() {}
```

注释在阶段 3 已经变成空格，所以前后注释、多个空格、跨行续行都不影响"相同"。但下面这些都是非良构：

```cpp title="redefine-bad.cpp" error
#define OBJ_LIKE    (1-1)
#define OBJ_LIKE    (0)         // 记号序列不同
#define OBJ_LIKE    (1 - 1)     // 空白不同：原来 1-1 之间没有空白
#define FUNC_LIKE(a) ( a )
#define FUNC_LIKE(b) ( a )      // 形参用法不同
#define FUNC_LIKE(b) ( b )      // 形参拼写不同——哪怕语义完全一样
```

!!! note "Clang 只给警告"
    Clang 对不兼容的重定义只给 `-Wmacro-redefined` **警告**，然后采用新定义。警告在标准意义上就是诊断，所以这符合"非良构必须诊断"的要求；但很多项目在不知不觉中依赖了"后定义覆盖前定义"——可移植的做法是先 `#undef`。

为什么要求"一模一样"而不是"语义等价"？因为同一个宏经常在多个头文件中重复定义（例如 `NULL` 曾经在好几个 C 头文件中各定义一次）。要求逐记号相同，既允许这种无害的重复，又能用最简单的比较发现真正的冲突。

### 对象式宏名后要有空白（¶4）

¶4：对象式宏的宏名与替换列表之间**必须**有空白。

```cpp
#define NOSPACE+1   // 违反 ¶4：宏名 NOSPACE，替换列表 +1，但中间没有空白
```

为什么？因为 `#define X(` 中的 `(` 前若无空白就是函数式宏（*lparen*）。要求对象式宏用空白分隔，是为了让 `#define X-1` 这种写法不会显得像 `#define X(1)` 那样有歧义。Clang 对此给出 `-Wc99-extensions` 警告（措辞是 "ISO C99 requires whitespace after the macro name"）。

### 实参个数（¶5）

¶5：若形参列表**不以** `...` 结尾，调用中实参的个数（**包括由零个记号构成的实参**）必须等于形参个数；否则实参个数**至少**等于形参个数（不计 `...`）。必须存在终结调用的 `)`。

"空实参也算一个实参"导致了几个初看奇怪的结论：

| 宏 | 调用 | 实参个数 | 合法吗 |
|---|---|---|---|
| `#define F0() x` | `F0()` | 0 | 是 |
| `#define F1(a) [a]` | `F1()` | **1**（一个空实参） | 是，展开为 `[]` |
| `#define F2(a,b) [a b]` | `F2(,)` | 2（两个空实参） | 是 |
| `#define F2(a,b) [a b]` | `F2()` | 1 | **否** |
| `#define V(a, ...) ...` | `V(1)` | 1 | 是（C++20 起） |

最后一行：C++17 及以前要求可变参数宏的实参个数**多于**具名形参个数，所以 `V(1)` 必须写成 `V(1,)`。C++20 放宽为"至少等于"，与 `__VA_OPT__` 配合使用。

### __VA_ARGS__ 和 __VA_OPT__ 的出现位置（¶6）

¶6：`__VA_ARGS__` 和 `__VA_OPT__` 只能出现在**使用了省略号的函数式宏**的替换列表中。在普通代码里写 `__VA_ARGS__` 非良构。

### 形参不能重名（¶7）

```cpp
#define G(x, x) x     // error: 形参在其作用域内必须唯一
```

### 宏名的名字空间（¶8）

¶8：紧跟 `define` 的标识符称为[[g:macro-name|宏名]]。宏名只有**一个**名字空间——没有作用域、没有重载：对象式宏 `X` 和函数式宏 `X` 不能共存，`#define` 一个已有的宏名就是重定义。替换列表前后的空白不属于替换列表。

### 禁止定义为宏的名字（¶9）

¶9：翻译单元不得 `#define` 或 `#undef` 与下列名字**拼写相同**的宏名：

- **关键字**（[[lex.key]]）；
- **表 4** 中具有特殊含义的标识符：`final`、`import`、`module`、`override`、`post`、`pre`（[[lex.name]]）；
- [[dcl.attr]] 中描述的**属性记号**：`noreturn`、`nodiscard`、`deprecated`、`fallthrough`、`assume` 等；

例外：`likely` 和 `unlikely` **可以**定义为**函数式**宏，也可以被 `#undef`。

```cpp title="reserved-macro-names.cpp" error
#define new  my_new      // error: 关键字
#define override         // error: 表 4
#define pre  1           // error: 表 4（C++26 契约中的 pre）
#define noreturn         // error: 属性记号
#define likely(x) __builtin_expect(!!(x), 1)   // OK：函数式宏形式的 likely 被特许
#define unlikely 0       // error: unlikely 只许定义为函数式宏
```

`likely`/`unlikely` 的特许是向现实妥协：Linux 内核等大量 C 代码早就定义了 `likely(x)`/`unlikely(x)` 宏。函数式宏只在后面紧跟 `(` 时才展开，而 `[[likely]]` 中 `likely` 后面是 `]`，所以二者互不干扰；但对象式宏 `#define likely` 会毁掉 `[[likely]]`。

注 1：替代记号（`and`、`bitor` 等，[[lex.digraph]]）不是标识符，所以根本**不可能**定义名为 `and` 的宏——`#define and &&` 的 `and` 不满足 `#define` 文法对 *identifier* 的要求。

!!! impl "实现现状"
    Clang 23 对 `#define new ...`、`#define override` 给 `-Wkeyword-macro` **警告**；对 `#define noreturn`、`#define pre 1`、`#define unlikely 0` **不给任何诊断**。所以在 Clang 上，这条规则只部分被检查。

另见 [[macro.names]]（标准库条款）：包含了标准库头文件的翻译单元，不得 `#define` 或 `#undef` 在任何标准库头文件中声明或定义的名字——例如不能 `#define move ...`。

### 指令名不被替换（¶10）

¶10：若在可以开始预处理指令的位置出现 `#` 后跟标识符，该标识符不受宏替换。这保证了 `#define include xxx` 之后 `#include` 仍然是 `#include`。

### 对象式宏（¶11–¶12）

¶11：`# define identifier replacement-list new-line` 定义[[g:object-like-macro|对象式宏]]：此后每个宏名的实例都被替换为替换列表，然后按 [[cpp.rescan]] 重新扫描。

脚注 117：到宏替换时，字符字面量和字符串字面量已经是完整的预处理记号，所以**不会**在其中寻找宏名或形参：

```cpp run title="no-expand-in-literal.cpp" ok
#define N 10
const char* s = "N";      // 仍是 "N"，不是 "10"
int main() { return s[0] == 'N' ? 0 : 1; }
```

（K&R C 之前的一些预处理器会在字符串里替换形参，这曾被用作"字符串化"的手段；标准 C 用 `#` 运算符取代了它。）

### 函数式宏与调用（¶13）

¶13：三种形式（`(identifier-list)`、`(...)`、`(identifier-list, ...)`）定义[[g:function-like-macro|函数式宏]]。此后每个"宏名后紧跟 `(` 作为**下一个预处理记号**"的实例开始一次**调用**；调用由配对的 `)` 终结，中间成对的括号被跳过。**调用内部的换行被视为普通空白**——所以一次调用可以跨很多行。

"下一个预处理记号是 `(`"是一个重要的开关：

```cpp
#define min(a, b) ((a) < (b) ? (a) : (b))
int x = min(1, 2);          // 展开
int y = (std::min)(1, 2);   // 不展开：min 后面是 )，不是 (
auto f = min;               // 不展开：函数式宏名单独出现时就是普通标识符
```

`(std::min)(a, b)` 是对付 `<windows.h>` 定义 `min`/`max` 宏的经典手法，原理就在这里。

### 实参的划分（¶14）

¶14：最外层配对括号之间的记号序列构成实参列表；实参之间用**逗号**分隔，但**内层配对圆括号**中的逗号不分隔实参。

注意：只有**圆括号**保护逗号。方括号、花括号、尖括号都不保护——预处理器不知道 `<` 是模板实参列表的开始：

```cpp
#define TWO(x, y) [x|y]
TWO({1,2})                   // → [{1|2}]           花括号不保护
TWO(std::map<int,int>)       // → [std::map<int|int>]  尖括号不保护
TWO((std::map<int,int>), z)  // → [(std::map<int,int>)|z]  圆括号保护
```

这是在宏里使用模板的经典痛点。常见对策：外加一层括号（若语境允许）、用类型别名 `using M = std::map<int,int>;`、或者把宏改成可变参数宏 `#define ONE(...) [__VA_ARGS__]`。

¶14 第二句：如果实参列表中有本来会作为预处理指令的记号序列（脚注 118：条件支持的指令也算），程序**非良构**（C++23 及以前是 UB）：

```cpp title="directive-in-args.cpp" error
#define M(a) a
int x = M(1
#ifdef BIG
  + 1000
#endif
);
```

Clang 对此只给 `-Wembedded-directive` 警告（措辞仍说 "has undefined behavior"），并实际执行了 `#ifdef`——GCC 也是如此。但 MSVC 的传统预处理器行为不同，这正是它当年被定为 UB 的原因。

### 经典的 max（¶15）

¶15 的例子 `#define max(a, b) ((a) > (b) ? (a) : (b))` 附带了一段难得的"规范内批评"：它会把某个实参**求值两次**（包括副作用），重复调用时生成的代码比函数多，而且**没有地址**（不能取地址）。括号确保实参与结果表达式的结合正确。

```cpp run title="max-double-eval.cpp" ok
#define max(a, b) ((a) > (b) ? (a) : (b))
int main() {
  int i = 1, j = 0;
  int m = max(i++, j);   // i++ 被求值两次：比较一次，作为结果再一次
  return (m == 2 && i == 3) ? 0 : 1;
}
```

### 可变参数（¶16）

¶16：若定义的 `)` 前紧跟 `...`，则尾部的实参（若有）**连同分隔它们的逗号**被合并为一个整体：[[g:variable-arguments|可变实参]]（*variable arguments*）。合并后的实参个数等于形参个数（不计 `...`）或比它多一。

即：`#define V(a, ...)` 调用 `V(1, 2, 3)` 时，`a` 对应 `1`，可变实参是 `2, 3`（含逗号）；`V(1)` 时没有可变实参。

## 实参替换（cpp.subst）

### 先展开，再代入（¶1）

¶1：实参确定后进行实参替换。替换列表中**既不在 `#` 或 `##` 之后、也不在 `##` 之前**的每个形参，被替换为：

- ¶1.1 若是 *va-opt-replacement*（`__VA_OPT__(...)`），见下文 ¶4；
- ¶1.2 否则，是对应实参**在所有宏都被展开之后**的记号。实参的记号被完全宏替换后再代入，**如同它们构成了预处理翻译单元的剩余部分、且后面再没有别的记号**。

这一句有两层意思。

**第一层：普通形参用的是展开后的实参；`#`/`##` 的操作数用的是原始实参。** 这是"两层宏"惯用法的根源：

```cpp run title="two-level.cpp" ok
#define str(x)  #x
#define xstr(x) str(x)
#define N 42
static_assert(__builtin_strlen(str(N)) == 1);    // "N"：# 的操作数不展开
static_assert(__builtin_strlen(xstr(N)) == 2);   // "42"：xstr 的 x 不是 # 的操作数，
                                                 //   先展开为 42，再交给 str
int main() {}
```

**第二层：实参的展开是"封闭"的。** "如同构成了翻译单元的剩余部分、且后面没有其他记号"意味着：实参中的函数式宏名如果在实参末尾，它**不能**从实参之外"借"一个 `(` 来完成调用。标准例 1：

```cpp
#define LPAREN() (
#define G(Q) 42
#define F(R, X, ...)  __VA_OPT__(G R X) )
int x = F(LPAREN(), 0, <:-);    // 替换为 int x = 42;
```

逐步看：实参 `R` = `LPAREN()`，完全展开为 `(`；`X` = `0`；可变实参 = `<:-`（非空）。`__VA_OPT__(G R X)` 代入后得到 `G ( 0`，再连同后面的 `)` 一起重新扫描，形成调用 `G(0)` → `42`。这里 `G` 和 `(` 是在**重新扫描**时才相遇的，而不是在展开实参时——实参 `LPAREN()` 本身展开出的 `(` 不会去找前面的东西。

### __VA_ARGS__（¶2–¶3）

¶2：替换列表中的 `__VA_ARGS__` 被当作一个形参，可变实参构成替换它的记号。

¶3 的例子：

```cpp
#define debug(...) fprintf(stderr, __VA_ARGS__)
#define showlist(...) puts(#__VA_ARGS__)
#define report(test, ...) ((test) ? puts(#test) : printf(__VA_ARGS__))
debug("Flag");                              // fprintf(stderr, "Flag");
debug("X = %d\n", x);                       // fprintf(stderr, "X = %d\n", x);
showlist(The first, second, and third items.);
                                            // puts("The first, second, and third items.");
report(x>y, "x is %d but y is %d", x, y);   // ((x>y) ? puts("x>y") : printf("x is %d but y is %d", x, y));
```

`showlist` 演示了 `#__VA_ARGS__`：可变实参中的逗号也被字符串化。

### __VA_OPT__：解决"多余的逗号"（¶4）

C++20 之前最臭名昭著的宏问题：

```cpp
#define LOG(fmt, ...) printf(fmt, __VA_ARGS__)
LOG("hi");          // → printf("hi", )     多余的逗号，语法错误
```

GCC 的扩展 `, ## __VA_ARGS__`（可变实参为空时吞掉前面的逗号）流行了多年，但它不标准、语义古怪。C++20 的 `__VA_OPT__`（[[P0306R4]]，措辞在 [[P1042R1]] 中修订）给出了干净的方案：

```cpp
#define LOG(fmt, ...) printf(fmt __VA_OPT__(,) __VA_ARGS__)
LOG("hi");          // → printf("hi" )
LOG("%d", 1);       // → printf("%d" , 1)
```

¶4 的精确规则：

1. `__VA_OPT__` 只能以 `__VA_OPT__ ( pp-tokens(opt) )` 的形式出现；它的 `)` 通过跳过内部配对括号确定。
2. 括号中**不得**再含 `__VA_OPT__`（不能嵌套）。
3. 若括号中的记号作为当前宏的替换列表是非良构的（例如以 `##` 开头），程序非良构。
4. *va-opt-replacement* 被当作一个**形参**，其对应"实参"定义为：
   - 若 `__VA_ARGS__`（作为既非 `#` 也非 `##` 操作数的替换结果）**由零个记号构成**——注意是**展开之后**为空——则为单个 **placemarker** 记号；
   - 否则，为括号内记号**作为当前宏的替换列表**进行展开的结果——即在其中做实参替换、`#`、`##`——但在删除 placemarker 和重新扫描**之前**。

注 1：placemarker 在字符串化之前被删除，也可能在重新扫描时被删除。

"展开之后为空"这一点很关键：

```cpp
#define F(...) f(0 __VA_OPT__(,) __VA_ARGS__)
#define EMP
F(EMP)      // → f(0)   可变实参是 EMP，展开后为空，所以 __VA_OPT__ 不产生逗号
```

标准例 3 逐个解读：

```cpp
#define F(...)           f(0 __VA_OPT__(,) __VA_ARGS__)
#define G(X, ...)        f(0, X __VA_OPT__(,) __VA_ARGS__)
#define SDEF(sname, ...) S sname __VA_OPT__(= { __VA_ARGS__ })
#define EMP

F(a, b, c)          // f(0, a, b, c)
F()                 // f(0)
F(EMP)              // f(0)

G(a, b, c)          // f(0, a, b, c)
G(a, )              // f(0, a)        可变实参是一个空实参 → 为空
G(a)                // f(0, a)        没有可变实参（C++20 起合法）

SDEF(foo);          // S foo;
SDEF(bar, 1, 2);    // S bar = { 1, 2 };
```

`SDEF` 展示了 `__VA_OPT__` 不只是用于逗号：任何"仅在有可变实参时才出现"的记号序列都可以。

接下来是与 `#`、`##` 交互的几个边角：

```cpp
#define H1(X, ...) X __VA_OPT__(##) __VA_ARGS__   // error: ## 不能出现在替换列表开头
```

`H1` 非良构：按第 3 条规则，`__VA_OPT__` 括号内的 `##` 作为"替换列表"时位于开头，违反 [[cpp.concat#1]]。

```cpp
#define H2(X, Y, ...) __VA_OPT__(X ## Y,) __VA_ARGS__
H2(a, b, c, d)      // ab, c, d
```

`H2`：`##` 在 `__VA_OPT__` 内部生效，拼出 `ab`。

```cpp
#define H3(X, ...) #__VA_OPT__(X##X X##X)
H3(, 0)             // ""
```

`H3`：`#` 可以作用于 `__VA_OPT__`（因为它被当作形参）。可变实参 `0` 非空，于是括号内容被展开：`X` 是空实参，在 `##` 旁边变成 placemarker，`X##X` 拼成 placemarker，两个 placemarker 之间的空白……最终 placemarker 在字符串化前被删除，字符串化一个空序列得到 `""`。

```cpp
#define H4(X, ...) __VA_OPT__(a X ## X) ## b
H4(, 1)             // a b
```

`H4`：`__VA_OPT__(...)` 整体作为 `##` 的左操作数。它的"实参"是 `a X ## X` 展开后的 `a <placemarker>`（placemarker 还没删）。然后 `<placemarker> ## b` → `b`。结果是 `a b`，而不是 `ab`——因为与 `b` 拼接的是 placemarker，不是 `a`。

```cpp
#define H5A(...) __VA_OPT__()/**/__VA_OPT__()
#define H5B(X) a ## X ## b
#define H5C(X) H5B(X)
H5C(H5A())          // ab
```

`H5`：`H5A()` 的可变实参为空，两个 `__VA_OPT__` 都变成 placemarker，最后被删除，`H5A()` 展开为**空**（中间的注释空白也随之无关）。于是 `H5B` 收到一个空实参，`a ## <placemarker> ## b` → `ab`。

!!! impl "实测"
    以上 `F`、`G`、`SDEF`、`H2`–`H5`、`LPAREN` 例子用 Clang 23 `-E` 全部得到与标准相同的结果。

## # 运算符：字符串化（cpp.stringize）

¶1：函数式宏替换列表中的每个 `#` 后面**必须**紧跟一个形参。（对象式宏中的 `#` 只是普通记号，没有这个约束。）

```cpp
#define S(a) #b     // error: # 后面不是形参
#define HASH #      // OK：对象式宏，# 只是一个普通记号
```

¶2 定义了字符串化：

- [[g:character-string-literal|字符串字面量]]（*character string literal*）指没有前缀的 *string-literal*。
- 若形参紧跟在 `#` 之后，二者被替换为**一个**字符串字面量预处理记号，内容是对应实参的记号序列（不含 placemarker）的拼写——即[[g:stringizing-argument|字符串化实参]]的拼写。
- 实参记号之间的**每处空白都变成一个空格**；首尾空白删除。
- 每个记号保持原始拼写，**除了**：在 *header-name*、字符字面量、字符串字面量（含首尾的 `"`）中，每个 `"` 和 `\` 前插入一个 `\`，每个换行字符替换为两字符序列 `\n`。
- 若结果不是合法的字符串字面量，非良构。
- 空实参得到 `""`。
- `#` 与 `##` 的求值顺序未指定。

```cpp
#define str(x) #x
str(  a   +    b  )        // "a + b"            空白规范化
str(a "\n" b)              // "a \"\\n\" b"      字面量内部的 " 和 \ 被转义
str('"')                   // "'\"'"
str()                      // ""
str(R"(line1
line2)")                   // "R\"(line1\nline2)\""   原始字符串中的真实换行变为 \n
```

最后一例展示了"换行替换为 `\n`"这条规则存在的意义：原始字符串字面量中可以有真实的换行字符，而普通字符串字面量里不可以，所以必须转写。

!!! lawyer "转义只发生在字面量内部"
    注意规则只说"字符字面量、字符串字面量、header-name **内部**"的 `"` 和 `\` 被转义。字面量**之外**的 `\` 是一个独立的预处理记号（"其他单个字符"类），不被转义。所以 `str(\)` 产生 `"\"`——不是合法的字符串字面量，非良构。Clang 23 对此只给 `invalid string literal, ignoring final '\'` 警告并产生 `""`。

!!! lawyer "空白的不确定性"
    [[lex.phases]] 阶段 3 中"非换行空白是保留还是压缩为一个空格"是未指定的，但对字符串化毫无影响：¶2 规定"每处空白"都变成**一个**空格。真正影响结果的只是**有无**空白——而有无空白在阶段 3 就确定了。所以 `str(a+b)` 一定是 `"a+b"`，`str(a + b)` 一定是 `"a + b"`。

## ## 运算符：记号拼接（cpp.concat）

### 不能在两端（¶1）

¶1：`##` 不得出现在任何一种宏的替换列表的开头或结尾——它需要左右两个操作数。

### 紧邻 ## 的形参不展开（¶2）

¶2：函数式宏的替换列表中，若形参紧邻 `##`（在前或在后），则形参被替换为对应实参的**原始记号序列**（不展开）；若实参由零个记号构成，则替换为一个 [[g:placemarker|placemarker]]（脚注 119：placemarker 不出现在文法中，只是阶段 4 内部的临时实体）。

### 拼接（¶3）

¶3：对于对象式和函数式宏调用，在重新扫描替换列表之前，替换列表中每个 `##`（**不是来自实参的**）被删除，其前一个记号与后一个记号**拼接**为一个记号。placemarker 的特殊规则：

- placemarker `##` placemarker → placemarker
- placemarker `##` X → X；X `##` placemarker → X

注 1：拼接可以形成 *universal-character-name*。若结果**不是合法的预处理记号**，程序非良构（C++23 及以前是 UB）。结果可以参与后续的宏替换。`##` 的求值顺序未指定。

```cpp
#define CAT(a, b) a ## b
CAT(x, 1)        // x1
CAT(+, =)        // +=
CAT(/, /)        // error: // 不是预处理记号（注释在阶段 3 就处理完了）
CAT(+, -)        // error: +- 不是一个预处理记号
CAT(., .)        // error: .. 不是（... 才是）
```

Clang 对后三者报错 `pasting formed '//', an invalid preprocessing token`。

"不是来自实参的"这个限定很重要：

```cpp
#define ID(x) x
#define F(x) [x]
F(a ## b)        // [a ## b]——## 来自实参，不是 F 的替换列表中的运算符
```

!!! lawyer "求值顺序未指定，何时有影响？"
    `a ## b ## c` 的拼接顺序是未指定的。大多数时候结果相同，但若中间结果不是合法记号就不同了：
    ```cpp
    #define cat3(a, b, c) a ## b ## c
    cat3(-, >, *)   // 从左到右：-> 再 ->*，合法；从右到左：>* 不是记号，非良构
    ```
    Clang 23 从左到右处理，得到 `->*`。可移植代码应保证任何拼接顺序下的中间结果都合法。

### 标准例 1：两层宏的全部奥秘（¶4）

```cpp
#define str(s)      # s
#define xstr(s)     str(s)
#define debug(s, t) printf("x" # s "= %d, x" # t "= %s", \
               x ## s, x ## t)
#define INCFILE(n)  vers ## n
#define glue(a, b)  a ## b
#define xglue(a, b) glue(a, b)
#define HIGHLOW     "hello"
#define LOW         LOW ", world"

debug(1, 2);
fputs(str(strncmp("abc\0d", "abc", '\4')        // this goes away
    == 0) str(: @\n), s);
#include xstr(INCFILE(2).h)
glue(HIGH, LOW);
xglue(HIGH, LOW)
```

结果：

```cpp
printf("x" "1" "= %d, x" "2" "= %s", x1, x2);
fputs("strncmp(\"abc\\0d\", \"abc\", '\\4') == 0" ": @\n", s);
#include "vers2.h"      // 宏替换之后、访问文件之前
"hello";
"hello" ", world"
```

逐行拆解：

- `debug(1, 2)`：`# s` → `"1"`，`x ## s` → `x1`。阶段 6 再把相邻的字符串字面量拼接成 `"x1= %d, x2= %s"`。
- `fputs(str(...) str(: @\n), s)`：实参跨行，行尾注释在阶段 3 已变成空格，所以"this goes away"。字符串化时 `"abc\0d"` 中的 `"` 和 `\` 被转义。第二个 `str(: @\n)` 中 `@`、`\`、`n` 都不在字面量内部，原样保留：结果是 `": @\n"`——它在阶段 7 里恰好又是一个合法的含换行转义的字符串。
- `#include xstr(INCFILE(2).h)`：`xstr` 的实参先完全展开，`INCFILE(2)` → `vers2`，于是得到 `vers2.h`；再交给 `str` 字符串化为 `"vers2.h"`。这正是 [[cpp.include#7]] 宏形式的典型用法。
- `glue(HIGH, LOW)`：`a`、`b` 紧邻 `##`，**不展开**，直接拼成 `HIGHLOW`，重新扫描时 `HIGHLOW` 是宏，得到 `"hello"`。
- `xglue(HIGH, LOW)`：`xglue` 的 `a`、`b` 不紧邻 `##`，**先展开**：`HIGH` 不是宏，保持；`LOW` 展开为 `LOW ", world"`——其中的 `LOW` 在自身的展开中被"涂蓝"（[[cpp.rescan#3]]），不再展开。于是 `glue(HIGH, LOW ", world")` → `HIGHLOW ", world"` → `"hello" ", world"`。

!!! note "空格可选"
    例子末尾说明：宏定义中 `#`、`##` 周围的空白是可选的。`# s` 和 `#s`、`a ## b` 和 `a##b` 等价。

### 标准例 2：造出来的 ## 不是运算符（¶5）

```cpp
#define hash_hash # ## #
#define mkstr(a) # a
#define in_between(a) mkstr(a)
#define join(c, d) in_between(c hash_hash d)
char p[] = join(x, y);          // 等价于 char p[] = "x ## y";
```

各阶段：

```text
join(x, y)
in_between(x hash_hash y)
in_between(x ## y)        ← 此处的 ## 是拼接出来的新记号
mkstr(x ## y)
"x ## y"
```

`hash_hash` 的替换列表 `# ## #` 中，中间的 `##` 是运算符，把两个 `#` 拼成一个 `##` **记号**。但这个新记号**不是** `##` 运算符——¶3 只处理"替换列表中、不是来自实参的" `##`。它作为 `in_between` 的实参一部分传下去，最终被原样字符串化。

### 标准例 3：placemarker（¶6）

```cpp
#define t(x,y,z) x ## y ## z
int j[] = { t(1,2,3), t(,4,5), t(6,,7), t(8,9,),
  t(10,,), t(,11,), t(,,12), t(,,) };
// → int j[] = { 123, 45, 67, 89, 10, 11, 12, };
```

`t(,,)` 的三个空实参都变成 placemarker，拼接后仍是 placemarker，最后被删除——什么也不剩，所以数组初始化器以 `12, ` 结尾，留下一个合法的尾逗号。

没有 placemarker 概念的话，`t(6,,7)` 中 `6 ## <空> ## 7` 就要讨论"和空的东西拼接"是什么意思。placemarker 是 C99 为此引入的一个形式化技巧：用一个"看不见的记号"占位，让每个 `##` 都有两个操作数。

!!! impl "实测"
    以上三个标准例子，Clang 23 `-E` 的输出与标准逐字一致（除空白外）。

## 宏定义的作用域（cpp.scope）

¶1：宏定义从定义处一直持续（**与块结构无关**），直到遇到对应的 `#undef`，或（若没有）直到翻译单元结束。阶段 4 之后宏定义**没有任何意义**。

¶2：`# undef identifier new-line` 使该标识符不再被定义为宏名。若它本来就没有被定义为宏名，指令被忽略（不是错误）。

```cpp run title="macro-scope.cpp" ok
void f() {
#define LOCAL 1          // 并不是"局部"的
}
namespace n {
  int g() { return LOCAL; }   // 照样可见：宏无视作用域与名字空间
}
#undef LOCAL
#undef NEVER_DEFINED     // OK：被忽略
int main() { return n::g() - 1; }
```

"阶段 4 之后没有意义"意味着：调试器看不到宏（除非编译器额外记录，如 GCC/Clang 的 `-g3`），宏不能被导出到命名模块（[[cpp.import]]），宏不参与链接，也不参与 ODR——两个翻译单元可以给同一个宏名完全不同的定义。但如果宏影响了某个 `inline` 函数或类定义的记号序列，两个 TU 中该定义的记号不同就违反了 ODR（[[basic.def.odr]]），这是 IFNDR。

!!! tip "push_macro / pop_macro"
    需要临时改写一个宏、之后恢复原定义时，标准没有提供机制。GCC、Clang、MSVC 都支持 `#pragma push_macro("X")` / `#pragma pop_macro("X")`（实现定义的 pragma，见 [[cpp.pragma]]）。

另外，[[cpp.predefined#4]] 禁止 `#define`/`#undef` 预定义宏名和 `defined`。

## 陷阱

!!! pitfall "多语句宏与 do { } while (0)"
    ```cpp
    #define SWAP(a, b) tmp = a; a = b; b = tmp
    if (x > y) SWAP(x, y);    // 只有第一条语句受 if 控制！
    ```
    惯用写法是 `#define SWAP(a, b) do { auto t = a; a = b; b = t; } while (0)`：它是**一条**语句，且要求调用处加分号，与函数调用的手感一致。

!!! pitfall "实参周围不加括号"
    ```cpp
    #define SQ(x) x * x
    SQ(1 + 2)     // → 1 + 2 * 1 + 2 == 5
    ```
    宏只做记号替换，不尊重优先级。替换列表中每个形参、以及整个替换列表，都应当加括号。

!!! pitfall "宏实参中的模板逗号"
    `ASSERT(std::is_same_v<A, B>)` 会被划分为两个实参。用额外的圆括号：`ASSERT((std::is_same_v<A, B>))`。

## 历史与演进

!!! history
    - **C++98**：对象式与函数式宏、`#`、`##`，与 C89 一致。空实参的行为在 C89/C++98 中是 UB。
    - **C++11**：与 C99 同步（[[N1653]]）：可变参数宏与 `__VA_ARGS__`、空宏实参、placemarker 规则。
    - **C++20**：`__VA_OPT__`（[[P0306R4]]，[[P1042R1]] 修订措辞）；可变参数宏允许省略全部可变实参（`G(a)`）。
    - **C++26 及当前草案**：多处 UB 改为非良构——`##` 拼出无效记号、宏实参中出现指令、字符串化结果不是合法字符串字面量等。

## 思考题

!!! question "思考题 1"
    下面各调用分别展开为什么？
    ```cpp
    #define F(x, ...) f(x __VA_OPT__(,) __VA_ARGS__)
    #define E
    F(1)
    F(1,)
    F(1, E)
    F(1, E E, )
    F(, 2)
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

- `F(1)` → `f(1 )`：没有可变实参（C++20 起合法）。
- `F(1,)` → `f(1 )`：可变实参是一个空实参，`__VA_ARGS__` 为空。
- `F(1, E)` → `f(1 )`：`__VA_ARGS__` 展开**之后**为空（[[cpp.subst#4]] 判断的是替换结果）。
- `F(1, E E, )` → `f(1 , ,)`：可变实参是 `E E, `，展开后为 `,`——一个逗号，非空！所以 `__VA_OPT__(,)` 产生逗号，结果是 `f(1 , ,)`。可变实参中的逗号是可变实参的一部分（[[cpp.replace.general#16]]）。
- `F(, 2)` → `f( , 2)`：`x` 为空，可变实参 `2`。

以上结果均经 Clang 23 `-E` 验证。
</details>

!!! question "思考题 2"
    为什么 `glue(HIGH, LOW)` 得到 `"hello"`，而 `xglue(HIGH, LOW)` 得到 `"hello" ", world"`？如果把 `LOW` 的定义改成 `#define LOW "!"`，`xglue(HIGH, LOW)` 又会怎样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前两问见上文 ¶4 的拆解：`glue` 的形参紧邻 `##`，实参不展开，直接拼成 `HIGHLOW`；`xglue` 的形参不紧邻 `##`，实参先完全展开（`LOW` → `LOW ", world"`，内部的 `LOW` 被涂蓝），然后 `glue` 拼接的是 `HIGH` 和**被涂蓝的** `LOW`，得到 `HIGHLOW`——这是一个**新**记号，不是被涂蓝的，所以重新扫描时展开为 `"hello"`；后面跟着 `", world"`。

若 `#define LOW "!"`，`xglue(HIGH, LOW)` 先把 `LOW` 展开为 `"!"`，然后 `glue(HIGH, "!")` 要拼接 `HIGH` 和 `"!"`，得到 `HIGH"!"`——这不是一个合法的预处理记号（标识符后跟引号不构成任何一种记号；`HIGH` 也不是合法的字符串前缀），程序非良构。Clang 23 报 `pasting formed 'HIGH"!"', an invalid preprocessing token`。
</details>

!!! question "思考题 3"
    `#define EMPTY` 之后，`#define F(x) #x` 的 `F(EMPTY)` 是 `""` 还是 `"EMPTY"`？`#define G(x) F(x)` 的 `G(EMPTY)` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`F(EMPTY)` 是 `"EMPTY"`：`#` 的操作数用原始实参，不展开。`G(EMPTY)` 是 `""`：`G` 的 `x` 不是 `#` 的操作数，实参先完全展开为空，`F()` 收到一个空实参，字符串化为 `""`（[[cpp.stringize#2]]：空实参得到 `""`）。
</details>

## 小结

!!! summary
    - 重定义必须逐记号相同（空白只看有无）；函数式宏还要求形参个数与拼写相同。
    - 空实参也算实参：`F()` 对单形参宏有一个空实参。只有**圆括号**保护实参中的逗号。
    - 不得定义关键字、`final`/`override`/`import`/`module`/`pre`/`post`、标准属性名为宏；`likely`/`unlikely` 仅可作函数式宏。
    - 实参在代入前**完全展开**，除非它是 `#` 或 `##` 的操作数——这就是"两层宏"惯用法的原理。
    - `__VA_OPT__(x)`：`__VA_ARGS__` 展开后非空才产生 `x`。
    - `#`：空白规范化为单个空格，字面量内的 `"` `\` 被转义，换行变 `\n`；结果非法则非良构。
    - `##`：拼不出合法记号则非良构（C++23 前为 UB）；空实参变 placemarker；拼出的 `##` 记号不是运算符。
    - 宏定义无视块结构，持续到 `#undef` 或 TU 结束；阶段 4 之后不复存在。
