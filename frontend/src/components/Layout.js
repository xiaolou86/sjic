import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, Drawer, AppBar, Toolbar, List, Typography, ListItem, ListItemIcon, ListItemText, IconButton, Avatar, Stack, Alert
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  Videocam, ModelTraining, Settings, Build, NotificationsActive, Task, Code, Logout, Computer, Dashboard as DashboardIcon, VpnKey, History, TouchApp
} from '@mui/icons-material';
import axios, { getBaseUrl } from '../utils/axios';
import ClickTracker from './ClickTracker';

const drawerWidth = 240;

const menuItems = [
  { text: '运行概览', icon: <DashboardIcon />, path: '/dashboard' },
  { text: '节点', icon: <Computer />, path: '/nodes' },
  { text: '视频源', icon: <Videocam />, path: '/streams' },
  { text: '模型管理', icon: <ModelTraining />, path: '/models', role: 'vendor' },
  { text: '算法清单', icon: <Code />, path: '/algorithms' },
  { text: '任务', icon: <Task />, path: '/tasks' },
  { text: '模型训练', icon: <Build />, path: '/training', role: 'vendor' },
  { text: '告警记录', icon: <NotificationsActive />, path: '/alerts' },
  { text: '授权管理', icon: <VpnKey />, path: '/license', always: true },
  { text: '操作日志', icon: <History />, path: '/operation-logs' },
  { text: '点击热点', icon: <TouchApp />, path: '/click-hotspots', role: 'vendor' },
  { text: '系统设置', icon: <Settings />, path: '/settings' },
];

const DEFAULT_BRANDING = {
  company_name: '',
  product_name: '视觉检测系统',
  logo_url: '',
};

function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [branding, setBranding] = useState(DEFAULT_BRANDING);
  const [licenseValid, setLicenseValid] = useState(null);
  const [licenseMessage, setLicenseMessage] = useState('');

  const loadBranding = useCallback(async () => {
    try {
      const data = await axios.get('/api/branding');
      setBranding({
        company_name: data.company_name || '',
        product_name: data.product_name || DEFAULT_BRANDING.product_name,
        logo_url: data.logo_url || '',
      });
      if (data.product_name) {
        document.title = data.product_name;
      }
    } catch (e) {
      // 保持默认标题
    }
  }, []);

  const loadLicense = useCallback(async () => {
    try {
      const status = await axios.get('/api/license/status');
      const valid = Boolean(status?.valid);
      setLicenseValid(valid);
      setLicenseMessage(status?.message || (valid ? '' : '请先导入授权'));
      if (!valid && location.pathname !== '/license') {
        navigate('/license', { replace: true });
      }
    } catch (e) {
      setLicenseValid(false);
      setLicenseMessage('无法获取授权状态，请检查后端服务');
      if (location.pathname !== '/license') {
        navigate('/license', { replace: true });
      }
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    loadBranding();
    const onUpdate = () => loadBranding();
    window.addEventListener('branding-updated', onUpdate);
    return () => window.removeEventListener('branding-updated', onUpdate);
  }, [loadBranding]);

  useEffect(() => {
    loadLicense();
    const onLicense = () => loadLicense();
    window.addEventListener('license-updated', onLicense);
    return () => window.removeEventListener('license-updated', onLicense);
  }, [loadLicense]);

  const handleLogout = async () => {
    try {
      await axios.post('/api/logout');
    } catch (e) {
      // 网络失败也要清掉本地登录态
    }
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('username');
    navigate('/login');
  };

  const userRole = localStorage.getItem('user_role');
  const filteredMenuItems = menuItems.filter(item => {
    if (item.role && item.role !== userRole) return false;
    return true;
  });

  const logoSrc = branding.logo_url ? `${getBaseUrl()}${branding.logo_url}` : '';

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
        <Toolbar sx={{ justifyContent: 'space-between' }}>
          <Stack direction="row" spacing={1.5} alignItems="center">
            {logoSrc && (
              <Avatar
                src={logoSrc}
                variant="rounded"
                sx={{
                  width: 36,
                  height: 36,
                  bgcolor: 'transparent',
                  border: (theme) => `1px solid ${alpha(theme.palette.primary.main, 0.35)}`,
                }}
              />
            )}
            <Typography variant="h6" noWrap component="div" sx={{ fontSize: '1rem' }}>
              {branding.product_name}
            </Typography>
          </Stack>
          <IconButton
            color="inherit"
            aria-label="退出登录"
            onClick={handleLogout}
            sx={{
              border: (theme) => `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
              '&:hover': {
                backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.12),
              },
            }}
          >
            <Logout />
          </IconButton>
        </Toolbar>
      </AppBar>
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
          },
        }}
      >
        <Toolbar />
        <Box sx={{ overflow: 'auto', py: 1 }}>
          <List>
            {filteredMenuItems.map((item) => {
              const disabled = licenseValid !== true && !item.always;
              return (
                <ListItem
                  button
                  key={item.text}
                  selected={location.pathname === item.path}
                  disabled={disabled}
                  onClick={() => {
                    if (!disabled) navigate(item.path);
                  }}
                >
                  <ListItemIcon>{item.icon}</ListItemIcon>
                  <ListItemText
                    primary={item.text}
                    primaryTypographyProps={{
                      fontSize: '0.9rem',
                      fontWeight: location.pathname === item.path ? 600 : 400,
                    }}
                  />
                </ListItem>
              );
            })}
          </List>
        </Box>
      </Drawer>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          minWidth: 0,
          position: 'relative',
        }}
      >
        <Toolbar />
        <ClickTracker />
        {licenseValid === false && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {licenseMessage || '尚未导入有效授权'}。请在「授权管理」导入试用版或正式版授权文件后继续使用。
          </Alert>
        )}
        {children}
      </Box>
    </Box>
  );
}

export default Layout;
