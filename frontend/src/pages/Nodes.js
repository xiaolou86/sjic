import React, { useState, useEffect } from 'react';
import {
    Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead,
    TableRow, Button, IconButton, Typography, Box, Dialog, DialogTitle,
    DialogContent, DialogActions, TextField, Chip, Select, MenuItem, OutlinedInput,
    Menu, ListItemIcon, ListItemText, Divider, LinearProgress, Tooltip, Snackbar, Alert, Stack,
    FormControl, InputLabel
} from '@mui/material';
import {
    Edit, Delete, Circle, RestartAlt, PowerSettingsNew, WifiTethering, SettingsBackupRestore, ContentCopy
} from '@mui/icons-material';
import axios from '../utils/axios';

function Nodes() {
    const canPower = ['customer', 'vendor'].includes(localStorage.getItem('user_role'));
    const [nodes, setNodes] = useState([]);
    const [cameras, setCameras] = useState([]);
    const [openDialog, setOpenDialog] = useState(false);
    const [editingNode, setEditingNode] = useState(null);
    const [formData, setFormData] = useState({ name: '', bound_camera_ids: [] });
    const [powerBusyId, setPowerBusyId] = useState(null);
    const [powerMenu, setPowerMenu] = useState({ anchor: null, node: null });
    const [copyMsg, setCopyMsg] = useState({ open: false, type: 'success', text: '' });

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

    const closePowerMenu = () => setPowerMenu({ anchor: null, node: null });

    const handleAgentRestart = async (node) => {
        closePowerMenu();
        if (!window.confirm(`确定重启边缘程序「${node.name}」？\n仅重启 Agent 容器，不关闭主机。需盒子侧 Docker Compose（restart: unless-stopped）。`)) {
            return;
        }
        setPowerBusyId(node.id);
        try {
            const result = await axios.post(`/api/nodes/${node.id}/restart`);
            window.alert(result.message || '重启程序指令已下发');
        } catch (error) {
            console.error('Error restarting agent:', error);
            window.alert('重启程序失败: ' + (error.response?.data?.error || error.message));
        } finally {
            setPowerBusyId(null);
        }
    };

    const handleNodePower = async (node, action) => {
        closePowerMenu();
        const messages = {
            reboot: `确定重启边缘主机「${node.name}」？\n主机将重新开机，正在运行的任务会中断。`,
            shutdown: `确定关闭边缘主机「${node.name}」？\n关机后需网络唤醒或现场开机才能再上线。`,
            wake: `向「${node.name}」发送网络唤醒（WoL）？\n请确认网卡已开启 WOL，且与平台在同一局域网。`,
        };
        if (!window.confirm(messages[action])) {
            return;
        }
        setPowerBusyId(node.id);
        try {
            const result = await axios.post(`/api/nodes/${node.id}/power`, { action });
            window.alert(result.message || '指令已下发');
        } catch (error) {
            console.error('Error node power:', error);
            window.alert('操作失败: ' + (error.response?.data?.error || error.message));
        } finally {
            setPowerBusyId(null);
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
        if (ageMs > 90000) return 'warning';
        return 'success';
    };

    const getStatusLabel = (status, lastHeartbeat) => {
        const color = getStatusColor(status, lastHeartbeat);
        if (color === 'success') return '在线';
        if (color === 'warning') return '失联';
        return '离线';
    };

    const formatLastOnline = (lastHeartbeat) => {
        if (!lastHeartbeat) return '-';
        const timeStr = typeof lastHeartbeat === 'string' ? lastHeartbeat.replace(/-/g, '/') : lastHeartbeat;
        const lastTime = new Date(timeStr);
        if (isNaN(lastTime.getTime())) return String(lastHeartbeat);
        return lastTime.toLocaleString();
    };

    const usageColor = (pct) => {
        if (pct >= 90) return 'error';
        if (pct >= 70) return 'warning';
        return 'primary';
    };

    const UsageBar = ({ label, value, hint }) => {
        if (value == null || Number.isNaN(Number(value)) || Number(value) < 0) {
            return (
                <Box sx={{ minWidth: 92 }}>
                    <Typography variant="caption" color="text.secondary">{label} -</Typography>
                </Box>
            );
        }
        const pct = Math.min(100, Math.max(0, Number(value)));
        const bar = (
            <Box sx={{ minWidth: 92 }}>
                <Typography variant="caption" sx={{ display: 'block', lineHeight: 1.2 }}>
                    {label} {pct.toFixed(0)}%
                </Typography>
                <LinearProgress
                    variant="determinate"
                    value={pct}
                    color={usageColor(pct)}
                    sx={{ height: 6, borderRadius: 1, mt: 0.25 }}
                />
            </Box>
        );
        return hint ? <Tooltip title={hint}>{bar}</Tooltip> : bar;
    };

    const renderHardware = (node) => {
        const hw = node.hardware_status || {};
        let gpu = hw.gpu_usage;
        if (gpu == null && hw.npu_usage != null) gpu = hw.npu_usage;
        if (gpu == null && hw.musa_mem_total_mb) {
            gpu = (Number(hw.musa_mem_used_mb) / Number(hw.musa_mem_total_mb)) * 100;
        }
        if (hw.cpu_usage == null && hw.mem_usage == null && gpu == null) {
            return <Typography variant="caption" color="text.secondary">暂无数据</Typography>;
        }
        const gpuLabel = String(node.architecture || '').toLowerCase().includes('rk3588') ? 'NPU' : 'GPU';
        const gpuWindow = Number(hw.gpu_usage_window_sec) > 0 ? Number(hw.gpu_usage_window_sec) : 30;
        return (
            <Stack direction="row" spacing={1.25} useFlexGap flexWrap="wrap">
                <UsageBar label="CPU" value={hw.cpu_usage} />
                <UsageBar label="内存" value={hw.mem_usage} />
                <UsageBar label={gpuLabel} value={gpu} hint={`${gpuLabel} 为近 ${gpuWindow} 秒平均值`} />
            </Stack>
        );
    };

    return (
        <Grid container spacing={3}>
            <Grid item xs={12}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
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
                                <TableCell>资源占用</TableCell>
                                <TableCell>绑定视频源</TableCell>
                                <TableCell>最近在线时间</TableCell>
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
                                        <TableCell>{node.ip_address || "-"}</TableCell>
                                        <TableCell>{node.architecture || "-"}</TableCell>
                                        <TableCell>{renderHardware(node)}</TableCell>
                                        <TableCell>
                                            {boundNames.length === 0 ? '-' : (
                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                                    {boundNames.map((name, idx) => (
                                                        <Chip key={`${node.id}-${idx}`} size="small" label={name} variant="outlined" />
                                                    ))}
                                                </Box>
                                            )}
                                        </TableCell>
                                        <TableCell>{formatLastOnline(node.last_heartbeat)}</TableCell>
                                        <TableCell>
                                            <IconButton onClick={() => handleEdit(node)} color="primary" title="编辑">
                                                <Edit />
                                            </IconButton>
                                            {canPower && (
                                                <IconButton
                                                    onClick={(e) => setPowerMenu({ anchor: e.currentTarget, node })}
                                                    color="warning"
                                                    title="电源操作"
                                                    disabled={powerBusyId === node.id}
                                                >
                                                    <PowerSettingsNew />
                                                </IconButton>
                                            )}
                                            <IconButton onClick={() => handleDelete(node.id)} color="error" title="移除">
                                                <Delete />
                                            </IconButton>
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                            {nodes.length === 0 && (
                                <TableRow>
                                    <TableCell colSpan={9} align="center" sx={{ py: 5 }}>
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

            <Menu
                anchorEl={powerMenu.anchor}
                open={Boolean(powerMenu.anchor)}
                onClose={closePowerMenu}
            >
                <MenuItem onClick={() => powerMenu.node && handleNodePower(powerMenu.node, 'reboot')}>
                    <ListItemIcon><RestartAlt fontSize="small" /></ListItemIcon>
                    <ListItemText primary="重启主机" />
                </MenuItem>
                <MenuItem onClick={() => powerMenu.node && handleNodePower(powerMenu.node, 'shutdown')}>
                    <ListItemIcon><PowerSettingsNew fontSize="small" /></ListItemIcon>
                    <ListItemText primary="关机" secondary="关闭后需现场开机或远程开机" />
                </MenuItem>
                <MenuItem onClick={() => powerMenu.node && handleNodePower(powerMenu.node, 'wake')}>
                    <ListItemIcon><WifiTethering fontSize="small" /></ListItemIcon>
                    <ListItemText primary="远程开机" />
                </MenuItem>
                <Divider />
                <MenuItem onClick={() => powerMenu.node && handleAgentRestart(powerMenu.node)}>
                    <ListItemIcon><SettingsBackupRestore fontSize="small" /></ListItemIcon>
                    <ListItemText primary="重启程序" secondary="仅重启程序，不关闭主机" />
                </MenuItem>
            </Menu>

            {/* 修改设备名弹窗 */}
            <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
                <DialogTitle>编辑节点</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 1, minWidth: 400 }}>
                        <TextField
                            fullWidth
                            label="节点别名"
                            value={formData.name}
                            onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                        />
                        <FormControl fullWidth sx={{ mt: 2 }}>
                            <InputLabel id="bound-cameras-label">绑定视频源（可多选）</InputLabel>
                            <Select
                                labelId="bound-cameras-label"
                                label="绑定视频源（可多选）"
                                multiple
                                value={formData.bound_camera_ids}
                                onChange={(e) => {
                                    const value = e.target.value;
                                    setFormData(prev => ({ ...prev, bound_camera_ids: typeof value === 'string' ? value.split(',') : value }));
                                }}
                                input={<OutlinedInput label="绑定视频源（可多选）" />}
                                renderValue={(selected) => {
                                    if (!selected || selected.length === 0) return '未选择';
                                    const names = selected.map(id => cameras.find(c => c.id === id)?.name || `ID=${id}`);
                                    return names.join(', ');
                                }}
                            >
                                {cameras.map((camera) => (
                                    <MenuItem key={camera.id} value={camera.id}>
                                        {camera.name}
                                    </MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenDialog(false)}>取消</Button>
                    <Button onClick={handleUpdate} variant="contained">保存</Button>
                </DialogActions>
            </Dialog>
            <Snackbar
                open={copyMsg.open}
                autoHideDuration={2500}
                onClose={() => setCopyMsg((prev) => ({ ...prev, open: false }))}
            >
                <Alert
                    severity={copyMsg.type}
                    onClose={() => setCopyMsg((prev) => ({ ...prev, open: false }))}
                >
                    {copyMsg.text}
                </Alert>
            </Snackbar>
        </Grid>
    );
}

export default Nodes;
