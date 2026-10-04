FROM node:24-slim AS frontend

WORKDIR /frontend
COPY src/web/package.json src/web/package-lock.json ./
RUN npm ci
COPY src/web/ ./
RUN npm run build
RUN npm install -g https://s3.us-south.cloud-object-storage.appdomain.cloud/bob-shell/bobshell-2.0.5.tgz

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_ENV=production \
    HOME=/app \
    PYTHONPATH=/app/src

COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/bobshell/dist/bob.js /usr/local/bin/bob

WORKDIR /app
COPY src/requirements.txt ./src/requirements.txt
RUN python -m pip install --no-cache-dir -r src/requirements.txt
COPY src/ ./src/
COPY demo_data/ ./demo_data/
COPY .bob/rules-osint-analyst/ ./.bob/rules-osint-analyst/
COPY --from=frontend /frontend/dist ./src/web/dist

RUN mkdir -p /app/data /app/.bob && chown -R 10001:10001 /app
USER 10001:10001

CMD ["python", "src/main.py"]