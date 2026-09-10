"""
LUMI light control
"""
import asyncio as aio
import colorsys
import logging
import math
import os
import random
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
    EFFECT_LIST = [
        "None",
        "Police",
        "Rainbow",
        "Strobe",
        "Blink",
        "Police Strobe",
        "Double Strobe",
        "Breathing",
        "Fire"
    ]

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
                # Apply color internally without software transition delay
                await self.red.write(int(r * self.red.max_brightness))
                await self.green.write(int(g * self.green.max_brightness))
                await self.blue.write(int(b * self.blue.max_brightness))
                hue = (hue + 0.01) % 1.0
                await aio.sleep(0.05)
        except aio.CancelledError:
            pass

    async def _police_strobe_effect(self):
        try:
            while True:
                for _ in range(2):
                    await self.red.write(self.red.max_brightness)
                    await self.green.write(0)
                    await self.blue.write(0)
                    await aio.sleep(0.05)
                    await self.red.write(0)
                    await aio.sleep(0.05)
                await aio.sleep(0.2)
                for _ in range(2):
                    await self.red.write(0)
                    await self.green.write(0)
                    await self.blue.write(self.blue.max_brightness)
                    await aio.sleep(0.05)
                    await self.blue.write(0)
                    await aio.sleep(0.05)
                await aio.sleep(0.2)
        except aio.CancelledError:
            pass

    async def _double_strobe_effect(self):
        try:
            while True:
                color = self.state.get('color', {})
                brightness = self.state.get('brightness', 255) / 255
                r = int((color.get('r', 255) / 255) * self.red.max_brightness * brightness)
                g = int((color.get('g', 255) / 255) * self.green.max_brightness * brightness)
                b = int((color.get('b', 255) / 255) * self.blue.max_brightness * brightness)

                for _ in range(2):
                    await self.red.write(r)
                    await self.green.write(g)
                    await self.blue.write(b)
                    await aio.sleep(0.05)
                    await self.red.write(0)
                    await self.green.write(0)
                    await self.blue.write(0)
                    await aio.sleep(0.05)
                await aio.sleep(0.1)

                for _ in range(2):
                    await self.red.write(r)
                    await self.green.write(g)
                    await self.blue.write(b)
                    await aio.sleep(0.05)
                    await self.red.write(0)
                    await self.green.write(0)
                    await self.blue.write(0)
                    await aio.sleep(0.05)
                await aio.sleep(0.5)
        except aio.CancelledError:
            pass

    async def _breathing_effect(self):
        try:
            step = 0
            while True:
                color = self.state.get('color', {})
                # Sine wave from 0.1 to 1.0
                brightness_factor = (math.sin(step) + 1) / 2 * 0.9 + 0.1
                r = int((color.get('r', 255) / 255) * self.red.max_brightness * brightness_factor)
                g = int((color.get('g', 255) / 255) * self.green.max_brightness * brightness_factor)
                b = int((color.get('b', 255) / 255) * self.blue.max_brightness * brightness_factor)

                await self.red.write(r)
                await self.green.write(g)
                await self.blue.write(b)

                step += 0.05
                await aio.sleep(0.05)
        except aio.CancelledError:
            pass

    async def _fire_effect(self):
        try:
            while True:
                brightness_factor = random.uniform(0.5, 1.0)
                # Orange/Red hue shifting slightly
                hue = random.uniform(0.0, 0.12)
                r_scale, g_scale, b_scale = colorsys.hsv_to_rgb(hue, 1.0, 1.0)

                r = int(r_scale * self.red.max_brightness * brightness_factor)
                g = int(g_scale * self.green.max_brightness * brightness_factor)
                b = int(b_scale * self.blue.max_brightness * brightness_factor)

                await self.red.write(r)
                await self.green.write(g)
                await self.blue.write(b)

                await aio.sleep(random.uniform(0.05, 0.15))
        except aio.CancelledError:
            pass

    async def _strobe_effect(self):
        try:
            while True:
                color = self.state.get('color', {})
                brightness = self.state.get('brightness', 255)
                b = brightness / 255
                await self.red.write(int((color.get('r', 255) / 255) * self.red.max_brightness * b))
                await self.green.write(int((color.get('g', 255) / 255) * self.green.max_brightness * b))
                await self.blue.write(int((color.get('b', 255) / 255) * self.blue.max_brightness * b))
                await aio.sleep(0.1)

                await self.red.write(0)
                await self.green.write(0)
                await self.blue.write(0)
                await aio.sleep(0.1)
        except aio.CancelledError:
            pass

    async def _blink_effect(self):
        try:
            while True:
                color = self.state.get('color', {})
                brightness = self.state.get('brightness', 255)
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

        # Update state directly so active effects can read it dynamically
        self.state['state'] = state
        self.state['brightness'] = target_brightness
        self.state['color'] = color

        # Handle effect stopping or starting
        if 'effect' in value and (not effect or effect == 'None'):
            # Clear effect explicitly requested
            self._cancel_effect()
            if 'effect' in self.state:
                del self.state['effect']
            # Continue with transition=0 if explicitly cleared to prevent delay conflicts
            transition = 0
        elif effect and effect in self.EFFECT_LIST:
            # Start new effect
            self._cancel_effect()
            self.state['effect'] = effect

            if effect == 'Police':
                self._effect_task = aio.create_task(self._police_effect())
            elif effect == 'Rainbow':
                self._effect_task = aio.create_task(self._rainbow_effect())
            elif effect == 'Strobe':
                self._effect_task = aio.create_task(self._strobe_effect())
            elif effect == 'Blink':
                self._effect_task = aio.create_task(self._blink_effect())
            elif effect == 'Police Strobe':
                self._effect_task = aio.create_task(self._police_strobe_effect())
            elif effect == 'Double Strobe':
                self._effect_task = aio.create_task(self._double_strobe_effect())
            elif effect == 'Breathing':
                self._effect_task = aio.create_task(self._breathing_effect())
            elif effect == 'Fire':
                self._effect_task = aio.create_task(self._fire_effect())

            logger.info(f'Start effect {effect}')
            return
        elif 'effect' not in value and self._effect_task:
            # Normal color change arrived while an effect is running
            # We must cancel the effect to respect the new color/state.
            self._cancel_effect()
            if 'effect' in self.state:
                del self.state['effect']
            transition = 0

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
