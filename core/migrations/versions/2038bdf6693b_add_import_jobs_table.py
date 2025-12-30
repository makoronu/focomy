"""add import_jobs table

Revision ID: 2038bdf6693b
Revises:
Create Date: 2025-12-30 09:44:29.008620
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '2038bdf6693b'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('import_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('source_url', sa.String(length=500), nullable=True),
        sa.Column('source_file', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('phase', sa.String(length=20), nullable=False),
        sa.Column('progress_current', sa.Integer(), nullable=False),
        sa.Column('progress_total', sa.Integer(), nullable=False),
        sa.Column('progress_message', sa.Text(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('analysis', sa.JSON(), nullable=True),
        sa.Column('posts_imported', sa.Integer(), nullable=False),
        sa.Column('pages_imported', sa.Integer(), nullable=False),
        sa.Column('media_imported', sa.Integer(), nullable=False),
        sa.Column('categories_imported', sa.Integer(), nullable=False),
        sa.Column('tags_imported', sa.Integer(), nullable=False),
        sa.Column('authors_imported', sa.Integer(), nullable=False),
        sa.Column('menus_imported', sa.Integer(), nullable=False),
        sa.Column('redirects_generated', sa.Integer(), nullable=False),
        sa.Column('errors', sa.JSON(), nullable=True),
        sa.Column('warnings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_import_jobs_status', 'import_jobs', ['status'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_import_jobs_status', table_name='import_jobs')
    op.drop_table('import_jobs')
