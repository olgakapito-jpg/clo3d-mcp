# Официальный API и extended: planning audit 2026-11-09

Статус: первичный read-only обзор, позднее дополненный A0. Не native acceptance.
Полная структурная спецификация и mapping теперь в `api/CLO_API_CATALOG.md`,
`api/CLO_OFFICIAL_API.md`, `api/CLO_SOURCE_MAPPINGS.md`. Сторонний код не запускался
и не копировался в production. Позднее пользователь сообщил точный target
установленной CLO: **2026.1.336**; runtime metadata новых bindings ещё не проверены.

## 1. Актуальная официальная база

- [Download](https://developer.clo3d.com/download.html): Latest SDK **11.0.1**,
  **CLO 2026.1.336 Official Release**.
- [Changelog](https://developer.clo3d.com/changelog.html): V11.0.1 October 2026,
  отдельное Documentation update October 2026. Предыдущая ветка 11.0.0 связана
  с 2026.1.224; «2026.1» без patch недостаточно для проверки соответствия.
- [API List](https://developer.clo3d.com/list.html),
  [исходник RST](https://developer.clo3d.com/_sources/list.rst.txt).
- [Option & Type](https://developer.clo3d.com/optiontype.html),
  [исходник](https://developer.clo3d.com/_sources/optiontype.rst.txt).
- [Python](https://developer.clo3d.com/python.html),
  [сценарии/options](https://developer.clo3d.com/scenario.html).
- [GUI reference](https://developer.clo3d.com/gui_api_reference.html),
  [GUI overview](https://developer.clo3d.com/gui_api.html).
- [Library](https://developer.clo3d.com/library.html),
  [Event Plugin](https://developer.clo3d.com/eventplugin.html): учесть как
  дополнительные interfaces, НЕ считать автоматически Python bindings.

Надпись сайта «CLO API 0.1» и footer ©2009–2025 не являются SDK version.
SDK zip не скачивался и не требуется для самого плана.

### Первичный подсчёт документационных записей

Read-only агент извлёк Python code blocks HTML `list.html` отдельно от C++:

```text
module        unique names   Python declaration blocks
export_api              91                         123
fabric_api             134                         284
import_api              38                          44
pattern_api            217                         233
rest_api                 7                           8
utility_api            364                         406
TOTAL                  851                        1098

gui_api: 39 unique names на отдельной reference page
optiontype: 77 top-level sections
```

Это начальная оценка universe, не окончательный нормализованный denominator.
Declaration blocks включают overloads/повторы (например, ImportAVAC), `W`
считаются отдельными именами. 77 секций не означают 77 constructible Python
классов. Повторяемое извлечение с content hashes и проверяемым результатом —
deliverable A0; parser/полный manifest в этой planning-фазе ещё не созданы.

REST names: CallRESTGet, CallRESTPost, CallRESTPost2,
CallRESTPostWithMultipartFormData, CallbackRestRequest,
CallbackRestMultiRequest, CallRESTPut. Сеть/credentials/SSRF и callbacks требуют
отдельных контрактов. `gui_api` — официальный Python API, не UI automation,
но создание окон/modal/callbacks не разрешает менять принятый executor молча.
ApiTypes/options/enums — обязательные зависимости полного покрытия.

## 2. Донор и границы проведённой проверки

Ревизия: [`df150d95db604e4651bbbdfb151b8204209a7d12`](https://github.com/adriendelmas/clo3d-mcp-extended/commit/df150d95db604e4651bbbdfb151b8204209a7d12),
2026-10-08 23:20:37 UTC; HEAD не проверялся. Источники:

- [plugin handlers](https://github.com/adriendelmas/clo3d-mcp-extended/blob/df150d95db604e4651bbbdfb151b8204209a7d12/plugin/clo3d_mcp_plugin.py)
- [server/extended modules](https://github.com/adriendelmas/clo3d-mcp-extended/tree/df150d95db604e4651bbbdfb151b8204209a7d12/src/clo3d_mcp)
- [tools catalogue](https://github.com/adriendelmas/clo3d-mcp-extended/blob/df150d95db604e4651bbbdfb151b8204209a7d12/docs/TOOLS.md)
- [README](https://github.com/adriendelmas/clo3d-mcp-extended/blob/df150d95db604e4651bbbdfb151b8204209a7d12/README.md)
- [LICENSE](https://github.com/adriendelmas/clo3d-mcp-extended/blob/df150d95db604e4651bbbdfb151b8204209a7d12/LICENSE),
  [NOTICE](https://github.com/adriendelmas/clo3d-mcp-extended/blob/df150d95db604e4651bbbdfb151b8204209a7d12/NOTICE)

Статический аудит: 170 MCP tools, 172 handler registry commands (дополнительно
ping/stop); 33 tools в server и 137 в extended modules. С local47 совпадают 44
имени, 126 новых; local import_dxf/ping/list_extensions среди tools донора нет.
Заявленная среда донора CLO 2025.2.236/Windows11 не доказывает CLO 2026.1.

Извлечено 336 qualified native references; 332 имени найдены в соответствующих
Python-секциях docs. Оставшиеся: удалённый utility_api.GetNestingBufferSpacing
и три type/factory references в export_api (NewImportExportOption,
ImportExportOption, ExportTechpackOption). Отсутствие последних в списке
функций не доказывает отсутствие типа — проверить ApiTypes/runtime.
Совпадение имён НЕ означает сверенные 332 контракта или принятые170 tools.

Основные donor-группы: geometry24; sewing14; simulation/arrangement/mesh15;
materials39; avatar/measurements/poses/grading16; files/library9;
visuals/colorways13; nesting4; documentation3. Это разбивка extended137,
а не всех170: оставшиеся33 — базовый server.

## 3. Обязательные поправки при переносе

### Возвраты и индексные пространства

- `AddSeamlinePairGroupPartial` возвращает int status: **0 success**, отрицательные
  коды ошибок. Нельзя bool(result); native return — не new seam ID. Сверить enum
  `SeamlinePairGroupResult`, получать новый group через diff/getters.
- `AddSeamlinePairGroup`: сигнатура bool, текст return описывает имя/wide string.
  Это противоречие docs, не повод stringify результат как успех.
- `CreateInternalShapeWithPoints` / `CreateBaseShapeWithPoints`: неоднозначный
  текст returned index, проверить identity child, не считать pattern index.
- `GetPatternOutlinePoints`: bbox top-left, Y вниз, мм; docs предупреждают
  real-pattern-list order против full pattern list с buttons/bindings для
  некоторых graphics API. Один namespace индексов нельзя применять повсюду.
- `SetMaterialProperties` возвращает JSON status/message, не bool. Getters
  могут вернуть default при unresolved context. Avatar material support по
  changelog11.0.1 и notes метода описаны не полностью согласованно: pending.
- Одноимённый `AddGraphicStyleToPattern` в utility_api и pattern_api имеет
  разные параметры/позиционную семантику; ключ должен включать module.

### Диалоги и binding options

- `ExportDXF()` и `ExportDXF(path)` документированы с диалогом.
  **`ExportDXF(path, ExportDxfOption)` документирован без option dialog**:
  проверить Python constructibility и принять отдельно, не исключать весь DXF.
- `ImportFile` зависит от формата и может открывать диалоги. Сохранить .avt
  через ImportFile/.avac через ImportAVAC как известный маршрут, но не обещать
  no-dialog. `ImportAvatar(avtPath, ImportExportOption)` — отдельный кандидат
  no-size/pose-dialog из latest docs, требует проверки типа и runtime.
- `ExportTechPackToStream` связан с associated image files и output folder;
  слово Stream не делает его автоматически read-only. Аналогично каждый
  Export*ToStream проверяется по описанию побочных файлов, а не по имени.

### Удалённые/исправленные API и ограничения донора

- `GetNestingBufferSpacing` удалён в11.0.0; latest использует отдельные
  Get/SetNestingFabricBufferSpacing и Get/SetNestingPatternBufferSpacing.
  Python tab содержит `std::array` — caster ещё нужно проверить.
- `MovePatternPoint`: у донора report повреждения; changelog9.1.1 говорит fix.
  Это отдельный safety gate на точном build, не вечное исключение и не PASS.
- `ImportPatternJSON`: donor сообщает replacement; official description
  недостаточно определяет это. Отдельный destructive case, не обещать append.
- Старое ограничение донора «нельзя двигать/удалять graphics» не переносить:
  latest содержит новые placement/reposition/lock/removal операции.
- `duplicate_fabric` донора экспортирует временный zfab и снова AddFabric:
  это файловый эффект, не чистая сценовая mutation; нужны paths/overwrite policy.
- `find_assets` обходит root через os.walk внутри CLO: не переносить произвольный
  recursive scan в callback. Discovery ассетов отдельно ограничить/согласовать.
- `find_api_types` донора обходит все загруженные modules: заменить будущим
  allowlist типов CLO, не раскрывать произвольный sys.modules.
- `_safe`/optimistic True/composite setters не являются error contracts.
  Field error не становится успешной строкой. Частичное применение не скрывать.

## 4. Дополнительные latest-домены сверх donor tools

Полный каталог должен включить structured geometry, cut/merge/trace, partial
sewing/connectivity/components, UV/UDIM/baking, generic material contexts,
avatar measure edge attachments, grading authoring/offsets, button pairs,
render/ZCMR/USD/Alembic/video, animation/wind, library/color-swatches/modular,
metadata/object browser/archive/validation, map generation/XTEX/Substance/AOP,
Hi-res tolerances, REST/GUI и обнаруженные SDK-only interfaces.

Все строки через схему A0: official → runtime/types → donor/legacy → current
HTTP → contracts/tests → real evidence. Library/Event/C++-only не вычёркивать,
но не превращать автоматически в Python tools. Blocked != implemented.

При последующей подготовке A0 сохранены воспроизводимые проверяемые data files:
`api/clo_official_api.json`, `api/clo_source_mappings.json` и общий
`api/clo_api_coverage.json` (sharded). Итог:890 qualified Python names,1134
unique declarations из1137 documentation blocks,77types и6interfaces; donor170,
legacy47,current14. Отличие от первичных1098blocks: добавленGUI и устранены
три повтора объявлений, occurrences сохранены. Semantic effect/units/options
review и runtime/real acceptance не объявляются завершёнными этим извлечением.
