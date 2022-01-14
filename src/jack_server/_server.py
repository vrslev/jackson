from ctypes import POINTER, pointer
from typing import Any, Callable, Literal

import jack_server._libjackserver_bindings as _lib


class Parameter:
    def __init__(self, ptr: Any):
        self.ptr = ptr
        self.type = _lib.jackctl_parameter_get_type(self.ptr)

    @property
    def name(self) -> bytes:
        return _lib.jackctl_parameter_get_name(self.ptr)

    @property
    def value(self):
        param_v = _lib.jackctl_parameter_get_value(self.ptr)
        if self.type == 1:
            # JackParamInt
            return param_v.i
        elif self.type == 2:
            # JackParamUInt
            return param_v.ui
        elif self.type == 3:
            # JackParamChar
            return param_v.c
        elif self.type == 4:
            # JackParamString
            return param_v.ss
        elif self.type == 5:
            # JackParamBool
            return param_v.b

    @value.setter
    def value(self, val: Any):
        param_v = _lib.jackctl_parameter_value()
        if self.type == 1:
            # JackParamInt
            param_v.i = int(val)
        elif self.type == 2:
            # JackParamUInt
            param_v.ui = int(val)
        elif self.type == 3:
            # JackParamChar
            assert isinstance(val, str) and len(val) == 1
            param_v.c = val
        elif self.type == 4:
            # JackParamString
            assert isinstance(val, bytes)
            param_v.ss = val
        elif self.type == 5:
            # JackParamBool
            param_v.b = bool(val)
        _lib.jackctl_parameter_set_value(self.ptr, pointer(param_v))


class Driver:
    def __init__(self, ptr: Any):
        self.ptr = ptr

        params_jslist = _lib.jackctl_driver_get_parameters(self.ptr)
        self.params: dict[bytes, Parameter] = {}

        for param_ptr in _lib.JSIter(params_jslist, POINTER(_lib.jackctl_parameter_t)):
            param = Parameter(param_ptr)
            self.params[param.name] = param

    @property
    def name(self) -> str:
        return _lib.jackctl_driver_get_name(self.ptr).decode()

    def set_device(self, name: str):
        self.params[b"device"].value = name.encode()

    def set_rate(self, rate: Literal[44100, 48000]):
        self.params[b"rate"].value = rate


class Server:
    def __init__(
        self,
        *,
        driver: str,
        device: str,
        rate: Literal[44100, 48000],
        stream_handler: Callable[[str], None] | None = None,
    ):
        self.ptr = _lib.jackctl_server_create(
            _lib.DeviceAcquireFunc(),  # type: ignore
            _lib.DeviceReleaseFunc(),  # type: ignore
            _lib.DeviceReservationLoop(),  # type: ignore
        )
        self.driver = self.get_driver_by_name(driver)
        self.driver.set_device(device)
        self.driver.set_rate(rate)

        if stream_handler:
            self._print = stream_handler
            set_error_function(self._print)
            set_info_function(self._print)
        else:
            self._print = print

    def get_driver_by_name(self, name: str):
        driver_jslist = _lib.jackctl_server_get_drivers_list(self.ptr)

        for ptr in _lib.JSIter(driver_jslist, POINTER(_lib.jackctl_driver_t)):
            driver = Driver(ptr)
            if driver.name == name:
                return driver

        raise RuntimeError(f"Driver not found: {name}")

    def start(self):
        self._print("Starting server...")
        _lib.jackctl_server_open(self.ptr, self.driver.ptr)
        _lib.jackctl_server_start(self.ptr)

    def stop(self):
        self._print("Stopping server...")
        _lib.jackctl_server_stop(self.ptr)
        _lib.jackctl_server_close(self.ptr)
        _lib.jackctl_server_destroy(self.ptr)

        if self._print is not print:
            set_error_function(None)
            set_info_function(None)


_dont_garbage_collect: list[Any] = []


def _wrap_error_or_info_callback(
    callback: Callable[[str], None] | None,
):
    if callback:

        def wrapped_callback(message: bytes):
            callback(message.decode())

        cb = _lib.PrintFunction(wrapped_callback)
    else:
        cb = _lib.PrintFunction()  # type: ignore

    _dont_garbage_collect.append(cb)
    return cb


def set_info_function(callback: Callable[[str], None] | None):
    _lib.jack_set_info_function(_wrap_error_or_info_callback(callback))


def set_error_function(callback: Callable[[str], None] | None):
    _lib.jack_set_error_function(_wrap_error_or_info_callback(callback))
