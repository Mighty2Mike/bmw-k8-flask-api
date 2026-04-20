# -----------------------------------------------------------------
# Stage 1: Builder — install dependencies in an isolated layer
# -----------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install deps first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -----------------------------------------------------------------
# Stage 2: Runtime — minimal final image
# -----------------------------------------------------------------
FROM python:3.11-slim

# Create non-root user for security best practice
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY src/ .

# Drop to non-root user
USER appuser

EXPOSE 5000

# Use gunicorn for production-grade multi-worker serving
# Workers = (2 * CPU cores) + 1 is a common rule of thumb
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", \
     "--threads", "4", "--timeout", "60", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "main:app"]
