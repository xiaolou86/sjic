import axios from 'axios';

// 导出 getBaseUrl 函数，用于获取基础 URL
export const getBaseUrl = () => {
  // 获取当前访问的域名和协议
  const { protocol, hostname } = window.location;
  const port = process.env.REACT_APP_BACKEND_PORT || '38881';
  if (process.env.NODE_ENV === 'development') {
    // 开发环境：优先使用环境变量，如果没有则回退到当前域名+端口
    return process.env.REACT_APP_API_URL || `${protocol}//${hostname}:${port}`;
  } else {
    // 生产环境：如果是同台服务器，通常直接使用当前域名
    return process.env.REACT_APP_API_URL || `${protocol}//${hostname}:${port}`;
  }
};

// 创建 axios 实例
const instance = axios.create({
  baseURL: getBaseUrl(),
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// 请求拦截器
instance.interceptors.request.use(
  config => {
    // 从 localStorage 获取 token
    const token = localStorage.getItem('token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// 响应拦截器
instance.interceptors.response.use(
  response => {
    return response.data;
  },
  error => {
    if (error.response && error.response.status === 401) {
      // 未授权，清除 token 并重定向到登录页
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// 导出 getWebSocketUrl 函数，用于获取 WebSocket URL
export const getWebSocketUrl = (path) => {
  const baseUrl = getBaseUrl() || window.location.origin;
  const urlObj = new URL(baseUrl);
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${urlObj.host}${path}`;
};

export default instance; 