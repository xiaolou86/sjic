# 阶段 1：构建 React 前端静态资源
FROM node:22 AS build

WORKDIR /app

# 安装前端依赖
COPY package*.json ./
RUN npm install

# 复制前端源码并执行打包构建
COPY . .
RUN npm run build

# 阶段 2：使用 Nginx 托管静态资源并反向代理后端服务
FROM nginx:alpine

# 拷贝打包好的静态文件到 Nginx 根目录
COPY --from=build /app/build /usr/share/nginx/html

# 拷贝 Nginx 路由代理配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露前端访问端口
EXPOSE 38880

CMD ["nginx", "-g", "daemon off;"]
 