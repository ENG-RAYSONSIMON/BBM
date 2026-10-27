FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=https://bbmapi.mauzo.tz/api/v1
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_APP_URL=https://bbm.mauzo.tz
ENV VITE_APP_URL=$VITE_APP_URL
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN mkdir -p /srv/static /srv/media \
    && chown 10001:10001 /srv/static /srv/media
EXPOSE 80
