import time
import socket

from pytribeam import log
from pytribeam import image as img
from pytribeam import types as tbt
from pytribeam.constants import Constants, Conversions
from pytribeam.external_oem.com import socket_command, socket_response, parse_socket_response



def configure_scan(connection: socket.socket, settings: tbt.EBSDSettings) -> bool:
    # patterns
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_savepatterns "{settings.save_patterns}"',
        expected_response='set_ebsd_params_savepatterns response "execution successful"',
    )
    # grid type
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_grid "{settings.grid_type}"',
        expected_response='set_ebsd_params_grid response "execution successful"',
    )
    # resolution
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_resolution "3"',
        expected_response='set_ebsd_params_resolution response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_customstepsize "{settings.scan_box.step_size_um}"',
        expected_response='set_ebsd_params_customstepsize response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_stepsize "{settings.scan_box.step_size_um}"',
        expected_response='set_ebsd_params_stepsize response "execution successful"',
    )
    # simulataneous EDS
    if settings.enable_eds:
        socket_command(
            connection=connection,
            command=f'set_ebsd_params_savespectra "{settings.enable_eds}"',
            expected_response='set_ebsd_params_savespectra response "execution successful"',
        )

    # start x and Y
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_ystart "{settings.scan_box.y_start_um}"',
        expected_response='set_ebsd_params_ystart response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_xstart "{settings.scan_box.x_start_um}"',
        expected_response='set_ebsd_params_xstart response "execution successful"',
    )

    # size x and Y
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_ysize "{settings.scan_box.y_size_um}"',
        expected_response='set_ebsd_params_ysize response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_xsize "{settings.scan_box.x_size_um}"',
        expected_response='set_ebsd_params_xsize response "execution successful"',
    )


def preflight(
    general_settings: tbt.GeneralSettings,
) -> bool:
    """EDAX only for now"""
    # TODO confirm the user is done befopre continuing

    edax_settings = general_settings.EDAX_settings

    connection = connect_EDAX(
        edax_settings.connection.host,
        edax_settings.connection.port,
    )

    folder = edax_settings.save_directory
    project_name = edax_settings.project_name
    guid = Constants.EDAX_GUID
    max_slice_number = general_settings.max_slice_number
    slice_thickness_um = general_settings.slice_thickness_um

    # EBSD preflight
    # folder locations and mapping
    socket_command(
        connection=connection,
        command='set_system_remoteaccesstype_ebsd "1"',
        expected_response='set_system_remoteaccesstype_ebsd response "execution successful"',
        timeout_s=5.0,
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_folderpath "{folder}"',
        expected_response='set_ebsd_params_folderpath response "execution successful"',
        pause_s=0.0,
    )
    socket_command(
        connection=connection,
        command=f'set_system_projectinfo_ext_ebsd "{guid}","{project_name}","{max_slice_number}","{slice_thickness_um}"',
        expected_response='set_system_projectinfo_ext_ebsd response "execution successful"',
        pause_s=0.0,
        timeout_s=120.0,
    )
    # socket_command(
    #     connection=connection,
    #     command=f"do_map_setup_start_ebsd",
    #     expected_response='do_map_setup_start_ebsd response "execution successful"',
    #     pause_s=0.0,
    #     timeout_s=60.0,
    # )
    disconnect_EDAX(connection=connection)
    return True


def connect_EDAX(ebsd_host: str, ebsd_port: int) -> socket.socket:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = ebsd_host
    port = ebsd_port
    connection.connect((host, port))
    print(f"\tConnected to {host}:{port}")
    # unlock and enable remote access
    socket_command(
        connection=connection,
        command="edax_unlock",
        expected_response="client connection accepted",
    )
    return connection


def disconnect_EDAX(connection: socket.socket) -> bool:
    connection.close()
    return True


def camera_saturation(
    microscope: tbt.Microscope,
    connection: socket.socket,
    hfw_mm=Constants.ebsd_camera_saturation_hfw_mm,
    delay_s=Constants.ebsd_camera_saturation_delay_s,
) -> float:
    """Measures the (EDAX) EBSD detector saturation. Returns in range [0,1]"""
    img.set_beam_device(
        microscope=microscope,
        device=tbt.Device.ELECTRON_BEAM,
    )
    initial_hfw_m = microscope.beams.electron_beam.horizontal_field_width.value
    initial_detector = tbt.DetectorType(microscope.detector.type.value)

    img.detector_type(microscope=microscope, detector=tbt.DetectorType.ETD)
    img.beam_hfw(
        beam=tbt.ElectronBeam(settings=tbt.BeamSettings()),
        microscope=microscope,
        hfw_mm=hfw_mm,
    )
    microscope.imaging.start_acquisition()
    time.sleep(delay_s)
    command = "get_camera_saturation"
    camera_saturation = socket_command(
        connection=connection,
        command=command,
        expected_response=None,
    )
    microscope.imaging.stop_acquisition()

    # reset detector and hfw
    img.detector_type(microscope=microscope, detector=initial_detector)
    img.beam_hfw(
        beam=tbt.ElectronBeam(settings=tbt.BeamSettings()),
        microscope=microscope,
        hfw_mm=initial_hfw_m * Conversions.M_TO_MM,
    )
    microscope.imaging.start_acquisition()
    time.sleep(delay_s)
    microscope.imaging.stop_acquisition()

    camera_saturation = float(parse_socket_response(camera_saturation, command))

    return float(camera_saturation)


def average_ci(connection: socket.socket) -> float:
    """Get the average confidence of the most recent scan."""
    command = "get_map_avg_ci"
    average_ci = socket_command(
        connection=connection,
        command=command,
        expected_response=None,
        timeout_s=60.0,
    )
    average_ci = float(parse_socket_response(average_ci, command))
    return average_ci


def insert_camera(connection=socket.socket):
    camera_status = socket_command(
        connection=connection,
        command="get_camera_status",
        expected_response=None,
        timeout_s=60.0,
    )
    if "slidein" in camera_status:
        # print("Slide is already in")
        return True
    print("\tInserting EDAX EBSD camera...")
    socket_command(
        connection=connection,
        command="do_map_insert_camera",
        expected_response='do_map_insert_camera response "execution successful"',
    )
    time.sleep(10.0)
    while True:
        response = socket_command(
            connection=connection,
            command="get_camera_status",
            expected_response=None,
            timeout_s=60.0,
        )
        # print("Camera status:", response)
        if response is None:
            pass
        elif "slidein" in response:
            break
        time.sleep(2.0)
    print("\tEDAX EBSD camera inserted")
    return True


def retract_camera(connection=socket.socket):
    camera_status = socket_command(
        connection=connection,
        command="get_camera_status",
        expected_response=None,
        timeout_s=60.0,
    )
    if "slideout" in camera_status:
        # print("Slide is already out")
        return True
    print("\tRetracting EDAX EBSD camera...")
    socket_command(
        connection=connection,
        command="do_map_retract_camera",
        expected_response='do_map_retract_camera response "execution successful"',
    )
    time.sleep(10.0)
    while True:
        response = socket_command(
            connection=connection,
            command="get_camera_status",
            expected_response=None,
            timeout_s=60.0,
        )
        # print("Camera status:", response)
        if response is None:
            pass
        elif "slideout" in response:
            break
        elif "slidemovewdog" in response:
            socket_command(
                connection=connection,
                command="do_map_retract_camera",
                expected_response='do_map_retract_camera response "execution successful"',
                timeout_s=60.0,
            )
        elif "slidewatchdog" in response:
            raise RuntimeError(
                "EBSD camera is in indeterminate state. Please manually adjust and restart."
            )
        time.sleep(2.0)
    print("\tEDAX EBSD camera retracted")
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    step: tbt.Step,
) -> bool:

    # Make connection
    connection = connect_EDAX(
        general_settings.EDAX_settings.connection.host,
        general_settings.EDAX_settings.connection.port,
    )

    # Set APEX variables properly
    configure_scan(
        connection=connection,
        settings=step_settings,
    )
    # Grab the camera saturation and log it
    cam_sat_p = camera_saturation(
        microscope=step_settings.image.microscope,
        connection=connection,
    )
    log.ebsd_camera_saturation(
        step_number=step.number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=Constants.ebsd_camera_saturation_dataset_name,
        cam_sat_p=cam_sat_p,
    )

    # Predict duration
    n_ticks = socket_command(
        connection=connection,
        command="get_map_duration_ebsd",
        expected_response=None,
    )
    n_ticks = float(parse_socket_response(n_ticks, "get_map_duration_ebsd"))
    expected_duration_s = n_ticks / 10000000 + Constants.edax_map_start_delay_s

    # Start scan and wait for expected duration
    socket_command(
        connection=connection,
        command=f'do_map_collection_start_ebsd "Slice_{slice_number:04}"',
        expected_response='do_map_collection_start_ebsd response "execution successful"',
    )
    scan_start_time = time.time()
    print(f"\tEBSD map started...")
    time.sleep(Constants.edax_map_start_delay_s)

    # Check map status every second to see when it finishes
    timeout = expected_duration_s * Constants.edax_timeout_scalar
    while True:
        map_status = socket_command(
            connection=connection,
            command=f"get_map_status_ebsd",
            expected_response=None,
            pause_s=1.0,
            timeout_s=120.0,
        )
        # map_status should return a string with "get_map_status_ebsd", the command that was originally sent
        # however, it is possible for it to return "event_map_collection_complete_ebsd mapping complete" instead due to the scan finishing
        # check to make sure it is one of those two
        if "get_map_status_ebsd" in map_status:
            map_status = parse_socket_response(map_status, "get_map_status_ebsd")
        elif "event_map_collection_complete_ebsd" in map_status:
            map_status = parse_socket_response(
                map_status, "event_map_collection_complete_ebsd"
            )
        else:
            raise RuntimeError(
                f"EDAX IPAPI returned an unexpected response. Please make sure the software is operating properly. Response: {map_status}"
            )

        # Check if the map status command is timed out (None) or if the map collection did not finish in time
        if map_status is None:
            # The IPAPI server did not respond in time. Try again.
            pass
        elif time.time() - scan_start_time > timeout:
            disconnect_EDAX(connection=connection)
            raise RuntimeError(
                f"EDAX EBSD Map did not complete within {timeout:.0f} seconds, aborting."
            )

        # We received a valid response, check the status
        map_status = tbt.EdaxMappingStatus(map_status)
        if map_status == tbt.EdaxMappingStatus.READY:
            # The map finished successfully
            print("\t\tMapping complete")
            break
        elif map_status == tbt.EdaxMappingStatus.MAPPING_COMPLETE:
            # The map finished successfully, but there might be a second message of "ready" coming"
            print("\t\tMapping complete")
            socket_response(
                connection=connection,
                timeout_s=10.0,
            )
            break
        time.sleep(Constants.edax_map_status_interval_s)

    # Record end time
    end_time = time.time()

    # Grab the average CI value and put in log
    avg_ci_p = average_ci(connection=connection)
    log.ebsd_average_ci(
        step_number=step.number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=Constants.ebsd_average_ci_dataset_name,
        avg_ci_p=avg_ci_p,
    )
    time.sleep(1.0)

    # Retract the EBSD camera
    retract_camera(connection=connection)

    # Disconnect socket to EDAX IPAPI
    disconnect_EDAX(connection=connection)

    # Check if the map was too quick
    actual_duration_s = end_time - scan_start_time
    if actual_duration_s < expected_duration_s:
        raise RuntimeError(
            f"EDAX EBSD map finished unexpectedly quickly. Expected duration was {expected_duration_s:.0f} seconds (actual duration was {actual_duration_s:.0f} seconds). Please check the EDAX software."
        )

    return True