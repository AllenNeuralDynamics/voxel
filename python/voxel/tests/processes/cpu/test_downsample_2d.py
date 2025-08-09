import numpy
import time

from voxel.utils.processing.cpu.downsample_2d import DownSample2D

# tensorstore
image = numpy.zeros((14192, 10640), dtype="uint16")
print(f"original image size: {image.shape}")
start_time = time.time()
cpu_binning = DownSample2D(binning=2)
binned_image = cpu_binning.run(image)
end_time = time.time()
run_time = end_time - start_time
print(f"downsampled image size: {binned_image.shape}")
print(f"run time = {run_time} [sec]")

from voxel.utils.processing.cpu.tensorstore.downsample_2d import DownSample2D

# tensorstore
image = numpy.zeros((14192, 10640), dtype="uint16")
print(f"original image size: {image.shape}")
start_time = time.time()
tensorstore_binning = DownSample2D(binning=2)
binned_image = tensorstore_binning.run(image)
end_time = time.time()
run_time = end_time - start_time
print(f"downsampled image size: {binned_image.shape}")
print(f"run time = {run_time} [sec]")
