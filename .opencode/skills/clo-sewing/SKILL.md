---
name: clo-sewing
description: Plan and review CLO garment assembly with seamline pairs. Use when asked to sew pieces into a garment, close a tube or cylinder, choose which edges to sew, or judge whether an assembly is closed. One seam pair joins one edge pair; a two-panel tube needs both side seams.
---

# CLO: сшивание деталей в изделие

Сначала прочитать корневой `AGENTS.md`, `clo-tool-workflows` и `clo-seamlines`;
точные контракты — `docs/CLO_MCP_TOOLS.md` §21,
`docs/CLO_SEAMLINING_CHECK.md`, рецепты — `docs/CLO_MCP_WORKFLOWS.md`.

## Главное правило

`add_seamline_pair` соединяет **одну** линию детали A с **одной** линией
детали B. Один успешный вызов — это один шов, а не замкнутое изделие.

- Две панели в цилиндр/трубу: нужны **два боковых шва** —
  `A.left ↔ B.left` и `A.right ↔ B.right`, каждый отдельным вызовом.
- Одна панель в цилиндр: сшить две противоположные боковые линии этой же
  детали (один шов).
- Не сшивать `line0` с `line0` только потому, что это первый индекс.
  Сопоставлять физические кромки по `location`, `orientation`, `length_mm`,
  `start_mm`/`end_mm` из `get_pattern_lines`.
- Замкнутость — топология, а не посадка: она не доказывает отсутствие
  пересечений с аватаром и не заменяет simulation.

## Сопоставление кромок

1. Fresh `get_pattern_list`; обе детали уникальны по имени.
2. `get_pattern_lines` для A и B; сохранить `line_index`, длину,
   orientation, location, start/end.
3. Выбрать пары равной длины и соответствующего location:
   left↔left, right↔right, front↔front и т.п. Для трубы нужны именно
   боковые (вертикальные) кромки, а не bottom↔bottom.
4. Проверить направление обхода: `direction_a`/`direction_b` задают, с какого
   конца начинается шов. Для трубы без перекрута начала обеих линий должны
   соответствовать одному физическому концу (верх↔верх, низ↔низ).
   Не считать `True/True` универсальным.
5. После каждого вызова — `verified` и `seam_count` +1, затем независимый
   readback линий/geometry. Только потом следующий шов.

## Partial seams и составные кромки

- `add_seamline_pair_partial` соединяет участок линии, а не всю кромку. Ratios
  **line-relative** (`0 <= start < end <= 1`); `direction` отдельно, descending
  input native отклоняет. Подробности и формулы — `clo-seamlines`.
- Кромка, разбитая насечками на несколько `LineList`-линий, — это несколько
  линий, а не одна. Ручной эталон может хранить один seam group на весь пробег
  линий (`LineID` первой линии + perimeter-доли). Одним partial-вызовом такой
  пробег не воспроизводится: декомпозировать на пары отдельных линий по
  относительным позициям вдоль пробега.
- Перед dispatch: валидатор интервалов (в пределах линии, без overlap и
  дубликатов на одной линии) и сверка длин сторон пары. Не передавать
  `LengthParam` reference-файла напрямую.
- `export_pattern_json` хранит `LengthParam` как долю **периметра детали**;
  не путать с входными line-relative ratios.
- `import_pattern_json` импортирует детали, но в этой сборке не восстанавливает
  швы (`seam_count_after=0`). Швы добавляются отдельными вызовами.
- Вытачки и self-seam (пояс в кольцо) — только `add_seamline_pair_partial`:
  `add_seamline_pair` отклоняет одинаковые детали (`invalid_parameters`).

## Рецепт: труба из двух панелей

- Preconditions: ready session, fresh list, обе детали с 4 outer lines,
  доступны `get_pattern_lines` и `add_seamline_pair`.
- Шаг 1: `add_seamline_pair(A, leftA, B, leftB, dirA, dirB)`.
- Readback: `seam_count` вырос на 1; line count/длины/geometry не изменились.
- Шаг 2: `add_seamline_pair(A, rightA, B, rightB, dirA, dirB)`.
- Readback: `seam_count` вырос ещё на 1; визуально боковые кромки соединены.
- Только теперь труба топологически замкнута, если нет других разрывов.
  Посадка/пересечения с аватаром проверяются отдельно (visual/simulation).

## Перекрёст швов (наблюдено live)

Два боковых шва могут лечь **перекрестно** — труба перекручена. Это не повод
добавлять третий шов.

- Остановить сборку; `seam_count` перекрёст не показывает, нужна визуальная
  проверка 3D.
- Проверить направления выбранных пар: `True/True` на обеих сторонах дал
  перекрёст на live-паре A/B (120×80). Универсального правила направлений пока
  нет; не записывать `True/True` как рецепт.
- Исправление: reversed direction на одной паре **или** развернуть панель
  вручную гизмо и заново проверить 3D. Изменение 3D-поворота через arrangement
  API не подтверждено.
- После исправления заново проверить оба бока; не считать `verified`/`seam_count`
  доказательством отсутствия перекрёста.

## Anti-patterns

- Один шов A↔B и вывод «цилиндр готов».
- Шов bottom↔bottom или top↔top для боковой трубы.
- `line0↔line0` по порядку массива без проверки кромки.
- Массовое сшивание всех пар линий без плана.
- Повторный вызов после error/unknown, чтобы «доклеить» шов.
- Удаление/merge деталей как автоматическая очистка после ошибки.
- Заявление посадки или закрытости только по `seam_count`.

## Stop rules

- `stale/invalid/unknown/session change` — остановить сборку, не повторять.
- Если первый боковой шов прошёл, а второй нет — сообщить «открытая труба,
  частичный шов», не выдавать её за закрытую и не делать retry.
- Нет MCP tool для удаления швов; список/участие — `get_seamline_pairs`.
  Не изобретать delete/merge; сброс — импорт на расходной сцене.
- Evidence: `docs/CLO_SEAMLINING_CHECK.md`, `docs/CLO_MCP_WORKFLOWS.md`.
