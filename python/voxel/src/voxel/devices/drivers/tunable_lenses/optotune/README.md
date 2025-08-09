# Setting up the Optotune ICC4C SDK

The Voxel OptotuneICC4CTunableLens Driver requires the manufacturer's SDK to be installed on the system.
The Optotune ICC4C SDK is available for download under the SDKs here <https://www.optotune.com/software-center>.
**Quick Link:** [Download v2.0.4922](https://archive.optotune.com/ICC-4C_PythonSDK_2.0.4922.zip)

As of the time of writing, the SDK is not available as a pip installable package on pypi.
The SDK is available for Windows, Linux, and MacOS. The SDK is available in C++, Python, and LabVIEW.

After downloading the zip file, extract the contents and navigate to the extraced directory and locate the .whl file.
The Python SDK can be installed using the following command:

```bash
cd <path_to_downloaded_sdk>
pip install <wheel_file>
```

Note: You might need to install both the OptoKummenberg and OptoICC libraries.

```bash
cd ICC-4C_PythonSDK_2.0.4922
pip install .\optoKummenberg-1.0.4894-py3-none-any.whl .\optoICC-2.0.4922-py3-none-any.whl

```
