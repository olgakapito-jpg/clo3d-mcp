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

## Следующие шаги

1. Probe → определить arrangement state и поля.
2. Если позиции/ориентации читаемы и settable — bounded tool(s)
   `get_arrangement`/`set_arrangement_position`; проверка readback.
3. Drape: либо найти доступный option/фактический вызов, либо UI-only gate
   (честно visual-only), без обещаний fit/3D acceptance.
4. Sewing/seams к аватару уже возможны через lineIndex; simulation отдельно.
