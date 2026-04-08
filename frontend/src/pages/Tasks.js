import React, { useState, useEffect } from 'react';
import {
  Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Switch, FormControlLabel, Select, MenuItem, IconButton,
  Typography, Divider, Box, InputAdornment
} from '@mui/material';
import { Add, Edit, Delete, PlayArrow, Stop, Info, Search } from '@mui/icons-material';
import axios from '../utils/axios';
import BeltCalibrationTool from '../components/BeltCalibrationTool';
import BeltDeviationCalibrationTool from '../components/BeltDeviationCalibrationTool';
import RegionSelectionTool from '../components/RegionSelectionTool';

function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [models, setModels] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [algorithms, setAlgorithms] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    modelId: '',
    cameraId: '',
    edge_node_id: '',
    confidence: 0.5,
    notificationEnabled: true,
    algorithm_id: '',
    algorithm_parameters: {
      min_area_cm2: 100,
      calibration: {
        belt_width: 0,
        points: []
      },
      regions: []
    }
  });
  const [openDetailDialog, setOpenDetailDialog] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);

  // Filtering States
  const [filterNodeId, setFilterNodeId] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchMetadata();
    fetchTasks();
    // 5秒轮询一次，仅更新任务状态，减少不必要的元数据请求
    const timer = setInterval(() => {
      fetchTasks();
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const fetchMetadata = async () => {
    try {
      const [modelsRes, camerasRes, algorithmsRes, nodesRes] = await Promise.all([
        axios.get('/api/models'),
        axios.get('/api/cameras'),
        axios.get('/api/algorithms'),
        axios.get('/api/nodes')
      ]);
      setModels(modelsRes || []);
      setCameras(camerasRes || []);
      setAlgorithms(algorithmsRes || []);
      setNodes(nodesRes.data || []);
    } catch (error) {
      console.error('Error fetching metadata:', error);
    }
  };

  const fetchTasks = async () => {
    try {
      const tasksRes = await axios.get('/api/tasks');
      setTasks(tasksRes || []);
    } catch (error) {
      console.error('Error fetching tasks:', error);
    }
  };

  const handleCreate = async () => {
    try {
      const response = await axios.post('/api/tasks', formData);
      setTasks([...tasks, response]);
      setOpenDialog(false);
    } catch (error) {
      console.error('Error creating task:', error);
    }
  };

  const handleUpdate = async () => {
    try {
      await axios.put(`/api/tasks/${editingTask.id}`, formData);
      setOpenDialog(false);
      resetForm();
      fetchTasks();
    } catch (error) {
      console.error('Error updating task:', error);
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`/api/tasks/${id}`);
      fetchTasks();
    } catch (error) {
      console.error('Error deleting task:', error);
    }
  };

  const handleEdit = (task) => {
    setFormData({
      id: task.id,
      name: task.name,
      cameraId: task.cameraId,
      modelId: task.modelId,
      algorithm_id: task.algorithm_id,
      edge_node_id: task.edge_node_id || '',
      confidence: task.confidence,
      alertThreshold: task.alertThreshold,
      notificationEnabled: task.notificationEnabled,
      algorithm_parameters: task.algorithm_parameters || {}
    });

    setEditingTask(task);
    setOpenDialog(true);
  };

  const resetForm = () => {
    setEditingTask(null);
    setFormData({
      name: '',
      modelId: '',
      cameraId: '',
      edge_node_id: (filterNodeId !== 'all' && filterNodeId !== 'unassigned') ? filterNodeId : '',
      confidence: 0.5,
      alertThreshold: 3,
      notificationEnabled: true,
      algorithm_id: '',
      algorithm_parameters: {
        min_area_cm2: 100,
        calibration: {
          belt_width: 0,
          points: []
        },
        regions: []
      }
    });
  };

  const handleStartDetection = async (task) => {
    try {
      await axios.post('/api/detection/start', {
        camera_id: task.cameraId,
        model_id: task.modelId,
        task_id: task.id,
        settings: {
          confidence: task.confidence,
          alert_threshold: task.alertThreshold,
          regions: task.regions,
          notification_enabled: task.notificationEnabled,
          algorithm_id: task.algorithm_id,
          algorithm_parameters: task.algorithm_parameters
        }
      });
      task.status = 'running';
      fetchTasks();
    } catch (error) {
      console.error('Error starting detection:', error);
    }
  };

  const handleStopDetection = async (task) => {
    try {
      await axios.post('/api/detection/stop', {
        task_id: task.id
      });
      task.status = 'stopped';
      fetchTasks();
    } catch (error) {
      console.error('Error stopping detection:', error);
    }
  };

  const handleCalibrate = (calibrationData) => {
    setFormData(prev => ({
      ...prev,
      algorithm_parameters: {
        ...prev.algorithm_parameters,
        calibration: calibrationData.calibration
      }
    }));
  };

  // 根据算法类型返回对应的标定工具
  const renderCalibrationTool = () => {
    if (!formData.algorithm_id) return null;

    const algorithm = algorithms.find(a => a.id === formData.algorithm_id);
    if (!algorithm) return null;

    console.log('algorithm.type=', algorithm.type)
    switch (algorithm.type) {
      case 'belt_broken':
        return (
          <BeltCalibrationTool
            cameraId={formData.cameraId}
            onCalibrate={handleCalibrate}
          />
        );
      case 'belt_deviation_detecion':
        return (
          <BeltDeviationCalibrationTool
            cameraId={formData.cameraId}
            algorithm_parameters={formData.algorithm_parameters}
            onCalibrate={handleCalibrate}
          />
        );
      default:
        return null;
    }
  };

  // 处理查看详情
  const handleViewDetail = async (task) => {
    try {
      // 获取任务详情，包括标定图像
      const response = await axios.get(`/api/tasks/${task.id}/detail`);
      setSelectedTask(response);
      setOpenDetailDialog(true);
    } catch (error) {
      console.error('Error fetching task detail:', error);
    }
  };

  // 处理区域选择
  const handleRegionSelect = (regionData) => {
    setFormData(prev => ({
      ...prev,
      algorithm_parameters: {
        ...prev.algorithm_parameters,
        detection_region: regionData.detection_region,
        calibration: regionData.calibration
      }
    }));
  };

  // 渲染算法参数
  const renderAlgorithmParams = (task) => {
    const algorithm = algorithms.find(a => a.id === task.algorithm_id);
    if (!algorithm) return null;

    switch (algorithm.type) {
      case 'object_detection':
        console.log('Detection region data:', task.algorithm_parameters?.detection_region);
        console.log('Points:', task.algorithm_parameters?.detection_region?.points);
        console.log('Frame size:', task.algorithm_parameters?.detection_region?.frame_size);

        return (
          <>
            <Typography variant="subtitle2" gutterBottom>目标检测参数：</Typography>
            <Grid container spacing={2}>
              {task.algorithm_parameters?.detection_region && task.algorithm_parameters.calibration && (
                <Grid item xs={12}>
                  <Typography gutterBottom>检测区域：</Typography>
                  <Box sx={{ position: 'relative', width: '100%', maxWidth: 800 }}>
                    <img
                      src={task.algorithm_parameters.calibration.image_data}
                      alt="Detection Region"
                      style={{ width: '100%', height: 'auto' }}
                    />
                    <canvas
                      ref={(canvas) => {
                        if (canvas && task.algorithm_parameters?.detection_region?.points) {
                          const ctx = canvas.getContext('2d');
                          const img = new Image();
                          img.onload = () => {
                            // 设置canvas尺寸与图像一致
                            canvas.width = task.algorithm_parameters.detection_region.frame_size.width;
                            canvas.height = task.algorithm_parameters.detection_region.frame_size.height;

                            // 绘制图像
                            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                            // 绘制检测区域
                            const points = task.algorithm_parameters.detection_region.points;
                            if (points && points.length > 0) {
                              ctx.beginPath();
                              ctx.moveTo(points[0].x, points[0].y);
                              points.forEach((point, index) => {
                                if (index > 0) {
                                  ctx.lineTo(point.x, point.y);
                                }
                              });

                              // 闭合路径
                              ctx.closePath();

                              // 填充和描边
                              ctx.fillStyle = 'rgba(255, 0, 0, 0.2)';
                              ctx.fill();
                              ctx.strokeStyle = 'yellow';
                              ctx.lineWidth = 2;
                              ctx.stroke();

                              // 绘制顶点
                              points.forEach(point => {
                                ctx.beginPath();
                                ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
                                ctx.fillStyle = 'red';
                                ctx.fill();
                                ctx.strokeStyle = 'white';
                                ctx.stroke();
                              });
                            }
                          };
                          img.src = task.algorithm_parameters.calibration.image_data;
                        }
                      }}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        pointerEvents: 'none'
                      }}
                    />
                  </Box>
                </Grid>
              )}
            </Grid>
          </>
        );
      case 'belt_broken':
        return (
          <>
            <Typography variant="subtitle2" gutterBottom>皮带破损检测参数：</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Typography>
                  最小异常面积：{task.algorithm_parameters.min_area_cm2} cm²
                </Typography>
              </Grid>
              <Grid item xs={12}>
                <Typography>
                  皮带宽度：{task.algorithm_parameters.calibration.belt_width} cm
                </Typography>
              </Grid>
              {task.algorithm_parameters.calibration.image_data && (
                <Grid item xs={12}>
                  <Typography gutterBottom>标定图像：</Typography>
                  <Box sx={{ position: 'relative', width: '100%', maxWidth: 800 }}>
                    <img
                      src={task.algorithm_parameters.calibration.image_data}
                      alt="Calibration"
                      style={{ width: '100%', height: 'auto' }}
                    />
                    {/* 绘制标定点 */}
                    <svg
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        pointerEvents: 'none'
                      }}
                    >
                      {task.algorithm_parameters.calibration.points.map((point, index) => (
                        <circle
                          key={index}
                          cx={`${point.x * 100 / task.algorithm_parameters.calibration.frame_size.width}%`}
                          cy={`${point.y * 100 / task.algorithm_parameters.calibration.frame_size.height}%`}
                          r="5"
                          fill="red"
                          stroke="white"
                        />
                      ))}
                      {task.algorithm_parameters.calibration.points.length === 2 && (
                        <line
                          x1={`${task.algorithm_parameters.calibration.points[0].x * 100 / task.algorithm_parameters.calibration.frame_size.width}%`}
                          y1={`${task.algorithm_parameters.calibration.points[0].y * 100 / task.algorithm_parameters.calibration.frame_size.height}%`}
                          x2={`${task.algorithm_parameters.calibration.points[1].x * 100 / task.algorithm_parameters.calibration.frame_size.width}%`}
                          y2={`${task.algorithm_parameters.calibration.points[1].y * 100 / task.algorithm_parameters.calibration.frame_size.height}%`}
                          stroke="red"
                          strokeWidth="2"
                        />
                      )}
                    </svg>
                  </Box>
                </Grid>
              )}
            </Grid>
          </>
        );
      case 'belt_deviation_detecion':
        return (
          <>
            <Typography variant="subtitle2" gutterBottom>检测参数：</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Typography>
                  边界线间距离：{task.algorithm_parameters.calibration.boundary_distance} cm
                </Typography>
              </Grid>
              <Grid item xs={12}>
                <Typography>
                  跑偏报警阈值：{task.algorithm_parameters.calibration.deviation_threshold} cm
                </Typography>
              </Grid>
              {task.algorithm_parameters.calibration.image_data && (
                <Grid item xs={12}>
                  <Typography gutterBottom>标定图像：</Typography>
                  <Box sx={{ position: 'relative', width: '100%', maxWidth: 800 }}>
                    <img
                      src={task.algorithm_parameters.calibration.image_data}
                      alt="Calibration"
                      style={{ width: '100%', height: 'auto' }}
                    />
                    {/* 绘制标定线 */}
                    <svg
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        pointerEvents: 'none'
                      }}
                    >
                      {task.algorithm_parameters.calibration.boundary_lines.map((line, index) => (
                        <g key={index}>
                          <line
                            x1={`${line[0].x * 100 / task.algorithm_parameters.calibration.frame_size.width}%`}
                            y1={`${line[0].y * 100 / task.algorithm_parameters.calibration.frame_size.height}%`}
                            x2={`${line[1].x * 100 / task.algorithm_parameters.calibration.frame_size.width}%`}
                            y2={`${line[1].y * 100 / task.algorithm_parameters.calibration.frame_size.height}%`}
                            stroke={index === 0 ? "blue" : "red"}
                            strokeWidth="2"
                          />
                          {line.map((point, pointIndex) => (
                            <circle
                              key={pointIndex}
                              cx={`${point.x * 100 / task.algorithm_parameters.calibration.frame_size.width}%`}
                              cy={`${point.y * 100 / task.algorithm_parameters.calibration.frame_size.height}%`}
                              r="5"
                              fill="yellow"
                              stroke="white"
                            />
                          ))}
                        </g>
                      ))}
                    </svg>
                  </Box>
                </Grid>
              )}
            </Grid>
          </>
        );
      default:
        return null;
    }
  };

  // 渲染算法特定参数
  const renderAlgorithmSpecificParams = () => {
    if (!formData.algorithm_id) return null;

    const algorithm = algorithms.find(a => a.id === formData.algorithm_id);
    if (!algorithm) return null;

    switch (algorithm.type) {
      case 'object_detection':
        return (
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <RegionSelectionTool
                cameraId={formData.cameraId}
                onSelect={handleRegionSelect}
                existingRegion={formData.algorithm_parameters}
              />
            </Grid>
          </Grid>
        );
      case 'belt_broken':
        return (
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              type="number"
              label="最小异常面积(cm²)"
              value={formData.algorithm_parameters.min_area_cm2}
              onChange={(e) => setFormData({
                ...formData,
                algorithm_parameters: {
                  ...formData.algorithm_parameters,
                  min_area_cm2: parseInt(e.target.value)
                }
              })}
              inputProps={{ min: 1 }}
            />
          </Grid>
        );
      case 'belt_deviation_detecion':
        return null; // 跑偏检测不需要额外参数
      default:
        return null;
    }
  };


  const filteredTasks = tasks.filter(t => {
    // 1. By Node
    if (filterNodeId === 'unassigned' && t.edge_node_id) return false;
    if (filterNodeId !== 'all' && filterNodeId !== 'unassigned' && t.edge_node_id !== filterNodeId) return false;

    // 2. By Status
    if (filterStatus !== 'all' && t.status !== filterStatus) return false;

    // 3. By Search Query
    if (searchQuery && !t.name.toLowerCase().includes(searchQuery.toLowerCase())) return false;

    return true;
  });

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Typography variant="h5" sx={{ fontWeight: 'bold' }}>调度任务中心</Typography>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => {
              resetForm();
              setOpenDialog(true);
            }}
          >
            添加新任务
          </Button>
        </div>

        {/* 高级过滤栏 */}
        <Paper sx={{ p: 2, display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            size="small"
            placeholder="搜索任务名称..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search fontSize="small" />
                </InputAdornment>
              ),
            }}
            sx={{ flexGrow: 1, minWidth: 200 }}
          />

          <Select
            size="small"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            displayEmpty
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="all">运行状态 (全部)</MenuItem>
            <MenuItem value="stopped">🔴 已停止 (Stopped)</MenuItem>
            <MenuItem value="starting">🟡 启动中 (Starting)</MenuItem>
            <MenuItem value="running">🟢 运行中 (Running)</MenuItem>
          </Select>

          <Select
            size="small"
            value={filterNodeId}
            onChange={(e) => setFilterNodeId(e.target.value)}
            displayEmpty
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="all">部署节点 (全平台)</MenuItem>
            <MenuItem value="unassigned">⚠️ 尚未分配节点的任务</MenuItem>
            {nodes.map(node => (
              <MenuItem key={node.id} value={node.id}>
                🖥️ {node.name}
              </MenuItem>
            ))}
          </Select>
        </Paper>
      </Grid>

      <Grid item xs={12}>
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>名称</TableCell>
                <TableCell>视频源</TableCell>
                <TableCell>算力节点</TableCell>
                <TableCell>模型</TableCell>
                <TableCell>算法</TableCell>
                <TableCell>状态</TableCell>
                <TableCell>操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredTasks.map((task) => (
                <TableRow key={task.id}>
                  <TableCell>{task.name}</TableCell>
                  <TableCell>{cameras.find(c => c.id === task.cameraId)?.name}</TableCell>
                  <TableCell>{nodes.find(n => n.id === task.edge_node_id)?.name || "无"}</TableCell>
                  <TableCell>{models.find(m => m.id === task.modelId)?.name}</TableCell>
                  <TableCell>{algorithms.find(a => a.id === task.algorithm_id)?.name}</TableCell>
                  <TableCell>{task.status}</TableCell>
                  <TableCell>
                    <IconButton onClick={() => handleEdit(task)}>
                      <Edit />
                    </IconButton>
                    <IconButton onClick={() => handleDelete(task.id)}>
                      <Delete />
                    </IconButton>
                    {task.status === 'running' ? (
                      <IconButton onClick={() => handleStopDetection(task)}>
                        <Stop />
                      </IconButton>
                    ) : (
                      <IconButton onClick={() => handleStartDetection(task)}>
                        <PlayArrow />
                      </IconButton>
                    )}
                    <IconButton onClick={() => handleViewDetail(task)}>
                      <Info />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Grid>

      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          {editingTask ? '编辑任务' : '创建任务'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="任务名称"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                margin="normal"
              />
            </Grid>

            <Grid item xs={12} md={6}>
              <Select
                fullWidth
                value={formData.modelId}
                onChange={(e) => setFormData({ ...formData, modelId: e.target.value })}
                displayEmpty
              >
                <MenuItem value="">选择模型</MenuItem>
                {models.map(model => (
                  <MenuItem key={model.id} value={model.id}>
                    {model.name}
                  </MenuItem>
                ))}
              </Select>
            </Grid>

            <Grid item xs={12} md={6}>
              <Select
                fullWidth
                value={formData.cameraId}
                onChange={(e) => setFormData({ ...formData, cameraId: e.target.value })}
                displayEmpty
              >
                <MenuItem value="">选择视频源</MenuItem>
                {cameras.map(camera => (
                  <MenuItem key={camera.id} value={camera.id}>
                    {camera.name}
                  </MenuItem>
                ))}
              </Select>
            </Grid>

            <Grid item xs={12} md={6}>
              <Select
                fullWidth
                value={formData.algorithm_id}
                onChange={(e) => setFormData({ ...formData, algorithm_id: e.target.value })}
                displayEmpty
              >
                <MenuItem value="">选择算法</MenuItem>
                {algorithms.map(algorithm => (
                  <MenuItem key={algorithm.id} value={algorithm.id}>
                    {algorithm.name}
                  </MenuItem>
                ))}
              </Select>
            </Grid>

            <Grid item xs={12} md={6}>
              <Select
                fullWidth
                value={formData.edge_node_id || ''}
                onChange={(e) => setFormData({ ...formData, edge_node_id: e.target.value })}
                displayEmpty
              >
                <MenuItem value="">选择运算节点</MenuItem>
                {nodes.map(node => (
                  <MenuItem key={node.id} value={node.id}>
                    {node.name} ({node.status === 'online' ? '🟢 在线' : '🔴 离线'})
                  </MenuItem>
                ))}
              </Select>
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="置信度"
                value={formData.confidence}
                onChange={(e) => setFormData({ ...formData, confidence: parseFloat(e.target.value) })}
                inputProps={{ step: 0.1, min: 0, max: 1 }}
              />
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="告警间隔(秒)"
                value={formData.alertThreshold}
                onChange={(e) => setFormData({ ...formData, alertThreshold: parseInt(e.target.value) })}
                inputProps={{ min: 1 }}
              />
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.notificationEnabled}
                    onChange={(e) => setFormData({ ...formData, notificationEnabled: e.target.checked })}
                  />
                }
                label="启用通知"
              />
            </Grid>

            {renderAlgorithmSpecificParams()}

            <Grid item xs={12}>
              {renderCalibrationTool()}
            </Grid>

          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>取消</Button>
          <Button onClick={editingTask ? handleUpdate : handleCreate} variant="contained">
            {editingTask ? '更新' : '创建'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 详情对话框 */}
      <Dialog
        open={openDetailDialog}
        onClose={() => setOpenDetailDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>任务详情</DialogTitle>
        <DialogContent>
          {selectedTask && (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Typography variant="subtitle1">基本信息</Typography>
                <Divider sx={{ my: 1 }} />
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography>
                      任务名称：{selectedTask.name}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography>
                      视频源：{cameras.find(c => c.id === selectedTask.cameraId)?.name}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography>
                      模型：{models.find(m => m.id === selectedTask.modelId)?.name}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography>
                      算法：{algorithms.find(a => a.id === selectedTask.algorithm_id)?.name}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography>
                      置信度：{selectedTask.confidence}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography>
                      告警间隔：{selectedTask.alertThreshold}秒
                    </Typography>
                  </Grid>
                </Grid>
              </Grid>

              <Grid item xs={12}>
                <Typography variant="subtitle1">算法参数</Typography>
                <Divider sx={{ my: 1 }} />
                {renderAlgorithmParams(selectedTask)}
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDetailDialog(false)}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Grid>
  );
}

export default Tasks; 