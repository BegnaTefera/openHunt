FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Next.js bakes the /api proxy target in at build time.
ARG API_URL=http://localhost:8000
ENV API_URL=$API_URL
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
