"""CLI import commands - WordPress import."""

import asyncio
import sys
from pathlib import Path


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
