# ---- Stage 1: build ----
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# GITHUB_PAGES is intentionally unset here — this build serves at the
# container root (nginx), not under a GitHub Pages subpath.
RUN npm run build

# ---- Stage 2: serve ----
FROM nginx:alpine AS serve

COPY --from=build /app/out /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
