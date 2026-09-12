import React, { useMemo, useState } from 'react';
import {
  Box, Button, Chip, FormControlLabel, Grid, MenuItem, Paper, Select,
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
};

function DetectionRulesEditor({ cameraId, algorithm, algorithmParameters, onChange }) {
  const [addPreset, setAddPreset] = useState('');

  const scenePresets = useMemo(() => {
    const fromSchema = algorithm?.parameter_schema?.scene_presets;
    return Array.isArray(fromSchema) ? fromSchema : [];
  }, [algorithm]);

  const rules = Array.isArray(algorithmParameters?.rules) ? algorithmParameters.rules : [];

  const updateRules = (nextRules) => {
    onChange({
      ...algorithmParameters,
      rules: nextRules,
    });
  };

  const handleAddPreset = () => {
    const preset = scenePresets.find((p) => p.id === addPreset);
    if (!preset) return;
    const next = {
      id: `rule_${Date.now()}`,
      type: preset.type,
      name: preset.name,
      scene_preset_id: preset.id,
      ...(preset.defaults || {}),
      enabled: true,
      detection_region: null,
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
          从预设添加场景（如人员缺席、识别手机）。同一任务只推理一次，多场景共用检测结果。
        </Typography>
      </Grid>

      {rules.length === 0 && (
        <Grid item xs={12}>
          <Typography variant="body2" color="text.secondary">尚未添加场景。</Typography>
        </Grid>
      )}

      {rules.map((rule, index) => {
        const fields = TYPE_FIELDS[rule.type] || [];
        const hasRegion = Boolean(rule.detection_region?.points?.length);
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
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    size="small"
                    label="告警类型"
                    value={rule.alert_type || ''}
                    onChange={(e) => patchRule(index, { alert_type: e.target.value })}
                  />
                </Grid>
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
