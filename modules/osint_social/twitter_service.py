"""Twitter/X OSINT service — uses tweepy + Bearer Token"""
from datetime import datetime
from config import settings, logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth


def get_health() -> PlatformHealth:
    if not settings.twitter_bearer_token:
        return PlatformHealth(available=False, reason="TWITTER_BEARER_TOKEN not configured")
    return PlatformHealth(available=True)


@rate_limited("twitter")
async def search(query: str = None, user: str = None, max_results: int = 10) -> list[OsintResult]:
    if not settings.twitter_bearer_token:
        return []
    try:
        import tweepy
        client = tweepy.Client(bearer_token=settings.twitter_bearer_token)
        results = []

        if query:
            resp = client.search_recent_tweets(query=query, max_results=min(max_results, 100), tweet_fields=["created_at", "author_id", "public_metrics"])
            if resp.data:
                for tweet in resp.data:
                    results.append(OsintResult(
                        plataforma="twitter",
                        tipo="tweet",
                        datos={"text": tweet.text, "author_id": tweet.author_id, "metrics": tweet.public_metrics, "id": tweet.id},
                        timestamp=tweet.created_at.isoformat() if tweet.created_at else datetime.now().isoformat(),
                        fuente_url=f"https://twitter.com/i/web/status/{tweet.id}",
                    ))

        if user:
            user_resp = client.get_user(username=user, user_fields=["description", "public_metrics", "profile_image_url", "created_at"])
            if user_resp.data:
                u = user_resp.data
                results.append(OsintResult(
                    plataforma="twitter",
                    tipo="perfil",
                    datos={"username": u.username, "name": u.name, "description": u.description, "metrics": u.public_metrics, "profile_image": u.profile_image_url},
                    timestamp=u.created_at.isoformat() if u.created_at else "",
                    fuente_url=f"https://twitter.com/{u.username}",
                ))

        return results
    except Exception as e:
        logger.error(f"Twitter search error: {e}")
        return []
