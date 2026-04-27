import React, { useState, useEffect } from 'react';
import { 
  Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, 
  Paper, IconButton, Box, LinearProgress, Typography, Alert
} from '@mui/material';
import { Delete, Upload, Edit } from '@mui/icons-material';
import axios from '../utils/axios';

function Models() {
  const [models, setModels] = useState([]);
  const [openUpload, setOpenUpload] = useState(false);
  const [openEdit, setOpenEdit] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [modelFile, setModelFile] = useState(null);
  const [modelName, setModelName] = useState('');
  const [modelDescription, setModelDescription] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [labelmapText, setLabelmapText] = useState('');
  const [labelmapError, setLabelmapError] = useState(null);

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const response = await axios.get('/api/models');
      setModels(response || []);
      console.log('Models:', response);
    } catch (error) {
      console.error('Error fetching models:', error);
    }
  };

  const handleUpload = async () => {
    if (!modelFile) {
      setError('请选择文件');
      return;
    }
    
    setUploading(true);
    setUploadProgress(0);
    setError(null);
    
    const formData = new FormData();
    formData.append('file', modelFile);
    formData.append('name', modelName);
    formData.append('description', modelDescription);
    
    console.log('FormData entries:');
    for (let pair of formData.entries()) {
      console.log(pair[0] + ': ' + pair[1]);
    }
    
    try {
      const response = await axios.post('/api/models/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          setUploadProgress(percentCompleted);
          console.log(`Upload progress: ${percentCompleted}%`);
        },
        timeout: 300000,
      });
      
      console.log('Upload response:', response);
      setUploading(false);
      setOpenUpload(false);
      setModelFile(null);
      setModelName('');
      setModelDescription('');
      fetchModels();
    } catch (error) {
      console.error('Error uploading model:', error);
      setError(error.response?.data?.error || '上传失败，请重试');
      setUploading(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`/api/models/${id}`);
      fetchModels();
    } catch (error) {
      console.error('Error deleting model:', error);
    }
  };

  const openLabelmapEditor = (model) => {
    setEditingModel(model);
    setModelName(model?.name || '');
    setModelDescription(model?.description || '');
    setLabelmapError(null);
    setLabelmapText(model?.labelmap ? JSON.stringify(model.labelmap, null, 2) : '[]');
    setOpenEdit(true);
  };

  const parseLabelmap = (text) => {
    if (!text || !text.trim()) return null;
    const parsed = JSON.parse(text);
    if (parsed === null) return null;

    // 允许两种格式：
    // 1) [{id:0,name:"person"}, ...]
    // 2) {"0":"person","1":"car"}  -> 转成数组
    if (Array.isArray(parsed)) {
      for (const item of parsed) {
        if (typeof item !== 'object' || item === null) throw new Error('labelmap 数组元素必须是对象');
        if (!Number.isInteger(item.id)) throw new Error('labelmap.id 必须是整数');
        if (typeof item.name !== 'string' || !item.name.trim()) throw new Error('labelmap.name 必须是非空字符串');
      }
      return parsed.map(x => ({ id: x.id, name: x.name.trim() }));
    }

    if (typeof parsed === 'object') {
      const arr = Object.entries(parsed).map(([k, v]) => ({
        id: Number(k),
        name: String(v).trim()
      }));
      for (const item of arr) {
        if (!Number.isInteger(item.id)) throw new Error(`label id ${item.id} 不是整数`);
        if (!item.name) throw new Error(`label id ${item.id} 的 name 不能为空`);
      }
      return arr.sort((a, b) => a.id - b.id);
    }

    throw new Error('labelmap 必须是数组或对象');
  };

  const handleSaveLabelmap = async () => {
    try {
      setLabelmapError(null);
      const labelmap = parseLabelmap(labelmapText);
      await axios.put(`/api/models/${editingModel.id}`, {
        name: modelName,
        description: modelDescription,
        labelmap
      });
      setOpenEdit(false);
      setEditingModel(null);
      setModelName('');
      setModelDescription('');
      fetchModels();
    } catch (e) {
      setLabelmapError(e?.message || '保存失败');
    }
  };

  return (
    <Box>
      <Box sx={{ mb: 2 }}>
        <Button
          variant="contained"
          startIcon={<Upload />}
          onClick={() => setOpenUpload(true)}
        >
          上传模型
        </Button>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>名称</TableCell>
              <TableCell>路径</TableCell>
              <TableCell>描述</TableCell>
              <TableCell>Label IDs</TableCell>
              <TableCell>创建时间</TableCell>
              <TableCell>操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {models.map((model) => (
              <TableRow key={model.id}>
                <TableCell>{model.id}</TableCell>
                <TableCell>{model.name}</TableCell>
                <TableCell>{model.path}</TableCell>
                <TableCell>{model.description}</TableCell>
                <TableCell>
                  {Array.isArray(model.labelmap) ? `${model.labelmap.length} 类` : (model.labelmap ? '已配置' : '未配置')}
                </TableCell>
                <TableCell>{new Date(model.created_at).toLocaleString()}</TableCell>
                <TableCell>
                  <IconButton
                    color="primary"
                    onClick={() => openLabelmapEditor(model)}
                    title="编辑 Label IDs"
                  >
                    <Edit />
                  </IconButton>
                  <IconButton
                    color="error"
                    onClick={() => handleDelete(model.id)}
                    title="删除"
                  >
                    <Delete />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={openUpload} onClose={() => setOpenUpload(false)}>
        <DialogTitle>上传模型</DialogTitle>
        <DialogContent>
          <TextField
            margin="dense"
            label="模型名称"
            fullWidth
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="模型描述"
            fullWidth
            multiline
            minRows={2}
            value={modelDescription}
            onChange={(e) => setModelDescription(e.target.value)}
          />
          <input
            type="file"
            accept=".pt,.pth,.weights,.engine,.onnx"
            onChange={(e) => setModelFile(e.target.files[0])}
            style={{ marginTop: '20px' }}
          />
          {uploading && (
            <div style={{ marginTop: '20px' }}>
              <Typography variant="body2" color="textSecondary">
                上传进度: {uploadProgress}%
              </Typography>
              <LinearProgress 
                variant="determinate" 
                value={uploadProgress} 
                sx={{ mt: 1 }}
              />
            </div>
          )}
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenUpload(false)}>取消</Button>
          <Button 
            onClick={handleUpload} 
            disabled={!modelFile || uploading}
          >
            {uploading ? '上传中...' : '上传'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={openEdit} onClose={() => setOpenEdit(false)} maxWidth="md" fullWidth>
        <DialogTitle>编辑模型</DialogTitle>
        <DialogContent>
          <TextField
            margin="dense"
            label="模型名称"
            fullWidth
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="模型描述"
            fullWidth
            multiline
            minRows={2}
            value={modelDescription}
            onChange={(e) => setModelDescription(e.target.value)}
            sx={{ mb: 2 }}
          />
          <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
            推荐格式：数组 <code>[{"{"}"id":0,"name":"person"{"}"},{"{"}"id":1,"name":"car"{"}"}]</code>，或对象 <code>{"{"}"0":"person","1":"car"{"}"}</code>
          </Typography>
          <TextField
            fullWidth
            multiline
            minRows={10}
            value={labelmapText}
            onChange={(e) => setLabelmapText(e.target.value)}
            placeholder='[{"id":0,"name":"person"}]'
          />
          {labelmapError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {labelmapError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenEdit(false)}>取消</Button>
          <Button onClick={handleSaveLabelmap} variant="contained" disabled={!editingModel}>
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default Models; 