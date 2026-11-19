FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npx ng build --configuration production

FROM nginx:1.27-alpine
ENV API_UPSTREAM=http://users-api:8080
# nginx image runs envsubst on /etc/nginx/templates/*.template at start
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/web/browser /usr/share/nginx/html
EXPOSE 80
