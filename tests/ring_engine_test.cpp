// Тесты анимации кольца: clang++ -std=c++17 -I esphome tests/ring_engine_test.cpp -o /tmp/rt && /tmp/rt
// Ридер опрашивается каждые 200 мс, кадр анимации — каждые 16 мс, как в прошивке.
#include "ring_engine.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

static int failures = 0;
#define CHECK(cond, msg)                                     \
  do {                                                       \
    if (!(cond)) {                                           \
      std::printf("  FAIL: %s (line %d)\n", msg, __LINE__); \
      failures++;                                            \
    }                                                        \
  } while (0)

using Phase = RingEngine::Phase;
using Status = RingEngine::Status;

struct Frame {
  float t;
  Phase phase;
  float signal, level, goal, max_px, min_lit_px;
  int lit;
};

// present(t) — лежит ли метка физически в зоне ридера; miss(poll) — ридер промахнулся.
// on_color — когда Home Assistant присылает цвет (секунды, <0 — никогда).
static std::vector<Frame> run(float seconds, std::function<bool(float)> present,
                              std::function<bool(int)> miss, float on_color, RingRgb color = {1, 0, 0},
                              Status status = Status::kOk, RingEngine *out = nullptr) {
  RingEngine e;
  std::vector<Frame> frames;
  bool raw = false, tagged = false, color_sent = false;
  int poll = 0;
  float next_poll = 0;
  for (int ms = 0; ms <= seconds * 1000; ms += 16) {
    float t = ms / 1000.0f;
    if (t >= next_poll) {
      bool hit = present(t) && !miss(poll);
      if (hit && !raw && !tagged) {
        e.new_tag();
        tagged = true;
      }
      if (!present(t)) tagged = false;
      raw = hit;
      poll++;
      next_poll += 0.2f;
    }
    if (on_color >= 0 && t >= on_color && !color_sent && tagged) {
      e.set_color(int(color.r * 255), int(color.g * 255), int(color.b * 255), 3.0f);
      color_sent = true;
    }
    e.tick(ms, raw, status);
    Frame f{t, e.phase(), e.signal(), e.level(), e.goal(), 0, 2, 0};
    for (int i = 0; i < RingEngine::kPixels; i++) {
      RingRgb p = e.pixel(i);
      float v = std::max({p.r, p.g, p.b});
      f.max_px = std::max(f.max_px, v);
      if (v > 0.01f) {
        f.lit++;
        f.min_lit_px = std::min(f.min_lit_px, v);
      }
    }
    frames.push_back(f);
  }
  if (out) *out = e;
  return frames;
}

static const char *name(Phase p) {
  switch (p) {
    case Phase::kIdle: return "idle ";
    case Phase::kPulse: return "pulse";
    case Phase::kHold: return "hold ";
    case Phase::kFade: return "fade ";
    case Phase::kDone: return "done ";
    case Phase::kRecede: return "reced";
  }
  return "?";
}

static void timeline(const std::vector<Frame> &fs, float step = 0.2f) {
  float next = 0;
  for (const auto &f : fs) {
    if (f.t + 1e-4f < next) continue;
    next += step;
    std::string bar(f.lit, '#');
    std::printf("  %5.2f %s sig=%.2f lvl=%.2f max=%.2f |%-24s|\n", f.t, name(f.phase), f.signal, f.level, f.max_px,
                bar.c_str());
  }
}

static float first(const std::vector<Frame> &fs, std::function<bool(const Frame &)> pred) {
  for (const auto &f : fs)
    if (pred(f)) return f.t;
  return -1;
}

int main() {
  auto never = [](int) { return false; };

  std::printf("1. Статуэтку поставили в 1.0 с, цвет от HA в 1.25 с\n");
  {
    auto fs = run(12, [](float t) { return t >= 1.0f; }, never, 1.25f);
    timeline(fs, 0.4f);
    float full = first(fs, [](const Frame &f) { return f.lit == 24 && f.max_px > 0.99f; });
    float pulse = first(fs, [](const Frame &f) { return f.phase == Phase::kPulse; });
    float done = first(fs, [](const Frame &f) { return f.phase == Phase::kDone; });
    CHECK(full > 1.0f && full < 2.2f, "кольцо заполняется целиком за ~1 с после того, как поставили");
    CHECK(pulse > full, "вдох — только после полного кольца");
    CHECK(done > 7.0f && done < 9.5f, "вдох + 3 с + выдох — и кольцо гаснет");
    CHECK(fs.back().max_px == 0, "пока статуэтка стоит после выдоха, кольцо не горит");
    int prev = 0;
    bool monotonic = true;
    for (const auto &f : fs) {
      if (f.phase != Phase::kIdle) break;
      if (f.lit < prev) monotonic = false;
      prev = f.lit;
    }
    CHECK(monotonic, "на подлёте пиксели только прибавляются, без дребезга");
  }

  std::printf("2. Ридер пропускает каждый 8-й опрос, пока статуэтка стоит\n");
  {
    auto fs = run(12, [](float t) { return t >= 1.0f; }, [](int poll) { return poll % 8 == 0; }, 1.25f);
    float done = first(fs, [](const Frame &f) { return f.phase == Phase::kDone; });
    bool receded = false;
    float min_hold = 2;
    for (const auto &f : fs) {
      if (f.phase == Phase::kHold) min_hold = std::min(min_hold, f.min_lit_px);
      if (f.t > 3 && f.t < done && f.phase == Phase::kIdle) receded = true;
    }
    CHECK(done > 0, "одиночные промахи не мешают дойти до конца");
    CHECK(!receded, "одиночный промах не гасит кольцо");
    CHECK(min_hold > 0.95f, "во время удержания яркость не проседает");
  }

  std::printf("3. Метку поднесли на 0.6 с и убрали, не поставив\n");
  {
    auto fs = run(5, [](float t) { return t >= 1.0f && t < 1.6f; }, [](int poll) { return poll % 2 == 0; }, 1.2f);
    timeline(fs, 0.2f);
    bool pulsed = false;
    for (const auto &f : fs)
      if (f.phase != Phase::kIdle) pulsed = true;
    float peak = 0;
    for (const auto &f : fs) peak = std::max(peak, f.level);
    CHECK(!pulsed, "без устойчивого сигнала вдоха нет");
    CHECK(peak > 0.05f && peak < 1.0f, "кольцо частично заполнилось и не до конца");
    CHECK(fs.back().max_px == 0, "после того как убрали — кольцо пустое");
  }

  std::printf("4. Метка не настроена в HA — через 0.6 с белый\n");
  {
    RingEngine e;
    auto fs = run(3, [](float t) { return t >= 0.5f; }, never, -1, {1, 0, 0}, Status::kOk, &e);
    RingRgb p = e.pixel(0);
    CHECK(fs.back().lit == 24, "кольцо заполнилось и без цвета от HA");
    CHECK(p.r > 0.9f && p.g > 0.9f && p.b > 0.9f, "цвет — белый");
    float first_lit = first(fs, [](const Frame &f) { return f.lit > 0; });
    CHECK(first_lit >= 1.1f, "до ответа HA кольцо не загорается чужим цветом");
  }

  std::printf("5. Статуэтку сняли во время удержания (в 4 с)\n");
  {
    auto fs = run(8, [](float t) { return t >= 1.0f && t < 4.0f; }, never, 1.25f);
    timeline(fs, 0.2f);
    float off = first(fs, [](const Frame &f) { return f.t > 4.0f && f.max_px == 0; });
    int prev = 24;
    bool monotonic = true;
    for (const auto &f : fs) {
      if (f.t < 4.0f) continue;
      if (f.lit > prev) monotonic = false;
      prev = f.lit;
    }
    CHECK(off > 4.0f && off < 6.0f, "кольцо гаснет за ~1.5 с после того, как сняли");
    CHECK(monotonic, "пиксели гаснут по очереди, без вспышек");
  }

  std::printf("6. Индикатор настройки Wi-Fi, пока на платформе пусто\n");
  {
    auto wifi = run(4, [](float) { return false; }, never, -1, {1, 0, 0}, Status::kWifiSetup);
    auto ok = run(4, [](float) { return false; }, never, -1, {1, 0, 0}, Status::kOk);
    float peak = 0;
    for (const auto &f : wifi) peak = std::max(peak, f.max_px);
    CHECK(peak > 0.05f && peak <= 0.16f, "в режиме настройки кольцо тихо дышит");
    CHECK(ok.back().max_px == 0 && ok[100].max_px == 0, "в обычном режиме пустое кольцо не горит");
  }


  std::printf("7. Метка висит на краю зоны: ридер видит её через раз\n");
  {
    auto fs = run(6, [](float t) { return t >= 1.0f; }, [](int poll) { return poll % 2 == 1 || poll % 7 == 0; }, 1.25f);
    timeline(fs, 0.2f);
    int lo = 99, hi = 0;
    for (const auto &f : fs) {
      if (f.t < 3.0f) continue;
      lo = std::min(lo, f.lit);
      hi = std::max(hi, f.lit);
    }
    int reversals = 0, dir = 0;
    float prev = -1;
    for (const auto &f : fs) {
      if (f.t < 3.0f) continue;
      if (prev >= 0 && std::fabs(f.level - prev) > 1e-4f) {
        int d = f.level > prev ? 1 : -1;
        if (dir != 0 && d != dir) reversals++;
        dir = d;
      }
      prev = f.level;
    }
    float max_jump = 0;
    for (size_t i = 0; i + 6 < fs.size(); i++) {
      if (fs[i].t < 3.0f) continue;
      bool partial = fs[i].goal > 0 && fs[i].goal < 1 && fs[i + 6].goal > 0 && fs[i + 6].goal < 1;
      if (!partial) continue;  // быстрое дозаполнение до полного и уход в ноль — по задумке
      max_jump = std::max(max_jump, std::fabs(fs[i + 6].level - fs[i].level));  // ~100 мс
    }
    std::printf("  пикселей горит: от %d до %d, смен направления за 3 с: %d, наибольший сдвиг за 100 мс: %.2f\n",
                lo, hi, reversals, max_jump);
    CHECK(max_jump <= 0.12f, "на краю зоны кольцо не прыгает: за 100 мс сдвиг не больше ~1.5 пикселя на сторону");
    CHECK(reversals <= 2, "на краю зоны кольцо не дребезжит туда-сюда");
  }


  std::printf("8. Зарядник по линии CC\n");
  {
    CHECK(usb_c_source_ma(1.6f, 0.0f) == 3000, "3 А на CC1");
    CHECK(usb_c_source_ma(0.0f, 1.6f) == 3000, "3 А на CC2 (кабель перевёрнут)");
    CHECK(usb_c_source_ma(0.9f, 0.02f) == 1500, "1.5 А");
    CHECK(usb_c_source_ma(0.42f, 0.0f) == 500, "кабель USB-A → C — по умолчанию");
    CHECK(usb_c_source_ma(0.0f, 0.0f) == 0, "гнездо пустое — неизвестно");
    CHECK(usb_c_source_ma(1.1f, 1.3f) == 0, "обе линии «висят» (не подпаяны) — неизвестно");
    CHECK(usb_c_source_ma(3.1f, 0.0f) == 0, "напряжение вне стандарта — неизвестно");
    CHECK(ring_budget_ma(3000) > 2000, "от 3 А кольцу хватает на полный белый (1.44 А)");
    CHECK(ring_budget_ma(1500) > 700 && ring_budget_ma(1500) < 800, "от 1.5 А — около 0.78 А");
    CHECK(ring_budget_ma(500) == 150 && ring_budget_ma(0) == 150, "слабый или неизвестный — минимум");
  }

  std::printf("9. Ограничитель тока\n");
  {
    RingRgb white[24], red[24];
    for (auto &p : white) p = {1, 1, 1};
    for (auto &p : red) p = {1, 0, 0};
    std::printf("  полный белый: %.0f мА, полный красный: %.0f мА\n", ring_current_ma(white, 24), ring_current_ma(red, 24));
    RingRgb w1[24], w2[24], r1[24];
    std::copy(white, white + 24, w1);
    std::copy(white, white + 24, w2);
    std::copy(red, red + 24, r1);
    CHECK(limit_power(w1, 24, ring_budget_ma(3000)) == 1.0f, "от 3 А белый не приглушается");
    float k = limit_power(w2, 24, ring_budget_ma(1500));
    float after = ring_current_ma(w2, 24);
    std::printf("  белый от 1.5 А: яркость ×%.2f, ток %.0f мА (бюджет %.0f)\n", k, after, ring_budget_ma(1500));
    CHECK(k < 1.0f && std::fabs(after - ring_budget_ma(1500)) < 2.0f, "от 1.5 А белый приглушён ровно до бюджета");
    CHECK(limit_power(r1, 24, ring_budget_ma(1500)) == 1.0f, "насыщенный цвет от 1.5 А — на полную");
    RingRgb w3[24];
    std::copy(white, white + 24, w3);
    limit_power(w3, 24, ring_budget_ma(0));
    CHECK(ring_current_ma(w3, 24) <= 151.0f && w3[0].r > 0.3f, "без данных о заряднике — тускло, но видно");
  }

  std::printf(failures ? "\nПРОВАЛЕНО: %d\n" : "\nВсе тесты прошли\n", failures);
  return failures ? 1 : 0;
}
