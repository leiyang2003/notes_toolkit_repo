FROM node:20-alpine AS deps

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

FROM node:20-alpine AS build

WORKDIR /frontend
COPY --from=deps /frontend/node_modules ./node_modules
COPY frontend ./
COPY packages /packages
RUN mkdir -p /frontend/public
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /frontend
ENV NODE_ENV=production

COPY --from=build /frontend/.next/standalone ./
COPY --from=build /frontend/.next/static ./.next/static
COPY --from=build /frontend/public ./public

EXPOSE 10000
CMD ["node", "server.js"]
