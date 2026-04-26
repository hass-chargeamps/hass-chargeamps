"""DataUpdateCoordinator for Chargeamps integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    ChargeAmpsClient,
    ChargePoint,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ChargeAmpsDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Chargeamps data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ChargeAmpsClient,
        update_interval: timedelta,
        chargepoint_ids: list[str] | None = None,
    ) -> None:
        """Initialize."""
        self.client = client
        self._chargepoint_ids = chargepoint_ids or []
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.data: dict[str, Any] = {
            "chargepoints": {},
            "status": {},
            "settings": {},
            "connector_settings": {},
            "total_energy": {},
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            all_chargepoints = await self.client.get_chargepoints()
            chargepoints = (
                [cp for cp in all_chargepoints if cp.id in self._chargepoint_ids] if self._chargepoint_ids else all_chargepoints
            )
            data: dict[str, Any] = {
                "chargepoints": {cp.id: cp for cp in chargepoints},
                "status": {},
                "settings": {},
                "connector_settings": {},
                "total_energy": {},
            }

            async def fetch_cp_data(cp: ChargePoint):
                """Fetch all data for a single charge point in parallel."""
                status_task = self.client.get_chargepoint_status(cp.id)
                settings_task = self.client.get_chargepoint_settings(cp.id)

                status, settings = await asyncio.gather(status_task, settings_task)

                data["status"][cp.id] = status
                data["settings"][cp.id] = settings

                # Fetch connector settings in parallel
                conn_settings_tasks = [
                    self.client.get_chargepoint_connector_settings(cp.id, conn.connector_id) for conn in cp.connectors
                ]
                conn_settings_results = await asyncio.gather(*conn_settings_tasks)
                for i, conn in enumerate(cp.connectors):
                    data["connector_settings"][(cp.id, conn.connector_id)] = conn_settings_results[i]

                # Calculate total energy from connector statuses (more efficient than fetching all sessions)
                total_energy = sum(conn_status.total_consumption_kwh for conn_status in status.connector_statuses)
                data["total_energy"][cp.id] = round(total_energy, 2)

            # Process all charge points in parallel
            await asyncio.gather(*(fetch_cp_data(cp) for cp in chargepoints))

            return data
        except Exception as error:
            _LOGGER.exception("Error updating Chargeamps data")
            raise UpdateFailed(f"Error communicating with API: {error}") from error
