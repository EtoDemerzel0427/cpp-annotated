---
title: "Iostreams base classes: ios_base, basic_ios and fpos"
summary: "The state shared by every stream: when eofbit, failbit and badbit get set, and operator bool looks only at fail(); the exception mask and why exceptions() throws immediately; format flags and the two setf overloads; copyfmt, xalloc/iword/pword and callbacks; the initial values set by basic_ios::init; fpos and the invalid position -1."
updated: 2026-10-19
---

!!! tldr
    - `eofbit` means some input ran into the end, `failbit` means the expected value was not obtained, `badbit` means the stream is corrupted. The three are independent: after successfully reading `"42"`, `eof()` is true and the stream still tests true.
    - `if (in)` and `while (in >> x)` test `!fail()` and ignore `eofbit`; `good()` requires all three bits to be clear.
    - With the exception mask turned on, `clear` and `setstate` throw `ios_base::failure` when the state matches the mask; `exceptions(m)` throws immediately for an existing state.
    - Format flags stay in effect, except width. The single-argument `setf(hex)` does not clear `dec` in the same group; use `setf(hex, basefield)` or the manipulator `std::hex`.
    - `copyfmt` copies the format but not the state; `xalloc`/`iword`/`pword` let custom formatting attach to a stream; passing the `pos_type(-1)` returned by a failed `tellg()` back to a stream member is undefined behavior.

## `ios_base` and `basic_ios`

The state of every stream object is split between two base classes.

`ios_base` is an ordinary class, not a template, and holds state independent of the character type: format flags, width, precision, the `locale`, storage for private use by the program (`iword`/`pword`), and the callback list. It also defines four nested types: `fmtflags`, `iostate`, `openmode` and `seekdir`.

`basic_ios<charT, traits>` derives from `ios_base` and adds the state that depends on the character type: the error state bits, the exception mask, the fill character (of type `charT`), the tied output stream `tie()`, and `rdbuf()`, the pointer to the stream buffer.

Because the parts that do not depend on `charT` live in a non-template base class, manipulators like `std::hex` need to be written only once: the signature is `ios_base& hex(ios_base&)`, which works for both `cout` and `wcout`.

`fmtflags`, `iostate` and `openmode` are **bitmask types** ([[g:bitmask-type]], [[bitmask.types]]): each constant represents one bit or a group of bits, and they can be combined with `|`, `&`, `^` and `~`. Whether they are integers or enumerations is up to the implementation; the synopsis writes them as `T1`, `T2`, `T3`, so do not assume `fmtflags` is `int`.

## Error state

### The three state bits [ios.iostate]

```cpp run ok
#include <iostream>
#include <sstream>

void probe(const char* input) {
  std::istringstream in(input);
  int x = -1;
  in >> x;
  std::cout << '"' << input << "\"\t x=" << x
            << " good=" << in.good() << " eof=" << in.eof()
            << " fail=" << in.fail() << " bool=" << static_cast<bool>(in) << '\n';
}

int main() {
  probe("42 ");          // x=42 good=1 eof=0 fail=0 bool=1
  probe("42");           // x=42 good=0 eof=1 fail=0 bool=1   success, but hit the end
  probe("abc");          // x=0  good=0 eof=0 fail=1 bool=0   conversion failed, x set to 0
  probe("");             // x=-1 good=0 eof=1 fail=1 bool=0   the sentry failed, x unchanged
  probe("99999999999");  // x=2147483647 good=0 eof=1 fail=1  overflow: failbit, x gets the maximum
}
```

The comments show the output in our tests. Line by line:

- `"42"`: to confirm that the number has ended, `num_get` must read one more character, and it reaches the end, so `eofbit` is set. The value was obtained successfully and `failbit` is not set, so `if (in >> x)` is true.
- `"abc"`: when conversion fails, `num_get` sets the value to 0 ([[facet.num.get.virtuals]]).
- `""`: the sentry of formatted input already hits the end while skipping whitespace and sets `failbit | eofbit` ([[istream.sentry#2]]); `num_get` is never called, so `x` stays `-1`.
- Overflow: `operator>>(int&)` first reads a `long` and then checks the range; if out of range it sets `failbit` and stores `numeric_limits<int>::max()` ([[istream.formatted.arithmetic#3]]). In our tests `long` is 64 bits, so `99999999999` fits in a `long` and gets clamped at this step.

¶1 `iostate` has three elements (Table 138), and ¶2 adds the constant `goodbit`, whose value is zero:

| Element | Standard's definition | Typical trigger |
|---|---|---|
| `badbit` | loss of integrity in an input or output sequence, such as an irrecoverable read error from a file | the stream buffer throws an exception; `rdbuf()` is null |
| `eofbit` | an input operation reached the end of an input sequence | during extraction the stream buffer reports no more characters |
| `failbit` | an input operation failed to read the expected characters, or an output operation failed to generate the desired characters | malformed number, overflow, no characters extracted at all, `seekg` failure |

### Querying and setting the state [iostate.flags]

| Function | Specification |
|---|---|
| `explicit operator bool()` | ¶1 returns `!fail()` |
| `operator!()` | ¶2 returns `fail()` |
| `rdstate()` | ¶3 the current error state |
| `clear(state = goodbit)` | ¶4–¶5 sets the state to `state`; see the next section |
| `setstate(state)` | ¶6 calls `clear(rdstate() | state)` |
| `good()` | ¶7 `rdstate() == 0` |
| `eof()` | ¶8 `eofbit` is set |
| `fail()` | ¶9 `failbit` or `badbit` is set |
| `bad()` | ¶10 `badbit` is set |

This table has three asymmetries, all worth remembering.

1. `operator bool` ignores `eofbit`; it is just `!fail()`. After successfully reading `"42"`, `eof()` is true and the stream still tests true. That is why `while (in >> x)` is the correct read loop and `while (!in.eof())` is wrong ([[input.output]]).
2. `fail()` also includes `badbit`; a footnote calls this historical practice. `fail()` being true does not mean `failbit` is set.
3. `good()` is not the same as `operator bool`. In the eof state, `good()` is false and `operator bool` is true.

### The exception mask

By default, a stream error only sets state bits and throws nothing. `exceptions(m)` sets an **exception mask**: from then on, as soon as the state contains a bit in `m`, `ios_base::failure` is thrown.

```cpp
void clear(iostate state = goodbit);
```

¶4 If `(state | (rdbuf() ? goodbit : badbit)) & exceptions()` is 0, returns; otherwise throws `ios_base::failure`, constructed with implementation-defined arguments. ¶5 Postcondition: if `rdbuf()` is non-null, `rdstate() == state`; otherwise `rdstate() == (state | badbit)`. So a stream with a null stream buffer is still in the `badbit` state after `clear()`.

The major implementations write the new state first and then decide whether to throw, so a `catch` block already sees the new state.

¶12 `exceptions(except)` sets the mask and then calls `clear(rdstate())`; the ¶13 postcondition is `exceptions() == except`. This means that if the stream is already in a state the mask selects, `exceptions(m)` throws immediately:

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abc");
  int x;
  in >> x;                                    // fails: failbit, no throw by default
  try {
    in.exceptions(std::ios_base::failbit);    // calls clear(rdstate()): throws immediately
  } catch (const std::ios_base::failure& e) {
    std::cout << (e.code() == std::io_errc::stream) << ' '
              << e.code().category().name() << '\n';    // 1 iostream
  }
}
```

!!! pitfall "With `failbit` exceptions on, a read loop throws at the end"
    After `in.exceptions(std::ios_base::failbit)`, the extraction in `while (in >> x)` that reaches the end sets `failbit | eofbit`, so it throws instead of making the loop condition false. To use exceptions for real errors, usually turn on only `badbit`, or check `eof()` in the `catch` to tell reaching the end apart from a format error.

    ```cpp run ok
    #include <iostream>
    #include <sstream>

    int main() {
      std::istringstream in("1 2 3");
      in.exceptions(std::ios_base::failbit);
      int x, sum = 0;
      try {
        while (in >> x) sum += x;
      } catch (const std::ios_base::failure&) {
        std::cout << "threw at end, sum=" << sum << " eof=" << in.eof() << '\n';  // sum=6 eof=1
      }
    }
    ```

### `ios_base::failure` and error codes [ios.failure], [error.reporting]

```cpp
class ios_base::failure : public system_error {
public:
  explicit failure(const string& msg, const error_code& ec = io_errc::stream);
  explicit failure(const char* msg, const error_code& ec = io_errc::stream);
};
```

[ios.failure] ¶1 `failure` is the base class of all exceptions thrown by the iostreams library to report errors detected during stream buffer operations. Since C++11 it derives from `system_error` (before that, from `exception`), so `catch (const std::system_error&)` also catches it, and `e.code()` can distinguish the cause. An implementation may also define it as an alias for some functionally equivalent class.

¶2 When throwing, implementations should provide an `ec` that identifies the specific reason. Note 2 gives examples: errors from the operating system would typically be reported as `system_category()` errors, and errors from within the stream library as `error_code(io_errc::stream, iostream_category())`.

[error.reporting] defines these error codes:

```cpp
enum class io_errc { stream = 1 };
template<> struct is_error_code_enum<io_errc> : true_type {};
error_code      make_error_code(io_errc e) noexcept;       // ¶1
error_condition make_error_condition(io_errc e) noexcept;  // ¶2
const error_category& iostream_category() noexcept;        // ¶3–¶4
```

¶4 The `name()` of `iostream_category()` returns `"iostream"`. Because `is_error_code_enum<io_errc>` is true, `io_errc::stream` implicitly converts to `error_code`, which is what makes the default argument `ec = io_errc::stream` of the `failure` constructors compile ([[syserr]]).

## Format state

### Format flags [ios.fmtflags]

¶1 The elements of `fmtflags` and their effects when set (Table 136):

| Element | Effect if set |
|---|---|
| `boolalpha` | insert and extract `bool` in alphabetic form (`true`/`false`) |
| `dec` / `oct` / `hex` | read and write integers in decimal, octal or hexadecimal |
| `fixed` / `scientific` | output floating-point numbers in fixed-point or scientific notation |
| `left` / `right` / `internal` | fill characters go on the right, on the left, or at a designated internal point (such as between the sign and the digits) |
| `showbase` | integer output has a base prefix (`0`, `0x`) |
| `showpoint` | floating-point output always has a decimal point |
| `showpos` | non-negative output has a `+` |
| `skipws` | skip leading whitespace before certain input operations |
| `unitbuf` | flush after each output operation |
| `uppercase` | replace certain lowercase letters with uppercase in output (`0X`, `1E+10`, hex digits) |

¶2 Table 137 defines three combined constants: `adjustfield = left | right | internal`, `basefield = dec | oct | hex`, `floatfield = scientific | fixed`. The bits in one group are semantically mutually exclusive, but they are independent bits, which is why `setf` has two overloads.

### The two `setf` overloads [fmtflags.state]

```cpp run ok
#include <iostream>

int main() {
  std::cout.setf(std::ios_base::hex);                          // dec is still set
  std::cout << 255 << '\n';                                    // 255
  std::cout.setf(std::ios_base::hex, std::ios_base::basefield);
  std::cout << 255 << '\n';                                    // ff
}
```

¶4 The single-argument `setf(f)` just ORs in `f`. A stream starts with `dec`, so `basefield` now contains both `dec` and `hex`. When `num_put` decides the base, it compares whether `flags() & basefield` equals `oct` or `hex` ([[facet.num.put.virtuals]]); with both bits set it equals neither, so it falls back to decimal.

¶6 The two-argument `setf(f, mask)` first clears all bits in `mask`, then sets `f & mask`. The manipulator `std::hex` calls this version internally ([[basefield.manip]]), so using manipulators avoids the problem.

The other format state functions:

| Function | Effect | Returns |
|---|---|---|
| `flags()` / `flags(f)` | read / replace all with `f` | current value / old value |
| `unsetf(mask)` | clear the bits in `mask` | nothing |
| `precision()` / `precision(p)` | precision for certain output conversions | current value / old value |
| `width()` / `width(w)` | minimum field width for certain output conversions | current value / old value |

What precision means depends on `floatfield`: in the default notation it is the number of significant digits; under `fixed` or `scientific` it is the number of digits after the decimal point. The initial value is 6.

```cpp run ok
#include <iostream>

int main() {
  std::cout.precision(3);
  std::cout << 1234.5678 << ' ';                    // 1.23e+03 (3 significant digits)
  std::cout << std::fixed << 1234.5678 << ' ';      // 1234.568
  std::cout << std::scientific << 1234.5678 << '\n';// 1.235e+03
}
```

### Manipulators [std.ios.manip]

The four subclauses [fmtflags.manip], [adjustfield.manip], [basefield.manip] and [floatfield.manip] are mechanical: each manipulator `m(str)` calls `str.setf(...)` or `str.unsetf(...)` and returns `str`.

| Manipulator | Effect |
|---|---|
| `boolalpha` / `noboolalpha`, `showbase` / `noshowbase`, `showpoint` / `noshowpoint`, `showpos` / `noshowpos`, `skipws` / `noskipws`, `uppercase` / `nouppercase`, `unitbuf` / `nounitbuf` | `setf(flag)` / `unsetf(flag)` |
| `internal`, `left`, `right` | `setf(flag, adjustfield)` |
| `dec`, `hex`, `oct` | `setf(flag, basefield)` |
| `fixed`, `scientific` | `setf(flag, floatfield)` |
| `hexfloat` | `setf(fixed | scientific, floatfield)` |
| `defaultfloat` | `unsetf(floatfield)` |

`cout << hex` works because `basic_ostream` has an `operator<<` taking `ios_base& (*)(ios_base&)` ([[ostream.inserters]]).

¶1 of each subclause says these functions are designated addressable functions ([[namespace.std]]), so `&std::hex` is well-formed and portable and can be stored in a function pointer. Most standard library functions may not have their address taken.

The note in [floatfield.manip] ¶8 explains that `ios_base::hex` cannot be used to specify a hexadecimal floating-point format, because it is not part of `floatfield`. Hexadecimal floating point is represented by setting both `fixed` and `scientific`:

```cpp run ok
#include <iostream>

int main() {
  std::cout << std::hexfloat << 1.0 << '\n';      // 0x1p+0
  std::cout << std::defaultfloat << std::hex;
  std::cout << 1.5 << ' ' << 255 << '\n';         // 1.5 ff: hex only affects integers
}
```

### locale [ios.base.locales]

¶1 `imbue(loc)` calls each registered callback as `(*fn)(imbue_event, *this, idx)`, at a time when `getloc()` already returns the new locale. ¶2 The postcondition is `getloc() == loc`; ¶3 returns the old value.

¶4 If no locale has been imbued, `getloc()` returns a copy of the global C++ locale `locale()` in effect when the stream was constructed. So a later call to `std::locale::global(...)` does not affect existing streams, including `cout`.

Besides calling `ios_base::imbue`, `basic_ios::imbue` also calls `rdbuf()->pubimbue(loc)` if `rdbuf()` is non-null ([[basic.ios.members#9]]); `ios_base::imbue` does not notify the stream buffer.

## `basic_ios` [ios]

### Initial state and `init` [basic.ios.cons]

¶1 `explicit basic_ios(basic_streambuf* sb)` calls `init(sb)`. ¶4 The postconditions of `init(sb)` are in Table 142:

| Member | Value after `init` |
|---|---|
| `rdbuf()` | `sb` |
| `tie()` | null |
| `rdstate()` | `goodbit` if `sb` is non-null, otherwise `badbit` |
| `exceptions()` | `goodbit`, i.e. no exceptions thrown |
| `flags()` | `skipws | dec` |
| `width()` | 0 |
| `precision()` | 6 |
| `fill()` | `widen(' ')` |
| `getloc()` | a copy of `locale()` |
| `iarray` / `parray` | null pointer |

¶2 The protected default constructor `basic_ios()` leaves its members uninitialized. `init` must be called before first use or before destruction, whichever comes first, otherwise the behavior is undefined. [[ios.base.cons#1]] says the same for `ios_base()`.

Why the two-step construction? `basic_ios` is a virtual base class of `basic_istream` and `basic_ostream`, and a virtual base is constructed by the most derived class ([[iostream.objects]]). Each intermediate class calls the do-nothing default constructor and then calls `init` from its own constructor.

¶3 The destructor does not destroy `rdbuf()`. A stream does not own its stream buffer, and one stream buffer can be shared by several streams, for example `std::ostream log(std::cout.rdbuf());`. An `ifstream` closes its file on destruction because it holds a `basic_filebuf` as a data member, which is destroyed along with it, and `~basic_filebuf` calls `close()` ([[filebuf.cons#5]]).

### Member functions [basic.ios.members]

```cpp run ok
#include <iostream>

int main() {
  std::ostream os(nullptr);              // init(nullptr): rdstate() == badbit
  std::cout << os.bad() << ' ';          // 1
  os.clear();                            // rdbuf() is null: badbit remains after clear
  std::cout << os.bad() << ' ';          // 1
  os.rdbuf(std::cout.rdbuf());           // rdbuf(sb) calls clear() internally
  std::cout << os.bad() << '\n';         // 0
  os << "now writes to stdout\n";
}
```

¶6 `rdbuf(sb)` calls `clear()`; the ¶7 postcondition is `rdbuf() == sb`. When passed a null pointer, `clear()` sets the state to `badbit` because `rdbuf()` is null.

¶1 `tie()` returns the output stream **tied** to this stream ([[g:tied-stream]]): before each input or output on this stream, the sentry first flushes that stream. ¶2 The precondition when setting it is that following the tie chain from `tiestr->tie()` never leads back to `tiestr`. Ties cannot form a cycle, otherwise flushing would recurse forever.

¶9 `imbue(loc)`: see the previous section. ¶11–¶12 `narrow` and `widen` delegate to `use_facet<ctype<char_type>>(getloc())`. ¶13–¶15 `fill` reads and writes the fill character, whose type is `charT`, which is why it is in `basic_ios` rather than `ios_base`.

### `copyfmt` (¶16–¶19)

`copyfmt(rhs)` copies the format, not the state or the connections. A common use is saving and restoring the format:

```cpp run ok
#include <iomanip>
#include <iostream>

int main() {
  std::ios saved(nullptr);
  saved.copyfmt(std::cout);                        // save
  std::cout << std::hex << std::showbase << std::setfill('*') << std::setw(8) << 255 << '\n';
  std::cout.copyfmt(saved);                        // restore
  std::cout << std::setw(8) << 255 << '\n';        // "     255"
}
```

¶16 If `this == addressof(rhs)`, does nothing; otherwise, in order:

1. ¶16.1 calls each callback of `*this` with `erase_event`, letting them release the resources `pword` points to;
2. ¶16.2 assigns the members of `rhs` to `*this`, except that `rdstate()`, `rdbuf()` and `exceptions()` are left unchanged; the `iword`/`pword` arrays are copied by contents, not by pointer; if a newly stored pointer points to an object outside `rhs` that will be destroyed along with `rhs`, it is changed to point to a newly constructed copy;
3. ¶16.3 calls each callback copied from `rhs` with `copyfmt_event`. The note in ¶17 explains that this second round of callbacks gives the program a chance to null out the copied `pword`, deep-copy the object it points to, or increment a reference count;
4. ¶16.4 finally calls `exceptions(rhs.exceptions())`.

The exception mask is set last and separately because `exceptions(m)` may throw immediately. Putting it last means the rest of the format has already been copied when it throws. Table 143 in ¶18 summarizes the result: `rdbuf()` and `rdstate()` are unchanged; `tie`, `exceptions`, `flags`, `width`, `precision`, `fill` and `getloc` all equal those of `rhs`.

### `move`, `swap`, `set_rdbuf` (¶20–¶25)

These three protected members are for derived stream classes to implement move operations:

- ¶20 `move(rhs)`: `*this` gets the state `rhs` had, except that `rdbuf()` is null. `rhs` is left in a valid but unspecified state, except that `rhs.rdbuf()` is unchanged and `rhs.tie()` is null.
- ¶21 `swap(rhs)`: swaps the state, but both sides' `rdbuf()` are unchanged.
- ¶22–¶25 `set_rdbuf(sb)`: the precondition is that `sb` is non-null; associates `sb` without calling `clear()`, unlike the public `rdbuf(sb)`; throws nothing.

`rdbuf` does not move along because streams like `ifstream` and `stringstream` hold their stream buffer as a data member. On a move, the derived class moves the stream buffer itself and then uses `set_rdbuf` to point to the stream buffer in the new object ([[file.streams]], [[string.streams]]). If `basic_ios::move` copied the pointer, the new stream would point into the old object's buffer.

## Custom format state

### `xalloc`, `iword`, `pword` [ios.base.storage]

These functions let user-defined format state attach to a stream the same way `std::hex` does:

```cpp run ok
#include <iostream>
#include <sstream>

const int style_slot = std::ios_base::xalloc();   // an index unique within the process

struct Point { int x, y; };

std::ostream& angle_style(std::ostream& os) { os.iword(style_slot) = 1; return os; }

std::ostream& operator<<(std::ostream& os, Point p) {
  if (os.iword(style_slot) == 1) return os << '<' << p.x << ';' << p.y << '>';
  return os << '(' << p.x << ", " << p.y << ')';
}

int main() {
  std::ostringstream a, b;
  a << angle_style << Point{1, 2};
  b << Point{1, 2};                 // b's slot is still 0
  std::cout << a.str() << ' ' << b.str() << '\n';   // <1;2> (1, 2)
  b.copyfmt(a);                     // copyfmt copies the contents of the iword array
  b << ' ' << Point{3, 4};
  std::cout << b.str() << '\n';     // (1, 2) <3;4>
}
```

¶1 `static int xalloc()` returns a new globally unique index. ¶2 Concurrent calls from multiple threads do not result in a data race.

¶3–¶5 The precondition of `long& iword(int idx)` is that `idx` came from `xalloc()`. It extends the internal array of `long` as needed, initializing new elements to 0, and returns a reference to the element at `idx`. ¶6–¶8 `void*& pword(int idx)` is the same, except that the array elements are pointers, initialized to null.

The returned reference becomes invalid after any other operation on the stream object, but the value itself is retained: a later call with the same index yields the same value, until the next `copyfmt`. So call `iword(slot)` afresh each time rather than storing the reference it returns.

If extending the array fails (for example, memory cannot be allocated) and `*this` is a base class subobject of a `basic_ios` object, the effect is as if `setstate(badbit)` were called on that object, and a valid reference to a value of 0 is returned.

`pword` stores a `void*`. If it points to a heap object owned by the stream, use the callbacks below to handle release and deep copying; otherwise after `copyfmt` both streams hold the same pointer, and there is no telling which one should free it on destruction.

### Callbacks [ios.base.callback]

```cpp
enum event { erase_event, imbue_event, copyfmt_event };
using event_callback = void (*)(event, ios_base&, int idx);
void register_callback(event_callback fn, int idx);
```

¶1 Precondition: `fn` does not throw exceptions.

¶2 Registers `(fn, idx)`; from then on `fn` is called with `idx` during `imbue()`, `copyfmt()` and `~ios_base()`. When an event occurs, the callbacks are called in the reverse order of registration; callbacks registered while a callback is running are not called until the next event.

¶3 Identical `(fn, idx)` pairs are not merged: register twice and it is called twice.

[ios.base.cons] ¶2 `~ios_base()` first calls each callback with `erase_event`, at a time when calling `ios_base` member functions from the callback has well-defined results; it then releases the memory occupied by `iword`/`pword`.

## Open modes and positioning

### `openmode` and `seekdir` [ios.openmode], [ios.seekdir]

| `openmode` element | Effect |
|---|---|
| `app` | seek to the end before each write |
| `ate` | seek to the end immediately after opening |
| `binary` | perform input and output in binary mode (as opposed to text mode) |
| `in` / `out` | open for input / output |
| `noreplace` {{c++23}} | open in exclusive mode: fail if the file already exists |
| `trunc` | truncate an existing stream when opening |

How these combinations map to `fopen` mode strings is in [[file.streams]]; for string streams and span streams, `in`, `out` and `ate` determine how the get and put areas are initialized ([[string.streams]]).

`seekdir` is an enumerated type ([[enumerated.types]]) with three values: `beg` relative to the beginning, `cur` relative to the current position, and `end` relative to the current end.

### `fpos` [fpos]

```cpp
template<class stateT> class fpos {
public:
  stateT state() const;
  void state(stateT);
private:
  stateT st;          // exposition only
};
```

`fpos` represents a position in a file: an offset convertible to and from `streamoff`, plus a conversion state `st`; for `char` streams the conversion state is `mbstate_t`. In a state-dependent multibyte encoding, how the bytes at a given byte offset are interpreted depends on the preceding shift state; returning to a position requires restoring the state along with it.

Table 141 in [fpos.operations] ¶1 specifies the operations `fpos` must support. With `P` a specialization of `fpos` and `O` meaning `streamoff`:

| Expression | Meaning |
|---|---|
| `P(o)`, `P p(o)`, `P p = o` | constructs from an offset, state value-initialized |
| `P()`, `P p;` | equals `P(0)` |
| `O(p)` | converts back to an offset; `P(O(p)) == p` |
| `p == q`, `p != q` | comparison |
| `p + o`, `p += o`, `p - o`, `p -= o`, `o + p` | position plus or minus an offset |
| `p - q` | the distance between two positions, of type `streamoff` |

¶1 also requires `stateT` to meet *Cpp17DefaultConstructible*, *Cpp17CopyConstructible*, *Cpp17CopyAssignable* and *Cpp17Destructible*. If `stateT`'s copy constructor, copy assignment and destructor are trivial, so are the corresponding members of `fpos`.

¶2 Stream operations that return `traits::pos_type` use `P(O(-1))` as an invalid value to report an error. Passing that value to any `istream`, `ostream` or `streambuf` member that accepts a `pos_type` is undefined behavior. So `seekg(tellg())` is undefined behavior when `tellg()` fails; check before use:

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abc");
  auto pos = in.tellg();
  if (pos == std::streampos(-1)) return 1;   // check first, then use
  in.get();
  in.seekg(pos);
  std::cout << static_cast<char>(in.get()) << '\n';   // a
}
```

## Members related to the standard stream objects

Constructing `ios_base::Init` ([ios.init]) guarantees that the eight standard stream objects in `<iostream>` have been constructed, and its destructor flushes the output streams when no other `Init` object is alive. The static member `sync_with_stdio` ([ios.members.static]) controls whether the standard streams are synchronized with C stdio. Both concern only the standard stream objects; see [[iostream.objects]].

## Questions

!!! question "Question 1"
    Which branch of this `if` is taken?
    ```cpp
    std::istringstream in("7");
    int x;
    in >> x;
    if (in.good()) { /* A */ } else if (in) { /* B */ } else { /* C */ }
    ```

<details markdown="1">
<summary>Answer</summary>

B. While reading `7`, `num_get` reaches the end in order to confirm the number has ended, setting `eofbit`, so `good()` is false ([[iostate.flags#7]]). The extraction itself succeeded and `failbit` is not set, so `operator bool`, i.e. `!fail()`, is true ([[iostate.flags#1]]).
</details>

!!! question "Question 2"
    `a` is in the `failbit` state, and `b.exceptions() == failbit`. What happens when `a.copyfmt(b)` is called?

<details markdown="1">
<summary>Answer</summary>

`copyfmt` does not copy `rdstate()`, so `a` is still in the `failbit` state. Its last step calls `exceptions(rhs.exceptions())` ([[basic.ios.members#16.4]]), which calls `clear(rdstate())`, finds `failbit & exceptions()` non-zero, and throws `ios_base::failure`. By then `flags`, `fill`, `iword` and the rest have all been copied.
</details>

## Summary

| Topic | Key points |
|---|---|
| Two classes | `ios_base` holds state independent of `charT`; `basic_ios` adds the state bits, `fill`, `tie`, `rdbuf` |
| State bits | `eofbit` hit the end, `failbit` did not get the expected value, `badbit` stream corrupted; `operator bool` is `!fail()` |
| Exceptions | `clear`, `setstate` and `exceptions(m)` may all throw; `exceptions(m)` throws immediately for an existing state |
| Format | Format state other than width stays in effect; `setf(f)` does not clear bits in the same group; use `setf(f, mask)` or manipulators |
| Custom format | `xalloc` plus `iword`/`pword`; `copyfmt` copies the array contents and triggers callbacks |
| `init` | `goodbit` (`badbit` if the stream buffer is null), `skipws | dec`, precision 6, space fill, no tie, no exceptions |
| `fpos` | Offset plus conversion state; `pos_type(-1)` signals an error, and passing it back to stream members is {{ub}} |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[ios.syn]: `<ios>` includes `<iosfwd>` and declares `streamoff`/`streamsize` ([[iostreams.requirements]]), `fpos`, `ios_base`, `basic_ios`, all the manipulators of the form `ios_base&(ios_base&)`, and `io_errc`, `is_error_code_enum<io_errc>`, `make_error_code`, `make_error_condition`, `iostream_category`.

[ios.base.general] ¶1 lists the member types defined by `ios_base`: `failure`, `Init`, the three bitmask types and the enumerated type `seekdir`. ¶2 says it maintains three kinds of data: state information reflecting the integrity of the stream buffer, control information that influences how to interpret input and generate output, and additional information stored by the program for its private use. The note in ¶3, for exposition, describes the third kind with three members `index`, `iarray` and `parray`, in terms of which `xalloc`, `iword` and `pword` are specified.

[ios.failure] ¶1 Note 1: when `ios_base::failure` is an alias for another class, that class needs to provide a nested `failure` type to emulate the injected-class-name. ¶3–¶4: both constructors construct the base class with `msg` and `ec`.

[ios.base.storage] ¶9: a subsequent call to `pword` on the same object may invalidate the previously returned value. Footnote 239 explains that an implementation can make both arrays sparse structures, each with a one-element cache.

[fpos.members] ¶1–¶2: `state(s)` assigns `s` to `st`; `state()` returns the current value of `st`.

[error.reporting] ¶1–¶2: `make_error_code(e)` and `make_error_condition(e)` return an `error_code` and an `error_condition` constructed from `static_cast<int>(e)` and `iostream_category()`, respectively. The rest of ¶4: this category object's `default_error_condition` and `equivalent` behave as specified for `error_category`.

</details>
