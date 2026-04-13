import React, { useState, useEffect } from 'react';
import {
  Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead, 
  TableRow, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Select, MenuItem, IconButton, Autocomplete, Chip, Box, Tooltip
} from '@mui/material';
import { Edit } from '@mui/icons-material';
import axios from '../utils/axios';

function Algorithms() {
  const [algorithms, setAlgorithms] = useState([]);
  const [models, setModels] = useState([]);
  
  const [openDialog, setOpenDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  
  const [formData, setFormData] = useState({
    name: '',
    type: '',
    description: '',
    model_id: '',
    labels: []
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [algs, mods] = await Promise.all([
        axios.get('/api/algorithms'),
        axios.get('/api/models')
      ]);
      setAlgorithms(algs || []);
      setModels(mods || []);
    } catch (error) {
      console.error('Error fetching data:', error);
    }
  };

  const handleUpdate = async () => {
    try {
      const payload = {
        description: formData.description,
        model_id: formData.model_id || null,
        labels: formData.labels || []
      };
      
      if (editingId) {
        await axios.put(`/api/algorithms/${editingId}`, payload);
      }
      setOpenDialog(false);
      fetchData();
    } catch (error) {
      console.error('Error saving algorithm:', error);
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
  
  // 稳健查找对应的模型 (兼容 id 为 int 或 string 的情况)
  const selectedModel = models.find(m => String(m.id) === String(formData.model_id));
  
  // Debug 日志，帮助排查 labels 没有看到的问题
  console.log("Selected Model:", selectedModel);
  console.log("Selected Model Labelmap:", selectedModel?.labelmap);

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h5" gutterBottom>
            基础算法配置
          </Typography>
          <Typography variant="body2" color="textSecondary">
            系统内置的底层算法引擎底座，您可以为它们关联默认的适用模型和检测目标，以便在创建调度任务时快速带入。
          </Typography>
        </Box>
      </Grid>
      
      <Grid item xs={12}>
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>算法名称</TableCell>
                <TableCell>底层算法标识 (Type)</TableCell>
                <TableCell>默认关联模型</TableCell>
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
                    <TableCell>{amodel ? amodel.name : '无'}</TableCell>
                    <TableCell>
                      {algorithm.labels && algorithm.labels.length > 0
                        ? algorithm.labels.join(', ')
                        : '默认全部'}
                    </TableCell>
                    <TableCell>
                      <Tooltip title="配置默认参数">
                        <IconButton onClick={() => handleEdit(algorithm)}><Edit /></IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Grid>

      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>配置算法默认值：{formData.name}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth label="底层算法标识 (只读)"
                value={formData.type}
                disabled
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth label="描 述"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </Grid>
            
            <Grid item xs={12}>
              <Typography variant="subtitle2" color="textSecondary" sx={{ mt: 1, mb: 1 }}>
                关联推荐模型与标签 (可选，将在配置任务时作为模板自动填充)
              </Typography>
              <Select
                fullWidth value={formData.model_id} displayEmpty
                onChange={(e) => setFormData({ ...formData, model_id: e.target.value, labels: [] })}
              >
                <MenuItem value="">不关联具体模型</MenuItem>
                {models.map(m => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
              </Select>
            </Grid>

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
          <Button onClick={() => setOpenDialog(false)}>取消</Button>
          <Button onClick={handleUpdate} variant="contained">
            保存配置
          </Button>
        </DialogActions>
      </Dialog>

    </Grid>
  );
}

export default Algorithms;