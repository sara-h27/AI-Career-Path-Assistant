FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# models/ holds the embedding model (copied with the code); without it fastembed downloads on first start.
ENV MODEL_CACHE_DIR=/app/models
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
