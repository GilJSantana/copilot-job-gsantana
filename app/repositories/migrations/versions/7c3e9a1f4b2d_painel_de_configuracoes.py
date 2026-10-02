"""painel de configuracoes: system_configs, profile_core e prompt_templates

Revision ID: 7c3e9a1f4b2d
Revises: 52be32dd6b3b
Create Date: 2026-10-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3e9a1f4b2d'
down_revision: Union[str, Sequence[str], None] = '52be32dd6b3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('system_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_configs')),
    sa.UniqueConstraint('key', name=op.f('uq_system_configs_key'))
    )
    op.create_table('profile_core',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_core'))
    )
    with op.batch_alter_table('profile_core', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profile_core_category'), ['category'], unique=False)

    op.create_table('prompt_templates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('template_text', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prompt_templates')),
    sa.UniqueConstraint('name', name=op.f('uq_prompt_templates_name'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('prompt_templates')
    with op.batch_alter_table('profile_core', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profile_core_category'))

    op.drop_table('profile_core')
    op.drop_table('system_configs')
