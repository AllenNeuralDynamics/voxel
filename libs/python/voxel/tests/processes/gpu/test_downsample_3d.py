import numpy
import time

from voxel.utils.processing.gpu.gputools.downsample_3d import DownSample3D

# gputools opencl
image = numpy.zeros((128, 2048, 2048), dtype="uint16")
print(f"original image size: {image.shape}")
start_time = time.time()
gpu_binning = DownSample3D(binning=2)
binned_image = gpu_binning.run(image)
end_time = time.time()
run_time = end_time - start_time
print(f"downsampled image size: {binned_image.shape}")
print(f"run time = {run_time} [sec]")

from voxel.utils.processing.gpu.cucim.downsample_3d import DownSample3D

# cucim cuda
image = numpy.zeros((128, 2048, 2048), dtype="uint16")
print(f"original image size: {image.shape}")
start_time = time.time()
gpu_binning = DownSample3D(binning=2)
binned_image = gpu_binning.run(image)
end_time = time.time()
run_time = end_time - start_time
print(f"downsampled image size: {binned_image.shape}")
print(f"run time = {run_time} [sec]")

from voxel.utils.processing.gpu.clesperanto.downsample_3d import DownSample3D

# pyclesperanto
image = numpy.zeros((128, 2048, 2048), dtype="uint16")
print(f"original image size: {image.shape}")
start_time = time.time()
gpu_binning = DownSample3D(binning=2)
binned_image = gpu_binning.run(image)
end_time = time.time()
run_time = end_time - start_time
print(f"downsampled image size: {binned_image.shape}")
print(f"run time = {run_time} [sec]")
