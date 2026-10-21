# SPDX-License-Identifier: MIT
import cv2,numpy as np,time,json,tempfile
from pathlib import Path
import argparse
p=argparse.ArgumentParser(description='Save one original-size photo per installed IMX219 mode')
p.add_argument('--output',type=Path,default=Path('captures'))
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
root=a.output
out=Path(tempfile.mkdtemp(prefix='imx219-modes-',dir=root))
profile=None
gains=np.ones(3,np.float32)
lut=np.clip(np.arange(256,dtype=np.float32)[:,None]*gains[None,:],0,255).round().astype(np.uint8).reshape(256,1,3)
ev=0.0
rows=[]
for mode,w,h,fps in [(0,3280,2464,21),(1,3280,1848,28),(2,1920,1080,30),(3,1640,1232,30),(4,1280,720,60)]:
 pipeline=(f'nvarguscamerasrc sensor-id=0 sensor-mode={mode} wbmode=1 exposurecompensation={ev} ! '
  f'video/x-raw(memory:NVMM),width={w},height={h},format=NV12,framerate={fps}/1 ! '
  f'nvvidconv ! video/x-raw,width={w},height={h},format=BGRx ! '
  'videoconvert ! video/x-raw,format=BGR ! appsink max-buffers=1 drop=true sync=false')
 cap=cv2.VideoCapture(pipeline,cv2.CAP_GSTREAMER)
 if not cap.isOpened():raise RuntimeError(f'Mode {mode} failed to open')
 start=time.monotonic();count=0;frame=None
 try:
  while time.monotonic()-start<4 or count<10:
   ok,frame=cap.read()
   if not ok:raise RuntimeError(f'Mode {mode} stopped streaming')
   count+=1
 finally:cap.release()
 assert frame.shape==(h,w,3),(mode,frame.shape)
 frame=cv2.LUT(frame,lut)
 p=out/f'imx219-{w}x{h}-{fps}fps.jpg'
 assert cv2.imwrite(str(p),frame,[cv2.IMWRITE_JPEG_QUALITY,95])
 row={'mode':mode,'width':w,'height':h,'configured_fps':fps,'frames_read':count,'warmup_seconds':round(time.monotonic()-start,3),'path':str(p)}
 rows.append(row);print('CAPTURED '+json.dumps(row),flush=True)
manifest={'camera':'Waveshare Pi5-IMX219-77','white_profile':profile,'note':'Original output dimensions; automatic white balance, no user-specific calibration; FPS is requested sensor mode, not measured throughput','captures':rows}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

print('GALLERY '+str(out),flush=True)
