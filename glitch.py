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

import subprocess
import argparse


from png import PNGGlitch

# 01010101 &= 11111111 -> 01010101    -> preserves data
# 01010101 &= 00000000 -> 00000000    -> wipes data
# 01010101 |= 11111111 -> 11111111    -> wipes data (to 255)
# 01010101 |= 00000000 -> 01010101    -> preserves data
# 01010101 ^= 11111111 -> 10101010    -> inverts colours
# 01010101 ^= 00000000 -> 01010101    -> preserves data
# 10101010 << 1        -> 101010100   -> data > 255, needs to be used with an & 0xFF to keep within 255
# 01010101 >> 1        -> 00101010    -> data loss

# scanline[byte] |= scanline[byte + 1]      -> seems to slowly lead to under exposure of the image (all to 11111111)
# scanline[byte] &= scanline[byte + 1]      -> image slowly gets over-exposed, very cool effects with paeth filter
# scanline[byte] ^= scanline[byte + 1]      -> messes around with the colours a lot, very little data loss over time




def checkArgs():
    parser = argparse.ArgumentParser(prog="png-glitch", description="Simple-ish tool to corrupt and mess with png files.")

    parser.add_argument('filename')
    parser.add_argument('-f', '--filter', 
                        choices=['0', '1', '2', '3', '4', 'random'], 
                        required=True,
                        help="""Sets the filter type of each scanline in the PNG file the specified filter type. 
                        The random value will select a filter at random, which can be used alongside the -s flag.""")
    parser.add_argument('-s', '--sections', 
                        type=int,
                        help="""Defines how many sections to split the PNG into, with each section having a random filter type.
                        To be used alongside '-f random' only.""")
    parser.add_argument('-r', '--redraw', 
                        action='store_true',
                        help="""Will redraw each pixel inside each scanline with an increasing offset.
                        This shifts the image diagonally, which can create some nice effects alongside various filters.""")
    parser.add_argument('--ffmpeg', 
                        action='store_true',
                        help="""This compresses the PNG, ensuring that each scanline is given the same filter.
                        This can help create unique effects on the PNG, and also allow for more consistent output results.""")
    parser.add_argument('-b', 
                        '--bitwise', 
                        type=str,
                        help="""Performs various bitwise operations on the unfiltered bytes extracted from the PNG.
                        This can create very unique effects.
                        The supported arguments are: or, xor, and, rshift, lshift, invert, swap, noise""")
    parser.add_argument('-c', '--convert', 
                        type=int,
                        help="""This argument is used to convert between PNG colortypes.
                        It will pad/delete bytes from the unfiltered png bytes as needed.
                        Note that if converting to a 'smaller' colortype, 
                        the deleted byte data is deleted permanently.""")
    parser.add_argument('-m', '--messy', 
                        action='store_true',
                        help="""A 'messy' conversion will create a unique scattering/offset effect on the image.
                        This will essentially pad a colortype 2 image with extra bytes to create a colortype 6 image, 
                        but then read it as if it were still a colortype 2 image.""")
    parser.add_argument('-u', '--undo', 
                        action='store_true',
                        help="""Undoes a 'messy' conversion. Essentially performs the inverse operations as -m.""")

    args = parser.parse_args()
    
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
    
    return (args.filename, args.filter, args.bitwise, args.convert, args.messy, args.undo, args.redraw, args.sections)



pngPath, requestedFilter, bitwiseOperator, convertValue, messy, undo, redraw, sections = checkArgs()

with open(pngPath, "r+b") as png:
    file = PNGGlitch(png)

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


    file.addFilters(requestedFilter, sections)

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
