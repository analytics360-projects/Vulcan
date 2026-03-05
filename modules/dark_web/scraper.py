"""Dark web site scraper — ported from nyx-crawler/dark_scrape.py"""
from html2text import HTML2Text
from bs4 import BeautifulSoup
import validators
import lxml.etree
import lxml.html
import re

from config import logger
from modules.dark_web.tor_utils import connect_tor, get_ip


class DarkScrape:
    def __init__(self):
        self.session = connect_tor()
        self.ip = get_ip(self.session)
        if self.ip:
            logger.info(f"DarkScrape connected: {self.ip}")
        self.response = ""
        self.url = ""
        self.soup = BeautifulSoup("", "html.parser")

    def emails(self):
        found = re.findall(r"[\w\.-]+@[\w\.-]+", str(self.response))
        return list(set(a for a in found if validators.email(a)))

    def links(self):
        links = [str(g.get("href")) for g in self.soup.find_all("a") if g.get("href")]
        links = [l for l in links if validators.url(l)]
        links += [
            a.replace(a.partition(".onion")[2], "")
            for a in re.findall(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", self.response)
        ]
        return list(set(links))

    def images(self):
        links = [g.get("src") for g in self.soup.find_all(lambda t: t.name in ("i", "img", "a")) if g.get("src")]
        return list(set(str(l) for l in links if validators.url(str(l))))

    def text(self):
        root = lxml.html.fromstring(self.response)
        lxml.etree.strip_elements(root, lxml.etree.Comment, "script", "head")
        text = lxml.html.tostring(root, method="text", encoding="unicode").replace("\r \r", "\n").replace("\n", " ").replace("\r", "")
        return text

    def title(self):
        return self.soup.title.text if self.soup.title else ""

    def bitcoins(self):
        return list(set(re.findall(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$", self.response)))

    def scrape(self, url):
        if not validators.url(url):
            logger.warning(f"Invalid URL: {url}")
            return self
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                self.response = r.text
            else:
                logger.warning(f"Response {r.status_code} for {url}")
        except Exception as e:
            logger.error(f"Scrape error: {e}")
            return self
        self.url = url
        self.soup = BeautifulSoup(self.response, "html.parser")
        return self

    @property
    def result(self):
        return {
            "url": self.url,
            "title": self.title(),
            "links": self.links(),
            "emails": self.emails(),
            "images": self.images(),
            "text": self.text(),
            "bitcoin": self.bitcoins(),
        }
