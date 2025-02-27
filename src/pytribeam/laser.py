#!/usr/bin/python3

# Default python modules
import os
from pathlib import Path
import time
import warnings
import contextlib, io
import math

try:
    import Laser.PythonControl as tfs_laser

    print("Laser PythonControl API imported.")
except:
    print("WARNING: Laser API not imported!")
    print("\tLaser control, as well as EBSD and EDS control are unavailable.")

# 3rd party .whl modules
import h5py

# Local scripts
from pytribeam.constants import Conversions, Constants
import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.insertable_devices as devices
import pytribeam.image as img


def laser_state_to_db(state: tbt.LaserState) -> dict:
    """converts a laser state type into a flattened dictionary"""
    db = {}

    db["wavelength_nm"] = state.wavelength_nm
    db["frequency_khz"] = state.frequency_khz
    db["pulse_divider"] = state.pulse_divider
    db["pulse_energy_uj"] = state.pulse_energy_uj
    db["objective_position_mm"] = state.objective_position_mm
    db["expected_pattern_duration_s"] = state.expected_pattern_duration_s

    beam_shift = state.beam_shift_um
    db["beam_shift_um_x"] = beam_shift.x
    db["beam_shift_um_y"] = beam_shift.y

    # we can name these differently depending on the needs of the GUI
    pattern = state.pattern
    db["laser_pattern_mode"] = pattern.mode.value
    db["laser_pattern_rotation_deg"] = pattern.rotation_deg
    db["laser_pattern_pulses_per_pixel"] = pattern.pulses_per_pixel
    db["laser_pattern_pixel_dwell_ms"] = pattern.pixel_dwell_ms

    geometry = pattern.geometry
    db["passes"] = geometry.passes
    db["laser_scan_type"] = geometry.scan_type.value
    db["geometry_type"] = geometry.type.value

    if geometry.type == tbt.LaserPatternType.BOX:
        db["size_x_um"] = geometry.size_x_um
        db["size_y_um"] = geometry.size_y_um
        db["pitch_x_um"] = geometry.pitch_x_um
        db["pitch_y_um"] = geometry.pitch_y_um
        db["coordinate_ref"] = geometry.coordinate_ref

    if geometry.type == tbt.LaserPatternType.LINE:
        db["size_um"] = geometry.size_um
        db["pitch_um"] = geometry.pitch_um

    return db


def laser_connected() -> bool:
    connect_msg = "Connection test successful.\n"
    laser_status = io.StringIO()
    try:
        with contextlib.redirect_stdout(laser_status):
            tfs_laser.TestConnection()
    except:
        return False
    else:
        if laser_status.getvalue() == connect_msg:
            return True
    return False


def _device_connections() -> tbt.DeviceStatus:
    """checks laser connection and associated external devices. Meant only to be a quick tool for the GUI, as it will not provide the user with additional info to try and fix it."""
    # laser must be connected to connect with other devices:
    if not laser_connected():
        laser = tbt.RetractableDeviceState.ERROR
        ebsd = tbt.RetractableDeviceState.ERROR
        eds = tbt.RetractableDeviceState.ERROR
    else:
        laser = tbt.RetractableDeviceState.CONNECTED
        ebsd = devices.connect_EBSD()  # retractable device state
        eds = devices.connect_EDS()  # retractable device state

    return tbt.DeviceStatus(
        laser=laser,
        ebsd=ebsd,
        eds=eds,
    )


def pattern_mode(mode: tbt.LaserPatternMode) -> bool:
    """Sets pattern mode."""
    tfs_laser.Patterning_Mode(mode.value)
    laser_state = factory.active_laser_state()
    if laser_state.pattern.mode != mode:
        raise SystemError("Unable to correctly set pattern mode.")
    return True


def pulse_energy_uj(
    energy_uj: float,
    energy_tol_uj: float = Constants.laser_energy_tol_uj,
    delay_s: float = 3.0,
) -> bool:
    """sets pulse energy on laser, should be done after pulse divider"""
    tfs_laser.Laser_SetPulseEnergy_MicroJoules(energy_uj)
    time.sleep(delay_s)
    laser_state = factory.active_laser_state()
    if not ut.in_interval(
        val=laser_state.pulse_energy_uj,
        limit=tbt.Limit(
            min=energy_uj - energy_tol_uj,
            max=energy_uj + energy_tol_uj,
        ),
        type=tbt.IntervalType.CLOSED,
    ):
        raise ValueError(
            f"Could not properly set pulse energy, requested '{energy_uj}' uJ",
            f"Current settings is {round(laser_state.pulse_energy_uj,3)} uJ",
        )
    return True


def pulse_divider(
    divider: int,
    delay_s: float = Constants.laser_delay_s,
) -> bool:
    """sets pulse divider on laser"""
    tfs_laser.Laser_PulseDivider(divider)
    time.sleep(delay_s)
    laser_state = factory.active_laser_state()
    if laser_state.pulse_divider != divider:
        raise ValueError(
            f"Could not properly set pulse divider, requested '{divider}'",
            f"Current settings have a divider of {laser_state.pulse_divider}.",
        )
    return True


def set_wavelength(
    wavelength: tbt.LaserWavelength,
    frequency_khz: float = 60,  # make constnat
    timeout_s: int = 180,  # 120,  # make constant
    num_attempts: int = 2,  # make a constant
    delay_s: int = 5,  # make a constant
) -> bool:
    def correct_wavelength(laser_state: tbt.LaserState):
        if laser_state.wavelength_nm == wavelength:
            return math.isclose(
                laser_state.frequency_khz, frequency_khz, abs_tol=0.5
            )  # TODO use constant for tolerance):
        return False

    for _ in range(num_attempts):
        if not correct_wavelength(factory.active_laser_state()):
            print("Adjusting preset...")
            tfs_laser.Laser_SetPreset(
                wavelength_nm=wavelength.value, frequency_kHz=frequency_khz
            )
        time_remaining = timeout_s
        while time_remaining > 0:
            laser_state = factory.active_laser_state()
            # print(time_remaining, laser_state.frequency_kHz)
            if correct_wavelength(laser_state=laser_state):
                return True
            time.sleep(delay_s)
            time_remaining -= delay_s

    return False


def read_power(delay_s: float = Constants.laser_delay_s) -> float:
    """measures laser power"""
    tfs_laser.Laser_ExternalPowerMeter_PowerMonitoringON()
    tfs_laser.Laser_ExternalPowerMeter_SetZeroOffset()
    tfs_laser.Laser_FireContinuously_Start()
    time.sleep(delay_s)
    power = tfs_laser.Laser_ExternalPowerMeter_ReadPower()
    tfs_laser.Laser_FireContinuously_Stop()
    tfs_laser.Laser_ExternalPowerMeter_PowerMonitoringOFF()
    return power


def insert_shutter(microscope: tbt.Microscope) -> bool:
    """inserts laser shutter"""
    devices.CCD_view(microscope=microscope)
    if tfs_laser.Shutter_GetState() != "Inserted":
        tfs_laser.Shutter_Insert()
    state = tfs_laser.Shutter_GetState()
    if state != "Inserted":
        raise SystemError(
            f"Could not insert laser shutter, current laser shutter state is '{state}'."
        )
    devices.CCD_pause(microscope=microscope)
    return True


def retract_shutter(microscope: tbt.Microscope) -> bool:
    """retract laser shutter"""
    devices.CCD_view(microscope=microscope)
    if tfs_laser.Shutter_GetState() != "Retracted":
        tfs_laser.Shutter_Retract()
    state = tfs_laser.Shutter_GetState()
    if state != "Retracted":
        raise SystemError(
            f"Could not retract laser shutter, current laser shutter state is '{state}'."
        )
    devices.CCD_pause(microscope=microscope)
    return True


def pulse_polarization(
    polarization: tbt.LaserPolarization, wavelength: tbt.LaserWavelength
) -> bool:
    """configure polarization of laser light, no way to read current value. This is controlled via "FlipperConfiguration", which takes the following strings:
    Waveplate_None switches to Vert. (P)
    Waveplate_1030 switches to Horiz. (S)
    Waveplate_515 switches to Horiz. (S)"""
    if polarization == tbt.LaserPolarization.VERTICAL:
        tfs_laser.FlipperConfiguration("Waveplate_None")
        return True
    elif polarization == tbt.LaserPolarization.HORIZONTAL:
        match_db = {
            tbt.LaserWavelength.NM_1030: "Waveplate_1030",
            tbt.LaserWavelength.NM_515: "Waveplate_515",
        }
        try:
            tfs_laser.FlipperConfiguration(match_db[wavelength])
        except KeyError:
            raise KeyError(
                f"Invalid laser wavelength, valid options are {[i.value for i in tbt.LaserWavelength]}"
            )
        return True
    else:
        raise KeyError(
            f"Invalid pulse polarization, valid options are {[i.value for i in tbt.LaserPolarization]}"
        )


def pulse_settings(pulse: tbt.LaserPulse) -> True:
    """Applies pulse settings"""
    active_state = factory.active_laser_state()
    if pulse.wavelength_nm != active_state.wavelength_nm:
        # wavelength settings
        set_wavelength(wavelength=pulse.wavelength_nm)
    pulse_divider(divider=pulse.divider)
    pulse_energy_uj(energy_uj=pulse.energy_uj)
    pulse_polarization(polarization=pulse.polarization, wavelength=pulse.wavelength_nm)
    return True


def retract_laser_objective() -> bool:
    "Retract laser objective to safe position"
    objective_position(position_mm=Constants.laser_objective_retracted_mm)
    return True


def objective_position(
    position_mm: float,
    tolerance_mm=Constants.laser_objective_tolerance_mm,
) -> bool:
    """Moves laser objective to requested position"""
    tfs_laser.LIP_UnlockZ()

    if not ut.in_interval(
        val=position_mm,
        limit=Constants.laser_objective_limit_mm,
        type=tbt.IntervalType.CLOSED,
    ):
        raise ValueError(
            f"Requested laser objective position of {position_mm} mm is out of range. Laser objective can travel from {Constants.laser_objective_limit_mm.min} to {Constants.laser_objective_limit_mm.max} mm."
        )

    for _ in range(2):
        if ut.in_interval(
            val=tfs_laser.LIP_GetZPosition(),
            limit=tbt.Limit(
                min=position_mm - tolerance_mm, max=position_mm + tolerance_mm
            ),
            type=tbt.IntervalType.CLOSED,
        ):
            return True
        tfs_laser.LIP_SetZPosition(position_mm, asynchronously=False)

    raise SystemError(
        f"Unable to move laser injection port objective to requested position of {position_mm} +/- {tolerance_mm} mm.",
        f"Currently at {tfs_laser.LIP_GetZPosition()} mm.",
    )


def _shift_axis(
    target: float,
    current: float,
    tolerance: float,
    axis: str,
) -> bool:
    """helper function for beam_shift"""
    for _ in range(2):
        if ut.in_interval(
            val=current,
            limit=tbt.Limit(
                min=target - tolerance,
                max=target + tolerance,
            ),
            type=tbt.IntervalType.CLOSED,
        ):
            return True
        if axis == "X":
            tfs_laser.BeamShift_Set_X(value=target)
            current = tfs_laser.BeamShift_Get_X()
        if axis == "Y":
            tfs_laser.BeamShift_Set_Y(value=target)
            current = tfs_laser.BeamShift_Get_Y()

    return False


def beam_shift(
    shift_um: tbt.Point,
    shift_tolerance_um: float = Constants.laser_beam_shift_tolerance_um,
) -> bool:
    current_shift_x = tfs_laser.BeamShift_Get_X()
    current_shift_y = tfs_laser.BeamShift_Get_Y()

    if not (
        _shift_axis(
            target=shift_um.x,
            current=current_shift_x,
            tolerance=shift_tolerance_um,
            axis="X",
        )
        and _shift_axis(
            target=shift_um.y,
            current=current_shift_y,
            tolerance=shift_tolerance_um,
            axis="Y",
        )
    ):
        raise ValueError(
            f"Unable to set laser beam shift. Requested beam shift of (x,y) = ({shift_um.x} um,{shift_um.y} um,), but current beam shift is ({tfs_laser.BeamShift_Get_X()} um, {tfs_laser.BeamShift_Get_Y()} um)."
        )
    return True


def create_pattern(pattern: tbt.LaserPattern):
    """Create patterning and check that it is set correctly"""
    pattern_mode(mode=pattern.mode)

    # check if pattern is empty or not
    if isinstance(pattern.geometry, tbt.LaserBoxPattern):
        box = pattern.geometry
        tfs_laser.Patterning_CreatePattern_Box(
            sizeX_um=box.size_x_um,
            sizeY_um=box.size_y_um,
            pitchX_um=box.pitch_x_um,
            pitchY_um=box.pitch_y_um,
            dwellTime_ms=pattern.pixel_dwell_ms,
            passes_int=box.passes,
            pulsesPerPixel_int=pattern.pulses_per_pixel,
            scanrotation_degrees=pattern.rotation_deg,
            scantype_string=box.scan_type.value,  # cast enum to string
            coordinateReference_string=box.coordinate_ref.value,  # cast enum to string
        )
    elif isinstance(pattern.geometry, tbt.LaserLinePattern):
        line = pattern.geometry
        tfs_laser.Patterning_CreatePattern_Line(
            sizeX_um=line.size_um,
            pitchX_um=line.pitch_um,
            dwellTime_ms=pattern.pixel_dwell_ms,
            passes_int=line.passes,
            pulsesPerPixel_int=pattern.pulses_per_pixel,
            scanrotation_degrees=pattern.rotation_deg,
            scantype_string=line.scan_type.value,  # cast enum to string
        )
    else:
        raise ValueError(
            f"Unsupported pattern geometry of type '{type(pattern.geometry)}'. Supported types are {tbt.LaserLinePattern, tbt.LaserBoxPattern}"
        )
    laser_state = factory.active_laser_state()
    if laser_state.pattern != pattern:
        raise SystemError("Unable to correctly set Pattern.")
    return True


def apply_laser_settings(image_beam: tbt.Beam, settings: tbt.LaserSettings) -> bool:
    """Applies laser settings to current patterning"""
    microscope = settings.microscope

    # forces rotation of electron beam for laser (TFS required)
    img.beam_scan_rotation(
        beam=image_beam,
        microscope=microscope,
        rotation_deg=Constants.image_scan_rotation_for_laser_deg,
    )
    # pulse settings
    pulse_settings(pulse=settings.pulse)

    # objective position
    objective_position(settings.objective_position_mm)

    # beam shift
    beam_shift(settings.beam_shift_um)

    # apply patterning settings
    create_pattern(pattern=settings.pattern)

    return True


def execute_patterning() -> bool:
    tfs_laser.Patterning_Start()

    return True


### main methods


def mill_region(
    settings: tbt.LaserSettings,
) -> bool:
    """laser milling main function"""
    # check connection
    if not laser_connected():
        raise SystemError("Laser is not connected")

    microscope = settings.microscope
    # initial_scan_rotation of ebeam
    devices.device_access(microscope=microscope)
    active_beam = factory.active_beam_with_settings(microscope=microscope)
    scan_settings = factory.active_scan_settings(microscope=microscope)
    initial_scan_rotation_deg = scan_settings.rotation_deg

    # apply laser settings
    apply_laser_settings(
        image_beam=active_beam,
        settings=settings,
    )

    # insert shutter
    insert_shutter(microscope=microscope)

    # execute patterning
    execute_patterning()

    # retract shutter
    retract_shutter(microscope=microscope)
    time.sleep(1)

    # reset scan rotation
    img.beam_scan_rotation(
        beam=active_beam,
        microscope=microscope,
        rotation_deg=initial_scan_rotation_deg,
    )

    return True


def laser_operation(
    step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int
) -> bool:
    log_file = Path(general_settings.exp_dir).joinpath(general_settings.h5_log_name)

    # TODO log laser power before

    mill_region(settings=step.operation_settings)

    # TODO log laser power after

    return True


def map_ebsd() -> bool:
    start_time = time.time()
    tfs_laser.EBSD_StartMap()
    time.sleep(1)
    end_time = time.time()
    map_time = end_time - start_time
    if map_time < Constants.min_map_time_s:
        raise ValueError(
            f"Mapping did not take minimum expected time of {Constants.min_map_time_s} seconds, please reset EBSD mapping software"
        )
    print(f"\t\tMapping Complete in {int(map_time)} seconds.")
    return True


def map_eds() -> bool:
    start_time = time.time()
    tfs_laser.EDS_StartMap()
    time.sleep(1)
    end_time = time.time()
    map_time = end_time - start_time
    if map_time < Constants.min_map_time_s:
        raise ValueError(
            f"Mapping did not take minimum expected time of {Constants.min_map_time_s} seconds, please reset EDS mapping software"
        )
    print(f"\t\tMapping Complete in {int(map_time)} seconds.")
    return True
