import React, { useState, useEffect, useCallback } from 'react';
import {
  Grid, TextField, Button, Typography, Snackbar, Alert,
  Card, CardContent, Box, Avatar, Stack
} from '@mui/material';
import { Save, CloudUpload, Delete, RestartAlt } from '@mui/icons-material';
import axios, { getBaseUrl } from '../utils/axios';
import { UI_THEME_OPTIONS, DEFAULT_UI_THEME } from '../theme';

const DEFAULT_SETTINGS = {
  external_alert_api: {
    url: '',
    token: '',
    secret: ''
  },
  alert: {
    retention_days: 30,
    image_quality: 95
  },
  system: {
    log_level: 'INFO',
    ui_theme: DEFAULT_UI_THEME
  },
  branding: {
    company_name: '',
    product_name: '智算检测平台',
    logo_filename: '',
    logo_url: ''
  }
};

function Settings() {
  const isVendor = localStorage.getItem('user_role') === 'vendor';
  const isCustomerAdmin = localStorage.getItem('user_role') === 'customer';
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [licenseValid, setLicenseValid] = useState(false);
  const [message, setMessage] = useState({ type: '', content: '' });
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [restartingBackend, setRestartingBackend] = useState(false);

  const showMsg = (type, content) => {
    setMessage({ type, content });
    setOpenSnackbar(true);
  };

  const fetchLicense = useCallback(async () => {
    try {
      const status = await axios.get('/api/license/status');
      setLicenseValid(Boolean(status?.valid));
    } catch (error) {
      setLicenseValid(false);
    }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const response = await axios.get('/api/settings');
      const mergedSettings = {
        ...DEFAULT_SETTINGS,
        ...response,
        external_alert_api: {
          ...DEFAULT_SETTINGS.external_alert_api,
          ...(response.external_alert_api || {})
        },
        alert: {
          ...DEFAULT_SETTINGS.alert,
          ...(response.alert || {})
        },
        system: {
          ...DEFAULT_SETTINGS.system,
          ...(response.system || {})
        },
        branding: {
          ...DEFAULT_SETTINGS.branding,
          ...(response.branding || {})
        }
      };
      setSettings(mergedSettings);
    } catch (error) {
      if (error.response?.status !== 403) {
        showMsg('error', '获取配置失败: ' + error.message);
      }
    }
  }, []);

  useEffect(() => {
    fetchLicense();
    fetchSettings();
    const onLicense = () => fetchLicense();
    window.addEventListener('license-updated', onLicense);
    return () => window.removeEventListener('license-updated', onLicense);
  }, [fetchLicense, fetchSettings]);

  const handleSave = async () => {
    try {
      const payload = {
        external_alert_api: settings.external_alert_api,
        alert: settings.alert,
        system: settings.system,
      };
      if (isVendor) {
        payload.branding = {
          company_name: settings.branding.company_name,
          product_name: settings.branding.product_name,
          logo_filename: settings.branding.logo_filename || '',
        };
      }
      await axios.post('/api/settings', payload);
      showMsg('success', '保存成功');
      window.dispatchEvent(new Event('branding-updated'));
    } catch (error) {
      showMsg('error', '保存失败: ' + (error.response?.data?.error || error.message));
    }
  };

  const handleChange = (section, field) => (event) => {
    setSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: event.target.value
      }
    }));
  };

  const handleLogoUpload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('logo', file);
      const result = await axios.post('/api/settings/logo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSettings(prev => ({
        ...prev,
        branding: {
          ...prev.branding,
          ...(result.branding || {}),
        }
      }));
      showMsg('success', 'Logo 上传成功');
      window.dispatchEvent(new Event('branding-updated'));
    } catch (error) {
      showMsg('error', 'Logo 上传失败: ' + (error.response?.data?.error || error.message));
    } finally {
      setUploading(false);
    }
  };

  const handleLogoRemove = async () => {
    try {
      const result = await axios.delete('/api/settings/logo');
      setSettings(prev => ({
        ...prev,
        branding: {
          ...prev.branding,
          ...(result.branding || {}),
          logo_filename: '',
          logo_url: '',
        }
      }));
      showMsg('success', 'Logo 已清除');
      window.dispatchEvent(new Event('branding-updated'));
    } catch (error) {
      showMsg('error', '清除失败: ' + error.message);
    }
  };

  const handleRestartBackend = async () => {
    if (!window.confirm('确定远程重启管理平台后端？服务将短暂中断，Docker 部署下会自动拉起。')) {
      return;
    }
    setRestartingBackend(true);
    try {
      const result = await axios.post('/api/admin/restart-backend');
      showMsg('success', result.message || '后端正在重启…');
    } catch (error) {
      showMsg('error', '重启失败: ' + (error.response?.data?.error || error.message));
      setRestartingBackend(false);
    }
  };

  const logoSrc = settings.branding.logo_url
    ? `${getBaseUrl()}${settings.branding.logo_url}`
    : '';

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Typography variant="h5" gutterBottom>系统设置</Typography>
      </Grid>

      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>界面主题</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              同时作用于登录页背景与平台整体配色，保存后立即生效。
            </Typography>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              {UI_THEME_OPTIONS.map((opt) => {
                const selected = (settings.system.ui_theme || DEFAULT_UI_THEME) === opt.value;
                return (
                  <Box
                    key={opt.value}
                    onClick={() => {
                      if (!licenseValid) return;
                      setSettings((prev) => ({
                        ...prev,
                        system: { ...prev.system, ui_theme: opt.value },
                      }));
                    }}
                    sx={{
                      width: 180,
                      cursor: licenseValid ? 'pointer' : 'default',
                      opacity: licenseValid ? 1 : 0.55,
                      borderRadius: 2,
                      overflow: 'hidden',
                      border: selected ? '2px solid' : '1px solid',
                      borderColor: selected ? 'primary.main' : 'divider',
                      boxShadow: selected ? 4 : 0,
                    }}
                  >
                    <Box sx={{ height: 72, background: opt.preview }} />
                    <Box sx={{ p: 1.25 }}>
                      <Typography variant="subtitle2">{opt.label}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {opt.description}
                      </Typography>
                    </Box>
                  </Box>
                );
              })}
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      {isVendor && (
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>品牌定制</Typography>
              <TextField
                fullWidth
                label="公司名称"
                value={settings.branding.company_name}
                onChange={handleChange('branding', 'company_name')}
                margin="normal"
                disabled={!licenseValid}
                helperText="显示在登录页最下方，格式如 @某某科技"
              />
              <TextField
                fullWidth
                label="产品名称"
                value={settings.branding.product_name}
                onChange={handleChange('branding', 'product_name')}
                margin="normal"
                disabled={!licenseValid}
              />
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }}>
                <Avatar
                  variant="rounded"
                  src={logoSrc || undefined}
                  sx={{ width: 64, height: 64, bgcolor: 'grey.800' }}
                >
                  {!logoSrc && 'Logo'}
                </Avatar>
                <Box>
                  <Button
                    variant="outlined"
                    component="label"
                    startIcon={<CloudUpload />}
                    disabled={uploading || !licenseValid}
                    sx={{ mr: 1 }}
                  >
                    {uploading ? '上传中…' : '上传 Logo'}
                    <input type="file" hidden accept="image/*" onChange={handleLogoUpload} />
                  </Button>
                  {logoSrc && (
                    <Button
                      color="inherit"
                      startIcon={<Delete />}
                      onClick={handleLogoRemove}
                      disabled={!licenseValid}
                    >
                      清除
                    </Button>
                  )}
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      )}

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>外部告警API设置</Typography>
            <TextField
              fullWidth
              label="API地址"
              value={settings.external_alert_api.url}
              onChange={handleChange('external_alert_api', 'url')}
              margin="normal"
              disabled={!licenseValid}
            />
            <TextField
              fullWidth
              label="Token"
              value={settings.external_alert_api.token}
              onChange={handleChange('external_alert_api', 'token')}
              margin="normal"
              disabled={!licenseValid}
            />
            <TextField
              fullWidth
              label="Secret"
              type="password"
              value={settings.external_alert_api.secret}
              onChange={handleChange('external_alert_api', 'secret')}
              margin="normal"
              disabled={!licenseValid}
            />
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>告警设置</Typography>
            <TextField
              fullWidth
              type="number"
              label="告警保留天数"
              value={settings.alert.retention_days}
              onChange={handleChange('alert', 'retention_days')}
              margin="normal"
              disabled={!licenseValid}
            />
            <TextField
              fullWidth
              type="number"
              label="图片质量(1-100)"
              value={settings.alert.image_quality}
              onChange={handleChange('alert', 'image_quality')}
              margin="normal"
              disabled={!licenseValid}
            />
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>系统设置</Typography>
            <TextField
              fullWidth
              select
              label="日志级别"
              value={settings.system.log_level}
              onChange={handleChange('system', 'log_level')}
              margin="normal"
              disabled={!licenseValid}
              SelectProps={{
                native: true
              }}
            >
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </TextField>
          </CardContent>
        </Card>
      </Grid>

      {isCustomerAdmin && (
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>服务运维</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                程序异常时可远程重启后端。平台与边缘均需 Docker Compose（restart: unless-stopped）部署才会自动拉起；
                边缘 Agent 请在「节点」页按台重启。
              </Typography>
              <Button
                variant="outlined"
                color="warning"
                startIcon={<RestartAlt />}
                onClick={handleRestartBackend}
                disabled={restartingBackend || !licenseValid}
              >
                {restartingBackend ? '正在重启…' : '重启管理平台后端'}
              </Button>
            </CardContent>
          </Card>
        </Grid>
      )}

      <Grid item xs={12}>
        <Button
          variant="contained"
          color="primary"
          startIcon={<Save />}
          onClick={handleSave}
          disabled={!licenseValid}
        >
          保存设置
        </Button>
      </Grid>

      <Snackbar
        open={openSnackbar}
        autoHideDuration={3000}
        onClose={() => setOpenSnackbar(false)}
      >
        <Alert severity={message.type} onClose={() => setOpenSnackbar(false)}>
          {message.content}
        </Alert>
      </Snackbar>
    </Grid>
  );
}

export default Settings;
