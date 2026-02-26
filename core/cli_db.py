"""CLI database commands - migrate, makemigrations, createuser."""

import asyncio
import os
import sys
from pathlib import Path


def cmd_migrate(args):
    """Run database migrations using Alembic."""
    from alembic.config import Config

    from alembic import command

    # Check if alembic.ini exists, otherwise create programmatic config
    alembic_ini = Path("alembic.ini")
    if alembic_ini.exists():
        alembic_cfg = Config("alembic.ini")
    else:
        # Create programmatic configuration
        alembic_cfg = Config()
        migrations_dir = Path("migrations")
        if not migrations_dir.exists():
            print("Error: No migrations directory found.")
            print("Run 'focomy makemigrations' first to generate migrations.")
            sys.exit(1)
        alembic_cfg.set_main_option("script_location", str(migrations_dir))

        # Get database URL from settings
        from .config import get_settings
        settings = get_settings()
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Show history
    if args.history:
        print("Migration history:")
        command.history(alembic_cfg, verbose=True)
        return

    # Show current revision
    if args.current:
        print("Current revision:")
        command.current(alembic_cfg, verbose=True)
        return

    # Downgrade
    if args.downgrade:
        print(f"Downgrading to {args.revision}...")
        command.downgrade(alembic_cfg, args.revision)
        print("Downgrade complete!")
        return

    # SQL output mode
    if args.sql:
        print(f"Generating SQL for migration to {args.revision}...")
        command.upgrade(alembic_cfg, args.revision, sql=True)
        return

    # Normal upgrade
    print(f"Running migrations to {args.revision}...")
    command.upgrade(alembic_cfg, args.revision)
    print("Migrations complete!")

    # Also create indexes for indexed fields
    async def create_indexes():
        from .database import async_session
        from .services.index import IndexService

        async with async_session() as db:
            index_svc = IndexService(db)
            results = await index_svc.create_indexes_for_all_types()
            if results:
                print("Created indexes:")
                for _type_name, indexes in results.items():
                    for idx in indexes:
                        print(f"  - {idx}")

    asyncio.run(create_indexes())


def cmd_makemigrations(args):
    """Generate a new migration using Alembic."""
    from alembic.config import Config

    from alembic import command

    migrations_dir = Path("migrations")
    alembic_ini = Path("alembic.ini")

    # Initialize Alembic if not exists
    if not migrations_dir.exists():
        print("Initializing Alembic migrations...")
        migrations_dir.mkdir()
        (migrations_dir / "versions").mkdir()

        # Create env.py
        env_py = '''"""Alembic environment configuration."""
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from alembic import context
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Base
from core.config import get_settings

config = context.config
settings = get_settings()

# Set sqlalchemy.url from settings
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    from sqlalchemy import create_engine
    connectable = create_engine(config.get_main_option("sqlalchemy.url"))
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''
        (migrations_dir / "env.py").write_text(env_py)

        # Create script.py.mako
        script_mako = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

def upgrade() -> None:
    ${upgrades if upgrades else "pass"}

def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''
        (migrations_dir / "script.py.mako").write_text(script_mako)
        print("Alembic initialized.")

    # Create programmatic config
    if alembic_ini.exists():
        alembic_cfg = Config("alembic.ini")
    else:
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", str(migrations_dir))

        from .config import get_settings
        settings = get_settings()
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    print(f"Generating migration: {args.message}")

    if args.autogenerate:
        command.revision(alembic_cfg, message=args.message, autogenerate=True)
    else:
        command.revision(alembic_cfg, message=args.message)

    print("Migration created successfully!")


def cmd_createuser(args):
    """Create a new user."""
    import getpass

    # Note: user.yaml is now always loaded from package (core/content_types/user.yaml)
    # No need to check or copy it locally

    email = args.email
    name = args.name
    role = args.role

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Error: Passwords do not match")
            sys.exit(1)

    if len(password) < 12:
        print("Error: Password must be at least 12 characters")
        sys.exit(1)

    print(f"Creating user: {email}")

    async def create_user():
        from .database import async_session, init_db
        from .services.auth import AuthService

        try:
            await init_db()
        except Exception as e:
            print(f"Error: Database initialization failed: {e}")
            sys.exit(1)

        try:
            async with async_session() as db:
                auth_service = AuthService(db)
                user = await auth_service.register(
                    email=email,
                    password=password,
                    name=name,
                    role=role,
                )
                print("\nUser created successfully!")
                print(f"  ID: {user.id}")
                print(f"  Email: {email}")
                print(f"  Name: {name}")
                print(f"  Role: {role}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    asyncio.run(create_user())
