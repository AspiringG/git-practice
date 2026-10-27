# Single image: builds the React frontend, then serves it together with the FastAPI backend on port 8000.

FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29"
COPY backend/app ./app
COPY --from=frontend /src/frontend/dist /app/frontend/dist
# SQLite database lives here; mount a volume to keep data between restarts.
VOLUME /app/backend/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
