from fastapi import FastAPI, Query
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import os
import time
import re
import pandas as pd
import requests

app = FastAPI()


def configure_driver():
    """Configures and returns a Chrome WebDriver instance for macOS"""
    chrome_driver_path = ChromeDriverManager().install()

    options = Options()
    options.add_argument("--headless")  # Run in headless mode (no GUI)
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=Service(chrome_driver_path), options=options)
    return driver



def scrape_marketplace(city: str, product: str, min_price: int, max_price: int, days_listed: int):
    """Realiza el scraping de Facebook Marketplace y devuelve los datos extraídos"""
    driver = configure_driver()

    url = f'https://www.facebook.com/marketplace/{city}/search?query={product}&minPrice={min_price}&maxPrice={max_price}&daysSinceListed={days_listed}&exact=false'
    driver.get(url)
    print(url)
    time.sleep(5)

    try:
        close_button = driver.find_element(By.XPATH, '//div[@aria-label="Close" and @role="button"]')
        close_button.click()
    except:
        pass

    last_height = driver.execute_script("return document.body.scrollHeight")

    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(4)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()

    links = soup.find_all('a')
    product_links = [link for link in links if
                     product.lower() in link.text.lower() and city.lower() in link.text.lower()]

    extracted_data = []
    numeric_pattern = re.compile(r'\d[\d,.]*')

    for item in product_links:
        url = item.get('href')
        text = '\n'.join(item.stripped_strings)
        lines = text.split('\n')

        price = None
        for line in lines:
            match = numeric_pattern.search(line)
            if match:
                price_str = match.group()
                price = float(price_str.replace(',', ''))
                break

        if price is not None:
            title = lines[-2] if len(lines) > 1 else "No Title"
            location = lines[-1] if len(lines) > 0 else "No Location"

            extracted_data.append({
                'title': title,
                'price': price,
                'location': location,
                'url': "https://www.facebook.com" + re.sub(r'\?.*', '', url) if url else "No URL"
            })

    sorted_data = sorted(extracted_data, key=lambda x: x['title'])
    return sorted_data[:100]


@app.get("/search")
def search_marketplace(
        city: str = Query(..., description="City to search in"),
        product: str = Query(..., description="Product to search for"),
        min_price: int = Query(0, description="Minimum price"),
        max_price: int = Query(1000, description="Maximum price"),
        days_listed: int = Query(7, description="Days since listed")
):
    """Endpoint para buscar productos en Facebook Marketplace"""
    results = scrape_marketplace(city, product, min_price, max_price, days_listed)
    return {"results": results}
