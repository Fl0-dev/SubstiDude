# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Budgets initiaux choisis sur délégation utilisateur ; pas un standard PDF."""

MIB = 1024 * 1024
MAX_RESOURCE_STREAM_BYTES = 32 * MIB
MAX_IMAGE_STREAM_BYTES = 128 * MIB
MAX_TOTAL_DECODED_STREAM_BYTES = 256 * MIB
MAX_RENDER_PIXELS = 16_000_000
# Appliqués au banc Windows et au worker applicatif PDFJob, pas aux appels directs.
MAX_PDF_PROCESS_BYTES = 2 * 1024 * MIB
MAX_JOB_SECONDS = 60
MAX_IPC_BYTES = 64 * MIB
