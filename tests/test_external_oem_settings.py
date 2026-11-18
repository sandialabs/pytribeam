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
    "project_folder": "D:/AZtec projects",
}

BRUKER_DB = {"dll_dir": "C:/Program Files/Bruker/Esprit API"}


CAMERA_POSITIONS = {
    "ebsd_inserted_position_mm": 20.0,
    "ebsd_retracted_position_mm": 0.0,
}


def bruker_db(**values):
    """Return a Bruker_settings block; only dll_dir is required."""
    return {**deepcopy(BRUKER_DB), **values}


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

    @pytest.mark.parametrize("port", [None, "missing"])
    def test_edax_defaults_the_port(self, port):
        db = deepcopy(EDAX_DB)
        if port == "missing":
            del db["connection"]["port"]
        else:
            db["connection"]["port"] = port

        edax = factory.edax_config(db)

        assert edax.connection.port == Constants.edax_ipapi_default_port == 8301

    def test_edax_blank_port_passes_validation(self, laser, edax_reachable):
        db = deepcopy(EDAX_DB)
        db["connection"]["port"] = None

        assert validate("EDAX", "EDAX", version=1.1, edax_settings=db)

    def test_oxford_defaults_the_port_and_dll_dir(self):
        oxford = factory.oxford_config(OXFORD_DB)

        assert oxford.connection == tbt.MicroscopeConnection(
            host="aztec-pc", port=Constants.oxford_aztec_default_port
        )
        assert oxford.dll_dir is None
        assert oxford.project_folder == Path("D:/AZtec projects")

    def test_oxford_explicit_port_and_dll_dir(self):
        db = deepcopy(OXFORD_DB)
        db["connection"]["port"] = 30000
        db["dll_dir"] = "C:/AZtec/Plugin"

        oxford = factory.oxford_config(db)

        assert oxford.connection.port == 30000
        assert oxford.dll_dir == Path("C:/AZtec/Plugin")

    def test_bruker_defaults(self):
        bruker = factory.bruker_config(bruker_db())

        assert bruker == tbt.BrukerConfig(
            dll_dir=Path("C:/Program Files/Bruker/Esprit API"),
            mode=tbt.BrukerConnectionMode.LOCAL,
            host=None,
            port=None,
            detector_index=1,
            move_detector=False,
            ebsd_inserted_position_mm=None,
            ebsd_retracted_position_mm=None,
        )

    @pytest.mark.parametrize("value", [None, False])
    def test_bruker_move_detector_is_off_unless_set(self, value):
        """As an unticked GUI checkbox: never moves the detector by accident."""
        bruker = factory.bruker_config(bruker_db(move_detector=value))
        assert bruker.move_detector is False

    def test_bruker_camera_positions(self):
        bruker = factory.bruker_config(
            bruker_db(ebsd_inserted_position_mm=20.0, ebsd_retracted_position_mm=0)
        )
        assert (
            bruker.ebsd_inserted_position_mm,
            bruker.ebsd_retracted_position_mm,
        ) == (
            20.0,
            0,
        )

    def test_bruker_tcp(self):
        bruker = factory.bruker_config(
            bruker_db(
                mode="tcp",
                host="esprit-pc",
                port=5328,
                detector_index=2,
                move_detector=False,
            )
        )

        assert bruker.mode == tbt.BrukerConnectionMode.TCP
        assert (bruker.host, bruker.port) == ("esprit-pc", 5328)
        assert (bruker.detector_index, bruker.move_detector) == (2, False)


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
        assert validate(
            "Bruker", "Bruker", bruker_settings=bruker_db(**CAMERA_POSITIONS)
        )

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
            lambda db: db["connection"].update(port=0),
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

    @pytest.mark.parametrize("oems", [("Oxford", None), (None, "Oxford")])
    def test_native_oxford_needs_a_project_folder(self, laser, oems):
        db = deepcopy(OXFORD_DB)
        del db["project_folder"]

        with pytest.raises(ValueError, match="project_folder"):
            validate(*oems, oxford_settings=db)

    @pytest.mark.parametrize("key", ["ebsd_profile", "eds_profile"])
    def test_profiles_in_the_general_block_point_to_the_steps(self, laser, key):
        """Profiles moved to each step's oxford_settings."""
        db = {**deepcopy(OXFORD_DB), key: "pyTriBeam"}

        with pytest.raises(ValueError, match="each EBSD/EDS step's 'oxford_settings"):
            validate("Oxford", "Oxford", oxford_settings=db)

    @pytest.mark.parametrize(
        "change",
        [
            lambda db: db["connection"].update(host=""),
            lambda db: db["connection"].update(port=0),
            lambda db: db["connection"].pop("host"),
            lambda db: db.update(dll_dir=3),
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
        "change, match",
        [
            (lambda db: db.pop("dll_dir"), "dll_dir"),
            (lambda db: db.update(dll_dir=""), "dll_dir"),
            (lambda db: db.update(mode="usb"), "mode"),
            (lambda db: db.update(mode="tcp"), "needs a 'host'"),
            (lambda db: db.update(port=0), "port"),
            (lambda db: db.update(detector_index=0), "detector_index"),
            (lambda db: db.update(detector_index=5), "detector_index"),
            (lambda db: db.update(ebsd_inserted_position_mm=-1.0), "inserted"),
            (lambda db: db.update(ebsd_retracted_position_mm="0"), "retracted"),
            (lambda db: db.update(move_detector="yes"), "move_detector"),
            (lambda db: db.update(password="edx"), "Bruker_settings"),
        ],
    )
    def test_invalid_bruker_block_is_refused(self, laser, change, match):
        db = bruker_db()
        change(db)

        with pytest.raises(ValueError, match=match):
            validate("Bruker", "Bruker", bruker_settings=db)

    def test_bruker_ebsd_needs_the_camera_positions(self, laser):
        with pytest.raises(ValueError, match="measured positions"):
            validate("Bruker", "Bruker", bruker_settings=bruker_db())
        with pytest.raises(ValueError, match="measured positions"):
            validate(
                "Bruker",
                None,
                bruker_settings=bruker_db(ebsd_inserted_position_mm=20.0),
            )

    def test_bruker_eds_only_needs_no_positions(self, laser):
        assert validate(None, "Bruker", bruker_settings=bruker_db())

    def test_camera_positions_must_be_distinguishable(self, laser):
        db = bruker_db(ebsd_inserted_position_mm=0.05, ebsd_retracted_position_mm=0.0)

        with pytest.raises(ValueError, match="differ by more than"):
            validate("Bruker", None, bruker_settings=db)

    def test_tcp_with_a_host(self, laser):
        assert validate(
            "Bruker",
            "Bruker",
            bruker_settings=bruker_db(
                mode="tcp", host="esprit-pc", port=5328, **CAMERA_POSITIONS
            ),
        )


class TestBrukerStepSettings:
    """Per-step `bruker_settings`: output folder and map size/dwell."""

    V12 = ut.yml_format(version=1.2)
    V11 = ut.yml_format(version=1.1)

    def eds_block(self, **values):
        block = {
            "output_path": "C:/data/eds",
            "map": {"width_px": 512, "height_px": 384, "dwell_us": 1024},
        }
        block.update(values)
        return {"bruker_settings": block}

    def ebsd_block(self, **values):
        step = self.eds_block(profile_name="default", **values)
        return step

    def test_eds(self):
        step = factory.bruker_eds_step(self.eds_block(), "map_eds", self.V12)

        assert step == tbt.BrukerEDSStepSettings(
            output_path=Path("C:/data/eds"),
            map=tbt.BrukerMapSettings(512, 384, 1024),
            run_name="map_eds",
        )

    def test_ebsd(self):
        step = factory.bruker_ebsd_step(
            self.ebsd_block(save_patterns=True), "map_ebsd", self.V12
        )

        assert step.profile_name == "default"
        assert step.save_patterns is True
        assert step.run_name == "map_ebsd"
        assert step.map == tbt.BrukerMapSettings(512, 384, 1024)

    def test_ebsd_save_patterns_defaults_off(self):
        step = factory.bruker_ebsd_step(self.ebsd_block(), "map_ebsd", self.V12)
        assert step.save_patterns is False

    @pytest.mark.parametrize(
        "step_settings",
        [
            {},
            {"bruker_settings": None},
            {
                # as the GUI writes it, untouched
                "bruker_settings": {
                    "output_path": None,
                    "profile_name": None,
                    "map": {"width_px": None, "height_px": None, "dwell_us": None},
                    "save_patterns": False,
                }
            },
        ],
    )
    def test_absent_or_blank_is_none(self, step_settings):
        assert factory.bruker_eds_step(step_settings, "s", self.V12) is None
        assert factory.bruker_ebsd_step(step_settings, "s", self.V12) is None

    def test_older_formats_ignore_it(self):
        assert factory.bruker_eds_step(self.eds_block(), "s", self.V11) is None

    @pytest.mark.parametrize(
        "change, match",
        [
            (lambda b: b.pop("output_path"), "output_path"),
            (lambda b: b["map"].update(width_px=0), "map.width_px"),
            (lambda b: b["map"].update(dwell_us=1.5), "map.dwell_us"),
            (lambda b: b["map"].pop("height_px"), "height_px"),
        ],
    )
    def test_invalid_eds_block(self, change, match):
        step = self.eds_block()
        change(step["bruker_settings"])

        with pytest.raises(ValueError, match=match):
            factory.bruker_eds_step(step, "map_eds", self.V12)

    def test_ebsd_needs_a_profile(self):
        step = self.eds_block()  # no profile_name

        with pytest.raises(ValueError, match="profile_name"):
            factory.bruker_ebsd_step(step, "map_ebsd", self.V12)


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
                Bruker_settings=bruker_db(**CAMERA_POSITIONS),
            )
        )

        assert settings.Bruker_settings == factory.bruker_config(
            bruker_db(**CAMERA_POSITIONS)
        )
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


# --------------------------------------------
# Blank vendor blocks (as the GUI writes them)
# --------------------------------------------

BLANK_EDAX = {
    "connection": {"host": None, "port": None},
    "save_directory": None,
    "project_name": "",
}


class TestVendorBlockSelection:
    """Which general vendor blocks count as configured.

    The GUI writes every block it knows, often with defaults such as ports, so
    a block is used only when its vendor is an OEM of the experiment and its
    key field (host, or Bruker's dll_dir) is filled in.
    """

    def db(self, ebsd_oem=None, eds_oem=None, **blocks):
        return {"EBSD_OEM": ebsd_oem, "EDS_OEM": eds_oem, **deepcopy(blocks)}

    def test_used_when_its_vendor_is_an_oem_and_the_key_field_is_set(self):
        db = self.db("EDAX", "EDAX", EDAX_settings=EDAX_DB)
        assert factory.vendor_block(db, "EDAX_settings") == EDAX_DB

    @pytest.mark.parametrize(
        "name, block",
        [
            ("EDAX_settings", EDAX_DB),
            ("Bruker_settings", bruker_db(port=5328)),
            ("Bruker_settings", {"dll_dir": None, "mode": "usb", "port": -1}),
        ],
    )
    def test_other_vendors_blocks_are_ignored(self, name, block):
        """Reported from the GUI: an Oxford pipeline failed on its Bruker block."""
        db = self.db("Oxford", "Oxford", **{name: block})
        assert factory.vendor_block(db, name) is None

    @pytest.mark.parametrize("oems", [("EDAX", None), (None, "EDAX")])
    def test_either_technique_counts(self, oems):
        db = self.db(*oems, EDAX_settings=EDAX_DB)
        assert factory.vendor_block(db, "EDAX_settings") is not None

    @pytest.mark.parametrize(
        "name, block",
        [
            ("EDAX_settings", BLANK_EDAX),
            ("EDAX_settings", {"connection": {"host": None, "port": 8301}}),
            ("Oxford_settings", {"connection": {"host": "", "port": 22201}}),
            (
                "Bruker_settings",
                {"dll_dir": None, "port": 5328, "move_detector": False},
            ),
        ],
    )
    def test_a_default_filled_block_without_its_key_field_is_unused(self, name, block):
        oem = {"EDAX_settings": "EDAX", "Oxford_settings": "Oxford"}.get(name, "Bruker")
        db = self.db(oem, oem, **{name: block})
        assert factory.vendor_block(db, name) is None

    def test_partly_filled_without_the_key_field_warns(self):
        db = self.db(
            "EDAX",
            "EDAX",
            EDAX_settings={"connection": {"host": None}, "project_name": "exp1"},
        )

        with pytest.warns(UserWarning, match="connection.host"):
            assert factory.vendor_block(db, "EDAX_settings") is None

    def test_edax_with_only_a_default_port_falls_back_to_laser_control(self, laser):
        laser(True)
        db = self.db("EDAX", "EDAX", EDAX_settings={"connection": {"port": 8301}})

        edax = factory.vendor_block(db, "EDAX_settings")

        assert edax is None
        assert validate("EDAX", "EDAX", version=1.1, edax_settings=edax)


class TestStepBlocks:
    """Step-level vendor blocks apply only to their technique's OEM."""

    @pytest.mark.parametrize(
        "technique, oem, expected",
        [
            (tbt.ExternalTechnique.EDS, OEM.BRUKER, True),
            (tbt.ExternalTechnique.EDS, OEM.EDAX, False),
            (tbt.ExternalTechnique.EBSD, OEM.EDAX, True),
            (tbt.ExternalTechnique.EBSD, OEM.BRUKER, False),
        ],
    )
    def test_step_uses(self, technique, oem, expected):
        settings = built_settings(OEM.EDAX, OEM.BRUKER)
        assert factory.step_uses(settings, technique, oem) is expected

    def test_without_general_settings_every_block_is_read(self):
        assert factory.step_uses(None, tbt.ExternalTechnique.EDS, OEM.BRUKER)

    @pytest.fixture
    def eds_factory(self, monkeypatch):
        """factory.eds with the microscope-dependent image parsing stubbed out."""
        monkeypatch.setattr(factory, "enforce_beam_type", lambda *a, **k: True)
        monkeypatch.setattr(factory, "image", lambda **kwargs: None)

        def make(general_settings, step_settings):
            return factory.eds(
                microscope=None,
                step_settings=step_settings,
                step_name="map_eds",
                yml_format=ut.yml_format(version=1.2),
                general_settings=general_settings,
            )

        return make

    def eds_step(self):
        return {
            # invalid for Bruker, as left over from an earlier Bruker setup
            "bruker_settings": {"output_path": "C:/data", "map": {"width_px": 0}},
            "edax_settings": {"resolution": "512x400", "num_frames": 2, "dwell_us": 50},
            "oxford_settings": {"profile": "EDS 512px 50us"},
        }

    def test_an_oxford_eds_step_reads_only_its_oxford_block(self, eds_factory):
        settings = built_settings(OEM.OXFORD, OEM.OXFORD)

        eds = eds_factory(settings, self.eds_step())

        assert eds.bruker is None and eds.edax is None
        assert eds.oxford == tbt.OxfordStepSettings(
            profile="EDS 512px 50us", run_name="map_eds"
        )

    def test_an_edax_eds_step_reads_only_its_edax_block(self, eds_factory):
        settings = built_settings(OEM.NONE, OEM.EDAX)

        eds = eds_factory(settings, self.eds_step())

        assert eds.bruker is None and eds.oxford is None
        assert eds.edax == tbt.EdaxEDSStepSettings("512x400", 2, 50.0)

    def test_a_bruker_eds_step_validates_its_block(self, eds_factory):
        settings = built_settings(OEM.NONE, OEM.BRUKER)

        with pytest.raises(ValueError, match="map"):
            eds_factory(settings, self.eds_step())


class TestOxfordStep:
    V12 = ut.yml_format(version=1.2)

    def test_profile(self):
        step = factory.oxford_step(
            {"oxford_settings": {"profile": "EBSD 1um step"}}, "ebsd_1", self.V12
        )
        assert step == tbt.OxfordStepSettings(
            profile="EBSD 1um step", run_name="ebsd_1"
        )

    def test_the_export_folder_is_not_a_step_setting(self):
        """Exports go to the experiment's AZtec project (Oxford_settings)."""
        with pytest.raises(ValueError, match="oxford_settings"):
            factory.oxford_step(
                {"oxford_settings": {"profile": "x", "output_path": "D:/out"}},
                "s",
                self.V12,
            )

    @pytest.mark.parametrize(
        "step_settings", [{}, {"oxford_settings": {"profile": None}}]
    )
    def test_absent_or_blank_is_none(self, step_settings):
        assert factory.oxford_step(step_settings, "s", self.V12) is None

    def test_older_formats_ignore_it(self):
        step_settings = {"oxford_settings": {"profile": "x"}}
        assert factory.oxford_step(step_settings, "s", ut.yml_format(1.1)) is None

    @pytest.mark.parametrize(
        "block",
        [{"profile": 3}, {"profile": "x", "extra": 1}],
    )
    def test_invalid(self, block):
        with pytest.raises(ValueError, match="oxford_settings"):
            factory.oxford_step({"oxford_settings": block}, "s", self.V12)


class TestEdaxEdsStep:
    V12 = ut.yml_format(version=1.2)

    def test_all_fields(self):
        step = factory.edax_eds_step(
            {
                "edax_settings": {
                    "resolution": "1024x800",
                    "num_frames": 4,
                    "dwell_us": 100,
                }
            },
            "s",
            self.V12,
        )
        assert step == tbt.EdaxEDSStepSettings("1024x800", 4, 100.0)

    def test_blank_fields_keep_apex_values(self):
        step = factory.edax_eds_step(
            {
                "edax_settings": {
                    "resolution": "256x200",
                    "num_frames": None,
                    "dwell_us": "",
                }
            },
            "s",
            self.V12,
        )
        assert step == tbt.EdaxEDSStepSettings("256x200", None, None)

    @pytest.mark.parametrize(
        "step_settings",
        [
            {},
            {"edax_settings": {"resolution": "", "num_frames": None, "dwell_us": None}},
        ],
    )
    def test_absent_or_blank_is_none(self, step_settings):
        assert factory.edax_eds_step(step_settings, "s", self.V12) is None

    def test_older_formats_ignore_it(self):
        step_settings = {"edax_settings": {"num_frames": 2}}
        assert factory.edax_eds_step(step_settings, "s", ut.yml_format(1.1)) is None

    def test_resolutions_are_the_edax_presets(self):
        assert factory.edax_eds_resolutions()[0] == "64x50"
        assert "4096x3200" in factory.edax_eds_resolutions()

    @pytest.mark.parametrize(
        "block, match",
        [
            ({"resolution": "500x400"}, "resolution"),
            ({"num_frames": 0}, "num_frames"),
            ({"num_frames": True, "resolution": "512x400"}, "num_frames"),
            ({"dwell_us": -5}, "dwell_us"),
        ],
    )
    def test_invalid(self, block, match):
        with pytest.raises(ValueError, match=match):
            factory.edax_eds_step({"edax_settings": block}, "s", self.V12)
