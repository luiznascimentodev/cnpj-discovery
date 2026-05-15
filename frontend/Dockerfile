FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci --legacy-peer-deps

COPY . .

ARG VITE_API_URL=/api/v1
ARG VITE_ACCOUNT_ID=production-account
ARG VITE_USER_ID=production-user
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_ACCOUNT_ID=${VITE_ACCOUNT_ID}
ENV VITE_USER_ID=${VITE_USER_ID}

RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ > /dev/null 2>&1 || exit 1
