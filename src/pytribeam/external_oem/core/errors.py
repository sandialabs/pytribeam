class DetectorError(Exception):
    pass


class APICallError(DetectorError):
    def __init__(self, function_name: str, rc: int, message: str = ""):
        self.function_name = function_name
        self.rc = rc
        self.message = message
        suffix = f" ({message})" if message else ""
        super().__init__(f"{function_name} failed rc={rc}{suffix}")


class ConfigurationError(DetectorError):
    pass
