import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import unittest
import numpy as np
import pygame
from visualiser import Analysis, Visualiser, RATE, COLOURS, BUNDLED_CHARSET, charset_path


class VisualiserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_frequency_stereo_and_silence(self):
        a = Analysis()
        t = np.arange(4096) / RATE
        signal = np.column_stack((.2 * np.sin(2*np.pi*100*t), np.zeros(4096)))
        for i in range(90):
            a.update(signal, 1, 1/60, i/60)
        self.assertGreater(a.stereo[0], .5)
        self.assertEqual(a.stereo[1], 0)
        self.assertGreater(a.bass, .1)
        self.assertLess(a.high, .01)
        for i in range(180):
            a.update(np.zeros((4096, 2)), 1, 1/60, 2+i/60)
        self.assertLess(a.bands.max(), .001)

    def test_quiet_music_moves_diamonds_and_spectrum(self):
        t = np.arange(4096) / RATE
        for mode in (0, 1):
            a = Analysis()
            v = Visualiser(BUNDLED_CHARSET)
            v.mode = mode
            frames = []
            for i in range(160):
                amplitude = .002 * (.2 + .8 * (np.sin(i*.1)+1)/2)
                signal = np.column_stack((amplitude*np.sin(2*np.pi*110*t),
                                          amplitude*np.sin(2*np.pi*330*t)))
                a.update(signal, 1, 1/60, i/60)
                frame = v.render(a, 1/60, i/60, 'TEST', 1, False, False, False)
                if i in (50, 100, 150):
                    frames.append(pygame.image.tobytes(frame, 'RGB'))
            self.assertEqual(len(set(frames)), 3, f'mode {mode+1} appears frozen')

    def test_every_pixel_uses_c64_palette(self):
        a = Analysis()
        a.bands[:] = np.linspace(.1, .9, 40)
        a.bass, a.mid, a.high = .7, .5, .3
        a.stereo[:] = [.4, .6]
        for mode in range(3):
            v = Visualiser(BUNDLED_CHARSET)
            v.mode = mode
            frame = v.render(a, 1/60, 1, 'TEST', 1, False, False)
            colours = set(map(tuple, pygame.surfarray.array3d(frame).reshape(-1, 3)))
            self.assertTrue(colours.issubset(set(COLOURS)))

    def test_hide_chrome_pause_and_help(self):
        v = Visualiser(BUNDLED_CHARSET)
        a = Analysis()
        a.bands[:] = .5
        frame = v.render(a, 1/60, 1, 'TEST', 1, False, False, False)
        self.assertEqual(frame.get_size(), (320, 200))
        energy = v.energy.copy()
        frame = v.render(a, 1/60, 2, 'TEST', 1, True, True, False)
        self.assertTrue(np.array_equal(v.energy, energy))
        self.assertEqual(frame.get_size(), (320, 240))
        self.assertEqual(charset_path('bundled'), BUNDLED_CHARSET)
        self.assertEqual(BUNDLED_CHARSET.stat().st_size, 2048)


if __name__ == '__main__':
    unittest.main()
