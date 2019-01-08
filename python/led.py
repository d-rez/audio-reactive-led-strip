from __future__ import print_function
from __future__ import division

import platform
import numpy as np
import config
from ChromaPython import ChromaApp, ChromaAppInfo, ChromaColor, Colors

# ESP8266 uses WiFi communication
if config.DEVICE == 'esp8266':
    import socket
    _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    Info = ChromaAppInfo
    Info.DeveloperName = 'd-rez'
    Info.DeveloperContact = 'dark.skeleton@gmail.com'
    Info.Category = 'application'
    Info.SupportedDevices = ['keyboard', 'mouse', 'mousepad', 'headset']
    Info.Description = 'Oh Rick, I don\'t know if that\'s a good idea.'
    Info.Title = 'Audio Reactive Chroma-extended LED strip'

    App = ChromaApp(Info)

# Raspberry Pi controls the LED strip directly
elif config.DEVICE == 'pi':
    import neopixel
    strip = neopixel.Adafruit_NeoPixel(config.N_PIXELS, config.LED_PIN,
                                       config.LED_FREQ_HZ, config.LED_DMA,
                                       config.LED_INVERT, config.BRIGHTNESS)
    strip.begin()
elif config.DEVICE == 'blinkstick':
    from blinkstick import blinkstick
    import signal
    import sys
    #Will turn all leds off when invoked.
    def signal_handler(signal, frame):
        all_off = [0]*(config.N_PIXELS*3)
        stick.set_led_data(0, all_off)
        sys.exit(0)

    stick = blinkstick.find_first()
    # Create a listener that turns the leds off when the program terminates
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

_gamma = np.load(config.GAMMA_TABLE_PATH)
"""Gamma lookup table used for nonlinear brightness correction"""

_prev_pixels = np.tile(253, (3, config.N_PIXELS))
"""Pixel values that were most recently displayed on the LED strip"""

pixels = np.tile(1, (3, config.N_PIXELS))
"""Pixel values for the LED strip"""

KeyboardGrid = [[ChromaColor(red=0, green=0, blue=0) for x in range(App.Keyboard.MaxColumn)] for y in range(App.Keyboard.MaxRow)]
KeypadGrid = [[ChromaColor(red=0, green=0, blue=0) for x in range(App.Keypad.MaxColumn)] for y in range(App.Keypad.MaxRow)]
MousepadGrid = [ChromaColor(red=0, green=0, blue=0) for x in range(App.Mousepad.MaxLED)]

chroma_rate_counter = 0
_is_python_2 = int(platform.python_version_tuple()[0]) == 2

def _update_esp8266():
    """Sends UDP packets to ESP8266 to update LED strip values

    The ESP8266 will receive and decode the packets to determine what values
    to display on the LED strip. The communication protocol supports LED strips
    with a maximum of 256 LEDs.

    The packet encoding scheme is:
        |i|r|g|b|
    where
        i (0 to 255): Index of LED to change (zero-based)
        r (0 to 255): Red value of LED
        g (0 to 255): Green value of LED
        b (0 to 255): Blue value of LED
    """
    global pixels, _prev_pixels
    # Truncate values and cast to integer
    pixels = np.clip(pixels, 0, 255).astype(int)
    # Optionally apply gamma correc tio
    p = _gamma[pixels] if config.SOFTWARE_GAMMA_CORRECTION else np.copy(pixels)
    MAX_PIXELS_PER_PACKET = 126
    # Pixel indices
    idx = range(pixels.shape[1])
    idx = [i for i in idx if not np.array_equal(p[:, i], _prev_pixels[:, i])]
    n_packets = len(idx) // MAX_PIXELS_PER_PACKET + 1
    idx = np.array_split(idx, n_packets)
    for packet_indices in idx:
        m = '' if _is_python_2 else []
        for i in packet_indices:
            if _is_python_2:
                m += chr(i) + chr(p[0][i]) + chr(p[1][i]) + chr(p[2][i])
            else:
                m.append(i)  # Index of pixel to change
                m.append(p[0][i])  # Pixel red value
                m.append(p[1][i])  # Pixel green value
                m.append(p[2][i])  # Pixel blue value
        m = m if _is_python_2 else bytes(m)
        _sock.sendto(m, (config.UDP_IP, config.UDP_PORT))
    _prev_pixels = np.copy(p)

def _update_chroma_scaled():
    """
    This function runs Chroma at scaled resolution.
    Every device will display the exact same section of the LED strip's spectrum, scaled down to each device's size
    This is my old implementation
    """
    global chroma_rate_counter, KeyboardGrid
    chroma_rate_counter = (chroma_rate_counter+1) % 2
    if chroma_rate_counter != 1:
      return
    global pixels, _prev_pixels, KeyboardGrid, KeypadGrid

    rr = pixels[0].reshape(15,4).mean(1).astype(int)
    gg = pixels[1].reshape(15,4).mean(1).astype(int)
    bb = pixels[2].reshape(15,4).mean(1).astype(int)
    mid = int(len(rr)/2)

    for i in range(15):
      App.Mousepad.setPosition(x=i,color=ChromaColor(red=rr[i], blue=bb[i], green=gg[i]))
    App.Mousepad.applyGrid()

    for i in range(0,7):
      App.Mouse.setPosition(x=0,y=i+1,color=ChromaColor(red=rr[i], green=gg[i], blue=bb[i]))
    for i in range(7,15):
      App.Mouse.setPosition(x=6,y=7-(i-7)+1,color=ChromaColor(red=rr[i], green=gg[i], blue=bb[i]))
    App.Mouse.setPosition(x=3,y=2,color=ChromaColor(red=rr[mid], green=gg[mid], blue=bb[mid]))
    App.Mouse.applyGrid()

    App.Headset.setNone()
    HeadsetColor = ChromaColor(red=rr[mid],blue=bb[mid],green=gg[mid])
    App.Headset.setStatic(color=HeadsetColor)

    # rescale to 20 for TKL keyboard
    rr = pixels[0].reshape(20,3).mean(1).astype(int)
    gg = pixels[1].reshape(20,3).mean(1).astype(int)
    bb = pixels[2].reshape(20,3).mean(1).astype(int)

    for x in range(2,18):
      KeyboardGrid[0][x-2].set(red=rr[x], green=gg[x], blue=bb[x])
    App.Keyboard.setCustomGrid(KeyboardGrid)
    App.Keyboard.applyGrid()
    KeyboardGrid.insert(0,[ChromaColor(red=0, green=0, blue=0) for x in range(22)])
    del KeyboardGrid[-1]

    # rescale to 5 for keypads
    rr = rr.reshape(5,4).mean(1).astype(int)
    gg = gg.reshape(5,4).mean(1).astype(int)
    bb = bb.reshape(5,4).mean(1).astype(int)

    for x in range(0,5):
      KeypadGrid[0][x].set(red=rr[x], green=gg[x], blue=bb[x])
    App.Keypad.setCustomGrid(KeypadGrid)
    App.Keypad.applyGrid()
    KeypadGrid.insert(0,[ChromaColor(red=0, green=0, blue=0) for x in range(App.Keypad.MaxColumn)])
    del KeypadGrid[-1]


def _update_pi():
    """Writes new LED values to the Raspberry Pi's LED strip

    Raspberry Pi uses the rpi_ws281x to control the LED strip directly.
    This function updates the LED strip with new values.
    """
    global pixels, _prev_pixels
    # Truncate values and cast to integer
    pixels = np.clip(pixels, 0, 255).astype(int)
    # Optional gamma correction
    p = _gamma[pixels] if config.SOFTWARE_GAMMA_CORRECTION else np.copy(pixels)
    # Encode 24-bit LED values in 32 bit integers
    r = np.left_shift(p[0][:].astype(int), 8)
    g = np.left_shift(p[1][:].astype(int), 16)
    b = p[2][:].astype(int)
    rgb = np.bitwise_or(np.bitwise_or(r, g), b)
    # Update the pixels
    for i in range(config.N_PIXELS):
        # Ignore pixels if they haven't changed (saves bandwidth)
        if np.array_equal(p[:, i], _prev_pixels[:, i]):
            continue
        strip._led_data[i] = rgb[i]
    _prev_pixels = np.copy(p)
    strip.show()

def _update_blinkstick():
    """Writes new LED values to the Blinkstick.
        This function updates the LED strip with new values.
    """
    global pixels
    
    # Truncate values and cast to integer
    pixels = np.clip(pixels, 0, 255).astype(int)
    # Optional gamma correction
    p = _gamma[pixels] if config.SOFTWARE_GAMMA_CORRECTION else np.copy(pixels)
    # Read the rgb values
    r = p[0][:].astype(int)
    g = p[1][:].astype(int)
    b = p[2][:].astype(int)

    #create array in which we will store the led states
    newstrip = [None]*(config.N_PIXELS*3)

    for i in range(config.N_PIXELS):
        # blinkstick uses GRB format
        newstrip[i*3] = g[i]
        newstrip[i*3+1] = r[i]
        newstrip[i*3+2] = b[i]
    #send the data to the blinkstick
    stick.set_led_data(0, newstrip)


def update():
    """Updates the LED strip values"""
    if config.DEVICE == 'esp8266':
        _update_esp8266()
        _update_chroma()
    elif config.DEVICE == 'pi':
        _update_pi()
    elif config.DEVICE == 'blinkstick':
        _update_blinkstick()
    else:
        raise ValueError('Invalid device selected')


# Execute this file to run a LED strand test
# If everything is working, you should see a red, green, and blue pixel scroll
# across the LED strip continously
if __name__ == '__main__':
    import time
    # Turn all pixels off
    pixels *= 0
    pixels[0, 0] = 255  # Set 1st pixel red
    pixels[1, 1] = 255  # Set 2nd pixel green
    pixels[2, 2] = 255  # Set 3rd pixel blue
    print('Starting LED strand test')
    while True:
        pixels = np.roll(pixels, 1, axis=1)
        update()
        time.sleep(.1)
