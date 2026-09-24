import React, { useState, useEffect } from 'react';
import {
  Grid, Card, CardContent, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Dialog, DialogTitle, DialogContent,
  DialogActions, TablePagination, IconButton, TextField, Button, Box, Stack,
  Chip, MenuItem, Alert as MuiAlert, InputAdornment, Checkbox
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  ZoomIn, Search, FileDownload, Clear, CheckCircle, Cancel, Undo, Event
} from '@mui/icons-material';
import axios, { getBaseUrl } from '../utils/axios';

const REVIEW_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '待确认' },
  { value: 'confirmed', label: '已确认' },
  { value: 'false_positive', label: '误报' },
];

const STATUS_META = {
  pending: { label: '待确认', color: 'warning' },
  confirmed: { label: '已确认', color: 'success' },
  false_positive: { label: '误报', color: 'default' },
};

function pad2(n) {
  return String(n).padStart(2, '0');
}

function nowDateTimeParts() {
  const d = new Date();
  return {
    date: `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
    time: `${pad2(d.getHours())}:${pad2(d.getMinutes())}`,
  };
}

function splitDateTime(value) {
  if (!value) return { date: '', time: '' };
  const [date, time] = String(value).split('T');
  return { date: date || '', time: (time || '').slice(0, 5) };
}

function DateTimeFilterField({ label, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [draftDate, setDraftDate] = useState('');
  const [draftTime, setDraftTime] = useState('');

  const handleOpen = (event) => {
    event?.stopPropagation?.();
    const parts = value ? splitDateTime(value) : nowDateTimeParts();
    setDraftDate(parts.date);
    setDraftTime(parts.time || '00:00');
    setOpen(true);
  };

  const nativePickerSx = {
    '& input::-webkit-calendar-picker-indicator': {
      cursor: 'pointer',
      opacity: 1,
      filter: (theme) => (theme.palette.mode === 'dark' ? 'invert(1)' : 'none'),
    },
  };

  return (
    <>
      <TextField
        size="small"
        label={label}
        value={value ? value.replace('T', ' ') : ''}
        placeholder="未选择"
        onClick={handleOpen}
        InputLabelProps={{ shrink: true }}
        InputProps={{
          readOnly: true,
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                color="primary"
                onClick={handleOpen}
                edge="end"
                size="small"
                aria-label={`选择${label}`}
                sx={{
                  bgcolor: (theme) => alpha(theme.palette.primary.main, 0.16),
                  '&:hover': {
                    bgcolor: (theme) => alpha(theme.palette.primary.main, 0.28),
                  },
                }}
              >
                <Event fontSize="small" />
              </IconButton>
            </InputAdornment>
          ),
        }}
        sx={{ minWidth: 240, cursor: 'pointer', '& .MuiInputBase-input': { cursor: 'pointer' } }}
      />
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{label}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="日期"
              type="date"
              value={draftDate}
              onChange={(e) => setDraftDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
              sx={nativePickerSx}
            />
            <TextField
              label="时间"
              type="time"
              value={draftTime}
              onChange={(e) => setDraftTime(e.target.value)}
              InputLabelProps={{ shrink: true }}
              inputProps={{ step: 60 }}
              fullWidth
              sx={nativePickerSx}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              onChange('');
              setOpen(false);
            }}
          >
            清除
          </Button>
          <Button onClick={() => setOpen(false)}>取消</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (draftDate && draftTime) onChange(`${draftDate}T${draftTime}`);
              setOpen(false);
            }}
            disabled={!draftDate || !draftTime}
          >
            确定
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [total, setTotal] = useState(0);
  const [preview, setPreview] = useState(null);
  const [keyword, setKeyword] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [reviewStatus, setReviewStatus] = useState('pending');
  const [appliedFilters, setAppliedFilters] = useState({
    keyword: '', start: '', end: '', review_status: 'pending',
  });
  const [exporting, setExporting] = useState('');
  const [selectedIds, setSelectedIds] = useState([]);
  const [reviewDialog, setReviewDialog] = useState(null);
  const [reviewNote, setReviewNote] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [actionError, setActionError] = useState(null);

  useEffect(() => {
    fetchAlerts();
  }, [page, rowsPerPage, appliedFilters]);

  const buildFilterParams = (filters = appliedFilters) => {
    const params = {};
    if (filters.keyword) params.keyword = filters.keyword;
    if (filters.start) params.start = filters.start;
    if (filters.end) params.end = filters.end;
    if (filters.review_status && filters.review_status !== 'all') {
      params.review_status = filters.review_status;
    }
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
      setActionError(error.response?.data?.error || '加载告警失败');
    }
  };

  const handleSearch = () => {
    setSelectedIds([]);
    setPage(0);
    setAppliedFilters({
      keyword: keyword.trim(),
      start: startTime,
      end: endTime,
      review_status: reviewStatus,
    });
  };

  const handleClearFilters = () => {
    setSelectedIds([]);
    setKeyword('');
    setStartTime('');
    setEndTime('');
    setReviewStatus('all');
    setPage(0);
    setAppliedFilters({ keyword: '', start: '', end: '', review_status: 'all' });
  };

  const readExportError = async (payload) => {
    if (payload instanceof Blob) {
      try {
        const json = JSON.parse(await payload.text());
        return json.error || '导出失败，请稍后重试';
      } catch (err) {
        return '导出失败，请稍后重试';
      }
    }
    return payload?.error || '导出失败，请稍后重试';
  };

  const toggleSelected = (id) => {
    setSelectedIds((prev) => (
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    ));
  };

  const togglePageSelected = (checked) => {
    const pageIds = alerts.map((alert) => alert.id);
    setSelectedIds((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, ...pageIds]));
      }
      return prev.filter((id) => !pageIds.includes(id));
    });
  };

  const downloadExportBlob = async (blob) => {
    if (!(blob instanceof Blob)) {
      throw new Error('导出响应无效');
    }
    const head = new Uint8Array(await blob.slice(0, 2).arrayBuffer());
    if (head[0] !== 0x50 || head[1] !== 0x4b) {
      window.alert(await readExportError(blob));
      return;
    }
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `alerts_export_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleExportSelected = async () => {
    if (selectedIds.length === 0) {
      window.alert('请先勾选要导出的告警记录');
      return;
    }
    setExporting('selected');
    try {
      const blob = await axios.post('/api/alerts/export', { ids: selectedIds }, {
        responseType: 'blob',
        timeout: 120000,
      });
      await downloadExportBlob(blob);
    } catch (error) {
      console.error('Error exporting alerts:', error);
      window.alert(await readExportError(error.response?.data));
    } finally {
      setExporting('');
    }
  };

  const handleExportQuery = async () => {
    if (total <= 0) {
      window.alert('当前查询没有可导出的告警记录');
      return;
    }
    if (!window.confirm(`将导出本次查询的全部 ${total} 条记录，包含其他页。`)) {
      return;
    }
    setExporting('query');
    try {
      const blob = await axios.post('/api/alerts/export', {
        scope: 'query',
        keyword: appliedFilters.keyword,
        start: appliedFilters.start,
        end: appliedFilters.end,
        review_status: appliedFilters.review_status,
      }, {
        responseType: 'blob',
        timeout: 120000,
      });
      await downloadExportBlob(blob);
    } catch (error) {
      console.error('Error exporting alerts:', error);
      window.alert(await readExportError(error.response?.data));
    } finally {
      setExporting('');
    }
  };

  const openReview = (alert, nextStatus) => {
    setActionError(null);
    setReviewNote(alert.review_note || '');
    setReviewDialog({ alert, nextStatus });
  };

  const submitReview = async () => {
    if (!reviewDialog) return;
    setReviewing(true);
    setActionError(null);
    try {
      await axios.patch(`/api/alerts/${reviewDialog.alert.id}/review`, {
        review_status: reviewDialog.nextStatus,
        review_note: reviewNote.trim() || null,
      });
      setReviewDialog(null);
      setReviewNote('');
      fetchAlerts();
    } catch (error) {
      console.error('Error reviewing alert:', error);
      setActionError(error.response?.data?.error || '处理失败，请稍后重试');
    } finally {
      setReviewing(false);
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
      alert_type: alert.alert_type_label || alert.alert_type || '',
      message: alert.message || '',
      timestamp: alert.timestamp,
      review_status: alert.review_status,
      reviewed_by: alert.reviewed_by,
      review_note: alert.review_note,
    });
  };

  const statusChip = (status) => {
    const meta = STATUS_META[status] || STATUS_META.pending;
    return <Chip size="small" label={meta.label} color={meta.color} />;
  };

  const reviewActionLabel = (status) => {
    if (status === 'confirmed') return '确认为属实';
    if (status === 'false_positive') return '标记为误报';
    return '重置为待确认';
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              告警记录
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              管理员可确认告警是否属实，或标记误报，便于日常处置与后续调参。
            </Typography>

            {actionError && (
              <MuiAlert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
                {actionError}
              </MuiAlert>
            )}

            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={2}
              alignItems={{ md: 'center' }}
              sx={{ mb: 2 }}
            >
              <TextField
                size="small"
                label="关键字"
                placeholder="视频源 / 场景 / 说明"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
                sx={{ minWidth: 220 }}
              />
              <TextField
                size="small"
                select
                label="处理状态"
                value={reviewStatus}
                onChange={(e) => setReviewStatus(e.target.value)}
                sx={{ minWidth: 140 }}
              >
                {REVIEW_OPTIONS.map((opt) => (
                  <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                ))}
              </TextField>
              <DateTimeFilterField
                label="开始时间"
                value={startTime}
                onChange={setStartTime}
              />
              <DateTimeFilterField
                label="结束时间"
                value={endTime}
                onChange={setEndTime}
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
                  onClick={handleExportSelected}
                  disabled={Boolean(exporting) || selectedIds.length === 0}
                >
                  {exporting === 'selected' ? '导出中…' : `导出选中(${selectedIds.length})`}
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<FileDownload />}
                  onClick={handleExportQuery}
                  disabled={Boolean(exporting) || total === 0}
                >
                  {exporting === 'query' ? '导出中…' : `导出查询结果(${total})`}
                </Button>
              </Box>
            </Stack>

            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox">
                      <Checkbox
                        size="small"
                        indeterminate={
                          alerts.some((alert) => selectedIds.includes(alert.id))
                          && !alerts.every((alert) => selectedIds.includes(alert.id))
                        }
                        checked={alerts.length > 0 && alerts.every((alert) => selectedIds.includes(alert.id))}
                        onChange={(e) => togglePageSelected(e.target.checked)}
                        inputProps={{ 'aria-label': '全选本页' }}
                      />
                    </TableCell>
                    <TableCell sx={{ width: 64 }}>序号</TableCell>
                    <TableCell>时间</TableCell>
                    <TableCell>视频源</TableCell>
                    <TableCell>场景</TableCell>
                    <TableCell>说明</TableCell>
                    <TableCell>置信度</TableCell>
                    <TableCell>状态</TableCell>
                    <TableCell>图片</TableCell>
                    <TableCell>操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {alerts.map((alert, index) => (
                    <TableRow key={alert.id} selected={selectedIds.includes(alert.id)}>
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          checked={selectedIds.includes(alert.id)}
                          onChange={() => toggleSelected(alert.id)}
                          inputProps={{ 'aria-label': `选择第 ${page * rowsPerPage + index + 1} 条` }}
                        />
                      </TableCell>
                      <TableCell>{page * rowsPerPage + index + 1}</TableCell>
                      <TableCell>{new Date(alert.timestamp).toLocaleString()}</TableCell>
                      <TableCell>{alert.camera_name}</TableCell>
                      <TableCell>{alert.alert_type_label || alert.alert_type}</TableCell>
                      <TableCell sx={{ maxWidth: 240, whiteSpace: 'normal' }}>
                        {alert.message || '-'}
                        {alert.review_note ? (
                          <Typography variant="caption" display="block" color="text.secondary">
                            备注：{alert.review_note}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        {alert.confidence != null ? `${(alert.confidence * 100).toFixed(2)}%` : '-'}
                      </TableCell>
                      <TableCell>
                        {statusChip(alert.review_status || 'pending')}
                        {alert.reviewed_by ? (
                          <Typography variant="caption" display="block" color="text.secondary">
                            {alert.reviewed_by}
                          </Typography>
                        ) : null}
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
                        <Stack direction="row" spacing={0.5}>
                          <IconButton
                            onClick={() => handlePreviewImage(alert)}
                            title="预览"
                            disabled={!alert.image_url}
                          >
                            <ZoomIn />
                          </IconButton>
                          {(alert.review_status || 'pending') !== 'confirmed' && (
                            <IconButton
                              color="success"
                              title="确认属实"
                              onClick={() => openReview(alert, 'confirmed')}
                            >
                              <CheckCircle />
                            </IconButton>
                          )}
                          {(alert.review_status || 'pending') !== 'false_positive' && (
                            <IconButton
                              color="warning"
                              title="标记误报"
                              onClick={() => openReview(alert, 'false_positive')}
                            >
                              <Cancel />
                            </IconButton>
                          )}
                          {(alert.review_status || 'pending') !== 'pending' && (
                            <IconButton
                              title="改回待确认"
                              onClick={() => openReview(alert, 'pending')}
                            >
                              <Undo />
                            </IconButton>
                          )}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                  {alerts.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={10} align="center">
                        <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
                          暂无告警记录
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
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

      <Dialog
        open={Boolean(reviewDialog)}
        onClose={() => !reviewing && setReviewDialog(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {reviewDialog ? reviewActionLabel(reviewDialog.nextStatus) : '处理告警'}
        </DialogTitle>
        <DialogContent>
          {reviewDialog && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {reviewDialog.alert.camera_name || '未知摄像头'}
              {' · '}
              {reviewDialog.alert.alert_type_label || reviewDialog.alert.alert_type}
              {reviewDialog.alert.message ? ` — ${reviewDialog.alert.message}` : ''}
            </Typography>
          )}
          <TextField
            autoFocus
            fullWidth
            multiline
            minRows={2}
            label="处理备注（可选）"
            placeholder="例如：现场核实属实 / 光线干扰导致误检"
            value={reviewNote}
            onChange={(e) => setReviewNote(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReviewDialog(null)} disabled={reviewing}>取消</Button>
          <Button variant="contained" onClick={submitReview} disabled={reviewing}>
            {reviewing ? '提交中…' : '确定'}
          </Button>
        </DialogActions>
      </Dialog>
    </Grid>
  );
}

export default Alerts;
