play: 
.\ffplay.exe rtmp://192.168.3.27/live/sjic1

push: 
.\ffmpeg.exe -re -stream_loop -1 -i ./test.mp4 -c:v copy -an -f flv rtmp://192.168.3.27/live/sjic1

rtmp server: 
.\node.exe rtmp-server.js