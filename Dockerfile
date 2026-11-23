# Works on any Docker host (Google Cloud Run, Railway, a VPS…). Render uses render.yaml instead.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080 HTTPS_ONLY=1
CMD exec gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 8 --timeout 330
