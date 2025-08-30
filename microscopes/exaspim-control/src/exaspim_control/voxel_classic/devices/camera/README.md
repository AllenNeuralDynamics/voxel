# Setting up voxel cameras

## Vieworks Cameras

To control the Vieworks VP-151MX camera you will need to install the **egrabber** python package. This is available for both Windows and Linux.

However, you will first need to have the [eGrabber for CoaxLink and GigELink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f) installed for your particular system.

The official python SDK is not published on PyPI but comes bundled with the eGrabber SDK as a wheel file.

If you plan to use the provided [Memento](./vieworks/memento.py) class for logging statistics from the camera, you will need to also install [Memento](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f)

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

## Ximea Cameras

To control Ximea cameras you will need to install the **ximea** python package.

The official python SDK is not published on PyPI but is available for download
on the Ximea website.

For Windows, install the Beta Release of the [Ximea API SP](https://www.ximea.com/support/wiki/apis/XIMEA_Windows_Software_Package) - Select xiApiPython checkbox in the API list.

Install the Ximea module by copying the whole folder \XIMEA\API\Python\v{x}\ximea (depending on the Python version) to site-packages of your Python environment.

> [!NOTE]
> For Python 2.x copy ximea folder placed in \XIMEA\API\Python\v2\
> For Python 3.x copy ximea folder placed in \XIMEA\API\Python\v3

For Linux, for the [instructions](https://www.ximea.com/support/wiki/apis/XIMEA_Linux_Software_Package#Installation) appropriately for your architecture.

## Hamamatsu Cameras

**DCAM SDK** (Windows)
To control Hamamatsu cameras you will need
[DCAM API](https://dcam-api.com/) installed for your particular system.

**DCAM SDK** *(Linux)
To control Hamamatsu cameras on Linux there is now a DCAM-Lite[https://www.hamamatsu.com/eu/en/product/cameras/software/driver-software/dcam-api-lite-for-linux.html] Python
API available. This is not yet tested with voxel_classic.
