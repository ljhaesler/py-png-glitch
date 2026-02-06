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


def finalizeCorruption(scanlines):
    modifiedData = b''.join(scanlines)

    recompressedData = zlib.compress(modifiedData)
    recalculatedLength = len(recompressedData).to_bytes(4)
    recalculatedCRC = zlib.crc32(b'IDAT' + recompressedData)

    png.seek(IDATChunkStart)
    tempRemovedData = png.read()
    png.seek(IDATChunkStart)
    png.truncate()
    png.write(recalculatedLength)
    png.write(b'IDAT')
    png.write(recompressedData)
    png.write(recalculatedCRC.to_bytes(4))
    png.write(tempRemovedData)

def addFilters(scanlines):
    for scanline in scanlines:
        scanline.insert(0, requestedFilter)
    print(f"Scanlines of length {len(scanlines[0])}")
    print(f"Wrote {dictFilter[requestedFilter]} filter to {height} scanlines")
    return scanlines

def bitwiseCorruption(scanlines, operator):
    for scanline in scanlines:
        if operator == "or":
            for byte in range(len(scanline) - 1):
                scanline[byte] |= scanline[byte + 1]
        elif operator == "xor":
            for byte in range(len(scanline) - 1):
                scanline[byte] ^= scanline[byte + 1]
        elif operator == "and":
            for byte in range(len(scanline) - 1):
                scanline[byte] &= scanline[byte + 1]

    return scanlines

def convertToRGBA(scanlines):
    # converts type 2 to type 6
    rgbaScanlines = []
    for scanline in scanlines:
        rgbaScanline = bytearray()
        for byte in range(0, len(scanline), 3):
            rgbaScanline.extend(scanline[byte:byte+3])
            rgbaScanline.append(0x00)
        rgbaScanlines.append(rgbaScanline)
    return rgbaScanlines

def convertToRGB(scanlines):
    # converts type 6 to type 2
    rgbScanlines = []
    for scanline in scanlines:
        rgbScanline = bytearray()
        for byte in range(0, len(scanline), 4):
            rgbScanline.extend(scanline[byte:byte+3])
        rgbScanlines.append(rgbScanline)
    return rgbScanlines

def parseIDATData(png):

    chunkType = None
    IDATData = bytearray()
    IDATQuantity = 0

    while chunkType != b'IEND':
        chunkLength, chunkType = struct.unpack(">I4s", png.read(8))

        # I think simply logging the quantity of each chunk found would be faster, particularly when a single idat chunk exists per scanline
        if chunkType == b'IDAT':
            IDATQuantity += 1
            IDATChunkStart = png.tell() - 8
            data = png.read(chunkLength)
            IDATData.extend(data)
            png.read(4) # read past the CRC value


            remainingData = png.read()
            png.seek(IDATChunkStart)
            png.truncate()
            png.write(remainingData)
            png.seek(IDATChunkStart)
        else:
            print(f"Chunk length: {chunkLength}")
            print(f"Chunk contents: {png.read(chunkLength)}")
            print(f"Skipping chunk...")
            png.seek(4, 1)        # + 4 to skip the chunk CRC as well, 1 defines seek from current position

    print(f"A total of {IDATQuantity} IDAT chunks were found and concatenated.")
    decompressedData = bytearray(zlib.decompress(IDATData))

    return decompressedData, IDATChunkStart


def checkArgs():
    parser = argparse.ArgumentParser(prog="png-glitch", description="Simple-ish tool to corrupt and mess with png files.")

    parser.add_argument('filename')
    parser.add_argument('-f', '--filter', type=int)
    parser.add_argument('-r', '--redraw', type=int)
    parser.add_argument('--ffmpeg', action='store_true')
    parser.add_argument('-b', '--bitwise', type=str)
    parser.add_argument('-c', '--convert', type=int)
    parser.add_argument('--colortype', type=int)

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
    
    return (args.filename, args.filter, args.redraw, args.bitwise, args.convert, args.colortype)

def rewriteColorType(png, setColorType):
    print('Rewriting color type')
    png.seek(25)
    png.write(setColorType.to_bytes(1))
    png.seek(16)
    currentData = png.read(13)
    print(f'Rewriting IHDR CRC')
    newIHDRCrc = zlib.crc32(b'IHDR' + currentData)
    png.write(newIHDRCrc.to_bytes(4))

def rewriteImageWidth(png, width):
    pos = png.tell()
    print('Rewriting image width')
    png.seek(16)
    png.write(width.to_bytes(4))
    png.seek(16)
    currentData = png.read(13)
    print(f'Rewriting IHDR CRC')
    newIHDRCrc = zlib.crc32(b'IHDR' + currentData)
    png.write(newIHDRCrc.to_bytes(4))
    png.seek(pos)

def checkHeader(png):
    print('Reading header')

    header = png.read(8)
    if header != b"\x89PNG\r\n\x1a\n":
        raise ValueError("File header does not indicate a PNG image.")
    
def checkIHDR(png):
    print('Reading IHDR')

    IHDRLength, IHDRType = struct.unpack(">I4s", png.read(8))   # read the next 8 bytes of the file
    if IHDRLength != 13: # necessarily, IHDRLength == 13
        raise ValueError("Unexpected IHDR Chunk length")
    
    IHDRData = png.read(IHDRLength)

    width, height, bitDepth, colorType, compression, filter, interlace = struct.unpack(">IIBBBBB", IHDRData)

    IHDRcrc, = struct.unpack(">I", png.read(4))
    expectedCRC = zlib.crc32(IHDRType + IHDRData)
    print(f"Expected CRC {expectedCRC} | Actual CRC {IHDRcrc}")

    if IHDRcrc != expectedCRC:
        raise ValueError("The expected CRC for the IHDR chunk does not match the CRC present on the file.")

    if bitDepth < 8:
        raise ValueError("Bit depths smaller than 8 are not supported at the moment")



    return (width, height, bitDepth, colorType, compression, filter, interlace)

def printIHDRData():
    print(f"{f"Image Width":<30} : {width}")
    print(f"{f"Image Height":<30} : {height}")
    print(f"{f"Bit Depth":<30} : {bitDepth}")
    print(f"{f"Color Type":<30} : {colorType}")
    print(f"{f"Compression":<30} : {compression}")
    print(f"{f"Filter Method":<30} : {filter}")
    print(f"{f"Interlace Method":<30} : {interlace}")

def extractScanlines(decompressedData):
    scanlines = []
    totalBytes = len(decompressedData)
    if convert == None:
        bytesPerScanline = totalBytes / height
    else:
        bytesPerScanline = dictBytesPerPixel[(convert, bitDepth)] * width + 1
    bytesPerPixel = (bytesPerScanline - 1 ) / width

    print(f"total bytes: {totalBytes} | bpsl: {bytesPerScanline} | bpp: {bytesPerPixel}")

    for i in range(0, totalBytes, int(bytesPerScanline)):
        # should remove all filter bytes from the scanlines
        scanline = decompressedData[i:i + int(bytesPerScanline)]
        del scanline[0]
        
        scanlines.append(scanline)
    print(f"Scanlines of length {len(scanlines[0])}")
    return scanlines

pngPath, requestedFilter, redraw, bitwise, convert, setColorType = checkArgs()

dictBytesPerPixel = {
    (0, 8): 1,
    (2, 8): 3,
    (3, 8): 1,
    (4, 8): 2,
    (6, 8): 4,
    (0, 16): 2,
    (2, 16): 6,
    (3, 16): 2,
    (4, 16): 4,
    (6, 16): 8
}

dictFilter = {
    0: "None",
    1: "Sub",
    2: "Up",
    3: "Average",
    4: "Paeth"
}

with open(pngPath, "r+b") as png:
    checkHeader(png)        # read the first 8 bytes of the png file, expected as b"\x89PNG\r\n\x1a\n"

    width, height, bitDepth, colorType, compression, filter, interlace = checkIHDR(png)

    decompressedData, IDATChunkStart = parseIDATData(png)

    scanlines = extractScanlines(decompressedData)

    if convert != None:
        if convert == 2:
            scanlines = convertToRGB(scanlines)
        elif convert == 6:
            scanlines = convertToRGBA(scanlines)
        rewriteColorType(png, convert)

    if bitwise:
        scanlines = bitwiseCorruption(scanlines, bitwise)

    scanlines = addFilters(scanlines)

    finalizeCorruption(scanlines)

    print(f'Glitched: "{pngPath}" successfully')
    printIHDRData()
    


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
