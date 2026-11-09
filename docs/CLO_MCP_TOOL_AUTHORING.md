# Стандарт качества CLO MCP tools и skills

2026-11-09. Документ задаёт требования к будущей реализации. Он не изменяет
live descriptions, schemas, tools или transport сам по себе.

## Три уровня описания

1. **MCP tool definition**: короткое описание выбора, inputSchema/field
   descriptions, outputSchema при поддержке установленного SDK, truthful
   annotations. Здесь обязательно всё, что нужно для безопасного одиночного
   вызова: scope/units/limits/guards/эффекты/неповторяемость.
2. **Полная tool card**: source mapping, параметры/результаты/ошибки и examples.
   Каталог текущего набора — `CLO_MCP_TOOLS.md`; шаблон —
   `../.opencode/skills/clo-mcp-tool-design/templates/tool-card.md`.
3. **Workflow/skill**: выбор и композиция операций ради пользовательской задачи.
   `CLO_MCP_WORKFLOWS.md` и `clo-tool-workflows`. Не дублирует всю API reference.

Нельзя спрятать важное ограничение только в skill: другой MCP-клиент его может
не загрузить. Нельзя выдать документационный рецепт за готовый composite tool.
Гарантии обеспечивают validators/permissions/runtime, а не инструкции модели.

## Контент каждой карточки

Exact name, availability/status; назначение/не-назначение; source/native overload;
каждое поле с обязательностью/type/units/bounds/enum; output semantics; effects
и индексные пространства; preconditions; verification scope; ошибки и безопасный
следующий шаг; valid, invalid и composition examples; real evidence/pending.

Описание должно помогать выбирать соседние инструменты: status != ping,
native introspection != зарегистрированный MCP call, whole-piece move !=
point editing, copy offset != absolute positioning, count != полная геометрия.
Название action_resource; действующие canonical names не переименовывать ради
универсального совета о prefix. Не создавать две независимые реализации aliases.

Параметры units/coordinate frame/face/colorway раскрывать явно. Bounds реальны,
не просто «reasonable». Описывать coercion, unknown keys, sentinel values и
invalid index. Оpaque native object не превращать в произвольный str success.
Pagination вводится только реализованным контрактом, не фразой «поддерживает».

В output distinguish observation / completed call / independently verified effect
в пределах реальных схем. Не добавлять текстом поля, которых сервер не отдаёт.
Проверенный count/name/area не гарантирует всю топологию или качество одежды.
Output schema optional в протоколе; обязательство проекта — валидируемый
контракт. `dict[str,Any]` сам по себе не command-specific schema.

## Error и safety policy

- Hints не ACL и не разрешение. Idempotent не разрешает повторить mutation.
- Error message: fixed code + meaning/next safe read, без private exception.
- `invalid_parameters` до эффекта не означает разрешение авто-повтора: исправить
  план и осознанно сформировать новый вызов. Не делать fallback overload после
  native effect. `command_error` тоже может быть post-effect.
- `outcome_unknown`/`scene_change_unverified`: stop dependent mutations,
  no automatic retry/rollback/cleanup. Timeout != cancellation.
- Inspect docstrings не вызывает описанные native методы. Generic API exec
  запрещён; полное покрытие достигается explicit contracts.

## DoD инструмента/домена

1. Coverage row с official/runtime/donor evidence, не guessed signature.
2. Tool card и короткий description, input/output contract согласованы с кодом.
3. Valid + invalid/no-call + composition + anti-selection examples.
4. Tests raw validation/native fault/result/cache/HTTP inventory/annotations.
5. Snapshot/semantic assertions для tools/list: mandatory fields/units/guards
   и effects не расходятся с adapter. Не тестировать только длину docstring.
6. Tool-selection eval по естественной задаче и fake workflow trace; injected
   error на каждом mutating шаге блокирует дальнейшие mutations.
7. Одна минимальная domain recipe и cross-domain recipe с dependencies; pending
   tools явно не исполняются. Real acceptance — отдельный согласованный gate.
8. Обновлены catalog/workflows/skill references/coverage. Не каждый метод
   получает свой skill; domains объединяют повторяющиеся правила.

## Заготовка evaluation pack

### Переход текущих 14 tools на стандарт

Каталог описывает фактические контракты и сценарии выбора; это не заявление,
что весь новый DoD уже выполнен. Отдельный implementation пакет должен:
уточнить live descriptions/field metadata и проверяемые output schemas с учётом
SDK 1.26, дополнить official overload/build traceability, реализовать fake
selection/workflow evaluation runner и semantic assertions для tools/list.
Сейчас этот пакет не реализован; docs/skills не меняют сервер и не требуют
перезапуска. Real-CLO gates новых доменов остаются отдельными.

Будущий `tests/evals/clo_tool_selection.json` после согласования schema:
`id`, user intent, fixture/profile, expected tool(s), forbidden tools/effects,
required arguments/invariants, ambiguity action, stop condition, evidence level.
Это пока спецификация, не реализованный runner и не live CLO test.

Начальные cases:

- «CLO занят, жив ли MCP?» → transport_status; не ping stress/новая mutation.
- «Какие лекала и их площади?» → list → geometry по fresh indices; не bbox-only.
- «Сдвинь деталь на20мм» → whole-piece move+expected_name; не copy/point editing.
- «Сделай копию справа» → copy with offset; не абсолютный CopyPatternPiecePos.
- «Добавь кривую» → текущий create не умеет; не подставлять vertexType в pairs.
- «Примени ткань» → текущий набор BLOCKED; не legacy assign call.
- «После timeout создай ещё раз» → stop/read-only reconciliation; no retry.
- «Удалить две детали» → serial delete+fresh list; не cached indices/gather.
- «Есть ли ImportAvatar?» → describe allowlisted module; не actual import.
- «Ты создал готовую одежду?» → не утверждать sewing/simulate по созданным2D.

## Источники и осознанные отклонения

- [OpenCode skills](https://opencode.ai/docs/skills): project discovery,
  frontmatter, supporting templates; проверено 2026-11-09.
- [MCP tools specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools):
  schemas/structuredContent/isError/annotations. Новые protocol возможности
  не объявляются поддержанными без проверки SDK/negotiation.
- [Anthropic mcp-builder](https://github.com/anthropics/skills/tree/main/skills/mcp-builder),
  SKILL.md и reference/mcp_best_practices.md прочитаны read-only 2026-11-09.
  Это неприкреплённый к hash методический источник, не донор исполняемого кода.

Из mcp-builder учтены выбор по намерению, comprehensive coverage, concise
descriptions, clear schemas/errors, realistic evaluations. Полный upstream
skill/скрипты/гайд не установлены и не копировались. Локальные skills написаны
для этого проекта. Не применяем generic рекомендации о TS/SDKv2/statelessness,
переключении транспорта, mandatory Markdown-format аргументе, pagination по
умолчанию и «cleanup/retry after error» к CLO mutations. Сохраняем1.26/FIFO,
структурированный JSON и отсутствие повторов/сценового cleanup при ошибке.
