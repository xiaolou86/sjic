import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { clearLocalSession, isUserIdle } from '../utils/idleLogout';

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  const idle = Boolean(token) && isUserIdle();

  useEffect(() => {
    if (idle) clearLocalSession();
  }, [idle]);

  if (!token || idle) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default PrivateRoute; 