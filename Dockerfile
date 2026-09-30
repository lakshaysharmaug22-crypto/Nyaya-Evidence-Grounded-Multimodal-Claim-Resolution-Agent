FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 nyaya
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m ml.train_tabular && mkdir -p /app/data && chown -R nyaya:nyaya /app/data /app/ml/artifacts
USER nyaya
ENV PORT=8000 DATA_DIR=/app/data PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/ready',timeout=4)"
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
