import React, { useState, useEffect } from 'react';
import { 
  Grid, Card, CardContent, Typography, Table, TableBody, TableCell, 
  TableContainer, TableHead, TableRow, Paper, Dialog, DialogContent,
  TablePagination, IconButton 
} from '@mui/material';
import { ZoomIn } from '@mui/icons-material';
import axios from '../utils/axios';

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [total, setTotal] = useState(0);
  const [previewImage, setPreviewImage] = useState(null);

  useEffect(() => {
    fetchAlerts();
  }, [page, rowsPerPage]);

  const fetchAlerts = async () => {
    try {
      const response = await axios.get('/api/alerts', {
        params: {
          page: page + 1,
          per_page: rowsPerPage
        }
      });
      setAlerts(response.items || []);
      setTotal(response.total || 0);
    } catch (error) {
      console.error('Error fetching alerts:', error);
    }
  };

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handlePreviewImage = (imageUrl) => {
    setPreviewImage(imageUrl);
  };

  // 添加一个处理图片 URL 的函数
  const getImageUrl = (imageUrl) => {
    if (!imageUrl) return '';
    if (imageUrl.startsWith('http')) {
      return imageUrl;
    }
    // 使用环境变量中的 API URL
    const baseUrl = process.env.REACT_APP_API_URL || '';
    return `${baseUrl}${imageUrl}`;
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              告警记录
            </Typography>
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
                      <TableCell>{(alert.confidence * 100).toFixed(2)}%</TableCell>
                      <TableCell>
                        <img
                          src={getImageUrl(alert.image_url)}
                          alt="告警截图"
                          style={{ width: 100, height: 'auto' }}
                        />
                      </TableCell>
                      <TableCell>
                        <IconButton 
                          onClick={() => handlePreviewImage(getImageUrl(alert.image_url))}
                          title="预览"
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

      {/* 图片预览对话框 */}
      <Dialog
        open={Boolean(previewImage)}
        onClose={() => setPreviewImage(null)}
        maxWidth="lg"
      >
        <DialogContent>
          {previewImage && (
            <img
              src={previewImage}
              alt="告警大图"
              style={{ width: '100%', height: 'auto' }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Grid>
  );
}

export default Alerts; 