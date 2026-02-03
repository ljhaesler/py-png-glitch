import struct
import zlib
import sys
import subprocess
import random

def checkArgs():
    pngPath = sys.argv[1] if len(sys.argv) > 1 else -1
    requestedFilter = int(sys.argv[2]) if len(sys.argv) > 2 else -1
    forceffmpeg = sys.argv[3].lower() if len(sys.argv) > 3 else -1
    ffmpegout = sys.argv[4] if len(sys.argv) > 4 else 'files/ffmpegoutput.png'

    if pngPath == -1:
        raise ValueError('A path to the PNG file must be specified')

    if requestedFilter not in [0, 1, 2, 3, 4]:
        raise ValueError("A filter type from 0-4 must be specified.")
    
    if forceffmpeg == "force":
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel", "panic",
                "-y",                 # overwrite output
                "-i", pngPath,
                "-pred", str(requestedFilter),
                ffmpegout
            ],
            check=True
        )
        print(f"File written to '{ffmpegout}' with requested FFmpeg filters")
        exit(0)
    
    return (pngPath, requestedFilter)

def rewriteColorType(png):
    print('Rewriting color type to standard RGB')
    png.seek(25)
    png.write(b'\x02')
    png.seek(16)
    currentData = png.read(13)
    print(f'Rewriting IHDR CRC')
    newIHDRCrc = zlib.crc32(b'IHDR' + currentData)
    png.write(newIHDRCrc.to_bytes(4))

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

    if bitDepth != 8:
        raise ValueError("Bit depths smaller than 8 are not supported at the moment")

    if colorType == 3:
        raise ValueError("Indexed color unsupported at the moment")
    
    if colorType == 6:
        rewriteColorType(png)

    return (width, height, bitDepth, colorType, compression, filter, interlace)

pngPath, requestedFilter = checkArgs()

with open(pngPath, "r+b") as png:

    checkHeader(png)        # read the first 8 bytes of the png file, expected as b"\x89PNG\r\n\x1a\n"
    width, height, bitDepth, colorType, compression, filter, interlace = checkIHDR(png)

    dictPerPixel = {
        0: 1,
        2: 3,
        3: 1,
        4: 2,
        6: 4
    }

    dictFilter = {
        0: "None",
        1: "Sub",
        2: "Up",
        3: "Average",
        4: "Paeth"
    }

    bytesPerPixel = dictPerPixel[colorType]
    scanlineSize = (width * bytesPerPixel + 1) # + 255 # when converting from colorType 6, if an offset is set, some cool effects can be generated. the offset must then be set back to 0 in order to display the png file
    IDATs = bytearray()
    scanlines = []                                  # IDAT chunks will be decompressed and each scanline appended to this list
    print(f"Expected size of each scan line {scanlineSize}")

    chunkType = None

    while chunkType != b'IEND':
        chunkLength, chunkType = struct.unpack(">I4s", png.read(8))
        print(f"Chunk found: {chunkType}")
        if chunkType == b'IDAT':
            IDATChunkStart = png.tell() - 8
            data = png.read(chunkLength)
            IDATs.extend(data)
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


    expectedDataSize = scanlineSize * height
    decompressedData = bytearray(zlib.decompress(IDATs))
    print(f"Expected size of decompressed data {expectedDataSize} | Actual size of decompressed data {len(decompressedData)}")

    for i in range(0, len(decompressedData), scanlineSize):
        scanlines.append(decompressedData[i:i + scanlineSize])

    rgbScanlines = bytearray()

    for scanline in scanlines:
        z = 0
        if colorType == 6:
            rgbScanline = bytearray()
            for j in range(1, len(scanline), 4):
                rgbScanline.extend(scanline[j:j+3])
            rgbScanline.insert(0, requestedFilter)
            rgbScanlines.extend(rgbScanline)
        else:
            scanline[0] = requestedFilter

    if colorType == 6:
        modifiedData = rgbScanlines
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
    print('Success')
