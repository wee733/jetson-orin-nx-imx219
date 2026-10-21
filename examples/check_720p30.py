# SPDX-License-Identifier: MIT
import cv2,time,numpy as np,json
from pathlib import Path
import argparse
a=argparse.ArgumentParser(description='Short 720p30 capture-only timing check')
a.add_argument('--output',type=Path,default=Path('capture-timing.json'))
a=a.parse_args()
p=('nvarguscamerasrc sensor-id=0 sensor-mode=4 ! '
 'video/x-raw(memory:NVMM),width=1280,height=720,format=NV12,framerate=30/1 ! '
 'nvvidconv ! video/x-raw,width=1280,height=720,format=BGRx ! '
 'videoconvert ! video/x-raw,format=BGR ! appsink max-buffers=1 drop=true sync=false')
c=cv2.VideoCapture(p,cv2.CAP_GSTREAMER)
assert c.isOpened()
times=[]
try:
 for i in range(210):
  ok,im=c.read();assert ok
  assert im.shape==(720,1280,3)
  if i>=60:times.append(time.monotonic())
finally:c.release()
dt=np.diff(times)*1000
result={'result':'PASS','shape':[720,1280,3],'frames_measured':len(times),'received_fps':(len(times)-1)/(times[-1]-times[0]),'interarrival_median_ms':float(np.median(dt)),'interarrival_p95_ms':float(np.percentile(dt,95)),'interarrival_max_ms':float(dt.max()),'scope':'Capture and BGR conversion only; algorithm and sensor-to-result latency not tested','pipeline':p}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
