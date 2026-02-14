FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create the persistent volume mount point
RUN mkdir -p /data

EXPOSE 8080

# Single worker: SQLite doesn't support concurrent writers,
# and APScheduler should only run in one process.
# Timeout is high because LLM calls can take a while.
CMD ["gunicorn", "bookbot.web:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "1", \
     "--timeout", "120"]
