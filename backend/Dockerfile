FROM node:20-alpine

WORKDIR /app/backend

ENV NODE_ENV=production
ENV PORT=5000

COPY backend/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY backend ./
COPY frontend ../frontend

RUN addgroup -S app && adduser -S app -G app && chown -R app:app /app

USER app

EXPOSE 5000

CMD ["node", "server.js"]
