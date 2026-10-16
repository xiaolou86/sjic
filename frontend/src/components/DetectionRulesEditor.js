import React, { useMemo, useState } from 'react';
import {
  Box, Button, Chip, FormControl, FormControlLabel, Grid, InputLabel, MenuItem, Paper, Select,
  Switch, TextField, Typography, IconButton
} from '@mui/material';
import { Add, Delete } from '@mui/icons-material';
import RegionSelectionTool from './RegionSelectionTool';

/** 按规则 type 决定编辑哪些字段（边缘仍按 type 跑 Presence/Linger/Absence/Crowd） */
const TYPE_FIELDS = {
  linger: ['linger_seconds'],
  absence: ['absent_seconds'],
  presence: [],
  crowd_count: ['min_count', 'seconds'],
  camera_occlusion: ['cover_ratio', 'seconds'],
};

function isCameraOcclusion(rule) {
  return rule?.type === 'camera_occlusion' || rule?.scene_preset_id === 'camera_occlusion';
}

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

function DetectionRulesEditor({ cameraId, algorithm, algorithmParameters, onChange, catalogPresets, taskConfidence, labelmap, highlightMissing = false, excludePresetIds = [] }) {
  const [addPreset, setAddPreset] = useState('');

  const scenePresets = useMemo(() => {
    const fromSchema = algorithm?.parameter_schema?.scene_presets;
    const list = Array.isArray(fromSchema) && fromSchema.length > 0
      ? fromSchema
      : (Array.isArray(catalogPresets) ? catalogPresets : []);
    const excluded = new Set(excludePresetIds || []);
    return list.filter((item) => !excluded.has(item?.id) && !excluded.has(item?.type));
  }, [algorithm, catalogPresets, excludePresetIds]);

  const rules = Array.isArray(algorithmParameters?.rules) ? algorithmParameters.rules : [];
  const labels = useMemo(
    () => labelsForScenes(labelmap, algorithm?.labels),
    [labelmap, algorithm],
  );

  const updateRules = (nextRules) => {
    onChange({
      ...algorithmParameters,
      rules: nextRules,
    });
  };

  const handleAddPreset = () => {
    const preset = scenePresets.find((p) => p.id === addPreset);
    if (!preset) return;
    const presetDefaults = preset.defaults || {};
    const next = {
      id: `rule_${Date.now()}`,
      type: preset.type,
      name: preset.name,
      scene_preset_id: preset.id,
      ...presetDefaults,
      class_ids: [],
      enabled: true,
      detection_region: null,
      schedule_start: presetDefaults.schedule_start || '',
      schedule_end: presetDefaults.schedule_end || '',
    };
    updateRules([...rules, next]);
    setAddPreset('');
  };

  const patchRule = (index, patch) => {
    updateRules(rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));
  };

  const removeRule = (index) => {
    updateRules(rules.filter((_, i) => i !== index));
  };

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <Typography variant="subtitle2" gutterBottom>检测场景</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          从预设添加场景。检测场景要选择类别；摄像头遮挡不用类别，添加后默认每天 08:00–18:00。场景时段、置信度优先于任务。
        </Typography>
      </Grid>

      {rules.length === 0 && (
        <Grid item xs={12}>
          <Typography variant="body2" color="text.secondary">尚未添加场景。</Typography>
        </Grid>
      )}

      {rules.map((rule, index) => {
        const fields = TYPE_FIELDS[rule.type] || [];
        const occlusion = isCameraOcclusion(rule);
        const hasRegion = Boolean(rule.detection_region?.points?.length);
        const selectedClass = Array.isArray(rule.class_ids) && rule.class_ids.length
          ? Number(rule.class_ids[0])
          : '';
        const classMissing = !occlusion && rule.enabled !== false && (selectedClass === '' || !Number.isInteger(selectedClass));
        return (
          <Grid item xs={12} key={rule.id || index}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
                <Chip size="small" label={rule.type} />
                <TextField
                  size="small"
                  label="场景名称"
                  value={rule.name || ''}
                  onChange={(e) => patchRule(index, { name: e.target.value })}
                  sx={{ minWidth: 160 }}
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={rule.enabled !== false}
                      onChange={(e) => patchRule(index, { enabled: e.target.checked })}
                    />
                  }
                  label="启用"
                />
                <Box sx={{ flex: 1 }} />
                <IconButton color="error" onClick={() => removeRule(index)} size="small">
                  <Delete />
                </IconButton>
              </Box>

              <Grid container spacing={2}>
                {!occlusion && (
                <Grid item xs={12} md={4}>
                  {labels.length > 0 ? (
                    <FormControl fullWidth size="small" error={highlightMissing && classMissing}>
                      <InputLabel>类别</InputLabel>
                      <Select
                        label="类别"
                        value={selectedClass}
                        onChange={(e) => {
                          const id = e.target.value;
                          patchRule(index, { class_ids: id === '' ? [] : [Number(id)] });
                        }}
                      >
                        <MenuItem value="">选择类别</MenuItem>
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
                      label="类别 ID"
                      value={selectedClass === '' ? '' : String(selectedClass)}
                      onChange={(e) => {
                        const raw = e.target.value.trim();
                        if (!raw) {
                          patchRule(index, { class_ids: [] });
                          return;
                        }
                        const id = parseInt(raw, 10);
                        patchRule(index, { class_ids: Number.isInteger(id) ? [id] : [] });
                      }}
                      error={highlightMissing && classMissing}
                    />
                  )}
                </Grid>
                )}
                {fields.includes('cover_ratio') && (
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      size="small"
                      type="number"
                      label="外圈遮挡比例"
                      value={rule.cover_ratio ?? 0.25}
                      onChange={(e) => patchRule(index, { cover_ratio: parseFloat(e.target.value) })}
                      inputProps={{ min: 0.05, max: 1, step: 0.05 }}
                      helperText="最外一圈发平的占比"
                    />
                  </Grid>
                )}
                {fields.includes('linger_seconds') && (
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      size="small"
                      type="number"
                      label="驻留时长(秒)"
                      value={rule.linger_seconds ?? 5}
                      onChange={(e) => patchRule(index, { linger_seconds: parseFloat(e.target.value) })}
                      inputProps={{ min: 1, step: 1 }}
                    />
                  </Grid>
                )}
                {fields.includes('absent_seconds') && (
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      size="small"
                      type="number"
                      label="缺席时长(秒)"
                      value={rule.absent_seconds ?? 600}
                      onChange={(e) => patchRule(index, { absent_seconds: parseFloat(e.target.value) })}
                      inputProps={{ min: 1, step: 1 }}
                    />
                  </Grid>
                )}
                {fields.includes('min_count') && (
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      size="small"
                      type="number"
                      label="人数阈值"
                      value={rule.min_count ?? 5}
                      onChange={(e) => patchRule(index, { min_count: parseInt(e.target.value, 10) })}
                      inputProps={{ min: 1, step: 1 }}
                    />
                  </Grid>
                )}
                {fields.includes('seconds') && (
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      size="small"
                      type="number"
                      label="持续时长(秒)"
                      value={rule.seconds ?? 10}
                      onChange={(e) => patchRule(index, { seconds: parseFloat(e.target.value) })}
                      inputProps={{ min: 1, step: 1 }}
                    />
                  </Grid>
                )}
                {!occlusion && (
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="场景置信度"
                    value={rule.confidence ?? ''}
                    placeholder={taskConfidence != null ? String(taskConfidence) : '跟随任务'}
                    onChange={(e) => {
                      const v = e.target.value;
                      patchRule(index, { confidence: v === '' ? null : parseFloat(v) });
                    }}
                    inputProps={{ step: 0.05, min: 0, max: 1 }}
                    helperText="留空用任务置信度"
                  />
                </Grid>
                )}
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    size="small"
                    label="告警类型"
                    value={rule.alert_type || ''}
                    onChange={(e) => patchRule(index, { alert_type: e.target.value })}
                  />
                </Grid>
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    size="small"
                    type="time"
                    label="场景开始"
                    value={rule.schedule_start || ''}
                    onChange={(e) => patchRule(index, { schedule_start: e.target.value })}
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ step: 60 }}
                    helperText="可选，优先于任务时段"
                  />
                </Grid>
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    size="small"
                    type="time"
                    label="场景结束"
                    value={rule.schedule_end || ''}
                    onChange={(e) => patchRule(index, { schedule_end: e.target.value })}
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ step: 60 }}
                  />
                </Grid>
                {!occlusion && (
                <Grid item xs={12}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                    <RegionSelectionTool
                      cameraId={cameraId}
                      buttonLabel={hasRegion ? '重新选择区域' : '选择检测区域'}
                      existingRegion={{
                        detection_region: rule.detection_region,
                        calibration: rule.calibration,
                      }}
                      onSelect={(regionData) => patchRule(index, {
                        detection_region: regionData.detection_region,
                        calibration: regionData.calibration,
                      })}
                    />
                    <Typography variant="body2" color={hasRegion ? 'success.main' : 'text.secondary'}>
                      {hasRegion ? `已标注 ${rule.detection_region.points.length} 个顶点` : '未标注区域（整帧有效）'}
                    </Typography>
                  </Box>
                </Grid>
                )}
              </Grid>
            </Paper>
          </Grid>
        );
      })}

      <Grid item xs={12}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <Select
            size="small"
            displayEmpty
            value={addPreset}
            onChange={(e) => setAddPreset(e.target.value)}
            sx={{ minWidth: 260 }}
            disabled={scenePresets.length === 0}
          >
            <MenuItem value="">选择场景预设…</MenuItem>
            {scenePresets.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.name}
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
    </Grid>
  );
}

export default DetectionRulesEditor;
