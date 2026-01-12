"""Focomy CLI - Command Line Interface."""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from . import __version__

GITHUB_REPO = "focomy/focomy"
PYPI_PACKAGE = "focomy"


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="focomy",
        description="Focomy - The Most Beautiful CMS",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"Focomy {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new Focomy site")
    init_parser.add_argument("name", help="Site directory name")
    init_parser.add_argument("--template", default="default", help="Template to use")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start development server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    serve_parser.add_argument("--port", "-p", type=int, default=8000, help="Port to bind")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("--revision", "-r", default="head", help="Target revision")
    migrate_parser.add_argument(
        "--sql", action="store_true", help="Output SQL instead of executing"
    )
    migrate_parser.add_argument("--history", action="store_true", help="Show migration history")
    migrate_parser.add_argument("--current", action="store_true", help="Show current revision")
    migrate_parser.add_argument(
        "--downgrade", action="store_true", help="Downgrade instead of upgrade"
    )

    # makemigrations
    makemigrations_parser = subparsers.add_parser("makemigrations", help="Generate new migration")
    makemigrations_parser.add_argument("--message", "-m", required=True, help="Migration message")
    makemigrations_parser.add_argument(
        "--autogenerate", action="store_true", help="Auto-detect schema changes"
    )

    # validate
    subparsers.add_parser("validate", help="Validate content type definitions")

    # update
    update_parser = subparsers.add_parser("update", help="Update Focomy to latest version")
    update_parser.add_argument("--check", action="store_true", help="Check for updates only")
    update_parser.add_argument("--force", action="store_true", help="Force update")
    update_parser.add_argument("--sync", action="store_true", help="Sync missing files from scaffold")

    # build
    build_parser = subparsers.add_parser("build", help="Build static site")
    build_parser.add_argument("--output", "-o", default="dist", help="Output directory")

    # backup
    backup_parser = subparsers.add_parser("backup", help="Backup database and uploads")
    backup_parser.add_argument("--output", "-o", default="backup.zip", help="Output file")
    backup_parser.add_argument("--include-db", action="store_true", help="Include database dump")

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("file", help="Backup file to restore")

    # createuser
    createuser_parser = subparsers.add_parser("createuser", help="Create a new user")
    createuser_parser.add_argument("--email", "-e", required=True, help="User email")
    createuser_parser.add_argument("--name", "-n", default="Admin", help="User name")
    createuser_parser.add_argument(
        "--password", "-p", help="Password (prompted if not provided)"
    )
    createuser_parser.add_argument(
        "--role", "-r", default="admin", choices=["admin", "editor", "author"], help="User role"
    )

    # import (WordPress import)
    import_parser = subparsers.add_parser("import", help="Import from WordPress")
    import_subparsers = import_parser.add_subparsers(dest="import_type", help="Import type")

    # import wordpress (from file)
    wp_file_parser = import_subparsers.add_parser("wordpress", help="Import from WordPress WXR file")
    wp_file_parser.add_argument("file", nargs="?", help="Path to WXR export file")
    wp_file_parser.add_argument("--url", "-u", help="WordPress site URL (for REST API)")
    wp_file_parser.add_argument("--username", help="WordPress username (for REST API)")
    wp_file_parser.add_argument("--password", help="Application Password (for REST API)")
    wp_file_parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't import")
    wp_file_parser.add_argument("--include-media", action="store_true", default=True, help="Download media files")
    wp_file_parser.add_argument("--include-drafts", action="store_true", default=True, help="Include draft posts")
    wp_file_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "migrate":
        cmd_migrate(args)
    elif args.command == "makemigrations":
        cmd_makemigrations(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "restore":
        cmd_restore(args)
    elif args.command == "createuser":
        cmd_createuser(args)
    elif args.command == "import":
        cmd_import(args)
    else:
        parser.print_help()


def _get_scaffold_path() -> Path:
    """Get the path to scaffold directory from package resources."""
    try:
        # Python 3.9+
        scaffold_files = resources.files("core.scaffold")
        return Path(str(scaffold_files))
    except (TypeError, AttributeError):
        # Fallback for older Python or when running from source
        return Path(__file__).parent / "scaffold"


def _copy_scaffold_file(
    scaffold_path: Path,
    target: Path,
    src_name: str,
    dst_name: str | None = None,
    replacements: dict | None = None,
) -> None:
    """Copy a file from scaffold to target, with optional replacements."""
    dst_name = dst_name or src_name
    src_file = scaffold_path / src_name
    dst_file = target / dst_name

    dst_file.parent.mkdir(parents=True, exist_ok=True)

    if src_file.exists():
        content = src_file.read_text()
        if replacements:
            for key, value in replacements.items():
                content = content.replace(f"{{{key}}}", value)
        dst_file.write_text(content)


def _copy_scaffold_dir(scaffold_path: Path, target: Path, src_dir: str) -> None:
    """Copy a directory from scaffold to target."""
    src = scaffold_path / src_dir
    dst = target / src_dir

    if src.exists() and src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def cmd_init(args):
    """Initialize a new Focomy site."""
    name = args.name
    target = Path(name)

    if target.exists():
        print(f"Error: Directory '{name}' already exists.")
        sys.exit(1)

    print(f"Creating new Focomy site: {name}")

    # Get scaffold path
    scaffold_path = _get_scaffold_path()

    # Create directory structure
    target.mkdir(parents=True)
    (target / "uploads").mkdir()
    (target / "static").mkdir()

    # Replacements for templates
    secret_key = os.urandom(32).hex()
    replacements = {
        "site_name": name,
        "secret_key": secret_key,
        "db_name": name,
    }

    # Copy config.yaml from template
    _copy_scaffold_file(scaffold_path, target, "config.yaml.template", "config.yaml", replacements)

    # Copy themes (user customizable)
    _copy_scaffold_dir(scaffold_path, target, "themes")

    # Create plugins directory for user extensions
    (target / "plugins").mkdir()
    (target / "plugins" / ".gitkeep").touch()

    # Note: content_types and relations.yaml are NOT copied
    # They are always loaded from the package (core/content_types/, core/relations.yaml)
    # Users can add custom content_types via plugins/

    # Copy .env from template
    _copy_scaffold_file(scaffold_path, target, ".env.template", ".env", replacements)

    # Copy .gitignore from template
    _copy_scaffold_file(scaffold_path, target, ".gitignore.template", ".gitignore")

    # Create .gitkeep in uploads
    (target / "uploads" / ".gitkeep").touch()

    print(
        f"""
Site created successfully!

Next steps:
  cd {name}
  # Create PostgreSQL database
  createdb {name}
  # Start the server
  focomy serve

Open http://localhost:8000/admin
"""
    )


def cmd_serve(args):
    """Start development server."""
    import uvicorn

    print(f"Starting Focomy on http://{args.host}:{args.port}")
    uvicorn.run(
        "core.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


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


def cmd_validate(args):
    """Validate content type definitions."""
    print("Validating content type definitions...")

    from .services.field import field_service

    errors = []
    content_types = field_service.get_all_content_types()

    for ct in content_types.values():
        print(f"  Checking {ct.name}...")
        # Basic validation
        if not ct.fields:
            errors.append(f"{ct.name}: No fields defined")

        for field in ct.fields:
            if not field.name:
                errors.append(f"{ct.name}: Field missing name")
            if not field.type:
                errors.append(f"{ct.name}.{field.name}: Missing type")

    if errors:
        print("\nValidation errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print(f"\nAll {len(content_types)} content types are valid!")


def cmd_update(args):
    """Update Focomy to latest version."""
    import httpx

    # Handle --sync option
    if args.sync:
        _sync_scaffold_files()
        return

    print("Checking for updates...")

    try:
        # Check PyPI for latest version
        response = httpx.get(f"https://pypi.org/pypi/{PYPI_PACKAGE}/json", timeout=10)
        if response.status_code == 200:
            data = response.json()
            latest_version = data["info"]["version"]

            if latest_version == __version__:
                print(f"You are running the latest version ({__version__})")
                return

            print(f"Current version: {__version__}")
            print(f"Latest version:  {latest_version}")

            if args.check:
                print("\nRun 'focomy update' to update.")
                return

            # Confirm update
            if not args.force:
                confirm = input("\nUpdate now? [y/N] ")
                if confirm.lower() != "y":
                    print("Update cancelled.")
                    return

            # Run pip upgrade
            print("\nUpdating...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", PYPI_PACKAGE],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                print(f"\nSuccessfully updated to {latest_version}!")
                print("Restart your server to apply changes.")
            else:
                print(f"\nUpdate failed: {result.stderr}")
                sys.exit(1)
        else:
            # Fallback to GitHub
            print("Could not check PyPI, checking GitHub...")
            _check_github_release(args)

    except Exception as e:
        print(f"Error checking for updates: {e}")
        sys.exit(1)


def _merge_content_type_fields(scaffold_file: Path, local_file: Path) -> bool:
    """Merge new fields from scaffold content_type into local file.

    Returns True if any fields were added.
    """
    try:
        with open(scaffold_file, encoding="utf-8") as f:
            scaffold_data = yaml.safe_load(f)
        with open(local_file, encoding="utf-8") as f:
            local_data = yaml.safe_load(f)

        if not scaffold_data or not local_data:
            return False

        scaffold_fields = scaffold_data.get("fields", [])
        local_fields = local_data.get("fields", [])

        # Get existing field names
        local_field_names = {f.get("name") for f in local_fields if f.get("name")}

        # Find new fields in scaffold
        new_fields = [
            f for f in scaffold_fields
            if f.get("name") and f.get("name") not in local_field_names
        ]

        if not new_fields:
            return False

        # Add new fields to local
        local_data["fields"].extend(new_fields)

        # Write back
        with open(local_file, "w", encoding="utf-8") as f:
            yaml.dump(local_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        print(f"  Added {len(new_fields)} new fields to {local_file.name}:")
        for field in new_fields:
            print(f"    + {field.get('name')}")

        return True
    except Exception as e:
        print(f"  Warning: Could not merge {local_file.name}: {e}")
        return False


def _sync_scaffold_files():
    """Sync missing files from scaffold to current site.

    Note: content_types and relations.yaml are NOT synced.
    They are always loaded from the package (core/content_types/, core/relations.yaml).
    This function only syncs theme templates.
    """
    scaffold_path = _get_scaffold_path()
    synced = []

    print("Syncing missing theme files from scaffold...")

    # Sync themes (only missing files, don't overwrite)
    themes_scaffold = scaffold_path / "themes"
    themes_local = Path("themes")
    if themes_scaffold.exists() and themes_local.exists():
        for theme_dir in themes_scaffold.iterdir():
            if theme_dir.is_dir():
                local_theme = themes_local / theme_dir.name
                if local_theme.exists():
                    # Sync missing template files
                    for template in theme_dir.rglob("*"):
                        if template.is_file():
                            rel_path = template.relative_to(theme_dir)
                            local_template = local_theme / rel_path
                            if not local_template.exists():
                                local_template.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy(template, local_template)
                                synced.append(f"themes/{theme_dir.name}/{rel_path}")

    if synced:
        print(f"\nSynced {len(synced)} files:")
        for f in synced:
            print(f"  + {f}")
    else:
        print("\nAll files are up to date.")


def _check_github_release(args):
    """Check GitHub for latest release."""
    import httpx

    response = httpx.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        timeout=10,
    )

    if response.status_code == 200:
        data = response.json()
        latest_version = data["tag_name"].lstrip("v")

        if latest_version == __version__:
            print(f"You are running the latest version ({__version__})")
        else:
            print(f"New version available: {latest_version}")
            print(f"Download: {data['html_url']}")
    else:
        print("Could not check for updates.")


def cmd_build(args):
    """Build static site."""
    output = Path(args.output)
    print(f"Building static site to {output}...")

    # TODO: Implement static site generation
    print("Static site generation is not yet implemented.")
    print("Use 'focomy serve' for dynamic serving.")


def cmd_backup(args):
    """Backup database and uploads."""
    import tempfile
    import zipfile
    from datetime import datetime

    output = Path(args.output)
    datetime.now().strftime("%Y%m%d_%H%M%S")

    if output.suffix != ".zip":
        output = output.with_suffix(".zip")

    print(f"Creating backup: {output}")

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        # Backup database if requested
        if args.include_db:
            print("  Dumping database...")
            try:
                from .config import settings

                # Parse database URL
                db_url = settings.database_url
                # Convert asyncpg URL to regular postgres URL for pg_dump
                db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

                # Create temp file for dump
                with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as tmp:
                    tmp_path = tmp.name

                result = subprocess.run(
                    ["pg_dump", db_url, "-f", tmp_path],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    print(f"\nError: pg_dump failed", file=sys.stderr)
                    if result.stderr:
                        print(f"  {result.stderr.strip()}", file=sys.stderr)
                    print("\nBackup aborted. Database dump is required when --include-db is specified.", file=sys.stderr)
                    os.unlink(tmp_path)
                    sys.exit(1)

                zf.write(tmp_path, "database.sql")
                print("  Added: database.sql")
                os.unlink(tmp_path)

            except Exception as e:
                print(f"\nError: Database backup failed: {e}", file=sys.stderr)
                sys.exit(1)

        # Backup uploads
        uploads_dir = Path("uploads")
        if uploads_dir.exists():
            for file in uploads_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, f"uploads/{file.relative_to(uploads_dir)}")
                    print(f"  Added: {file}")

        # Backup config
        if Path("config.yaml").exists():
            zf.write("config.yaml", "config.yaml")

        # Note: content_types and relations.yaml are NOT backed up
        # They are always loaded from the package (core/content_types/, core/relations.yaml)

        # Backup plugins (user extensions)
        plugins_dir = Path("plugins")
        if plugins_dir.exists():
            for file in plugins_dir.rglob("*"):
                if file.is_file() and file.name != ".gitkeep":
                    zf.write(file, f"plugins/{file.relative_to(plugins_dir)}")

        # Backup themes
        themes_dir = Path("themes")
        if themes_dir.exists():
            for file in themes_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, f"themes/{file.relative_to(themes_dir)}")

    print(f"\nBackup complete: {output}")
    if not args.include_db:
        print("Tip: Use --include-db to include database dump")


def cmd_restore(args):
    """Restore from backup."""
    import zipfile

    backup_file = Path(args.file)
    if not backup_file.exists():
        print(f"Error: Backup file not found: {backup_file}")
        sys.exit(1)

    print(f"Restoring from: {backup_file}")

    with zipfile.ZipFile(backup_file, "r") as zf:
        # List contents
        names = zf.namelist()
        has_db = "database.sql" in names

        # Restore files
        for name in names:
            if name == "database.sql":
                continue  # Handle separately

            target = Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            zf.extract(name, ".")
            print(f"  Restored: {name}")

        # Restore database
        if has_db:
            print("\nRestoring database...")
            try:
                from .config import settings

                db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

                # Extract SQL file
                zf.extract("database.sql", ".")

                result = subprocess.run(
                    ["psql", db_url, "-f", "database.sql"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    print("  Database restored successfully")
                else:
                    print(f"  Warning: Database restore failed: {result.stderr}")

                os.unlink("database.sql")

            except Exception as e:
                print(f"  Warning: Database restore failed: {e}")

    print("\nRestore complete!")


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


def cmd_import(args):
    """Import from WordPress."""
    if not hasattr(args, "import_type") or not args.import_type:
        print("Usage: focomy import wordpress <file.xml>")
        print("       focomy import wordpress --url https://example.com --username admin --password xxxx")
        sys.exit(1)

    if args.import_type == "wordpress":
        cmd_import_wordpress(args)


def cmd_import_wordpress(args):
    """Import from WordPress (WXR file or REST API)."""
    from pathlib import Path

    # Determine source type
    source_type = None
    source_file = None
    source_url = None

    if args.file:
        source_type = "wxr"
        source_file = Path(args.file)
        if not source_file.exists():
            print(f"Error: File not found: {source_file}")
            sys.exit(1)
        print(f"Importing from WXR file: {source_file}")
    elif args.url:
        source_type = "rest_api"
        source_url = args.url
        print(f"Importing from WordPress site: {source_url}")
    else:
        print("Error: Specify either a WXR file or --url for REST API import")
        print("\nExamples:")
        print("  focomy import wordpress export.xml")
        print("  focomy import wordpress --url https://example.com --username admin --password xxxx")
        sys.exit(1)

    async def run_import():
        from .database import async_session, init_db
        from .services.wordpress_import import (
            WordPressAnalyzer,
            WordPressImportService,
            WordPressRESTClient,
            RESTClientConfig,
            WXRParser,
        )

        await init_db()

        async with async_session() as db:
            import_svc = WordPressImportService(db)

            # Create import job
            config = {
                "import_media": args.include_media,
                "include_drafts": args.include_drafts,
                "username": args.username or "",
                "password": args.password or "",
            }

            job = await import_svc.create_job(
                source_type=source_type,
                source_url=source_url,
                source_file=str(source_file) if source_file else None,
                config=config,
            )

            print(f"Created import job: {job.id}")

            # Test connection for REST API
            if source_type == "rest_api":
                print("\nTesting connection...")
                rest_config = RESTClientConfig(
                    site_url=source_url,
                    username=args.username or "",
                    password=args.password or "",
                )
                async with WordPressRESTClient(rest_config) as client:
                    test_result = await client.test_connection()
                    if test_result.success:
                        print(f"  Connected to: {test_result.site_name}")
                        print(f"  Authenticated: {'Yes' if test_result.authenticated else 'No'}")
                    else:
                        print(f"  Connection failed: {test_result.message}")
                        for error in test_result.errors:
                            print(f"    - {error}")
                        sys.exit(1)

            # Analyze
            print("\nAnalyzing WordPress data...")
            analysis = await import_svc.analyze(job.id)

            if not analysis:
                print("Error: Analysis failed")
                sys.exit(1)

            # Print analysis
            print("\n" + "=" * 60)
            print("ANALYSIS RESULTS")
            print("=" * 60)
            print(f"Site: {analysis.get('site_name', 'Unknown')}")
            print(f"URL:  {analysis.get('site_url', 'Unknown')}")
            print(f"WordPress Version: {analysis.get('wp_version', 'Unknown')}")
            print()
            print("Content:")
            posts = analysis.get("posts", {})
            pages = analysis.get("pages", {})
            media = analysis.get("media", {})
            print(f"  Posts:      {posts.get('total', 0):>6} ({posts.get('published', 0)} published)")
            print(f"  Pages:      {pages.get('total', 0):>6} ({pages.get('published', 0)} published)")
            print(f"  Media:      {media.get('total_count', 0):>6}")
            print(f"  Categories: {analysis.get('categories_count', 0):>6}")
            print(f"  Tags:       {analysis.get('tags_count', 0):>6}")
            print(f"  Users:      {analysis.get('users_count', 0):>6}")
            print(f"  Comments:   {analysis.get('comments_count', 0):>6}")
            print(f"  Menus:      {analysis.get('menus_count', 0):>6}")

            # Custom post types
            cpts = analysis.get("custom_post_types", [])
            if cpts:
                print("\nCustom Post Types:")
                for cpt in cpts:
                    print(f"  {cpt['name']}: {cpt['count']}")

            # Detected plugins
            plugins = analysis.get("detected_plugins", [])
            if plugins:
                print("\nDetected Plugins:")
                for plugin in plugins:
                    print(f"  {plugin['name']}")

            # Warnings
            warnings = analysis.get("warnings", [])
            if warnings:
                print("\nWarnings:")
                for w in warnings:
                    print(f"  [{w['code']}] {w['message']}")

            # Estimates
            print()
            print(f"Estimated Time:    {analysis.get('estimated_time', 'Unknown')}")
            print(f"Estimated Storage: {analysis.get('estimated_storage', 'Unknown')}")
            print("=" * 60)

            # Dry run stops here
            if args.dry_run:
                print("\nDry run complete. No data imported.")
                return

            # Confirm import
            print()
            confirm = input("Proceed with import? [y/N] ")
            if confirm.lower() != "y":
                print("Import cancelled.")
                return

            # Run import
            print("\nStarting import...")

            def progress_callback(current, total, message):
                if args.verbose:
                    pct = int(current / total * 100) if total > 0 else 0
                    print(f"  [{pct:3d}%] {message}")

            result = await import_svc.run_import(job.id)

            if result and result.success:
                print("\n" + "=" * 60)
                print("IMPORT COMPLETE")
                print("=" * 60)
                print(f"  Posts imported:      {result.posts_imported}")
                print(f"  Pages imported:      {result.pages_imported}")
                print(f"  Media imported:      {result.media_imported}")
                print(f"  Categories imported: {result.categories_imported}")
                print(f"  Tags imported:       {result.tags_imported}")
                print(f"  Authors imported:    {result.authors_imported}")
                print(f"  Menus imported:      {result.menus_imported}")
                print("=" * 60)
            else:
                print("\nImport failed. Check logs for details.")
                job = await import_svc.get_job(job.id)
                if job and job.errors:
                    print("\nErrors:")
                    for error in job.errors:
                        print(f"  - {error}")
                sys.exit(1)

    asyncio.run(run_import())


if __name__ == "__main__":
    main()
