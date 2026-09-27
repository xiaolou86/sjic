import React, { useMemo, useState } from 'react';
import {
  Box, Button, Chip, FormControlLabel, Grid, MenuItem, Paper, Select,
  Switch, TextField, Typography, IconButton
} from '@mui/material';
import { Add, Delete } from '@mui/icons-material';

function normalizeLabelmap(raw) {
  if (Array.isArray(raw)) {
    return raw.filter((item) => item && Number.isInteger(item.id));
  }
  if (raw && typeof raw === 'object') {
    return Object.entries(raw)
      .map(([id, name]) => ({ id: Number(id), name: String(name) }))
      .filter((item) => Number.isInteger(item.id));
  }
  return [];
}

function FusionScenesEditor({ algorithmParameters, onChange, catalogPresets, taskConfidence, labelmap }) {
  const [addPreset, setAddPreset] = useState('');
  const fusions = Array.isArray(algorithmParameters?.fusions) ? algorithmParameters.fusions : [];
  const labels = useMemo(() => normalizeLabelmap(labelmap), [labelmap]);
  const scenePresets = Array.isArray(catalogPresets) ? catalogPresets : [];

  const update = (next) => {
    onChange({ ...algorithmParameters, fusions: next });
  };

  const patch = (index, patchFields) => {
    update(fusions.map((item, i) => (i === index ? { ...item, ...patchFields } : item)));
  };

  const handleAddPreset = () => {
    const preset = scenePresets.find((item) => item.id === addPreset);
    if (!preset) return;
    update([
      ...fusions,
      {
        id: `fusion_${Date.now()}`,
        type: preset.type,
        name: preset.name,
        scene_preset_id: preset.id,
        ...(preset.defaults || {}),
        enabled: true,
        schedule_start: '',
        schedule_end: '',
      },
    ]);
    setAddPreset('');
  };

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="subtitle2" gutterBottom>融合场景</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          智能眼镜会在同一帧上先做目标检测、再做姿态。只有眼镜框落在头部、且手腕靠近耳朵，才计为一次触碰。
        </Typography>
      </Grid>

      {fusions.length === 0 && (
        <Grid item xs={12}>
          <Typography variant="body2" color="text.secondary">尚未添加融合场景。</Typography>
        </Grid>
      )}

      {fusions.map((item, index) => (
        <Grid item xs={12} key={item.id || index}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
              <Chip size="small" label="检测+姿态" />
              <TextField
                size="small"
                label="名称"
                value={item.name || ''}
                onChange={(e) => patch(index, { name: e.target.value })}
                sx={{ minWidth: 180 }}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={item.enabled !== false}
                    onChange={(e) => patch(index, { enabled: e.target.checked })}
                  />
                }
                label="启用"
              />
              <Box sx={{ flex: 1 }} />
              <IconButton color="error" size="small" onClick={() => update(fusions.filter((_, i) => i !== index))}>
                <Delete />
              </IconButton>
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                {labels.length > 0 ? (
                  <Select
                    fullWidth
                    size="small"
                    multiple
                    displayEmpty
                    value={Array.isArray(item.class_ids) ? item.class_ids : []}
                    onChange={(e) => patch(index, { class_ids: e.target.value.map((id) => Number(id)) })}
                    renderValue={(selected) => {
                      if (!selected.length) return '选择眼镜类别';
                      return selected.map((id) => labels.find((label) => label.id === id)?.name || id).join('、');
                    }}
                  >
                    {labels.map((label) => (
                      <MenuItem key={label.id} value={label.id}>
                        {label.name}（{label.id}）
                      </MenuItem>
                    ))}
                  </Select>
                ) : (
                  <TextField
                    fullWidth
                    size="small"
                    label="眼镜类别 ID"
                    value={Array.isArray(item.class_ids) ? item.class_ids.join(',') : ''}
                    onChange={(e) => {
                      const classIds = e.target.value
                        .split(',')
                        .map((part) => parseInt(part.trim(), 10))
                        .filter((id) => Number.isInteger(id));
                      patch(index, { class_ids: classIds });
                    }}
                    helperText="检测模型未配置 labelmap 时，填写类别 ID，多个用逗号分隔"
                  />
                )}
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="统计窗口(秒)"
                  value={item.seconds ?? 30}
                  onChange={(e) => patch(index, { seconds: parseFloat(e.target.value) })}
                  inputProps={{ min: 1, step: 1 }}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="最少触碰次数"
                  value={item.min_touches ?? 3}
                  onChange={(e) => patch(index, { min_touches: parseInt(e.target.value, 10) })}
                  inputProps={{ min: 2, step: 1 }}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="耳旁距离阈值"
                  value={item.ear_dist_ratio ?? 0.28}
                  onChange={(e) => patch(index, { ear_dist_ratio: parseFloat(e.target.value) })}
                  inputProps={{ min: 0.05, max: 1, step: 0.01 }}
                  helperText="相对肩宽，越小越要贴近耳朵"
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="场景置信度"
                  value={item.confidence ?? ''}
                  placeholder={taskConfidence != null ? String(taskConfidence) : '跟随任务'}
                  onChange={(e) => {
                    const value = e.target.value;
                    patch(index, { confidence: value === '' ? null : parseFloat(value) });
                  }}
                  inputProps={{ step: 0.05, min: 0, max: 1 }}
                  helperText="留空用任务置信度"
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="time"
                  label="场景开始"
                  value={item.schedule_start || ''}
                  onChange={(e) => patch(index, { schedule_start: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                  inputProps={{ step: 60 }}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="time"
                  label="场景结束"
                  value={item.schedule_end || ''}
                  onChange={(e) => patch(index, { schedule_end: e.target.value })}
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
              <MenuItem value="">从融合场景添加…</MenuItem>
              {scenePresets.map((preset) => (
                <MenuItem key={preset.id} value={preset.id}>{preset.name}</MenuItem>
              ))}
            </Select>
            <Button variant="contained" startIcon={<Add />} disabled={!addPreset} onClick={handleAddPreset}>
              添加场景
            </Button>
          </Box>
        </Grid>
      )}
    </Grid>
  );
}

export default FusionScenesEditor;
