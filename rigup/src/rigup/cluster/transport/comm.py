from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

_REQ_CMD_ = b"REQ"
_GET_CMD_ = b"GET"
_SET_CMD_ = b"SET"
_INT_CMD_ = b"INT"


class Proto(StrEnum):
    TCP = "tcp"
    IPC = "ipc"
    INPROC = "inproc"


class DeviceAddress(BaseModel, ABC):
    proto: Proto

    model_config = {"frozen": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_unique_addrs(self) -> "DeviceAddress":
        if self.rpc_addr == self.pub_addr:
            raise ValueError("rpc_addr and pub_addr must be different")
        return self

    @property
    @abstractmethod
    def rpc_addr(self) -> str: ...

    @property
    @abstractmethod
    def pub_addr(self) -> str: ...

    def __str__(self) -> str:
        return f"rpc_addr={self.rpc_addr} pub_addr={self.pub_addr}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(rpc_addr={self.rpc_addr}, pub_addr={self.pub_addr})"


class DeviceAddressTCP(DeviceAddress):
    proto: Proto = Field(default=Proto.TCP, frozen=True)
    host: str = Field(default="127.0.0.1", min_length=1)
    rpc: int = Field(..., ge=1, le=65535)
    pub: int = Field(..., ge=1, le=65535)

    @field_validator("host", mode="before")
    @classmethod
    def validate_host(cls, value: str) -> str:
        host = value.strip()
        if host.count(":") >= 2 and not host.startswith("[") and not host.endswith("]"):
            return f"[{host}]"
        return host

    @property
    def rpc_addr(self) -> str:
        return self._addr(self.rpc)

    @property
    def pub_addr(self) -> str:
        return self._addr(self.pub)

    def _addr(self, port: int) -> str:
        h = self.host
        if h.startswith("[") and "%" in h:
            # RFC 6874 encoding for zone IDs inside brackets
            inner = h[1:-1].replace("%", "%25")
            h = f"[{inner}]"
        return f"{self.proto.value}://{h}:{port}"

    def as_loopback(self) -> "DeviceAddressTCP":
        return DeviceAddressTCP(host="127.0.0.1", rpc=self.rpc, pub=self.pub)

    def as_open(self) -> "DeviceAddressTCP":
        return DeviceAddressTCP(host="0.0.0.0", rpc=self.rpc, pub=self.pub)  # noqa: S104 :: allow bind all


class DeviceAddressIPC(DeviceAddress):
    proto: Proto = Field(default=Proto.IPC, frozen=True)
    rep: str = Field(..., min_length=1)
    pub: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"{self.proto.value}://{self.rep}"

    @property
    def pub_addr(self) -> str:
        return f"{self.proto.value}://{self.pub}"


class DeviceAddressINPROC(DeviceAddress):
    proto: Proto = Field(default=Proto.INPROC, frozen=True)
    rep: str = Field(..., min_length=1)
    pub: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"{self.proto.value}://{self.rep}"

    @property
    def pub_addr(self) -> str:
        return f"{self.proto.value}://{self.pub}"
