import React, { useState, useRef, useEffect } from 'react';
import { 
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  Paper, Box, Typography
} from '@mui/material';
import axios, { getBaseUrl } from '../utils/axios';

function RegionSelectionTool({ cameraId, onSelect, existingRegion }) {
  const [open, setOpen] = useState(false);
  const [imageUrl, setImageUrl] = useState(null);
  const [points, setPoints] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [frameSize, setFrameSize] = useState({ width: 800, height: 600 });
  const [isDrawing, setIsDrawing] = useState(false);
  const canvasRef = useRef(null);
  const [currentPoint, setCurrentPoint] = useState(null);
  const [draggingPointIndex, setDraggingPointIndex] = useState(null);
  const [isComplete, setIsComplete] = useState(false);
  const [hoveredPointIndex, setHoveredPointIndex] = useState(null);

  // 加载已有的区域数据
  useEffect(() => {
    if (open && existingRegion && existingRegion.detection_region) {
      // 如果有现有的图像数据，使用它
      if (existingRegion.calibration && existingRegion.calibration.image_data) {
        setImageUrl(existingRegion.calibration.image_data);
        setIsStreaming(false);
      }
      
      // 设置点数据
      if (existingRegion.detection_region.points && existingRegion.detection_region.points.length > 0) {
        setPoints(existingRegion.detection_region.points);
        setIsComplete(true);
      }
      
      // 设置帧尺寸
      if (existingRegion.detection_region.frame_size) {
        setFrameSize(existingRegion.detection_region.frame_size);
      }
    }
  }, [open, existingRegion]);

  // 计算缩放后的尺寸
  const calculateAspectRatio = (originalWidth, originalHeight, maxWidth = 800) => {
    const ratio = originalWidth / originalHeight;
    let width = maxWidth;
    let height = maxWidth / ratio;
    return { width, height };
  };

  // 构建 MJPEG 流地址
  const getMjpegUrl = () => {
    const base = getBaseUrl();
    return `${base}/api/mjpeg/${cameraId}`;
  };

  // 开始视频流预览
  const startStreaming = () => {
    if (!cameraId) return;
    
    if (imageUrl) {
      URL.revokeObjectURL(imageUrl);
      setImageUrl(null);
      setPoints([]);
      setIsComplete(false);
    }
    
    setIsStreaming(true);
  };

  // 停止预览并截取当前帧用于画线
  const stopStreaming = async () => {
    setIsStreaming(false);
    // 通过 HTTP 接口截取一帧作为标定底图
    await captureFrameFromServer();
  };

  // 从服务端截取一帧静态图
  const captureFrameFromServer = async () => {
    try {
      const response = await axios.post('/api/cameras/capture', {
        camera_id: cameraId
      }, {
        responseType: 'blob'
      });

      const blob = response instanceof Blob ? response : new Blob([response], { type: 'image/jpeg' });
      const url = URL.createObjectURL(blob);
      
      // 获取实际图像尺寸
      const img = new Image();
      img.onload = () => {
        const size = calculateAspectRatio(img.width, img.height);
        setFrameSize(size);
      };
      img.src = url;
      
      setImageUrl(url);
    } catch (error) {
      console.error('Error capturing frame:', error);
    }
  };

  const captureFrame = async () => {
    if (isStreaming) {
      await stopStreaming();
    } else {
      await captureFrameFromServer();
    }
  };

  const handleCanvasClick = (event) => {
    if (!imageUrl) return;
    
    // 处理右键点击 - 完成绘制
    if (event.button === 2) {
      if (points.length >= 3) {
        setIsComplete(true);
      }
      return;
    }

    // 如果已经完成绘制，不再添加新点
    if (isComplete) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const point = {
      x: x * scaleX,
      y: y * scaleY
    };

    // 添加新点
    setPoints(prev => [...prev, point]);
  };

  const handleMouseMove = (event) => {
    if (!imageUrl) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const currentPos = {
      x: x * scaleX,
      y: y * scaleY
    };

    // 检查是否悬停在某个点上
    const hoverIndex = points.findIndex(p => 
      Math.hypot(p.x - currentPos.x, p.y - currentPos.y) < 10
    );
    setHoveredPointIndex(hoverIndex);

    if (draggingPointIndex !== null) {
      // 拖动已存在的点
      setPoints(prev => prev.map((p, index) => 
        index === draggingPointIndex ? currentPos : p
      ));
    } else if (!isComplete) {
      // 更新当前鼠标位置（用于绘制临时线段）
      setCurrentPoint(currentPos);
    }

    drawCanvas();
  };

  const handleMouseDown = (event) => {
    if (event.button === 0 && hoveredPointIndex !== null) { // 左键点击
      event.preventDefault(); // 防止触发 click 事件
      setDraggingPointIndex(hoveredPointIndex);
    }
  };

  const handleMouseUp = () => {
    setDraggingPointIndex(null);
  };

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = new Image();
    img.src = imageUrl;

    img.onload = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      if (points.length > 0) {
        // 绘制已确定的点和线段
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        points.forEach((point, index) => {
          if (index > 0) {
            ctx.lineTo(point.x, point.y);
          }
        });

        // 如果完成绘制，连接首尾点
        if (isComplete) {
          ctx.closePath();
        } else if (currentPoint && points.length > 0) {
          // 绘制当前移动的线段
          ctx.lineTo(currentPoint.x, currentPoint.y);
        }

        ctx.strokeStyle = 'yellow';
        ctx.lineWidth = 2;
        ctx.stroke();

        if (isComplete) {
          ctx.fillStyle = 'rgba(255, 255, 0, 0.2)';
          ctx.fill();
        }

        // 绘制顶点
        points.forEach((point, index) => {
          ctx.beginPath();
          ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
          ctx.fillStyle = draggingPointIndex === index ? 'blue' : 
                         hoveredPointIndex === index ? 'yellow' : 'red';
          ctx.fill();
          ctx.strokeStyle = 'white';
          ctx.stroke();
        });
      }
    };
  };

  const handleReset = () => {
    setPoints([]);
    setCurrentPoint(null);
    setIsComplete(false);
    drawCanvas();
  };

  const handleConfirm = async () => {
    if (points.length < 3 || !imageUrl) return;

    try {
      // 获取当前图像的 blob 数据
      const response = await fetch(imageUrl);
      const blob = await response.blob();
      
      // 将 blob 转换为 base64
      const reader = new FileReader();
      reader.readAsDataURL(blob);
      
      reader.onloadend = () => {
        const base64data = reader.result;
        
        // 调用父组件的回调
        onSelect({
          detection_region: {
            points: points,
            frame_size: frameSize
          },
          calibration: {
            frame: base64data  // 使用 base64 编码的图像数据
          }
        });
      };

      setOpen(false);
    } catch (error) {
      console.error('Error in calibration:', error);
    }
  };

  useEffect(() => {
    if (imageUrl) {
      drawCanvas();
    }
  }, [imageUrl, points, currentPoint, isComplete, draggingPointIndex]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (imageUrl) {
        URL.revokeObjectURL(imageUrl);
      }
    };
  }, []);

  return (
    <>
      <Button variant="outlined" onClick={() => setOpen(true)}>
        选择检测区域
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>选择检测区域</DialogTitle>
        <DialogContent>
          {/* 操作说明 */}
          <Paper sx={{ p: 2, mb: 2, bgcolor: '#2f2f2f', color: '#ffffff' }}>
            <Typography variant="subtitle2" gutterBottom>
              操作说明：
            </Typography>
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              <li>点击"开始预览"查看视频源画面</li>
              <li>点击"画线框"或"停止预览"保存当前画面</li>
              <li>在图像上点击选择区域顶点（至少3个点）</li>
              <li>点击"确定"完成区域选择</li>
            </ol>
          </Paper>

          {/* 操作按钮 */}
          <Paper sx={{ p: 2, mb: 2 }}>
            <Button 
              variant="contained" 
              onClick={isStreaming ? stopStreaming : startStreaming}
              disabled={!cameraId}
              sx={{ mr: 2 }}
            >
              {isStreaming ? '停止预览' : '开始预览'}
            </Button>
            <Button 
              variant="contained" 
              onClick={captureFrame}
              disabled={!cameraId || !isStreaming}
              sx={{ mr: 2 }}
            >
              画线框
            </Button>
            <Button 
              variant="outlined" 
              onClick={handleReset}
              disabled={!imageUrl}
            >
              重置
            </Button>
          </Paper>

          {/* 视频预览/图像区域 */}
          <Box sx={{ width: '100%', maxWidth: 800, margin: '0 auto' }}>
            {isStreaming && !imageUrl ? (
              <img
                src={getMjpegUrl()}
                alt="Video stream"
                style={{ 
                  width: '100%',
                  height: 'auto',
                  border: '1px solid #ccc'
                }}
              />
            ) : imageUrl && (
              <canvas
                ref={canvasRef}
                width={frameSize.width}
                height={frameSize.height}
                onClick={handleCanvasClick}
                onMouseMove={handleMouseMove}
                onMouseDown={handleMouseDown}
                onMouseUp={handleMouseUp}
                onMouseLeave={() => {
                  setHoveredPointIndex(null);
                  setDraggingPointIndex(null);
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  handleCanvasClick(e);
                }}
                style={{ 
                  border: '1px solid #ccc',
                  cursor: draggingPointIndex !== null ? 'grabbing' : 
                         hoveredPointIndex !== null ? 'grab' :
                         isComplete ? 'default' : 'crosshair'
                }}
              />
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>取消</Button>
          <Button 
            onClick={handleConfirm}
            variant="contained"
            disabled={points.length < 3}
          >
            确定
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default RegionSelectionTool;