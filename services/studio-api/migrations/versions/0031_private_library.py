"""Owner-private notebooks, immutable revisions, resource archive and sourced memory.

Revision ID: 0031_private_library
Revises: 0030_inference_providers
"""

from __future__ import annotations

from alembic import op

revision = "0031_private_library"
down_revision = "0030_inference_providers"
branch_labels = None
depends_on = None


def _tables():  # type: ignore[no-untyped-def]
    # Explicit owned tables only: never create/drop unrelated metadata here.
    from studio.domain.library.models import (
        LibraryFolder,
        LibrarySource,
        Notebook,
        NotebookPage,
        PageRevision,
        ResearchMemory,
    )

    return [
        c.__table__
        for c in (
            LibraryFolder,
            Notebook,
            NotebookPage,
            PageRevision,
            LibrarySource,
            ResearchMemory,
        )
    ]


def upgrade() -> None:
    for table in _tables():
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in reversed(_tables()):
        table.drop(op.get_bind(), checkfirst=True)
