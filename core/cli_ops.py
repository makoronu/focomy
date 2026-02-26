"""CLI operations commands - update, backup, restore, import."""

import asyncio
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

import yaml

from . import __version__

GITHUB_REPO = "focomy/focomy"
PYPI_PACKAGE = "focomy"


def _get_scaffold_path() -> Path:
    """Get the path to scaffold directory from package resources."""
    try:
        # Python 3.9+
        scaffold_files = resources.files("core.scaffold")
        return Path(str(scaffold_files))
    except (TypeError, AttributeError):
        # Fallback for older Python or when running from source
        return Path(__file__).parent / "scaffold"


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
