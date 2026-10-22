---
title: Debugging C++ programs
summary: "Debugging C++ with lldb on macOS: where debug info comes from, how optimization levels affect stepping and variables, breakpoints, conditional breakpoints, exception breakpoints and watchpoints, inspecting STL containers, reading crash call stacks and core files, using ASan reports as debugging clues, C++26's <debugging>, and printing types and tracing values at compile time and run time."
group: Debugging and diagnostics
tags: toolchain, debugging, lldb, sanitizer, crashes, source_location
updated: 2026-10-19
---

!!! tldr
    - A debugger relies on the debug info (DWARF) the compiler writes to map machine instructions back to source lines and variables. Under `-O0 -g` the mapping is one-to-one; with optimization on, the as-if rule lets variables vanish and statements merge or reorder, so the debugger shows `<variable not available>` and stepping skips lines.
    - Only about ten lldb operations are commonly used: breakpoints by function or line, conditional breakpoints, `breakpoint set -E c++` to stop where an exception is thrown, `next`/`step`/`finish`, `bt`, `frame variable`, `watchpoint set variable`. A conditional breakpoint stops the process to evaluate the condition on every hit, about 5 ms each on our test machine; in hot loops, put the condition in the code instead.
    - On a crash, look at the stop reason and fault address first, then walk up the call stack looking at variables. macOS doesn't write core files by default; you can save the state from lldb with `process save-core`.
    - An ASan report gives three call stacks: the faulting access, the deallocation and the allocation. Run under lldb, it stops in the faulting frame, and `memory history` brings back the other two.
    - The types in template code can be made to show up in compiler errors (a class template declared but not defined, a deliberately failing `static_assert`); at run time, use `__PRETTY_FUNCTION__` or `std::source_location`. Print debug output to `stderr`, with file, line and function name.

!!! note "Test setup"
    Apple M2 Pro, macOS 26, Homebrew Clang 23.1.3 with its own libc++ headers. Homebrew's LLVM doesn't include lldb, so we used the lldb from Xcode's command line tools (`lldb --version` prints `lldb-2100.0.16.4`). Sessions were recorded in batch mode: `lldb -b -o 'command' -o 'command' ./prog`; when the program crashes, `-k 'command'` gives commands to run after the crash, otherwise lldb stops at the interactive prompt waiting for input. Source context and disassembly are omitted from the output, with cuts shown as `...`. The Anaconda installation on `PATH` on our test machine carries an old `ld` (see [[toolchain/compilation-pipeline]]), which reports `can't parse dwarf compilation unit info` when linking and produces programs without debug info; it was removed from `PATH` for these experiments.

## Where debug info comes from

`-g` makes the compiler write **debug information** into the object file: which source line and column each machine instruction corresponds to, which register or stack slot each variable lives in and over which range of instructions it is valid, and the member layout of every type. The format on Linux and macOS is DWARF. The debugger has no other source of information; everything it shows comes from here.

macOS has a peculiarity: the linker doesn't copy DWARF into the executable, it only records the paths of the `.o` files. To get debug info that can be stored on its own, run `dsymutil` to produce a `.dSYM` directory. When compiling and linking in one step, as in `clang++ -g x.cpp -o x`, the driver calls it automatically; when compiling and linking separately, it doesn't:

```text
$ clang++ -std=c++2c -g -c loop.cpp && clang++ loop.o -o loop
$ lldb -b -o 'breakpoint set -f loop.cpp -l 7' ./loop
Breakpoint 1: where = loop`total(...) + 60 at loop.cpp:7:10, address = 0x0000000100000524
$ rm loop.o
$ lldb -b -o 'breakpoint set -f loop.cpp -l 7' ./loop
Breakpoint 1: no locations (pending).
WARNING:  Unable to resolve breakpoint to any actual locations.
```

With the `.o` deleted, the same program has no line information. This happens when a build system cleans intermediate files, or when an executable is copied to another machine; for release or archiving, run `dsymutil loop` first and keep `loop.dSYM`.

## Optimization and the debugging experience

The same code compiled with `-O0` and with `-O2`, setting a breakpoint on `main` and stepping repeatedly:

```cpp run title="step.cpp" ok
#include <cstdio>

static int square(int x) { return x * x; }

int main(int argc, char**) {
  int a = argc + 1;
  int b = square(a);
  int c = a + b;
  std::printf("%d\n", c);
  int d = c * 2;
  std::printf("%d\n", d);
  return 0;
}
```

Under `-O0 -g`, the breakpoint stops at line 6, each `next` advances one line, and every variable can be inspected at any time:

```text
(lldb) breakpoint set -n main
(lldb) run
-> 6   	  int a = argc + 1;
(lldb) frame variable
(int) argc = 1
(int) a = 1
(int) b = 1876944424
(int) c = -1
(int) d = -16
(lldb) next
-> 7   	  int b = square(a);
...
(lldb) next
-> 11  	  std::printf("%d\n", d);
(lldb) frame variable
(int) argc = 1
(int) a = 2
(int) b = 4
(int) c = 6
(int) d = 12
```

At the first `frame variable`, `b`, `c` and `d` haven't been initialized yet, and the debugger shows whatever bytes were already in those stack slots. Under [[basic.indet#1]], such automatic variables have an **erroneous value** ([[g:erroneous-value|erroneous value]]) in C++26, and a program reading one has erroneous behavior; a debugger reading memory isn't bound by that rule and just sees a number that happens to be there.

Under `-O2 -g`, the same commands give:

```text
(lldb) run
-> 8   	  int c = a + b;
(lldb) frame variable
(int) argc = 1
(int) c = <variable not available>
(int) d = <variable not available>
(int) a = <no location, value may have been optimized out>
(int) b = <no location, value may have been optimized out>
(lldb) next
-> 9   	  std::printf("%d\n", c);
(lldb) next
-> 10  	  int d = c * 2;
```

The breakpoint lands directly on line 8; lines 6 and 7 have no corresponding instructions. `a` and `b` never existed: after `square` is inlined, the whole computation is a few arithmetic instructions on `argc`. The standard permits this: an implementation only needs to produce the same **observable behavior** ([[g:observable-behavior|observable behavior]]) as the abstract machine, that is, volatile accesses, data written to files, and input and output on interactive devices ([[intro.abstract#1]], [[intro.abstract#8]]). The values of local variables and the order in which statements execute aren't part of it; that is the [[g:as-if-rule|as-if rule]]. The debugger sees the real machine, not the abstract machine.

| Options | Behavior of `step.cpp` in our tests | Suitable for |
|---|---|---|
| `-O0 -g` | Can stop at every line; variables inspectable at any time | Day-to-day development, stepping through logic |
| `-Og -g` | Can stop at every line; variables inspectable only after assignment, `<variable not available>` before | When you need some optimization and still want to debug |
| `-O1 -g`, `-O2 -g` | Starts at line 8; `a` and `b` have no location | Release builds, performance problems, problems that only appear with optimization |

Clang 23's `-Og` is more than an optimization level: `clang++ -g -Og -c step.cpp -###` shows the driver also passes `-fextend-variable-liveness=all`, which keeps variables inspectable throughout their scope. `-O1` doesn't have this option.

!!! tip "Recommendation"
    Develop with `-O0 -g`, or `-Og -g` if the project is too slow; build releases with `-g` too (CMake's RelWithDebInfo, see [[toolchain/cmake]]). Debug info doesn't go into the loaded code segments and doesn't affect run-time speed, but it decides whether you can make sense of the call stack when production crashes. Problems that appear only at `-O2` and vanish at `-O0` are mostly UB or data races; look for them with sanitizers first, not the debugger (see [[topics/undefined-behavior]]).

## Breakpoints, stepping and inspecting variables

| Purpose | lldb command | Short form |
|---|---|---|
| Breakpoint on a function | `breakpoint set -n total` | `b total` |
| Breakpoint on a line | `breakpoint set -f loop.cpp -l 7` | `b loop.cpp:7` |
| Conditional breakpoint | `breakpoint set -f loop.cpp -l 7 -c "i == 500"` | |
| Stop when an exception is thrown | `breakpoint set -E c++` | |
| Run, continue | `run`, `continue` | `r`, `c` |
| Step, not into calls | `next` | `n` |
| Step into calls | `step` | `s` |
| Run until the current function returns | `finish` | |
| Call stack | `bt`, `bt 5` | |
| Switch stack frame | `frame select 2`, `up`, `down` | `f 2` |
| Inspect variables | `frame variable`, `frame variable x s` | `v x` |
| Evaluate an expression | `expression -- v.size()` | `p v.size()` |
| Watch memory writes | `watchpoint set variable p.checksum` | |

`frame variable` only reads debug info and memory, without executing code in the target program; `expression` compiles the expression and runs it in the target process. The difference shows up when inspecting containers.

A conditional breakpoint is useful for stopping at one particular iteration of a large loop:

```cpp run title="loop.cpp" ok
#include <cstdio>
#include <vector>

long total(const std::vector<int>& v) {
  long s = 0;
  for (std::size_t i = 0; i < v.size(); ++i) {
    s += v[i];
  }
  return s;
}

int main() {
  std::vector<int> v(1000);
  for (int i = 0; i < 1000; ++i) v[i] = i % 7;
  std::printf("%ld\n", total(v));
}
```

```text
(lldb) breakpoint set -f loop.cpp -l 7 -c "i == 500"
Breakpoint 1: where = loop`total(...) + 60 at loop.cpp:7:10, address = 0x0000000100000524
(lldb) run
* thread #1, queue = 'com.apple.main-thread', stop reason = breakpoint 1.1
    frame #0: 0x0000000100000524 loop`total(v=size=error: ...) at loop.cpp:7:10
-> 7   	    s += v[i];
(lldb) frame variable i s
(std::size_t) i = 500
(long) s = 1494
```

The condition isn't evaluated in the program. Every time execution reaches the line, the process stops, lldb reads `i` and computes the condition, and lets the process continue if it is false. With the loop changed to 20000 iterations and the condition to `i == 19999`, the whole session took about 104 seconds on our test machine, versus about 1 second with the breakpoint disabled: roughly 5 ms per hit. In a hot loop, a faster approach is to temporarily write `if (i == 19999) __builtin_debugtrap();` in the code; see the `<debugging>` section below.

Choose a breakpoint line where the variable already exists. With a conditional breakpoint on a one-line range-based for such as `for (int x : v) s += x;`, we got two breakpoint locations, the first before the loop variable `x` is declared, where evaluating the condition fails with `use of undeclared identifier 'x'`.

## Inspecting STL containers

lldb has built-in **data formatters** for libc++: they know the internal structure of `std::vector`, `std::map` and `std::string`, and show them as lists of elements rather than a heap of pointers.

```cpp run title="stl.cpp" ok
#include <map>
#include <print>
#include <string>
#include <vector>

int sum(const std::vector<int>& v) {
  int s = 0;
  for (int x : v) s += x;
  return s;
}

int main() {
  std::vector<int> v{3, 1, 4, 1, 5};
  std::map<std::string, int> m{{"apple", 3}, {"pear", 5}};
  std::string s = "a string long enough to live on the heap";
  std::println("{}", sum(v) + m.size() + s.size());
}
```

Compiled with Homebrew Clang 23, stopped at line 16:

```text
(lldb) frame variable v m s
(std::vector<int>) v = size=error: Failed to determine start/end of vector data. {}
(std::map<std::string, int>) m = size=2 {
  [0] = (first = "apple", second = 3)
  [1] = (first = "pear", second = 5)
}
(std::string) s = "a string long enough to live on the heap"
```

`map` and `string` are fine, `vector` fails. `frame variable --raw v` shows the raw members:

```text
(std::__1::vector<int, std::__1::allocator<int> >) v = {
  __layout_ = {
    __begin_ = 0x0000000100601bf0
    __end_ = 0x0000000100601c04
     = {
      __capacity_ = 0x0000000100601c04
      ...
```

The cause is a version mismatch. The formatters read container internals by member name; libc++ 23 moved `vector`'s three pointers into a `__layout_` member, while Xcode's lldb was written against Apple's own libc++. Compiling the same file with Apple Clang (`/usr/bin/clang++`, paired with Apple's libc++), the same lldb shows:

```text
(lldb) frame variable v
(std::vector<int>) v = size=5 {
  [0] = 3
  [1] = 1
  [2] = 4
  [3] = 1
  [4] = 5
}
(lldb) frame variable v[2]
(int) v[2] = 4
```

When a formatter fails, you can bypass it and read memory directly: `parray 5 v.__layout_.__begin_` prints 5 elements starting at that pointer. The long-term fix is to have the debugger and the standard library come from the same toolchain, for example LLVM's own lldb with Homebrew's libc++ (not installed on our test machine, not verified).

Another common failure is calling a container's member function with `expression`:

```text
(lldb) p v[2]
error: Couldn't look up symbols:
  $__lldb_func::0x1:0x85c8:_ZNSt3__16vectorIiNS_9allocatorIiEEEixB9nqe210106Em
Hint: The expression tried to call a function that is not present in the target, perhaps because it was optimized out by the compiler.
```

This time the program was compiled with Apple Clang, the formatters work and `frame variable v[2]` works, but `p v[2]` fails. `vector<int>::operator[]` is a member function of a class template. Under [[temp.inst#3]], implicitly instantiating a class template specialization instantiates only the declarations of its member functions; under [[temp.inst#4]], a definition is instantiated only when it is referenced in a context that requires a definition. The program never calls `operator[]`, so the executable doesn't contain the function, and the expression evaluator has nothing to call. In the same program, `p v.size()` succeeds: `nm` shows that the executable contains a body for `vector<int>::size()` (libc++ uses it internally), but none for `operator[]`. `frame variable v[2]` goes through synthetic children provided by the formatter and needs no function call.

## Stopping where an exception is thrown

```cpp run title="exc.cpp" ok
#include <cstdio>
#include <map>
#include <stdexcept>
#include <string>

int parse_port(const std::string& s) {
  return std::stoi(s);                 // throws invalid_argument for non-numbers
}

int main() {
  std::map<std::string, std::string> cfg{
      {"host", "localhost"}, {"port", "80a"}, {"backup", "x"}};
  for (const auto& [k, v] : cfg) {
    try {
      if (k != "host") std::printf("%s=%d\n", k.c_str(), parse_port(v));
    } catch (const std::exception& e) {
      std::printf("%s: %s\n", k.c_str(), e.what());
    }
  }
}
```

The program prints `backup: stoi: no conversion` and `port=80`. The exception has already been caught, and by the time you look in the `catch`, the stack at the throw point has long been unwound. `breakpoint set -E c++` makes lldb stop at the moment the exception is thrown:

```text
(lldb) breakpoint set -E c++
Breakpoint 1: no locations (pending).
(lldb) run
2 locations added to breakpoint 1
* thread #1, queue = 'com.apple.main-thread', stop reason = breakpoint 1.1
    frame #0: 0x0000000180810040 libc++abi.dylib`__cxa_throw
(lldb) bt 6
  * frame #0: 0x0000000180810040 libc++abi.dylib`__cxa_throw
    frame #1: 0x00000001807a2618 libc++.1.dylib`std::__1::__throw_invalid_argument[abi:nqe210106](char const*) + 72
    frame #2: 0x00000001807a25a8 libc++.1.dylib`std::__1::(anonymous namespace)::throw_from_string_invalid_arg(...) + 60
    frame #3: 0x0000000180784a98 libc++.1.dylib`std::__1::stoi(...) + 224
    frame #4: 0x0000000100000508 exc`parse_port(s="x") at exc.cpp:7:10
    frame #5: 0x00000001000006ac exc`main at exc.cpp:15:58
```

This breakpoint is set on the runtime library's `__cxa_throw` and `__cxa_rethrow` (`breakpoint list` shows `catch: off throw: on`). Every `throw` compiles to a call to `__cxa_throw`, so it stops no matter where the exception is thrown. The mechanism is described in [[toolchain/exception-implementation]]. `frame select 4` switches to your own code, where you can see the bad input was `"x"`.

lldb's help says `-O type-name` stops only when a given type is thrown. We tried `breakpoint set -E c++ -O std::out_of_range`, and the program still stopped where `invalid_argument` was thrown; the filter had no effect. In programs with many exceptions, you can first set a breakpoint in the `catch` clause to find out which kind of exception it is, and then go back to the throw point.

Uncaught exceptions don't need this breakpoint. Mainstream implementations call `std::terminate` without unwinding the stack when no handler is found ([[except.handle#8]] allows this), so the call stack of the throw point is intact in the crash state.

## Finding who changed memory with a watchpoint

A value changes mysteriously, and the code that changes it isn't where you suspect: this is the typical use of a watchpoint. A **watchpoint** makes the processor trap when an address is written, and the debugger stops right after the instruction that wrote it.

```cpp run title="watch.cpp" ub
#include <cstdio>

struct Packet {
  char name[8];
  int  checksum;
};

void set_name(Packet& p, const char* s) {
  int i = 0;
  while (s[i] != '\0') {        // no check that i < 8
    p.name[i] = s[i];
    ++i;
  }
  p.name[i] = '\0';
}

int main() {
  Packet p{};
  p.checksum = 42;
  set_name(p, "sensor-12");
  std::printf("checksum = %d\n", p.checksum);
}
```

The program prints `checksum = 50`. `"sensor-12"` has 9 characters, so `p.name[8]` is past the end of the array, which is UB; with the layout on our test machine, it happens to write the lowest byte of the immediately following `checksum` (the character `'2'` has value 50). Stop at line 20, after the assignment, and watch `checksum`:

```text
(lldb) breakpoint set -f watch.cpp -l 20
(lldb) run
(lldb) watchpoint set variable p.checksum
Watchpoint created: Watchpoint 1: addr = 0x16fdfe580 size = 4 state = enabled type = m
...
(lldb) continue

Watchpoint 1 hit:
old value: 42
new value: 50
* thread #1, queue = 'com.apple.main-thread', stop reason = watchpoint 1
    frame #0: 0x00000001000004d8 watch`set_name(p=0x000000016fdfe578, s="sensor-12") at watch.cpp:12:5
-> 12  	    ++i;
(lldb) frame variable i
(int) i = 8
```

When it stops, the PC is already at the `++i` after the write, and `i == 8` identifies the out-of-bounds iteration. Watchpoints use the processor's debug registers, of which there are very few, so only a few small address ranges can be watched; delete a watchpoint on a local variable once its stack frame returns, or it will fire on unrelated writes (continuing on our test machine, it hit once more during process exit).

Sanitizers behave differently on this example. `-fsanitize=address` reports nothing: the out-of-bounds write still lands inside the `Packet` object, and ASan only places redzones between objects. `-fsanitize=undefined` reports `runtime error: index 8 out of bounds for type 'char[8]'`, because the compiler knows the array type of `p.name`. If the write went through a `char*` pointer, UBSan wouldn't see it either, and a watchpoint is the most direct tool.

## Reading a crash

```cpp run title="crash.cpp" ub
#include <cstdio>

namespace app {
struct Node { int value; Node* next; };

template <class F>
int walk(const Node* n, F f) {
  int s = 0;
  for (; n; n = n->next->next) s += f(n->value);  // skips two at a time
  return s;
}
}  // namespace app

int main() {
  app::Node c{3, nullptr}, b{2, &c}, a{1, &b};
  std::printf("%d\n", app::walk(&a, [](int x) { return x * 10; }));
}
```

Run directly, the shell only gives exit code 139 (128 + 11 for `SIGSEGV`). Run under lldb, the commands given with `-k` execute automatically on the crash:

```text
$ lldb -b -o run -k bt -k 'frame variable' -k 'frame select 1' -k 'frame variable' -k 'quit 1' ./crash
(lldb) run
* thread #1, queue = 'com.apple.main-thread', stop reason = EXC_BAD_ACCESS (code=1, address=0x8)
    frame #0: 0x00000001000005a0 crash`int app::walk<main::$_0>(n=0x000000016fdfe590, f=(unnamed class) @ 0x000000016fdfe54f) at crash.cpp:9:26
-> 9   	  for (; n; n = n->next->next) s += f(n->value);  // skips two at a time
    	                         ^
(lldb) bt
  * frame #0: 0x00000001000005a0 crash`int app::walk<main::$_0>(...) at crash.cpp:9:26
    frame #1: 0x000000010000052c crash`main at crash.cpp:16:23
    frame #2: 0x00000001804afe00 dyld`start + 6992
(lldb) frame variable
(const app::Node *) n = 0x000000016fdfe590
((unnamed class)) f = {}
(int) s = 40
(lldb) frame select 1
(lldb) frame variable
(app::Node) c = {
  value = 3
  next = nullptr
}
...
```

Read it in this order:

1. The stop reason. `EXC_BAD_ACCESS` is macOS's name for an invalid memory access, and `address=0x8` is the fault address. A very small address almost always means accessing a member through a null pointer: in `Node`, `int value` takes 4 bytes, plus 4 bytes of alignment, and the offset of `next` is exactly 8.
2. The column. `9:26` points at the second `->next`. The `n->next` read by the first `->` is a null pointer, and the second one takes a member through it.
3. The variables. `n` points to `c` (the value of `b.next` in `frame select 1`), and `c.next` is `nullptr`; `s = 40` says the previous iteration processed `a`. The cause is now clear: two steps from `a` reached `c`, and on the next two steps the node in between doesn't exist.

The function names in the call stack have already been **demangled** into C++ syntax. The symbol table stores mangled names; `nm` shows them as they are, and `c++filt` demangles them:

```text
$ nm crash | grep walk
0000000100000554 t __ZN3app4walkIZ4mainE3$_0EEiPKNS_4NodeET_
$ nm crash | grep walk | awk '{print $3}' | c++filt
int app::walk<main::$_0>(app::Node const*, main::$_0)
```

`main::$_0` is the internal name Clang gives the closure type of the lambda in `main`. The mangling rules are in [[toolchain/name-mangling]].

### Core files

A **core file** is a snapshot of a process's memory and registers when it crashed, which can be opened in a debugger afterwards. The kernel settings on our test machine are `kern.coredump: 1` and `kern.corefile: /cores/core.%P`, but the shell's default `ulimit -c` is 0. The experiment results:

- After `ulimit -c unlimited`, running `./crash` exits with code 139, and `/cores` contains no file.
- Retrying after adding the `com.apple.security.get-task-allow` entitlement to the program with `codesign`: still nothing.
- `/cores` is owned by root with mode 755, and `touch /cores/x` reports `Permission denied`. An ordinary user's process can't write files there, which is very likely the direct reason there is no core. Changing that directory's permissions needs administrator action, which we didn't take, so we couldn't confirm whether a core would be produced after changing them.

From inside the debugger, though, you can save the state directly and open it later:

```text
$ lldb -b -o run -k 'process save-core --style stack crash.core' -k 'quit 1' ./crash
$ ls -l crash.core
-rw-------@ 1 weiran  wheel  20480 Oct 19 19:12 crash.core
$ lldb -c crash.core ./crash -o bt -o 'frame variable'
* thread #1, stop reason = ESR_EC_DABORT_EL0 (fault address: 0x8)
  * frame #0: 0x00000001000005a0 crash`int app::walk<main::$_0>(n=0x000000016fdfe570, ...) at crash.cpp:9:26
    frame #1: 0x000000010000052c crash`main at crash.cpp:16:23
    frame #2: 0x00000001804afe00 libsystem_kernel.dylib`host_request_notification + 72
(lldb) frame variable
(const app::Node *) n = 0x000000016fdfe570
((unnamed class)) f = {}
(int) s = 40
```

`--style stack` saves only the stack and registers, hence just 20 KB. The cost is that system library code isn't in the file; lldb maps addresses using the machine's current libraries, and frame 2 is mislabeled as `host_request_notification` (it is actually `dyld`'s `start`). Frames and variables in your own code are complete, which is enough for problems like this one; use `--style full` for the full memory.

## Using sanitizer reports as debugging clues

The kinds of sanitizer and their overhead are covered in [[topics/undefined-behavior]], and examples of the various memory errors in [[topics/dangling-references]]. This section is about reading an ASan report.

```cpp run title="uaf.cpp" ub
#include <cstdio>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  int& first = v[0];
  v.push_back(4);              // not enough capacity, reallocates
  std::printf("%d\n", first);  // first refers to the freed old array
}
```

Compiled with `-g -O0 -fsanitize=address` and run, the first report we got had `atos failed to symbolize address` for every frame, with addresses but no function names. On macOS, ASan calls the system's `atos` for symbolization by default, and it failed in our environment. Pointing it at LLVM's own symbolizer works:

```text
$ ASAN_SYMBOLIZER_PATH=/opt/homebrew/opt/llvm/bin/llvm-symbolizer ./uaf
==56439==ERROR: AddressSanitizer: heap-use-after-free on address 0x6020000000d0 at pc ...
READ of size 4 at 0x6020000000d0 thread T0
    #0 0x000102988aac in main <dir>/uaf.cpp:8:23
    #1 0x0001804afdfc in start (/usr/lib/dyld:arm64e+0x1fdfc)

0x6020000000d0 is located 0 bytes inside of 12-byte region [0x6020000000d0,0x6020000000dc)
freed by thread T0 here:
    #0 0x000102f39854 in _ZdlPv (.../libclang_rt.asan_osx_dynamic.dylib:arm64+0x65854)
    #1 ... in void std::__1::__libcpp_deallocate[abi:nqe230103]<int>(...) .../__new/allocate.h:62:10
    ...
    #6 ... in int* std::__1::vector<int, ...>::__emplace_back_slow_path[abi:nqe230103]<int>(int&&) .../__vector/vector.h:1055:1
    ...
    #10 ... in std::__1::vector<int, ...>::push_back[abi:nqe230103](int&&) .../__vector/vector.h:466:90
    #11 ... in main <dir>/uaf.cpp:7:5

previously allocated by thread T0 here:
    #0 ... in _Znwm (.../libclang_rt.asan_osx_dynamic.dylib:arm64+0x6545c)
    ...
    #6 ... in std::__1::vector<int, ...>::__vallocate[abi:nqe230103](unsigned long) .../__vector/vector.h:607:25
    ...
SUMMARY: AddressSanitizer: heap-use-after-free ...
Shadow bytes around the buggy address:
  0x602000000000: fa fa fd fa fa fa fd fd fa fa fd fd fa fa 00 06
=>0x602000000080: fa fa 00 06 fa fa 00 00 fa fa[fd]fd fa fa fa fa
  0x602000000100: fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa fa
Shadow byte legend (one shadow byte represents 8 application bytes):
  Addressable:           00
  Partially addressable: 01 02 03 04 05 06 07
  Heap left redzone:       fa
  Freed heap region:       fd
  ...
```

The report has four parts; read them in order:

1. The error kind and the access. `heap-use-after-free`, a 4-byte read at line 8. This part tells you where the error happened, but the cause usually isn't there.
2. Which memory the address is in. The read is at byte 0 of a 12-byte region. 12 bytes is exactly 3 `int`s, that is, `v`'s original array.
3. The deallocation and allocation call stacks. The dozens of frames in the middle are libc++ internals; search from the bottom up for the first frame of your own code: the deallocation happened in the `push_back` at line 7, and the allocation when `v` was constructed at line 5 (in the truncated part). The three locations together tell the whole story: allocated at line 5, a reference taken at line 6, freed by the reallocation at line 7, used at line 8.
4. **Shadow bytes**. ASan keeps 1 byte of state for every 8 bytes of application memory: `00` means all 8 bytes are addressable, `01`–`07` mean only the first few bytes are, `fa` is a redzone between heap blocks, and `fd` is freed memory. The brackets mark the accessed cell: `[fd]fd` are the two cells for this 12-byte region, both freed. For an out-of-bounds access, the brackets land on an `fa`, and the neighboring `00` and `0x` cells tell you how far past the end it went.

Running an ASan program under lldb, it stops at the report and automatically selects the faulting frame:

```text
(lldb) run
* thread #1, queue = 'com.apple.main-thread', stop reason = Use of deallocated memory
    frame #5: 0x0000000100000ab0 uaf0`main at uaf.cpp:8:23
(lldb) memory history &first
  thread #4294967295: tid = 0x0001, ... name = 'Memory deallocated by Thread 1'
    ...
    frame #11: 0x0000000100000a48 uaf0`main at uaf.cpp:7:5
  thread #4294967295: tid = 0x0001, ... name = 'Memory allocated by Thread 1'
    ...
    frame #10: 0x00000001000009fc uaf0`main at uaf.cpp:5:20
```

`memory history` shows the deallocation and allocation stacks recorded by ASan as two pseudo-threads, which you can inspect frame by frame like ordinary stacks.

## Asking for the debugger from code: `<debugging>` {{c++26}}

C++26 adds the header `<debugging>`, with three functions: `std::breakpoint()`, `std::breakpoint_if_debugging()` and `std::is_debugger_present()` ([[P2546R5]]).

!!! std
    `void breakpoint() noexcept;` The semantics of this function are implementation-defined.

The semantics of `breakpoint()` are entirely implementation-defined ([[debugging.utility#1]]); a note says the intent is to pause the program and hand control to a debugger when one is present, and that the program may terminate abnormally when none is. `breakpoint_if_debugging()` is equivalent to asking `is_debugger_present()` and then calling `breakpoint()` (¶2). The default behavior of `is_debugger_present()` is implementation-defined (¶4), and it is a replaceable function (¶5, [[P2810R4]]): a program can provide its own definition, for example deciding from an environment variable whether it is running in a controlled debugging environment.

At the time of writing, Clang 23's libc++ doesn't implement this header yet: `#include <debugging>` reports `'debugging' file not found`, and in the implementation-status comments of `<version>`, `__cpp_lib_debugging` is commented out; in the current draft this macro's value is `202403L`. Until it is available, the same effect can be written on macOS with platform interfaces:

```cpp run title="trap.cpp"
#include <cstdio>
#include <sys/sysctl.h>
#include <unistd.h>

// when the process is being traced, the kernel sets P_TRACED in p_flag
bool debugger_attached() {
  kinfo_proc info{};
  std::size_t size = sizeof info;
  int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()};
  if (sysctl(mib, 4, &info, &size, nullptr, 0) != 0) return false;
  return (info.kp_proc.p_flag & P_TRACED) != 0;
}

int main() {
  std::printf("debugger: %d\n", debugger_attached());
  if (debugger_attached()) __builtin_debugtrap();
  std::puts("after trap");
}
```

This code only compiles on macOS, so it carries no verdict marker. Run directly, it prints `debugger: 0` and `after trap`; run under lldb, it prints `debugger: 1` and then stops:

```text
* thread #1, queue = 'com.apple.main-thread', stop reason = EXC_BREAKPOINT (code=1, subcode=0x1000005d0)
    frame #0: 0x00000001000005d4 trap`main at trap.cpp:16:28
(lldb) continue
after trap
Process 58751 exited with status = 0 (0x00000000)
```

`__builtin_debugtrap()` is a Clang builtin that compiled to `brk #0xf000` on our test machine, and lldb can continue execution after it. Don't confuse it with `__builtin_trap()`: that compiles to `brk #0x1` and signals an unrecoverable error; the compiler treats it as a call that doesn't return and the code after it as unreachable, so you can't count on continuing from there.

## Debugging templates: make the compiler tell you the type

When template code goes wrong, the first step is often finding out what type some `T` or some `decltype` actually is. The most direct way is to make the compiler write it out in an error message:

```cpp title="show-type.cpp" error
#include <map>
#include <string>
#include <vector>

template <class T> struct show_type;   // declared only, not defined

int main() {
  std::map<std::string, std::vector<int>> m;
  auto it = m.begin();
  auto&& [k, v] = *it;
  show_type<decltype(it)>{};           // error: incomplete type
  show_type<decltype(k)>{};            // error: incomplete type
}
```

```text
show-type.cpp:11:3: error: implicit instantiation of undefined template 'show_type<std::__map_iterator<std::__tree_iterator<std::__value_type<std::string, std::vector<int>>, std::__tree_node<std::__value_type<std::string, std::vector<int>>, void *> *, long>>>'
show-type.cpp:12:3: error: implicit instantiation of undefined template 'show_type<const std::string>'
```

The second line deserves attention: `k` is a structured binding, and `decltype(k)` is not `const std::string&` but its **referenced type**, `const std::string` ([[dcl.type.decltype#1]]). Questions like this are hard to settle by reading code; one print from the compiler settles them.

To see the `T` deduced for a function template, put a `static_assert` in the function body that always fails and depends on `T`:

```cpp title="inspect-t.cpp" error
#include <type_traits>

template <class T> void f(T&&) {
  static_assert(std::is_void_v<T>, "inspect T");
}

int main() {
  const int x = 0;
  f(x);
  f(42);
}
```

```text
inspect-t.cpp:4:17: error: static assertion failed due to requirement 'std::is_void_v<const int &>': inspect T
inspect-t.cpp:9:3: note: in instantiation of function template specialization 'f<const int &>' requested here
inspect-t.cpp:4:17: error: static assertion failed due to requirement 'std::is_void_v<int>': inspect T
inspect-t.cpp:10:3: note: in instantiation of function template specialization 'f<int>' requested here
```

The condition must depend on `T`. With `static_assert(false)`, every instantiation still fails, but `T` doesn't appear in the error message. General methods for reading long template errors are in [[toolchain/reading-compiler-errors]].

Types can be printed at run time too. GCC's and Clang's `__PRETTY_FUNCTION__` includes the template arguments, and on Clang `std::source_location::function_name()` gives the same string:

```cpp run title="pretty.cpp" ok
#include <print>
#include <source_location>
#include <string_view>
#include <utility>
#include <vector>

template <class T>
void g(T&&) {
  std::println("{}", __PRETTY_FUNCTION__);
  std::println("{}", std::source_location::current().function_name());
}

template <class T>
constexpr std::string_view type_name() {
  std::string_view s = __PRETTY_FUNCTION__;   // "... [T = ...]"
  auto b = s.find("T = ") + 4;
  return s.substr(b, s.rfind(']') - b);
}

int main() {
  std::vector<int> v;
  g(v);
  g(std::move(v));
  std::println("{}", type_name<decltype(v.begin())>());
}
```

```text
void g(T &&) [T = std::vector<int> &]
void g(T &&) [T = std::vector<int> &]
void g(T &&) [T = std::vector<int>]
void g(T &&) [T = std::vector<int>]
std::__wrap_iter<int *>
```

The content of neither form is constrained by the standard: `__PRETTY_FUNCTION__` is a compiler extension, and the value of `function_name()` is implementation-defined ([[support.srcloc.cons#1]]). Slicing on `"T = "` as `type_name` does works with Clang 23, but another compiler formats things differently, so it is only suitable for temporary debugging.

## Print debugging done right

Printing variables at key points is often faster than stepping, especially for problems that are multithreaded, timing-dependent, or appear on only one machine. Three things need to be right: where the output goes, what information it carries, and whether printing itself changes the program.

```cpp run title="trace.cpp" ok
#include <map>
#include <print>
#include <source_location>
#include <string>
#include <vector>

template <class T>
const T& trace(const T& value, const char* expr,
               std::source_location loc =
                   std::source_location::current()) {
  std::println(stderr, "{}:{} [{}] {} = {}", loc.file_name(),
               loc.line(), loc.function_name(), expr, value);
  return value;
}
#define TRACE(e) trace((e), #e)

int parse(const std::string& s) {
  TRACE(s);
  return static_cast<int>(TRACE(s.size()));
}

int main() {
  std::vector<std::string> args{"x", "tab\there", ""};
  std::map<std::string, int> m{{"a", 1}};
  TRACE(args);
  TRACE(m);
  return parse("abc") - 3;
}
```

```text
trace.cpp:25 [int main()] args = ["x", "tab\there", ""]
trace.cpp:26 [int main()] m = {"a": 1}
trace.cpp:18 [int parse(const std::string &)] s = abc
trace.cpp:19 [int parse(const std::string &)] s.size() = 3
```

- Location. `std::source_location::current()` written in a default argument gets the location of the call site, not of `trace` itself ([[support.srcloc.cons#2]]). The macro has only one job left: turning the expression's source into a string with `#e`.
- Containers print directly. C++23's `std::format` and `std::print` can format ranges ([[P2286R8]]): a `vector` shows as `[...]`, a `map` as `{k: v}`, and strings as elements are quoted and escaped, so empty strings and tabs are obvious at a glance.
- The original value is returned. `trace` returns its argument, so it can wrap any expression without changing the expression's value, as on line 19. Note that it returns a reference: the temporary in `TRACE(s.size())` lives until the end of the full-expression, so using it within the same expression is fine; writing `const auto& n = TRACE(s.size());` dangles (see [[topics/dangling-references]]).

There is a practical reason to print to `stderr`: it is unbuffered. If the program crashes after printing, whatever was still in a buffer is lost:

```cpp run title="lost.cpp" ub
#include <cstdio>
#include <print>

int main(int argc, char**) {
  std::printf("printf: before crash\n");
  std::println(stderr, "stderr: before crash");
  int* volatile p = nullptr;
  if (argc > 0) *p = 1;                  // UB: dereferencing a null pointer
}
```

With output piped (`./lost 2>&1 | cat`), we saw only `stderr: before crash`; the `stdout` line stayed in the buffer and disappeared with the process. In that situation `stdout` is fully buffered, and `\n` doesn't trigger a write.

The standard has something to say about this too. C++26 specifies that the return from a function that delivers data to be written to a file to the host environment is an **observable checkpoint** ([[g:observable-checkpoint|observable checkpoint]], [[cstdio.syn#2]]); observable behavior before a checkpoint must be produced faithfully even if UB happens afterwards ([[intro.abstract#6]]). Writing into a buffer isn't delivery yet, so only the `stderr` output, or output after `fflush`, is covered by this guarantee. See [[topics/undefined-behavior]] for a detailed discussion.

!!! pitfall "Printing changes the program"
    A problem that disappears when you add a print statement is a typical symptom of UB and data races. A print is an opaque external call: it changes register allocation, inlining decisions and timing between threads, and UB that the optimizer was exploiting may no longer trigger. When this happens, don't leave the print in as a fix; use sanitizers to find the real cause.

## Questions

!!! question
    Under `-O2 -g`, lldb stops at line 8 of `step.cpp`, and `frame variable a` shows `<no location, value may have been optimized out>`. Is this a compiler defect? Does the `-O2` program still conform to the standard?

<details markdown="1">
<summary>Answer</summary>

It isn't a defect. [[intro.abstract#1]] only requires the implementation to emulate the observable behavior of the abstract machine, and the observable behavior listed in ¶8 doesn't include the values of local variables. `a` is just an intermediate result for computing `c`; once the compiler folds the whole computation into a few instructions, `a` no longer occupies any register or memory, and the debug info truthfully says it has no location. The program's output is the same as at `-O0`, so it conforms. Debug info itself isn't part of the standard, and how much it can describe is a matter of implementation quality; Clang's `-Og` with `-fextend-variable-liveness=all` exists precisely to improve this.
</details>

!!! question
    `p v[2]` reports `The expression tried to call a function that is not present in the target`, while `p v.size()` works. What line can you add to the program to make `p v[2]` work? Why?

<details markdown="1">
<summary>Answer</summary>

Actually call `v[0]` (or any subscript) somewhere in the program, for example `std::printf("%d\n", v[0]);`. When `vector<int>` is implicitly instantiated, only the declarations of its member functions are instantiated ([[temp.inst#3]]); a definition is instantiated only when referenced in a context that requires a definition ([[temp.inst#4]]), and only then is its code in the executable. Even so, at `-O2` it may be inlined everywhere and have no separate function body, so `frame variable v[2]` is more reliable: it reads memory through the formatter and calls no function.
</details>

!!! question
    `watch.cpp` built with ASan reports nothing, while built with UBSan it reports the out-of-bounds access. If `set_name`'s parameter is changed to `char* dst`, the function writes `dst[i] = s[i]`, and the caller passes `p.name`, can UBSan still report it?

<details markdown="1">
<summary>Answer</summary>

No. UBSan's array bounds check is only inserted where the compiler knows the array type and length; `-fsanitize=bounds` handles subscript expressions like `p.name[i]`. Once the parameter is a `char*`, the function only knows a pointer, and `dst[8]` is just pointer arithmetic to the compiler. ASan doesn't see it either, because the write is still inside the `Packet` object. The behavior is still UB (it goes past the end of the `char[8]`). Here a watchpoint is the direct way to find the writer; another is static analysis (see [[toolchain/static-analysis]]).
</details>

## Summary

| Problem | Tool | Key points |
|---|---|---|
| Logic error, want to see every step | `-O0 -g` + `next`/`step`/`frame variable` | With optimization, variables and line numbers get lost, as the as-if rule allows |
| Fails only on one iteration | Conditional breakpoint | About 5 ms per hit; in hot loops use an `if` in the code plus `__builtin_debugtrap()` |
| Where is the exception thrown? | `breakpoint set -E c++` | Stops at `__cxa_throw`; look up the stack for your own frame |
| A value is unexpectedly overwritten | `watchpoint set variable` | Stops after the write; ASan can't see overflows within an object |
| Crash | `bt`, `frame variable`, fault address | A small address usually means a member access through a null pointer; macOS writes no core by default, use `process save-core` |
| Memory errors | ASan report, `memory history` | Read the three call stacks; on our test machine `ASAN_SYMBOLIZER_PATH` had to be set |
| Containers don't display | `frame variable --raw`, `parray` | lldb and libc++ versions must match |
| Types in templates | An undefined `show_type<T>`, a `static_assert` that depends on `T` | At run time, `__PRETTY_FUNCTION__`, `source_location` |
| Print debugging | `std::println(stderr, ...)` + `source_location` | Buffered `stdout` content is lost on a crash |

A debugger can only tell you what the program did. Once a fix is confirmed, turn the input that triggered the problem into a test so it doesn't come back (see [[toolchain/testing]]).
