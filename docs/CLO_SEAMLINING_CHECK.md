# Швы (seamline pairs) — контракт и bounded probe

Target: CLO2026.1.336. Статус: **contract review + один real probe подготовлен;
MCP tool ещё не реализован**. Это отдельный домен, не продолжение построения.

## API-факты

- `pattern_api.AddSeamlinePairGroup` — три overload:
  - `(patternA, lineA, patternB, lineB, directionA, directionB) -> bool`
  - `(patternA, lineA, patternB, childIndex, lineB, directionA, directionB) -> bool`
  - `(patternA, childA, lineA, patternB, childB, lineB, directionA, directionB) -> bool`
- Docstring первого overload противоречит сигнатуре: `@return name of sewing
  group` при объявленном `-> bool`. Реальный literal/тип нужно наблюдать.
- `directionA/B`: true forward, false backward. Порядок и направление пары
  влияют на stitch orientation; фиксировать явно.
- `lineIndex` — линия границы в порядке обхода; брать из свежего
  `GetPatternLineInfo` (`lineIndex`), не из позиции массива. Child overloads
  используют child namespace и в первый tool не входят.
- Reads: `GetSeamlinePairGroupCount`, `GetSeamlinePairGroupName`,
  `GetSeamlinePairGroupListInPattern`;
  `GetPatternGroupsBySeamlineConnectivity(bool,bool)` → JSON groups.
- `AddSeamlinePairGroupPartial` возвращает `int`, `SEAMLINE_PAIR_SUCCESS=0`;
  ratios start<end; отдельный следующий пакет.
- `MergeSewnPatterns`, `DeleteLine` — destructive, не в первый пакет.

## Probe

`diagnostics/clo3d_mcp_seam_probe.py`, один Run, verified idle service:

1. Находит own `MCP_SEAM_A`/`MCP_SEAM_B` (уже созданы, 120×80), уникальные имена.
2. Берёт `lineIndex=0` у обеих (длины120), снимает lines/geometry/seam count.
3. Один `AddSeamlinePairGroup(A,0,B,0,True,True)`.
4. Читает native return type/literal, seam count/connectivity, lines/geometry
   после; имена групп не выводятся.
5. Один native seam call, без retry; exception → STOP.

Ожидаемый JSON `clo_seam_probe_v1`: `seams_before/after`, `native_return_type`,
`native_return`/`native_return_int`, `lines_after == lines_before`,
`geometry_after == geometry_before`, `connectivity_after.group_count`.

## Границы

- Только own pieces; чужие детали не трогать.
- Если seam count не вырос или geometry/lines изменились — считать неизвестным
  эффектом, не повторять и не удалять.
- Partial seam, topstitch, buttons, merge — отдельные пакеты.
- После probe own pieces/seam остаются; удаление — отдельными fresh-list шагами.

## Будущий MCP tool (proposal)

`add_seamline_pair`: strict args `pattern_a_index/expected_name_a/line_a_index,
pattern_b_index/expected_name_b/line_b_index,direction_a,direction_b`; preflight
fresh list/lines, one native call, result `verified,seam_count,seam_group_index`;
errors `stale_pattern`, `invalid_line_index`, `invalid_native_result`,
`scene_change_unverified`, `command_error`; no retry/cleanup. Return literal
`AddSeamlinePairGroup` не считать успехом без readback seam count.

Local tests: `tests/test_seam_probe.py`.
