# Texts for Medium, Habr and LinkedIn

Replace the placeholders in square brackets before posting. The line about the AI assistant is
optional but recommended.

---

## Medium (English)

**Title:** Where, Not How Much: What I Learned About Noise in Flow-Matching Samplers

**Subtitle:** A negative result on curvature, a small model-dependent effect, and a human study that did not see it.

Image generators built on flow matching can be run with a stochastic sampler, which adds fresh
noise at every step. How strong that noise is (a parameter called `eta`) is usually set once by hand
and left constant. I wanted to know whether the sampler could choose it by itself, step by step,
from information it already has for free.

The idea was simple. At every step a multistep solver can compute how sharply the trajectory is
bending (its curvature) and how much its prediction and correction disagree. If noise is
harmful where the field is "stiff" and useful where it is smooth, then spending a fixed noise
budget according to curvature should beat a constant, at no extra cost in network evaluations.

I built it as a node for ComfyUI and tested it on three open models (Anima, Flux 3 Klein,
MOSS-Image) at 6–15 steps, always comparing against a constant-`eta` run that spends exactly the
same total noise. That control matters: without it, "adaptive" results are usually just "less noise".

**What I found**

- **Curvature did not work.** On none of the three models did it give a stable benefit. The sign of
  the effect flipped with the number of steps.
- **The solver's own error estimate did work a little.** Putting more noise where the error is
  small gave a gain on Flux 3 Klein of about 1–2 % of the texture value. It held on fresh seeds
  under criteria I wrote down before running. On MOSS-Image the effect was one-sided, and on
  Anima I could not detect it.
- **The adaptation was not the point.** A fixed schedule, averaged from independent runs and
  applied to every image, gave the same result. Noise at the two ends of the noise window helps;
  noise in the middle matters less. It is where the noise goes that counts, not what the sampler sees.
- **People could not tell.** In a forced-choice study with 39 respondents, people clearly saw the
  difference between weak and strong noise, but could not tell the new allocation from plain noise.

This is mostly a negative result, and I think it is worth sharing as one. The code, per-image
numbers and survey analysis are open: [repository link]. A preprint is here: [preprint link].

*[Optional: I used an AI assistant (Claude) for coding, running the experiments and drafting; I take responsibility for the content.]*

---

## Habr (русский)

**Заголовок:** Не сколько, а куда: что я выяснил про шум в SDE-сэмплерах flow-matching моделей

**Хабы (предложение):** Машинное обучение, Искусственный интеллект, Open source.

Генераторы изображений на flow matching можно запускать со стохастическим сэмплером: на каждом
шаге он подмешивает свежий шум. Сила этого шума (параметр `eta`) обычно подбирается руками один
раз и остаётся константой. Я хотел понять, может ли сэмплер выбирать её сам, шаг за шагом, из
информации, которая у него уже есть бесплатно.

**Идея.** Многошаговый решатель на каждом шаге может посчитать, насколько резко изгибается
траектория (кривизна), и насколько расходятся его предсказание и поправка (оценка ошибки). Если
шум вредит там, где поле «жёсткое», и полезен там, где оно гладкое, то фиксированный бюджет шума,
распределённый по кривизне, должен обыгрывать константу без единого лишнего вызова сети.

**Что сделано.** Нода для ComfyUI, проверка на трёх открытых моделях (Anima, Flux 3 Klein,
MOSS-Image) на 6–15 шагах. Главное в методике: каждый адаптивный запуск сравнивается с запуском
с постоянной `eta` и **точно таким же суммарным бюджетом шума**. Без этого «адаптивный» результат
чаще всего оказывается просто «меньше шума» (в моей прошлой работе так и вышло).

**Результаты**

- **Кривизна не сработала.** Ни на одной модели стабильного выигрыша нет; знак эффекта меняется
  с числом шагов.
- **Оценка ошибки самого решателя сработала немного.** Если шума больше там, где ошибка мала,
  на Flux 3 Klein выигрыш около 1–2 % от значения текстуры. Он подтвердился на новых seed по
  критериям, записанным до запуска. На MOSS-Image эффект односторонний, на Anima я его не обнаружил.
- **Адаптация оказалась не нужна.** Фиксированный график, усреднённый по независимым запускам и
  применённый ко всем картинкам, даёт тот же результат. Шум на краях окна шума помогает, в
  середине важен меньше. Важно, куда попадает шум, а не что видит сэмплер.
- **Люди разницы не увидели.** В опросе на 39 человек (какая из двух картинок «больше похожа на
  ИИ») большую разницу между слабым и сильным шумом люди заметили, а новое распределение от
  обычного шума отличить не смогли.

**Ограничения.** Метрики считаются в латентном пространстве, а не по глазам; по умолчанию 16 пар
картинок на бюджет; на Krea 2 вышел неубедительный результат из-за недостатка мощности; на
Anima использована другая версия ComfyUI, чем на остальных; опрос неформальный, без отбора.

Это в основном отрицательный результат, и я считаю, что о таком стоит рассказывать. Код, числа
по каждой картинке и разбор опроса открыты: [ссылка на репозиторий]. Препринт: [ссылка на препринт].

*[По желанию: при работе я использовал ИИ-ассистента (Claude) для кода, запуска экспериментов и черновика; за содержание отвечаю я.]*

---

## LinkedIn (English)

I just finished a small research project on stochastic samplers for flow-matching image models,
and the headline is a negative result.

Question: can a sampler set its own noise strength, step by step, from information it already
has for free (trajectory curvature and its own error estimate), and beat a hand-picked constant
at 6–15 steps?

What I did: built it as a ComfyUI node and tested it on Anima, Flux 3 Klein and MOSS-Image, always
against a constant-noise run that spends exactly the same total noise.

What I found:
• Curvature: no stable effect on any model.
• The solver's error estimate: a small gain on Flux 3 Klein (about 1–2 % of the texture value),
  confirmed on fresh seeds under criteria set in advance. One-sided on MOSS-Image, not detectable
  on Anima.
• A fixed schedule reproduced the gain, so adaptation wasn't needed. Where the noise goes matters.
• In a 39-person forced-choice study, people saw big noise differences but could not tell the new
  allocation from plain noise.

Code, per-image metrics and the preprint are open: [link]

#MachineLearning #DiffusionModels #FlowMatching #GenerativeAI #OpenScience
