# Setting up voxel cameras

## Vieworks Cameras

To control the Vieworks VP-151MX camera you will need to install the **egrabber** python package.

However, you will first need to have the [eGrabber for CoaxLink and GigELink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f) installed for your particular system.

The official python SDK is not published on PyPI but comes bundled with the eGrabber SDK as a wheel file.

> [!NOTE]
> To download the eGrabber SDK, you will first need to make an account.

Once the eGrabber SDK is installed, find the wheel file in the program's subfolder and install it into your environment using pip.

For example on windows:

```bash
    pip install "C:\Program Files\Euresys\eGrabber\python\egrabber-xx.xx.x.xx-py2.py3-none-any.whl"
```

> [!NOTE]
> Replace the path with the actual path to the wheel file on your system.
> Replace the version number with the actual version of the wheel file you downloaded.

For more info installing the Python wheel file, see the [notes from Euresys](https://documentation.euresys.com/Products/COAXLINK/COAXLINK/en-us/Content/04_eGrabber/programmers-guide/Python.htm).

## Hamamatsu Cameras

**DCAM SDK** (Windows only)
To control Hamamatsu cameras you will need
[DCAM API](https://dcam-api.com/) installed for your particular system.
