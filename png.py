import struct
import random
import zlib

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

IHDRFields = {
    "width": 16,
    "height": 20,
    "bitDepth": 24,
    "colorType": 25,
    "compression": 26,
    "interlace": 27,
    "filter": 28 
}

class PNGGlitch:
    IHDRStart: int
    IHDREnd: int
    width: int
    height: int
    bitDepth: int
    colorType: int
    compression: int
    filter: int
    interlace: int
    bpp: int
    IDATChunkStart: int
    decompressedData: bytearray
    unfilteredData: bytearray
    filteredData: bytearray

    def __init__(self, png):
        self.png = png
        self.baseFilters = []
        self.IHDRStart = 8
        self.IHDREnd = 33

    def start(self):
        self.checkHeader()
        self.checkIHDR()
        self.parseIDATData()
        self.removeFilters()

    def finish(self):
        self.printIHDRData()
        recompressedData = zlib.compress(self.filteredData)
        recalculatedLength = len(recompressedData).to_bytes(4)
        recalculatedCRC = zlib.crc32(b'IDAT' + recompressedData)

        self.png.seek(self.IDATChunkStart)
        tempRemovedData = self.png.read()
        self.png.seek(self.IDATChunkStart)
        self.png.truncate()
        self.png.write(recalculatedLength)
        self.png.write(b'IDAT')
        self.png.write(recompressedData)
        self.png.write(recalculatedCRC.to_bytes(4))
        self.png.write(tempRemovedData)

    def checkHeader(self):
        print('Reading header')
        self.png.seek(0)
        self.header = self.png.read(8)
        
    def checkIHDR(self):
        self.png.seek(self.IHDRStart)

        IHDRLength, IHDRType = struct.unpack(">I4s", self.png.read(8))

        if IHDRLength != 13: # necessarily, IHDRLength == 13
            raise ValueError("Unexpected IHDR Chunk length")
        
        if IHDRType != b'IHDR':
            raise ValueError("Unexpected chunk type, not valid IHDR chunk")

        IHDRData = self.png.read(IHDRLength)

        self.width, self.height, self.bitDepth, self.colorType, self.compression, self.filter, self.interlace = struct.unpack(">IIBBBBB", IHDRData)
        self.bpp = dictBytesPerPixel[(self.colorType, self.bitDepth)]

        if self.bitDepth < 8:
            raise ValueError("Bit depths smaller than 8 are not supported at the moment")
        
    def parseIDATData(self):
        chunkType = None
        IDATQuantity = 0
        IDATData = bytearray()

        self.png.seek(self.IHDREnd)

        while chunkType != b'IEND':
            chunkLength, chunkType = struct.unpack(">I4s", self.png.read(8))

            if chunkType == b'IDAT':
                IDATQuantity += 1
                self.IDATChunkStart = self.png.tell() - 8
                data = self.png.read(chunkLength)
                IDATData.extend(data)
                self.png.read(4) 

                # code to delete idat chunks for when they are rewritten as a single IDAT chunk at the end of the corruption.
                remainingData = self.png.read()
                self.png.seek(self.IDATChunkStart)
                self.png.truncate()
                self.png.write(remainingData)
                self.png.seek(self.IDATChunkStart)
            else:
                print(f'Chunk found: {chunkType} | Skipping chunk...')
                self.png.read(chunkLength)
                self.png.seek(4, 1)        # + 4 to skip the chunk CRC as well, 1 defines seek from current position

        print(f"A total of {IDATQuantity} IDAT chunks were found and concatenated.")
        self.decompressedData = bytearray(zlib.decompress(IDATData))

    def removeFilters(self):
        unfilteredData = bytearray()
        lengthTotalData = len(self.decompressedData)
        bytesPerScanline = self.bpp * self.width + 1

        for i in range(0, lengthTotalData, bytesPerScanline):
            scanline = self.decompressedData[i:i + bytesPerScanline]
            self.baseFilters.insert(0, scanline[0])
            del scanline[0]

            unfilteredData.extend(scanline)

        self.unfilteredData = unfilteredData

    def addFilters(self, filter, sections):
        filteredData = bytearray()
        lengthUnfilteredData = len(self.unfilteredData)
        bytesPerUnfilteredScanline = self.bpp * self.width
        if filter == 'keep':
            for i in range (0, lengthUnfilteredData, bytesPerUnfilteredScanline):
                scanline = self.unfilteredData[i: i + bytesPerUnfilteredScanline]
                scanline.insert(0, self.baseFilters.pop())

                filteredData.extend(scanline)
        elif filter == 'random':
            scanlines = []

            for i in range (0, lengthUnfilteredData, bytesPerUnfilteredScanline):
                scanline = self.unfilteredData[i: i + bytesPerUnfilteredScanline]
                scanlines.append(scanline)

            sections = sections if sections else 1
            scanlineSections = len(scanlines) // sections

            for i in range(sections):
                filterValue = random.randint(1, 4)
                start = i * scanlineSections
                end = ((i + 1) * scanlineSections if i < sections - 1 else len(scanlines))

                for j in range(start, end):
                    scanlines[j].insert(0, filterValue)

            filteredData = b''.join(scanlines)
        else:
            filter = int(filter)
            for i in range (0, lengthUnfilteredData, bytesPerUnfilteredScanline):
                scanline = self.unfilteredData[i: i + bytesPerUnfilteredScanline]
                scanline.insert(0, filter)

                filteredData.extend(scanline)

        self.filteredData = filteredData

    def writeIHDR(self, field, value):
        initialFileLocation = self.png.tell()

        print(f'Rewriting {field} to {value}')
        self.png.seek(IHDRFields[field])

        if field == "width" or field == "height":
            self.png.write(value.to_bytes(4))
        else:
            self.png.write(value.to_bytes(1))

        # code to rewrite IHDR CRC
        self.png.seek(16)
        currentData = self.png.read(13)
        newIHDRCrc = zlib.crc32(b'IHDR' + currentData)
        self.png.write(newIHDRCrc.to_bytes(4))

        # needed to update self values
        self.checkIHDR()
        # return to previous location
        self.png.seek(initialFileLocation)

    def messyConvert(self):
        # when a messy conversion is wanted, it's important to have excess pixels/padding pixels to work with
        # if the colortype of the original png is 2, then when attempting a messy conversion to type 6, the image will be undersized.
        # => 3 bpp cannot display 4 bpp at the same resolution
        # the simplest way around this is by padding 3 bpp to 4 bpp beforehand via convertColorType
        # then setColorType to 2 and convertColorType back to 2
        # the issue being, there are many bytes of data that remain 'unused'
        if self.colorType == 6:
            # 4 bpp will be read as 3 bpp, 
            self.writeIHDR('colorType', 2)
            # convert the resulting 3 bpp image into a 'real' 3 bpp image ( this actually does nothing... )
            # I think I just have to forget about colorTypes other than 2 or 6, because the current way the conversion is implemented ruins this process.
            # on the other hand, it does mean that the process can be entirely undone, as no data is actually deleted.
            self.convertColorType(2)
        else:
            self.convertColorType(6)
            self.writeIHDR('colorType', 2)
            # again, does nothing
            self.convertColorType(2)

    def undoMessyConvert(self):
        if self.colorType == 6:
            self.convertColorType(2)
            self.writeIHDR('colorType', 6)
            ##
            self.convertColorType(2)
        else:
            self.writeIHDR('colorType', 6)
            ##
            self.convertColorType(2)

    def convertColorType(self, chosenType):
        newBPP = dictBytesPerPixel[(chosenType, self.bitDepth)]
        currentBPP = self.bpp

        newBytes = bytearray()

        if currentBPP >= newBPP:
            for i in range(0, len(self.unfilteredData), self.bpp):
                # this will destroy data, the bytes are lost permanently
                newByte = self.unfilteredData[i:i + newBPP]
                newBytes.extend(newByte)
        else:
            for i in range(0, len(self.unfilteredData), self.bpp):
                newByte = self.unfilteredData[i:i + self.bpp]
                newByte.extend(b'\xFF' * (newBPP - currentBPP))
                newBytes.extend(newByte)

        self.unfilteredData = newBytes
        self.writeIHDR("colorType", chosenType)

    def printIHDRData(self):
        print(f"{f"Image Width":<30} : {self.width}")
        print(f"{f"Image Height":<30} : {self.height}")
        print(f"{f"Bit Depth":<30} : {self.bitDepth}")
        print(f"{f"Color Type":<30} : {self.colorType}")
        print(f"{f"Compression":<30} : {self.compression}")
        print(f"{f"Filter Method":<30} : {self.filter}")
        print(f"{f"Interlace Method":<30} : {self.interlace}")
        print(f"Expected length of data: {self.bpp * self.height * self.width + self.height} | Actual length of data: {len(self.filteredData)}")

    def bitwiseCorrupt(self, operator):
        # must be on the unfilteredData, otherwise filter bytes will get corrupted and the PNG becomes unreadable
        if operator == "or":
            for i in range(len(self.unfilteredData) - 1):
                self.unfilteredData[i] |= self.unfilteredData[i + 1]
        elif operator == "xor":
            for i in range(len(self.unfilteredData) - 1):
                self.unfilteredData[i] ^= self.unfilteredData[i + 1]
        elif operator == "and":
            for i in range(len(self.unfilteredData) - 1):
                self.unfilteredData[i] &= self.unfilteredData[i + 1]
        elif operator == "rshift":
            for i in range(len(self.unfilteredData)):
                self.unfilteredData[i] = self.unfilteredData[i] >> 1 
        elif operator == "lshift":
            for i in range(len(self.unfilteredData)):
                self.unfilteredData[i] = (self.unfilteredData[i] << 1) & 0xFF
        elif operator == "invert":
            for i in range(len(self.unfilteredData)):
                self.unfilteredData[i] ^= 0xFF
        elif operator == "swap":
            for i in range(len(self.unfilteredData) - 3):
                self.unfilteredData[i] = self.unfilteredData[i + 1]
        elif operator == "noise":
            for i in range(len(self.unfilteredData)):
                if self.unfilteredData[i] < 32:
                    self.unfilteredData[i] = random.randint(0, 3)
                    # even a tiny amount of noise seems to ruin the output after filtering
                    # some cool effects can be achieved extremely small values however
                elif self.unfilteredData[i] > 223:
                    self.unfilteredData[i] = random.randint(252, 255)

    def offsetCorrupt(self):
        scanlines = []
        lengthUnfilteredData = len(self.unfilteredData)
        bytesPerScanline = self.bpp * self.width

        for i in range(0, lengthUnfilteredData, bytesPerScanline):
            scanline = self.decompressedData[i:i + bytesPerScanline]
            scanlines.append(scanline)

        for i in range(len(scanlines)):
            scanlines[i] = scanlines[i][-i:] + scanlines[i][:-i]

        self.unfilteredData = bytearray(b''.join(scanlines))

        
