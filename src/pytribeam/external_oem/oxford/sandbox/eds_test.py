from aztec_wrapper import AztecPluginClient

with AztecPluginClient(host="127.0.0.1", port=22201) as aztec:
    status = aztec.acquire_eds_map(
        name="Python EDS Map Test",
        site_name=None,
        wait=True,
    )

    print(status.State)
