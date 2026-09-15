import React, { useEffect, useState } from 'react';
import {
  Grid,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  IconButton,
  Autocomplete,
  Chip,
  Box,
  Tooltip,
  Alert,
  Tabs,
  Tab,
} from '@mui/material';
import { Edit, Delete, Publish, ContentCopy } from '@mui/icons-material';
import axios from '../utils/axios';

const FALLBACK_ENGINES = [
  { value: 'object_detection', label: '目标检测' },
  { value: 'pose_behavior', label: '姿态行为检测' },
  { value: 'camera_health', label: '画面健康检测' },
  { value: 'mouse_idle', label: '鼠标空闲检测' },
  { value: 'belt_broken', label: '皮带破损检测' },
  { value: 'belt_deviation_detection', label: '皮带跑偏检测' },
  { value: 'belt_broken_series', label: '皮带撕裂序列检测' },
  { value: 'belt_broken_high', label: '高精度皮带撕裂检测' },
];

function Algorithms() {
  const isSuperAdmin = localStorage.getItem('user_role') === 'vendor';

  const [algorithms, setAlgorithms] = useState([]);
  const [models, setModels] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formError, setFormError] = useState('');
  const [tab, setTab] = useState(0); // 0=上架算法 1=系统模板

  const [formData, setFormData] = useState({
    name: '',
    type: '',
    engine: '',
    category: '',
    description: '',
    model_id: '',
    labels: [],
    infer_fps: 5,
    is_system_template: false,
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [algs, cat] = await Promise.all([
        axios.get('/api/algorithms'),
        axios.get('/api/algorithms/catalog').catch(() => null),
      ]);
      setAlgorithms(algs || []);
      setCatalog(cat);

      if (isSuperAdmin) {
        const mods = await axios.get('/api/models');
        setModels(mods || []);
      } else {
        setModels([]);
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    }
  };

  const engines = catalog?.engines?.length
    ? catalog.engines.map((e) => ({ value: e.value, label: e.label || e.value, needs_model: e.needs_model }))
    : FALLBACK_ENGINES;

  const engineLabel = (algorithm) => {
    const value = algorithm.engine || algorithm.type;
    return engines.find((e) => e.value === value)?.label || value || '-';
  };
  const templates = algorithms.filter((a) => a.is_system_template);
  const instances = algorithms.filter((a) => !a.is_system_template);

  const resetForm = () => {
    setEditingId(null);
    setFormError('');
    setFormData({
      name: '',
      type: '',
      engine: '',
      category: '',
      description: '',
      model_id: '',
      labels: [],
      infer_fps: 5,
      is_system_template: false,
    });
  };

  const handleEdit = (alg) => {
    setEditingId(alg.id);
    setFormError('');
    setFormData({
      name: alg.name,
      type: alg.type,
      engine: alg.engine || alg.type,
      category: alg.category || '',
      description: alg.description || '',
      model_id: alg.model_id || '',
      labels: alg.labels || [],
      infer_fps: alg.infer_fps != null ? alg.infer_fps : 5,
      is_system_template: !!alg.is_system_template,
    });
    setOpenDialog(true);
  };

  const handleDerive = async (template) => {
    const name = window.prompt('上架算法名称', `${template.name}（上架）`);
    if (name === null) return;
    try {
      await axios.post(`/api/algorithms/${template.id}/derive`, { name: name.trim() || undefined });
      fetchData();
    } catch (error) {
      console.error('Error deriving algorithm:', error);
      window.alert(error?.response?.data?.error || '派生失败');
    }
  };

  const handleUpdate = async () => {
    setFormError('');
    try {
      const payload = formData.is_system_template
        ? {
            name: formData.name,
            description: formData.description,
            category: formData.category || null,
          }
        : {
            name: formData.name,
            description: formData.description,
            category: formData.category || null,
            model_id: formData.model_id || null,
            labels: formData.labels || [],
            infer_fps: Number(formData.infer_fps) > 0 ? Number(formData.infer_fps) : 5,
          };

      await axios.put(`/api/algorithms/${editingId}`, payload);
      setOpenDialog(false);
      fetchData();
    } catch (error) {
      console.error('Error saving algorithm:', error);
      setFormError(error?.response?.data?.error || '保存失败');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('确认删除该上架算法？')) return;
    try {
      await axios.delete(`/api/algorithms/${id}`);
      fetchData();
    } catch (error) {
      console.error('Error deleting algorithm:', error);
      window.alert(error?.response?.data?.error || '删除失败');
    }
  };

  const handlePublish = async (algorithm) => {
    try {
      await axios.post(`/api/algorithms/${algorithm.id}/publish`, {});
      fetchData();
    } catch (error) {
      console.error('Error publishing algorithm:', error);
      window.alert(error?.response?.data?.error || '发布失败');
    }
  };

  const selectedModel = models.find((m) => String(m.id) === String(formData.model_id));
  const needsModel = (() => {
    const meta = catalog?.engines?.find((e) => e.value === (formData.engine || formData.type));
    if (meta && typeof meta.needs_model === 'boolean') return meta.needs_model;
    return true;
  })();

  const renderTemplateTable = (rows) => (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>名称</TableCell>
            <TableCell>引擎</TableCell>
            <TableCell>分类</TableCell>
            <TableCell>派生</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={4}>
                <Typography variant="body2" color="text.secondary">
                  暂无系统模板（重启后端同步目录后出现）
                </Typography>
              </TableCell>
            </TableRow>
          )}
          {rows.map((algorithm) => {
            const presetCount = Array.isArray(algorithm.parameter_schema?.scene_presets)
              ? algorithm.parameter_schema.scene_presets.length
              : 0;
            return (
              <TableRow key={algorithm.id}>
                <TableCell>
                  {algorithm.name}
                  {presetCount > 0 && (
                    <Typography variant="caption" display="block" color="text.secondary">
                      {presetCount} 个场景预设
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Chip label={engineLabel(algorithm)} size="small" color="primary" variant="outlined" />
                </TableCell>
                <TableCell>{algorithm.category || '-'}</TableCell>
                <TableCell>
                  <Tooltip title="派生上架实例（拷贝场景预设，再绑模型发布）">
                    <IconButton onClick={() => handleDerive(algorithm)} color="primary">
                      <ContentCopy />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="查看/改描述">
                    <IconButton onClick={() => handleEdit(algorithm)}>
                      <Edit />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const renderInstanceTable = (rows) => (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>名称</TableCell>
            {isSuperAdmin && <TableCell>引擎</TableCell>}
            <TableCell>分类</TableCell>
            {isSuperAdmin && <TableCell>绑定模型</TableCell>}
            {isSuperAdmin && <TableCell>推理FPS</TableCell>}
            {isSuperAdmin && <TableCell>发布状态</TableCell>}
            {isSuperAdmin && <TableCell>操作</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={isSuperAdmin ? 7 : 2}>
                <Typography variant="body2" color="text.secondary">
                  {isSuperAdmin ? '暂无上架算法，请到「系统模板」页签派生' : '暂无可用算法'}
                </Typography>
              </TableCell>
            </TableRow>
          )}
          {rows.map((algorithm) => {
            const amodel = models.find((m) => String(m.id) === String(algorithm.model_id));
            const presetCount = Array.isArray(algorithm.parameter_schema?.scene_presets)
              ? algorithm.parameter_schema.scene_presets.length
              : 0;
            return (
              <TableRow key={algorithm.id}>
                <TableCell>
                  {algorithm.name}
                  {presetCount > 0 && (
                    <Typography variant="caption" display="block" color="text.secondary">
                      {presetCount} 个场景预设
                    </Typography>
                  )}
                </TableCell>
                {isSuperAdmin && (
                  <TableCell>
                    <Chip label={engineLabel(algorithm)} size="small" color="primary" variant="outlined" />
                  </TableCell>
                )}
                <TableCell>{algorithm.category || '-'}</TableCell>
                {isSuperAdmin && (
                  <TableCell>
                    {amodel ? amodel.name : (algorithm.needs_model === false ? '无需模型' : '未绑定')}
                  </TableCell>
                )}
                {isSuperAdmin && (
                  <TableCell>
                    {algorithm.infer_fps != null ? algorithm.infer_fps : 5}
                  </TableCell>
                )}
                {isSuperAdmin && (
                  <TableCell>
                    {algorithm.published ? (
                      <Chip size="small" color="success" label="已发布" />
                    ) : (
                      <Chip size="small" color="warning" label="未发布" />
                    )}
                  </TableCell>
                )}
                {isSuperAdmin && (
                  <TableCell>
                    <Tooltip title="编辑（绑模型 / 推理FPS）">
                      <IconButton onClick={() => handleEdit(algorithm)}>
                        <Edit />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={algorithm.published ? '已发布' : '发布后对客户与任务可见'}>
                      <span>
                        <IconButton
                          onClick={() => handlePublish(algorithm)}
                          color="primary"
                          disabled={algorithm.published}
                        >
                          <Publish />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="删除">
                      <IconButton onClick={() => handleDelete(algorithm.id)} color="error">
                        <Delete />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Box>
          <Typography variant="h5" gutterBottom sx={{ userSelect: 'none' }}>
            算法清单
            {isSuperAdmin && <Chip size="small" color="primary" label="服务商超管" sx={{ ml: 2 }} />}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            {isSuperAdmin
              ? '系统模板提供场景预设，不可直接发布。从模板「派生上架」后绑定一个模型再发布；同一引擎若要换模型规格，再派生一条实例即可（同一时刻一条实例只绑一个模型）。'
              : '以下为已发布可用算法，仅供查看；建任务时在「任务」页选择即可。'}
          </Typography>
        </Box>
      </Grid>

      {isSuperAdmin ? (
        <Grid item xs={12}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
          >
            <Tab label={`上架算法（${instances.length}）`} />
            <Tab label={`系统模板（${templates.length}）`} />
          </Tabs>

          {tab === 0 && (
            <Box>
              <Alert severity="info" sx={{ mb: 2 }}>
                上架算法流程：系统模板 → 派生 → 编辑绑定模型 → 发布。客户建任务时只能选已发布项。
              </Alert>
              {renderInstanceTable(instances)}
            </Box>
          )}

          {tab === 1 && (
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                由产品目录同步，含场景预设；不可绑模型、不可发布。点击「派生」生成可上架算法。
              </Typography>
              {renderTemplateTable(templates)}
            </Box>
          )}
        </Grid>
      ) : (
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>可用算法</Typography>
          {renderInstanceTable(instances)}
        </Grid>
      )}

      {isSuperAdmin && (
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {formData.is_system_template ? `系统模板：${formData.name}` : `编辑上架算法：${formData.name}`}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {formError && (
              <Grid item xs={12}>
                <Alert severity="error">{formError}</Alert>
              </Grid>
            )}
            {formData.is_system_template && (
              <Grid item xs={12}>
                <Alert severity="warning">
                  模板不能发布、不能绑模型。请关闭后点击「派生」创建上架实例。
                </Alert>
              </Grid>
            )}

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="算法名称"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </Grid>

            <Grid item xs={12}>
              <Select fullWidth value={formData.engine} displayEmpty disabled>
                <MenuItem value="" disabled>边缘引擎</MenuItem>
                {engines.map((t) => (
                  <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                ))}
              </Select>
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="描述"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </Grid>

            {!formData.is_system_template && needsModel && (
              <Grid item xs={12}>
                <Typography variant="subtitle2" color="error" sx={{ mt: 1, mb: 1 }}>
                  绑定模型（发布前必填；一条上架算法同时只绑一个模型）
                </Typography>
                <Select
                  fullWidth
                  value={formData.model_id}
                  displayEmpty
                  onChange={(e) => setFormData({ ...formData, model_id: e.target.value, labels: [] })}
                >
                  <MenuItem value="">未绑定</MenuItem>
                  {models.map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
                </Select>
              </Grid>
            )}

            {!formData.is_system_template && (
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  type="number"
                  label="推理帧率 inferFps"
                  value={formData.infer_fps}
                  onChange={(e) => setFormData({ ...formData, infer_fps: e.target.value })}
                  inputProps={{ min: 0.5, max: 30, step: 0.5 }}
                  helperText="边缘每秒推理次数；目标检测常用 2～5，跌倒类姿态建议 ≥5"
                />
              </Grid>
            )}

            {selectedModel && Array.isArray(selectedModel.labelmap) && selectedModel.labelmap.length > 0 && (
              <Grid item xs={12}>
                <Autocomplete
                  multiple
                  options={selectedModel.labelmap}
                  getOptionLabel={(option) => option.name || String(option.id)}
                  value={selectedModel.labelmap.filter((l) => (formData.labels || []).includes(l.id))}
                  onChange={(event, newValue) => {
                    setFormData({ ...formData, labels: newValue.map((v) => v.id) });
                  }}
                  renderInput={(params) => (
                    <TextField {...params} variant="outlined" label="默认关注的检测目标（可选）" />
                  )}
                  renderTags={(value, getTagProps) =>
                    value.map((option, index) => (
                      <Chip variant="outlined" label={option.name || String(option.id)} {...getTagProps({ index })} />
                    ))
                  }
                  isOptionEqualToValue={(option, value) => String(option.id) === String(value.id)}
                  disabled={formData.is_system_template}
                />
              </Grid>
            )}
          </Grid>
        </DialogContent>

        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>取消</Button>
          <Button onClick={handleUpdate} variant="contained">
            保存
          </Button>
        </DialogActions>
      </Dialog>
      )}
    </Grid>
  );
}

export default Algorithms;
