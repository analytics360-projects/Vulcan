"""Shared Selenium WebDriver management — moved from services/webdriver.py"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from contextlib import contextmanager
import time

from config import settings, logger


@contextmanager
def get_driver():
    driver = None
    try:
        chrome_driver_path = ChromeDriverManager().install()
        options = Options()
        if settings.headless_browser:
            options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--window-size={settings.window_size}")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument(f"user-agent={settings.browser_user_agent}")
        driver = webdriver.Chrome(service=Service(chrome_driver_path), options=options)
        driver.set_page_load_timeout(settings.default_timeout)
        yield driver
    except Exception as e:
        logger.error(f"Error setting up WebDriver: {e}")
        raise
    finally:
        if driver:
            driver.quit()


def handle_facebook_dialogs(driver):
    dialog_buttons = [
        (By.XPATH, '//div[@aria-label="Close" and @role="button"]'),
        (By.XPATH, '//button[contains(text(), "Accept All")]'),
        (By.XPATH, '//button[contains(text(), "Accept")]'),
        (By.XPATH, '//button[contains(text(), "Aceptar")]'),
        (By.XPATH, '//button[contains(text(), "Continue")]'),
        (By.XPATH, '//button[contains(text(), "Continuar")]'),
        (By.XPATH, '//button[contains(text(), "Not Now")]'),
        (By.XPATH, '//button[contains(text(), "Ahora no")]'),
    ]
    try:
        for selector_type, selector in dialog_buttons:
            try:
                button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((selector_type, selector))
                )
                button.click()
                time.sleep(1)
                logger.info(f"Clicked dialog button: {selector}")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Error handling dialogs: {e}")


def wait_for_element(driver, by, selector, timeout=None):
    timeout = timeout or settings.default_timeout
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def wait_for_clickable(driver, by, selector, timeout=None):
    timeout = timeout or settings.default_timeout
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )
