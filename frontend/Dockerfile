FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN chown -R node:node /app
USER node
EXPOSE 5173
# Development server only. Amplify serves the built static app in AWS later.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
