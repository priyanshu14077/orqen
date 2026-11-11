"""Record how many agent steps each test run took.

The live judging view shows steps next to tokens and latency for every test. The
count is not secret, so contestants can read it for hidden tests too.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE judging.test_results
        ADD COLUMN steps integer NOT NULL DEFAULT 0 CHECK (steps >= 0);
    GRANT SELECT (steps) ON judging.test_results TO orqen_contestant;
    """)


def downgrade() -> None:
    op.execute("""
    REVOKE SELECT (steps) ON judging.test_results FROM orqen_contestant;
    ALTER TABLE judging.test_results DROP COLUMN steps;
    """)
