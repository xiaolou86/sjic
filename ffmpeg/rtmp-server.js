const NodeMediaServer = require('node-media-server');

const config = {
    rtmp: {
        port: 1935,
        chunk_size: 60000,
        gop_cache: true,
        ping: 30,
        ping_timeout: 60
    },
    http: {
        port: 8000,
        allow_origin: '*'
    }
};

var nms = new NodeMediaServer(config);
nms.run();

console.log('RTMP服务器已启动');
console.log('推流地址: rtmp://localhost/live/流名称');
console.log('播放地址: rtmp://localhost/live/流名称');
console.log('HTTP播放: http://localhost:8000/live/流名称.flv');