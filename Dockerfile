FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    anthropic>=0.100.0 \
    fastapi>=0.115.0 \
    openai>=1.0.0 \
    httpx>=0.28.0 \
    psycopg[binary]>=3.2.0 \
    pydantic-settings>=2.6.0 \
    python-dotenv>=1.0.1 \
    pyyaml>=6.0.2 \
    requests>=2.32.0 \
    shapely>=2.0.6 \
    "uvicorn[standard]>=0.32.0"

COPY api/ api/
COPY sources/ sources/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
