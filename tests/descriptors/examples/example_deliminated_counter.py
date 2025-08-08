from typing import Literal

from voxel.utils.descriptors.deliminated_property import deliminated_property

if __name__ == "__main__":

    class Temperature:
        def __init__(self):
            self._value: float = 24
            self.season: Literal["summer", "winter", "spring", "autumn"] = "summer"

        @deliminated_property(
            minimum=lambda self: self.min_celsius, maximum=lambda self: self.max_celsius, step=0.1, unit="°C"
        )
        def celsius(self) -> float:
            return self._value

        @celsius.setter
        def celsius(self, value: float) -> None:
            self._value = value

        @property
        def max_celsius(self) -> float:
            return 100 if self.season == "summer" else 75

        @property
        def min_celsius(self) -> float:
            return -10 if self.season == "winter" else 20

    class Counter:
        def __init__(self):
            self._value: int = 0

        @deliminated_property(minimum=0, maximum=100, step=1)
        def count(self) -> int:
            return self._value

        @count.setter
        def count(self, value) -> None:
            self._value = value

    def print_temperature(t: Temperature):
        print(f"Season is: {t.season}")
        print(f"Celsius step: {t.celsius.step}{t.celsius.unit}")
        print(f"Celsius min: {t.celsius.minimum}{t.celsius.unit}")
        print(f"Celsius max: {t.celsius.maximum}{t.celsius.unit}")
        print(f"Celsius val: {t.celsius}{t.celsius.unit}\n")

    def print_counter(c: Counter):
        print(f"Counter step: {c.count.step}{c.count.unit}")
        print(f"Counter min: {c.count.minimum}{c.count.unit}")
        print(f"Counter max: {c.count.maximum}{c.count.unit}")
        print(f"Counter val: {c.count}{c.count.unit}\n")

    # Test with float (Temperature)
    temp = Temperature()
    print("Initial temperature setting:")
    print_temperature(temp)

    temp.celsius = 30.5
    print("After setting temperature to 30.5°C:")
    print_temperature(temp)

    temp.celsius = 150  # This should be clamped to 100
    print("After attempting to set temperature to 150°C:")
    print_temperature(temp)

    # Test with int (Counter)
    counter = Counter()
    print("Initial counter setting:")
    print_counter(counter)

    counter.count = 50
    print("After setting counter to 50:")
    print_counter(counter)

    counter.count = 150  # This should be clamped to 100
    print("After attempting to set counter to 150:")
    print_counter(counter)

    counter.count = 75.7  # This should be rounded to 76 # type: ignore
    print("After attempting to set counter to 75.7:")
    print_counter(counter)
