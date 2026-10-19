# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# Проект BrickIndex (AI-каталог LEGO)

Источник правды — `LEGO.md` (ТЗ + исследование + спринты в прил. А). Работаем строго по одному спринту, только рекомендованные в LEGO.md решения (путь D: retrieval-first).

## Архитектура (LEGO.md §6)

Два слоя, оба обязательны:
1. **Retrieval-идентичность:** фото → сегментация (SAM 3.1) → кроп → эмбеддинг DINOv3 → FAISS по multi-view-рендерам LDraw → `part_num`.
2. **Слой атрибутов:** `part_num` → {holes, pins, axle, shape…}. Rebrickable геометрию НЕ хранит — атрибуты строим сами (парсинг имён + LDraw-геометрия + курирование), начиная с Technic-подмножества.

Цвет определяется после идентичности: LAB + баланс белого, ограничение множеством цветов из `elements` (part × color).

Компоненты: Android-клиент (Kotlin/Compose/Room, офлайн-каталог) → FastAPI-сервер (инференс) → Postgres (каталог + атрибуты). Офлайн-конвейер: LDraw → Blender-рендер → эмбеддинги → FAISS-индекс.

## Стек

- Python 3.13, venv в `venv/`; зависимости — `requirements.txt` (блоки раскомментируются по спринтам).
- PostgreSQL 16 (Homebrew, запущен как сервис), БД `brickindex`, подключение локальным пользователем без пароля: `dbname=brickindex`.
- Позже: PyTorch, HF Transformers ≥4.56 / timm ≥1.0.20 (DINOv3), Ultralytics ≥8.3.237 (SAM 3), FAISS, OpenCV, Blender+ImportLDraw.

## Структура

```
LEGO.md                     ТЗ (источник правды)
requirements.txt            зависимости по спринтам
db/schema.sql               справочник каталога (идемпотентный DDL)
scripts/import_catalog.py   скачивание + идемпотентный импорт дампов Rebrickable
scripts/verify_import.py    тесты Спринта 0 (счётчики, FK, выборка с картинками)
scripts/render.py           CLI multi-view рендера эталонов (Спринт 1)
scripts/blender_render.py   исполняется внутри headless Blender (не запускать напрямую)
data/raw/*.csv.gz           дампы Rebrickable (не коммитить)
data/ldraw/                 библиотека LDraw (parts/*.dat, 24.3k деталей)
data/renders/<part>/        PNG-эталоны: <part>_v<NN>.png
```

## Факты о данных Rebrickable (выяснено аудитом Спринта 0)

- Дампы: `parts` (63.5k), `colors` (275, поля id,name,rgb,is_trans,num_parts,num_sets,y1,y2), `part_categories` (76), `elements` (112.5k), `part_relationships` (36.7k), `inventory_parts` (1.5M). Ссылочная целостность дампов чистая (0 сирот).
- **`part_external_ids` в CSV-дампах НЕТ** — внешние ID (BrickLink/LDraw) доступны только через API v3 (~1 req/sec). Понадобится для Спринта 1 (ldraw_id); часто `part_num` совпадает с LDraw-именем файла.
- Отдельного файла картинок нет: `part_images` строится из `inventory_parts.img_url` (первый непустой URL на part × color, ~96k пар).
- `elements.design_id` пуст у ~19% строк; `rel_type`: A=alternate, B=sub-part, M=mold, P=print, R=pair, T=pattern.
- Импорт идемпотентен через upsert; строки, исчезнувшие из дампа, не удаляются (на них будет ссылаться коллекция пользователя).

## Рендер эталонов (выяснено аудитом Спринта 1)

- Blender 5.1.2 (brew cask, бинарь `blender`), headless: `--background --factory-startup`.
- Аддон импорта LDraw: `cuddlyogre/ExportLdraw` (v25.4.1103) установлен в
  `~/Library/Application Support/Blender/5.1/scripts/addons/ExportLdraw`;
  на офиц. платформе расширений Blender LDraw-импортёра нет. Оператор:
  `bpy.ops.ldraw_exporter.import_operator(filepath=..., ldraw_path=...)`.
  Ошибка `ImportOptions.json not found` в логе — безвредна (нет дефолт-конфига).
- Материал детали в аддоне: RGB-узел "Color" → группа "LEGO Standard"
  (не Principled BSDF) — цвет меняется через `node.outputs[0].default_value`.
- Модель детали: `data/ldraw/parts/<part_num>.dat` — для большинства деталей
  part_num = имя LDraw-файла; исключения потребуют маппинга через API.
- Параметры по умолчанию: 24 ракурса (спираль Фибоначчи по всей сфере),
  512×512, Cycles 16 сэмплов + denoise (GPU Metal), вариативный свет/фон/цвет
  пластика, сид = part_num (воспроизводимо). ~1–2 с/кадр, ~50–55 с/деталь.
- Камера: per-view фит `camera_fit_coords` по проекции bbox (ПАТЧ п.1) —
  деталь занимает стабильную долю кадра независимо от вытянутости.
  Это дало +4 п.п. Recall@1 против фита по ограничивающей сфере.
- Рендер GPU-bound: параллельные инстансы Blender на M1 суммарно МЕДЛЕННЕЕ
  одного (21 кадр/мин на 3 воркерах против ~29 на одном). Рендерить в 1 поток.
- Убивать Blender: `pkill -f "Blender --background"` — с ЗАГЛАВНОЙ B
  (строчная матчится только на путь скрипта blender_render.py).
- `data/ldraw_complete.zip` (136 МБ) — исходный архив, можно удалить.

## Retrieval (выяснено аудитом Спринта 2)

- Эмбеддер: **DINOv2-base** (`facebook/dinov2-base`, Apache-2.0). DINOv3 на HF
  gated (401 без токена) — фолбэк по LEGO.md Прил. Б.1. Переключение на DINOv3:
  `export BRICKINDEX_MODEL=facebook/dinov3-vitb16-pretrain-lvd1689m` + HF-токен
  с принятой лицензией, затем пересборка индекса.
- Вектор: pooler_output (CLS), L2-нормирован; метрика cosine = IndexFlatIP.
  Multi-view: все 24 ракурса в индексе, агрегация при поиске — max по ракурсам.
- **macOS-ловушка:** faiss-cpu и torch несут каждый свой libomp → тихий segfault
  или OMP Error #15. Решение в `scripts/retrieval.py`: KMP_DUPLICATE_LIB_OK=TRUE
  + импорт torch строго ДО faiss. В entry-скриптах faiss напрямую не импортировать
  (использовать `retrieval.new_index`).
- transformers 5.x требует torchvision для AutoImageProcessor.
- Индекс: `data/index/` (index.faiss + labels.json c model id). Наполнение —
  топ-100 частотных Technic-деталей (`data/index_parts.txt`), ~55 c/деталь рендера.
- Валидация: `data/val_real/<part_num>.jpg` — 98 реальных фото Rebrickable
  (elements/photos URL; /ldraw/ исключены как синтетика). Метрики на них:
  **Recall@5 = 96.9%** (цель ≥90% — достигнута), Recall@1 = 45.9% (цель ≥75% —
  ожидаемо до few-shot калибровки и re-ranking, этап 4 дорожной карты).
  Промахи top-1 — внутри кластеров похожих (оси/пины/балки соседних длин).
- Фото своих деталей пользователя для честной валидации ещё не снимались
  (Прил. Б.5) — понадобятся к этапу калибровки.

## Сегментация (выяснено аудитом Спринта 3)

- **SAM 3 gated на HF** (401, как DINOv3) -> используется **SAM 2.1 base**
  (`sam2.1_b.pt`, свободные веса Ultralytics, лежит в корне проекта).
  Переключение: `BRICKINDEX_SAM=sam3.pt` + HF-токен, тогда доступен текстовый
  промпт «lego piece» (SAM3SemanticPredictor уже есть в ultralytics 8.4.92).
- **Everything-режим SAM на раскладке ненадёжен**: выдаёт фрагменты деталей
  вместо целых, результат зависит от фона; плотнее сетка точек/мягче пороги
  делают ХУЖЕ. Рабочая схема в `scripts/segmentation.py`: порог от цвета фона
  -> морфология -> связные компоненты -> слияние пересекающихся боксов ->
  боксы как **box-промпты** в SAM -> точные маски. Требует контрастного фона
  (это и так требование UX, §7 шаг 1). Фолбэк на everything-режим, если фон
  не выделился. ~2 с на раскладку 1536×1152 (CPU M1).
- Параметры everything-режима (points_stride и пр.) прокидываются только
  через `SAM2Predictor(overrides=...)` напрямую, не через `SAM()(...)`.
- Тестовые раскладки: `scripts/make_test_layout.py` (композит из рендеров,
  хромакей по углу фона) -> `data/val_seg/layout10.png`; на реальных фото
  раскладок ещё не проверялось.

## Команды

```
venv/bin/python scripts/import_catalog.py --download   # скачать дампы + импорт
venv/bin/python scripts/verify_import.py               # тесты Спринта 0
venv/bin/python scripts/render.py --part 32524 --views 24 --out data/renders
venv/bin/python scripts/build_index.py                 # рендеры -> FAISS
venv/bin/python scripts/search.py photo.jpg --k 5      # CLI-поиск
venv/bin/uvicorn app:app --app-dir scripts --port 8000 # /identify, /segment, /health
venv/bin/python scripts/eval_real.py --val data/val_real  # Recall@1/@5 на реальных фото
venv/bin/python scripts/make_test_layout.py --n 10     # тестовая раскладка
venv/bin/python scripts/fill_attributes.py             # атрибуты Technic (имена+LDraw+curated)
venv/bin/python scripts/verify_attributes.py           # сверка с эталоном 30 деталей
venv/bin/python scripts/eval_color.py                  # точность цвета (val_color)
```

## Метрики ядра (98 реальных фото, `eval_real.py`)

Итоговая таблица «100 vs 623 деталей» (R@1 / R@5, %; rr = rerank 0.05):

| Конфигурация | индекс 100 | индекс 623 (полный Technic) |
|---|---|---|
| DINOv2 max | 50.0 / 96.9 | 37.8 / 85.7 |
| DINOv2 vote | 59.2 / 96.9 | 27.6 / 85.7 |
| DINOv2 vote+rr | 61.2 / 98.0 | 28.6 / 87.8 |
| DINOv2 max+rr | — | 42.9 / 84.7 |
| DINOv3 max | 58.2 / 95.9 | 44.9 / 89.8 |
| **DINOv3 max+rr** | — | **48.0 / 92.9** ✓ цель R@5>=90 |

Выводы (важно, дорого добыты):
- **Метрики на малом индексе ЛЬСТЯТ** (п.2 патча подтверждён): R@5 96.9 -> 85.7
  при том же пайплайне. Порог готовности проверять только на полном индексе.
- **vote рушится на большом индексе** (27.6): популярные формы заливают
  голосование. max устойчивее к масштабу. Агрегация × модель × размер
  индекса взаимодействуют — перемерять при каждом изменении.
- **DINOv3 выигрывает на полном индексе** (+7 п.п. R@1, +5 R@5 против DINOv2).
- Боевая конфигурация: DINOv3 + agg=max (env BRICKINDEX_AGG) + rerank 0.05;
  боевой индекс data/index = копия data/index_full_dinov3.
- До фикса камеры (DINOv2, max, 100): 45.9 / 96.9 -> фикс камеры дал +4.1 R@1.
- DINOv3 требует HF_TOKEN из `.env` (Read-токен; fine-grained без галочки
  gated repos даёт 403). `export $(grep -v '^#' .env | xargs)` перед запуском.
- П.3 патча: своп подтверждён — Спринт 5 (атрибуты + re-ranking) выполнен
  до Спринта 4 (цвет); few-shot позже по накопленным confirmations.

## macOS: faiss + torch (двойной libomp)

Симптомы: тихий segfault (exit 139) или OMP Error #15, причём может
проявиться только на большом индексе. Полное решение — один OpenMP-рантайм:
`faiss/.dylibs/libomp.dylib` заменён симлинком на `torch/lib/libomp.dylib`
(оригинал сохранён как libomp.dylib.bak). ВНИМАНИЕ: переустановка faiss-cpu
(`pip install --force ...`) вернёт дубликат — повторить симлинк.
KMP_DUPLICATE_LIB_OK и порядок импорта (torch до faiss) в retrieval.py
оставлены как второй эшелон защиты.

## Атрибутный слой (выяснено в Спринте 5)

- `part_attributes`: 964 Technic-строки (623 с LDraw-геометрией). Заполнение:
  `fill_attributes.py` = имена (`name_attrs.py`) + LDraw (`ldraw_geom.py`) +
  курирование (`data/attr_curated.csv`, source='curated' не перезаписывается).
- **Габариты из LDraw надёжны** (bbox по вершинам, 1 стад = 20 LDU, оси
  сортированы по убыванию). Точность на эталоне 30 деталей: 153/153 полей.
- **Отверстия: LDraw-примитивы неконсистентны между авторами файлов**
  (`beamhole`=отверстие+сосед-негатив, `peghole`=половинка торца,
  `npeghole`=«Peg Hole Negative» — это ПИНОВОЕ отверстие, НЕ крестовое).
  Правило: балки — из имени (1xN -> N; AxB гнутая -> A+B-1 минус крестовые),
  кирпичи — peghole/2, прочее — LDraw+имя. Крестовые: имя приоритетно,
  `axl?ho*`-примитивы — только бинарный сигнал.
- При курировании СНАЧАЛА смотреть рендер детали (я сам ошибся с 43857 —
  у неё 2 пиновых, а не пин+крест).
- Тест: `verify_attributes.py` против `data/attr_ground_truth.csv`.
- **Геометрический re-ranking работает как tie-breaker**: голоса первичны,
  штраф |log(aspect_фото / aspect_LDraw)| решает при равных голосах.
  Пере-сортировка по штрафованному сходству ЛОМАЕТ vote (проверено).
  Боевая конфигурация /identify: agg=vote + rerank w=0.05.

## Цвет (выяснено в Спринте 4)

- `scripts/color_id.py`: маска порогом от фона -> баланс белого по фону
  (фон = эталон; в мобильном UX — карточка в кадре) -> медиана пикселей
  **50–90 перцентиля светлоты** (вся маска утягивает в тень, топ — в блик)
  -> LAB с пониженным весом L (0.4) -> ближайший цвет, ограниченный
  цветами детали из `elements`.
- Метрики на 42 реальных фото известных цветов (`data/val_color/`,
  имя файла `<part>__<color_id>.jpg`, `eval_color.py`):
  **top-1 67%, top-3 86%; без ограничения по elements — 5%** (ограничение
  = главный буст, подтверждено §9). Средняя Technic-деталь = 7.7 цветов.
- Промахи top-1 — почти все «трудные пары» (Dark Gray↔Dark Bluish Gray
  d=3.2, Black↔Trans-Black, White↔Light Bluish Gray) -> в /identify флаг
  `color_needs_confirmation` (отрыв top-2 < 5 или дистанция > 25).
- Оговорка: валидация на студийных миниатюрах Rebrickable (~192px, JPEG);
  на фото пользователя с белой карточкой ожидается лучше.

## ПАТЧ К ТЗ (после Спринта 3) — выполнен

1. `collection` на момент патча не существовала (Спринт 0 делал только
   справочник) — создана сразу с `user_id int NOT NULL DEFAULT 1` + индекс.
   Каталог (parts/colors/elements/...) остаётся user-agnostic.
2. `confirmations` создана по спецификации патча (+ FK на parts/colors,
   индекс по user_id). Это накопительный few-shot-набор: писать при каждом
   подтверждении top-K; отдельной фотосессии для калибровки НЕ планировать.
3. Аудит валидации: Recall Спринта 2 измерялся на РЕАЛЬНЫХ фото (98 шт.,
   Rebrickable elements/photos; /ldraw/ исключены) — метрика действительна.
   Скрипт переименован: `eval_recall.py` -> `eval_real.py`. Рендеры в
   валидацию не класть. Оговорка: фото студийные, не «полевые».
4. Бэклог Спринта 6: экран «О приложении» со строкой о модели эмбеддера
   (переключились на DINOv3 ViT-B/16 — `AboutScreen.kt` обновлён, было DINOv2)
   + дисклеймер «не связано с LEGO Group, LEGO® — товарный знак».

## Android MVP (выяснено в Спринте 6)

- Проект `android/` (Kotlin/Compose, Room, minSdk 26 / compileSdk 35). 4 экрана:
  Скан (CameraX -> `/identify` -> выбор кандидата -> в коллекцию + очередь
  `/confirm`), Коллекция (Room — локальный источник правды), Поиск
  (параметрический по атрибутам, ОФЛАЙН из assets), Инфо (адрес сервера +
  дисклеймер LEGO®). Клиент API — OkHttp.
- Каталог на устройстве — read-only снапшот `app/src/main/assets/catalog.db`
  (SQLite), генерит `scripts/export_catalog_snapshot.py`; схемы таблиц
  catalog_part/catalog_color/part_attr обязаны совпадать с Room 1:1.
- **Сборка требует JDK 21 (JBR из Android Studio), НЕ Homebrew openjdk 26**
  (тот несовместим с Gradle 8.11 — макс. JDK 23). `gradlew` берёт JVM только из
  JAVA_HOME/PATH (свойство `org.gradle.java.home` читается ПОЗЖЕ, для бутстрапа
  не годится) -> `JAVA_HOME` прописан в `~/.zshenv`; `org.gradle.java.home` в
  `android/gradle.properties` дополнительно пиннит JDK демона на JBR 21.
  Команда: `cd android && ./gradlew assembleDebug` -> app-debug.apk (~19 МБ).
- **Строку эмбеддера в `AboutScreen.kt` держать синхронной с `/health.model`**
  (сейчас DINOv3 ViT-B/16). Единого источника правды нет — при смене модели
  править вручную.
- Серверная приёмка пройдена вживую: /health, /identify (top-5), /confirm
  (пишет строку в confirmations + кроп), /segment (10/10 на layout10).
- НЕ проверено (headless нельзя): on-device сценарий «фото -> подтвердил ->
  нашёл по фильтрам» (п.1-5 чек-листа) — нужен телефон/эмулятор с app-debug.apk.

## Статус спринтов (LEGO.md прил. А)

- [x] Спринт 0 — данные и каталог (Postgres, импорт, тесты)
- [x] Спринт 1 — офлайн-рендер эталонов (Blender 5.1 + ExportLdraw, render.py)
- [x] Спринт 2 — эмбеддинги и FAISS (DINOv2, /identify; Recall@5=96.9%)
- [x] Спринт 3 — сегментация (SAM 2.1 + box-промпты, /segment; 10/10 на тесте)
- [x] ПАТЧ К ТЗ — collection(+user_id), confirmations, eval_real.py, бэклог
- [x] ПАТЧ (параллельно Спринту 3) — камера, абляция, DINOv3, re-ranking;
      п.2 (полный индекс 623) ждёт фонового рендера
- [x] Спринт 5 (по свопу из патча) — атрибутный слой Technic + re-ranking;
      /identify: R@1 61.2 / R@5 98.0 (было 45.9 / 96.9)
- [x] Спринт 4 — цвет (color_id.py, /identify: color + needs_confirmation;
      top-1 67% / top-3 86% на 42 фото, ограничение по elements = буст 13x)
- [~] Спринт 6 — Android MVP — код собран (4 экрана Compose, Room, клиент API),
      debug-APK актуален; серверная приёмка пройдена (/identify, /confirm,
      /segment, /health). Остаётся on-device прогон сценария (см. «Android MVP»)
