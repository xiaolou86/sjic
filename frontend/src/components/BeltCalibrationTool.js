import React, { useState, useRef, useEffect } from 'react';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Paper, Box, Typography
} from '@mui/material';
import { useCameraPreviewSnapshot } from './hooks/useCameraPreviewSnapshot';

function BeltCalibrationTool({ cameraId, onCalibrate }) {
  const [open, setOpen] = useState(false);
  const [points, setPoints] = useState([]);
  const [beltWidth, setBeltWidth] = useState(0); 
  const [draggingPointIndex, setDraggingPointIndex] = useState(null);

  const canvasRef = useRef(null);
  const snapshotImgRef = useRef(null);

  const {
    isStreaming,
    imageUrl,
    frameSize,
    videoRef,
    mjpegUrl,
    startStreaming,
    stopPreviewTraffic,
    clearImage,
    setImmediateSnapshot,
    captureFrameFromServer,
  } = useCameraPreviewSnapshot(cameraId, { maxWidth: 800 });

  const handleStartPreview = () => {
    setPoints([]);
    setBeltWidth(0);
    startStreaming();
  };

  const calculateAspectRatio = (originalWidth, originalHeight, maxWidth = 800) => {
    const ratio = originalWidth / originalHeight;
    return { width: maxWidth, height: maxWidth / ratio };
  };

  const handlePauseAndFreeze = async () => {
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

  const handleClose = () => {
    stopPreviewTraffic();
    clearImage();
    setOpen(false);
  };

  const handleMouseDown = (event) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const clickedIdx = points.findIndex(p => Math.hypot(p.x - x, p.y - y) < 10);
    if (clickedIdx !== -1) setDraggingPointIndex(clickedIdx);
  };

  const handleCanvasClick = (event) => {
    if (draggingPointIndex !== null) {
      setDraggingPointIndex(null);
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    if (points.length < 2) {
      setPoints([...points, { x: event.clientX - rect.left, y: event.clientY - rect.top }]);
    }
  };

  const handleMouseMove = (event) => {
    if (draggingPointIndex === null) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const newPoints = [...points];
    newPoints[draggingPointIndex] = {
      x: Math.max(0, Math.min(event.clientX - rect.left, canvasRef.current.width)),
      y: Math.max(0, Math.min(event.clientY - rect.top, canvasRef.current.height))
    };
    setPoints(newPoints);
  };

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas || !imageUrl) return;
    const image = snapshotImgRef.current;
    if (!image) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    points.forEach((p, idx) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 5, 0, 2 * Math.PI);
      ctx.fillStyle = draggingPointIndex === idx ? 'yellow' : 'red';
      ctx.fill();
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

  const handleReset = () => {
    setPoints([]);
    setBeltWidth(0);
    setDraggingPointIndex(null);
  };

  const handleCalibrate = async () => {
    if (!imageUrl || points.length !== 2 || !beltWidth) return;
    try {
      const resp = await fetch(imageUrl);
      const blob = await resp.blob();
      const reader = new FileReader();
      reader.readAsDataURL(blob);
      reader.onloadend = () => {
        onCalibrate({
          calibration: {
            points, belt_width: beltWidth,
            pixel_width: Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y),
            frame_size: frameSize, frame: reader.result
          }
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

  useEffect(() => { if (imageUrl) drawCanvas(); }, [imageUrl, points]);

  return (
    <>
      <Button variant="outlined" onClick={() => setOpen(true)}>皮带宽度标定</Button>
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>皮带宽度标定</DialogTitle>
        <DialogContent>
          <Paper sx={{ p: 2, mb: 2, bgcolor: '#2f2f2f', color: '#ffffff' }}>
            <Typography variant="subtitle2">操作说明：</Typography>
            <ol style={{ fontSize: '0.85rem' }}>
              <li>点击"开始预览"查看实时画面</li>
              <li>点击"暂停并截帧"冻结当前画面，然后点击两点标记皮带宽度</li>
              <li>完成后输入实际宽度(cm)并确认</li>
            </ol>
          </Paper>
          <Paper sx={{ p: 1, mb: 2 }}>
            <Button variant="contained" onClick={isStreaming ? handlePauseAndFreeze : handleStartPreview} sx={{ mr: 2 }}>
              {isStreaming ? '暂停并截帧' : '开始预览'}
            </Button>
            <Button variant="outlined" onClick={handleReset} disabled={!imageUrl}>重置</Button>
          </Paper>
          <Box sx={{ width: '100%', textAlign: 'center' }}>
            {isStreaming && !imageUrl && (
              <img
                ref={videoRef}
                src={mjpegUrl}
                style={{ width: '100%', border: '1px solid #ccc' }}
                alt="Live"
              />
            )}
            {imageUrl && (
              <>
                <canvas
                  ref={canvasRef}
                  width={frameSize.width}
                  height={frameSize.height}
                  onClick={handleCanvasClick}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={() => setDraggingPointIndex(null)}
                  style={{ border: '1px solid #ccc', cursor: draggingPointIndex !== null ? 'grabbing' : 'crosshair' }}
                />
                <TextField fullWidth type="number" label="皮带实际宽度(cm)" value={beltWidth} sx={{ mt: 2 }}
                           onChange={(e) => setBeltWidth(parseFloat(e.target.value))} />
              </>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>取消</Button>
          <Button onClick={handleCalibrate} variant="contained" disabled={points.length !== 2 || !beltWidth}>确定</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default BeltCalibrationTool;