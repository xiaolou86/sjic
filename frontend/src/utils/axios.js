import axios from 'axios';
import { clearLocalSession } from './idleLogout';

// 导出 getBaseUrl 函数，用于获取基础 URL
export const getBaseUrl = () => {
  // 获取当前访问的域名和协议
  const { protocol, hostname } = window.location;
  const origin = window.location.origin;
  const port = process.env.REACT_APP_BACKEND_PORT || '38881';
  const explicitApiUrl = process.env.REACT_APP_API_URL;

  if (explicitApiUrl) {
    return explicitApiUrl;
  }

  if (process.env.NODE_ENV === 'development') {
    // 开发环境：默认走当前域名 + 后端端口
    return `${protocol}//${hostname}:${port}`;
  } else {
    // 生产环境：默认同源，避免 NAT/反向代理场景下端口不可达导致 blocked:other
    return origin;
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
    const token = localStorage.getItem('token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    // FormData 需由浏览器自动带 multipart boundary
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      if (config.headers && config.headers['Content-Type']) {
        delete config.headers['Content-Type'];
      }
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
      const reqUrl = error.config?.url || '';
      const onLoginPage = typeof window !== 'undefined' && window.location.pathname === '/login';
      // 登录接口失败只把错误交给页面提示，不要整页重载（否则提示一闪而过、输入被清空）
      if (!reqUrl.includes('/api/login') && !onLoginPage) {
        clearLocalSession();
        window.location.href = '/login';
      }
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