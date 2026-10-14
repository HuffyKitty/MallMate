FROM node:22-alpine
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:18080
ARG NEXT_PUBLIC_SHOW_DEMO_CREDENTIALS=false
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_SHOW_DEMO_CREDENTIALS=${NEXT_PUBLIC_SHOW_DEMO_CREDENTIALS}
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]

