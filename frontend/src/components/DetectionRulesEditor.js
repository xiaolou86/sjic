import React, { useMemo, useState } from 'react';
import {
  Box, Button, Chip, FormControlLabel, Grid, MenuItem, Paper, Select,
  Switch, TextField, Typography, IconButton
} from '@mui/material';
import { Add, Delete } from '@mui/icons-material';
import RegionSelectionTool from './RegionSelectionTool';

const FALLBACK_RULE_TYPES = [
  {
    type: 'linger',
    name: '区域内驻留',
    defaults: { linger_seconds: 5, alert_type: 'exam_desk_linger', class_ids: [0], enabled: true },
  },
  {
    type: 'absence',
    name: '区域内缺席',
    defaults: { absent_seconds: 600, alert_type: 'invigilator_absent', class_ids: [0], enabled: true },
  },
  {
    type: 'presence',
    name: '区域内出现',
    defaults: { alert_type: 'object_detection', class_ids: [0], enabled: true },
  },
];

function DetectionRulesEditor({ cameraId, algorithm, algorithmParameters, onChange }) {
  const [addType, setAddType] = useState('');

  const ruleTypes = useMemo(() => {
    const fromSchema = algorithm?.parameter_schema?.rule_types;
    return Array.isArray(fromSchema) && fromSchema.length > 0 ? fromSchema : FALLBACK_RULE_TYPES;
  }, [algorithm]);

  const rules = Array.isArray(algorithmParameters?.rules) ? algorithmParameters.rules : [];

  const typeMeta = (type) => ruleTypes.find((t) => t.type === type);

  const updateRules = (nextRules) => {
    onChange({
      ...algorithmParameters,
      rules: nextRules,
    });
  };

  const handleAdd = () => {
    const meta = typeMeta(addType);
    if (!meta) return;
    const next = {
      id: `rule_${Date.now()}`,
      type: meta.type,
      name: meta.name,
      ...(meta.defaults || {}),
      enabled: true,
      detection_region: null,
    };
    updateRules([...rules, next]);
    setAddType('');
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
        <Typography variant="subtitle2" gutterBottom>检测规则</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          同一任务只跑一次推理；可叠加多条规则（驻留 / 缺席 / 出现）。每条规则各自画 ROI。
        </Typography>
      </Grid>

      {rules.map((rule, index) => {
        const meta = typeMeta(rule.type);
        const hasRegion = Boolean(rule.detection_region?.points?.length);
        return (
          <Grid item xs={12} key={rule.id || index}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
                <Chip size="small" label={meta?.name || rule.type} />
                <TextField
                  size="small"
                  label="规则名称"
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
                {rule.type === 'linger' && (
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
                {rule.type === 'absence' && (
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      size="small"
                      type="number"
                      label="缺席时长(秒)"
                      value={rule.absent_seconds ?? 600}
                      onChange={(e) => patchRule(index, { absent_seconds: parseFloat(e.target.value) })}
                      inputProps={{ min: 1, step: 1 }}
                      helperText="默认 600 秒（10 分钟）"
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
            value={addType}
            onChange={(e) => setAddType(e.target.value)}
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="">选择规则类型</MenuItem>
            {ruleTypes.map((t) => (
              <MenuItem key={t.type} value={t.type}>{t.name}</MenuItem>
            ))}
          </Select>
          <Button
            variant="outlined"
            startIcon={<Add />}
            disabled={!addType}
            onClick={handleAdd}
          >
            添加规则
          </Button>
        </Box>
      </Grid>
    </Grid>
  );
}

export default DetectionRulesEditor;
