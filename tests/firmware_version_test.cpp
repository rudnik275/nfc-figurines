// Тесты сравнения версий прошивки: clang++ -std=c++17 -I esphome tests/firmware_version_test.cpp -o /tmp/vt && /tmp/vt
#include "firmware_version.h"

#include <cstdio>

static int failures = 0;
#define CHECK(cond, msg)                                     \
  do {                                                       \
    if (!(cond)) {                                           \
      std::printf("  FAIL: %s (line %d)\n", msg, __LINE__); \
      failures++;                                            \
    }                                                        \
  } while (0)

int main() {
  std::printf("1. Новее — ставим сами\n");
  CHECK(version_newer("0.8", "0.7"), "0.8 новее 0.7");
  CHECK(version_newer("1.0", "0.9"), "1.0 новее 0.9");
  CHECK(version_newer("0.10", "0.9"), "0.10 новее 0.9: числа, а не строки");
  CHECK(version_newer("0.8.1", "0.8"), "0.8.1 новее 0.8");

  std::printf("2. Та же или старше — не трогаем\n");
  CHECK(!version_newer("0.8", "0.8"), "та же версия");
  CHECK(!version_newer("0.8", "0.8.0"), "0.8 и 0.8.0 — одна версия");
  CHECK(!version_newer("0.8", "0.9"), "стенд на 0.9 не откатывается на опубликованную 0.8");
  CHECK(!version_newer("0.9", "0.10"), "0.9 старше 0.10");

  std::printf("3. Мусор в манифесте не ставится\n");
  CHECK(!version_newer("", "0.8"), "пустая версия");
  CHECK(!version_newer("abc", "0.8"), "не число");
  CHECK(!version_newer("0.9-dev", "0.9"), "хвост после числа не делает версию новее");
  CHECK(version_newer("0.9", "0.8-dev"), "но и не мешает сравнить число");

  std::printf(failures ? "\nПРОВАЛЕНО: %d\n" : "\nВсе тесты прошли\n", failures);
  return failures ? 1 : 0;
}
