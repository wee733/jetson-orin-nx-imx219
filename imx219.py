# SPDX-License-Identifier: MIT
"""IMX219 capture with the bundled indoor white-paper correction; --raw-color disables it."""
import argparse,time,json
from pathlib import Path
import cv2
import numpy as np
from collections import deque
p=argparse.ArgumentParser()
p.add_argument('--wb',choices=['auto','indoor','daylight'],help='indoor means Argus incandescent/wbmode=2')
p.add_argument('--shutter-us',type=float,help='Fixed exposure in microseconds; translated to Argus nanoseconds')
p.add_argument('--max-exposure-us',type=float,help='Upper exposure limit in microseconds; keeps automatic exposure')
p.add_argument('--gain',type=float,help='Fixed sensor analog gain multiplier')
p.add_argument('--max-gain',type=float,help='Analog gain upper limit, with minimum 1x')
p.add_argument('--isp-gain',type=float,help='Fixed ISP digital gain multiplier')
p.add_argument('--headless',action='store_true')
p.add_argument('--frames',type=int,default=0,help='0: run until Q or Ctrl-C')
p.add_argument('--save',type=Path)
p.add_argument('--white-profile',type=Path,help='White balance JSON; defaults to bundled white_balance.json')
p.add_argument('--raw-color',action='store_true',help='Disable the application LUT and use auto WB unless --wb is set')
p.add_argument('--calibrate-white',type=Path,help='Save a white-reference profile after convergence')
p.add_argument('--ev',type=float,help='Exposure compensation in stops; defaults to saved profile or 0')
p.add_argument('--roi',type=int,nargs=4,default=[480,180,640,320],metavar=('X0','Y0','X1','Y1'))
a=p.parse_args()
if a.frames<0: p.error('--frames must be nonnegative')
if a.calibrate_white and a.white_profile: p.error('Use calibration or correction, not both')
if a.calibrate_white and a.frames and a.frames<90: p.error('Calibration needs at least 90 frames')
if a.raw_color and a.white_profile:p.error('Choose --raw-color or --white-profile')
if not a.calibrate_white and not a.raw_color and a.white_profile is None:
 a.white_profile=Path(__file__).with_name('white_balance.json')
profile=None;lut=None;correction_ms=deque(maxlen=300);reference=deque(maxlen=30);reference_clipping=deque(maxlen=30)
if a.white_profile:
 profile=json.loads(a.white_profile.read_text())
 if profile.get('output_resolution')!=[960,540]:raise SystemExit('Profile output resolution differs from 960x540')
 if a.wb is None:a.wb=profile['wb_preset']
 if profile['wb_preset']!=a.wb:raise SystemExit('White profile requires --wb '+profile['wb_preset'])
 gains=np.asarray(profile['gains_bgr'],np.float32)
 if gains.shape!=(3,) or not np.isfinite(gains).all() or not ((gains>=0.25)&(gains<=4)).all():raise SystemExit('Invalid white profile gains')
 lut=np.clip(np.arange(256,dtype=np.float32)[:,None]*gains[None,:],0,255).round().astype(np.uint8).reshape(256,1,3)
if a.wb is None:a.wb='indoor' if a.calibrate_white else 'auto'
ev=a.ev if a.ev is not None else (profile.get('exposure_compensation_ev',0.0) if profile else 0.0)
if not -2<=ev<=2:raise SystemExit('Exposure compensation must be between -2 and 2')
controls={k:getattr(a,k) for k in ('shutter_us','max_exposure_us','gain','max_gain','isp_gain') if getattr(a,k) is not None}
if profile:
 saved=profile.get('capture_controls',{})
 if controls and controls!=saved:raise SystemExit('Exposure/gain controls differ from white profile; recalibrate')
 controls=saved
for k,v in controls.items():
 if not np.isfinite(v) or v<=0:raise SystemExit(k+' must be positive and finite')
if 'shutter_us' in controls and 'max_exposure_us' in controls:raise SystemExit('Choose fixed shutter or exposure upper limit')
if 'gain' in controls and 'max_gain' in controls:raise SystemExit('Choose fixed analog gain or upper limit')
extra=''
for k,v in controls.items():
 if k in ('shutter_us','max_exposure_us'):
  if v>33000:raise SystemExit('This 30fps example limits exposure to 33000 us; sensor limits also apply')
  high=round(v*1000);low=high if k=='shutter_us' else 13000
  if high<low:raise SystemExit('Exposure below example minimum 13 us')
  extra+=f' exposuretimerange="{low} {high}"'
 else:
  if v<1:raise SystemExit('Gain must be at least 1x; actual sensor limits also apply')
  if k!='isp_gain' and v>10.625:raise SystemExit('This tested mode supports sensor gain up to 10.625x')
  prop='ispdigitalgainrange' if k=='isp_gain' else 'gainrange'
  low=1 if k=='max_gain' else v
  extra+=f' {prop}="{low} {v}"'
wb={'auto':1,'indoor':2,'daylight':5}[a.wb]
pipeline=(f'nvarguscamerasrc sensor-id=0 sensor-mode=2 wbmode={wb} exposurecompensation={ev}{extra} ! '
 'video/x-raw(memory:NVMM),width=1920,height=1080,format=NV12,framerate=30/1 ! '
 'nvvidconv ! video/x-raw,width=960,height=540,format=BGRx ! '
 'videoconvert ! video/x-raw,format=BGR ! appsink max-buffers=1 drop=true sync=false')
cap=cv2.VideoCapture(pipeline,cv2.CAP_GSTREAMER)
if not cap.isOpened():raise SystemExit('Could not open IMX219 CSI0 pipeline')
count=0;frame=None;start=time.monotonic()
try:
 while a.frames==0 or count<a.frames:
  ok,frame=cap.read()
  if not ok:raise RuntimeError('Camera stopped delivering frames')
  count+=1
  if a.calibrate_white and count>60:
   x0,y0,x1,y1=a.roi
   if not (0<=x0<x1<=frame.shape[1] and 0<=y0<y1<=frame.shape[0]):raise RuntimeError('ROI outside output image')
   region=frame[y0:y1,x0:x1]
   reference.append(np.median(region.reshape(-1,3),axis=0))
   reference_clipping.append(float(np.mean(np.any(region>=254,axis=2))))
  if lut is not None:
   t=time.perf_counter();frame=cv2.LUT(frame,lut);correction_ms.append((time.perf_counter()-t)*1000)
  if not a.headless:
   cv2.imshow('Pi5-IMX219-77 ('+a.wb+')',frame)
   if cv2.waitKey(1)&255 in (ord('q'),27):break
except KeyboardInterrupt:pass
finally:
 cap.release()
 if not a.headless:cv2.destroyAllWindows()
if a.calibrate_white:
 if len(reference)<30:raise RuntimeError('Capture at least 90 frames for white reference')
 median=np.median(np.asarray(list(reference)),axis=0)
 if max(reference_clipping)>0.01:raise RuntimeError('More than 1% of white ROI pixels are clipped; lower exposure')
 if median.min()<25 or median.max()>245:raise RuntimeError('Reference too dark or near saturation; adjust lighting')
 gains=median[1]/median
 if not ((gains>=0.25)&(gains<=4)).all():raise RuntimeError('Unsafe reference gain range')
 profile={'schema':1,'camera':'Waveshare Pi5-IMX219-77','wb_preset':a.wb,'ROI':a.roi,'capture_controls':controls,'exposure_compensation_ev':ev,'median_bgr':median.tolist(),'gains_bgr':gains.tolist(),'output_resolution':[960,540],'scope':'Current lighting only; white neutrality correction after ISP, not colorimetric/lens-shading calibration'}
 a.calibrate_white.write_text(json.dumps(profile,indent=2)+'\n')
if a.save is not None and frame is not None:
 if not cv2.imwrite(str(a.save),frame):raise RuntimeError('Could not save image')
print(json.dumps({'frames':count,'seconds':round(time.monotonic()-start,3),'wb_preset':a.wb,'capture_controls':controls,'pipeline':pipeline,'white_profile':str(a.white_profile) if a.white_profile else None,'mean_correction_ms':float(np.mean(correction_ms)) if correction_ms else 0}))
