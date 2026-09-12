import React, { useState, useEffect } from 'react';
import {
  Grid, Card, CardContent, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Dialog, DialogTitle, DialogContent,
  TablePagination, IconButton, TextField, Button, Box, Stack
} from '@mui/material';
import { ZoomIn, Search, FileDownload, Clear } from '@mui/icons-material';
import axios, { getBaseUrl } from '../utils/axios';

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [total, setTotal] = useState(0);
  const [preview, setPreview] = useState(null);
  const [keyword, setKeyword] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [appliedFilters, setAppliedFilters] = useState({ keyword: '', start: '', end: '' });
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    fetchAlerts();
  }, [page, rowsPerPage, appliedFilters]);

  const buildFilterParams = (filters = appliedFilters) => {
    const params = {};
    if (filters.keyword) params.keyword = filters.keyword;
    if (filters.start) params.start = filters.start;
    if (filters.end) params.end = filters.end;
    return params;
  };

  const fetchAlerts = async () => {
    try {
      const response = await axios.get('/api/alerts', {
        params: {
          page: page + 1,
          per_page: rowsPerPage,
          ...buildFilterParams(),
        }
      });
      setAlerts(response.items || []);
      setTotal(response.total || 0);
    } catch (error) {
      console.error('Error fetching alerts:', error);
    }
  };

  const handleSearch = () => {
    setPage(0);
    setAppliedFilters({
      keyword: keyword.trim(),
      start: startTime,
      end: endTime,
    });
  };

  const handleClearFilters = () => {
    setKeyword('');
    setStartTime('');
    setEndTime('');
    setPage(0);
    setAppliedFilters({ keyword: '', start: '', end: '' });
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await axios.get('/api/alerts/export', {
        params: buildFilterParams({
          keyword: keyword.trim() || appliedFilters.keyword,
          start: startTime || appliedFilters.start,
          end: endTime || appliedFilters.end,
        }),
        responseType: 'blob',
        timeout: 120000,
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `alerts_export_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error exporting alerts:', error);
      window.alert('导出失败，请稍后重试');
    } finally {
      setExporting(false);
    }
  };

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const getImageUrl = (imageUrl) => {
    if (!imageUrl) return '';
    if (imageUrl.startsWith('http')) {
      return imageUrl;
    }
    const baseUrl = getBaseUrl() || '';
    return `${baseUrl}${imageUrl}`;
  };

  const handlePreviewImage = (alert) => {
    setPreview({
      url: getImageUrl(alert.image_url),
      camera_name: alert.camera_name || '未知摄像头',
      alert_type: alert.alert_type || '',
      message: alert.message || '',
      timestamp: alert.timestamp,
    });
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              告警记录
            </Typography>

            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={2}
              alignItems={{ md: 'center' }}
              sx={{ mb: 2 }}
            >
              <TextField
                size="small"
                label="关键字"
                placeholder="摄像头 / 类型 / 说明"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
                sx={{ minWidth: 220 }}
              />
              <TextField
                size="small"
                label="开始时间"
                type="datetime-local"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                size="small"
                label="结束时间"
                type="datetime-local"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button variant="contained" startIcon={<Search />} onClick={handleSearch}>
                  查询
                </Button>
                <Button variant="outlined" startIcon={<Clear />} onClick={handleClearFilters}>
                  清空
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<FileDownload />}
                  onClick={handleExport}
                  disabled={exporting}
                >
                  {exporting ? '导出中…' : '导出(含图片)'}
                </Button>
              </Box>
            </Stack>

            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>时间</TableCell>
                    <TableCell>视频源</TableCell>
                    <TableCell>类型</TableCell>
                    <TableCell>说明</TableCell>
                    <TableCell>置信度</TableCell>
                    <TableCell>图片</TableCell>
                    <TableCell>操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {alerts.map((alert) => (
                    <TableRow key={alert.id}>
                      <TableCell>{new Date(alert.timestamp).toLocaleString()}</TableCell>
                      <TableCell>{alert.camera_name}</TableCell>
                      <TableCell>{alert.alert_type}</TableCell>
                      <TableCell sx={{ maxWidth: 280, whiteSpace: 'normal' }}>
                        {alert.message || '-'}
                      </TableCell>
                      <TableCell>
                        {alert.confidence != null ? `${(alert.confidence * 100).toFixed(2)}%` : '-'}
                      </TableCell>
                      <TableCell>
                        {alert.image_url ? (
                          <img
                            src={getImageUrl(alert.image_url)}
                            alt="告警截图"
                            style={{ width: 100, height: 'auto', cursor: 'pointer' }}
                            onClick={() => handlePreviewImage(alert)}
                          />
                        ) : '-'}
                      </TableCell>
                      <TableCell>
                        <IconButton
                          onClick={() => handlePreviewImage(alert)}
                          title="预览"
                          disabled={!alert.image_url}
                        >
                          <ZoomIn />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <TablePagination
                component="div"
                count={total}
                page={page}
                onPageChange={handleChangePage}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleChangeRowsPerPage}
                rowsPerPageOptions={[10, 25, 50, 100]}
                labelRowsPerPage="每页行数"
              />
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>

      <Dialog
        open={Boolean(preview)}
        onClose={() => setPreview(null)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          {preview?.camera_name || '告警图片'}
          {preview?.alert_type ? ` · ${preview.alert_type}` : ''}
          {preview?.timestamp ? (
            <Typography variant="body2" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
              {new Date(preview.timestamp).toLocaleString()}
              {preview.message ? ` — ${preview.message}` : ''}
            </Typography>
          ) : null}
        </DialogTitle>
        <DialogContent>
          {preview?.url && (
            <img
              src={preview.url}
              alt={`${preview.camera_name || '告警'}大图`}
              style={{ width: '100%', height: 'auto' }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Grid>
  );
}

export default Alerts;
