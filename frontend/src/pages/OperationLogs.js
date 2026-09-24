import React, { useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Chip, MenuItem, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TablePagination, TableRow, TextField, Typography, Button,
} from '@mui/material';
import axios from '../utils/axios';

const ACTIONS = [
  { value: 'all', label: '全部操作' },
  { value: 'create', label: '创建' },
  { value: 'update', label: '修改' },
  { value: 'delete', label: '删除' },
  { value: 'login', label: '登录' },
  { value: 'logout', label: '登出' },
  { value: 'operate', label: '其他操作' },
];

const MODULES = ['认证', '视频源', '任务', '算法', '模型', '节点', '告警', '检测', '训练', '授权', '系统设置', '系统'];
const CUSTOMER_HIDDEN_MODULES = new Set(['模型', '训练']);

function moduleLabel(value) {
  return !value || value === 'all' ? '全部模块' : value;
}

const ACTION_LABEL = Object.fromEntries(ACTIONS.filter((item) => item.value).map((item) => [item.value, item.label]));

const ROLE_LABEL = {
  vendor: '厂商管理员',
  customer: '客户管理员',
};

function formatTime(value) {
  if (!value) return '';
  return String(value).replace('T', ' ').slice(0, 19);
}

function OperationLogs() {
  const isVendor = localStorage.getItem('user_role') === 'vendor';
  const moduleOptions = [
    'all',
    ...MODULES.filter((name) => isVendor || !CUSTOMER_HIDDEN_MODULES.has(name)),
  ];
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState('all');
  const [module, setModule] = useState('all');
  const [keyword, setKeyword] = useState('');
  const [applied, setApplied] = useState({ action: 'all', module: 'all', keyword: '' });
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await axios.get('/api/operation-logs', {
          params: {
            page: page + 1,
            per_page: rowsPerPage,
            action: applied.action && applied.action !== 'all' ? applied.action : undefined,
            module: applied.module && applied.module !== 'all' ? applied.module : undefined,
            keyword: applied.keyword || undefined,
          },
        });
        if (cancelled) return;
        setItems(data.items || []);
        setTotal(data.total || 0);
        setError('');
      } catch (err) {
        if (!cancelled) setError(err.response?.data?.error || '加载操作日志失败');
      }
    };
    load();
    return () => { cancelled = true; };
  }, [page, rowsPerPage, applied]);

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>操作日志</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          记录登录、登出，以及创建、修改、删除等重要操作。
        </Typography>
        {error && (
          <Typography color="error" variant="body2" sx={{ mb: 2 }}>{error}</Typography>
        )}
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
          <TextField
            select
            size="small"
            label="操作"
            value={action}
            onChange={(e) => setAction(e.target.value)}
            sx={{ minWidth: 160 }}
            SelectProps={{
              displayEmpty: true,
              renderValue: (selected) => ACTIONS.find((item) => item.value === selected)?.label || '全部操作',
            }}
          >
            {ACTIONS.map((item) => (
              <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label="模块"
            value={module}
            onChange={(e) => setModule(e.target.value)}
            sx={{ minWidth: 160 }}
            SelectProps={{
              displayEmpty: true,
              renderValue: (selected) => moduleLabel(selected),
            }}
          >
            {moduleOptions.map((item) => (
              <MenuItem key={item} value={item}>{moduleLabel(item)}</MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            label="关键字"
            placeholder="用户 / 摘要"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setPage(0);
                setApplied({ action, module, keyword: keyword.trim() });
              }
            }}
            sx={{ minWidth: 200 }}
          />
          <Button
            variant="contained"
            onClick={() => {
              setPage(0);
              setApplied({ action, module, keyword: keyword.trim() });
            }}
          >
            查询
          </Button>
        </Stack>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>时间</TableCell>
                <TableCell>用户</TableCell>
                <TableCell>操作</TableCell>
                <TableCell>模块</TableCell>
                <TableCell>摘要</TableCell>
                <TableCell>结果</TableCell>
                <TableCell>IP</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{formatTime(row.created_at)}</TableCell>
                  <TableCell>
                    <Box>{row.username || '-'}</Box>
                    <Typography variant="caption" color="text.secondary">
                      {ROLE_LABEL[row.role] || row.role || ''}
                    </Typography>
                  </TableCell>
                  <TableCell>{ACTION_LABEL[row.action] || row.action}</TableCell>
                  <TableCell>{row.module}</TableCell>
                  <TableCell>{row.summary}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={row.success ? '成功' : '失败'}
                      color={row.success ? 'success' : 'error'}
                    />
                  </TableCell>
                  <TableCell>{row.ip || '-'}</TableCell>
                </TableRow>
              ))}
              {!items.length && (
                <TableRow>
                  <TableCell colSpan={7} align="center">暂无操作日志</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={(event, next) => setPage(next)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(event) => {
            setRowsPerPage(parseInt(event.target.value, 10));
            setPage(0);
          }}
          rowsPerPageOptions={[10, 20, 50]}
          labelRowsPerPage="每页"
        />
      </CardContent>
    </Card>
  );
}

export default OperationLogs;
