import React, { useMemo, useState } from 'react';
import {
  Box, Button, FormControlLabel, Grid, MenuItem, Paper, Select,
  Switch, TextField, Typography, IconButton
} from '@mui/material';
import { Add, Delete } from '@mui/icons-material';
import RegionSelectionTool from './RegionSelectionTool';

/**
 * 姿态行为：从场景预设添加多条行为，同一 pose task 一次推理。
 * 滞留 / 聚集只统计姿态检出的人数，不判断具体姿态。
 */

function PoseBehaviorEditor({ algorithm, algorithmParameters, onChange, catalogPresets, taskConfidence, excludePresetIds, cameraId }) {
  const [addPreset, setAddPreset] = useState('');

  const behaviors = Array.isArray(algorithmParameters?.behaviors)
    ? algorithmParameters.behaviors
    : [];

  const scenePresets = useMemo(() => {
    const fromSchema = algorithm?.parameter_schema?.scene_presets;
    const catalog = Array.isArray(catalogPresets) ? catalogPresets : [];
    const schema = Array.isArray(fromSchema) ? fromSchema : [];
    // 目录是当前场景。算法上留下的旧预设不再出现在添加列表里。
    const source = catalog.length > 0 ? catalog : schema;
    const excluded = new Set(excludePresetIds || []);
    return source.filter((preset) => (
      preset
      && !excluded.has(preset.id)
      && !excluded.has(preset.type)
    ));
  }, [algorithm, catalogPresets, excludePresetIds]);

  const visibleBehaviors = behaviors
    .map((b, index) => ({ b, index }));

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
      detection_region: null,
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
          可添加多个场景。每个场景可单独画检测区域，不画则使用整个画面。场景时段、置信度优先于任务。人员倒地请用目标检测。智能手表请在混合任务的融合场景里添加。手指屏幕只报站立，长时间不看屏幕只报非站立，站立判断与考台旁站人相同。考台旁站人要有骨骼点，人框高宽比达标，且至少一条腿的膝角和上下身夹角都伸直，同一人几乎不动达到持续时长记为辅助作弊。
        </Typography>
      </Grid>

      {visibleBehaviors.length === 0 && (
        <Grid item xs={12}>
          <Typography variant="body2" color="text.secondary">
            {scenePresets.length === 0
              ? '该算法没有场景预设（请确认使用的是从模板派生并已补齐 schema 的上架算法）。'
              : '尚未添加行为，请从下方场景预设添加。'}
          </Typography>
        </Grid>
      )}

      {visibleBehaviors.map(({ b, index }) => (
        <Grid item xs={12} key={b.id || index}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
              <TextField
                size="small"
                label="场景名称"
                value={b.name || ''}
                InputProps={{ readOnly: true }}
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
              {b.type !== 'linger' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label={durationLabel(b)}
                    value={b.seconds ?? (b.type === 'invigilator_absent' ? 120 : (b.type === 'crowd_count' || b.type === 'desk_stand') ? 10 : 3)}
                    onChange={(e) => patchBehavior(index, { seconds: parseFloat(e.target.value) })}
                    inputProps={{ min: 0.5, step: (b.type === 'invigilator_absent' || b.type === 'crowd_count' || b.type === 'desk_stand') ? 1 : 0.5 }}
                  />
                </Grid>
              )}
              {b.type === 'linger' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="滞留时长(秒)"
                    value={b.linger_seconds ?? 300}
                    onChange={(e) => patchBehavior(index, { linger_seconds: parseFloat(e.target.value) })}
                    inputProps={{ min: 1, step: 1 }}
                  />
                </Grid>
              )}
              {b.type === 'crowd_count' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="人数阈值"
                    value={b.min_count ?? 5}
                    onChange={(e) => patchBehavior(index, { min_count: parseInt(e.target.value, 10) })}
                    inputProps={{ min: 1, step: 1 }}
                  />
                </Grid>
              )}
              {b.type === 'gaze_away' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="偏航阈值(°)"
                    value={b.yaw_degrees ?? 25}
                    onChange={(e) => patchBehavior(index, { yaw_degrees: parseFloat(e.target.value) })}
                    inputProps={{ min: 1, step: 1 }}
                  />
                </Grid>
              )}
              {b.type === 'head_down' && (
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
              {b.type === 'desk_stand' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="站立长高比"
                    value={b.min_height_width ?? 1.6}
                    onChange={(e) => patchBehavior(index, { min_height_width: parseFloat(e.target.value) })}
                    inputProps={{ min: 0.5, step: 0.05 }}
                    helperText="框高/框宽。先过这道线，再看腿是否伸直"
                  />
                </Grid>
              )}
              {b.type === 'desk_stand' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="膝角(°)"
                    value={b.min_knee_degrees ?? 150}
                    onChange={(e) => patchBehavior(index, { min_knee_degrees: parseFloat(e.target.value) })}
                    inputProps={{ min: 90, max: 179, step: 1 }}
                    helperText="大腿与小腿的夹角，至少一条腿达到才算站着"
                  />
                </Grid>
              )}
              {b.type === 'desk_stand' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="上下身夹角(°)"
                    value={b.min_hip_degrees ?? 140}
                    onChange={(e) => patchBehavior(index, { min_hip_degrees: parseFloat(e.target.value) })}
                    inputProps={{ min: 90, max: 179, step: 1 }}
                    helperText="肩-髋与髋-膝的夹角。坐着伸腿时膝可以是直的，但这里会弯"
                  />
                </Grid>
              )}
              {b.type === 'desk_stand' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="静止范围"
                    value={b.max_move_ratio ?? 1}
                    onChange={(e) => patchBehavior(index, { max_move_ratio: parseFloat(e.target.value) })}
                    inputProps={{ min: 0.1, step: 0.1 }}
                    helperText="相对框宽，人走远超过这个倍数就重新计时"
                  />
                </Grid>
              )}
              {b.type === 'finger_point' && (
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="静止范围"
                    value={b.max_move_ratio ?? 1}
                    onChange={(e) => patchBehavior(index, { max_move_ratio: parseFloat(e.target.value) })}
                    inputProps={{ min: 0.1, step: 0.1 }}
                    helperText="相对肩宽。走远超过这个倍数就重新计时，路过摆臂不算指屏"
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
              <Grid item xs={12}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <RegionSelectionTool
                    cameraId={cameraId}
                    buttonLabel={b.detection_region?.points?.length ? '重新选择区域' : '选择检测区域'}
                    existingRegion={{
                      detection_region: b.detection_region,
                      calibration: b.calibration,
                    }}
                    onSelect={(regionData) => patchBehavior(index, {
                      detection_region: regionData.detection_region,
                      calibration: regionData.calibration,
                    })}
                  />
                  <Typography variant="body2" color={b.detection_region?.points?.length ? 'success.main' : 'text.secondary'}>
                    {b.detection_region?.points?.length
                      ? `本场景已标注 ${b.detection_region.points.length} 个顶点`
                      : '本场景未标注区域（整帧有效）'}
                  </Typography>
                </Box>
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
