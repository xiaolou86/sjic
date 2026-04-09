import { useCallback, useEffect, useRef, useState } from 'react';
import axios, { getBaseUrl } from '../../utils/axios';

// 用于断开 MJPEG 连接的静态透明像素
const STOP_URL =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

function calculateAspectRatio(originalWidth, originalHeight, maxWidth = 800) {
  const ratio = originalWidth / originalHeight;
  return { width: maxWidth, height: maxWidth / ratio };
}

export function useCameraPreviewSnapshot(cameraId, { maxWidth = 800 } = {}) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [imageUrl, setImageUrl] = useState(null);
  const [frameSize, setFrameSize] = useState({ width: maxWidth, height: (maxWidth * 3) / 4 });
  const [streamKey, setStreamKey] = useState(0);

  const videoRef = useRef(null);
  const lastBlobUrlRef = useRef(null);

  const revokeIfBlobUrl = useCallback((url) => {
    if (url && typeof url === 'string' && url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(url);
      } catch {
        // ignore
      }
    }
  }, []);

  const stopPreviewTraffic = useCallback(() => {
    if (videoRef.current) {
      videoRef.current.src = STOP_URL;
    }
    setIsStreaming(false);
  }, []);

  const clearImage = useCallback(() => {
    setImageUrl((prev) => {
      revokeIfBlobUrl(prev);
      return null;
    });
    lastBlobUrlRef.current = null;
  }, [revokeIfBlobUrl]);

  const setImmediateSnapshot = useCallback((dataUrl, nextFrameSize) => {
    // dataUrl(如 data:image/jpeg;base64,...) 不需要 revoke
    setImageUrl(dataUrl);
    if (nextFrameSize) setFrameSize(nextFrameSize);
  }, []);

  const startStreaming = useCallback(() => {
    if (!cameraId) return;
    // 重新开始预览时，立刻清掉静态帧，避免继续占用内存
    clearImage();
    setIsStreaming(true);
    setStreamKey(Date.now());
  }, [cameraId, clearImage]);

  const captureFrameFromServer = useCallback(async () => {
    if (!cameraId) return;
    const resp = await axios.post(
      '/api/cameras/capture',
      { camera_id: cameraId },
      { responseType: 'blob' }
    );
    const blob = resp instanceof Blob ? resp : new Blob([resp], { type: 'image/jpeg' });
    const url = URL.createObjectURL(blob);

    // 先记录，等新图真正 load 成功后再替换/回收旧的，避免白屏闪烁
    const nextUrl = url;

    await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        setFrameSize(calculateAspectRatio(img.width, img.height, maxWidth));
        setImageUrl((prev) => {
          revokeIfBlobUrl(prev);
          return nextUrl;
        });
        lastBlobUrlRef.current = nextUrl;
        resolve();
      };
      img.onerror = () => {
        revokeIfBlobUrl(nextUrl);
        reject(new Error('Failed to load captured frame'));
      };
      img.src = nextUrl;
    });
  }, [cameraId, maxWidth, revokeIfBlobUrl]);

  // 需求点：停止预览 / 进入画框时立即停止流量
  const stopStreamingAndCapture = useCallback(async () => {
    stopPreviewTraffic();
    await captureFrameFromServer();
  }, [captureFrameFromServer, stopPreviewTraffic]);

  const mjpegUrl = cameraId ? `${getBaseUrl()}/api/mjpeg/${cameraId}?t=${streamKey}` : null;

  useEffect(() => {
    return () => {
      // 组件卸载时确保断开连接并回收 blob
      try {
        if (videoRef.current) videoRef.current.src = STOP_URL;
      } catch {
        // ignore
      }
      revokeIfBlobUrl(lastBlobUrlRef.current);
    };
  }, [revokeIfBlobUrl]);

  return {
    STOP_URL,
    isStreaming,
    imageUrl,
    frameSize,
    streamKey,
    videoRef,
    mjpegUrl,
    clearImage,
    setImmediateSnapshot,
    setImageUrl,
    setFrameSize,
    startStreaming,
    stopPreviewTraffic,
    captureFrameFromServer,
    stopStreamingAndCapture,
  };
}

