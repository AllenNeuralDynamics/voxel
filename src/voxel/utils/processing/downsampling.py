from abc import ABC, abstractmethod
from collections.abc import Iterator

# import cupy as cp
import jax.numpy as jnp
import numpy as np
import tensorstore as ts
import torch
from jax import device_put


class VoxelDownsampler[T](ABC):
    def __init__(self, levels: int = 1, base: int = 2, factors: list[int] | None = None) -> None:
        """
        Initialize the downsampler with the number of pyramid levels and a base factor.

        :param :levels (int): Number of pyramid levels (including the original level).
        :param :base (int): Downsampling base factor (default is 2).
        """

        if factors is not None:
            self.factors = factors
        elif levels < 1 or base < 1:
            raise ValueError("Levels and base must be greater than 0.")
        else:
            self.factors = self._compute_factors(levels=levels, base=base)

    def set_factors(self, levels: int, base: int = 2) -> None:
        """Set the downsampling factors by computing them from the base and levels."""
        self.factors = self._compute_factors(base=base, levels=levels)

    @staticmethod
    def _compute_factors(levels: int, base: int) -> list[int]:
        return [base**i for i in range(levels)]

    def downsample(self, data: np.ndarray) -> Iterator[T]:
        """Compute the pyramidal data as a 4D array.
        :param data: The input 3D data.
        :return: Iterator of downsampled data.
        """
        if data.ndim == 2:
            return self.downsample_2d(data)
        elif data.ndim == 3:
            return self.downsample_3d(data)
        else:
            raise ValueError("Data must be 2D or 3D.")

    @abstractmethod
    def downsample_2d(self, data: np.ndarray) -> Iterator[T]:
        """Compute the pyramidal data as a 3D array.
        :param data: The input 2D data.
        :return: Iterator of downsampled data.
        """
        pass

    @abstractmethod
    def downsample_3d(self, data: np.ndarray) -> Iterator[T]:
        """Compute the pyramidal data as a 4D array.
        :param data: The input 3D data.
        :return: Iterator of downsampled data.
        """
        return self.downsample(data)


class NumPyDownsampler(VoxelDownsampler):
    def downsample_2d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        for factor in self.factors:
            if factor == 1:
                yield data
            else:
                downsampled = (
                    data[::factor, ::factor]
                    + data[1::factor, ::factor]
                    + data[::factor, 1::factor]
                    + data[1::factor, 1::factor]
                ) // 4
                yield downsampled

    def downsample_3d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        for factor in self.factors:
            if factor == 1:
                yield data
            else:
                downsampled = (
                    data[::factor, ::factor, ::factor]
                    + data[1::factor, ::factor, ::factor]
                    + data[::factor, 1::factor, ::factor]
                    + data[::factor, ::factor, 1::factor]
                    + data[1::factor, 1::factor, ::factor]
                    + data[::factor, 1::factor, 1::factor]
                    + data[1::factor, ::factor, 1::factor]
                    + data[1::factor, 1::factor, 1::factor]
                ) // 8
                yield downsampled


class TensorStoreDownsampler(VoxelDownsampler[np.ndarray]):
    def _downsample(self, data: np.ndarray) -> Iterator[np.ndarray]:
        """
        Generalized downsampling logic for both 2D and 3D data.

        :param data: Input 2D or 3D NumPy array.
        :return: Downsampled data.
        """
        ts_data = ts.array(data)
        for factor in self.factors:
            if factor == 1:
                yield ts_data.read().result()
            else:
                factors = [factor] * data.ndim
                downsampled = (
                    ts.downsample(
                        ts_data,
                        downsample_factors=factors,
                        method="mean",
                    )
                    .read()
                    .result()
                )
                yield downsampled

    def downsample_2d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        """Downsample 2D data using TensorStore."""
        return self._downsample(data)

    def downsample_3d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        """Downsample 3D data using TensorStore."""
        return self._downsample(data)


class JaxDownsampler(VoxelDownsampler):
    def _downsample(self, data: jnp.ndarray, factor: int) -> np.ndarray:
        """
        Generalized downsampling logic for both 2D and 3D data.

        :param data: Input 2D or 3D JAX array.
        :param factor: Downsampling factor.
        :return: Downsampled data.
        """
        ndim = data.ndim

        # Compute the new shape for the downsampling
        cropped_shape = tuple(data.shape[i] - (data.shape[i] % factor) for i in range(ndim))
        reshaped_shape = tuple(cropped_shape[i] // factor for i in range(ndim))
        block_shape = tuple(factor for _ in range(ndim))

        # Crop the data to be divisible by the factor
        slices = tuple(slice(0, cropped_shape[i]) for i in range(ndim))
        cropped_data = data[slices]

        # Reshape and compute the mean over the block dimensions
        reshaped = cropped_data.reshape(
            *(reshaped_shape[i] for i in range(ndim)),
            *(block_shape[i] for i in range(ndim)),
        )
        downsampled = reshaped.mean(axis=tuple(range(ndim, 2 * ndim)))  # Mean over block axe
        downsampled.block_until_ready()
        return np.array(downsampled)

    def downsample_2d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        # Move data to JAX device
        data_jax = device_put(data)

        for factor in self.factors:
            if factor == 1:
                yield data_jax
            else:
                yield self._downsample(data_jax, factor)

    def downsample_3d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        # Move data to JAX device
        data_jax = device_put(data)

        for factor in self.factors:
            if factor == 1:
                yield data_jax
            else:
                yield self._downsample(data_jax, factor)


class TorchDownsampler(VoxelDownsampler):
    def __init__(self, levels: int = 1, base: int = 2, factors: list[int] | None = None, device: str = "cuda"):
        """
        Initialize the Torch-based downsampler with the number of pyramid levels and a base factor.

        :param levels: Number of pyramid levels (including the original level).
        :param base: Downsampling base factor (default is 2).
        :param factors: Custom downsampling factors.
        :param device: Device to use for computation ('cuda' or 'cpu').
        """
        super().__init__(levels=levels, base=base, factors=factors)
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")

    def _downsample(self, data: torch.Tensor, factor: int) -> torch.Tensor:
        """
        Generalized downsampling logic for both 2D and 3D data.

        :param data: Input 2D or 3D Torch tensor.
        :param factor: Downsampling factor.
        :return: Downsampled tensor.
        """
        ndim = data.ndim
        kernel_size = (factor,) * ndim
        stride = (factor,) * ndim

        # Apply average pooling for downsampling
        if ndim == 2:
            downsampled = torch.nn.functional.avg_pool2d(
                data.unsqueeze(0).unsqueeze(0),  # Add batch and channel dims
                kernel_size=kernel_size,
                stride=stride,
            ).squeeze()  # Remove batch and channel dims
        elif ndim == 3:
            downsampled = torch.nn.functional.avg_pool3d(
                data.unsqueeze(0).unsqueeze(0),  # Add batch and channel dims
                kernel_size=kernel_size,
                stride=stride,
            ).squeeze()  # Remove batch and channel dims
        else:
            raise ValueError("Data must be 2D or 3D.")

        return downsampled

    def downsample_2d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        """
        Downsample 2D data using Torch.

        :param data: Input 2D NumPy array.
        :return: Iterator of downsampled data as NumPy arrays.
        """
        data_torch = torch.tensor(data, device=self.device, dtype=torch.float32)

        for factor in self.factors:
            if factor == 1:
                yield data_torch.cpu().numpy()
            else:
                yield self._downsample(data_torch, factor).cpu().numpy()

    def downsample_3d(self, data: np.ndarray) -> Iterator[np.ndarray]:
        """
        Downsample 3D data using Torch.

        :param data: Input 3D NumPy array.
        :return: Iterator of downsampled data as NumPy arrays.
        """
        data_torch = torch.tensor(data, device=self.device, dtype=torch.float32)

        for factor in self.factors:
            if factor == 1:
                yield data_torch.cpu().numpy()
            else:
                yield self._downsample(data_torch, factor).cpu().numpy()


# class CuPyDownsampler(VoxelDownsampler):
#     def __init__(self, levels: int = 1, base: int = 2, factors: list[int] | None = None) -> None:
#         """
#         Initialize the downsampler with the number of pyramid levels and a base factor.

#         :param :levels (int): Number of pyramid levels (including the original level).
#         :param :base (int): Downsampling base factor (default is 2).
#         """
#         # Ensure that a GPU is available
#         if not cp.cuda.is_available():
#             raise ValueError("No GPU found. CuPy downsampling requires a GPU.")
#         super().__init__(levels, base, factors)

#     def _downsample(self, data: cp.ndarray, factor: int) -> cp.ndarray:
#         """
#         Generalized downsampling logic for both 2D and 3D data.

#         :param data: Input 2D or 3D CuPy array.
#         :param factor: Downsampling factor.
#         :return: Downsampled data.
#         """
#         ndim = data.ndim

#         # Compute new shape
#         cropped_shape = tuple(data.shape[i] - (data.shape[i] % factor) for i in range(ndim))
#         reshaped_shape = tuple(cropped_shape[i] // factor for i in range(ndim))
#         block_shape = tuple(factor for _ in range(ndim))

#         # Crop to make dimensions divisible by the factor
#         slices = tuple(slice(0, cropped_shape[i]) for i in range(ndim))
#         cropped_data = data[slices]

#         # Reshape into blocks and compute the mean over blocks
#         reshaped = cropped_data.reshape(
#             *(reshaped_shape[i] for i in range(ndim)),
#             *(block_shape[i] for i in range(ndim)),
#         )
#         downsampled = reshaped.mean(axis=tuple(range(ndim, 2 * ndim)))  # Mean over block axes
#         return downsampled

#     def downsample_2d(self, data: np.ndarray) -> Iterator[np.ndarray]:
#         # Transfer data to GPU
#         data_gpu = cp.array(data)

#         for factor in self.factors:
#             if factor == 1:
#                 yield cp.asnumpy(data_gpu)  # Transfer back to CPU
#             else:
#                 downsampled = self._downsample(data_gpu, factor)
#                 yield cp.asnumpy(downsampled)  # Transfer back to CPU

#     def downsample_3d(self, data: np.ndarray) -> Iterator[np.ndarray]:
#         # Transfer data to GPU
#         data_gpu = cp.array(data)

#         for factor in self.factors:
#             if factor == 1:
#                 yield cp.asnumpy(data_gpu)  # Transfer back to CPU
#             else:
#                 downsampled = self._downsample(data_gpu, factor)
#                 yield cp.asnumpy(downsampled)  # Transfer back to CPU


if __name__ == "__main__":
    import time

    from voxel.utils.frame_gen import CheckeredGenerator  # generate_checkered_batch

    start_gen = time.time()
    frames = CheckeredGenerator(height_px=12800, width_px=12800, initial_size=4).generate()
    frame = frames[0]
    print(f"Generated frames in {time.time() - start_gen:.6f} seconds")

    # Initialize the downsampler with 4 levels and a base factor of 2
    jax_downsampler = JaxDownsampler(levels=4, base=2)
    np_downsampler = NumPyDownsampler(levels=4, base=2)
    ts_downsampler = TensorStoreDownsampler(levels=4, base=2)
    # cp_downsampler = CuPyDownsampler(levels=4, base=2)
    torch_downsampler = TorchDownsampler(levels=4, base=2)

    def profile_downsampler(downsampler: VoxelDownsampler, frames) -> None:
        print(f"Using {downsampler.__class__.__name__}")

        start_time = time.time()
        pyramidal_data = downsampler.downsample(frames)

        print(f"Factors: {downsampler.factors}")

        for factor, level_data in zip(downsampler.factors, pyramidal_data):
            print(f"Factor: {factor}, Shape: {level_data.shape}")

        print(f"Total time: {time.time() - start_time:.6f} seconds")

    # profile_downsampler(cp_downsampler, frames)

    for downsampler in [jax_downsampler, torch_downsampler]:
        # downsampler.factors = [2]
        print()
        profile_downsampler(downsampler, frame)
