import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, Drawer, AppBar, Toolbar, List, Typography, ListItem, ListItemIcon, ListItemText,
  Avatar, Stack, Alert, Button, Menu, MenuItem, Divider, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, Snackbar
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  Videocam, ModelTraining, Settings, Build, NotificationsActive, Task, Code, Logout, Computer,
  Dashboard as DashboardIcon, VpnKey, History, TouchApp, Lock
} from '@mui/icons-material';
import axios, { getBaseUrl } from '../utils/axios';
import { clearLocalSession, isUserIdle, markUserActivity } from '../utils/idleLogout';
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

const ROLE_LABELS = {
  vendor: '服务商',
  customer: '管理员',
};

const EMPTY_PASSWORD = {
  old_password: '',
  new_password: '',
  confirm_password: '',
};

function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [branding, setBranding] = useState(DEFAULT_BRANDING);
  const [licenseValid, setLicenseValid] = useState(null);
  const [licenseMessage, setLicenseMessage] = useState('');
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [passwordForm, setPasswordForm] = useState(EMPTY_PASSWORD);
  const [passwordError, setPasswordError] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [notice, setNotice] = useState('');

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

  const loggedOut = useRef(false);

  const handleLogout = async () => {
    if (loggedOut.current) return;
    loggedOut.current = true;
    setMenuAnchor(null);
    try {
      await axios.post('/api/logout');
    } catch (e) {
      // 网络失败也要清掉本地登录态
    }
    clearLocalSession();
    navigate('/login', { replace: true });
  };

  useEffect(() => {
    if (!localStorage.getItem('token')) return undefined;
    if (isUserIdle()) {
      handleLogout();
      return undefined;
    }
    markUserActivity(true);

    const onActivity = () => markUserActivity(false);
    const events = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'mousemove'];
    events.forEach((name) => window.addEventListener(name, onActivity, { passive: true }));
    window.addEventListener('scroll', onActivity, { passive: true, capture: true });

    const tick = () => {
      if (isUserIdle()) handleLogout();
    };
    const timer = window.setInterval(tick, 15000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', onVisible);
    const onStorage = (event) => {
      if (event.key === 'token' && !event.newValue) {
        loggedOut.current = true;
        navigate('/login', { replace: true });
        return;
      }
      tick();
    };
    window.addEventListener('storage', onStorage);

    return () => {
      events.forEach((name) => window.removeEventListener(name, onActivity));
      window.removeEventListener('scroll', onActivity, { capture: true });
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('storage', onStorage);
    };
  }, [navigate]);

  const openPasswordDialog = () => {
    setMenuAnchor(null);
    setPasswordForm(EMPTY_PASSWORD);
    setPasswordError('');
    setPasswordOpen(true);
  };

  const handleChangePassword = async () => {
    if (!passwordForm.old_password || !passwordForm.new_password) {
      setPasswordError('请填写原密码和新密码');
      return;
    }
    if (passwordForm.new_password.length < 6) {
      setPasswordError('新密码至少 6 位');
      return;
    }
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordError('两次输入的新密码不一致');
      return;
    }
    setChangingPassword(true);
    setPasswordError('');
    try {
      const result = await axios.post('/api/auth/password', {
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password,
      });
      setPasswordOpen(false);
      setNotice(result.message || '密码已更新，下次登录请使用新密码');
    } catch (error) {
      setPasswordError(error.response?.data?.error || error.message || '修改失败');
    } finally {
      setChangingPassword(false);
    }
  };

  const userRole = localStorage.getItem('user_role');
  const username = localStorage.getItem('username') || '';
  const roleLabel = ROLE_LABELS[userRole] || '';
  const avatarLetter = (username || '?').slice(0, 1).toUpperCase();
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
          <Button
            color="inherit"
            aria-label="个人中心"
            aria-haspopup="true"
            onClick={(e) => setMenuAnchor(e.currentTarget)}
            sx={{
              textTransform: 'none',
              border: (theme) => `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
              '&:hover': {
                backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.12),
              },
            }}
          >
            <Stack direction="row" spacing={1} alignItems="center">
              <Avatar
                sx={{
                  width: 28,
                  height: 28,
                  fontSize: '0.85rem',
                  bgcolor: (theme) => alpha(theme.palette.primary.main, 0.25),
                  color: 'inherit',
                }}
              >
                {avatarLetter}
              </Avatar>
              <Box sx={{ textAlign: 'left', lineHeight: 1.15 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{username || '未登录'}</Typography>
                {roleLabel && (
                  <Typography variant="caption" sx={{ opacity: 0.75 }}>{roleLabel}</Typography>
                )}
              </Box>
            </Stack>
          </Button>
          <Menu
            anchorEl={menuAnchor}
            open={Boolean(menuAnchor)}
            onClose={() => setMenuAnchor(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <MenuItem onClick={openPasswordDialog}>
              <ListItemIcon><Lock fontSize="small" /></ListItemIcon>
              修改密码
            </MenuItem>
            <Divider />
            <MenuItem onClick={handleLogout}>
              <ListItemIcon><Logout fontSize="small" /></ListItemIcon>
              退出登录
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>
      <Dialog open={passwordOpen} onClose={() => !changingPassword && setPasswordOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>修改密码</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            当前账号：{username || '-'}。保存后本次登录仍然有效，下次登录使用新密码。
          </Typography>
          {passwordError && (
            <Alert severity="error" sx={{ mb: 1 }}>{passwordError}</Alert>
          )}
          <TextField
            fullWidth
            type="password"
            label="原密码"
            margin="dense"
            value={passwordForm.old_password}
            autoComplete="current-password"
            onChange={(e) => setPasswordForm((prev) => ({ ...prev, old_password: e.target.value }))}
          />
          <TextField
            fullWidth
            type="password"
            label="新密码"
            margin="dense"
            helperText="至少 6 位"
            value={passwordForm.new_password}
            autoComplete="new-password"
            onChange={(e) => setPasswordForm((prev) => ({ ...prev, new_password: e.target.value }))}
          />
          <TextField
            fullWidth
            type="password"
            label="确认新密码"
            margin="dense"
            value={passwordForm.confirm_password}
            autoComplete="new-password"
            onChange={(e) => setPasswordForm((prev) => ({ ...prev, confirm_password: e.target.value }))}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPasswordOpen(false)} disabled={changingPassword}>取消</Button>
          <Button variant="contained" onClick={handleChangePassword} disabled={changingPassword}>
            {changingPassword ? '提交中…' : '保存'}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={Boolean(notice)}
        autoHideDuration={3000}
        onClose={() => setNotice('')}
        message={notice}
      />
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
