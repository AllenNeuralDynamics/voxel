from vxl_drivers.tigerhub.model import Reply


class ASIProtocolError(RuntimeError):
    """A reply could not be turned into a usable result.

    Base for both "the controller said nothing" and "the controller said something unusable".
    Catch this where any bad reply should be tolerated; catch a subclass to distinguish them.
    """

    def __init__(self, operation: str, reply: Reply, msg: str | None = None):
        self.operation = operation
        self.reply = reply
        super().__init__(msg or f"Error decoding {operation}: {reply}")


class ASIDecodeError(ASIProtocolError):
    """The controller replied, but the reply was malformed or carried an error code."""


class ASINoReplyError(ASIProtocolError):
    """The controller sent nothing back — the serial read returned empty before its timeout.

    A sibling of `ASIDecodeError` rather than a subclass: handlers that mean "tolerate a malformed
    reply" should not silently absorb a dead link as well. Use `ASIProtocolError` to catch both.
    """

    def __init__(self, operation: str, reply: Reply):
        super().__init__(operation, reply, f"No reply to {operation}: the serial read returned nothing")
