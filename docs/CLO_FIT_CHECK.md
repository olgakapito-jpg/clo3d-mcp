# Avatar + arrangement/fit — статус и probe

Target: CLO2026.1.336.

## Avatar import — live PASS

`import_avatar` с absolute `.avt` (≤128MiB) через live `ImportFile(path)->bool`
(ImportAvatar недоступен: его `ImportExportOption` тип отсутствует в binding).
Live gate 2026-11-09, build `5baaf8a15555`: `avatar_count 0→1`,
name `Female_Mannequin_final_v11_Aforsize_03`; path не эхоился.

## Arrangement — блокер и probe

- GetArrangementList/GetArrangementOfPattern (+setters) доступны.
- `ReDrape3DArrangement(opt)` требует `Marvelous::ImportExportOption`; в live
  `export_api.ImportExportOption/NewImportExportOption` available=false.
  Drape через MCP пока не подтверждён.
- `diagnostics/clo3d_mcp_arrangement_probe.py` читает arrangement для всех
  деталей (≤32) и печатает keys + numeric/bool values, строки только type/len.
  Один Run, idle service, без мутаций и retry. Нужен, чтобы понять:
  arranged ли детали после avatar import, какие индексы/поля использовать.

Ожидаемый JSON `clo_arrangement_probe_v1`: `count`, `list_length`,
`pieces[i].arrangement.keys/fields`.

## 3D visibility: уточнено 2026-11-09

Пять деталей (A–D seam + MCP_3D_TEST) имеют одинаковый arrangement (`Arrangement
Point`, offsets50/50/50, orientation180, typeCurved). **Все пять видны в 3D.**
Первые четыре были за пределами экрана; пользователь увидел их после zoom-out.
Значит 2D-координата и 3D-положение независимы, а сшитость не скрывает детали.
Предыдущая гипотеза про необходимость simulation для видимости **опровергнута**;
simulate probe не нужен и не запускался.

## ReDrape через ApiTypes.ImportExportOption

`utility_api.ReDrape3DArrangement` требует `Marvelous::ImportExportOption`.
`export_api.ImportExportOption/NewImportExportOption` в live недоступны, но тип
документирован как `ApiTypes.ImportExportOption` с полями
`bAddArrangementPoints`, `bAutoCreateFittingSuit`, `bMoveGarment`.
`diagnostics/clo3d_mcp_redrape_probe.py` создаёт option через `ApiTypes`,
ставит эти флаги (если есть), вызывает ReDrape один раз и печатает counts.
One-shot, avatar>=1, visual-only evidence; при option/construct/API exception —
STOP. После Run пользователь смотрит 3D: появились ли детали на аватаре.

## Следующие шаги

1. Визуально проверить, как A–D/MCP_3D_TEST стоят на аватаре (плоско/пересечения).
2. `get_arrangement` уже реализован (23 tools); при необходимости
   `set_arrangement_position`/`orientation` с readback.
3. Drape/посадка: ReDrape упирается в недоступный ImportExportOption; либо
   найти доступный option, либо UI-only gate (честно visual-only).
4. Sewing/seams к аватару уже возможны через lineIndex; simulation отдельно.
