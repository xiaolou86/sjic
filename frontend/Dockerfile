# 阶段 1：构建 React 前端静态资源
FROM node:22 AS build

WORKDIR /app

# 安装前端依赖
COPY package*.json ./
RUN npm install

# 复制前端源码并执行打包构建
COPY . .
RUN npm run build

# 阶段 2：使用 Nginx 托管静态资源、模型下发，并反向代理后端
FROM nginx:1.25-alpine

# 拷贝打包好的静态文件到 Nginx 根目录
COPY --from=build /app/build /usr/share/nginx/html

# 使用官方 entrypoint 的 envsubst：注入 DOWNLOAD_SECURE_KEY
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

RUN mkdir -p /usr/share/nginx/models

# 暴露前端 / 模型下载端口
EXPOSE 38880

CMD ["nginx", "-g", "daemon off;"]
