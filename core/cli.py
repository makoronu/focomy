"""Focomy CLI - Command Line Interface."""

import argparse
import os
import shutil
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
        from .cli_db import cmd_migrate
        cmd_migrate(args)
    elif args.command == "makemigrations":
        from .cli_db import cmd_makemigrations
        cmd_makemigrations(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "update":
        from .cli_ops import cmd_update
        cmd_update(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "backup":
        from .cli_ops import cmd_backup
        cmd_backup(args)
    elif args.command == "restore":
        from .cli_ops import cmd_restore
        cmd_restore(args)
    elif args.command == "createuser":
        from .cli_db import cmd_createuser
        cmd_createuser(args)
    elif args.command == "import":
        from .cli_import import cmd_import
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


def cmd_build(args):
    """Build static site."""
    output = Path(args.output)
    print(f"Building static site to {output}...")

    # TODO: Implement static site generation
    print("Static site generation is not yet implemented.")
    print("Use 'focomy serve' for dynamic serving.")


if __name__ == "__main__":
    main()
