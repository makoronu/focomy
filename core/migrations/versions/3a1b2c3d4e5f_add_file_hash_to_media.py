"""add file_hash to media

Revision ID: 3a1b2c3d4e5f
Revises: 2038bdf6693b
Create Date: 2025-12-30 10:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '3a1b2c3d4e5f'
down_revision: Union[str, None] = '2038bdf6693b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('media', sa.Column('file_hash', sa.String(length=64), nullable=True))
    op.create_index('ix_media_file_hash', 'media', ['file_hash'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_media_file_hash', table_name='media')
    op.drop_column('media', 'file_hash')
