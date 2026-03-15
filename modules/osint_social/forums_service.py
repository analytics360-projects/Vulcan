"""Forums OSINT service — asyncpraw (Reddit) + BS4 generic"""
from datetime import datetime
from config import settings, logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth


def get_health() -> PlatformHealth:
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return PlatformHealth(available=True, reason="Google fallback mode (REDDIT_CLIENT_ID/SECRET not configured)")
    return PlatformHealth(available=True)


async def _google_forums_fallback(query: str, max_results: int) -> list[OsintResult]:
    """Fallback: search forums via Google dorks when Reddit API keys are not configured."""
    results = []
    try:
        from modules.google_search.service import search as google_search
        dork = f'site:reddit.com OR site:quora.com OR site:foros.com "{query}"'
        google_results = await google_search(dork, max_results=max_results)
        for item in google_results:
            results.append(OsintResult(
                plataforma="forums_google",
                tipo="post",
                datos={
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", item.get("description", "")),
                    "source": item.get("source", item.get("domain", "")),
                },
                fuente_url=item.get("url", item.get("link", "")),
            ))
    except Exception as e:
        logger.warning(f"Forums Google fallback error: {e}")
    return results


@rate_limited("forums")
async def search(query: str = None, subreddit: str = None, max_results: int = 10) -> list[OsintResult]:
    if not settings.reddit_client_id:
        return await _google_forums_fallback(query, max_results) if query else []
    results = []
    try:
        import asyncpraw

        reddit = asyncpraw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

        if subreddit and query:
            sub = await reddit.subreddit(subreddit)
            async for post in sub.search(query, limit=max_results):
                results.append(OsintResult(
                    plataforma="reddit",
                    tipo="post",
                    datos={"title": post.title, "selftext": post.selftext[:500] if post.selftext else "", "score": post.score, "num_comments": post.num_comments, "author": str(post.author)},
                    timestamp=datetime.fromtimestamp(post.created_utc).isoformat(),
                    fuente_url=f"https://reddit.com{post.permalink}",
                ))
        elif query:
            async for post in reddit.subreddit("all").search(query, limit=max_results):
                results.append(OsintResult(
                    plataforma="reddit",
                    tipo="post",
                    datos={"title": post.title, "selftext": post.selftext[:500] if post.selftext else "", "score": post.score, "subreddit": str(post.subreddit)},
                    timestamp=datetime.fromtimestamp(post.created_utc).isoformat(),
                    fuente_url=f"https://reddit.com{post.permalink}",
                ))

        await reddit.close()
    except Exception as e:
        logger.error(f"Forums search error: {e}")
    return results
