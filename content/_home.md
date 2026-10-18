## 这个网站怎么读

C++ 标准是写给编译器作者和委员会成员的**规格说明**，不是写给普通程序员的教材：定义先于使用，一条规则的各个部分散落在多个条款里，例子往往只有一行 `// error`，既不解释为什么错，也不说怎么改。

这里的每一页都对应标准中的一个条款（用 **stable name** 标识，如 `[basic.life]`），在原文结构之上补三样东西：

- **释义**：把规范性文字讲成人话，并标出它的精确边界。段落号 ¶ 与草案一致，随时可以对照 eel.is 原文。
- **上下文**：这条规则为什么存在、解决了什么问题（比如不这样限制，编译器的哪些优化就无法成立）、和哪些条款联动、历史上怎么演变过来的。
- **例子**：每个例子都标注判定（✓ 良构 / ✗ 非良构 / ☠ UB …），大多数可以一键在 Compiler Explorer 里运行。

## 建议的阅读路线

标准不必从第一页顺序读下去。下面几条路线按主题组织，可以按需要选读。

### 1. 基本词汇

如果分不清未定义行为、未指明行为和编译错误，先从这里开始——这是 language lawyer 的基本词汇：

- [[topics/how-to-read-the-standard|专题：如何阅读 C++ 标准]]：stable name、段落号、提案与 DR 的演进、查证的方法；
- [[intro.defs|术语与定义]] 和 [[intro.compliance|实现合规性]]：弄清 UB、unspecified、implementation-defined、ill-formed、IFNDR 的区别，以及 C++26 新增的 erroneous behavior。

### 2. 对象与生命周期

placement new、存储复用，以及为什么在旧对象的存储上构造新对象后，有时需要 `std::launder` 才能通过旧指针访问新对象：

- [[basic.def.odr|ODR]] → [[intro.object|对象模型]] → [[basic.life|生命周期]] → [[basic.stc|存储期]] → [[class.temporary|临时对象]]。

### 3. 表达式

为什么具名的右值引用是左值、各种隐式转换做了什么、表达式中各部分的求值先后：

- [[topics/value-categories|专题：值类别]] → [[basic.lval|值类别]] → [[conv|标准转换]] → [[expr.arith.conv|寻常算术转换]] → [[intro.execution|求值顺序]]。

### 4. 名字

编译器为什么找不到某个名字、为什么报歧义：

- [[basic.scope|作用域]] → [[basic.lookup|名字查找]] → [[basic.lookup.argdep|实参依赖查找（ADL）]] → [[basic.link|链接]]。

### 5. 之后

- **初始化**：[[topics/initialization|专题：初始化]] 与 [[dcl.init]]；
- **重载决议**：[[topics/overload-resolution-walkthrough|专题：重载决议推演]] 与 [[over.match]]；
- **模板**：[[topics/two-phase-lookup|专题：两阶段查找]]、[[temp.res]]、[[temp.dep]]、[[temp.deduct]]；
- **常量求值与编译期编程**：[[topics/compile-time-programming|专题：编译期编程]] 与 [[expr.const]]。

---

侧栏里加粗、带朱点的条款已有笔记；灰色条款点击后直接跳到 eel.is 原文。按 <kbd>/</kbd> 可以随时按 stable name 或关键词搜索。
