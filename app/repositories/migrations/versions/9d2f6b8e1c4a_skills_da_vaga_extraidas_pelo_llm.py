"""skills da vaga extraidas pelo llm

Revision ID: 9d2f6b8e1c4a
Revises: 7c3e9a1f4b2d
Create Date: 2026-11-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d2f6b8e1c4a'
down_revision: Union[str, Sequence[str], None] = '7c3e9a1f4b2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('match_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('job_skills', sa.JSON(), server_default=sa.text("'[]'"), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('match_results', schema=None) as batch_op:
        batch_op.drop_column('job_skills')
