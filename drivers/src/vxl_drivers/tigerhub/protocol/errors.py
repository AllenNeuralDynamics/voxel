from vxl_drivers.tigerhub.model import Reply


class ASIDecodeError(RuntimeError):
    def __init__(self, operation: str, reply: Reply, msg: str | None = None):
        self.operation = operation
        self.reply = reply
        super().__init__(msg or f"Error decoding {operation}: {reply}")


class ASINoReplyError(ASIDecodeError):
    """The controller sent nothing back — the serial read returned empty before its timeout.

    Subclasses `ASIDecodeError` so existing handlers keep catching it. Only ops that require data to
    produce a result raise this; ops that just acknowledge still treat an empty reply as success.
    """

    def __init__(self, operation: str, reply: Reply):
        super().__init__(operation, reply, f"No reply to {operation}: the serial read returned nothing")
