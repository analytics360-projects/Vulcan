FROM python:3.11-slim

WORKDIR /app

# System dependencies: Chrome + Tor
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 curl unzip \
    tor obfs4proxy \
    libgconf-2-4 libxi6 libnss3 libfontconfig1 libxss1 \
    libappindicator3-1 libasound2 libatk-bridge2.0-0 libgtk-3-0 \
    xvfb procps \
    && rm -rf /var/lib/apt/lists/*

# Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Tor config
RUN mkdir -p /var/lib/tor-data && chmod 700 /var/lib/tor-data
RUN printf "SocksPort 127.0.0.1:9050\nControlPort 127.0.0.1:9051\nDataDirectory /var/lib/tor-data\nRunAsDaemon 0\n" > /etc/tor/torrc

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY . .

ENV HEADLESS_BROWSER=true
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Start: Tor → Xvfb → Uvicorn
RUN printf '#!/bin/bash\ntor &\nsleep 5\nXvfb :99 -screen 0 1920x1080x24 &\nsleep 1\nexec uvicorn main:app --host 0.0.0.0 --port 8000\n' > /app/start.sh \
    && chmod +x /app/start.sh

CMD ["/bin/bash", "/app/start.sh"]
