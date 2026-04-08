import React, { useState, useRef, useEffect } from 'react';
import { 
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Paper, Box
} from '@mui/material';
import axios, { getBaseUrl } from '../utils/axios';

function BeltCalibrationTool({ cameraId, onCalibrate }) {
  const [open, setOpen] = useState(false);
  const [imageUrl, setImageUrl] = useState(null);
  const [points, setPoints] = useState([]);
  const [beltWidth, setBeltWidth] = useState(0); // 真实宽度(cm)
  const [isStreaming, setIsStreaming] = useState(false);
  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const [frameSize, setFrameSize] = useState({ width: 800, height: 600 });
  const [draggingPointIndex, setDraggingPointIndex] = useState(null);

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
    
    // 清除之前的标定图像和点
    if (imageUrl) {
      URL.revokeObjectURL(imageUrl);
      setImageUrl(null);
      setPoints([]);
      setBeltWidth(0);
    }
    
    setIsStreaming(true);
  };

  // 停止预览并截取当前帧用于画线
  const stopStreaming = async () => {
    setIsStreaming(false);
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

  // 从视频流中截取当前帧
  const captureFrame = async () => {
    if (isStreaming) {
      await stopStreaming();
    } else {
      await captureFrameFromServer();
    }
  };

  // 处理鼠标按下
  const handleMouseDown = (event) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    // 检查是否点击了已存在的点
    const clickedPointIndex = points.findIndex(point => {
      const distance = Math.sqrt(
        Math.pow(point.x - x, 2) + Math.pow(point.y - y, 2)
      );
      return distance < 10;  // 10像素的点击范围
    });

    if (clickedPointIndex !== -1) {
      // 如果点击了已存在的点，开始拖动
      setDraggingPointIndex(clickedPointIndex);
    }
  };

  // 处理画布点击
  const handleCanvasClick = (event) => {
    if (draggingPointIndex !== null) {
      // 如果正在拖动，则点击时确认新位置
      setDraggingPointIndex(null);
      return;
    }

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    if (points.length < 2) {
      // 如果点数小于2，添加新点
      setPoints([...points, { x, y }]);
    }
  };

  // 处理鼠标移动
  const handleMouseMove = (event) => {
    if (draggingPointIndex === null) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(event.clientX - rect.left, canvas.width));
    const y = Math.max(0, Math.min(event.clientY - rect.top, canvas.height));

    // 更新点的位置
    const newPoints = [...points];
    newPoints[draggingPointIndex] = { x, y };
    setPoints(newPoints);
  };

  // 处理鼠标松开
  const handleMouseUp = () => {
    setDraggingPointIndex(null);
  };

  // 绘制画布
  const drawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const image = imageRef.current;

    // 清空画布
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // 绘制图片
    if (image) {
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    }

    // 绘制点和线
    points.forEach((point, index) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, 5, 0, 2 * Math.PI);  // 增大点的大小
      ctx.fillStyle = index === draggingPointIndex ? 'yellow' : 'red';  // 拖动时改变颜色
      ctx.fill();
      ctx.strokeStyle = 'white';  // 添加白色边框
      ctx.lineWidth = 2;
      ctx.stroke();
    });

    if (points.length === 2) {
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      ctx.lineTo(points[1].x, points[1].y);
      ctx.strokeStyle = 'red';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  };

  // 计算标定结果
  const handleCalibrate = async () => {
    if (!imageUrl || points.length !== 2 || !beltWidth) return;

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
        onCalibrate({
          calibration: {
            points: points,
            belt_width: beltWidth,
            pixel_width: Math.sqrt(
              Math.pow(points[1].x - points[0].x, 2) + 
              Math.pow(points[1].y - points[0].y, 2)
            ),
            frame_size: frameSize,
            frame: base64data  // 使用 base64 编码的图像数据
          }
        });
      };

      setOpen(false);
    } catch (error) {
      console.error('Error in calibration:', error);
    }
  };

  // 重置标定
  const handleReset = () => {
    setPoints([]);
    setBeltWidth(0);
    if (imageUrl) {
      URL.revokeObjectURL(imageUrl);
      setImageUrl(null);
    }
  };

  useEffect(() => {
    if (imageUrl && canvasRef.current) {
      const image = new Image();
      image.src = imageUrl;
      image.onload = () => {
        imageRef.current = image;
        drawCanvas();
      };
    }
  }, [imageUrl]);

  useEffect(() => {
    if (canvasRef.current) {
      drawCanvas();
    }
  }, [points]);

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
        皮带宽度标定
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>皮带宽度标定</DialogTitle>
        <DialogContent>
          {/* 操作说明 */}
          <Paper style={{ 
            padding: 16, 
            marginBottom: 16, 
            backgroundColor: '#2f2f2f',
            color: '#ffffff'
          }}>
            <div style={{ 
              marginBottom: 8, 
              fontSize: '0.9rem', 
              fontWeight: 500 
            }}>
              操作说明：
            </div>
            <ol style={{ 
              margin: 0, 
              paddingLeft: 20,
              fontSize: '0.85rem'
            }}>
              <li>点击"开始预览"查看视频源画面</li>
              <li>点击"画线框"或"停止预览"保存当前画面</li>
              <li>在图像上标记皮带两边的点（可拖动调整位置）：
                <ul style={{ 
                  fontSize: '0.8rem',
                  color: '#e0e0e0'
                }}>
                  <li>单击添加标定点（需要标记2个点）</li>
                  <li>拖动已有的点可以微调位置</li>
                </ul>
              </li>
              <li>输入皮带实际宽度(cm)</li>
              <li>点击"确定"完成标定</li>
            </ol>
          </Paper>

          {/* 操作按钮 */}
          <Paper style={{ padding: 16, marginBottom: 16 }}>
            <Button 
              variant="contained" 
              onClick={isStreaming ? stopStreaming : startStreaming}
              disabled={!cameraId}
              style={{ marginRight: 16 }}
            >
              {isStreaming ? '停止预览' : '开始预览'}
            </Button>
            <Button 
              variant="contained" 
              onClick={captureFrame}
              disabled={!cameraId || !isStreaming}
              style={{ marginRight: 16 }}
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

          {/* 视频预览区域 */}
          {isStreaming && !imageUrl && (
            <Box 
              mb={2} 
              sx={{ 
                width: '100%',
                maxWidth: 800,
                display: 'flex',
                justifyContent: 'center'
              }}
            >
              <img
                src={getMjpegUrl()}
                style={{ 
                  width: '100%',
                  height: 'auto',
                  border: '1px solid #ccc',
                  objectFit: 'contain'
                }}
                alt="Video stream"
              />
            </Box>
          )}

          {/* 标定区域 */}
          {imageUrl && (
            <>
              <Box sx={{ 
                width: '100%',
                maxWidth: 800,
                display: 'flex',
                justifyContent: 'center'
              }}>
                <canvas
                  ref={canvasRef}
                  width={frameSize.width}
                  height={frameSize.height}
                  onClick={handleCanvasClick}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={handleMouseUp}
                  style={{ 
                    border: '1px solid #ccc', 
                    marginBottom: 16,
                    objectFit: 'contain',
                    cursor: draggingPointIndex !== null ? 'grabbing' : 'crosshair'
                  }}
                />
              </Box>
              <TextField
                fullWidth
                type="number"
                label="皮带实际宽度(cm)"
                value={beltWidth}
                onChange={(e) => setBeltWidth(parseFloat(e.target.value))}
                inputProps={{ min: 0, step: 0.1 }}
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>取消</Button>
          <Button 
            onClick={handleCalibrate}
            variant="contained"
            disabled={points.length !== 2 || !beltWidth}
          >
            确定
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default BeltCalibrationTool;