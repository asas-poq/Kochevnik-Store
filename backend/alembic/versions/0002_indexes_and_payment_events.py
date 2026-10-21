"""Индексы под реальные запросы и таблица payment_events для идемпотентных вебхуков

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_orders_user_created", "orders", ["user_id", "created_at"]),
    ("ix_orders_status_created", "orders", ["status", "created_at"]),
    ("ix_order_items_product_id", "order_items", ["product_id"]),
    ("ix_product_reviews_parent_id", "product_reviews", ["parent_id"]),
    ("ix_product_reviews_listing", "product_reviews", ["product_id", "is_approved", "created_at"]),
    ("ix_products_status_first_seen", "products", ["status", "first_seen"]),
    ("ix_crawl_queue_source_status", "crawl_queue", ["source_id", "status"]),
]


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.String(120), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("payment_id", "event", name="uq_payment_event"),
    )
    op.create_index("ix_payment_events_order_id", "payment_events", ["order_id"])
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("payment_events")
