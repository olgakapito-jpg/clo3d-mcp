# Пакеты доменной приёмки W0–W8

Дата подготовки: 2026-11-09. **Только CLO2026.1.336 / SDK11.0.1**; другая
сборка — BLOCKED до пересмотра контрактов. Это предложенные критерии и fixtures,
не журнал PASS и не разрешение исполнять native API. Сейчас real CLO calls,
restart/stop и загрузка ассетов **не выполняются**. Пользователь вернётся и сам
перезапустит CLO/MCP после законченной локальной подготовки.

Источники: [roadmap](CLO_API_COVERAGE_PLAN.md), [briefs A0–A7](CLO_API_AGENT_TASKS.md),
[current14](CLO_MCP_TOOLS.md), [правила tool contracts](CLO_MCP_TOOL_AUTHORING.md).
Здесь W0–W8 — **волны roadmap**. Рецепты W1–W5 в
[CLO_MCP_WORKFLOWS.md](CLO_MCP_WORKFLOWS.md) имеют отдельную нумерацию и не
обозначают реализацию соответствующих доменных волн.

## 1. Что уже доступно, что заблокировано

Текущий принятый pattern profile публикует **14 tools**:

```text
get_session_info       transport_status          ping
get_pattern_count      create_test_rectangle     list_clo_api
describe_clo_api       get_pattern_list          get_pattern_geometry
create_pattern         set_pattern_name          copy_pattern_with_offset
move_pattern_relative  delete_pattern
```

Первые два — внешние snapshots, не ответ native CLO; introspection не исполняет
описанные методы. В этом наборе **нет** fabric/avatar/pose/project I/O/colorway/
topology/sewing/simulation/export/grading/nesting/UV/render/REST/GUI tools.
Legacy handlers и наличие callable не делают их доступными. Все будущие
доменные пакеты ниже **BLOCKED_IMPLEMENTATION**, пока явные tools, contracts,
capabilities и локальные tests не реализованы и не интегрированы. Имена будущих
capabilities ниже — требования, не команды для вызова.

Не повторять принятые P0–P3, pattern package, `load10` или `load1000` как gate.
Новая пара деталей для ткани/швов — новая целевая fixture, не повтор нагрузки.
P4 modal/forced-exit остаётся отдельным pending scope; не включать в этот прогон.
Принятый отказ от 30-минутного soak сохраняется.

## 2. Общие gates, статусы и короткие лимиты

### Единые package IDs B00–B13

Связь с `docs/api/review_gates.json` и
`docs/api/current_operation_scope.json` (ими владеет координатор):

- **B00** — offline/dry-run, подготовка assets и offline W0/W8 reconciliation.
- **B01** — runtime metadata/types probe, W0; только согласованный read-only scope.
- **B02** — scene read-only, W1a.
- **B03** — fabrics, W1b; import fabric — отдельный согласованный подпакет B03.
- **B04** — avatar reads/individual visibility/measurement, W1c.
- **B05** — avatar import, отдельно от B04; F-avatar + explicit import gate.
- **B06** — colorways, W1d.
- **B07** — topology/geometry, W2.
- **B08** — sewing/accessories, W3 (первый срез — sewing).
- **B09** — arrangement/short simulation, W4.
- **B10** — project/import/export, W5; avatar import остаётся B05.
- **B11** — grading/nesting/UV, W6.
- **B12** — display/render/animation, W7a–c.
- **B13** — external/global/GUI/lifecycle, W7d: отдельные permissions,
  не автоматический execution package.

`B00`/`B01` не означают реализацию будущих доменов. Подпакеты наследуют ID
и scope своей B-группы, но имеют отдельные initial state/permission/evidence;
совпадение ID не разрешает запуск всех mutations группы сразу. Общие G0–G3
ниже — readiness/evidence gates, **не** альтернативные package IDs.

**G0 / offline readiness:** A0 entries с official/runtime provenance, exact
overload/types/units и исходом binding review; tool cards, raw validators,
fault/selection/composition tests; доступность нужных getters. Документированный
851-name universe не равно 851 проверенным bindings и не равно 851 MCP tools.

**G1 / user preflight после возвращения:** пользователь подтверждает сборку,
свежий CLO + launcher, разрешённую disposable сцену и отсутствие ручного editing
во время пакета; выбранные assets, эффект add/replace, output policy и scope.
Проверить реальные tools/list + session info/capabilities/ready/queue, сохранить
identity без токенов/приватных путей. Нет server-side session guard в current14:
повторный status check не атомарен и не гарантирует защиту от смены сцены.

**G2 / один пакет:** свежие targets → preflight → ровно одна mutation → проверка
result/schema → независимый readback → ручное визуальное подтверждение, если
оно требуется → следующий шаг. Не enqueue dependent changes заранее; не gather.
Каждый подпакет согласуется отдельно, не «полный API одной giant mutation».

**G3 / evidence:** отдельно записать implementation/local/real evidence,
наблюдаемые invariants, visual verdict пользователя, remaining uncertainty.
Коды в этом документе — **статусы отчёта**, не новые поля ответов MCP:

- `VERIFIED`: совпали конкретные заявленные invariants и обязательный visual gate;
  не утверждение качества всей одежды или покрытия домена.
- `COMPLETED_UNVERIFIED`: native call завершился, эффекта/качества недостаточно
  для доказательства. Не открывает зависимый опасный gate.
- `BLOCKED_IMPLEMENTATION`, `BLOCKED_ASSET`, `BLOCKED_BINDING`,
  `BLOCKED_PERMISSION`: prerequisites не выполнены; это не PASS и не hidden skip.
- `FAILED`: установлен mismatch/error; `UNKNOWN`: dispatched outcome неизвестен.

**Предложенный стандарт малого пакета:** ≤16 scene tool calls, ≤3 mutations,
≤2 новых деталей, ≤1 импортируемого asset, ≤2 изменяемых targets; client budget
90с на пакет, 30с на шаг, metadata response/report ≤180000 bytes. External
snapshots/readback входят в бюджет вызовов; если тесно — разбить, не убрать
readback. Это бюджеты будущего клиента, не существующие параметры tools и не
native cancellation. Для текущего describe: ≤16 symbols/call, ≤8192 doc chars;
для pattern list ≤256; create — 3–64 вершины, straight simple polygon, без curves.
Точные действующие bounds/units: current14. Не подменять их proposal budgets.

**Общий STOP:** первый error/isError/schema mismatch, stale/duplicate target,
readback mismatch, changed session, unexpected queue work, dialog, busy/quarantine,
потеря отзывчивости UI, client timeout/disconnect/ручная остановка. Не отправлять
следующие mutations, retry/fallback overload/rollback/cleanup; не закрывать диалог
автоматически. Client Ctrl+C останавливает отправку/ожидание, **не native API**.
После неизвестного исхода отдельная bounded read-only сверка при доступном
executor, без auto-resume. Getter/ping ждут ту же FIFO, не прерывают занятый CLO.

**Stop method для будущего запуска:** прекратить отправку, Ctrl+C внешнего
клиента; пользователь при необходимости отдельно запускает
`plugin/clo3d_mcp_stop.py`. Bridge stop не обещает прервать выполняющийся native
вызов. При зависшем native вызове — сообщить uncertainty, не kill по имени/порту.
Теперь ничего из этого не запускать. Offline helper ниже не связан с MCP/CLO.

Отрицательные случаи по умолчанию — **fake/unit**, не destructive live fault
injection. В реальном CLO invalid/no-call cases допустимы только после доказанной
валидации до enqueue; client timeout, modal UI, process death и сетевые ошибки
на живом приложении требуют отдельного permission/gate.

## 3. Fixture proposals и безопасная инвентаризация

Asset root задаётся пользователем явно; установленная библиотека CLO Assets
строго **read-only**. Не скачивать, не копировать и не открывать содержимое файлов
при подготовке. Не делать рекурсивный поиск по машине. Установка в папке с именем
«CLO Assets» сама по себе не доказывает official provenance, лицензию, содержимое
или совместимость. Это **unknown до user/content gate**. Проект может ссылаться
на внешние textures/assets или открывать диалоги: filename не выявляет это.

Предлагаемые маленькие пакеты, каждый утверждается по одному выбранному файлу:

- **F-fabric:** один `.zfab`, положительный размер ≤64MiB. Гипотеза: простой
  материал для назначения двум synthetic панелям. Без обещания physical/PBR
  полей, textures, face/colorway semantics. Содержимое и импорт BLOCKED_ASSET.
- **F-avatar:** один `.avt` или `.avac` ≤128MiB. Гипотеза: одиночный avatar для
  individual visibility/pose; не предполагать gender, scale, число объектов,
  геометрию или add/replace. Форматы/overloads сверяются A0, не fallback.
- **F-project:** один `.zprj` или `.zpac` ≤128MiB; возможная отдельная fixture
  для open/save. Имя «sample/simple» не доказывает малую сцену. Нет авто-открытия;
  пользователь подтверждает состав, dependencies и replace semantics до W5.
- **F-pose:** один `.pos` или `.apf` ≤16MiB. Это **поисковые format hints**, не
  утверждение существования реализованного import route. Нужны совместимый
  выбранный avatar, формат/units/поза и contract; пока BLOCKED_BINDING/ASSET.
- **F-panels:** до двух явно созданных simple straight polygons с уникальными
  run names и свежими readbacks; не disk asset, не готовая одежда. Создание
  собственных объектов — отдельный разрешённый fixture step в общем бюджете.
  Не импортировать неизвестный garment, чтобы «сэкономить» preconditions.
- **F-special:** grading/nesting/UV/render/animation сцены подбираются отдельно.
  Базовая fixture не считается подходящей для этих доменов автоматически.

### Внешний stdlib helper (без CLO)

Путь запуска: `scripts/prepare_acceptance_assets.py`; dependency installs не
нужны. Установить `$AssetRoot` в явный разрешённый root локально; не сохранять
машинный путь в git. Пример **не** обращается к CLO:

```powershell
python scripts/prepare_acceptance_assets.py --root "$AssetRoot" --max-entries 2000 --max-depth 4
```

Default: только summary со счётчиками; без root/filenames/absolute paths,
без файлов вывода. Для **явно выбранного существующего** `$ReportDir` разрешены
только gitignored project `acceptance-output/` либо его подпапки:

```powershell
python scripts/prepare_acceptance_assets.py --root "$AssetRoot" --output-dir "$ReportDir" --max-entries 2000 --max-depth 4 --candidates-per-kind 3
```

Ожидаемый stdout: `Metadata only`, bounded entries, format-hint/proposal counts,
`compatibility UNKNOWN`, явный факт report/no report. Stop: Ctrl+C; никаких CLO
effects. Failure: exit2/refused, metadata errors, cap/depth cut либо отсутствующий
кандидат означают incomplete/blocked, а не доказанное отсутствие всех assets.
Внешняя оболочка при автоматическом вызове задаёт timeout (например, 30с);
лимиты entries/depth не ограничивают задержку конкретного filesystem operation.

Контракт helper:

- `--root` обязателен; повтор до4, roots не пересекаются. Нет default machine path;
  разделители `/` и `\` нормализуются лексически **до любого lstat**; UNC/network
  и device prefixes (включая смешанные `\/` и `/\`, `//?/` и `//./` после
  нормализации) отклоняются до filesystem access (mapped network
  drives не определяются stdlib helper: пользователь задаёт только local roots).
- `--max-entries` 1–10000, default2000 **на все roots вместе**, включая directory
  entries; `--max-depth` 0–12, default4, файлы корня depth0. Не сортирует весь
  каталог до cap: bounded walk не гарантирует одинаковый observed subset.
- `--candidates-per-kind` 1–5, default3; отбор **среди наблюдавшихся** по extension,
  positive size budget, smallest size, filename tie-break; не content parsing.
  По умолчанию до12 предложений суммарно. Не читать bytes, headers, hashes,
  archives, thumbnails, timestamps, owner/ACL или linked targets.
- Skip symlink/junction/reparse points, включая roots/ancestors; metadata errors
  счётчиком, без native exceptions/paths. Не следовать special entries; filename
  metadata ≤512 chars, без непечатных символов. Scan не делает directory creation.
- Report — только `acceptance-assets.json` в явно выбранном существующем
  project `acceptance-output/` или его descendants. Произвольные `docs/`, `src/`,
  root проекта, похожие prefix-папки и пути вне проекта запрещены; input/output
  должны быть disjoint.
  Reject linked output/ancestors, `..`, pre-existing target; exclusive create,
  no overwrite даже symlink/hardlink target. Payload ≤180000 bytes.
- Report содержит root IDs, relative filenames, format hints и sizes, не machine
  absolute paths. **Relative filenames тоже private metadata**: reports untracked,
  не прикладывать без review. Нет committed asset inventories или copied assets.
- Path checks — не sandbox против враждебной concurrent directory replacement;
  roots/output не должны изменяться параллельно. На ошибке записи возможен
  partial report; не удалять/перезаписывать его автоматически, выбрать новую
  подпапку после осмотра пользователем.

## 4. Матрица W0–W8

Каждая карточка содержит initial state/assets/capability/sequence/criteria/
negative/limits/stop/gate. Общие лимиты и STOP выше обязательны для всех карточек.
Это проект acceptance, не запускаемый script plan. Native units/options задаёт
A0 contract, не этот документ.

### W0 — A0 каталог, типы, source traceability (B00/B01)

**Статус:** offline часть доступна; bounded current14 introspection существует,
но сейчас **не вызывается**. Полный runtime universe/types — BLOCKED_IMPLEMENTATION.

- **Initial/assets:** исходники official catalog/provenance + current14 cards;
  никакой сцены/asset для offline работы. Runtime — только после G1.
- **Required capability:** current `list_clo_api`/`describe_clo_api` лишь для
  пяти разрешённых modules. REST/GUI/ApiTypes отсутствуют в этом whitelist.
  Расширенное discovery требует отдельного allowlisted implementation/probe.
- **Sequence:** offline reconcile qualified symbol+overload → type/option gaps
  → snapshot current tools/capabilities после user gate → максимум одна
  selected describe порция → review official semantics, без вызова методов.
- **Invariants/visual:** каждому entry отдельные docs/runtime/implementation/
  local/real states; aliases не удваивают denominator; неизвестное явно unknown.
  Visual N/A для offline, UI responsiveness — только user наблюдение runtime.
- **Negative:** fake missing types, conflicting overload, absent/empty docs,
  truncated list; unknown module/17 symbols → no-call, не generic exec/import.
- **Limits/STOP/gate:** runtime ≤1 list +1 describe (≤16 symbols) за пакет,
  без mutations. Отсутствующая семантика → BLOCKED_BINDING. G0 закрывает только
  каталог/traceability, не подтверждает выполнение API; затем G1/G2 для доменов.

### W1 — scene, fabric, avatar, colorway (B02–B06)

**Статус всех новых domain tools: BLOCKED_IMPLEMENTATION.**

- **Initial/assets:** G1 scene snapshot, ≤2 own F-panels, известные active
  colorway/face и уникальные names; F-fabric/F-avatar только для отдельных import
  подпакетов. Scene reads не должны скрыто делать New/open/save.
- **Required capability:** bounded project/garment reads с privacy; fabric
  list/info/assignment/color reads + guarded assignment/color setter; individual
  avatar visibility read/set; colorway list/current/copy/name/switch/delete.
  Imports/replace/delete — свои explicit file/scope contracts, не implicit setup.
- **Sequence:** W1a scene getters только; W1b fabric baseline → одно assignment
  → readback → отдельно одна color mutation → readback; W1c avatar baseline →
  одна individual visibility mutation → readback + visual; measurement reads
  в отдельном B04 подпакете проверяют typed bound-record fields/units, без
  opaque string fallback. B05 — отдельный avatar import после format/content
  gate, без пробного fallback. W1d own colorway copy
  → readback, затем rename/switch в следующем коротком пакете. Planned delete
  собственных копий — отдельный успешный шаг, не finally.
- **Invariants/visual:** assignment правильной панели/ткани/face/colorway,
  untouched panel unchanged; color values в contract tolerance + user color
  observation; avatar count/identity неизменны, меняется только выбранная
  visibility; colorway count/order/current согласованы, linking материалов
  отдельно доказан. Пользователь подтверждает отсутствие unexpected scene loss.
- **Negative:** fake duplicate/stale names, changed active colorway, all-avatar
  вместо individual, no-op setter, post-effect exception, malformed records,
  invalid enum/last-colorway delete; missing asset → BLOCKED_ASSET до native.
- **Limits/STOP/gate:** ≤3 mutations/подпакет, ≤1 import только отдельным пакетом;
  отсутствие getter блокирует setter. Не считать count/name доказательством
  avatar/fabric import contents. G0 + explicit assets G1 → G2 по одному W1a–d;
  W1 real не означает принятия PBR/physical/measurements/pose.

### W2 — полная геометрия и свойства деталей (B07)

**Статус:** только simple polygon/list/area/position/bbox current14 доступны;
outline/components/curves/properties и topology mutations BLOCKED_IMPLEMENTATION.

- **Initial/assets:** ≤2 F-panels, свежие list/geometry, отдельная fixture
  с известным outline для будущих curves/internal lines. Не load10 повтор.
- **Required capability:** bounded outline/components/line namespace reads,
  guarded свойства + независимые getters; отдельно topology mutation contracts.
- **Sequence:** inspect topology → выбрать **одну** property → baseline → setter
  → independent property/topology read; create/internal shape/cut/unfold —
  отдельные пакеты после проверенного namespace, не inferred из bbox.
- **Invariants/visual:** units/координаты/порядок компонентов соответствуют
  контракту; count/order/area/position и unrelated properties не изменились
  кроме явно заявленного эффекта; пользователь видит ожидаемые edges/shape,
  отсутствие unexpected holes/self-intersections/перемещения.
- **Negative:** fake invalid component, stale topology, degenerate/curved inputs
  в straight polygon tool, oversize outlines, ignored setter/partial effect.
  `MovePatternPoint` остаётся отдельным BLOCKED_BINDING до воспроизведения/решения.
- **Limits/STOP/gate:** ≤1 topology mutation/пакет; ≤64 vertices только current
  create, будущие bounds не выдумывать. Любой topology mismatch STOP. G0/G1,
  topology reads accepted → guarded setter → destructive topology отдельный gate.

### W3 — sewing, topstitch, buttons/zippers/trims/graphics (B08)

**Статус:** BLOCKED_IMPLEMENTATION; первый пакет — только одна seam pair.

- **Initial/assets:** две согласованные F-panels, fresh verified edge/component
  namespace из W2; без simulation; accessories требуют отдельных chosen fixtures.
- **Required capability:** connectivity/seam reads, guarded exact-overload pair
  creation; отдельные contracts placement/materials для остальных поддоменов.
- **Sequence:** baseline edges/lengths/directions → один seam pair → independent
  connectivity read → visual; topstitch/accessory placement — каждый отдельный
  пакет, не автоматически вслед за seam count.
- **Invariants/visual:** правильные две линии, endpoints/direction/partial ranges,
  count delta и unchanged unrelated groups; geometry unchanged. Пользователь
  подтверждает seam orientation и отсутствие перекрученной/ошибочной связности.
  Seam count сам по себе не verification и не «одежда готова».
- **Negative:** fake cross-namespace/stale edge, invalid partial range, неверный
  overload, no-op return, duplicate connectivity, post-create exception.
- **Limits/STOP/gate:** ≤1 seam/accessory creation/пакет, ≤2 targets. Нет надёжного
  connectivity readback → COMPLETED_UNVERIFIED, зависимая sim заблокирована.
  G0/G1 + W2 topology evidence → G2 seam; остальные группы не покрыты seam smoke.

### W4 — arrangement, mesh и короткая simulation (B09)

**Статус:** BLOCKED_IMPLEMENTATION; simulation требует отдельного user gate.

- **Initial/assets:** user-approved garment/аватар с доказанной совместимостью,
  W1/W3 evidence, known placement и небольшая mesh; не произвольный F-project.
- **Required capability:** arrangement/mesh/settings getters; guarded setters;
  bounded simulation с честной native timeout/stop semantics и measurable readback.
- **Sequence:** read baseline → одна placement/settings mutation → readback +
  visual; **в другом пакете** одна короткая simulation → независимые mesh/position
  observations + user visual. Settings не устанавливать длинной пачкой заранее.
- **Invariants/visual:** стабильные object identities/topology/seam relations,
  finite geometry и ожидаемый mesh range; пользователь видит отсутствие explosion,
  сильного unintended penetration/исчезновения, проверяет UI responsiveness.
  Physically correct fit не выводится из `Simulate -> bool`.
- **Negative:** fake ignored setting, blocking native, post-dispatch timeout,
  broken output-list binding, NaN/oversized mesh; это не живой freeze injection.
- **Limits/STOP/gate:** ≤1 simulation/пакет; proposal native request ≤5с **только
  если** доказаны units/termination; client ≤30с не обеспечивает этого. Если
  нельзя установить bounded work/верификацию — BLOCKED_BINDING, не пробный запуск.
  G0/G1 + topology/sewing/placement readiness + explicit simulation permission.

### W5 — project I/O, import/export и артефакты (B10; avatar import — B05)

**Статус:** BLOCKED_IMPLEMENTATION; file write и scene replacement — явные gates.

- **Initial/assets:** выбранные F-project/F-fabric/F-avatar/F-pose с content
  confirmation по отдельности; выбранный пользователем новый output subdirectory
  repo (для этой подготовки `acceptance-output/`), вне inputs, untracked.
- **Required capability:** explicit format/options/add-or-replace tool contracts,
  no-dialog routes, guarded output allowlist/no-overwrite/artifact list. Не
  generic import/exec, не попытки разных overload после native error.
- **Sequence:** W5a один выбранный import/open → scene readback + visual; W5b
  один export → bounded filesystem artifact metadata check → пользователь
  подтверждает открываемость/изображение отдельно. Save/new/open — отдельные
  пакеты и destructive scopes, не fixture setup без уведомления.
- **Invariants/visual:** input untouched; output в разрешённой папке, ожидаемые
  имена/число/positive sizes, нет overwrite/unexpected companions; scene effect
  соответствует declared add/replace. Непустой файл не доказывает содержимое,
  export success не доказывает roundtrip compatibility. Visual required для
  snapshots/garment/pose и отдельного ручного artifact review.
- **Negative:** fake missing file, wrong extension/options, symlink/out-of-root,
  pre-existing target, permission denied, partial artifacts, dialog-only route.
- **Limits/STOP/gate:** ≤1 import **или** export/пакет; budget companions ≤16,
  суммарно ≤128MiB proposal, иначе blocker/пересмотр до запуска. На partial/error
  STOP, сохранить artifacts, no retry/delete. G0/G1 + explicit path/overwrite
  и replace permission; official/library content compatibility пока unknown.

### W6 — grading, nesting, UV (B11; не один общий smoke)

**Статус:** BLOCKED_IMPLEMENTATION + BLOCKED_ASSET до F-special.

- **Initial/assets:** отдельные user-approved grading rules/sizes, nesting sheet
  и UV topology fixtures; baseline units/quantities/grain/islands фиксированы.
- **Required capability:** bounded domain reads + validated rules/options setters,
  topology/quality readback; nesting start/stop только с установленными semantics.
- **Sequence:** один inspect пакет для каждого поддомена → одна rule/offset/UV
  transform → independent readback + visual; nesting run отдельно после bounds.
- **Invariants/visual:** grading expected dimensions/size membership; nesting
  quantities/rotation/grain/containment/no overlap; UV islands/seams/scale/packing
  согласованы. Пользователь подтверждает на выбранном layout, count недостаточен.
- **Negative:** fake invalid size/group, mm/cm mismatch, stale island namespace,
  disallowed grain rotation, failed nesting stop, partial transforms.
- **Limits/STOP/gate:** ≤2 sizes/детали либо ≤2 islands для первого setter smoke;
  nesting ≤5с requested только при доказанной native bounded semantics. Нет
  качественных критериев/getter → BLOCKED_BINDING. G0/G1 + special fixture approval.

### W7 — animation/render/display (B12) и рискованные service группы (B13)

**Статус:** BLOCKED_IMPLEMENTATION. Ниже четыре независимых permission scopes.

- **Initial/assets:** animation/render требуют F-special, known camera/lighting,
  frame range, output directory; display baseline scene/global distinction.
  REST/auth/service группы не наследуют permission от disposable scene.
- **Required capability:** explicit bounded local display/frame/render tools с
  readback/artifact policy; REST/GUI/lifecycle/global/auth/network — отдельные
  reviewed contracts. Текущий introspection их даже не перечисляет полностью.
- **Sequence:** W7a local scene display getter/setter/readback; W7b один frame
  preview; W7c один tiny render/artifact+visual только после согласования;
  W7d **не автоматический прогон**: только план permission/risk review для REST,
  GUI, registration/plugins/scripts, application lifecycle, global settings,
  cloud/auth/network. No UI clicks, no secret collection в report.
- **Invariants/visual:** frame/camera/output соответствуют fixture, unrelated
  settings не изменены; пользователь подтверждает изображение/видимость.
  Service effect/host/user/data destination нельзя считать approved по наличию API.
- **Negative:** fake excessive frame range, wrong output, blocking render, leaked
  path/token, unintended global setter, denied permission → zero native effects.
- **Limits/STOP/gate:** preview ≤1 frame, render proposal ≤512×512/1 image, client
  ≤90с только при принятом native bound; иначе BLOCKED_BINDING. W7d всегда
  BLOCKED_PERMISSION до отдельного согласования **каждой** рискованной категории.
  Не закрывать/перезапускать CLO, не регистрировать widget/plugin и не менять
  глобальную среду для достижения coverage. G0/G1 не заменяют этот permission.

### W8 — закрытие реестра и версионная регрессия (B00 reconciliation)

**Статус:** offline reconciliation доступна; полная real acceptance BLOCKED до
закрытия зависимостей W0–W7. Единственный target этой подготовки2026.1.336.

- **Initial/assets:** coverage/evidence records всех предыдущих пакетов,
  unresolved blockers и reviewed untracked reports; новых assets не требуется.
- **Required capability:** offline schema/completeness/report checks; runtime
  inventory diff лишь через реально реализованные allowlisted tools после gate.
- **Sequence:** reconcile every symbol+overload/type → раздельные denominators
  catalog/implementation/local/real → blocker report → назначить следующий
  минимальный пакет. При future upgrade только diff/review, не auto expansion.
- **Invariants/visual:** ни один unknown/blocked/excluded не засчитан implemented
  или real_pass; evidence scope/version указаны; no secrets/absolute private
  paths/assets в git, каждый tracked source/data shard ≤200000bytes. Visual N/A
  для отчёта; visual evidence предыдущих пакетов не подменяется count.
- **Negative:** fake orphan/missing row/evidence, alias double count, mixed
  version, COMPLETED_UNVERIFIED засчитан VERIFIED, giant shard, private paths.
- **Limits/STOP/gate:** offline только, bounded report/shards; unresolved entries
  возвращаются как blockers. W8 не запускает повтор P0–P3/load10 автоматически.
  Полноту объявлять лишь по согласованному denominator и закрытым gates;
  сегодняшняя подготовка этого результата не утверждает.

## 5. Предлагаемый порядок возвращения пользователя

1. Координатор заканчивает offline A0/local tests, review документов и выбранных
   asset proposals; никакого автозапуска. Реализации будущих domain tools нет —
   matrix остаётся BLOCKED, независимо от успешной подготовки reports.
2. Пользователь подтверждает exact build, перезапускает CLO/MCP сам; короткий
   metadata/discovery пакет W0 только в реально доступном scope current14.
3. Согласовать один реализованный первый W1 read-only подпакет; затем один
   assignment/color либо individual visibility. Asset import — отдельный gate.
4. Каждая следующая карточка — новое bounded разрешение по prerequisites, не
   blanket «run full API». При первом STOP остальные пакеты не запускаются.

Форма evidence: package ID + build + approved scope + initial observations +
actual tool sequence (без секретов/машинных путей) + result/readback invariants +
client/native timing с честными units + user visual verdict + report status +
blocker/next gate. Fixture filename можно держать только в локальном untracked
report. Не помещать exports, screenshots или installed assets в tracked files.
