# Use official slim Python image
FROM python:3.12-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# System dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python -m pip install --upgrade pip

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project (gemma4 folder with manage.py and apps)
COPY . .

# Navigate to Django project root where manage.py is located
WORKDIR /app/gemma4

# Collect static files (ignore errors if Django not fully configured)
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

# Expose port
EXPOSE 8080

# Run gunicorn, binding to $PORT environment variable (Cloud Run default is 8080)
CMD ["sh", "-c", "gunicorn gemma4.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 4 --timeout 120"]