FROM node:22-alpine

WORKDIR /app

COPY web/package*.json ./
RUN npm ci

COPY web ./

# Vacío por defecto -> el panel llama a la API con rutas relativas (mismo origen
# detrás de Caddy). Solo se sobreescribe si la API vive en otro dominio.
ARG NEXT_PUBLIC_API_BASE=
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npm", "run", "start"]
