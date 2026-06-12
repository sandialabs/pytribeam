import ctypes as ct

c_u32 = ct.c_uint32
c_i32 = ct.c_int32
c_u16 = ct.c_uint16
c_dbl = ct.c_double
c_bool = ct.c_bool


class TOpenClientOptions(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("Version", c_i32),
        ("GUIMode", c_i32),
        ("StartNew", c_bool),
        ("IdentifierLength", ct.c_uint8),
        ("TCPHost", ct.c_char * 64),
        ("TCPPort", c_u16),
    ]
