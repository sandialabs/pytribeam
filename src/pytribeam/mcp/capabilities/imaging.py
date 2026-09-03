#!/usr/bin/python3
"""
Imaging Capabilities
====================

Capabilities that set imaging conditions and acquire images.

Same rule as ``stage.py``: wrappers, not workflows. Ordering and safety
sequencing live in ``pytribeam.workflow``.

Acquired images are returned as resource references plus a downsampled
preview. Full frames are never inlined into a response.

Work package 4.
"""
