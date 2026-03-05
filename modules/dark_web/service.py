"""Dark web search — ported from nyx-crawler/dark_search.py"""
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote
import re
import time
import logging
from datetime import datetime, timedelta

from config import settings, logger
from modules.dark_web.tor_utils import connect_tor, change_ip, get_ip


class DarkSearch:
    def __init__(self):
        self.timeout = settings.tor_timeout
        self.request_delay = settings.tor_request_delay
        self.max_retries = settings.tor_max_retries
        self.session = None
        self.last_request_time = datetime.now() - timedelta(seconds=self.request_delay)
        self._setup_tor_session()

    def _setup_tor_session(self):
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                logger.info(f"Connecting to Tor (attempt {retry_count + 1}/{self.max_retries})")
                self.session = connect_tor()
                time.sleep(2)
                test_ip = get_ip(self.session)
                if test_ip:
                    logger.info(f"Connected to Tor: {test_ip}")
                    self.session.headers.update({
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "DNT": "1",
                    })
                    return
                retry_count += 1
                time.sleep(5)
            except Exception as e:
                logger.error(f"Tor setup error: {e}")
                retry_count += 1
                time.sleep(5)
        raise ConnectionError("Unable to establish Tor connection")

    def _throttle(self):
        elapsed = (datetime.now() - self.last_request_time).total_seconds()
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = datetime.now()

    def _get(self, url):
        self._throttle()
        for attempt in range(self.max_retries):
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r
                if r.status_code in (429, 403):
                    change_ip()
                attempt += 1
                time.sleep(2)
            except Exception as e:
                logger.error(f"Request error ({attempt+1}/{self.max_retries}): {e}")
                time.sleep(2)
        return None

    @staticmethod
    def _clean_query(query):
        sanitized = re.sub(r"[^a-zA-Z0-9\s\-_]", "", query)
        return "+".join([quote(q) for q in sanitized.split()])

    @staticmethod
    def _beautify(text):
        return " ".join(text.replace("\n", " ").split()) if text else ""

    @staticmethod
    def _extract_date(text):
        patterns = [
            r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
            r"\d{4}[-/]\d{1,2}[-/]\d{1,2}",
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    def torch_search(self, query):
        SITE = "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion"
        q = self._clean_query(query)
        r = self._get(f"{SITE}/search?query={q}&action=search")
        if not r:
            r = self._get(f"{SITE}/4a1f6b371c/search.cgi?q={q}&cmd=Search!&ps=20")
        if not r:
            return []

        results, links = [], []
        try:
            soup = BeautifulSoup(r.text, "html.parser")
            blocks = soup.find_all("div", {"class": "result"}) or soup.find_all("div", {"class": "searchResults"})
            if blocks:
                for block in blocks:
                    title_el = block.find("h5") or block.find("h4") or block.find("a")
                    if not title_el:
                        continue
                    link_el = title_el if title_el.name == "a" else title_el.find("a")
                    if not link_el:
                        continue
                    link = unquote(link_el.get("href", ""))
                    if not link.startswith("http"):
                        link = SITE + link
                    if link in links:
                        continue
                    links.append(link)
                    desc_el = block.find("p") or block.find("div", {"class": "description"})
                    date = self._extract_date(desc_el.text) if desc_el else None
                    results.append({"title": self._beautify(link_el.text), "link": link, "date": date, "thumbnail": None})
            else:
                for dl in soup.find_all("dl"):
                    dt = dl.find("dt")
                    if not dt:
                        continue
                    a = dt.find("a")
                    if not a:
                        continue
                    link = unquote(a.get("href", ""))
                    if not link.startswith("http"):
                        link = SITE + link
                    if link in links:
                        continue
                    links.append(link)
                    dd = dl.find("dd")
                    date = self._extract_date(dd.text) if dd else None
                    results.append({"title": self._beautify(a.text), "link": link, "date": date, "thumbnail": None})
        except Exception as e:
            logger.error(f"Torch parse error: {e}")
        return results

    def onion_land_search(self, query):
        SITE = "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search"
        q = self._clean_query(query)
        r = self._get(f"{SITE}?q={q}")
        if not r:
            return []

        results, links = [], []
        try:
            soup = BeautifulSoup(r.text, "html.parser")
            for block in soup.find_all("div", {"class": "result-block"}):
                a = block.find("a")
                if a and a.get("data-category") == "sponsored-text":
                    continue
                title = self._beautify(a.text) if a else ""
                link_div = block.find("div", {"class": "link"})
                link = self._beautify(link_div.text) if link_div else ""
                if link in links:
                    continue
                links.append(link)
                desc_div = block.find("div", {"class": "desc"})
                date = self._extract_date(desc_div.text) if desc_div else None
                results.append({"title": title, "link": link, "date": date, "thumbnail": None})
        except Exception as e:
            logger.error(f"OnionLand parse error: {e}")
        return results

    def search(self, query, engines=None):
        if not query:
            return []
        available = {"torch": self.torch_search, "onion_land": self.onion_land_search}
        engines = [e for e in (engines or available.keys()) if e in available]
        if not engines:
            return []

        all_results, link_scores = [], {}
        for eng in engines:
            try:
                eng_results = available[eng](query)
                for r in eng_results:
                    r["engine"] = eng
                    link_scores[r.get("link", "")] = link_scores.get(r.get("link", ""), 0) + 1
                all_results.extend(eng_results)
            except Exception as e:
                logger.error(f"Engine {eng} error: {e}")

        for r in all_results:
            r["score"] = link_scores.get(r.get("link"), 0)

        seen, unique = set(), []
        for r in sorted(all_results, key=lambda x: x.get("score", 0), reverse=True):
            link = r.get("link")
            if link and link not in seen:
                seen.add(link)
                unique.append(r)
        return unique


# Lazy singleton
_searcher: DarkSearch | None = None


def get_searcher() -> DarkSearch:
    global _searcher
    if _searcher is None:
        _searcher = DarkSearch()
    return _searcher
