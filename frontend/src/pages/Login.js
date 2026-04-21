import React, { useState } from 'react';
import { 
  Box, Card, CardContent, TextField, Button, Typography, 
  Container, Alert 
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import axios from '../utils/axios';

function Login() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  const [error, setError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post('/api/login', formData);
      localStorage.setItem('token', response.token);
      localStorage.setItem('user_role', response.role);
      localStorage.setItem('username', response.username);
      navigate('/');
    } catch (error) {
      setError('用户名或密码错误');
    }
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ 
        minHeight: '100vh', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center' 
      }}>
        <Card sx={{ width: '100%' }}>
          <CardContent>
            <Typography variant="h5" align="center" gutterBottom>
              智算检测平台
            </Typography>
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
                sx={{ mt: 2 }}
              >
                登录
              </Button>
            </form>
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
}

export default Login; 