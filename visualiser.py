#!/usr/bin/env python3
"""PETSCII / 64 — a character-grid visual instrument for system audio."""
import argparse
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import numpy as np
import pygame

# Pepto's measured VIC-II palette. Every rendered pixel uses one of these colours.
PALETTE = [0x000000, 0xFFFFFF, 0x68372B, 0x70A4B2, 0x6F3D86, 0x588D43,
           0x352879, 0xB8C76F, 0x6F4F25, 0x433900, 0x9A6759, 0x444444,
           0x6C6C6C, 0x9AD284, 0x6C5EB5, 0x959595]
COLOURS = [((c >> 16) & 255, (c >> 8) & 255, c & 255) for c in PALETTE]
ACCENTS = [14, 3, 13, 7, 10, 4, 6]
MODES = ['DIAMONDS', 'SPECTRUM', 'KALEIDOSCOPE']
RATE, BLOCK = 44100, 1024
VERSION = '0.1.0'
ROOT = Path(__file__).resolve().parent
BUNDLED_CHARSET = ROOT / 'assets/petscii-inspired.bin'


def charset_path(value):
    if value == 'bundled':
        return BUNDLED_CHARSET
    if value:
        return Path(value).expanduser()
    for directory in ('C64', 'C64DTV', 'SCPU64'):
        candidate = Path('/usr/share/vice') / directory / 'chargen-901225-01.bin'
        if candidate.is_file():
            return candidate
    return BUNDLED_CHARSET


class Audio:
    """Read the output monitor, never the microphone; bound memory to one FFT window."""
    def __init__(self, source=None):
        self.lock = threading.Lock()
        self.samples = np.zeros((4096, 2), dtype=np.float32)
        self.process = None
        self.error = ''
        self.last_data = 0.0
        self.closed = False
        self.source = source
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        try:
            if not shutil.which('parec') or not shutil.which('pactl'):
                raise RuntimeError('Install pulseaudio-utils (Arch: libpulse) for audio capture')
            sink = subprocess.check_output(['pactl', 'get-default-sink'], timeout=4,
                                           stderr=subprocess.PIPE, text=True).strip()
            source = self.source or sink + '.monitor'
            self.process = subprocess.Popen(
                ['parec', '--device=' + source, '--format=float32le',
                 '--rate=' + str(RATE), '--channels=2', '--latency-msec=30'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if self.closed:
                self.process.terminate()
                return
            while not self.closed:
                raw = self.process.stdout.read(BLOCK * 8)
                if len(raw) != BLOCK * 8:
                    if not self.closed:
                        self.error = 'Audio capture stopped. Press R to reconnect.'
                    break
                data = np.frombuffer(raw, dtype='<f4').reshape(-1, 2)
                with self.lock:
                    self.samples[:-BLOCK] = self.samples[BLOCK:]
                    self.samples[-BLOCK:] = np.nan_to_num(data)
                    self.last_data = time.monotonic()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            self.error = str(exc).splitlines()[0]

    def snapshot(self):
        with self.lock:
            return self.samples.copy()

    def close(self):
        self.closed = True
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.thread.join(timeout=1)


class Analysis:
    def __init__(self):
        self.window = np.hanning(4096)
        self.freq = np.fft.rfftfreq(4096, 1 / RATE)
        edges = np.geomspace(35, 16000, 41)
        self.masks = [(self.freq >= lo) & (self.freq < hi)
                      for lo, hi in zip(edges[:-1], edges[1:])]
        self.bands = np.zeros(40)
        self.stereo = np.zeros(2)
        self.bass = self.mid = self.high = self.beat = 0.0
        self.average = 0.12
        self.last_beat = -1.0

    def update(self, samples, gain, dt, now):
        mono = samples.mean(axis=1)
        magnitude = np.abs(np.fft.rfft(mono * self.window)) / (len(mono) / 4)
        values = np.array([np.max(magnitude[m]) if m.any() else 0 for m in self.masks])
        # Log compression keeps quieter music visible without turning silence into motion.
        target = np.clip(np.log1p(values * gain * 70) / 3.5, 0, 1)
        speeds = np.where(target > self.bands, 24, 5)
        self.bands += (target - self.bands) * (1 - np.exp(-speeds * dt))
        levels = np.sqrt(np.mean(samples ** 2, axis=0))
        self.stereo += (np.clip(levels * gain * 5, 0, 1) - self.stereo) * (1 - math.exp(-12 * dt))
        self.bass = float(np.mean(self.bands[:12]))
        self.mid = float(np.mean(self.bands[12:28]))
        self.high = float(np.mean(self.bands[28:]))
        self.average += (self.bass - self.average) * (1 - math.exp(-1.5 * dt))
        self.beat *= math.exp(-8 * dt)
        if self.bass > max(0.16, self.average * 1.35) and now - self.last_beat > 0.22:
            self.beat = 1.0
            self.last_beat = now


class Characters:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        if len(raw) < 2048:
            raise ValueError('Character ROM must contain at least 2048 bytes')
        self.cache = {}
        for code in range(256):
            bits = raw[code * 8:code * 8 + 8]
            for colour, rgb in enumerate(COLOURS):
                tile = pygame.Surface((8, 8), pygame.SRCALPHA)
                for y, row in enumerate(bits):
                    for x in range(8):
                        if row & (128 >> x):
                            tile.set_at((x, y), rgb)
                self.cache[code, colour] = tile

    def char(self, surface, x, y, code, colour):
        surface.blit(self.cache[code, colour], (x * 8, y * 8))

    def text(self, surface, x, y, value, colour=3):
        for i, ch in enumerate(value.upper()):
            code = ord(ch)
            if 64 <= code <= 95:
                code -= 64
            if code > 127:
                code = 32
            self.char(surface, x + i, y, code, colour)


class Visualiser:
    def __init__(self, charset):
        self.font = Characters(charset)
        self.original_font = Path(charset).resolve() != BUNDLED_CHARSET.resolve()
        self.glyphs = np.full((25, 40), 32, dtype=np.int16)
        self.energy = np.zeros((25, 40))
        self.colours = np.full((25, 40), 14, dtype=np.int16)
        self.mode = 0
        self.scheme = 0
        self.trails = True
        self.reference = .08
        self.motion = 0.0
        self.previous_pulse = 0.0
        self.rings = []

    def responsive_levels(self, a, dt):
        # Local gain for modes 1/2: mode 3 keeps its original response.
        peak = float(np.max(a.bands))
        speed = 8 if peak > self.reference else .35
        self.reference += (peak - self.reference) * (1 - math.exp(-speed * dt))
        levels = np.clip(a.bands / max(.025, self.reference), 0, 1)
        activity = min(1, peak / .018)
        return levels * activity

    def mark(self, x, y, glyph, colour, strength=1):
        if 0 <= x < 40 and 0 <= y < 25:
            self.glyphs[y, x] = glyph
            self.colours[y, x] = colour
            self.energy[y, x] = strength

    def diamond(self, cx, cy, radius, colour, filled=False):
        radius = max(1, int(radius))
        for y in range(-radius, radius + 1):
            width = radius - abs(y)
            for sign in (-1, 1):
                glyph = 77 if sign * y < 0 else 78
                self.mark(cx + sign * width, cy + y, glyph, colour)
            if filled:
                for x in range(-width + 1, width):
                    self.mark(cx + x, cy + y, 102, colour, .85)
        for x, y in [(cx, cy-radius), (cx, cy+radius), (cx-radius, cy), (cx+radius, cy)]:
            self.mark(x, y, 90, colour)

    def render(self, a, dt, now, status, gain, paused, help_visible, chrome=True):
        if not paused:
            self.energy *= math.exp(-dt * (5 if self.trails else 1000))
        colours = ACCENTS[self.scheme:] + ACCENTS[:self.scheme]
        if paused:
            pass
        elif self.mode == 0:
            levels = self.responsive_levels(a, dt)
            bass = float(np.max(levels[:16]))
            mids = float(np.max(levels[16:30]))
            activity = float(np.max(levels))
            self.motion += dt * (.2 + activity * 1.7)
            if bass > self.previous_pulse + .08 and bass > .3:
                self.rings.append([1.0, int(self.motion * 3) % 7])
            self.previous_pulse += (bass - self.previous_pulse) * (1 - math.exp(-5 * dt))
            self.rings = [[r + dt * (7 + bass * 9), c] for r, c in self.rings if r < 23]
            for radius, colour in self.rings:
                self.diamond(19, 12, radius, colours[colour])
                self.diamond(20, 12, radius, colours[colour])
            stereo_max = max(.001, float(np.max(a.stereo)))
            for side, cx in enumerate((10, 29)):
                stereo = float(a.stereo[side]) / stereo_max
                radius = 1 + bass * 7 + stereo * activity * 3
                for layer in range(5, 0, -1):
                    ripple = math.sin(self.motion * 3 - layer * .8) * mids * 1.5
                    size = max(1, radius * layer / 5 + ripple)
                    colour = colours[(layer + int(self.motion)) % 7]
                    self.diamond(cx, 12, size, colour, layer == 1 and bass > .55)
            self.diamond(19, 12, 1 + mids * 6, colours[int(self.motion * 2) % 7])
        elif self.mode == 1:
            levels = self.responsive_levels(a, dt)
            self.motion += dt * float(np.max(levels)) * 2
            # A symmetric frequency tapestry: twin columns bloom above/below
            # the centre, with patterned bodies and bright diamond tips.
            for band in range(20):
                level = float(np.max(levels[band*2:band*2+2]))
                height = min(12, int(level ** .65 * 12))
                for offset in range(height):
                    colour = colours[(offset // 2 + band // 3 + int(self.motion)) % 7]
                    glyph = [102, 86, 81, 90][(offset + band + int(self.motion * 2)) % 4]
                    for x in (19-band, 20+band):
                        self.mark(x, 12-offset, glyph, colour)
                        self.mark(x, 12+offset, glyph, colour)
                if height:
                    for x in (19-band, 20+band):
                        self.mark(x, 12-height, 90, 1)
                        self.mark(x, 12+height, 90, 1)
        else:
            for y in range(13):
                for x in range(20):
                    r = math.hypot(x / 1.55, y)
                    theta = math.atan2(y, x + .01)
                    band = float(a.bands[min(39, int(r * 2))])
                    wave = math.sin(r * .85 - now * (.4 + a.mid * 2) + math.cos(theta * 4) * a.bass * 4)
                    if band > .015 and wave > .7 - band * .8:
                        glyph = [90, 81, 102, 86, 77, 78][int(r + now * a.high * 2) % 6]
                        colour = colours[int(r / 2 + a.beat * 2) % 7]
                        for xx, yy in [(19-x, 12-y), (20+x, 12-y), (19-x, 12+y), (20+x, 12+y)]:
                            self.mark(xx, yy, glyph, colour, min(1, .5 + band))
        canvas = pygame.Surface((320, 240))
        canvas.fill(COLOURS[0])
        for y in range(25):
            for x in range(40):
                e = self.energy[y, x]
                if e > .045:
                    colour = int(self.colours[y, x]) if e > .55 else (12 if e > .2 else 11)
                    self.font.char(canvas, x, y + 3, int(self.glyphs[y, x]), colour)
        canvas.fill(COLOURS[6], (0, 0, 320, 24))
        self.font.text(canvas, 1, 0, 'PETSCII / 64', 1)
        self.font.text(canvas, 25, 0, MODES[self.mode], 3)
        self.font.text(canvas, 1, 1, status[:38], 7 if 'ERROR' in status else 3)
        self.font.text(canvas, 1, 2, f'GAIN {gain:.1f}  TRAILS {"ON" if self.trails else "OFF"}' + ('  PAUSED' if paused else ''), 14)
        canvas.fill(COLOURS[6], (0, 224, 320, 16))
        self.font.text(canvas, 1, 28, '1-3 MODE  C COLOUR  T TRAILS  ? HELP', 3)
        self.font.text(canvas, 1, 29, 'SPACE PAUSE  +/- GAIN  F FULLSCREEN', 14)
        if help_visible:
            canvas.fill(COLOURS[6], (16, 48, 288, 152))
            lines = ['PETSCII / 64', '', '1 DIAMONDS   2 SPECTRUM', '3 KALEIDOSCOPE', 'C CYCLE COLOURS   T TRAILS', '+/- INPUT GAIN   SPACE FREEZE', 'F FULLSCREEN    D DEMO AUDIO', 'R RECONNECT SYSTEM AUDIO', 'S SAVE SCREENSHOT', '? CLOSE HELP   Q / ESC QUIT', '', '40 X 25 CELLS / 16 VIC-II COLOURS', 'C64 CHARACTER ROM' if self.original_font else 'PETSCII-INSPIRED BUNDLED FONT']
            for i, line in enumerate(lines):
                self.font.text(canvas, 3, 7+i, line, 1 if i == 0 else 3)
        if not chrome and not help_visible:
            return canvas.subsurface((0, 24, 320, 200)).copy()
        return canvas


def demo_samples(now):
    t = now + np.arange(4096) / RATE
    envelope = .18 * np.exp(-((t * 2) % 1) * 9)
    left = envelope * np.sin(2 * np.pi * 65 * t)
    left += .045 * np.sin(2 * np.pi * (220 + 110 * int(now % 4)) * t)
    left += .013 * np.sin(2 * np.pi * 4400 * t) * np.exp(-((t * 4) % 1) * 14)
    right = left * (.75 + .2 * math.sin(now)) + .025 * np.sin(2 * np.pi * 330 * t)
    return np.column_stack((left, right)).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version='PETSCII / 64 ' + VERSION)
    parser.add_argument('--demo', action='store_true', help='synthetic audio, no capture needed')
    parser.add_argument('--source', help='PulseAudio/PipeWire monitor source override')
    parser.add_argument('--charset', help='character ROM path, or bundled (default: auto-detect)')
    parser.add_argument('--mode', choices=[m.lower() for m in MODES], default='kaleidoscope')
    parser.add_argument('--frames', type=int, default=0, help='exit after N frames (verification)')
    parser.add_argument('--screenshot', type=Path, help='save the last frame on exit')
    args = parser.parse_args()
    charset = charset_path(args.charset)
    if not charset.is_file():
        parser.error('Character file missing. Supply a path with --charset or use bundled.')
    pygame.display.init()
    screen = pygame.display.set_mode((960, 720), pygame.RESIZABLE)
    pygame.display.set_caption('PETSCII / 64 — music visualiser')
    visual = Visualiser(charset)
    visual.mode = MODES.index(args.mode.upper())
    analysis = Analysis()
    audio = None if args.demo else Audio(args.source)
    demo, paused, fullscreen, help_visible = args.demo, False, False, False
    gain, frame, running = 1.0, 0, True
    clock = pygame.time.Clock()
    started = time.monotonic()
    last_input = 0.0
    canvas = None
    try:
        while running:
            dt = min(.1, clock.tick(60) / 1000)
            now = time.monotonic() - started
            for event in pygame.event.get():
                if event.type in (pygame.KEYDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                    last_input = now
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    key = event.key
                    if key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        visual.mode = key - pygame.K_1
                        visual.energy.fill(0)
                    elif key == pygame.K_c:
                        visual.scheme = (visual.scheme + 1) % 7
                    elif key == pygame.K_t:
                        visual.trails = not visual.trails
                    elif key == pygame.K_SPACE:
                        paused = not paused
                    elif key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                        gain = min(10, gain * 1.2)
                    elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                        gain = max(.1, gain / 1.2)
                    elif key == pygame.K_f:
                        fullscreen = not fullscreen
                        screen = pygame.display.set_mode((0, 0) if fullscreen else (960, 720), pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
                    elif key in (pygame.K_SLASH, pygame.K_h):
                        help_visible = not help_visible
                    elif key == pygame.K_d:
                        demo = not demo
                        if demo and audio:
                            audio.close()
                            audio = None
                        elif not demo:
                            audio = Audio(args.source)
                        analysis = Analysis()
                    elif key == pygame.K_r:
                        if audio:
                            audio.close()
                        demo = False
                        audio = Audio(args.source)
                    elif key == pygame.K_s and canvas:
                        name = Path(__file__).parent / time.strftime('petscii-%Y%m%d-%H%M%S.png')
                        pygame.image.save(canvas, name)
                        print(f'Saved {name}')
            if not paused:
                analysis.update(demo_samples(now) if demo else audio.snapshot(), gain, dt, now)
            if demo:
                status = 'DEMO / PRESS D FOR SYSTEM AUDIO'
            elif audio.error:
                status = 'AUDIO ERROR / R RETRY / D DEMO'
            elif not audio.last_data:
                status = 'CONNECTING TO SYSTEM AUDIO...'
            elif time.monotonic() - audio.last_data > 2:
                status = 'AUDIO STALLED / R TO RECONNECT'
            elif np.max(analysis.bands) < .01:
                status = 'LISTENING / PLAY MUSIC IN CLIAMP'
            else:
                status = 'LIVE / SYSTEM AUDIO / STEREO'
            chrome = help_visible or now - last_input < 2
            pygame.mouse.set_visible(chrome)
            canvas = visual.render(analysis, dt, now, status, gain, paused, help_visible, chrome)
            w, h = screen.get_size()
            cw, ch = canvas.get_size()
            scale = max(1, min(w // cw, h // ch))
            size = (cw * scale, ch * scale)
            screen.fill(COLOURS[0])
            screen.blit(pygame.transform.scale(canvas, size), ((w-size[0])//2, (h-size[1])//2))
            pygame.display.flip()
            frame += 1
            if args.frames and frame >= args.frames:
                running = False
        if args.screenshot and canvas:
            pygame.image.save(pygame.transform.scale(canvas, (canvas.get_width()*3, canvas.get_height()*3)), args.screenshot)
    finally:
        if audio:
            if audio.error:
                print('Audio: ' + audio.error)
            audio.close()
        pygame.quit()


if __name__ == '__main__':
    main()
