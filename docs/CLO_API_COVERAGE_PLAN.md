# Полное покрытие CLO API — план переноса и расширения

Дата: 2026-11-09. Статус: **A0 и подготовка приёмки в работе; новые домены не включены**.

## 1. Цель и текущая граница согласования

Цель пользователя — полностью покрыть доступный функционал актуального CLO API.
170 tools проекта `adriendelmas/clo3d-mcp-extended` — источник решений, не граница
покрытия. Исходный локальный legacy-каталог также не является границей.

Первоначально пользователь выбрал только план и задания. Затем 2026-11-09
явно поручил самостоятельную работу над **A0 и полной подготовкой комплексного
тестирования**, включая локальные проверки и делегирование. Реальную приёмку
проводим вместе короткими пакетами после его перезапуска CLO/MCP. Текущая работа
не выполняет реальные CLO calls, не перезапускает MCP, не включает будущие
домены автоматически и не обещает реализовать весь native API за несколько часов.
Контракты и реализация каждого нового домена остаются отдельным пакетом.

Уточнения пользователя:

- Target только **CLO 2026.1.336**, номер сообщён пользователем; совместимость
  с другими сборками не требуется. Это не измерение runtime bindings.
- Каталог CLO Assets в Public Documents разрешён только на чтение; точный
  локальный путь хранится в заметке проекта, не в portable manifest.
- Результаты разрешены в подпапке проекта `acceptance-output/` (gitignored),
  не поверх исходных assets. Это пользовательские exports/reports, не IPC.
- Критерии предлагает агент, согласовываем перед коротким real пакетом.
- Сабагенты используют ту же модель, что основной агент; выбранный при этой
  подготовке model ID фиксируется в отчёте, не как постоянная настройка.

Принято и не повторяется как gate:

- P0–P3, первый пакет лекал, реальный `load10`, read-only `load1000`.
- Локальные коммиты первого пакета: `0afdbcf`, `dd40272`.
- Перед A0 полный результат повторно проверен: 306 passed (34.00 с). Новый
  итог после A0 фиксируется отдельно; это не real-CLO evidence.
- P4 modal/forced-exit остаются отдельными непроверенными пунктами; отказ от
  отдельного 30-минутного soak сохраняется. Они не объявляются завершёнными.

## 2. Что означает «актуальный» и «доступный»

Поддерживать две независимые оси:

1. Последний официально опубликованный API: источник, дата проверки, версия,
   конкретная страница метода, объявления перегрузок, связанные типы/enum/options.
2. API установленной CLO: пользователь подтвердил 2026.1.336; ранее измерен
   embedded Python 3.11.8 x64. Наличие callable/docstring
   проверяется в этой среде, реальная семантика — отдельным испытанием.

Документация новее установленной CLO не является разрешением обновлять CLO.
C++-описание метода не доказывает доступность Python binding. Новый модуль,
класс или option record сначала исследуется; пять текущих модулей introspection
не объявляются всем API. Требующие SDK/C++/UI automation операции остаются
видимыми blockers до отдельного решения, а не заменяются другим стеком молча.

Официальный API задаёт исходный каталог. Дополнить его публичными callable
установленной CLO, отсутствующими в документации, и кандидатами из extended.
Не выполнять найденные методы автоматически и не публиковать generic exec.

## 3. Источники и provenance

Зафиксированный latest: SDK11.0.1 / CLO2026.1.336, October2026. Проверенные
официальные ссылки, первичный подсчёт851 Python names в шести модулях +39GUI,
расхождения и результаты donor audit:
[`CLO_API_OFFICIAL_AUDIT.md`](CLO_API_OFFICIAL_AUDIT.md).
Это документированный universe, не подтверждённые851 bindings.

- Официальная точка входа: https://developer.clo3d.com/ и Python-раздел
  https://developer.clo3d.com/python.html . Версионность страниц требуется
  установить по источнику, а не вывести из даты компьютера.
- Донор: https://github.com/adriendelmas/clo3d-mcp-extended . Ранее исследованная
  ревизия: `df150d95db604e4651bbbdfb151b8204209a7d12`.
- Локальные `src/clo3d_mcp/server.py` и `plugin/clo3d_mcp_plugin.py`: полезные
  существующие маршруты, но legacy listener не импортируется и не запускается.
- Живые `list_clo_api` / `describe_clo_api`: bounded introspection без вызова
  описываемых native методов. Наличие != корректность != real acceptance.
- Первичные результаты этой подготовки: `docs/CLO_API_RUNTIME_EVIDENCE.md`.
- Локальный baseline47: `docs/CLO_API_LOCAL_BASELINE.md`.

При заимствовании кода сохранять MIT attribution/NOTICE донора; `LICENSE`
локального upstream не заменять. Не скачивать SDK/ассеты в git и не запускать
сторонний код. Без исполнения заимствованного кода возможно изучение исходников.

## 4. Реестр покрытия: первая обязательная задача

Отслеживаемый реестр подготовлен: `docs/api/clo_api_coverage.json` и читаемый
`docs/api/CLO_API_CATALOG.md`; official/source snapshots и coverage shards рядом.
Это исходные сведения/документация, **не IPC**. В нём нет session secrets,
машинных путей, пользовательских сцен или результатов сеансового обмена.

Получено890 qualified Python names (851основной список +39GUI),1134уникальных
declarations из1137blocks,77types/options,6дополнительных interfaces. Сопоставлены
donor170/local47/current14. Методические и native-contract неизвестные не
маскируются: per-overload semantics/implementation/real acceptance остаются
отдельными statuses. Current ограниченные10native operations сохранены как
scope, не автоматически принятые все официальные перегрузки.

Единица учёта: `module.symbol + overload_id`, а не количество MCP tools.
Alias `W`/не-`W` можно связать с одной операцией только с явной записью о
проверенной эквивалентности; overload нельзя считать покрытым через соседний.
Классы, enum и option records учитывать как зависимости операций, не раздувать
ими число реализованных команд. Вспомогательные/деструкторные exports также
должны получить классификацию, не становиться инструментами автоматически.

Поля строки реестра:

- `id`, `domain`, `module`, `symbol`, `overload`, `signature`, `units`;
- `docs_url`, `docs_version`, `checked_on`, `signature_source`;
- `runtime_presence`: present / absent / not_checked;
- `binding_status`: callable / types_missing / ambiguous / not_checked;
- `effect`: read / scene_mutation / filesystem_write / external_effect /
  lifecycle / unknown; `may_open_dialog`, `may_block_ui`;
- `donor_revision`, `donor_tool`, `donor_handler`, `local_equivalent`;
- `implementation`: planned / implemented / alias / blocked / excluded;
- `blocker_reason`, `decision_needed`, `owner_task`, `dependencies`;
- `contract_path`, `adapter_path`, `tool_name`, `test_paths`;
- `verification`: not_tested / local_pass / real_pass / real_fail;
- `verification_method`: getter / return_value / artifact / user_visual /
  unavailable; `acceptance_scope`, `evidence_reference`.

Ошибки и ограничения — отдельные оси, не один статус «готово». Пример:
implemented + local_pass + present ещё НЕ real_pass. Setter без getter может
подтверждать только завершение native вызова/return value, но не объявлять
`verified=true` без согласованного критерия эффекта.

Полнота отчётности: каждый элемент объединённого каталога классифицирован.
Полнота реализации: каждая доступная согласованная операция реализована либо
имеет незакрытый blocker; blocked/excluded НЕ считаются реализованными.
Проценты давать отдельно для каталога, реализации и реальной приёмки, с явным
знаменателем. Отсутствие в донорах не причина исключить официальный метод.

## 5. Полная доменная карта

Порядок — по зависимостям, не обещание одновременной готовности всех пакетов.

### W0. Каталог, типы, правила контрактов

Сверка official / runtime / extended / legacy; все модули и перегрузки;
инвентаризация enums/options; проверяемый реестр; единые ошибки/валидация и
правила composition без произвольного dispatch. Выявить неизвестные bindings.

### W1. Базовая сцена, материалы, аватар, цветовые варианты

- Project/version/read-only garment information; bounded JSON/records.
- Fabric count/name/info, assignment, color; затем импорт/replace/delete,
  PBR, физические параметры, текстуры и material/face/colorway semantics.
- Avatar count/names/genders/properties/visibility; import/delete;
  позы, измерения, activation/smooth/subdivision/soft body/текстуры.
- Colorway count/name/current/copy/delete, связанные материалы и цвета.

Начальный поднабор этой волны хорош для ближайшей совместной пакетной приёмки;
его точный scope выбирается перед реализацией. Импорт требует явно выбранных
локальных файлов; подготовка контрактов возможна без них, приёмка — нет.

### W2. Полная геометрия лекал и свойства

Outline/line/component/internal/baseline reads; линии, точки, кривые,
внутренние формы, аннотации; flip/unfold/symmetry/instances/layer clone;
grain, shrinkage, thickness, layer, freeze/lock/hide/solidify и прочие свойства.
Сначала read-only топология; затем простые setters с readback; затем
разрушающие операции. Не использовать небезопасный `MovePatternPoint` до
отдельного воспроизведения и решения. JSON/CPX import/export классифицировать
по фактической замене/добавлению сцены и файловым эффектам.

### W3. Швы, строчки, фурнитура и графика

Seamline groups, partial sewing, connectivity; topstitch styles/properties;
buttons/buttonholes/pairs, zippers, trims, graphics, их placement/materials.
Все индексы компонентов сверяются по актуальной топологии. Длинные перегрузки
не переносить позиционно по догадке. Create/merge/cut требуют отдельной фикстуры
и критериев связности/геометрии. Швы — не эквивалент «готовая одежда».

### W4. 3D-расстановка, mesh и короткая симуляция

Arrangement list/position/orientation/shape, redrape/reset; particle distance,
mesh type/count; quality/settings, wind/gravity/collision; bounded simulate.
Сначала getters и setters с независимой сверкой, затем один короткий цикл на
заданной сцене. Timeout не отменяет Simulate; секундный предел клиента не
гарантирует секундный предел native API. Рендер и симуляция не стрессуются
неограниченно. По каждой настройке определить getter или честный уровень
подтверждения. Multi-setter без атомарности сообщает partial/unknown outcome.

### W5. Project I/O, импорты и экспорты

New/open/save; ZPRJ/ZPAC, DXF/CPX/JSON, OBJ/FBX/GLTF/GLB/USD/Alembic;
avatar/pose/fabric outputs; snapshot/thumbnail/custom views/turntable,
tech pack/BOM/POM/garment information. Точный набор определяется W0.
Нужны allowlist options, существующая папка вывода, политика overwrite,
проверка фактических артефактов и bounded list дополнительных файлов.
Не делать повторный экспорт на TypeError после входа в native вызов.
Dialog-only методы не автоматизировать кликами. Вызовы без dialog — отдельные
API, а не молчаливая подмена. Проект/импорт может заменить сцену: это явная
семантика контракта и отдельный пакет проверки, без скрытого NewProject.

### W6. Градация, nesting и UV

Grading sizes/groups/rules/offsets/paired avatar/quantity mix;
nesting settings/fixed positions/grain/start/stop; UV spaces/packing/transforms.
Нужны специальные сцены, единицы, отчёт о топологии и качественные критерии;
невозможно принять по одному count. Сначала inspect/getters, затем bounded
операции с заранее выбранной сценой.

### W7. Анимация, рендер, отображение и сервисный API

Frames/ranges/recording/cache; render settings/status/outputs/lights/camera;
display/view styles; metadata/object browser/library/assets; остальные публичные
операции, выявленные W0. Cloud/auth/network, plugin/widget registration,
script registration, process/application lifecycle — видимые отдельные группы
риска. Полнота API не разрешает молча устанавливать плагины, запускать скрипты,
отправлять данные в сеть, завершать CLO или менять глобальную среду.
Для таких групп нужен отдельный контракт и согласование побочных эффектов.

### W8. Закрытие покрытия и версионная регрессия

Проверить все неклассифицированные строки; сопоставить bindings/types/options;
выпустить отчёт доступно/реализовано/реально принято/blockers. Повторить diff
каталога после обновления CLO/official docs, а не автоматически расширять
whitelist. Устаревшие принятые gates не повторять без затронувшей их причины.

## 6. Архитектура будущей реализации

Сохранить Python + официальный FastMCP 1.26.0 + HTTP loopback + Named Pipe +
одну внешнюю FIFO. Это расширение API, не переписывание транспорта.

Новые домены: stdlib-only `*_contract.py`, `*_api.py`, отдельные внешние
`*_tools.py`, tests. API adapter получает фиксированные modules от launcher;
не импортирует legacy listener или MCP. Регистрация только явных операций.
Общие точки protocol/jobs/executor/HTTP/launcher меняет один integration owner.
Не включать все найденные callable как capabilities и не вводить arbitrary
`call_api(module, name, args)` даже для достижения численного покрытия.

Сохранять raw validation до coercion SDK: лишние поля, bool-as-int,
NaN/Infinity, строковый JSON, oversized collections, unknown enums/options
отклоняются до enqueue и повторно на границе исполнителя. Нужны явные units,
лимиты ответа/работы, stale object guards и guards текущего colorway/сцены.
`expected_name` — не durable ID и не защита от всех внешних изменений.

Перед mutation проверить нужные getters, типы и аргументы. После входа в
native setter исключение/readback failure может означать изменившуюся сцену.
Не повторять setter, не делать автоматический rollback/cleanup. Уже принятые
коды `outcome_unknown`, `scene_change_unverified` не маскировать успехом.
Новые public codes согласовать и провести через все слои одним owner.

Файловые импорты/экспорты — явные пользовательские операции, не IPC.
Проверить абсолютные локальные пути, формат/существование, размер/доступ,
overwrite, побочные файлы и диалоги; не выполнять каталоговый поиск ассетов
по всей машине. Read-only импорт документов/схем не требует сцены.

## 7. Организация передачи и приёмки

Подробные briefs: `docs/CLO_API_AGENT_TASKS.md`. Сначала W0, затем независимые
доменные adapters/contracts/tests, потом последовательная интеграция и один
внешний bounded acceptance client. Реализационные сабагенты не получают права
одновременно тестировать CLO или изменять общие transport-файлы.

Один перезапуск после законченной локальной волны; свежий процесс CLO нужен
из-за cached modules/retained callbacks. «Перезапуск MCP» не равен hot reload
embedded Python. Не перезапускать/останавливать приложение вместо пользователя.

Будущий пакетный прогон состоит из discovery, preflight, независимых domain
smoke сценариев и cross-domain сценария. Это не одна гигантская транзакция.
После первой ошибки/unknown зависимые mutations не отправляются, cleanup в
finally запрещён. Все subsequent mutations подаются последовательно, не
заранее в FIFO. Принятый pattern load не повторяется; создать несколько
специальных деталей для новых fabrics/sewing проверок допустимо как новая
фикстура, но не объявлять этим повторную приёмку первого пакета.

У каждого сценария: assets, initial state, ожидаемые эффекты, инструментальные
и визуальные критерии, native/client timing, stop method и failure criteria.
Нет подходящего ассета — BLOCKED, не PASS и не скрытый skip. Setter с неполным
readback — COMPLETED_UNVERIFIED, не VERIFIED. Полная локальная suite не
заменяет реальные проверки; полная цель не достигнута до закрытия реестра.
