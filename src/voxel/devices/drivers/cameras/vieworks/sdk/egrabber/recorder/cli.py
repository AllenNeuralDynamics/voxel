import ctypes as ct
import math
import os
import re
import shutil
import signal
import sys
import threading
import time
import traceback
from datetime import datetime

import click

from . import *
from ..egentl import EGenTL
from ..egrabber import *


# Override some of click's default behavior
class Group(click.Group):
    def get_help_option(self, ctx):
        h = super(Group, self).get_help_option(ctx)
        if h:
            h.help = "display help and exit"
        return h

    def command(self, *args, **kwargs):
        class Command(click.Command):
            def get_help_option(self, ctx):
                h = super(Command, self).get_help_option(ctx)
                if h:
                    h.help = "display help and exit"
                return h

        return super(Group, self).command(cls=Command, *args, **kwargs)


# Container
class Container(object):
    def __init__(self, lib=None, path=None):
        self.lib = RecorderLibrary(lib)
        self.path = os.path.abspath(path or ".")

    def open(self, mode=RECORDER_OPEN_MODE_READ, close_mode=RECORDER_CLOSE_MODE_KEEP, path_suffix=None):
        return self.lib.open_recorder(
            os.path.join(self.path, path_suffix) if path_suffix else self.path, mode, close_mode=close_mode
        )

    def set(self, parameter, value):
        self.lib._set(parameter, value)


pass_container = click.make_pass_decorator(Container)


# Command line interface root
@click.group(cls=Group)
@click.option("--lib", default=None, type=click.Path(exists=True, dir_okay=False), hidden=True)
@click.option("-C", "--container", default=".", type=click.Path(file_okay=False), help="path to container")
@click.pass_context
def cli(ctx, lib, container):
    ctx.obj = Container(lib, container)


# status
@cli.command(short_help="show basic information")
@pass_container
def status(container):
    """Show information related to the container."""

    def show_size(n):
        if n > 1e9:
            return "%i (%.1f GB)" % (n, n / 1e9)
        elif n > 1e6:
            return "%i (%.1f MB)" % (n, n / 1e6)
        else:
            return "%i (%.1f kB)" % (n, n / 1e3)

    with container.open() as recorder:
        click.echo("Container path:                  %s" % container.path)
        click.echo("Container size:                  %s" % show_size(recorder.get(RECORDER_PARAMETER_CONTAINER_SIZE)))
        click.echo("Number of chapters in container: %i" % recorder.get(RECORDER_PARAMETER_CHAPTER_COUNT))
        click.echo("Number of records in container:  %i" % recorder.get(RECORDER_PARAMETER_RECORD_COUNT))
        click.echo(
            "Remaining space in container:    %s"
            % show_size(recorder.get(RECORDER_PARAMETER_REMAINING_SPACE_IN_CONTAINER))
        )
        click.echo(
            "Remaining space on device:       %s"
            % show_size(recorder.get(RECORDER_PARAMETER_REMAINING_SPACE_ON_DEVICE))
        )
        click.echo("Buffer optimal alignment:        %i" % recorder.get(RECORDER_PARAMETER_BUFFER_OPTIMAL_ALIGNMENT))
        click.echo("Database version:                %s" % recorder.get(RECORDER_PARAMETER_DATABASE_VERSION))
        click.echo("eGrabber Recorder version:       %s" % recorder.get(RECORDER_PARAMETER_VERSION))


def asUTC(utc):
    d = datetime.utcfromtimestamp(utc)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f UTC")


# log
@cli.command(short_help="show container records")
@pass_container
def log(container):
    """Show information related to records written in the container."""
    with container.open() as recorder:
        record_count = recorder.get(RECORDER_PARAMETER_RECORD_COUNT)

        def show_info():
            yield "Chapters\n"
            yield "--------\n"
            for index in range(len(recorder.chapters)):
                chapter = recorder.chapters[index]
                lines = [] if index == 0 else ["\n"]
                lines += ["  index:             %i\n" % index]
                if chapter:
                    lines += ["  name:              %s\n" % chapter.name]
                    lines += ["  user info:         %s\n" % chapter.user_info]
                    lines += ["  base record index: %i\n" % chapter.base_record_index]
                    lines += ["  number of records: %i\n" % chapter.record_count]
                    lines += ["  timestamp:         %.9f\n" % (chapter.timestamp_ns * 1e-9)]
                    lines += [
                        "  utc:               %.9f (%s)\n" % (chapter.utc_ns * 1e-9, asUTC(chapter.utc_ns * 1e-9))
                    ]
                else:
                    lines += ["  <not available>\n"]
                yield "".join(lines)
            yield "\n"
            yield "Records\n"
            yield "-------\n"
            for index in range(record_count):
                recorder.set(RECORDER_PARAMETER_RECORD_INDEX, index)
                info = recorder.read_info()
                lines = [] if index == 0 else ["\n"]
                lines += ["  index:          %i\n" % index]
                lines += ["  size:           %i\n" % info.size]
                lines += ["  pitch:          %i\n" % info.pitch]
                lines += ["  width:          %i\n" % info.width]
                lines += ["  height:         %i\n" % info.height]
                lines += ["  pixel format:   0x%08x (%s)\n" % (info.pixelformat, get_pixel_format(info.pixelformat))]
                lines += ["  part count:     %i\n" % info.partCount]
                lines += ["  timestamp:      %.9f\n" % (info.timestamp * 1e-9)]
                lines += ["  utc:            %.9f (%s)\n" % (info.utc * 1e-9, asUTC(info.utc * 1e-9))]
                lines += ["  user data:      %i\n" % info.userdata]
                lines += ["  chapter index:  %i\n" % info.chapterIndex]
                yield "".join(lines)

        click.echo_via_pager(show_info)


# export
@cli.command(short_help="export images")
@click.option(
    "-o",
    "--output",
    default="@n.tiff",
    type=click.Path(),
    show_default=True,
    help="destination path (`@n` patterns will be replaced by `record index - start index`)",
)
@click.option(
    "-i",
    "--index",
    default=0,
    type=click.INT,
    show_default=True,
    help="start index relative to the beginning of the container (or chapter if defined); "
    "negative values are relative to the end of the container (or chapter if defined)",
)
@click.option("-n", "--count", default=None, type=click.INT, help="number of records to export")
@click.option("-f", "--format", default=None, metavar="FORMAT", help="export pixel format")
@click.option(
    "-c",
    "--chapter",
    default=None,
    metavar="CHAPTER",
    help="start from a specified chapter (identified by name or index); "
    "the start index (-i) becomes relative to that chapter",
)
@pass_container
def export(container, output, index, count, format, chapter):
    """Export images from the container."""
    with container.open() as recorder:
        if chapter is not None:
            try:
                found_chapter = recorder.chapters[int(chapter)]
            except ValueError:
                found_chapter = recorder.find_chapter_by_name(chapter)
            except Exception:
                found_chapter = None
            if not found_chapter:
                raise click.ClickException("Chapter not found: %s" % chapter)
            record_count = found_chapter.record_count
        else:
            found_chapter = None
            record_count = recorder.get(RECORDER_PARAMETER_RECORD_COUNT)
        if not index:
            index = 0
        if index < 0 and record_count + index >= 0:
            index = record_count + index
        if index < 0 or index >= record_count:
            raise click.ClickException("Index out of bounds")
        if count is None:
            count = record_count - index
        if found_chapter:
            index += found_chapter.base_record_index
        recorder.set(RECORDER_PARAMETER_RECORD_INDEX, index)
        if looks_like_dir(output):
            output = os.path.join(output, "@n.tiff")
        if format is None:
            format = 0
        else:
            try:
                format = int(format)
            except ValueError:
                format = get_pixel_format_value(format)
        makedirs(os.path.dirname(output))
        with click.progressbar(length=count, label="Exporting images") as bar:
            bar.already_exported = 0  # using bar.pos would be simpler, but it's not part of the documented API

            def on_progress(progress):
                index = progress.index + 1
                inc, bar.already_exported = index - bar.already_exported, index
                bar.update(inc)

            h = signal.signal(signal.SIGINT, lambda n, f: recorder.abort())  # ok because we're on the main thread
            try:
                recorder.export(output, count, export_pixel_format=format, on_progress=on_progress)
            finally:
                signal.signal(signal.SIGINT, h)


def read_size(s):
    unit = {"": 1, "B": 1, "KB": 1000, "MB": 1000 * 1000, "GB": 1000 * 1000 * 1000, "TB": 1000 * 1000 * 1000 * 1000}
    m = re.match("^(\d+)(B|KB|MB|GB|TB)?$", "".join(s.split()), re.IGNORECASE)
    if m:
        size = int(m[1])
        if m[2]:
            size *= unit[m[2].upper()]
        return size
    else:
        raise click.ClickException("Invalid size: %s" % s)


def makedirs(path):
    try:
        os.makedirs(path)
    except Exception:
        pass


def looks_like_dir(path):
    if os.path.isdir(path):
        return True
    _, tail = os.path.split(path)
    if not tail:
        return True
    _, ext = os.path.splitext(tail)
    if not ext:
        return True
    return False


# create
@cli.command(short_help="create a new container")
@click.option(
    "--size",
    default="0",
    metavar="SIZE",
    show_default=True,
    help="size of the new container (SIZE can be suffixed by one of the following: B, kB, MB, GB, TB)",
)
@pass_container
def create(container, size):
    """Create a new container."""
    try:
        with container.open():
            pass
        raise click.ClickException("A container already exists in %s" % container.path)
    except RecorderError as err:
        pass
    makedirs(container.path)
    with container.open(RECORDER_OPEN_MODE_WRITE, RECORDER_CLOSE_MODE_KEEP) as recorder:
        size = read_size(size)
        recorder.set(RECORDER_PARAMETER_CONTAINER_SIZE, size)


# resize
@cli.command(short_help="resize the container")
@click.option(
    "--size",
    default=None,
    metavar="SIZE",
    help="new container size (SIZE can be suffixed by one of the following: B, kB, MB, GB, TB)",
)
@click.option("--dont-trim-chapters", default=False, flag_value=True, help="keep trailing empty chapters")
@pass_container
def resize(container, size, dont_trim_chapters):
    """Resize the container.

    If --size is omitted, the container is trimmed (i.e., the container is
    reduced to the smallest size that fits the container contents).
    """
    close_mode = RECORDER_CLOSE_MODE_TRIM if size is None else RECORDER_CLOSE_MODE_KEEP
    close_mode += RECORDER_CLOSE_MODE_DONT_TRIM_CHAPTERS if dont_trim_chapters else 0
    with container.open(RECORDER_OPEN_MODE_APPEND, close_mode) as recorder:
        if size is not None:
            size = read_size(size)
            recorder.set(RECORDER_PARAMETER_CONTAINER_SIZE, size)


# record
@cli.command(short_help="record images")
@click.option("--cti", default=None, metavar="PATH", help="path to the GenTL producer library")
@click.option("--if", "iface", default=0, metavar="ID", help="interface id", show_default=True)
@click.option("--dev", default=0, metavar="ID", help="device id", show_default=True)
@click.option("--ds", default=0, metavar="ID", help="data stream id", show_default=True)
@click.option("-n", "--count", default=None, type=click.INT, help="number of images to record")
@click.option("--buffers", default=3, type=click.INT, help="number of buffers to use", show_default=True)
@click.option("--setup", default=None, metavar="SCRIPT", help="script to execute before starting the data stream")
@click.option("-c", "--chapter", default="", metavar="CHAPTER", help="optional chapter name")
@click.option("--chapter-info", default="", metavar="INFO", help="optional chapter user information")
@click.option(
    "--trim-container", default=False, flag_value=True, help="trim the container size when closing the recorder"
)
@click.option("--dont-trim-chapters", default=False, flag_value=True, help="keep trailing empty chapters")
@pass_container
def record(
    container, cti, iface, dev, ds, count, buffers, setup, chapter, chapter_info, trim_container, dont_trim_chapters
):
    """Record images in the container."""
    close_mode = RECORDER_CLOSE_MODE_TRIM if trim_container else RECORDER_CLOSE_MODE_KEEP
    close_mode += RECORDER_CLOSE_MODE_DONT_TRIM_CHAPTERS if dont_trim_chapters else 0
    with container.open(RECORDER_OPEN_MODE_APPEND, close_mode) as recorder:
        gentl = EGenTL(cti)
        grabber = EGrabber(gentl, interface=iface, device=dev, data_stream=ds)
        alignment = recorder.get(RECORDER_PARAMETER_BUFFER_OPTIMAL_ALIGNMENT)
        grabber.stream.set("BufferAllocationAlignmentControl", "Enable")
        grabber.stream.set("BufferAllocationAlignment", alignment)
        if setup:
            grabber.run_script(setup)
        grabber.realloc_buffers(buffers)
        if count is None:
            remaining_space = recorder.get(RECORDER_PARAMETER_REMAINING_SPACE_IN_CONTAINER)
            count = int(remaining_space / grabber.get_payload_size())
            if not count:
                raise DataFileFull
        if count:
            grabber.start(count)
        recorder.start_chapter(chapter, chapter_info)
        with click.progressbar(range(count), label="Recording images") as bar:
            for n in bar:
                with Buffer(grabber) as buffer:
                    info = RECORDER_BUFFER_INFO()
                    info.size = buffer.get_info(BUFFER_INFO_SIZE, INFO_DATATYPE_SIZET)
                    info.pitch = buffer.get_info(BUFFER_INFO_CUSTOM_LINE_PITCH, INFO_DATATYPE_SIZET)
                    info.width = buffer.get_info(BUFFER_INFO_WIDTH, INFO_DATATYPE_SIZET)
                    info.height = buffer.get_info(BUFFER_INFO_DELIVERED_IMAGEHEIGHT, INFO_DATATYPE_SIZET)
                    info.pixelformat = buffer.get_info(BUFFER_INFO_PIXELFORMAT, INFO_DATATYPE_UINT64)
                    info.partCount = buffer.get_info(BUFFER_INFO_CUSTOM_NUM_PARTS, INFO_DATATYPE_SIZET)
                    info.partSize = buffer.get_info(BUFFER_INFO_CUSTOM_PART_SIZE, INFO_DATATYPE_SIZET)
                    info.timestamp = buffer.get_info(BUFFER_INFO_TIMESTAMP_NS, INFO_DATATYPE_UINT64)
                    info.userdata = 0
                    base = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR)
                    recorder.write(info, to_cchar_array(base, info.size))


class RandomBytesBuffer:
    def __init__(self, size, alignment):
        buffer_size = size + alignment - 1
        self._buffer = (ct.c_char * buffer_size).from_buffer(bytearray(os.urandom(buffer_size)))
        address = ct.addressof(self._buffer)
        offset = 0
        if address % alignment:
            offset = alignment - (address % alignment)
        self._aligned = ct.c_void_p(address + offset)

    def aligned(self):
        return self._aligned


class Perfs:
    def __init__(self):
        self.t_start = None
        self.t_end = None
        self.written = 0
        self.mbps = []

    def is_running(self):
        return self.t_start is not None and self.t_end is None

    def start(self):
        self.__init__()
        self.t_start = datetime.now()

    def stop(self):
        self.t_end = datetime.now()

    def add_bytes_written(self, n):
        self.written += n
        dt = math.floor((datetime.now() - self.t_start).total_seconds())
        for pad in range(len(self.mbps), dt + 1):
            self.mbps.append(0)
        self.mbps[dt] += n / 1e6

    def get_bytes_written(self):
        return self.written

    def get_duration(self):
        if self.t_start:
            if self.t_end:
                return (self.t_end - self.t_start).total_seconds()
            else:
                return (datetime.now() - self.t_start).total_seconds()
        return 0

    def get_MBps(self, period=None):
        if period and period < len(self.mbps):
            return sum(self.mbps[-period - 1 : -1]) / period
        duration = self.get_duration()
        if duration:
            return self.written / duration / 1e6
        return 0


class BenchmarkRecorderStats:
    def __init__(self, rix):
        self.rix = rix
        self.start_write_time = None
        self.end_write_time = None
        self.bytes_written = 0
        self.write_duration = 0
        self.open_duration = 0
        self.close_duration = 0
        self.bytes_written_per_second_count = 0
        self.bytes_written_per_second_min = None
        self.bytes_written_per_second_max = None
        self.bytes_written_per_second_sum = 0
        self.open_count = 0
        self.open_duration_min = None
        self.open_duration_max = None
        self.open_duration_sum = 0
        self.close_count = 0
        self.close_duration_min = None
        self.close_duration_max = None
        self.close_duration_sum = 0

    def set_open_duration(self, d):
        self.open_count += 1
        self.open_duration = d
        self.open_duration_sum += d
        self.open_duration_min = d if self.open_duration_min is None else min(self.open_duration_min, d)
        self.open_duration_max = d if self.open_duration_max is None else max(self.open_duration_max, d)

    def set_close_duration(self, d, full):
        self.close_count += 1
        self.close_duration = d
        self.close_duration_sum += d
        self.close_duration_min = d if self.close_duration_min is None else min(self.close_duration_min, d)
        self.close_duration_max = d if self.close_duration_max is None else max(self.close_duration_max, d)
        # write_duration
        if full and self.start_write_time and self.end_write_time:
            d = (self.end_write_time - self.start_write_time).total_seconds()
            self.write_duration = d
            if d:
                bytes_written_per_second = self.bytes_written / d
                self.bytes_written_per_second_count += 1
                self.bytes_written_per_second_min = (
                    bytes_written_per_second
                    if self.bytes_written_per_second_min is None
                    else min(self.bytes_written_per_second_min, bytes_written_per_second)
                )
                self.bytes_written_per_second_max = (
                    bytes_written_per_second
                    if self.bytes_written_per_second_max is None
                    else max(self.bytes_written_per_second_max, bytes_written_per_second)
                )
                self.bytes_written_per_second_sum += bytes_written_per_second

    def set_start_write_time(self, t):
        if self.start_write_time is None:
            self.start_write_time = t

    def set_end_write_time(self, t):
        self.end_write_time = t

    def add_bytes_written(self, n):
        self.bytes_written += n

    def get_bytes_written_per_second(self, include_open=False, include_close=False):
        if self.write_duration:
            d = self.write_duration
            d += self.open_duration if include_open else 0
            d += self.close_duration if include_close else 0
            return self.bytes_written / d
        else:
            return None

    def reset(self):
        self.start_write_time = None
        self.end_write_time = None
        self.bytes_written = 0
        self.write_duration = 0
        self.open_duration = 0
        self.close_duration = 0


class BenchmarkStats:
    def __init__(self):
        self.lock = threading.Lock()
        self.megabytes_written_per_second = []
        self.megabytes_written_per_second_from_open_to_close = []
        self.open_durations = []
        self.close_durations = []

    def push(self, recorderStats):
        if recorderStats.write_duration:
            with self.lock:
                self.megabytes_written_per_second.append(
                    recorderStats.get_bytes_written_per_second(False, False) / 1000000
                )
                self.megabytes_written_per_second_from_open_to_close.append(
                    recorderStats.get_bytes_written_per_second(True, True) / 1000000
                )
                self.open_durations.append(recorderStats.open_duration)
                self.close_durations.append(recorderStats.close_duration)

    def snaphot(self):
        s = BenchmarkStats()
        with self.lock:
            s.megabytes_written_per_second += self.megabytes_written_per_second
            s.megabytes_written_per_second_from_open_to_close += self.megabytes_written_per_second_from_open_to_close
            s.open_durations += self.open_durations
            s.close_durations += self.close_durations
            return s


# benchmark
@cli.command(short_help="measure container write performance (creates several containers)")
@click.option(
    "--size",
    default="1GB",
    metavar="SIZE",
    show_default=True,
    help="size of one container (SIZE can be suffixed by one of the following: B, kB, MB, GB, TB)",
)
@click.option("--container-count", default=1, show_default=True, type=click.INT, help="number of containers to create")
@click.option("--buffer-count", default=1000, show_default=True, type=click.INT, help="number of allocated buffers")
@click.option("--buffer-size", default=1920 * 1080, show_default=True, type=click.INT, help="size of one buffer")
@click.option(
    "--warmup", default=20, show_default=True, type=click.INT, help="warmup duration (seconds) excluded from stats"
)
@click.option("--plot", default=False, flag_value=True, type=click.BOOL, help="plot live data")
@click.option("--verbose", default=False, flag_value=True, help="enable verbose output")
@click.option("--reuse-existing", default=False, flag_value=True, help="reuse existing containers")
@pass_container
def benchmark(container, size, container_count, buffer_count, buffer_size, warmup, plot, verbose, reuse_existing):
    """Measure container write performance."""
    txt_size = size
    size = read_size(txt_size)
    recorders = [None for _ in range(container_count)]
    suffixes = ["%d" % ix for ix in range(container_count)]
    stats = [BenchmarkRecorderStats(rix) for rix in range(container_count)]
    closing = [False for _ in range(container_count)]
    stopping = [False]
    echoLock = threading.Lock()
    benchmarkStats = BenchmarkStats()
    perfs = Perfs()

    def log(txt):
        if verbose:
            with echoLock:
                click.echo(txt)

    def open_recorder(rix):
        dt = datetime.now()
        r = container.open(RECORDER_OPEN_MODE_WRITE, RECORDER_CLOSE_MODE_KEEP, suffixes[rix])
        r.set(RECORDER_PARAMETER_CONTAINER_SIZE, size)
        stats[rix].set_open_duration((datetime.now() - dt).total_seconds())
        log("Container[%d] opened in %.6f s" % (rix, stats[rix].open_duration))
        return r

    def close_recorder(r, rix, full):
        dt = datetime.now()
        r.close()
        stats[rix].set_close_duration((datetime.now() - dt).total_seconds(), full)
        log("Container[%d] closed in %.6f s" % (rix, stats[rix].close_duration))

    def thread_fn_close_recorder(r, rix, full, reopen):
        close_recorder(r, rix, full)
        bytes_per_second = stats[rix].get_bytes_written_per_second()
        if bytes_per_second:
            log("Container[%d] write rate %.3f MB/s" % (rix, bytes_per_second / 1000000))
        bytes_per_second = stats[rix].get_bytes_written_per_second(True, True)
        if bytes_per_second:
            log("Container[%d] write rate including open/close %.3f MB/s " % (rix, bytes_per_second / 1000000))
        benchmarkStats.push(stats[rix])
        stats[rix].reset()
        closing[rix] = False
        if reopen and not stopping[0]:
            recorders[rix] = open_recorder(rix)

    def close_recorder_in_background(rix, full, reopen):
        if recorders[rix] and not closing[rix]:
            r = recorders[rix]
            recorders[rix] = None
            closing[rix] = True
            t = threading.Thread(target=thread_fn_close_recorder, args=(r, rix, full, reopen))
            t.start()
        else:
            return None

    def thread_fn_benchmark(container_count, buffer_count, buffer_size, warmup):
        try:
            alignment = None
            for rix in range(container_count):
                path = os.path.join(container.path, suffixes[rix])
                log("Preparing container[%d] %s" % (rix, path))
                if not reuse_existing:
                    shutil.rmtree(path, ignore_errors=True)
                makedirs(path)
                r = open_recorder(rix)
                if alignment is None:
                    alignment = r.get(RECORDER_PARAMETER_BUFFER_OPTIMAL_ALIGNMENT)
                close_recorder(r, rix, False)
                stats[rix].reset()
            if buffer_size % alignment:
                buffer_size += alignment - (buffer_size % alignment)
            log("Allocating %d aligned buffers of %d bytes" % (buffer_count, buffer_size))
            buffers = [(ix + 1, RandomBytesBuffer(buffer_size, alignment)) for ix in range(buffer_count)]
            log("Each container can store %d buffers" % (size // buffer_size))
            info = RECORDER_BUFFER_INFO()
            info.size = buffer_size
            info.pitch = buffer_size
            info.width = buffer_size
            info.height = 1
            info.pixelformat = 0x01080001  # Mono8
            info.partCount = 1
            info.timestamp = 0
            info.userdata = 0
            full = [False for _ in range(container_count)]
            recorder_ix = 0
            log("Starting benchmark...")
            for rix in range(container_count):
                recorders[rix] = open_recorder(rix)
            if warmup > 0:
                log("Warmup... (%d sec)" % warmup)
            startTime = datetime.now()
            while True:
                if recorders[recorder_ix]:
                    if not full[recorder_ix] and not stopping[0]:
                        (ix, buffer) = buffers.pop(0)
                        buffers.append((ix, buffer))
                        try:
                            dt = datetime.now()
                            if not perfs.is_running() and (dt - startTime).total_seconds() > warmup:
                                if warmup > 0:
                                    log("Warmup complete")
                                perfs.start()
                            recorders[recorder_ix].write(info, buffer.aligned())
                            if perfs.is_running():
                                stats[recorder_ix].set_end_write_time(datetime.now())
                                perfs.add_bytes_written(buffer_size)
                                stats[recorder_ix].set_start_write_time(dt)
                                stats[recorder_ix].add_bytes_written(buffer_size)
                        except DataFileFull:
                            full[recorder_ix] = True
                            recorder_ix = (recorder_ix + 1) % container_count
                interrupting = stopping[0]
                for rix in range(container_count):
                    if full[rix] or interrupting:
                        close_recorder_in_background(rix, full[rix], not interrupting)
                        full[rix] = False
                if not any(closing) and interrupting:
                    break
        except:
            traceback.print_exc()
        finally:
            for recorder in recorders:
                if recorder:
                    recorder.close()
            perfs.stop()

    def interrupt_handler(signum, frame):
        log("[Interrupting...]")
        if not stopping[0]:
            stopping[0] = True

    hSIGINT = signal.signal(signal.SIGINT, interrupt_handler)
    try:
        benchmark = threading.Thread(
            target=thread_fn_benchmark, args=(container_count, buffer_count, buffer_size, warmup)
        )
        benchmark.start()
        if plot:
            import matplotlib.pyplot as plt

            fig, (ax_rate, ax_perfs) = plt.subplots(2)
            ax_duration = ax_rate.twinx()

            def handle_close(evt):
                interrupt_handler(None, None)

            fig.canvas.mpl_connect("close_event", handle_close)
            s = lambda n: "s" if n > 1 else ""
            warmingUp = True
            title = "Writes to %d container%s of %s" % (container_count, s(container_count), txt_size)
            ax_rate.set_title("Warmup: " + title + " (%d sec)" % warmup)
            ax_rate.set_ylabel("Data rate [MB/s]")
            ax_rate.set_xlabel("Step")
            ax_duration.set_ylabel("Duration [s]")
            (plot_write_rate,) = ax_rate.plot(
                [], [], label="Data rate (write only)", color="tab:blue", alpha=0.7, linestyle="dotted"
            )
            (plot_open_write_close_rate,) = ax_rate.plot(
                [], [], label="Data rate (open, write, close)", color="tab:blue"
            )
            (plot_open_durations,) = ax_duration.plot([], [], label="Open duration", color="tab:green", alpha=0.7)
            (plot_close_durations,) = ax_duration.plot([], [], label="Close duration", color="tab:red", alpha=0.7)
            plots = [plot_write_rate, plot_open_write_close_rate, plot_open_durations, plot_close_durations]
            plt.legend(plots, [p.get_label() for p in plots], loc=0)
            ax_perfs.set_xlabel("Time [s]")
            ax_perfs.set_ylabel("Data rate [MB/s]")
            (plot_perfs,) = ax_perfs.plot([], [], color="tab:blue", alpha=0.3, label="Write")
            (plot_perfs_last_minute,) = ax_perfs.plot(
                [], [], color="tab:blue", linestyle="dashed", label="Last minute average"
            )
            plots = [plot_perfs, plot_perfs_last_minute]
            ax_perfs.legend(plots, [p.get_label() for p in plots], loc=0)
            ann = None

            def update():
                nonlocal ann
                nonlocal warmingUp
                s = benchmarkStats.snaphot()
                N = len(s.megabytes_written_per_second)
                if warmingUp and perfs.is_running():
                    ax_rate.set_title(title)
                    warmingUp = False
                if N > 1:
                    plot_write_rate.set_data(range(N), s.megabytes_written_per_second)
                    plot_open_write_close_rate.set_data(range(N), s.megabytes_written_per_second_from_open_to_close)
                    plot_open_durations.set_data(range(N), s.open_durations)
                    plot_close_durations.set_data(range(N), s.close_durations)
                    ax_rate.set_xlim(0, N - 1)
                    ax_rate.set_ylim(
                        0,
                        max(max(s.megabytes_written_per_second), max(s.megabytes_written_per_second_from_open_to_close))
                        * 1.1,
                    )
                    ax_duration.set_ylim(0, math.ceil(max(max(s.open_durations), max(s.close_durations)) * 1.1))
                else:
                    ax_rate.set_xlim(0, 1)
                    ax_rate.set_ylim(0, 1)
                    ax_duration.set_ylim(0, 1)
                ax_rate.relim()
                ax_duration.relim()
                N = len(perfs.mbps)
                if N > 1:
                    plot_perfs.set_data(range(N - 1), perfs.mbps[: N - 1])
                    avg60 = perfs.get_MBps(60)
                    plot_perfs_last_minute.set_data([0, N - 1], [avg60, avg60])
                    if ann:
                        ann.remove()
                    ann = ax_perfs.annotate("%.3f" % avg60, xy=(N - 1, avg60), xycoords="data", color="tab:blue")
                    ax_perfs.set_xlim(0, N - 1)
                    ax_perfs.set_ylim(0, max(perfs.mbps))
                else:
                    ax_perfs.set_xlim(0, 1)
                    ax_perfs.set_ylim(0, 1)

            plt.tight_layout()
            fig.show()
            while not stopping[0]:
                update()
                fig.canvas.draw_idle()
                fig.canvas.start_event_loop(1.0)
            fig.savefig("benchmark-%s.png" % time.strftime("%Y%m%d-%H%M%S"))
        else:
            while not stopping[0]:
                time.sleep(1.0)
    except:
        traceback.print_exc()
        interrupt_handler(None, None)
    finally:
        benchmark.join()
        signal.signal(signal.SIGINT, hSIGINT)
    if verbose:
        hline = "-" * 70
        click.echo(hline)
        for rix in range(container_count):
            s = stats[rix]
            fmt = "{:<15}{:>10}{:>15}{:>15}{:>15}"
            na = "N/A"
            lines = [
                fmt.format("Container[%d]" % rix, "count", "min", "max", "avg"),
                fmt.format(
                    "open",
                    s.open_count,
                    na if s.open_duration_min is None else "%.6f" % s.open_duration_min,
                    na if s.open_duration_max is None else "%.6f" % s.open_duration_max,
                    na if s.open_count == 0 else "%.6f" % (s.open_duration_sum / s.open_count),
                ),
                fmt.format(
                    "close",
                    s.close_count,
                    na if s.close_duration_min is None else "%.6f" % s.close_duration_min,
                    na if s.close_duration_max is None else "%.6f" % s.close_duration_max,
                    na if s.close_count == 0 else "%.6f" % (s.close_duration_sum / s.close_count),
                ),
                fmt.format(
                    "write MB/s",
                    s.bytes_written_per_second_count,
                    (
                        na
                        if s.bytes_written_per_second_min is None
                        else "%.3f" % (s.bytes_written_per_second_min / 1000000)
                    ),
                    (
                        na
                        if s.bytes_written_per_second_max is None
                        else "%.3f" % (s.bytes_written_per_second_max / 1000000)
                    ),
                    (
                        na
                        if s.bytes_written_per_second_count == 0
                        else "%.3f" % (s.bytes_written_per_second_sum / s.bytes_written_per_second_count / 1000000)
                    ),
                ),
                hline,
            ]
            for line in lines:
                click.echo(line)
        click.echo(hline)
    click.echo(
        "Wrote %u bytes in %.6f s (%.3f MB/s)" % (perfs.get_bytes_written(), perfs.get_duration(), perfs.get_MBps())
    )
    click.echo("Average over last minute: %.3f MB/s" % perfs.get_MBps(60))


gentl = None


def get_pixel_format(pf):
    global gentl
    if not gentl:
        gentl = EGenTL()
    try:
        return gentl.image_get_pixel_format(pf)
    except Exception:
        return "unknown"


def get_pixel_format_value(pf):
    global gentl
    if not gentl:
        gentl = EGenTL()
    return gentl.image_get_pixel_format_value(pf)


def main():
    try:
        cli(prog_name="python -m egrabber.recorder", help_option_names=["-h", "--help"])
    except RecorderError as err:
        click.echo("Error: %s" % err)
        sys.exit(1)
    except Exception as err:
        click.echo("Exception: %s" % err)
        sys.exit(1)
