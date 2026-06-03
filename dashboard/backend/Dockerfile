FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl && apt-get clean
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8099/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099"]
