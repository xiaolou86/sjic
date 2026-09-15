import React, { useState, useEffect, useCallback } from 'react';
import {
  Grid, TextField, Button, Typography, Snackbar, Alert,
  Card, CardContent, Stack, Chip, Divider
} from '@mui/material';
import { CloudUpload, ContentCopy, VpnKey } from '@mui/icons-material';
import axios from '../utils/axios';
import { copyText } from '../utils/clipboard';

const EDITION_LABEL = {
  trial: '试用版',
  official: '正式版',
};

function License() {
  const [license, setLicense] = useState(null);
  const [message, setMessage] = useState({ type: '', content: '' });
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [importingLicense, setImportingLicense] = useState(false);

  const showMsg = (type, content) => {
    setMessage({ type, content });
    setOpenSnackbar(true);
  };

  const fetchLicense = useCallback(async () => {
    try {
      const status = await axios.get('/api/license/status');
      setLicense(status);
    } catch (error) {
      showMsg('error', '获取授权状态失败: ' + (error.response?.data?.error || error.message));
    }
  }, []);

  useEffect(() => {
    fetchLicense();
  }, [fetchLicense]);

  const handleCopyMachineCode = async () => {
    const code = license?.machine_code || '';
    if (!code) return;
    try {
      await copyText(code);
      showMsg('success', '机器码已复制');
    } catch (e) {
      showMsg('error', '复制失败，请手动选择机器码');
    }
  };

  const handleLicenseImport = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setImportingLicense(true);
    try {
      const formData = new FormData();
      formData.append('license', file);
      const result = await axios.post('/api/license/import', formData);
      setLicense(result.status || result);
      showMsg('success', result.message || '授权导入成功');
      window.dispatchEvent(new Event('license-updated'));
    } catch (error) {
      showMsg('error', '导入失败: ' + (error.response?.data?.error || error.message));
      if (error.response?.data?.status) {
        setLicense(error.response.data.status);
      }
    } finally {
      setImportingLicense(false);
    }
  };

  const licenseValid = Boolean(license?.valid);
  const editionLabel = EDITION_LABEL[license?.edition] || (license?.edition ? license.edition : '未授权');

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Typography variant="h5" gutterBottom>授权管理</Typography>
      </Grid>

      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <VpnKey fontSize="small" />
              <Typography variant="h6">授权状态</Typography>
              <Chip
                size="small"
                label={licenseValid ? '有效' : '无效 / 未导入'}
                color={licenseValid ? 'success' : 'warning'}
              />
              <Chip size="small" label={editionLabel} variant="outlined" />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              新部署需先导入试用版或正式版授权后才能使用业务功能。试用版有效期一个月，授权控制可接入视频路数。
              请将下方机器码发给发行方以生成绑定本机的授权文件。
            </Typography>

            <TextField
              fullWidth
              label="本机机器码"
              value={license?.machine_code || ''}
              margin="normal"
              InputProps={{ readOnly: true }}
            />
            <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
              <Button
                variant="outlined"
                startIcon={<ContentCopy />}
                onClick={handleCopyMachineCode}
                disabled={!license?.machine_code}
              >
                复制机器码
              </Button>
              <Button
                variant="contained"
                component="label"
                startIcon={<CloudUpload />}
                disabled={importingLicense}
              >
                {importingLicense ? '导入中…' : '导入授权文件'}
                <input type="file" hidden accept=".json,application/json" onChange={handleLicenseImport} />
              </Button>
            </Stack>

            <Divider sx={{ my: 1.5 }} />
            <Grid container spacing={1}>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="text.secondary">视频路数上限</Typography>
                <Typography>
                  {licenseValid
                    ? (license.max_cameras > 0 ? license.max_cameras : '不限')
                    : '—'}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="text.secondary">到期时间</Typography>
                <Typography>
                  {license?.expires_at || '—'}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="text.secondary">客户标识</Typography>
                <Typography>{license?.customer_id || '—'}</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="text.secondary">状态说明</Typography>
                <Typography>{license?.message || (licenseValid ? '正常' : '—')}</Typography>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Snackbar
        open={openSnackbar}
        autoHideDuration={3000}
        onClose={() => setOpenSnackbar(false)}
      >
        <Alert severity={message.type} onClose={() => setOpenSnackbar(false)}>
          {message.content}
        </Alert>
      </Snackbar>
    </Grid>
  );
}

export default License;
