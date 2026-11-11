---
name: clo-seamlines
description: Operate CLO seam pairs safely: whole-line add_seamline_pair and partial add_seamline_pair_partial; convert exported perimeter fractions to line-relative API ratios, decompose multi-segment reference edges, validate intervals and verify seam_count. Use before any seam mutation or when a seam result is uncertain.
---

# CLO: швы (`add_seamline_pair`, `add_seamline_pair_partial`)

Сначала прочитать корневой `AGENTS.md`, `clo-tool-workflows` и `clo-sewing`
(сборка изделия важнее выбора индексов). Точные контракты:
`docs/CLO_MCP_TOOLS.md` §21 и §49; evidence: `docs/CLO_SEAMLINING_CHECK.md`.

## Область

- `add_seamline_pair` соединяет **одну whole outer line** детали A с **одной**
  whole outer line детали B, 6-аргументный overload.
- `add_seamline_pair_partial` соединяет **участок** одной whole outer line с
  участком другой; ratios задаются относительно длины этой линии. Одинаковые
  детали (`pattern_a == pattern_b`) разрешены — так делаются darts, вытачки и
  waistband self-seam; whole-line tool такие пары отклоняет.
- Один вызов = одна пара участков = один seam group. Замкнутая труба из двух
  панелей требует **двух** вызовов (левый и правый боковые швы); см. `clo-sewing`.
- Не входят: child overloads, `MergeSewnPatterns`, `DeleteLine`, topstitch,
  buttons, seam allowance. Публичного удаления швов нет: сброс — только
  `import_pattern_json` на расходной сцене или перезагрузка проекта.
- `import_pattern_json` в этой сборке **не восстанавливает** швы: live-импорт
  5 деталей дал `seam_count_after=0`. JSON — источник деталей, швы добавляются
  вызовами seam tools.

## Семантика ratios (live-калибровка 2026-11-11)

Главное: **вход и export нормированы по-разному**.

- Входные `start_ratio`/`end_ratio` — **line-relative**: доля длины конкретной
  линии из `get_pattern_lines`. `0.25–0.75` на линии 80 мм = участок 20–60 мм.
- Входные ratios всегда **возрастающие**: `start < end` на каждой стороне.
  `direction=true/false` кодирует ориентацию стежка, а не порядок чисел.
  Descending input (`0.9 → 0.3`) native отклоняет: `invalid_native_result`,
  `seam_count` не меняется. Это проверено live.
- `export_pattern_json` пишет `LengthParam` как **долю периметра всей детали**
  от начала обхода (`LineList[0].PointList[0]`):

```text
export = (prefix_offset(line) + ratio * line_length) / pattern_perimeter
ratio  = (export * pattern_perimeter - prefix_offset(line)) / line_length
```

- `prefix_offset(line)` — сумма длин всех предыдущих линий `LineList` в порядке
  обхода. Для `line0` offset = 0, поэтому там формула вырождается в
  `export = ratio * line_length / perimeter`; для остальных линий это неверно.
- `direction=false` лишь меняет порядок в export: `fStart` соответствует
  входному `end`, поэтому export выглядит descending. Физический участок тот
  же; повторно передавать descending в API нельзя.
- snapping по насечкам не выполняется; ratios применяются буквально.

Калибровочные точки (прямоугольники, проверено export-ом):

| Деталь | Линия | Периметр | Вход | Export |
| --- | --- | --- | --- | --- |
| CAL_A/B 120×80 | line0, 120 мм | 400 | 0.25–0.75 | 0.075–0.225 |
| CAL_A/B 120×80 | line1, 80 мм | 400 | 0.25–0.75 | 0.350–0.450 |
| CAL_C/D 200×100 | line1, 100 мм | 600 | 0.25–0.75 | 0.375–0.45833 |
| CAL_C/D 200×100 | line3, 100 мм | 600 | 0.0–0.5 | 0.83333–0.91667 |
| CAL_A/B 120×80 | line3, 80 мм | 400 | 0.30–0.90, dir false | 0.980–0.860 |

Обратное преобразование export → API проверено: все 7 калибровочных швов
восстановили исходные ratios с точностью до float.

## Reference-проект: швы на multi-segment edges

Ручной эталон содержит **20 seam groups, но это не 20 швов по одной линии**.

- Каждая сторона группы ссылается на один `LineID`, а `LengthParam` покрывает
  **непрерывный пробег нескольких соседних линий**: например группа 0 — это
  `BACK_L` линии 4→11 (~1064.8 мм) ↔ `FRONT_L` линии 27→19 (~1064.6 мм).
- Концы таких пробегов совпадают с границами линий эталона с точностью 0.000 мм;
  исключение — пояс `WAISTBAND line2`, где интервалы лежат внутри одной линии
  и делят её на последовательные части.
- API работает с одной линией за вызов: вызов по `line0` панели из 5 точек
  сшил только 60.8 мм из 120 мм кромки (export `fEnd=0.15144`). Merge-lines/
  edge-path API нет; `DeletePoint` не опубликован и уничтожил бы насечки.
  Поэтому reference-группу нельзя передать как один partial seam:
  `LengthParam` эталона — это perimeter-доли, а не line-relative ratios.
  Прямая передача даёт неверные позиции, наложения и предупреждение CLO
  «abnormal/overlapped seamlines».
- Рабочий путь: **декомпозиция пробега на пары отдельных линий** по общим
  относительным позициям вдоль пробега. Для эталона это 91 сырая пара;
  11 sub-0.5mm slivers отбрасываются, остаётся 80 dispatchable. Расхождение
  длин сторон — посадка/ease (в эталоне до 20.6 мм), его фиксируют, а не
  «исправляют» ratios; точный дубль сегмента между группами — отдельное
  предупреждение.
- Альтернатива — смоделировать каждую кромку одной `Polyline`-линией
  (промежуточные точки, концы `Straight`). Тогда один вызов кроет всю кромку.
  `seam_plan.py --curve-target` даёт 38 пар для такой топологии; `BACK_*`
  линий 18, `FRONT_*` 15. Цена: насечки теряются как точки, side-кромка
  удлиняется на ~1.4 мм; длину проверять после импорта.

## Preflight

1. `get_session_info`: `ready`, `connected`, `executor_verified`, нет busy/error.
2. `get_pattern_list`: обе детали существуют, имена уникальны.
3. `get_pattern_lines` для A и B: `line_count`, `line_index`, `length_mm`,
   `orientation`, `location`, `start_mm`/`end_mm`.
4. Построить физический план: для каждой пары — линия A/линия B, интервал в мм
   вдоль линии, ascending ratios, direction.
5. Прогнать валидатор **до** dispatch (см. ниже). Ошибка плана — не начинать.

## Валидатор плана (обязателен)

- Для каждой стороны: `0 <= start_ratio < end_ratio <= 1`; интервал
  `[start*L, end*L]` не выходит за длину линии.
- Для каждой линии собрать все покрытые интервалы; запретить overlap и
  дубликаты (допустимы только стыки `end == next start` в пределах float).
- Multi-segment run: разбить на подынтервалы по границам линий; каждая
  подпара должна лежать внутри одной линии.
- Сверить длины двух сторон каждой пары: расхождение больше ~1 мм — STOP,
  это ошибка сопоставления кромок, а не повод «подтянуть» ratios.
- Не передавать в API значения из `LengthParam` reference-файла и не
  конвертировать их «на глаз»: только формулы выше или декомпозиция.

## Вызов и проверка

1. Один seam-вызов с точными свежими индексами и валидированными ratios.
2. Проверить `ok:true`, `verified:true`, `seam_count` = прежний + 1.
3. Независимый readback: `get_pattern_lines` обеих деталей — line_count,
   длины и порядок не изменились; `get_pattern_geometry` — area/bbox/position
   не изменились.
4. Только после этого — следующий шов.
5. Визуальная проверка — отдельное наблюдение. Перекрёст/разрыв или красные
   seamlines = STOP, не добавлять швы; `seam_count` это не обнаруживает.
6. `export_pattern_json` после серии — единственный способ увидеть сохранённые
   `LengthParam`; сверить ожидаемую формулу для каждой пары.

## Порядок для брюк

1. Импорт деталей (`import_pattern_json`), seams=0.
2. Четыре leg-шва (side/inseam) — по одному whole-line вызову на кромку;
   readback + 3D после серии.
3. Центральные швы (center front/back).
4. Пояс — последним, включая self-seam; именно он чаще даёт abnormal seamlines.
5. `set_arrangement` для всех деталей: `Leg_Front_L`/`Leg_Back_L`/
   `Leg_Front_R`/`Leg_Back_R`, пояс `Body_Waist_L` + orientation 180.
6. `simulate(120)` → скриншот. 60 шагов может оставить переходные дыры у
   crotch; это не topology error, пока повторная симуляция не подтвердила.

## Отказы

- `stale_pattern`/`invalid_parameters`: заново прочитать list/lines, не
  повторять старый вызов.
- `invalid_native_result`: native вернул non-zero или не вырос `seam_count`.
  Сцену считать изменённой; не повторять, не «доклеивать» соседний участок.
- `outcome_unknown`/timeout/session change: STOP mutations; read-only сверка
  при доступном executor, затем сброс сцены импортом на расходном проекте.
- Никакого автоматического rollback, delete, merge или cleanup после ошибки.
- `seam_count` без независимого readback не доказывает неизменность geometry.

## Anti-patterns

- Считать export `LengthParam` line-relative или умножать его на `P/L`.
- Передавать descending ratios, потому что export был descending.
- Сшивать reference-группу одним вызовом по её первому `LineID`.
- Сшить `line0` с `line0`, потому что это первый индекс.
- Один шов A↔B и назвать результат цилиндром.
- Массово сшивать все пары без плана, валидатора и readback после каждого.
- Повторять dispatched seam после timeout/unknown.
- Удалять детали, чтобы «сбросить» швы, без явного разрешения.
