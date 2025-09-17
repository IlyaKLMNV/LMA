# Use slim python image
FROM python:3.12-slim

# System deps (иногда нужны для сборки/работы pypdf/pandas и т.п.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl gosu && \
    rm -rf /var/lib/apt/lists/*

# Workdir inside container
WORKDIR /app

# Install deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Expose API port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
