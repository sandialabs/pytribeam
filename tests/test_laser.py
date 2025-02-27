## python standard libraries
from pathlib import Path
import platform
import time
import requests

# 3rd party libraries
import pytest


# Local
import pytribeam.constants as cs
from pytribeam.constants import Conversions
import pytribeam.laser as laser
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.insertable_devices as devices
import pytribeam.factory as factory


@ut.run_on_microscope_machine
def test_laser_connected():
    connect_msg = "Connection test successful.\n"

    assert laser.laser_connected() == True


@ut.run_on_microscope_machine
def test_pattern_mode():
    coarse = tbt.LaserPatternMode.COARSE
    aa = laser.pattern_mode(mode=coarse)
    assert aa == True

    fine = tbt.LaserPatternMode.FINE
    bb = laser.pattern_mode(mode=fine)
    assert bb == True


@ut.run_on_microscope_machine
def test_pulse_divider():
    laser.tfs_laser.Laser_PulseDivider(2)
    time.sleep(3.0)

    with pytest.raises(ValueError) as err:
        laser.pulse_divider(1e15)
    assert err.type == ValueError
    assert (
        err.value.args[0]
        == f"Could not properly set pulse divider, requested '1000000000000000.0'"
    )

    laser.pulse_divider(1)
    state = factory.active_laser_state()
    assert state.pulse_divider == 1


@ut.run_on_microscope_machine
def test_pulse_energy_uj():
    laser.tfs_laser.Laser_SetPulseEnergy_MicroJoules(10.0)
    time.sleep(3.0)
    tolerance = 0.1

    with pytest.raises(ValueError) as err:
        laser.pulse_energy_uj(100.0)
    assert err.type == ValueError
    assert (
        err.value.args[0] == "Could not properly set pulse energy, requested '100.0' uJ"
    )

    laser.pulse_energy_uj(5.0, energy_tol_uj=tolerance)
    state = factory.active_laser_state()
    assert state.pulse_energy_uj == pytest.approx(5.0, abs=tolerance)


@ut.run_on_microscope_machine
def test_insert_shutter():
    """tests laser shutter insert"""
    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    laser.tfs_laser.Shutter_Retract()

    assert laser.tfs_laser.Shutter_GetState() == "Retracted"

    assert laser.insert_shutter(microscope=microscope) == True

    assert laser.tfs_laser.Shutter_GetState() == "Inserted"

    laser.tfs_laser.Shutter_Retract()

    assert laser.tfs_laser.Shutter_GetState() == "Retracted"

    microscope.disconnect()


@ut.run_on_microscope_machine
def test_retract_shutter():
    """tests laser shutter retract"""
    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    laser.tfs_laser.Shutter_Insert()

    assert laser.tfs_laser.Shutter_GetState() == "Inserted"

    assert laser.retract_shutter(microscope=microscope) == True

    assert laser.tfs_laser.Shutter_GetState() == "Retracted"

    microscope.disconnect()


@ut.run_on_microscope_machine
def test_set_wavelength():
    """test wavelength setting on the laser"""
    assert laser.set_wavelength(wavelength=tbt.LaserWavelength.NM_515)
    assert laser.set_wavelength(wavelength=tbt.LaserWavelength.NM_1030)


@ut.run_on_microscope_machine
def test_device_connections():
    """test device connections. Current test will work on offline machine only, when all statuses should be 'Error'"""
    status = laser._device_connections()
    assert (
        str(status)
        == f'Laser: "{status.laser.value}"\nEBSD Detector: "{status.ebsd.value}"\nEDS Detector: "{status.eds.value}"'
    )


@ut.run_on_microscope_machine
def test_pulse_polarization():
    """test polarization of laser pulses"""
    wavelength = tbt.LaserWavelength.NM_1030
    laser.set_wavelength(wavelength=wavelength)
    polarization = tbt.LaserPolarization.HORIZONTAL
    assert (
        laser.pulse_polarization(polarization=polarization, wavelength=wavelength)
        == True
    )

    polarization = tbt.LaserPolarization("vertical")
    assert (
        laser.pulse_polarization(polarization=polarization, wavelength=wavelength)
        == True
    )

    polarization = tbt.LaserPolarization("horizontal")
    assert (
        laser.pulse_polarization(polarization=polarization, wavelength=wavelength)
        == True
    )

    with pytest.raises(KeyError) as err:
        laser.pulse_polarization(polarization="none", wavelength=wavelength)
    assert err.type == KeyError
    assert (
        err.value.args[0]
        == f"Invalid pulse polarization, valid options are {[i.value for i in tbt.LaserPolarization]}"
    )
    polarization = tbt.LaserPolarization.VERTICAL
    assert (
        laser.pulse_polarization(polarization=polarization, wavelength=wavelength)
        == True
    )


@ut.run_on_microscope_machine
def test_objective_position():
    laser.objective_position(
        position_mm=5.0, tolerance_mm=cs.Constants.laser_objective_tolerance_mm
    )
    assert laser.tfs_laser.LIP_GetZPosition() == pytest.approx(5.0, abs=0.005)

    with pytest.raises(SystemError) as err:
        laser.objective_position(position_mm=4.990, tolerance_mm=0.00001)
    assert err.type == SystemError
    assert (
        err.value.args[0]
        == f"Unable to move laser injection port objective to requested position of 4.99 +/- 1e-05 mm."
    )

    assert laser.retract_laser_objective() == True


@ut.run_on_microscope_machine
def test_pulse_settings():
    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    pulse_01 = tbt.LaserPulse(
        wavelength_nm=tbt.LaserWavelength.NM_1030,
        divider=2,
        energy_uj=5.0,
        polarization=tbt.LaserPolarization.VERTICAL,
    )

    laser.pulse_settings(pulse=pulse_01)

    active_settings = factory.active_laser_settings(microscope=microscope)
    active_pulse = active_settings.pulse

    assert pulse_01.wavelength_nm == active_pulse.wavelength_nm
    assert pulse_01.divider == active_pulse.divider
    assert pulse_01.energy_uj == pytest.approx(
        active_pulse.energy_uj, abs=cs.Constants.laser_energy_tol_uj
    )
    # TODO cannot check polarization state


@ut.run_on_microscope_machine
def test_beam_shift():
    laser.tfs_laser.BeamShift_Set_X(0.0)
    laser.tfs_laser.BeamShift_Set_Y(0.0)

    shift_um = tbt.Point(
        x=3.5,
        y=5.5,
    )
    laser.beam_shift(shift_um=shift_um)

    assert laser.tfs_laser.BeamShift_Get_X() == pytest.approx(
        3.5, abs=cs.Constants.laser_beam_shift_tolerance_um
    )
    assert laser.tfs_laser.BeamShift_Get_Y() == pytest.approx(
        5.0, abs=cs.Constants.laser_beam_shift_tolerance_um
    )

    laser.tfs_laser.BeamShift_Set_X(0.0)
    laser.tfs_laser.BeamShift_Set_Y(0.0)


@ut.run_on_microscope_machine
def test_create_pattern():
    pattern = tbt.LaserPattern(
        mode=tbt.LaserPatternMode.COARSE,
        rotation_deg=0.0,
        # pulses_per_pixel=2,
        pixel_dwell_ms=0.5,
        geometry=tbt.LaserBoxPattern(
            passes=10,
            size_x_um=200.0,
            size_y_um=100.0,
            pitch_x_um=2.0,
            pitch_y_um=3.0,
            scan_type=tbt.LaserScanType.SERPENTINE,
            coordinate_ref=tbt.CoordinateReference.UPPER_CENTER,
        ),
    )

    laser.create_pattern(pattern=pattern)

    line_pattern = tbt.LaserPattern(
        mode=tbt.LaserPatternMode.FINE,
        rotation_deg=10.0,
        pulses_per_pixel=20,
        # pixel_dwell_ms=10.0,
        geometry=tbt.LaserLinePattern(
            passes=3,
            size_um=532,
            pitch_um=1.1,
            scan_type=tbt.LaserScanType.LAP,
        ),
    )

    laser.create_pattern(pattern=line_pattern)


def small_test_pattern(microscope: tbt.Microscope) -> tbt.LaserSettings:
    laser_settings = tbt.LaserSettings(
        microscope=microscope,
        pulse=tbt.LaserPulse(
            wavelength_nm=tbt.LaserWavelength.NM_1030,
            divider=2,
            energy_uj=5.0,
            polarization=tbt.LaserPolarization.VERTICAL,
        ),
        objective_position_mm=2.5,
        beam_shift_um=tbt.Point(
            x=0.0,
            y=0.0,
        ),
        pattern=tbt.LaserPattern(
            mode=tbt.LaserPatternMode.COARSE,
            rotation_deg=0.0,
            # pulses_per_pixel=2,
            pixel_dwell_ms=0.5,
            geometry=tbt.LaserBoxPattern(
                passes=10,
                size_x_um=20.0,
                size_y_um=10.0,
                pitch_x_um=2.0,
                pitch_y_um=3.0,
                scan_type=tbt.LaserScanType.SERPENTINE,
                coordinate_ref=tbt.CoordinateReference.UPPER_CENTER,
            ),
        ),
    )

    # initial_scan_rotation of ebeam
    devices.device_access(microscope=microscope)
    active_beam = factory.active_beam_with_settings(microscope=microscope)

    laser.apply_laser_settings(
        image_beam=active_beam,
        settings=laser_settings,
    )

    return laser_settings


@ut.run_on_microscope_machine
def test_apply_laser_settings():
    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    laser_settings = small_test_pattern(microscope=microscope)

    microscope.disconnect()


@pytest.mark.skipif(
    (
        not any(
            platform.uname().node.lower() in machine.lower()
            for machine in (cs.Constants.microscope_machines)
        )
    )
    or (not cs.Constants.test_hardware_movement),
    reason="Run on microscope machine only",
)
def test_execute_patterning(capsys):
    # connect to microscope
    microscope = tbt.Microscope()
    ut.connect_microscope(
        microscope=microscope, quiet_output=True, connection_host="localhost"
    )

    laser_settings = small_test_pattern(microscope=microscope)

    no_shutter_msg = "Error from Laser Control UI: Chamber shutter is not inserted. Use the Shutter_Insert function before calling this one."
    try:
        laser.execute_patterning()
        captured = capsys.readouterr()
        assert captured.out == no_shutter_msg
    except Exception as e:
        pass

    laser.insert_shutter(microscope=microscope)
    laser.execute_patterning()
    laser.retract_shutter(microscope=microscope)

    microscope.disconnect()


@ut.run_on_microscope_machine
def test_mill_region():
    # connect to microscope
    microscope = tbt.Microscope()
    ut.connect_microscope(
        microscope=microscope, quiet_output=True, connection_host="localhost"
    )

    laser_settings = small_test_pattern(microscope=microscope)

    laser.mill_region(laser_settings)


@ut.run_on_microscope_machine
def test_read_values():
    """tests laser state assumes test is run in startup mode"""
    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    small_test_pattern(microscope=microscope)

    known_state = tbt.LaserState(
        wavelength_nm=tbt.LaserWavelength.NM_1030,
        frequency_khz=30.0,
        pulse_divider=2,
        pulse_energy_uj=5.0,
        objective_position_mm=2.5,
        beam_shift_um=tbt.Point(
            x=0.0,
            y=0.0,
        ),
        pattern=tbt.LaserPattern(
            mode=tbt.LaserPatternMode.COARSE,
            rotation_deg=0.0,
            # pulses_per_pixel=2,
            pixel_dwell_ms=0.5,
            geometry=tbt.LaserBoxPattern(
                passes=10,
                size_x_um=20.0,
                size_y_um=10.0,
                pitch_x_um=2.0,
                pitch_y_um=3.0,
                scan_type=tbt.LaserScanType.SERPENTINE,
                coordinate_ref=tbt.CoordinateReference.UPPER_CENTER,
            ),
        ),
    )

    found_state = factory.active_laser_state()

    assert found_state.wavelength_nm == known_state.wavelength_nm
    assert found_state.frequency_khz == pytest.approx(
        known_state.frequency_khz, abs=0.5
    )
    assert found_state.pulse_divider == known_state.pulse_divider
    assert found_state.pulse_energy_uj == pytest.approx(
        known_state.pulse_energy_uj, abs=0.005
    )
    assert found_state.objective_position_mm == pytest.approx(
        known_state.objective_position_mm, abs=cs.Constants.laser_objective_tolerance_mm
    )
    assert found_state.beam_shift_um.x == pytest.approx(
        known_state.beam_shift_um.x, abs=0.005
    )
    assert found_state.beam_shift_um.y == pytest.approx(
        known_state.beam_shift_um.y, abs=0.005
    )

    microscope.disconnect()


@ut.run_on_microscope_machine
def test_read_power():
    pulse_01 = tbt.LaserPulse(
        wavelength_nm=tbt.LaserWavelength.NM_1030,
        divider=1,
        energy_uj=10.0,
        polarization=tbt.LaserPolarization.VERTICAL,
    )
    laser.pulse_settings(pulse=pulse_01)

    power_01 = laser.read_power()
    assert power_01 > 0

    pulse_02 = tbt.LaserPulse(
        wavelength_nm=tbt.LaserWavelength.NM_1030,
        divider=2,
        energy_uj=10.0,
        polarization=tbt.LaserPolarization.VERTICAL,
    )
    laser.pulse_settings(pulse=pulse_02)

    power_02 = laser.read_power()
    assert power_02 > 0

    assert power_01 > power_02

    assert ut.in_interval(
        val=power_01 / power_02,
        limit=tbt.Limit(min=1.9, max=2.1),
        type=tbt.IntervalType.OPEN,
    )

    laser.tfs_laser.Laser_PulseDivider(1)
    laser.tfs_laser.Laser_SetPulseEnergy_MicroJoules(2.0)
