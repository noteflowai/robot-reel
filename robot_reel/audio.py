"""Original synthesized soundtrack. No samples or third-party music."""
import subprocess
import wave

import imageio_ffmpeg
import numpy as np


def add_soundtrack(output, duration):
    rate = 44100
    t = np.arange(round(duration * rate)) / rate
    audio = np.zeros_like(t)
    beat = 60 / 112
    for start in np.arange(0, duration, beat):
        dt = t-start
        mask = (dt >= 0) & (dt < .3)
        x = dt[mask]
        audio[mask] += .22*np.sin(2*np.pi*(48*x+22*.025*(1-np.exp(-x/.025))))*np.exp(-x*15)
    notes = [130.81, 155.56, 196., 233.08]
    for i, start in enumerate(np.arange(0, duration, beat/2)):
        dt = t-start
        mask = (dt >= 0) & (dt < .5)
        x = dt[mask]
        audio[mask] += .045*np.sin(2*np.pi*notes[i % 4]*2*x)*np.exp(-x*9)*(1-np.exp(-x*80))
    audio *= np.clip(t/1.5, 0, 1)*np.clip((duration-t)/2, 0, 1)
    path = output / "soundtrack.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1)*32767).astype("<i2").tobytes())
    for name in ["robot-reel", "robot-reel-vertical"]:
        source = output / f"{name}.mp4"
        temp = output / f"{name}-mux.mp4"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error",
                        "-i", str(source), "-i", str(path),
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                        "-shortest", "-movflags", "+faststart", str(temp)], check=True)
        temp.replace(source)
