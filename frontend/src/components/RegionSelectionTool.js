import React, { useState, useRef, useEffect } from 'react';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  Paper, Box, Typography
} from '@mui/material';
import { useCameraPreviewSnapshot } from './hooks/useCameraPreviewSnapshot';

function RegionSelectionTool({ cameraId, onSelect, existingRegion, buttonLabel = '选择检测区域' }) {
  const [open, setOpen] = useState(false);
  const [points, setPoints] = useState([]);
  const [isComplete, setIsComplete] = useState(false);
  const [hoveredPointIndex, setHoveredPointIndex] = useState(null);
  const [draggingPointIndex, setDraggingPointIndex] = useState(null);
  const [currentPoint, setCurrentPoint] = useState(null);

  const canvasRef = useRef(null);
  const snapshotImgRef = useRef(null);
  const {
    isStreaming,
    imageUrl,
    frameSize,
    mjpegUrl,
    videoRef,
    startStreaming,
    stopPreviewTraffic,
    clearImage,
    setImmediateSnapshot,
    captureFrameFromServer,
    setImageUrl,
    setFrameSize,
  } = useCameraPreviewSnapshot(cameraId, { maxWidth: 800 });

  // 加载已有的区域数据
  useEffect(() => {
    if (open && existingRegion && existingRegion.detection_region) {
      if (existingRegion.calibration && existingRegion.calibration.image_data) {
        setImageUrl(existingRegion.calibration.image_data);
        stopPreviewTraffic();
      }
      if (existingRegion.detection_region.points) {
        setPoints(existingRegion.detection_region.points);
        setIsComplete(true);
      }
      if (existingRegion.detection_region.frame_size) {
        setFrameSize(existingRegion.detection_region.frame_size);
      }
    }
  }, [open, existingRegion, setFrameSize, setImageUrl, stopPreviewTraffic]);

  // 开始预览
  const handleStartPreview = () => {
    clearImage();
    setPoints([]);
    setIsComplete(false);
    startStreaming();
  };

  const calculateAspectRatio = (originalWidth, originalHeight, maxWidth = 800) => {
    const ratio = originalWidth / originalHeight;
    return { width: maxWidth, height: maxWidth / ratio };
  };

  const handlePauseAndFreeze = async () => {
    // 本地冻结当前帧（避免 UI 闪烁）并立即断流。
    // 仅当本地快照失败（如 canvas taint/CORS）时，才回退到服务端截帧。
    const imgEl = videoRef.current;
    let snapshotOk = false;
    if (imgEl && imgEl.naturalWidth && imgEl.naturalHeight) {
      const off = document.createElement('canvas');
      off.width = imgEl.naturalWidth;
      off.height = imgEl.naturalHeight;
      const ctx = off.getContext('2d');
      if (ctx) {
        try {
          ctx.drawImage(imgEl, 0, 0);
          const dataUrl = off.toDataURL('image/jpeg', 0.85);
          setImmediateSnapshot(dataUrl, calculateAspectRatio(off.width, off.height, 800));
          snapshotOk = true;
        } catch (e) {
          snapshotOk = false;
          // ignore and fallback below
        }
      }
    }
    if (snapshotOk) {
      await new Promise((resolve) => requestAnimationFrame(resolve));
      stopPreviewTraffic();
      return;
    }
    // 本地冻结失败时，先拿到服务端静态帧再断流，避免出现约 1s 的空白闪烁
    await captureFrameFromServer();
    stopPreviewTraffic();
  };

  // 关闭
  const handleClose = () => {
    stopPreviewTraffic();
    clearImage();
    setOpen(false);
  };

  const handleCanvasClick = (event) => {
    if (!imageUrl || isComplete) return;
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    setPoints(prev => [...prev, {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY
    }]);
  };

  const handleMouseMove = (event) => {
    if (!imageUrl) return;
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const pos = { x: (event.clientX - rect.left) * scaleX, y: (event.clientY - rect.top) * scaleY };

    const hoverIndex = points.findIndex(p => Math.hypot(p.x - pos.x, p.y - pos.y) < 10);
    setHoveredPointIndex(hoverIndex);

    if (draggingPointIndex !== null) {
      setPoints(prev => prev.map((p, i) => i === draggingPointIndex ? pos : p));
    } else if (!isComplete) {
      setCurrentPoint(pos);
    }
    drawCanvas();
  };

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas || !imageUrl) return;
    const img = snapshotImgRef.current;
    if (!img) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    if (points.length > 0) {
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      points.forEach(p => ctx.lineTo(p.x, p.y));
      if (isComplete) ctx.closePath();
      else if (currentPoint) ctx.lineTo(currentPoint.x, currentPoint.y);
      ctx.strokeStyle = 'yellow';
      ctx.lineWidth = 2;
      ctx.stroke();
      if (isComplete) {
        ctx.fillStyle = 'rgba(255, 255, 0, 0.2)';
        ctx.fill();
      }
      points.forEach((p, i) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = draggingPointIndex === i ? 'blue' : (hoveredPointIndex === i ? 'yellow' : 'red');
        ctx.fill();
        ctx.stroke();
      });
    }
  };

  const handleReset = () => {
    setPoints([]);
    setCurrentPoint(null);
    setIsComplete(false);
    setHoveredPointIndex(null);
    setDraggingPointIndex(null);
  };

  const handleConfirm = async () => {
    if (points.length < 3 || !imageUrl) return;
    try {
      const response = await fetch(imageUrl);
      const blob = await response.blob();
      const reader = new FileReader();
      reader.readAsDataURL(blob);
      reader.onloadend = () => {
        onSelect({
          detection_region: { points, frame_size: frameSize },
          calibration: { frame: reader.result }
        });
      };
      setOpen(false);
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    if (!imageUrl) {
      snapshotImgRef.current = null;
      return;
    }
    const img = new Image();
    img.onload = () => {
      snapshotImgRef.current = img;
      drawCanvas();
    };
    img.src = imageUrl;
  }, [imageUrl]);

  useEffect(() => { if (imageUrl) drawCanvas(); }, [imageUrl, points, currentPoint, isComplete, draggingPointIndex]);

  return (
    <>
      <Button variant="outlined" size="small" onClick={() => setOpen(true)}>{buttonLabel}</Button>
      <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
        <DialogTitle>选择检测区域</DialogTitle>
        <DialogContent>
          <Paper sx={{ p: 2, mb: 2, bgcolor: '#2f2f2f', color: '#ffffff' }}>
            <Typography variant="subtitle2">操作说明：</Typography>
            <ol style={{ fontSize: '0.85rem' }}>
              <li>点击"开始预览"查看实时画面</li>
              <li>点击"暂停并截帧"冻结当前画面，然后开始标注区域</li>
              <li>点击画面添加顶点，右键或点击起始点完成闭合</li>
            </ol>
          </Paper>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Button variant="contained" onClick={isStreaming ? handlePauseAndFreeze : handleStartPreview} sx={{ mr: 2 }}>
              {isStreaming ? '暂停并截帧' : '开始预览'}
            </Button>
            <Button variant="outlined" onClick={handleReset} disabled={!imageUrl}>重置</Button>
          </Paper>
          <Box sx={{ width: '100%', maxWidth: 800, margin: '0 auto', textAlign: 'center' }}>
            {isStreaming && !imageUrl && (
              <img
                ref={videoRef}
                src={mjpegUrl}
                alt="Live"
                style={{ width: '100%', border: '1px solid #ccc' }}
              />
            )}
            {imageUrl && (
              <canvas
                ref={canvasRef}
                width={frameSize.width}
                height={frameSize.height}
                onClick={handleCanvasClick}
                onMouseMove={handleMouseMove}
                onMouseDown={(e) => setDraggingPointIndex(hoveredPointIndex)}
                onMouseUp={() => setDraggingPointIndex(null)}
                onContextMenu={(e) => { e.preventDefault(); if (points.length >= 3) setIsComplete(true); }}
                style={{ border: '1px solid #ccc', cursor: draggingPointIndex !== null ? 'grabbing' : 'crosshair' }}
              />
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>取消</Button>
          <Button onClick={handleConfirm} variant="contained" disabled={points.length < 3}>确定</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default RegionSelectionTool;