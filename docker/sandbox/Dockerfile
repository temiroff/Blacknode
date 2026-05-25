FROM python:3.12-slim

# Pre-install common libraries so learned nodes can use them
# even with --network=none at runtime
RUN pip install --no-cache-dir \
    requests==2.32.* \
    beautifulsoup4==4.12.* \
    feedparser==6.0.* \
    lxml==5.2.* \
    python-dateutil==2.9.* \
    pyyaml==6.0.* \
    pillow==10.4.*

WORKDIR /workspace
USER nobody
