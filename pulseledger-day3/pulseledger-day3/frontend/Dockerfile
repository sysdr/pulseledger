FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Inlined into the browser bundle at build time: must be the HOST address.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8003
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npx next build
EXPOSE 4003
CMD ["npx", "next", "start", "-p", "4003"]
