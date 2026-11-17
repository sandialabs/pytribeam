import os
import sys
import threading

from pythonnet import load

load("netfx")

import clr

PLUGIN_DIR = r"C:\Program Files\Oxford Instruments NanoAnalysis\Plugin"

sys.path.append(PLUGIN_DIR)

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(PLUGIN_DIR)

clr.AddReference("OINA.Plugin.AcquisitionClient")

from OINA.Plugin.AcquisitionClient import (
    AcquisitionType,
    AutoLockMode,
    Session,
)


class AztecPluginClient:
    def __init__(self, host="127.0.0.1", port=22201):
        self.connection_string = f"{host}:{port}"
        self.session = None
        self.client = None
        self.finished_event = threading.Event()
        self.last_status = None

    def connect(self):
        self.session = Session.Connect(self.connection_string)
        return self

    def acquire_client(self):
        if self.session is None:
            raise RuntimeError("Session is not connected.")

        self.client = self.session.GetAcquisitionClient()
        self.client.Finished += self._on_finished
        self.client.ProgressChanged += self._on_progress_changed
        return self.client

    def release_client(self):
        if self.client is not None:
            try:
                self.client.Finished -= self._on_finished
                self.client.ProgressChanged -= self._on_progress_changed
            except Exception:
                pass

            try:
                self.session.ReleaseAcquisitionClient(self.client)
            finally:
                self.client = None

    def disconnect(self):
        try:
            self.release_client()
        finally:
            if self.session is not None:
                Session.Disconnect(self.session)
                self.session = None

    def acquire_eds_map(self, name=None, site_name=None, wait=True):
        return self._start_acquisition(
            acquisition_type=AcquisitionType.EdsMap,
            name=name,
            site_name=site_name,
            wait=wait,
        )

    def acquire_ebsd_map(self, name=None, site_name=None, wait=True):
        return self._start_acquisition(
            acquisition_type=AcquisitionType.EbsdMap,
            name=name,
            site_name=site_name,
            wait=wait,
        )

    def acquire_electron_image_and_eds_map(self, name=None, site_name=None, wait=True):
        acquisition_type = AcquisitionType.ElectronImage | AcquisitionType.EdsMap

        return self._start_acquisition(
            acquisition_type=acquisition_type,
            name=name,
            site_name=site_name,
            wait=wait,
        )

    def acquire_electron_image_and_ebsd_map(self, name=None, site_name=None, wait=True):
        acquisition_type = AcquisitionType.ElectronImage | AcquisitionType.EbsdMap

        return self._start_acquisition(
            acquisition_type=acquisition_type,
            name=name,
            site_name=site_name,
            wait=wait,
        )

    def _start_acquisition(
        self, acquisition_type, name=None, site_name=None, wait=True
    ):
        if self.client is None:
            self.acquire_client()

        self.finished_event.clear()
        self.last_status = None

        self.client.AcquisitionType = acquisition_type

        if site_name is None:
            self.client.SiteName = self.client.CurrentSite
        else:
            self.client.SiteName = site_name

        if name is None:
            self.client.StartAcquisition()
        else:
            self.client.StartAcquisition(name)

        if wait:
            self.finished_event.wait()
            return self.last_status

        return None

    def stop_acquisition(self):
        if self.client is None:
            raise RuntimeError("No acquisition client is active.")

        self.client.StopAcquisition()

    def set_autolock_off(self):
        if self.client is None:
            self.acquire_client()

        self.client.AutoLockMode = AutoLockMode.Off

    def set_autolock_auto(self):
        if self.client is None:
            self.acquire_client()

        self.client.AutoLockMode = AutoLockMode.Auto

    def _on_finished(self, sender, args):
        status = args.AcquisitionStatus
        self.last_status = status

        print(f"Acquisition finished. State: {status.State}")
        print(f"Message: {status.Message}")

        if status.Error is not None:
            print(f"Error: {status.Error.Message}")

        self.finished_event.set()

    def _on_progress_changed(self, sender, args):
        progress = args.AcquisitionProgress
        print(
            f"Progress: {progress.ProgressPercentage}% "
            f"ETA: {progress.EstimatedSecondsToCompletion} s"
        )

    def __enter__(self):
        self.connect()
        self.acquire_client()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()
