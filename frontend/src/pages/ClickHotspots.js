import React, { useEffect, useState } from 'react';
import {
  Box, Card, CardContent, LinearProgress, MenuItem, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import axios from '../utils/axios';

const PAGE_NAMES = {
  '/dashboard': '运行概览',
  '/nodes': '节点',
  '/streams': '视频源',
  '/models': '模型管理',
  '/algorithms': '算法清单',
  '/tasks': '任务',
  '/training': '模型训练',
  '/alerts': '告警记录',
  '/license': '授权管理',
  '/settings': '系统设置',
  '/operation-logs': '操作日志',
  '/click-hotspots': '点击热点',
};

const RANGES = [
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
  { value: 90, label: '近 90 天' },
];

function pageName(path) {
  return PAGE_NAMES[path] || path;
}

function formatTime(value) {
  if (!value) return '';
  return String(value).replace('T', ' ').slice(0, 19);
}

function ClickHotspots() {
  const [days, setDays] = useState(7);
  const [page, setPage] = useState('');
  const [pages, setPages] = useState([]);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await axios.get('/api/analytics/hotspots', {
          params: { days, page: page || undefined },
        });
        if (cancelled) return;
        setItems(data.items || []);
        setPages(data.pages || []);
        setTotal(data.total_clicks || 0);
        setError('');
      } catch (err) {
        if (!cancelled) setError(err.response?.data?.error || '加载点击热点失败');
      }
    };
    load();
    return () => { cancelled = true; };
  }, [days, page]);

  const maxClicks = items.reduce((max, item) => Math.max(max, item.clicks || 0), 0) || 1;

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>点击热点</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          统计界面按钮与菜单的点击次数，供后续优化布局。此页仅厂商管理员可见。
        </Typography>
        {error && (
          <Typography color="error" variant="body2" sx={{ mb: 2 }}>{error}</Typography>
        )}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} sx={{ mb: 2 }}>
          <TextField
            select
            size="small"
            label="时间"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            sx={{ minWidth: 140 }}
          >
            {RANGES.map((item) => (
              <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label="页面"
            value={page}
            onChange={(e) => setPage(e.target.value)}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">全部页面</MenuItem>
            {pages.map((item) => (
              <MenuItem key={item} value={item}>{pageName(item)}</MenuItem>
            ))}
          </TextField>
          <Typography variant="body2" color="text.secondary">
            合计 {total} 次点击
          </Typography>
        </Stack>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>页面</TableCell>
              <TableCell>控件</TableCell>
              <TableCell width="32%">热度</TableCell>
              <TableCell align="right">点击</TableCell>
              <TableCell align="right">用户数</TableCell>
              <TableCell>最近点击</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow key={`${item.page}-${item.label}`}>
                <TableCell>{pageName(item.page)}</TableCell>
                <TableCell>{item.label}</TableCell>
                <TableCell>
                  <LinearProgress
                    variant="determinate"
                    value={Math.round((item.clicks / maxClicks) * 100)}
                  />
                </TableCell>
                <TableCell align="right">{item.clicks}</TableCell>
                <TableCell align="right">{item.users}</TableCell>
                <TableCell>{formatTime(item.last_at)}</TableCell>
              </TableRow>
            ))}
            {!items.length && (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Box sx={{ py: 2 }}>所选范围内还没有点击记录</Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export default ClickHotspots;
