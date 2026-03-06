"""Social Account Manager — multi-platform singleton for rotating login sessions"""
import json
import random
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import psycopg2
import psycopg2.extras
from selenium.webdriver.common.by import By

from config import settings, logger
from shared.webdriver import human_delay


_COOLDOWN_MINUTES = 15
_COOLDOWN_THRESHOLD = 3
_BAN_THRESHOLD = 10

# Supported platforms
PLATFORMS = ["facebook", "instagram", "tiktok"]


class SocialAccountManager:
    """Manages social media accounts for session rotation across platforms."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def _get_conn(self):
        conn_str = settings.postgres_main_connection_string or settings.postgres_connection_string
        return psycopg2.connect(conn_str)

    def init(self):
        """Initialize the manager — verify DB connection."""
        if self._initialized:
            return
        try:
            conn = self._get_conn()
            conn.close()
            self._initialized = True
            stats = self.get_stats_all()
            logger.info(f"SocialAccountManager initialized — {stats}")
        except Exception as e:
            logger.warning(f"SocialAccountManager init failed: {e}")
            raise

    # ── Account selection ──

    def get_account(self, platform: str) -> Optional[Dict[str, Any]]:
        """Round-robin selection of an available account for given platform."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM social_accounts
                    WHERE platform = %s
                      AND status = 'active'
                      AND (cooldown_until IS NULL OR cooldown_until < NOW())
                    ORDER BY last_used ASC NULLS FIRST
                    LIMIT 1
                """, (platform,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def get_all_accounts(self, platform: str = None) -> List[Dict[str, Any]]:
        """Return all accounts, optionally filtered by platform."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if platform:
                    cur.execute("SELECT * FROM social_accounts WHERE platform = %s ORDER BY id", (platform,))
                else:
                    cur.execute("SELECT * FROM social_accounts ORDER BY platform, id")
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_account_by_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM social_accounts WHERE id = %s", (account_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    # ── Status updates ──

    def mark_used(self, account_id: int):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE social_accounts SET last_used = NOW() WHERE id = %s", (account_id,))
            conn.commit()
        finally:
            conn.close()

    def mark_failed(self, account_id: int):
        """Increment fail_count. Cooldown after threshold, ban after ban threshold."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "UPDATE social_accounts SET fail_count = fail_count + 1 WHERE id = %s RETURNING fail_count",
                    (account_id,),
                )
                row = cur.fetchone()
                if row:
                    fail_count = row["fail_count"]
                    if fail_count >= _BAN_THRESHOLD:
                        cur.execute("UPDATE social_accounts SET status = 'banned' WHERE id = %s", (account_id,))
                        logger.warning(f"Social account {account_id} banned after {fail_count} failures")
                    elif fail_count >= _COOLDOWN_THRESHOLD:
                        cooldown_until = datetime.now() + timedelta(minutes=_COOLDOWN_MINUTES)
                        cur.execute(
                            "UPDATE social_accounts SET status = 'cooldown', cooldown_until = %s WHERE id = %s",
                            (cooldown_until, account_id),
                        )
                        logger.info(f"Social account {account_id} in cooldown until {cooldown_until}")
            conn.commit()
        finally:
            conn.close()

    def mark_success(self, account_id: int):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE social_accounts SET fail_count = 0, status = 'active', cooldown_until = NULL WHERE id = %s",
                    (account_id,),
                )
            conn.commit()
        finally:
            conn.close()

    # ── Cookies ──

    def save_cookies(self, account_id: int, cookies: list):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE social_accounts SET cookies_json = %s WHERE id = %s", (json.dumps(cookies), account_id))
            conn.commit()
        finally:
            conn.close()

    def get_cookies(self, account_id: int) -> Optional[list]:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT cookies_json FROM social_accounts WHERE id = %s", (account_id,))
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
                return None
        finally:
            conn.close()

    # ── Account CRUD ──

    def add_account(self, platform: str, email: str, password: str, notes: str = None) -> int:
        if platform not in PLATFORMS:
            raise ValueError(f"Platform '{platform}' not supported. Use: {PLATFORMS}")
        ua = random.choice([
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ])
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO social_accounts (platform, email, password, user_agent, notes)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (platform, email, password, ua, notes),
                )
                account_id = cur.fetchone()[0]
            conn.commit()
            return account_id
        finally:
            conn.close()

    def delete_account(self, account_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM social_accounts WHERE id = %s", (account_id,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    def update_status(self, account_id: int, status: str) -> bool:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE social_accounts SET status = %s WHERE id = %s", (status, account_id))
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        finally:
            conn.close()

    def get_stats(self, platform: str) -> Dict[str, int]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status = 'active' AND (cooldown_until IS NULL OR cooldown_until < NOW())) AS active,
                        COUNT(*) FILTER (WHERE status = 'cooldown' OR (cooldown_until IS NOT NULL AND cooldown_until >= NOW())) AS cooldown,
                        COUNT(*) FILTER (WHERE status = 'banned') AS banned,
                        COUNT(*) FILTER (WHERE status = 'disabled') AS disabled
                    FROM social_accounts
                    WHERE platform = %s
                """, (platform,))
                return dict(cur.fetchone())
        finally:
            conn.close()

    def get_stats_all(self) -> Dict[str, Dict[str, int]]:
        """Stats grouped by platform."""
        result = {}
        for p in PLATFORMS:
            result[p] = self.get_stats(p)
        return result

    # ── Platform-specific login logic ──

    def login(self, driver, account: Dict[str, Any]) -> bool:
        """Route to platform-specific login."""
        platform = account["platform"]
        if platform == "facebook":
            return self._login_facebook(driver, account)
        elif platform == "instagram":
            return self._login_instagram(driver, account)
        elif platform == "tiktok":
            return self._login_tiktok(driver, account)
        else:
            logger.error(f"No login handler for platform: {platform}")
            return False

    def ensure_logged_in(self, driver, platform: str) -> bool:
        """Check if logged in. If not, pick an account and login."""
        checker = {
            "facebook": self._is_logged_in_facebook,
            "instagram": self._is_logged_in_instagram,
            "tiktok": self._is_logged_in_tiktok,
        }
        check_fn = checker.get(platform)
        if check_fn and check_fn(driver):
            return True

        account = self.get_account(platform)
        if not account:
            logger.warning(f"No available {platform} accounts for login")
            return False

        return self.login(driver, account)

    # ── Facebook ──

    def _login_facebook(self, driver, account: Dict[str, Any]) -> bool:
        account_id = account["id"]

        # Try cookie-based login first
        cookies = self.get_cookies(account_id)
        if cookies:
            try:
                driver.get("https://www.facebook.com/")
                human_delay(1.0, 2.0)
                for cookie in cookies:
                    cookie.pop("sameSite", None)
                    cookie.pop("httpOnly", None)
                    try:
                        driver.add_cookie(cookie)
                    except Exception:
                        continue
                driver.refresh()
                human_delay(2.0, 4.0)
                if self._is_logged_in_facebook(driver):
                    logger.info(f"FB cookie login succeeded for account {account_id}")
                    self.mark_used(account_id)
                    self.mark_success(account_id)
                    self.save_cookies(account_id, driver.get_cookies())
                    return True
            except Exception as e:
                logger.warning(f"Cookie login error for FB account {account_id}: {e}")

        # Email/password fallback
        try:
            driver.get("https://www.facebook.com/login")
            human_delay(2.0, 4.0)
            email_field = driver.find_element(By.ID, "email")
            email_field.clear()
            for char in account["email"]:
                email_field.send_keys(char)
                human_delay(0.05, 0.15)
            human_delay(0.5, 1.0)
            pass_field = driver.find_element(By.ID, "pass")
            pass_field.clear()
            for char in account["password"]:
                pass_field.send_keys(char)
                human_delay(0.05, 0.15)
            human_delay(0.5, 1.5)
            login_btn = driver.find_element(By.CSS_SELECTOR, "button[name='login'], input[name='login'], button[type='submit']")
            login_btn.click()
            human_delay(3.0, 6.0)
            if self._is_logged_in_facebook(driver):
                logger.info(f"FB credential login succeeded for account {account_id}")
                self._mark_login_success(account_id)
                return True
            else:
                logger.warning(f"FB credential login failed for account {account_id}")
                self.mark_failed(account_id)
                return False
        except Exception as e:
            logger.error(f"FB login error for account {account_id}: {e}")
            self.mark_failed(account_id)
            return False

    def _is_logged_in_facebook(self, driver) -> bool:
        try:
            url = driver.current_url.lower()
            if "/login" in url or "checkpoint" in url:
                return False
            page_source = driver.page_source
            indicators = [
                'aria-label="Facebook"', 'aria-label="Your profile"',
                'aria-label="Tu perfil"', 'aria-label="Account"',
                'aria-label="Cuenta"', "/me",
            ]
            return any(ind in page_source for ind in indicators)
        except Exception:
            return False

    # ── Instagram ──

    def _login_instagram(self, driver, account: Dict[str, Any]) -> bool:
        account_id = account["id"]

        # Try cookie-based login first
        cookies = self.get_cookies(account_id)
        if cookies:
            try:
                driver.get("https://www.instagram.com/")
                human_delay(1.0, 2.0)
                for cookie in cookies:
                    cookie.pop("sameSite", None)
                    cookie.pop("httpOnly", None)
                    try:
                        driver.add_cookie(cookie)
                    except Exception:
                        continue
                driver.refresh()
                human_delay(2.0, 4.0)
                if self._is_logged_in_instagram(driver):
                    logger.info(f"IG cookie login succeeded for account {account_id}")
                    self.mark_used(account_id)
                    self.mark_success(account_id)
                    self.save_cookies(account_id, driver.get_cookies())
                    return True
            except Exception as e:
                logger.warning(f"Cookie login error for IG account {account_id}: {e}")

        # Email/password fallback
        try:
            driver.get("https://www.instagram.com/accounts/login/")
            human_delay(2.0, 4.0)

            # Dismiss cookie banner if present
            for btn_text in ["Allow All Cookies", "Allow essential and optional cookies", "Permitir cookies", "Accept", "Aceptar"]:
                try:
                    btn = driver.find_element(By.XPATH, f'//button[contains(text(), "{btn_text}")]')
                    btn.click()
                    human_delay(0.5, 1.5)
                    break
                except Exception:
                    pass

            email_field = driver.find_element(By.CSS_SELECTOR, "input[name='username']")
            email_field.clear()
            for char in account["email"]:
                email_field.send_keys(char)
                human_delay(0.05, 0.15)
            human_delay(0.5, 1.0)

            pass_field = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
            pass_field.clear()
            for char in account["password"]:
                pass_field.send_keys(char)
                human_delay(0.05, 0.15)
            human_delay(0.5, 1.5)

            login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_btn.click()
            human_delay(4.0, 7.0)

            # Dismiss "Save Login Info" or "Not Now" popups
            for btn_text in ["Not Now", "Ahora no", "Not now"]:
                try:
                    btn = driver.find_element(By.XPATH, f'//button[contains(text(), "{btn_text}")]')
                    btn.click()
                    human_delay(1.0, 2.0)
                except Exception:
                    pass

            if self._is_logged_in_instagram(driver):
                logger.info(f"IG credential login succeeded for account {account_id}")
                self._mark_login_success(account_id)
                return True
            else:
                logger.warning(f"IG credential login failed for account {account_id}")
                self.mark_failed(account_id)
                return False
        except Exception as e:
            logger.error(f"IG login error for account {account_id}: {e}")
            self.mark_failed(account_id)
            return False

    def _is_logged_in_instagram(self, driver) -> bool:
        try:
            url = driver.current_url.lower()
            if "/accounts/login" in url or "/challenge" in url:
                return False
            page_source = driver.page_source
            indicators = [
                'aria-label="Home"', 'aria-label="Inicio"',
                'aria-label="Search"', 'aria-label="Buscar"',
                'aria-label="New post"', 'aria-label="Nueva publicación"',
                '"viewer"', 'coreSidebarListItems',
            ]
            return any(ind in page_source for ind in indicators)
        except Exception:
            return False

    # ── TikTok ──

    def _login_tiktok(self, driver, account: Dict[str, Any]) -> bool:
        account_id = account["id"]

        # Try cookie-based login first
        cookies = self.get_cookies(account_id)
        if cookies:
            try:
                driver.get("https://www.tiktok.com/")
                human_delay(1.0, 2.0)
                for cookie in cookies:
                    cookie.pop("sameSite", None)
                    cookie.pop("httpOnly", None)
                    try:
                        driver.add_cookie(cookie)
                    except Exception:
                        continue
                driver.refresh()
                human_delay(2.0, 4.0)
                if self._is_logged_in_tiktok(driver):
                    logger.info(f"TikTok cookie login succeeded for account {account_id}")
                    self.mark_used(account_id)
                    self.mark_success(account_id)
                    self.save_cookies(account_id, driver.get_cookies())
                    return True
            except Exception as e:
                logger.warning(f"Cookie login error for TikTok account {account_id}: {e}")

        # TikTok login via email — navigate to login page
        try:
            driver.get("https://www.tiktok.com/login/phone-or-email/email")
            human_delay(2.0, 4.0)

            email_field = driver.find_element(By.CSS_SELECTOR, "input[name='username'], input[placeholder*='email'], input[placeholder*='Email'], input[type='text']")
            email_field.clear()
            for char in account["email"]:
                email_field.send_keys(char)
                human_delay(0.05, 0.15)
            human_delay(0.5, 1.0)

            pass_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            pass_field.clear()
            for char in account["password"]:
                pass_field.send_keys(char)
                human_delay(0.05, 0.15)
            human_delay(0.5, 1.5)

            login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button[data-e2e='login-button']")
            login_btn.click()
            human_delay(4.0, 7.0)

            if self._is_logged_in_tiktok(driver):
                logger.info(f"TikTok credential login succeeded for account {account_id}")
                self._mark_login_success(account_id)
                return True
            else:
                logger.warning(f"TikTok credential login failed for account {account_id}")
                self.mark_failed(account_id)
                return False
        except Exception as e:
            logger.error(f"TikTok login error for account {account_id}: {e}")
            self.mark_failed(account_id)
            return False

    def _is_logged_in_tiktok(self, driver) -> bool:
        try:
            url = driver.current_url.lower()
            if "/login" in url:
                return False
            page_source = driver.page_source
            indicators = [
                'data-e2e="profile-icon"', 'data-e2e="inbox"',
                'data-e2e="upload-icon"', '"uniqueId"',
            ]
            return any(ind in page_source for ind in indicators)
        except Exception:
            return False

    # ── Shared helpers ──

    def _mark_login_success(self, account_id: int):
        """Mark login successful: update timestamps, save cookies."""
        self.mark_used(account_id)
        self.mark_success(account_id)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE social_accounts SET last_login = NOW() WHERE id = %s", (account_id,))
            conn.commit()
        finally:
            conn.close()


# Module-level singleton
social_account_manager = SocialAccountManager()
