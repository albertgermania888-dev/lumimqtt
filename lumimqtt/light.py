"""
LUMI light control
"""
import asyncio as aio
import colorsys
import logging
import os
import typing as ty

from .device import Device

logger = logging.getLogger(__name__)


class LED(Device):
    """
    LED control
    """
    def __init__(self, name, device_dir):
        brightness_dev = os.path.join(device_dir, 'brightness')
        super().__init__(name, brightness_dev)
        self.brightness = int(self.read_raw(self.device_file))
        max_brightness_dev = os.path.join(device_dir, 'max_brightness')
        self.max_brightness = int(self.read_raw(max_brightness_dev))

    async def write(self, value: int):
        with open(self.device_file, 'w') as f:
            f.write(f'{value}\n')


class Light(Device):
    """
    Light control
    """
    COLOR_MODE = 'rgb'
    BRIGHTNESS = True
    EFFECT = True
    EFFECT_LIST = ["Police", "Rainbow", "Strobe", "Blink"]

    def __init__(self, name, devices: dict, topic):
        super().__init__(name, None, topic)
        self._effect_task = None
        self.red = LED(f'{name}_red', devices['red'])
        self.green = LED(f'{name}_green', devices['green'])
        self.blue = LED(f'{name}_blue', devices['blue'])

        self.leds = {
            'r': self.red,
            'g': self.green,
            'b': self.blue,
        }

        self.state: ty.Dict[str, ty.Any] = {
            'state': 'ON' if any((self.red.brightness,
                                 self.green.brightness,
                                 self.blue.brightness)) else 'OFF',
            'brightness': 255,
            'color': {},
            'color_mode': self.COLOR_MODE,
        }
        for c, led in self.leds.items():
            self.state['color'][c] = int(
                led.brightness / led.max_brightness * 255)

    @property
    def topic_set(self):
        return f'{self.topic}/set'

    def _cancel_effect(self):
        if self._effect_task and not self._effect_task.done():
            self._effect_task.cancel()
            self._effect_task = None

    async def _police_effect(self):
        try:
            while True:
                await self.red.write(self.red.max_brightness)
                await self.green.write(0)
                await self.blue.write(0)
                await aio.sleep(0.3)

                await self.red.write(0)
                await self.green.write(0)
                await self.blue.write(self.blue.max_brightness)
                await aio.sleep(0.3)
        except aio.CancelledError:
            pass

    async def _rainbow_effect(self):
        try:
            hue = 0.0
            while True:
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                await self.red.write(int(r * self.red.max_brightness))
                await self.green.write(int(g * self.green.max_brightness))
                await self.blue.write(int(b * self.blue.max_brightness))
                hue = (hue + 0.05) % 1.0
                await aio.sleep(0.1)
        except aio.CancelledError:
            pass

    async def _strobe_effect(self, brightness):
        try:
            while True:
                # White color with given brightness
                b = brightness / 255
                await self.red.write(int(self.red.max_brightness * b))
                await self.green.write(int(self.green.max_brightness * b))
                await self.blue.write(int(self.blue.max_brightness * b))
                await aio.sleep(0.1)

                await self.red.write(0)
                await self.green.write(0)
                await self.blue.write(0)
                await aio.sleep(0.1)
        except aio.CancelledError:
            pass

    async def _blink_effect(self, color, brightness):
        try:
            while True:
                b = brightness / 255
                await self.red.write(int((color.get('r', 255) / 255) * self.red.max_brightness * b))
                await self.green.write(int((color.get('g', 255) / 255) * self.green.max_brightness * b))
                await self.blue.write(int((color.get('b', 255) / 255) * self.blue.max_brightness * b))
                await aio.sleep(1.0)

                await self.red.write(0)
                await self.green.write(0)
                await self.blue.write(0)
                await aio.sleep(1.0)
        except aio.CancelledError:
            pass

    async def set(self, value: dict, transition_period: float):
        self._cancel_effect()

        state = value.get('state', self.state['state'])
        color = value.get('color', self.state['color'])
        # have to save to separate variable, to keep it after off
        target_brightness = \
            brightness = value.get('brightness', self.state['brightness'])
        transition = value.get('transition', transition_period)  # seconds
        effect = value.get('effect')

        start_brightness = self.state['brightness']
        start_color = self.state['color']

        # workaround for openhab light switch
        if color['r'] == color['g'] == color['b'] == 0:
            color = self.state['color']
            state = 'OFF'

        if self.state['state'].lower() == 'off':
            start_brightness = 0
            if color['r'] == 0 and color['g'] == 0 and color['b'] == 0:
                color['r'] = color['g'] = color['b'] = 255
        if state.lower() == 'off':
            brightness = 0

        if effect and effect in self.EFFECT_LIST:
            self.state['effect'] = effect
            self.state['state'] = state
            self.state['brightness'] = target_brightness
            self.state['color'] = color

            if effect == 'Police':
                self._effect_task = aio.create_task(self._police_effect())
            elif effect == 'Rainbow':
                self._effect_task = aio.create_task(self._rainbow_effect())
            elif effect == 'Strobe':
                self._effect_task = aio.create_task(self._strobe_effect(brightness))
            elif effect == 'Blink':
                self._effect_task = aio.create_task(self._blink_effect(color, brightness))

            logger.info(f'Start effect {effect}')
            return

        # Clear effect if no effect or unsupported effect
        if 'effect' in self.state:
            del self.state['effect']

        def color_repr(color: dict):
            return f'#{color["r"]:02x}{color["g"]:02x}{color["b"]:02x}'

        logger.info(f'Change light from {self.state["state"]} '
                    f'{start_brightness} {color_repr(start_color)} '
                    f'to {state} {brightness} {color_repr(start_color)}')

        if transition:
            steps = int(12 * transition)
            if steps < 1:
                steps = 1
            delay = transition / steps / 3
            for step_num in range(1, steps):
                for c, led in self.leds.items():
                    step = (color[c] * brightness / 255 -
                            start_color[c] * start_brightness / 255) / steps
                    next_value = (start_color[c] * start_brightness / 255 +
                                  step * step_num) / 255 * led.max_brightness
                    next_value = int(min(max(next_value, 0),
                                         led.max_brightness))  # normalize
                    await led.write(next_value)
                await aio.sleep(delay)

        for c, led in self.leds.items():
            next_value = color[c] / 255 * led.max_brightness * brightness / 255
            next_value = int(min(max(next_value, 0),
                                 led.max_brightness))  # normalize
            await led.write(next_value)

        self.state = {
            'state': state,
            'brightness': target_brightness,
            'color': color,
            'color_mode': self.COLOR_MODE,
        }
