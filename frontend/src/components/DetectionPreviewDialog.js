import React, { useEffect, useState } from 'react';
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  Typography
} from '@mui/material';
import axios from '../utils/axios';
import { taskStatusLabel } from '../utils/taskStatus';

export function taskPreviewEngines(task) {
  if (!task) return [];
  if (task.pipeline === 'exam' || task.algorithm_engine === 'exam_pipeline' || task.od_algorithm_id || task.pose_algorithm_id) {
    const engines = [];
    if (task.od_algorithm_id) engines.push('object_detection');
    if (task.pose_algorithm_id) engines.push('pose_behavior');
    if (engines.length) return engines;
  }
  if (task.algorithm_engine === 'object_detection' || task.algorithm_engine === 'pose_behavior') {
    return [task.algorithm_engine];
  }
  return [];
}

function formatScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return number.toFixed(2);
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return `${Math.round(number * 100)}%`;
}

function extractApiError(error, fallback) {
  const data = error?.response?.data;
  if (typeof data?.error === 'string' && data.error) return data.error;
  return fallback;
}

function CountBlock({ title, data, emptyText, noun, hint }) {
  if (!data) {
    return (
      <Box sx={{ flex: 1, minWidth: 220 }}>
        <Typography variant="subtitle1">{title}</Typography>
        <Typography variant="body2" color="text.secondary">这一帧还没有{title}结果</Typography>
      </Box>
    );
  }
  if (data.ok === false) {
    return (
      <Box sx={{ flex: 1, minWidth: 220 }}>
        <Typography variant="subtitle1">{title}</Typography>
        <Typography variant="body2" color="error">这一帧推理失败</Typography>
      </Box>
    );
  }
  const classes = Array.isArray(data.classes) ? data.classes : [];
  return (
    <Box sx={{ flex: 1, minWidth: 220 }}>
      <Typography variant="subtitle1">{title}</Typography>
      <Typography variant="h5" sx={{ my: 0.5 }}>
        {data.count ?? 0}
        <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
          个超过阈值的{noun}
        </Typography>
      </Typography>
      <Typography variant="body2" color="text.secondary">
        推理阈值 {formatScore(data.threshold)}
        {data.with_skeleton != null ? ` · 有骨骼点 ${data.with_skeleton}` : ''}
        {data.max_confidence ? ` · 最高 ${formatScore(data.max_confidence)}` : ''}
      </Typography>
      {hint && (
        <Typography variant="body2" color="text.secondary">{hint}</Typography>
      )}
      {data.shown != null && data.count > data.shown && (
        <Typography variant="body2" color="text.secondary">
          画面上画出置信度最高的 {data.shown} 个，其余只计入上面的数量
        </Typography>
      )}
      {classes.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mt: 1 }}>
          {classes.map((item) => (
            <Chip
              key={`${item.id}-${item.name}`}
              size="small"
              variant="outlined"
              label={`${item.name} ${item.count} · 最高 ${formatScore(item.max_confidence)}`}
            />
          ))}
        </Box>
      )}
      {!classes.length && (data.count ?? 0) === 0 && (
        <Typography variant="body2" sx={{ mt: 1 }}>{emptyText}</Typography>
      )}
    </Box>
  );
}

const MOUNT_LABEL = {
  front_top: '前上方',
  back_top: '后上方',
  side_top: '侧上方',
  top: '正上方',
};

function PoseDebug({ pose, scenes }) {
  const people = Array.isArray(pose?.people) ? pose.people : [];
  const sceneRows = Array.isArray(scenes) ? scenes : [];
  if (!people.length && !sceneRows.length) return null;
  return (
    <Box sx={{ mt: 2 }}>
      {people.map((person, index) => (
        <Box key={`person-${index}`} sx={{ mb: 2 }}>
          <Typography variant="subtitle2">
            人{person.index || index + 1} 骨骼点
            {person.confidence != null ? ` · 置信度 ${formatScore(person.confidence)}` : ''}
            {person.usable != null ? ` · 可用 ${person.usable}/17` : ''}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            编号和画面上的「人1」是同一个人。坐标是这张推理图的像素。不可用表示置信度不够或坐标为 0，几何判断会当这个点不存在。
            {Array.isArray(person.missing) && person.missing.length ? ` 不可用：${person.missing.join('、')}` : ''}
          </Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 0.25, mt: 0.75 }}>
            {(person.points || []).map((point) => (
              <Typography
                key={point.i}
                variant="caption"
                sx={{ fontFamily: 'monospace', color: point.ok ? 'text.primary' : 'text.disabled' }}
              >
                {point.ok
                  ? `${point.name} ${point.x},${point.y} c${formatScore(point.c)}`
                  : `${point.name} 不可用${point.c != null ? ` c${formatScore(point.c)}` : ''}`}
              </Typography>
            ))}
          </Box>
        </Box>
      ))}
      {sceneRows.length > 0 && (
        <Box>
          <Typography variant="subtitle2">本帧场景</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
            「成立」只说明这一帧的几何条件过了。告警还要凑够停留时间，并且不在冷却时间内。
          </Typography>
          {sceneRows.map((scene, index) => (
            <Box key={`${scene.type || 'scene'}-${index}`} sx={{ mb: 1 }}>
              <Typography variant="body2">
                {scene.name || '场景'}
                {scene.view ? ` · ${MOUNT_LABEL[scene.view] || scene.view}` : ''}
                {scene.seconds ? ` · 需持续 ${scene.seconds}s` : ''}
              </Typography>
              {scene.reason && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  {scene.reason}
                </Typography>
              )}
              {(scene.people || []).map((person, personIndex) => (
                <Typography key={personIndex} variant="caption" sx={{ display: 'block' }}>
                  {person.index ? `人${person.index} · ` : ''}
                  {person.hit ? '本帧成立' : '本帧不成立'}
                  {person.confidence != null ? ` · 置信度 ${formatScore(person.confidence)}` : ''}
                  {person.held != null ? ` · 已持续 ${person.held}s` : ''}
                  {person.reason ? ` · ${person.reason}` : ''}
                </Typography>
              ))}
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

function DetectionPreviewDialog({ task, onClose }) {
  const [image, setImage] = useState(null);
  const [stats, setStats] = useState(null);
  const [ageMs, setAgeMs] = useState(null);
  const [waiting, setWaiting] = useState(true);
  const [armError, setArmError] = useState('');
  const [pollError, setPollError] = useState('');
  const [session, setSession] = useState(null);
  const [waitedLong, setWaitedLong] = useState(false);
  const engines = session?.engines?.length ? session.engines : taskPreviewEngines(task);

  useEffect(() => {
    if (!task?.id) return undefined;
    let stopped = false;
    const view = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setImage(null);
    setStats(null);
    setAgeMs(null);
    setWaiting(true);
    setArmError('');
    setPollError('');
    setSession(null);
    setWaitedLong(false);

    const arm = async () => {
      if (stopped) return;
      const issuedAt = Date.now();
      try {
        const data = await axios.post(`/api/tasks/${task.id}/preview`, {
          enabled: true,
          view,
          issued_at: issuedAt,
        });
        if (!stopped) {
          setSession(data || null);
          setArmError('');
        }
      } catch (error) {
        if (!stopped) setArmError(extractApiError(error, '打不开检测预览'));
      }
    };

    const poll = async () => {
      try {
        const data = await axios.get(`/api/tasks/${task.id}/preview`);
        if (stopped) return;
        setWaiting(Boolean(data?.waiting) || !data?.image);
        setStats(data?.stats || null);
        setAgeMs(Number.isFinite(data?.age_ms) ? data.age_ms : null);
        setImage(data?.image || null);
        setPollError('');
      } catch (error) {
        if (!stopped) setPollError(extractApiError(error, '刷新检测画面失败'));
      }
    };

    arm();
    poll();
    const keepTimer = setInterval(arm, 3000);
    const pollTimer = setInterval(poll, 400);
    const waitTimer = setTimeout(() => setWaitedLong(true), 8000);
    return () => {
      stopped = true;
      clearInterval(keepTimer);
      clearInterval(pollTimer);
      clearTimeout(waitTimer);
      axios.post(`/api/tasks/${task.id}/preview`, {
        enabled: false,
        view,
        issued_at: Date.now(),
      }).catch(() => {});
    };
  }, [task?.id]);

  if (!task) return null;

  const inferMs = stats?.infer_ms;
  const stale = !waiting && ageMs != null && ageMs > 4000;
  const taskRunning = task.status === 'running';

  return (
    <Dialog open onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>检测预览 — {task.name}</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 1.5 }}>
          画面是边缘正在推理的那一帧。目标检测画框并标出类别，姿态检测画骨骼点。
          摄像头遮挡单独显示外圈发平的比例，画面上的「阈值 0.50」是目标检测的置信度。
          骨骼点坐标和本帧场景结论在画面下面，用来区分是点没检全，还是几何判断没过。
          这里成立不等于已经告警，告警还要等停留时间，并且不在冷却时间内。
          识别眼镜、识别手表只要出现所选类别就告警。AI眼镜默认要手腕离开后再贴耳 3 次，一张不动的图只会记 1 次。智能手表要两只手腕都靠近手表框。
        </Alert>
        {armError && <Alert severity="error" sx={{ mb: 1.5 }}>{armError}</Alert>}
        {!armError && session && session.node_status && session.node_status !== 'online' && (
          <Alert severity="warning" sx={{ mb: 1.5 }}>算力节点不在线，预览指令到不了边缘。</Alert>
        )}
        {!armError && !taskRunning && (
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            任务当前是「{taskStatusLabel(task.status)}」。先启动任务，节点开始推理后这里才会有画面。
          </Alert>
        )}
        <Box
          sx={{
            bgcolor: '#000',
            minHeight: 280,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mb: 2,
          }}
        >
          {image ? (
            <img
              src={`data:image/jpeg;base64,${image}`}
              alt="实时检测画面"
              style={{ width: '100%', maxHeight: '68vh', objectFit: 'contain', display: 'block' }}
            />
          ) : (
            <Box sx={{ px: 2, py: 6, textAlign: 'center' }}>
              <Typography color="grey.400">正在等待边缘回传检测画面…</Typography>
              {waitedLong && (
                <Typography color="grey.500" variant="body2" sx={{ mt: 1 }}>
                  确认任务已启动，并且算力节点在线。节点离线或任务没在推理时，这里不会有画面。
                </Typography>
              )}
            </Box>
          )}
        </Box>
        {pollError && <Alert severity="warning" sx={{ mb: 1.5 }}>{pollError}</Alert>}
        {stale && (
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            已经 {(ageMs / 1000).toFixed(1)} 秒没有新画面。任务可能停了，或节点暂时没推上来。
          </Alert>
        )}
        {image && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {engines.includes('object_detection') && (
              <CountBlock
                title="目标检测"
                noun="目标"
                data={stats?.object}
                emptyText="这一帧没有超过阈值的目标"
                hint="只包含这个任务选过的类别"
              />
            )}
            {engines.includes('pose_behavior') && (
              <CountBlock
                title="姿态检测"
                noun="人体"
                data={stats?.pose}
                emptyText="这一帧没有超过阈值的人体"
              />
            )}
            {stats?.occlusion && (
              <Box sx={{ flex: 1, minWidth: 220 }}>
                <Typography variant="subtitle1">摄像头遮挡</Typography>
                <Typography variant="h5" sx={{ my: 0.5 }}>
                  {formatPercent(stats.occlusion.ratio)}
                  <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                    外圈发平
                  </Typography>
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  门槛 {formatPercent(stats.occlusion.cover_ratio)}
                  {stats.occlusion.held != null
                    ? ` · 已持续 ${stats.occlusion.held}s / ${stats.occlusion.seconds}s`
                    : ''}
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  {stats.occlusion.hit
                    ? '这一帧外圈已经发平。持续满设定时长后告警。'
                    : '这一帧外圈还有纹理。'}
                </Typography>
              </Box>
            )}
          </Box>
        )}
        {image && <PoseDebug pose={stats?.pose} scenes={stats?.scenes} />}
        {(inferMs != null || ageMs != null) && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
            {inferMs != null ? `推理 ${inferMs} ms` : ''}
            {inferMs != null && ageMs != null ? ' · ' : ''}
            {ageMs != null ? `画面 ${(ageMs / 1000).toFixed(1)} 秒前` : ''}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>关闭</Button>
      </DialogActions>
    </Dialog>
  );
}

export default DetectionPreviewDialog;
