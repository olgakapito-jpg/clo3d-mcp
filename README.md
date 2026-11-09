# CLO3D MCP — Python / Windows Named Pipe

Один скрипт внутри CLO запускает отдельный MCP HTTP-процесс для текущего
сеанса. Ассистент подключается по `http://127.0.0.1:8765/mcp`.
Обмен с CLO — Named Pipe, **без файлов запросов, ответов и heartbeat**.

Транспортный MVP дополнен первым пакетом лекал (**9 новых инструментов**;
реальные изменения, load10 и отзывчивость UI подтверждены); не полный набор
построения одежды. Проверенная среда: Windows, CLO 2026.1, встроенный Python
3.11.8 x64, внешний CPython 3.11.9, официальный MCP SDK 1.26.0.
P0–P3 приняты реальными проверками; P4 (нагрузка/длительная работа) выполняется.

Первый пакет: ограниченная документация CLO API, список/геометрия деталей,
создание прямолинейного контура, имя, копирование, перемещение целой детали,
удаление. Проверка: `docs/PATTERN_API_CHECK.md`. После обновления нужен перезапуск
CLO и launcher: старый исполнитель продолжает использовать кэшированные модули.

## Подготовка

- Один экземпляр CLO с Python Script Editor и действующей лицензией.
- Установленные `uv` и CPython 3.11. Исходники должны оставаться доступны CLO.
- Из корня checkout выполнить во внешнем PowerShell, **не внутри CLO**:

```powershell
uv sync --frozen --python 3.11
```

Launcher ожидает `.venv/Scripts/python.exe`. Никаких установок пакетов в
встроенный Python CLO, собственного C++, CLO SDK или Qt не требуется.
Python-пакет декларирует 3.10+, но новый runtime проверен только на указанной
выше среде; совместимость с другими версиями не обещается.

## Запуск

1. Открыть CLO, для диагностики — расходную тестовую сцену.
2. В **Script → Script Editor** открыть `plugin/clo3d_mcp_start.py` и нажать Run.
3. Закрыть Script Editor. Launcher возвращает управление, callback обслуживается
   UI CLO. STARTED — ещё не готовность; ожидается READY и/или `ready=True` в MCP.
4. Если CLO не задаёт `__file__`, указать абсолютный путь к корню checkout
   в `ROOT` в начале launcher. Не подменять внешний Python на `sys.executable` CLO.

Повторный запуск в **том же CLO** даёт ALREADY_STARTED, не второй процесс.
Второй экземпляр CLO на том же порту не поддерживается: занятый порт — ошибка,
чужой сервер не завершается. После изменения runtime-модулей открыть свежий CLO,
не перезагружать модули с сохранёнными native callbacks на месте.

### Панель Старт / Стоп (gui_api)

Вместо отдельных start/stop scripts можно открыть в Script Editor
`plugin/clo3d_mcp_panel.py` и нажать Run. Если `__file__` отсутствует, задать
`ROOT` в начале этого скрипта. Появится dock panel CLO (fallback — tool window)
с кнопками **Старт**, **Стоп**, **Обновить** и статусом. Периодического callback
в gui_api нет, поэтому статус обновляется после действий и по **Обновить**.
Закрытие панели не останавливает сервер; повторный Run показывает её снова.
Нет Win32/Qt и дополнительных зависимостей.
Жёсткого лимита запусков нет; launcher очищает кеш runtime-модулей
на Stop→Start, но сам panel/launcher нужно запускать из свежего файла. Реальная
GUI-приёмка панели ожидает проверки:
[инструкция и критерии](docs/CLO_MCP_PANEL_CHECK.md).

Перенос формы на macOS и управление restart из ассистента — отдельное
[предложение controller/supervisor](docs/CLO_MCP_CONTROLLER_PLAN.md), не включённая
поддержка. UI теперь штатный CLO `gui_api` (dock panel); transport/runtime macOS
требуют самостоятельной реализации и реальной приёмки.

## Текущий проект OpenCode / OpenChamber

`opencode.json` уже содержит project-local remote `clo`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "clo": {
        "type": "remote",
        "url": "http://127.0.0.1:8765/mcp",
        "protocol": "legacy"
      }
    }
  }
}
```

`legacy` здесь — classic MCP initialize официального SDK 1.26, **не файловый IPC**.
В другом checkout добавить project-local remote через
`opencode mcp add clo --url http://127.0.0.1:8765/mcp`.
Проверить `opencode mcp list` или панель MCP / `/mcps`. Конфигурация
перечитывается без перезапуска OpenCode. До запуска CLO или после его закрытия
ECONNREFUSED нормально. Глобальные настройки проекта не требуются.

## Инструменты нового пути

- `ping`: реальный round trip через FIFO в UI executor CLO.
- `get_pattern_count`: последовательное чтение числа лекал.
- `transport_status`: внешняя очередь/HTTP; доступен и при занятом CLO.
- `get_session_info`: CLO session ID, PID и readiness (не MCP HTTP session ID).
- `create_test_rectangle`: **один** квадрат 100×100 в координатах API (мм)
  в начале 2D. Изменяет сцену; запускать осознанно, не повторять после timeout.
- Первый пакет лекал: `list_clo_api`, `describe_clo_api`, `get_pattern_list`,
  `get_pattern_geometry`, `create_pattern`, `set_pattern_name`,
  `copy_pattern_with_offset`, `move_pattern_relative`, `delete_pattern`.
  Строгие параметры, stale-index guard и readback; native compatibility ещё
  проверяется по [отдельной инструкции](docs/PATTERN_API_CHECK.md).
- Inventory: `get_fabric_list`, `get_avatars` — read-only Object Browser
  (fabric indices без colorway). Это не assignment/pose.
- Relationship: `get_pattern_fabric`, `assign_pattern_fabric` — limited real
  API/readback PASS; assign только после fresh list/current mapping, один
  effect и независимый readback.
- Outline: `get_pattern_outline` — read-only, real gate **BLOCKED**: native `[]`
  для существующей детали; не retry, не success и не bbox/line fallback.
- Lines: `get_pattern_lines` — read-only внешние линии (lineIndex, length_mm,
  orientation, location, start/end/mid, mid_norm), один native read; кривые и
  frame после move/rotate отдельно не заявлены.

Новый путь не загружает extensions и не публикует legacy-команды импорта,
экспорта, симуляции или exec. Параметризованное создание: до 64 точек, прямые или curve-вершины (0/2/3);
отверстия не подключены, curve semantics предварительные.

Описание каждого текущего инструмента: [каталог текущих tools](docs/CLO_MCP_TOOLS.md).
Выбор и совместное использование: [рецепты](docs/CLO_MCP_WORKFLOWS.md).
Для разработки следующих пакетов: [стандарт описаний](docs/CLO_MCP_TOOL_AUTHORING.md)
и [локальные skills и шаблоны](docs/AGENT_WORKFLOW.md). Эти документы сами по себе
не меняют live MCP metadata и не требуют перезапуска CLO/MCP.

## Остановка

Внутри того же CLO запустить `plugin/clo3d_mcp_stop.py`, закрыть редактор
на несколько секунд. FINISHED должен показать stopped, exit code0,
оба cleanup_pending=False и error=None. Повторный stop выводит отчёт.
После обычного закрытия CLO его MCP завершается сам по pinned process handle.
Управляется только принадлежащий сеансу child, не процессы по имени/порту.

## Версия и кеш embedded Python

- `clo3d_mcp.BUILD` — 12 hex SHA-256 от исходников пакета. `get_session_info`
  отдаёт `server_build` (внешний процесс) и `executor_build` (интерпретатор CLO).
- Совпали → Stop→Start действительно загрузил текущие исходники. Разные → во
  встроенном Python остались stale `sys.modules`; запустите Start ещё раз
  (лаунчер очищает `clo3d_mcp.*` и `importlib.invalidate_caches` перед импортом),
  при необходимости — полный restart CLO.
- Launcher чистит кеш только при запуске из свежего файла: Script Editor нужно
  переоткрыть с диска, иначе выполнится старый буфер. Изменения самого launcher,
  CLO C++/API-модулей и `.pyc` не лечатся очисткой `sys.modules` — нужен новый Run
  или restart CLO.

## Гарантии и ограничения

- Один выполняемый CLO job, внешняя FIFO32, bounded history128/waiters128.
- Раздельные deadlines очереди/dispatch. Timeout и отмена после dispatch
  **не останавливают CLO API**. Следующий job не идёт поверх незавершённого.
- Отправленные команды автоматически не повторяются. `outcome_unknown` означает
  необходимость сверить сцену; exactly-once через падение процесса не обещается.
- Долгий синхронный CLO API может блокировать UI. Пауза callback или модальное
  окно не считаются смертью CLO. Readiness подтверждает только текущий сеанс.
- HTTP только loopback, строгие Host/Origin checks. **HTTP без отдельной
  аутентификации**: доверяем локальным процессам машины. Не открывать порт
  наружу, не ставить proxy; loopback не защита от вредоносного локального ПО.
- Pipe — ACL текущего пользователя, peer PID и HMAC. Секрет в памяти, не в логах.
- Остановленные поколения callback удерживаются до выхода CLO: очередь WM_TIMER
  может ссылаться на их адрес. Жёсткого лимита нет; после многих Stop→Start память
  растёт, полный restart CLO её освобождает.
- Поддержка не-Windows и нескольких CLO не входит в новый путь.

## Диагностика и тесты

План следующего расширения: [полное покрытие актуального CLO API](docs/CLO_API_COVERAGE_PLAN.md),
[задания сабагентам](docs/CLO_API_AGENT_TASKS.md). Это планирование, не новый
набор включённых tools; реализация и реальные проверки новых доменов ещё не начаты.

Подготовка A0 и комплексной приёмки:
[общий реестр official/donor/current](docs/api/CLO_API_CATALOG.md),
[порядок совместной проверки](docs/CLO_COMPREHENSIVE_CHECK.md),
[короткие пакеты и критерии](docs/CLO_ACCEPTANCE_PACKAGES.md),
[offline/dry-run клиент](docs/DOMAIN_BATCH_CHECK.md),
[metadata probe](docs/CLO_API_PROBE_CHECK.md),
[offline evaluation сценариев](docs/CLO_TOOL_EVALUATION.md).
Target — только CLO **2026.1.336**. Исходные assets только на чтение;
разрешённые отчёты/экспорты — в gitignored `acceptance-output/`, не IPC.

`http_bind_failed`: порт занят, не убивать владельца порта. NOT_STARTED:
проверить корень проекта и подготовленную `.venv`. Нет строки READY:
проверить `get_session_info` — в принятом CLO callback работал, хотя вывод
READY не появился. Не запускать launcher бесконечно и не скрывать сбои retries.

```powershell
uv run --frozen --with pytest pytest -q
```

Windows CI запускает эту же suite, включая actual pipe/process тесты без CLO.
Локальные fake API и HTTP/pipe проверки **не заменяют** ручную приёмку CLO.
Реальные результаты и инструкции:

- [План и границы этапов](docs/PYTHON_TRANSPORT_PLAN.md)
- [Принятый P3](docs/P3_MCP_CHECK.md)
- [P4: ограниченная нагрузка и ручные проверки](docs/P4_TRANSPORT_CHECK.md)

## Legacy и происхождение

Upstream: [Ubani-Studio/clo3d-mcp](https://github.com/Ubani-Studio/clo3d-mcp),
автор исходного проекта Alabo MacPepple-Jaja. Исходные handlers и тесты сохранены.
Историческая инструкция с каталогом бизнес-инструментов сохранена в
[docs/LEGACY_README.md](docs/LEGACY_README.md); это **не** инструкция нового пути.
`uv run clo3d-mcp` / `src/clo3d_mcp/server.py` и
`plugin/clo3d_mcp_plugin.py` остаются отдельным stdio/file legacy-режимом.
Новый launcher никогда не переключается на него автоматически.

MIT, см. [LICENSE](LICENSE). SDK/сцены CLO в репозиторий не включены;
нужна собственная лицензия CLO.
