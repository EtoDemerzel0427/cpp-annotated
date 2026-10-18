#include <cctype>
#include <algorithm>
#include <string>
#include <functional>
void a() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(), std::toupper); // ?
}
