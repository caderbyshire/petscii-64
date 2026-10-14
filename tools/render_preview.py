"""Render shareable previews from synthetic stereo audio and the bundled font."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import sys
from pathlib import Path
import numpy as np
import pygame

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from visualiser import Analysis, Visualiser, BUNDLED_CHARSET, RATE

pygame.display.init()
pygame.display.set_mode((1, 1))
output = ROOT / 'docs'
output.mkdir(exist_ok=True)
frames = Path('/tmp/petscii-preview-frames')
frames.mkdir(exist_ok=True)
frequencies = np.geomspace(55, 14000, 36)
time_axis = np.arange(4096) / RATE

for mode, name in enumerate(('diamonds', 'spectrum', 'kaleidoscope')):
    a = Analysis()
    v = Visualiser(BUNDLED_CHARSET)
    v.mode = mode
    for i in range(120):
        now = i / 15
        amplitudes = .028 * (.25 + .75 * (np.sin(np.arange(36)*.3 + now*1.8)+1)/2)
        tones = np.sin(2*np.pi*frequencies[:, None]*(time_axis[None, :] + now))
        left = (tones * amplitudes[:, None]).sum(axis=0)
        right = (tones * (amplitudes * (.8 + .2*np.sin(now + np.arange(36))))[:, None]).sum(axis=0)
        a.update(np.column_stack((left, right)), 1, 1/15, now)
        image = v.render(a, 1/15, now, 'DEMO', 1, False, False, False)
        if mode == 2:
            pygame.image.save(pygame.transform.scale(image, (640, 400)), frames / f'{i:03}.png')
        if i == 70:
            pygame.image.save(pygame.transform.scale(image, (960, 600)), output / (name + '.png'))
pygame.quit()
print('Previews rendered from synthetic stereo audio.')
