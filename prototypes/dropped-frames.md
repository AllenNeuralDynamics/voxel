# Dropped frames in camera drivers

Written on 2026-11-20 as a follow-up. Nothing here is built.

## What it is

A camera driver can lose a frame before the controller grabs it: the camera's or the frame grabber's buffer
overflows, or the transport skips a frame. Each driver reports this in `StreamInfo.dropped_frames`
(`base.py`), streamed through `stream_info` (`area.py`). Nothing reads it today.

This is not the same as a writer drop. The writer drops whole batches when every buffer is busy, on purpose, and
reports them as frame ranges (`writer.dropped`, `Image.dropped` in the record).

## What each driver reports today

| Driver | Source | Meaning |
| --- | --- | --- |
| pco (`drivers/src/vxl_drivers/cameras/pco.py`) | `bFIFOOverflow` in the recorder status | 0 or 1: a flag that an overflow happened, not a count |
| ximea (`.../ximea.py`) | `XI_CNT_SEL_API_SKIPPED_FRAMES` counter | a count; when it resets is not checked |
| egrabber (`.../egrabber.py`) | `STREAM_INFO_NUM_UNDERRUN` | buffer underruns of the stream |
| Hamamatsu (`.../dcam/hamamatsu.py`) | worked out inside `stream_info` | an estimate, updated only when the stream is read, reset in `_start` |
| simulated | always 0 | |

So the numbers cannot be compared between drivers, and some cannot be trusted as counts.

## What already catches a driver drop

A lost frame means the camera grabs fewer frames than its batch asked for. Its last grab waits for a trigger that
never comes, times out, and the batch fails; the record then fails the visit with `acquisition.frames_missing`.
So a driver drop is not silent. What is missing is the reason: the record says frames are missing, not that the
driver dropped them.

## To do

1. Agree 1 rule for every driver: `dropped_frames` counts the frames lost since the last `start()`, and is 0 after
   it.
2. Fix each driver to that rule: pco needs a real count (or `None` when the hardware only gives a flag), ximea needs
   its counter read at `start()` and subtracted, Hamamatsu needs a count that does not depend on how often the
   stream is read.
3. Then the acquisition reads it at the end of each batch and keeps it in the record as a diagnostic next to the
   missing frames.
