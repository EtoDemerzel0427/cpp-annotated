---
title: Core language undefined behavior (Annex F)
summary: The informative Annex F catalogs the 80 kinds of undefined behavior stated explicitly in the core language text, each with a stable name; this page explains what it includes and excludes, how to use it to find rules, and summarizes whether each entry can be caught by a sanitizer or by constant evaluation on Clang 23.
updated: 2026-10-19
---

!!! tldr
    - Annex F collects the undefined behavior stated explicitly in Clauses 4 to 15 (the core language) with wording such as the behavior is undefined: 80 entries, each with a stable name of the form `[ub:…]`.
    - It does not include implicit UB, standard library UB, erroneous behavior or IFNDR. Not finding something in the annex does not mean it is not UB.
    - The annex is informative and creates no rules, and a few of its examples are even wrong. Base judgments and citations on the paragraphs of the main text.
    - Constant evaluation is the only means the standard guarantees will detect core language UB, and its scope of checking is the same as Annex F's scope.
    - Run-time tools each cover one category: UBSan covers arithmetic and invalid values, ASan covers memory, TSan covers data races; most UB at the level of the object model cannot be detected.

**Undefined behavior** (UB, [[defns.undefined]]) is behavior for which the standard imposes no requirements. In the main text such rules are scattered across more than a thousand pages; Annex F collects the ones stated explicitly in the core language part into a catalog. Each entry has a stable name, such as `[ub:expr.add.out.of.bounds]`, plus a link back to the main text, a one-sentence summary and an example. These stable names carry the `ub:` prefix and form a separate namespace from the stable names of the main text: `[ub:expr.add.out.of.bounds]` is not a subclause of [[expr.add]].

The entry-by-entry analysis is on seven sub-pages; each entry gives the source in the main text, an example rewritten so that it compiles, and test results for sanitizers and constant evaluation on Clang 23:

| Subclause | Page | Entries | Main topics |
|---|---|---|---|
| F.2 | [[ub.basic]] | 22 | implicit object creation, lifetime, indeterminate values, invalid pointers, unsequenced modifications, data races, forward progress, static destruction |
| F.3 | [[ub.expr]] | 34 | overflow, division by zero, strict aliasing, out-of-range conversions, wrong downcasts, out-of-bounds pointers, mismatched new and delete, shifts |
| F.4 | [[ub.stmt]] | 3 | flowing off the end of a non-void function, flowing off the end of a coroutine, recursive initialization of a static local variable |
| F.5 | [[ub.dcl]] | 9 | modifying const objects, volatile, reference binding, coroutine resume and destroy, `[[assume]]`, `[[noreturn]]` |
| F.6 | [[ub.class]] | 10 | double destruction, pure virtual calls during construction and destruction, member access, virtual calls, `typeid`, `dynamic_cast` |
| F.7 | [[ub.temp]] | 1 | infinite recursion in template instantiation |
| F.8 | [[ub.except]] | 1 | accessing members in the handler of a constructor's or destructor's function-try-block |

## Scope ([ub.general])

¶1 Annex F collects undefined behavior stated explicitly in [intro] through [cpp] (Clauses 4 to 15, i.e. the whole core language) using one of the following phrasings:

- ¶1.1–¶1.3 *is undefined*, *the behavior is undefined*, *the behavior of the program is undefined*;
- ¶1.4–¶1.7 *has undefined behavior*, *have undefined behavior*, *result has undefined behavior*, *results in undefined behavior*.

Each entry contains a title, a cross-reference, a summary of the situation and example code. The example is only one way to trigger the UB and is not meant to be exhaustive. The 80 entries are distributed by clause as: [basic] 22, [expr] 34, [stmt] 3, [dcl] 9, [class] 10, [temp] 1, [except] 1. The four clauses [lex], [module], [over] and [cpp] have no entries; violations there are either ill-formed or IFNDR (ill-formed, no diagnostic required, see [[ifndr]]).

The following categories are not in the annex but deserve the same caution:

- **Implicit UB**. ¶1 says explicitly that implicit undefined behavior is out of scope. Per [[defns.undefined]], behavior for which the standard gives no definition is also UB; there is no sentence to cite for such UB, so it cannot be cataloged.
- **Standard library UB**. The scope ends at [cpp], so precondition violations in Clauses 16 to 33 (such as an out-of-range `std::vector::operator[]`) are not included.
- **Erroneous behavior** (EB). EB is defined behavior that the standard merely considers an error. The only place the annex mentions it is F.2.14: reading an indeterminate value is UB, reading an erroneous value is not.
- **IFNDR**. When a no-diagnostic-required rule is violated, the standard also imposes no requirements on the whole program, but these have their own catalog, Annex G ([[ifndr]]).

## Relation between the annex and the main text

Annex F, and Annex G which catalogs IFNDR, were both added to the working draft after C++23; the cataloging work comes from proposal [[P1705]]. Annex F is an informative annex and creates no rules. Whether a behavior is UB is decided by the main text; where the two conflict, the main text governs, and citations should cite paragraphs of the main text.

You can navigate in both directions. The main text adds a marker pointing into the annex after every place it states UB explicitly, as in this sentence from [[basic.life#7]]:

> the pointer is used as the operand of a *delete-expression* ([ub:lifetime.outside.pointer.delete]),

The Specified in field of the annex entry links back to the main text. So searching a subclause of the main text for `[ub:` lists all of that subclause's explicit UB.

The annex may contain errors and should be read against the main text. The current draft has the following (details on the sub-pages):

- The summary of F.2.4 still has the old wording, applying only to class types with non-trivial destructors; the current main text [[basic.life#7.1]] has dropped that restriction (see [[ub.basic#lifetime.outside.pointer.delete]]).
- The summary of F.2.17 says both indirection through and calling a deallocation function with an invalid pointer are UB; the current main text [[basic.compound#6.1]] lists only indirection as UB, and the double-free problem is handled by the preconditions of `operator delete` (see [[ub.basic#basic.compound.invalid.pointer]]).
- The summaries and examples of F.3.22 and F.3.23 are swapped. The main text [[expr.delete#2]] attaches `[ub:expr.delete.mismatch]` to the sentence about single-object delete, but the annex's example uses `delete[]` on the result of a single-object new (see [[ub.expr#expr.delete.mismatch]]).
- The example of F.5.5 actually has no UB. `int& ir1 = i3;` is constant initialization and completes before the dynamic initialization of `int i2 = ir1;` (see [[ub.dcl#dcl.ref.uninitialized.reference]]).
- The example of F.5.7 does not demonstrate its title. When `destroy()` is called in `current_value()`, the coroutine is suspended; the example's real problem is access after destruction.
- A comment in the example of F.3.28 says that `1.0 / 0.0` is not UB on floating-point systems that can represent infinity, but the main text [[expr.mul#4]] makes a zero divisor UB with no such exception.
- The example of F.2.3 writes `new (&s+1) S()`. `&s + 1` points past the whole array, which does not match the comment's offset of 1 byte; it should be `s + 1`.
- Example 1 of F.3.21 replaces the placement form of `operator new`, which the standard says is not replaceable ([[new.delete.placement]]).

## How to find these UB

### Constant evaluation

```cpp error
constexpr int f(int d) { return 1 / d; }
constexpr int x = f(0);  // error: not a constant expression (note: division by zero)
```

[[expr.const.core#2.8]] says that an expression that would evaluate an operation with undefined or erroneous behavior as specified in [intro] through [cpp] is not a core constant expression. This scope is exactly the same as Annex F's scope. So putting suspect code into the initializer of a `constexpr` variable or a `static_assert` is the only means at the level of the standard that is guaranteed to diagnose core language UB.

There are two exceptions:

- **Runtime-undefined behavior** ([[g:runtime-undefined-behavior]]). [[expr.const.core#3]] says that when an evaluation is problematic only because of such behavior, whether the expression is a core constant expression is implementation-defined. Two entries in Annex F fall into this category: an `[[assume]]` assumption that is false (F.5.8, Clang rejects), and a `[[noreturn]]` function that returns (F.5.9, Clang accepts).
- **Standard library UB**. [[expr.const.core#4]] says that when an evaluation would have UB specified in the library clauses, it is unspecified whether the expression is a constant expression. This mirrors Annex F not including library UB.

Implementations also miss things. For `constexpr int f(int i) { i = i++ + i; return i; }`, Clang 23 only gives a `-Wunsequenced` warning, and constant evaluation computes a result for `f(1)` anyway, although by the standard it is not a constant expression. So passing constexpr does not prove the absence of UB.

### Sanitizers

Run-time UB can only be caught by tools when they hit it on some execution path. The table below summarizes our tests (Clang 23.1.3, arm64 macOS) and can be used to estimate whether a kind of UB can be caught:

| Tool | Flag | Entries it catches |
|---|---|---|
| UBSan | `-fsanitize=undefined` | signed overflow, division by zero, `INT_MIN / -1`, out-of-range shifts, floating-to-integer conversion out of range, invalid values of `bool` and enumerations, null pointer dereference, misaligned construction, calls through an incompatible function type, flowing off the end of a non-void function, false `[[assume]]`, returning `[[noreturn]]` functions, placement new yielding a null pointer |
| UBSan vptr | `-fsanitize=vptr` (not in the default `undefined` set on this platform) | wrong downcasts of polymorphic types, taking the address of a virtual base member before it is constructed |
| ASan | `-fsanitize=address` | use after free, double free, out-of-bounds access, calling `free` on a wrong address, and out-of-bounds reads and writes caused by many kinds of type-related UB |
| ASan option | `ASAN_OPTIONS=alloc_dealloc_mismatch=1` (off by default on macOS) | mismatched forms of `new` and `delete[]` |
| TSan | `-fsanitize=thread` | data races |
| TySan | `-fsanitize=type` | strict aliasing violations |

Almost no UB at the object-model level can be caught: implicit creation having no solution, pointers and glvalues outside lifetime, copying of unions, dissimilar types in member access, dissimilar types in pointer arithmetic, and the various restrictions during construction and destruction. They leave no detectable trace at run time. MSan (which detects uninitialized reads) does not support macOS and was not tested for this page.

### Compiler warnings

Some UB can be seen statically at compile time: `-Wreturn-type` (F.4.1, F.4.2), `-Wunsequenced` (F.2.18), `-Wmismatched-new-delete` (F.3.22, F.3.23), `-Winvalid-noreturn` (F.5.9), `-Wcall-to-pure-virtual-from-ctor-dtor` (F.6.2). They can only be warnings, because the program itself is well-formed: UB is a property of an execution and only happens when execution reaches it.

## All entries

The Tested column summarizes the results on Clang 23: it lists the tools that find the problem; constant evaluation means the same operation is rejected during constant evaluation; none means neither ASan nor UBSan reported anything at run time. See each entry for the specific output.


### F.2 [basic]

| Entry | Gist | Main text | Tested |
|---|---|---|---|
| [[ub.basic#intro.object.implicit.create\|intro.object.implicit.create]] | implicit object creation has no solution | [[intro.object#13]] | none |
| [[ub.basic#intro.object.implicit.pointer\|intro.object.implicit.pointer]] | no suitable created object | [[intro.object#14]] | none |
| [[ub.basic#basic.align.object.alignment\|basic.align.object.alignment]] | creating an object in misaligned storage | [[basic.align#1]] | UBSan |
| [[ub.basic#lifetime.outside.pointer.delete\|lifetime.outside.pointer.delete]] | deleting an object whose lifetime has ended | [[basic.life#7.1]] | none |
| [[ub.basic#lifetime.outside.pointer.member\|lifetime.outside.pointer.member]] | accessing a member through such a pointer | [[basic.life#7.2]] | constant evaluation |
| [[ub.basic#lifetime.outside.pointer.virtual\|lifetime.outside.pointer.virtual]] | converting such a pointer to a virtual base pointer | [[basic.life#7.3]] | none |
| [[ub.basic#lifetime.outside.pointer.dynamic.cast\|lifetime.outside.pointer.dynamic.cast]] | `dynamic_cast` on such a pointer | [[basic.life#7.4]] | none |
| [[ub.basic#lifetime.outside.glvalue.access\|lifetime.outside.glvalue.access]] | accessing an object through such a glvalue | [[basic.life#8.1]] | constant evaluation |
| [[ub.basic#lifetime.outside.glvalue.member\|lifetime.outside.glvalue.member]] | calling a member function through such a glvalue | [[basic.life#8.2]] | none |
| [[ub.basic#lifetime.outside.glvalue.virtual\|lifetime.outside.glvalue.virtual]] | binding such a glvalue to a virtual base reference | [[basic.life#8.3]] | none |
| [[ub.basic#lifetime.outside.glvalue.dynamic.cast\|lifetime.outside.glvalue.dynamic.cast]] | `dynamic_cast`/`typeid` on such a glvalue | [[basic.life#8.4]] | none |
| [[ub.basic#original.type.implicit.destructor\|original.type.implicit.destructor]] | storage holds a different type at implicit destruction | [[basic.life#11]] | none |
| [[ub.basic#creating.within.const.complete.obj\|creating.within.const.complete.obj]] | creating an object in the storage of a const complete object | [[basic.life#12]] | — |
| [[ub.basic#basic.indet.value\|basic.indet.value]] | evaluation produces an indeterminate value | [[basic.indet#2]] | constant evaluation |
| [[ub.basic#basic.stc.alloc.dealloc.constraint\|basic.stc.alloc.dealloc.constraint]] | replaced allocation/deallocation function violates its contract | [[basic.stc.dynamic.general#3]] | ASan (indirectly) |
| [[ub.basic#basic.stc.alloc.zero.dereference\|basic.stc.alloc.zero.dereference]] | dereferencing the result of a zero-byte allocation | [[basic.stc.dynamic.allocation#2]] | ASan |
| [[ub.basic#basic.compound.invalid.pointer\|basic.compound.invalid.pointer]] | indirection through an invalid pointer | [[basic.compound#6.1]] | ASan, constant evaluation |
| [[ub.basic#intro.execution.unsequenced.modification\|intro.execution.unsequenced.modification]] | unsequenced side effects | [[intro.execution#10]] | `-Wunsequenced` only |
| [[ub.basic#intro.races.data\|intro.races.data]] | data race | [[intro.races#17]] | TSan |
| [[ub.basic#intro.progress.stops\|intro.progress.stops]] | a thread stops making progress | [[intro.progress#1]] | none (`-O2` emits a trap instruction) |
| [[ub.basic#basic.start.main.exit.during.destruction\|basic.start.main.exit.during.destruction]] | calling `std::exit` during static destruction | [[basic.start.main#4]] | none |
| [[ub.basic#basic.start.term.use.after.destruction\|basic.start.term.use.after.destruction]] | using a destroyed block-scope static variable | [[basic.start.term#5]] | none |

### F.3 [expr]

| Entry | Gist | Main text | Tested |
|---|---|---|---|
| [[ub.expr#expr.expr.eval\|expr.expr.eval]] | result undefined or not representable (overflow) | [[expr.pre#4]] | UBSan, constant evaluation |
| [[ub.expr#expr.basic.lvalue.strict.aliasing.violation\|expr.basic.lvalue.strict.aliasing.violation]] | strict aliasing violation | [[basic.lval#11]] | TySan |
| [[ub.expr#expr.basic.lvalue.union.initialization\|expr.basic.lvalue.union.initialization]] | a union's default copy applied to a non-union object | [[basic.lval#11]] | none |
| [[ub.expr#expr.type.reference.lifetime\|expr.type.reference.lifetime]] | the corresponding pointer is invalid when a reference is evaluated | [[expr.type#1]] | ASan, constant evaluation |
| [[ub.expr#conv.lval.valid.representation\|conv.lval.valid.representation]] | reading an invalid value representation | [[conv.lval#3]] | UBSan, constant evaluation |
| [[ub.expr#conv.double.out.of.range\|conv.double.out.of.range]] | floating-point conversion out of range | [[conv.double#2]] | not triggered under IEEE 754 |
| [[ub.expr#conv.fpint.float.not.represented\|conv.fpint.float.not.represented]] | floating-to-integer value not representable | [[conv.fpint#1]] | UBSan, constant evaluation |
| [[ub.expr#conv.fpint.int.not.represented\|conv.fpint.int.not.represented]] | integer-to-floating out of range | [[conv.fpint#2]] | not triggered under IEEE 754 |
| [[ub.expr#conv.ptr.virtual.base\|conv.ptr.virtual.base]] | converting an invalid pointer to a virtual base | [[conv.ptr#3]] | ASan (indirectly) |
| [[ub.expr#conv.member.missing.member\|conv.member.missing.member]] | member pointer converted to a derived class lacking the member | [[conv.mem#2]] | none |
| [[ub.expr#expr.call.different.type\|expr.call.different.type]] | calling through an incompatible function type | [[expr.call#6]] | UBSan |
| [[ub.expr#expr.ref.member.not.similar\|expr.ref.member.not.similar]] | object type not similar in member access | [[expr.ref#10]] | none |
| [[ub.expr#expr.dynamic.cast.pointer.lifetime\|expr.dynamic.cast.pointer.lifetime]] | `dynamic_cast` pointer does not point to a suitable object | [[expr.dynamic.cast#7]] | none |
| [[ub.expr#expr.dynamic.cast.glvalue.lifetime\|expr.dynamic.cast.glvalue.lifetime]] | `dynamic_cast` glvalue does not refer to a suitable object | [[expr.dynamic.cast#7]] | — |
| [[ub.expr#expr.static.cast.base.class\|expr.static.cast.base.class]] | wrong target in a reference downcast | [[expr.static.cast#2]] | vptr, constant evaluation |
| [[ub.expr#expr.static.cast.enum.outside.range\|expr.static.cast.enum.outside.range]] | outside the range of values when converting to an enumeration | [[expr.static.cast#8]] | UBSan (on read), constant evaluation |
| [[ub.expr#expr.static.cast.fp.outside.range\|expr.static.cast.fp.outside.range]] | explicit floating-point conversion out of range | [[expr.static.cast#9]] | not triggered under IEEE 754 |
| [[ub.expr#expr.static.cast.downcast.wrong.derived.type\|expr.static.cast.downcast.wrong.derived.type]] | wrong target in a pointer downcast | [[expr.static.cast#10]] | vptr |
| [[ub.expr#expr.static.cast.does.not.contain.original.member\|expr.static.cast.does.not.contain.original.member]] | member pointer converted to an unrelated base class | [[expr.static.cast#11]] | — |
| [[ub.expr#expr.unary.dereference\|expr.unary.dereference]] | indirection through a pointer that does not point to an object | [[expr.unary.op#1]] | UBSan, constant evaluation |
| [[ub.expr#expr.new.non.allocating.null\|expr.new.non.allocating.null]] | placement new yields a null pointer | [[expr.new#22]] | UBSan |
| [[ub.expr#expr.delete.mismatch\|expr.delete.mismatch]] | operand of single-object delete not from single-object new | [[expr.delete#2]] | warning, ASan (with option), constant evaluation |
| [[ub.expr#expr.delete.array.mismatch\|expr.delete.array.mismatch]] | operand of array delete not from array new | [[expr.delete#2]] | warning, ASan (with option), constant evaluation |
| [[ub.expr#expr.delete.dynamic.type.differ\|expr.delete.dynamic.type.differ]] | polymorphic deletion without a virtual destructor | [[expr.delete#3]] | ASan with multiple inheritance, constant evaluation |
| [[ub.expr#expr.delete.dynamic.array.dynamic.type.differ\|expr.delete.dynamic.array.dynamic.type.differ]] | polymorphic deletion of an array | [[expr.delete#3]] | none |
| [[ub.expr#expr.mptr.oper.not.contain.member\|expr.mptr.oper.not.contain.member]] | object of `.*` does not contain the member | [[expr.mptr.oper#4]] | ASan (indirectly), constant evaluation |
| [[ub.expr#expr.mptr.oper.member.func.null\|expr.mptr.oper.member.func.null]] | member pointer of `.*` is null | [[expr.mptr.oper#6]] | ASan (SEGV), constant evaluation |
| [[ub.expr#expr.mul.div.by.zero\|expr.mul.div.by.zero]] | division by zero | [[expr.mul#4]] | UBSan, constant evaluation |
| [[ub.expr#expr.mul.representable.type.result\|expr.mul.representable.type.result]] | quotient not representable (`INT_MIN / -1`) | [[expr.mul#4]] | UBSan, constant evaluation |
| [[ub.expr#expr.add.out.of.bounds\|expr.add.out.of.bounds]] | creating an out-of-bounds pointer | [[expr.add#4.3]] | constant evaluation (at run time only reported on access) |
| [[ub.expr#expr.add.sub.diff.pointers\|expr.add.sub.diff.pointers]] | subtracting pointers into different arrays | [[expr.add#5.3]] | constant evaluation |
| [[ub.expr#expr.add.not.similar\|expr.add.not.similar]] | pointer arithmetic type not similar to the element type | [[expr.add#6]] | none |
| [[ub.expr#expr.shift.neg.and.width\|expr.shift.neg.and.width]] | shift count negative or not less than the width | [[expr.shift#1]] | UBSan, constant evaluation |
| [[ub.expr#expr.assign.overlap\|expr.assign.overlap]] | source and target of assignment partially overlap | [[expr.assign#7]] | none |

### F.4 [stmt]

| Entry | Gist | Main text | Tested |
|---|---|---|---|
| [[ub.stmt#stmt.return.flow.off\|stmt.return.flow.off]] | flowing off the end of a non-void function | [[stmt.return#4]] | warning, UBSan, constant evaluation |
| [[ub.stmt#stmt.return.coroutine.flow.off\|stmt.return.coroutine.flow.off]] | coroutine flows off the end without `return_void` | [[stmt.return.coroutine#3]] | warning |
| [[ub.stmt#stmt.dcl.local.static.init.recursive\|stmt.dcl.local.static.init.recursive]] | recursive initialization of a static local variable | [[stmt.dcl#3]] | libc++abi aborts |

### F.5 [dcl]

| Entry | Gist | Main text | Tested |
|---|---|---|---|
| [[ub.dcl#dcl.type.cv.modify.const.obj\|dcl.type.cv.modify.const.obj]] | modifying a const object | [[dcl.type.cv#4]] | ASan when in a read-only segment, constant evaluation |
| [[ub.dcl#dcl.type.cv.access.volatile\|dcl.type.cv.access.volatile]] | accessing a volatile object through a non-volatile glvalue | [[dcl.type.cv#5]] | — |
| [[ub.dcl#dcl.ref.incompatible.function\|dcl.ref.incompatible.function]] | function reference bound to an incompatible function | [[dcl.ref#6]] | UBSan (on call) |
| [[ub.dcl#dcl.ref.incompatible.type\|dcl.ref.incompatible.type]] | object reference bound to an inaccessible object | [[dcl.ref#6]] | none |
| [[ub.dcl#dcl.ref.uninitialized.reference\|dcl.ref.uninitialized.reference]] | reference evaluated before it is initialized | [[dcl.ref#6]] | ASan (SEGV) |
| [[ub.dcl#dcl.fct.def.coroutine.resume.not.suspended\|dcl.fct.def.coroutine.resume.not.suspended]] | resuming a coroutine that is not suspended | [[dcl.fct.def.coroutine#8]] | ASan (SEGV) |
| [[ub.dcl#dcl.fct.def.coroutine.destroy.not.suspended\|dcl.fct.def.coroutine.destroy.not.suspended]] | destroying a coroutine that is not suspended | [[dcl.fct.def.coroutine#11]] | ASan |
| [[ub.dcl#dcl.attr.assume.false\|dcl.attr.assume.false]] | false `[[assume]]` (runtime-undefined) | [[dcl.attr.assume#1]] | UBSan, constant evaluation |
| [[ub.dcl#dcl.attr.noreturn.eventually.returns\|dcl.attr.noreturn.eventually.returns]] | a `[[noreturn]]` function returns (runtime-undefined) | [[dcl.attr.noreturn#2]] | warning, UBSan; constant evaluation accepts |

### F.6 [class], F.7 [temp], F.8 [except]

| Entry | Gist | Main text | Tested |
|---|---|---|---|
| [[ub.class#class.dtor.no.longer.exists\|class.dtor.no.longer.exists]] | calling the destructor again on a dead object | [[class.dtor#18]] | ASan (if the destructor releases resources), constant evaluation |
| [[ub.class#class.abstract.pure.virtual\|class.abstract.pure.virtual]] | virtual call to a pure virtual function during construction/destruction | [[class.abstract#6]] | warning (for direct calls), runtime library aborts |
| [[ub.class#class.base.init.mem.fun\|class.base.init.mem.fun]] | calling a member function before base initialization completes | [[class.base.init#18]] | none |
| [[ub.class#class.cdtor.before.ctor\|class.cdtor.before.ctor]] | referring to a member or base before construction begins | [[class.cdtor#1]] | vptr (with virtual bases) |
| [[ub.class#class.cdtor.after.dtor\|class.cdtor.after.dtor]] | referring to a member or base after destruction completes | [[class.cdtor#1]] | none |
| [[ub.class#class.cdtor.convert.pointer\|class.cdtor.convert.pointer]] | converting to a base pointer before construction/after destruction | [[class.cdtor#3]] | none |
| [[ub.class#class.cdtor.form.pointer\|class.cdtor.form.pointer]] | forming a member pointer before construction/after destruction | [[class.cdtor#3]] | none |
| [[ub.class#class.cdtor.virtual.not.x\|class.cdtor.virtual.not.x]] | virtual call through "a part other than x" | [[class.cdtor#4]] | none |
| [[ub.class#class.cdtor.typeid\|class.cdtor.typeid]] | wrong static type for `typeid` during construction/destruction | [[class.cdtor#5]] | none |
| [[ub.class#class.cdtor.dynamic.cast\|class.cdtor.dynamic.cast]] | wrong static type for `dynamic_cast` during construction/destruction | [[class.cdtor#6]] | none |
| [[ub.temp#temp.inst.inf.recursion\|temp.inst.inf.recursion]] | infinite recursion in template instantiation | [[temp.inst#18]] | compile-time fatal error (depth limit) |
| [[ub.except#except.handle.handler.ctor.dtor\|except.handle.handler.ctor.dtor]] | accessing members in a function-try-block handler | [[except.handle#11]] | none |

## Common misconceptions

!!! pitfall "It's not in the annex, so it's not UB"
    The annex only includes UB stated explicitly in the core language. Implicit UB and standard library UB are not in it, and they are UB all the same.

!!! pitfall "The sanitizer didn't report anything, so there's no UB"
    In the tables above, nearly half of the entries are tested as none, and most of those leave no detectable trace in any execution.

!!! pitfall "The result is correct at -O0, so it's fine"
    The examples for strict aliasing (F.3.2), flowing off the end of a function (F.4.1), a thread not making progress (F.2.20) and a returning `[[noreturn]]` function (F.5.9) all change behavior at `-O2`. The consequences of UB come mainly from the optimizer's reasoning, not from the hardware.

## Questions

!!! question "1. Why is the scope of Annex F exactly the same as [expr.const.core] ¶2.8?"
    Both say Clause [intro] through Clause [cpp]. Is that a coincidence?

<details markdown="1">
<summary>Answer</summary>

It is not a coincidence. [[expr.const.core#2.8]] requires implementations to recognize the UB and EB specified in [intro] through [cpp] during constant evaluation, while [[expr.const.core#4]] leaves the handling of library UB unspecified. For the set of UB that constant evaluation must diagnose to be a finite list that can be checked, those UB have to be listed one by one, and Annex F is the UB part of that list. Making F.5.8 and F.5.9 runtime-undefined behavior serves to exempt them from checking in constant evaluation: whether they make an expression non-constant is implementation-defined ([[expr.const.core#3]]).
</details>

!!! question "2. F.3.30 and F.2.17 are both about bad pointers. What is the difference?"
    What is the behavior of `int a[10]; int* p = a + 11;` and of `int* q = new int; delete q; q + 1;`?

<details markdown="1">
<summary>Answer</summary>

`a + 11` creates an out-of-bounds pointer, which by [[expr.add#4.3]] is UB outright, even if it is never dereferenced. After `delete`, `q` becomes a pointer value that is invalid in the current evaluation. By [[basic.compound#6]], indirection through it is UB (F.2.17), while using it in addition or comparison is implementation-defined. So the former is UB and the latter's behavior is implementation-defined. The standard leaves this latitude for invalid pointers because a lot of real code compares pointer values after deallocation.
</details>
