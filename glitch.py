#   So far I have found a few different parameters that drastically change the form of the final JPEG
#   1. The filters that the png was originally compressed with
#       ->  This can be controlled with ffmpeg via --pred, ensuring that each scanline is give the same filter type
#       ->  Otherwise, the base compression of the file, which can be somewhat controlled via something like pngcrush, but fundamentally is left to the whim of the encoder
#   2. Whether or not the colortype was modified before conversion to RGB or not.
#       ->  If the colortype of a type 6 png is set to 0, 2, or 4 before -c is called, a unique color-banding effect can be achieved. Each type creates it's own distinct effect.
#       ->  Otherwise, a standard conversion to type 2 will occur.
#   3. During this moment, before conversion and after modifying the colortype, any bitwise corruptions/modifications will impact the output post-conversion.
#       ->  xor, and, or will each modify data permanently and the exact form before the operation is pretty much impossible to return to.
#       ->  this permanently modified data necessarily impacts the conversion process, and creates unique/distinct effects.
#   4. Finally, bitwise corruptions to the converted file are permanent, and each operation creates a unique/random effect on the final image.

# Changing the colortype after setting a particular filter will also modify the data in unpredictable ways


import struct
import zlib
import sys
import subprocess
import random
import argparse
import math
from PIL import Image

from png import PNG

# 01010101 &= 11111111 -> 01010101    -> preserves data
# 01010101 &= 00000000 -> 00000000    -> wipes data
# 01010101 |= 11111111 -> 11111111    -> wipes data (to 255)
# 01010101 |= 00000000 -> 01010101    -> preserves data
# 01010101 ^= 11111111 -> 10101010    -> inverts colours
# 01010101 ^= 00000000 -> 01010101    -> preserves data
# 10101010 << 1        -> 101010100   -> data > 255, needs to be used with an & 0xFF to keep within 255
# 01010101 >> 1        -> 00101010    -> data loss

# scanline[byte] |= scanline[byte + 1]      -> seems to slowly lead to over exposure of the image (all to 11111111)
# scanline[byte] &= scanline[byte + 1]      -> image slowly gets under-exposed, very cool effects with paeth filter
# scanline[byte] ^= scanline[byte + 1]      -> messes around with the colours a lot, no data loss over time




def checkArgs():
    parser = argparse.ArgumentParser(prog="png-glitch", description="Simple-ish tool to corrupt and mess with png files.")

    parser.add_argument('filename')
    parser.add_argument('-f', '--filter', type=int)
    parser.add_argument('-r', '--redraw', action='store_true')
    parser.add_argument('--ffmpeg', action='store_true')
    parser.add_argument('-b', '--bitwise', type=str)
    parser.add_argument('-c', '--convert', type=int)
    parser.add_argument('-m', '--messy', action='store_true')
    parser.add_argument('-u', '--undo', action='store_true')

    args = parser.parse_args()

    if args.filename == None:
        raise ValueError('A path to the PNG file must be specified')

    if args.filter not in [0, 1, 2, 3, 4]:
        raise ValueError("A filter type from 0-4 must be specified.")
    
    if args.ffmpeg:
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel", "panic",
                "-y",                 # overwrite output
                "-i", args.filename,
                "-pred", str(args.filter),
                "files/ffmpegout.png"
            ],
            check=True
        )
        print(f"File written to 'files/ffmpegout.png' with requested FFmpeg filters")
        exit(0)
    
    return (args.filename, args.filter, args.bitwise, args.convert, args.messy, args.undo, args.redraw)



pngPath, requestedFilter, bitwiseOperator, convertValue, messy, undo, redraw = checkArgs()

with open(pngPath, "r+b") as png:
    file = PNG(png)

    file.start()

    if bitwiseOperator:
        file.bitwiseCorrupt(bitwiseOperator)

    if redraw:
        file.offsetCorrupt()

    if messy:
        file.messyConvert()

    if undo:
        file.undoMessyConvert()

    if convertValue != None:
        file.convertColorType(convertValue)


    file.addFilters(requestedFilter)

    file.finish()

    print(f'Glitched: "{pngPath}" successfully')
    


    # image = Image.open(png)
    # image.show()

    # when conversion is desired, we calculate the scanlines FIRST based on the colorType we are converting to
    # this means that a different amount of bytes per pixel are expected inside each scanline before the image is even converted
    # for example: 2 to 6 means we'll be reading 4 bpp from an image that is actually 3 bpp.
    # Because the decoder will be reading 4 bpp from the image, each 12 bytes that would correspond to 4 RGB pixels are now read as 3 RGBA pixels
    # This condensation of the image results in a loss of height, but an interesting banding/repeating effect occurs.

    # the issue of height loss is then resolved during the actual conversion process, where the 3 bpp image is padded out with an extra byte per pixel.
    # this means that the 12 bytes are now padded to 16, meaning 4 RGB pixels are read as 4 RGBA pixels.
    # the end result of this is that the image is left with very interesting color-banding effects.
