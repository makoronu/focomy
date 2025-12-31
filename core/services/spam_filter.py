"""Spam Filter Service - Advanced spam detection.

Integrates:
- Akismet API for spam detection
- Honeypot fields
- Rate limiting
- Content analysis
"""

import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SpamCheckResult:
    """Result of spam check."""

    is_spam: bool
    confidence: float  # 0.0 to 1.0
    reasons: list[str]
    should_moderate: bool  # Needs human review


@dataclass
class CommentData:
    """Comment data for spam checking."""

    content: str
    author_name: str
    author_email: str
    author_url: str | None
    author_ip: str
    user_agent: str
    referrer: str | None
    post_id: str
    post_url: str


class SpamFilterService:
    """
    Advanced spam filtering service.

    Usage:
        spam_filter = SpamFilterService(akismet_key="your_key")

        # Check a comment
        result = await spam_filter.check_comment(comment_data)

        if result.is_spam:
            reject_comment()
        elif result.should_moderate:
            queue_for_moderation()
    """

    AKISMET_URL = "https://rest.akismet.com/1.1"

    def __init__(
        self,
        akismet_key: str = None,
        site_url: str = "",
    ):
        self.akismet_key = akismet_key
        self.site_url = site_url
        self._rate_limits: dict[str, list[datetime]] = defaultdict(list)
        self._known_spammers: set[str] = set()

    async def check_comment(
        self,
        comment: CommentData,
    ) -> SpamCheckResult:
        """
        Check if a comment is spam.

        Uses multiple detection methods:
        1. Rate limiting
        2. Content analysis
        3. Known spammer list
        4. Akismet API
        """
        reasons = []
        scores = []

        # Rate limit check
        rate_score, rate_reason = self._check_rate_limit(comment.author_ip)
        if rate_reason:
            reasons.append(rate_reason)
        scores.append(rate_score)

        # Known spammer check
        if self._is_known_spammer(comment):
            reasons.append("Known spammer")
            scores.append(1.0)

        # Content analysis
        content_score, content_reasons = self._analyze_content(comment.content)
        reasons.extend(content_reasons)
        scores.append(content_score)

        # URL analysis
        url_score, url_reason = self._check_urls(comment)
        if url_reason:
            reasons.append(url_reason)
        scores.append(url_score)

        # Akismet check (if configured)
        if self.akismet_key:
            akismet_result = await self._check_akismet(comment)
            if akismet_result:
                reasons.append("Akismet flagged as spam")
                scores.append(0.9)

        # Calculate final score
        if scores:
            confidence = max(scores)
        else:
            confidence = 0.0

        is_spam = confidence >= 0.8
        should_moderate = 0.4 <= confidence < 0.8

        return SpamCheckResult(
            is_spam=is_spam,
            confidence=confidence,
            reasons=reasons,
            should_moderate=should_moderate,
        )

    def _check_rate_limit(
        self,
        ip_address: str,
        max_per_minute: int = 5,
    ) -> tuple[float, str | None]:
        """Check for rate limit violations."""
        now = utcnow()
        minute_ago = now - timedelta(minutes=1)

        # Clean old entries
        self._rate_limits[ip_address] = [t for t in self._rate_limits[ip_address] if t > minute_ago]

        # Count recent requests
        count = len(self._rate_limits[ip_address])

        # Add current request
        self._rate_limits[ip_address].append(now)

        if count >= max_per_minute:
            return 0.7, f"Rate limit exceeded: {count} comments/minute"

        return 0.0, None

    def _is_known_spammer(self, comment: CommentData) -> bool:
        """Check against known spammer list."""
        # Check email hash
        email_hash = hashlib.md5(comment.author_email.lower().encode()).hexdigest()
        if email_hash in self._known_spammers:
            return True

        # Check IP
        if comment.author_ip in self._known_spammers:
            return True

        return False

    def _analyze_content(self, content: str) -> tuple[float, list[str]]:
        """Analyze comment content for spam patterns."""
        reasons = []
        score = 0.0

        content_lower = content.lower()

        # Check for excessive links
        url_pattern = r"https?://\S+"
        urls = re.findall(url_pattern, content)
        if len(urls) > 3:
            reasons.append(f"Too many URLs ({len(urls)})")
            score = max(score, 0.6)

        # Check for spam keywords
        spam_keywords = [
            "buy now",
            "click here",
            "free money",
            "make money fast",
            "viagra",
            "casino",
            "lottery",
            "winner",
            "congratulations",
            "act now",
            "limited time",
            "earn extra",
            "work from home",
        ]
        for keyword in spam_keywords:
            if keyword in content_lower:
                reasons.append(f"Spam keyword: {keyword}")
                score = max(score, 0.7)
                break

        # Check for all caps
        if len(content) > 20:
            upper_ratio = sum(1 for c in content if c.isupper()) / len(content)
            if upper_ratio > 0.7:
                reasons.append("Excessive caps")
                score = max(score, 0.4)

        # Check for repeated characters
        if re.search(r"(.)\1{5,}", content):
            reasons.append("Repeated characters")
            score = max(score, 0.5)

        # Check for very short content
        if len(content.strip()) < 10:
            reasons.append("Very short content")
            score = max(score, 0.3)

        return score, reasons

    def _check_urls(self, comment: CommentData) -> tuple[float, str | None]:
        """Check URLs for spam indicators."""
        if not comment.author_url:
            return 0.0, None

        url = comment.author_url.lower()

        # Known spam TLDs
        spam_tlds = [".xyz", ".top", ".click", ".loan", ".work"]
        for tld in spam_tlds:
            if url.endswith(tld):
                return 0.6, f"Suspicious TLD: {tld}"

        return 0.0, None

    async def _check_akismet(self, comment: CommentData) -> bool:
        """Check comment with Akismet API."""
        if not self.akismet_key:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://{self.akismet_key}.rest.akismet.com/1.1/comment-check",
                    data={
                        "blog": self.site_url,
                        "user_ip": comment.author_ip,
                        "user_agent": comment.user_agent,
                        "referrer": comment.referrer or "",
                        "permalink": comment.post_url,
                        "comment_type": "comment",
                        "comment_author": comment.author_name,
                        "comment_author_email": comment.author_email,
                        "comment_author_url": comment.author_url or "",
                        "comment_content": comment.content,
                    },
                    timeout=5.0,
                )

                return response.text.strip().lower() == "true"

        except Exception:
            return False

    async def report_spam(self, comment: CommentData) -> None:
        """Report a false negative (missed spam) to Akismet."""
        if not self.akismet_key:
            return

        # Add to known spammers
        email_hash = hashlib.md5(comment.author_email.lower().encode()).hexdigest()
        self._known_spammers.add(email_hash)

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://{self.akismet_key}.rest.akismet.com/1.1/submit-spam",
                    data={
                        "blog": self.site_url,
                        "user_ip": comment.author_ip,
                        "user_agent": comment.user_agent,
                        "comment_author": comment.author_name,
                        "comment_author_email": comment.author_email,
                        "comment_content": comment.content,
                    },
                    timeout=5.0,
                )
        except Exception as e:
            logger.debug(f"Akismet report_spam failed: {e}")

    async def report_ham(self, comment: CommentData) -> None:
        """Report a false positive (legitimate marked as spam) to Akismet."""
        if not self.akismet_key:
            return

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://{self.akismet_key}.rest.akismet.com/1.1/submit-ham",
                    data={
                        "blog": self.site_url,
                        "user_ip": comment.author_ip,
                        "user_agent": comment.user_agent,
                        "comment_author": comment.author_name,
                        "comment_author_email": comment.author_email,
                        "comment_content": comment.content,
                    },
                    timeout=5.0,
                )
        except Exception as e:
            logger.debug(f"Akismet report_ham failed: {e}")

    async def verify_key(self) -> bool:
        """Verify Akismet API key."""
        if not self.akismet_key:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.AKISMET_URL}/verify-key",
                    data={
                        "key": self.akismet_key,
                        "blog": self.site_url,
                    },
                    timeout=5.0,
                )

                return response.text.strip().lower() == "valid"

        except Exception:
            return False


class HoneypotField:
    """
    Honeypot field for bot detection.

    Usage:
        honeypot = HoneypotField()

        # In template: add hidden field with honeypot.field_name
        <input type="text" name="{{ honeypot.field_name }}" style="display:none">

        # On submit: check if field was filled
        if honeypot.is_bot(request.form.get(honeypot.field_name)):
            reject()
    """

    # Common honeypot field names
    FIELD_NAMES = [
        "website_url",
        "phone_number",
        "fax_number",
        "address_2",
    ]

    def __init__(self, field_name: str = None):
        self.field_name = field_name or self.FIELD_NAMES[0]

    def is_bot(self, field_value: str) -> bool:
        """Check if honeypot was triggered (bots fill hidden fields)."""
        return bool(field_value and field_value.strip())


def get_spam_filter_service(
    akismet_key: str = None,
    site_url: str = "",
) -> SpamFilterService:
    return SpamFilterService(akismet_key, site_url)
