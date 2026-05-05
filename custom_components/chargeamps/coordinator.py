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
        self._total_energy_max: dict[str, float] = {}
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

                # Calculate total energy — use a high watermark so the sensor doesn't
                # drop to 0 between sessions (total_consumption_kwh resets per session).
                live_total = round(sum(cs.total_consumption_kwh for cs in status.connector_statuses), 2)
                prev_max = self._total_energy_max.get(cp.id, 0.0)
                if live_total > prev_max:
                    self._total_energy_max[cp.id] = live_total
                data["total_energy"][cp.id] = self._total_energy_max[cp.id]

            # Process all charge points in parallel
            await asyncio.gather(*(fetch_cp_data(cp) for cp in chargepoints))

            return data
        except Exception as error:
            _LOGGER.exception("Error updating Chargeamps data")
            raise UpdateFailed(f"Error communicating with API: {error}") from error

    async def recalculate_total_energy(self, charge_point_id: str) -> float:
        """Recompute total energy from the full session history in the Charge Amps API.

        Sums all completed sessions plus any ongoing session energy from the live
        status, then updates the high watermark so subsequent polls don't overwrite it.
        """
        sessions = await self.client.get_all_chargingsessions(charge_point_id)
        completed_ids = {s.id for s in sessions if s.end_time is not None}
        completed_total = sum(s.total_consumption_kwh for s in sessions if s.end_time is not None)

        # Add energy for any active session not yet recorded as completed
        active_total = 0.0
        status = self.data["status"].get(charge_point_id)
        if status:
            for cs in status.connector_statuses:
                if cs.session_id not in completed_ids:
                    active_total += cs.total_consumption_kwh or 0.0

        total = round(completed_total + active_total, 2)
        self._total_energy_max[charge_point_id] = max(total, self._total_energy_max.get(charge_point_id, 0.0))
        self.data["total_energy"][charge_point_id] = self._total_energy_max[charge_point_id]
        self.async_set_updated_data(self.data)
        _LOGGER.info("Recalculated total energy for %s: %.2f kWh", charge_point_id, self._total_energy_max[charge_point_id])
        return self._total_energy_max[charge_point_id]
