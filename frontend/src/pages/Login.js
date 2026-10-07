import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, Avatar, Stack, keyframes
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useNavigate } from 'react-router-dom';
import axios, { getBaseUrl } from '../utils/axios';
import { markUserActivity } from '../utils/idleLogout';
import { DEFAULT_UI_THEME, getLoginVisual, getTitleGradient } from '../theme';

const pulse = keyframes`
  0%, 100% { opacity: 0.45; transform: scale(1); }
  50% { opacity: 0.75; transform: scale(1.05); }
`;

const scan = keyframes`
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100vh); }
`;

function Login() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  const [error, setError] = useState('');
  const [branding, setBranding] = useState({
    company_name: '',
    product_name: '智算检测平台',
    logo_url: '',
    ui_theme: DEFAULT_UI_THEME,
  });

  useEffect(() => {
    axios.get('/api/branding')
      .then((data) => {
        setBranding({
          company_name: data.company_name || '',
          product_name: data.product_name || '智算检测平台',
          logo_url: data.logo_url || '',
          ui_theme: data.ui_theme || DEFAULT_UI_THEME,
        });
        if (data.product_name) {
          document.title = data.product_name;
        }
      })
      .catch(() => {});
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post('/api/login', formData);
      localStorage.setItem('token', response.token);
      localStorage.setItem('user_role', response.role);
      localStorage.setItem('username', response.username);
      markUserActivity(true);
      navigate('/dashboard');
    } catch (err) {
      setError('用户名或密码错误');
    }
  };

  const logoSrc = branding.logo_url ? `${getBaseUrl()}${branding.logo_url}` : '';
  const visual = getLoginVisual(branding.ui_theme);
  const titleGradient = getTitleGradient(branding.ui_theme);

  return (
    <Box
      sx={{
        minHeight: '100vh',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        px: 2,
        backgroundColor: visual.pageBg,
        backgroundImage: visual.backgroundImage(alpha),
        backgroundSize: visual.backgroundSize,
      }}
    >
      <Box
        sx={{
          position: 'absolute',
          width: 420,
          height: 420,
          borderRadius: '50%',
          top: '8%',
          left: '12%',
          background: `radial-gradient(circle, ${alpha(visual.orb1, 0.25)} 0%, transparent 70%)`,
          filter: 'blur(8px)',
          animation: `${pulse} 8s ease-in-out infinite`,
          pointerEvents: 'none',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          width: 320,
          height: 320,
          borderRadius: '50%',
          bottom: '10%',
          right: '10%',
          background: `radial-gradient(circle, ${alpha(visual.orb2, 0.18)} 0%, transparent 70%)`,
          filter: 'blur(10px)',
          animation: `${pulse} 10s ease-in-out infinite reverse`,
          pointerEvents: 'none',
        }}
      />

      {visual.showScan && (
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            overflow: 'hidden',
            '&::after': {
              content: '""',
              position: 'absolute',
              left: 0,
              right: 0,
              height: 120,
              background: `linear-gradient(180deg, transparent, ${alpha(visual.scan, 0.08)}, transparent)`,
              animation: `${scan} 9s linear infinite`,
            },
          }}
        />
      )}

      <Box
        sx={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          py: 6,
          position: 'relative',
          zIndex: 1,
        }}
      >
        <Card
          sx={{
            width: '100%',
            maxWidth: 420,
            backgroundColor: visual.cardBg(alpha),
            backdropFilter: 'blur(18px)',
            border: `1px solid ${visual.cardBorder(alpha)}`,
            boxShadow: `
              0 0 0 1px ${visual.accent(alpha)},
              0 24px 64px ${alpha('#000000', 0.45)},
              0 0 40px ${visual.cardGlow(alpha)}
            `,
          }}
        >
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Stack alignItems="center" spacing={1} sx={{ mb: 3 }}>
              {logoSrc && (
                <Avatar
                  src={logoSrc}
                  variant="rounded"
                  sx={{ width: 72, height: 72, bgcolor: 'transparent', mb: 0.5 }}
                />
              )}
              <Typography
                variant="h5"
                align="center"
                sx={{
                  background: titleGradient,
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  color: 'transparent',
                }}
              >
                {branding.product_name}
              </Typography>
            </Stack>
            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}
            <form onSubmit={handleLogin}>
              <TextField
                fullWidth
                label="用户名"
                margin="normal"
                value={formData.username}
                onChange={(e) => setFormData({
                  ...formData,
                  username: e.target.value
                })}
              />
              <TextField
                fullWidth
                label="密码"
                type="password"
                margin="normal"
                value={formData.password}
                onChange={(e) => setFormData({
                  ...formData,
                  password: e.target.value
                })}
              />
              <Button
                fullWidth
                variant="contained"
                type="submit"
                size="large"
                sx={{ mt: 3, py: 1.2 }}
              >
                登录
              </Button>
            </form>
          </CardContent>
        </Card>
      </Box>

      {branding.company_name && (
        <Typography
          variant="caption"
          align="center"
          sx={{
            position: 'relative',
            zIndex: 1,
            pb: 2.5,
            color: visual.footer(alpha),
            letterSpacing: '0.06em',
          }}
        >
          @{branding.company_name}
        </Typography>
      )}
    </Box>
  );
}

export default Login;
