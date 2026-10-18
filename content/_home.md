## 这个网站怎么读

标准本身是写给编译器作者的：定义先于使用，规则散落各处，例子往往只有一行 `// error`。这里的每一页都对应标准中的一个条款（用 **stable name** 标识，如 `[basic.life]`），在原文结构之上补三样东西：

- **释义**：把规范性文字讲成人话，并标出它的精确边界。段落号 ¶ 与草案一致，随时可以对照 eel.is 原文。
- **上下文**：这条规则为什么存在、解决了什么问题、和哪些条款联动、历史上怎么演变过来的。
- **例子**：每个例子都标注判定（✓ 良构 / ✗ 非良构 / ☠ UB …），大多数可以一键在 Compiler Explorer 里运行。

## 建议的阅读路线

**第一站**：先读 [[intro.defs|术语与定义]] 和 [[intro.compliance|实现合规性]]，弄清 UB、unspecified、implementation-defined、ill-formed、IFNDR 的区别——这是 language lawyer 的基本词汇。

**对象与生命周期**：[[basic.def.odr|ODR]] → [[intro.object|对象模型]] → [[basic.life|生命周期]] → [[basic.stc|存储期]] → [[class.temporary|临时对象]]。

**表达式**：[[basic.lval|值类别]] → [[conv|标准转换]] → [[expr.arith.conv|寻常算术转换]] → [[intro.execution|求值顺序]]。

**名字**：[[basic.scope|作用域]] → [[basic.lookup|名字查找]] → [[basic.lookup.argdep|ADL]] → [[basic.link|链接]]。

**之后**：初始化（[[dcl.init]]）、重载决议（[[over.match]]）、模板（[[temp.res]]、[[temp.deduct]]）、常量求值（[[expr.const]]）。

侧栏里加粗、带朱点的条款已有笔记；灰色条款点击后直接跳到 eel.is 原文。按 <kbd>/</kbd> 可以随时按 stable name 或关键词搜索。
