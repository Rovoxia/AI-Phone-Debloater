#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Phone-Debloater — Remembered Device Registry
===============================================
Manages non-sensitive persistent device records for returning users and auto-reconnection.
Security invariant: NEVER stores pairing codes, passwords, or private keys.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .models import DeviceInfo, RememberedDevice

logger = logging.getLogger("rovoxia.connection.device_registry")

DEFAULT_REGISTRY_DIR = Path.home() / ".ai-phone-debloater"
FALLBACK_REGISTRY_DIR = Path.home() / "AiPhoneDebloater"
REGISTRY_FILENAME = "known_devices.json"


class DeviceRegistry:
    """Persistent storage for remembered Android devices."""

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        registry_file: Optional[Path] = None,
    ) -> None:
        if registry_file:
            self.file_path = Path(registry_file)
            self.registry_dir = self.file_path.parent
        elif storage_dir:
            self.registry_dir = Path(storage_dir)
            self.file_path = self.registry_dir / REGISTRY_FILENAME
        else:
            self.registry_dir = DEFAULT_REGISTRY_DIR
            self.file_path = self.registry_dir / REGISTRY_FILENAME
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        try:
            self.registry_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.debug(f"Could not create primary registry dir {self.registry_dir}: {exc}")
            self.registry_dir = FALLBACK_REGISTRY_DIR
            self.file_path = self.registry_dir / REGISTRY_FILENAME
            try:
                self.registry_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def load_all(self) -> List[RememberedDevice]:
        """Load all remembered devices from disk."""
        if not self.file_path.is_file():
            return []

        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return [RememberedDevice.from_dict(d) for d in data if isinstance(d, dict)]
        except (OSError, ValueError) as exc:
            logger.warning(f"Error loading device registry {self.file_path}: {exc}")
            return []

    def save_all(self, devices: List[RememberedDevice]) -> bool:
        """Persist device records atomically to disk."""
        self._ensure_dir()
        tmp_file = self.file_path.with_suffix(".tmp")
        try:
            records = [d.to_dict() for d in devices]
            with tmp_file.open("w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            os.replace(tmp_file, self.file_path)
            return True
        except OSError as exc:
            logger.error(f"Failed to save device registry {self.file_path}: {exc}")
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass
            return False

    def get(self, physical_id: str) -> Optional[RememberedDevice]:
        """Look up a remembered device by its physical ID."""
        if not physical_id:
            return None
        for dev in self.load_all():
            if dev.physical_id == physical_id:
                return dev
        return None

    def remember(self, info: DeviceInfo, friendly_name: Optional[str] = None) -> RememberedDevice:
        """
        Record or update a successfully connected device.
        Never stores passwords, pairing codes, or private keys.
        """
        devices = self.load_all()
        pid = info.physical_id or info.serial
        now_iso = datetime.now(timezone.utc).isoformat()

        name = friendly_name or (
            f"{info.manufacturer} {info.model}".strip() if info.model else info.serial
        )

        existing = next((d for d in devices if d.physical_id == pid), None)
        if existing:
            existing.manufacturer = info.manufacturer or existing.manufacturer
            existing.model = info.model or existing.model
            existing.last_transport = info.transport_type
            existing.last_endpoint = info.endpoint or (info.serial if info.is_wireless() else "")
            existing.last_connected = now_iso
            if friendly_name:
                existing.friendly_name = friendly_name
            record = existing
        else:
            record = RememberedDevice(
                physical_id=pid,
                friendly_name=name,
                manufacturer=info.manufacturer,
                model=info.model,
                last_transport=info.transport_type,
                last_endpoint=info.endpoint or (info.serial if info.is_wireless() else ""),
                last_connected=now_iso,
                auto_reconnect=True,
            )
            devices.append(record)

        self.save_all(devices)
        logger.info(f"Remembered device: {record.friendly_name} ({record.physical_id})")
        return record

    def forget(self, physical_id: str) -> bool:
        """Remove a device from remembered devices."""
        devices = self.load_all()
        filtered = [d for d in devices if d.physical_id != physical_id]
        if len(filtered) != len(devices):
            self.save_all(filtered)
            logger.info(f"Forgot device with physical ID: {physical_id}")
            return True
        return False

    def set_friendly_name(self, physical_id: str, new_name: str) -> bool:
        """Update friendly name for a device."""
        devices = self.load_all()
        for dev in devices:
            if dev.physical_id == physical_id:
                dev.friendly_name = new_name.strip()
                self.save_all(devices)
                return True
        return False

    def clear(self) -> bool:
        """Clear all remembered devices."""
        return self.save_all([])
