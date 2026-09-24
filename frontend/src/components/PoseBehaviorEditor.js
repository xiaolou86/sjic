import React, { useMemo, useState } from 'react';
import {
  Box, Button, FormControlLabel, Grid, MenuItem, Paper, Select,
  Switch, TextField, Typography, IconButton, Chip
} from '@mui/material';
import { Add, Delete } from '@mui/icons-material';

/**
 * 姿态行为：从场景预设添加多条行为，同一 pose task 一次推理。
 */
function PoseBehaviorEditor({ algorithm, algorithmParameters, onChange, catalogPresets, taskConfidence }) {
  const [addPreset, setAddPreset] = useState('');

  const behaviors = Array.isArray(algorithmParameters?.behaviors)
    ? algorithmParameters.behaviors
    : [];

  const scenePresets = useMemo(() => {
    const fromSchema = algorithm?.parameter_schema?.scene_presets;
    if (Array.isArray(fromSchema) && fromSchema.length > 0) return fromSchema;
    return Array.isArray(catalogPresets) ? catalogPresets : [];
  }, [algorithm, catalogPresets]);

  const patchBehavior = (index, patch) => {
    const next = behaviors.map((b, i) => (i === index ? { ...b, ...patch } : b));
    onChange({ ...algorithmParameters, behaviors: next });
  };

  const removeBehavior = (index) => {
    onChange({
      ...algorithmParameters,
      behaviors: behaviors.filter((_, i) => i !== index),
    });
  };

  const handleAddPreset = () => {
    const preset = scenePresets.find((p) => p.id === addPreset);
    if (!preset) return;
    const next = {
      id: `beh_${Date.now()}`,
      type: preset.type,
      name: preset.name,
      scene_preset_id: preset.id,
      ...(preset.defaults || {}),
      enabled: true,
      schedule_start: '',
      schedule_end: '',
    };
    onChange({
      ...algorithmParameters,
      behaviors: [...behaviors, next],
    });
    setAddPreset('');
  };

  const durationLabel = (b) => {
    if (b.type === 'smart_glasses') return '统计窗口(秒)';
    if (b.type === 'invigilator_absent') return '判定间隔(秒)';
    return '持续时长(秒)';
  };

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="subtitle2" gutterBottom>姿态行为 / 场景</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          同一任务只跑一次姿态推理；可叠加多个行为。场景时段、置信度优先于任务。人员倒地请用目标检测场景。
          张望/不看屏幕等几何判断取决于视频源的安装位置（前上方/后上方/侧上方/正上方），请在「视频源」页配置。
        </Typography>
      </Grid>

      {behaviors.length === 0 && (
        <Grid item xs={12}>
          <Typography variant="body2" color="text.secondary">
            {scenePresets.length === 0
              ? '该算法没有场景预设（请确认使用的是从模板派生并已补齐 schema 的上架算法）。'
              : '尚未添加行为，请从下方场景预设添加。'}
          </Typography>
        </Grid>
      )}

      {behaviors.map((b, index) => (
        <Grid item xs={12} key={b.id || index}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
              <Chip size="small" label={b.type} />
              <TextField
                size="small"
                label="名称"
                value={b.name || ''}
                onChange={(e) => patchBehavior(index, { name: e.target.value })}
                sx={{ minWidth: 140 }}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={b.enabled !== false}
                    onChange={(e) => patchBehavior(index, { enabled: e.target.checked })}
                  />
                }
                label="启用"
              />
              <Box sx={{ flex: 1 }} />
              <IconButton color="error" onClick={() => removeBehavior(index)} size="small">
                <Delete />
              </IconButton>
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label={durationLabel(b)}
                  value={b.seconds ?? (b.type === 'invigilator_absent' ? 120 : 3)}
                  onChange={(e) => patchBehavior(index, { seconds: parseFloat(e.target.value) })}
                  inputProps={{ min: 0.5, step: b.type === 'invigilator_absent' ? 10 : 0.5 }}
                />
              </Grid>
              {(b.type === 'look_aside' || b.type === 'gaze_away') && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="偏航阈值(°)"
                    value={b.yaw_degrees ?? 45}
                    onChange={(e) => patchBehavior(index, { yaw_degrees: parseFloat(e.target.value) })}
                    inputProps={{ min: 1, step: 1 }}
                  />
                </Grid>
              )}
              {(b.type === 'head_down' || b.type === 'gaze_away') && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="低头俯仰(°)"
                    value={b.pitch_degrees ?? 30}
                    onChange={(e) => patchBehavior(index, { pitch_degrees: parseFloat(e.target.value) })}
                    inputProps={{ min: 1, step: 1 }}
                  />
                </Grid>
              )}
              {b.type === 'smart_glasses' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="最少触碰次数"
                    value={b.min_touches ?? 3}
                    onChange={(e) => patchBehavior(index, { min_touches: parseInt(e.target.value, 10) })}
                    inputProps={{ min: 2, step: 1 }}
                  />
                </Grid>
              )}
              {b.type === 'smart_glasses' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="耳旁距离阈值"
                    value={b.ear_dist_ratio ?? 0.28}
                    onChange={(e) => patchBehavior(index, { ear_dist_ratio: parseFloat(e.target.value) })}
                    inputProps={{ min: 0.05, max: 1, step: 0.01 }}
                    helperText="相对肩宽，越小越要贴近耳朵"
                  />
                </Grid>
              )}
              {b.type === 'invigilator_absent' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="最少站立人数"
                    value={b.min_standing ?? 2}
                    onChange={(e) => patchBehavior(index, { min_standing: parseInt(e.target.value, 10) })}
                    inputProps={{ min: 1, step: 1 }}
                  />
                </Grid>
              )}
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="场景置信度"
                  value={b.confidence ?? ''}
                  placeholder={taskConfidence != null ? String(taskConfidence) : '跟随任务'}
                  onChange={(e) => {
                    const v = e.target.value;
                    patchBehavior(index, { confidence: v === '' ? null : parseFloat(v) });
                  }}
                  inputProps={{ step: 0.05, min: 0, max: 1 }}
                  helperText="留空用任务置信度"
                />
              </Grid>
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  size="small"
                  label="告警类型"
                  value={b.alert_type || ''}
                  onChange={(e) => patchBehavior(index, { alert_type: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  size="small"
                  type="time"
                  label="场景开始"
                  value={b.schedule_start || ''}
                  onChange={(e) => patchBehavior(index, { schedule_start: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                  inputProps={{ step: 60 }}
                  helperText="可选，优先于任务时段"
                />
              </Grid>
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  size="small"
                  type="time"
                  label="场景结束"
                  value={b.schedule_end || ''}
                  onChange={(e) => patchBehavior(index, { schedule_end: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                  inputProps={{ step: 60 }}
                />
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      ))}

      {scenePresets.length > 0 && (
        <Grid item xs={12}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            <Select
              size="small"
              displayEmpty
              value={addPreset}
              onChange={(e) => setAddPreset(e.target.value)}
              sx={{ minWidth: 260 }}
            >
              <MenuItem value="">从场景预设添加…</MenuItem>
              {scenePresets.map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.name}（{p.type}）
                </MenuItem>
              ))}
            </Select>
            <Button
              variant="contained"
              startIcon={<Add />}
              disabled={!addPreset}
              onClick={handleAddPreset}
            >
              添加场景
            </Button>
          </Box>
        </Grid>
      )}
    </Grid>
  );
}

export default PoseBehaviorEditor;
