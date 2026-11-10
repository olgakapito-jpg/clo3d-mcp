---
name: clo-seamlines
description: Operate CLO whole-line seam pairs safely: enumerate outer lines, choose line indices and directions, call add_seamline_pair once per edge pair, verify seam_count and unchanged geometry. Use before any seam mutation or when a seam result is uncertain.
---

# CLO: whole-line seam pairs (`add_seamline_pair`)

Сначала прочитать корневой `AGENTS.md`, `clo-tool-workflows` и `clo-sewing`
(сборка изделия важнее выбора индексов). Точный контракт tool:
`docs/CLO_MCP_TOOLS.md` §21; evidence: `docs/CLO_SEAMLINING_CHECK.md`.

## Область

- `add_seamline_pair` соединяет **одну whole outer line** детали A с **одной**
  whole outer line детали B, 6-аргументный overload.
- Один вызов = одна пара кромок = один шов. Замкнутая труба из двух панелей
  требует **двух** вызовов (левый и правый боковые швы); см. `clo-sewing`.
- Не входят: partial ratios, child overloads, topstitch, buttons,
  `MergeSewnPatterns`, удаление/список seam pairs. Не изобретать эти вызовы.
- Нет MCP getter-а для списка швов; единственный счётчик — `seam_count` в
  результате mutation. Не считать его полным описанием изделия.

## Args и identity

- `pattern_a_index`, `expected_name_a`, `pattern_b_index`, `expected_name_b` —
  из fresh `get_pattern_list`; имя уникально, индекс не durable ID.
- `line_a_index`/`line_b_index` — `line_index` из fresh `get_pattern_lines`,
  **не** позиция в массиве и не outline point index.
- `direction_a`/`direction_b` — строгие native bool: `true` forward, `false`
  backward. Они задают, с какого конца начинается шов; не считать `True/True`
  универсально правильным.
- Lines должны быть whole outer lines; child/internal/partial не входят.

## Preflight

1. `get_session_info`: `ready`, `connected`, `executor_verified`, нет busy/error.
2. `get_pattern_list`: обе детали существуют, имена уникальны.
3. `get_pattern_lines` для A и B: сохранить `line_count`, `line_index`,
   `length_mm`, `orientation`, `location`, `start_mm`/`end_mm`.
4. Выбрать пары кромок по смыслу (left↔left, right↔right, равная длина),
   а не по `line0↔line0`.
5. Зафиксировать выбранные индексы и направления в плане до mutation.

## Вызов и проверка

1. Один `add_seamline_pair` с точными свежими индексами.
2. Проверить `ok:true`, `verified:true`, `seam_count` = прежний + 1.
3. Независимый readback: `get_pattern_lines` обеих деталей — line_count,
   длины и порядок не изменились; `get_pattern_geometry` — area/bbox/position
   не изменились.
4. Только после этого — следующий шов; для трубы это вторая боковая пара.
5. Визуальная проверка шва — отдельное наблюдение, не доказанное `seam_count`.
   Проверить, что новый шов не перекрещивает соседний: перекрёст = STOP,
   не добавлять швы; `seam_count` его не обнаруживает. `True/True` на обеих
   сторонах трубы дал перекрёст в live-сцене — правило направлений не установлено.

## Отказы

- `stale_pattern`/`invalid_parameters`: заново прочитать list/lines, не
  повторять старый вызов.
- `scene_change_unverified`/`command_error`/unknown/session change: STOP
  mutations; отдельно bounded read-only сверка при доступном executor.
- Если первый шов прошёл, а второй нет — явно сообщить «частичная сборка,
  труба открыта»; не выдавать за закрытую и не делать retry.
- Никакого автоматического rollback, delete, merge или cleanup после ошибки.
- `seam_count` без независимого readback не доказывает неизменность geometry.

## Anti-patterns

- Сшить `line0` с `line0`, потому что это первый индекс.
- Один шов A↔B и назвать результат цилиндром.
- Использовать outline endpoints как `lineIndex`.
- Массово сшивать все пары линий без плана и без readback после каждого.
- Повторять dispatched seam после timeout/unknown.
- Удалять детали, чтобы «сбросить» швы, без явного разрешения.
