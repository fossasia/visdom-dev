# Build context is the repo root (needs frontend/ and deploy/).
# Stage 1 — build the console SPA.
FROM node:22-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2 — nginx serving the built SPA and reverse-proxying the backends.
FROM nginx:1.27-alpine
COPY --from=frontend /src/dist /usr/share/nginx/html
# Rendered by the image's envsubst entrypoint using the environment (see compose).
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/security-headers.conf /etc/nginx/security-headers.conf
COPY deploy/nginx-main.conf /etc/nginx/nginx.conf
