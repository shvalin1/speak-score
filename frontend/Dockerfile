# ビルドコンテキストはリポジトリルート（@shared が ../shared を参照するため）。
#   docker build -f frontend/Dockerfile .
# Stage 1: Build
FROM node:20-slim AS builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
WORKDIR /app
COPY shared ./shared
COPY frontend ./frontend
WORKDIR /app/frontend
# Firebase Web 設定はビルド時に bundle へ焼き込む（Vite は import.meta.env.VITE_* を静的展開）。
# web apiKey は公開値（クライアントに配布される前提の識別子）なので build-arg で渡してよい。
# 未指定だと本番で Firebase 初期化が undefined になり認証が機能しない。
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ENV VITE_FIREBASE_API_KEY=${VITE_FIREBASE_API_KEY}
ENV VITE_FIREBASE_AUTH_DOMAIN=${VITE_FIREBASE_AUTH_DOMAIN}
ENV VITE_FIREBASE_PROJECT_ID=${VITE_FIREBASE_PROJECT_ID}
RUN npm run build

# Stage 2: Serve（Nginx が静的配信 + /api を backend へ reverse proxy）
# 公式イメージの templates 機構で ${BACKEND_URL} を envsubst 展開（$host 等は環境変数に無いので保持）。
FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/frontend/dist /usr/share/nginx/html
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
