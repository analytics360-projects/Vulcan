FROM python:3.11-slim

WORKDIR /app

# System dependencies: Chromium + Tor + headless support
# Also includes libs needed by undetected-chromedriver (downloads its own Chrome)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 curl unzip \
    tor obfs4proxy \
    chromium chromium-driver \
    libxi6 libnss3 libfontconfig1 libxss1 \
    libasound2t64 libatk-bridge2.0-0 libgtk-3-0 \
    libgbm1 libvulkan1 fonts-liberation \
    xvfb procps \
    build-essential g++ \
    && rm -rf /var/lib/apt/lists/*

# Tor config
RUN mkdir -p /var/lib/tor-data && chmod 700 /var/lib/tor-data
RUN printf "SocksPort 127.0.0.1:9050\nControlPort 127.0.0.1:9051\nDataDirectory /var/lib/tor-data\nRunAsDaemon 0\n" > /etc/tor/torrc

# Python dependencies
# Install numpy<2.0 first — server CPU lacks X86_V2 instructions required by numpy 2.x
# Then install everything else, using --no-build-isolation for packages that
# build from source (insightface) so they use our pinned numpy, not their own
COPY requirements.txt .
RUN pip install --no-cache-dir "numpy<2.0" \
    && pip install --no-cache-dir --no-build-isolation insightface>=0.7.3 \
    && pip install --no-cache-dir -r requirements.txt

# Application
COPY . .

ENV HEADLESS_BROWSER=true
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

EXPOSE 8000

# Start: Tor -> Xvfb -> Uvicorn
RUN printf '#!/bin/bash\ntor &\nsleep 5\nXvfb :99 -screen 0 1920x1080x24 &\nsleep 1\nexec uvicorn main:app --host 0.0.0.0 --port 8000\n' > /app/start.sh \
    && chmod +x /app/start.sh

CMD ["/bin/bash", "/app/start.sh"]
