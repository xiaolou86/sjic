import React, { useState, useEffect, useRef } from 'react';
import {
  Grid, Card, CardContent, Typography, Button, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, Alert, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Paper, IconButton
} from '@mui/material';
import { Add, Visibility, Delete, Close, Edit } from '@mui/icons-material';
import axios, { getBaseUrl, getWebSocketUrl } from '../utils/axios';
import VideoPlayer from '../components/VideoPlayer';
import JSMpeg from '@cycjimmy/jsmpeg-player';

function VideoStreams() {
  const [streams, setStreams] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [openPreview, setOpenPreview] = useState(false);
  const [selectedStream, setSelectedStream] = useState(null);
  const [newStream, setNewStream] = useState({ name: '', url: '' });
  const [editingStream, setEditingStream] = useState(null);
  const [error, setError] = useState(null);
  const [previewingCamera, setPreviewingCamera] = useState(null);

  useEffect(() => {
    fetchStreams();
  }, []);

  const fetchStreams = async () => {
    try {
      const response = await axios.get('/api/cameras');
      setStreams(response || []);
      console.log('Streams:', response);
    } catch (error) {
      console.error('Error fetching streams:', error);
      setError('Failed to load video streams');
      setStreams([]);
    }
  };

  const handleAddStream = async () => {
    try {
      await axios.post('/api/cameras', newStream);
      setOpenDialog(false);
      setNewStream({ name: '', url: '' });
      fetchStreams();
    } catch (error) {
      console.error('Error adding stream:', error);
    }
  };

  const handleEditStream = (stream) => {
    setEditingStream(stream);
    setNewStream({ name: stream.name || '', url: stream.url || '' });
    setOpenDialog(true);
  };

  const handleSaveStream = async () => {
    try {
      if (editingStream) {
        await axios.put(`/api/cameras/${editingStream.id}`, newStream);
      } else {
        await axios.post('/api/cameras', newStream);
      }
      setOpenDialog(false);
      setEditingStream(null);
      setNewStream({ name: '', url: '' });
      fetchStreams();
    } catch (error) {
      console.error('Error saving stream:', error);
    }
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingStream(null);
    setNewStream({ name: '', url: '' });
  };

  const handlePreview = (camera) => {
    setPreviewingCamera(camera);
  };

  const handleClosePreview = () => {
    setPreviewingCamera(null);
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`/api/cameras/${id}`);
      fetchStreams();
    } catch (error) {
      console.error('Error deleting stream:', error);
    }
  };

  return (
    <>
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setOpenDialog(true)}
            sx={{ mb: 2 }}
          >
            添加视频源
          </Button>
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>名称</TableCell>
                  <TableCell>URL</TableCell>
                  <TableCell>状态</TableCell>
                  <TableCell>创建时间</TableCell>
                  <TableCell>操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {streams.map((stream) => (
                  <TableRow key={stream.id}>
                    <TableCell>{stream.id}</TableCell>
                    <TableCell>{stream.name}</TableCell>
                    <TableCell>{stream.url}</TableCell>
                    <TableCell>{stream.status ? '在线' : '离线'}</TableCell>
                    <TableCell>{new Date(stream.created_at).toLocaleString()}</TableCell>
                    <TableCell>
                      <IconButton
                        color="primary"
                        onClick={() => handlePreview(stream)}
                        title="预览"
                      >
                        <Visibility />
                      </IconButton>
                      <IconButton
                        color="primary"
                        onClick={() => handleEditStream(stream)}
                        title="修改"
                      >
                        <Edit />
                      </IconButton>
                      <IconButton
                        color="error"
                        onClick={() => handleDelete(stream.id)}
                        title="删除"
                      >
                        <Delete />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Grid>
      </Grid>

      {/* 添加视频源对话框 */}
      <Dialog open={openDialog} onClose={handleCloseDialog}>
        <DialogTitle>{editingStream ? '修改视频源' : '添加视频源'}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="名称"
            fullWidth
            value={newStream.name}
            onChange={(e) => setNewStream({ ...newStream, name: e.target.value })}
          />
          <TextField
            margin="dense"
            label="RTSP地址"
            fullWidth
            value={newStream.url}
            onChange={(e) => setNewStream({ ...newStream, url: e.target.value })}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button onClick={handleSaveStream} color="primary">
            {editingStream ? '保存' : '添加'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 预览对话框 */}
      <Dialog
        open={Boolean(previewingCamera)}
        onClose={handleClosePreview}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          预览 - {previewingCamera?.name}
          <IconButton
            onClick={handleClosePreview}
            sx={{ position: 'absolute', right: 8, top: 8 }}
          >
            <Close />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          {previewingCamera && (
            <MJPEGPlayer cameraId={previewingCamera.id} />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function VideoPreview({ cameraId }) {
  return (
    <div>
      <MJPEGPlayer cameraId={cameraId} />
    </div>
  );
}

function JSMpegPlayer({ cameraId, onError }) {
  const canvasRef = useRef(null);
  const playerRef = useRef(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [useHttpFallback, setUseHttpFallback] = useState(false);

  useEffect(() => {
    let player = null;

    const initPlayer = () => {
      if (!canvasRef.current) return;

      try {
        setLoading(true);

        let url;
        if (useHttpFallback) {
          // 使用 HTTP 流作为备选方案
          const baseUrl = getBaseUrl();
          url = `${baseUrl}/api/stream/${cameraId}`;
          console.log('Using HTTP fallback URL:', url);
        } else {
          // 使用 WebSocket
          const token = localStorage.getItem('token');
          url = getWebSocketUrl(`/ws/stream/${cameraId}?token=${token}`);
          console.log('Connecting to WebSocket URL:', url);
        }

        // 创建 JSMpeg 播放器
        const options = {
          canvas: canvasRef.current,
          autoplay: true,
          audio: false,
          loop: true,
          videoBufferSize: 512 * 1024,
          onPlay: () => {
            console.log('Stream started playing');
            setLoading(false);
          },
          onError: (err) => {
            console.error('JSMpeg error:', err);

            // 如果 WebSocket 失败，尝试 HTTP 流
            if (!useHttpFallback) {
              console.log('Switching to HTTP fallback');
              setUseHttpFallback(true);
            } else {
              setError(`播放错误: ${err}`);
              setLoading(false);
              if (onError) onError(err);
            }
          }
        };

        // 如果使用 WebSocket，添加协议选项
        if (!useHttpFallback) {
          options.protocols = ['binary'];
        }

        player = new JSMpeg.Player(url, options);
        playerRef.current = player;
        console.log('JSMpeg player initialized');

        // 添加超时检查
        setTimeout(() => {
          if (loading && !error && !useHttpFallback) {
            console.log('WebSocket connection timeout, switching to HTTP fallback');
            setUseHttpFallback(true);
          }
        }, 5000);
      } catch (err) {
        console.error('Error initializing JSMpeg player:', err);
        setError(`初始化错误: ${err.message}`);
        setLoading(false);
        if (onError) onError(err);
      }
    };

    // 初始化播放器
    initPlayer();

    // 清理函数
    return () => {
      console.log('Cleaning up JSMpeg player');
      if (playerRef.current) {
        try {
          const p = playerRef.current;
          if (p && typeof p.destroy === 'function') {
            p.destroy();
          }
          playerRef.current = null;
        } catch (err) {
          console.error('Error destroying JSMpeg player:', err);
        }
      }
    };
  }, [cameraId, useHttpFallback, onError]);

  return (
    <div className="video-container" style={{ textAlign: 'center' }}>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
          <Button
            color="inherit"
            size="small"
            onClick={() => window.location.reload()}
            sx={{ ml: 2 }}
          >
            重试
          </Button>
        </Alert>
      )}
      {loading && !error && (
        <div style={{ marginBottom: '10px' }}>
          <Typography variant="body2" color="textSecondary">
            正在加载视频流...
          </Typography>
        </div>
      )}
      <canvas
        ref={canvasRef}
        width="640"
        height="360"
        style={{
          width: '100%',
          maxWidth: '800px',
          backgroundColor: '#000'
        }}
      />
    </div>
  );
}

function HttpStreamPlayer({ cameraId, onError }) {
  const canvasRef = useRef(null);
  const playerRef = useRef(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let player = null;

    const initPlayer = () => {
      if (!canvasRef.current) return;

      try {
        setLoading(true);
        // 使用 getBaseUrl 获取基础 URL
        const baseUrl = getBaseUrl();
        const url = `${baseUrl}/api/stream/${cameraId}`;
        console.log('Connecting to HTTP stream URL:', url);

        // 创建 JSMpeg 播放器
        player = new JSMpeg.Player(url, {
          canvas: canvasRef.current,
          autoplay: true,
          audio: false,
          loop: true,
          pauseWhenHidden: false,
          videoBufferSize: 512 * 1024,
          onPlay: () => {
            console.log('HTTP Stream started playing');
            setLoading(false);
          },
          onError: (err) => {
            console.error('JSMpeg HTTP error:', err);
            setError(`播放错误: ${err}`);
            setLoading(false);
            if (onError) onError(err);
          }
        });

        playerRef.current = player;
        console.log('HTTP JSMpeg player initialized');

        // 添加超时检查
        setTimeout(() => {
          if (loading && !error) {
            console.log('HTTP stream timeout');
            setError('HTTP 视频流加载超时');
            if (onError) onError('timeout');
          }
        }, 10000);
      } catch (err) {
        console.error('Error initializing HTTP JSMpeg player:', err);
        setError(`初始化错误: ${err.message}`);
        setLoading(false);
        if (onError) onError(err);
      }
    };

    // 初始化播放器
    initPlayer();

    // 清理函数
    return () => {
      console.log('Cleaning up HTTP JSMpeg player');
      if (playerRef.current) {
        try {
          const p = playerRef.current;
          if (p && typeof p.destroy === 'function') {
            p.destroy();
          }
          playerRef.current = null;
        } catch (err) {
          console.error('Error destroying HTTP JSMpeg player:', err);
        }
      }
    };
  }, [cameraId, onError]);

  return (
    <div className="video-container" style={{ textAlign: 'center' }}>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
          <Button
            color="inherit"
            size="small"
            onClick={() => window.location.reload()}
            sx={{ ml: 2 }}
          >
            重试
          </Button>
        </Alert>
      )}
      {loading && !error && (
        <div style={{ marginBottom: '10px' }}>
          <Typography variant="body2" color="textSecondary">
            正在加载 HTTP 视频流...
          </Typography>
        </div>
      )}
      <canvas
        ref={canvasRef}
        width="640"
        height="360"
        style={{
          width: '100%',
          maxWidth: '800px',
          backgroundColor: '#000'
        }}
      />
    </div>
  );
}

function HLSPlayer({ cameraId }) {
  const videoRef = useRef(null);

  useEffect(() => {
    if (videoRef.current) {
      // 使用 getBaseUrl 获取基础 URL
      const baseUrl = getBaseUrl();
      const hlsUrl = `${baseUrl}/api/hls/${cameraId}/playlist.m3u8`;
      console.log('Loading HLS stream from:', hlsUrl);

      if (videoRef.current.canPlayType('application/vnd.apple.mpegurl')) {
        // 原生 HLS 支持 (Safari)
        videoRef.current.src = hlsUrl;
      } else if (window.Hls) {
        // 使用 hls.js (Chrome, Firefox 等)
        const hls = new window.Hls();
        hls.loadSource(hlsUrl);
        hls.attachMedia(videoRef.current);
      } else {
        console.error('浏览器不支持 HLS');
      }
    }
  }, [cameraId]);

  return (
    <div className="video-container" style={{ textAlign: 'center' }}>
      <video
        ref={videoRef}
        controls
        autoPlay
        style={{
          width: '100%',
          maxWidth: '800px',
          backgroundColor: '#000'
        }}
      />
    </div>
  );
}

function MJPEGPlayer({ cameraId }) {
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const imgRef = useRef(null);

  // 构建 MJPEG 流 URL (提升至 useEffect 之前，修复初始化顺序问题)
  const baseUrl = getBaseUrl();
  const streamUrl = `${baseUrl}/api/mjpeg/${cameraId}`;

  useEffect(() => {
    // 图像加载完成时的处理
    const handleImageLoad = () => {
      setLoading(false);
    };

    // 图像加载失败时的处理
    const handleImageError = () => {
      // 只有在真的加载出错，且 src 不为空时才提示报错
      if (imgRef.current && imgRef.current.src !== window.location.href && imgRef.current.src !== "") {
        setError('视频流加载失败');
        setLoading(false);
      }
    };

    let mounted = true;

    // 添加事件监听器
    const imgElement = imgRef.current;
    if (imgElement) {
      imgElement.addEventListener('load', handleImageLoad);
      imgElement.addEventListener('error', handleImageError);

      // 核心修复：在这里显式注入 URL，触发预览加载
      imgElement.src = streamUrl;
    }

    // 清理函数
    return () => {
      mounted = false;
      if (imgElement) {
        imgElement.removeEventListener('load', handleImageLoad);
        imgElement.removeEventListener('error', handleImageError);
        // 主动杀掉长连接：将 src 置为空，切断向后端的请求
        imgElement.src = "";
      }
    };
  }, [cameraId, streamUrl]); // 强制监听 URL 变化防止渲染死锁

  return (
    <div className="video-container" style={{ textAlign: 'center' }}>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
          <Button
            color="inherit"
            size="small"
            onClick={() => window.location.reload()}
            sx={{ ml: 2 }}
          >
            重试
          </Button>
        </Alert>
      )}
      {loading && !error && (
        <div style={{ marginBottom: '10px' }}>
          <Typography variant="body2" color="textSecondary">
            正在加载视频流...
          </Typography>
        </div>
      )}
      <img
        ref={imgRef}
        alt="Camera Stream"
        style={{
          width: '100%',
          maxWidth: '800px',
          backgroundColor: '#000',
          display: error ? 'none' : 'block'
        }}
      />
    </div>
  );
}

export default VideoStreams; 