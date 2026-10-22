---
title: Passkey and attorney-client
summary: A friend gets every private member at once. Passkey restricts a single public function to chosen callers, attorney-client forwards only selected private members; plus the gaps that `{}` aggregate initialization, make_shared, explicit instantiation and static reflection leave in access control.
tags: access control, friend, passkey, attorney-client, make_shared, idiom
updated: 2026-10-19
---

!!! tldr
    - A friend gets all of a class's private and protected members at once, and friendship is neither inherited nor transitive. To let through only one function, or only one caller, you need something else.
    - Passkey gives a public function one extra by-value parameter of an empty type `Key`. `Key`'s constructor is private, and only the chosen caller is its friend. In our tests on arm64 and x86-64 the empty `Key` occupies no register, and the generated code is the same as without it.
    - Up to C++17, a private `Key() = default;` does not stop `Key` from being an aggregate, so anyone can bypass it with `{}`. From C++20, a class with a user-declared constructor is not an aggregate. `Key() {}` or `explicit Key() = default;` is safe in every version.
    - `make_shared` calls the constructor from inside the standard library, so a private constructor cannot be used with it. Making the constructor public but requiring a private nested `Key` parameter lets you use `make_shared` while still keeping outsiders out.
    - Attorney-client uses an intermediate class that forwards only selected private members. Explicit instantiation does not check access for template arguments, and neither do C++26 splice expressions; neither back door belongs in production code.

## Friendship grants too much

```cpp title="engine.cpp" ok
class Engine {
  int rpm_ = 0;
  int fuel_ = 100;
  void set_rpm(int r) { rpm_ = r; }
  void drain_fuel() { fuel_ = 0; }
  friend class Mechanic;   // intent: only let Mechanic call set_rpm
};

class Mechanic {
public:
  void tune(Engine& e) { e.set_rpm(800); }
  void oops(Engine& e) { e.drain_fuel(); }   // also allowed
};
```

A **friend** ([[g:friend|friend]]) is a function or class named by a class that may name that class's private and protected members ([[class.friend#1]]). The grant is all or nothing: `Mechanic` only needs `set_rpm`, but it also gets `rpm_`, `fuel_` and `drain_fuel`. From then on, `Engine`'s invariants are maintained not only by its own member functions but by every line of `Mechanic` too.

You can make just one member function a friend, e.g. `friend void Mechanic::tune(Engine&);`. This narrows the calling side, but the accessed side is still every member. And because the declaration uses a qualified name, `tune` has to be looked up in `Mechanic`, so `Engine`'s header must first see the complete definition of `Mechanic`.

¶9 also says friendship is neither inherited nor transitive:

```cpp title="friend-not-inherited.cpp" error
class Engine {
  void set_rpm(int) {}
  friend class Mechanic;
};

class Mechanic {
  friend class Helper;
public:
  void tune(Engine& e) { e.set_rpm(800); }   // OK
};

class Apprentice : public Mechanic {
public:
  void tune2(Engine& e) { e.set_rpm(900); }  // error: friendship is not inherited
};

class Helper {
public:
  void poke(Engine& e) { e.set_rpm(1); }     // error: friendship is not transitive
};
```

Clang 23 reports `'set_rpm' is a private member of 'Engine'` for both. Friendship is a grant written to a specific class; it does not spread through derivation and cannot be delegated. Both idioms below build on these two rules: put an intermediate type between the granting side and the using side, and let it decide what gets through.

| Approach | Who gets access | To what | Where the change goes |
|---|---|---|---|
| `friend class X` | every member of X | all private and protected members | the accessed class |
| `friend void X::f()` | one member function | all private and protected members | the accessed class, which then depends on X's definition |
| passkey | classes that can construct `Key` | the few public functions taking a `Key` parameter | one extra parameter in the function signature |
| attorney-client | friends of the attorney | the few private members the attorney forwards | one extra intermediate class |

## Passkey: putting access into a parameter type

```cpp run title="passkey.cpp" ok
#include <cstdio>

template <class T>
class Key {
  friend T;                // C++11: a template parameter can be a friend
  Key() {}                 // private, user-provided
};

class Registry;

class Database {
public:
  void reset(Key<Registry>) { std::puts("reset"); }   // only Registry can call this
  void query() const { std::puts("query"); }           // anyone can call this
};

class Registry {
public:
  void shutdown(Database& db) { db.reset({}); }  // OK: Registry is a friend of Key<Registry>
};

int main() {
  Database db;
  Registry r;
  r.shutdown(db);
  db.query();
}
```

`reset` is public and anyone can name it, but calling it requires first producing a `Key<Registry>`. The argument `{}` copy-list-initializes the parameter; empty braces value-initialize `Key`, which calls its default constructor. Access is checked at the call site: the note in [[class.access.general#6]] says implicit references to constructors are subject to access control too. Called from within `Registry`, which is a friend, the check passes; from anywhere else it fails:

```cpp title="passkey-outsider.cpp" error
template <class T> class Key { friend T; Key() {} };
class Registry;
class Database { public: void reset(Key<Registry>) {} };

void outsider(Database& db) {
  db.reset({});   // error: calling a private constructor of class 'Key<Registry>'
}
```

The granularity is now per function: `Database` can let only `Registry` call `reset`, hand another function to `Auditor` with `Key<Auditor>`, and keep everything else private. C++26 allows `friend Ts...;`, so a single `Key<Owner, Auditor>` can let several classes through; see the pack expansion section of [[class.friend]] ([[P2893R3]]).

### Cost

`Key` is an empty class passed by value. With `reset` marked `noinline`, comparing `reset(Key<Registry>, int)` against `reset_plain(int)` without a `Key` at `-O2`: on arm64 and with `--target=x86_64-linux-gnu`, both the callee and the call site are identical instruction for instruction in our tests. The `int` arrives in the second integer register (`w1`, `%esi`) in both, and `Key` takes neither a register nor stack space.

The cost is in the name. `Key<Registry>` is a parameter type and ends up in the mangled name (`_ZN8Database5resetE3KeyI8RegistryEi`), so adding or removing a passkey on a published function changes the ABI.

### The gap left by `= default`

<div class="compare" markdown="1">

```cpp title="defaulted.cpp"
class Registry;
class Token {
  friend class Registry;
  Token() = default;   // private, defaulted
};
struct Database {
  void reset(Token) {}
};
void attacker(Database& db) {
  db.reset({});
  // C++11/14/17: OK, aggregate initialization
  // C++20: error, private constructor
}
```

```cpp title="user-provided.cpp" error
class Registry;
class Token {
  friend class Registry;
  Token() {}           // private, user-provided
};
struct Database {
  void reset(Token) {}
};
void attacker(Database& db) {
  db.reset({});
  // error: calls the private
  // constructor in every version
}
```

</div>

The `Token` on the left defaults its constructor on its first declaration. Such a constructor is user-declared but not user-provided. From C++11 to C++17 the definition of aggregate only excluded user-provided constructors (C++17 also excluded `explicit` constructors), so the `Token` on the left is an aggregate. For an **aggregate** ([[g:aggregate]]), `{}` is aggregate initialization: the elements are initialized one by one, no constructor is called at all, and so there is no private constructor to check.

C++20 changed this to exclude every user-declared constructor ([[dcl.init.aggr#1]] ¶1.1, [[P1008R1]]). The `Token` on the left is no longer an aggregate, `{}` has to call the private default constructor, and the call is an error. Results with Clang 23:

| `-std=` | `Token() = default;` | `Token() {}` | `explicit Token() = default;` |
|---|---|---|---|
| c++11 / c++14 / c++17 | both `{}` and `Token{}` compile | error | both `{}` and `Token{}` are errors |
| c++20 / c++2c | error | error | both `{}` and `Token{}` are errors |

For code that must also work in C++17 and earlier, write a user-provided `Key() {}`. The alternative is `explicit Key() = default;`: an explicit constructor makes the class a non-aggregate from C++17, and in a copy-list-initialization context, value-initialization that selects an explicit default constructor is ill-formed (last sentence of [[over.match.ctor#1]], [[CWG1518]]). Clang treats this as a defect fix and reports `chosen constructor is explicit in copy-initialization` even with `-std=c++11`. The price is that the friend itself cannot write `{}` either; it has to write `Key{}`. The standard library's `std::in_place_t` and `std::piecewise_construct_t` use exactly `explicit ... () = default;`, so that `{}` does not implicitly convert to these tag types ([[utility.syn]]).

### Guards against mistakes, not malice

Passkey stops accidental calls, not deliberate circumvention.

- `Key` can be copied. A callee that receives a `Key` can store it or pass it on to someone else. To close this, delete the copy constructor: from C++17, `Key{}` is a prvalue that initializes the parameter directly, without needing a copy constructor (see Question 1).
- `Key` is a trivially copyable empty class, so `std::bit_cast<Key<Registry>>('x')` compiles and runs without ever going through the constructor.
- Explicit instantiation and C++26 splice expressions can both get past access control; see below.

## Private constructors and make_shared

The most common use of passkey is not to restrict callers but to work with `std::make_shared`. A class that should only be created through a factory function naturally makes its constructor private:

```cpp title="private-ctor.cpp" error
#include <memory>
class Session {
  explicit Session(int fd) : fd_(fd) {}
  int fd_;
public:
  static std::shared_ptr<Session> open(int fd) {
    return std::make_shared<Session>(fd);   // error
  }
  int fd() const { return fd_; }
};
```

`open` is a member and may call the private constructor, but `open` is not what actually calls the constructor. The standard says `make_shared` initializes the object with `::new(pv) U(l...)` ([[util.smartptr.shared.create#7.4]]). That expression appears in some internal function of the standard library, which has no access. In libc++ in our tests the diagnostic is in `construct_at.h`, reading `calling a private constructor of class 'Session'`, preceded by five levels of instantiation notes. `make_unique` is the same ([[unique.ptr.create#2]]); there the diagnostic appears in `unique_ptr.h`.

Declaring `std::make_shared` a friend is not reliable: the standard specifies only the expression used for construction, not which function it appears in. Passkey moves the access check back into `open`:

```cpp run title="passkey-make-shared.cpp" ok
#include <cstdio>
#include <memory>

class Session {
  struct Key { explicit Key() = default; };   // private nested type
  int fd_;
public:
  Session(Key, int fd) : fd_(fd) {}          // public, but requires a Key
  static std::shared_ptr<Session> open(int fd) {
    return std::make_shared<Session>(Key{}, fd);
  }
  int fd() const { return fd_; }
};

int main() {
  auto s = Session::open(3);
  std::printf("%d %zu\n", s->fd(), sizeof(Session));   // 3 4
}
```

The constructor is now public, so the `::new` inside `make_shared` can call it. `Key{}` is written inside the member function `open`, and the nested type `Session::Key` is private: only members and friends of `Session` can name it. `Key` only appears as a parameter, so `sizeof(Session)` is still 4. All three outsider attempts fail:

```cpp title="passkey-make-shared-outsider.cpp" error
#include <memory>
class Session {
  struct Key { explicit Key() = default; };
public:
  Session(Key, int) {}
};

void outsider() {
  Session a({}, 3);              // error: Key's constructor is explicit
  Session b(Session::Key{}, 3);  // error: 'Key' is a private member of 'Session'
  auto c = std::make_shared<Session>(Session::Key{}, 3);   // error: same as above
}
```

The `explicit` cannot be dropped here. Access control applies to names ([[class.access.general#6]]), and `{}` does not spell the name `Key`. If `Key` were an aggregate, or its constructor not `explicit`, the first line would compile:

<div class="compare" markdown="1">

```cpp title="leaky-key.cpp" ok
class Session {
  struct Key {};      // private, but an aggregate
public:
  Session(Key, int) {}
};
Session a({}, 3);     // OK: Key is never named
```

```cpp title="sealed-key.cpp" error
class Session {
  struct Key {
    explicit Key() = default;
  };
public:
  Session(Key, int) {}
};
Session a({}, 3);     // error
```

</div>

Another common workaround is to define, inside `open`, a local class derived from `Session` with a public constructor, and `make_shared` that derived class instead. That requires `Session` not to be `final`, and the object's dynamic type becomes a different class. Passkey has neither side effect. The design of factory functions themselves is covered in [[patterns/factory-and-registration]], and the single allocation of `make_shared` in [[topics/ownership-and-smart-pointers]].

## Attorney-client: forwarding only selected private members

Passkey is suited to restricting who calls a public function. A different need is to let one class use a few private members without touching the public interface:

```cpp run title="attorney.cpp" ok
#include <cstdio>

class Buffer {
  int data_[4] = {1, 2, 3, 4};
  int size_ = 4;
  void reserve(int) { std::puts("reserve"); }
  void unsafe_resize(int n) { size_ = n; }   // not to be handed to any outsider
  friend class BufferAttorney;
public:
  int size() const { return size_; }
};

class BufferAttorney {
  // forwards only the two private members Serializer needs
  static int* raw(Buffer& b) { return b.data_; }
  static void reserve(Buffer& b, int n) { b.reserve(n); }
  friend class Serializer;
};

class Serializer {
public:
  static void load(Buffer& b) {
    BufferAttorney::reserve(b, 4);
    BufferAttorney::raw(b)[0] = 42;
  }
};

int main() {
  Buffer b;
  Serializer::load(b);
  std::printf("%d\n", b.size());
}
```

`Buffer` (the client) declares `BufferAttorney` a friend. Every member of `BufferAttorney` (the attorney) is a private static forwarding function, and it in turn declares only `Serializer` a friend. Since friendship is not transitive, `Serializer` is not a friend of `Buffer` and can touch `Buffer` only through the two functions the attorney forwards. A third party cannot even use the attorney:

```cpp title="attorney-limits.cpp" error
class Buffer {
  void unsafe_resize(int) {}
  void reserve(int) {}
  friend class BufferAttorney;
};
class BufferAttorney {
  static void reserve(Buffer& b, int n) { b.reserve(n); }
  friend class Serializer;
};
class Serializer {
public:
  static void load(Buffer& b) { b.unsafe_resize(0); }  // error: 'unsafe_resize' is a private member of 'Buffer'
};
void outsider(Buffer& b) { BufferAttorney::reserve(b, 1); }  // error: 'reserve' is a private member of 'BufferAttorney'
```

The forwarding functions are defined in the class and are implicitly inline. At `-O2` in our tests, a function writing `data_[0]` through the attorney and one writing it directly compile to the same two instructions. A forwarding function that calls a virtual function still dispatches dynamically: the attorney decides only whether a call is allowed, not what it means.

The cost is maintenance. Each client/user pair needs an attorney, and when a client's private member is renamed or changes signature, the attorney has to follow. The attorney must also be visible to the user, just like the client, so it usually lives in the client's header.

| | passkey | attorney-client |
|---|---|---|
| What is let through | public functions of the client | private members of the client |
| Change to the client | one extra `Key` parameter in the signature | one line, `friend class Attorney;` |
| How the user calls it | `obj.f({}, ...)` | `Attorney::f(obj, ...)` |
| Changes the mangled name | yes | no |
| Run-time overhead (`-O2`, in our tests) | none | none |

## Explicit instantiation: a legal back door

Access control has one more gap, and this one comes from the standard itself. In explicit instantiation and explicit specialization declarations, the usual access checking rules do not apply to names, except in a few places such as function bodies, default arguments, base-clauses and member-specifications ([[temp.spec.general#6]]). The rule makes it convenient to explicitly instantiate templates or specialize traits for private nested types, but it also lets anyone obtain a member pointer to a private member:

```cpp run title="rob.cpp" ok
#include <cstdio>

class Vault {
  int secret_ = 42;
};

// tag type: declares a friend function findable only through ADL
struct VaultSecret {
  friend int Vault::* get(VaultSecret);
};

// a friend definition inside a class template carries the template argument out
template <int Vault::* M>
struct Rob {
  friend int Vault::* get(VaultSecret) { return M; }
};

// explicit instantiation: &Vault::secret_ in the template argument is not access-checked
template struct Rob<&Vault::secret_>;

int main() {
  Vault v;
  std::printf("%d\n", v.*get(VaultSecret{}));   // 42
}
```

Use the same template argument in an implicit instantiation, such as `Rob<&Vault::secret_> r;`, and Clang reports `'secret_' is a private member of 'Vault'`. `get` is a hidden friend, found only by argument-dependent lookup in the associated class `VaultSecret` (see the hidden friends section of [[topics/name-lookup-and-customization]]); `v.*p` uses a member pointer and never names `secret_`. A step-by-step analysis and a version that takes a private member function are in the legal back door section of [[class.access]]. From C++20, template arguments of partial specializations are not checked this way either ([[temp.spec.partial.general#10]], [[P0692R1]]).

!!! pitfall "Do not use it in production code"
    The code is well-formed and runs without reports under ASan and UBSan, but it bypasses the only tool a class author has to maintain invariants, and a reviewer cannot tell from `Vault`'s definition that someone is modifying its members. The same explicit instantiation definition may appear only once in the whole program ([[temp.spec.general#5]] ¶5.1); writing it in two translation units violates this, and in our tests linking two such files together produced no diagnostic at all. When tests need access to private members, passkey or an attorney is the reviewable alternative.

## Static reflection and access control {{c++26}}

C++26 static reflection offers another route. Queries such as `std::meta::members_of` and `nonstatic_data_members_of` all take an **access context** ([[g:access-context]]) argument: `access_context::current()` returns only the members accessible at the call site, while `access_context::unchecked()` returns all of them ([[meta.reflection.access.context]], [[P3547R1]]). Once you have the reflection of a member, naming it with a splice expression always passes the access check ([[class.access.base#5]] ¶5.3):

```cpp
#include <meta>
class Vault { int secret_ = 42; };

consteval std::meta::info secret_member() {
  return std::meta::nonstatic_data_members_of(
      ^^Vault, std::meta::access_context::unchecked())[0];
}
int peek(Vault& v) { return v.[: secret_member() :]; }
```

Clang 23 does not support static reflection yet (there is no `<meta>`, and `-freflection` is ignored), so this code has not been compile-tested and carries no verdict. Compared with explicit instantiation, getting past access control here requires writing the word `unchecked()`, which is visible in the code. The full rules for the query functions are in [[meta.reflection.queries]].

## How to choose

| Need | Approach |
|---|---|
| One class needs most of another's internal state; the two are really one component | plain `friend class`; consider merging them or making one nested |
| A public function should be called by only one or two classes | passkey; `Key() {}` for C++17 and earlier |
| Private constructor, but you want `make_shared` or `make_unique` | a private nested `struct Key { explicit Key() = default; };` plus a public constructor |
| A class needs only a few private members, and the public interface should stay as is | attorney-client |
| Several classes each need a different subset of private members | one attorney per user; if there are many, first check whether the class has too many responsibilities |
| You want to restrict what derived classes can call | neither access control nor friendship fits; see [[patterns/nvi]] |
| Unit tests want to read private members | test through the public interface first; if you really must, use an attorney, not the explicit instantiation back door |

## Questions

!!! question "1"
    `Key`'s copy constructor is deleted, its default constructor is private, and `A` is a friend. `A` writes `f(Key{})`, where `f` takes `Key` by value. Does it compile in C++14? In C++17?

<details markdown="1">
<summary>Answer</summary>

Not in C++14; yes from C++17. In C++14, `Key{}` first creates a temporary, which then copy-initializes the parameter; even if the copy is elided, the copy or move constructor must be usable, and the deleted copy constructor also suppresses the implicit declaration of the move constructor. Clang 23 with `-std=c++14` reports `call to deleted constructor of 'Key'`. From C++17, when an object is initialized from a prvalue of the same type, the initializer expression of the prvalue initializes the target object directly ([[dcl.init.general#15]] ¶15.6.1), and no copy constructor is involved. Written as `f({})`, both versions compile, because the parameter is initialized directly from the empty braces and there was never a temporary. More in [[topics/special-members-and-elision]].
</details>

!!! question "2"
    `Session::Key` is a private nested aggregate `struct Key {};`, and the constructor `Session(Key, int)` is public. An outsider's `Session a({}, 3);` compiles. What about `std::make_shared<Session>({}, 3)`?

<details markdown="1">
<summary>Answer</summary>

It does not compile, but for reasons unrelated to access control. `make_shared`'s parameter is a forwarding reference pack `Args&&...`. When a braced-init-list is an argument, the corresponding parameter is a non-deduced context ([[temp.deduct.call#1]]), so the pack cannot be deduced. Clang 23's note is `deduced incomplete pack <(no value), int>`. So this hole only appears where the constructor is called directly, and going through `make_shared` actually blocks it. Do not rely on that; `Key` should still be written as `explicit Key() = default;`.
</details>

!!! question "3"
    Why does the attorney forward through static member functions, instead of `Buffer` writing `friend void Serializer::load(Buffer&);`?

<details markdown="1">
<summary>Answer</summary>

The latter only narrows the caller side: `Serializer::load` can still access every private member of `Buffer` ([[class.friend#1]]), `unsafe_resize` included. It also requires `Buffer`'s header to see the complete definition of `Serializer` first, because `Serializer::load` is a qualified name that must be looked up in `Serializer`, so the client ends up depending on its user. The attorney runs the other way: the client knows only the attorney's name, the attorney decides which members to forward, and the user depends on the attorney.
</details>
