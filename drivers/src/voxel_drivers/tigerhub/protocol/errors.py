from voxel_drivers.tigerhub.model import Reply


class ASIDecodeError(RuntimeError):
    def __init__(self, operation: str, reply: Reply):
        self.operation = operation
        self.reply = reply
        super().__init__(f"Error decoding {operation}: {reply}")
