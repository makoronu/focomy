"""Focomy CLI - Command Line Interface."""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Optional

# Version
__version__ = "0.1.0"

GITHUB_REPO = "focomy/focomy"
PYPI_PACKAGE = "focomy"


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="focomy",
        description="Focomy - The Most Beautiful CMS",
    )
    parser.add_argument(
        "--version", "-v",
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
    migrate_parser.add_argument("--sql", action="store_true", help="Output SQL instead of executing")
    migrate_parser.add_argument("--history", action="store_true", help="Show migration history")
    migrate_parser.add_argument("--current", action="store_true", help="Show current revision")
    migrate_parser.add_argument("--downgrade", action="store_true", help="Downgrade instead of upgrade")

    # makemigrations
    makemigrations_parser = subparsers.add_parser("makemigrations", help="Generate new migration")
    makemigrations_parser.add_argument("--message", "-m", required=True, help="Migration message")
    makemigrations_parser.add_argument("--autogenerate", action="store_true", help="Auto-detect schema changes")

    # validate
    subparsers.add_parser("validate", help="Validate content type definitions")

    # update
    update_parser = subparsers.add_parser("update", help="Update Focomy to latest version")
    update_parser.add_argument("--check", action="store_true", help="Check for updates only")
    update_parser.add_argument("--force", action="store_true", help="Force update")

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
    createuser_parser.add_argument("--role", "-r", default="admin", choices=["admin", "editor", "author"], help="User role")
    createuser_parser.add_argument("--password", "-p", help="Password (prompted if not provided)")

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
    dst_name: Optional[str] = None,
    replacements: Optional[dict] = None,
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
    _copy_scaffold_file(
        scaffold_path, target,
        "config.yaml.template", "config.yaml",
        replacements
    )

    # Copy content_types
    _copy_scaffold_dir(scaffold_path, target, "content_types")

    # Copy themes
    _copy_scaffold_dir(scaffold_path, target, "themes")

    # Copy relations.yaml
    _copy_scaffold_file(scaffold_path, target, "relations.yaml")

    # Copy .env from template
    _copy_scaffold_file(
        scaffold_path, target,
        ".env.template", ".env",
        replacements
    )

    # Copy .gitignore from template
    _copy_scaffold_file(
        scaffold_path, target,
        ".gitignore.template", ".gitignore"
    )

    # Create .gitkeep in uploads
    (target / "uploads" / ".gitkeep").touch()

    print(f"""
Site created successfully!

Next steps:
  cd {name}
  # Create PostgreSQL database
  createdb {name}
  # Start the server
  focomy serve

Open http://localhost:8000/admin
""")


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

    alembic_cfg = Config("alembic.ini")

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
                for type_name, indexes in results.items():
                    for idx in indexes:
                        print(f"  - {idx}")

    asyncio.run(create_indexes())


def cmd_makemigrations(args):
    """Generate a new migration using Alembic."""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")

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

    for ct in content_types:
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
    import zipfile
    from datetime import datetime
    import tempfile

    output = Path(args.output)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output.suffix != ".zip":
        output = output.with_suffix(".zip")

    print(f"Creating backup: {output}")

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        # Backup database if requested
        if args.include_db:
            print("  Dumping database...")
            try:
                from .config import settings
                import urllib.parse

                # Parse database URL
                db_url = settings.database_url
                # Convert asyncpg URL to regular postgres URL for pg_dump
                db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

                # Create temp file for dump
                with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as tmp:
                    tmp_path = tmp.name

                result = subprocess.run(
                    ["pg_dump", db_url, "-f", tmp_path],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    zf.write(tmp_path, "database.sql")
                    print("  Added: database.sql")
                    os.unlink(tmp_path)
                else:
                    print(f"  Warning: pg_dump failed: {result.stderr}")

            except Exception as e:
                print(f"  Warning: Database backup failed: {e}")

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

        # Backup content types
        ct_dir = Path("content_types")
        if ct_dir.exists():
            for file in ct_dir.glob("*.yaml"):
                zf.write(file, f"content_types/{file.name}")

        # Backup relations
        if Path("relations.yaml").exists():
            zf.write("relations.yaml", "relations.yaml")

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
        from .database import init_db, async_session
        from .services.auth import AuthService

        await init_db()

        async with async_session() as db:
            auth_service = AuthService(db)
            try:
                user = await auth_service.register(
                    email=email,
                    password=password,
                    name=name,
                    role=role,
                )
                print(f"\nUser created successfully!")
                print(f"  ID: {user.id}")
                print(f"  Email: {email}")
                print(f"  Name: {name}")
                print(f"  Role: {role}")
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

    asyncio.run(create_user())


if __name__ == "__main__":
    main()
