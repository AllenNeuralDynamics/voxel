import numpy
import tifffile
import os
import shutil
import time
from pathlib import Path
from voxel.processes.file_transfer.rsync import FileTransfer

temp_dir = Path('temp')
temp_filename = 'temp.tiff'
# create a dummy file
image = numpy.random.randint(low=128, high=256, size=(256, 2048, 2048), dtype='uint16')
tifffile.imwrite(temp_filename, image)
if not os.path.exists(temp_dir):
	os.mkdir(temp_dir)
current_dir = Path(os.getcwd())

transfer = FileTransfer(external_directory=f'{current_dir / temp_dir}')
transfer.filename = temp_filename
transfer.local_directory = current_dir
transfer.start()
while transfer.signal_progress_percent < 100.0:
	print(transfer.signal_progress_percent)
	time.sleep(1)
print(transfer.signal_progress_percent)
# delete external directory and contents
shutil.rmtree(temp_dir)