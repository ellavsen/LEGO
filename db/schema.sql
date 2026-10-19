-- BrickIndex: справочник каталога Rebrickable (LEGO.md §10.1)
-- Read-only справочные таблицы, обновляются импортом CSV-дампов.
-- Применение: psql -d brickindex -f db/schema.sql

CREATE TABLE IF NOT EXISTS part_categories (
    id   integer PRIMARY KEY,
    name text    NOT NULL
);

CREATE TABLE IF NOT EXISTS colors (
    id        integer PRIMARY KEY,          -- включая -1 = [Unknown]
    name      text    NOT NULL,
    rgb_hex   char(6) NOT NULL,
    is_trans  boolean NOT NULL,
    num_parts integer,
    num_sets  integer,
    year_from integer,
    year_to   integer
);

CREATE TABLE IF NOT EXISTS parts (
    part_num      text    PRIMARY KEY,
    name          text    NOT NULL,
    part_cat_id   integer NOT NULL REFERENCES part_categories(id),
    part_material text
);

-- Какие сочетания part × color физически существуют (ограничивает
-- определение цвета в pipeline, LEGO.md §9)
CREATE TABLE IF NOT EXISTS elements (
    element_id text    PRIMARY KEY,
    part_num   text    NOT NULL REFERENCES parts(part_num),
    color_id   integer NOT NULL REFERENCES colors(id),
    design_id  text                          -- пусто у ~19% элементов
);

-- rel_type: A=alternate, B=sub-part, M=mold, P=print, R=pair, T=pattern
CREATE TABLE IF NOT EXISTS part_relationships (
    rel_type        char(1) NOT NULL,
    child_part_num  text    NOT NULL REFERENCES parts(part_num),
    parent_part_num text    NOT NULL REFERENCES parts(part_num),
    PRIMARY KEY (rel_type, child_part_num, parent_part_num)
);

-- Картинки part × color. В дампах нет отдельного файла картинок:
-- URL извлекаются из inventory_parts.csv (первый непустой img_url).
CREATE TABLE IF NOT EXISTS part_images (
    part_num text    NOT NULL REFERENCES parts(part_num),
    color_id integer NOT NULL REFERENCES colors(id),
    img_url  text    NOT NULL,
    PRIMARY KEY (part_num, color_id)
);

CREATE INDEX IF NOT EXISTS idx_parts_cat      ON parts(part_cat_id);
CREATE INDEX IF NOT EXISTS idx_elements_part  ON elements(part_num);
CREATE INDEX IF NOT EXISTS idx_elements_color ON elements(color_id);
CREATE INDEX IF NOT EXISTS idx_rel_parent     ON part_relationships(parent_part_num);

-- Журнал импортов: когда и сколько строк загружено
CREATE TABLE IF NOT EXISTS import_log (
    id          serial PRIMARY KEY,
    table_name  text        NOT NULL,
    row_count   integer     NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

-- Слой атрибутов (Спринт 5, LEGO.md §10.3) — «оборонимый ров».
-- Заполняется автоматически (имена + LDraw-геометрия), правится курированием.
CREATE TABLE IF NOT EXISTS part_attributes (
    part_num         text PRIMARY KEY REFERENCES parts(part_num),
    type             text,        -- beam|beam_thin|brick|axle|pin|gear|connector|panel|bush|...
    length_studs     real,        -- габариты bbox в стадах (сортированы по убыванию)
    width_studs      real,
    height_studs     real,
    hole_count       integer,     -- круглые (пиновые) отверстия
    axle_hole_count  integer,     -- крестовые (осевые) отверстия
    pin_count        integer,     -- штырьки-пины наружу
    stud_count       integer,     -- шипы
    has_axle         boolean,     -- есть осевой стержень
    has_ball_joint   boolean,
    gear_teeth       integer,     -- число зубьев (NULL если не шестерня)
    shape            text,        -- straight|L|T|bent|angled|round|...
    angle_deg        real,
    name_len_a       real,        -- "N x M" из имени (модули, не bbox)
    name_len_b       real,
    source           text NOT NULL DEFAULT 'auto',  -- auto|curated
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attr_type  ON part_attributes(type);
CREATE INDEX IF NOT EXISTS idx_attr_holes ON part_attributes(hole_count);
CREATE INDEX IF NOT EXISTS idx_attr_shape ON part_attributes(shape);

-- ===== Пользовательские данные (ПАТЧ К ТЗ после Спринта 3) =====
-- Каталог выше остаётся общим и user-agnostic; user_id только здесь.

-- Коллекция пользователя (LEGO.md §10.2 + user_id из патча)
CREATE TABLE IF NOT EXISTS collection (
    id               serial  PRIMARY KEY,
    user_id          integer NOT NULL DEFAULT 1,
    part_num         text    NOT NULL REFERENCES parts(part_num),
    color_id         integer NOT NULL REFERENCES colors(id),
    quantity         integer NOT NULL DEFAULT 1,
    location_tag     text,
    added_at         timestamptz NOT NULL DEFAULT now(),
    source_photo_ref text,
    confidence       real,
    verified         boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_collection_user ON collection(user_id);
CREATE INDEX IF NOT EXISTS idx_collection_part ON collection(part_num, color_id);

-- Подтверждения кандидатов top-K: накопительный few-shot-набор для
-- калибровки эмбеддера (отдельной фотосессии не будет — патч, п.2)
CREATE TABLE IF NOT EXISTS confirmations (
    id               serial  PRIMARY KEY,
    user_id          integer NOT NULL DEFAULT 1,
    crop_ref         text    NOT NULL,          -- путь/ключ сохранённого кропа
    candidates       jsonb   NOT NULL,          -- top-K [{part_num, score}, ...]
    chosen_part_num  text    NOT NULL REFERENCES parts(part_num),
    chosen_color_id  integer REFERENCES colors(id),
    was_top1         boolean NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_confirmations_user ON confirmations(user_id);
