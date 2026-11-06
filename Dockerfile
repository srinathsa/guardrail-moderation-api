FROM python:3.11-slim

WORKDIR /app

# System deps for Pillow / psycopg2 build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install core deps always. Heavy ML deps (torch/transformers/detoxify) are
# installed too by default; if you want a lightweight stub-only image
# (no ML libs, faster build), build with:
#   docker build --build-arg SKIP_ML=1 .
ARG SKIP_ML=0
RUN if [ "$SKIP_ML" = "1" ]; then \
      grep -vE '^(torch|transformers|detoxify)' requirements.txt > requirements.min.txt && \
      pip install --no-cache-dir -r requirements.min.txt ; \
    else \
      pip install --no-cache-dir -r requirements.txt ; \
    fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
