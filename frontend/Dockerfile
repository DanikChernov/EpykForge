FROM node:24-alpine AS build
WORKDIR /app
ARG VITE_FORGE_API_URL
ENV VITE_FORGE_API_URL=$VITE_FORGE_API_URL
COPY frontend/package*.json ./
RUN npm install
COPY frontend ./
RUN test -n "$VITE_FORGE_API_URL" || (echo "VITE_FORGE_API_URL is required for the production frontend image" && exit 1)
RUN case "$VITE_FORGE_API_URL" in http://*|https://*) ;; *) echo "VITE_FORGE_API_URL must be an absolute http(s) URL" && exit 1 ;; esac
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
