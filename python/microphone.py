import time
import numpy as np
import pyaudio
import config


def start_stream(callback):
    p = pyaudio.PyAudio()
    frames_per_buffer = int(config.MIC_RATE / config.FPS)
    wasapi = p.get_default_output_device_info()
    config.MIC_RATE = int(wasapi["defaultSampleRate"])
    stream = p.open(format=pyaudio.paInt16,
                    channels=wasapi["maxOutputChannels"],
                    rate=config.MIC_RATE,
                    input=True,
                    input_device_index = wasapi["index"],
                    frames_per_buffer=frames_per_buffer,
                    as_loopback = True)
    overflows = 0
    prev_ovf_time = time.time()
    while True:
        try:
		    # http://stackoverflow.com/questions/22636499/convert-multi-channel-pyaudio-into-numpy-array
            y = np.fromstring(stream.read(frames_per_buffer), dtype=np.int16)
            y = np.reshape(y, (frames_per_buffer, wasapi["maxOutputChannels"]))
            y = y.astype(np.float32)
            callback(y[:, 0])
        except IOError:
            overflows += 1
            if time.time() > prev_ovf_time + 1:
                prev_ovf_time = time.time()
                print('Audio buffer has overflowed {} times'.format(overflows))
    stream.stop_stream()
    stream.close()
    p.terminate()
