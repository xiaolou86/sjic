import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Layout from './components/Layout';
import PrivateRoute from './components/PrivateRoute';
import Login from './pages/Login';
import VideoStreams from './pages/VideoStreams';
import Models from './pages/Models';
import Tasks from './pages/Tasks';
import Training from './pages/Training';
import Alerts from './pages/Alerts';
import Algorithms from './pages/Algorithms';
import Settings from './pages/Settings';
import Nodes from './pages/Nodes';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

function App() {
  const isSuperAdmin = localStorage.getItem('user_role') === 'vendor';

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={
            <PrivateRoute>
              <Layout>
                <Navigate to="/streams" />
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