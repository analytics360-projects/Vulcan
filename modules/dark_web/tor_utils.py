"""Tor connection utilities — ported from nyx-crawler/utils.py"""
from stem.control import Controller
from stem import Signal
import requests
import json

from config import settings, logger


def get_ip(session):
    try:
        r = session.get("http://httpbin.org/ip", timeout=settings.tor_timeout)
        if r.status_code == 200:
            return json.loads(r.text).get("origin")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Could not locate IP: {e}")
    return None


def connect_tor():
    session = requests.session()
    proxy = f"socks5h://127.0.0.1:{settings.tor_socks_port}"
    session.proxies = {"http": proxy, "https": proxy}
    return session


def change_ip():
    try:
        with Controller.from_port(address="127.0.0.1", port=settings.tor_control_port) as controller:
            controller.authenticate(password=settings.tor_control_password or None)
            controller.signal(Signal.NEWNYM)
        logger.info("Tor circuit changed")
    except Exception as e:
        logger.error(f"Error changing Tor IP: {e}")
