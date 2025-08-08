<h1>
    <div>
        <img src="../../voxel-logo.png" alt="Voxel Logo" width="50" height="50">
    </div>
    ExA-SPIM Control
</h1>

- [Overview](#overview)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Finding Device IDs](#finding-device-ids)
  - [Recommended Hardware](#recommended-hardware)
  - [Documentation](#documentation)
  - [Usage](#usage)
- [Support and Contribution](#support-and-contribution)
- [License](#license)

## Overview

This repository provides acquisition software for the expansion-assisted selective plane illumination microscope (ExA-SPIM).

> [!NOTE]
> **Expansion-assisted selective plane illumination microscopy for nanoscale imaging of centimeter-scale tissues.** eLife **12**:RP91979
*<https://doi.org/10.7554/eLife.91979.2>*

## Getting Started

### Prerequisites

- **Python: >=3.10, <=3.11** (tested)
- We using a virtual environment:
  - [venv](https://docs.python.org/3.11/library/venv.html)
  - Conda: [Anaconda](https://www.anaconda.com/products/individual) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)

This control software can optionally check I/O bandwidth to a local and externally networked drive location. This requires [fio](https://github.com/axboe/fio) to be installed. For Windows, please install the correct [binary files](https://github.com/axboe/fio/releases).

### Installation

1. Create a virtual environment and activate it:
    On Windows:

    ```bash
    conda create -n exaspim-control
    conda activate exaspim-control
    ```

    or

    ```bash
    python -m venv exaspim-control
    .\exaspim-control\Scripts\activate
    ```

2. Clone the repository:

    ```bash
    git clone https://github.com/AllenNeuralDynamics/exaspim-control.git && cd exaspim-control
    ```

3. To use the software, in the root directory, run:

    ```bash
    pip install -e .
    ```

     This should install two repositories that this repository builds upon:
     - [voxel](https://github.com/AllenNeuralDynamics/voxel) - core drivers, microscope, and acquisition codebase
     - [view](https://github.com/AllenNeuralDynamics/view) - core GUI codebase

4. For the Vieworks VP-151MX camera you will need to install the **egrabber** drivers. This is available for both Windows and Linux [eGrabber for CoaxLink and GigELink](https://www.euresys.com/en/Support/Download-area?Series=105d06c5-6ad9-42ff-b7ce-622585ce607f).

5. NI-DAQmx is required. Visit [ni.com/downloads](ni.com/downloads) to download the latest version of NI-DAQmx. None of the recommended additional items are required for nidaqmx to function, and they can be removed to minimize installation size. It is recommended you continue to install the NI Certificates package to allow your Operating System to trust NI built binaries, improving your software and hardware installation experience.

6. To communicate with the ASI stages, the [USB driver](https://www.asiimaging.com/support/downloads/usb-support-on-ms-2000-wk-controllers/) must be installed.

### Finding Device IDs

> [!NOTE]
> Device IDs (i.e. serial numbers) are necessary to accurately construct the [instrument.yaml](./src/exaspim_control/experimental/instrument.yaml) file.

1. To find the camera serial number, open the eGrabber Studio program. The connected camera should be listed with a serial number in parantheses. For example: VIEWORKS VP-151MX-M6H0 (##########).

2. To find the COM port for the Tiger Controller used for the ASI stages, we recommend using the [Tiger Control Panel](https://asiimaging.com/docs/tiger_control_panel). Please follow instructions in the link for installation and usage instructions.

3. To find the device number (i.e. Dev#) for the NI-DAQ, we recommend using a program such as [DAQExpress](https://www.ni.com/en/support/downloads/software-products/download.daqexpress.html?srsltid=AfmBOorqILt1ZQBJS6danKWZslqrQ-NUqIQ0kZrmQdNLI_b2HxMcql8C#348849) or programatically determing the device number. Running the example code below should reveal the number of all NI devices connected to the computer.

     ```python
     import nidaqmx

     for device in nidaqmx.system.System.local().devices:
     print(f"device number = {device.name}")
     ```

4. To find the ID of the Coherent Genesis lasers, open a terminal and activate the virtual environment with the installed exaspim-control repository. Then issue the following commands, which should return the ID of all detected Genesis lasers

     ```bash
     > cohrhops
     Found 3 devices:
       J687424BP914:
       A700467EP203:
       R708588EQ173:
       ...
     ```

     The 488 nm laser ID format will be A###########, the 561 nm laser ID format will be J###########, and the 639 nm laser ID format will be R###########.

5. To find the COM port for the Optotune ICC4C Controller, we recommend using the [Optotune Cockpit](https://www.optotune.com/software-center) software. Please follow instructions in the link for installation and usage instructions.

6. To find the ID of the Thorlabs MFF101 flip mounts, we recommend using the [Thorlabs Kinesis](https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=Motion_Control&viewtab=0) software. Please follow instructions in the link for installation and usage instructions. The ID is the serial number of the device.

7. To find the ID of the Thorabs PM100D power meter, we recommend using the [Thorlabs Optical Power Monitor](https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=OPM) software. Please follow instructions in the link for installation and usage instructions. The ID is the serial number of the device.

8. To find the ID of the Thorlabs TSP101 temperature and humidity sensor, we recommend using the [Thorlabs TSP101](https://www.thorlabs.com/thorproduct.cfm?partnumber=TSP01) software. Please follow instructions in the link for installation and usage instructions. The ID is the serial number of the device.

### Recommended Hardware

>[!IMPORTANT]
> The ExA-SPIM system operates at data rates up to 1.8 GB/sec. Datasets can also be multiple terabytes. Therefore it is recommended to have a large M.2 or U.2/3 NVME drive for data storage.

<br>

>[!IMPORTANT]
>Each raw camera is 288 megapixels (14192x10640 px). Live streaming therefore requires on-the-fly generation of multiple resolutions for each raw camera frame at high speed. This repository computes this pyramid using a GPU. Therefore it is recommended to have a decent GPU with at least 16 GB of RAM (i.e. NVIDIA A4000 or above).# New Document.

<br>

> [!WARNING]
> By factory default, the Vieworks VP-151MX (or other model) cameras have firmware enablewd dark signal non-uniformity (DSNU) correction enabled. This results in non-uniform background pattern for lower light level imaging (i.e. fluorescence microscopy). This can be disabled by Vieworks over a remote support session by contacting [**support@vieworks.com**](support@vieworks.com)

### Documentation

- *(coming soon)*

### Usage

Example configuration files for a real experimental system are provided:

- [instrument.yaml](./src/exaspim_control/experimental/instrument.yaml)
- [acquisition.yaml](./src/exaspim_control/experimental/acquisition.yaml)
- [gui_config.yaml](./src/exaspim_control/experimental/gui_config.yaml)

And the code can be launched by running [```main.py```](./src/exaspim_control/experimental/main.py)

Files for a [simulated microscope](./src/exaspim_control/simulated/) are also available.

## Support and Contribution

If you encounter any problems or would like to contribute to the project,
please submit an [Issue](https://github.com/AllenNeuralDynamics/exaspim-control/issues)
on GitHub.

## License

exaspim-control is licensed under the MIT License. For more details, see
the [LICENSE](LICENSE) file.
