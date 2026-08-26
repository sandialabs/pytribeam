# python standard libraries

# 3rd party libraries
import pytest

# Local
import pytribeam.external_oem.device_control as external_devices
import pytribeam.types as tbt

# ----------------
# Helper functions
# ----------------


def general_settings(
    ebsd_oem: tbt.ExternalDeviceOEM,
    eds_oem: tbt.ExternalDeviceOEM,
) -> tbt.GeneralSettings:
    """Build minimal GeneralSettings for external OEM device-control tests."""
    return tbt.GeneralSettings(
        yml_version=1.0,
        slice_thickness_um=1.0,
        max_slice_number=1,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(
            translational_um=1.0,
            angular_deg=1.0,
        ),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=ebsd_oem,
        EDS_OEM=eds_oem,
        exp_dir=".",
        h5_log_name="log",
        step_count=1,
    )


# -----
# Tests
# -----


@pytest.mark.simulated
class TestBrukerDeviceControlPlaceholders:
    """Phase 1 Bruker dispatcher tests for no-op placeholder behavior."""

    def test_bruker_connect_ebsd_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.BRUKER,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        status = external_devices.connect_ebsd(general_settings=settings)
        captured = capsys.readouterr()

        assert status == tbt.RetractableDeviceState.CONNECTED
        assert (
            "Bruker EBSD device control is not implemented in Phase 1" in captured.out
        )

    def test_bruker_connect_eds_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.BRUKER,
        )

        status = external_devices.connect_eds(general_settings=settings)
        captured = capsys.readouterr()

        assert status == tbt.RetractableDeviceState.CONNECTED
        assert (
            "Bruker EDS device control is handled by the Bruker workflow configuration"
            in captured.out
        )

    def test_bruker_insert_ebsd_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.BRUKER,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.insert_ebsd(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EBSD device control is not implemented in Phase 1" in captured.out
        )

    def test_bruker_retract_ebsd_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.BRUKER,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.retract_ebsd(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EBSD device control is not implemented in Phase 1" in captured.out
        )

    def test_bruker_insert_eds_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.BRUKER,
        )

        assert external_devices.insert_eds(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EDS device control is handled by the Bruker workflow configuration"
            in captured.out
        )

    def test_bruker_retract_eds_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.BRUKER,
        )

        assert external_devices.retract_eds(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EDS device control is handled by the Bruker workflow configuration"
            in captured.out
        )


@pytest.mark.laser_hardware
@pytest.mark.oxford_hardware
class TestOxfordDeviceControlDispatcher:
    """Oxford hardware tests for dispatcher routes that use TFS Laser API."""

    def test_connect_ebsd_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.OXFORD,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        status = external_devices.connect_ebsd(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_connect_eds_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.OXFORD,
        )

        status = external_devices.connect_eds(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_retract_ebsd_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.OXFORD,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.retract_ebsd(
            microscope=microscope,
            general_settings=settings,
        )

    def test_retract_eds_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.OXFORD,
        )

        assert external_devices.retract_eds(
            microscope=microscope,
            general_settings=settings,
        )


@pytest.mark.laser_hardware
@pytest.mark.edax_hardware
class TestEdaxDeviceControlDispatcher:
    """EDAX hardware tests for dispatcher routes that use TFS Laser API."""

    def test_connect_ebsd_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.EDAX,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        status = external_devices.connect_ebsd(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_connect_eds_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.EDAX,
        )

        status = external_devices.connect_eds(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_retract_ebsd_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.EDAX,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.retract_ebsd(
            microscope=microscope,
            general_settings=settings,
        )

    def test_retract_eds_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.EDAX,
        )

        assert external_devices.retract_eds(
            microscope=microscope,
            general_settings=settings,
        )
