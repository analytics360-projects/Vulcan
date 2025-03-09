from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from contextlib import contextmanager
import time

from config import (
    HEADLESS, WINDOW_SIZE, DEFAULT_TIMEOUT, BROWSER_USER_AGENT, logger
)


@contextmanager
def get_driver():
    """
    Context manager for WebDriver to ensure proper setup and cleanup.

    Yields:
        webdriver.Chrome: A configured Chrome WebDriver instance
    """
    driver = None
    try:
        chrome_driver_path = ChromeDriverManager().install()

        options = Options()
        if HEADLESS:
            options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--window-size={WINDOW_SIZE}")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        # Use a realistic user agent
        options.add_argument(f"user-agent={BROWSER_USER_AGENT}")

        driver = webdriver.Chrome(service=Service(chrome_driver_path), options=options)
        driver.set_page_load_timeout(DEFAULT_TIMEOUT)
        yield driver
    except Exception as e:
        logger.error(f"Error setting up WebDriver: {str(e)}")
        raise
    finally:
        if driver:
            driver.quit()


def handle_facebook_dialogs(driver):
    """
    Handle various Facebook login/cookie dialogs that might appear.

    Args:
        driver (webdriver.Chrome): The WebDriver instance
    """
    try:
        # List of possible dialog selectors and buttons
        dialog_buttons = [
            (By.XPATH, '//div[@aria-label="Close" and @role="button"]'),
            (By.XPATH, '//button[contains(text(), "Accept All")]'),
            (By.XPATH, '//button[contains(text(), "Accept")]'),
            (By.XPATH, '//button[contains(text(), "Aceptar")]'),
            (By.XPATH, '//button[contains(text(), "Continue")]'),
            (By.XPATH, '//button[contains(text(), "Continuar")]'),
            (By.XPATH, '//button[contains(text(), "Not Now")]'),
            (By.XPATH, '//button[contains(text(), "Ahora no")]')
        ]

        for selector_type, selector in dialog_buttons:
            try:
                # Short timeout to quickly check for each button
                button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((selector_type, selector))
                )
                button.click()
                time.sleep(1)
                logger.info(f"Clicked dialog button: {selector}")
            except:
                pass
    except Exception as e:
        logger.warning(f"Error handling dialogs: {str(e)}")


def wait_for_element(driver, by, selector, timeout=DEFAULT_TIMEOUT):
    """
    Wait for an element to be present in the DOM.

    Args:
        driver (webdriver.Chrome): The WebDriver instance
        by (selenium.webdriver.common.by.By): The method to locate the element
        selector (str): The selector string
        timeout (int): Maximum time to wait for the element, in seconds

    Returns:
        WebElement: The found element

    Raises:
        TimeoutException: If the element is not found within the timeout
    """
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def wait_for_clickable(driver, by, selector, timeout=DEFAULT_TIMEOUT):
    """
    Wait for an element to be clickable.

    Args:
        driver (webdriver.Chrome): The WebDriver instance
        by (selenium.webdriver.common.by.By): The method to locate the element
        selector (str): The selector string
        timeout (int): Maximum time to wait for the element, in seconds

    Returns:
        WebElement: The found element

    Raises:
        TimeoutException: If the element is not found or not clickable within the timeout
    """
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )
