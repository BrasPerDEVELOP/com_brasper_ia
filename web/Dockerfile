FROM node:22-alpine

WORKDIR /app

RUN npm install -g pnpm@10.15.1
COPY web/package.json web/pnpm-lock.yaml web/.npmrc ./
RUN pnpm install --frozen-lockfile

COPY web ./

# Vacío por defecto -> el panel llama a la API con rutas relativas (mismo origen
# detrás de Caddy). Solo se sobreescribe si la API vive en otro dominio.
ARG NEXT_PUBLIC_API_BASE=
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN pnpm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["pnpm", "run", "start"]
