#updated dockerfile. previous one used ubuntu:latest and apt-installed python (with a base of even more cves) and did chown in a separate layer, now it's a slim official python image and copy --chown for a safer build. in short, that one had a soul...
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -m -u 10001 appuser
WORKDIR /app
COPY --chown=appuser:appuser requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt
COPY --chown=appuser:appuser app/ /app
USER appuser
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1',8080)); s.close()"
EXPOSE 8080
CMD ["python", "app.py"]
