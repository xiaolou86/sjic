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
} from '@mui/material';
import { Edit, Delete, Add, Publish } from '@mui/icons-material';
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

  const [formData, setFormData] = useState({
    name: '',
    type: '',
    engine: '',
    category: '',
    description: '',
    model_id: '',
    labels: [],
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
  const products = catalog?.products || [];
  const categories = catalog?.categories || [];

  const resetForm = () => {
    setEditingId(null);
    setFormData({
      name: '',
      type: '',
      engine: '',
      category: '',
      description: '',
      model_id: '',
      labels: [],
    });
  };

  const applyProductPreset = (productType) => {
    const p = products.find((x) => x.type === productType);
    if (!p) {
      setFormData((prev) => ({ ...prev, type: productType, engine: productType }));
      return;
    }
    setFormData((prev) => ({
      ...prev,
      type: p.type,
      engine: p.engine,
      name: prev.name || p.name,
      description: prev.description || p.description,
      category: p.category,
    }));
  };

  const handleEdit = (alg) => {
    setEditingId(alg.id);
    setFormData({
      name: alg.name,
      type: alg.type,
      engine: alg.engine || alg.type,
      category: alg.category || '',
      description: alg.description || '',
      model_id: alg.model_id || '',
      labels: alg.labels || [],
    });
    setOpenDialog(true);
  };

  const handleUpdateOrCreate = async () => {
    try {
      const payload = {
        name: formData.name,
        type: formData.type,
        engine: formData.engine || formData.type,
        category: formData.category || null,
        description: formData.description,
        model_id: formData.model_id || null,
        labels: formData.labels || [],
      };

      if (editingId) {
        await axios.put(`/api/algorithms/${editingId}`, payload);
      } else {
        await axios.post('/api/algorithms', payload);
      }

      setOpenDialog(false);
      fetchData();
    } catch (error) {
      console.error('Error saving algorithm:', error);
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`/api/algorithms/${id}`);
      fetchData();
    } catch (error) {
      console.error('Error deleting algorithm:', error);
    }
  };

  const handlePublish = async (algorithm) => {
    try {
      await axios.post(`/api/algorithms/${algorithm.id}/publish`, {});
      fetchData();
    } catch (error) {
      console.error('Error publishing algorithm:', error);
    }
  };

  const selectedModel = models.find((m) => String(m.id) === String(formData.model_id));
  const needsModel = (() => {
    const meta = catalog?.engines?.find((e) => e.value === (formData.engine || formData.type));
    if (meta && typeof meta.needs_model === 'boolean') return meta.needs_model;
    return true;
  })();

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h5" gutterBottom sx={{ userSelect: 'none' }}>
              算法模板
              {isSuperAdmin && <Chip size="small" color="primary" label="服务商超管" sx={{ ml: 2 }} />}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              上架的是引擎级算法（目标检测 / 姿态检测等）。客户建任务时选一个算法，再在任务里加多条规则/场景。
            </Typography>
          </Box>
          {isSuperAdmin && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => {
                resetForm();
                setOpenDialog(true);
              }}
            >
              添加算法
            </Button>
          )}
        </Box>
      </Grid>

      <Grid item xs={12}>
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>算法名称</TableCell>
                <TableCell>标识 type</TableCell>
                <TableCell>引擎</TableCell>
                <TableCell>分类</TableCell>
                {isSuperAdmin && <TableCell>绑定模型</TableCell>}
                {isSuperAdmin && <TableCell>发布状态</TableCell>}
                <TableCell>操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {algorithms.map((algorithm) => {
                const amodel = models.find((m) => String(m.id) === String(algorithm.model_id));
                return (
                  <TableRow key={algorithm.id}>
                    <TableCell>{algorithm.name}</TableCell>
                    <TableCell><Chip label={algorithm.type} size="small" variant="outlined" /></TableCell>
                    <TableCell>
                      <Chip label={algorithm.engine || algorithm.type} size="small" color="primary" variant="outlined" />
                    </TableCell>
                    <TableCell>{algorithm.category || '-'}</TableCell>
                    {isSuperAdmin && (
                      <TableCell>
                        {amodel ? amodel.name : (algorithm.needs_model === false ? '无需模型' : '未绑定')}
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
                    <TableCell>
                      <Tooltip title={isSuperAdmin ? '修改(含模型绑定)' : '查看'}>
                        <IconButton onClick={() => handleEdit(algorithm)}>
                          <Edit />
                        </IconButton>
                      </Tooltip>
                      {isSuperAdmin && (
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
                      )}
                      {isSuperAdmin && (
                        <Tooltip title="删除">
                          <IconButton onClick={() => handleDelete(algorithm.id)} color="error">
                            <Delete />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Grid>

      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingId ? `编辑算法：${formData.name}` : '添加算法'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {!editingId && products.length > 0 && (
              <Grid item xs={12}>
                <Select
                  fullWidth
                  displayEmpty
                  value=""
                  onChange={(e) => applyProductPreset(e.target.value)}
                >
                  <MenuItem value="" disabled>从目录快速填充（推荐按引擎选）…</MenuItem>
                  {products.map((p) => (
                    <MenuItem key={p.type} value={p.type}>
                      {p.name} ({p.type})
                    </MenuItem>
                  ))}
                </Select>
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

            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="标识 type"
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                disabled={!!editingId}
                helperText="建议与引擎相同，如 object_detection"
              />
            </Grid>

            <Grid item xs={12} md={6}>
              <Select
                fullWidth
                value={formData.engine}
                displayEmpty
                onChange={(e) => setFormData({
                  ...formData,
                  engine: e.target.value,
                  type: formData.type || e.target.value,
                })}
              >
                <MenuItem value="" disabled>边缘引擎</MenuItem>
                {engines.map((t) => (
                  <MenuItem key={t.value} value={t.value}>{t.label} ({t.value})</MenuItem>
                ))}
              </Select>
            </Grid>

            <Grid item xs={12}>
              <Select
                fullWidth
                value={formData.category}
                displayEmpty
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              >
                <MenuItem value="">分类</MenuItem>
                {categories.map((c) => (
                  <MenuItem key={c.value} value={c.value}>{c.label}</MenuItem>
                ))}
              </Select>
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="描述"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                disabled={!isSuperAdmin}
              />
            </Grid>

            {isSuperAdmin && needsModel && (
              <Grid item xs={12}>
                <Typography variant="subtitle2" color="error" sx={{ mt: 1, mb: 1 }}>
                  绑定模型（发布前必填）
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
                  disabled={!isSuperAdmin}
                />
              </Grid>
            )}
          </Grid>
        </DialogContent>

        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>{isSuperAdmin ? '取消' : '关闭'}</Button>
          {isSuperAdmin && (
            <Button onClick={handleUpdateOrCreate} variant="contained">
              {editingId ? '保存配置' : '确定创建'}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Grid>
  );
}

export default Algorithms;
