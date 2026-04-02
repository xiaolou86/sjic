import React, { useState, useEffect } from 'react';
import {
    Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead,
    TableRow, Button, IconButton, Typography, Box, Dialog, DialogTitle,
    DialogContent, DialogActions, TextField, Chip
} from '@mui/material';
import { Edit, Delete, Computer, Circle } from '@mui/icons-material';
import axios from '../utils/axios';

function Nodes() {
    const [nodes, setNodes] = useState([]);
    const [openDialog, setOpenDialog] = useState(false);
    const [editingNode, setEditingNode] = useState(null);
    const [formData, setFormData] = useState({ name: '' });

    useEffect(() => {
        fetchNodes();
        // 自动刷新心跳状态
        const interval = setInterval(fetchNodes, 5000);
        return () => clearInterval(interval);
    }, []);

    const fetchNodes = async () => {
        try {
            const response = await axios.get('/api/nodes');
            setNodes(response.data || []);
        } catch (error) {
            console.error('Error fetching nodes:', error);
        }
    };

    const handleEdit = (node) => {
        setEditingNode(node);
        setFormData({ name: node.name });
        setOpenDialog(true);
    };

    const handleUpdate = async () => {
        try {
            await axios.put(`/api/nodes/${editingNode.id}`, formData);
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

        // 如果超过 30 秒没心跳，标记为离线
        const lastTime = new Date(lastHeartbeat).getTime();
        if (Date.now() - lastTime > 30000) return 'warning';
        return 'success';
    };

    return (
        <Grid container spacing={3}>
            <Grid item xs={12}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <Typography variant="h5">边缘算力节点(Edge Node)</Typography>
                </div>
            </Grid>

            <Grid item xs={12}>
                <TableContainer component={Paper}>
                    <Table>
                        <TableHead>
                            <TableRow>
                                <TableCell>状态</TableCell>
                                <TableCell>名称</TableCell>
                                <TableCell>MAC地址 / 唯一凭据</TableCell>
                                <TableCell>IP 地址</TableCell>
                                <TableCell>软硬件架构</TableCell>
                                <TableCell>最后心跳时间</TableCell>
                                <TableCell>操作</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {nodes.map((node) => {
                                const statusColor = getStatusColor(node.status, node.last_heartbeat);
                                return (
                                    <TableRow key={node.id}>
                                        <TableCell>
                                            <Chip
                                                icon={<Circle fontSize="small" />}
                                                label={statusColor === 'success' ? '在线' : '离线'}
                                                color={statusColor}
                                                size="small"
                                                variant="outlined"
                                            />
                                        </TableCell>
                                        <TableCell><b>{node.name}</b></TableCell>
                                        <TableCell>{node.mac_address}</TableCell>
                                        <TableCell>{node.ip_address || "未知"}</TableCell>
                                        <TableCell>{node.architecture || "未知"}</TableCell>
                                        <TableCell>{node.last_heartbeat || "暂无数据"}</TableCell>
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
                                    <TableCell colSpan={7} align="center" sx={{ py: 5 }}>
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
                            onChange={(e) => setFormData({ name: e.target.value })}
                        />
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
