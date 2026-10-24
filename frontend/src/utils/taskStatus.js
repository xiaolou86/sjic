export const TASK_STATUS_LABEL = {
  running: '运行中',
  stopped: '已停止',
  starting: '启动中',
  syncing: '启动中',
  waiting: '等待节点上线',
  error: '出错',
  failed: '启动失败',
};

export function taskStatusLabel(status) {
  return TASK_STATUS_LABEL[status] || status || '未运行';
}

export function isTaskActive(status) {
  return ['running', 'starting', 'syncing', 'waiting'].includes(status);
}
