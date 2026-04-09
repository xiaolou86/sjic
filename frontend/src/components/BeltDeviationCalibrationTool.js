import React, { useState, useRef, useEffect } from 'react';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Paper, Box, Grid, Typography
} from '@mui/material';
import { useCameraPreviewSnapshot } from './hooks/useCameraPreviewSnapshot';

function BeltDeviationCalibrationTool({ cameraId, algorithm_parameters, onCalibrate }) {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState([]);
  const [boundaryDistance, setBoundaryDistance] = useState(0);
  const [deviationThreshold, setDeviationThreshold] = useState(0);
  const [currentLine, setCurrentLine] = useState(null);
  const [draggingPoint, setDraggingPoint] = useState(null);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

  const canvasRef = useRef(null);
  const snapshotImgRef = useRef(null);
  const originalParametersRef = useRef(null);

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
    setFrameSize,
  } = useCameraPreviewSnapshot(cameraId, { maxWidth: 800 });

  useEffect(() => {
    if (algorithm_parameters && algorithm_parameters.calibration) {
      originalParametersRef.current = JSON.parse(JSON.stringify(algorithm_parameters));
      const cal = algorithm_parameters.calibration;
      if (cal.frame_size) setFrameSize(cal.frame_size);
      if (cal.boundary_lines) setLines(cal.boundary_lines);
      if (cal.boundary_distance) setBoundaryDistance(cal.boundary_distance);
      if (cal.deviation_threshold) setDeviationThreshold(cal.deviation_threshold);
    }
  }, [algorithm_parameters]);

  const handleStartPreview = () => {
    setLines([]);
    setBoundaryDistance(0);
    setDeviationThreshold(0);
    setCurrentLine(null);
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

  const handleCanvasClick = (event) => {
    if (draggingPoint) {
      setDraggingPoint(null);
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    const pos = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    if (lines.length < 2) {
      if (!currentLine) setCurrentLine([pos]);
      else {
        setLines([...lines, [...currentLine, pos]]);
        setCurrentLine(null);
      }
    }
  };

  const handleMouseDown = (event) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    lines.forEach((line, lidx) => {
      line.forEach((p, pidx) => {
        if (Math.hypot(p.x - x, p.y - y) < 10) setDraggingPoint({ lineIndex: lidx, pointIndex: pidx });
      });
    });
  };

  const handleMouseMove = (event) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const pos = {
      x: Math.max(0, Math.min(event.clientX - rect.left, canvasRef.current.width)),
      y: Math.max(0, Math.min(event.clientY - rect.top, canvasRef.current.height))
    };
    setMousePosition(pos);
    if (draggingPoint) {
      const newLines = [...lines];
      newLines[draggingPoint.lineIndex][draggingPoint.pointIndex] = pos;
      setLines(newLines);
    }
  };

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas || !imageUrl) return;
    const img = snapshotImgRef.current;
    if (!img) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    lines.forEach((line, idx) => {
      ctx.beginPath();
      ctx.moveTo(line[0].x, line[0].y);
      ctx.lineTo(line[1].x, line[1].y);
      ctx.strokeStyle = idx === 0 ? 'blue' : 'red';
      ctx.lineWidth = 2;
      ctx.stroke();
      line.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, 2 * Math.PI);
        ctx.fillStyle = 'yellow';
        ctx.fill();
        ctx.stroke();
      });
    });
    if (currentLine?.length === 1) {
      ctx.beginPath();
      ctx.moveTo(currentLine[0].x, currentLine[0].y);
      ctx.lineTo(mousePosition.x, mousePosition.y);
      ctx.strokeStyle = 'gray';
      ctx.setLineDash([5, 5]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  };

  const handleReset = () => {
    if (originalParametersRef.current?.calibration) {
      const cal = originalParametersRef.current.calibration;
      setLines(cal.boundary_lines || []);
      setBoundaryDistance(cal.boundary_distance || 0);
      setDeviationThreshold(cal.deviation_threshold || 0);
    } else {
      setLines([]); setBoundaryDistance(0); setDeviationThreshold(0);
    }
    setCurrentLine(null);
  };

  const handleCalibrate = async () => {
    if (!imageUrl || lines.length !== 2 || !boundaryDistance || !deviationThreshold) return;
    try {
      const resp = await fetch(imageUrl);
      const blob = await resp.blob();
      const reader = new FileReader();
      reader.readAsDataURL(blob);
      reader.onloadend = () => {
        onCalibrate({
          calibration: {
            boundary_lines: lines, boundary_distance: boundaryDistance,
            deviation_threshold: deviationThreshold, frame_size: frameSize,
            frame: reader.result
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

  useEffect(() => { if (imageUrl) drawCanvas(); }, [lines, currentLine, mousePosition, imageUrl]);

  return (
    <>
      <Button variant="outlined" onClick={() => setOpen(true)}>边界标定</Button>
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>边界标定</DialogTitle>
        <DialogContent>
          <Paper sx={{ p: 2, mb: 2, bgcolor: '#2f2f2f', color: '#ffffff' }}>
            <Typography variant="subtitle2">操作说明：</Typography>
            <ol style={{ fontSize: '0.85rem' }}>
              <li>点击"开始预览"查看实时画面</li>
              <li>点击"暂停并截帧"冻结当前画面，然后画两条线标记皮带左右边界</li>
              <li>输入间距及报警阈值(cm)后确定</li>
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
                  onMouseUp={() => setDraggingPoint(null)}
                  style={{ border: '1px solid #ccc', cursor: draggingPoint ? 'grabbing' : 'crosshair' }}
                />
                <Grid container spacing={2} sx={{ mt: 2 }}>
                  <Grid item xs={6}>
                    <TextField fullWidth type="number" label="边界线间距离(cm)" value={boundaryDistance}
                               onChange={(e) => setBoundaryDistance(parseFloat(e.target.value))} />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField fullWidth type="number" label="跑偏报警阈值(cm)" value={deviationThreshold}
                               onChange={(e) => setDeviationThreshold(parseFloat(e.target.value))} />
                  </Grid>
                </Grid>
              </>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>取消</Button>
          <Button onClick={handleCalibrate} variant="contained" disabled={lines.length !== 2 || !boundaryDistance || !deviationThreshold}>确定</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default BeltDeviationCalibrationTool;