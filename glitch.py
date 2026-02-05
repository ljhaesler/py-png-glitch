#   
#   
#   
#   
#   



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
    print(f"Wrote {dictFilter[requestedFilter]} filter to {height} scanlines")

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
        scanline[0] = requestedFilter
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

def convertFromRGBA(scanlines):
    rgbScanlines = []
    for scanline in scanlines:
        rgbScanline = bytearray()
        for byte in range(1, len(scanline), 4):
            rgbScanline.extend(scanline[byte:byte+3])
        rgbScanline.insert(0, 0x00)
        rgbScanlines.append(rgbScanline)
    return rgbScanlines

def parseIDATData(png):

    chunkType = None
    IDATData = bytearray()

    while chunkType != b'IEND':
        chunkLength, chunkType = struct.unpack(">I4s", png.read(8))

        # I think simply logging the quantity of each chunk found would be faster, particularly when a single idat chunk exists per scanline
        print(f"Chunk found: {chunkType}")
        if chunkType == b'IDAT':
            IDATChunkStart = png.tell() - 8
            data = png.read(chunkLength)
            IDATData.extend(data)
            dataCRC, = struct.unpack(">I", png.read(4))

            print(f"Expected CRC {zlib.crc32(chunkType + data)} | Actual CRC {dataCRC}")

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

    decompressedData = bytearray(zlib.decompress(IDATData))

    return decompressedData, IDATChunkStart


def checkArgs():
    parser = argparse.ArgumentParser(prog="png-glitch", description="Simple-ish tool to corrupt and mess with png files.")

    parser.add_argument('filename')
    parser.add_argument('-f', '--filter', type=int)
    parser.add_argument('-r', '--redraw', type=int)
    parser.add_argument('--ffmpeg', action='store_true')
    parser.add_argument('-b', '--bitwise', type=str)
    parser.add_argument('-c', '--convert', action='store_true')
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

def rewriteColorType(png, colortype):
    print('Rewriting color type to standard RGB')
    png.seek(25)
    png.write(colortype.to_bytes(1))
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

    print(f"{f"Image Width":<30} : {width}")
    print(f"{f"Image Height":<30} : {height}")
    print(f"{f"Bit Depth":<30} : {bitDepth}")
    print(f"{f"Color Type":<30} : {colorType}")
    print(f"{f"Compression":<30} : {compression}")
    print(f"{f"Filter Method":<30} : {filter}")
    print(f"{f"Interlace Method":<30} : {interlace}")
    IHDRcrc, = struct.unpack(">I", png.read(4))
    expectedCRC = zlib.crc32(IHDRType + IHDRData)
    print(f"Expected CRC {expectedCRC} | Actual CRC {IHDRcrc}")

    if IHDRcrc != expectedCRC:
        raise ValueError("The expected CRC for the IHDR chunk does not match the CRC present on the file.")

    if bitDepth < 8:
        raise ValueError("Bit depths smaller than 8 are not supported at the moment")
    
    if colorType == 3:
        raise ValueError("Indexed color unsupported at the moment")


    return (width, height, bitDepth, colorType, compression, filter, interlace)

pngPath, requestedFilter, redraw, bitwise, convert, colortype = checkArgs()

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

    scanlines = []                                  # IDAT chunks will be decompressed and each scanline appended to this list
    
    if colortype:
        rewriteColorType(png, colortype)

    bytesPerPixel = dictBytesPerPixel[(colorType, bitDepth)]
    scanlineSize = (width * bytesPerPixel + 1) + (redraw if redraw != None else 0) 
    print(f"Defined size of each scan line {scanlineSize}")

    decompressedData, IDATChunkStart = parseIDATData(png)
    expectedDataSize = (width * bytesPerPixel + 1) * height

    print(f"{float(scanlineSize - 1)} | {(len(decompressedData) - height) / height}")

    # if float(scanlineSize - 1) != (len(decompressedData) - height) / height:
    #     newWidth = math.ceil((scanlineSize - 1) / bytesPerPixel)
    #     print(f"A width of {newWidth} px for the image would be recommended")
    #     rewriteImageWidth(png, newWidth)


    for i in range(0, len(decompressedData), width * bytesPerPixel + 1):
        scanlines.append(decompressedData[i:i + width * bytesPerPixel + 1])

    if convert:
        # this conversion is inherently lossy. Each 4th pixel in the png file is lost permanently.
        # It is best to only convert the image after rewriting the color type as desired, as rewriting the colortype isn't lossy
        scanlines = convertFromRGBA(scanlines)
        rewriteColorType(png, 2)

    if bitwise:
        scanlines = bitwiseCorruption(scanlines, bitwise)

    scanlines = addFilters(scanlines)

    finalizeCorruption(scanlines)

    
    print(f'Glitched: "{pngPath}" successfully')

    # image = Image.open(png)
    # image.show()
