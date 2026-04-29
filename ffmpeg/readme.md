play: 
.\ffplay.exe rtmp://192.168.3.27/live/sjic1
.\ffmpeg.exe -loop 1 -i ./bus.jpg -vf "fps=5" -c:v libx264 -preset ultrafast -tune stillimage -f flv rtmp://192.168.3.27/live/sjic1

push: 
.\ffmpeg.exe -re -stream_loop -1 -i ./test.mp4 -c:v copy -an -f flv rtmp://192.168.3.27/live/sjic1

rtmp server: 
.\node.exe rtmp-server.js