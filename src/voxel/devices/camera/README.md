# Setting up voxel cameras

## Vieworks Cameras

**eGrabber SDK** (Windows and Linux)
To control the Vieworks VP-151MX camera you will need
[eGrabber for CoaxLink and GigELink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f) installed for your particular
system. Note that, to download the eGrabber SDK, you will first need to make
an account. After downloading and installing eGrabber, you will need to install
the eGrabber python package (stored as a wheel file). For more info installing
the Python wheel file, see the [notes from Euresys](https://documentation.euresys.com/Products/COAXLINK/COAXLINK/en-us/Content/04_eGrabber/programmers-guide/Python.htm).

Generally, the process should be as simple as finding the wheel package in the
eGrabber subfolder and invoking:

```bash
    pip install egrabber-xx.xx.x.xx-py2.py3-none-any.whl
```

## Hamamatsu Cameras

**DCAM SDK** (Windows only)
To control Hamamatsu cameras you will need
[DCAM API](https://dcam-api.com/) installed for your particular system.
