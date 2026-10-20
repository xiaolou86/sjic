import React, { useMemo, useState } from 'react';
import {
  Box, Button, Chip, FormControl, FormControlLabel, Grid, InputLabel, MenuItem, Paper, Select,
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

function labelsForScenes(labelmap, allowedIds) {
  const all = normalizeLabelmap(labelmap);
  const selected = (Array.isArray(allowedIds) ? allowedIds : [])
    .map((id) => Number(id))
    .filter((id) => Number.isInteger(id));
  if (!selected.length) return all;
  const allowed = new Set(selected);
  const filtered = all.filter((item) => allowed.has(item.id));
  return filtered.length ? filtered : selected.map((id) => ({ id, name: String(id) }));
}

function FusionScenesEditor({ algorithmParameters, onChange, catalogPresets, taskConfidence, labelmap, allowedLabelIds, highlightMissing = false }) {
  const [addPreset, setAddPreset] = useState('');
  const fusions = Array.isArray(algorithmParameters?.fusions) ? algorithmParameters.fusions : [];
  const labels = useMemo(
    () => labelsForScenes(labelmap, allowedLabelIds),
    [labelmap, allowedLabelIds],
  );
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
          请选择对应类别。智能手表默认点击 1 次即有作弊嫌疑。
        </Typography>
      </Grid>

      {fusions.length === 0 && (
        <Grid item xs={12}>
          <Typography variant="body2" color="text.secondary">尚未添加融合场景。</Typography>
        </Grid>
      )}

      {fusions.map((item, index) => {
        const isWatch = item.type === 'smart_watch';
        const classPlaceholder = isWatch ? '选择手表类别' : '选择眼镜类别';
        const classIdLabel = isWatch ? '手表类别 ID' : '眼镜类别 ID';
        const countLabel = isWatch ? '最少点击次数' : '最少触碰次数';
        const countDefault = isWatch ? 1 : 3;
        const countMin = isWatch ? 1 : 2;
        const distLabel = isWatch ? '点击距离阈值' : '耳旁距离阈值';
        const distKey = isWatch ? 'watch_dist_ratio' : 'ear_dist_ratio';
        const distDefault = isWatch ? 0.5 : 0.28;
        const distHelp = isWatch
          ? '相对肩宽。另一只手进入该范围算一次点击，只戴表不算'
          : '相对肩宽，越小越要贴近耳朵';
        const selectedClass = Array.isArray(item.class_ids) && item.class_ids.length && Number.isInteger(Number(item.class_ids[0]))
          ? Number(item.class_ids[0])
          : '';
        return (
        <Grid item xs={12} key={item.id || index}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
              <Chip size="small" label="检测+姿态" />
              <TextField
                size="small"
                label="场景名称"
                value={item.name || ''}
                InputProps={{ readOnly: true }}
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
                  <FormControl fullWidth size="small" error={highlightMissing && item.enabled !== false && selectedClass === ''}>
                    <InputLabel>{isWatch ? '手表类别' : '眼镜类别'}</InputLabel>
                    <Select
                      label={isWatch ? '手表类别' : '眼镜类别'}
                      value={selectedClass}
                      onChange={(e) => {
                        const id = e.target.value;
                        patch(index, { class_ids: id === '' ? [] : [Number(id)] });
                      }}
                    >
                      <MenuItem value="">{classPlaceholder}</MenuItem>
                      {labels.map((label) => (
                        <MenuItem key={label.id} value={label.id}>
                          {label.name}（{label.id}）
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                ) : (
                  <TextField
                    fullWidth
                    size="small"
                    label={classIdLabel}
                    value={selectedClass === '' ? '' : String(selectedClass)}
                    onChange={(e) => {
                      const raw = e.target.value.trim();
                      if (!raw) {
                        patch(index, { class_ids: [] });
                        return;
                      }
                      const id = parseInt(raw, 10);
                      patch(index, { class_ids: Number.isInteger(id) ? [id] : [] });
                    }}
                    error={highlightMissing && item.enabled !== false && selectedClass === ''}
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
                  helperText={isWatch ? '多次点击需落在这个窗口内；默认 1 次会立刻计数' : '多次触碰需落在这个窗口内'}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label={countLabel}
                  value={item.min_touches ?? countDefault}
                  onChange={(e) => patch(index, { min_touches: parseInt(e.target.value, 10) })}
                  inputProps={{ min: countMin, step: 1 }}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label={distLabel}
                  value={item[distKey] ?? distDefault}
                  onChange={(e) => patch(index, { [distKey]: parseFloat(e.target.value) })}
                  inputProps={{ min: 0.05, max: isWatch ? 1.5 : 1, step: 0.01 }}
                  helperText={distHelp}
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
        );
      })}

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
