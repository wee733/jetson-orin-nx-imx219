# Jetson Orin NX + Waveshare IMX219-77 (79.3°)

**English** | [简体中文](README.zh-CN.md)

CSI0, P3768/P3767-0000, Ubuntu 24.04. The DT tool accepts L4T R39.2.1 and R39.2.2; an accepted revision is not proof that a particular carrier or tuning is correct. The original capture was on R39.2.1. CONFIG override loading and capture were checked on R39.2.2.

## Correct the optics in Argus, before RGB conversion or NVENC

The RBP194 tuning is for the Pi V2 lens. Loading its shading tables with different optics can amplify red at the edges. Do not install the 2018 Nano tuning wholesale: it contains ISP4-only keys and lacks the v4 AWB mapping. A selected NITO (as in the earlier R39.2.1 setup) or stale nvcam caches can mask a text override. The presence of `imx219.nito` alone does **not** establish which mode is active.

On the Jetson, supply the actual IMX219-77 calibration; do not substitute tables from another lens. The default vendor input is `/home/nvidia/workspaces/damiao-bringup/waveshare-isp/camera_overrides.isp`. The script extracts RBP194 from the installed `libnvodm_imager.so`, imports only matching optical keys, keeps three complete shading grids and updates the v4 gray-line mapping. Preview to a **new** file without root:

```bash
python3 install_isp_override.py --waveshare /path/to/waveshare/camera_overrides.isp --output build/camera_overrides.isp
```

With the aircraft grounded/disarmed and all camera clients stopped, install in CONFIG mode. This is a **host-wide** override; do not use on a mixed-camera system without validating all sensors.

```bash
sudo python3 -I install_isp_override.py --waveshare /path/to/waveshare/camera_overrides.isp --install
```

The installer backs up the previous file (or records its absence), installs root:root 0644, clears both nvcam and serial caches, restarts Argus, captures 60 buffers, and checks this daemon invocation for `Found override file` and no `Invalid isp config attribute`. A failed check restores the prior state. It does not edit the service or remove NITO files. To restore the previous configuration (also restarts Argus):

```bash
sudo python3 -I install_isp_override.py --uninstall
```

## Capture and verify

Requires system OpenCV with GStreamer and NumPy. The CLI and `IMX219()` now default to native ISP color: auto WB (`wbmode=1`), 0 EV, **no** 8-bit LUT. `--raw-color` is the explicit spelling; it does not mean raw Bayer. The guide outputs 960×540 BGR, not the ROS app's 1280×720 RGB8.

```bash
python3 imx219.py --headless --frames 180 --max-exposure-us 5000 --save frame.png
```

Try 5000–8000 µs as an **upper limit**, not a fixed shutter. AE can shorten exposure down to the sensor minimum and vary gain. An upper limit does not create light: short exposures in low light can still be very noisy. Verify on a matte gray/white target under known light and a moving edge; parsing successfully is not an image-quality measurement. `--shutter-us` explicitly fixes exposure and cannot be combined with `--max-exposure-us`.

Optional white-point trim under one light (ROI in output coordinates):

```bash
python3 imx219.py --headless --frames 180 --max-exposure-us 5000 --roi 320 200 440 280 --calibrate-white my-white.json
python3 imx219.py --white-profile my-white.json
```

The old incandescent/−0.7 EV LUT is available **only** with `--white-profile white_balance.json` or `IMX219('white_balance.json')`. Other Argus clients do not inherit a software profile.

## Device tree: only if the camera is missing

`enable_imx219.py` builds locally with `fdtoverlay` (package `device-tree-compiler`), without writing `/boot`. Pass all required carrier overlays in order: they are applied before IMX219-A. On the Damiao setup the USB overlay refers to `dm_usb*` symbols in **its matching base**. The stock base alone failed with `FDT_ERR_NOTFOUND`: do not omit the carrier overlay to make that error disappear.

```bash
python3 enable_imx219.py --base /home/nvidia/workspaces/damiao-bringup/local-base.dtb --extra-overlays /home/nvidia/workspaces/damiao-bringup/damiao-v2-uart-usb3.dtbo --output build-dt-new
```

Use a new output directory. For the reference carrier only, omit `--extra-overlays` and use its matching `--base`. `manifest.json` records ordered inputs, SHA256s, graph validation and the output digest. Offline validation is not a UART/USB hardware test. If installing a DTB separately, preserve the existing boot entry and recovery path; this ISP change does not require a DTB flash or reboot.

## License

Original code: MIT. NVIDIA drivers, DT/DTBO, NITO, and ISP tables are not redistributed. Generate the override from locally supplied inputs under their respective licenses.
