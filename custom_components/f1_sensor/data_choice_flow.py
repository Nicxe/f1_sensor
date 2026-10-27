"""Review voluntary sensor reductions without requiring an upgrade choice."""

from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .runtime import effective_entry_settings


class SensorSelectionFlow:
    """Preserve existing selections and review explicit entity removals."""

    async def _async_review_sensor_changes(self, entry, checked, finish):
        from .config_flow import _build_sensor_options

        sensor_options = _build_sensor_options()
        previous = set(sensor_options) - set(
            effective_entry_settings(entry).get("disabled_sensors", [])
        )
        removed = sorted(previous - set(checked))
        if not removed:
            return finish()
        self._sensor_review_finish = finish
        self._sensor_review_removed = ", ".join(sensor_options[key] for key in removed)
        return await self.async_step_sensor_review()

    async def async_step_sensor_review(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get("confirm") is True:
                return self._sensor_review_finish()
            errors["confirm"] = "confirmation_required"
        return self.async_show_form(
            step_id="sensor_review",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=False): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders={"removed_sensors": self._sensor_review_removed},
        )
