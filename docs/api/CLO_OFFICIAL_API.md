# Официальная структурная спецификация CLO API

Target: **CLO2026.1.336 / SDK 11.0.1**. Проверено: 2026-11-09.
Источник — официальные публичные HTML и RST; это не SDK, не runtime inventory и не real acceptance.

## Полнота и denominator

- API List: **851 qualified names / 1098 Python declaration blocks** (первичная оценка 851/1098 подтверждена).
- Отдельный GUI reference: **39 names / 39 blocks** (39 подтверждены).
- Всего: **890 names / 1137 blocks / 1134 уникальных объявлений**.
- Option & Type: **77 records / 582 members**, включая enum values и методы records (77 секций подтверждены).
- Дополнительные C++ interfaces: **6**; не входят в Python denominator.

- `export_api`: 91 names, 123 blocks, 123 unique declarations.
- `fabric_api`: 134 names, 284 blocks, 284 unique declarations.
- `gui_api`: 39 names, 39 blocks, 39 unique declarations.
- `import_api`: 38 names, 44 blocks, 42 unique declarations.
- `pattern_api`: 217 names, 233 blocks, 233 unique declarations.
- `rest_api`: 7 names, 8 blocks, 8 unique declarations.
- `utility_api`: 364 names, 406 blocks, 405 unique declarations.

Один occurrence соответствует одному документированному Python-блоку с двумя source locations (HTML/RST); эти две ссылки не удваивают denominator.
Повторы одного normalized signature объединены, но documentation и все occurrences сохранены. Разные overload/default/return spelling и W/non-W имена не объединяются.

### Повторяющиеся объявления

- `import_api.ImportAVAC`: `def ImportAVAC(_filePath : str, _apfFilePath : str) -> bool` — 2 occurrences.
- `import_api.ImportGraphicStyleFromImage`: `def ImportGraphicStyleFromImage(_filePath : str) -> bool` — 2 occurrences.
- `utility_api.SaveCLOFileThumbnail`: `def SaveCLOFileThumbnail(filePath : str, outputPath : str, thumbnailIndex : int) -> bool` — 2 occurrences.

## Формат и использование

`clo_official_api.json` — индекс с provenance, counts, относительными shard paths и SHA-256 каждого shard. Файлы `official/*.json` меньше 160000 bytes; полный сайт/SDK/assets не сохраняются.
`scripts/build_official_api_catalog.py:load_catalog(path)` возвращает `methods`, `types`, `interfaces`, `sources`, `counts`, `provenance` после проверки hashes/IDs/references.
Method ID — qualified name; declaration ID — qualified name + SHA-256 prefix normalized signature. Raw spelling и @param/@return docs сохранены; comments не интерпретируются как проверенные диапазоны/defaults.
Type member содержит raw declaration, annotation/value raw и описание; продолжения комментариев сохраняются. Enum values присваиваются только при явном `=`, значения в комментариях остаются описанием.
Type references: `resolved` только при наличии type record; `documentation_mention` не означает binding/parameter type. Неизвестные annotation identifiers — `unresolved`. `ApiTypes` — документированный namespace, не результат import/probe.

Source `sha256` хеширует фактически скачанные HTML/RST bytes (`hash_scope=fetched_source_bytes_not_normalized`); shard `sha256` хеширует normalized JSON bytes (`hash_scope=normalized_json_shard_bytes`). Это разные уровни provenance. Method notes ограничены 16000 characters на occurrence, превышение вызывает ошибку, а не обрезание. Source anchors сохранены в HTML locations.

## Ограничения и blockers

- Весь runtime_presence/binding_status методов — not_checked. Наличие Python tab не доказывает callable/constructibility/совместимость build.
- Сигнатуры с C++ spelling/pointers в Python tab и unresolved types помечены ambiguous; ошибки документации не исправляются догадками. parse_status параметра ambiguous сохраняет raw.
- Параметры извлекаются текстовым bracket/quote-aware parser; ни eval, ни import, ни исполнение snippets не используются. Единицы/эффекты/семантика в raw docs, а не выдуманные контракты.
- HTML/RST блоки сверяются по порядку, языку и тексту (игнорируются только trailing spaces). Различия/count drift приводят к ошибке, не к потере блока. Межстраничной пагинации в этих официальных reference sources нет; все секции читаются целиком.
- Library: web docs называют интерфейсы/factory, но полный список их методов отсылает к SDK sample; signature null, явный blocker. Event: 2D signature только из C++ example, 3D signature не выведена по аналогии.
- Парные C++ tabs сохранены как документация, не самостоятельные Python API. C++-only Library/Event не включены в methods. GUI callback/modal APIs не дают разрешение на UI automation/restart.
- Public docs не pinned version archive: snapshot SHA-256 и download/changelog evidence связывают каталог с latest на дату проверки; будущий drift требует review, не автоматического расширения runtime whitelist.
- Текстовые противоречия @return и сигнатур не разрешены автоматически; независимая контрактная проверка по каждой операции остаётся обязательной.

Не разрешённые annotation identifiers (число объявлений/ссылок):
- `CloTheme`: 1.
- `CloWidgetType`: 3.
- `QWidget`: 2.
- `int64_t`: 1.
- `std::array`: 2.
- `std::function`: 2.

## Воспроизведение (без CLO)

```powershell
python scripts/build_official_api_catalog.py --check
uv run --frozen --with pytest pytest -q tests/test_official_api_catalog.py
python scripts/build_official_api_catalog.py --refresh --check
python scripts/build_official_api_catalog.py --refresh --checked-on YYYY-MM-DD
python scripts/build_official_api_catalog.py --source-dir <cached-source-dir> --checked-on YYYY-MM-DD --check
```

Без refresh/source-dir `--check` полностью offline, проверяет committed manifest и отчёт. С refresh/source-dir строит заново и сравнивает все bytes; `--check` никогда не пишет. Для сравнения берётся snapshot date индекса, если --checked-on не указан. Refresh — один bounded fetch каждого из 16 фиксированных source URLs, без retries: 20 s/socket, общий deadline 180 s проверяется между requests/64KB reads, до 4 MB/source. Socket timeout ограничивает бездействие, не всю длительность read при медленном потоке; не обещается hard wall-clock предел сетевого стека. Ошибка fetch/build не меняет committed files.
Источники можно заранее сохранить вне repo в approved Temp/opencode. Для offline rebuild нужны все 16 исходных файлов, они не коммитятся. Generator не удаляет старые shards автоматически; индекс определяет активный набор.

## Source provenance

Release: October 2026; documentation update: October 2026. SDK URLs извлечены только как ссылки, архивы не скачивались.

- [changelog.html](https://developer.clo3d.com/changelog.html): 122122 bytes; SHA-256 `19657c3fd07ab7ce2bc962e82147efc44aefc0b988a1fde122587aef0bdbe543`.
- [changelog.rst.txt](https://developer.clo3d.com/_sources/changelog.rst.txt): 68406 bytes; SHA-256 `b5d351ea4965aaa8916d21cb640bcf68997e46b9398ec6d3f901075daf4e83f8`.
- [download.html](https://developer.clo3d.com/download.html): 56608 bytes; SHA-256 `c5766af01ebd9112f399cff9ff41119518cc45044c1a2e6425f7337b6454864f`.
- [download.rst.txt](https://developer.clo3d.com/_sources/download.rst.txt): 17376 bytes; SHA-256 `69d438b2284a5d6124db2f4f719d680bcbdd6aedfd6dedaf5819f83aac306eb4`.
- [eventplugin.html](https://developer.clo3d.com/eventplugin.html): 19995 bytes; SHA-256 `3b52cc3723356a129e95663deb68fd8464afc5b84054f915bb8b3bf5cf90fce7`.
- [eventplugin.rst.txt](https://developer.clo3d.com/_sources/eventplugin.rst.txt): 4134 bytes; SHA-256 `17e6e3bb977054bb976cfc343b6c2598e87ccb835d5f0b5cb9bf7110559b6118`.
- [gui_api_reference.html](https://developer.clo3d.com/gui_api_reference.html): 70402 bytes; SHA-256 `8b34f236abc73263e13c5899c93ab08278c1d5f506e2d4b4de3b1f0cd62c3b53`.
- [gui_api_reference.rst.txt](https://developer.clo3d.com/_sources/gui_api_reference.rst.txt): 22067 bytes; SHA-256 `707245798c3351e85ad883f4b343ba9cd9f422b7b13a302db9f23c9ba3d5f53b`.
- [library.html](https://developer.clo3d.com/library.html): 11112 bytes; SHA-256 `4e4ca06369b1df045cfec6e47890030b23709c6f49df66f90e9125034339dcb2`.
- [library.rst.txt](https://developer.clo3d.com/_sources/library.rst.txt): 2032 bytes; SHA-256 `1e14651d874bb3cfbe8c94492de9d82fc7d4ea17676847e67cb062679d101391`.
- [list.html](https://developer.clo3d.com/list.html): 2564067 bytes; SHA-256 `9efa3a05dbb8c8db3fb3dae9eb9b8b578025be17ac9e5e57b86545a7314ba951`.
- [list.rst.txt](https://developer.clo3d.com/_sources/list.rst.txt): 950239 bytes; SHA-256 `bbd825dad535c44525b98bdbe358d8129a6fcb300d89c90e7e5297443cf34862`.
- [optiontype.html](https://developer.clo3d.com/optiontype.html): 169325 bytes; SHA-256 `71220fb0c2f8b2990a66aa85a38007e412056282b1c68ae18de09fb46e679984`.
- [optiontype.rst.txt](https://developer.clo3d.com/_sources/optiontype.rst.txt): 72889 bytes; SHA-256 `e07f57452eb101c2a529d7712e6421420b74182825c9e1deb1e58381f9d479a7`.
- [python.html](https://developer.clo3d.com/python.html): 8830 bytes; SHA-256 `d59059f2d1ea5c1b88e16e6dda5bef0b6254ff742f499cad2c8a4b2f26249d06`.
- [python.rst.txt](https://developer.clo3d.com/_sources/python.rst.txt): 741 bytes; SHA-256 `8809f57014e453614799b4803bd4893536a759931b5309d26f4d3020c8c2d420`.
