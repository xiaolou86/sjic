import React, { useState, useEffect } from 'react';
import {
  Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead, 
  TableRow, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Select, MenuItem, IconButton, Autocomplete, Chip, Box, Tooltip
} from '@mui/material';
import { Edit, Delete, Add, Publish } from '@mui/icons-material';
import axios from '../utils/axios';

const ALGORITHM_TYPES = [
  { value: 'object_detection', label: '通用目标检测' },
  { value: 'belt_broken', label: '皮带表面故障检测' },
  { value: 'belt_deviation_detection', label: '皮带跑偏检测' },
  { value: 'belt_broken_series', label: '皮带撕裂与磨损检测' },
  { value: 'belt_broken_high', label: '高精度皮带表面撕裂检测' },
  { value: 'other', label: '其他专用固化引擎' }
];

function Algorithms() {
  const [algorithms, setAlgorithms] = useState([]);
  const [models, setModels] = useState([]);
  
  const [openDialog, setOpenDialog] = useState(false);
  const [openPublishDialog, setOpenPublishDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [publishingAlgorithm, setPublishingAlgorithm] = useState(null);
  
  const isSuperAdmin = localStorage.getItem('user_role') === 'vendor';
  
  const [formData, setFormData] = useState({
    name: '',
    type: '',
    description: '',
    model_id: '',
    labels: []
  });

  const [publishForm, setPublishForm] = useState({
    model_id: '',
    labels: []
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

  const handleUpdateOrCreate = async () => {
    try {
      const payload = {
        name: formData.name,
        type: formData.type,
        description: formData.description,
        model_id: formData.model_id || null,
        labels: formData.labels || []
      };
      
      if (editingId) {
        await axios.put(`/api/algorithms/${editingId}`, payload);
      } else {
        await axios.post('/api/algorithms', payload);
      }
      setOpenDialog(false);
      fetchData();
    } catch (error) {
      console.error('Error saving algorithm/app:', error);
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`/api/algorithms/${id}`);
      fetchData();
    } catch (error) {
      console.error('Error deleting algorithm/app:', error);
    }
  };

  const handleOpenPublish = (algorithm) => {
    setPublishingAlgorithm(algorithm);
    setPublishForm({
      model_id: algorithm.model_id || '',
      labels: Array.isArray(algorithm.labels) ? algorithm.labels : []
    });
    setOpenPublishDialog(true);
  };

  const handlePublishVersion = async () => {
    if (!publishingAlgorithm) return;
    try {
      await axios.post(`/api/algorithms/${publishingAlgorithm.id}/publish`, {
        model_id: publishForm.model_id,
        labels: publishForm.labels
      });
      setOpenPublishDialog(false);
      setPublishingAlgorithm(null);
      fetchData();
    } catch (error) {
      console.error('Error publishing algorithm version:', error);
    }
  };

  const handleEdit = (alg) => {
    setEditingId(alg.id);
    setFormData({
      name: alg.name,
      type: alg.type,
      description: alg.description || '',
      model_id: alg.model_id || '',
      labels: alg.labels || []
    });
    setOpenDialog(true);
  };
  
  const resetForm = () => {
    setEditingId(null);
    setFormData({ name: '', type: '', description: '', model_id: '', labels: [] });
  };
  
  // 稳健查找对应的模型 (兼容 id 为 int 或 string 的情况)
  const selectedModel = models.find(m => String(m.id) === String(formData.model_id));
  
  // Debug 日志，帮助排查 labels 没有看到的问题
  console.log("Selected Model:", selectedModel);
  console.log("Selected Model Labelmap:", selectedModel?.labelmap);

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h5" gutterBottom sx={{ userSelect: 'none' }}>
              业务场景配置 (算法模板) 
              {isSuperAdmin && <Chip size="small" color="primary" label="服务商超管" sx={{ ml: 2 }}/>}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              在这里查看和配置您的商业应用场景。
            </Typography>
          </Box>
          {isSuperAdmin && (
            <Button variant="contained" startIcon={<Add />} onClick={() => { resetForm(); setOpenDialog(true); }}>
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
                {isSuperAdmin && <TableCell>算法模型</TableCell>}
                <TableCell>关心的标签 (Labels)</TableCell>
                <TableCell>操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {algorithms.map((algorithm) => {
                const amodel = models.find(m => String(m.id) === String(algorithm.model_id));
                return (
                  <TableRow key={algorithm.id}>
                    <TableCell>{algorithm.name}</TableCell>
                    <TableCell><Chip label={algorithm.type} size="small" variant="outlined"/></TableCell>
                    {isSuperAdmin && <TableCell>{amodel ? amodel.name : '等待绑定'}</TableCell>}
                    <TableCell>
                      {algorithm.labels && algorithm.labels.length > 0
                        ? algorithm.labels.join(', ')
                        : '默认全部'}
                    </TableCell>
                    <TableCell>
                      <Tooltip title={isSuperAdmin ? "配置参数/模型" : "查看模板详情"}>
                        <IconButton onClick={() => handleEdit(algorithm)}><Edit /></IconButton>
                      </Tooltip>
                      {isSuperAdmin && (
                        <Tooltip title="发布算法版本(切换生效模型)">
                          <IconButton onClick={() => handleOpenPublish(algorithm)} color="primary"><Publish /></IconButton>
                        </Tooltip>
                      )}
                      {isSuperAdmin && (
                        <Tooltip title="删除该业务场景">
                          <IconButton onClick={() => handleDelete(algorithm.id)} color="error"><Delete /></IconButton>
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
                fullWidth label="应用场景名称 (如: 安全帽检查)"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <Select
                fullWidth value={formData.type} displayEmpty
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                disabled={!!editingId}
              >
                <MenuItem value="" disabled>请选择底部调用的算法引擎 (Type)</MenuItem>
                {ALGORITHM_TYPES.map(t => <MenuItem key={t.value} value={t.value}>{t.value} ({t.label})</MenuItem>)}
              </Select>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth label="描 述"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                disabled={!isSuperAdmin}
              />
            </Grid>
            
            {isSuperAdmin && (
              <Grid item xs={12}>
                <Typography variant="subtitle2" color="error" sx={{ mt: 1, mb: 1 }}>
                  [出厂配置] 绑定私密核心基座模型 (仅开发可视)
                </Typography>
                <Select
                  fullWidth value={formData.model_id} displayEmpty
                  onChange={(e) => setFormData({ ...formData, model_id: e.target.value, labels: [] })}
                >
                  <MenuItem value="">未绑定 (空缺必报错)</MenuItem>
                  {models.map(m => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
                </Select>
              </Grid>
            )}

            {selectedModel && selectedModel.labelmap && Array.isArray(selectedModel.labelmap) && selectedModel.labelmap.length > 0 && (
              <Grid item xs={12}>
                <Autocomplete
                  multiple
                  options={selectedModel.labelmap}
                  getOptionLabel={(option) => option.name || String(option.id)}
                  value={selectedModel.labelmap.filter(l => (formData.labels || []).includes(l.id))}
                  onChange={(event, newValue) => {
                    setFormData({ ...formData, labels: newValue.map(v => v.id) });
                  }}
                  renderInput={(params) => (
                    <TextField {...params} variant="outlined" label="默认关注的检测目标 (不配置则全捡)" />
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
            
            {selectedModel && (!selectedModel.labelmap || !Array.isArray(selectedModel.labelmap) || selectedModel.labelmap.length === 0) && (
              <Grid item xs={12}>
                <Typography variant="body2" color="error">
                  提示: 选中的模型 ({selectedModel.name}) 未配置 labelmap，无法选择具体目标。
                </Typography>
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

      <Dialog open={openPublishDialog} onClose={() => setOpenPublishDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          发布算法版本{publishingAlgorithm ? `：${publishingAlgorithm.name}` : ''}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <Typography variant="body2" color="textSecondary">
                发布后该算法新建与运行任务将自动使用这里绑定的模型。
              </Typography>
            </Grid>
            <Grid item xs={12}>
              <Select
                fullWidth
                value={publishForm.model_id}
                displayEmpty
                onChange={(e) => setPublishForm({ ...publishForm, model_id: e.target.value, labels: [] })}
              >
                <MenuItem value="">选择生效模型</MenuItem>
                {models.map(m => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
              </Select>
            </Grid>

            {(() => {
              const currentModel = models.find(m => String(m.id) === String(publishForm.model_id));
              if (!currentModel || !Array.isArray(currentModel.labelmap) || currentModel.labelmap.length === 0) {
                return null;
              }
              return (
                <Grid item xs={12}>
                  <Autocomplete
                    multiple
                    options={currentModel.labelmap}
                    getOptionLabel={(option) => option.name || String(option.id)}
                    value={currentModel.labelmap.filter(l => (publishForm.labels || []).includes(l.id))}
                    onChange={(event, newValue) => {
                      setPublishForm({ ...publishForm, labels: newValue.map(v => v.id) });
                    }}
                    renderInput={(params) => (
                      <TextField {...params} variant="outlined" label="默认关注标签(可选)" />
                    )}
                    renderTags={(value, getTagProps) =>
                      value.map((option, index) => (
                        <Chip variant="outlined" label={option.name || String(option.id)} {...getTagProps({ index })} />
                      ))
                    }
                    isOptionEqualToValue={(option, value) => String(option.id) === String(value.id)}
                  />
                </Grid>
              );
            })()}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenPublishDialog(false)}>取消</Button>
          <Button onClick={handlePublishVersion} variant="contained">发布</Button>
        </DialogActions>
      </Dialog>

    </Grid>
  );
}

export default Algorithms;