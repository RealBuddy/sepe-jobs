# Вакансии Астурии (SEPE) — авто-каталог

Ежедневно тянет вакансии провинции **Астурия** (все секторы) из [Sistema Nacional de Empleo](https://www.sistemanacionalempleo.es/), переводит профессии на русский и публикует поисковый каталог.

## Что внутри
- **`index.html`** — поисковый каталог (поиск рус/исп + фильтр по городу). Это то, что отдаётся на GitHub Pages.
- **`offers/<город>/<профессия> — <id>.md`** — по файлу на вакансию, сгруппировано по municipio (удобно фильтровать по Gijón и т.п.).
- **`catalog.csv`** — та же выгрузка таблицей.
- **`translations.json`** — кэш переводов ES→RU (ручные + Google). Растёт со временем, новые занятия переводятся один раз.

## Пайплайн (GitHub Actions, `.github/workflows/crawl.yml`)
Раз в сутки ночью (`cron: 0 1 * * *` ≈ 02–03:00 Мадрид) + кнопка ручного запуска:
```
scrape_asturias.py   → asturias_offers.json   (вежливый краул: 1 сессия, троттлинг 3–4.5с, stop-on-block)
translate.py         → дополняет translations.json (Google Translate только для НОВЫХ занятий)
build_catalog.py     → index.html + catalog.csv + offers/
commit + push        → GitHub Pages отдаёт свежий index.html
```

## Одноразовая настройка после первого пуша
1. **Settings → Pages → Build and deployment → Deploy from a branch → `main` / `root`.**
   Каталог будет на `https://<user>.github.io/<repo>/`.
2. Всё. Actions сам обновляет данные ночью; для проверки — вкладка **Actions → Run workflow**.

## Локальный запуск
```bash
pip install -r requirements.txt
python scrape_asturias.py && python translate.py && python build_catalog.py
open index.html
```

## Заметки
- Это **репетиция на Астурии**. Расширить на другие провинции / всю Испанию — убрать/замкнуть фильтр `provincia` в `scrape_asturias.py`.
- Ссылка на вакансию (`detalleOferta.do?id=…&ret=B`) — публичная, работает без сессии, содержит «Datos de contacto» для отклика.
- Данные — публичные вакансии гос-службы занятости Испании; каталог их агрегирует со ссылкой на первоисточник.
