# Focomy

**The Most Beautiful CMS** - A metadata-driven, zero-duplicate-code content management system.

## Features

- **Metadata-Driven**: Define content types in YAML, no code changes needed
- **Zero Duplicate Code**: One EntityService handles all content types
- **First-Class Relations**: Many-to-many, many-to-one, self-referential
- **Built-in SEO**: JSON-LD, OGP, Twitter Cards, Sitemap, RSS/Atom feeds
- **Modern Stack**: FastAPI, PostgreSQL, HTMX, Editor.js
- **Security First**: HSTS, CSP, CSRF protection, rate limiting

## Quick Start

### Using pip

```bash
pip install focomy
focomy init mysite
cd mysite
focomy serve
```

### Using Docker

```bash
git clone https://github.com/focomy/focomy.git
cd focomy
docker-compose up -d
```

Open http://localhost:8000/admin

## Installation

### Requirements

- Python 3.10+
- PostgreSQL 13+

### From PyPI

```bash
pip install focomy

# With Redis support (for caching/sessions)
pip install focomy[redis]
```

### From Source

```bash
git clone https://github.com/focomy/focomy.git
cd focomy
pip install -e .
```

## CLI Commands

```bash
# Initialize a new site
focomy init mysite

# Start development server
focomy serve --port 8000

# Run database migrations
focomy migrate

# Validate content type definitions
focomy validate

# Check for updates
focomy update --check

# Update to latest version
focomy update
```

## Configuration

### config.yaml

```yaml
site:
  name: "My Site"
  url: "https://example.com"
  language: "ja"

security:
  secret_key: "your-secret-key"
```

### Content Types

Define in `content_types/*.yaml`:

```yaml
name: post
label: Post
fields:
  - name: title
    type: string
    required: true
  - name: body
    type: blocks
  - name: status
    type: select
    options: [draft, published]
```

## Deployment

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/focomy)

### Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/focomy/focomy)

### Docker Compose

```bash
docker-compose up -d
```

## Documentation

- [Getting Started](https://focomy.dev/docs/getting-started)
- [Content Types](https://focomy.dev/docs/content-types)
- [API Reference](https://focomy.dev/docs/api)
- [Theming](https://focomy.dev/docs/theming)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read our [Contributing Guide](CONTRIBUTING.md).
