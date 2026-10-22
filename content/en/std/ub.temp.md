---
title: Undefined behavior in [temp]
summary: The result of an infinite recursion in template instantiation is undefined; this is a compile-time kind of UB, and real compilers stop with an error at an implementation-defined depth limit.
updated: 2026-10-19
---

!!! tldr
    - Only one thing in Clause 13 is stated explicitly as undefined behavior: template instantiation getting into infinite recursion ([[temp.inst#18]]).
    - This is compile-time UB. The standard imposes no requirements on the compilation process itself; the compiler may report an error, run out of memory, or never finish.
    - Real compilers stop with an error at an implementation-defined recursion depth limit. Clang's default is 1024, adjustable with `-ftemplate-depth=N`.
    - Most other template-related pitfalls are IFNDR (the program is ill-formed, but the standard does not require the compiler to diagnose it), cataloged in Annex G [[ifndr]].

Annex F collects the undefined behavior stated explicitly in the core language; see [[ub]] for the overview. Its F.7 subclause corresponds to Clause 13 [temp] and has a single entry, which differs from all the others: it happens at compile time, not while the program runs.

### F.7.1 Infinite recursion in template instantiation {#temp.inst.inf.recursion}

`[ub:temp.inst.inf.recursion]` · main text [[temp.inst#18]]

```cpp ub
template <class T>
class X {
  X<T>* p;   // OK: a pointer member does not require X<T> to be complete and triggers no instantiation
  X<T*> a;   // instantiating X<T> requires a complete X<T*>, which in turn requires X<T**>...
};

int main() {
  X<int> x;   // UB: instantiation gets into infinite recursion
}
```

Defining a variable of type `X<int>` requires implicitly instantiating `X<int>`. It has a member of type `X<int*>`, and a member's type must be complete, so `X<int*>` has to be instantiated, and so on; the chain never ends. The member `p` is only a pointer, and the type a pointer points to need not be complete, so it causes no instantiation.

[[temp.inst#18]] first says there is an implementation-defined limit on the total depth of recursive instantiations, which could involve more than one template, and then says the result of an infinite recursion is undefined. Annex B [[implimits]] recommends this limit be at least 1024.

Clang 23 does not actually recurse forever. On reaching the limit it reports `fatal error: recursive template instantiation exceeded maximum depth of 1024`, with a hint that `-ftemplate-depth=N` adjusts the limit; with `-ftemplate-depth=50`, the number in the error changes to 50 accordingly.

Why doesn't the standard make this ill-formed and require a diagnostic? Template instantiation is as powerful as a Turing machine, and a compiler cannot decide in general whether an instantiation chain terminates, so the standard cannot require it to report infinite recursion reliably. On the other hand, programs that exceed implementation limits may be rejected anyway ([[intro.compliance.general#2.1]]). So undefined here has only one practical meaning: the standard imposes no requirements on compilation, and a compiler that reports an error, crashes from memory exhaustion, or runs forever does not violate the standard.

This UB never survives to run time, since the program cannot even be produced, so detecting it with sanitizers is out of the question. In practice the only thing to care about is the depth limit itself; see [[implimits]] for the defaults of the various compilers.
