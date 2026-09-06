import React, { useState, useEffect } from 'react';
import {
    Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead,
    TableRow, Button, IconButton, Typography, Box, Dialog, DialogTitle,
    DialogContent, DialogActions, TextField, Chip, Select, MenuItem, OutlinedInput
} from '@mui/material';
import { Edit, Delete, Computer, Circle } from '@mui/icons-material';
import axios from '../utils/axios';

function Nodes() {
    const [nodes, setNodes] = useState([]);
    const [cameras, setCameras] = useState([]);
    const [openDialog, setOpenDialog] = useState(false);
    const [editingNode, setEditingNode] = useState(null);
    const [formData, setFormData] = useState({ name: '', bound_camera_ids: [] });

    useEffect(() => {
        fetchNodes();
        fetchCameras();
        // 自动刷新心跳状态
        const interval = setInterval(fetchNodes, 5000);
        return () => clearInterval(interval);
    }, []);

    const fetchNodes = async () => {
        try {
            const response = await axios.get('/api/nodes');
            setNodes(response || []);
        } catch (error) {
            console.error('Error fetching nodes:', error);
        }
    };

    const fetchCameras = async () => {
        try {
            const response = await axios.get('/api/cameras');
            setCameras(response || []);
        } catch (error) {
            console.error('Error fetching cameras:', error);
        }
    };

    const handleEdit = (node) => {
        setEditingNode(node);
        setFormData({ name: node.name, bound_camera_ids: Array.isArray(node.bound_camera_ids) ? node.bound_camera_ids : [] });
        setOpenDialog(true);
    };

    const handleUpdate = async () => {
        try {
            await axios.put(`/api/nodes/${editingNode.id}`, {
                name: formData.name,
                bound_camera_ids: formData.bound_camera_ids
            });
            setOpenDialog(false);
            fetchNodes();
        } catch (error) {
            console.error('Error updating node:', error);
        }
    };

    const handleDelete = async (id) => {
        if (window.confirm("确定要强制移除该边缘计算盒子吗？(移除后盒子可通过重启重新注册)")) {
            try {
                await axios.delete(`/api/nodes/${id}`);
                fetchNodes();
            } catch (error) {
                console.error('Error deleting node:', error);
            }
        }
    };

    const getStatusColor = (status, lastHeartbeat) => {
        if (status !== 'online') return 'error';
        if (!lastHeartbeat) return 'warning';

        // 统一时间字符串解析（兼容各类浏览器）
        const timeStr = typeof lastHeartbeat === 'string' ? lastHeartbeat.replace(/-/g, '/') : lastHeartbeat;
        const lastTime = new Date(timeStr).getTime();
        if (isNaN(lastTime)) return 'warning';

        // 边缘节点心跳周期为 30 秒，设置 90 秒（3倍周期）作为失联缓冲，避免正常网络波动误判离线
        const ageMs = Date.now() - lastTime;
        // #region agent log
        fetch('http://127.0.0.1:7453/ingest/081782cc-6465-4a44-ac05-89d5ee6ce675',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'902a99'},body:JSON.stringify({sessionId:'902a99',hypothesisId:'H4',location:'Nodes.js:getStatusColor',message:'frontend status calc',data:{status,lastHeartbeat,lastTime,ageMs,tzOffsetMin:new Date().getTimezoneOffset()},timestamp:Date.now()})}).catch(()=>{});
        // #endregion
        if (ageMs > 90000) return 'warning';
        return 'success';
    };

    const getStatusLabel = (status, lastHeartbeat) => {
        const color = getStatusColor(status, lastHeartbeat);
        if (color === 'success') return '在线';
        if (color === 'warning') return '失联';
        return '离线';
    };

    return (
        <Grid container spacing={3}>
            <Grid item xs={12}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <Typography variant="h5">节点</Typography>
                </div>
            </Grid>

            <Grid item xs={12}>
                <TableContainer component={Paper}>
                    <Table>
                        <TableHead>
                            <TableRow>
                                <TableCell>状态</TableCell>
                                <TableCell>名称</TableCell>
                                <TableCell>机器码</TableCell>
                                <TableCell>IP 地址</TableCell>
                                <TableCell>机器型号</TableCell>
                                <TableCell>绑定视频源</TableCell>
                                <TableCell>心跳时间</TableCell>
                                <TableCell>操作</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {nodes.map((node) => {
                                const statusColor = getStatusColor(node.status, node.last_heartbeat);
                                const statusLabel = getStatusLabel(node.status, node.last_heartbeat);
                                const boundIds = Array.isArray(node.bound_camera_ids) ? node.bound_camera_ids : [];
                                const boundNames = boundIds
                                    .map(id => cameras.find(c => c.id === id)?.name || `ID=${id}`);
                                return (
                                    <TableRow key={node.id}>
                                        <TableCell>
                                            <Chip
                                                icon={<Circle fontSize="small" />}
                                                label={statusLabel}
                                                color={statusColor}
                                                size="small"
                                                variant="outlined"
                                            />
                                        </TableCell>
                                        <TableCell><b>{node.name}</b></TableCell>
                                        <TableCell>{node.mac_address}</TableCell>
                                        <TableCell>{node.ip_address || "-"}</TableCell>
                                        <TableCell>{node.architecture || "-"}</TableCell>
                                        <TableCell>
                                            {boundNames.length === 0 ? '-' : (
                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                                    {boundNames.map((name, idx) => (
                                                        <Chip key={`${node.id}-${idx}`} size="small" label={name} variant="outlined" />
                                                    ))}
                                                </Box>
                                            )}
                                        </TableCell>
                                        <TableCell>{node.last_heartbeat || "-"}</TableCell>
                                        <TableCell>
                                            <IconButton onClick={() => handleEdit(node)} color="primary">
                                                <Edit />
                                            </IconButton>
                                            <IconButton onClick={() => handleDelete(node.id)} color="error">
                                                <Delete />
                                            </IconButton>
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                            {nodes.length === 0 && (
                                <TableRow>
                                    <TableCell colSpan={8} align="center" sx={{ py: 5 }}>
                                        <Typography color="textSecondary">
                                            暂无注册的边缘节点。请在下位机中配置 MQTT 连接并启动 Edge Agent。
                                        </Typography>
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
            </Grid>

            {/* 修改设备名弹窗 */}
            <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
                <DialogTitle>重命名节点</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 1, minWidth: 400 }}>
                        <TextField
                            fullWidth
                            label="节点别名"
                            value={formData.name}
                            onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                        />
                        <Box sx={{ mt: 2 }}>
                            <Select
                                fullWidth
                                multiple
                                value={formData.bound_camera_ids}
                                onChange={(e) => {
                                    const value = e.target.value;
                                    setFormData(prev => ({ ...prev, bound_camera_ids: typeof value === 'string' ? value.split(',') : value }));
                                }}
                                displayEmpty
                                input={<OutlinedInput />}
                                renderValue={(selected) => {
                                    if (!selected || selected.length === 0) return '未绑定视频源（全部可选）';
                                    const names = selected.map(id => cameras.find(c => c.id === id)?.name || `ID=${id}`);
                                    return names.join(', ');
                                }}
                            >
                                <MenuItem disabled value="">
                                    未绑定视频源（全部可选）
                                </MenuItem>
                                {cameras.map((camera) => (
                                    <MenuItem key={camera.id} value={camera.id}>
                                        {camera.name}
                                    </MenuItem>
                                ))}
                            </Select>
                        </Box>
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenDialog(false)}>取消</Button>
                    <Button onClick={handleUpdate} variant="contained">保存</Button>
                </DialogActions>
            </Dialog>
        </Grid>
    );
}

export default Nodes;
