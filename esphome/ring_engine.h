#pragma once
// Анимация кольца подставки. Чистый C++ без ESPHome: логика проверяется тестами
// на компьютере (tests/ring_engine_test.cpp), прошивка только вызывает tick() и pixel().
//
// PN532 не мерит расстояние до метки, поэтому «сигнал» — сглаженная доля удачных
// опросов ридера: на подлёте метка ловится через раз, на платформе — каждый опрос.
// Кольцо заполняется от пикселя start в обе стороны навстречу друг другу, пропорционально
// сигналу. Скорость роста и убывания ограничена, край заполнения переливается
// между соседними пикселями — одиночные промахи ридера не дают дребезга яркости.
// Метка встала на платформу → «вдох» → горит hold секунд → гаснет «выдохом».
#include <algorithm>
#include <cmath>
#include <cstdint>

struct RingRgb {
  float r, g, b;
};

class RingEngine {
 public:
  static constexpr int kPixels = 24;
  enum class Phase { kIdle, kPulse, kHold, kFade, kDone, kRecede };
  enum class Status { kOk, kWifiSetup, kNoHa };

  int start = 0;  // пиксель, от которого расходятся обе волны

  // Время — в секундах. Значения подбираются на стенде.
  float signal_tau = 0.8f;      // сглаживание сигнала
  float fill_time = 0.5f;       // кольцо не заполняется быстрее этого
  float empty_time = 0.8f;      // и не пустеет быстрее этого
  float signal_floor = 0.10f;   // сигнал ниже — кольцо пустое
  float signal_full = 0.55f;    // сигнал выше — кольцо полное
  float deadband = 0.15f;       // кольцо сдвигается, только если уровень изменился больше этого
  float rise_after = 0.15f;     // кольцо растёт, если сигнал вырос и держится столько...
  float drop_after = 0.6f;      // ...а убывает, только если сигнал упал и держится столько
  float partial_time = 1.0f;    // промежуточные шаги на краю зоны — медленно, без рывков
  float placed_level = 0.8f;    // полное кольцо при таком сигнале...
  float placed_after = 0.3f;    // ...столько времени — метка стоит на платформе
  float removed_level = 0.3f;   // сигнал ниже — метку убрали
  float pulse_time = 0.8f;
  float pulse_depth = 0.35f;
  float fade_time = 2.0f;
  float color_wait = 0.6f;      // столько ждём цвет от Home Assistant, потом белый
  float default_hold = 3.0f;
  float status_level = 0.15f;   // яркость индикатора «нужна настройка»
  float status_period = 3.0f;

  // Новая метка: прежний цвет больше не годится, ждём цвет от HA.
  void new_tag() {
    has_tag_ = true;
    color_ready_ = false;
    color_wait_t_ = 0;
    if (phase_ != Phase::kIdle) go(Phase::kIdle);
    level_ = goal_ = 0;
  }

  // Цвет и время свечения для текущей метки — из блупринта Home Assistant.
  void set_color(int r, int g, int b, float hold) {
    target_ = {r / 255.0f, g / 255.0f, b / 255.0f};
    hold_ = hold > 0 ? hold : default_hold;
    if (!color_ready_) color_ = target_;
    color_ready_ = true;
  }

  void tick(uint32_t now_ms, bool raw_present, Status status) {
    float dt = started_ ? (now_ms - last_ms_) / 1000.0f : 0.0f;
    dt = std::clamp(dt, 0.0f, 0.1f);
    started_ = true;
    last_ms_ = now_ms;
    status_ = status;
    status_t_ += dt;

    signal_ += ((raw_present ? 1.0f : 0.0f) - signal_) * (1.0f - std::exp(-dt / signal_tau));

    if (has_tag_ && !color_ready_) {
      color_wait_t_ += dt;
      if (color_wait_t_ >= color_wait) {
        target_ = color_ = {1, 1, 1};
        hold_ = default_hold;
        color_ready_ = true;
      }
    }
    float k = 1.0f - std::exp(-dt / 0.12f);
    color_.r += (target_.r - color_.r) * k;
    color_.g += (target_.g - color_.g) * k;
    color_.b += (target_.b - color_.b) * k;

    phase_t_ += dt;
    switch (phase_) {
      case Phase::kIdle: {
        float want = color_ready_ ? clamp01((signal_ - signal_floor) / (signal_full - signal_floor)) : 0.0f;
        // Колебания сигнала на краю зоны ридера не двигают кольцо: цель меняется, только
        // если сигнал ушёл дальше deadband и держится там — вверх недолго, вниз дольше.
        rise_t_ = (want >= 1.0f || want > goal_ + deadband) ? rise_t_ + dt : 0.0f;
        drop_t_ = (want < goal_ - deadband || (want <= 0.0f && goal_ > 0.0f)) ? drop_t_ + dt : 0.0f;
        if (rise_t_ >= rise_after || (want >= 1.0f && goal_ < 1.0f && rise_t_ > 0)) goal_ = want;
        if (drop_t_ >= drop_after) goal_ = want;
        bool partial = goal_ > 0.0f && goal_ < 1.0f;
        if (goal_ > level_) {
          level_ = std::min(goal_, level_ + dt / (partial ? partial_time : fill_time));
        } else {
          level_ = std::max(goal_, level_ - dt / (partial ? partial_time : empty_time));
        }
        bri_ = 1;
        high_t_ = (level_ >= 1.0f && signal_ >= placed_level) ? high_t_ + dt : 0.0f;
        if (high_t_ >= placed_after) go(Phase::kPulse);
        break;
      }
      case Phase::kPulse:
        bri_ = 1.0f - pulse_depth * std::sin(kPi * std::min(phase_t_ / pulse_time, 1.0f));
        if (signal_ < removed_level) {
          recede();
        } else if (phase_t_ >= pulse_time) {
          go(Phase::kHold);
        }
        break;
      case Phase::kHold:
        bri_ = 1;
        if (signal_ < removed_level) {
          recede();
        } else if (phase_t_ >= hold_) {
          go(Phase::kFade);
        }
        break;
      case Phase::kFade:
        bri_ = 0.5f * (1.0f + std::cos(kPi * std::min(phase_t_ / fade_time, 1.0f)));
        if (phase_t_ >= fade_time) go(Phase::kDone);
        break;
      case Phase::kRecede:
        level_ = std::max(0.0f, level_ - dt / empty_time);
        bri_ = 1;
        if (level_ <= 0.0f) {
          goal_ = 0;
          go(Phase::kIdle);
        }
        break;
      case Phase::kDone:
        bri_ = 0;
        if (signal_ < removed_level) {
          level_ = goal_ = 0;
          go(Phase::kIdle);
        }
        break;
    }
  }

  RingRgb pixel(int i) const {
    if (phase_ == Phase::kIdle && level_ <= 0.001f && status_ != Status::kOk) {
      float b = status_level * 0.5f * (1.0f - std::cos(2.0f * kPi * status_t_ / status_period));
      RingRgb c = status_ == Status::kWifiSetup ? RingRgb{0.1f, 0.3f, 1.0f} : RingRgb{1.0f, 0.5f, 0.0f};
      return {c.r * b, c.g * b, c.b * b};
    }
    int d = ((i - start) % kPixels + kPixels) % kPixels;
    int k = d < kPixels / 2 ? d : kPixels - 1 - d;
    float v = clamp01(level_ * (kPixels / 2) - k) * bri_;
    return {color_.r * v, color_.g * v, color_.b * v};
  }

  Phase phase() const { return phase_; }
  float signal() const { return signal_; }
  float level() const { return level_; }
  float goal() const { return goal_; }

 private:
  static constexpr float kPi = 3.14159265f;
  static float clamp01(float v) { return std::clamp(v, 0.0f, 1.0f); }

  void go(Phase p) {
    phase_ = p;
    phase_t_ = 0;
    high_t_ = 0;
  }
  // Метку убрали, пока кольцо горело: пиксели гаснут по очереди от центра к началу.
  void recede() {
    level_ = 1;
    bri_ = 1;
    go(Phase::kRecede);
  }

  Phase phase_ = Phase::kIdle;
  Status status_ = Status::kOk;
  bool started_ = false;
  uint32_t last_ms_ = 0;
  float signal_ = 0, level_ = 0, goal_ = 0, bri_ = 1;
  float phase_t_ = 0, high_t_ = 0, status_t_ = 0, rise_t_ = 0, drop_t_ = 0;
  bool has_tag_ = false, color_ready_ = false;
  float color_wait_t_ = 0, hold_ = 3.0f;
  RingRgb color_{1, 1, 1}, target_{1, 1, 1};
};

// ── Питание ────────────────────────────────────────────────────────────────
// Зарядник USB-C сообщает, сколько готов отдать на 5 В, напряжением на линии CC
// (на резисторе 5.1 кОм в гнезде): до 0.66 В — USB по умолчанию, до 1.23 В — 1.5 А,
// выше — 3 А. Кабель USB-A → C всегда показывает «по умолчанию». Работает одна
// линия CC — та, что соединена кабелем; на второй около 0 В.
// Возвращает мА, 0 — неизвестно (гнездо не подключено, CC не подпаяны, помеха).
inline int usb_c_source_ma(float cc1, float cc2) {
  float lo = std::min(cc1, cc2), hi = std::max(cc1, cc2);
  if (lo > 0.2f || hi < 0.2f || hi > 2.2f) return 0;
  if (hi < 0.66f) return 500;
  if (hi < 1.23f) return 1500;
  return 3000;
}

// Сколько можно отдать кольцу: мощность зарядника с запасом 15 % минус ~0.5 А
// на ESP32 и ридер. Неизвестный или слабый источник — минимум, кольцо тусклое.
inline float ring_budget_ma(int source_ma) {
  constexpr float kSystemMa = 500, kMargin = 0.85f, kFloorMa = 150;
  if (source_ma <= 0) return kFloorMa;
  return std::max(kFloorMa, source_ma * kMargin - kSystemMa);
}

// Приглушает кадр, если оценка тока кольца выше бюджета. Значения 0..1 — до гаммы:
// ESPHome применяет гамму 2.8 уже после, поэтому ток канала ∝ значение^2.8.
// ch_ma — ток одного канала WS2812B на полной яркости (номинал ~20 мА).
// Возвращает множитель, на который приглушили (1 — не трогали).
inline float limit_power(RingRgb *px, int n, float budget_ma, float ch_ma = 20.0f, float gamma = 2.8f) {
  float est = 0;
  for (int i = 0; i < n; i++)
    est += (std::pow(px[i].r, gamma) + std::pow(px[i].g, gamma) + std::pow(px[i].b, gamma)) * ch_ma;
  if (est <= budget_ma || est <= 0) return 1.0f;
  float k = std::pow(budget_ma / est, 1.0f / gamma);
  for (int i = 0; i < n; i++) px[i] = {px[i].r * k, px[i].g * k, px[i].b * k};
  return k;
}

inline float ring_current_ma(const RingRgb *px, int n, float ch_ma = 20.0f, float gamma = 2.8f) {
  float est = 0;
  for (int i = 0; i < n; i++)
    est += (std::pow(px[i].r, gamma) + std::pow(px[i].g, gamma) + std::pow(px[i].b, gamma)) * ch_ma;
  return est;
}

inline RingEngine &ring_engine() {
  static RingEngine engine;
  return engine;
}
