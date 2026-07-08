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


class TSegment(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("Y", ct.c_uint32),
        ("XStart", ct.c_uint32),
        ("XCount", ct.c_int32),
    ]


PSegmentList = ct.POINTER(TSegment)


class TFeatureData(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("SegmentCount", ct.c_int32),
        ("Segments", PSegmentList),
    ]


class TRTElementRegion(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("Element", ct.c_int32),
        ("IdentifierLength", ct.c_uint8),
        ("Line", ct.c_char * 10),
        ("Energy", ct.c_double),
        ("Width", ct.c_double),
        ("R", ct.c_ubyte),
        ("G", ct.c_ubyte),
        ("B", ct.c_ubyte),
    ]


class TRTHyMapProfileSettings(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("Version", ct.c_int32),
        ("ElementCount", ct.c_int32),
        ("ElementRegions", TRTElementRegion * 51),
        ("ImageFilter", ct.c_int32),
        ("MapFilter", ct.c_int32),
        ("MapFilterWidth", ct.c_int32),
        ("ColorMixMethod", ct.c_int32),
        ("Brightness", ct.c_double),
        ("Gamma", ct.c_double),
        ("ColorSaturation", ct.c_double),
        ("AbsoluteScaling", ct.c_bool),
        ("Normalization", ct.c_bool),
        ("Deconvolution", ct.c_bool),
    ]
