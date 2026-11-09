---
name: clo-mcp-tool-design
description: Design or review CLO MCP tools, precise descriptions, input and output contracts, API traceability, discoverability, composition examples and tool-selection evaluations. Use before adding or documenting a tool.
---

# CLO MCP: проектирование инструментов

Прочитать корневой `AGENTS.md`. Пути этого skill относительны его каталогу;
корень проекта — `../../..`. Это инструкции по проектированию, не разрешение
реализации или запуска инструментов. Для HTTP/SDK дополнительно загрузить
`python-mcp-session`, для native adapter — `clo-python-runtime`.

## Источники

- `../../../docs/CLO_API_COVERAGE_PLAN.md`: цель покрытия и evidence statuses.
- `../../../docs/CLO_MCP_TOOL_AUTHORING.md`: обязательный стандарт описания.
- `../../../docs/CLO_MCP_TOOLS.md`: реально опубликованный набор, не legacy.
- `templates/tool-card.md`: полная карточка будущего инструмента.

Официальные CLO docs и binding установленной сборки определяют контракт.
Extended — донор, не source of truth. Для SDK сверить uv.lock/installed API;
сохранить официальный Python FastMCP1.26, HTTP/Named Pipe/FIFO. Общие советы
MCP-builder не разрешают TypeScript, SDK migration или смену транспорта.

## Порядок проектирования

1. Сформулировать пользовательское намерение, результат и границы операции.
   Проверить существующие tools: не плодить synonyms/aliases ради coverage.
2. Привязать qualified CLO symbol, overload, units, coordinate/index namespace,
   option types/enum, версию и evidence. Не угадывать arg0/return semantics.
3. Заполнить карточку: когда выбирать/не выбирать, inputs/outputs, guards,
   effects, limits, verification, errors и следующий безопасный шаг.
4. Написать короткий server-visible description. Первое предложение — действие
   и объект; далее ключевое отличие, units/scope, обязательные guards и риск.
   Критический запрет retry обязан быть здесь, а не только в skill/docs.
5. Сопоставить raw validators, JSON schemas, docstring и примеры. SDK coercion
   не заменяет валидацию. Указать все mandatory поля, запрет extras, bool-as-int,
   NaN, oversized inputs. Output schema описывает реальность, не желаемый API.
6. Annotations должны отражать эффекты; hints не ACL/разрешение. Idempotent
   hint никогда не даёт права повторить dispatched mutation после timeout.
7. Добавить minimum: один valid и один invalid/no-call пример, один пример
   композиции, одну типичную ошибку выбора с объяснением альтернативы.
8. Задать evaluation: выбор tool по намерению, правильные args/единицы,
   проверка результата и stop-on-error. Mutating evals только fake, не live CLO.
9. Review traceability: official → contract → adapter → tools/list → tests →
   workflow → evidence. Каждый пробел/blocker записать, не назвать готовностью.

## Tool и workflow — разные уровни

Полное API покрывать явными предметными операциями. Рецепт из нескольких tools
по умолчанию хранить в workflow skill, не превращать в новый server tool.
Composite tool оправдан только отдельным контрактом: bounded work, preconditions,
partial effects, readback и failure outcome. Не объявлять atomic transaction.
Нельзя generic call_api/exec для закрытия coverage. Не расширять полномочия
инструмента через текст workflow или скрытый cleanup.

## Проверка качества

Пользователь/модель должны понять без исходников: что изменится, чем отличается
соседний tool, какие индексы/units, как проверить успех и что делать при ошибке.
Присутствие callable, завершение вызова, проверенный эффект и полная real-CLO
приёмка — разные утверждения. Не изобретать completed/verified поля, которых
нет в текущей схеме; новые поля требуют реализации и тестов.
