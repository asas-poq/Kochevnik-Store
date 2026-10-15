-- Схема БД. SQLite сейчас, переносится на PostgreSQL почти без изменений
-- (INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL/BIGSERIAL, TEXT -> TIMESTAMPTZ для дат).
--
-- Принципы, чтобы структуру не приходилось менять:
--  1. source_id везде: завтра добавите второго конкурента без новых таблиц.
--  2. Всё, что не знаем заранее (замеры, уход, странные поля) -> product_attributes (key/value)
--     и products.raw_json, а не новые колонки.
--  3. Цена в отдельной таблице с историей, а не колонкой в товаре.
--  4. Размеры, картинки, материалы - отдельные таблицы (связь 1:N).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    base_url  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id  INTEGER NOT NULL REFERENCES sources(id),
    slug       TEXT NOT NULL,
    name       TEXT,
    url        TEXT,
    parent_id  INTEGER REFERENCES categories(id),
    UNIQUE (source_id, slug)
);

-- Одна строка = одна страница товара конкурента (у них это "модель в одном цвете").
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL REFERENCES sources(id),
    slug          TEXT NOT NULL,            -- последняя часть URL, ключ товара
    url           TEXT NOT NULL,
    article       TEXT,                     -- "Арт." у конкурента
    name          TEXT,
    brand         TEXT,
    category_id   INTEGER REFERENCES categories(id),
    color         TEXT,
    color_group   TEXT,                     -- общий ключ для всех цветов одной модели
    composition   TEXT,                     -- "100% пух яка" как есть
    care_text     TEXT,                     -- "Состав и уход"
    measurements  TEXT,                     -- "Замеры изделия" как есть (сырой текст)
    description   TEXT,
    status        TEXT NOT NULL DEFAULT 'active',   -- active / removed
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    content_hash  TEXT,                     -- чтобы видеть, что карточка изменилась
    raw_json      TEXT,                     -- всё, что распарсили, одним JSON
    UNIQUE (source_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_group    ON products(source_id, color_group);
CREATE INDEX IF NOT EXISTS idx_products_article  ON products(article);

CREATE TABLE IF NOT EXISTS product_sizes (
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    size        TEXT NOT NULL,
    in_stock    INTEGER,                    -- 1/0, NULL = не удалось определить
    PRIMARY KEY (product_id, size)
);

CREATE TABLE IF NOT EXISTS product_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    url         TEXT NOT NULL,
    UNIQUE (product_id, url)
);

-- Нормализованный состав: "100% пух яка" -> (пух яка, 100)
CREATE TABLE IF NOT EXISTS product_materials (
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    material    TEXT NOT NULL,
    percent     REAL,
    PRIMARY KEY (product_id, material)
);

-- Универсальные поля: ключ/значение. Новое поле у конкурента = новая строка, а не ALTER TABLE.
CREATE TABLE IF NOT EXISTS product_attributes (
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value       TEXT,
    PRIMARY KEY (product_id, key)
);

-- Ссылки на соседние цвета (как их показывает сайт)
CREATE TABLE IF NOT EXISTS product_color_links (
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sibling_slug TEXT NOT NULL,
    PRIMARY KEY (product_id, sibling_slug)
);

-- Пишем строку только когда цена изменилась.
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price       INTEGER NOT NULL,
    old_price   INTEGER,
    currency    TEXT NOT NULL DEFAULT 'RUB',
    scraped_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_product ON price_history(product_id, scraped_at);

-- Очередь URL для парсинга (позволяет докачивать после обрыва)
CREATE TABLE IF NOT EXISTS crawl_queue (
    source_id    INTEGER NOT NULL REFERENCES sources(id),
    url          TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending / done / error
    error        TEXT,
    updated_at   TEXT,
    PRIMARY KEY (source_id, url)
);
