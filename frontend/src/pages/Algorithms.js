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

const ALGORITHM_TYPES = [
  { value: 'object_detection', label: '通用目标检测' },
  { value: 'belt_broken', label: '皮带表面故障检测' },
  { value: 'belt_deviation_detection', label: '皮带跑偏检测' },
  { value: 'belt_broken_series', label: '皮带撕裂与磨损检测' },
  { value: 'belt_broken_high', label: '高精度皮带表面撕裂检测' },
  { value: 'other', label: '其他专用固化引擎' },
];

function Algorithms() {
  const isSuperAdmin = localStorage.getItem('user_role') === 'vendor';

  const [algorithms, setAlgorithms] = useState([]);
  const [models, setModels] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);

  const [formData, setFormData] = useState({
    name: '',
    type: '',
    description: '',
    model_id: '',
    labels: [],
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const algs = await axios.get('/api/algorithms');
      setAlgorithms(algs || []);

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

  const resetForm = () => {
    setEditingId(null);
    setFormData({ name: '', type: '', description: '', model_id: '', labels: [] });
  };

  const handleEdit = (alg) => {
    setEditingId(alg.id);
    setFormData({
      name: alg.name,
      type: alg.type,
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

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h5" gutterBottom sx={{ userSelect: 'none' }}>
              业务场景配置 (算法模板)
              {isSuperAdmin && <Chip size="small" color="primary" label="服务商超管" sx={{ ml: 2 }} />}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              修改里绑定模型，发布只做上架可见性控制。
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
              添加业务场景
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
                <TableCell>底层算法标识 (Type)</TableCell>
                {isSuperAdmin && <TableCell>绑定模型</TableCell>}
                {isSuperAdmin && <TableCell>发布状态</TableCell>}
                <TableCell>关心的标签 (Labels)</TableCell>
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
                    {isSuperAdmin && <TableCell>{amodel ? amodel.name : '未绑定'}</TableCell>}
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
                      {algorithm.labels && algorithm.labels.length > 0
                        ? algorithm.labels.join(', ')
                        : '默认全部'}
                    </TableCell>
                    <TableCell>
                      <Tooltip title={isSuperAdmin ? '修改(含模型绑定)' : '查看模板详情'}>
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
                        <Tooltip title="删除该业务场景">
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
        <DialogTitle>{editingId ? `编辑业务场景：${formData.name}` : '添加新的业务场景'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="应用场景名称"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </Grid>

            <Grid item xs={12}>
              <Select
                fullWidth
                value={formData.type}
                displayEmpty
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                disabled={!!editingId}
              >
                <MenuItem value="" disabled>请选择底层算法引擎 (Type)</MenuItem>
                {ALGORITHM_TYPES.map((t) => (
                  <MenuItem key={t.value} value={t.value}>{t.value} ({t.label})</MenuItem>
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

            {isSuperAdmin && (
              <Grid item xs={12}>
                <Typography variant="subtitle2" color="error" sx={{ mt: 1, mb: 1 }}>
                  绑定私密模型 (仅超管可见)
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
                    <TextField {...params} variant="outlined" label="默认关注的检测目标" />
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
