"""Safe JSON replay for pinned task-scoped campaigns (CS-0603)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0021_optimization_campaigns"
down_revision: str | None = "0020_dataset_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_campaigns",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_revision_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("definition", pg.JSONB(), nullable=False),
        sa.Column("spec_digest", sa.String(64), nullable=False),
        sa.Column("replay", pg.JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("creation_key", sa.String(100), nullable=False),
        sa.Column("commands", pg.JSONB(), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id", "task_id"], ["research_tasks.workspace_id", "research_tasks.id"], name="fk_optimization_scope_task"),
        sa.ForeignKeyConstraint(["contract_revision_id"], ["success_contract_revisions.id"], name="fk_optimization_contract"),
        sa.UniqueConstraint("workspace_id", "task_id", "creation_key", name="uq_optimization_creation"),
        sa.CheckConstraint("revision > 0", name="optimization_revision"),
    )
    op.create_index("ix_optimization_campaigns_workspace_id", "optimization_campaigns", ["workspace_id"])
    op.create_index("ix_optimization_task", "optimization_campaigns", ["workspace_id", "task_id", "created_at", "id"])
    op.execute("""
    CREATE FUNCTION protect_optimization_definition() RETURNS trigger AS $$
    BEGIN
      IF ROW(NEW.workspace_id, NEW.task_id, NEW.contract_revision_id, NEW.definition,
             NEW.spec_digest, NEW.creation_key, NEW.created_by)
         IS DISTINCT FROM ROW(OLD.workspace_id, OLD.task_id, OLD.contract_revision_id,
             OLD.definition, OLD.spec_digest, OLD.creation_key, OLD.created_by) THEN
        RAISE EXCEPTION 'optimization campaign definition is immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER optimization_definition_immutable BEFORE UPDATE ON optimization_campaigns
      FOR EACH ROW EXECUTE FUNCTION protect_optimization_definition();
    """)


def downgrade() -> None:
    op.drop_table("optimization_campaigns")
    op.execute("DROP FUNCTION protect_optimization_definition()")
