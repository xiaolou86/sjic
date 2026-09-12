import React, { useState, useEffect } from 'react';
import {
  Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Switch, FormControlLabel, Select, MenuItem, IconButton,
  Typography, Divider, Box, InputAdornment, Alert, Chip
} from '@mui/material';
import { Add, Edit, Delete, PlayArrow, Stop, Info, Search } from '@mui/icons-material';
import axios from '../utils/axios';
import BeltCalibrationTool from '../components/BeltCalibrationTool';
import BeltDeviationCalibrationTool from '../components/BeltDeviationCalibrationTool';
import DetectionRulesEditor from '../components/DetectionRulesEditor';
import PoseBehaviorEditor from '../components/PoseBehaviorEditor';

function mergeAlgoDefaults(algorithm, prevParams = {}) {
  const defaults = algorithm?.parameter_schema?.default_task_params || {};
  const next = { ...defaults, ...prevParams };
  // 按引擎建任务：默认空规则列表，由用户添加多个场景
  if (!Array.isArray(prevParams.rules)) {
    next.rules = Array.isArray(defaults.rules) ? [...defaults.rules] : [];
  }
  if (!Array.isArray(prevParams.behaviors)) {
    next.behaviors = Array.isArray(defaults.behaviors) ? [...defaults.behaviors] : [];
  }
  if (algorithm?.labels?.length && (!next.labels || next.labels.length === 0)) {
    next.labels = algorithm.labels;
  }
  return next;
}

function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [algorithms, setAlgorithms] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    cameraId: '',
    edge_node_id: '',
    confidence: 0.5,
    notificationEnabled: true,
    algorithm_id: '',
    algorithm_parameters: {
      labels: [],
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
  const [formError, setFormError] = useState('');

  // Filtering States
  const [filterNodeId, setFilterNodeId] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const taskAlgorithms = algorithms.filter((a) => a.published === true);
  const selectedAlgorithm = algorithms.find((a) => a.id === formData.algorithm_id);

  const extractApiError = (error, fallback) => {
    const data = error?.response?.data;
    if (typeof data?.error === 'string' && data.error) return data.error;
    if (typeof data?.message === 'string' && data.message) return data.message;
    return fallback;
  };

  useEffect(() => {
    fetchMetadata();
    fetchTasks();
    // 5秒轮询一次，仅更新任务状态，减少不必要的元数据请求
    const timer = setInterval(() => {
      fetchTasks();
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  // 当选择了节点且未显式选择视频源时，自动回填节点绑定的视频源（最佳实践：降低重复配置）
  useEffect(() => {
    if (!formData.edge_node_id) return;
    if (formData.cameraId) return;
    const node = nodes.find(n => n.id === formData.edge_node_id);
    const ids = Array.isArray(node?.bound_camera_ids) ? node.bound_camera_ids : [];
    // 仅当节点只绑定了 1 个视频源时才自动回填；否则改为提示 + 过滤列表，避免误选
    if (ids.length === 1) {
      setFormData(prev => ({ ...prev, cameraId: ids[0] }));
    }
  }, [formData.edge_node_id, formData.cameraId, nodes]);

  const getNodeBoundCameraIds = () => {
    if (!formData.edge_node_id) return null;
    const node = nodes.find(n => n.id === formData.edge_node_id);
    const ids = Array.isArray(node?.bound_camera_ids) ? node.bound_camera_ids : [];
    return ids;
  };

  const fetchMetadata = async () => {
    try {
      const [camerasRes, algorithmsRes, nodesRes, catalogRes] = await Promise.all([
        axios.get('/api/cameras'),
        axios.get('/api/algorithms'),
        axios.get('/api/nodes'),
        axios.get('/api/algorithms/catalog').catch(() => null),
      ]);
      setCameras(camerasRes || []);
      setAlgorithms(algorithmsRes || []);
      setNodes(nodesRes || []);
      setCatalog(catalogRes);
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
    setFormError('');
    try {
      const response = await axios.post('/api/tasks', formData);
      setTasks([...tasks, response]);
      setOpenDialog(false);
      resetForm();
      fetchTasks();
    } catch (error) {
      console.error('Error creating task:', error);
      setFormError(extractApiError(error, '创建任务失败'));
    }
  };

  const handleUpdate = async () => {
    setFormError('');
    try {
      await axios.put(`/api/tasks/${editingTask.id}`, formData);
      setOpenDialog(false);
      resetForm();
      fetchTasks();
    } catch (error) {
      console.error('Error updating task:', error);
      setFormError(extractApiError(error, '更新任务失败'));
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('确定要删除该任务吗？此操作不可恢复。')) return;
    try {
      await axios.delete(`/api/tasks/${id}`);
      fetchTasks();
    } catch (error) {
      console.error('Error deleting task:', error);
    }
  };

  const handleEdit = (task) => {
    setFormError('');
    setFormData({
      id: task.id,
      name: task.name,
      cameraId: task.cameraId,
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
    setFormError('');
    setFormData({
      name: '',
      cameraId: '',
      edge_node_id: (filterNodeId !== 'all' && filterNodeId !== 'unassigned') ? filterNodeId : '',
      confidence: 0.5,
      alertThreshold: 3,
      notificationEnabled: true,
      algorithm_id: '',
      algorithm_parameters: {
        labels: [],
        min_area_cm2: 100,
        calibration: {
          belt_width: 0,
          points: []
        },
        regions: [],
        rules: [],
        behaviors: []
      }
    });
  };

  const handleStartDetection = async (task) => {
    try {
      await axios.post('/api/detection/start', {
        task_id: task.id
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

    console.log('algorithm.type=', algorithm.type, 'engine=', algorithm.engine)
    const engine = algorithm.engine || algorithm.type;
    switch (engine) {
      case 'belt_broken':
        return (
          <BeltCalibrationTool
            cameraId={formData.cameraId}
            onCalibrate={handleCalibrate}
          />
        );
      case 'belt_deviation_detection':
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

  const renderAlgorithmParams = (task) => {
    const algorithm = algorithms.find(a => a.id === task.algorithm_id);
    if (!algorithm) return null;

    const selectedLabels = task.algorithm_parameters?.labels || [];
    
    const labelsUI = selectedLabels.length > 0 ? (
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12}>
          <Typography variant="subtitle2" gutterBottom>关注的检测目标：</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {selectedLabels.map(l => (
              <Chip key={String(l)} label={String(l)} variant="outlined" size="small" color="primary" />
            ))}
          </Box>
        </Grid>
      </Grid>
    ) : null;

    const specificContent = (() => {
      const engine = algorithm.engine || algorithm.type;
      switch (engine) {
        case 'object_detection': {
          const rules = Array.isArray(task.algorithm_parameters?.rules) ? task.algorithm_parameters.rules : [];
          const legacyRegion = task.algorithm_parameters?.detection_region;
          return (
            <>
              <Typography variant="subtitle2" gutterBottom>目标检测规则：</Typography>
              {rules.length === 0 && !legacyRegion && (
                <Typography color="text.secondary">未配置规则</Typography>
              )}
              {rules.map((rule, idx) => (
                <Box key={rule.id || idx} sx={{ mb: 2 }}>
                  <Typography>
                    {rule.name || rule.type}
                    {rule.enabled === false ? '（已关闭）' : ''}
                    {rule.type === 'linger' ? ` · 驻留 ${rule.linger_seconds ?? 5} 秒` : ''}
                    {rule.type === 'absence' ? ` · 缺席 ${rule.absent_seconds ?? 600} 秒` : ''}
                    {rule.type === 'crowd_count' ? ` · ≥${rule.min_count ?? 5}人 / ${rule.seconds ?? 10}秒` : ''}
                    {` · 告警 ${rule.alert_type || '-'}`}
                    {rule.detection_region?.points?.length ? ` · ROI ${rule.detection_region.points.length} 点` : ' · 整帧'}
                  </Typography>
                </Box>
              ))}
              {legacyRegion && rules.length === 0 && (
                <Typography>旧版检测区域：{legacyRegion.points?.length || 0} 个顶点</Typography>
              )}
            </>
          );
        }
        case 'pose_behavior': {
          const behaviors = Array.isArray(task.algorithm_parameters?.behaviors) ? task.algorithm_parameters.behaviors : [];
          return (
            <>
              <Typography variant="subtitle2" gutterBottom>姿态行为：</Typography>
              {behaviors.map((b, idx) => (
                <Typography key={b.id || idx}>
                  {b.name || b.type} · {b.seconds ?? '-'} 秒
                  {b.enabled === false ? '（已关闭）' : ''}
                </Typography>
              ))}
            </>
          );
        }
        case 'camera_health':
          return (
            <Typography>
              黑屏比例 {task.algorithm_parameters?.black_ratio ?? 0.85} ·
              持续 {task.algorithm_parameters?.seconds ?? 3} 秒
            </Typography>
          );
        case 'mouse_idle':
          return (
            <Typography>空闲阈值 {task.algorithm_parameters?.idle_seconds ?? 60} 秒</Typography>
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
        case 'belt_deviation_detection':
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
    })();

    return (
      <>
        {labelsUI}
        {specificContent}
      </>
    );
  };

  // 渲染算法特定参数
  const renderAlgorithmSpecificParams = () => {
    if (!formData.algorithm_id) return null;

    const algorithm = algorithms.find(a => a.id === formData.algorithm_id);
    if (!algorithm) return null;
    const engine = algorithm.engine || algorithm.type;
    const editor = algorithm.parameter_schema?.ui?.editor;

    if (engine === 'object_detection' || editor === 'detection_rules') {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <DetectionRulesEditor
              cameraId={formData.cameraId}
              algorithm={algorithm}
              algorithmParameters={formData.algorithm_parameters}
              catalogPresets={catalog?.od_scene_presets}
              onChange={(nextParams) => setFormData((prev) => ({
                ...prev,
                algorithm_parameters: nextParams,
              }))}
            />
          </Grid>
        </Grid>
      );
    }
    if (engine === 'pose_behavior' || editor === 'pose_behavior') {
      return (
        <PoseBehaviorEditor
          algorithm={algorithm}
          algorithmParameters={formData.algorithm_parameters}
          catalogPresets={catalog?.pose_scene_presets}
          onChange={(nextParams) => setFormData((prev) => ({
            ...prev,
            algorithm_parameters: nextParams,
          }))}
        />
      );
    }
    if (engine === 'camera_health' || editor === 'camera_health') {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <TextField
              fullWidth
              type="number"
              label="黑屏占比阈值"
              value={formData.algorithm_parameters?.black_ratio ?? 0.85}
              onChange={(e) => setFormData({
                ...formData,
                algorithm_parameters: {
                  ...formData.algorithm_parameters,
                  black_ratio: parseFloat(e.target.value),
                },
              })}
              inputProps={{ min: 0.5, max: 0.99, step: 0.01 }}
              helperText="画面暗部比例超过此值判为遮挡/黑屏"
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <TextField
              fullWidth
              type="number"
              label="持续秒数"
              value={formData.algorithm_parameters?.seconds ?? 3}
              onChange={(e) => setFormData({
                ...formData,
                algorithm_parameters: {
                  ...formData.algorithm_parameters,
                  seconds: parseFloat(e.target.value),
                },
              })}
              inputProps={{ min: 1, step: 1 }}
            />
          </Grid>
        </Grid>
      );
    }
    if (engine === 'mouse_idle' || editor === 'mouse_idle') {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <TextField
              fullWidth
              type="number"
              label="无鼠标操作时长(秒)"
              value={formData.algorithm_parameters?.idle_seconds ?? 60}
              onChange={(e) => setFormData({
                ...formData,
                algorithm_parameters: {
                  ...formData.algorithm_parameters,
                  idle_seconds: parseFloat(e.target.value),
                },
              })}
              inputProps={{ min: 10, step: 1 }}
              helperText="边缘需写入鼠标活动时间戳文件"
            />
          </Grid>
        </Grid>
      );
    }
    if (engine === 'belt_broken') {
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
    }
    return null;
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
            添加任务
          </Button>
        </div>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          同一摄像头按引擎建任务：目标检测挂多条规则，姿态检测挂多个行为；不要为每个小场景单独建任务。
        </Typography>

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
            {formError && (
              <Grid item xs={12}>
                <Alert severity="error">{formError}</Alert>
              </Grid>
            )}
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
              {(() => {
                const ids = getNodeBoundCameraIds();
                if (!ids || ids.length === 0) return null;
                const nodeName = nodes.find(n => n.id === formData.edge_node_id)?.name || '该节点';
                return (
                  <Alert severity="info" sx={{ mb: 1 }}>
                    {nodeName} 已绑定 {ids.length} 个可用视频源；此处默认仅展示这些视频源（你仍可切换节点来改变范围）。
                  </Alert>
                );
              })()}
              <Select
                fullWidth
                value={formData.cameraId}
                onChange={(e) => setFormData({ ...formData, cameraId: e.target.value })}
                displayEmpty
              >
                <MenuItem value="">选择视频源</MenuItem>
                {(() => {
                  const boundIds = getNodeBoundCameraIds();
                  const filtered = Array.isArray(boundIds) && boundIds.length > 0
                    ? cameras.filter(c => boundIds.includes(c.id))
                    : cameras;
                  return filtered.map(camera => (
                    <MenuItem key={camera.id} value={camera.id}>
                      {camera.name}
                    </MenuItem>
                  ));
                })()}
              </Select>
            </Grid>

            <Grid item xs={12} md={6}>
              <Select
                fullWidth
                value={formData.algorithm_id}
                onChange={(e) => {
                  const algId = e.target.value;
                  const selectedAlg = algorithms.find(a => a.id === algId);
                  setFormError('');
                  setFormData(prev => ({
                    ...prev,
                    algorithm_id: algId,
                    algorithm_parameters: mergeAlgoDefaults(selectedAlg, {
                      labels: selectedAlg?.labels || [],
                      rules: undefined,
                      behaviors: undefined,
                    }),
                  }));
                }}
                displayEmpty
              >
                <MenuItem value="">选择算法（按引擎，仅已发布）</MenuItem>
                {taskAlgorithms.map(algorithm => (
                  <MenuItem key={algorithm.id} value={algorithm.id}>
                    {algorithm.name}
                    {algorithm.engine ? ` · ${algorithm.engine}` : ''}
                  </MenuItem>
                ))}
              </Select>
              {(() => {
                const selectedAlg = selectedAlgorithm;
                if (!selectedAlg) {
                  if (algorithms.length > 0 && taskAlgorithms.length === 0) {
                    return (
                      <Alert severity="warning" sx={{ mt: 1 }}>
                        当前没有已发布的算法。请先到「算法」页绑定模型并发布（姿态算法需 YOLO-Pose 模型）。
                      </Alert>
                    );
                  }
                  return null;
                }
                if (selectedAlg.published !== true) {
                  return (
                    <Alert severity="error" sx={{ mt: 1 }}>
                      该算法未发布，无法创建任务。请先在「算法」页发布。
                    </Alert>
                  );
                }
                // vendor 响应含 model_id；未绑模型时提前提示
                if (
                  selectedAlg.needs_model
                  && Object.prototype.hasOwnProperty.call(selectedAlg, 'model_id')
                  && !selectedAlg.model_id
                ) {
                  return (
                    <Alert severity="error" sx={{ mt: 1 }}>
                      该算法未绑定模型。姿态任务请先绑定 Pose 模型后再发布。
                    </Alert>
                  );
                }
                const engine = selectedAlg.engine || selectedAlg.type;
                const tip = engine === 'object_detection'
                  ? '可在下方添加多条检测规则/场景（缺席、手机、帽子等），同一任务只推理一次。'
                  : engine === 'pose_behavior'
                    ? '可在下方添加多个姿态行为/场景（张望、手托下巴等），同一任务只推理一次。姿态算法需已绑定并发布 Pose 模型。'
                    : null;
                if (!tip) return null;
                return <Alert severity="info" sx={{ mt: 1 }}>{tip}</Alert>;
              })()}
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