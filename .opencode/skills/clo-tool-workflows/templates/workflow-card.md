# Workflow: <id — пользовательский результат>

Статус: draft / fake-tested / real-accepted; recipe не новый composite tool.

- Trigger / когда НЕ использовать:
- Пользовательское разрешение / scope / external effects:
- Exact required published tools + capability/profile/build:
- Assets, исходная сцена, identity/units/index namespaces:
- Лимиты calls/mutations/objects/time/result; client deadline != native cancel:

## Последовательность

1. Discover/read: <tool(args), проверяемые поля>.
2. Preflight: <guards и stop при mismatch>.
3. Mutation: <один вызов; args из какого свежего read>.
4. Verification: <getter/artifact/visual; tolerance; что не доказано>.
5. Next dependency: <только после успешных обязательных checks>.
6. Planned cleanup: <если вообще нужен; own objects; no finally cleanup>.

Для каждой стрелки указать outputs → inputs, invalidated references и условие
остановки. В planning docs использовать placeholders, не придуманные IDs.

## Отказы

- Missing tool/asset/approval → BLOCKED до mutation.
- Unknown/error/timeout/schema failure/session change → STOP mutations.
- Read-only reconciliation: <bounded calls после доступности executor>.
- Что нельзя retry/undo; что остаётся неизвестным:

## Оценка и evidence

- Synthetic fixture, expected call trace и результаты:
- Инъекция ошибки на каждом шаге: никакой последующей mutation:
- Выбор tool по естественному запросу; negative/ambiguous запрос:
- Real acceptance reference/scope/pending; не live eval в pytest:
