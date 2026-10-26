# Device properties

`rigup.device.props` provides Python property decorators that constrain values and carry metadata to clients.
Device code reads and assigns properties normally; handles and UIs receive the value together with its current
bounds or choices.

## Defining a property

Use a constraint decorator in place of `@property`, with `@describe` on the getter to expose it through rigup:

```python
from rigup import Device, describe
from rigup.device.props import numeric


class Light(Device):
    __DEVICE_TYPE__ = "light"

    def __init__(self, uid: str) -> None:
        super().__init__(uid)
        self._power = 0.0

    @numeric(minimum=0.0, maximum=100.0, step=0.1)
    @describe(label="Power", units="mW")
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        self._power = value
```

The descriptor applies constraints before calling the setter. Omit the setter for a read-only property.
For unconstrained values, including booleans and structured data, use ordinary `@property` with `@describe`.

## Choosing constraints

| Decorator | Value type | Constraints |
| --- | --- | --- |
| `numeric(...)` | `float` | `minimum`, `maximum`, `step`, or `options` |
| `numeric_int(...)` | `int` | `minimum`, `maximum`, `step`, or `options` |
| `enumerated(options=...)` | `str` | Explicit choices |

Numeric properties support two forms:

```python
numeric(minimum=0.0, maximum=100.0, step=0.1)
numeric(options=[0.0, 25.5, 100.0])
numeric_int(options=[1, 2, 4, 8])
```

Range constraints are individually optional. Values are clamped to the minimum, snapped to the step grid, then
clamped to the maximum. The grid starts at the minimum, or zero when omitted; ties round upward. The maximum
can therefore be accepted even when it falls off the grid.

Numeric options require membership in the supplied choices: unsupported values raise `ValueError` before the
setter runs. An empty sequence permits no values. Combining `options` with any range constraint is rejected by
static checking and raises `TypeError` when the decorator is created.

Bounds, step, and options can also be callbacks taking the device instance, such as
`numeric_int(options=lambda self: self.available_binnings)`. They are resolved on each read or write. Reads
apply constraints too: numeric ranges normalize the returned value, while choices validate it.

For string choices, `enumerated` logs a warning and leaves the value unchanged on unsupported writes with
nonempty options. Unsupported reads raise `ValueError`.

## Values and client metadata

Local reads return subclasses of the underlying Python type: `NumericFloat`, `NumericInt`, or
`EnumeratedString`. These carry constraint attributes and expose `to_property_model()`. Casting to a plain
`float`, `int`, or `str` discards that metadata.

`PropertyModel.from_value()` converts these wrappers, ordinary values, enums, and structured data to the common
client representation. Controllers use it for reads and write readbacks; handles, RPC, and property streams
preserve the resulting model.

- `kind` describes the value type: `float`, `integer`, `string`, `bool`, or `generic`.
- `value` is the observed value.
- Non-null `options` means discrete choices, including for floats and integers. Check `options is not None`;
  an empty list does not mean an unconstrained value.
- Otherwise, numeric controls use `minimum`, `maximum`, and `step`, each of which may be null.

Python clients can retrieve the complete observation:

```python
model = await handle.props.get_model("power")
```

The same metadata is available in `handle.props.cache` and a typed property's `.model`. Scalar helpers such as
`get_value()` and typed property `.value`/`.get()` return only the value.

Constraints can change without the value changing. Subscribe to `handle.props` for complete observations;
typed property subscriptions notify only when the parsed value changes. Labels, units, and access information
come separately from `DeviceInterface`.
