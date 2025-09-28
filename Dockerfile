# Base image with Python 3.12
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install git (needed for git+https:// dependencies)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Cloud Run requires a PORT variable
ENV PORT=8080

# Entrypoint for the bot
CMD ["python", "main.py"]
