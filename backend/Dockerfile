FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY backend /app/backend
WORKDIR /app/backend
RUN python -m pip install --no-cache-dir -e .

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "forge.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
