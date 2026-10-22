---
title: RAII and scope guards
summary: "Tying a resource's lifetime to an object's lifetime: which language rules guarantee that destructors run, how to write a move-only resource handle, using unique_ptr deleters and scope guards and what they cost, locks and threads in the standard library, lifetimes across coroutine suspension, and the cases RAII doesn't cover plus common traps."
tags: RAII, scope guard, destructors, lifetime, idiom
updated: 2026-10-19
---

!!! tldr
    - RAII puts the code that releases a resource into an object's destructor. However a scope is left, whether by normal execution, `return`, `break` or an exception, automatic objects are destroyed in reverse order of construction, so cleanup is written once.
    - A resource handle class is usually move-only: copying is deleted, and after a move the source enters an empty state that owns nothing, which the destructor must handle. A constructor that takes over a raw handle should be `explicit`.
    - Most of the time you don't need to write that class: `unique_ptr` with an empty-class deleter is a handle with zero extra space; for one-off cleanup use a scope guard, which at `-O2` generates the same code as a hand-written `try`/`catch`.
    - Coroutine suspension does not leave a scope; local objects live until the coroutine frame is destroyed. `exit`, `quick_exit`, `abort` and uncaught exceptions may not destroy local objects at all.
    - The most common mistakes are unnamed guards (`std::lock_guard<std::mutex>{m};` unlocks immediately), and member declaration orders that make a thread join only after the data it uses has been destroyed.

## Four exits, one piece of cleanup code

A function opens a file, allocates a buffer and parses the contents, with several exits along the way:

<div class="compare" markdown="1">

```cpp
bool load(const char* path) {
  std::FILE* f = std::fopen(path, "rb");
  if (!f) return false;
  char* buf = new char[4096];
  if (std::fread(buf, 1, 4096, f) == 0) {
    delete[] buf;
    std::fclose(f);
    return false;
  }
  parse(buf);   // throws: both resources leak
  delete[] buf;
  std::fclose(f);
  return true;
}
```

```cpp
bool load(const char* path) {
  file_ptr f(std::fopen(path, "rb"));
  if (!f) return false;
  auto buf = std::make_unique<char[]>(4096);
  if (std::fread(buf.get(), 1, 4096,
                 f.get()) == 0)
    return false;
  parse(buf.get());  // throws: both are released
  return true;
}
```

</div>

On the left, every exit has to release each resource acquired so far, and the exception exit has nowhere to put release code at all. On the right, `file_ptr` is `std::unique_ptr<std::FILE, fclose_deleter>` (defined below) and `buf` is a `unique_ptr<char[]>`. Their destructors do the releasing, and every exit reaches them.

This technique is called **RAII** (resource acquisition is initialization): acquiring a resource initializes an object that owns it, and the object releases the resource when destroyed. The name emphasizes acquisition, but the part that does the work is the other half: when destructors are guaranteed to run.

## The rules that make it work

### Leaving a scope destroys

On a transfer of control from one point to another, block-scope automatic variables that are active at the origin and not at the destination are destroyed in reverse order of construction ([[stmt.dcl#2]]). The rule doesn't care how control transfers: falling off the end of a block, `return`, `break`, `continue` and `goto` are all the same; the note in [[stmt.jump.general#2]] summarizes it as leaving a scope by whatever means.

The order for `return` is specified too: first the return value is initialized from the operand, then temporaries in the operand are destroyed, then local variables ([[stmt.return#5]]). So when the destructors run, the return value has already been computed, and local RAII objects can safely guard the code that computes it.

Exceptions take a different road to the same result. As an exception passes from `throw` to a handler, the automatic objects constructed since the `try` block was entered and not yet destroyed are destroyed in reverse order of the completion of their construction ([[except.ctor#2]]); this is [[g:stack-unwinding|stack unwinding]]. When a constructor throws partway through, the members and bases already constructed are destroyed too ([[except.ctor#3]]). The details and examples of both are in [[topics/exception-safety]].

### Reverse order

Local variables are destroyed in reverse order of declaration, and so are class members: after the destructor body runs, member destructors are called in reverse order of the completion of their construction, followed by the bases ([[class.dtor#13]]). Members are always initialized in declaration order, regardless of the order written in the initializer list ([[class.base.init#15]]), so destruction order is the reverse of declaration order.

The reason for reverse order is dependency: an object constructed later may refer to one constructed earlier, but not the other way around. Reverse destruction guarantees that whenever an object is destroyed, the objects it depends on are still alive. This guarantee holds only when declaration order matches dependency order; the traps section below has a counterexample.

### Temporaries

A temporary is destroyed as the last step of evaluating the full-expression ([[g:full-expression]]) containing it, even if evaluation ends with an exception ([[class.temporary#4]]). When a temporary is bound directly to a reference, its lifetime is extended to that of the reference ([[class.temporary#6]]).

```cpp run title="order.cpp" ok
#include <cstdio>

struct Trace {
  const char* name;
  explicit Trace(const char* n) : name(n) { std::printf("+%s ", name); }
  ~Trace() { std::printf("-%s ", name); }
};

Trace make(const char* n) { return Trace(n); }

struct Pair {
  Trace first{"m1"};
  Trace second{"m2"};
};

int main() {
  {
    Trace a("a");
    Pair p;
    make("tmp"), std::printf("[expr] ");   // the temporary lives until the full-expression ends
    const Trace& r = make("ext");          // bound to a reference: extended to the end of r's scope
    Trace b("b");
    std::printf("[end] ");
  }
  std::printf("\n");
  try {
    Trace c("c");
    throw 0;
  } catch (int) { std::printf("[handler]\n"); }
}
```

Output in our tests:

```text
+a +m1 +m2 +tmp [expr] -tmp +ext +b [end] -b -ext -m2 -m1 -a
+c -c [handler]
```

`tmp` is destroyed right after the comma expression is evaluated; `ext` is extended and destroyed in reverse order along with the local variables; `p`'s two members are destroyed in reverse declaration order; `c` is destroyed before entering the handler.

## Writing an RAII class

A POSIX file descriptor is an `int`, and there is no ready-made standard library type to manage it. A proper handle class looks roughly like this:

```cpp run title="unique-fd.cpp" ok
#include <cstdio>
#include <fcntl.h>
#include <unistd.h>
#include <utility>

class UniqueFd {
  int fd_ = -1;                              // -1: owns no descriptor
public:
  UniqueFd() = default;
  explicit UniqueFd(int fd) noexcept : fd_(fd) {}
  UniqueFd(const UniqueFd&) = delete;
  UniqueFd& operator=(const UniqueFd&) = delete;
  UniqueFd(UniqueFd&& o) noexcept : fd_(std::exchange(o.fd_, -1)) {}
  UniqueFd& operator=(UniqueFd&& o) noexcept {
    reset(std::exchange(o.fd_, -1));         // on self-move-assignment, o.fd_ becomes -1 first
    return *this;
  }
  ~UniqueFd() { reset(); }

  int get() const noexcept { return fd_; }
  explicit operator bool() const noexcept { return fd_ >= 0; }
  [[nodiscard]] int release() noexcept { return std::exchange(fd_, -1); }
  void reset(int fd = -1) noexcept {
    if (int old = std::exchange(fd_, fd); old >= 0) ::close(old);
  }
};

UniqueFd open_read(const char* path) {
  return UniqueFd(::open(path, O_RDONLY));   // open returns -1 on failure, i.e. an empty handle
}

int main() {
  UniqueFd a = open_read("/etc/hosts");
  UniqueFd b = std::move(a);                 // a becomes empty, b owns the descriptor
  std::printf("a=%d b=%s\n", a.get(), b ? "open" : "empty");
  int raw = b.release();                     // gives up ownership; b no longer closes it
  std::printf("b=%d close(raw)=%d\n", b.get(), ::close(raw));
  UniqueFd c = open_read("/no/such/file");
  std::printf("c=%s\n", c ? "open" : "empty");
}
```

In our tests it prints `a=-1 b=open`, `b=-1 close(raw)=0`, `c=empty`, with no ASan or UBSan reports. The following explains why each member is written as it is.

### The empty state and moves

A handle class first needs a state that owns no resource, here `-1`. Move construction transfers the resource to the new object and puts the source in the empty state; the destructor and `reset` do nothing in the empty state. Moved-from objects are still destroyed, so the empty state is not optional: it is what makes move semantics possible.

For its own types, the standard library generally promises only that a moved-from object is in a valid but unspecified state ([[lib.types.movedfrom#1]]). A handle class can promise more; `unique_ptr` guarantees `get() == nullptr` after a move ([[unique.ptr.single.ctor#18]]). Your own handle classes should also state the moved-from state as an explicit guarantee, so callers can assign to it, check it or let it be destroyed after a move.

Move assignment is written `reset(std::exchange(o.fd_, -1))`: first empty the source, then close our old descriptor and take the new one. On self-move-assignment, `exchange` has already set `fd_` to `-1`, and `reset` writes the original value back, so the object still owns the descriptor; we verified this (Clang warns `-Wself-move` for an explicit `b = std::move(b)`).

### Copying, `noexcept` and `explicit`

Two objects owning the same descriptor would close it twice, so copying must be forbidden. In fact, declaring a move constructor already defines the implicit copy constructor as deleted ([[class.copy.ctor#6]]); writing `= delete` explicitly is so readers see the intent at a glance.

The move operations and the destructor are `noexcept`. A move just exchanges integers and cannot fail; `std::vector` uses this to decide between moving and copying when it grows, as explained in [[topics/exception-safety]]. Destructors are `noexcept` by default anyway, and errors from `close` should not be thrown from a destructor either; see below.

A constructor that takes over a raw handle must be `explicit`, or an `int` silently turns into an object that owns it:

<div class="compare" markdown="1">

```cpp
// UniqueFd(int) without explicit
void send_all(UniqueFd sock);

void f(int fd) {
  send_all(fd);   // compiles: the parameter's destruction
}                 // closes the caller's fd
```

```cpp
// explicit UniqueFd(int)
void send_all(UniqueFd sock);

void f(int fd) {
  send_all(fd);   // error: no implicit conversion
  send_all(UniqueFd(fd));  // ownership transfer is explicit
}
```

</div>

`release()` is the exit in the other direction: it hands back the raw handle and becomes empty, and the caller is responsible for releasing from then on. Discarding its return value is a leak, so it is marked `[[nodiscard]]`. This matches the semantics of `unique_ptr::release` ([[unique.ptr.single.modifiers#1]]).

### What if acquisition fails

Constructors have no return value. When acquisition fails, there are two options: throw an exception so the object never exists, or enter the empty state like `UniqueFd` and let the caller check. Objects using the second option always need an empty state, which moves require anyway, so handle classes usually support both. When error details are needed, acquisition can be a factory function returning `std::expected<UniqueFd, std::error_code>`.

### Rule of zero

Once a handle class exists, classes that use it need no special member functions of their own:

```cpp
struct Connection {
  UniqueFd sock;
  std::string peer;
};
static_assert(!std::is_copy_constructible_v<Connection>);
static_assert(std::is_nothrow_move_constructible_v<Connection>);
```

Both assertions hold in our tests. The compiler-generated move constructor moves member by member, with `noexcept` deduced from the members; copying is deleted because `UniqueFd` is not copyable. This is the Rule of zero: the resource-managing code lives in one class that does only that, and other classes just compose it. The full Rule of 3/5/0 is in [[topics/special-members-and-elision]].

## `unique_ptr` with a deleter

When the resource itself is a pointer, such as a `FILE*`, a struct pointer returned by a C library, or the result of `malloc`, there is no need to write a handle class: `unique_ptr`'s second template argument is the release function:

```cpp run title="deleters.cpp" ok
#include <cstdio>
#include <memory>

struct fclose_deleter {
  void operator()(std::FILE* f) const noexcept { std::fclose(f); }
};
using file_ptr = std::unique_ptr<std::FILE, fclose_deleter>;

using file_lambda = std::unique_ptr<std::FILE,
    decltype([](std::FILE* f) noexcept { std::fclose(f); })>;   // C++20

void close_file(std::FILE* f) noexcept { std::fclose(f); }      // our own function
using file_fnptr = std::unique_ptr<std::FILE, void (*)(std::FILE*) noexcept>;

int main() {
  file_ptr a(std::fopen("/etc/hosts", "r"));
  file_lambda b(std::fopen("/etc/hosts", "r"));
  file_fnptr c(std::fopen("/etc/hosts", "r"), &close_file);   // every object carries the pointer
  std::printf("%zu %zu %zu\n", sizeof a, sizeof b, sizeof c);
}
```

In our tests it prints `8 8 16`. An empty-class deleter takes no space, so the `unique_ptr` is as big as a raw pointer; a function pointer deleter must be stored in each object, doubling the size, and calls go through an indirect jump unless the optimizer can prove the pointer's value. So the recommendation is an empty function object class, or from C++20 simply the type of a captureless lambda.

Don't write `decltype(&std::fclose)` or `&std::fclose`. Except for the few functions the standard explicitly designates as addressable, taking the address of a standard library function has unspecified behavior and may even be ill-formed ([[namespace.std#6]]), and C library functions are included. Calling it in the body of a deleter has no such problem.

If the deleter type defines a nested type `pointer`, `unique_ptr` stores that type instead of `T*` ([[unique.ptr.single.general#4]]), so in principle it can manage non-pointer handles such as `int` descriptors. But that `pointer` type must meet *Cpp17NullablePointer*, comparing with and constructing from `nullptr`, and wrapping it is no simpler than the `UniqueFd` of the previous section. The remaining details of `unique_ptr`, including `out_ptr` for handing to C interfaces, are in [[topics/ownership-and-smart-pointers]].

## Scope guards

Some cleanup appears only once in one function, such as restoring a global setting or undoing a step already completed. Writing a dedicated class for it isn't worth it; instead use a **scope guard**: it stores a function object on construction and calls it on destruction.

```cpp run title="scope-exit.cpp" ok
#include <cstdio>
#include <utility>

template<class F>
class [[nodiscard]] scope_exit {
  F f_;
  bool active_ = true;
public:
  explicit scope_exit(F f) noexcept(noexcept(F(std::move(f))))
      : f_(std::move(f)) {}
  scope_exit(const scope_exit&) = delete;
  scope_exit& operator=(const scope_exit&) = delete;
  ~scope_exit() { if (active_) f_(); }
  void release() noexcept { active_ = false; }   // cancels the cleanup
};

int depth = 0;

void visit(int n) {
  ++depth;
  auto _ = scope_exit([] { --depth; });         // C++26: _ needs no name
  if (n == 0) return;
  visit(n - 1);
}

int main() {
  visit(3);
  std::printf("depth=%d\n", depth);             // 0
}
```

A few details. Class template argument deduction means `scope_exit(lambda)` doesn't need the lambda's type spelled out. Copying and moving are both deleted, but since C++17 a prvalue initializes the variable directly without a move, so `auto _ = scope_exit(...)` compiles ([[dcl.init.general#15.6.1]]), and so does a factory function returning a `scope_exit` by value; conversely, `scope_exit g(...); return g;` needs a move constructor and is ill-formed. C++26 allows multiple variables named `_` in the same scope ([[P2169R4]]), so a whole series of guards can all be called `_`.

`scope_fail`, which runs only on failure, and `scope_success`, which runs only on success, differ from the above only in the condition in the destructor: record `std::uncaught_exceptions()` on construction, and if the count is larger on destruction, stack unwinding is in progress ([[uncaught.exceptions#1]]). Why the count is compared rather than checked for being greater than 0, and a complete example using `scope_fail` to implement the strong guarantee, are in [[topics/exception-safety]].

| Guard | Condition for running the function on destruction |
|---|---|
| `scope_exit` | always (unless `release()` was called) |
| `scope_fail` | `uncaught_exceptions()` is greater than at construction |
| `scope_success` | `uncaught_exceptions()` is not greater than at construction |

These three names come from `std::experimental::scope_exit` and friends in version 3 of the Library Fundamentals TS ([[P0052R10]]), whose proposal also had a general resource handle, `unique_resource`. They never made it into the standard, and libc++ in our tests doesn't implement this part of the TS either, so real projects write their own or use a third-party library.

### Cost

Put a function that may throw between an acquisition and a release, written once with `try`/`catch` and once with `scope_exit`:

<div class="compare" markdown="1">

```cpp
void by_hand() {
  void* r = acquire();
  try { use(r); }
  catch (...) { release_res(r); throw; }
  release_res(r);
}
```

```cpp
void by_guard() {
  void* r = acquire();
  scope_exit g([r] { release_res(r); });
  use(r);
}
```

</div>

With Clang 23 `-O2` (arm64), the normal paths of the two are identical instruction for instruction: call `acquire`, call `use`, then tail-call `release_res`, with the `active_` flag optimized away. On the exception path the guard version is shorter: its landing pad just calls `release_res` and then `_Unwind_Resume`, while the hand-written version goes through `__cxa_begin_catch`, `__cxa_rethrow` and `__cxa_end_catch`.

`scope_fail` is not free. `uncaught_exceptions()` is a function in the runtime library whose result the compiler doesn't know, so the normal path also has two calls (one at construction, one at destruction) and a comparison. As for object size, a lambda capturing one pointer plus a `bool` or `int` gives a `sizeof` of 16 in our tests.

## RAII in the standard library

Many standard library types are RAII classes themselves, with their destructors' effects written into the specification:

| Type | On destruction | Movable | Source |
|---|---|---|---|
| `unique_ptr<T, D>` | calls the deleter if non-null | yes, the source becomes empty | [[unique.ptr.single.dtor]] |
| `lock_guard<M>` | `unlock()` | no | [[thread.lock.guard#6]] |
| `scoped_lock<Ms...>` | `unlock()` on each | no | [[thread.lock.scoped#6]] |
| `unique_lock<M>` | `unlock()` if it owns the lock | yes, the source is no longer associated with a mutex | [[thread.lock.unique.cons#20]] |
| `jthread` | if joinable, `request_stop()` then `join()` | yes | [[thread.jthread.cons#12]] |
| `thread` | calls `std::terminate` if joinable | yes | [[thread.thread.destr#1]] |
| `fstream` and other file streams | closes the file, swallowing any exception | yes | [[filebuf.cons#5]] |

`lock_guard` is the simplest: lock on construction, unlock on destruction, no moving, no early unlock. `scoped_lock` can lock several mutexes at once, using `std::lock`'s deadlock-avoidance algorithm internally ([[thread.lock.scoped#2]]). `unique_lock` has more state: it can defer locking, unlock early and be handed to someone else, and it is what `condition_variable::wait` needs.

```cpp run title="locks.cpp" ok
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <queue>
#include <thread>

struct Account { std::mutex m; long balance = 100; };

void transfer(Account& from, Account& to, long n) {
  std::scoped_lock lk(from.m, to.m);       // locks both at once; lock order can't deadlock
  from.balance -= n;
  to.balance += n;
}

std::mutex qm;
std::condition_variable cv;
std::queue<int> q;

int pop() {
  std::unique_lock lk(qm);                 // wait needs a unique_lock it can unlock and relock
  cv.wait(lk, [] { return !q.empty(); });
  int v = q.front();
  q.pop();
  lk.unlock();                             // released early; destruction then does nothing
  return v * 2;                            // work that doesn't need the lock
}

int main() {
  Account a, b;
  {
    std::jthread t1([&] { for (int i = 0; i < 1000; ++i) transfer(a, b, 1); });
    std::jthread t2([&] { for (int i = 0; i < 1000; ++i) transfer(b, a, 1); });
  }                                        // jthread joins on destruction
  std::printf("%ld %ld\n", a.balance, b.balance);

  std::jthread consumer([] { std::printf("%d\n", pop()); });
  { std::lock_guard lk(qm); q.push(21); }
  cv.notify_one();
}
```

In our tests it prints `100 100` and `42`, with no TSan reports. `t1` and `t2` request the two locks in opposite orders; locking them one after another with two `lock_guard`s could deadlock.

`std::thread` is not a complete RAII class: its destructor terminates the program if the thread is still joinable ([[thread.thread.destr#1]]). The rationale given in the standard's note is that automatically joining or detaching on destruction would both introduce hard-to-debug problems on exception paths. C++20's `jthread` chose to join, and requests the thread to stop through a `stop_token` before joining, so its destructor neither terminates the program nor waits forever for a thread that won't finish, provided the thread function checks for stop requests.

## Coroutines: suspension is not leaving a scope

When a coroutine suspends at `co_await`, control returns to the caller, but the coroutine's local variables have not left their scope; the second note in [[stmt.jump.general#2]] says explicitly that suspension is not leaving a scope. Local variables live in the [[g:coroutine-state|coroutine state]] (usually on the heap) until the coroutine finishes running or `destroy()` is called on its handle ([[dcl.fct.def.coroutine#11]]).

```cpp run title="coro.cpp" ok
#include <coroutine>
#include <cstdio>
#include <utility>

struct Trace {
  const char* name;
  explicit Trace(const char* n) : name(n) { std::printf("+%s\n", name); }
  ~Trace() { std::printf("-%s\n", name); }
};

struct Task {                              // a minimal coroutine type that owns the frame
  struct promise_type {
    Task get_return_object() {
      return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() { throw; }
  };
  std::coroutine_handle<promise_type> h;
  explicit Task(std::coroutine_handle<promise_type> h) : h(h) {}
  Task(Task&& o) noexcept : h(std::exchange(o.h, {})) {}
  ~Task() { if (h) h.destroy(); }          // Task is itself an RAII class
  void resume() { h.resume(); }
};

Task job() {
  Trace t("local");
  std::puts("before suspend");
  co_await std::suspend_always{};          // suspended: t is still alive
  std::puts("after resume");               // never reached in this example
}

int main() {
  Task task = job();
  task.resume();                           // runs until it suspends at co_await
  std::puts("main: dropping task");
}                                          // ~Task calls destroy(); t is destroyed here
```

In our tests it prints `+local`, `before suspend`, `main: dropping task`, `-local`. The coroutine is never resumed, but `destroy()` counts as a transfer of control out of the function ([[dcl.fct.def.coroutine#11]]), and the local variables alive at the suspension point are destroyed in reverse order as usual. So RAII still holds in coroutines, provided the coroutine frame itself has an RAII owner, here `Task`. A coroutine frame nobody `destroy()`s leaks along with every local object in it.

Lifetimes spanning suspension points also bring two problems.

First, locks across `co_await`. Suspending while holding a `std::lock_guard` keeps the lock held for the entire suspension; if the coroutine resumes on another thread, the destructor calls `unlock()` from a different thread, violating the precondition that the calling thread owns the mutex ([[thread.mutex.requirements.mutex.general#21]]), and violating a precondition is UB ([[structure.specifications#3.4]]). For mutual exclusion in asynchronous code, use an asynchronous mutex provided by the scheduler, or end the lock's scope before `co_await`.

Second, a coroutine's reference parameters copy only the reference itself ([[dcl.fct.def.coroutine#13]]). If the caller's argument is a temporary, it is destroyed after the first suspension, and using it after resumption is a dangling reference. More examples are in [[topics/dangling-references]].

## Where RAII doesn't reach

### Destructors cannot report errors

`close` and `fclose` can fail, for instance when flushing the buffer hits a full disk. A destructor cannot pass that error to the caller: it is `noexcept` by default, and even if made throwing, throwing during stack unwinding terminates the program. The usual approach is to provide a separate explicit `close()`, which callers who care about errors call first and check, while the destructor only does a fallback that cannot fail. The reasoning and measurements are in [[topics/exception-safety]].

### The program doesn't end normally

Destructors run only when control leaves a scope according to the language rules. Several ways of ending a program never leave the scope at all:

```cpp run title="exits.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <stdexcept>

struct Flush {
  const char* name;
  ~Flush() { std::printf("~%s ", name); std::fflush(stdout); }
};

Flush global{"static"};

int main(int argc, char**) {
  Flush local{"local"};
  switch (argc) {
    case 1: return 0;                               // normal return
    case 2: std::exit(0);                           // automatic objects are not destroyed
    case 3: std::quick_exit(0);                     // no objects are destroyed
    case 4: throw std::runtime_error("unhandled");  // no handler: whether to unwind is implementation-defined
  }
}
```

| How it ends | Destroyed in our tests | Rule |
|---|---|---|
| Return from `main` | `local`, `static` | `main`'s locals are destroyed first, then static objects as for `exit` |
| `std::exit` | only `static` | automatic objects are not destroyed ([[support.start.term#9]]) |
| `std::quick_exit` | neither | only functions registered with `at_quick_exit` are called ([[support.start.term#13]]) |
| Uncaught exception | neither, exit code 134 | whether the stack is unwound is implementation-defined ([[except.terminate#2]]) |

`std::abort` and `std::_Exit` likewise run no destructors ([[support.start.term#5]]). It follows that when a process crashes or is killed by a signal, RAII cannot guarantee external state is consistent: resources that outlive the process, such as lock files, temporary files and shared memory, need a separate recovery mechanism, e.g. checking and cleaning up at startup.

### Work that escapes its scope

RAII depends on scopes; once a task escapes the scope that created it, no object is left to finish up for it. After `std::thread::detach()`, the `thread` object no longer represents that thread ([[thread.thread.member#8]]), and local variables the thread captured by reference may have been destroyed long ago; a callback registered with a global event loop may still be called after the object that registered it is destroyed. Problems like these require the task to own the data it uses (capture by value, `shared_ptr`), or a scope object that can wait for all tasks to finish. Callbacks and lifetimes are covered in [[patterns/observer]].

## Traps

### Unnamed guards

A guard object is only useful if it lives until the end of the scope. Forget to name it, and it becomes a temporary, or something else entirely:

```cpp
std::mutex m;
int counter;

void f1() {
  std::lock_guard<std::mutex>{m};     // a temporary: locks then immediately unlocks
  ++counter;                          // not locked
}
void f2() {
  std::unique_lock<std::mutex>(m);    // declares a unique_lock named m
  ++counter;                          // not locked
}
void f3() {
  std::lock_guard<std::mutex>(m);     // error: also a declaration, and lock_guard can't be default-constructed
}
```

`f1` is an expression statement, and the temporary is destroyed at the semicolon ([[class.temporary#4]]). The parenthesized versions in `f2` and `f3` are sneakier: when a statement can be interpreted as either an expression or a declaration, it is a declaration ([[stmt.ambig#1]]), so `(m)` becomes a parenthesized variable name declaring a new variable `m` that hides the outer mutex. `unique_lock` has a default constructor, so `f2` compiles and yields a lock associated with no mutex; `lock_guard` doesn't, so `f3` happens to fail to compile. The detailed disambiguation rules are in [[dcl.ambig.res]].

Clang 23 with libc++ warns `-Wunused-value` for `f1` (ignoring temporary created by a constructor declared with 'nodiscard' attribute) and `-Wvexing-parse` for `f2` and `f3`. The warning for `f1` comes from the `[[nodiscard]]` libc++ puts on these constructors: since C++20, calling a nodiscard constructor or constructing an object of a nodiscard type in the form of an explicit type conversion is also a nodiscard call, and discarding it should be warned about ([[dcl.attr.nodiscard#3]], [[P1771R1]]). That is the implementation's choice; the standard doesn't require `lock_guard` to be marked that way. For an ordinary class without `[[nodiscard]]`, `G{1};` produces no warning at all in our tests. So guard classes you write yourself should be marked `[[nodiscard]]`, as `scope_exit` above is.

### Temporary lifetime of proxy objects

A common design keeps data together with the lock that protects it, with the data accessible only through a proxy object holding the lock. When the proxy is a temporary, the lock covers exactly the full-expression:

```cpp run title="synchronized.cpp" ok
#include <cstdio>
#include <mutex>
#include <vector>

template<class T>
class Synchronized {                       // data kept together with its lock
  T data_;
  std::mutex mu_;
public:
  class Locked {                           // proxy object holding the lock
    std::unique_lock<std::mutex> lk_;
    T* p_;
  public:
    Locked(std::mutex& m, T* p) : lk_(m), p_(p) { std::puts("  lock"); }
    ~Locked() { std::puts("  unlock"); }
    T* operator->() const { return p_; }
    T& operator*() const { return *p_; }
  };
  Locked lock() { return {mu_, &data_}; }
};

int main() {
  Synchronized<std::vector<int>> s;
  std::puts("A");
  s.lock()->push_back(1);                  // the lock covers the whole full-expression
  std::puts("B");
  auto& v = *s.lock();                     // the proxy is destroyed when this declaration ends
  v.push_back(2);                          // not locked
  std::puts("C");
  for (int x : *s.lock())                  // from C++23 the temporary lives until the loop ends
    std::printf("  %d\n", x);
  std::puts("D");
}
```

With `-std=c++2c` in our tests, both `A` and `B` are followed immediately by `lock` and `unlock`, while `C` is followed by `lock`, `1`, `2`, `unlock`. `v` binds to the reference returned by `operator*`, not to the temporary itself, so it doesn't extend the proxy's lifetime, and `v.push_back(2)` runs outside the lock.

The range-`for` case depends on the language version. From C++23, temporaries in a range-`for` initializer live until the loop ends ([[class.temporary#7]], [[P2718R0]]); compiling the same program with `-std=c++20`, `C` is followed by `lock`, `unlock`, then `1`, `2`, with the entire loop outside the lock. Upgrading the language version can also make a lock that used to be released before the loop stay held until the loop ends; [[diff.cpp20]] has an example that deadlocks because of this.

### Destruction order of members

Members are destroyed in reverse declaration order. When a class owns a thread that uses other members of the class, the thread must be declared last:

```cpp run title="member-order.cpp" ub
#include <chrono>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>

class Sampler {
  std::jthread worker_;                    // declared first, so destroyed last
  std::mutex mu_;
  std::vector<int> samples_;
public:
  Sampler()
      : worker_([this](std::stop_token st) {
          while (!st.stop_requested()) {
            std::lock_guard lk(mu_);
            samples_.push_back(42);
          }
        }) {}
  // ~Sampler destroys samples_, then mu_, and only then worker_:
  // until it requests stop and joins, the thread keeps using destroyed members
};

int main() {
  {
    Sampler s;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  std::puts("done");
}
```

`~Sampler`'s body is empty; afterwards `samples_` is destroyed, then `mu_`, and only then does `worker_`'s destructor request stop and join ([[class.dtor#13]]). In between, the thread keeps locking the destroyed mutex and writing into the destroyed vector. Running 5 times without sanitizers in our tests, 1 run terminated with `mutex lock failed: Invalid argument`; TSan reports a data race inside the vector. After moving `worker_` to be declared last, TSan reports nothing.

`jthread`'s destructor joins automatically and so looks like RAII already, but it can only guarantee the thread ends when `worker_` itself is destroyed; it cannot decide the destruction timing of other members on the class's behalf. The general rule: if member A uses member B during its lifetime, declare A after B.

## When to use it

| Situation | Recommendation |
|---|---|
| The resource is a pointer with a dedicated release function | `unique_ptr` with an empty-class deleter |
| The resource is an integer handle or other non-pointer value used everywhere | a move-only handle class, with Rule of zero for everything else |
| One-off cleanup or undo in one function | a scope guard |
| Undo only on failure | a `scope_fail`-style guard, or reorder the steps so no undo is needed |
| Mutual exclusion | `lock_guard`; `scoped_lock` for several locks; `unique_lock` with condition variables or early unlocking |
| Threads | `jthread`, checking the `stop_token` in the thread function |
| Release can fail and the caller needs to know | provide an explicit `close()`; the destructor is only a fallback |
| The resource lives outside the process and survives crashes | a recovery mechanism in addition to RAII |
| Release requires asynchronous waiting | destructors can't `co_await`; use an async scope or an explicit closing coroutine |

## Questions

!!! question "1"
    `UniqueFd::reset` writes the new value into `fd_` first and then closes the old one. The specification of `unique_ptr::reset` requires this order too. What would go wrong the other way round, closing the old value first and assigning afterwards?

<details markdown="1">
<summary>Answer</summary>

The release operation may indirectly access this handle object again. The `unique_ptr` case is the classic one: the object the deleter deletes may itself own this `unique_ptr`, as with the pointer to the next node in a linked list node, so `*this` may be destroyed while the deleter runs. The note in [[unique.ptr.single.modifiers#3]] explains this: assigning first and then calling the deleter means `*this` is in a consistent state while the deleter runs, and `*this` is not accessed afterwards. In the reverse order, others would see an object pointing to a released resource while the deleter runs, and after the deleter returns, the code would write to an object that may no longer exist.
</details>

!!! question "2"
    Which of the two functions below compiles? For the one that does, when does the guard run?

    ```cpp
    auto make_guard() { return scope_exit([] { std::puts("cleanup"); }); }
    auto bad() { scope_exit g([] {}); return g; }
    ```

<details markdown="1">
<summary>Answer</summary>

`make_guard` compiles, `bad` doesn't. The operand of `make_guard`'s return statement is a prvalue, and since C++17 it initializes the caller's result object directly, without needing a copy or move constructor ([[dcl.init.general#15.6.1]]). When the caller writes `auto _ = make_guard();`, the guard runs at the end of the caller's scope; in our tests the output shows the caller's work first, then `cleanup`. `bad` returns a named local variable, and the return statement copy-initializes the result object from it ([[stmt.return#2]]). `g` is implicitly movable, so it is an xvalue here ([[expr.prim.id.unqual#12]]), which needs a move constructor, and that is deleted. The compiler may elide this construction (NRVO, [[class.copy.elision#1]]), but elision is not mandatory, and the selected constructor must still be usable. Clang reports a call to a deleted constructor.
</details>

!!! question "3"
    Besides its destruction order, the `Sampler` in `member-order.cpp` has another problem at construction. What is it?

<details markdown="1">
<summary>Answer</summary>

Members are initialized in declaration order ([[class.base.init#15.3]]). `worker_` is declared first, so its constructor runs first, and when the thread starts, `mu_` and `samples_` have not been constructed yet; the thread immediately locking and writing to them uses objects whose lifetimes have not begun. Moving `worker_` to be declared last fixes both the construction and the destruction problems: the thread starts only after all the members it uses are constructed, and is joined before they are destroyed.
</details>
