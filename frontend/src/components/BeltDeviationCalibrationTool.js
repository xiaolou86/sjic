import React, { useState, useRef, useEffect } from 'react';
import { 
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Paper, Box, Grid
} from '@mui/material';
import axios, { getBaseUrl } from '../utils/axios';

function BeltDeviationCalibrationTool({ cameraId, algorithm_parameters, onCalibrate}) {
  const [open, setOpen] = useState(false);
  const [imageUrl, setImageUrl] = useState(null);
  const [lines, setLines] = useState([]); // 存储2条边界线，每条线由2个点组成
  const [isStreaming, setIsStreaming] = useState(false);
  const [frameSize, setFrameSize] = useState({ width: 800, height: 600 });
  const [boundaryDistance, setBoundaryDistance] = useState(0); // 两条边界线之间的实际距离(cm)
  const [deviationThreshold, setDeviationThreshold] = useState(0); // 跑偏报警阈值(cm)
  const [currentLine, setCurrentLine] = useState(null); // 当前正在绘制的线
  const [draggingPoint, setDraggingPoint] = useState(null); // 当前拖动的点 {lineIndex, pointIndex}
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  
  // 在组件顶部添加一个 ref 来存储原始参数
  const originalParametersRef = useRef(null);

  // 加载已有的区域数据
  useEffect(() => {
    if (algorithm_parameters && algorithm_parameters.calibration) {
      // 保存原始参数的深拷贝
      originalParametersRef.current = JSON.parse(JSON.stringify(algorithm_parameters));
      
      if (algorithm_parameters.calibration.frame_size) {
        setFrameSize(algorithm_parameters.calibration.frame_size);
      }
      if (algorithm_parameters.calibration.boundary_lines) {
        setLines(algorithm_parameters.calibration.boundary_lines);
      }
      if (algorithm_parameters.calibration.boundary_distance) {
        setBoundaryDistance(algorithm_parameters.calibration.boundary_distance);
      }
      if (algorithm_parameters.calibration.deviation_threshold) {
        setDeviationThreshold(algorithm_parameters.calibration.deviation_threshold);
      }
    }
  }, [algorithm_parameters]);

  // 添加缺失的 refs
  const canvasRef = useRef(null);
  const imageRef = useRef(null);

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
    
    // 清除之前的标定图像和数据
    if (imageUrl) {
      URL.revokeObjectURL(imageUrl);
      setImageUrl(null);
      setLines([]);
      setBoundaryDistance(0);
      setDeviationThreshold(0);
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

  // 处理画布点击
  const handleCanvasClick = (event) => {
    if (draggingPoint) {
      setDraggingPoint(null);
      return;
    }

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    if (lines.length < 2) {
      if (!currentLine) {
        // 开始新线
        setCurrentLine([{ x, y }]);
      } else if (currentLine.length === 1) {
        // 完成当前线
        const newLine = [...currentLine, { x, y }];
        setLines([...lines, newLine]);
        setCurrentLine(null);
      }
    }
  };

  // 处理鼠标按下
  const handleMouseDown = (event) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    // 检查是否点击了已存在线的端点
    lines.forEach((line, lineIndex) => {
      line.forEach((point, pointIndex) => {
        const distance = Math.sqrt(
          Math.pow(point.x - x, 2) + Math.pow(point.y - y, 2)
        );
        if (distance < 10) {
          setDraggingPoint({ lineIndex, pointIndex });
        }
      });
    });
  };

  // 处理鼠标移动
  const handleMouseMove = (event) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(event.clientX - rect.left, canvas.width));
    const y = Math.max(0, Math.min(event.clientY - rect.top, canvas.height));
    
    setMousePosition({ x, y });

    if (draggingPoint) {
      // 更新拖动点的位置
      const newLines = [...lines];
      newLines[draggingPoint.lineIndex][draggingPoint.pointIndex] = { x, y };
      setLines(newLines);
    }
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

    // 绘制已完成的线
    lines.forEach((line, index) => {
      ctx.beginPath();
      ctx.moveTo(line[0].x, line[0].y);
      ctx.lineTo(line[1].x, line[1].y);
      ctx.strokeStyle = index === 0 ? 'blue' : 'red';
      ctx.lineWidth = 2;
      ctx.stroke();

      // 绘制端点
      line.forEach(point => {
        ctx.beginPath();
        ctx.arc(point.x, point.y, 5, 0, 2 * Math.PI);
        ctx.fillStyle = 'yellow';
        ctx.fill();
        ctx.strokeStyle = 'white';
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    });

    // 绘制正在绘制的线
    if (currentLine?.length === 1) {
      ctx.beginPath();
      ctx.moveTo(currentLine[0].x, currentLine[0].y);
      ctx.lineTo(mousePosition.x, mousePosition.y);
      ctx.strokeStyle = 'gray';
      ctx.setLineDash([5, 5]); // 添加虚线效果
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]); // 恢复实线
    }
  };

  // 计算标定结果
  const handleCalibrate = async () => {
    if (!imageUrl || lines.length !== 2 || !boundaryDistance || !deviationThreshold) return;

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
            boundary_lines: lines,
            boundary_distance: boundaryDistance,
            deviation_threshold: deviationThreshold,
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
    // 如果有原始参数，使用它们
    if (originalParametersRef.current && originalParametersRef.current.calibration) {
      const originalCalibration = originalParametersRef.current.calibration;
      
      if (originalCalibration.boundary_lines) {
        setLines([...originalCalibration.boundary_lines]);
      } else {
        setLines([]);
      }
      
      if (originalCalibration.boundary_distance) {
        setBoundaryDistance(originalCalibration.boundary_distance);
      } else {
        setBoundaryDistance(0);
      }
      
      if (originalCalibration.deviation_threshold) {
        setDeviationThreshold(originalCalibration.deviation_threshold);
      } else {
        setDeviationThreshold(0);
      }
    } else {
      // 如果没有原始参数，重置为空
      setLines([]);
      setBoundaryDistance(0);
      setDeviationThreshold(0);
    }
    
    setCurrentLine(null);
  };

  // 添加 useEffect 来监听鼠标位置变化
  useEffect(() => {
    if (canvasRef.current) {
      drawCanvas();
    }
  }, [lines, currentLine, mousePosition, imageUrl]);

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
        边界标定
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>边界标定</DialogTitle>
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
              <li>在图像上标记两条边界线（可拖动调整位置）：
                <ul style={{ 
                  fontSize: '0.8rem',
                  color: '#e0e0e0'
                }}>
                  <li>点击两个点绘制一条线</li>
                  <li>需要绘制两条边界线</li>
                  <li>可拖动端点调整位置</li>
                </ul>
              </li>
              <li>输入两条边界线之间的实际距离(cm)</li>
              <li>输入允许的最大跑偏距离(cm)</li>
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
                justifyContent: 'center',
                marginBottom: 2
              }}>
                <img
                  ref={imageRef}
                  src={imageUrl}
                  style={{
                    display: 'none'  // 隐藏原始图片，只用于 canvas 绘制
                  }}
                  onLoad={() => {
                    if (canvasRef.current) {
                      drawCanvas();
                    }
                  }}
                  alt="Calibration"
                />
                <canvas
                  ref={canvasRef}
                  width={frameSize.width}
                  height={frameSize.height}
                  onClick={handleCanvasClick}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={() => setDraggingPoint(null)}
                  onMouseLeave={() => setDraggingPoint(null)}
                  style={{ 
                    border: '1px solid #ccc',
                    objectFit: 'contain',
                    cursor: draggingPoint ? 'grabbing' : currentLine ? 'crosshair' : 'default'
                  }}
                />
              </Box>

              {/* 参数输入 */}
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    type="number"
                    label="边界线间距离(cm)"
                    value={boundaryDistance}
                    onChange={(e) => setBoundaryDistance(parseFloat(e.target.value))}
                    inputProps={{ min: 0, step: 0.1 }}
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    type="number"
                    label="跑偏报警阈值(cm)"
                    value={deviationThreshold}
                    onChange={(e) => setDeviationThreshold(parseFloat(e.target.value))}
                    inputProps={{ min: 0, step: 0.1 }}
                  />
                </Grid>
              </Grid>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>取消</Button>
          <Button 
            onClick={handleCalibrate}
            variant="contained"
            disabled={lines.length !== 2 || !boundaryDistance || !deviationThreshold}
          >
            确定
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default BeltDeviationCalibrationTool;