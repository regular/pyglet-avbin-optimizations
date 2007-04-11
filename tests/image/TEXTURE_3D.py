#!/usr/bin/env python

'''
'''

__docformat__ = 'restructuredtext'
__version__ = '$Id: $'

import unittest

from pyglet.gl import *
from pyglet.image import *
from pyglet.window import *

__noninteractive = True

class TestTexture3D(unittest.TestCase):
    def create_image(self, width, height, color):
        data = ('%c' % color) * (width * height)
        return ImageData(width, height, 'L', data)

    def check_image(self, image, width, height, color):
        self.assertTrue(image.width == width)
        self.assertTrue(image.height == height)
        color = '%c' % (color)
        image = image.image_data
        image.pitch = image.width
        image.format = 'L'
        data = image.data
        self.assertTrue(data == color * len(data))

    def set_grid_image(self, itemwidth, itemheight, rows, cols, rowpad, colpad):
        data = ''
        color = 1
        width = itemwidth * cols + colpad * (cols - 1)
        height = itemheight * rows + rowpad * (rows - 1)
        for row in range(rows):
            rowdata = ''
            for col in range(cols):
                rowdata += ('%c' % color) * itemwidth
                if col < cols - 1:
                    rowdata += '\0' * colpad
                color += 1

            data += rowdata * itemheight
            if row < rows - 1:
                data += (width * '\0') * rowpad
        assert len(data) == width * height
        self.image = ImageData(width, height, 'L', data)
        grid = ImageGrid(self.image, rows, cols,
            itemwidth, itemheight, rowpad, colpad)
        self.grid = Texture3D.create_for_image_grid(grid)

    def check_cell(self, cellimage, cellindex):
        self.assertTrue(cellimage.width == self.grid.item_width)
        self.assertTrue(cellimage.height == self.grid.item_height)

        color = '%c' % (cellindex + 1)
        cellimage = cellimage.image_data
        cellimage.pitch = cellimage.width
        cellimage.format = 'L'
        data = cellimage.data
        self.assertTrue(data == color * len(data))

    def setUp(self):
        self.w = Window(visible=False)

    def test2(self):
        # Test 2 images of 32x32
        images = [self.create_image(32, 32, i+1) for i in range(2)]
        texture = Texture3D.create_for_images(images)
        self.assertTrue(len(texture) == 2)
        for i in range(2):
            self.check_image(texture[i], 32, 32, i+1)

    def test5(self):
        # test 5 images of 31x94  (power2 issues)
        images = [self.create_image(31, 94, i+1) for i in range(5)]
        texture = Texture3D.create_for_images(images)
        self.assertTrue(len(texture) == 5)
        for i in range(5):
            self.check_image(texture[i], 31, 94, i+1)

    def testSet(self):
        # test replacing an image
        images = [self.create_image(32, 32, i+1) for i in range(3)]
        texture = Texture3D.create_for_images(images)
        self.assertTrue(len(texture) == 3)
        for i in range(3):
            self.check_image(texture[i], 32, 32, i+1)
        texture[1] = self.create_image(32, 32, 87)
        self.check_image(texture[0], 32, 32, 1)
        self.check_image(texture[1], 32, 32, 87)
        self.check_image(texture[2], 32, 32, 3)

    def testSquare(self):
        # Test a 3x3 grid with no padding and 4x4 images
        rows = cols = 3
        self.set_grid_image(4, 4, rows, cols, 0, 0)
        for i in range(rows * cols): 
            self.check_cell(self.grid[i], i)

    def testRect(self):
        # Test a 2x5 grid with no padding and 3x8 images
        rows, cols = 2, 5
        self.set_grid_image(3, 8, rows, cols, 0, 0)
        for i in range(rows * cols): 
            self.check_cell(self.grid[i], i)

    def testPad(self):
        # Test a 5x3 grid with rowpad=3 and colpad=7 and 10x9 images
        rows, cols = 5, 3
        self.set_grid_image(10, 9, rows, cols, 3, 7)
        for i in range(rows * cols): 
            self.check_cell(self.grid[i], i)

if __name__ == '__main__':
    unittest.main()
