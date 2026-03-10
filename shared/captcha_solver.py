"""CAPTCHA solving via 2captcha.com or anti-captcha.com APIs.

Usage (async):
    from shared.captcha_solver import solve_recaptcha_v2
    token = await solve_recaptcha_v2(site_key, page_url)

Usage (sync — for Selenium contexts):
    from shared.captcha_solver import solve_recaptcha_v2_sync
    token = solve_recaptcha_v2_sync(site_key, page_url)
"""
import asyncio
import time
import httpx
from config import settings, logger


def solve_recaptcha_v2_sync(
    site_key: str,
    page_url: str,
    invisible: bool = True,
    timeout_secs: int = 120,
) -> str | None:
    """Synchronous wrapper — uses httpx sync client directly."""
    if not settings.captcha_api_key:
        logger.warning("[CAPTCHA] No captcha_api_key configured — cannot solve reCAPTCHA")
        return None

    if settings.captcha_service == "2captcha":
        return _solve_2captcha_sync(site_key, page_url, invisible, timeout_secs)
    elif settings.captcha_service == "anti-captcha":
        return _solve_anticaptcha_sync(site_key, page_url, invisible, timeout_secs)
    else:
        logger.error(f"[CAPTCHA] Unknown service: {settings.captcha_service}")
        return None


def _solve_2captcha_sync(
    site_key: str, page_url: str, invisible: bool, timeout_secs: int
) -> str | None:
    """Solve via 2captcha.com (synchronous)."""
    api_key = settings.captcha_api_key
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=30) as client:
            params = {
                "key": api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1,
            }
            if invisible:
                params["invisible"] = 1

            resp = client.post("https://2captcha.com/in.php", data=params)
            data = resp.json()
            if data.get("status") != 1:
                logger.error(f"[CAPTCHA] 2captcha submit failed: {data}")
                return None

            task_id = data["request"]
            logger.info(f"[CAPTCHA] 2captcha task: {task_id}")

            time.sleep(15)
            elapsed = 0
            while elapsed < timeout_secs:
                resp = client.get(
                    "https://2captcha.com/res.php",
                    params={"key": api_key, "action": "get", "id": task_id, "json": 1},
                )
                result = resp.json()
                if result.get("status") == 1:
                    token = result["request"]
                    ms = (time.perf_counter() - t0) * 1000
                    logger.info(f"[CAPTCHA] Solved in {ms:.0f}ms")
                    return token
                elif result.get("request") == "CAPCHA_NOT_READY":
                    time.sleep(5)
                    elapsed += 5
                else:
                    logger.error(f"[CAPTCHA] 2captcha error: {result}")
                    return None
            logger.warning(f"[CAPTCHA] Timed out ({timeout_secs}s)")
            return None
    except Exception as e:
        logger.error(f"[CAPTCHA] Exception: {e}")
        return None


def _solve_anticaptcha_sync(
    site_key: str, page_url: str, invisible: bool, timeout_secs: int
) -> str | None:
    """Solve via anti-captcha.com (synchronous)."""
    api_key = settings.captcha_api_key
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=30) as client:
            payload = {
                "clientKey": api_key,
                "task": {
                    "type": "RecaptchaV2TaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                    "isInvisible": invisible,
                },
            }
            resp = client.post("https://api.anti-captcha.com/createTask", json=payload)
            data = resp.json()
            if data.get("errorId", 1) != 0:
                logger.error(f"[CAPTCHA] anti-captcha submit failed: {data}")
                return None

            task_id = data["taskId"]
            logger.info(f"[CAPTCHA] anti-captcha task: {task_id}")

            time.sleep(10)
            elapsed = 0
            while elapsed < timeout_secs:
                resp = client.post(
                    "https://api.anti-captcha.com/getTaskResult",
                    json={"clientKey": api_key, "taskId": task_id},
                )
                result = resp.json()
                if result.get("status") == "ready":
                    token = result["solution"]["gRecaptchaResponse"]
                    ms = (time.perf_counter() - t0) * 1000
                    logger.info(f"[CAPTCHA] Solved in {ms:.0f}ms")
                    return token
                elif result.get("status") == "processing":
                    time.sleep(5)
                    elapsed += 5
                else:
                    logger.error(f"[CAPTCHA] anti-captcha error: {result}")
                    return None
            logger.warning(f"[CAPTCHA] Timed out ({timeout_secs}s)")
            return None
    except Exception as e:
        logger.error(f"[CAPTCHA] Exception: {e}")
        return None


async def solve_recaptcha_v2(
    site_key: str,
    page_url: str,
    invisible: bool = True,
    timeout_secs: int = 120,
) -> str | None:
    """
    Solve a reCAPTCHA v2 challenge via external service.
    Returns the g-recaptcha-response token or None on failure.
    """
    if not settings.captcha_api_key:
        logger.warning("[CAPTCHA] No captcha_api_key configured — cannot solve reCAPTCHA")
        return None

    if settings.captcha_service == "2captcha":
        return await _solve_2captcha(site_key, page_url, invisible, timeout_secs)
    elif settings.captcha_service == "anti-captcha":
        return await _solve_anticaptcha(site_key, page_url, invisible, timeout_secs)
    else:
        logger.error(f"[CAPTCHA] Unknown service: {settings.captcha_service}")
        return None


async def _solve_2captcha(
    site_key: str, page_url: str, invisible: bool, timeout_secs: int
) -> str | None:
    """Solve via 2captcha.com API."""
    api_key = settings.captcha_api_key
    t0 = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Submit captcha task
            params = {
                "key": api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1,
            }
            if invisible:
                params["invisible"] = 1

            resp = await client.post("https://2captcha.com/in.php", data=params)
            data = resp.json()

            if data.get("status") != 1:
                logger.error(f"[CAPTCHA] 2captcha submit failed: {data}")
                return None

            task_id = data["request"]
            logger.info(f"[CAPTCHA] 2captcha task submitted: {task_id}")

            # Step 2: Poll for result
            elapsed = 0
            poll_interval = 5
            await asyncio.sleep(15)  # 2captcha recommends waiting 15s before first poll

            while elapsed < timeout_secs:
                resp = await client.get(
                    "https://2captcha.com/res.php",
                    params={"key": api_key, "action": "get", "id": task_id, "json": 1},
                )
                result = resp.json()

                if result.get("status") == 1:
                    token = result["request"]
                    ms = (time.perf_counter() - t0) * 1000
                    logger.info(f"[CAPTCHA] 2captcha solved in {ms:.0f}ms (token: {token[:30]}...)")
                    return token
                elif result.get("request") == "CAPCHA_NOT_READY":
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                else:
                    logger.error(f"[CAPTCHA] 2captcha error: {result}")
                    return None

            logger.warning(f"[CAPTCHA] 2captcha timed out after {timeout_secs}s")
            return None

    except Exception as e:
        logger.error(f"[CAPTCHA] 2captcha exception: {e}")
        return None


async def _solve_anticaptcha(
    site_key: str, page_url: str, invisible: bool, timeout_secs: int
) -> str | None:
    """Solve via anti-captcha.com API."""
    api_key = settings.captcha_api_key
    t0 = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Create task
            payload = {
                "clientKey": api_key,
                "task": {
                    "type": "RecaptchaV2TaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                    "isInvisible": invisible,
                },
            }
            resp = await client.post(
                "https://api.anti-captcha.com/createTask", json=payload
            )
            data = resp.json()

            if data.get("errorId", 1) != 0:
                logger.error(f"[CAPTCHA] anti-captcha submit failed: {data}")
                return None

            task_id = data["taskId"]
            logger.info(f"[CAPTCHA] anti-captcha task: {task_id}")

            # Step 2: Poll
            elapsed = 0
            poll_interval = 5
            await asyncio.sleep(10)

            while elapsed < timeout_secs:
                resp = await client.post(
                    "https://api.anti-captcha.com/getTaskResult",
                    json={"clientKey": api_key, "taskId": task_id},
                )
                result = resp.json()

                if result.get("status") == "ready":
                    token = result["solution"]["gRecaptchaResponse"]
                    ms = (time.perf_counter() - t0) * 1000
                    logger.info(f"[CAPTCHA] anti-captcha solved in {ms:.0f}ms")
                    return token
                elif result.get("status") == "processing":
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                else:
                    logger.error(f"[CAPTCHA] anti-captcha error: {result}")
                    return None

            logger.warning(f"[CAPTCHA] anti-captcha timed out after {timeout_secs}s")
            return None

    except Exception as e:
        logger.error(f"[CAPTCHA] anti-captcha exception: {e}")
        return None
