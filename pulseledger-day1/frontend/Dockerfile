FROM node:22-slim
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npx next build
EXPOSE 4001
ENV NEXT_PUBLIC_API_BASE=http://backend:8001
CMD ["npx", "next", "start", "-p", "4001"]
