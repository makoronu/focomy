#!/usr/bin/env python
"""Focomy CLI - command line interface for Focomy CMS."""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def cmd_serve(args):
    """Start development server."""
    import uvicorn

    uvicorn.run(
        "core.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def cmd_migrate(args):
    """Run database migrations."""

    async def run():
        from core.database import init_db

        print("Running migrations...")
        await init_db()
        print("Migrations complete.")

    asyncio.run(run())


def cmd_validate(args):
    """Validate content type definitions."""
    from core.services.field import field_service

    print("Validating content types...")

    content_types = field_service.get_all_content_types()
    errors = []

    for name, ct in content_types.items():
        print(f"  - {name}: {len(ct.fields)} fields")

        # Check for required fields
        for field in ct.fields:
            if not field.name:
                errors.append(f"{name}: Field missing name")
            if not field.type:
                errors.append(f"{name}.{field.name}: Field missing type")

    # Validate relations
    print("\nValidating relations...")
    relations = field_service.get_all_relation_types()

    for name, rel in relations.items():
        print(f"  - {name}: {rel.from_type} -> {rel.to_type}")

        if rel.from_type not in content_types:
            errors.append(f"{name}: Unknown from_type '{rel.from_type}'")
        if rel.to_type not in content_types:
            errors.append(f"{name}: Unknown to_type '{rel.to_type}'")

    if errors:
        print(f"\nFound {len(errors)} errors:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("\nValidation passed!")


def cmd_build(args):
    """Build static site."""

    async def run():
        from core.database import init_db
        from core.services.entity import EntityService
        from core.services.seo import SEOService
        from core.services.theme import theme_service

        await init_db()

        output_dir = Path(args.output)
        output_dir.mkdir(exist_ok=True)

        print(f"Building static site to {output_dir}...")

        # Get database session
        from core.database import async_session

        async with async_session() as db:
            entity_svc = EntityService(db)
            seo_svc = SEOService(entity_svc, args.base_url)

            # Build index
            print("  - Building index.html")
            posts = await entity_svc.find(
                "post",
                limit=100,
                order_by="-created_at",
            )
            posts_data = [entity_svc.serialize(p) for p in posts]

            index_html = theme_service.render("index.html", {"posts": posts_data})
            (output_dir / "index.html").write_text(index_html)

            # Build posts
            print(f"  - Building {len(posts)} posts")
            posts_dir = output_dir / "post"
            posts_dir.mkdir(exist_ok=True)

            for post in posts:
                post_data = entity_svc.serialize(post)
                slug = post_data.get("slug", post.id)

                meta = seo_svc.generate_meta(post)
                seo_meta = seo_svc.render_meta_tags(meta)

                post_html = theme_service.render(
                    "post.html",
                    {
                        "post": post_data,
                        "seo_meta": seo_meta,
                    },
                )

                (posts_dir / f"{slug}.html").write_text(post_html)

            # Build pages
            pages = await entity_svc.find("page", limit=100)
            print(f"  - Building {len(pages)} pages")

            pages_dir = output_dir / "page"
            pages_dir.mkdir(exist_ok=True)

            for page in pages:
                page_data = entity_svc.serialize(page)
                slug = page_data.get("slug", page.id)

                meta = seo_svc.generate_meta(page)
                seo_meta = seo_svc.render_meta_tags(meta)

                page_html = theme_service.render(
                    "post.html",
                    {
                        "post": page_data,
                        "seo_meta": seo_meta,
                    },
                )

                (pages_dir / f"{slug}.html").write_text(page_html)

            # Build sitemap
            print("  - Building sitemap.xml")
            sitemap = await seo_svc.generate_sitemap()
            (output_dir / "sitemap.xml").write_text(sitemap)

        print(f"\nBuild complete! Output: {output_dir}")

    asyncio.run(run())


def cmd_create_user(args):
    """Create admin user."""

    async def run():
        from core.database import async_session, init_db
        from core.services.auth import AuthService

        await init_db()

        async with async_session() as db:
            auth_svc = AuthService(db)

            try:
                user = await auth_svc.register(
                    email=args.email,
                    password=args.password,
                    name=args.name,
                    role=args.role,
                )
                print(f"User created: {user.id}")
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

    asyncio.run(run())


def cmd_seed(args):
    """Create sample data."""

    async def run():
        from core.database import async_session, init_db
        from core.services.entity import EntityService

        await init_db()

        async with async_session() as db:
            entity_svc = EntityService(db)

            # Categories
            categories = [
                {"name": "Technology", "slug": "technology"},
                {"name": "Design", "slug": "design"},
                {"name": "Business", "slug": "business"},
            ]

            print("Creating categories...")
            for cat in categories:
                try:
                    await entity_svc.create("category", cat)
                    print(f"  Created: {cat['name']}")
                except Exception:
                    print(f"  Exists: {cat['name']}")

            # Posts
            posts = [
                {
                    "title": "Welcome to Focomy",
                    "slug": "welcome-to-focomy",
                    "body": [{"type": "paragraph", "data": {"text": "Your first post."}}],
                    "status": "published",
                },
            ]

            print("Creating posts...")
            for post in posts:
                try:
                    await entity_svc.create("post", post)
                    print(f"  Created: {post['title']}")
                except Exception:
                    print(f"  Exists: {post['title']}")

            # Page
            print("Creating pages...")
            try:
                await entity_svc.create(
                    "page",
                    {
                        "title": "About",
                        "slug": "about",
                        "body": [{"type": "paragraph", "data": {"text": "About us."}}],
                        "status": "published",
                    },
                )
                print("  Created: About")
            except Exception:
                print("  Exists: About")

        print("\nSeed complete!")

    asyncio.run(run())


def cmd_export(args):
    """Export data to JSON."""
    import json

    async def run():
        from core.database import async_session, init_db
        from core.services.entity import EntityService
        from core.services.field import field_service

        await init_db()

        async with async_session() as db:
            entity_svc = EntityService(db)
            data = {"content_types": {}}

            for ct in field_service.get_all_content_types():
                entities = await entity_svc.find(ct.name, limit=10000)
                data["content_types"][ct.name] = [entity_svc.serialize(e) for e in entities]

            output = args.output or "export.json"
            Path(output).write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"Exported to {output}")

    asyncio.run(run())


def cmd_import(args):
    """Import data from JSON."""
    import json

    async def run():
        from core.database import async_session, init_db
        from core.services.entity import EntityService

        await init_db()

        input_file = args.input
        if not Path(input_file).exists():
            print(f"Error: File not found: {input_file}")
            return

        data = json.loads(Path(input_file).read_text())

        async with async_session() as db:
            entity_svc = EntityService(db)

            for type_name, entities in data.get("content_types", {}).items():
                for entity_data in entities:
                    entity_data.pop("id", None)
                    entity_data.pop("created_at", None)
                    entity_data.pop("updated_at", None)

                    try:
                        await entity_svc.create(type_name, entity_data)
                        name = entity_data.get("title") or entity_data.get("name")
                        print(f"  Imported {type_name}: {name}")
                    except Exception as e:
                        print(f"  Error: {e}")

        print("\nImport complete!")

    asyncio.run(run())


def cmd_cache_clear(args):
    """Clear all caches."""
    from core.services.cache import cache_service

    count = cache_service.invalidate_all()
    print(f"Cleared {count} cache entries")


def main():
    parser = argparse.ArgumentParser(
        prog="focomy",
        description="Focomy CMS - The Most Beautiful CMS",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start development server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    serve_parser.set_defaults(func=cmd_serve)

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.set_defaults(func=cmd_migrate)

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate content types")
    validate_parser.set_defaults(func=cmd_validate)

    # build
    build_parser = subparsers.add_parser("build", help="Build static site")
    build_parser.add_argument("--output", "-o", default="dist", help="Output directory")
    build_parser.add_argument("--base-url", default="", help="Base URL for links")
    build_parser.set_defaults(func=cmd_build)

    # create-user
    user_parser = subparsers.add_parser("create-user", help="Create admin user")
    user_parser.add_argument("--email", required=True, help="User email")
    user_parser.add_argument("--password", required=True, help="User password")
    user_parser.add_argument("--name", required=True, help="User name")
    user_parser.add_argument("--role", default="admin", help="User role")
    user_parser.set_defaults(func=cmd_create_user)

    # seed
    seed_parser = subparsers.add_parser("seed", help="Create sample data")
    seed_parser.set_defaults(func=cmd_seed)

    # export
    export_parser = subparsers.add_parser("export", help="Export data to JSON")
    export_parser.add_argument("--output", "-o", help="Output file (default: export.json)")
    export_parser.set_defaults(func=cmd_export)

    # import
    import_parser = subparsers.add_parser("import", help="Import data from JSON")
    import_parser.add_argument("input", help="Input JSON file")
    import_parser.set_defaults(func=cmd_import)

    # cache:clear
    cache_parser = subparsers.add_parser("cache:clear", help="Clear all caches")
    cache_parser.set_defaults(func=cmd_cache_clear)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
