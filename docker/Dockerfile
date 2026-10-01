FROM python:3.11-slim

WORKDIR /app

# Install git so repo-based ingestion and git clone operations work inside the container.
RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1+cpu" && \
    python -m pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
