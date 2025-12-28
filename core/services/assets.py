"""Asset URL management with CDN support."""

from pathlib import Path

from ..config import settings


def get_asset_url(path: str, absolute: bool = False) -> str:
    """Get asset URL, using CDN if configured.

    Args:
        path: Relative path to asset (e.g., "/uploads/image.jpg")
        absolute: If True, return absolute URL with domain

    Returns:
        URL to the asset
    """
    cdn_config = settings.media.cdn

    if cdn_config.enabled and cdn_config.url:
        # Use CDN URL
        cdn_base = cdn_config.url.rstrip("/")
        # Remove leading slash for CDN
        clean_path = path.lstrip("/")
        return f"{cdn_base}/{clean_path}"

    # Use local URL
    if absolute:
        site_url = settings.site.url.rstrip("/")
        return f"{site_url}{path}"

    return path


def get_upload_url(filename: str, absolute: bool = False) -> str:
    """Get URL for an uploaded file.

    Args:
        filename: Filename or relative path within uploads
        absolute: If True, return absolute URL with domain

    Returns:
        URL to the uploaded file
    """
    # Ensure path starts with /uploads/
    if not filename.startswith("/"):
        path = f"/uploads/{filename}"
    elif not filename.startswith("/uploads/"):
        path = f"/uploads{filename}"
    else:
        path = filename

    return get_asset_url(path, absolute)


def get_static_url(path: str, absolute: bool = False) -> str:
    """Get URL for a static file.

    Args:
        path: Path relative to static directory
        absolute: If True, return absolute URL with domain

    Returns:
        URL to the static file
    """
    if not path.startswith("/"):
        path = f"/static/{path}"
    elif not path.startswith("/static/"):
        path = f"/static{path}"

    return get_asset_url(path, absolute)


class S3Client:
    """Simple S3 client for file uploads."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-load boto3 client."""
        if self._client is None:
            import boto3

            cdn_config = settings.media.cdn
            self._client = boto3.client(
                "s3",
                region_name=cdn_config.s3_region,
                aws_access_key_id=cdn_config.s3_access_key,
                aws_secret_access_key=cdn_config.s3_secret_key,
            )
        return self._client

    def upload_file(
        self,
        file_path: Path,
        s3_key: str,
        content_type: str | None = None,
    ) -> str:
        """Upload file to S3.

        Args:
            file_path: Local file path
            s3_key: S3 object key
            content_type: MIME type of the file

        Returns:
            S3 URL of the uploaded file
        """
        cdn_config = settings.media.cdn
        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        # Make publicly readable
        extra_args["ACL"] = "public-read"

        # Set cache headers for static assets
        extra_args["CacheControl"] = "public, max-age=31536000"

        self.client.upload_file(
            str(file_path),
            cdn_config.s3_bucket,
            s3_key,
            ExtraArgs=extra_args,
        )

        # Return CDN URL if configured, otherwise S3 URL
        if cdn_config.url:
            return f"{cdn_config.url.rstrip('/')}/{s3_key}"

        return f"https://{cdn_config.s3_bucket}.s3.{cdn_config.s3_region}.amazonaws.com/{s3_key}"

    def delete_file(self, s3_key: str) -> bool:
        """Delete file from S3.

        Args:
            s3_key: S3 object key

        Returns:
            True if deleted successfully
        """
        cdn_config = settings.media.cdn
        try:
            self.client.delete_object(
                Bucket=cdn_config.s3_bucket,
                Key=s3_key,
            )
            return True
        except Exception:
            return False


# Singleton instance
s3_client = S3Client()
