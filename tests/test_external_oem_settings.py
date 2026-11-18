"""Configuration of external OEM backends: vendor settings blocks (YAML v1.2),
their validation, and backend resolution."""

# python standard libraries
from copy import deepcopy
from pathlib import Path

# 3rd party libraries
import pytest

# pytribeam.types needs AutoScript. Skip, rather than error at collection, on
# machines without it.
pytest.importorskip("autoscript_sdb_microscope_client")

# Local
import pytribeam.external_oem.dispatch as external_devices
import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut
from pytribeam.constants import Constants
from pytribeam.external_oem.core.errors import ConfigurationError

OEM = tbt.ExternalDeviceOEM
BACKEND = tbt.ExternalBackend

EDAX_DB = {
    "save_directory": "D:/EDAX Data/exp1",
    "project_name": "exp1",
    "connection": {"host": "edax-pc", "port": 8301},
}

OXFORD_DB = {
    "connection": {"host": "aztec-pc", "port": None},
    "ebsd_profile": "pyTriBeam EBSD",
    "eds_profile": "pyTriBeam EDS",
}

BRUKER_SESSION = {"dll_dir": "C:/Program Files/Bruker/Esprit API", "password": "pw"}
BRUKER_EDS = {
    "output": {"root_dir": "C:/data/eds"},
    "detector": {},
    "map": {
        "mode": "simple",
        "width_px": 64,
        "height_px": 48,
        "pixel_time_us": 1024,
    },
}
BRUKER_EBSD = {
    "output": {"root_dir": "C:/data/ebsd"},
    "detector": {"inserted_position_mm": 20.0, "retracted_position_mm": 0.0},
    "acquisition": {
        "profile_name": "default",
        "width_px": 50,
        "height_px": 24,
        "pixel_time_us": 512,
    },
}


def bruker_db(eds=True, ebsd=True):
    """Return a Bruker_settings block with the requested technique sections."""
    db = {"session": BRUKER_SESSION}
    if eds:
        db["eds"] = BRUKER_EDS
    if ebsd:
        db["ebsd"] = BRUKER_EBSD
    return deepcopy(db)


@pytest.fixture
def laser(monkeypatch):
    """Control whether the LaserControl API looks available, and record checks."""
    import pytribeam.laser as fs_laser

    def set_available(available: bool):
        if available:
            monkeypatch.setattr(fs_laser, "tfs_laser", object(), raising=False)
        else:
            monkeypatch.delattr(fs_laser, "tfs_laser", raising=False)

    set_available(False)
    return set_available


@pytest.fixture
def edax_reachable(monkeypatch):
    """Record dispatcher connection tests as (backend, technique) pairs.

    Validation itself never connects; `factory.general` tests each native
    backend's connection once the settings are built.
    """
    calls = []

    def test_connection(general_settings, technique):
        backend = external_devices.backend(general_settings, technique)
        calls.append((backend, technique))
        return True

    monkeypatch.setattr(external_devices, "test_connection", test_connection)
    return calls


def validate(ebsd_oem, eds_oem, version=1.2, **blocks):
    return factory.validate_EBSD_EDS_settings(
        yml_format=ut.yml_format(version=version),
        ebsd_oem=ebsd_oem,
        eds_oem=eds_oem,
        **blocks,
    )


# -----------------
# Backend resolution
# -----------------


class TestResolveBackend:
    @pytest.mark.parametrize(
        "oem, blocks, expected",
        [
            (OEM.NONE, {}, None),
            (OEM.EDAX, {}, BACKEND.TFS_LASER),
            (OEM.EDAX, {"edax_settings": EDAX_DB}, BACKEND.EDAX_IPAPI),
            (OEM.OXFORD, {}, BACKEND.TFS_LASER),
            (OEM.OXFORD, {"oxford_settings": OXFORD_DB}, BACKEND.OXFORD_AZTEC),
            (OEM.BRUKER, {"bruker_settings": bruker_db()}, BACKEND.BRUKER_ESPRIT),
        ],
    )
    def test_native_when_the_vendor_block_is_present(self, oem, blocks, expected):
        assert external_devices.resolve_backend(oem, **blocks) is expected

    @pytest.mark.parametrize(
        "oem, foreign",
        [
            (OEM.EDAX, {"oxford_settings": OXFORD_DB}),
            (OEM.OXFORD, {"edax_settings": EDAX_DB}),
        ],
    )
    def test_another_vendors_block_does_not_select_native(self, oem, foreign):
        assert external_devices.resolve_backend(oem, **foreign) is BACKEND.TFS_LASER

    def test_bruker_without_its_block_has_no_fallback(self):
        with pytest.raises(ConfigurationError, match="Bruker_settings"):
            external_devices.resolve_backend(OEM.BRUKER, edax_settings=EDAX_DB)

    def test_rejects_a_raw_string(self):
        with pytest.raises(TypeError):
            external_devices.resolve_backend("EDAX")

    def test_accepts_parsed_config_objects(self):
        edax = factory.edax_config(EDAX_DB)
        assert (
            external_devices.resolve_backend(OEM.EDAX, edax_settings=edax)
            is BACKEND.EDAX_IPAPI
        )


# ---------------------------
# Parsing vendor settings blocks
# ---------------------------


class TestVendorConfigParsing:
    def test_absent_blocks_parse_to_none(self):
        assert factory.edax_config(None) is None
        assert factory.oxford_config(None) is None
        assert factory.bruker_config(None) is None

    def test_edax(self):
        edax = factory.edax_config(EDAX_DB)

        assert edax == tbt.EDAXConfig(
            save_directory="D:/EDAX Data/exp1",
            project_name="exp1",
            connection=tbt.MicroscopeConnection(host="edax-pc", port=8301),
        )

    def test_oxford_defaults_the_port_and_dll_dir(self):
        oxford = factory.oxford_config(OXFORD_DB)

        assert oxford.connection == tbt.MicroscopeConnection(
            host="aztec-pc", port=Constants.oxford_aztec_default_port
        )
        assert oxford.ebsd_profile == "pyTriBeam EBSD"
        assert oxford.eds_profile == "pyTriBeam EDS"
        assert oxford.dll_dir is None

    def test_oxford_explicit_port_and_dll_dir(self):
        db = deepcopy(OXFORD_DB)
        db["connection"]["port"] = 30000
        db["dll_dir"] = "C:/AZtec/Plugin"

        oxford = factory.oxford_config(db)

        assert oxford.connection.port == 30000
        assert oxford.dll_dir == Path("C:/AZtec/Plugin")

    def test_bruker(self):
        bruker = factory.bruker_config(bruker_db())

        assert isinstance(bruker, tbt.BrukerConfig)
        assert bruker.session.password == "pw"
        assert bruker.eds is not None and bruker.ebsd is not None


# -------------------------
# Validating EBSD/EDS settings
# -------------------------


class TestValidateEbsdEdsSettings:
    def test_no_oem_needs_nothing(self, laser):
        assert validate(None, None)

    def test_differing_oems_are_refused(self, laser):
        with pytest.raises(NotImplementedError, match="Differing"):
            validate("EDAX", "Oxford", edax_settings=EDAX_DB)

    def test_unknown_oem_is_refused(self, laser):
        with pytest.raises(ValueError, match="Unsupported EBSD OEM"):
            validate("Zeiss", None)

    # LaserControl is needed only by the fallback

    @pytest.mark.parametrize("oem", ["EDAX", "Oxford"])
    def test_fallback_requires_laser_control(self, laser, oem):
        with pytest.raises(SystemError, match="Laser API not accessible"):
            validate(oem, oem)

    @pytest.mark.parametrize("oem", ["EDAX", "Oxford"])
    def test_fallback_passes_with_laser_control(self, laser, oem):
        laser(True)
        assert validate(oem, oem)

    def test_native_edax_does_not_require_laser_control(self, laser, edax_reachable):
        assert validate("EDAX", "EDAX", version=1.1, edax_settings=EDAX_DB)
        assert edax_reachable == []  # validation does not connect

    def test_native_oxford_does_not_require_laser_control(self, laser):
        assert validate("Oxford", "Oxford", oxford_settings=OXFORD_DB)

    def test_native_bruker_does_not_require_laser_control(self, laser):
        assert validate("Bruker", "Bruker", bruker_settings=bruker_db())

    # EDAX

    @pytest.mark.parametrize(
        "change",
        [
            lambda db: db.pop("save_directory"),
            lambda db: db.pop("project_name"),
            lambda db: db.pop("connection"),
            lambda db: db.update(project_name=7),
            lambda db: db["connection"].pop("host"),
            lambda db: db["connection"].update(port="8301"),
        ],
    )
    def test_invalid_edax_block_is_refused(self, laser, edax_reachable, change):
        """Missing keys used to raise KeyError; all problems are now ValueError."""
        db = deepcopy(EDAX_DB)
        change(db)

        with pytest.raises(ValueError, match="EDAX_settings"):
            validate("EDAX", "EDAX", version=1.1, edax_settings=db)
        assert edax_reachable == []

    def test_unused_edax_block_is_checked_but_not_connected(
        self, laser, edax_reachable
    ):
        """v1.1 configurations carry EDAX_settings whatever the OEM."""
        assert validate(
            "Oxford", "Oxford", oxford_settings=OXFORD_DB, edax_settings=EDAX_DB
        )
        assert edax_reachable == []

        bad = deepcopy(EDAX_DB)
        bad["connection"]["port"] = "8301"
        with pytest.raises(ValueError, match="EDAX_settings"):
            validate("Oxford", "Oxford", oxford_settings=OXFORD_DB, edax_settings=bad)

    def test_edax_fallback_does_not_connect_to_the_ipapi(self, laser, edax_reachable):
        laser(True)

        assert validate("EDAX", "EDAX", version=1.1)
        assert edax_reachable == []

    # Oxford

    @pytest.mark.parametrize(
        "ebsd_oem, eds_oem, missing",
        [
            ("Oxford", None, "ebsd_profile"),
            (None, "Oxford", "eds_profile"),
        ],
    )
    def test_native_oxford_needs_a_profile_per_technique(
        self, laser, ebsd_oem, eds_oem, missing
    ):
        db = deepcopy(OXFORD_DB)
        db[missing] = None

        with pytest.raises(ValueError, match=f"Oxford_settings.{missing}"):
            validate(ebsd_oem, eds_oem, oxford_settings=db)

    def test_unused_oxford_profile_may_be_omitted(self, laser):
        db = deepcopy(OXFORD_DB)
        del db["eds_profile"]

        assert validate("Oxford", None, oxford_settings=db)

    @pytest.mark.parametrize(
        "change",
        [
            lambda db: db["connection"].update(host=""),
            lambda db: db["connection"].update(port=0),
            lambda db: db["connection"].pop("host"),
            lambda db: db.update(ebsd_profile=3),
            lambda db: db.update(unknown_key=True),
            lambda db: db.pop("connection"),
        ],
    )
    def test_invalid_oxford_block_is_refused(self, laser, change):
        db = deepcopy(OXFORD_DB)
        change(db)

        with pytest.raises(ValueError, match="Oxford_settings"):
            validate("Oxford", "Oxford", oxford_settings=db)

    # Bruker

    def test_bruker_without_its_block_is_refused(self, laser):
        with pytest.raises(ValueError, match="Bruker_settings"):
            validate(None, "Bruker")

    @pytest.mark.parametrize(
        "ebsd_oem, eds_oem, sections, match",
        [
            ("Bruker", None, {"ebsd": False}, "no 'ebsd' section"),
            (None, "Bruker", {"eds": False}, "no 'eds' section"),
        ],
    )
    def test_bruker_needs_a_section_per_enabled_technique(
        self, laser, ebsd_oem, eds_oem, sections, match
    ):
        with pytest.raises(ValueError, match=match):
            validate(ebsd_oem, eds_oem, bruker_settings=bruker_db(**sections))

    def test_unused_bruker_section_may_be_omitted(self, laser):
        assert validate(None, "Bruker", bruker_settings=bruker_db(ebsd=False))

    def test_invalid_bruker_block_is_refused(self, laser):
        db = bruker_db()
        db["ebsd"]["detector"]["retracted_position_mm"] = 20.0

        with pytest.raises(ValueError, match="Invalid 'Bruker_settings'"):
            validate("Bruker", "Bruker", bruker_settings=db)


# ---------------------------------
# Connection tests after validation
# ---------------------------------


def built_settings(ebsd_oem, eds_oem, **blocks):
    return tbt.GeneralSettings(
        yml_version=1.2,
        slice_thickness_um=1.0,
        max_slice_number=1,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(translational_um=1.0, angular_deg=1.0),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=ebsd_oem,
        EDS_OEM=eds_oem,
        exp_dir=".",
        h5_log_name="log",
        step_count=1,
        **blocks,
    )


class TestExternalConnections:
    def test_each_native_technique_is_tested(self, edax_reachable):
        settings = built_settings(
            OEM.OXFORD, OEM.OXFORD, Oxford_settings=factory.oxford_config(OXFORD_DB)
        )

        assert factory.test_external_connections(settings)
        assert edax_reachable == [
            (BACKEND.OXFORD_AZTEC, tbt.ExternalTechnique.EBSD),
            (BACKEND.OXFORD_AZTEC, tbt.ExternalTechnique.EDS),
        ]

    def test_only_configured_techniques(self, edax_reachable):
        settings = built_settings(
            OEM.NONE, OEM.EDAX, EDAX_settings=factory.edax_config(EDAX_DB)
        )

        factory.test_external_connections(settings)

        assert edax_reachable == [(BACKEND.EDAX_IPAPI, tbt.ExternalTechnique.EDS)]

    @pytest.mark.parametrize("oem", [OEM.EDAX, OEM.OXFORD, OEM.NONE])
    def test_laser_control_fallback_and_no_oem_are_skipped(self, edax_reachable, oem):
        assert factory.test_external_connections(built_settings(oem, oem))
        assert edax_reachable == []

    def test_an_unreachable_vendor_fails_validation(self, monkeypatch):
        def unreachable(general_settings, technique):
            raise external_devices.DetectorError("AZtec not listening")

        monkeypatch.setattr(external_devices, "test_connection", unreachable)
        settings = built_settings(
            OEM.OXFORD, OEM.NONE, Oxford_settings=factory.oxford_config(OXFORD_DB)
        )

        with pytest.raises(external_devices.DetectorError, match="not listening"):
            factory.test_external_connections(settings)


# -------------------------------------
# Full general-settings parse (microscope)
# -------------------------------------


@pytest.mark.simulated
class TestGeneralSettingsV12:
    def general_db(self, tmp_path, **general):
        return {
            "slice_thickness_um": 2.0,
            "max_slice_num": 400,
            "pre_tilt_deg": 36.0,
            "sectioning_axis": "Z",
            "stage_translational_tol_um": 0.5,
            "stage_angular_tol_deg": 0.02,
            "connection_host": "localhost",
            "connection_port": None,
            "exp_dir": str(tmp_path),
            "h5_log_name": "log",
            "step_count": 1,
            **general,
        }

    def parse(self, db, version=1.2):
        return factory.general(general_db=db, yml_format=ut.yml_format(version))

    def test_v12_without_vendor_blocks(self, tmp_path, laser):
        settings = self.parse(self.general_db(tmp_path, EBSD_OEM=None, EDS_OEM=None))

        assert settings.yml_version == 1.2
        assert settings.EDAX_settings is None
        assert settings.Oxford_settings is None
        assert settings.Bruker_settings is None

    def test_v11_without_an_edax_block(self, tmp_path, laser):
        """v1.1 used to fail here even with no EDAX OEM configured."""
        settings = self.parse(
            self.general_db(tmp_path, EBSD_OEM=None, EDS_OEM=None), version=1.1
        )

        assert settings.EDAX_settings is None

    def test_v12_oxford(self, tmp_path, laser, edax_reachable):
        settings = self.parse(
            self.general_db(
                tmp_path,
                EBSD_OEM="Oxford",
                EDS_OEM="Oxford",
                Oxford_settings=deepcopy(OXFORD_DB),
            )
        )

        assert settings.Oxford_settings == factory.oxford_config(OXFORD_DB)
        assert [backend for backend, _ in edax_reachable] == [BACKEND.OXFORD_AZTEC] * 2

    def test_v12_bruker(self, tmp_path, laser, edax_reachable):
        settings = self.parse(
            self.general_db(
                tmp_path,
                EBSD_OEM="Bruker",
                EDS_OEM="Bruker",
                Bruker_settings=bruker_db(),
            )
        )

        assert settings.Bruker_settings == factory.bruker_config(bruker_db())
        assert [backend for backend, _ in edax_reachable] == [BACKEND.BRUKER_ESPRIT] * 2

    def test_v11_ignores_v12_blocks(self, tmp_path, laser):
        settings = self.parse(
            self.general_db(
                tmp_path,
                EBSD_OEM=None,
                EDS_OEM=None,
                Oxford_settings=deepcopy(OXFORD_DB),
            ),
            version=1.1,
        )

        assert settings.Oxford_settings is None
