ARG DOCKER_MIRROR=dockerhub.timeweb.cloud
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY_FALLBACK=https://mirrors.aliyun.com/npm/

FROM ${DOCKER_MIRROR}/library/node:20-slim AS builder

ARG NPM_REGISTRY
ARG NPM_REGISTRY_FALLBACK
WORKDIR /app

COPY .npmrc ./
COPY package.json ./

RUN npm config set registry "${NPM_REGISTRY}" && \
    npm install --legacy-peer-deps --fetch-retries=5 --fetch-retry-mintimeout=20000 || \
    (echo "npm primary mirror failed, trying Aliyun..." && \
     npm config set registry "${NPM_REGISTRY_FALLBACK}" && \
     npm install --legacy-peer-deps)

COPY . .
RUN npm run build

FROM ${DOCKER_MIRROR}/library/nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
