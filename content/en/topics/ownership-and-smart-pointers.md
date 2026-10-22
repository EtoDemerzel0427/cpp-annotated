---
title: Ownership and smart pointer design
summary: "Using types to express who is responsible for destroying an object: the four kinds of ownership (unique, shared, borrowed, value semantics), the costs and rules of unique_ptr, shared_ptr and weak_ptr, how to pass smart pointers as function parameters, and out_ptr, indirect, polymorphic and the most common ownership mistakes."
tags: smart pointers, ownership, unique_ptr, shared_ptr, weak_ptr, RAII, topic
updated: 2026-10-19
---

!!! tldr
    - Every dynamically allocated object should have a clear owner responsible for destroying it. There are four kinds of ownership: unique (`unique_ptr`), shared (`shared_ptr`), borrowed (`T&`, `T*`, `weak_ptr`), and value semantics (holding a `T` directly).
    - A `unique_ptr` with a stateless deleter is the same size as a raw pointer and generates the same code; it can't be copied, only moved. When it holds an incomplete type, the enclosing class's destructor, constructors and move assignment must be defined in the `.cpp` where the type is complete.
    - A `shared_ptr` is two pointers plus a control block. `make_shared` allocates only once, but a `weak_ptr` delays release of the whole block; the reference count is thread-safe, while neither the pointed-to object nor the `shared_ptr` variable itself is.
    - Write a smart pointer in a function parameter only to express a change of ownership: a `unique_ptr` by value means taking over, a `shared_ptr` by value means sharing; to just use the object, pass `T&` or `T*`.
    - The most common mistakes are giving the same raw pointer to two `shared_ptr`s, keeping the `get()` of a temporary smart pointer, and `shared_ptr`s referring to each other in a cycle; ASan and LSan catch most of them.

## Who calls delete

```cpp run title="legacy.cpp" ub
#include <cstdio>
struct Widget { int id; };

// the header only has these declarations; nothing says who is responsible for delete
Widget* make_widget(int id);
void    register_widget(Widget* w);   // does the registry keep w? will it delete it?
Widget* find_widget(int id);          // must the caller delete it when done?

static Widget* registry[8];
Widget* make_widget(int id) { return new Widget{id}; }
void register_widget(Widget* w) { registry[w->id] = w; }
Widget* find_widget(int id) { return registry[id]; }
void shutdown() { for (Widget* w : registry) delete w; }

int main() {
  register_widget(make_widget(1));
  delete find_widget(1);   // the caller thinks it should delete
  shutdown();              // the registry deletes again: UB
}
```

All three function signatures are `Widget*`, but they mean completely different things: the first hands over a new object, the second takes it over, and the third only lends it to the caller for a look. The signatures carry none of this information; it relies on documentation and convention. As soon as a convention is misread, the result is a leak or a double free. ASan reports `attempting double-free`.

An object's **owner** is the party responsible for ending its lifetime and releasing its storage. C++ doesn't track ownership: the compiler won't stop two places from `delete`ing the same pointer, nor warn that nothing ever `delete`s it. What you can do is write ownership into the types, so the compiler checks transfers and copies:

```cpp run title="typed.cpp" ok
#include <cstdio>
#include <map>
#include <memory>

struct Widget { int id; };

std::unique_ptr<Widget> make_widget(int id);       // the caller gets ownership
void register_widget(std::unique_ptr<Widget> w);   // the registry takes over ownership
Widget* find_widget(int id);                       // borrowing: may be null, don't delete

std::map<int, std::unique_ptr<Widget>> registry;
std::unique_ptr<Widget> make_widget(int id) { return std::make_unique<Widget>(id); }
void register_widget(std::unique_ptr<Widget> w) { int id = w->id; registry[id] = std::move(w); }
Widget* find_widget(int id) {
  auto it = registry.find(id);
  return it == registry.end() ? nullptr : it->second.get();
}

int main() {
  register_widget(make_widget(1));
  if (Widget* w = find_widget(1)) std::printf("%d\n", w->id);
}
```

Now the signatures themselves state the ownership: returning a `unique_ptr` means handing over, taking a `unique_ptr` by value means taking over, and returning a raw pointer means borrowing. The objects held by the registry are released when `registry` is destroyed, without a single hand-written `delete`.

## Four kinds of ownership

| Ownership | Meaning | Typical types |
|---|---|---|
| Value semantics | The object is part of its holder; copying the holder copies the object | A `T` member, `std::optional<T>`, `std::vector<T>`, C++26's `indirect<T>`, `polymorphic<T>` |
| Unique | Exactly one owner; ownership can be transferred but not copied | `std::unique_ptr<T>` |
| Shared | Several owners; the last one to leave destroys the object | `std::shared_ptr<T>` |
| Borrowed, observing | Uses the object without being responsible for destroying it; the owner must live longer | `T&`, `T*`, `std::string_view`, `std::span`; `std::weak_ptr<T>` can check whether the object still exists |

The order of choice is usually top to bottom: use a value if you can; when it must go on the heap (polymorphism, an incomplete type, large size, ownership transfer), use `unique_ptr`; use `shared_ptr` only when the object really has no single owner and its lifetime is decided jointly by several parties.

A borrower doesn't own the object, and its safety depends entirely on the owner outliving it. Errors of this kind are collectively called dangling; see [[topics/dangling-references]]. In modern code a raw pointer `T*` means borrowing by default; it can be null and can be repointed; `T&` means a borrow that is guaranteed to exist and won't change what it refers to.

Smart pointers are all applications of RAII (Resource Acquisition Is Initialization): the resource is acquired in the constructor and released in the destructor, and since the destructor runs both at the end of a scope and during exception unwinding, release can't be forgotten. The standard puts these types in [[smartptr]], and C++26's value-semantic wrapper types in [[mem.composite.types]].

## `unique_ptr`: unique ownership

`unique_ptr<T, D>` stores a pointer and a [[g:deleter]] `D`, and calls the deleter to dispose of the pointed-to object when it is itself destroyed ([[unique.ptr.general#1]]). The default deleter `default_delete<T>` performs `delete`. The destructor is equivalent to `if (get()) get_deleter()(get());`, so a null pointer is never passed to the deleter ([[unique.ptr.single.dtor#1]]).

### Not copyable, only movable

<div class="compare" markdown="1">

```cpp run title="move.cpp" ok
#include <memory>
#include <utility>
int main() {
  auto a = std::make_unique<int>(1);
  auto b = std::move(a);  // transfer
  return a == nullptr && *b == 1
             ? 0 : 1;
}
```

```cpp run title="copy.cpp" error
#include <memory>
int main() {
  auto a = std::make_unique<int>(1);
  auto b = a;  // error: copy constructor
               // is deleted
}
```

</div>

If it could be copied, two `unique_ptr`s would each `delete` once when destroyed. The standard says every `unique_ptr` specialization is move constructible and move assignable, but not copy constructible or copy assignable ([[unique.ptr.general#4]]). After a move the source is empty, so ownership is in exactly one place at any moment.

So a class with a `unique_ptr` member also can't be copied implicitly: its implicit copy constructor is defined as deleted ([[class.copy.ctor]]). That's usually exactly what you want; for deep copies, see `indirect` below.

### Zero overhead: size and generated code

```cpp run title="size.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <memory>

struct FreeDeleter {                     // stateless function object
  void operator()(void* p) const noexcept { std::free(p); }
};
struct CountingDeleter {                 // stateful: holds a pointer to a counter
  int* count;
  void operator()(int* p) const noexcept { ++*count; delete p; }
};

int main() {
  auto lam = [](int* p) { delete p; };
  std::printf("%zu\n", sizeof(int*));                                     // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int>));                     // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, FreeDeleter>));        // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, decltype(lam)>));      // 8
  std::printf("%zu\n", sizeof(std::unique_ptr<int, void (*)(int*)>));     // 16
  std::printf("%zu\n", sizeof(std::unique_ptr<int, CountingDeleter>));    // 16
  std::printf("%zu\n", sizeof(std::shared_ptr<int>));                     // 16
}
```

The comments are the output with 64-bit libc++. An empty deleter (the default deleter, an empty function object, a lambda without captures) takes no space; the implementation uses the empty base optimization or `[[no_unique_address]]` to overlap it with the pointer. The standard doesn't require this, so the verdict is {{impl}}. A function pointer deleter or a deleter with data has to actually be stored, so the `unique_ptr` doubles in size, and calls through a function pointer usually can't be inlined. So custom deleters should be written as stateless function objects.

The same size isn't enough; the generated code should be the same too. With Clang 23 at `-O2`, the two functions below compile to identical arm64 instructions:

```cpp ok
#include <memory>
void use(int*) noexcept;
void by_raw()   { int* p = new int(42); use(p); delete p; }
void by_smart() { auto p = std::make_unique<int>(42); use(p.get()); }
```

`use` is declared `noexcept`, so neither needs an exception cleanup path. If `use` might throw, `by_smart` gets an extra piece of code that calls `delete` during unwinding, while `by_raw` simply leaks in that case. The only real extra cost appears when passing a `unique_ptr` by value: under the Itanium C++ ABI, types with non-trivial destructors can't be passed in registers; see the ABI section at the end of [[unique.ptr]].

### Custom deleters and arrays

Resources from C libraries are released with dedicated functions; write that as a deleter and the resource can be handed to `unique_ptr`:

```cpp
struct fclose_deleter {
  void operator()(std::FILE* f) const noexcept { std::fclose(f); }
};
using file_ptr = std::unique_ptr<std::FILE, fclose_deleter>;
```

The deleter is part of the `unique_ptr` type: `unique_ptr<FILE, fclose_deleter>` and `unique_ptr<FILE, other_deleter>` are unrelated types. A deleter can also define a nested type `pointer`, letting `unique_ptr` manage handles that aren't pointers, such as file descriptors ([[unique.ptr.single.general#4]]).

Arrays need `unique_ptr<T[]>`, whose default deleter calls `delete[]` and which provides `operator[]`:

```cpp run title="array.cpp" ub
#include <cstdio>
#include <memory>
int main() {
  auto a = std::make_unique<int[]>(4);    // 4 ints, value-initialized to 0
  a[3] = 7;
  std::unique_ptr<int> wrong(new int[4]); // compiles; destruction frees the result of new[] with delete
  std::printf("%d\n", a[3]);
}
```

When `wrong` is destroyed it performs `delete` on an object created by array `new`, which is UB ([[expr.delete#2]]). ASan on macOS doesn't check this mismatch by default; with `ASAN_OPTIONS=alloc_dealloc_mismatch=1` it reports `alloc-dealloc-mismatch (operator new [] vs operator delete)`. In real code a dynamic array should almost always be a `std::vector`, which also remembers its length.

### Incomplete types: the pimpl rule

The **pimpl** (pointer to implementation) idiom moves a class's private members into an `Impl` struct defined only in the `.cpp`, leaving just a `unique_ptr` to it in the header. When implementation details change, code that includes the header doesn't need recompiling.

[[unique.ptr.general#4]] allows `T` to be an incomplete type, but `default_delete<T>::operator()` requires `T` to be complete ([unique.ptr.dltr.dflt] ¶3, see [[unique.ptr.dltr]]). So the key is where `~unique_ptr<Impl>` gets instantiated:

```cpp title="widget-bad.cpp" error
#include <memory>
class Widget {
public:
  Widget() {}               // defined in the class: must be able to destroy an already constructed impl
  // no destructor declared: the implicit destructor is defined at first use
private:
  struct Impl;
  std::unique_ptr<Impl> impl;
};
void user() { Widget w; }   // error: ~unique_ptr<Impl> instantiated here
```

libc++ reports `sizeof` applied to the incomplete type `Widget::Impl`, with the instantiation chain pointing to the constructor on line 4. Three rules together determine which members instantiate `~unique_ptr<Impl>`:

1. Special member functions that are implicitly declared or `= default` in the class are implicitly defined where they are odr-used ([[dcl.fct.def.default#5]]). Without a written destructor, `~Widget` is defined in `user()`, where `Impl` is incomplete.
2. A constructor must be able to destroy already constructed members if an exception occurs, so a non-delegating constructor potentially invokes the destructor of every member ([[class.base.init#14]]). The in-class `Widget() {}` therefore also needs `~unique_ptr<Impl>`.
3. Move assignment destroys the old `Impl`, and an in-class `= default` move assignment is defined where it is used, so it also needs the complete type.

The solution is to only declare these members in the header and define them after `Impl` is complete. A function written `= default` after its first declaration is defined where the `= default` is written ([[dcl.fct.def.default#5]]):

```cpp title="widget.h"
#include <memory>
class Widget {
public:
  Widget();
  ~Widget();                              // declaration only
  Widget(Widget&&) noexcept;
  Widget& operator=(Widget&&) noexcept;
  int value() const;
private:
  struct Impl;                            // incomplete type
  std::unique_ptr<Impl> impl;
};
```

```cpp title="widget.cpp" ok
#include "widget.h"
#include <string>
struct Widget::Impl { int v = 42; std::string name; };
Widget::Widget() : impl(std::make_unique<Impl>()) {}
Widget::~Widget() = default;              // Impl is complete here
Widget::Widget(Widget&&) noexcept = default;
Widget& Widget::operator=(Widget&&) noexcept = default;
int Widget::value() const { return impl->v; }
```

Compiling and running these two files together with a `main.cpp` that move-constructs and move-assigns `Widget`s, neither ASan nor UBSan reports anything.

!!! impl "An in-class `= default` move constructor"
    By rule 2, an in-class `Widget(Widget&&) = default;` is also a non-delegating constructor and likewise potentially invokes `impl`'s destructor. But a function defaulted on its first declaration is only implicitly defined when it is odr-used ([[dcl.fct.def.default#5]]), so writing just this line without ever moving a `Widget` causes no error; with Clang 23, as soon as `Widget b(std::move(a));` appears it reports `invalid application of 'sizeof' to an incomplete type`, noting "in defaulted move constructor for 'Widget' first required here". The safe approach is to put all special members in the `.cpp`.

`shared_ptr` doesn't have this problem: it stores the means of deletion in the control block at construction, so destruction doesn't need to know `T` ([[util.sharedptr]]).

### `make_unique`

`make_unique<T>(args...)` returns `unique_ptr<T>(new T(std::forward<Args>(args)...))` ([[unique.ptr.create#2]]). The reasons to use it are that `new` doesn't appear in the code and the type name needn't be written twice.

In C++14 there was one more reason: `f(std::unique_ptr<T>(new T), g())` could execute `new T` first, then a throwing `g()`, and the object leaked before the `unique_ptr` was constructed. C++17 specifies that the initializations of parameters don't interleave ([[expr.call#8]]), so this leak can no longer happen.

`make_unique<T[]>(n)` value-initializes the elements; `make_unique_for_overwrite` default-initializes them, suitable for large buffers that are about to be overwritten entirely. The full table is in [[unique.ptr]].

## `shared_ptr`: shared ownership

### Two pointers and a control block

All `shared_ptr`s and `weak_ptr`s in a group sharing ownership point to the same **control block**, which stores the strong count, the weak count, the deleter and the allocator. Each `shared_ptr` itself stores two pointers: the stored pointer returned by `get()`, and the control block pointer. When the strong count reaches zero the object is destroyed; when the weak count also reaches zero the control block is freed. The standard doesn't mention control blocks; it's the model shared by all implementations; see [[util.sharedptr]].

The last line of `size.cpp` above shows that `shared_ptr<int>` is 16 bytes.

### `make_shared`: one allocation, and its cost

```cpp run title="alloc.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <new>

static int allocs = 0, frees = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { ++frees; std::free(p); }
void operator delete(void* p, std::size_t) noexcept { ++frees; std::free(p); }

struct Big {
  char data[1024];
  ~Big() { std::puts("  ~Big"); }
};

int main() {
  {
    std::shared_ptr<Big> a(new Big);            // new Big + control block
    std::printf("shared_ptr(new): allocs=%d\n", allocs);
  }
  allocs = frees = 0;
  std::weak_ptr<Big> w;
  {
    auto b = std::make_shared<Big>();           // object and control block allocated together
    std::printf("make_shared:     allocs=%d\n", allocs);
    w = b;
  }                                             // strong count reaches zero: ~Big runs
  std::printf("after last shared_ptr: frees=%d\n", frees);
  w.reset();                                    // weak count reaches zero: the whole block is freed
  std::printf("after weak_ptr reset:  frees=%d\n", frees);
}
```

Output:

```text
shared_ptr(new): allocs=2
  ~Big
make_shared:     allocs=1
  ~Big
after last shared_ptr: frees=0
after weak_ptr reset:  frees=1
```

`shared_ptr<Big>(new Big)` allocates twice, once for the object and once for the control block. `make_shared` puts the object inside the control block and allocates only once; the standard recommends that implementations perform at most one allocation ([[util.smartptr.shared.create#7.1]]), which is a recommendation rather than a requirement, so the verdict is {{impl}}.

The cost is in the second half. When the last `shared_ptr` goes away, `~Big` runs immediately, but the object and the control block are in the same piece of memory, so as long as a `weak_ptr` remains, that 1 KB can't be returned. A large object combined with long-lived `weak_ptr`s (a cache, for example) can hold on to a considerable amount of memory. In that case use `shared_ptr<T>(new T)` instead, and the object's memory can be freed when the strong count reaches zero.

### Type erasure of the deleter

```cpp run title="erase.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <type_traits>
#include <vector>

struct FreeDeleter { void operator()(void* p) const noexcept { std::free(p); } };
struct LogDeleter {
  const char* tag;
  void operator()(int* p) const { std::printf("delete %s\n", tag); delete p; }
};

int main() {
  // unique_ptr: the deleter is part of the type
  static_assert(!std::is_same_v<std::unique_ptr<int, FreeDeleter>,
                                std::unique_ptr<int, LogDeleter>>);
  // shared_ptr: the deleter goes into the control block; type and size are unchanged
  std::vector<std::shared_ptr<int>> v;
  v.emplace_back(new int(1));
  v.emplace_back(static_cast<int*>(std::malloc(sizeof(int))), FreeDeleter{});
  v.emplace_back(new int(3), LogDeleter{"third"});
  std::printf("%zu %d\n", sizeof(v[2]),
              std::get_deleter<LogDeleter>(v[2]) != nullptr);  // 16 1
}
```

The deleter of `shared_ptr<T>` isn't in its type. The constructor `shared_ptr(Y* p, D d)` stores `d` together with the actual type `Y` in the control block ([[util.smartptr.shared.const#11]]), and destruction calls it through a virtual function of the control block. This is [[g:type-erasure]]: one `vector<shared_ptr<int>>` can hold objects released in three different ways.

The same mechanism lets `shared_ptr<Base>(new Derived)` correctly destroy the `Derived` even when `Base` has no virtual destructor, and lets `shared_ptr<void>` destroy any object. The cost is one extra vtable pointer in the control block and one extra indirect call per destruction.

### The aliasing constructor

```cpp
auto p = std::make_shared<Person>("Ada", 36);
std::shared_ptr<int> age(p, &p->age);   // owns the whole Person, points to its member
```

The aliasing constructor separates the stored pointer from the owned object: `age` keeps the whole `Person` alive, while dereferencing it yields an `int` ([[util.smartptr.shared.const#14]]). It suits handing a subobject to code that only knows the subobject's type, while ensuring the enclosing object isn't destroyed first. The four cast functions such as `static_pointer_cast` are implemented with it too. Details and pitfalls are in [[util.smartptr.shared]].

### Thread safety: count, object, variable

The thread safety guarantee of `shared_ptr` is a single sentence ([[util.smartptr.shared.general#5]]): for the purpose of determining data races, member functions access only the `shared_ptr` and `weak_ptr` objects themselves, not the objects they point to; changes in `use_count()` don't count as modifications that may cause data races. This gives three levels:

| What is accessed | Several threads doing it at once | Conclusion |
|---|---|---|
| The reference count: each copies and destroys different `shared_ptr` objects | The count is modified concurrently | Safe; the implementation must use atomic operations |
| The pointed-to object: writing `*p` through their own copies | The same object is written concurrently | Data race, nothing to do with `shared_ptr` |
| The same `shared_ptr` variable: one thread assigns, another reads | The same object is read and written concurrently | Data race; use `atomic<shared_ptr<T>>` |

```cpp run title="race-object.cpp" ub
#include <memory>
#include <thread>

int main() {
  auto p = std::make_shared<int>(0);
  std::jthread t([p] { ++*p; });   // the thread holds its own copy: the count is fine
  ++*p;                            // two threads write the same int: data race
}
```

`-fsanitize=thread` reports a `data race` at the `++*p` in the lambda. Capturing `p` by value only guarantees the `int` isn't freed before both threads are done with it; it doesn't synchronize access to the `int`. Either make the object immutable (`shared_ptr<const T>`), or have the object do its own locking.

The third row's case is shown by the example in [[util.sharedptr]]: a reader copying `p` while a writer assigns to `p` may read a new stored pointer paired with the old control block. C++20's `std::atomic<std::shared_ptr<T>>` ([[P0718R2]]) allows a `shared_ptr` variable to be read and written concurrently: reading the pointer and incrementing the count happen within one atomic operation, while decrementing the old object's count, destroying it and freeing it happen after the atomic operation ([[util.smartptr.atomic.general#2]]). At the time of writing libc++ in our tests doesn't implement this partial specialization yet; `std::atomic<std::shared_ptr<int>>` falls to the primary template and is rejected by its `static_assert` requiring `T` to be trivially copyable.

## `weak_ptr`: a non-owning observer

### Cycles

```cpp run title="cycle.cpp"
#include <memory>
#include <string>
#include <vector>

struct Child;
struct Parent {
  std::vector<std::shared_ptr<Child>> children;
};
struct Child {
  std::shared_ptr<Parent> parent;   // points back to its owner: forms a cycle
  std::string name;
};

void build() {
  auto p = std::make_shared<Parent>();
  auto c = std::make_shared<Child>();
  c->parent = p;
  p->children.push_back(c);
}   // after p and c are destroyed, both strong counts are still 1, and neither is destroyed

int main() { build(); }
```

`shared_ptr` only counts; it has no cycle detection. When `build()` returns, the `Parent` is owned by `Child::parent` and the `Child` is owned by `Parent::children`; both counts stop at 1, and neither object is ever destroyed. The leak itself isn't UB; the program is well-formed and its behavior is defined, it's just that this memory is never freed and the cleanup in the destructors never runs.

Compiled with `-fsanitize=address -O1` and run with `ASAN_OPTIONS=detect_leaks=1`, LeakSanitizer reports:

```text
==ERROR: LeakSanitizer: detected memory leaks
Indirect leak of 64 byte(s) in 1 object(s) allocated from:
    ... in main cycle.cpp
Indirect leak of 48 byte(s) in 1 object(s) allocated from:
Indirect leak of 16 byte(s) in 1 object(s) allocated from:
SUMMARY: AddressSanitizer: 128 byte(s) leaked in 3 allocation(s).
```

All three blocks are indirect leaks: each is reachable from another leaked block, and none is lost directly from the program's roots, which is the signature of a cycle. LSan judges reachability by conservative scanning, and stale pointer values left on the stack can make it think the objects are still reachable; in an `-O0` build in our tests it sometimes doesn't report this cycle. ASan on macOS doesn't enable leak detection by default; you have to set `detect_leaks=1` explicitly.

The fix is to decide the direction of ownership: the parent owns the children, and a child points back to its parent with a `weak_ptr<Parent>`. A `weak_ptr` increments the weak count, which keeps the control block alive but not the object.

### `lock()` and races

`weak_ptr` has no `operator*`, `operator->` or `get()`. The only way to access the object is `lock()`, which atomically checks whether the object is alive and obtains a `shared_ptr` ([[util.smartptr.weak.obs#3]]):

```cpp run title="observer.cpp" ok
#include <cstdio>
#include <memory>
#include <set>

struct Listener {
  int id;
  void on_event() const { std::printf("listener %d\n", id); }
};

class Subject {
  // doesn't own the listeners; ordered by ownership, so key order doesn't change after expiry
  std::set<std::weak_ptr<Listener>, std::owner_less<>> listeners_;
public:
  void subscribe(const std::shared_ptr<Listener>& l) { listeners_.insert(l); }
  void notify() {
    for (auto it = listeners_.begin(); it != listeners_.end();) {
      if (auto l = it->lock()) { l->on_event(); ++it; }   // atomically check and acquire ownership
      else it = listeners_.erase(it);                     // already destroyed: clean up along the way
    }
  }
  std::size_t size() const { return listeners_.size(); }
};

int main() {
  Subject s;
  auto a = std::make_shared<Listener>(1);
  {
    auto b = std::make_shared<Listener>(2);
    s.subscribe(a);
    s.subscribe(b);
    s.notify();                       // listener 1, listener 2, order unspecified
  }                                   // b destroyed, Subject doesn't know
  s.notify();                         // only listener 1
  std::printf("%zu\n", s.size());     // 1
}
```

The output is `listener 1`, `listener 2`, `listener 1`, `1`. `if (auto l = it->lock())` combines checking and using into one step: the `l` obtained guarantees the object stays alive throughout the `if` block, even if another thread is destroying the last owner.

Calling `expired()` and then `lock()` is wrong. After `expired()` returns `false` and before `lock()`, another thread may destroy the object; `lock()` returns a null pointer, and the following dereference is UB. Only a `true` from `expired()` is reliable, because a destroyed object never comes back.

### `owner_less`: comparing by ownership

The `std::set` in the example uses `std::owner_less<>` rather than the default `std::less`. `weak_ptr` has no `<` at all: its stored pointer may already dangle, and comparing by address makes no sense. `owner_less` calls `owner_before`, which compares which ownership group the two belong to, in effect the address of the control block ([[util.smartptr.ownerless#2]]). The control block survives the object's destruction, so key order doesn't change and the `set`'s invariant isn't broken.

`shared_ptr` also has both kinds of comparison: `==` compares stored pointers, while `owner_before` and `owner_equal` compare ownership. A `shared_ptr` made by the aliasing constructor has the same ownership as the original but a different stored pointer. C++26 also adds the `owner_hash` and `owner_equal` function objects, so `weak_ptr` can be a key in unordered containers; see [[util.smartptr.ownerless]].

## `enable_shared_from_this`

Sometimes an object needs a `shared_ptr` to itself from within its own member function, for example to hand itself to an asynchronous callback while guaranteeing it is still alive when the callback runs. Writing `std::shared_ptr<Session>(this)` directly creates a second control block, and it and the existing group outside each delete the object once.

```cpp run title="session.cpp" ok
#include <cstdio>
#include <functional>
#include <memory>

struct Session : std::enable_shared_from_this<Session> {
  // the callback shares ownership of the Session: the object is guaranteed alive when it runs
  std::function<void()> keep_alive_callback() {
    return [self = shared_from_this()] { self->done(); };
  }
  // the callback only observes: does nothing if the object has been destroyed
  std::function<void()> weak_callback() {
    return [w = weak_from_this()] {
      if (auto self = w.lock()) self->done();
      else std::puts("session gone");
    };
  }
  void done() { std::puts("done"); }
};

int main() {
  std::function<void()> cb1, cb2;
  {
    auto s = std::make_shared<Session>();
    cb1 = s->keep_alive_callback();
    cb2 = s->weak_callback();
  }
  cb1();          // done: the self in cb1 keeps the Session alive
  cb1 = nullptr;  // the last owner goes away
  cb2();          // session gone

  Session local;  // not owned by any shared_ptr
  try { local.keep_alive_callback(); }
  catch (const std::bad_weak_ptr&) { std::puts("bad_weak_ptr"); }
}
```

The output is `done`, `session gone`, `bad_weak_ptr`. `enable_shared_from_this<T>` hides a `weak_ptr` in the base class (exposition-only name *weak-this*), and `shared_from_this()` returns `shared_ptr<T>(weak-this)` ([[util.smartptr.enab#7]]). It isn't the base class itself that fills in *weak-this*, but the `shared_ptr` constructor or `make_shared` that creates the first ownership group ([[util.smartptr.shared.const#1]]). Its pitfalls follow from this:

- **It can't be used in the constructor.** The object is still being constructed, `make_shared` hasn't yet reached the point of filling in *weak-this*, and `shared_from_this()` throws `bad_weak_ptr`. The same holds in the destructor, when the strong count has already reached zero. If the object needs to register itself elsewhere on creation, use a private constructor and a static factory function that registers after `make_shared`.
- **The object must already be owned by a `shared_ptr`.** Calling `shared_from_this()` on a stack object or an object owned by a `unique_ptr` throws `bad_weak_ptr`. It throws since C++17; before that it was UB.
- **The base class must be accessible.** `class Session : std::enable_shared_from_this<Session>` is private inheritance; the `shared_ptr` constructor can't see this base, doesn't fill in *weak-this*, gives no diagnostic, and `shared_from_this()` always throws.
- **It doesn't prevent the wrong form.** Even after inheriting from it, `shared_ptr<Session>(this)` still creates a second control block.

The two callbacks represent two designs. `keep_alive_callback` extends the object's lifetime, suited to cases where the object must be alive until the callback runs; `weak_callback` doesn't extend it, and the callback automatically becomes a no-op once the object is destroyed, suited to timers, event subscriptions and the like that shouldn't in turn keep the object alive. More details are in [[util.smartptr.enab]].

## How to pass smart pointers as function parameters

The parameter type states what the function does with ownership. The table below follows F.7 and R.30–R.37 of the C++ Core Guidelines:

| Parameter | What it expresses | At the call site |
|---|---|---|
| `T&`, `const T&`, `T*` | Only uses the object, no ownership involved; `T*` may be null | `f(*p)`, `f(p.get())` |
| `unique_ptr<T>` (by value) | The function takes over ownership | `f(std::move(p))` |
| `unique_ptr<T>&` | The function may reset or replace the caller's pointer | `f(p)` |
| `shared_ptr<T>` (by value) | The function will keep a share of ownership, for example in a member | `f(p)` or `f(std::move(p))` |
| `shared_ptr<T>&` | The function may reset or replace the caller's pointer | `f(p)` |
| `const shared_ptr<T>&` | The function may or may not decide to keep a share of ownership | `f(p)` |

The most common mistake is writing the parameter as `const shared_ptr<T>&` or `shared_ptr<T>` when the function only wants to use the object. The former ties the function to `shared_ptr`, so stack objects and objects owned by a `unique_ptr` can't be passed; the latter does an atomic increment and decrement on every call. To just use the object, pass `T&`.

### Taking over ownership: by value, not by rvalue reference

```cpp run title="sink.cpp" ok
#include <cstdio>
#include <memory>
#include <utility>
#include <vector>

std::vector<std::unique_ptr<int>> store;
void sink_val(std::unique_ptr<int> p) { store.push_back(std::move(p)); }
void sink_ref(std::unique_ptr<int>&& p) {          // may or may not take over
  if (*p > 10) store.push_back(std::move(p));
}

int main() {
  auto a = std::make_unique<int>(1);
  auto b = std::make_unique<int>(1);
  sink_val(std::move(a));
  sink_ref(std::move(b));
  std::printf("%d %d\n", a == nullptr, b == nullptr);   // 1 0
}
```

With pass by value, the parameter `p` is move-constructed from the argument at the call site, so `a` is certainly empty as soon as the call ends; the transfer of ownership is plain to see. With pass by rvalue reference, `std::move(b)` is just a cast, the function body decides whether to actually move from it, and the caller can't be sure of `b`'s state afterwards.

### A borrowed reference must not come from a smart pointer that may be reassigned

```cpp run title="pin.cpp" ub
#include <cstdio>
#include <memory>
#include <string>

struct Config { std::string name = std::string(64, 'c'); };
std::shared_ptr<Config> g_config = std::make_shared<Config>();

void reload() { g_config = std::make_shared<Config>(); }   // the old Config is destroyed

void print(const Config& c) {
  reload();                            // indirectly frees the object c refers to
  std::printf("%zu\n", c.name.size()); // UB
}

int main() {
  print(*g_config);
}
```

`print` taking `const Config&` is the right design; the problem is at the call site: the reference comes from the global `g_config`, and before using `c`, `print` indirectly assigns to `g_config`, so the last owner of the old object goes away. ASan reports `heap-use-after-free` in `print`. This is what Core Guidelines R.37 means by not taking a borrow from a smart pointer that may be modified through an alias. The fix is to make a copy at the call site first, so a local variable pins the object: `auto pin = g_config; print(*pin);`, which we verified prints `64`.

## `out_ptr` and `inout_ptr`: handing off to C interfaces

C interfaces often hand out newly allocated resources through a `T**` parameter. C++23's `std::out_ptr` ([[P1132R8]]) adapts a smart pointer to such a parameter:

```cpp run title="out-ptr.cpp" ok
#include <cstdio>
#include <memory>

// a typical C interface: hands out a new resource via T**, with a dedicated release function
extern "C" {
struct db { int handle; };
int  db_open(const char* name, db** out) {
  if (!name) return -1;            // doesn't write *out on failure
  *out = new db{42};
  return 0;
}
void db_close(db* d) { delete d; }
}

struct db_closer {
  void operator()(db* d) const noexcept { db_close(d); }
};
using db_ptr = std::unique_ptr<db, db_closer>;

int main() {
  db_ptr conn;
  if (db_open("test", std::out_ptr(conn)) != 0) return 1;
  std::printf("%d\n", conn->handle);   // 42; db_close is called when leaving the scope
}
```

`std::out_ptr(conn)` constructs a temporary object that first empties `conn`, then hands the address of an internal raw pointer to the C function; when the temporary is destroyed at the end of the full-expression, it `reset`s the pointer written by the C function into `conn`. There is no raw pointer variable to manage by hand along the way, and if the C function fails and writes nothing, `conn` stays empty.

Two things to note. The result is written back only at the end of the full-expression, so reading `conn` within the same expression still sees a null pointer. When the C function needs to read and itself release the old value, use `std::inout_ptr` instead, which at the end calls `release()` on the old value rather than deleting it. `shared_ptr` with `out_ptr` must be given an explicit deleter or it's ill-formed, because C resources should almost never be released with `delete`; `shared_ptr` with `inout_ptr` is always ill-formed, because a `shared_ptr` can't give up unique ownership ([[out.ptr.t#3]], [[inout.ptr.t#3]]). The rules item by item are in [[smartptr.adapt]].

## Value-semantic alternatives: `indirect` and `polymorphic` {{c++26}}

There are three common reasons to put a member on the heap: the member's type is incomplete at that point (pimpl, recursive data structures); the member is large and you want the enclosing object smaller and faster to move; the member's dynamic type is only known at run time. Using a `unique_ptr` for such a member costs the enclosing class its value semantics:

```cpp
struct Shape { virtual ~Shape() = default; virtual double area() const = 0; };

struct Scene {
  std::unique_ptr<Body> body;                 // pimpl or a large object
  std::vector<std::unique_ptr<Shape>> shapes; // polymorphic members
  void touch() const { body->dirty = true; }  // even a const function can modify *body
};
// Scene can't be copied: copy constructor and copy assignment must be hand-written, and Shape must provide a virtual clone()
// body may be null: every access has to consider it
```

C++26's `std::indirect<T>` and `std::polymorphic<T>` ([[P3019R14]]) treat an object on the heap as a value:

```cpp
#include <memory>
#include <vector>

struct Scene {
  std::indirect<Body> body;                    // copying Scene copies the Body
  std::vector<std::polymorphic<Shape>> shapes; // copied by dynamic type, no clone() needed
  // void touch() const { body->dirty = true; }  // error: here *body is a const Body&
};

void demo() {
  Scene a;                                     // body default-constructs a Body; not null
  a.shapes.emplace_back(std::in_place_type<Circle>, 1.0);
  Scene b = a;                                 // the implicit copy is a deep copy
}
```

At the time of writing libc++ in our tests doesn't implement these two classes yet, so the two snippets above haven't been compiled and carry no verdict. The following conclusions come from the draft:

- **Copying copies the value.** `indirect`'s copy constructor constructs a new `T` from `*other` ([[indirect.ctor#9]]); `polymorphic` uses the copy constructor of the owned object's actual type `U` ([[polymorphic.ctor#8]]), so there is no slicing. To guarantee copying always works, `polymorphic` requires `U` to be copyable at construction ([[polymorphic.ctor#12]]).
- **`const` propagates.** `operator*` of a `const indirect<T>` returns `const T&`, and `operator->` returns `const_pointer` ([[indirect.obs]]).
- **No empty state.** Default construction also allocates and constructs a `T` ([[indirect.ctor#5]]). Only after being moved from can it be [[g:valueless]] ([[indirect.general#1]]), which can be queried with `valueless_after_move()`. `polymorphic`'s move constructor is even allowed to move-construct a new object instead of taking over the pointer, to permit a small object optimization, so it isn't necessarily valueless after being moved from ([[polymorphic.ctor#10]]).
- **`T` may be incomplete.** As with `unique_ptr`, the destructor requires `T` to be complete, and the pimpl rule still applies.
- **`polymorphic` destroys by actual type** ([[polymorphic.dtor#2]]), so the base class doesn't need a virtual destructor.

| Member type | Storage location | Can be empty | Copying the enclosing class | `const` propagation |
|---|---|---|---|---|
| `T` | Inside the object | No | Copies the `T` | Yes |
| `unique_ptr<T>` | Heap | Yes | Can't be implicitly copied | No |
| `shared_ptr<T>` | Heap | Yes | Both enclosing objects share the same `T` | No |
| `indirect<T>` | Heap | Only after being moved from | Copies the `T` | Yes |
| `polymorphic<T>` | Heap, or an internal small buffer of the implementation | Only after being moved from | Copies by dynamic type | Yes |

Using a `shared_ptr` member to gain copyability is common but wrong: the two copied enclosing objects share the same inner object, and modifying one affects the other, which isn't value semantics. The full rules for both are in [[indirect]] and [[polymorphic]], and the design motivation in [[mem.composite.types]].

## Common mistakes

| Mistake | Consequence | Can it be detected |
|---|---|---|
| Giving the same raw pointer to two `shared_ptr`s | Two control blocks, each deletes once: UB | ASan: `attempting double-free` |
| Writing `shared_ptr<T>(this)` in a member function | Same as above | Same as above; use `shared_from_this()` instead |
| Keeping the `get()` of a temporary smart pointer | Dangling pointer: UB | Clang `-Wdangling-gsl`; ASan: `heap-use-after-free` |
| `shared_ptr`s referring to each other | Cycle, never freed | LSan: `Indirect leak` |
| `unique_ptr<Base>` pointing to a derived class whose `Base` destructor isn't virtual | UB ([[expr.delete#3]]) | No compiler error; see [[unique.ptr]] |
| Not catching the return value of `release()` | Leak | LSan |
| Calling `shared_from_this()` in a constructor | Throws `bad_weak_ptr` | Run-time exception |

Examples of the first two:

```cpp run title="two-owners.cpp" ub
#include <memory>
struct Node { int v = 0; };
int main() {
  Node* raw = new Node;
  std::shared_ptr<Node> a(raw);
  std::shared_ptr<Node> b(raw);   // second control block
}                                 // b and a each delete once
```

Each time a `shared_ptr` is constructed from a raw pointer, a new ownership group is created. Constructing `b` violates the precondition that `delete raw` must have well-defined behavior ([[util.smartptr.shared.const#5]]), since `raw` already belongs to another group. The way to avoid it is never to let the raw pointer appear at all: use `make_shared`, and when you need a cast, use `static_pointer_cast`, not `shared_ptr<D>(static_cast<D*>(b.get()))`.

An example of keeping `get()`:

```cpp run title="get.cpp" ub
#include <cstdio>
#include <memory>
#include <string>

std::unique_ptr<std::string> load() {
  return std::make_unique<std::string>("a string long enough to be on the heap");
}

int main() {
  std::string* s = load().get();   // the temporary unique_ptr is destroyed at the end of this line
  std::printf("%zu\n", s->size()); // UB: the object has been deleted
}
```

Clang 23 gives a `-Wdangling-gsl` warning saying the object backing the pointer will be destroyed at the end of the full-expression, and ASan reports `heap-use-after-free`. What `get()` returns is a borrow, valid no longer than the owner that issued it. The full picture of this class of problem is in [[topics/dangling-references]].

## Questions

!!! question "1"
    A class has a `std::unique_ptr<Impl> impl;` member; the header declares `~Widget();` and the `.cpp` defines `Widget::~Widget() = default;`, but the header also has an in-class definition `Widget(int x) : impl(nullptr) { (void)x; }`. Does code that includes this header and creates `Widget(1)` compile?

<details markdown="1">
<summary>Answer</summary>

No. `Widget(int)` is a non-delegating constructor, and by [[class.base.init#14]] it potentially invokes the destructor of every member, so that already constructed members can be destroyed if a later member's initialization throws. That requires instantiating `~unique_ptr<Impl>`, and in turn `default_delete<Impl>::operator()`, which requires `Impl` to be complete ([unique.ptr.dltr.dflt] ¶3, see [[unique.ptr.dltr]]). It doesn't matter that `impl` is initialized to a null pointer; the decision is made at compile time. This constructor must also move to the `.cpp`.
</details>

!!! question "2"
    After `auto sp = std::make_shared<std::vector<char>>(100'000'000);`, the program stores `std::weak_ptr w = sp;` in a long-lived cache and then calls `sp.reset()`. When are those 100 MB returned to the system? What about with `std::shared_ptr<std::vector<char>>(new std::vector<char>(100'000'000))`?

<details markdown="1">
<summary>Answer</summary>

In both forms, the strong count reaches zero at `sp.reset()` and the `vector`'s destructor runs immediately; its 100 MB buffer was allocated separately by the `vector` itself and is freed at that point. What the control block delays freeing is only the few dozen bytes of the `vector` object itself. The delayed release of `make_shared` matters only when `T` itself is large, as in `make_shared<std::array<char, 100'000'000>>()`: those 100 MB are inside the control block and can only be returned once the `weak_ptr` in the cache is destroyed too.
</details>

!!! question "3"
    A function has the signature `void attach(std::shared_ptr<Logger> log);`, and its implementation is just `log->write("attached");` without keeping `log`. What's wrong with this signature? What should it be changed to?

<details markdown="1">
<summary>Answer</summary>

Taking a `shared_ptr` by value says the function will keep a share of ownership, but here it only uses the object. There are two costs: every call does an atomic increment and decrement; and the caller must hold a `shared_ptr`, so a `Logger` on the stack or one owned by a `unique_ptr` can't be passed. It should be `void attach(Logger& log);`, called as `attach(*p)`. If the `Logger` might not exist, use `Logger*`.
</details>
