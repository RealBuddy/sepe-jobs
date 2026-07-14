# SEPE scraping — техническая документация / handoff

Всё, что нужно, чтобы подхватить проект `sepe-jobs` (или перенести логику в FarmLiaison).
Дата разведки: 2026-07-14.

---

## 1. Что это
Каталог вакансий Испании из **SEPE / Sistema Nacional de Empleo** (гос. служба занятости, портал «Empléate»).
Сейчас — **репетиция на провинции Астурия** (все секторы, ~600 вакансий). Расширяемо на всю Испанию.

Источник: `https://www.sistemanacionalempleo.es/OfertaDifusionWEB/`

---

## 2. Реверс-инжиниринг портала (главное)

Портал — **старый Struts** (`.do`), **stateful**, кодировка **ISO-8859-1** (не UTF-8!). Форма/выдача — HTML (не JSON, API нет).

### Поток (flow)
```
1. GET  busquedaOfertas.do?modo=continuar          → куки сессии + idFlujo (в <input name="idFlujo">)
2. GET  busquedaOfertas.do?modo=cambiarModo&idFlujo=<idf>   → переключение в «расширенный поиск»
3. POST busquedaOfertas.do?modo=continuar          → страница выдачи (стр.1) + «Total de páginas: N»
4. GET  listadoOfertas.do?modo=pagina&idFlujo=<idf>&indice=<off>   → страницы 2..N
5. GET  detalleOferta.do?modo=inicio&id=<ID>&ret=B → детальная вакансии
```

### `idFlujo` — токен потока
- Приходит в форме (`<input name="idFlujo" value="...">`) и в куке `JSESSIONID_empleo_cl`.
- **Привязан к сессии.** Нужен во ВСЕХ последующих запросах (поиск, пагинация, детальная).
- Реюзать между независимыми сессиями нельзя — брать свежий с GET формы.

### Параметры POST-поиска (form `busquedaOfertasForm`)
| Параметр | Значение |
|---|---|
| `idFlujo` | из формы |
| `palabraBusqueda` | ключевое слово (или пусто) |
| `sectorProfesional` | код сектора (см. ниже) или пусто |
| `provincia` | код провинции INE (`33`=Asturias) или пусто |
| `municipio` | код municipio (AJAX-подгружается по провинции; можно не задавать и фильтровать по тексту) |
| `area` | `/es` (язык) |
| `diaINI/mesINI/anioINI`, `diaFIN/mesFIN/anioFIN` | диапазон дат (можно пусто) |
| `salarioCuantia` | пусто |
| `botonNavegacion` | `Enviar` |

### Коды сектора (`sectorProfesional`)
29 опций. Агро-релевантные:
- **`AA` = AGRARIO** ← главный агро-сектор (~360 вакансий по Испании)
- `PA` = PESCA Y ACUICULTURA
- `IA` = INDUSTRIAS ALIMENTARIAS
Полный список — в HTML расширенной формы (`<select name='sectorProfesional'>`, одинарные кавычки!).

### Провинции (`provincia`) — коды INE
54 опции. `33`=ASTURIAS, `15`=A CORUÑA, и т.д. Полный список — `<select name="provincia">` в расширенной форме.

### Пагинация
- **40 вакансий на страницу**, параметр `indice` = offset: 1, 41, 81, 121…
- Число страниц — текст **«Total de páginas: N»** на странице выдачи.
- Ссылки: `listadoOfertas.do?modo=pagina&idFlujo=<idf>&indice=<off>`.

### Парсинг строки выдачи
Строка = `Дата(dd/mm/yyyy) | <a ...detalleOferta.do?id=NNN...>Заголовок</a> | Municipio | (Provincia)`.
- **ID оферты** — числовой (напр. `032026004779`), **первые 2 цифры = код провинции SEPE**. Стабильный `externalId`/дедуп-ключ.
- **Заголовок** — стандартизированное название занятия SEPE + суффикс `(ref.: NNNN)` / «N puestos de …» (нормализовать перед переводом/дедупом — см. `norm()` в `build_catalog.py`).
- **Локация** = `municipio (provincia)`. Координат нет → геокодить.

### Детальная страница (`detalleOferta.do?id=…&ret=B`)
Содержит: описание, **Requisitos** (требования), **Datos de contacto** (email/телефон для отклика), число мест.
⚠️ **ОТКРЫТЫЙ ВОПРОС:** работает ли этот URL как публичный permalink БЕЗ сессии. 2026-07-14 холодный заход отдавал 8KB error-заглушку (`.aviso` красным) — НО в тот момент **наш IP был заблокирован WAF** (см. §4), так что тест недостоверен. **Проверить заново с чистого IP.** Если permalink не работает без сессии — план Б: **втягивать описание+контакт в наш каталог** во время краула (пока держим idFlujo).

---

## 3. Данные (снимок 2026-07)
- **Астурия (provincia=33), все секторы:** ~600 вакансий (15 стр.). 100% с локацией, 55 municipios (Gijón 114, Oviedo 62, Siero 56…).
- **Сектор AGRARIO (AA) по Испании:** ~360 (9 стр.).
- **Все секторы, вся Испания:** ~12 436 (≈310 стр.).
- Кого ищут в Астурии (топ): сиделки за пожилыми (gerocultor), уборщики, повара, официанты, медсёстры, каменщики, горничные, грузчики. Сервисная экономика стареющего региона.

### Геокодинг
`municipio + provincia + ", España"` → **Nominatim** (`nominatim.openstreetmap.org/search?format=json&countrycodes=es`).
- 100% попаданий на тесте. Лимит **1 req/сек**, обязателен `User-Agent`.
- **Кэшировать по городу навсегда** (~1–2k уникальных городов на всю Испанию → геокодим один раз).

---

## 4. Анти-бан / WAF ⚠️ КРИТИЧНО
- Перед SEPE стоит **F5 BIG-IP ASM (WAF)** — куки `TS0114a3a3`.
- `robots.txt` — без `Disallow` (только sitemap).
- **Вежливый темп проходит** (проверено): серии запросов с паузами 2–4.5с → 200, без блока.
- **НО: агрессия банит IP.** 2026-07-14 после дня тестов+краулов **наш домашний IP словил временный блок** (детальные страницы стали отдавать 8KB error; с мобильного/другого IP — открывалось). Кулдаун снимается сам за минуты–часы.
- **Правила краула:** одна сессия, строго последовательно, пауза **3–4.5с + джиттер**, реалистичный UA+Referer, **stop-on-block** (маркеры: `request rejected/access denied/support id` + резкое падение размера ответа), экспоненциальный бэкофф, резюмируемость, **раз в сутки ночью**.
- GitHub Actions-раннер: первый краул прошёл (IP GitHub не забанен). Но при расширении на всю Испанию (~310 стр.) риск выше — дробить/растягивать.

---

## 5. Пайплайн (файлы репо)
```
scrape_asturias.py   краул провинции 33 → asturias_offers.json  (защита MIN_OK=100: не затирать хорошие данные пустым сбором)
translate.py         ES→RU для НОВЫХ занятий через deep-translator (Google), кэш в translations.json (ручные переводы — основа)
build_catalog.py     → index.html (поиск+фильтр по городу) + catalog.csv + offers/<municipio>/*.md
.github/workflows/crawl.yml   cron '0 1 * * *' (~03:00 Мадрид) + workflow_dispatch; коммитит свежие данные обратно (rebase+retry)
```
Локально: `pip install -r requirements.txt && python scrape_asturias.py && python translate.py && python build_catalog.py`.
Pages: Settings → Pages → Deploy from branch → `main` / root. Сайт: `https://realbuddy.github.io/sepe-jobs/`.

---

## 6. Roadmap / что дальше
1. **Проверить permalink детальной с чистого IP** (§2). Если не работает без сессии → ингест описания+контакта в каталог.
2. **Расширение на всю Испанию:** убрать фильтр `provincia` (весь набор) ИЛИ цикл по 52 провинциям (аккуратнее к WAF: по провинции меньше страниц за сессию). Переименовать `scrape_asturias.py`→общий, параметризовать провинцией/сектором.
3. **Геокодинг + карта** (если нужен визуальный слой; данные уже 100% геокодируемы).
4. **Перенос в FarmLiaison** (основная цель): агро-фильтр `sectorProfesional=AA`, схема `Job` (nullable farmId + lat/lng/location/externalId/source/sourceUrl), авто-публикация, mark-and-sweep протухших. См. `docs/brainstorms/2026-07-07-quehayhoy-event-import-requirements.md` в основном репо как образец конвейера (зеркалим event-import).

---

## 7. Полезные факты
- Кодировка запросов/ответов — **ISO-8859-1** (`urllib.parse.quote(..., encoding='iso-8859-1')`, декодировать `.decode('iso-8859-1')`).
- Селекты в форме — местами **одинарные кавычки** (`name='sectorProfesional'`): regex должен ловить и `'` и `"`.
- Заголовки — стандартизированные занятия SEPE (близко к CNO). Хороши для дедупа/перевода после `norm()`.
