# Jetson Orin NX + Waveshare IMX219

**English** | [简体中文](README.zh-CN.md)

Enable IMX219 capture and apply the measured correction for a purple color cast. **The bundled correction is enabled by default; calibration is optional.**

Tested on Orin NX 16GB, Ubuntu 24.04 / JetPack 7.2.1 / L4T R39.2.1, Waveshare **Pi5-IMX219-77 (79.3°)**, and a CSI0 connection. Uses the installed `nv_imx219` driver and original NITO.

## Capture with color correction

Requires system OpenCV with GStreamer support and NumPy. Run from the repository directory:

```bash
python3 imx219.py
python3 imx219.py --headless --frames 180 --save corrected.jpg
python3 imx219.py --raw-color  # Compare without the LUT, using auto white balance
```

Preview, saved images, and the Python API all apply `white_balance.json`.

| Setting | Measured indoor profile |
|---|---|
| White balance | Argus `wbmode=2` (incandescent), named `indoor` in this script |
| Exposure compensation | `-0.7 EV`; shutter and gain remain automatic |
| BGR gains | `[0.8691588785, 1, 1.1772151899]` |
| Sensor input / application output | 1920×1080 at 30 fps / 960×540 BGR |

The correction is a per-channel LUT applied after the ISP. It reproduces our indoor white-reference adjustment, not a universal vendor ISP calibration. Different lighting may need a new profile. Other applications do not inherit this correction.

## Optional: create your own white-reference profile

Place white paper under your working light. Set the ROI in **960×540 output coordinates**, avoiding shadows, glare, and paper edges:

```bash
python3 imx219.py --wb indoor --ev -0.7 --headless --frames 180 \
  --roi 320 200 440 280 --calibrate-white my-white.json
python3 imx219.py --white-profile my-white.json
```

The script warms up for 60 frames, then uses the last 30 reference samples to calculate BGR gains as `G/B, 1, G/R`. It rejects dark or clipped references. Check a separate area of the paper afterward.

## Exposure and gain

```bash
# Fixed 20 ms exposure, 1.5x analog gain, 1x ISP digital gain
python3 imx219.py --raw-color --shutter-us 20000 --gain 1.5 --isp-gain 1
# Automatic exposure capped at 5 ms, analog gain capped at 4x
python3 imx219.py --raw-color --max-exposure-us 5000 --max-gain 4 --isp-gain 1
```

Shutter arguments use microseconds, converted to nanoseconds for Argus. These are usage examples; adjust for light and motion. The libcamera commands in the [Waveshare manual](https://www.waveshare.com/wiki/Pi5-IMX219) are not directly interchangeable with Jetson commands. The old Nano `camera_overrides.isp` produced unsupported-field errors on this system and was not adopted.

## If `/dev/video0` is missing

`enable_imx219.py` merges the installed NVIDIA IMX219-A overlay and validates the sensor → NVCSI → VI links. It does not configure other peripherals.

```bash
sudo apt install device-tree-compiler v4l-utils
python3 enable_imx219.py
sudo install -m 644 build/imx219-local.dtb /boot/dtb/imx219-local.dtb
sudo cp /boot/extlinux/extlinux.conf /boot/extlinux/extlinux.conf.imx219-backup
```

Edit `extlinux.conf`: duplicate the current boot entry, preserving its LINUX, INITRD, and APPEND lines. Give the new entry a unique label, set `FDT /boot/dtb/imx219-local.dtb`, and point DEFAULT to that label. Keep the original entry for recovery. If you already use a custom FDT or overlays, merge those settings first instead of replacing them. Reboot and check `v4l2-ctl --list-devices`.

The camera-only DTB passed offline checks; successful capture was previously tested with a DTB containing additional carrier settings. CLI capture and the corrected-frame API each passed a 90-frame capture check.

## License

Original code is MIT licensed. NVIDIA drivers, DTB/DTBO files, and NITO are not redistributed; their BSP licenses apply.
