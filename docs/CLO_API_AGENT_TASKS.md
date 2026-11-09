# Задания сабагентам: полное покрытие CLO API

Дата: 2026-11-09. Связанный план: `docs/CLO_API_COVERAGE_PLAN.md`.
**A0 и подготовка приёмки разрешены пользователем 2026-11-09.** Остальные
implementation briefs не включают новые домены автоматически; реальные CLO
испытания — совместно после перезапуска пользователем. Исторические задания
ниже задают scope пакетов, а не разрешение выполнить весь native API.

## Общая инструкция для каждого будущего задания

Прочитать `AGENTS.md`, план покрытия и профильный skill. Работать только в
назначенных файлах; чужие изменения не перезаписывать. Никаких commits/push,
обновлений зависимостей, смены транспорта, C++, UI automation, arbitrary exec,
импорта legacy listener или реальных CLO mutations без отдельного задания.
Стандарт Python внутри CLO — stdlib-only, native modules передаются извне,
вызов adapter только из принятого UI executor. Не менять callback/thread модель.

Перед кодом по каждой операции заполнить запись реестра:
official URL/version/signature + runtime signature + donor mapping + эффект +
units/options + target guards + readback + ограничения. Если факты расходятся,
вернуть blocker, не реализовывать предположение. Перегрузки/enum значения из
docstrings `arg0` не угадывать. Заимствованный существенный код требует MIT
attribution и сохранения notices. Донор — не доказательство native correctness.

Все будущие mutations: preflight до setter, без retries/fallback signatures,
без автоматического rollback. После setter любое исключение может быть
post-effect; не возвращать ложный успех. Readback не всегда транзакция.
Результаты bounded, exact schema, фиксированные public errors без native
tracebacks/секретов/приватных путей. Статусы implementation/local/real раздельны.

Отчёт агента: изменённые файлы, source mapping, команды тестов и фактический
результат, ограничения, integration request, следующий real-CLO gate. Если
код не проверен в CLO — прямо указать pending. Исторические 306 passed не
использовать как результат своего запуска.

## Владение и зависимости

Для всех tools загрузить `clo-mcp-tool-design`; для multi-tool сценариев и
будущих доменных skills — `clo-tool-workflows`. Стандарт:
`docs/CLO_MCP_TOOL_AUTHORING.md`, текущий каталог `docs/CLO_MCP_TOOLS.md`,
рецепты `docs/CLO_MCP_WORKFLOWS.md`. Каждый implementation brief включает
tool-card, точное server-visible описание/field semantics, valid/invalid/
composition examples, fake tool-selection evaluation и workflow stop tests.
Workflow/skill не объявляет будущие tools включёнными и не заменяет validators.

Роли независимы, но это не требование запускать всех агентов одновременно.
Имена файлов ниже — предлагаемые, существующие пользовательские файлы не
заменять. В разных волнах может работать один и тот же агент.

- A0 — реестр official/runtime/donor, до контракта всех доменов.
- A1 — общий integration contract, после A0 initial slice, до parallel coding.
- A2/A3/A4 — независимые fabrics / avatar / scene-colorways.
- A5 — batch framework; fake tests возможны параллельно A2–A4 после A1.
- A6 — поздние домены, каждый в отдельном задании по шаблону ниже.
- A7 — независимый review после интеграции; не владеет production edits.
- Координатор — принимает интерфейсы, интегрирует последовательно, ведёт реестр
  и единолично выполняет согласованные реальные проверки.

Один owner общих файлов: `protocol.py`, `jobs.py`, `pipe_session.py`,
`pipe_runtime.py`, `transport_server.py`, `plugin/clo3d_mcp_start.py`, общие
runtime/HTTP/Windows tests. Доменные агенты их не редактируют; возвращают
точный integration request. Исходные паттерны и legacy tests сохраняются.

## A0. Полный каталог и API specification

Подготовлен offline результат: `docs/api/CLO_API_CATALOG.md`, official/source
snapshots и общий coverage index. Semantic contract review и новый runtime
binding gate остаются открытыми; структурный реестр сам по себе не включает
tools. `scripts/build_api_coverage.py --check` воспроизводит join без сети.

**Цель:** проверяемый denominator полного покрытия, не ещё один список tools.

**Owner files:** будущие `docs/api/clo_api_coverage.json`,
`docs/api/CLO_API_CATALOG.md`, `tests/test_api_coverage_catalog.py`; при
необходимости отдельный offline report helper после согласования. Не менять
текущие runtime introspection limits без A1.

**Работа:**

1. Установить официальные index/Python/API pages, версию, дату, ссылки на
   changelog. Сохранить только нужную структурную спецификацию, не полный SDK.
2. Перечислить все разделы/модули/методы, значимые overloads, типы, enum/options.
   Отдельно отметить документацию C++ и реальную доступность Python.
3. Сопоставить установленную CLO 2026.1. Сейчас read-only проверены лишь пять
   модулей и 43 описания методов: `docs/CLO_API_RUNTIME_EVIDENCE.md`.
   Расширение discovery на новые modules/types — отдельный согласованный
   bounded probe; не делать wildcard imports или native calls по каталогу.
4. Сопоставить pinned extended revision
   `df150d95db604e4651bbbdfb151b8204209a7d12` и local47 baseline.
   Учесть methods, которых нет ни в одном доноре.
5. Составить gaps, explicit aliases и blockers с доказательствами и условием
   разблокирования. Принятый simple-polygon create не считать всеми кривыми.
6. Согласовать first-wave rows: список команд, перегрузки и тестовые критерии.

**DoD:** валидный schema, уникальные IDs, все обнаруженные entries имеют статус;
все links/version provenance; aliases не удваивают coverage; тесты ловят
unknown owner/status/missing evidence. Документированные и runtime-only entries
не теряются. Не найденные сигнатуры помечены not_checked, не invented.

## A1. Контракты интеграции и composition

**Owner:** один integration owner, общие файлы выше; новые
`command_catalog.py` / `command_contract.py` — только при реальной необходимости.

**Зависимости:** A0 first slice, схема params/results A2–A4 согласована.

**Работа:**

- Зафиксировать общий `CommandError`, error vocabulary, params/result validation
  и HTTP registrar интерфейс. Не создавать отдельные несовместимые exceptions.
- Статический command ownership/capability profiles, без plugin loader.
  Disabled command отвергается до enqueue, не только внутри CLO.
- `protocol.py`: согласованные profiles, JOB params и wire errors; framing,
  version/security не менять ради добавления домена без причины.
- `jobs.py`: params до ID allocation; validate_result до cache success;
  убрать неоднозначный fallback новых доменов в diagnostic rectangle branch.
- `pipe_session.py`: явная композиция handler/contract и negotiated whitelist;
  сохранить high-water dedup до native call, включая errors/reconnect.
- `pipe_runtime.py`: согласованный профиль/env и dispatcher, без batch loop
  в UI callback; один executing job и текущая lifecycle/thread модель.
- `transport_server.py`: raw validation до SDK coercion, explicit tool
  registration, аннотации эффектов, service readiness/error mapping.
- Launcher: собрать adapters из native modules, не импортировать legacy.
  Сохранить early ALREADY_STARTED guard до повторной загрузки adapters.
- Session guard: решить server-side expected-session проверку до enqueue для
  batch run. Клиентская status-проверка не атомарна; не обещать абсолютную
  защиту при переподключении. Не выдавать run_id за session token.
- Если нужны job IDs в отчёте, спроектировать интерфейс отдельно: сейчас
  successful HTTP result не содержит надёжного correlation ID для recovery.

**DoD:** focused HTTP/executor/runtime tests + actual Windows roundtrip нового
профиля с fake native API + full suite; выключенные/unnegotiated команды
невозможны; нет replay, invalid cache success или weakened Host/Origin.
Существующие диагностические профили/принятый pattern package не сломаны.
Реальный CLO gate остаётся pending.

## A2. Fabrics/materials

**Owner files:** `fabric_contract.py`, `fabric_api.py`, `fabric_tools.py` в
`src/clo3d_mcp/`; `tests/test_fabric_contract.py`, `test_fabric_api.py`,
`test_fabric_tools.py`; `docs/FABRIC_API_CHECK.md`.

**Первый срез:** fabric count/list/name/info, assignment read,
`assign_fabric_to_pattern`, base color read/set; add/replace/delete только
с доказуемой идентификацией и выбранным asset. Остальной PBR/textures/physical
API остаётся в реестре для следующего среза, не теряется.

**Кандидатные команды и guards:**

- `get_fabric_count`, `get_fabric_list`, `get_fabric_info(fabric_index)`;
- `get_fabric_for_pattern(pattern_index)`;
- `assign_fabric_to_pattern(pattern_index, expected_pattern_name,
  fabric_index, expected_fabric_name, ...explicit scope/option...)`;
- `get_fabric_color`, `set_fabric_color` — точные face/colorway и диапазон;
- один canonical `add_fabric` вместо add/import дубля;
- replace/delete — stale target guard, текущий colorway/assignment invariants.

Не назначать limits/options по догадке; их фиксирует A0/A1. Из реального
docstring уже известен RGBA getter и bool/int overload count. Не использовать
`bool(native_result)` как единственное подтверждение эффекта.

Count alone не идентифицирует материал; replacement с тем же именем/count
требует большего readback или честного completed-unverified. Assignment
проверяет pattern identity и getter назначения; color — значения с допуском
в правильном face/colorway. Паттерны создаёт явный acceptance scenario, не
adapter. Add/replace принимают только явно выбранный локальный формат, реально
поддержанный CLO; не разрешать `.jfab` или другие расширения без подтверждения.

**DoD:** schema + stateful fault tests (stale/duplicate names, scope change,
no-op, wrong return/index, post-effect exception, broken readback, unrelated
changes). Missing getter блокирует mutation до эффекта. Нет assets в fixtures.
Инструкция: reads → одна assignment/color mutation → independent readback;
import/delete в отдельном сценарии. Real acceptance pending.

## A3. Avatar/pose/measurements

**Owner files:** `avatar_contract.py`, `avatar_api.py`, `avatar_tools.py`;
`tests/test_avatar_contract.py`, `test_avatar_api.py`, `test_avatar_tools.py`;
`docs/AVATAR_API_CHECK.md`. Общее batch script принадлежит A5.

**Первый срез:** bounded `get_avatars`, per-avatar visibility read/set,
properties read; import с выбранным локальным asset. Далее properties setters,
pose, measurements, activation/soft-body/textures и delete по реестру.

- `get_avatars()` использует согласованные count/name/gender lists. Ошибку
  длины не маскировать пустым списком. `get_avatar_genders` — проекция, не
  независимая дублирующая реализация.
- `set_avatar_visibility(avatar_index, expected_name, show)` — индивидуальный
  scope с `IsShowAvatar(index)` и `SetShowHideAvatar(show,index)`; runtime
  signatures уже подтверждены. All-avatar setter — отдельный explicit scope,
  не молчаливая замена индивидуального.
- `import_avatar(file_path, apf_path=...)`: `.avt → ImportFile`,
  `.avac → ImportAVAC`; подтвердить docs и format semantics. APF для `.avt`
  не игнорировать: отказ или отдельно определённый pose route. Нет пробного
  ImportAVAC с последующим ImportFile после отказа/exception.
- `GetAvatarMeasurements` возвращает bound records; проверить доступность
  полей/типов и units, не stringify opaque object.
- Property dictionaries — allowlist документированных ключей/типов, не
  произвольное изменение неизвестных native свойств.
- Delete требует защищённой идентификации всех targets, сдвигов индексов и
  явного destructive scope. `DeleteAvatar` принимает list[int], не int.

Count/name не доказывают геометрию/позу. Import add/replace семантика для
каждого формата должна быть установлена до claim verified. Если нет достаточного
readback, сообщать уровень доказательства, визуальную проверку и blocker.

**DoD:** params/results и fault tests, format/APF/scope guards, mismatch/native
record serialization/ignored setter/post-change error. Реальная проверка только
с выбранным пользователем asset, независимым readback и UI-подтверждением.

## A4. Scene metadata/colorways

**Owner files:** `scene_contract.py`, `scene_api.py`, `scene_tools.py`;
`colorway_contract.py`, `colorway_api.py`, `colorway_tools.py`;
соответствующие `tests/test_*_contract.py`, `test_*_api.py`, `test_*_tools.py`;
`docs/SCENE_COLORWAY_API_CHECK.md`.

**Первый срез scene:** `get_project_info`, `get_garment_info`. Первый не равен
bridge `get_session_info`. Bounded JSON stream без silent raw-text fallback;
privacy policy для project path. Никаких NewProject/open/save в первом smoke.

**Colorways:** get list/current/name; set current, rename, copy, delete.
Index+expected_name и uniqueness guards; контроль active colorway перед
fabric mutation. Copy option enum meanings сверить в official docs, не
полагаться на legacy comments. Delete последнего варианта по умолчанию запретить
до установленного контракта. Copy+rename — multi-effect, не transaction.

Readback switch — current-index; rename — names/count/order; copy — native
returned index/count+1/остальной список/new name; delete — точный остаток и
valid current index. Linking материалов проверяется cross-domain сценарием,
список имён его не подтверждает.

**DoD:** stale/duplicate/mismatched snapshots, enum/last-item policy, no-op,
invalid returned index, post-effect failure. Smoke только собственной уникально
именованной копии: copy → rename/switch → reads → explicit planned delete.
После failure нет восстановления current colorway/cleanup автоматически.

Project new/open/save остаются отдельным W5 заданием с file/artifact contracts;
`open_file`/`import_file` объединяются по реальной семантике формата, не по имени.

## A5. Единый bounded клиент приёмки

**Owner files:** `scripts/verify_domains.py`, `tests/test_verify_domains.py`,
`docs/DOMAIN_BATCH_CHECK.md`. Не менять принятый `verify_patterns.py` без причины.

**Зависимости:** A1 schema/session guard; A0 evidence; domain contracts;
для реального run — chosen assets/permissions. Framework можно тестировать fake
client до готовности adapters. Pytest не запускает реальные CLO проверки.

Режимы:

- `discover`: inventory/capabilities/docstrings/allowlisted getters, без imports;
- `dry-run`: проверить static plan/dependencies/лимиты, без native effects;
- `run`: explicit выбранный сценарий и разрешение mutations; exports только
  с дополнительным user output path. Никаких browse/download/recursive scan.

Static whitelist plans, не произвольный execution engine. Run ID и session
identity фиксируются до первого шага. Перед mutation повторно проверить session,
ready, quarantine/error, unexpected queue work и domain preconditions. Status
guard сам по себе не atomic; опираться на решение A1. Один outstanding mutation,
следующий не enqueue до успешного результата и обязательного readback.

На первом error/unknown/timeout/disconnect/schema mismatch/failed readback/
session change/dialog/manual stop — закончить mutation run. Никаких gather,
retries, reconnect-and-resume, speculative enqueue или cleanup в finally.
Context manager может закрыть HTTP ресурсы, но не менять сцену. Плановая уборка
собственных объектов — обычные explicit успешные шаги с identity guards.

Лимиты: шаги/mutations/objects/response size/per-step/общая длительность;
stdout report без private paths/secrets; отдельные states verified, completed,
unsupported, blocked, failed, unknown. Completed без readback не закрывает
зависимый опасный gate. Нет asset — BLOCKED; не PASS/скрытый skip.

Simulate timeout не означает stop; не отправлять auto Stop/cleanup после него.
Exports: выбранная пользователем подпапка проекта `acceptance-output/`,
gitignored и вне input Assets; no overwrite по умолчанию,
no deleting partial outputs. Client Ctrl+C прекращает отправку/ожидание, не
обещает native cancellation. Bridge stop — отдельный пользовательский script.

**DoD tests:** injected failure на каждом шаге → ноль последующих mutations;
discover/dry-run ноль effects; changed session; queued work; post-dispatch
timeout; invalid schema; missing assets; completed != verified; bounded report;
принятый pattern load не запускается. Использовать fake clocks/events.

Инструкция real gate: свежий CLO/launcher, выбранная сцена/ассеты, expected
results, duration bounds (client != native), Ctrl+C, stop script, failure
criteria, последующая отдельная read-only сверка после unknown без resume.

## A6. Шаблон задания для остальных доменов полного API

Применять отдельно к W2 geometry/properties, W3 sewing/topstitch/trims/graphics,
W4 arrangement/mesh/simulation/wind, W5 I/O, W6 grading/nesting/UV,
W7 animation/render/display/metadata/library и найденным W0 группам.

1. Выписать точный набор реестровых IDs/overloads; определить missing rows.
2. Зафиксировать domain owner files `<domain>_contract.py`, `<domain>_api.py`,
   `<domain>_tools.py`, tests и `docs/<DOMAIN>_API_CHECK.md`.
3. Описать effects/units/limits/options/asset prerequisites и native behavior.
4. Сперва getters/topology/type conversion, затем mutation со stale guards и
   независимым критерием. Для long-running — duration/cancellation limits.
5. Передать integration request A1; общие файлы не редактировать.
6. Focused tests, результат, pending blockers; затем integration owner запускает
   shared regression и full suite. Никаких real calls агентом самостоятельно.
7. Включить bounded acceptance plan A5: fixture, effect, getter/artifact/visual
   evidence, stop/fail criteria. Blocked методы не объявлять покрытыми.

Специальные gates:

- Geometry: контуры/curves/internal lines/types/топология и unaffected pieces.
- Sewing: направления/пары/partial ranges; count не равен правильному шву.
- Simulation: bool return != физически корректная драпировка; GetClothPositions
  Python output-list binding не считать рабочим до проверки.
- I/O: option record bindings, strict keys/overwrites/output manifests/dialogs;
  ImportPatternJSON replacement — explicit, не append.
- Grading/nesting/UV: отдельные fixtures, units/quality/invariants, не count-only.
- Cloud/plugins/scripts/widgets/lifecycle: явное согласование external/global
  effects. Полная инвентаризация не разрешает arbitrary execution или auth calls.

## A7. Независимый review и завершение волны

**Режим:** read-only review, без исправлений чужих файлов и без real CLO calls.
Проверить traceability official overload → contract → adapter → tool → whitelist
→ result validator → tests → acceptance evidence. Поиск false verified, silent
coercion, retries, signature fallbacks после native effect, cleanup в finally,
opaque native serialization, escapes profile, scene/files/network side effects.

Integration owner после замечаний выполняет focused → HTTP/runtime → actual
Windows pipe/process → full suite и diff audit. `test_no_assets.py` проверяет
tracked files: untracked документацию/fixtures также проверить до staging.
Runtime no-IPC-files audit и repository no-assets audit — разные доказательства.
Export tests не ослабляют глобальный запрет IPC-записей.

**Перед совместной CLO приёмкой передать пользователю:** точный список enabled
tools/сценариев, локальные test results, known blockers, выбранные assets,
порядок fresh CLO/start, ожидаемые эффекты и stop/failure criteria. Никаких
скрытых real runs. После приёмки — обновление каждой строки реестра, не общей
надписью «все API работают».
