import struct
import zlib
import sys
import subprocess
import random
import argparse
import math

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
    
    return (args.filename, args.filter, args.redraw)

def rewriteColorType(png):
    print('Rewriting color type to standard RGB')
    png.seek(25)
    png.write(b'\x02')
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
    
    if colorType == 6:
        rewriteColorType(png)

    return (width, height, bitDepth, colorType, compression, filter, interlace)

pngPath, requestedFilter, redraw = checkArgs()

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

    bytesPerPixel = dictBytesPerPixel[(colorType, bitDepth)]
    scanlineSize = (width * bytesPerPixel + 1) + (redraw if redraw != None else 0) 
    print(f"Defined size of each scan line {scanlineSize}")
    # If an offset is set, some cool effects can be generated. the offset must then be set back to 0 in order to display the png file
    # this offset can be more easily be implemented by simply messing with the height/width in IHDR
    # the weirder effects were due to how rgbScanlines were calculated
    # I think that using some bitwise operations could have the same effect

    decompressedData, IDATChunkStart = parseIDATData(png)
    expectedDataSize = (width * bytesPerPixel + 1) * height

    print(f"{float(scanlineSize - 1)} | {(len(decompressedData) - height) / height}")

    if float(scanlineSize - 1) != (len(decompressedData) - height) / height:
        newWidth = math.ceil((scanlineSize - 1) / bytesPerPixel)
        print(f"A width of {newWidth} px for the image would be recommended")
        rewriteImageWidth(png, newWidth)

    scanlines = []                                  # IDAT chunks will be decompressed and each scanline appended to this list

    for i in range(0, len(decompressedData), width * bytesPerPixel + 1):
        scanlines.append(decompressedData[i:i + width * bytesPerPixel + 1])

    rgbScanlines = []

    for scanline in scanlines:
        if colorType == 6:
            
            rgbScanline = bytearray()
            for j in range(1, len(scanline), 4):
                # implement bitwise operation logic here
                rgbScanline.extend(scanline[j:j+3])
            rgbScanline.insert(0, requestedFilter)
            rgbScanlines.append(rgbScanline)
        else:
            scanline[0] = requestedFilter

    if colorType == 6:
        modifiedData = b''.join(rgbScanlines)
    else:
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
    print(f'Glitched: "{pngPath}" successfully')
