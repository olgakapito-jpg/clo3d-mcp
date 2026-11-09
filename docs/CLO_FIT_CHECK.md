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

## Дальше: SetArrangement indices

ReDrape v2 прошёл native (flags applied, return None), но визуально ничего не
изменил: вероятно, ReDrape только пересчитывает уже назначенный arrangement, а
детали стоят на `Arrangement Point`. Нужно назначить реальные points через
`SetArrangement(patternIndex, arrangementIndex)`, индекс брать из 110-элементной
библиотеки.

`diagnostics/clo3d_mcp_arrangement_list_probe.py` читает `GetArrangementList` и
печатает до110 записей: preset name/type/offset/orientation (read-only, one-shot).
По нему выберем индексы front/back/sleeve и сделаем bounded `set_arrangement`
tool с readback `get_arrangement` + UI.

## Arrange probe: SetArrangement + ReDrape

`diagnostics/clo3d_mcp_arrange_probe.py` назначает own-деталям реальные
arrangement points и делает один ReDrape:

- MCP_3D_TEST → 59 Body_Front_Center_1
- MCP_SEAM_A → 60 Body_Front_Center_2
- MCP_SEAM_B → 43 Body_Back_Center_2
- MCP_SEAM_C → 6 Arm_Front_1_L
- MCP_SEAM_D → 0 Arm_Back_1_L

Пять `SetArrangement` + readback имени + один ReDrape с ApiTypes option/flags.
One-shot, no retry; exception на assign/redrape → STOP. Effect visual-only; если
детали встали на аватар — оформляем `set_arrangement` tool и повторяем ReDrape
через отдельный tool.

## Следующие шаги

1. Визуально проверить, как A–D/MCP_3D_TEST стоят на аватаре (плоско/пересечения).
2. `get_arrangement` уже реализован (23 tools); при необходимости
   `set_arrangement_position`/`orientation` с readback.
3. Drape/посадка: ReDrape упирается в недоступный ImportExportOption; либо
   найти доступный option, либо UI-only gate (честно visual-only).
4. Sewing/seams к аватару уже возможны через lineIndex; simulation отдельно.
