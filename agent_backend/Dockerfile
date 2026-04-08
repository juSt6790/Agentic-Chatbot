# ====== Stage 1: Build dependencies ======
FROM python:3.12-slim AS builder
 
# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc bash \
&& rm -rf /var/lib/apt/lists/*
 
# WORKDIR /app/mcp_gmail
 
# Copy dependency list
COPY requirements.txt .
 
# Install dependencies to a separate folder
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
 
 
# ====== Stage 2: Final lightweight image ======
FROM python:3.12-slim AS final
 
# Set the working directory
# WORKDIR /app/mcp_gmail
 
# Install bash (for running shell scripts if needed)
RUN apt-get update && apt-get install -y --no-install-recommends bash \
&& rm -rf /var/lib/apt/lists/*
 
# Copy installed dependencies
COPY --from=builder /install /usr/local
 
# Copy the full application code
COPY . .

# Remove pre-existing .env, if any
RUN rm -f .env

# Force copy .env.test → .env inside Docker
COPY .env.test .env
RUN rm -f .env.*
 
# Expose the API port (if needed)
EXPOSE 80 8000
 
# Environment variables for Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/
 
RUN pwd && ls -lart
 
# Set Permissions
 RUN chmod +x start_cosi_app.sh
 # RUN chmod 644 certs/*.pem

 RUN pwd && ls -lart app
# Command to run the application
CMD ["sh", "start_cosi_app.sh"]
