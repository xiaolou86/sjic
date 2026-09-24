import React, { useEffect, useMemo, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { createAppTheme, DEFAULT_UI_THEME } from './theme';
import axios from './utils/axios';
import Layout from './components/Layout';
import PrivateRoute from './components/PrivateRoute';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import VideoStreams from './pages/VideoStreams';
import Models from './pages/Models';
import Tasks from './pages/Tasks';
import Training from './pages/Training';
import Alerts from './pages/Alerts';
import Algorithms from './pages/Algorithms';
import Settings from './pages/Settings';
import License from './pages/License';
import Nodes from './pages/Nodes';
import OperationLogs from './pages/OperationLogs';
import ClickHotspots from './pages/ClickHotspots';

function App() {
  const isSuperAdmin = localStorage.getItem('user_role') === 'vendor';
  const [uiTheme, setUiTheme] = useState(DEFAULT_UI_THEME);
  const theme = useMemo(() => createAppTheme(uiTheme), [uiTheme]);

  useEffect(() => {
    const loadTheme = () => {
      axios.get('/api/branding')
        .then((data) => {
          if (data?.ui_theme) setUiTheme(data.ui_theme);
        })
        .catch(() => {});
    };
    loadTheme();
    window.addEventListener('branding-updated', loadTheme);
    return () => window.removeEventListener('branding-updated', loadTheme);
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={
            <PrivateRoute>
              <Layout>
                <Navigate to="/dashboard" replace />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/dashboard" element={
            <PrivateRoute>
              <Layout>
                <Dashboard />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/streams" element={
            <PrivateRoute>
              <Layout>
                <VideoStreams />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/nodes" element={
            <PrivateRoute>
              <Layout>
                <Nodes />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/models" element={
            <PrivateRoute>
              <Layout>
                <Models />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/tasks" element={
            <PrivateRoute>
              <Layout>
                <Tasks />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/training" element={
            <PrivateRoute>
              <Layout>
                {isSuperAdmin ? <Training /> : <Navigate to="/tasks" replace />}
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/alerts" element={
            <PrivateRoute>
              <Layout>
                <Alerts />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/algorithms" element={
            <PrivateRoute>
              <Layout>
                <Algorithms />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/license" element={
            <PrivateRoute>
              <Layout>
                <License />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/operation-logs" element={
            <PrivateRoute>
              <Layout>
                <OperationLogs />
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/click-hotspots" element={
            <PrivateRoute>
              <Layout>
                {isSuperAdmin ? <ClickHotspots /> : <Navigate to="/dashboard" replace />}
              </Layout>
            </PrivateRoute>
          } />
          <Route path="/settings" element={
            <PrivateRoute>
              <Layout>
                <Settings />
              </Layout>
            </PrivateRoute>
          } />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
