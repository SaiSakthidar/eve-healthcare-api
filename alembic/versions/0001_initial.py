"""initial schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(255), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("email"))
    op.create_table("diagnostic_centres", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("location", sa.String(255), nullable=False))
    op.create_table("diagnostic_tests", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.UniqueConstraint("name"))
    op.create_table("centre_tests", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("centre_id", sa.Integer(), sa.ForeignKey("diagnostic_centres.id"), nullable=False), sa.Column("test_id", sa.Integer(), sa.ForeignKey("diagnostic_tests.id"), nullable=False), sa.Column("price", sa.Numeric(10, 2), nullable=False), sa.UniqueConstraint("centre_id", "test_id"))
    op.create_table("bookings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("centre_test_id", sa.Integer(), sa.ForeignKey("centre_tests.id"), nullable=False), sa.Column("appointment_at", sa.DateTime(timezone=True), nullable=False), sa.Column("amount", sa.Numeric(10, 2), nullable=False), sa.Column("status", sa.String(20), nullable=False))
    op.create_table("payments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False), sa.Column("provider_reference", sa.String(255), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("amount", sa.Numeric(10, 2), nullable=False), sa.UniqueConstraint("provider_reference"))
    op.create_table("payment_webhook_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_id", sa.String(255), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("event_id"))


def downgrade():
    for table in ("payment_webhook_events", "payments", "bookings", "centre_tests", "diagnostic_tests", "diagnostic_centres", "users"):
        op.drop_table(table)

