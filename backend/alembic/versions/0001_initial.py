"""Все таблицы, как их создавал create_all до перехода на Alembic

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.String(255), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_sources_id", "sources", ["id"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("default_city", sa.String(120)),
        sa.Column("default_delivery_address", sa.String(500)),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
    )
    op.create_index("ix_categories_id", "categories", ["id"])
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    op.create_table(
        "crawl_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("source_id", "url", name="uq_crawl_queue_source_url"),
    )
    op.create_index("ix_crawl_queue_url", "crawl_queue", ["url"])
    op.create_index("ix_crawl_queue_status", "crawl_queue", ["status"])

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("article", sa.String(64)),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("brand", sa.String(120)),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("color", sa.String(80)),
        sa.Column("color_hex", sa.String(16)),
        sa.Column("color_group", sa.String(255)),
        sa.Column("composition", sa.String(255)),
        sa.Column("density_yarn", sa.String(120)),
        sa.Column("care_text", sa.Text()),
        sa.Column("measurements", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("current_price", sa.Integer(), nullable=False),
        sa.Column("old_price", sa.Integer()),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("likes_count", sa.Integer(), nullable=False),
        sa.Column("reviews_count", sa.Integer(), nullable=False),
        sa.Column("rating_avg", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("first_seen", TS, nullable=False),
        sa.Column("last_seen", TS, nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("raw_json", sa.JSON()),
    )
    op.create_index("ix_products_id", "products", ["id"])
    op.create_index("ix_products_slug", "products", ["slug"], unique=True)
    op.create_index("ix_products_article", "products", ["article"])
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_color", "products", ["color"])
    op.create_index("ix_products_color_group", "products", ["color_group"])
    op.create_index("ix_products_status", "products", ["status"])
    op.create_index("ix_products_category_status", "products", ["category_id", "status"])
    op.create_index("ix_products_current_price", "products", ["current_price"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("old_price", sa.Integer()),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("scraped_at", TS, nullable=False),
    )
    op.create_index("ix_price_history_id", "price_history", ["id"])
    op.create_index("ix_price_history_product_id", "price_history", ["product_id"])

    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
    )
    op.create_index("ix_product_images_id", "product_images", ["id"])
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])

    op.create_table(
        "product_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material", sa.String(100), nullable=False),
        sa.Column("percent", sa.Float(), nullable=False),
    )
    op.create_index("ix_product_materials_product_id", "product_materials", ["product_id"])
    op.create_index("ix_product_materials_material", "product_materials", ["material"])

    op.create_table(
        "product_color_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sibling_slug", sa.String(255), nullable=False),
        sa.UniqueConstraint("product_id", "sibling_slug", name="uq_product_color_sibling"),
    )
    op.create_index("ix_product_color_links_product_id", "product_color_links", ["product_id"])
    op.create_index("ix_product_color_links_sibling_slug", "product_color_links", ["sibling_slug"])

    op.create_table(
        "product_sizes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("size", sa.String(32), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(80)),
        sa.Column("measurements_cm", sa.String(255)),
        sa.UniqueConstraint("product_id", "size", name="uq_product_size"),
    )
    op.create_index("ix_product_sizes_product_id", "product_sizes", ["product_id"])
    op.create_index("ix_product_sizes_size", "product_sizes", ["size"])

    op.create_table(
        "product_attributes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attr_key", sa.String(120), nullable=False),
        sa.Column("attr_value", sa.String(500), nullable=False),
    )
    op.create_index("ix_product_attributes_product_id", "product_attributes", ["product_id"])
    op.create_index("ix_product_attributes_attr_key", "product_attributes", ["attr_key"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("refresh_jti", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip", sa.String(64)),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
    )
    op.create_index("ix_user_sessions_jti", "user_sessions", ["jti"], unique=True)
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("customer_name", sa.String(150), nullable=False),
        sa.Column("customer_phone", sa.String(32), nullable=False),
        sa.Column("customer_email", sa.String(255)),
        sa.Column("delivery_method", sa.String(50), nullable=False),
        sa.Column("delivery_city", sa.String(120), nullable=False),
        sa.Column("delivery_address", sa.String(500), nullable=False),
        sa.Column("cdek_pvz_code", sa.String(64)),
        sa.Column("customer_comment", sa.Text()),
        sa.Column("items_total", sa.Integer(), nullable=False),
        sa.Column("delivery_cost", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payment_id", sa.String(120)),
        sa.Column("payment_url", sa.String(500)),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("paid_at", TS),
    )
    op.create_index("ix_orders_id", "orders", ["id"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_customer_phone", "orders", ["customer_phone"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_payment_id", "orders", ["payment_id"], unique=True)

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("product_sizes.id", ondelete="SET NULL")),
        sa.Column("product_name", sa.String(300), nullable=False),
        sa.Column("product_slug", sa.String(255), nullable=False),
        sa.Column("color", sa.String(80)),
        sa.Column("size", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("subtotal", sa.Integer(), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "order_telegram_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("order_id", "role", name="uq_order_telegram_role"),
    )
    op.create_index("ix_order_telegram_messages_id", "order_telegram_messages", ["id"])
    op.create_index("ix_order_telegram_messages_order_id", "order_telegram_messages", ["order_id"])

    op.create_table(
        "product_likes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("user_id", "product_id", name="uq_user_product_like"),
    )
    op.create_index("ix_product_likes_user_id", "product_likes", ["user_id"])
    op.create_index("ix_product_likes_product_id", "product_likes", ["product_id"])

    op.create_table(
        "product_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("product_reviews.id", ondelete="CASCADE")),
        sa.Column("rating", sa.Integer()),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("advantages", sa.String(500)),
        sa.Column("disadvantages", sa.String(500)),
        sa.Column("is_verified_purchase", sa.Boolean(), nullable=False),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("admin_reply", sa.Text()),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_product_reviews_id", "product_reviews", ["id"])
    op.create_index("ix_product_reviews_product_id", "product_reviews", ["product_id"])
    op.create_index("ix_product_reviews_user_id", "product_reviews", ["user_id"])
    op.create_index(
        "uq_review_user_product_root",
        "product_reviews",
        ["user_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
        sqlite_where=sa.text("parent_id IS NULL"),
    )


def downgrade() -> None:
    for table in (
        "product_reviews", "product_likes", "order_telegram_messages", "order_items", "orders",
        "user_sessions", "product_attributes", "product_sizes", "product_color_links",
        "product_materials", "product_images", "price_history", "products", "crawl_queue",
        "categories", "users", "sources",
    ):  # fmt: skip
        op.drop_table(table)
