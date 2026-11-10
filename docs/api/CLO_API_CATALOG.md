# A0: общий реестр official / runtime / donor / local / current

Target только **CLO2026.1.336**, SDK11.0.1. Это offline source specification,
не исполнение native API и не публикация новых tools. Обновляется командой
`uv run --frozen python scripts/build_api_coverage.py`; проверка без записи:
`uv run --frozen python scripts/build_api_coverage.py --check`.

## Denominator и точность

- Official qualified Python names: **890** (включая GUI).
- Уникальные нормализованные объявления/overloads: **1134**.
- Отдельные документированные types/options: **77**; дополнительные
  interfaces: **6**. Не прибавляются к implemented tools.
- Donor tools: **170**, local legacy: **47**,
  current enabled tools: **44**, current native-operation scopes: **52**.
- Исторические docstring observations: **43** names;
  это presence/callability на уровне symbol, не точная проверка overload.
- Official names со static donor mapping: **332**;
  с legacy mapping: **50**. Это не coverage реализации.

| Module | Unique declarations |
|---|---:|
| `export_api` | 123 |
| `fabric_api` | 284 |
| `gui_api` | 39 |
| `import_api` | 42 |
| `pattern_api` | 233 |
| `rest_api` | 8 |
| `utility_api` | 405 |

`clo_api_coverage.json` содержит index/counts/input hashes и coverage shards с
hash/count; все строки включают id/symbol/signature/docs evidence, runtime/binding,
owner/domain, donor/legacy links, current-operation reference, dependencies и gates.
Полные parameters/returns/docs prose/C++ pair/type-member details — в official
record по `official_record_id` через `clo_official_api.json`. Tool/handler/helper
locations и provenance — в `clo_source_mappings.json`. Это ссылки на канонические
данные, не потеря сведений и не раздувание одинаковых текстов в каждом слое.

## Чего реестр НЕ утверждает

Каждая строка классифицирована, но semantic contract (effect/units/dialogs,
индексный namespace/options/readback) остаётся **not_checked** до review данного
пакета. Лексический domain/owner — только planning bucket, не semantic evidence.
Даже `Get*`/`*Stream` не означает безопасный read. Все официальные per-overload
implementation пока planned, verification not_tested; это намеренно не выводится
из количества refs. Исходные принятые10 pattern native operations и14 tools
не потеряны. Текущий инвентарь дополнен read-only inventories с частичным real
evidence и открытым fabric mismatch: actual scope/evidence живёт в
`current_operation_scope.json`, `../CLO_INVENTORY_CHECK.md` и source mappings,
не объявляется полным покрытием официальных перегрузок.

Наличие docstring поднимает только symbol-level runtime presence/callability;
типы и конкретная overload semantics остаются отдельным gate. Type reference
resolved в official manifest означает documentation link, не Python binding.
Unresolved tokens/необычные annotations сохранены для review, не угадываются.

## Nonofficial / removed / factory references

- `export_api.ExportTechpackOption`: May be removed method, type/factory or runtime-only name. Not silently excluded or declared a callable method.
- `export_api.ImportExportOption`: May be removed method, type/factory or runtime-only name. Not silently excluded or declared a callable method.
- `export_api.NewImportExportOption`: May be removed method, type/factory or runtime-only name. Not silently excluded or declared a callable method.
- `utility_api.GetNestingBufferSpacing`: May be removed method, type/factory or runtime-only name. Not silently excluded or declared a callable method.

Их не теряем и не считаем автоматически доступными методами. Removed nesting
getter отдельно связан с review gate; factory references требуют type review.

## Приёмка и дальнейшие пакеты

`review_gates.json` задаёт явные условия разблокирования, а
`../CLO_ACCEPTANCE_PACKAGES.md` — B00–B13 с bounded критериями. Общий порядок:
`../CLO_COMPREHENSIVE_CHECK.md`. REST/GUI/global/lifecycle не включаются в
автоматический run. Полный manifest — подготовка denominator, не обещание
проверить весь API за один запуск или реализовать его generic dispatcher.

Источники/точные counts/anomalies: `CLO_OFFICIAL_API.md` и `CLO_SOURCE_MAPPINGS.md`.
Реальные новые CLO calls при генерации реестра не выполняются.
